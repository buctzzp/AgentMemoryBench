"""隔离 method worker 共用的主进程 JSON-lines transport。

本模块只拥有子进程 pipe、请求序号、stdout 协议、stderr 诊断尾部、timeout 与
尽力终止。产品环境、initialize/shutdown payload、数据库生命周期、namespace 和
业务完成门仍由各 method runtime 显式负责。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Sequence
import json
from pathlib import Path
import selectors
import subprocess
import threading
from typing import Any

from memory_benchmark.core import ConfigurationError


WORKER_TRANSPORT_LOGICAL_PATH = (
    "src/memory_benchmark/methods/worker_transport.py"
)


class JsonLinesWorkerTransport:
    """管理一个可重启 worker 的严格串行 JSON-lines 通道。"""

    def __init__(
        self,
        *,
        product_label: str,
        request_timeout_seconds: float,
        timeout_detail: str | None,
        request_sort_keys: bool = False,
        stderr_tail_lines: int = 80,
        stderr_tail_char_limit: int = 3000,
        terminate_on_timeout: bool = True,
        terminate_on_protocol_error: bool = True,
        forget_process_on_terminate: bool = False,
    ) -> None:
        """保存稳定 transport policy。

        启动参数与 secret redactor 延迟到 ``start``。
        """

        if not product_label.strip():
            raise ValueError("product_label must not be blank")
        if request_timeout_seconds <= 0:
            raise ValueError("request_timeout_seconds must be positive")
        if stderr_tail_lines <= 0:
            raise ValueError("stderr_tail_lines must be positive")
        if stderr_tail_char_limit <= 0:
            raise ValueError("stderr_tail_char_limit must be positive")
        self.product_label = product_label
        self.request_timeout_seconds = request_timeout_seconds
        self.timeout_detail = timeout_detail
        self.request_sort_keys = request_sort_keys
        self.stderr_tail_char_limit = stderr_tail_char_limit
        self.terminate_on_timeout = terminate_on_timeout
        self.terminate_on_protocol_error = terminate_on_protocol_error
        self.forget_process_on_terminate = forget_process_on_terminate
        self._process: subprocess.Popen[str] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=stderr_tail_lines)
        self._stderr_redactor: Callable[[str], str] = lambda text: text
        self._request_lock = threading.Lock()
        self._request_sequence = 0

    @property
    def process(self) -> subprocess.Popen[str] | None:
        """返回当前或最后一个子进程，供产品 lifecycle 核对退出状态。"""

        return self._process

    @property
    def has_process(self) -> bool:
        """返回 transport 是否仍持有一个子进程对象。"""

        return self._process is not None

    @property
    def is_running(self) -> bool:
        """返回当前子进程是否仍在运行。"""

        return self._process is not None and self._process.poll() is None

    @property
    def stderr_tail(self) -> tuple[str, ...]:
        """返回已脱敏 stderr 尾部的只读快照。"""

        return tuple(self._stderr_tail)

    def start(
        self,
        *,
        argv: Sequence[str],
        cwd: Path,
        env: dict[str, str],
        stderr_thread_name: str,
        stderr_redactor: Callable[[str], str],
    ) -> None:
        """启动一个 stdio worker，并立即后台排空其 stderr。"""

        if self._process is not None:
            if self._process.poll() is None:
                raise ConfigurationError(
                    f"{self.product_label} worker is already running"
                )
            raise ConfigurationError(self.failure_text("exited"))
        self._stderr_redactor = stderr_redactor
        self._process = subprocess.Popen(
            list(argv),
            cwd=cwd,
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            name=stderr_thread_name,
            daemon=True,
        )
        self._stderr_thread.start()

    def _drain_stderr(self) -> None:
        """持续排空 stderr，并仅保存调用方脱敏后的有限尾部。"""

        process = self._process
        if process is None or process.stderr is None:
            return
        for line in process.stderr:
            self._stderr_tail.append(self._stderr_redactor(line.rstrip()))

    def request(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送一条请求，并严格验证 response id、状态与 result 形状。"""

        process = self._process
        if process is None or process.stdin is None or process.stdout is None:
            raise ConfigurationError(
                f"{self.product_label} worker is not running"
            )
        with self._request_lock:
            if process.poll() is not None:
                raise ConfigurationError(self.failure_text("exited"))
            self._request_sequence += 1
            request_id = self._request_sequence
            process.stdin.write(
                json.dumps(
                    {
                        "request_id": request_id,
                        "command": command,
                        "payload": payload,
                    },
                    ensure_ascii=False,
                    sort_keys=self.request_sort_keys,
                )
                + "\n"
            )
            process.stdin.flush()
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            try:
                ready = selector.select(self.request_timeout_seconds)
            finally:
                selector.close()
            if not ready:
                if self.terminate_on_timeout:
                    self.terminate()
                message = (
                    f"{self.product_label} worker command timed out: {command}"
                )
                if self.timeout_detail:
                    message += f"; {self.timeout_detail}"
                raise ConfigurationError(message)
            raw = process.stdout.readline()
            if not raw:
                raise ConfigurationError(self.failure_text("closed stdout"))
            try:
                response = json.loads(raw)
            except json.JSONDecodeError as exc:
                if self.terminate_on_protocol_error:
                    self.terminate()
                raise ConfigurationError(
                    f"{self.product_label} worker protocol was polluted: "
                    f"{raw[:200]!r}"
                ) from exc
            if not isinstance(response, dict) or response.get("request_id") != request_id:
                if self.terminate_on_protocol_error:
                    self.terminate()
                raise ConfigurationError(
                    f"{self.product_label} worker response identity mismatch"
                )
            if response.get("ok") is not True:
                raise ConfigurationError(
                    f"{self.product_label} worker {command} failed "
                    f"[{response.get('error_type')}]: {response.get('error')}"
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise ConfigurationError(
                    f"{self.product_label} worker result must be an object"
                )
            return result

    def failure_text(self, state: str) -> str:
        """构造只含脱敏 stderr 尾部的稳定失败摘要。"""

        tail = "\n".join(self._stderr_tail)[-self.stderr_tail_char_limit :]
        return f"{self.product_label} worker {state}; stderr tail: {tail}"

    def wait(self, *, timeout: float) -> int:
        """等待当前子进程退出；没有进程时拒绝伪造成功。"""

        if self._process is None:
            raise ConfigurationError(
                f"{self.product_label} worker is not running"
            )
        return self._process.wait(timeout=timeout)

    def terminate(self, *, forget_process: bool | None = None) -> None:
        """尽力终止子进程并关闭 pipe。

        该操作不代表产品业务 shutdown 成功。
        """

        process = self._process
        if process is None:
            return
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for stream in (process.stdin, process.stdout, process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        should_forget = (
            self.forget_process_on_terminate
            if forget_process is None
            else forget_process
        )
        if should_forget:
            self._process = None


__all__ = ["JsonLinesWorkerTransport", "WORKER_TRANSPORT_LOGICAL_PATH"]
