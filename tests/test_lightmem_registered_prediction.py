"""测试 LightMem 通过统一 registry 进入通用 prediction runner 的装配。

本文件只使用 fake LightMem runtime，不初始化官方 LightMemory、不调用真实 API。
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.benchmark_adapters import (
    BenchmarkLoadRequest,
    BenchmarkRegistration,
    BenchmarkVariantSpec,
    PreparedBenchmarkRun,
    RunScope,
)
from memory_benchmark.benchmark_adapters.base import BenchmarkAdapter
from memory_benchmark.cli import run_prediction as run_prediction_module
from memory_benchmark.config import AnswerLLMSettings, OpenAISettings, load_path_settings
from memory_benchmark.core import (
    AddResult,
    AnswerResult,
    Conversation,
    Dataset,
    GoldAnswerInfo,
    MethodCapability,
    Question,
    AnswerPromptResult,
    PromptMessage,
    Session,
    TaskFamily,
    Turn,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
)
from memory_benchmark.methods import registry as method_registry_module
from memory_benchmark.prompts.benchmarks.locomo import (
    build_locomo_unified_answer_prompt,
)
from memory_benchmark.readers.answer import AnswerLLMResponse
from memory_benchmark.storage import read_jsonl


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class FakeLightMemForRegisteredPrediction(MemoryProvider):
    """替代真实 LightMem adapter，避免模型加载和 API 调用。"""

    instances: list["FakeLightMemForRegisteredPrediction"] = []
    consume_granularity = "turn"

    def __init__(self, **kwargs) -> None:
        """记录 registry factory 传入的构造参数。"""

        self.kwargs = kwargs
        if kwargs.get("consume_granularity") is not None:
            self.consume_granularity = kwargs["consume_granularity"]
        self.ingested_units: list[IngestUnit] = []
        self.answered_questions: list[Question] = []
        self.retrieved_questions: list[Question] = []
        self.instances.append(self)

    def ingest(self, unit: IngestUnit) -> IngestResult:
        """记录生产事件流交付的公开 ingest unit。"""

        self.ingested_units.append(unit)
        return IngestResult()

    def get_answer(self, question: Question) -> AnswerResult:
        """返回固定答案，用于验证通用 runner artifacts。"""

        self.answered_questions.append(question)
        return AnswerResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer=f"fake lightmem answer for {question.question_id}",
        )

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回固定检索上下文，用于验证 retrieve-first runner artifacts。"""

        question = query.source_question
        assert question is not None
        self.retrieved_questions.append(question)
        longmemeval = self.kwargs.get("consume_granularity") == "pair"
        prompt_messages = (
            [
                PromptMessage(role="system", content="You are a helpful assistant."),
                PromptMessage(
                    role="user",
                    content=(
                        f"Question time:{question.question_time} and question:{question.text}\n"
                        "Please answer the question based on the following memories: "
                        "LIGHTMEM-LONGMEMEVAL-NATIVE-MEMORY"
                    ),
                ),
            ]
            if longmemeval
            else [PromptMessage(role="system", content="LIGHTMEM-LOCOMO-NATIVE-PROMPT")]
        )
        return RetrievalResult(
            formatted_memory=f"fake lightmem context for {question.question_id}",
            prompt_messages=tuple(prompt_messages),
            metadata={
                "method": "lightmem",
                "answer_context": "reader-layout-must-not-replace-native-messages",
            },
        )


class FakeBenchmarkAdapter(BenchmarkAdapter):
    """满足 BenchmarkRegistration 类型约束的空 adapter。"""

    name = "locomo"

    def load_dataset(self, limit: int | None = None) -> Dataset:
        """本测试不通过 adapter 实例加载数据。"""

        raise AssertionError("registered smoke uses prepare_run directly")


def _build_registered_smoke_dataset() -> Dataset:
    """构造最小 LoCoMo-like conversation-QA 数据集。"""

    return Dataset(
        dataset_name="locomo",
        metadata={"variant": "locomo10", "run_scope": RunScope.SMOKE.value},
        conversations=[
            Conversation(
                conversation_id="conv-lightmem-1",
                sessions=[
                    Session(
                        session_id="session-1",
                        session_time="2026-01-01",
                        turns=[
                            Turn(
                                turn_id="turn-1",
                                speaker="Alice",
                                content="I like tea.",
                            ),
                            Turn(
                                turn_id="turn-2",
                                speaker="Bob",
                                content="I will remember that.",
                            ),
                        ],
                    )
                ],
                questions=[
                    Question(
                        question_id="q-1",
                        conversation_id="conv-lightmem-1",
                        text="What does Alice like?",
                        category="1",
                    )
                ],
                gold_answers={
                    "q-1": GoldAnswerInfo(
                        question_id="q-1",
                        answer="tea",
                        evidence=["private-evidence"],
                    )
                },
            )
        ],
    )


def _build_fake_benchmark_registration() -> BenchmarkRegistration:
    """构造只含一个 locomo10 variant 的 fake benchmark registration。"""

    def prepare_run(
        project_root: Path,
        request: BenchmarkLoadRequest,
    ) -> PreparedBenchmarkRun:
        """返回固定 smoke dataset，并校验 service 传入的 request。"""

        assert project_root == PROJECT_ROOT
        assert request == BenchmarkLoadRequest(
            variant="locomo10",
            run_scope=RunScope.SMOKE,
            smoke_turn_limit=2,
            smoke_conversation_limit=1,
        )
        return PreparedBenchmarkRun(
            variant="locomo10",
            run_scope=RunScope.SMOKE,
            dataset=_build_registered_smoke_dataset(),
            source_relative_paths=(Path("pyproject.toml"),),
        )

    return BenchmarkRegistration(
        name="locomo",
        adapter_cls=FakeBenchmarkAdapter,
        task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        variants=(
            BenchmarkVariantSpec(
                name="locomo10",
                source_relative_paths=(Path("pyproject.toml"),),
            ),
        ),
        default_variant="locomo10",
        prepare_run=prepare_run,
        prediction_enabled=True,
        prompt_track="unified",
        unified_prompt_builder=build_locomo_unified_answer_prompt,
    )


def test_lightmem_registered_prediction_runs_generic_runner_offline(
    tmp_path,
    monkeypatch,
) -> None:
    """LightMem 应通过统一 registered prediction service 写出标准 artifacts。"""

    FakeLightMemForRegisteredPrediction.instances.clear()
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
        "get_benchmark_registration",
        lambda benchmark_name: _build_fake_benchmark_registration(),
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

    class FakeAnswerClient:
        """离线 fake framework answer client，避免 registered 测试触发真实 API。"""

        model_name = "fake-answer-client"

        def __init__(
            self,
            *,
            settings: OpenAISettings,
            answer_settings: AnswerLLMSettings,
        ) -> None:
            """保存 OpenAI-compatible settings 以覆盖构造路径。"""

            self.settings = settings
            self.answer_settings = answer_settings

        def complete(self, *, prompt: str) -> str:
            """返回固定答案；prompt 内容由 framework reader 负责拼接。"""

            return "framework fake answer"

    monkeypatch.setattr(
        run_prediction_module,
        "OpenAICompatibleAnswerLLMClient",
        FakeAnswerClient,
        raising=False,
    )
    monkeypatch.setattr(
        method_registry_module,
        "LightMem",
        FakeLightMemForRegisteredPrediction,
    )
    registration = method_registry_module.get_method_registration("lightmem")
    monkeypatch.setattr(
        run_prediction_module,
        "get_method_registration",
        lambda method_name: registration,
    )

    result = run_prediction_module.run_registered_conversation_qa_prediction(
        project_root=PROJECT_ROOT,
        method_name="lightmem",
        benchmark_name="locomo",
        profile_name="smoke",
        run_id="lightmem-offline-smoke",
        confirm_api=True,
        smoke_turn_limit=2,
        smoke_conversation_limit=1,
        enable_efficiency_observability=False,
    )

    assert result.benchmark == "locomo"
    assert result.selector == "locomo10"
    assert result.runs[0].run_id == "lightmem-offline-smoke"
    assert len(FakeLightMemForRegisteredPrediction.instances) == 1
    fake_method = FakeLightMemForRegisteredPrediction.instances[0]
    assert fake_method.kwargs["config"].profile_name == "smoke"
    assert len(fake_method.ingested_units) == 2
    assert [unit.turn_id for unit in fake_method.ingested_units] == [
        "turn-1",
        "turn-2",
    ]
    assert fake_method.answered_questions == []
    assert [question.question_id for question in fake_method.retrieved_questions] == [
        "q-1"
    ]

    run_dir = tmp_path / "outputs" / "lightmem-offline-smoke"
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    predictions = read_jsonl(run_dir / "artifacts" / "method_predictions.jsonl")
    public_questions = read_jsonl(run_dir / "artifacts" / "public_questions.jsonl")

    assert manifest["method_name"] == "LightMem"
    assert manifest["method"]["config"]["profile_name"] == "smoke"
    assert manifest["method"]["consume_granularity"] == "turn"
    assert predictions[0]["answer"] == "framework fake answer"
    assert public_questions[0]["question_id"] == "q-1"
    assert "gold_answers" not in public_questions[0]



def test_lightmem_native_config_track_is_rejected_for_new_runs(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """旧 native 资产可读，但不能再从 prediction 入口创建新 run。"""

    real_paths = load_path_settings(PROJECT_ROOT)
    test_paths = replace(real_paths, outputs_root=tmp_path / "outputs")
    monkeypatch.setattr(
        run_prediction_module,
        "load_path_settings",
        lambda project_root: test_paths,
    )
    monkeypatch.setattr(
        run_prediction_module,
        "get_benchmark_registration",
        lambda benchmark_name: _build_fake_benchmark_registration(),
    )

    with pytest.raises(ConfigurationError, match="native config-track"):
        run_prediction_module.run_registered_conversation_qa_prediction(
            project_root=PROJECT_ROOT,
            method_name="lightmem",
            benchmark_name="locomo",
            profile_name="smoke",
            config_track="native",
            run_id="must-not-exist",
            confirm_api=True,
            enable_efficiency_observability=False,
        )

    assert not (tmp_path / "outputs").exists()
