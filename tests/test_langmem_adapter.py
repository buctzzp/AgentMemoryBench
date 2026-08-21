"""测试 LangMem adapter 的产品载荷、状态协议、观测与 metric 边界。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.config import OpenAISettings, PathSettings, load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.provider_protocol import RetrievalQuery, SessionBatch, TurnEvent
from memory_benchmark.methods.langmem_adapter import (
    LANGMEM_ADAPTER_VERSION,
    LANGMEM_EMPTY_MEMORY_SENTINEL,
    LangMem,
    LangMemConfig,
    LangMemRuntime,
    _effective_time_prefix,
    _namespace_id,
    _operation_id,
    build_langmem_source_identity,
    clean_langmem_conversation_state,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EmbeddingCallObservation,
    LLMCallObservation,
)


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeRuntime:
    """记录 adapter 发出的窄 worker 命令。"""

    instances: list["_FakeRuntime"] = []

    def __init__(self, **kwargs: Any) -> None:
        """保存构造参数与可注入返回。"""

        self.kwargs = kwargs
        self.started = 0
        self.ingest_calls: list[dict[str, Any]] = []
        self.retrieve_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.close_calls = 0
        self.fail_close = False
        self.reused_operation = False
        self.items: list[dict[str, Any]] = [
            {
                "key": "mem<&1",
                "content": "Alice & Bob moved <home>.",
                "kind": "Memory",
                "score": 0.75,
            },
            {
                "key": "mem-2",
                "content": "They prefer tea.",
                "kind": "Memory",
                "score": 0.25,
            },
        ]
        type(self).instances.append(self)

    def ensure_started(self) -> None:
        """记录 prepare 调用。"""

        self.started += 1

    def ingest(
        self,
        *,
        namespace_id: str,
        operation_id: str,
        messages: list[dict[str, str]],
        max_steps: int,
    ) -> dict[str, Any]:
        """返回一条 LLM 与两条 embedding 观测。"""

        self.ingest_calls.append(
            {
                "namespace_id": namespace_id,
                "operation_id": operation_id,
                "messages": messages,
                "max_steps": max_steps,
            }
        )
        return {
            "changed_memory_keys": ["mem-1"],
            "embedding_observations": [
                {"input_tokens": 5, "latency_ms": 1.25, "text_count": 1},
                {"input_tokens": 8, "latency_ms": 2.5, "text_count": 2},
            ],
            "llm_observations": [{"input_tokens": 21, "output_tokens": 7}],
            "memory_count": 1,
            "rehydrated_entry_count": 0,
            "rehydration_embedding_calls": 0,
            "reused_operation": self.reused_operation,
        }

    def retrieve(
        self,
        *,
        namespace_id: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        """返回 product 排序与 query embedding 观测。"""

        self.retrieve_calls.append(
            {"namespace_id": namespace_id, "query": query, "limit": limit}
        )
        return {
            "embedding_observations": [
                {"input_tokens": 4, "latency_ms": 0.75, "text_count": 1}
            ],
            "items": list(self.items[:limit]),
            "latency_ms": 1.5,
            "rehydrated_entry_count": 0,
            "rehydration_embedding_calls": 0,
        }

    def delete_namespace(self, *, namespace_id: str) -> dict[str, Any]:
        """记录 conversation-scoped clean。"""

        self.delete_calls.append(namespace_id)
        return {"deleted": True, "deleted_entry_count": 1}

    def close(self) -> None:
        """记录 runtime cleanup；可注入失败。"""

        self.close_calls += 1
        if self.fail_close:
            raise ConfigurationError("close failed")


def _config(**overrides: Any) -> LangMemConfig:
    """构造最小合法 LangMem profile。"""

    values: dict[str, Any] = {
        "llm_model": "mimo-v2.5",
        "embedding_model_path": "models/all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "embedding_normalize": True,
        "query_limit": 5,
        "max_steps": 1,
        "enable_inserts": True,
        "enable_deletes": False,
        "worker_request_timeout_seconds": 600.0,
        "max_workers": 1,
    }
    values.update(overrides)
    return LangMemConfig(**values)


def _paths(root: Path) -> PathSettings:
    """构造 fake runtime 所需项目路径。"""

    for relative in (
        "data",
        "models/all-MiniLM-L6-v2",
        "outputs",
        "third_party/benchmarks",
        "third_party/methods/langmem",
    ):
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
) -> LangMem:
    """构造使用 fake runtime 的真实 adapter。"""

    _FakeRuntime.instances.clear()
    return LangMem(
        config=_config(),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs" / "run" / "method_state",
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            model="mimo-v2.5",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        efficiency_collector=collector,
        benchmark_name=benchmark_name,
        runtime_factory=_FakeRuntime,
    )


def _event(
    *,
    role: str,
    speaker: str,
    content: str,
    turn_id: str,
    turn_time: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> TurnEvent:
    """构造一个 canonical event，并保留 original 字段。"""

    supplied = dict(metadata or {})
    supplied.setdefault("original_content", content)
    supplied.setdefault("original_turn_time", turn_time)
    supplied.setdefault("turn_metadata", {})
    return TurnEvent(
        role=role,
        speaker_name=speaker,
        content=content,
        timestamp=turn_time,
        isolation_key="run_conv",
        session_id="s1",
        turn_id=turn_id,
        metadata=supplied,
    )


def _batch(
    events: list[TurnEvent],
    *,
    session_time: str | None = None,
) -> SessionBatch:
    """把 events 包成一个 session batch。"""

    return SessionBatch(
        isolation_key="run_conv",
        session_id="s1",
        events=tuple(events),
        session_time=session_time,
    )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"embedding_dimension": 768}, "embedding_dimension=384"),
        ({"embedding_normalize": False}, "normalized embeddings"),
        ({"query_limit": 6}, "query_limit=5"),
        ({"max_steps": 2}, "max_steps=1"),
        ({"enable_inserts": False}, "enable_inserts=true"),
        ({"enable_deletes": True}, "enable_inserts=true"),
        ({"worker_request_timeout_seconds": 0.0}, "positive and finite"),
    ],
)
def test_langmem_config_rejects_main_profile_drift(
    override: dict[str, Any],
    message: str,
) -> None:
    """M1 锁定的 factory 默认与 embedding 身份不得静默漂移。"""

    with pytest.raises(ConfigurationError, match=message):
        _config(**override)


def test_langmem_prepare_is_lazy_and_cleanup_commits_only_after_close(
    tmp_path: Path,
) -> None:
    """构造不启动 worker；prepare 启动一次，close 失败后可重试。"""

    provider = _provider(tmp_path)
    assert _FakeRuntime.instances == []

    provider.prepare(None)
    runtime = _FakeRuntime.instances[0]
    assert runtime.started == 1
    runtime.fail_close = True
    with pytest.raises(ConfigurationError, match="close failed"):
        provider.cleanup()
    runtime.fail_close = False
    provider.cleanup()
    provider.cleanup()
    assert runtime.close_calls == 2


def test_langmem_locomo_fixed_roles_speaker_time_and_image_are_lossless(
    tmp_path: Path,
) -> None:
    """LoCoMo 固定 speaker 映射、真实名字、source time 与共享 caption 同时成立。"""

    provider = _provider(tmp_path, benchmark_name="locomo")
    conversation_metadata = {"speaker_a": "Caroline", "speaker_b": "Melanie"}
    events = [
        _event(
            role="speaker",
            speaker="Melanie",
            content="Look at this",
            turn_id="D1:1",
            turn_time="2023-05-20 10:00",
            metadata={
                "conversation_metadata": conversation_metadata,
                "original_content": "Look at this",
                "original_turn_time": "2023-05-20 10:00",
                "turn_metadata": {},
                "turn_images": [
                    {
                        "image_id": "image-1",
                        "path": "/private/path.jpg",
                        "caption": "a red kite",
                        "metadata": {"query": "private locator"},
                    }
                ],
            },
        ),
        _event(
            role="speaker",
            speaker="Caroline",
            content="Lovely",
            turn_id="D1:2",
            metadata={
                "conversation_metadata": conversation_metadata,
                "original_content": "Lovely",
                "original_turn_time": None,
                "turn_metadata": {},
            },
        ),
    ]

    provider.ingest(_batch(events, session_time="2023-05-20 09:00"))
    messages = _FakeRuntime.instances[0].ingest_calls[0]["messages"]

    assert messages == [
        {
            "role": "assistant",
            "content": (
                "[Turn time: 2023-05-20 10:00] Melanie: Look at this "
                "[Sharing image that shows: a red kite]"
            ),
        },
        {
            "role": "user",
            "content": "[Session time: 2023-05-20 09:00] Caroline: Lovely",
        },
    ]
    serialized = json.dumps(messages, ensure_ascii=False)
    assert "/private/path.jpg" not in serialized
    assert "private locator" not in serialized


@pytest.mark.parametrize(
    "roles",
    [
        ("assistant", "user"),
        ("user", "user", "assistant"),
        ("user",),
        ("assistant",),
        ("user", "assistant", "user"),
    ],
)
def test_langmem_preserves_non_locomo_role_order_without_placeholder(
    tmp_path: Path,
    roles: tuple[str, ...],
) -> None:
    """assistant-first、same-role、singleton 与 odd tail 都逐条原序交付。"""

    provider = _provider(tmp_path)
    events = [
        _event(
            role=role,
            speaker=role,
            content=f"message-{index}",
            turn_id=f"t{index}",
        )
        for index, role in enumerate(roles)
    ]

    provider.ingest(_batch(events))
    messages = _FakeRuntime.instances[0].ingest_calls[0]["messages"]

    assert [message["role"] for message in messages] == list(roles)
    assert [message["content"] for message in messages] == [
        f"message-{index}" for index in range(len(roles))
    ]
    assert len(messages) == len(events)


def test_langmem_membench_embedded_time_place_is_not_duplicated_and_none_stays_none(
    tmp_path: Path,
) -> None:
    """MemBench 尾部原文保留，marker=True 不重复前缀，noise 不伪造时间。"""

    provider = _provider(tmp_path, benchmark_name="membench")
    embedded = (
        "I love The Godfather. "
        "(place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
    )
    events = [
        _event(
            role="user",
            speaker="user",
            content=embedded,
            turn_id="t1",
            turn_time="2024-10-01 08:00",
            metadata={
                "original_content": embedded,
                "original_turn_time": "2024-10-01 08:00",
                "turn_metadata": {"source_timestamp_embedded_in_content": True},
            },
        ),
        _event(
            role="assistant",
            speaker="assistant",
            content="noise without source time or place",
            turn_id="t2",
        ),
    ]

    provider.ingest(_batch(events, session_time=None))
    messages = _FakeRuntime.instances[0].ingest_calls[0]["messages"]

    assert messages[0]["content"] == embedded
    assert messages[0]["content"].count("2024-10-01 08:00") == 1
    assert messages[1]["content"] == "noise without source time or place"
    assert "None" not in messages[1]["content"]


def test_langmem_ingest_operation_identity_and_observations_are_exact_once(
    tmp_path: Path,
) -> None:
    """相同 session retry 复用 operation，LLM/embedding observation 不重复记。"""

    collector = EfficiencyCollector(run_id="langmem-test", enabled=True)
    provider = _provider(tmp_path, collector=collector)
    batch = _batch(
        [_event(role="user", speaker="user", content="fact", turn_id="t1")]
    )

    with collector.conversation_scope("conv") as scope:
        first = provider.ingest(batch)
        runtime = _FakeRuntime.instances[0]
        runtime.reused_operation = True
        second = provider.ingest(batch)
        collector.record_memory_build_total_latency(latency_ms=3.0)

    assert first is not None and second is not None
    assert first.metadata["operation_id"] == second.metadata["operation_id"]
    assert first.metadata["operation_reused"] is False
    assert second.metadata["operation_reused"] is True
    llm = [item for item in scope.records if isinstance(item, LLMCallObservation)]
    embeddings = [
        item for item in scope.records if isinstance(item, EmbeddingCallObservation)
    ]
    assert [(item.input_tokens, item.output_tokens) for item in llm] == [(21, 7)]
    assert [item.input_tokens for item in embeddings] == [5, 8]


def test_langmem_retrieve_preserves_rank_score_and_evidence(
    tmp_path: Path,
) -> None:
    """product asearch 顺序不重排，evolved provenance N/A 与 stable rank 分离。"""

    collector = EfficiencyCollector(run_id="langmem-retrieve", enabled=True)
    provider = _provider(tmp_path, collector=collector)
    query = RetrievalQuery(
        query_text="Where did Alice move?",
        isolation_key="run_conv",
        question_time="2026-01-01",
        top_k=2,
        purpose="qa",
    )

    with collector.question_scope("conv", "q1") as scope:
        result = provider.retrieve(query)
        collector.record_answer_generation(latency_ms=1.0)

    assert [item.item_id for item in result.items or ()] == ["mem<&1", "mem-2"]
    assert [item.score for item in result.items or ()] == [0.75, 0.25]
    assert 'id="mem&lt;&amp;1"' in result.formatted_memory
    assert "Alice &amp; Bob moved &lt;home&gt;." in result.formatted_memory
    assert result.evidence is not None
    assert result.evidence.semantic_provenance.status == "n_a"
    assert result.evidence.provenance_granularity == "none"
    assert result.evidence.stable_ranking.status == "valid"
    embeddings = [
        item for item in scope.records if isinstance(item, EmbeddingCallObservation)
    ]
    assert len(embeddings) == 1
    assert embeddings[0].input_tokens == 4
    assert embeddings[0].stage.value == "retrieval"


def test_langmem_zero_hit_is_valid_empty_tuple_not_missing_items(
    tmp_path: Path,
) -> None:
    """真实 zero hit 与 provider 无结构化 items 必须可区分。"""

    provider = _provider(tmp_path)
    provider._require_runtime().items = []  # type: ignore[attr-defined]

    result = provider.retrieve(
        RetrievalQuery(
            query_text="nothing",
            isolation_key="run_conv",
            question_time=None,
            top_k=10,
            purpose="memory_update_probe",
        )
    )

    assert result.items == ()
    assert result.formatted_memory == LANGMEM_EMPTY_MEMORY_SENTINEL
    assert result.evidence is not None
    assert result.evidence.stable_ranking.status == "valid"


@pytest.mark.parametrize("bad_score", [float("nan"), float("inf"), "0.5", True])
def test_langmem_retrieve_rejects_invalid_scores(
    tmp_path: Path,
    bad_score: Any,
) -> None:
    """NaN、Infinity、字符串和 bool 都不能冒充 product score。"""

    provider = _provider(tmp_path)
    runtime = provider._require_runtime()
    runtime.items = [  # type: ignore[attr-defined]
        {"key": "m1", "content": "fact", "kind": "Memory", "score": bad_score}
    ]

    with pytest.raises(ConfigurationError, match="item.score"):
        provider.retrieve(
            RetrievalQuery(
                query_text="query",
                isolation_key="run_conv",
                question_time=None,
                top_k=1,
                purpose="qa",
            )
        )


def test_langmem_clean_is_namespace_scoped_and_deterministic(tmp_path: Path) -> None:
    """failed-ingest cleanup 只向 worker 发送当前 isolation 的 opaque namespace。"""

    provider = _provider(tmp_path)

    clean_langmem_conversation_state(provider=provider, isolation_key="run_conv")
    runtime = _FakeRuntime.instances[0]

    assert runtime.delete_calls == [_namespace_id("run_conv")]
    assert _namespace_id("run_conv") == _namespace_id("run_conv")
    assert _namespace_id("run_conv") != _namespace_id("run_other")


def test_langmem_operation_id_changes_with_payload_or_session() -> None:
    """operation journal 不能把不同 session/payload 错认成已完成重试。"""

    base = _operation_id(
        namespace_id="a" * 32,
        session_id="s1",
        messages=[{"role": "user", "content": "one"}],
        max_steps=1,
    )
    changed_content = _operation_id(
        namespace_id="a" * 32,
        session_id="s1",
        messages=[{"role": "user", "content": "two"}],
        max_steps=1,
    )
    changed_session = _operation_id(
        namespace_id="a" * 32,
        session_id="s2",
        messages=[{"role": "user", "content": "one"}],
        max_steps=1,
    )

    assert len(base) == 64
    assert len({base, changed_content, changed_session}) == 3


def test_langmem_time_prefix_has_exact_turn_session_none_precedence() -> None:
    """时间只渲染一次，不用 wall clock 或字符串 None 补缺。"""

    assert _effective_time_prefix(
        turn_time=" t ", session_time="s", source_timestamp_embedded=False
    ) == "[Turn time: t] "
    assert _effective_time_prefix(
        turn_time="t", session_time="s", source_timestamp_embedded=True
    ) == ""
    assert _effective_time_prefix(
        turn_time=None, session_time=" s ", source_timestamp_embedded=True
    ) == "[Session time: s] "
    assert _effective_time_prefix(
        turn_time=None, session_time=None, source_timestamp_embedded=False
    ) == ""


def test_langmem_runtime_environment_does_not_forward_unrelated_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """独立 worker 环境只携带当前 build key，不继承其他 provider secret。"""

    paths = _paths(tmp_path)
    settings = OpenAISettings(api_key="chosen-secret", model="mimo-v2.5")
    runtime = LangMemRuntime(
        config=_config(),
        openai_settings=settings,
        path_settings=paths,
        storage_root=tmp_path / "outputs" / "run" / "method_state",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated-openai")
    monkeypatch.setenv("OPENCODEGO_API_KEY", "unrelated-opencodego")

    environment = runtime._worker_environment()

    assert environment["MEMORY_BENCHMARK_LANGMEM_BUILD_API_KEY"] == "chosen-secret"
    assert "OPENAI_API_KEY" not in environment
    assert "OPENCODEGO_API_KEY" not in environment


def test_langmem_source_identity_covers_current_source_and_runtime_files() -> None:
    """source identity 必须同时覆盖 selected upstream 与四个 wrapper/lock 文件。"""

    identity = build_langmem_source_identity(load_path_settings(PROJECT_ROOT))

    assert identity["commit"] == "56d85939d80bb731bd5e237567148d817d7bfd16"
    assert identity["package_version"] == "0.0.30"
    assert identity["file_count"] == 9
    assert identity["vendored_source_sha256"] == (
        "50999bd9675304d514d86218033898ac1930a57958aeda95cb967f22f59753fb"
    )
    assert len(identity["runtime_lock_sha256"]) == 64
    assert set(identity["wrapper_hashes"]) == {
        "scripts/bootstrap_langmem_runtime.sh",
        "scripts/requirements/langmem-runtime.txt",
        "src/memory_benchmark/methods/langmem_adapter.py",
        "src/memory_benchmark/methods/langmem_worker.py",
        "src/memory_benchmark/methods/worker_transport.py",
    }
    assert len(identity["source_sha256"]) == 64


def test_langmem_runtime_declares_transport_failure_policy(tmp_path: Path) -> None:
    """LangMem 协议失败应杀 worker，并保留 journal-authority 失败句。"""

    runtime = LangMemRuntime(
        config=_config(),
        openai_settings=OpenAISettings(api_key="test", model="model"),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
    )

    assert runtime._transport.terminate_on_timeout is True
    assert runtime._transport.terminate_on_protocol_error is True
    assert runtime._transport.forget_process_on_terminate is False
    assert runtime._transport.timeout_detail == (
        "the operation journal remains the only resume authority"
    )


def test_langmem_manifest_contains_no_secret_or_absolute_state_path() -> None:
    """公开 config identity 只声明产品语义，不包含 runtime secret/URL/state root。"""

    manifest = _config().to_manifest()
    serialized = json.dumps(manifest, ensure_ascii=False, sort_keys=True)

    assert manifest["adapter_version"] == LANGMEM_ADAPTER_VERSION
    assert manifest["product_surface"] == (
        "create_memory_store_manager+ainvoke+asearch"
    )
    assert manifest["query_model"] is None
    assert "api_key" not in serialized.lower()
    assert "base_url" not in serialized.lower()
    assert "/Users/" not in serialized
