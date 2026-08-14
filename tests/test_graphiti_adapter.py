"""测试 Graphiti OSS adapter 的五格输入、lineage、readout 与生命周期。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from memory_benchmark.config import OpenAISettings, PathSettings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.core.provider_protocol import RetrievalQuery, SessionRef, TurnEvent
from memory_benchmark.methods.graphiti_adapter import (
    GRAPHITI_EMPTY_MEMORY_SENTINEL,
    GraphitiConfig,
    GraphitiOSS,
    GraphitiRuntime,
    _reference_time,
    build_graphiti_source_identity,
    clean_graphiti_conversation_state,
    validate_graphiti_variant,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EmbeddingCallObservation,
    LLMCallObservation,
)


pytestmark = pytest.mark.unit


class _FakeRuntime:
    """记录 adapter 发出的最窄 worker 命令。"""

    instances: list["_FakeRuntime"] = []

    def __init__(self, **kwargs: Any) -> None:
        """保存构造依赖和可注入返回。"""

        self.kwargs = kwargs
        self.started = 0
        self.ingest_calls: list[dict[str, Any]] = []
        self.retrieve_calls: list[dict[str, Any]] = []
        self.session_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.close_calls = 0
        self.fail_close = False
        self.items: list[dict[str, Any]] = [
            {
                "expired_at": None,
                "fact": "Alice & Bob moved <home>.",
                "invalid_at": None,
                "reference_time": "2024-01-02T03:04:05+00:00",
                "source_turn_ids": ["D1:1", "D1:2"],
                "uuid": "edge<&1",
                "valid_at": "2024-01-02T03:04:05+00:00",
            }
        ]
        type(self).instances.append(self)

    def ensure_started(self) -> None:
        """记录 prepare。"""

        self.started += 1

    def ingest(self, **kwargs: Any) -> dict[str, Any]:
        """返回一次 API 与一次 embedding 观测。"""

        self.ingest_calls.append(dict(kwargs))
        return {
            "edge_count": 2,
            "embedding_observations": [
                {"input_tokens": 5, "latency_ms": 1.25, "text_count": 1}
            ],
            "episode_uuid": "episode-1",
            "llm_observations": [{"input_tokens": 21, "output_tokens": 7}],
            "reused_operation": False,
        }

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        """返回有序 product edge 与 query embedding。"""

        self.retrieve_calls.append(dict(kwargs))
        return {
            "embedding_observations": [
                {"input_tokens": 4, "latency_ms": 0.75, "text_count": 1}
            ],
            "items": list(self.items[: kwargs["limit"]]),
            "latency_ms": 1.5,
        }

    def session_memories(self, **kwargs: Any) -> dict[str, Any]:
        """返回当前 session active facts。"""

        self.session_calls.append(dict(kwargs))
        return {"memories": ["current fact", "second fact"]}

    def delete_conversation(self, *, isolation_key: str) -> dict[str, Any]:
        """记录物理 clean。"""

        self.delete_calls.append(isolation_key)
        return {"deleted": True}

    def close(self) -> None:
        """记录 cleanup，并可注入失败。"""

        self.close_calls += 1
        if self.fail_close:
            raise ConfigurationError("close failed")


def _config(**overrides: Any) -> GraphitiConfig:
    """构造合法 smoke config。"""

    values: dict[str, Any] = {
        "llm_model": "deepseek-v4-flash",
        "structured_output_mode": "json_object",
        "llm_temperature": 1.0,
        "llm_max_tokens": 16384,
        "embedding_model_path": "models/all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "embedding_normalize": True,
        "query_limit": 20,
        "max_coroutines": 10,
        "worker_request_timeout_seconds": 900.0,
        "max_workers": 1,
    }
    values.update(overrides)
    return GraphitiConfig(**values)


def _paths(root: Path) -> PathSettings:
    """构造 fake runtime 所需路径与空 runtime sentinel。"""

    for relative in (
        "data",
        "models/all-MiniLM-L6-v2",
        "outputs",
        "third_party/benchmarks",
        "third_party/methods/graphiti/.venv/bin",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)
    (root / "third_party/methods/graphiti/.venv/bin/python").write_text(
        "fake\n", encoding="utf-8"
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
    benchmark_name: str = "longmemeval",
    session_memory_report: bool = False,
    collector: EfficiencyCollector | None = None,
) -> GraphitiOSS:
    """构造使用 fake runtime 的真实 adapter。"""

    _FakeRuntime.instances.clear()
    return GraphitiOSS(
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
        efficiency_collector=collector,
        runtime_factory=_FakeRuntime,
    )


def _event(
    *,
    role: str,
    speaker: str,
    content: str,
    turn_id: str = "s1:t1",
    timestamp: str | None = "2024-01-02 03:04",
    metadata: dict[str, Any] | None = None,
) -> TurnEvent:
    """构造保留 original content/time 的 canonical turn。"""

    supplied = dict(metadata or {})
    supplied.setdefault("original_content", content)
    supplied.setdefault("original_turn_time", timestamp)
    supplied.setdefault("turn_metadata", {})
    return TurnEvent(
        role=role,
        speaker_name=speaker,
        content=content,
        timestamp=timestamp,
        isolation_key="run_conv",
        session_id="s1",
        turn_id=turn_id,
        metadata=supplied,
    )


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"structured_output_mode": "xml"}, "structured_output_mode"),
        ({"llm_temperature": -1}, "llm_temperature"),
        ({"llm_max_tokens": 0}, "positive integer"),
        ({"embedding_dimension": 768}, "embedding_dimension=384"),
        ({"embedding_normalize": False}, "normalized embeddings"),
        ({"query_limit": 10}, "query_limit=20"),
        ({"max_coroutines": 0}, "positive integer"),
        ({"worker_request_timeout_seconds": 0}, "positive and finite"),
    ],
)
def test_graphiti_config_rejects_identity_drift(
    override: dict[str, Any], message: str
) -> None:
    """M2 锁定参数不得被宽松配置绕过。"""

    with pytest.raises(ConfigurationError, match=message):
        _config(**override)


def test_graphiti_prepare_is_lazy_and_cleanup_is_retryable(tmp_path: Path) -> None:
    """构造不启动 worker；close 失败后 provider 不得伪装 cleaned。"""

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


def test_graphiti_locomo_fixed_role_speaker_image_and_time_are_lossless(
    tmp_path: Path,
) -> None:
    """LoCoMo speaker/role、caption 与 turn time 同时进入 product payload。"""

    provider = _provider(tmp_path, benchmark_name="locomo")
    metadata = {
        "conversation_metadata": {
            "speaker_a": "Caroline",
            "speaker_b": "Melanie",
        },
        "original_content": "Look at this",
        "original_turn_time": "1:56 pm on 8 May, 2023",
        "turn_metadata": {},
        "turn_images": [
            {
                "image_id": "image-1",
                "path": "/private/path.jpg",
                "caption": "a red kite",
                "metadata": {"query": "private locator"},
            }
        ],
    }
    provider.ingest(
        _event(
            role="speaker",
            speaker="Melanie",
            content="Look at this",
            turn_id="D1:1",
            timestamp="1:56 pm on 8 May, 2023",
            metadata=metadata,
        )
    )
    call = _FakeRuntime.instances[0].ingest_calls[0]
    assert call["episode_body"] == (
        "Melanie (assistant): Look at this "
        "[Sharing image that shows: a red kite]"
    )
    assert call["reference_time"] == "2023-05-08T13:56:00+00:00"
    serialized = json.dumps(call, ensure_ascii=False)
    assert "/private/path.jpg" not in serialized
    assert "private locator" not in serialized


@pytest.mark.parametrize(
    ("benchmark_name", "role", "content"),
    [
        ("longmemeval", "assistant", "assistant-first stays first"),
        ("beam", "user", "orphan user stays singleton"),
        ("halumem", "assistant", "correction stays assistant"),
    ],
)
def test_graphiti_non_locomo_turns_preserve_role_without_placeholder(
    tmp_path: Path,
    benchmark_name: str,
    role: str,
    content: str,
) -> None:
    """连续 role、assistant-first、orphan 都是单 episode，不伪造配对。"""

    provider = _provider(tmp_path, benchmark_name=benchmark_name)
    provider.ingest(_event(role=role, speaker=role, content=content))
    calls = _FakeRuntime.instances[0].ingest_calls
    assert len(calls) == 1
    assert calls[0]["episode_body"] == f"{role}: {content}"


def test_graphiti_membench_preserves_embedded_place_time_and_structured_time(
    tmp_path: Path,
) -> None:
    """MemBench 原文尾部不删除，同时 reference_time 另走 typed channel。"""

    provider = _provider(tmp_path, benchmark_name="membench")
    content = (
        "I love The Godfather. "
        "(place: Boston, MA; time: '2024-10-01 08:00' Tuesday)"
    )
    provider.ingest(
        _event(
            role="user",
            speaker="user",
            content=content,
            timestamp="2024-10-01 08:00",
            metadata={
                "original_content": content,
                "original_turn_time": "2024-10-01 08:00",
                "turn_metadata": {"source_timestamp_embedded_in_content": True},
            },
        )
    )
    call = _FakeRuntime.instances[0].ingest_calls[0]
    assert call["episode_body"] == f"user: {content}"
    assert call["episode_body"].count("2024-10-01 08:00") == 1
    assert call["reference_time"] == "2024-10-01T08:00:00+00:00"


def test_graphiti_missing_or_unparseable_source_time_fails_before_runtime_write(
    tmp_path: Path,
) -> None:
    """不以 question/sibling/wall clock 替代缺失或坏 source time。"""

    provider = _provider(tmp_path, benchmark_name="membench")
    with pytest.raises(ConfigurationError, match="timestamp fabrication"):
        provider.ingest(
            _event(
                role="user",
                speaker="user",
                content="noise",
                timestamp=None,
            )
        )
    with pytest.raises(ConfigurationError, match="cannot parse"):
        provider.ingest(
            _event(
                role="user",
                speaker="user",
                content="noise",
                timestamp="after lunch someday",
            )
        )
    assert _FakeRuntime.instances == []


def test_graphiti_retrieve_preserves_rank_temporal_fields_and_turn_lineage(
    tmp_path: Path,
) -> None:
    """RRF rank、score=None、多 source turn 与 XML escaping 同时成立。"""

    provider = _provider(tmp_path)
    result = provider.retrieve(
        RetrievalQuery(
            query_text="Where did they move?",
            isolation_key="run_conv",
            question_time="2025-01-01",
            top_k=10,
            purpose="qa",
        )
    )
    assert result.items is not None
    assert result.items[0].score is None
    assert result.items[0].source_turn_ids == ("D1:1", "D1:2")
    assert result.items[0].metadata["product_rank"] == 1
    assert 'id="edge&lt;&amp;1"' in result.formatted_memory
    assert "Alice &amp; Bob moved &lt;home&gt;." in result.formatted_memory
    assert "D1:1" not in result.formatted_memory
    assert result.evidence is not None
    assert result.evidence.semantic_provenance.status == "valid"
    assert result.evidence.provenance_granularity == "turn"
    assert result.evidence.stable_ranking.status == "valid"
    call = _FakeRuntime.instances[0].retrieve_calls[0]
    assert call == {
        "isolation_key": "run_conv",
        "query": "Where did they move?",
        "limit": 10,
    }


def test_graphiti_zero_hit_and_halu_session_report_are_distinct(tmp_path: Path) -> None:
    """zero-hit 是有效空检索；HaluMem report 只取 worker 的 active delta。"""

    provider = _provider(
        tmp_path,
        benchmark_name="halumem",
        session_memory_report=True,
    )
    provider._require_runtime().items = []  # type: ignore[attr-defined]
    result = provider.retrieve(
        RetrievalQuery(
            query_text="nothing",
            isolation_key="run_conv",
            question_time=None,
            top_k=10,
            purpose="extraction_probe",
        )
    )
    assert result.items == ()
    assert result.formatted_memory == GRAPHITI_EMPTY_MEMORY_SENTINEL
    report = provider.end_session(SessionRef("run_conv", "s1"))
    assert report is not None
    assert report.memories == ["current fact", "second fact"]
    assert _FakeRuntime.instances[0].session_calls == [
        {"isolation_key": "run_conv", "session_id": "s1"}
    ]


def test_graphiti_efficiency_observations_are_scoped_and_not_replayed(
    tmp_path: Path,
) -> None:
    """build usage 精确记录一次，retrieve embedding 进入 retrieval stage。"""

    collector = EfficiencyCollector(run_id="graphiti-observability", enabled=True)
    provider = _provider(tmp_path, collector=collector)
    with collector.conversation_scope("conv") as build_scope:
        event = _event(role="user", speaker="user", content="hello")
        provider.ingest(event)
        provider.ingest(event)
        collector.record_memory_build_total_latency(latency_ms=3.0)
    with collector.question_scope("conv", "q1") as question_scope:
        provider.retrieve(
            RetrievalQuery(
                query_text="hello?",
                isolation_key="run_conv",
                question_time=None,
                top_k=10,
                purpose="qa",
            )
        )
        collector.record_answer_generation(latency_ms=1.0)
    llm = [
        item for item in build_scope.records if isinstance(item, LLMCallObservation)
    ]
    embedding = [
        item
        for item in (*build_scope.records, *question_scope.records)
        if isinstance(item, EmbeddingCallObservation)
    ]
    assert [(item.input_tokens, item.output_tokens) for item in llm] == [(21, 7)]
    assert [item.input_tokens for item in embedding] == [5, 4]
    assert embedding[-1].stage.value == "retrieval"


def test_graphiti_clean_calls_exact_isolation_and_cleanup(tmp_path: Path) -> None:
    """failed clean 使用明确 isolation key；正常 cleanup 不物理删状态。"""

    provider = _provider(tmp_path)
    clean_graphiti_conversation_state(provider=provider, isolation_key="run_conv")
    runtime = _FakeRuntime.instances[0]
    assert runtime.delete_calls == ["run_conv"]
    provider.cleanup()
    assert runtime.close_calls == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2023/05/20 (Sat) 02:21", "2023-05-20T02:21:00+00:00"),
        ("March-15-2024", "2024-03-15T00:00:00+00:00"),
        ("1:56 pm on 8 May, 2023", "2023-05-08T13:56:00+00:00"),
        ("2024-01-02T03:04:05Z", "2024-01-02T03:04:05+00:00"),
    ],
)
def test_graphiti_reference_time_formats(raw: str, expected: str) -> None:
    """五格已知 source-time 格式稳定归一到 UTC。"""

    assert _reference_time(raw) == expected


def test_graphiti_variant_gate_rejects_only_membench_100k() -> None:
    """缺时 100k 在 runtime 前拒绝，其余 concrete variant 保持可规划。"""

    with pytest.raises(ConfigurationError, match="timestamp fabrication"):
        validate_graphiti_variant("membench", "100k")
    for benchmark, variant in (
        ("membench", "0_10k"),
        ("locomo", "locomo10"),
        ("longmemeval", "s_cleaned"),
        ("beam", "10m"),
        ("halumem", "medium"),
    ):
        validate_graphiti_variant(benchmark, variant)


def test_graphiti_source_identity_covers_shared_worker_transport() -> None:
    """共享 transport 变化必须进入 Graphiti source/resume 身份。"""

    identity = build_graphiti_source_identity()

    assert "src/memory_benchmark/methods/worker_transport.py" in (
        identity["wrapper_hashes"]
    )


def test_graphiti_runtime_declares_transport_failure_policy(tmp_path: Path) -> None:
    """Graphiti 协议失败应杀 worker，并保留退出对象阻止隐式重启。"""

    runtime = GraphitiRuntime(
        config=_config(),
        openai_settings=OpenAISettings(api_key="test", model="model"),
        path_settings=_paths(tmp_path),
        storage_root=tmp_path / "outputs/run/method_state",
    )

    assert runtime._transport.terminate_on_timeout is True
    assert runtime._transport.terminate_on_protocol_error is True
    assert runtime._transport.forget_process_on_terminate is False
