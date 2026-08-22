"""OpenAI-compatible method transport 覆写测试。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.openai_transport import (
    merge_chat_completions_request_overrides,
    with_chat_completions_request_overrides,
)


pytestmark = pytest.mark.unit


class _FakeCompletions:
    """记录最终发送参数的 Chat Completions fake。"""

    def __init__(self) -> None:
        """初始化调用账。"""

        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        """记录参数并返回稳定 sentinel。"""

        self.calls.append(dict(kwargs))
        return "response"


def test_client_wrapper_injects_reasoning_effort_without_mutating_caller() -> None:
    """ox runtime 的 low reasoning 应只在发送边界注入。"""

    endpoint = _FakeCompletions()
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=endpoint),
        embeddings="preserved",
    )
    wrapped = with_chat_completions_request_overrides(
        client,
        {"reasoning_effort": "low"},
    )
    request = {"model": "ox-alpha-free", "messages": []}

    assert wrapped.chat.completions.create(**request) == "response"
    assert request == {"model": "ox-alpha-free", "messages": []}
    assert endpoint.calls == [
        {
            "model": "ox-alpha-free",
            "messages": [],
            "reasoning_effort": "low",
        }
    ]
    assert wrapped.embeddings == "preserved"


def test_extra_body_merge_preserves_product_fields_and_rejects_conflicts() -> None:
    """旧 runtime thinking 参数可与产品 extra_body 共存，但冲突必须 fail-fast。"""

    assert merge_chat_completions_request_overrides(
        {"extra_body": {"trace": True}},
        {"extra_body": {"thinking": {"type": "disabled"}}},
    ) == {
        "extra_body": {
            "trace": True,
            "thinking": {"type": "disabled"},
        }
    }
    with pytest.raises(ConfigurationError, match="reasoning_effort"):
        merge_chat_completions_request_overrides(
            {"reasoning_effort": "high"},
            {"reasoning_effort": "low"},
        )


def test_json_schema_downgrade_is_narrow_and_does_not_mutate_caller() -> None:
    """兼容层只把显式 json_schema 降为 json_object。"""

    request = {
        "model": "ox-alpha-free",
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "answer", "schema": {"type": "object"}},
        },
    }

    merged = merge_chat_completions_request_overrides(
        request,
        {"reasoning_effort": "low"},
        json_schema_as_json_object=True,
    )

    assert request["response_format"]["type"] == "json_schema"
    assert merged == {
        "model": "ox-alpha-free",
        "response_format": {"type": "json_object"},
        "reasoning_effort": "low",
    }
    assert merge_chat_completions_request_overrides(
        {"response_format": {"type": "json_object"}},
        None,
        json_schema_as_json_object=True,
    ) == {"response_format": {"type": "json_object"}}
    with pytest.raises(ConfigurationError, match="response_format"):
        merge_chat_completions_request_overrides(
            {"response_format": "json"},
            None,
            json_schema_as_json_object=True,
        )


def test_response_observer_sees_final_sync_request_and_response() -> None:
    """同步 observer 应看到合并后的参数与原 response，且不改变返回值。"""

    endpoint = _FakeCompletions()
    client = SimpleNamespace(chat=SimpleNamespace(completions=endpoint))
    observed: list[tuple[object, dict[str, object]]] = []
    wrapped = with_chat_completions_request_overrides(
        client,
        {"reasoning_effort": "low"},
        response_observer=lambda response, request: observed.append(
            (response, dict(request))
        ),
    )

    assert wrapped.chat.completions.create(model="ox-alpha-free") == "response"
    assert observed == [
        ("response", {"model": "ox-alpha-free", "reasoning_effort": "low"})
    ]


def test_response_observer_waits_for_async_response() -> None:
    """异步 client 的 observer 必须在 await 后执行。"""

    class _AsyncCompletions:
        """返回 coroutine 的最小 async endpoint。"""

        async def create(self, **_kwargs: object) -> object:
            """返回稳定异步 sentinel。"""

            return "async-response"

    observed: list[object] = []
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=_AsyncCompletions())
    )
    wrapped = with_chat_completions_request_overrides(
        client,
        None,
        response_observer=lambda response, _request: observed.append(response),
    )

    result = asyncio.run(wrapped.chat.completions.create(model="m"))

    assert result == "async-response"
    assert observed == ["async-response"]


def test_stream_observer_waits_for_full_consumption_and_injects_usage() -> None:
    """stream observer 只能在完整消费后收到全部 chunk 与 usage 请求。"""

    chunks = [SimpleNamespace(value="a"), SimpleNamespace(value="b")]

    class _StreamingCompletions:
        """返回同步 iterator 并记录最终请求。"""

        def __init__(self) -> None:
            """初始化请求账。"""

            self.calls: list[dict[str, object]] = []

        def create(self, **kwargs: object):
            """返回稳定 chunk iterator。"""

            self.calls.append(dict(kwargs))
            return iter(chunks)

    endpoint = _StreamingCompletions()
    observed: list[object] = []
    client = SimpleNamespace(chat=SimpleNamespace(completions=endpoint))
    wrapped = with_chat_completions_request_overrides(
        client,
        None,
        include_stream_usage=True,
        response_observer=lambda response, _request: observed.append(response),
    )

    stream = wrapped.chat.completions.create(
        model="ox-alpha-free",
        stream=True,
    )
    assert observed == []
    assert list(stream) == chunks
    assert observed == [tuple(chunks)]
    assert endpoint.calls == [
        {
            "model": "ox-alpha-free",
            "stream": True,
            "stream_options": {"include_usage": True},
        }
    ]


def test_stream_usage_override_rejects_false_conflict() -> None:
    """产品显式禁止 usage 时不得被观测层静默覆盖。"""

    with pytest.raises(ConfigurationError, match="include_usage"):
        merge_chat_completions_request_overrides(
            {
                "stream": True,
                "stream_options": {"include_usage": False},
            },
            None,
            include_stream_usage=True,
        )
