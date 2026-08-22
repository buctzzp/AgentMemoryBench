"""EverOS v1.2.3 独立 Python 3.12 JSON-lines worker。

worker 进入官方 ``create_app`` lifespan，随后调用与 HTTP route 相同的 typed
memorize/search/get service。它不理解 benchmark/gold/answer，只负责产品输入、
精确后台完成门、public readout 与 API usage 观测。
"""

from __future__ import annotations

import asyncio
from importlib import import_module
import json
import math
import os
from pathlib import Path
import sys
from time import monotonic, perf_counter_ns
import traceback
from typing import Any


EVEROS_ADAPTER_VERSION = "everos-product-chat-v6"
EVEROS_WORKER_SCHEMA_VERSION = "everos-worker-protocol-v2"
EVEROS_PRODUCT_SURFACE = "create_app-lifespan+typed-memorize-search-get"
EVEROS_ROOT_MARKER = ".memory-benchmark-everos-root.json"
_TERMINAL_FAILURES = frozenset({"dead_letter", "crashed"})
_CASCADE_SETTLE_POLL_SECONDS = 0.05
_OPENCODEGO_REASONING_EFFORT_LOW_MODELS = frozenset({"ox-alpha-free"})


def _required_text(value: Any, label: str) -> str:
    """读取非空字符串，拒绝宽松转换。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


def _required_int(value: Any, label: str, *, minimum: int = 0) -> int:
    """读取有下界的整数；bool 不得冒充整数。"""

    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _required_float(value: Any, label: str, *, positive: bool = False) -> float:
    """读取有限数值，可要求严格为正。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    resolved = float(value)
    if not math.isfinite(resolved) or (positive and resolved <= 0):
        qualifier = "positive and finite" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}")
    return resolved


def _required_text_list(value: Any, label: str) -> list[str]:
    """读取非空、无重复文本列表。"""

    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a non-empty text list")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return list(value)


def _validate_llm_observation(value: Any) -> dict[str, int]:
    """校验一次 LLM API usage。"""

    if not isinstance(value, dict) or set(value) != {
        "input_tokens",
        "output_tokens",
    }:
        raise ValueError("LLM observation has invalid shape")
    return {
        "input_tokens": _required_int(value.get("input_tokens"), "input_tokens"),
        "output_tokens": _required_int(
            value.get("output_tokens"), "output_tokens"
        ),
    }


def _validate_embedding_observation(value: Any) -> dict[str, Any]:
    """校验一次 embedding API usage 与本地 wall timer。"""

    if not isinstance(value, dict) or set(value) != {
        "input_tokens",
        "latency_ms",
        "text_count",
    }:
        raise ValueError("embedding observation has invalid shape")
    latency = _required_float(value.get("latency_ms"), "latency_ms")
    if latency < 0:
        raise ValueError("latency_ms must be non-negative")
    return {
        "input_tokens": _required_int(value.get("input_tokens"), "input_tokens"),
        "latency_ms": latency,
        "text_count": _required_int(
            value.get("text_count"), "text_count", minimum=1
        ),
    }


def _validate_rerank_observation(value: Any) -> dict[str, Any]:
    """校验一次非空 rerank 调用的逻辑调用量与本地 wall timer。"""

    if not isinstance(value, dict) or set(value) != {
        "document_count",
        "latency_ms",
    }:
        raise ValueError("rerank observation has invalid shape")
    latency = _required_float(value.get("latency_ms"), "latency_ms")
    if latency < 0:
        raise ValueError("latency_ms must be non-negative")
    return {
        "document_count": _required_int(
            value.get("document_count"), "document_count", minimum=1
        ),
        "latency_ms": latency,
    }


class _ObservedLLMClient:
    """透传 product LLM client 并读取每次真实 ChatResponse.usage。"""

    def __init__(self, inner: Any, engine: "_WorkerEngine") -> None:
        """保存原 product client 与当前 operation 观测账。"""

        self._inner = inner
        self._engine = engine

    async def chat(self, *args: Any, **kwargs: Any) -> Any:
        """注入模型专属公开参数，成功 response 在手时记录 exact usage。"""

        copied = dict(kwargs)
        model = copied.get("model") or os.environ.get("EVEROS_LLM__MODEL")
        if model in _OPENCODEGO_REASONING_EFFORT_LOW_MODELS:
            existing = copied.get("reasoning_effort")
            if existing not in {None, "low"}:
                raise ValueError(
                    "EverOS caller supplied conflicting reasoning_effort"
                )
            copied["reasoning_effort"] = "low"
        response = await self._inner.chat(*args, **copied)
        usage = getattr(response, "usage", None)
        if usage is None:
            raise RuntimeError("EverOS LLM response has no exact usage")
        self._engine.record_llm(
            {
                "input_tokens": _required_int(
                    getattr(usage, "prompt_tokens", None), "prompt_tokens"
                ),
                "output_tokens": _required_int(
                    getattr(usage, "completion_tokens", None),
                    "completion_tokens",
                ),
            }
        )
        return response

    def __getattr__(self, name: str) -> Any:
        """透传 product LLM client 的非观测属性。"""

        return getattr(self._inner, name)


class _ObservedEmbeddingsEndpoint:
    """透传 AsyncOpenAI embeddings endpoint 并捕获 response usage。"""

    def __init__(self, inner: Any, engine: "_WorkerEngine") -> None:
        """保存原 embeddings endpoint 与当前 operation 观测账。"""

        self._inner = inner
        self._engine = engine

    async def create(self, *args: Any, **kwargs: Any) -> Any:
        """保持 request/response 不变，只记录 API usage 与调用延迟。"""

        raw_input = kwargs.get("input")
        text_count = len(raw_input) if isinstance(raw_input, list) else 1
        started_ns = perf_counter_ns()
        response = await self._inner.create(*args, **kwargs)
        latency_ms = max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)
        usage = getattr(response, "usage", None)
        if usage is None:
            raise RuntimeError("EverOS embedding response has no exact usage")
        self._engine.record_embedding(
            {
                "input_tokens": _required_int(
                    getattr(usage, "prompt_tokens", None), "prompt_tokens"
                ),
                "latency_ms": latency_ms,
                "text_count": text_count,
            }
        )
        return response

    def __getattr__(self, name: str) -> Any:
        """透传 endpoint 其余属性。"""

        return getattr(self._inner, name)


class _ObservedRerankProvider:
    """透传 product reranker，并为主 chat/Episode 轨证明零外部调用。"""

    def __init__(self, inner: Any, engine: "_WorkerEngine") -> None:
        """保存原 provider 与当前 operation 观测账。"""

        self._inner = inner
        self._engine = engine

    async def rerank(self, *args: Any, **kwargs: Any) -> Any:
        """逐字透传非空 rerank；成功返回后记录逻辑调用与延迟。"""

        documents = args[1] if len(args) >= 2 else kwargs.get("documents")
        try:
            document_count = len(documents)
        except TypeError:
            document_count = 0
        started_ns = perf_counter_ns()
        response = await self._inner.rerank(*args, **kwargs)
        if document_count:
            self._engine.record_rerank(
                {
                    "document_count": document_count,
                    "latency_ms": max(
                        0.0, (perf_counter_ns() - started_ns) / 1_000_000
                    ),
                }
            )
        return response

    def __getattr__(self, name: str) -> Any:
        """透传 provider 其余属性。"""

        return getattr(self._inner, name)


class _WorkerEngine:
    """持有一个物理 EverOS root 的 official lifespan 与命令状态。"""

    def __init__(self) -> None:
        """初始化尚未进入 lifespan 的串行 worker 状态。"""

        self.app: Any = None
        self.lifespan: Any = None
        self.config: dict[str, Any] | None = None
        self._closed = False
        self._llm_observations: list[dict[str, int]] | None = None
        self._embedding_observations: list[dict[str, Any]] | None = None
        self._rerank_observations: list[dict[str, Any]] | None = None

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """校验协议 envelope 并分发单条命令。"""

        if set(request) != {"request_id", "command", "payload"}:
            raise ValueError("request must contain exactly request_id/command/payload")
        _required_int(request.get("request_id"), "request_id", minimum=1)
        command = _required_text(request.get("command"), "command")
        payload = request.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if command == "initialize":
            return await self.initialize(payload)
        self._require_ready()
        if command == "ingest_session":
            return await self.ingest_session(payload)
        if command == "retrieve":
            return await self.retrieve(payload)
        if command == "get_session_memories":
            return await self.get_session_memories(payload)
        if command == "shutdown":
            return await self.shutdown()
        raise ValueError(f"unsupported EverOS worker command: {command}")

    async def initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """进入 official lifespan，并在 capability 单例处安装纯观测 wrapper。"""

        if self.app is not None or self._closed:
            raise RuntimeError("EverOS worker can only initialize once")
        expected = {
            "adapter_version",
            "add_batch_size",
            "app_id",
            "drain_timeout_seconds",
            "project_id",
            "root_marker",
            "search_method",
        }
        if set(payload) != expected:
            raise ValueError("initialize payload shape mismatch")
        if payload.get("adapter_version") != EVEROS_ADAPTER_VERSION:
            raise ValueError("EverOS adapter version mismatch")
        root = Path(_required_text(os.environ.get("EVEROS_ROOT"), "EVEROS_ROOT"))
        marker = payload.get("root_marker")
        if not isinstance(marker, dict):
            raise ValueError("root_marker must be an object")
        marker_path = root / EVEROS_ROOT_MARKER
        if json.loads(marker_path.read_text(encoding="utf-8")) != marker:
            raise RuntimeError("EverOS root marker identity mismatch")
        self.config = {
            "add_batch_size": _required_int(
                payload.get("add_batch_size"), "add_batch_size", minimum=1
            ),
            "app_id": _required_text(payload.get("app_id"), "app_id"),
            "drain_timeout_seconds": _required_float(
                payload.get("drain_timeout_seconds"),
                "drain_timeout_seconds",
                positive=True,
            ),
            "project_id": _required_text(payload.get("project_id"), "project_id"),
            "search_method": _required_text(
                payload.get("search_method"), "search_method"
            ),
        }
        if self.config["add_batch_size"] != 25:
            raise ValueError("EverOS product profile requires add_batch_size=25")
        if self.config["search_method"] != "hybrid":
            raise ValueError("EverOS product profile requires hybrid search")

        from everos.entrypoints.api.app import create_app

        self.app = create_app()
        self.lifespan = self.app.router.lifespan_context(self.app)
        try:
            await self.lifespan.__aenter__()
        except BaseException:
            self.app = None
            self.lifespan = None
            raise
        try:
            self._install_observers()
        except BaseException as observer_error:
            error_info = sys.exc_info()
            shutdown_error: BaseException | None = None
            try:
                await self.lifespan.__aexit__(*error_info)
            except BaseException as exc:
                shutdown_error = exc
            self.app = None
            self.lifespan = None
            if shutdown_error is not None:
                raise ExceptionGroup(
                    "EverOS observer install and lifespan cleanup both failed",
                    [observer_error, shutdown_error],
                )
            raise
        return {
            "adapter_version": EVEROS_ADAPTER_VERSION,
            "product_surface": EVEROS_PRODUCT_SURFACE,
            "status": "ready",
            "worker_schema_version": EVEROS_WORKER_SCHEMA_VERSION,
        }

    def _install_observers(self) -> None:
        """包装 product 单例，不修改任何算法返回值或调用参数。"""

        import everos.component.embedding.accessor as embedding_accessor
        import everos.component.llm.client as llm_accessor
        import everos.component.rerank.accessor as rerank_accessor

        search_service = import_module("everos.service.search")

        if search_service._manager is not None:
            raise RuntimeError(
                "EverOS search manager initialized before rerank observer install"
            )
        llm_client = llm_accessor._llm_client
        if llm_client is None:
            raise RuntimeError("EverOS LLM lifespan did not initialize its client")
        capability = embedding_accessor.get_embedding_capability()
        provider = capability.provider
        if provider is None:
            raise RuntimeError("EverOS HYBRID profile requires embedding capability")
        client = getattr(provider, "_client", None)
        endpoint = getattr(client, "embeddings", None)
        if endpoint is None:
            raise RuntimeError("EverOS embedding provider has no observable endpoint")
        rerank_capability = rerank_accessor.get_rerank_capability()
        rerank_provider = rerank_capability.provider

        llm_accessor._llm_client = _ObservedLLMClient(llm_client, self)
        client.embeddings = _ObservedEmbeddingsEndpoint(endpoint, self)
        if rerank_provider is not None:
            rerank_accessor._capability = rerank_capability.__class__(
                provider=_ObservedRerankProvider(rerank_provider, self)
            )

    def _require_ready(self) -> None:
        """拒绝初始化前或 shutdown 后的业务命令。"""

        if self.app is None or self.lifespan is None or self.config is None:
            raise RuntimeError("EverOS worker is not initialized")
        if self._closed:
            raise RuntimeError("EverOS worker is closed")

    def begin_observations(self) -> None:
        """建立一个覆盖同步 pipeline 与 exact-drained OME 的观测 buffer。"""

        if (
            self._llm_observations is not None
            or self._embedding_observations is not None
            or self._rerank_observations is not None
        ):
            raise RuntimeError("EverOS observation buffer is already active")
        self._llm_observations = []
        self._embedding_observations = []
        self._rerank_observations = []

    def finish_observations(
        self,
    ) -> tuple[
        list[dict[str, int]],
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        """冻结成功 operation 的观测并清空 buffer。"""

        if (
            self._llm_observations is None
            or self._embedding_observations is None
            or self._rerank_observations is None
        ):
            raise RuntimeError("EverOS observation buffer is not active")
        llm = list(self._llm_observations)
        embedding = list(self._embedding_observations)
        rerank = list(self._rerank_observations)
        self._llm_observations = None
        self._embedding_observations = None
        self._rerank_observations = None
        return llm, embedding, rerank

    def discard_observations(self) -> None:
        """失败 operation 不向父进程冒充成功 usage。"""

        self._llm_observations = None
        self._embedding_observations = None
        self._rerank_observations = None

    def record_llm(self, observation: dict[str, int]) -> None:
        """记录一次真实 LLM response usage。"""

        if self._llm_observations is None:
            raise RuntimeError("EverOS LLM call occurred outside an operation")
        self._llm_observations.append(_validate_llm_observation(observation))

    def record_embedding(self, observation: dict[str, Any]) -> None:
        """记录一次真实 embedding response usage。"""

        if self._embedding_observations is None:
            raise RuntimeError("EverOS embedding call occurred outside an operation")
        self._embedding_observations.append(
            _validate_embedding_observation(observation)
        )

    def record_rerank(self, observation: dict[str, Any]) -> None:
        """记录一次成功的非空 rerank 逻辑调用。"""

        if self._rerank_observations is None:
            raise RuntimeError("EverOS rerank call occurred outside an operation")
        self._rerank_observations.append(
            _validate_rerank_observation(observation)
        )

    async def ingest_session(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按官方 batch=25 add，随后 flush、exact drain 与 session public get。"""

        expected = {"messages", "operation_id", "owner_ids", "session_id"}
        if set(payload) != expected:
            raise ValueError("ingest_session payload shape mismatch")
        operation_id = _required_text(payload.get("operation_id"), "operation_id")
        session_id = _required_text(payload.get("session_id"), "session_id")
        owner_ids = _required_text_list(payload.get("owner_ids"), "owner_ids")
        messages = self._validate_messages(payload.get("messages"))
        self.begin_observations()
        try:
            from everos.entrypoints.api.routes.memorize import MemorizeAddRequest
            from everos.service import memorize

            for offset in range(0, len(messages), self.config["add_batch_size"]):
                request = MemorizeAddRequest(
                    session_id=session_id,
                    app_id=self.config["app_id"],
                    project_id=self.config["project_id"],
                    messages=messages[offset : offset + self.config["add_batch_size"]],
                )
                await memorize(request.model_dump(mode="python"))
            await memorize(
                {
                    "session_id": session_id,
                    "app_id": self.config["app_id"],
                    "project_id": self.config["project_id"],
                    "messages": [],
                },
                is_final=True,
            )
            drain = await self._exact_drain()
            session_items = await self._get_session_items(owner_ids, session_id)
            llm, embedding, rerank = self.finish_observations()
        except BaseException:
            self.discard_observations()
            raise
        return {
            "embedding_observations": embedding,
            "exact_drain": True,
            "exact_drain_details": drain,
            "llm_observations": llm,
            "operation_id": operation_id,
            "rerank_observations": rerank,
            "session_items": session_items,
        }

    @staticmethod
    def _validate_messages(value: Any) -> list[dict[str, Any]]:
        """强校 product message shape；结构锚只允许唯一空 user。"""

        if not isinstance(value, list) or not value:
            raise ValueError("messages must be a non-empty list")
        normalized: list[dict[str, Any]] = []
        empty_count = 0
        for index, message in enumerate(value):
            expected = {"content", "role", "sender_id", "sender_name", "timestamp"}
            if not isinstance(message, dict) or set(message) != expected:
                raise ValueError(f"messages[{index}] has invalid shape")
            role = _required_text(message.get("role"), f"messages[{index}].role")
            if role not in {"user", "assistant"}:
                raise ValueError(f"messages[{index}].role is unsupported")
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError(f"messages[{index}].content must be text")
            if not content:
                empty_count += 1
                if index != 0 or role != "user":
                    raise ValueError(
                        "only the first structural user anchor may have empty content"
                    )
            sender_name = message.get("sender_name")
            if sender_name is not None and not isinstance(sender_name, str):
                raise ValueError(f"messages[{index}].sender_name must be text or null")
            normalized.append(
                {
                    "content": content,
                    "role": role,
                    "sender_id": _required_text(
                        message.get("sender_id"), f"messages[{index}].sender_id"
                    ),
                    "sender_name": sender_name,
                    "timestamp": _required_int(
                        message.get("timestamp"),
                        f"messages[{index}].timestamp",
                        minimum=1,
                    ),
                }
            )
        if empty_count > 1:
            raise ValueError("messages contain multiple structural anchors")
        return normalized

    async def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        """逐 owner 调 public search，再按 score/owner/rank 稳定全局合并。"""

        if set(payload) != {"owner_ids", "query", "top_k"}:
            raise ValueError("retrieve payload shape mismatch")
        owner_ids = _required_text_list(payload.get("owner_ids"), "owner_ids")
        query = _required_text(payload.get("query"), "query")
        top_k = _required_int(payload.get("top_k"), "top_k", minimum=1)
        if top_k > 100:
            raise ValueError("EverOS public search top_k must be <=100")
        self.begin_observations()
        try:
            started_ns = perf_counter_ns()
            owner_results = []
            for owner_index, owner_id in enumerate(owner_ids):
                episodes = await self._search_owner(owner_id, query, top_k)
                for product_rank, episode in enumerate(episodes, start=1):
                    owner_results.append(
                        (owner_index, product_rank, episode)
                    )
            latency_ms = max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)
            owner_results.sort(
                key=lambda row: (
                    -_required_float(row[2].get("score"), "episode.score"),
                    row[0],
                    row[1],
                    _required_text(row[2].get("id"), "episode.id"),
                )
            )
            deduplicated: list[dict[str, Any]] = []
            seen: set[tuple[Any, ...]] = set()
            for owner_index, product_rank, episode in owner_results:
                key = (
                    episode.get("session_id"),
                    episode.get("timestamp"),
                    episode.get("episode"),
                )
                if key in seen:
                    continue
                seen.add(key)
                normalized = dict(episode)
                normalized["owner_merge_index"] = owner_index
                normalized["owner_product_rank"] = product_rank
                deduplicated.append(normalized)
                if len(deduplicated) == top_k:
                    break
            llm, embedding, rerank = self.finish_observations()
        except BaseException:
            self.discard_observations()
            raise
        return {
            "embedding_observations": embedding,
            "items": deduplicated,
            "latency_ms": latency_ms,
            "llm_observations": llm,
            "rerank_observations": rerank,
        }

    async def _search_owner(
        self,
        owner_id: str,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """调用一次 public typed SearchRequest/service。"""

        from everos.memory.search import SearchRequest
        from everos.service import search

        request = SearchRequest(
            user_id=owner_id,
            app_id=self.config["app_id"],
            project_id=self.config["project_id"],
            query=query,
            method=self.config["search_method"],
            top_k=top_k,
            include_profile=False,
            enable_llm_rerank=False,
            filters=None,
        )
        response = await search(request)
        raw = response.model_dump(mode="json")
        episodes = raw.get("data", {}).get("episodes")
        if not isinstance(episodes, list) or not all(
            isinstance(item, dict) for item in episodes
        ):
            raise RuntimeError("EverOS search response episodes has invalid shape")
        return list(episodes)

    async def get_session_memories(self, payload: dict[str, Any]) -> dict[str, Any]:
        """读取一个 session 的全部 owner Episodes，不产生模型调用。"""

        if set(payload) != {"owner_ids", "session_id"}:
            raise ValueError("get_session_memories payload shape mismatch")
        owner_ids = _required_text_list(payload.get("owner_ids"), "owner_ids")
        session_id = _required_text(payload.get("session_id"), "session_id")
        return {
            "session_items": await self._get_session_items(owner_ids, session_id)
        }

    async def _get_session_items(
        self,
        owner_ids: list[str],
        session_id: str,
    ) -> list[dict[str, Any]]:
        """按 owner 顺序分页 public get，并去除 fan-out 的逐字重复 Episode。"""

        from everos.memory.get import GetRequest
        from everos.service import get

        items: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for owner_id in owner_ids:
            page = 1
            while True:
                request = GetRequest(
                    user_id=owner_id,
                    app_id=self.config["app_id"],
                    project_id=self.config["project_id"],
                    memory_type="episode",
                    page=page,
                    page_size=100,
                    sort_by="timestamp",
                    sort_order="asc",
                    filters={"session_id": session_id},
                )
                response = await get(request)
                raw = response.model_dump(mode="json")
                data = raw.get("data")
                if not isinstance(data, dict):
                    raise RuntimeError("EverOS get response data has invalid shape")
                episodes = data.get("episodes")
                if not isinstance(episodes, list) or not all(
                    isinstance(item, dict) for item in episodes
                ):
                    raise RuntimeError("EverOS get response episodes has invalid shape")
                for episode in episodes:
                    normalized = dict(episode)
                    normalized.setdefault("atomic_facts", [])
                    key = (
                        normalized.get("session_id"),
                        normalized.get("timestamp"),
                        normalized.get("episode"),
                    )
                    if key in seen:
                        continue
                    seen.add(key)
                    items.append(normalized)
                count = _required_int(data.get("count"), "get.count")
                total = _required_int(data.get("total_count"), "get.total_count")
                if page * 100 >= total or count == 0:
                    break
                page += 1
        items.sort(
            key=lambda item: (
                str(item.get("timestamp") or ""),
                str(item.get("id") or ""),
            )
        )
        return items

    async def _exact_drain(self) -> dict[str, Any]:
        """等待 OME 全终态并把 Cascade 扫描/队列/优化精确压至稳定零。

        当前 worker 的物理 root 只属于一个 conversation，因此 whole-root run/queue
        检查就是 conversation-scoped，不会把兄弟 conversation 的历史失败混进来。
        """

        lifespan_data = getattr(self.app.state, "lifespan_data", None)
        if not isinstance(lifespan_data, dict):
            raise RuntimeError("EverOS lifespan_data is unavailable")
        engine = lifespan_data.get("ome")
        cascade = lifespan_data.get("cascade")
        if engine is None or cascade is None:
            raise RuntimeError("EverOS OME/Cascade lifespan providers are missing")
        timeout = self.config["drain_timeout_seconds"]
        if not await engine.wait_idle(timeout=timeout):
            raise TimeoutError("EverOS OME did not reach idle before deadline")
        ome = await self._assert_ome_terminal(engine)

        total_processed = 0
        stable_zero_passes = 0
        cascade_deadline = monotonic() + timeout
        while True:
            processed = await cascade.sync_once()
            total_processed += processed
            health = await cascade.health()
            if not health.healthy:
                raise RuntimeError(
                    "EverOS Cascade is operationally unhealthy: "
                    + ", ".join(health.reasons)
                )
            if health.failed_retryable:
                raise RuntimeError(
                    f"EverOS Cascade has {health.failed_retryable} retryable failures"
                )
            if health.failed_permanent:
                raise RuntimeError(
                    f"EverOS Cascade has {health.failed_permanent} permanent failures"
                )
            if processed == 0 and health.pending == 0:
                stable_zero_passes += 1
                if stable_zero_passes == 2:
                    break
            else:
                stable_zero_passes = 0
            remaining = cascade_deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    "EverOS Cascade did not reach two stable zero passes "
                    "before deadline"
                )
            # ``health.pending`` includes rows already claimed by the product's
            # background worker.  A fixed tight loop can exhaust its iteration
            # budget before that task gets another event-loop turn, then tear
            # down the operation observation buffer while the task is still
            # issuing model calls.  Yield under the same wall-clock deadline so
            # completion remains exact without changing Cascade scheduling.
            await asyncio.sleep(min(_CASCADE_SETTLE_POLL_SECONDS, remaining))
        if not await engine.wait_idle(timeout=timeout):
            raise TimeoutError("EverOS transitive OME work did not reach idle")
        final_ome = await self._assert_ome_terminal(engine)
        return {
            "cascade_processed": total_processed,
            "cascade_stable_zero_passes": stable_zero_passes,
            "ome_run_count_before_cascade": ome["run_count"],
            "ome_run_count_after_cascade": final_ome["run_count"],
        }

    @staticmethod
    async def _assert_ome_terminal(engine: Any) -> dict[str, int]:
        """按 event retry 链判 OME：失败 attempt 可恢复，最终链必须 success。"""

        from everos.infra.ome.records import RunStatus

        rows: list[Any] = []
        for meta in engine._registry.all():
            strategy_rows = await engine.list_runs(meta.name, limit=100_000)
            if len(strategy_rows) >= 100_000:
                raise RuntimeError("EverOS OME run history exceeded exact audit limit")
            rows.extend(strategy_rows)
        by_event: dict[str, list[Any]] = {}
        for row in rows:
            by_event.setdefault(row.event_id or row.run_id, []).append(row)
        for event_id, event_rows in by_event.items():
            statuses = {row.status.value for row in event_rows}
            if RunStatus.RUNNING.value in statuses:
                raise RuntimeError(f"EverOS OME event {event_id} remains running")
            failures = statuses & _TERMINAL_FAILURES
            if failures:
                raise RuntimeError(
                    f"EverOS OME event {event_id} ended in {sorted(failures)}"
                )
            if RunStatus.FAILED.value in statuses and RunStatus.SUCCESS.value not in statuses:
                raise RuntimeError(
                    f"EverOS OME event {event_id} has failed attempts without success"
                )
        return {"run_count": len(rows), "event_count": len(by_event)}

    async def shutdown(self) -> dict[str, Any]:
        """先 exact drain，再退出 patched official lifespan。"""

        if self._closed:
            return {"status": "closed"}
        await self._exact_drain()
        lifespan = self.lifespan
        if lifespan is None:
            raise RuntimeError("EverOS lifespan is missing during shutdown")
        await lifespan.__aexit__(None, None, None)
        self.lifespan = None
        self.app = None
        self._closed = True
        return {"status": "closed"}


def _sanitize_error(message: str) -> str:
    """从错误文本移除 worker 可见的全部 credential。"""

    redacted = message
    for name, value in os.environ.items():
        if (
            name.endswith("__API_KEY")
            or name.endswith("_KEY")
            or name.endswith("_TOKEN")
        ) and value:
            redacted = redacted.replace(value, "<redacted>")
    return redacted


def _prepare_protocol_stream() -> Any:
    """保留原 stdout 给 JSON 协议，把第三方输出全部导向 stderr。"""

    protocol = os.fdopen(
        os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1
    )
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    return protocol


def main() -> int:
    """运行长驻串行命令循环。"""

    protocol = _prepare_protocol_stream()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    engine = _WorkerEngine()
    try:
        for raw_line in sys.stdin:
            request_id: Any = None
            should_stop = False
            try:
                request = json.loads(raw_line)
                if not isinstance(request, dict):
                    raise ValueError("request must be an object")
                request_id = request.get("request_id")
                result = loop.run_until_complete(engine.dispatch(request))
                response = {"request_id": request_id, "ok": True, "result": result}
                should_stop = request.get("command") == "shutdown"
            except BaseException as exc:
                traceback.print_exc(file=sys.stderr)
                response = {
                    "request_id": request_id,
                    "ok": False,
                    "error_type": exc.__class__.__name__,
                    "error": _sanitize_error(str(exc)),
                }
            protocol.write(
                json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n"
            )
            protocol.flush()
            if should_stop:
                break
    finally:
        if engine.app is not None and not engine._closed:
            try:
                loop.run_until_complete(engine.shutdown())
            except BaseException:
                traceback.print_exc(file=sys.stderr)
        loop.close()
        protocol.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
