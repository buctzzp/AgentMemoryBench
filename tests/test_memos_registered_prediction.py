"""测试 MemOS 通过统一 registry 进入通用 v3 prediction runner。

五个 benchmark 各跑一条 fake chain，全部穿过真实 registry / 真实
`run_registered_conversation_qa_prediction` / 真实通用 runner；只把 MemOS
adapter 类替换成不加载模型、不连服务、不调真实 API 的替身，不新建
method × benchmark 专用 runner。
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    PreparedBenchmarkRun,
    RunScope,
)
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import AnswerLLMSettings, OpenAISettings, load_path_settings
from memory_benchmark.core import (
    AnswerPromptResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    MethodCapability,
    PromptMessage,
    Question,
    Session,
    TaskFamily,
    Turn,
)
from memory_benchmark.core.provider_protocol import (
    EvidenceAssertion,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalEvidence,
    RetrievalQuery,
    RetrievalResult,
    RetrievedItem,
    SessionBatch,
    SessionRef,
)
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.methods.memos_adapter import (
    MEMOS_EMPTY_MEMORY_SENTINEL,
    MEMOS_REFERENCE_TIME_EFFECT,
)
from memory_benchmark.storage import read_jsonl


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ("locomo", "longmemeval", "membench", "beam", "halumem")


class FakeMemOSForRegisteredPrediction(MemoryProvider):
    """替代真实 MemOS adapter：不 init_server、不连 Neo4j/Qdrant、不调真实 API。"""

    consume_granularity = "session"
    session_memory_report = False
    provenance_granularity = "none"
    instances: list["FakeMemOSForRegisteredPrediction"] = []

    def __init__(self, **kwargs) -> None:
        """记录 registry factory 传入的构造参数。"""

        self.kwargs = kwargs
        self.ingested_batches: list[SessionBatch] = []
        self.retrievals: list[RetrievalQuery] = []
        self.cleanup_calls = 0
        self.instances.append(self)

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """只接受 session 粒度，与注册声明保持一致。"""

        assert isinstance(unit, SessionBatch)
        self.ingested_batches.append(unit)
        return IngestResult(
            unit_ref=SessionRef(
                isolation_key=unit.isolation_key,
                session_id=unit.session_id,
            ),
            metadata={"method": "memos", "message_count": len(unit.events)},
        )

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回镜像真实 adapter 契约的 unified 口径检索结果。"""

        self.retrievals.append(query)
        return RetrievalResult(
            formatted_memory="fake memos memory",
            items=(
                RetrievedItem(
                    item_id="fake-memory-1",
                    content="fake memos memory",
                    score=0.77,
                    timestamp="2026-01-01T00:00:00",
                    source_turn_ids=("t1",),
                    metadata={"memory_type": "LongTermMemory"},
                ),
            ),
            metadata={
                "method": "memos",
                "prompt_track": "unified",
                "reference_time_effect": MEMOS_REFERENCE_TIME_EFFECT,
                "provenance_granularity": "none",
            },
            evidence=RetrievalEvidence(
                semantic_provenance=EvidenceAssertion(
                    status="pending",
                    reason_code="memos_generated_memory_semantic_lineage_unverified",
                    reason="Fake mirrors the MemOS window-generated memory contract.",
                ),
                provenance_granularity="none",
                stable_ranking=EvidenceAssertion(
                    status="pending",
                    reason_code="memos_product_rerank_stability_unverified",
                    reason="Fake mirrors the MemOS product rerank contract.",
                ),
            ),
        )

    def cleanup(self) -> None:
        """记录通用 runner 的 cleanup 调用次数。"""

        self.cleanup_calls += 1


@pytest.mark.parametrize("benchmark_name", BENCHMARKS)
def test_memos_registered_prediction_runs_five_benchmarks_through_generic_runner(
    benchmark_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """五个 benchmark 各一条 registered fake chain 穿过通用 runner 并写出 v3 artifacts。"""

    FakeMemOSForRegisteredPrediction.instances.clear()
    _install_offline_registered_stack(monkeypatch, tmp_path)

    run_id = f"memos-{benchmark_name}-fake-smoke"
    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="memos",
        benchmark_name=benchmark_name,
        profile_name="smoke",
        run_id=run_id,
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        enable_efficiency_observability=False,
    )

    assert result.benchmark == benchmark_name
    assert len(FakeMemOSForRegisteredPrediction.instances) == 1
    instance = FakeMemOSForRegisteredPrediction.instances[0]

    # session 粒度：两个 turn 聚合成一个 SessionBatch。
    assert len(instance.ingested_batches) == 1
    assert len(instance.ingested_batches[0].events) == 2
    assert [query.query_text for query in instance.retrievals] == [
        f"What should {benchmark_name} remember?"
    ]
    # 通用 runner 必须在成功路径 cleanup 恰好一次。
    assert instance.cleanup_calls == 1

    run_dir = tmp_path / "outputs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    prompts = read_jsonl(run_dir / "artifacts" / "answer_prompts.prediction.jsonl")
    public_questions = read_jsonl(run_dir / "artifacts" / "public_questions.jsonl")

    assert manifest["method_name"] == "MemOS"
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["consume_granularity"] == "session"
    assert manifest["method"]["provenance_granularity"] == "none"
    assert manifest["method"]["retrieval_evidence_contract_version"] == "v1"
    assert manifest["method"]["config"]["adapter_version"] == "memos-v2.0.25-product-v1"
    assert predictions[0]["answer"] == "framework fake answer"
    assert prompts[0]["formatted_memory"] == "fake memos memory"

    # 逐题 evidence 必须落到 artifact 且保持 pending / none，不因命中而升级。
    evidence = prompts[0]["retrieval_evidence"]
    assert evidence["semantic_provenance"]["status"] == "pending"
    assert evidence["provenance_granularity"] == "none"
    assert evidence["stable_ranking"]["status"] == "pending"

    # 私有标签不得进入 method 可见 artifact。
    assert public_questions[0]["question_id"] == f"{benchmark_name}:q1"
    assert "gold_answers" not in public_questions[0]
    assert "evidence" not in public_questions[0]


def test_memos_registered_prediction_zero_hit_uses_sentinel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """零命中时 formatted_memory 必须是非空 sentinel，且 evidence 仍为 pending。"""

    class _ZeroHitMemOS(FakeMemOSForRegisteredPrediction):
        """零命中替身。"""

        instances: list["_ZeroHitMemOS"] = []

        def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
            """返回 sentinel + 空 items。"""

            self.retrievals.append(query)
            return RetrievalResult(
                formatted_memory=MEMOS_EMPTY_MEMORY_SENTINEL,
                items=(),
                metadata={"method": "memos", "prompt_track": "unified"},
                evidence=RetrievalEvidence(
                    semantic_provenance=EvidenceAssertion(
                        status="pending",
                        reason_code=(
                            "memos_generated_memory_semantic_lineage_unverified"
                        ),
                        reason="Zero hit does not change this static fact.",
                    ),
                    provenance_granularity="none",
                    stable_ranking=EvidenceAssertion(
                        status="pending",
                        reason_code="memos_product_rerank_stability_unverified",
                        reason="Zero hit does not change this static fact.",
                    ),
                ),
            )

    _ZeroHitMemOS.instances.clear()
    _install_offline_registered_stack(monkeypatch, tmp_path, provider_class=_ZeroHitMemOS)

    run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="memos",
        benchmark_name="halumem",
        profile_name="smoke",
        run_id="memos-halumem-zero-hit",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        enable_efficiency_observability=False,
    )

    run_dir = tmp_path / "outputs" / "memos-halumem-zero-hit"
    prompts = read_jsonl(run_dir / "artifacts" / "answer_prompts.prediction.jsonl")

    assert prompts[0]["formatted_memory"] == MEMOS_EMPTY_MEMORY_SENTINEL
    assert prompts[0]["retrieved_items"] == []
    assert prompts[0]["retrieval_evidence"]["stable_ranking"]["status"] == "pending"


def _install_offline_registered_stack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider_class: type[MemoryProvider] | None = None,
) -> None:
    """把 registered prediction 依赖的外部入口全部换成离线替身。"""

    real_paths = load_path_settings(PROJECT_ROOT)
    test_paths = replace(real_paths, outputs_root=tmp_path / "outputs")
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: test_paths,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_openai_settings",
        lambda project_root, api_provider=None: OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        FakeAnswerClient,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: _fake_registration(benchmark_name),
    )
    monkeypatch.setattr(
        method_registry_module,
        "MemOS",
        provider_class or FakeMemOSForRegisteredPrediction,
    )


class FakeAnswerClient:
    """离线 fake framework answer client，避免 registered 测试触发真实 API。"""

    model_name = "fake-answer-client"

    def __init__(
        self,
        *,
        settings: OpenAISettings,
        answer_settings: AnswerLLMSettings,
    ) -> None:
        """保存 settings，以覆盖真实 client 的构造路径。"""

        self.settings = settings
        self.answer_settings = answer_settings

    def complete(self, *, prompt: str) -> str:
        """返回固定答案；prompt 拼接由 framework reader 负责。"""

        return "framework fake answer"


def _fake_registration(benchmark_name: str):
    """构造五个 benchmark 共用的最小 fake benchmark registration。"""

    return SimpleNamespace(
        name=benchmark_name,
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        default_variant=f"{benchmark_name}-fake",
        variant_names=lambda: (f"{benchmark_name}-fake",),
        prepare=lambda project_root, request: _prepared_run(
            benchmark_name=benchmark_name,
            project_root=project_root,
            request=request,
        ),
        prediction_enabled=True,
        unified_prompt_builder=_fake_unified_prompt_builder,
    )


def _fake_unified_prompt_builder(question, retrieval_result) -> AnswerPromptResult:
    """benchmark 统一 answer builder 替身：只消费 formatted_memory。

    MemOS 主配置走 unified 口径，answer prompt 由 benchmark 统一 builder 生成，
    不使用 MemOS 自带答题入口。
    """

    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        prompt_messages=[
            PromptMessage(role="system", content="You are a benchmark QA judge."),
            PromptMessage(
                role="user",
                content=(
                    f"Memory:\n{retrieval_result.formatted_memory}\n\n"
                    f"Question: {question.text}"
                ),
            ),
        ],
        metadata={"prompt_track": "unified"},
    )


def _prepared_run(
    *,
    benchmark_name: str,
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """返回固定 fake smoke dataset，并校验 registered service 请求。"""

    assert project_root == PROJECT_ROOT
    assert request == BenchmarkLoadRequest(
        variant=f"{benchmark_name}-fake",
        run_scope=RunScope.SMOKE,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
    )
    return PreparedBenchmarkRun(
        variant=f"{benchmark_name}-fake",
        run_scope=RunScope.SMOKE,
        dataset=_fake_dataset(benchmark_name),
        source_relative_paths=(Path("pyproject.toml"),),
    )


def _fake_dataset(benchmark_name: str) -> Dataset:
    """构造最小 conversation-QA fake dataset。"""

    question = Question(
        question_id=f"{benchmark_name}:q1",
        conversation_id=f"{benchmark_name}:conv-1",
        text=f"What should {benchmark_name} remember?",
    )
    return Dataset(
        dataset_name=benchmark_name,
        metadata={"variant": f"{benchmark_name}-fake", "run_scope": "smoke"},
        conversations=[
            Conversation(
                conversation_id=f"{benchmark_name}:conv-1",
                metadata={"speaker_a": "Alice", "speaker_b": "Bob"},
                sessions=[
                    Session(
                        session_id="session-1",
                        session_time="2026-01-01T00:00:00",
                        turns=[
                            Turn(
                                turn_id="t1",
                                speaker="Alice",
                                normalized_role="user",
                                content=f"{benchmark_name} fact one.",
                            ),
                            Turn(
                                turn_id="t2",
                                speaker="Bob",
                                normalized_role="assistant",
                                content=f"{benchmark_name} fact two.",
                            ),
                        ],
                    )
                ],
                questions=[question],
                gold_answers={
                    question.question_id: GoldAnswerInfo(
                        question_id=question.question_id,
                        answer="fake answer",
                        evidence=["private-evidence"],
                    )
                },
            )
        ],
    )
