"""测试共享 JSON-lines worker transport 的协议与失败状态机。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
import json
import os
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.worker_transport import (
    JsonLinesWorkerTransport,
    WorkerCommandError,
)


pytestmark = pytest.mark.unit


_WORKER_SCRIPT = r"""
import json
import sys
import time

mode = sys.argv[1]
for raw in sys.stdin:
    request = json.loads(raw)
    request_id = request["request_id"]
    if mode == "success":
        response = {
            "request_id": request_id,
            "ok": True,
            "result": {"payload": request["payload"], "raw": raw.rstrip("\n")},
        }
        print(json.dumps(response, ensure_ascii=False), flush=True)
        continue
    if mode == "stderr_many":
        for index in range(5):
            print(f"diagnostic-{index} secret=s3cr3t", file=sys.stderr, flush=True)
        print(json.dumps({"request_id": request_id, "ok": True, "result": {}}), flush=True)
        continue
    if mode == "bad_json":
        print("not-json", flush=True)
        time.sleep(5)
        continue
    if mode == "mismatch":
        print(json.dumps({"request_id": request_id + 1, "ok": True, "result": {}}), flush=True)
        time.sleep(5)
        continue
    if mode == "failure":
        response = {
            "request_id": request_id,
            "ok": False,
            "error_type": "Boom",
            "error": "bad input",
        }
        print(json.dumps(response), flush=True)
        continue
    if mode == "failure_details":
        response = {
            "request_id": request_id,
            "ok": False,
            "error_type": "Boom",
            "error": "bad input",
            "error_details": {"llm_observations": [{"input_tokens": 3, "output_tokens": 1}]},
        }
        print(json.dumps(response), flush=True)
        continue
    if mode == "invalid_result":
        print(json.dumps({"request_id": request_id, "ok": True, "result": []}), flush=True)
        continue
    if mode == "timeout":
        print("secret=s3cr3t", file=sys.stderr, flush=True)
        time.sleep(5)
        continue
    if mode == "closed_stdout":
        print("endpoint=private secret=s3cr3t", file=sys.stderr, flush=True)
        raise SystemExit(7)
"""


def _start_transport(
    tmp_path: Path,
    *,
    mode: str,
    product_label: str = "Example",
    timeout_seconds: float = 1.0,
    timeout_detail: str | None = "cleanup before retry",
    sort_keys: bool = False,
    terminate_on_timeout: bool = True,
    terminate_on_protocol_error: bool = True,
    forget_process_on_terminate: bool = False,
    diagnostic_log_path: Path | None = None,
    stderr_tail_lines: int = 80,
) -> JsonLinesWorkerTransport:
    """启动一个不访问网络的最小协议 worker。"""

    transport = JsonLinesWorkerTransport(
        product_label=product_label,
        request_timeout_seconds=timeout_seconds,
        timeout_detail=timeout_detail,
        request_sort_keys=sort_keys,
        stderr_tail_char_limit=2000,
        stderr_tail_lines=stderr_tail_lines,
        terminate_on_timeout=terminate_on_timeout,
        terminate_on_protocol_error=terminate_on_protocol_error,
        forget_process_on_terminate=forget_process_on_terminate,
        diagnostic_log_path=diagnostic_log_path,
    )
    transport.start(
        argv=[sys.executable, "-u", "-c", _WORKER_SCRIPT, mode],
        cwd=tmp_path,
        env=dict(os.environ),
        stderr_thread_name=f"test-worker-{mode}-stderr",
        stderr_redactor=lambda line: line.replace("s3cr3t", "<redacted>"),
    )
    return transport


def test_worker_transport_persists_full_redacted_stderr_beyond_tail(
    tmp_path: Path,
) -> None:
    """worker stderr 全量写 method.log，失败摘要仍只保留有限脱敏 tail。"""

    log_path = tmp_path / "logs" / "method.log"
    transport = _start_transport(
        tmp_path,
        mode="stderr_many",
        diagnostic_log_path=log_path,
        stderr_tail_lines=2,
    )
    try:
        assert transport.request("ingest", {}) == {}
    finally:
        transport.terminate()

    content = log_path.read_text(encoding="utf-8")
    for index in range(5):
        assert f"diagnostic-{index} secret=<redacted>" in content
    assert "s3cr3t" not in content
    assert len(transport.stderr_tail) == 2
    assert transport.stderr_tail[0].startswith("diagnostic-3")


def test_worker_transport_preserves_request_bytes_order_and_sequence(
    tmp_path: Path,
) -> None:
    """成功路径应保持 Unicode、sort policy 与单 transport 递增 request id。"""

    transport = _start_transport(tmp_path, mode="success", sort_keys=True)
    try:
        first = transport.request("ingest", {"z": "上海", "a": 1})
        second = transport.request("retrieve", {"query": "哪里？"})
    finally:
        transport.terminate()

    assert first["payload"] == {"z": "上海", "a": 1}
    assert first["raw"] == json.dumps(
        {
            "request_id": 1,
            "command": "ingest",
            "payload": {"z": "上海", "a": 1},
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    assert json.loads(second["raw"])["request_id"] == 2


def test_worker_transport_serializes_concurrent_callers(tmp_path: Path) -> None:
    """多线程调用必须由一把锁串行化，response 不得串题。"""

    transport = _start_transport(tmp_path, mode="success")
    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(
                    lambda index: transport.request("echo", {"index": index}),
                    range(8),
                )
            )
    finally:
        transport.terminate()

    assert {result["payload"]["index"] for result in results} == set(range(8))
    assert sorted(json.loads(result["raw"])["request_id"] for result in results) == (
        list(range(1, 9))
    )


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("failure", "Example worker ingest failed [Boom]: bad input"),
        ("invalid_result", "Example worker result must be an object"),
    ],
)
def test_worker_transport_rejects_worker_failure_and_invalid_result(
    tmp_path: Path,
    mode: str,
    message: str,
) -> None:
    """业务失败与非法 result 均不得被伪装成成功对象。"""

    transport = _start_transport(tmp_path, mode=mode)
    try:
        with pytest.raises(ConfigurationError, match=message.replace("[", r"\[")):
            transport.request("ingest", {})
        assert transport.is_running
    finally:
        transport.terminate()


def test_worker_transport_exposes_validated_failure_details(tmp_path: Path) -> None:
    """worker 可把脱敏结构化 usage 随业务异常交给 adapter，不能伪装 result。"""

    transport = _start_transport(tmp_path, mode="failure_details")
    try:
        with pytest.raises(WorkerCommandError) as raised:
            transport.request("ingest", {})
        assert raised.value.error_type == "Boom"
        assert raised.value.details == {
            "llm_observations": [{"input_tokens": 3, "output_tokens": 1}]
        }
        assert transport.is_running
    finally:
        transport.terminate()


def test_worker_transport_bad_json_terminates_and_forgets_by_policy(
    tmp_path: Path,
) -> None:
    """EverOS 风格协议污染应立即终止并允许显式清 root 后重启 transport。"""

    transport = _start_transport(
        tmp_path,
        mode="bad_json",
        forget_process_on_terminate=True,
    )

    with pytest.raises(ConfigurationError, match="protocol was polluted"):
        transport.request("ingest", {})

    assert not transport.has_process
    transport.terminate()


def test_worker_transport_identity_mismatch_terminates_but_retains_failure_handle(
    tmp_path: Path,
) -> None:
    """Graphiti/LangMem 风格协议错配应终止且保留退出对象以拒绝隐式重启。"""

    transport = _start_transport(tmp_path, mode="mismatch")

    with pytest.raises(ConfigurationError, match="response identity mismatch"):
        transport.request("retrieve", {})

    assert transport.has_process
    assert not transport.is_running
    transport.terminate()


def test_worker_transport_timeout_policy_preserves_letta_lifecycle_ownership(
    tmp_path: Path,
) -> None:
    """Letta timeout 只报错，不得越权替产品 Docker cleanup 提交终止政策。"""

    transport = _start_transport(
        tmp_path,
        mode="timeout",
        product_label="Letta",
        timeout_seconds=0.05,
        timeout_detail=None,
        terminate_on_timeout=False,
        terminate_on_protocol_error=False,
    )
    try:
        with pytest.raises(
            ConfigurationError,
            match="Letta worker command timed out: ingest$",
        ):
            transport.request("ingest", {})
        assert transport.is_running
    finally:
        transport.terminate()


def test_worker_transport_timeout_can_terminate_for_journaled_products(
    tmp_path: Path,
) -> None:
    """有 clean-retry authority 的产品可要求 timeout 后立即杀 worker。"""

    transport = _start_transport(
        tmp_path,
        mode="timeout",
        product_label="LangMem",
        timeout_seconds=0.05,
        timeout_detail="the operation journal remains the only resume authority",
        forget_process_on_terminate=True,
    )

    with pytest.raises(
        ConfigurationError,
        match=(
            "LangMem worker command timed out: ingest; "
            "the operation journal remains the only resume authority"
        ),
    ):
        transport.request("ingest", {})

    assert not transport.has_process


def test_worker_transport_early_exit_keeps_only_redacted_stderr_tail(
    tmp_path: Path,
) -> None:
    """stdout 提前关闭时诊断尾部可追溯，但 secret 不得进入错误面。"""

    transport = _start_transport(tmp_path, mode="closed_stdout")
    try:
        with pytest.raises(ConfigurationError, match="closed stdout"):
            transport.request("ingest", {})
        deadline = monotonic() + 1.0
        while not transport.stderr_tail and monotonic() < deadline:
            sleep(0.01)
        failure = transport.failure_text("exited")
    finally:
        transport.terminate()

    assert "s3cr3t" not in failure
    assert "secret=<redacted>" in failure
    assert "endpoint=private" in failure


def test_worker_transport_terminate_is_idempotent(tmp_path: Path) -> None:
    """transport 资源回收可重复调用，但不会把它解释为产品 shutdown 成功。"""

    transport = _start_transport(
        tmp_path,
        mode="timeout",
        forget_process_on_terminate=True,
    )

    transport.terminate()
    transport.terminate()

    assert not transport.has_process


def test_worker_transport_kills_process_that_ignores_terminate() -> None:
    """忽略 terminate 的 worker 必须进入 kill fallback 并关闭三条 pipe。"""

    class StubbornProcess:
        """模拟忽略 terminate、只响应 kill 的 Popen。"""

        def __init__(self) -> None:
            """建立三条可核对关闭状态的文本 pipe。"""

            self.stdin = StringIO()
            self.stdout = StringIO()
            self.stderr = StringIO()
            self.terminate_calls = 0
            self.kill_calls = 0
            self.killed = False

        def poll(self) -> int | None:
            """kill 前始终报告运行中。"""

            return -9 if self.killed else None

        def terminate(self) -> None:
            """记录但忽略温和终止。"""

            self.terminate_calls += 1

        def kill(self) -> None:
            """记录强制终止。"""

            self.kill_calls += 1
            self.killed = True

        def wait(self, timeout: float) -> int:
            """kill 前模拟超时，kill 后返回退出码。"""

            if not self.killed:
                raise subprocess.TimeoutExpired(cmd="worker", timeout=timeout)
            return -9

    transport = JsonLinesWorkerTransport(
        product_label="Example",
        request_timeout_seconds=1.0,
        timeout_detail=None,
        forget_process_on_terminate=True,
    )
    process = StubbornProcess()
    transport._process = process  # type: ignore[assignment]

    transport.terminate()

    assert process.terminate_calls == 1
    assert process.kill_calls == 1
    assert process.stdin.closed
    assert process.stdout.closed
    assert process.stderr.closed
    assert not transport.has_process


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"product_label": " "}, "product_label must not be blank"),
        ({"request_timeout_seconds": 0}, "request_timeout_seconds must be positive"),
        ({"stderr_tail_lines": 0}, "stderr_tail_lines must be positive"),
        ({"stderr_tail_char_limit": 0}, "stderr_tail_char_limit must be positive"),
    ],
)
def test_worker_transport_rejects_invalid_policy(
    kwargs: dict[str, object],
    message: str,
) -> None:
    """无效 policy 必须在启动子进程前 fail-fast。"""

    values: dict[str, object] = {
        "product_label": "Example",
        "request_timeout_seconds": 1.0,
        "timeout_detail": None,
    }
    values.update(kwargs)

    with pytest.raises(ValueError, match=message):
        JsonLinesWorkerTransport(**values)  # type: ignore[arg-type]
