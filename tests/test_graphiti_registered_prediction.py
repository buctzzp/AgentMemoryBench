"""测试 Graphiti OSS 经 registry 进入五格通用 provider-v3 prediction 链。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
    ConfigurationError,
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
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.methods import load_method_profile
from memory_benchmark.methods.graphiti_adapter import GraphitiOSS
from memory_benchmark.observability import RunContext
from memory_benchmark.prompts.benchmarks.halumem import (
    build_halumem_unified_answer_prompt,
)
from memory_benchmark.readers.answer import FakeAnswerLLMClient, FrameworkAnswerReader
from memory_benchmark.runners.operation_level import run_operation_level_predictions
from memory_benchmark.runners.prediction import PredictionRunPolicy
from memory_benchmark.storage import ExperimentPaths, read_jsonl


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = ("locomo", "longmemeval", "membench", "beam", "halumem")


class _RegisteredFakeRuntime:
    """记录真实 Graphiti adapter 发出的 product worker 命令。"""

    instances: list["_RegisteredFakeRuntime"] = []

    def __init__(self, **kwargs: Any) -> None:
        """保存独占 storage root 与命令账。"""

        self.kwargs = kwargs
        self.started = 0
        self.ingest_calls: list[dict[str, Any]] = []
        self.retrieve_calls: list[dict[str, Any]] = []
        self.session_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.close_calls = 0
        type(self).instances.append(self)

    def ensure_started(self) -> None:
        """记录 prepare 的 runtime 握手。"""

        self.started += 1

    def ingest(self, **kwargs: Any) -> dict[str, Any]:
        """返回一个产品 episode 与一条 resolved edge。"""

        self.ingest_calls.append(dict(kwargs))
        return {
            "edge_count": 1,
            "embedding_observations": [],
            "episode_uuid": f"episode-{len(self.ingest_calls)}",
            "llm_observations": [],
            "reused_operation": False,
        }

    def retrieve(self, **kwargs: Any) -> dict[str, Any]:
        """返回稳定 product rank 与真实 public turn lineage。"""

        self.retrieve_calls.append(dict(kwargs))
        return {
            "embedding_observations": [],
            "items": [
                {
                    "expired_at": None,
                    "fact": "Graphiti current fact.",
                    "invalid_at": None,
                    "reference_time": "2026-01-01T00:00:00+00:00",
                    "source_turn_ids": [self.ingest_calls[0]["turn_id"]],
                    "uuid": "edge-1",
                    "valid_at": "2026-01-01T00:00:00+00:00",
                }
            ],
            "latency_ms": 0.5,
        }

    def session_memories(self, **kwargs: Any) -> dict[str, Any]:
        """返回 session-local active fact。"""

        self.session_calls.append(dict(kwargs))
        return {"memories": ["Graphiti current fact."]}

    def delete_conversation(self, *, isolation_key: str) -> dict[str, Any]:
        """返回 exact physical delete 确认。"""

        self.delete_calls.append(isolation_key)
        return {"deleted": True}

    def close(self) -> None:
        """记录通用 runner cleanup。"""

        self.close_calls += 1


class _RegisteredGraphiti(GraphitiOSS):
    """保留生产 adapter，只替换 isolated product worker。"""

    instances: list["_RegisteredGraphiti"] = []

    def __init__(self, **kwargs: Any) -> None:
        """注入 fake runtime。"""

        super().__init__(**kwargs, runtime_factory=_RegisteredFakeRuntime)
        self.prepare_calls = 0
        type(self).instances.append(self)

    def prepare(self, run_context: Any) -> None:
        """记录并执行 production lazy prepare。"""

        self.prepare_calls += 1
        super().prepare(run_context)


class _FakeAnswerClient:
    """离线 framework answer client。"""

    model_name = "fake-answer-client"

    def __init__(
        self,
        *,
        settings: OpenAISettings,
        answer_settings: AnswerLLMSettings,
    ) -> None:
        """保存公开 answer runtime 配置。"""

        self.settings = settings
        self.answer_settings = answer_settings

    def complete(self, *, prompt: str) -> str:
        """确认 unified builder 消费 Graphiti product readout。"""

        assert "Graphiti current fact." in prompt
        return "framework fake answer"


@pytest.mark.parametrize("benchmark_name", BENCHMARKS)
def test_graphiti_registered_prediction_runs_all_five_benchmarks(
    benchmark_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """五格均穿过 registry、turn event、真实 adapter 与统一 answer builder。"""

    _RegisteredGraphiti.instances.clear()
    _RegisteredFakeRuntime.instances.clear()
    _install_offline_stack(monkeypatch, tmp_path)
    run_id = f"graphiti-{benchmark_name}-fake-smoke"

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="graphiti",
        benchmark_name=benchmark_name,
        profile_name="smoke",
        run_id=run_id,
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        enable_efficiency_observability=False,
        progress_enabled=False,
    )

    assert result.benchmark == benchmark_name
    assert len(_RegisteredGraphiti.instances) == 1
    assert _RegisteredGraphiti.instances[0].prepare_calls == 1
    assert len(_RegisteredFakeRuntime.instances) == 1
    runtime = _RegisteredFakeRuntime.instances[0]
    assert runtime.started == 1
    assert len(runtime.ingest_calls) == 2
    assert runtime.close_calls == 1
    bodies = [call["episode_body"] for call in runtime.ingest_calls]
    if benchmark_name == "locomo":
        assert bodies == [
            "Alice (user): fact one",
            "Bob (assistant): fact two",
        ]
    else:
        assert bodies == ["user: fact one", "assistant: fact two"]
    assert all(
        call["reference_time"] == "2026-01-01T00:00:00+00:00"
        for call in runtime.ingest_calls
    )
    assert "private answer" not in json.dumps(
        runtime.ingest_calls,
        ensure_ascii=False,
    )
    assert "private evidence" not in json.dumps(
        runtime.ingest_calls,
        ensure_ascii=False,
    )

    run_dir = tmp_path / "outputs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    predictions = read_jsonl(run_dir / "artifacts/method_predictions.jsonl")
    prompts = read_jsonl(run_dir / "artifacts/answer_prompts.prediction.jsonl")
    public_questions = read_jsonl(run_dir / "artifacts/public_questions.jsonl")

    assert manifest["method_name"] == "Graphiti OSS"
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["consume_granularity"] == "turn"
    assert manifest["method"]["provenance_granularity"] == "turn"
    assert manifest["method"]["retrieval_evidence_contract_version"] == "v1"
    config = manifest["method"]["config"]
    assert config["adapter_version"] == "graphiti-oss-product-v1"
    assert config["product_surface"] == "Graphiti.add_episode+Graphiti.search"
    assert config["search_recipe"] == "edge-bm25+cosine+rrf"
    assert config["embedding_dimension"] == 384
    assert predictions[0]["answer"] == "framework fake answer"
    assert [item["item_id"] for item in prompts[0]["retrieved_items"]] == [
        "edge-1"
    ]
    evidence = prompts[0]["retrieval_evidence"]
    assert evidence["semantic_provenance"]["status"] == "valid"
    assert evidence["stable_ranking"]["status"] == "valid"
    assert evidence["provenance_granularity"] == "turn"
    assert public_questions[0]["question_id"] == f"{benchmark_name}:q1"
    assert "gold_answers" not in public_questions[0]
    assert "evidence" not in public_questions[0]


def test_graphiti_registered_w2_uses_independent_provider_workers_and_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W2 必须是两个 provider/worker/root，不能共享 embedded runtime。"""

    _RegisteredGraphiti.instances.clear()
    _RegisteredFakeRuntime.instances.clear()
    _install_offline_stack(monkeypatch, tmp_path)
    registration = _fake_registration("locomo")
    registration.prepare = lambda project_root, request: _prepared_two_conversations(
        project_root=project_root,
        request=request,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda _benchmark_name: registration,
    )

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="graphiti",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="graphiti-locomo-fake-w2",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=2,
        smoke_max_workers=2,
        enable_efficiency_observability=False,
        progress_enabled=False,
    )

    assert result.runs[0].summary.completed_questions == 2
    assert len(_RegisteredGraphiti.instances) == 2
    assert len(_RegisteredFakeRuntime.instances) == 2
    assert len(
        {
            runtime.kwargs["storage_root"]
            for runtime in _RegisteredFakeRuntime.instances
        }
    ) == 2
    assert len(
        {
            runtime.ingest_calls[0]["isolation_key"]
            for runtime in _RegisteredFakeRuntime.instances
        }
    ) == 2
    assert all(runtime.close_calls == 1 for runtime in _RegisteredFakeRuntime.instances)


def test_graphiti_halumem_operation_runner_keeps_extraction_update_and_qa(
    tmp_path: Path,
) -> None:
    """Graphiti session edge report支持 extraction/update，QA 走统一 reader。"""

    _RegisteredGraphiti.instances.clear()
    _RegisteredFakeRuntime.instances.clear()
    paths = replace(load_path_settings(PROJECT_ROOT), outputs_root=tmp_path)
    config = load_method_profile("graphiti", "smoke", project_root=PROJECT_ROOT)
    context = RunContext.create(
        run_id="graphiti-halumem-operation-fake",
        benchmark_name="halumem",
        method_name="Graphiti OSS",
        model_name="mimo-v2.5",
        output_root=tmp_path,
    )
    provider = _RegisteredGraphiti(
        config=config,
        path_settings=paths,
        storage_root=context.method_state_dir,
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            model="mimo-v2.5",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        benchmark_name="halumem",
        session_memory_report=True,
    )
    question = Question(
        question_id="halu-user-1:s1:q1",
        conversation_id="halu-user-1",
        text="Where does Riley live?",
    )
    dataset = Dataset(
        dataset_name="halumem",
        metadata={"variant": "medium", "run_scope": "smoke"},
        conversations=[
            Conversation(
                conversation_id="halu-user-1",
                sessions=[
                    Session(
                        session_id="s1",
                        session_time="2025-09-04T18:42:18+00:00",
                        turns=[
                            Turn(
                                turn_id="s1:t1",
                                speaker="user",
                                normalized_role="user",
                                content="I live in Boston.",
                            )
                        ],
                        private_metadata={
                            "is_generated_qa_session": False,
                            "memory_points": [
                                {
                                    "index": 1,
                                    "memory_content": "Riley lives in Boston",
                                    "memory_type": "Persona Memory",
                                    "is_update": "True",
                                    "original_memories": ["Riley lived elsewhere"],
                                }
                            ],
                        },
                    )
                ],
                questions=[question],
                gold_answers={
                    question.question_id: GoldAnswerInfo(
                        question_id=question.question_id,
                        answer="Boston",
                        evidence=["Riley lives in Boston"],
                        metadata={"session_id": "s1"},
                    )
                },
            )
        ],
    )

    summary = run_operation_level_predictions(
        dataset=dataset,
        provider=provider,
        run_context=context,
        policy=PredictionRunPolicy(max_workers=1, progress_enabled=False),
        method_manifest=config.to_manifest(),
        benchmark_variant="medium",
        run_scope=RunScope.SMOKE,
        answer_reader=FrameworkAnswerReader(
            client=FakeAnswerLLMClient(answer="Boston")
        ),
        unified_prompt_builder=build_halumem_unified_answer_prompt,
        protocol_version="v3",
        provenance_granularity="turn",
        retrieval_evidence_contract_version="v1",
    )

    runtime = _RegisteredFakeRuntime.instances[0]
    artifact_paths = ExperimentPaths.create(context.run_dir)
    session_reports = read_jsonl(artifact_paths.session_memory_reports_path)
    update_probes = read_jsonl(
        artifact_paths.artifacts_dir / "update_probe_results.jsonl"
    )
    answer_prompts = read_jsonl(artifact_paths.answer_prompts_path)
    assert summary.completed_questions == 1
    assert provider.prepare_calls == 1
    assert len(runtime.ingest_calls) == 1
    assert len(runtime.retrieve_calls) == 2
    assert runtime.close_calls == 1
    assert session_reports[0]["status"] == "ok"
    assert session_reports[0]["memories"] == ["Graphiti current fact."]
    assert update_probes[0]["memories_from_system"] == [
        "Graphiti current fact."
    ]
    evidence = answer_prompts[0]["retrieval_evidence"]
    assert evidence["semantic_provenance"]["status"] == "valid"
    assert evidence["stable_ranking"]["status"] == "valid"
    assert evidence["provenance_granularity"] == "turn"


def test_graphiti_membench_100k_fails_before_cost_runtime_and_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """缺时 variant 必须在 confirm/API/config/output 前由 registry 门拒绝。"""

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
        "_confirm_prediction_cost",
        lambda **_kwargs: pytest.fail("cost confirmation must not be reached"),
    )
    monkeypatch.setattr(
        run_prediction_module,
        "load_method_profile",
        lambda **_kwargs: pytest.fail("method config must not be loaded"),
    )

    with pytest.raises(
        ConfigurationError,
        match="does not support MemBench variant '100k'",
    ):
        run_prediction_module.run_registered_conversation_qa_prediction(
            project_root=PROJECT_ROOT,
            method_name="graphiti",
            benchmark_name="membench",
            profile_name="smoke",
            variant="100k",
            run_id="graphiti-membench-100k-rejected",
            confirm_api=True,
            progress_enabled=False,
        )

    assert not (tmp_path / "outputs").exists()


def _install_offline_stack(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """替换 API 与 benchmark loader，保留 registry/runner 生产链。"""

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
            model="mimo-v2.5",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        _FakeAnswerClient,
        raising=False,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: _fake_registration(benchmark_name),
    )
    monkeypatch.setattr(method_registry_module, "GraphitiOSS", _RegisteredGraphiti)


def _fake_registration(benchmark_name: str) -> SimpleNamespace:
    """构造五家共用的最小 benchmark registration。"""

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
        unified_prompt_builder=_fake_prompt_builder,
    )


def _fake_prompt_builder(
    question: Question,
    retrieval_result: Any,
) -> AnswerPromptResult:
    """用 framework builder 消费完整 Graphiti formatted_memory。"""

    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        prompt_messages=[
            PromptMessage(role="system", content="Answer from memory."),
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
    """返回固定两 turn 数据并校验 smoke 裁剪请求。"""

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


def _prepared_two_conversations(
    *,
    project_root: Path,
    request: BenchmarkLoadRequest,
) -> PreparedBenchmarkRun:
    """返回两个 LoCoMo isolation，供 isolated W2 验证。"""

    assert project_root == PROJECT_ROOT
    assert request == BenchmarkLoadRequest(
        variant="locomo-fake",
        run_scope=RunScope.SMOKE,
        smoke_turn_limit=2,
        smoke_conversation_limit=2,
    )
    first = _fake_dataset("locomo").conversations[0]
    second_question = Question(
        question_id="locomo:q2",
        conversation_id="locomo:conv-2",
        text="What should locomo remember next?",
    )
    second = Conversation(
        conversation_id="locomo:conv-2",
        metadata={"speaker_a": "Alice", "speaker_b": "Bob"},
        sessions=first.sessions,
        questions=[second_question],
        gold_answers={
            second_question.question_id: GoldAnswerInfo(
                question_id=second_question.question_id,
                answer="private answer",
                evidence=["private evidence"],
            )
        },
    )
    return PreparedBenchmarkRun(
        variant="locomo-fake",
        run_scope=RunScope.SMOKE,
        dataset=Dataset(
            dataset_name="locomo",
            metadata={"variant": "locomo-fake", "run_scope": "smoke"},
            conversations=[first, second],
        ),
        source_relative_paths=(Path("pyproject.toml"),),
    )


def _fake_dataset(benchmark_name: str) -> Dataset:
    """构造带公开 speaker/session time 与私有 gold 的最小数据集。"""

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
                                speaker=(
                                    "Alice" if benchmark_name == "locomo" else "user"
                                ),
                                normalized_role="user",
                                content="fact one",
                            ),
                            Turn(
                                turn_id="t2",
                                speaker=(
                                    "Bob"
                                    if benchmark_name == "locomo"
                                    else "assistant"
                                ),
                                normalized_role="assistant",
                                content="fact two",
                            ),
                        ],
                    )
                ],
                questions=[question],
                gold_answers={
                    question.question_id: GoldAnswerInfo(
                        question_id=question.question_id,
                        answer="private answer",
                        evidence=["private evidence"],
                    )
                },
            )
        ],
    )
