"""测试 retrieve-first 核心协议。

本文件只验证 core 层数据结构和抽象接口，不调用外部模型。测试目标是确认
新的 memory-module 接口能够以单个 Conversation 为写入单位，并按 Question
返回 method 构造好的完整 AnswerPromptResult.answer_prompt。
"""

from __future__ import annotations

from memory_benchmark.core import (
    AddResult,
    AnswerPromptResult,
    Conversation,
    MethodCapability,
    Question,
    Session,
    Turn,
)
from memory_benchmark.core.interfaces import BaseMemoryProvider


class TinyProvider(BaseMemoryProvider):
    """最小 retrieve-first provider，用于验证抽象接口可实例化。"""

    def __init__(self) -> None:
        """初始化测试用状态。

        输入:
            无。

        输出:
            None。`added` 记录写入过的 conversation id，便于断言。
        """

        self.added: list[str] = []

    def add(self, conversation: Conversation) -> AddResult:
        """写入单个 conversation。

        输入:
            conversation: 框架清洗后的公开 conversation。

        输出:
            AddResult: 记录本次写入成功的 conversation id。
        """

        self.added.append(conversation.conversation_id)
        return AddResult(conversation_ids=[conversation.conversation_id])

    def retrieve(self, question: Question) -> AnswerPromptResult:
        """按问题返回 method 构造好的完整 answer prompt。

        输入:
            question: 框架传给 method 的公开问题。

        输出:
            AnswerPromptResult: `answer_prompt` 是后续 answer LLM 的完整输入。
        """

        return AnswerPromptResult(
            question_id=question.question_id,
            conversation_id=question.conversation_id,
            answer_prompt="Question: What does Alice like?\nMemory: Alice likes tea.",
            metadata={"strategy": "tiny"},
        )


def test_base_memory_provider_adds_one_conversation_and_builds_answer_prompt() -> None:
    """新主接口应只接收单个 conversation，并返回完整 answer_prompt。"""

    provider = TinyProvider()
    conversation = Conversation(
        conversation_id="conv-1",
        sessions=[
            Session(
                session_id="s1",
                turns=[Turn(turn_id="t1", speaker="Alice", content="I like tea.")],
            )
        ],
    )
    question = Question(
        question_id="q1",
        conversation_id="conv-1",
        text="What does Alice like?",
    )

    add_result = provider.add(conversation)
    retrieval = provider.retrieve(question)

    assert add_result.conversation_ids == ["conv-1"]
    assert provider.added == ["conv-1"]
    assert retrieval.question_id == "q1"
    assert retrieval.conversation_id == "conv-1"
    assert retrieval.answer_prompt == "Question: What does Alice like?\nMemory: Alice likes tea."
    assert retrieval.metadata == {"strategy": "tiny"}


def test_memory_retrieval_capability_is_public_contract() -> None:
    """capability 层应包含 memory_retrieval，供 registry 做兼容性判断。"""

    assert MethodCapability.MEMORY_RETRIEVAL.value == "memory_retrieval"
