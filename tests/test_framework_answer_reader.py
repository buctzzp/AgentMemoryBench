"""测试 framework-owned answer reader。

Reader 只负责把 method 构造好的完整 answer prompt 交给可替换 LLM client。
这里使用 fake client，确保测试不会触发真实 API。
"""

from __future__ import annotations

import pytest

from memory_benchmark.config import AnswerLLMSettings, OpenAISettings
from memory_benchmark.core import AnswerPromptResult, PromptMessage, Question
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.readers.answer import (
    AnswerPromptTemplate,
    FakeAnswerLLMClient,
    FrameworkAnswerReader,
)


def _question() -> Question:
    """构造一个包含时间和类别的公开问题。

    输入:
        无。

    输出:
        Question: reader 可见的问题对象，不包含 gold answer 或 evidence。
    """

    return Question(
        question_id="q1",
        conversation_id="conv-1",
        text="What does Alice like?",
        question_time="2024-01-01",
        category="single_hop",
    )


def _retrieval() -> AnswerPromptResult:
    """构造一个 method 生成的完整 role message prompt。

    输入:
        无。

    输出:
        AnswerPromptResult: `prompt_messages` 可直接交给 answer LLM。
    """

    return AnswerPromptResult(
        question_id="q1",
        conversation_id="conv-1",
        prompt_messages=[
            PromptMessage(
                role="system",
                content="Use the following memory to answer.",
            ),
            PromptMessage(
                role="user",
                content=(
                    "Question Time: 2024-01-01\n"
                    "Memory: Alice said she likes tea.\n"
                    "Question: What does Alice like?"
                ),
            ),
        ],
        metadata={"answer_context": "Alice said she likes tea."},
    )


def test_reader_sends_method_owned_answer_prompt_to_llm() -> None:
    """reader 不再压平 role，而是发送 method 生成的完整 prompt_messages。"""

    client = FakeAnswerLLMClient(answer="Alice likes tea.")
    reader = FrameworkAnswerReader(client=client)

    result = reader.generate_answer(question=_question(), retrieval=_retrieval())

    assert result.answer == "Alice likes tea."
    assert result.question_id == "q1"
    assert result.conversation_id == "conv-1"
    assert result.metadata["answer_reader"] == "framework"
    assert result.metadata["answer_model"] == "fake-answer-llm"
    assert "What does Alice like?" in client.calls[0]["prompt"]
    assert "Alice said she likes tea." in client.calls[0]["prompt"]
    assert "2024-01-01" in client.calls[0]["prompt"]
    assert client.calls[0]["messages"] == [
        {"role": "system", "content": "Use the following memory to answer."},
        {
            "role": "user",
            "content": (
                "Question Time: 2024-01-01\n"
                "Memory: Alice said she likes tea.\n"
                "Question: What does Alice like?"
            ),
        },
    ]
    assert client.calls[0]["prompt"] == _retrieval().answer_prompt


def test_custom_prompt_requires_question_and_memory_context_placeholders() -> None:
    """自定义 prompt 少任一核心占位符都应 fail closed。"""

    with pytest.raises(ConfigurationError, match="memory_context"):
        AnswerPromptTemplate(
            template="Question: {question}\nAnswer:",
            profile_name="broken",
        )

    with pytest.raises(ConfigurationError, match="question"):
        AnswerPromptTemplate(
            template="Memory: {memory_context}\nAnswer:",
            profile_name="broken",
        )


def test_reader_rejects_empty_prompt_messages() -> None:
    """Phase 1 默认不允许空 prompt_messages 静默回答。"""

    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="anything"))
    retrieval = AnswerPromptResult(
        question_id="q1",
        conversation_id="conv-1",
        prompt_messages=[],
    )

    with pytest.raises(ConfigurationError, match="prompt_messages"):
        reader.generate_answer(question=_question(), retrieval=retrieval)


def test_reader_rejects_mismatched_retrieval_question_id() -> None:
    """retrieval question_id 必须和当前 question 对齐。"""

    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="anything"))
    retrieval = AnswerPromptResult(
        question_id="other-question",
        conversation_id="conv-1",
        answer_prompt="Alice said she likes tea.",
    )

    with pytest.raises(ConfigurationError, match="question_id mismatch"):
        reader.generate_answer(question=_question(), retrieval=retrieval)


def test_reader_rejects_mismatched_retrieval_conversation_id() -> None:
    """retrieval conversation_id 必须和当前 question 对齐。"""

    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="anything"))
    retrieval = AnswerPromptResult(
        question_id="q1",
        conversation_id="other-conversation",
        answer_prompt="Alice said she likes tea.",
    )

    with pytest.raises(ConfigurationError, match="conversation_id mismatch"):
        reader.generate_answer(question=_question(), retrieval=retrieval)


def test_reader_rejects_empty_llm_answer() -> None:
    """answer LLM 返回空白文本时应 fail closed。"""

    reader = FrameworkAnswerReader(client=FakeAnswerLLMClient(answer="   "))

    with pytest.raises(ConfigurationError, match="empty answer"):
        reader.generate_answer(question=_question(), retrieval=_retrieval())


def test_answer_prompt_result_keeps_answer_prompt_text_view() -> None:
    """prompt_messages 是主协议，answer_prompt 是兼容 artifact 的文本视图。"""

    retrieval = _retrieval()

    assert retrieval.answer_prompt == (
        "[system]\nUse the following memory to answer.\n\n"
        "[user]\n"
        "Question Time: 2024-01-01\n"
        "Memory: Alice said she likes tea.\n"
        "Question: What does Alice like?"
    )


def test_reader_public_package_exports_core_classes() -> None:
    """readers 包入口应导出 framework reader 的核心类型。"""

    from memory_benchmark.readers import (  # noqa: PLC0415
        AnswerPromptTemplate as ExportedAnswerPromptTemplate,
        FakeAnswerLLMClient as ExportedFakeAnswerLLMClient,
        FrameworkAnswerReader as ExportedFrameworkAnswerReader,
    )

    assert ExportedAnswerPromptTemplate is AnswerPromptTemplate
    assert ExportedFakeAnswerLLMClient is FakeAnswerLLMClient
    assert ExportedFrameworkAnswerReader is FrameworkAnswerReader


def test_openai_compatible_answer_client_uses_configured_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI-compatible reader client 应读取 settings，但测试不触网。"""

    from memory_benchmark.readers.answer import (  # noqa: PLC0415
        OpenAICompatibleAnswerLLMClient,
    )

    captured: dict[str, object] = {}

    class FakeCompletions:
        """模拟 OpenAI chat.completions.create() 返回结构。"""

        def create(self, **kwargs: object) -> object:
            """记录请求参数并返回最小 completion 响应。"""

            captured.update(kwargs)
            message = type("Message", (), {"content": "answer"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice], "usage": None})()

    class FakeOpenAI:
        """模拟 OpenAI client，确保测试不会访问网络。"""

        def __init__(self, **kwargs: object) -> None:
            """记录 client 初始化参数。"""

            captured["client_kwargs"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("memory_benchmark.readers.answer.OpenAI", FakeOpenAI)

    client = OpenAICompatibleAnswerLLMClient(
        settings=OpenAISettings(
            api_key="sk-test",
            base_url="https://example.test/v1",
            model="gpt-4o-mini",
            timeout_seconds=60,
            max_retries=8,
        )
    )

    assert client.complete(prompt="hello") == "answer"
    assert captured["client_kwargs"] == {
        "api_key": "sk-test",
        "timeout": 60,
        "max_retries": 8,
        "base_url": "https://example.test/v1",
    }
    assert captured["model"] == "gpt-4o-mini"
    assert captured["messages"] == [{"role": "user", "content": "hello"}]


def test_openai_compatible_answer_client_passes_explicit_answer_llm_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """answer LLM 参数应显式传给 SDK，未配置字段不能冒充官方参数。"""

    from memory_benchmark.readers.answer import (  # noqa: PLC0415
        OpenAICompatibleAnswerLLMClient,
    )

    captured: dict[str, object] = {}

    class FakeCompletions:
        """模拟 OpenAI chat completions，记录 create() 参数。"""

        def create(self, **kwargs: object) -> object:
            """返回最小 response，同时暴露请求参数供断言。"""

            captured.update(kwargs)
            message = type("Message", (), {"content": "answer"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice], "usage": None})()

    class FakeOpenAI:
        """模拟 OpenAI client，避免真实网络调用。"""

        def __init__(self, **kwargs: object) -> None:
            """只保留 chat.completions.create 入口。"""

            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("memory_benchmark.readers.answer.OpenAI", FakeOpenAI)

    client = OpenAICompatibleAnswerLLMClient(
        settings=OpenAISettings(api_key="sk-test", model="gpt-4o-mini"),
        answer_settings=AnswerLLMSettings(
            model="gpt-4o-mini",
            message_role="system",
            temperature=0.0,
            max_tokens=None,
            top_p=0.8,
            timeout_seconds=60,
            max_retries=8,
        ),
    )

    assert client.complete(prompt="official prompt") == "answer"
    assert captured["model"] == "gpt-4o-mini"
    assert captured["messages"] == [
        {"role": "system", "content": "official prompt"}
    ]
    assert captured["temperature"] == 0.0
    assert captured["top_p"] == 0.8
    assert "max_tokens" not in captured


def test_openai_compatible_answer_client_sends_prompt_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenAI-compatible answer client 应直接发送 method 返回的 role messages。"""

    from memory_benchmark.readers.answer import (  # noqa: PLC0415
        OpenAICompatibleAnswerLLMClient,
    )

    captured: dict[str, object] = {}

    class FakeCompletions:
        """模拟 OpenAI chat completions，记录 create() 参数。"""

        def create(self, **kwargs: object) -> object:
            """返回最小 response。"""

            captured.update(kwargs)
            message = type("Message", (), {"content": "answer"})()
            choice = type("Choice", (), {"message": message})()
            return type("Response", (), {"choices": [choice], "usage": None})()

    class FakeOpenAI:
        """模拟 OpenAI client。"""

        def __init__(self, **kwargs: object) -> None:
            """只暴露 chat.completions。"""

            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("memory_benchmark.readers.answer.OpenAI", FakeOpenAI)

    client = OpenAICompatibleAnswerLLMClient(
        settings=OpenAISettings(api_key="sk-test", model="gpt-4o-mini"),
        answer_settings=AnswerLLMSettings(model="gpt-4o-mini", temperature=0.7),
    )
    response = client.complete_messages_with_metadata(
        messages=[
            PromptMessage("system", "official system"),
            PromptMessage("user", "official user"),
        ]
    )

    assert response.text == "answer"
    assert captured["messages"] == [
        {"role": "system", "content": "official system"},
        {"role": "user", "content": "official user"},
    ]
    assert captured["temperature"] == 0.7


def test_answer_llm_settings_rejects_unsupported_message_role() -> None:
    """answer LLM message role 只允许 OpenAI chat completions 支持的公开角色。"""

    with pytest.raises(ConfigurationError, match="message_role"):
        AnswerLLMSettings(model="gpt-4o-mini", message_role="developer")
