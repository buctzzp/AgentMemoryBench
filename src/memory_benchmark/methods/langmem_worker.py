"""LangMem 独立 Python 3.12 运行时的 JSON-lines worker。

worker 只在 vendored LangMem 虚拟环境中导入第三方依赖。它通过官方
``create_memory_store_manager``、``MemoryStoreManager.ainvoke`` 与 ``asearch``
执行产品算法，并在公开 ``InMemoryStore`` 边界补充原子快照、幂等 operation journal
与逐调用观测；不负责 benchmark 适配或最终答题。
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import threading
from time import perf_counter_ns
import traceback
from typing import Any


LANGMEM_ADAPTER_VERSION = "langmem-background-product-v2"
LANGMEM_WORKER_STATE_SCHEMA_VERSION = "langmem-worker-state-v2"
_NAMESPACE_PREFIX = "memories"
_MAX_NAMESPACE_ITEMS = 1_000_000
_ALLOWED_ROLES = frozenset({"user", "assistant"})
_OPENCODEGO_REASONING_EFFORT_LOW_MODELS = frozenset({"ox-alpha-free"})


def _required_text(value: Any, label: str) -> str:
    """读取非空字符串，拒绝协议层宽松转换。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


def _required_int(value: Any, label: str, *, minimum: int = 0) -> int:
    """读取不小于下界的整数；布尔值不能冒充整数。"""

    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _required_float(value: Any, label: str, *, positive: bool = False) -> float:
    """读取有限数值，并可要求严格为正。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    resolved = float(value)
    if not math.isfinite(resolved) or (positive and resolved <= 0):
        qualifier = "positive and finite" if positive else "finite"
        raise ValueError(f"{label} must be {qualifier}")
    return resolved


def _optional_text(value: Any, label: str) -> str | None:
    """读取可空文本；空白字符串仍视为错误。"""

    if value is None:
        return None
    return _required_text(value, label)


def _validate_namespace_id(value: Any) -> str:
    """校验 adapter 生成的固定长度十六进制 namespace id。"""

    text = _required_text(value, "namespace_id")
    if len(text) != 32 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError("namespace_id must be 32 lowercase hexadecimal characters")
    return text


def _validate_messages(value: Any) -> list[dict[str, str]]:
    """强校验 manager 的 role/content messages，不接收额外字段。"""

    if not isinstance(value, list) or not value:
        raise ValueError("messages must be a non-empty list")
    normalized: list[dict[str, str]] = []
    for index, message in enumerate(value):
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise ValueError(
                f"messages[{index}] must contain exactly role and content"
            )
        role = _required_text(message.get("role"), f"messages[{index}].role")
        if role not in _ALLOWED_ROLES:
            raise ValueError(f"messages[{index}].role is unsupported: {role!r}")
        content = _required_text(message.get("content"), f"messages[{index}].content")
        normalized.append({"role": role, "content": content})
    return normalized


def _input_digest(messages: list[dict[str, str]], max_steps: int) -> str:
    """计算一次 ingest 的稳定公开输入摘要。"""

    payload = json.dumps(
        {"messages": messages, "max_steps": max_steps},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _atomic_write_json(path: Path, payload: Any) -> None:
    """在同目录写临时文件并原子替换，避免半截状态冒充可 resume。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    """读取严格 JSON 状态。"""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid LangMem state file: {path}") from exc


def _validate_embedding_observation(value: Any) -> dict[str, Any]:
    """校验 worker 返回的单次本地 embedding 观测。"""

    if not isinstance(value, dict) or set(value) != {
        "input_tokens",
        "latency_ms",
        "text_count",
    }:
        raise ValueError("embedding observation has an invalid shape")
    input_tokens = _required_int(value.get("input_tokens"), "input_tokens")
    text_count = _required_int(value.get("text_count"), "text_count", minimum=1)
    latency_ms = _required_float(value.get("latency_ms"), "latency_ms")
    if latency_ms < 0:
        raise ValueError("latency_ms must be non-negative")
    return {
        "input_tokens": input_tokens,
        "latency_ms": latency_ms,
        "text_count": text_count,
    }


def _validate_llm_observation(value: Any) -> dict[str, int]:
    """校验 worker 捕获的一次真实 LLM response usage。"""

    if not isinstance(value, dict) or set(value) != {"input_tokens", "output_tokens"}:
        raise ValueError("LLM observation has an invalid shape")
    return {
        "input_tokens": _required_int(value.get("input_tokens"), "input_tokens"),
        "output_tokens": _required_int(value.get("output_tokens"), "output_tokens"),
    }


def _validate_entry(value: Any) -> dict[str, Any]:
    """校验快照中的 product store key/value。"""

    if not isinstance(value, dict) or set(value) != {"key", "value"}:
        raise ValueError("LangMem state entry must contain exactly key/value")
    key = _required_text(value.get("key"), "entry.key")
    stored_value = value.get("value")
    if not isinstance(stored_value, dict):
        raise ValueError("entry.value must be an object")
    try:
        json.dumps(stored_value, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError("entry.value must be JSON serializable") from exc
    return {"key": key, "value": deepcopy(stored_value)}


def _validate_operation(value: Any) -> dict[str, Any]:
    """校验已完成 operation journal 记录。"""

    expected = {
        "changed_memories",
        "changed_memory_keys",
        "embedding_observations",
        "input_digest",
        "llm_observations",
        "memory_count",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("LangMem completed operation has an invalid shape")
    changed = value.get("changed_memory_keys")
    if not isinstance(changed, list) or not all(
        isinstance(item, str) and item.strip() for item in changed
    ):
        raise ValueError("changed_memory_keys must be a list of non-blank strings")
    changed_memories = value.get("changed_memories")
    if not isinstance(changed_memories, list):
        raise ValueError("changed_memories must be a list")
    normalized_changed_memories = [
        _validate_entry(item) for item in changed_memories
    ]
    if [item["key"] for item in normalized_changed_memories] != changed:
        raise ValueError(
            "changed_memories must match changed_memory_keys in product order"
        )
    llm = value.get("llm_observations")
    embedding = value.get("embedding_observations")
    if not isinstance(llm, list) or not isinstance(embedding, list):
        raise ValueError("operation observations must be lists")
    return {
        "changed_memories": normalized_changed_memories,
        "changed_memory_keys": list(changed),
        "embedding_observations": [
            _validate_embedding_observation(item) for item in embedding
        ],
        "input_digest": _required_text(value.get("input_digest"), "input_digest"),
        "llm_observations": [_validate_llm_observation(item) for item in llm],
        "memory_count": _required_int(value.get("memory_count"), "memory_count"),
    }


def _validate_state(value: Any, *, expected_namespace_id: str) -> dict[str, Any]:
    """完整校验一个 namespace 的原子快照与 journal。"""

    expected = {
        "adapter_version",
        "completed_operations",
        "entries",
        "namespace_id",
        "schema_version",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("LangMem state has an invalid top-level shape")
    if value.get("schema_version") != LANGMEM_WORKER_STATE_SCHEMA_VERSION:
        raise ValueError("LangMem worker state schema version mismatch")
    if value.get("adapter_version") != LANGMEM_ADAPTER_VERSION:
        raise ValueError("LangMem adapter version mismatch in worker state")
    namespace_id = _validate_namespace_id(value.get("namespace_id"))
    if namespace_id != expected_namespace_id:
        raise ValueError("LangMem state namespace identity mismatch")
    entries = value.get("entries")
    operations = value.get("completed_operations")
    if not isinstance(entries, list) or not isinstance(operations, dict):
        raise ValueError("LangMem state entries/operations have invalid types")
    normalized_entries = [_validate_entry(item) for item in entries]
    keys = [item["key"] for item in normalized_entries]
    if len(keys) != len(set(keys)):
        raise ValueError("LangMem state contains duplicate entry keys")
    normalized_operations: dict[str, dict[str, Any]] = {}
    for operation_id, operation in operations.items():
        normalized_id = _required_text(operation_id, "operation_id")
        normalized_operations[normalized_id] = _validate_operation(operation)
    return {
        "adapter_version": LANGMEM_ADAPTER_VERSION,
        "completed_operations": normalized_operations,
        "entries": normalized_entries,
        "namespace_id": namespace_id,
        "schema_version": LANGMEM_WORKER_STATE_SCHEMA_VERSION,
    }


def _empty_state(namespace_id: str) -> dict[str, Any]:
    """构造一个尚无 memory 与 operation 的合法状态。"""

    return {
        "adapter_version": LANGMEM_ADAPTER_VERSION,
        "completed_operations": {},
        "entries": [],
        "namespace_id": namespace_id,
        "schema_version": LANGMEM_WORKER_STATE_SCHEMA_VERSION,
    }


def _usage_from_llm_result(response: Any) -> dict[str, int]:
    """从一次 LangChain LLMResult 读取 provider 返回的精确 usage。"""

    usage: Any = None
    generations = getattr(response, "generations", None)
    if isinstance(generations, list) and generations:
        first_group = generations[0]
        if isinstance(first_group, list) and first_group:
            message = getattr(first_group[0], "message", None)
            usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        llm_output = getattr(response, "llm_output", None)
        if isinstance(llm_output, dict):
            usage = llm_output.get("token_usage") or llm_output.get("usage")
    if not isinstance(usage, dict):
        raise RuntimeError("LangMem build LLM response omitted exact token usage")
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens"))
    return {
        "input_tokens": _required_int(input_tokens, "usage.input_tokens"),
        "output_tokens": _required_int(output_tokens, "usage.output_tokens"),
    }


class _WorkerEngine:
    """在单一 event loop 内持有官方 manager、store 与持久化状态。"""

    def __init__(self) -> None:
        """创建未初始化 worker。"""

        self.config: dict[str, Any] = {}
        self.manager: Any = None
        self.store: Any = None
        self.embedding_model: Any = None
        self.usage_callback: Any = None
        self.state_root: Path | None = None
        self.loaded_namespaces: set[str] = set()
        self._llm_observations: list[dict[str, int]] | None = None
        self._embedding_observations: list[dict[str, Any]] | None = None
        self._failed_error_details: dict[str, Any] | None = None
        self._observation_lock = threading.Lock()
        self._unscoped_embedding_calls = 0
        self._closed = False

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """路由一条已解析 JSON-lines 请求。"""

        self._failed_error_details = None
        command = _required_text(request.get("command"), "command")
        payload = request.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if command == "initialize":
            return await self.initialize(payload)
        self._require_ready()
        if command == "ping":
            return {"status": "ready"}
        if command == "ingest":
            return await self.ingest(payload)
        if command == "retrieve":
            return await self.retrieve(payload)
        if command == "delete_namespace":
            return await self.delete_namespace(payload)
        if command == "shutdown":
            return await self.shutdown()
        raise ValueError(f"unknown command: {command}")

    async def initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """构造真实 ChatOpenAI、MiniLM、InMemoryStore 与官方 manager。"""

        if self.manager is not None:
            raise RuntimeError("LangMem worker was already initialized")
        raw_config = payload.get("config")
        if not isinstance(raw_config, dict):
            raise ValueError("initialize.config must be an object")
        self.config = self._validate_config(raw_config)
        state_root = Path(_required_text(payload.get("state_root"), "state_root"))
        if not state_root.is_absolute():
            raise ValueError("state_root must be absolute")
        state_root.mkdir(parents=True, exist_ok=True)
        self.state_root = state_root

        model_path = Path(self.config["embedding_model_path"])
        if not model_path.is_absolute() or not model_path.is_dir():
            raise ValueError("embedding_model_path must be an existing absolute directory")
        api_key_name = "MEMORY_BENCHMARK_LANGMEM_BUILD_API_KEY"
        api_key = _required_text(os.environ.get(api_key_name), api_key_name)

        from langchain_core.callbacks import BaseCallbackHandler
        from langchain_core.embeddings import Embeddings
        from langchain_openai import ChatOpenAI
        from langgraph.store.memory import InMemoryStore
        from langmem import create_memory_store_manager
        from sentence_transformers import SentenceTransformer

        engine = self

        class _ObservedUsageCallback(BaseCallbackHandler):
            """把每次成功 LLM response usage 送回当前 operation。"""

            raise_error = True

            def on_llm_end(self, response: Any, **_kwargs: Any) -> None:
                """记录 exact usage；provider 漏 usage 时让业务调用失败。"""

                engine._record_llm_observation(_usage_from_llm_result(response))

        class _ObservedEmbeddings(Embeddings):
            """序列化访问本地 SentenceTransformer，并逐调用记录事实。"""

            def __init__(self) -> None:
                """加载本地模型并创建线程锁。"""

                self.model = SentenceTransformer(str(model_path))
                self.lock = threading.Lock()

            def _encode(self, texts: list[str]) -> list[list[float]]:
                """对实际收到的文本编码并记录 tokenizer/latency。"""

                if not texts:
                    return []
                with self.lock:
                    tokenized = self.model.tokenizer(
                        texts,
                        add_special_tokens=True,
                        padding=False,
                        truncation=True,
                        max_length=self.model.max_seq_length,
                    )
                    input_tokens = sum(len(ids) for ids in tokenized["input_ids"])
                    started_ns = perf_counter_ns()
                    vectors = self.model.encode(
                        texts,
                        normalize_embeddings=self.config_normalize,
                        convert_to_numpy=True,
                    )
                    latency_ms = max(
                        0.0,
                        (perf_counter_ns() - started_ns) / 1_000_000,
                    )
                if vectors.shape != (len(texts), self.config_dimension):
                    raise RuntimeError(
                        "LangMem embedding output dimension mismatch: "
                        f"shape={vectors.shape!r}"
                    )
                engine._record_embedding_observation(
                    {
                        "input_tokens": input_tokens,
                        "latency_ms": latency_ms,
                        "text_count": len(texts),
                    }
                )
                return vectors.tolist()

            @property
            def config_dimension(self) -> int:
                """读取 worker 已校验的 embedding dimension。"""

                return engine.config["embedding_dimension"]

            @property
            def config_normalize(self) -> bool:
                """读取 worker 已校验的 normalize 开关。"""

                return engine.config["embedding_normalize"]

            def embed_documents(self, texts: list[str]) -> list[list[float]]:
                """实现 LangChain 同步批量 embedding 接口。"""

                return self._encode(list(texts))

            def embed_query(self, text: str) -> list[float]:
                """实现 LangChain 同步 query embedding 接口。"""

                return self._encode([text])[0]

            async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
                """在线程中执行本地批量 embedding，避免阻塞 event loop。"""

                return await asyncio.to_thread(self._encode, list(texts))

            async def aembed_query(self, text: str) -> list[float]:
                """在线程中执行本地 query embedding。"""

                return (await asyncio.to_thread(self._encode, [text]))[0]

        chat_kwargs: dict[str, Any] = {
            "api_key": api_key,
            "max_retries": self.config["api_max_retries"],
            "model": self.config["llm_model"],
            "timeout": self.config["api_timeout_seconds"],
            "use_responses_api": False,
        }
        if self.config["api_base_url"] is not None:
            chat_kwargs["base_url"] = self.config["api_base_url"]
        if self.config["api_provider"] == "opencodego":
            if self.config["llm_model"] in _OPENCODEGO_REASONING_EFFORT_LOW_MODELS:
                chat_kwargs["reasoning_effort"] = "low"
            else:
                chat_kwargs["extra_body"] = {"thinking": {"type": "disabled"}}
        chat_model = ChatOpenAI(**chat_kwargs)
        self.embedding_model = _ObservedEmbeddings()
        self.usage_callback = _ObservedUsageCallback()
        self.store = InMemoryStore(
            index={
                "dims": self.config["embedding_dimension"],
                "embed": self.embedding_model,
            }
        )
        self.manager = create_memory_store_manager(
            chat_model,
            enable_inserts=self.config["enable_inserts"],
            enable_deletes=self.config["enable_deletes"],
            query_limit=self.config["query_limit"],
            namespace=(_NAMESPACE_PREFIX, "{langgraph_user_id}"),
            store=self.store,
        )
        return {
            "adapter_version": LANGMEM_ADAPTER_VERSION,
            "status": "ready",
            "product_surface": "create_memory_store_manager+ainvoke+asearch",
        }

    @staticmethod
    def _validate_config(raw: dict[str, Any]) -> dict[str, Any]:
        """强校验 worker 真正消费的配置；secret 不经 payload。"""

        provider = _required_text(raw.get("api_provider"), "api_provider")
        if provider not in {"primary", "opencodego"}:
            raise ValueError("api_provider must be primary or opencodego")
        enable_inserts = raw.get("enable_inserts")
        enable_deletes = raw.get("enable_deletes")
        embedding_normalize = raw.get("embedding_normalize")
        for label, value in (
            ("enable_inserts", enable_inserts),
            ("enable_deletes", enable_deletes),
            ("embedding_normalize", embedding_normalize),
        ):
            if type(value) is not bool:
                raise ValueError(f"{label} must be boolean")
        if enable_inserts is not True or enable_deletes is not False:
            raise ValueError("LangMem product profile requires inserts=true/deletes=false")
        return {
            "api_base_url": _optional_text(raw.get("api_base_url"), "api_base_url"),
            "api_max_retries": _required_int(
                raw.get("api_max_retries"), "api_max_retries"
            ),
            "api_provider": provider,
            "api_timeout_seconds": _required_float(
                raw.get("api_timeout_seconds"),
                "api_timeout_seconds",
                positive=True,
            ),
            "embedding_dimension": _required_int(
                raw.get("embedding_dimension"),
                "embedding_dimension",
                minimum=1,
            ),
            "embedding_model_path": _required_text(
                raw.get("embedding_model_path"), "embedding_model_path"
            ),
            "embedding_normalize": embedding_normalize,
            "enable_deletes": enable_deletes,
            "enable_inserts": enable_inserts,
            "llm_model": _required_text(raw.get("llm_model"), "llm_model"),
            "max_steps": _required_int(raw.get("max_steps"), "max_steps", minimum=1),
            "query_limit": _required_int(
                raw.get("query_limit"), "query_limit", minimum=1
            ),
        }

    def _require_ready(self) -> None:
        """拒绝初始化前或关闭后的业务命令。"""

        if self.manager is None or self.store is None or self.state_root is None:
            raise RuntimeError("LangMem worker is not initialized")
        if self._closed:
            raise RuntimeError("LangMem worker is closed")

    def _namespace(self, namespace_id: str) -> tuple[str, str]:
        """返回与官方 NamespaceTemplate 一致的 concrete namespace。"""

        return (_NAMESPACE_PREFIX, namespace_id)

    def _config_for_namespace(self, namespace_id: str) -> dict[str, Any]:
        """构造官方 manager 解析动态 namespace 的 RunnableConfig。"""

        return {"configurable": {"langgraph_user_id": namespace_id}}

    def _state_path(self, namespace_id: str) -> Path:
        """返回 namespace 的 active 原子状态路径。"""

        assert self.state_root is not None
        return self.state_root / f"{namespace_id}.json"

    def _cleanup_path(self, namespace_id: str) -> Path:
        """返回 clean retry tombstone 路径。"""

        assert self.state_root is not None
        return self.state_root / f"{namespace_id}.cleanup.json"

    def _load_state(self, namespace_id: str) -> dict[str, Any]:
        """读取 active 状态；不存在时返回未提交空状态。"""

        path = self._state_path(namespace_id)
        if not path.is_file():
            return _empty_state(namespace_id)
        return _validate_state(_read_json(path), expected_namespace_id=namespace_id)

    async def _ensure_namespace_loaded(self, namespace_id: str) -> dict[str, int]:
        """经公开 store.put 恢复快照，返回未混入算法 scope 的恢复开销。"""

        if self._cleanup_path(namespace_id).exists():
            raise RuntimeError(
                "LangMem namespace has an unfinished cleanup tombstone; retry cleanup first"
            )
        if namespace_id in self.loaded_namespaces:
            return {"rehydrated_entry_count": 0, "rehydration_embedding_calls": 0}
        state = self._load_state(namespace_id)
        before = self._unscoped_embedding_calls
        for entry in state["entries"]:
            await self.store.aput(
                self._namespace(namespace_id),
                entry["key"],
                deepcopy(entry["value"]),
            )
        self.loaded_namespaces.add(namespace_id)
        return {
            "rehydrated_entry_count": len(state["entries"]),
            "rehydration_embedding_calls": self._unscoped_embedding_calls - before,
        }

    async def _snapshot_entries(self, namespace_id: str) -> list[dict[str, Any]]:
        """按 product store 当前插入顺序读取 exact key/value。"""

        items = await self.store.asearch(
            self._namespace(namespace_id),
            query=None,
            limit=_MAX_NAMESPACE_ITEMS,
        )
        return [
            {"key": item.key, "value": deepcopy(item.value)} for item in items
        ]

    async def _replace_entries(
        self,
        namespace_id: str,
        entries: list[dict[str, Any]],
    ) -> None:
        """经公开 delete/put 恢复 namespace exact key/value/order。"""

        namespace = self._namespace(namespace_id)
        current = await self.store.asearch(
            namespace,
            query=None,
            limit=_MAX_NAMESPACE_ITEMS,
        )
        for item in current:
            await self.store.adelete(namespace, item.key)
        for entry in entries:
            await self.store.aput(
                namespace,
                entry["key"],
                deepcopy(entry["value"]),
            )

    def _begin_observations(self) -> None:
        """建立一次业务 operation 的 LLM/embedding buffer。"""

        with self._observation_lock:
            if self._llm_observations is not None or self._embedding_observations is not None:
                raise RuntimeError("LangMem observation buffer is already active")
            self._llm_observations = []
            self._embedding_observations = []

    def _finish_observations(self) -> tuple[list[dict[str, int]], list[dict[str, Any]]]:
        """冻结并清空当前成功 operation 的观测。"""

        with self._observation_lock:
            if self._llm_observations is None or self._embedding_observations is None:
                raise RuntimeError("LangMem observation buffer is not active")
            llm = list(self._llm_observations)
            embedding = list(self._embedding_observations)
            self._llm_observations = None
            self._embedding_observations = None
        return llm, embedding

    def _discard_observations(
        self,
    ) -> tuple[list[dict[str, int]], list[dict[str, Any]]]:
        """弹出失败 operation 已完成的调用，供 attempt ledger 使用。"""

        with self._observation_lock:
            llm = list(self._llm_observations or [])
            embedding = list(self._embedding_observations or [])
            self._llm_observations = None
            self._embedding_observations = None
        return llm, embedding

    def _set_failed_observations(
        self,
        *,
        llm: list[dict[str, int]],
        embedding: list[dict[str, Any]],
    ) -> None:
        """保存当前命令失败前已拿到的公开 usage/latency。"""

        self._failed_error_details = {
            "llm_observations": [dict(item) for item in llm],
            "embedding_observations": [dict(item) for item in embedding],
        }

    def pop_failed_error_details(self) -> dict[str, Any] | None:
        """返回并清除最近一次失败命令的结构化观测。"""

        details = self._failed_error_details
        self._failed_error_details = None
        return details

    def _record_llm_observation(self, observation: dict[str, int]) -> None:
        """追加一次 exact LLM usage；非业务 scope 调用视为错误。"""

        normalized = _validate_llm_observation(observation)
        with self._observation_lock:
            if self._llm_observations is None:
                raise RuntimeError("LangMem LLM call occurred outside an ingest operation")
            self._llm_observations.append(normalized)

    def _record_embedding_observation(self, observation: dict[str, Any]) -> None:
        """追加实际 embedding 调用，恢复期调用单独计数而不伪装业务 scope。"""

        normalized = _validate_embedding_observation(observation)
        with self._observation_lock:
            if self._embedding_observations is None:
                self._unscoped_embedding_calls += 1
                return
            self._embedding_observations.append(normalized)

    async def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        """执行一次 session 级官方 async manager transaction。"""

        namespace_id = _validate_namespace_id(payload.get("namespace_id"))
        operation_id = _required_text(payload.get("operation_id"), "operation_id")
        messages = _validate_messages(payload.get("messages"))
        max_steps = _required_int(payload.get("max_steps"), "max_steps", minimum=1)
        if max_steps != self.config["max_steps"]:
            raise ValueError("ingest max_steps differs from initialized product profile")
        digest = _input_digest(messages, max_steps)
        rehydration = await self._ensure_namespace_loaded(namespace_id)
        state = self._load_state(namespace_id)
        completed = state["completed_operations"].get(operation_id)
        if completed is not None:
            if completed["input_digest"] != digest:
                raise RuntimeError("LangMem operation id was reused with different input")
            return {**deepcopy(completed), **rehydration, "reused_operation": True}

        before_entries = await self._snapshot_entries(namespace_id)
        llm_observations: list[dict[str, int]] = []
        embedding_observations: list[dict[str, Any]] = []
        self._begin_observations()
        try:
            changed = await self.manager.ainvoke(
                {"messages": messages, "max_steps": max_steps},
                config={
                    **self._config_for_namespace(namespace_id),
                    "callbacks": [self.usage_callback],
                },
            )
            llm_observations, embedding_observations = self._finish_observations()
            if not isinstance(changed, list):
                raise RuntimeError("LangMem manager returned a non-list result")
            changed_keys: list[str] = []
            for item in changed:
                if not isinstance(item, dict):
                    raise RuntimeError("LangMem manager changed-memory item is malformed")
                changed_keys.append(_required_text(item.get("key"), "changed.key"))
            entries = await self._snapshot_entries(namespace_id)
            entries_by_key = {entry["key"]: entry for entry in entries}
            if len(set(changed_keys)) != len(changed_keys):
                raise RuntimeError("LangMem manager returned duplicate changed-memory keys")
            missing_changed_keys = [
                key for key in changed_keys if key not in entries_by_key
            ]
            if missing_changed_keys:
                raise RuntimeError(
                    "LangMem changed-memory keys are absent from the current product "
                    f"store: {missing_changed_keys}"
                )
            operation = {
                "changed_memories": [
                    deepcopy(entries_by_key[key]) for key in changed_keys
                ],
                "changed_memory_keys": changed_keys,
                "embedding_observations": embedding_observations,
                "input_digest": digest,
                "llm_observations": llm_observations,
                "memory_count": len(entries),
            }
            next_state = {
                **state,
                "entries": entries,
                "completed_operations": {
                    **state["completed_operations"],
                    operation_id: operation,
                },
            }
            _validate_state(next_state, expected_namespace_id=namespace_id)
            _atomic_write_json(self._state_path(namespace_id), next_state)
        except BaseException:
            buffered_llm, buffered_embedding = self._discard_observations()
            self._set_failed_observations(
                llm=llm_observations or buffered_llm,
                embedding=embedding_observations or buffered_embedding,
            )
            await self._replace_entries(namespace_id, before_entries)
            raise
        return {**deepcopy(operation), **rehydration, "reused_operation": False}

    async def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调用官方 ``MemoryStoreManager.asearch`` 并保留产品 rank/score。"""

        namespace_id = _validate_namespace_id(payload.get("namespace_id"))
        query = _required_text(payload.get("query"), "query")
        limit = _required_int(payload.get("limit"), "limit", minimum=1)
        rehydration = await self._ensure_namespace_loaded(namespace_id)
        llm_observations: list[dict[str, int]] = []
        embedding_observations: list[dict[str, Any]] = []
        self._begin_observations()
        try:
            started_ns = perf_counter_ns()
            items = await self.manager.asearch(
                query=query,
                limit=limit,
                config={
                    **self._config_for_namespace(namespace_id),
                    "callbacks": [self.usage_callback],
                },
            )
            latency_ms = max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)
            llm_observations, embedding_observations = self._finish_observations()
            if llm_observations:
                raise RuntimeError("LangMem product asearch unexpectedly called an LLM")
        except BaseException:
            buffered_llm, buffered_embedding = self._discard_observations()
            self._set_failed_observations(
                llm=llm_observations or buffered_llm,
                embedding=embedding_observations or buffered_embedding,
            )
            raise
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            value = item.value
            if hasattr(value, "model_dump"):
                content_value = value.model_dump(mode="json")
                kind = value.__class__.__name__
            elif isinstance(value, dict):
                kind = str(value.get("kind") or "dict")
                raw_content = value.get("content", value)
                content_value = (
                    raw_content if isinstance(raw_content, dict) else {"content": raw_content}
                )
            else:
                raise RuntimeError("LangMem search item value is unsupported")
            content = content_value.get("content")
            if not isinstance(content, str) or not content.strip():
                content = json.dumps(content_value, ensure_ascii=False, sort_keys=True)
            score = item.score
            if score is not None:
                score = _required_float(score, "search.score")
            normalized_items.append(
                {
                    "content": content,
                    "key": _required_text(item.key, "search.key"),
                    "kind": kind,
                    "score": score,
                }
            )
        return {
            "embedding_observations": embedding_observations,
            "items": normalized_items,
            "latency_ms": latency_ms,
            **rehydration,
        }

    async def delete_namespace(self, payload: dict[str, Any]) -> dict[str, Any]:
        """以 tombstone 支持 namespace-scoped、可重试 cleanup。"""

        namespace_id = _validate_namespace_id(payload.get("namespace_id"))
        active_path = self._state_path(namespace_id)
        cleanup_path = self._cleanup_path(namespace_id)
        if cleanup_path.is_file():
            state = _validate_state(
                _read_json(cleanup_path),
                expected_namespace_id=namespace_id,
            )
        elif active_path.is_file():
            state = self._load_state(namespace_id)
            _atomic_write_json(cleanup_path, state)
            active_path.unlink()
        else:
            state = _empty_state(namespace_id)

        if namespace_id not in self.loaded_namespaces:
            for entry in state["entries"]:
                await self.store.aput(
                    self._namespace(namespace_id),
                    entry["key"],
                    deepcopy(entry["value"]),
                )
            self.loaded_namespaces.add(namespace_id)
        namespace = self._namespace(namespace_id)
        current = await self.store.asearch(
            namespace,
            query=None,
            limit=_MAX_NAMESPACE_ITEMS,
        )
        for item in current:
            await self.store.adelete(namespace, item.key)
        remaining = await self.store.asearch(
            namespace,
            query=None,
            limit=1,
        )
        if remaining:
            raise RuntimeError("LangMem namespace is not empty after cleanup")
        active_path.unlink(missing_ok=True)
        cleanup_path.unlink(missing_ok=True)
        self.loaded_namespaces.discard(namespace_id)
        return {"deleted": True, "deleted_entry_count": len(current)}

    async def shutdown(self) -> dict[str, Any]:
        """关闭进程内引用；所有成功状态已在每次 ingest 原子提交。"""

        self.manager = None
        self.store = None
        self.embedding_model = None
        self.usage_callback = None
        self.loaded_namespaces.clear()
        self._closed = True
        return {"status": "closed"}


def _sanitize_error(message: str) -> str:
    """从错误文本移除 worker 私有 API key。"""

    secret = os.environ.get("MEMORY_BENCHMARK_LANGMEM_BUILD_API_KEY")
    return message.replace(secret, "<redacted>") if secret else message


def _prepare_protocol_stream() -> Any:
    """保留原 stdout 给协议，把第三方普通输出全部改送 stderr。"""

    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    return protocol


def main() -> int:
    """运行长驻、串行的 JSON-lines 命令循环。"""

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
                error_details = engine.pop_failed_error_details()
                if error_details is not None:
                    response["error_details"] = error_details
            protocol.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
            protocol.flush()
            if should_stop:
                break
    finally:
        if engine.manager is not None and not engine._closed:
            try:
                loop.run_until_complete(engine.shutdown())
            except BaseException:
                traceback.print_exc(file=sys.stderr)
        loop.close()
        protocol.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
