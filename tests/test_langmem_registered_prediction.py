"""测试 LangMem 经 registry 进入五格通用 provider-v3 prediction 链。"""

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
from memory_benchmark.methods import load_method_profile
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.methods.langmem_adapter import LangMem
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
    """记录真实 LangMem adapter 发出的 product 命令，不调用模型。"""

    instances: list["_RegisteredFakeRuntime"] = []

    def __init__(self, **kwargs: Any) -> None:
        """保存 factory 参数并初始化调用账。"""

        self.kwargs = kwargs
        self.started = False
        self.ensure_started_calls = 0
        self.ingest_calls: list[dict[str, Any]] = []
        self.retrieve_calls: list[dict[str, Any]] = []
        self.delete_calls: list[str] = []
        self.close_calls = 0
        self.instances.append(self)

    def ensure_started(self) -> None:
        """记录通用 runner 的 prepare。"""

        if not self.started:
            self.ensure_started_calls += 1
            self.started = True

    def ingest(
        self,
        *,
        namespace_id: str,
        operation_id: str,
        messages: list[dict[str, str]],
        max_steps: int,
    ) -> dict[str, Any]:
        """记录完整 session messages，并返回精确观测。"""

        self.ensure_started()
        self.ingest_calls.append(
            {
                "namespace_id": namespace_id,
                "operation_id": operation_id,
                "messages": messages,
                "max_steps": max_steps,
            }
        )
        return {
            "changed_memories": [
                {
                    "key": "memory-1",
                    "value": {
                        "kind": "Memory",
                        "content": {"content": "LangMem current memory."},
                    },
                }
            ],
            "changed_memory_keys": ["memory-1"],
            "embedding_observations": [
                {"input_tokens": 5, "latency_ms": 0.5, "text_count": 1}
            ],
            "llm_observations": [{"input_tokens": 10, "output_tokens": 2}],
            "memory_count": 1,
            "rehydrated_entry_count": 0,
            "rehydration_embedding_calls": 0,
            "reused_operation": False,
        }

    def retrieve(
        self,
        *,
        namespace_id: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        """返回一条 evolved product memory。"""

        self.ensure_started()
        self.retrieve_calls.append(
            {"namespace_id": namespace_id, "query": query, "limit": limit}
        )
        return {
            "embedding_observations": [
                {"input_tokens": 3, "latency_ms": 0.25, "text_count": 1}
            ],
            "items": [
                {
                    "key": "memory-1",
                    "content": "LangMem current memory.",
                    "kind": "Memory",
                    "score": 0.9,
                }
            ],
            "latency_ms": 0.75,
            "rehydrated_entry_count": 0,
            "rehydration_embedding_calls": 0,
        }

    def delete_namespace(self, *, namespace_id: str) -> dict[str, Any]:
        """为 clean-hook 提供幂等删除结果。"""

        self.delete_calls.append(namespace_id)
        return {"deleted": True, "deleted_entry_count": 1}

    def close(self) -> None:
        """记录通用 runner 的 cleanup。"""

        self.close_calls += 1


class _RegisteredLangMem(LangMem):
    """保留生产 adapter，只替换独立 worker runtime。"""

    instances: list["_RegisteredLangMem"] = []

    def __init__(self, **kwargs: Any) -> None:
        """把 fake runtime 注入真实 adapter。"""

        super().__init__(**kwargs, runtime_factory=_RegisteredFakeRuntime)
        self.prepare_calls = 0
        self.instances.append(self)

    def prepare(self, run_context: Any) -> None:
        """记录 generic runner 的 prepare 并调用生产实现。"""

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
        """保存构造身份。"""

        self.settings = settings
        self.answer_settings = answer_settings

    def complete(self, *, prompt: str) -> str:
        """验证 builder 收到 product readout 后返回固定答案。"""

        assert "LangMem current memory." in prompt
        return "framework fake answer"


@pytest.mark.parametrize("benchmark_name", BENCHMARKS)
def test_langmem_registered_prediction_runs_five_benchmarks_through_generic_runner(
    benchmark_name: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """五家均穿过 registry、session 聚合、真实 adapter 与统一 builder。"""

    _RegisteredLangMem.instances.clear()
    _RegisteredFakeRuntime.instances.clear()
    _install_offline_stack(monkeypatch, tmp_path)
    run_id = f"langmem-{benchmark_name}-fake-smoke"

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="langmem",
        benchmark_name=benchmark_name,
        profile_name="smoke",
        run_id=run_id,
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        enable_efficiency_observability=False,
    )

    assert result.benchmark == benchmark_name
    assert len(_RegisteredLangMem.instances) == 1
    assert _RegisteredLangMem.instances[0].prepare_calls == 1
    assert len(_RegisteredFakeRuntime.instances) == 1
    runtime = _RegisteredFakeRuntime.instances[0]
    assert runtime.ensure_started_calls >= 1
    assert len(runtime.ingest_calls) == 1
    assert runtime.close_calls == 1
    messages = runtime.ingest_calls[0]["messages"]
    assert [message["role"] for message in messages] == ["user", "assistant"]
    if benchmark_name == "locomo":
        assert messages == [
            {
                "role": "user",
                "content": "[Session time: 2026-01-01T00:00:00] Alice: fact one",
            },
            {
                "role": "assistant",
                "content": "[Session time: 2026-01-01T00:00:00] Bob: fact two",
            },
        ]
    else:
        assert messages == [
            {
                "role": "user",
                "content": "[Session time: 2026-01-01T00:00:00] fact one",
            },
            {
                "role": "assistant",
                "content": "[Session time: 2026-01-01T00:00:00] fact two",
            },
        ]
    serialized_messages = json.dumps(messages, ensure_ascii=False)
    assert "private answer" not in serialized_messages
    assert "private evidence" not in serialized_messages

    run_dir = tmp_path / "outputs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    prompts = read_jsonl(run_dir / "artifacts" / "answer_prompts.prediction.jsonl")
    public_questions = read_jsonl(run_dir / "artifacts" / "public_questions.jsonl")

    assert manifest["method_name"] == "LangMem"
    assert manifest["method"]["protocol_version"] == "v3"
    assert manifest["method"]["consume_granularity"] == "session"
    assert manifest["method"]["provenance_granularity"] == "none"
    assert manifest["method"]["retrieval_evidence_contract_version"] == "v1"
    config = manifest["method"]["config"]
    assert config["adapter_version"] == "langmem-background-product-v2"
    assert config["product_surface"] == (
        "create_memory_store_manager+ainvoke+asearch"
    )
    assert config["query_model"] is None
    assert config["query_limit"] == 5
    assert config["enable_deletes"] is False
    assert predictions[0]["answer"] == "framework fake answer"
    assert [item["item_id"] for item in prompts[0]["retrieved_items"]] == [
        "memory-1"
    ]
    evidence = prompts[0]["retrieval_evidence"]
    assert evidence["semantic_provenance"]["status"] == "n_a"
    assert evidence["stable_ranking"]["status"] == "valid"
    assert evidence["provenance_granularity"] == "none"
    assert public_questions[0]["question_id"] == f"{benchmark_name}:q1"
    assert "gold_answers" not in public_questions[0]
    assert "evidence" not in public_questions[0]


def test_langmem_halumem_operation_runner_reports_changed_product_memory(
    tmp_path: Path,
) -> None:
    """operation runner 报告事务 current delta，并保留 evolved-state update/QA。"""

    _RegisteredLangMem.instances.clear()
    _RegisteredFakeRuntime.instances.clear()
    paths = replace(load_path_settings(PROJECT_ROOT), outputs_root=tmp_path)
    config = load_method_profile("langmem", "smoke", project_root=PROJECT_ROOT)
    context = RunContext.create(
        run_id="langmem-halumem-operation-fake",
        benchmark_name="halumem",
        method_name="LangMem",
        model_name="ox-alpha-free",
        output_root=tmp_path,
    )
    provider = _RegisteredLangMem(
        config=config,
        path_settings=paths,
        storage_root=context.method_state_dir,
        openai_settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            model="ox-alpha-free",
            provider="opencodego",
            judge_transport="chat_completions",
        ),
        session_memory_report=True,
        benchmark_name="halumem",
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
        provenance_granularity="none",
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
    assert session_reports[0]["memories"] == ["LangMem current memory."]
    assert update_probes[0]["memories_from_system"] == [
        "LangMem current memory."
    ]
    evidence = answer_prompts[0]["retrieval_evidence"]
    assert evidence["semantic_provenance"]["status"] == "n_a"
    assert evidence["stable_ranking"]["status"] == "valid"


def test_langmem_registered_w2_uses_two_independent_runtime_and_state_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W2 必须是两个 provider/worker/store/state owner，不能共享 tokenizer 或状态。"""

    _RegisteredLangMem.instances.clear()
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
        method_name="langmem",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="langmem-locomo-fake-w2",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=2,
        smoke_max_workers=2,
        enable_efficiency_observability=False,
        progress_enabled=False,
    )

    assert len(result.runs) == 1
    assert result.runs[0].summary.completed_questions == 2
    assert len(_RegisteredLangMem.instances) == 2
    assert len(_RegisteredFakeRuntime.instances) == 2
    storage_roots = {
        runtime.kwargs["storage_root"]
        for runtime in _RegisteredFakeRuntime.instances
    }
    namespaces = {
        runtime.ingest_calls[0]["namespace_id"]
        for runtime in _RegisteredFakeRuntime.instances
    }
    assert len(storage_roots) == 2
    assert len(namespaces) == 2
    assert all(runtime.close_calls == 1 for runtime in _RegisteredFakeRuntime.instances)


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
        lambda project_root, api_provider=None, expected_model=None: OpenAISettings(
            api_key="sk-test",
            base_url="https://example.invalid/v1",
            model="ox-alpha-free",
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
    monkeypatch.setattr(method_registry_module, "LangMem", _RegisteredLangMem)


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
    """用 framework builder 消费 LangMem 的完整 formatted_memory。"""

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
    """返回两个 LoCoMo isolation，供真实 isolated-worker runner 验证 W2。"""

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
