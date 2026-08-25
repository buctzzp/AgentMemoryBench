"""测试 Letta sleeptime-memory adapter 的 payload、身份与失败边界。"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from typing import Any

import pytest

import memory_benchmark.methods.letta_adapter as letta_adapter_module
from memory_benchmark.config import OpenAISettings, PathSettings, load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    RetrievalQuery,
    SessionBatch,
    SessionRef,
    TurnEvent,
)
from memory_benchmark.methods.letta_adapter import (
    LETTA_ADAPTER_VERSION,
    Letta,
    LettaConfig,
    LettaRuntime,
    _effective_time_prefix,
    _official_message_wrapper,
    build_letta_source_identity,
    clean_letta_conversation_state,
)
from memory_benchmark.methods.worker_transport import WorkerCommandError
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    FailedEfficiencyAttempt,
    LLMCallObservation,
)


pytestmark = pytest.mark.unit


class _FakeRuntime:
    """记录 adapter 请求的 hermetic runtime 替身。"""

    instances: list["_FakeRuntime"] = []

    def __init__(self, **kwargs: Any) -> None:
        """保存构造参数并建立可注入行为。"""

        self.kwargs = kwargs
        self.started = 0
        self.ensure_calls: list[str] = []
        self.ingest_calls: list[dict[str, str]] = []
        self.read_calls: list[dict[str, str | None]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.close_calls = 0
        self.fail_close = False
        self.fail_delete = False
        self.fail_ingest = False
        self.blocks: list[dict[str, Any]] = [
            {
                "id": "block-summary",
                "label": "summary",
                "description": "Summary & status",
                "value": "A short summary.",
            },
            {
                "id": "block-human",
                "label": "human",
                "description": "Human <facts>",
                "value": "Alice lives in Seattle.",
            },
        ]
        self.usage = [
            {"input_tokens": 11, "output_tokens": 3},
            {"input_tokens": 7, "output_tokens": 2},
        ]
        type(self).instances.append(self)

    def ensure_started(self) -> None:
        """记录 prepare/runtime 启动。"""

        self.started += 1

    def ensure_subject(self, subject_id: str) -> dict[str, Any]:
        """返回稳定 subject 资源身份。"""

        self.ensure_calls.append(subject_id)
        return {
            "subject_id": subject_id,
            "agent_id": "agent-1",
            "block_ids": ["block-human", "block-summary"],
            "archive_id": "archive-1",
        }

    def ingest(self, *, subject_id: str, operation_id: str, content: str) -> dict[str, Any]:
        """记录一次 build wrapper 并返回真实 usage 形状。"""

        self.ingest_calls.append(
            {
                "subject_id": subject_id,
                "operation_id": operation_id,
                "content": content,
            }
        )
        if self.fail_ingest:
            raise ConfigurationError("ingest failed after product write")
        return {
            **self.ensure_subject(subject_id),
            "usage": list(self.usage),
            "step_count": len(self.usage),
            "stop_reason": "tool_rule",
        }

    def read_blocks(self, *, subject_id: str, agent_id: str | None) -> dict[str, Any]:
        """返回故意乱序的 core blocks。"""

        self.read_calls.append({"subject_id": subject_id, "agent_id": agent_id})
        return {"agent_id": "agent-1", "blocks": list(self.blocks)}

    def delete_subject(
        self,
        *,
        subject_id: str,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """记录 namespace clean；可注入首轮失败。"""

        self.delete_calls.append({"subject_id": subject_id, "state": state})
        if self.fail_delete:
            raise ConfigurationError("delete failed")
        return {"deleted": True}

    def close(self) -> None:
        """记录 cleanup；可注入失败。"""

        self.close_calls += 1
        if self.fail_close:
            raise ConfigurationError("close failed")


def _config(**overrides: Any) -> LettaConfig:
    """构造最小合法 Letta 配置。"""

    values: dict[str, Any] = {
        "llm_model": "gpt-4o-mini",
        "context_window": 128000,
        "max_tokens": 4096,
        "temperature": 0.0,
        "max_steps": 50,
        "max_messages_per_batch": 10,
        "human_block_limit": 10000,
        "summary_block_limit": 1000,
        "postgres_image": "ankane/pgvector:v0.5.1",
        "postgres_startup_timeout_seconds": 60.0,
        "worker_request_timeout_seconds": 600.0,
        "max_workers": 1,
    }
    values.update(overrides)
    return LettaConfig(**values)


def _paths(root: Path) -> PathSettings:
    """为 fake runtime 构造项目内路径配置。"""

    for relative in ("data", "models", "outputs", "third_party/benchmarks", "third_party/methods"):
        (root / relative).mkdir(parents=True, exist_ok=True)
    return PathSettings(
        project_root=root,
        data_root=root / "data",
        models_root=root / "models",
        outputs_root=root / "outputs",
        third_party_root=root / "third_party",
        third_party_benchmarks_root=root / "third_party/benchmarks",
        third_party_methods_root=root / "third_party/methods",
    )


def _provider(
    tmp_path: Path,
    *,
    benchmark_name: str = "longmemeval",
    collector: EfficiencyCollector | None = None,
    config: LettaConfig | None = None,
    session_memory_report: bool = False,
    runtime_factory: Any = _FakeRuntime,
) -> Letta:
    """构造使用 fake runtime 的 adapter。"""

    _FakeRuntime.instances.clear()
    selected = config or _config()
    return Letta(
        config=selected,
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
        openai_settings=OpenAISettings(
            api_key="sk-test",
            model=selected.llm_model,
        ),
        efficiency_collector=collector,
        session_memory_report=session_memory_report,
        benchmark_name=benchmark_name,
        runtime_factory=runtime_factory,
    )


def _event(
    *,
    role: str,
    speaker: str,
    content: str,
    turn_id: str,
    timestamp: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TurnEvent:
    """构造同一公开 session 的 turn event。"""

    return TurnEvent(
        role=role,
        speaker_name=speaker,
        content=content,
        timestamp=timestamp,
        isolation_key="run_conv",
        session_id="s1",
        turn_id=turn_id,
        metadata=metadata or {},
    )


def _batch(events: list[TurnEvent], *, session_time: str | None = None) -> SessionBatch:
    """把测试 events 包成一个 session batch。"""

    return SessionBatch(
        isolation_key="run_conv",
        session_id="s1",
        events=tuple(events),
        session_time=session_time,
    )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"max_messages_per_batch": 11}, "must not exceed 10"),
        ({"human_block_limit": 9999}, "locks human=10000"),
        ({"worker_request_timeout_seconds": 0.0}, "must be positive"),
    ],
)
def test_letta_config_rejects_product_contract_drift(
    override: dict[str, Any],
    message: str,
) -> None:
    """影响 product 身份或未证能力的配置必须构造期失败。"""

    with pytest.raises(ConfigurationError, match=message):
        _config(**override)


def test_letta_config_accepts_independent_runtime_w2() -> None:
    """W2 是 execution 拓扑，不改变 sleeptime memory method 参数。"""

    assert _config(max_workers=2).max_workers == 2


def test_letta_w2_storage_roots_own_distinct_product_runtimes(tmp_path: Path) -> None:
    """两个 conversation worker 必须拥有不同容器、volume 与 runtime tag。"""

    paths = _paths(tmp_path)
    settings = OpenAISettings(api_key="test", model="model")
    first = LettaRuntime(
        config=_config(max_workers=2),
        openai_settings=settings,
        path_settings=paths,
        storage_root=paths.outputs_root / "run/method_state/worker_0",
    )
    second = LettaRuntime(
        config=_config(max_workers=2),
        openai_settings=settings,
        path_settings=paths,
        storage_root=paths.outputs_root / "run/method_state/worker_1",
    )

    assert first._identity != second._identity
    assert first._container_name != second._container_name
    assert first._volume_name != second._volume_name
    assert first.runtime_tag != second.runtime_tag


def test_letta_runtime_enables_pgvector_before_schema_migration() -> None:
    """Alembic 创建 VECTOR 列前必须显式、幂等启用数据库扩展。"""

    runtime = object.__new__(LettaRuntime)
    runtime._container_name = "owned-letta-postgres"
    calls: list[tuple[list[str], bool]] = []

    def _fake_docker(args: list[str], *, check: bool = True) -> None:
        """记录扩展初始化命令。"""

        calls.append((args, check))

    runtime._docker = _fake_docker

    runtime._ensure_pgvector_extension()

    assert calls == [
        (
            [
                "exec",
                "owned-letta-postgres",
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                "letta",
                "-d",
                "letta",
                "-c",
                "CREATE EXTENSION IF NOT EXISTS vector",
            ],
            True,
        )
    ]


def test_letta_runtime_waits_for_final_tcp_sql_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """初始化临时 Unix server 不得被误认成最终 product-ready。"""

    runtime = object.__new__(LettaRuntime)
    runtime._container_name = "owned-letta-postgres"
    runtime.config = _config(postgres_startup_timeout_seconds=1.0)
    calls: list[tuple[list[str], bool]] = []
    responses = iter(
        [
            subprocess.CompletedProcess([], 1, "", "connection refused"),
            subprocess.CompletedProcess([], 0, "1\n", ""),
            subprocess.CompletedProcess([], 0, "127.0.0.1:49152\n", ""),
        ]
    )

    def _fake_docker(
        args: list[str], *, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        """模拟临时 server 拒绝 TCP，最终 server 随后就绪。"""

        calls.append((args, check))
        return next(responses)

    runtime._docker = _fake_docker
    monkeypatch.setattr(letta_adapter_module, "sleep", lambda _: None)

    assert runtime._wait_for_postgres() == 49152
    assert calls == [
        (
            [
                "exec",
                "owned-letta-postgres",
                "psql",
                "-h",
                "127.0.0.1",
                "-Atqc",
                "SELECT 1",
                "-U",
                "letta",
                "-d",
                "letta",
            ],
            False,
        ),
        (
            [
                "exec",
                "owned-letta-postgres",
                "psql",
                "-h",
                "127.0.0.1",
                "-Atqc",
                "SELECT 1",
                "-U",
                "letta",
                "-d",
                "letta",
            ],
            False,
        ),
        (["port", "owned-letta-postgres", "5432/tcp"], True),
    ]


def test_letta_worker_environment_is_allowlisted_and_scopes_build_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """worker 不得继承任意宿主 secret，build key 只进私有变量。"""

    paths = _paths(tmp_path)
    runtime = LettaRuntime(
        config=_config(),
        openai_settings=OpenAISettings(
            api_key="private-build-key",
            base_url="https://example.invalid/v1",
            model="gpt-4o-mini",
            provider="primary",
        ),
        path_settings=paths,
        storage_root=paths.outputs_root / "run/method_state",
    )
    monkeypatch.setenv("UNRELATED_DATABASE_PASSWORD", "must-not-cross")
    monkeypatch.setenv("OPENAI_API_KEY", "host-openai-key")
    monkeypatch.setenv("PATH", "/controlled/bin")

    without_key = runtime._worker_environment(5432, include_build_key=False)
    with_key = runtime._worker_environment(5432, include_build_key=True)

    assert without_key["PATH"] == "/controlled/bin"
    assert "UNRELATED_DATABASE_PASSWORD" not in without_key
    assert "OPENAI_API_KEY" not in without_key
    assert "MEMORY_BENCHMARK_LETTA_BUILD_API_KEY" not in without_key
    assert with_key["MEMORY_BENCHMARK_LETTA_BUILD_API_KEY"] == "private-build-key"
    assert with_key["HOME"].startswith(str(runtime.storage_root))
    assert with_key["LETTA_PG_URI"].endswith("/letta?sslmode=disable")


def test_letta_parent_stderr_tail_redacts_key_and_endpoint() -> None:
    """worker 已输出的失败尾行也必须在进入架构师错误面前二次脱敏。"""

    runtime = object.__new__(LettaRuntime)
    api_key = "private-build-key-value"
    endpoint = "https://private-runtime.example/v1"
    runtime.openai_settings = OpenAISettings(
        api_key=api_key,
        base_url=endpoint,
        model="mimo-v2.5",
        provider="opencodego",
        judge_transport="chat_completions",
    )
    redact = runtime._worker_stderr_redactor()
    rendered = "\n".join(
        (
            redact(f"request={endpoint}/chat/completions key={api_key}"),
            redact("ordinary failure context"),
        )
    )
    assert api_key not in rendered
    assert endpoint not in rendered
    assert "<redacted-api-key>" in rendered
    assert "<redacted-api-base-url>/chat/completions" in rendered
    assert "ordinary failure context" in rendered


def test_letta_runtime_declares_transport_failure_policy(tmp_path: Path) -> None:
    """Letta timeout/协议错误只报错，最终终止继续归 Docker lifecycle。"""

    runtime = LettaRuntime(
        config=_config(),
        openai_settings=OpenAISettings(api_key="test", model="model"),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
    )

    assert runtime._transport.terminate_on_timeout is False
    assert runtime._transport.terminate_on_protocol_error is False
    assert runtime._transport.forget_process_on_terminate is False
    assert runtime._transport.stderr_tail_char_limit == 2000


def test_letta_locomo_payload_preserves_speakers_time_caption_and_sdk_wrapper(
    tmp_path: Path,
) -> None:
    """LoCoMo 固定 speaker 映射并保留真实名、session time 与共享 caption。"""

    provider = _provider(tmp_path, benchmark_name="locomo")
    metadata = {
        "conversation_metadata": {"speaker_a": "Caroline", "speaker_b": "Melanie"},
    }
    first = _event(
        role="Caroline",
        speaker="Caroline",
        content="already rendered noise",
        turn_id="D1:1",
        metadata={
            **metadata,
            "original_content": "I moved to Seattle.",
            "turn_images": [
                {
                    "image_id": "img-1",
                    "path": "/private/path.png",
                    "caption": "a rainy skyline",
                    "metadata": {"query": "private locator"},
                }
            ],
        },
    )
    second = _event(
        role="Melanie",
        speaker="Melanie",
        content="Welcome!",
        turn_id="D1:2",
        metadata=metadata,
    )

    result = provider.ingest(
        _batch([first, second], session_time="2023-05-20 10:00")
    )

    runtime = _FakeRuntime.instances[0]
    assert result is not None
    assert result.metadata["build_call_count"] == 1
    assert runtime.ingest_calls[0]["content"] == (
        "<messages>The following message interactions have occured:\n"
        "user: [Session time: 2023-05-20 10:00] Caroline: I moved to Seattle. "
        "[Sharing image that shows: a rainy skyline]\n"
        "assistant: [Session time: 2023-05-20 10:00] Melanie: Welcome!"
        "</messages>"
    )
    assert "/private/path.png" not in runtime.ingest_calls[0]["content"]
    assert "private locator" not in runtime.ingest_calls[0]["content"]


def test_letta_membench_embedded_time_is_not_prefixed_twice(tmp_path: Path) -> None:
    """MemBench marker=True 时保留尾部 time/place 原文且不追加前缀。"""

    provider = _provider(tmp_path, benchmark_name="membench")
    content = "I love The Godfather. (place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
    event = _event(
        role="user",
        speaker="user",
        content=content,
        turn_id="0:0",
        timestamp="2024-10-01 08:00",
        metadata={
            "original_content": content,
            "original_turn_time": "2024-10-01 08:00",
            "turn_metadata": {"source_timestamp_embedded_in_content": True},
        },
    )

    provider.ingest(_batch([event]))

    written = _FakeRuntime.instances[0].ingest_calls[0]["content"]
    assert written.count("2024-10-01 08:00") == 1
    assert "[Turn time:" not in written
    assert "place: Boston, MA" in written


def test_letta_missing_time_and_role_anomalies_need_no_placeholder(tmp_path: Path) -> None:
    """assistant-first、连续同 role、singleton 与 missing time 均按原序进入 SDK。"""

    provider = _provider(tmp_path)
    events = [
        _event(role="assistant", speaker="assistant", content="A1", turn_id="t1"),
        _event(role="assistant", speaker="assistant", content="A2", turn_id="t2"),
        _event(role="user", speaker="user", content="U1", turn_id="t3"),
    ]

    provider.ingest(_batch(events))

    written = _FakeRuntime.instances[0].ingest_calls[0]["content"]
    assert written == (
        "<messages>The following message interactions have occured:\n"
        "assistant: A1\nassistant: A2\nuser: U1</messages>"
    )
    assert "placeholder" not in written.lower()
    assert "time:" not in written.lower()


def test_letta_never_crosses_session_when_chunking(tmp_path: Path) -> None:
    """11 条 session 只拆成 10+1 两批，下一 session 由 runner 单独调用。"""

    provider = _provider(tmp_path)
    events = [
        _event(
            role="user" if index % 2 == 0 else "assistant",
            speaker="user" if index % 2 == 0 else "assistant",
            content=f"message-{index}",
            turn_id=f"t{index}",
        )
        for index in range(11)
    ]

    result = provider.ingest(_batch(events))

    calls = _FakeRuntime.instances[0].ingest_calls
    assert result is not None
    assert result.metadata["build_call_count"] == 2
    assert calls[0]["content"].count("message-") == 10
    assert calls[1]["content"].count("message-") == 1
    assert "message-10" not in calls[0]["content"]
    assert "message-10" in calls[1]["content"]


def test_letta_completed_operation_replay_is_idempotent(tmp_path: Path) -> None:
    """adapter 成功后、checkpoint 前崩溃的同批重放不得再次调用产品写链。"""

    provider = _provider(tmp_path)
    batch = _batch(
        [_event(role="user", speaker="user", content="hello", turn_id="t1")]
    )

    first = provider.ingest(batch)
    second = provider.ingest(batch)

    runtime = _FakeRuntime.instances[0]
    assert first is not None and second is not None
    assert len(runtime.ingest_calls) == 1
    assert first.metadata["build_call_count"] == 1
    assert first.metadata["reused_build_call_count"] == 0
    assert second.metadata["build_call_count"] == 0
    assert second.metadata["reused_build_call_count"] == 1
    sidecar = json.loads(
        provider._sidecar_path("run_conv").read_text(encoding="utf-8")
    )
    assert sidecar["pending_operation_id"] is None
    assert len(sidecar["completed_operation_ids"]) == 1


def test_letta_halumem_reports_crash_safe_changed_core_block_delta(
    tmp_path: Path,
) -> None:
    """报告稳定 block ID 的产品 after-value，并从 sidecar 原样重放结果。"""

    provider = _provider(
        tmp_path,
        benchmark_name="halumem",
        session_memory_report=True,
    )
    runtime = provider._require_runtime()
    assert isinstance(runtime, _FakeRuntime)
    original_ingest = runtime.ingest

    def _mutating_ingest(
        *,
        subject_id: str,
        operation_id: str,
        content: str,
    ) -> dict[str, Any]:
        """模拟 sleeptime tool 在成功 step 中改写 human block。"""

        result = original_ingest(
            subject_id=subject_id,
            operation_id=operation_id,
            content=content,
        )
        runtime.blocks[1] = {
            **runtime.blocks[1],
            "value": "Alice now lives in Boston.",
        }
        return result

    runtime.ingest = _mutating_ingest
    batch = _batch(
        [_event(role="user", speaker="user", content="raw input", turn_id="t1")]
    )

    provider.ingest(batch)
    first = provider.end_session(
        SessionRef(isolation_key="run_conv", session_id="s1")
    )
    provider.ingest(batch)
    second = provider.end_session(
        SessionRef(isolation_key="run_conv", session_id="s1")
    )

    assert first is not None and second is not None
    assert first.memories == ["Alice now lives in Boston."]
    assert second.memories == first.memories
    sidecar = json.loads(provider._sidecar_path("run_conv").read_text())
    assert sidecar["session_reports"]["s1"]["before_blocks"][0]["id"] == "block-human"
    assert sidecar["session_reports"]["s1"]["memories"] == first.memories


def test_letta_ambiguous_pending_operation_requires_namespace_clean(
    tmp_path: Path,
) -> None:
    """产品可能已写但 terminal 未验收时，resume 必须停在 clean-retry 门。"""

    provider = _provider(tmp_path)
    runtime = provider._require_runtime()
    assert isinstance(runtime, _FakeRuntime)
    runtime.fail_ingest = True
    batch = _batch(
        [_event(role="user", speaker="user", content="hello", turn_id="t1")]
    )

    with pytest.raises(ConfigurationError, match="ingest failed after product write"):
        provider.ingest(batch)

    sidecar_path = provider._sidecar_path("run_conv")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert isinstance(sidecar["pending_operation_id"], str)
    assert sidecar["completed_operation_ids"] == []
    runtime.fail_ingest = False
    with pytest.raises(ConfigurationError, match="ambiguous pending build"):
        provider.ingest(batch)
    assert len(runtime.ingest_calls) == 1

    clean_letta_conversation_state(provider=provider, isolation_key="run_conv")
    assert not sidecar_path.exists()


def test_letta_rejects_subject_identity_drift_before_sidecar_write(
    tmp_path: Path,
) -> None:
    """ensure_subject 回错 namespace 时不得写 sidecar 或进入产品 build。"""

    provider = _provider(tmp_path)
    runtime = provider._require_runtime()
    assert isinstance(runtime, _FakeRuntime)

    def _wrong_subject(_subject_id: str) -> dict[str, Any]:
        """返回结构合法但 subject 错位的 worker 响应。"""

        return {
            "subject_id": "another-subject",
            "agent_id": "agent-1",
            "block_ids": ["block-human", "block-summary"],
            "archive_id": "archive-1",
        }

    runtime.ensure_subject = _wrong_subject

    with pytest.raises(ConfigurationError, match="different subject identity"):
        provider.ingest(
            _batch([_event(role="user", speaker="user", content="hello", turn_id="t1")])
        )

    assert not provider._sidecar_path("run_conv").exists()
    assert runtime.ingest_calls == []


def test_letta_rejects_ingest_resource_drift_and_keeps_pending_journal(
    tmp_path: Path,
) -> None:
    """build 回错 agent/block/archive 时必须停在 ambiguous pending clean 门。"""

    provider = _provider(tmp_path)
    runtime = provider._require_runtime()
    assert isinstance(runtime, _FakeRuntime)

    def _wrong_ingest(
        *,
        subject_id: str,
        operation_id: str,
        content: str,
    ) -> dict[str, Any]:
        """模拟产品已写后 worker 回了另一个 agent 身份。"""

        runtime.ingest_calls.append(
            {
                "subject_id": subject_id,
                "operation_id": operation_id,
                "content": content,
            }
        )
        return {
            "subject_id": subject_id,
            "agent_id": "agent-other",
            "block_ids": ["block-human", "block-summary"],
            "archive_id": "archive-1",
            "usage": [{"input_tokens": 1, "output_tokens": 1}],
            "step_count": 1,
        }

    runtime.ingest = _wrong_ingest

    with pytest.raises(ConfigurationError, match="different agent_id"):
        provider.ingest(
            _batch([_event(role="user", speaker="user", content="hello", turn_id="t1")])
        )

    sidecar = json.loads(
        provider._sidecar_path("run_conv").read_text(encoding="utf-8")
    )
    assert isinstance(sidecar["pending_operation_id"], str)
    assert sidecar["completed_operation_ids"] == []


def test_letta_rejects_readout_block_identity_drift(tmp_path: Path) -> None:
    """readout 被换块或改 label 时不得静默注入 answer prompt。"""

    provider = _provider(tmp_path)
    provider.ingest(
        _batch([_event(role="user", speaker="user", content="hello", turn_id="t1")])
    )
    runtime = _FakeRuntime.instances[0]
    runtime.blocks[0] = {**runtime.blocks[0], "id": "block-other"}

    with pytest.raises(ConfigurationError, match="conflicts with sidecar"):
        provider.retrieve(
            RetrievalQuery(
                query_text="q",
                isolation_key="run_conv",
                question_time=None,
                top_k=10,
                purpose="qa",
            )
        )


def test_letta_usage_is_replayed_as_exact_per_call_observations(tmp_path: Path) -> None:
    """worker 的每条 provider usage 必须逐调用写入 collector，不按 batch 猜测。"""

    collector = EfficiencyCollector(run_id="run", enabled=True)
    provider = _provider(tmp_path, collector=collector)
    event = _event(role="user", speaker="user", content="hello", turn_id="t1")

    with collector.conversation_scope("conv") as scope:
        provider.ingest(_batch([event]))
        collector.record_memory_build_total_latency(latency_ms=1.0)

    llm_records = [record for record in scope.records if hasattr(record, "input_tokens")]
    assert [(record.input_tokens, record.output_tokens) for record in llm_records] == [
        (11, 3),
        (7, 2),
    ]
    assert all(record.token_measurement_source.value == "api_usage" for record in llm_records)


def test_letta_failed_worker_usage_reaches_attempt_ledger(tmp_path: Path) -> None:
    """Letta step 失败不能抹掉此前已返回 exact usage 的 provider calls。"""

    class _FailingRuntime(_FakeRuntime):
        """模拟 worker 带结构化 usage 的业务失败。"""

        def ingest(self, **kwargs: Any) -> dict[str, Any]:
            """记录请求后返回 WorkerCommandError。"""

            self.ingest_calls.append(dict(kwargs))
            raise WorkerCommandError(
                "Letta worker ingest failed [RuntimeError]: planned",
                error_type="RuntimeError",
                details={
                    "llm_observations": [
                        {"input_tokens": 17, "output_tokens": 5}
                    ]
                },
            )

    collector = EfficiencyCollector(run_id="letta-failed", enabled=True)
    attempts: list[FailedEfficiencyAttempt] = []
    collector.bind_failed_attempt_sink(attempts.append)
    provider = _provider(
        tmp_path,
        collector=collector,
        runtime_factory=_FailingRuntime,
    )

    with pytest.raises(WorkerCommandError, match="planned"):
        with collector.conversation_scope("conv"):
            provider.ingest(
                _batch(
                    [_event(role="user", speaker="user", content="hello", turn_id="t1")]
                )
            )

    assert len(attempts) == 1
    assert len(attempts[0].calls) == 1
    call = attempts[0].calls[0]
    assert isinstance(call, LLMCallObservation)
    assert (call.input_tokens, call.output_tokens) == (17, 5)


def test_letta_readout_is_sorted_query_independent_and_metric_na(tmp_path: Path) -> None:
    """readout 应稳定排序 core blocks，并明确不产生 retrieval items/rank。"""

    provider = _provider(tmp_path)
    provider.ingest(
        _batch([_event(role="user", speaker="user", content="hello", turn_id="t1")])
    )

    result = provider.retrieve(
        RetrievalQuery(
            query_text="Where does Alice live?",
            isolation_key="run_conv",
            question_time=None,
            top_k=10,
            purpose="qa",
        )
    )

    assert result.formatted_memory.index('label="human"') < result.formatted_memory.index('label="summary"')
    assert 'description="Human &lt;facts&gt;"' in result.formatted_memory
    assert 'description="Summary &amp; status"' in result.formatted_memory
    assert result.items is None
    assert result.metadata["query_consumed_by_method"] is False
    assert result.evidence is not None
    assert result.evidence.semantic_provenance.status == "n_a"
    assert result.evidence.stable_ranking.status == "n_a"
    assert _FakeRuntime.instances[0].read_calls == [
        {
            "subject_id": provider._subject_id("run_conv"),
            "agent_id": "agent-1",
        }
    ]


def test_letta_retrieve_refuses_missing_or_conflicting_sidecar(tmp_path: Path) -> None:
    """resume readout 不得仅凭 hash 猜 agent；缺失/漂移 sidecar 必须失败。"""

    provider = _provider(tmp_path)
    query = RetrievalQuery(
        query_text="q",
        isolation_key="run_conv",
        question_time=None,
        top_k=10,
        purpose="qa",
    )
    with pytest.raises(ConfigurationError, match="sidecar is missing"):
        provider.retrieve(query)

    provider.ingest(
        _batch([_event(role="user", speaker="user", content="hello", turn_id="t1")])
    )
    path = provider._sidecar_path("run_conv")
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["subject_id"] = "different-subject"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="identity mismatch"):
        provider.retrieve(query)


def test_letta_clean_retry_keeps_pending_sidecar_until_verified_delete(tmp_path: Path) -> None:
    """clean 失败必须保留 pending sidecar；同一资源重试成功后才删除。"""

    provider = _provider(tmp_path)
    provider.ingest(
        _batch([_event(role="user", speaker="user", content="hello", turn_id="t1")])
    )
    runtime = _FakeRuntime.instances[0]
    runtime.fail_delete = True

    with pytest.raises(ConfigurationError, match="delete failed"):
        clean_letta_conversation_state(provider=provider, isolation_key="run_conv")

    path = provider._sidecar_path("run_conv")
    assert json.loads(path.read_text(encoding="utf-8"))["cleanup_phase"] == "pending"
    runtime.fail_delete = False
    clean_letta_conversation_state(provider=provider, isolation_key="run_conv")
    assert not path.exists()
    assert len(runtime.delete_calls) == 2
    assert runtime.delete_calls[1]["state"]["cleanup_phase"] == "pending"


def test_letta_cleanup_only_commits_after_runtime_close_succeeds(tmp_path: Path) -> None:
    """runtime close 失败时 provider 必须保留引用，允许同对象再试。"""

    provider = _provider(tmp_path)
    provider.prepare(None)
    runtime = _FakeRuntime.instances[0]
    runtime.fail_close = True

    with pytest.raises(ConfigurationError, match="close failed"):
        provider.cleanup()

    assert provider._runtime is runtime
    assert provider._cleaned is False
    runtime.fail_close = False
    provider.cleanup()
    provider.cleanup()
    assert provider._runtime is None
    assert provider._cleaned is True
    assert runtime.close_calls == 2


def test_letta_time_marker_requires_literal_true() -> None:
    """字符串 true/False 不得误删 source time。"""

    assert _effective_time_prefix(
        turn_time="2024-01-01 10:00",
        session_time="2024-01-01",
        source_timestamp_embedded=True,
    ) == ""
    assert _effective_time_prefix(
        turn_time="2024-01-01 10:00",
        session_time="2024-01-01",
        source_timestamp_embedded="true",
    ) == "[Turn time: 2024-01-01 10:00] "
    assert _effective_time_prefix(
        turn_time=None,
        session_time="2024-01-01",
        source_timestamp_embedded=True,
    ) == "[Session time: 2024-01-01] "


def test_letta_official_wrapper_preserves_arbitrary_role_sequence() -> None:
    """formatter 只保留输入顺序和 role，不要求 user/assistant 成对。"""

    assert _official_message_wrapper(
        [
            {"role": "assistant", "content": "one"},
            {"role": "assistant", "content": "two"},
        ]
    ) == (
        "<messages>The following message interactions have occured:\n"
        "assistant: one\nassistant: two</messages>"
    )


def test_letta_source_identity_is_pinned_and_excludes_untracked_paper() -> None:
    """source identity 应覆盖承重源码/wrapper，但排除用户放入的 PDF。"""

    identity = build_letta_source_identity(load_path_settings())

    assert identity["commit"] == "b76da9092518cbaa2d09042e52fdcbde69243e18"
    assert identity["release_tag"] == "0.16.8"
    assert identity["sdk_release_tag"] == "v0.2.0"
    assert identity["source_mode"].startswith("vendored-letta")
    assert all(not path.lower().endswith(".pdf") for path in identity["files"])
    assert identity["wrapper_hashes"].keys() == {
        "scripts/bootstrap_letta_runtime.sh",
        "src/memory_benchmark/methods/letta_adapter.py",
        "src/memory_benchmark/methods/letta_worker.py",
        "src/memory_benchmark/methods/worker_transport.py",
    }
