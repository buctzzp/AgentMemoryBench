"""测试 EverOS adapter 的五格输入、产品 readout、sidecar 与清理边界。"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
from typing import Any

import pytest

from memory_benchmark.config import OpenAISettings, PathSettings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    RetrievalQuery,
    SessionBatch,
    SessionRef,
    TurnEvent,
)
from memory_benchmark.methods.everos_adapter import (
    EVEROS_ADAPTER_VERSION,
    EVEROS_COMMIT,
    EVEROS_EMPTY_MEMORY_SENTINEL,
    EVEROS_ROOT_MARKER,
    EVEROS_STATE_SCHEMA_VERSION,
    EverOS,
    EverOSConfig,
    EverOSRuntime,
    _namespace_id,
    _parse_timestamp_ms,
    build_everos_source_identity,
    clean_everos_conversation_state,
    validate_everos_variant,
)


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeRuntime:
    """记录 adapter 发出的 typed-product worker 命令。"""

    instances: list["_FakeRuntime"] = []

    def __init__(self, **kwargs: Any) -> None:
        """保存依赖和命令账。"""

        self.kwargs = kwargs
        self.ingest_calls: list[dict[str, Any]] = []
        self.retrieve_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.close_calls = 0
        self.fail_close = False
        self.retrieval_items: list[dict[str, Any]] = []
        self.ingest_rerank_observations: list[dict[str, Any]] = []
        self.retrieval_rerank_observations: list[dict[str, Any]] = []
        type(self).instances.append(self)

    @staticmethod
    def _episode(session_id: str) -> dict[str, Any]:
        """返回 public get 可见的最小 Episode。"""

        return {
            "id": "episode-1",
            "session_id": session_id,
            "timestamp": "2024-01-02T03:04:05Z",
            "sender_ids": ["sender-1"],
            "subject": "Alice",
            "summary": "Alice moved.",
            "episode": "Alice moved to Seattle.",
            "type": "Conversation",
            "atomic_facts": [
                {"id": "fact-1", "content": "Alice lives in Seattle."}
            ],
        }

    def ingest_session(self, **kwargs: Any) -> dict[str, Any]:
        """记录完整 session payload 并返回成功 exact-drain。"""

        self.ingest_calls.append(dict(kwargs))
        return {
            "embedding_observations": [],
            "exact_drain": True,
            "llm_observations": [],
            "operation_id": kwargs["operation_id"],
            "rerank_observations": list(self.ingest_rerank_observations),
            "session_items": [self._episode(kwargs["session_id"])],
        }

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        """返回可注入的 public HYBRID 结果。"""

        self.retrieve_calls.append(dict(kwargs))
        return {
            "embedding_observations": [],
            "items": list(self.retrieval_items[: kwargs["top_k"]]),
            "latency_ms": 1.25,
            "llm_observations": [],
            "rerank_observations": list(self.retrieval_rerank_observations),
        }

    def get_session_memories(self, **kwargs: Any) -> dict[str, Any]:
        """记录 public get 并返回 session-local Episode。"""

        self.get_calls.append(dict(kwargs))
        return {"session_items": [self._episode(kwargs["session_id"])]}

    def delete_conversation(self, *, isolation_key: str) -> dict[str, Any]:
        """记录物理 root 清理。"""

        self.delete_calls.append(isolation_key)
        return {"already_absent": False, "deleted": True}

    def close(self) -> None:
        """记录 cleanup；可注入失败验证成功后提交。"""

        self.close_calls += 1
        if self.fail_close:
            raise ConfigurationError("close failed")


def _config(**overrides: Any) -> EverOSConfig:
    """构造 M2 主 profile 的最小合法配置。"""

    values: dict[str, Any] = {
        "llm_model": "deepseek-v4-flash",
        "memory_mode": "chat",
        "search_method": "hybrid",
        "add_batch_size": 25,
        "embedding_model": "Qwen/Qwen3-Embedding-4B",
        "embedding_dimension": 1024,
        "embedding_provider": "deepinfra-openai-compatible",
        "embedding_credential_env": "EVEROS_DEEPINFRA_API_KEY",
        "rerank_provider": "deepinfra",
        "rerank_model": "Qwen/Qwen3-Reranker-4B",
        "rerank_credential_env": "EVEROS_DEEPINFRA_API_KEY",
        "rerank_capability_mode": "configured",
        "app_id": "memorybenchmark",
        "project_id": "phase1",
        "worker_request_timeout_seconds": 30.0,
        "drain_timeout_seconds": 20.0,
        "max_workers": 1,
    }
    values.update(overrides)
    return EverOSConfig(**values)


def _paths(root: Path) -> PathSettings:
    """构造不依赖主工作区第三方目录的 fake path settings。"""

    for relative in (
        "data",
        "models",
        "outputs",
        "third_party/benchmarks",
        "third_party/methods/EverOS",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "third_party/methods/EverOS/pyproject.toml").write_text(
        "[project]\nname='everos'\nversion='1.2.3'\n",
        encoding="utf-8",
    )
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
    benchmark_name: str,
    session_memory_report: bool = False,
) -> EverOS:
    """构造使用 fake runtime 的真实 adapter。"""

    _FakeRuntime.instances.clear()
    return EverOS(
        config=_config(),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        benchmark_name=benchmark_name,
        session_memory_report=session_memory_report,
        runtime_factory=_FakeRuntime,
    )


def _event(
    *,
    role: str,
    speaker: str,
    content: str,
    turn_id: str,
    turn_time: str | None = None,
    session_time: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TurnEvent:
    """构造保留 original public fields 的 canonical event。"""

    supplied = dict(metadata or {})
    supplied.setdefault("original_content", content)
    supplied.setdefault("original_turn_time", turn_time)
    supplied.setdefault("original_session_time", session_time)
    supplied.setdefault("turn_metadata", {})
    return TurnEvent(
        role=role,
        speaker_name=speaker,
        content=content,
        timestamp=turn_time or session_time,
        isolation_key="run_conv",
        session_id="s1",
        turn_id=turn_id,
        metadata=supplied,
    )


def _batch(
    events: list[TurnEvent],
    *,
    session_id: str = "s1",
    session_time: str | None = "2026-01-01T00:00:00",
) -> SessionBatch:
    """把事件包装成一个 production session ingest unit。"""

    return SessionBatch(
        isolation_key="run_conv",
        session_id=session_id,
        events=tuple(events),
        session_time=session_time,
    )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"memory_mode": "agent"}, "memory_mode='chat'"),
        ({"search_method": "agentic"}, "search_method='hybrid'"),
        ({"add_batch_size": 2}, "add_batch_size=25"),
        ({"embedding_dimension": 768}, "embedding_dimension=1024"),
        ({"embedding_model": "other"}, "Qwen/Qwen3-Embedding-4B"),
        ({"embedding_provider": "other"}, "embedding_provider"),
        (
            {
                "embedding_provider": "openrouter-openai-compatible",
                "embedding_credential_env": "EVEROS_DEEPINFRA_API_KEY",
            },
            "credential environment",
        ),
        ({"rerank_provider": "vllm"}, "rerank provider"),
        ({"rerank_model": "other"}, "rerank model"),
        ({"rerank_capability_mode": "optional"}, "rerank_capability_mode"),
        ({"max_workers": 0}, "positive integer"),
        ({"drain_timeout_seconds": float("nan")}, "positive and finite"),
        ({"app_id": "../escape"}, "PathSafeId"),
    ],
)
def test_everos_config_rejects_main_profile_drift(
    override: dict[str, Any],
    message: str,
) -> None:
    """M1 锁定的产品算法/检索/隔离身份不得静默漂移。"""

    with pytest.raises(ConfigurationError, match=message):
        _config(**override)


def test_everos_manifest_contains_public_identity_but_no_secret_value() -> None:
    """manifest 只声明 credential 变量名，不携带 key/base URL。"""

    manifest = _config().to_manifest()

    assert manifest["adapter_version"] == EVEROS_ADAPTER_VERSION
    assert manifest["consume_granularity"] == "session"
    assert manifest["missing_timestamp_policy"] == "require-source-time-v1"
    assert manifest["timestamp_derivation_policy"] == (
        "locomo-official-30s-only-v1"
    )
    assert manifest["input_content_time_prefix"] is False
    assert manifest["product_episode_time_policy"] == "source-derived-only-v1"
    serialized = json.dumps(manifest, sort_keys=True)
    assert "sk-test" not in serialized
    assert "base_url" not in serialized


def test_everos_openrouter_embedding_transport_is_explicit_and_secret_safe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """smoke transport 必须显式注入 OpenRouter endpoint，且不写进公开 manifest。"""

    config = _config(
        embedding_provider="openrouter-openai-compatible",
        embedding_credential_env="openrouter_key",
        rerank_capability_mode="disabled-zero-call",
    )
    monkeypatch.setenv("openrouter_key", "private-openrouter-key")
    monkeypatch.setenv("openrouter_base_url", "https://openrouter.example/v1")
    runtime = EverOSRuntime(
        config=config,
        openai_settings=OpenAISettings(
            api_key="private-llm-key",
            base_url="https://llm.example/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
    )

    environment = runtime._worker_environment(tmp_path / "product")
    manifest = config.to_manifest()

    assert environment["EVEROS_EMBEDDING__API_KEY"] == "private-openrouter-key"
    assert environment["EVEROS_EMBEDDING__BASE_URL"] == (
        "https://openrouter.example/v1"
    )
    assert "EVEROS_RERANK__API_KEY" not in environment
    assert manifest["embedding_provider"] == "openrouter-openai-compatible"
    serialized = json.dumps(manifest, sort_keys=True)
    assert "private-openrouter-key" not in serialized
    assert "https://openrouter.example/v1" not in serialized


def test_everos_product_root_omits_endpoint_template_and_keeps_ome_config(
    tmp_path: Path,
) -> None:
    """产品根只落 OME 策略，不得复制含 provider endpoint 的 everos.toml。"""

    paths = _paths(tmp_path)
    everos_root = paths.third_party_methods_root / "EverOS"
    config_root = everos_root / "src/everos/config"
    config_root.mkdir(parents=True)
    (config_root / "default.toml").write_text(
        '[llm]\nbase_url = "https://must-not-persist.invalid/v1"\n',
        encoding="utf-8",
    )
    ome_payload = b"[strategies.extract_atomic_facts]\nenabled = true\n"
    (config_root / "default_ome.toml").write_bytes(ome_payload)
    runtime = EverOSRuntime(
        config=_config(),
        openai_settings=OpenAISettings(
            api_key="private-llm-key",
            base_url="https://llm.example/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        path_settings=paths,
        storage_root=tmp_path / "outputs/run/method_state",
    )

    product_root, marker = runtime._prepare_product_root("run_conv")

    assert marker["adapter_version"] == EVEROS_ADAPTER_VERSION
    assert not (product_root / "everos.toml").exists()
    assert (product_root / "ome.toml").read_bytes() == ome_payload
    serialized_root = "\n".join(
        path.read_text(encoding="utf-8")
        for path in product_root.iterdir()
        if path.is_file()
    )
    assert "base_url" not in serialized_root
    assert "must-not-persist.invalid" not in serialized_root
    assert "private-llm-key" not in serialized_root
    assert runtime._prepare_product_root("run_conv") == (product_root, marker)

    (product_root / "ome.toml").write_text("drift", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="config drifted: ome.toml"):
        runtime._prepare_product_root("run_conv")


def test_everos_openrouter_embedding_requires_its_declared_endpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """OpenRouter transport 缺 endpoint 时必须在 worker 启动前失败。"""

    config = _config(
        embedding_provider="openrouter-openai-compatible",
        embedding_credential_env="openrouter_key",
        rerank_capability_mode="disabled-zero-call",
    )
    monkeypatch.setenv("openrouter_key", "private-openrouter-key")
    monkeypatch.delenv("openrouter_base_url", raising=False)
    monkeypatch.delenv("OPENROUTER_BASE_URL", raising=False)
    runtime = EverOSRuntime(
        config=config,
        openai_settings=OpenAISettings(
            api_key="private-llm-key",
            base_url="https://llm.example/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
    )

    with pytest.raises(ConfigurationError, match="embedding endpoint is missing"):
        runtime._worker_environment(tmp_path / "product")


def test_everos_configured_reranker_requires_credential_before_worker_start(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """official-full 声明 configured 时，不得让缺 key 降级成 optional capability。"""

    config = _config(
        embedding_provider="openrouter-openai-compatible",
        embedding_credential_env="openrouter_key",
    )
    monkeypatch.setenv("openrouter_key", "private-openrouter-key")
    monkeypatch.setenv("openrouter_base_url", "https://openrouter.example/v1")
    monkeypatch.delenv("EVEROS_DEEPINFRA_API_KEY", raising=False)
    runtime = EverOSRuntime(
        config=config,
        openai_settings=OpenAISettings(
            api_key="private-llm-key",
            base_url="https://llm.example/v1",
            model="gpt-4o-mini",
        ),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
    )

    with pytest.raises(ConfigurationError, match="configured rerank capability"):
        runtime._worker_environment(tmp_path / "product")


def test_everos_locomo_uses_real_speakers_all_user_owners_caption_and_30s(
    tmp_path: Path,
) -> None:
    """LoCoMo 忠实采用官方 all-user 多 owner 姿势并补共享 caption。"""

    provider = _provider(tmp_path, benchmark_name="locomo")
    events = [
        _event(
            role="speaker",
            speaker="Caroline",
            content="Look at this",
            turn_id="D1:1",
            session_time="1:56 pm on 8 May, 2023",
            metadata={
                "original_content": "Look at this",
                "original_turn_time": None,
                "original_session_time": "1:56 pm on 8 May, 2023",
                "turn_metadata": {},
                "turn_images": [
                    {
                        "image_id": "img-1",
                        "path": "/private/image.jpg",
                        "caption": "a red kite",
                        "metadata": {"query": "private locator"},
                    }
                ],
            },
        ),
        _event(
            role="speaker",
            speaker="Melanie",
            content="It is beautiful",
            turn_id="D1:2",
            session_time="1:56 pm on 8 May, 2023",
        ),
        _event(
            role="speaker",
            speaker="Caroline",
            content="I agree",
            turn_id="D1:3",
            session_time="1:56 pm on 8 May, 2023",
        ),
    ]

    provider.ingest(_batch(events, session_time="1:56 pm on 8 May, 2023"))
    call = _FakeRuntime.instances[0].ingest_calls[0]
    messages = call["messages"]

    assert [message["role"] for message in messages] == ["user", "user", "user"]
    assert [message["sender_name"] for message in messages] == [
        "Caroline",
        "Melanie",
        "Caroline",
    ]
    assert len(call["owner_ids"]) == 2
    assert [message["timestamp"] for message in messages] == [
        _parse_timestamp_ms("1:56 pm on 8 May, 2023"),
        _parse_timestamp_ms("1:56 pm on 8 May, 2023") + 30_000,
        _parse_timestamp_ms("1:56 pm on 8 May, 2023") + 60_000,
    ]
    assert messages[0]["content"] == (
        "Look at this [Sharing image that shows: a red kite]"
    )
    serialized = json.dumps(messages, ensure_ascii=False)
    assert "/private/image.jpg" not in serialized
    assert "private locator" not in serialized
    assert "[Session time:" not in serialized


def test_everos_longmemeval_preserves_assistant_first_same_role_and_singleton(
    tmp_path: Path,
) -> None:
    """非 LoCoMo 不重新配对、重排、换 role 或添加自然语言 placeholder。"""

    provider = _provider(tmp_path, benchmark_name="longmemeval")
    events = [
        _event(
            role="assistant",
            speaker="assistant",
            content="assistant-first",
            turn_id="t1",
            session_time="2023/05/20 (Sat) 02:21",
        ),
        _event(
            role="assistant",
            speaker="assistant",
            content="same-role",
            turn_id="t2",
            session_time="2023/05/20 (Sat) 02:21",
        ),
        _event(
            role="user",
            speaker="user",
            content="singleton user tail",
            turn_id="t3",
            session_time="2023/05/20 (Sat) 02:21",
        ),
    ]

    provider.ingest(_batch(events, session_time="2023/05/20 (Sat) 02:21"))
    messages = _FakeRuntime.instances[0].ingest_calls[0]["messages"]

    assert [message["role"] for message in messages] == [
        "assistant",
        "assistant",
        "user",
    ]
    assert [message["content"] for message in messages] == [
        "assistant-first",
        "same-role",
        "singleton user tail",
    ]
    assert all(message["content"] for message in messages)


def test_everos_assistant_only_session_gets_one_source_less_structural_anchor(
    tmp_path: Path,
) -> None:
    """whole-session assistant-only 只补一个空 user owner anchor，不伪造事实。"""

    provider = _provider(tmp_path, benchmark_name="longmemeval")
    events = [
        _event(
            role="assistant",
            speaker="assistant",
            content="first assistant fact",
            turn_id="t1",
        ),
        _event(
            role="assistant",
            speaker="assistant",
            content="second assistant fact",
            turn_id="t2",
        ),
    ]

    result = provider.ingest(_batch(events))
    call = _FakeRuntime.instances[0].ingest_calls[0]
    messages = call["messages"]

    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == ""
    assert messages[0]["sender_name"] is None
    assert [message["role"] for message in messages[1:]] == [
        "assistant",
        "assistant",
    ]
    assert [message["content"] for message in messages[1:]] == [
        "first assistant fact",
        "second assistant fact",
    ]
    assert result is not None
    assert result.metadata["synthetic_owner_anchor_count"] == 1
    sidecar = json.loads(provider._sidecar_path("run_conv").read_text())
    source_rows = next(iter(sidecar["sessions"].values()))["source_rows"]
    assert source_rows[0] == {
        "product_timestamp_ms": messages[0]["timestamp"],
        "source_timestamp": None,
        "synthetic_anchor": True,
        "timestamp_kind": "structural-owner-anchor",
        "turn_id": None,
    }


def test_everos_membench_preserves_tail_time_place_and_source_time(
    tmp_path: Path,
) -> None:
    """MemBench 原文不删尾部 time/place，typed 字段另传 source time。"""

    provider = _provider(tmp_path, benchmark_name="membench")
    original = (
        "I love The Godfather. "
        "(place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
    )
    events = [
        _event(
            role="user",
            speaker="user",
            content=original,
            turn_id="step-1:user",
            turn_time="2024-10-01 08:00",
            metadata={
                "original_content": original,
                "original_turn_time": "2024-10-01 08:00",
                "original_session_time": None,
                "turn_metadata": {"source_timestamp_embedded_in_content": True},
            },
        ),
        _event(
            role="assistant",
            speaker="assistant",
            content="reply without an embedded suffix",
            turn_id="step-2:assistant",
            turn_time="2024-10-01 08:01",
        ),
    ]

    result = provider.ingest(_batch(events))
    messages = _FakeRuntime.instances[0].ingest_calls[0]["messages"]

    assert messages[0]["content"] == original
    assert original.count("2024-10-01 08:00") == 1
    assert messages[0]["timestamp"] == _parse_timestamp_ms("2024-10-01 08:00")
    assert messages[1]["content"] == "reply without an embedded suffix"
    assert messages[1]["timestamp"] == _parse_timestamp_ms("2024-10-01 08:01")
    assert result is not None
    assert result.metadata["derived_timestamp_count"] == 0
    sidecar = json.loads(provider._sidecar_path("run_conv").read_text())
    source_rows = next(iter(sidecar["sessions"].values()))["source_rows"]
    assert [row["timestamp_kind"] for row in source_rows] == [
        "source-exact",
        "source-exact",
    ]


def test_everos_missing_source_time_fails_before_runtime_or_product_write(
    tmp_path: Path,
) -> None:
    """产品 prompt 会渲染 timestamp，缺时必须拒绝而非制造伪日期。"""

    provider = _provider(tmp_path, benchmark_name="membench")
    events = [
        _event(
            role="user",
            speaker="user",
            content="noise without time",
            turn_id="step-1:user",
        ),
        _event(
            role="assistant",
            speaker="assistant",
            content="more noise without time",
            turn_id="step-1:assistant",
        ),
    ]

    with pytest.raises(ConfigurationError, match="refusing to fabricate time"):
        provider.ingest(_batch(events, session_time=None))

    assert _FakeRuntime.instances == []
    assert not provider._sidecar_path("run_conv").exists()


def test_everos_variant_gate_rejects_only_membench_100k() -> None:
    """100K 缺时 variant 必须拒绝，已有 source-time variants 保持可用。"""

    validate_everos_variant("membench", "0_10k")
    validate_everos_variant("locomo", "default")
    validate_everos_variant("longmemeval", "S-cleaned")
    validate_everos_variant("beam", "100k")
    validate_everos_variant("halumem", "medium")
    with pytest.raises(ConfigurationError, match="timestamp fabrication is forbidden"):
        validate_everos_variant("membench", "100k")


def test_everos_beam_preserves_canonical_role_order_and_session_time(
    tmp_path: Path,
) -> None:
    """BEAM 原序 user/assistant 不因 pair、id 异常或 session fallback 被重构。"""

    provider = _provider(tmp_path, benchmark_name="beam")
    events = [
        _event(
            role="user",
            speaker="user",
            content="question",
            turn_id="0:0",
            session_time="July-15-2024",
        ),
        _event(
            role="assistant",
            speaker="assistant",
            content="answer",
            turn_id="0:1",
            session_time="July-15-2024",
        ),
        _event(
            role="user",
            speaker="user",
            content="dangling follow-up",
            turn_id="0:2",
            session_time="July-15-2024",
        ),
    ]

    provider.ingest(_batch(events, session_time="July-15-2024"))
    messages = _FakeRuntime.instances[0].ingest_calls[0]["messages"]

    assert [message["role"] for message in messages] == [
        "user",
        "assistant",
        "user",
    ]
    assert [message["content"] for message in messages] == [
        "question",
        "answer",
        "dangling follow-up",
    ]
    assert len({message["timestamp"] for message in messages}) == 1


def test_everos_halumem_returns_only_current_session_public_episode(
    tmp_path: Path,
) -> None:
    """HaluMem end_session 只读本次 product session，支持 extraction/update。"""

    provider = _provider(
        tmp_path,
        benchmark_name="halumem",
        session_memory_report=True,
    )
    event = _event(
        role="user",
        speaker="user",
        content="I moved to Seattle.",
        turn_id="s1:t1",
        turn_time="2024-01-02T03:04:05Z",
    )

    ingest = provider.ingest(_batch([event]))
    report = provider.end_session(SessionRef("run_conv", "s1"))

    assert ingest is not None
    assert ingest.session_memories == [
        "Subject: Alice\nSummary: Alice moved.\nEpisode: Alice moved to Seattle."
        "\nAtomic facts:\n- Alice lives in Seattle."
    ]
    assert report is not None
    assert report.memories == ingest.session_memories
    assert report.metadata == {
        "method": "everos",
        "scope": "session-local-public-get",
        "memory_unit": "episode",
    }


def test_everos_retrieval_formats_episode_and_declares_truthful_evidence(
    tmp_path: Path,
) -> None:
    """Episode readout 保留产品 score/rank，semantic provenance 诚实 N/A。"""

    provider = _provider(tmp_path, benchmark_name="locomo")
    provider.ingest(
        _batch(
            [
                _event(
                    role="speaker",
                    speaker="Caroline",
                    content="I moved.",
                    turn_id="D1:1",
                    session_time="1:56 pm on 8 May, 2023",
                )
            ],
            session_time="1:56 pm on 8 May, 2023",
        )
    )
    runtime = _FakeRuntime.instances[0]
    product_session_id = runtime.ingest_calls[0]["session_id"]
    item = runtime._episode(product_session_id)
    item["score"] = 0.875
    runtime.retrieval_items = [item]

    result = provider.retrieve(
        RetrievalQuery(
            isolation_key="run_conv",
            query_text="Where did Alice move?",
            question_time=None,
            top_k=10,
            purpose="qa",
        )
    )

    assert len(result.items or ()) == 1
    retrieved = result.items[0]
    assert retrieved.item_id == "episode-1"
    assert retrieved.score == 0.875
    assert retrieved.source_turn_ids == ()
    assert retrieved.timestamp == "2024-01-02T03:04:05Z"
    assert retrieved.metadata["timestamp_semantics"] == (
        "source-derived-product-time"
    )
    assert result.formatted_memory.startswith(
        '<episode rank="1" id="episode-1" score="0.875" product_time='
    )
    assert result.evidence is not None
    assert result.evidence.semantic_provenance.status == "n_a"
    assert result.evidence.provenance_granularity == "none"
    assert result.evidence.stable_ranking.status == "valid"


def test_everos_formatted_memory_never_renders_derived_product_time(
    tmp_path: Path,
) -> None:
    """LoCoMo 官方派生顺序时间不得借 metadata 进入 answer context。"""

    provider = _provider(tmp_path, benchmark_name="locomo")
    provider.ingest(
        _batch(
            [
                _event(
                    role="user",
                    speaker="Alice",
                    content="first fact",
                    turn_id="t1",
                ),
                _event(
                    role="user",
                    speaker="Bob",
                    content="second fact",
                    turn_id="t2",
                ),
            ],
        )
    )
    runtime = _FakeRuntime.instances[0]
    product_session_id = runtime.ingest_calls[0]["session_id"]
    episode = runtime._episode(product_session_id)
    episode["score"] = 0.5
    runtime.retrieval_items = [episode]

    result = provider.retrieve(
        RetrievalQuery(
            isolation_key="run_conv",
            query_text="noise",
            question_time=None,
            top_k=10,
            purpose="qa",
        )
    )

    assert result.items is not None
    assert result.items[0].timestamp is None
    assert result.items[0].metadata["product_timestamp"]
    assert result.items[0].metadata["timestamp_semantics"] == (
        "method-operational-or-unmapped-not-source-exact"
    )
    assert "product_time=" not in result.formatted_memory

    episode["session_id"] = None
    unmapped = provider.retrieve(
        RetrievalQuery(
            isolation_key="run_conv",
            query_text="merged",
            question_time=None,
            top_k=10,
            purpose="qa",
        )
    )
    assert unmapped.items is not None and unmapped.items[0].timestamp is None
    assert "product_time=" not in unmapped.formatted_memory


def test_everos_zero_hit_is_valid_empty_search_not_backend_failure(
    tmp_path: Path,
) -> None:
    """public search [] 写 sentinel 和 valid stable rank，不伪造检索 item。"""

    provider = _provider(tmp_path, benchmark_name="membench")
    provider.ingest(
        _batch(
            [_event(role="user", speaker="user", content="fact", turn_id="t1")]
        )
    )

    result = provider.retrieve(
        RetrievalQuery(
            isolation_key="run_conv",
            query_text="missing",
            question_time=None,
            top_k=5,
            purpose="qa",
        )
    )

    assert result.formatted_memory == EVEROS_EMPTY_MEMORY_SENTINEL
    assert result.items == ()
    assert result.evidence is not None
    assert result.evidence.stable_ranking.status == "valid"


@pytest.mark.parametrize("stage", ["ingest", "retrieve"])
def test_everos_main_chat_episode_profile_rejects_any_rerank_call(
    tmp_path: Path,
    stage: str,
) -> None:
    """主轨只允许 Episode hierarchy；任何非空 rerank 观测都必须停机。"""

    provider = _provider(tmp_path, benchmark_name="longmemeval")
    runtime = provider._require_runtime()
    assert isinstance(runtime, _FakeRuntime)
    observation = {"document_count": 2, "latency_ms": 1.25}
    if stage == "ingest":
        runtime.ingest_rerank_observations = [observation]
        with pytest.raises(ConfigurationError, match="memory build.*reranker"):
            provider.ingest(
                _batch(
                    [
                        _event(
                            role="user",
                            speaker="user",
                            content="fact",
                            turn_id="t1",
                        )
                    ]
                )
            )
        return

    provider.ingest(
        _batch(
            [_event(role="user", speaker="user", content="fact", turn_id="t1")]
        )
    )
    runtime.retrieval_rerank_observations = [observation]
    with pytest.raises(ConfigurationError, match="retrieval.*reranker"):
        provider.retrieve(
            RetrievalQuery(
                isolation_key="run_conv",
                query_text="fact",
                question_time=None,
                top_k=5,
                purpose="qa",
            )
        )


def test_everos_completed_operation_is_reused_without_second_product_add(
    tmp_path: Path,
) -> None:
    """sidecar 成功 journal 让安全 resume 不重复付费 add。"""

    provider = _provider(tmp_path, benchmark_name="longmemeval")
    batch = _batch(
        [_event(role="user", speaker="user", content="fact", turn_id="t1")]
    )

    first = provider.ingest(batch)
    second = provider.ingest(batch)

    assert len(_FakeRuntime.instances[0].ingest_calls) == 1
    assert first is not None and first.metadata["operation_reused"] is False
    assert second is not None and second.metadata["operation_reused"] is True
    assert second.session_memories is None


def test_everos_sidecar_rejects_forged_source_lineage_and_count(
    tmp_path: Path,
) -> None:
    """sidecar 不能靠篡改 anchor/turn/time count 获得虚假 provenance。"""

    provider = _provider(tmp_path, benchmark_name="longmemeval")
    provider.ingest(
        _batch(
            [_event(role="user", speaker="user", content="fact", turn_id="t1")]
        )
    )
    path = provider._sidecar_path("run_conv")
    sidecar = json.loads(path.read_text(encoding="utf-8"))
    session = next(iter(sidecar["sessions"].values()))
    session["source_rows"][0]["synthetic_anchor"] = True
    path.write_text(json.dumps(sidecar), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="structural owner anchor"):
        provider._load_sidecar("run_conv")

    session["source_rows"][0]["synthetic_anchor"] = False
    session["derived_timestamp_count"] = 1
    path.write_text(json.dumps(sidecar), encoding="utf-8")
    with pytest.raises(ConfigurationError, match="derived timestamp count"):
        provider._load_sidecar("run_conv")


def test_everos_cleanup_commits_only_after_runtime_close_succeeds(
    tmp_path: Path,
) -> None:
    """cleanup 失败不得丢 runtime 引用或伪装幂等成功。"""

    provider = _provider(tmp_path, benchmark_name="longmemeval")
    provider.ingest(
        _batch(
            [_event(role="user", speaker="user", content="fact", turn_id="t1")]
        )
    )
    runtime = _FakeRuntime.instances[0]
    runtime.fail_close = True

    with pytest.raises(ConfigurationError, match="close failed"):
        provider.cleanup()
    assert provider._runtime is runtime
    runtime.fail_close = False
    provider.cleanup()
    provider.cleanup()
    assert runtime.close_calls == 2


def test_clean_everos_conversation_state_removes_sidecar_after_root_ack(
    tmp_path: Path,
) -> None:
    """clean retry 先获 product root 删除确认，再移除对应 sidecar。"""

    provider = _provider(tmp_path, benchmark_name="longmemeval")
    provider.ingest(
        _batch(
            [_event(role="user", speaker="user", content="fact", turn_id="t1")]
        )
    )
    sidecar = provider._sidecar_path("run_conv")
    assert sidecar.is_file()

    clean_everos_conversation_state(provider=provider, isolation_key="run_conv")

    assert not sidecar.exists()
    assert _FakeRuntime.instances[0].delete_calls == ["run_conv"]


def test_everos_runtime_delete_refuses_unmarked_or_wrong_identity_root(
    tmp_path: Path,
) -> None:
    """物理清理必须同时满足 containment 与精确 marker identity。"""

    runtime = EverOSRuntime(
        config=_config(),
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
    )
    root = runtime._conversation_root("run_conv")
    root.mkdir(parents=True)
    (root / "foreign.txt").write_text("do not delete", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="unmarked"):
        runtime.delete_conversation(isolation_key="run_conv")
    assert (root / "foreign.txt").read_text(encoding="utf-8") == "do not delete"

    (root / EVEROS_ROOT_MARKER).write_text(
        json.dumps(
            {
                "adapter_version": EVEROS_ADAPTER_VERSION,
                "everos_commit": "wrong",
                "isolation_hash": _namespace_id("run_conv"),
                "schema_version": EVEROS_STATE_SCHEMA_VERSION,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="does not match"):
        runtime.delete_conversation(isolation_key="run_conv")
    assert root.exists()


def test_everos_runtime_delete_retries_after_partial_tombstone_removal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """rmtree 中断后须从受身份保护 tombstone 继续，不得误报 already absent。"""

    runtime = EverOSRuntime(
        config=_config(),
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
    )
    root = runtime._conversation_root("run_conv")
    root.mkdir(parents=True)
    marker = {
        "adapter_version": EVEROS_ADAPTER_VERSION,
        "everos_commit": EVEROS_COMMIT,
        "isolation_hash": _namespace_id("run_conv"),
        "schema_version": EVEROS_STATE_SCHEMA_VERSION,
    }
    (root / EVEROS_ROOT_MARKER).write_text(json.dumps(marker), encoding="utf-8")
    (root / "payload.bin").write_bytes(b"memory")
    real_rmtree = shutil.rmtree
    calls = 0

    def _interrupt_once(path: Path) -> None:
        """首次模拟进程在 rename 后、删除前中断。"""

        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated interrupted cleanup")
        real_rmtree(path)

    monkeypatch.setattr(
        "memory_benchmark.methods.everos_adapter.shutil.rmtree",
        _interrupt_once,
    )

    with pytest.raises(OSError, match="interrupted cleanup"):
        runtime.delete_conversation(isolation_key="run_conv")
    tombstone = root.with_name(f".{root.name}.cleanup")
    cleanup_marker = root.with_name(f".{root.name}.cleanup.json")
    assert not root.exists()
    assert tombstone.exists()
    assert cleanup_marker.exists()

    result = runtime.delete_conversation(isolation_key="run_conv")

    assert result == {"deleted": True, "already_absent": False}
    assert not tombstone.exists()
    assert not cleanup_marker.exists()


def test_everos_source_identity_covers_patch_worker_runtime_lock_and_templates() -> None:
    """source identity 必须盖住 v1.2.3、patch、worker 与两份 root 模板。"""

    identity = build_everos_source_identity()

    assert identity["commit"] == EVEROS_COMMIT
    assert identity["package_version"] == "1.2.3"
    assert identity["runtime_lock_sha256"]
    assert "src/everos/config/default.toml" in identity["files"]
    assert "src/everos/config/default_ome.toml" in identity["files"]
    assert "scripts/patches/everos-product-runtime-observability.patch" in (
        identity["wrapper_hashes"]
    )
