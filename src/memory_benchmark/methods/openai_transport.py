"""OpenAI-compatible Chat Completions 请求覆写的最小适配层。

不同 method 的产品实现各自持有 OpenAI SDK client。这里仅在真正发送请求前合并
provider/model 专属的公开传输参数，不改 prompt、算法顺序、返回对象或重试语义。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from inspect import isawaitable
from typing import Any

from memory_benchmark.core import ConfigurationError


def with_chat_completions_request_overrides(
    client: Any,
    overrides: Mapping[str, object] | None,
    *,
    json_schema_as_json_object: bool = False,
    include_stream_usage: bool = False,
    response_observer: Callable[[Any, Mapping[str, Any]], None] | None = None,
) -> Any:
    """返回只覆写 ``chat.completions.create`` 请求参数的透明 client。

    空覆写时原样返回 client。调用方已经显式给出相同值时允许通过；同名但值不同
    时 fail-fast，避免 profile 身份与产品调用悄悄分叉。
    """

    normalized = dict(overrides or {})
    if (
        not normalized
        and not json_schema_as_json_object
        and not include_stream_usage
        and response_observer is None
    ):
        return client
    return _OpenAIClientWithRequestOverrides(
        client,
        normalized,
        json_schema_as_json_object=json_schema_as_json_object,
        include_stream_usage=include_stream_usage,
        response_observer=response_observer,
    )


def merge_chat_completions_request_overrides(
    kwargs: Mapping[str, Any],
    overrides: Mapping[str, object] | None,
    *,
    json_schema_as_json_object: bool = False,
    include_stream_usage: bool = False,
) -> dict[str, Any]:
    """无损合并一次 Chat Completions 调用与 profile 覆写。"""

    merged = dict(kwargs)
    if json_schema_as_json_object:
        merged = _downgrade_json_schema_response_format(merged)
    if include_stream_usage and merged.get("stream") is True:
        merged["stream_options"] = _merge_stream_options(
            merged.get("stream_options")
        )
    for key, expected in dict(overrides or {}).items():
        if key == "extra_body":
            merged[key] = _merge_extra_body(merged.get(key), expected)
            continue
        if key in merged and merged[key] != expected:
            raise ConfigurationError(
                "Chat Completions request conflicts with runtime override: "
                f"{key}"
            )
        merged[key] = expected
    return merged


def _merge_stream_options(current: object) -> dict[str, Any]:
    """为 streaming 请求启用官方 usage 尾块，冲突时 fail-fast。"""

    if current is None:
        return {"include_usage": True}
    if not isinstance(current, Mapping):
        raise ConfigurationError(
            "Chat Completions stream_options must be a mapping"
        )
    merged = dict(current)
    if "include_usage" in merged and merged["include_usage"] is not True:
        raise ConfigurationError(
            "Chat Completions stream_options.include_usage conflicts with "
            "runtime observation"
        )
    merged["include_usage"] = True
    return merged


def _downgrade_json_schema_response_format(
    kwargs: Mapping[str, Any],
) -> dict[str, Any]:
    """把不受当前 endpoint 约束的 JSON schema 降为 JSON object 模式。

    只替换显式 ``type=json_schema``；没有 response_format 或调用方已经使用其他
    模式时保持原样。该兼容层不改 prompt，目标是避免 provider 接受 schema 却忽略
    schema 字段约束。
    """

    merged = dict(kwargs)
    response_format = merged.get("response_format")
    if response_format is None:
        return merged
    if not isinstance(response_format, Mapping):
        raise ConfigurationError(
            "Chat Completions response_format must be a mapping"
        )
    if response_format.get("type") == "json_schema":
        merged["response_format"] = {"type": "json_object"}
    return merged


def _merge_extra_body(current: object, expected: object) -> dict[str, Any]:
    """合并 OpenAI-compatible ``extra_body``，冲突时拒绝静默覆盖。"""

    if not isinstance(expected, Mapping):
        raise ConfigurationError("Runtime extra_body override must be a mapping")
    if current is None:
        return dict(expected)
    if not isinstance(current, Mapping):
        raise ConfigurationError("Chat Completions extra_body must be a mapping")
    merged = dict(current)
    for key, value in expected.items():
        if key in merged and merged[key] != value:
            raise ConfigurationError(
                "Chat Completions extra_body conflicts with runtime override: "
                f"{key}"
            )
        merged[key] = value
    return merged


class _OpenAIClientWithRequestOverrides:
    """透明转发 OpenAI client，仅替换 chat namespace。"""

    def __init__(
        self,
        client: Any,
        overrides: dict[str, object],
        *,
        json_schema_as_json_object: bool,
        include_stream_usage: bool,
        response_observer: Callable[[Any, Mapping[str, Any]], None] | None,
    ) -> None:
        """保存原 client 与不可变副本覆写。"""

        self._client = client
        self.chat = _ChatWithRequestOverrides(
            client.chat,
            overrides,
            json_schema_as_json_object=json_schema_as_json_object,
            include_stream_usage=include_stream_usage,
            response_observer=response_observer,
        )

    def __getattr__(self, name: str) -> Any:
        """转发所有未包装属性。"""

        return getattr(self._client, name)


class _ChatWithRequestOverrides:
    """透明转发 chat namespace，仅替换 completions namespace。"""

    def __init__(
        self,
        chat: Any,
        overrides: dict[str, object],
        *,
        json_schema_as_json_object: bool,
        include_stream_usage: bool,
        response_observer: Callable[[Any, Mapping[str, Any]], None] | None,
    ) -> None:
        """保存原 namespace 与覆写。"""

        self._chat = chat
        self.completions = _CompletionsWithRequestOverrides(
            chat.completions,
            overrides,
            json_schema_as_json_object=json_schema_as_json_object,
            include_stream_usage=include_stream_usage,
            response_observer=response_observer,
        )

    def __getattr__(self, name: str) -> Any:
        """转发所有未包装属性。"""

        return getattr(self._chat, name)


class _CompletionsWithRequestOverrides:
    """在 create 边界合并请求参数，兼容同步与异步 OpenAI client。"""

    def __init__(
        self,
        completions: Any,
        overrides: dict[str, object],
        *,
        json_schema_as_json_object: bool,
        include_stream_usage: bool,
        response_observer: Callable[[Any, Mapping[str, Any]], None] | None,
    ) -> None:
        """保存原 endpoint 与覆写。"""

        self._completions = completions
        self._overrides = dict(overrides)
        self._json_schema_as_json_object = json_schema_as_json_object
        self._include_stream_usage = include_stream_usage
        self._response_observer = response_observer

    def create(self, *args: Any, **kwargs: Any) -> Any:
        """合并覆写后调用原 endpoint；返回值或 coroutine 原样转发。"""

        request_kwargs = merge_chat_completions_request_overrides(
            kwargs,
            self._overrides,
            json_schema_as_json_object=self._json_schema_as_json_object,
            include_stream_usage=self._include_stream_usage,
        )
        response = self._completions.create(
            *args,
            **request_kwargs,
        )
        if self._response_observer is None:
            return response
        if isawaitable(response):
            return self._observe_async(response, request_kwargs)
        return self._observe_resolved(response, request_kwargs)

    async def _observe_async(
        self,
        response: Any,
        request_kwargs: Mapping[str, Any],
    ) -> Any:
        """等待异步 response 后执行同一只读 observation。"""

        resolved = await response
        return self._observe_resolved(resolved, request_kwargs)

    def _observe_resolved(
        self,
        response: Any,
        request_kwargs: Mapping[str, Any],
    ) -> Any:
        """非流式立即观测；流式等待调用方消费完全部 chunk。"""

        assert self._response_observer is not None
        if request_kwargs.get("stream") is True:
            if hasattr(response, "__aiter__"):
                return _ObservedAsyncStream(
                    response,
                    self._response_observer,
                    request_kwargs,
                )
            if hasattr(response, "__iter__"):
                return _ObservedSyncStream(
                    response,
                    self._response_observer,
                    request_kwargs,
                )
        self._response_observer(response, dict(request_kwargs))
        return response

    def __getattr__(self, name: str) -> Any:
        """转发所有未包装属性。"""

        return getattr(self._completions, name)


class _ObservedSyncStream:
    """透明代理同步 stream，并在完整消费后把 chunk 序列交给 observer。"""

    def __init__(
        self,
        stream: Any,
        observer: Callable[[Any, Mapping[str, Any]], None],
        request_kwargs: Mapping[str, Any],
    ) -> None:
        """保存原 stream、observer 与最终请求。"""

        self._stream = stream
        self._iterator = iter(stream)
        self._observer = observer
        self._request_kwargs = dict(request_kwargs)
        self._chunks: list[Any] = []
        self._observed = False

    def __iter__(self) -> "_ObservedSyncStream":
        """返回透明 iterator。"""

        return self

    def __next__(self) -> Any:
        """逐块转发，并在自然结束时提交一次 observation。"""

        try:
            chunk = next(self._iterator)
        except StopIteration:
            self._observe_once()
            raise
        self._chunks.append(chunk)
        return chunk

    def _observe_once(self) -> None:
        """只在完整 stream 生命周期提交一次。"""

        if self._observed:
            return
        self._observed = True
        self._observer(tuple(self._chunks), dict(self._request_kwargs))

    def __getattr__(self, name: str) -> Any:
        """转发 stream 的其他属性。"""

        return getattr(self._stream, name)


class _ObservedAsyncStream:
    """透明代理异步 stream，并在完整消费后提交 chunk 序列。"""

    def __init__(
        self,
        stream: Any,
        observer: Callable[[Any, Mapping[str, Any]], None],
        request_kwargs: Mapping[str, Any],
    ) -> None:
        """保存原 async stream、observer 与最终请求。"""

        self._stream = stream
        self._iterator = stream.__aiter__()
        self._observer = observer
        self._request_kwargs = dict(request_kwargs)
        self._chunks: list[Any] = []
        self._observed = False

    def __aiter__(self) -> "_ObservedAsyncStream":
        """返回透明 async iterator。"""

        return self

    async def __anext__(self) -> Any:
        """逐块转发，并在自然结束时提交一次 observation。"""

        try:
            chunk = await self._iterator.__anext__()
        except StopAsyncIteration:
            self._observe_once()
            raise
        self._chunks.append(chunk)
        return chunk

    def _observe_once(self) -> None:
        """只在完整 async stream 生命周期提交一次。"""

        if self._observed:
            return
        self._observed = True
        self._observer(tuple(self._chunks), dict(self._request_kwargs))

    def __getattr__(self, name: str) -> Any:
        """转发 async stream 的其他属性。"""

        return getattr(self._stream, name)
