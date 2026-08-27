"""LightMem paper-native answer/judge profile 逐字 parity 测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters.locomo_prompt import (
    build_locomo_unified_answer_prompt,
)
from memory_benchmark.core import (
    AnswerResult,
    ConfigurationError,
    GoldAnswerInfo,
    PromptMessage,
    Question,
)
from memory_benchmark.core.provider_protocol import RetrievedItem, RetrievalResult
from memory_benchmark.evaluators.locomo_judge import LoCoMoJudgeEvaluator
from memory_benchmark.prompts.author.lightmem import (
    LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROMPT,
    LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT,
    LIGHTMEM_NATIVE_ANSWER_PROFILES,
    LIGHTMEM_NATIVE_JUDGE_PROFILES,
    build_lightmem_locomo_native_answer_prompt,
    build_lightmem_longmemeval_native_answer_prompt,
    lightmem_locomo_native_judge_skips_category,
)
from memory_benchmark.runners.prediction_answer import _retrieval_result_from_record


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LIGHTMEM_ROOT = PROJECT_ROOT / "third_party" / "methods" / "LightMem" / "experiments"


def test_locomo_native_answer_matches_runtime_official_ast() -> None:
    """LoCoMo native answer 应与官方标准模板替换后逐字一致。"""

    official = _assignment_string(
        LIGHTMEM_ROOT / "locomo" / "prompts.py", "ANSWER_PROMPT"
    )
    expected = official.format(
        speaker_1_name="Alice",
        speaker_1_memories="Alice memory",
        speaker_2_name="Bob",
        speaker_2_memories="Bob memory",
        question="What happened?",
    )
    question = Question("q1", "c1", "What happened?")
    retrieval = RetrievalResult(
        formatted_memory="Alice memory\nBob memory",
        prompt_messages=(PromptMessage(role="system", content=expected),),
    )
    result = build_lightmem_locomo_native_answer_prompt(question, retrieval)

    assert LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROMPT == official
    assert result.prompt_messages == [PromptMessage(role="system", content=expected)]
    assert result.answer_prompt == expected


def test_locomo_author_answer_rebuilds_exactly_from_compact_items() -> None:
    """v2 artifact 只凭结构化命中也应重建首次 speaker 顺序与 pretty date。"""

    question = Question("q1", "c1", "What happened?")
    items = (
        RetrievedItem(
            item_id="b1",
            content="2023-05-09T08:30:00.000 Tue Bob memory",
            score=0.9,
            timestamp="2023-05-09T08:30:00.000",
            metadata={"source": "vector", "speaker_name": "Bob", "weekday": "Tue"},
        ),
        RetrievedItem(
            item_id="a1",
            content="2023-05-08T13:56:00.000 Mon Alice memory",
            score=0.8,
            timestamp="2023-05-08T13:56:00.000",
            metadata={
                "source": "vector",
                "speaker_name": "Alice",
                "weekday": "Mon",
            },
        ),
        RetrievedItem(
            item_id="b2",
            content="2023-05-10T10:00:00.000 Wed Bob second memory",
            score=0.7,
            timestamp="2023-05-10T10:00:00.000",
            metadata={"source": "vector", "speaker_name": "Bob", "weekday": "Wed"},
        ),
    )
    result = build_lightmem_locomo_native_answer_prompt(
        question,
        RetrievalResult(formatted_memory="product readout", items=items),
    )
    expected = LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROMPT.format(
        speaker_1_name="Bob",
        speaker_1_memories=(
            "[Memory recorded on: 09 May 2023, Tue]\nBob memory\n\n"
            "[Memory recorded on: 10 May 2023, Wed]\nBob second memory"
        ),
        speaker_2_name="Alice",
        speaker_2_memories=(
            "[Memory recorded on: 08 May 2023, Mon]\nAlice memory"
        ),
        question=question.text,
    )

    assert result.answer_prompt == expected
    assert result.prompt_messages == [PromptMessage(role="system", content=expected)]
    assert result.metadata["prompt_track"] == "unified"


def test_locomo_author_compact_item_shape_fails_loudly() -> None:
    """缺 speaker/weekday 的旧 compact item 不得静默生成不同作者 prompt。"""

    item = RetrievedItem(
        item_id="m1",
        content="2023-05-08T13:56:00.000 Mon memory",
        score=0.9,
        timestamp="2023-05-08T13:56:00.000",
        metadata={"source": "vector"},
    )
    with pytest.raises(ConfigurationError, match="missing speaker_name"):
        build_lightmem_locomo_native_answer_prompt(
            Question("q1", "c1", "What happened?"),
            RetrievalResult(formatted_memory="memory", items=(item,)),
        )


def test_locomo_author_builder_rebuilds_from_json_artifact_shape() -> None:
    """JSON 往返后的 v2 payload 不依赖已释放 provider 的 prompt_messages。"""

    record = {
        "formatted_memory": "2023-05-08T13:56:00.000 Mon Alice memory",
        "retrieved_items": [
            {
                "item_id": "a1",
                "content": "2023-05-08T13:56:00.000 Mon Alice memory",
                "score": 0.8,
                "timestamp": "2023-05-08T13:56:00.000",
                "source_turn_ids": ["D1:1"],
                "metadata": {
                    "source": "vector",
                    "speaker_name": "Alice",
                    "weekday": "Mon",
                },
            }
        ],
        "retrieval_metadata": {"method": "lightmem"},
        "retrieval_evidence": None,
    }
    question = Question("q1", "c1", "What happened?")

    result = build_lightmem_locomo_native_answer_prompt(
        question,
        _retrieval_result_from_record(record),
    )

    assert "Memories for user Alice:" in result.answer_prompt
    assert "[Memory recorded on: 08 May 2023, Mon]\nAlice memory" in (
        result.answer_prompt
    )
    assert "prompt_messages" not in record


def test_longmemeval_native_answer_matches_runtime_official_ast() -> None:
    """LongMemEval native answer 的 system/user messages 应与官方调用点逐字一致。"""

    item = {"question_date": "2025-01-02", "question": "What happened?"}
    related_memories = ["memory one", "memory two"]
    official_messages = _official_longmemeval_answer_messages(item, related_memories)
    result = build_lightmem_longmemeval_native_answer_prompt(
        Question("q1", "c1", item["question"], question_time=item["question_date"]),
        RetrievalResult(
            formatted_memory="reader-formatted-memory-must-not-be-used",
            prompt_messages=tuple(
                PromptMessage(role=message["role"], content=message["content"])
                for message in official_messages
            ),
        ),
    )

    assert [message.to_dict() for message in result.prompt_messages] == official_messages


def test_locomo_native_judge_matches_official_ast_and_skips_category_five() -> None:
    """LoCoMo native judge prompt/参数与 category 5 跳过语义应一手一致。"""

    official = _assignment_string(
        LIGHTMEM_ROOT / "locomo" / "llm_judge.py", "ACCURACY_PROMPT"
    )
    profile = LIGHTMEM_NATIVE_JUDGE_PROFILES["locomo"]
    assert LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT == official
    assert profile.prompt_template == official
    assert profile.temperature == 0.0
    assert profile.response_format == {"type": "json_object"}
    assert profile.skipped_categories == frozenset({"5"})
    assert lightmem_locomo_native_judge_skips_category(5) is True
    assert lightmem_locomo_native_judge_skips_category("5") is True
    assert lightmem_locomo_native_judge_skips_category(4) is False


def test_longmemeval_native_judge_reuses_existing_official_evaluator() -> None:
    """LongMemEval native judge 应映射到现有官方 parity evaluator，不重复实现。"""

    profile = LIGHTMEM_NATIVE_JUDGE_PROFILES["longmemeval"]
    assert profile.evaluator_key == "longmemeval-judge"
    assert profile.prompt_template is None
    assert (profile.temperature, profile.max_tokens, profile.n) == (0.0, 10, 1)


def test_native_answer_parameters_match_each_official_final_call() -> None:
    """LoCoMo 与 LME 的最终 API 调用参数不同，不能再误共用一组默认。"""

    locomo = LIGHTMEM_NATIVE_ANSWER_PROFILES["locomo"].settings
    longmemeval = LIGHTMEM_NATIVE_ANSWER_PROFILES["longmemeval"].settings
    assert (locomo.temperature, locomo.max_tokens, locomo.top_p) == (
        0.0,
        None,
        None,
    )
    assert (longmemeval.temperature, longmemeval.max_tokens, longmemeval.top_p) == (
        0.0,
        2000,
        0.8,
    )


def test_native_and_unified_locomo_answer_tracks_are_textually_distinct() -> None:
    """LightMem native LoCoMo answer 不得退化成 benchmark unified prompt。"""

    question = Question("q1", "c1", "What happened?")
    native_text = LIGHTMEM_LOCOMO_NATIVE_ANSWER_PROMPT.format(
        speaker_1_name="Alice",
        speaker_1_memories="memory one",
        speaker_2_name="Bob",
        speaker_2_memories="memory two",
        question=question.text,
    )
    retrieval = RetrievalResult(formatted_memory="memory one\nmemory two")
    unified_text = build_locomo_unified_answer_prompt(question, retrieval).answer_prompt
    assert native_text != unified_text


def test_native_and_existing_locomo_judge_profiles_are_textually_distinct() -> None:
    """逐字 native judge 应保留现有 auxiliary judge 的七处文本差异。"""

    question = Question("q1", "c1", "What happened?")
    prediction = AnswerResult("q1", "c1", "answer")
    gold = GoldAnswerInfo("q1", "gold")
    existing = LoCoMoJudgeEvaluator(mode="compact").build_prompt(
        question, prediction, gold
    )
    native = LIGHTMEM_LOCOMO_NATIVE_JUDGE_PROMPT.format(
        question=question.text,
        gold_answer=gold.answer,
        generated_answer=prediction.answer,
    )
    assert native != existing


def _assignment_string(path: Path, variable_name: str) -> str:
    """运行时 AST 提取官方模块级字符串常量。"""

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == variable_name
        ):
            value = ast.literal_eval(node.value)
            assert isinstance(value, str)
            return value
    raise AssertionError(f"{variable_name} not found in {path}")


def _official_longmemeval_answer_messages(
    item: dict[str, str], related_memories: list[str]
) -> list[dict[str, str]]:
    """从官方 AST 现场执行 182-187 行 message 构造，不导入有副作用模块。"""

    path = LIGHTMEM_ROOT / "longmemeval" / "run_lightmem_gpt.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.Assign, ast.Expr))
        and getattr(node, "lineno", 0) in {182, 183, 184}
    ]
    nodes.sort(key=lambda node: node.lineno)
    module = ast.fix_missing_locations(ast.Module(body=nodes, type_ignores=[]))
    namespace: dict[str, object] = {
        "item": item,
        "related_memories": related_memories,
    }
    exec(compile(module, str(path), "exec"), {}, namespace)
    messages = namespace["messages"]
    assert isinstance(messages, list)
    return messages
