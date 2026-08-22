"""Graphiti OSS 独立 Python 3.12 JSON-lines worker。

worker 只在 vendored Graphiti 虚拟环境中导入第三方依赖，调用公开
``Graphiti.add_episode`` / ``Graphiti.search``。每个 conversation 使用独占
FalkorDB Lite 文件；原子 sidecar 只记录幂等、source lineage 与 HaluMem session
delta，不修改 graph 算法或 answer 逻辑。
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from time import perf_counter_ns
import traceback
from types import SimpleNamespace
from typing import Any


# 必须在任何 graphiti_core import 前关闭 upstream 默认开启的 PostHog telemetry。
os.environ["GRAPHITI_TELEMETRY_ENABLED"] = "false"

GRAPHITI_ADAPTER_VERSION = "graphiti-oss-product-v1"
GRAPHITI_PRODUCT_SURFACE = "Graphiti.add_episode+Graphiti.search"
GRAPHITI_STATE_SCHEMA_VERSION = "graphiti-worker-state-v1"
GRAPHITI_CLEANUP_SCHEMA_VERSION = "graphiti-worker-cleanup-v1"
GRAPHITI_CONVERSATION_MARKER = "conversation_id.txt"
GRAPHITI_DATABASE = "graphiti"
_SESSION_NONE_KEY = "__none__"
_OPENCODEGO_REASONING_EFFORT_LOW_MODELS = frozenset({"ox-alpha-free"})


def _required_text(value: Any, label: str) -> str:
    """读取非空字符串。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    """读取可空文本；空白文本仍为协议错误。"""

    if value is None:
        return None
    return _required_text(value, label)


def _required_int(value: Any, label: str, *, minimum: int = 0) -> int:
    """读取不小于下界的整数，拒绝 bool。"""

    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _required_float(
    value: Any,
    label: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> float:
    """读取有限数值，可要求正值或非负。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be numeric")
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ValueError(f"{label} must be finite")
    if positive and resolved <= 0:
        raise ValueError(f"{label} must be positive")
    if non_negative and resolved < 0:
        raise ValueError(f"{label} must be non-negative")
    return resolved


def _required_bool(value: Any, label: str) -> bool:
    """读取严格布尔值。"""

    if type(value) is not bool:
        raise ValueError(f"{label} must be boolean")
    return value


def _validate_hex_id(value: Any, label: str, length: int = 64) -> str:
    """校验固定长度小写十六进制 id。"""

    text = _required_text(value, label)
    if len(text) != length or any(ch not in "0123456789abcdef" for ch in text):
        raise ValueError(f"{label} must be {length} lowercase hexadecimal characters")
    return text


def _session_key(session_id: str | None) -> str:
    """把可空 session id 变成 JSON object 的稳定 key。"""

    return _SESSION_NONE_KEY if session_id is None else session_id


def _state_dir_name(isolation_key: str) -> str:
    """把任意公开 isolation key 映射成稳定、安全目录名。"""

    digest = hashlib.sha256(isolation_key.encode("utf-8")).hexdigest()[:24]
    return f"conversation_{digest}"


def _atomic_write_json(path: Path, payload: Any) -> None:
    """同目录 fsync 后原子替换 JSON，拒绝半截 sidecar。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(name)
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
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    """同步目录项变更，使 sidecar/cleanup 提交跨进程崩溃可恢复。"""

    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _read_json(path: Path) -> Any:
    """读取严格 JSON。"""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid Graphiti state file: {path}") from exc


def _empty_state(isolation_key: str) -> dict[str, Any]:
    """返回一个空 conversation sidecar。"""

    return {
        "contract_version": GRAPHITI_STATE_SCHEMA_VERSION,
        "isolation_key": isolation_key,
        "episode_to_turn": {},
        "operations": {},
        "sessions": {},
    }


def _validate_string_list(value: Any, label: str) -> list[str]:
    """校验无重复、允许为空的非空字符串列表。"""

    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ValueError(f"{label} must be a list of non-blank strings")
    if len(value) != len(set(value)):
        raise ValueError(f"{label} must not contain duplicates")
    return list(value)


def _validate_observation_list(value: Any, label: str) -> list[dict[str, Any]]:
    """校验已提交 operation 的 observation 列表。"""

    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{label} must be a list of objects")
    return [dict(item) for item in value]


def _validate_state(value: Any, isolation_key: str) -> dict[str, Any]:
    """强校验 sidecar schema，禁止宽松恢复。"""

    expected = {
        "contract_version",
        "episode_to_turn",
        "isolation_key",
        "operations",
        "sessions",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ValueError("Graphiti state has an invalid top-level shape")
    if value.get("contract_version") != GRAPHITI_STATE_SCHEMA_VERSION:
        raise ValueError("Graphiti state contract_version mismatch")
    if value.get("isolation_key") != isolation_key:
        raise ValueError("Graphiti state isolation_key mismatch")
    episode_to_turn = value.get("episode_to_turn")
    if not isinstance(episode_to_turn, dict):
        raise ValueError("Graphiti episode_to_turn must be an object")
    normalized_episode_to_turn: dict[str, str] = {}
    for episode_uuid, turn_id in episode_to_turn.items():
        normalized_episode_to_turn[_required_text(episode_uuid, "episode uuid")] = (
            _required_text(turn_id, "turn id")
        )
    operations = value.get("operations")
    if not isinstance(operations, dict):
        raise ValueError("Graphiti operations must be an object")
    normalized_operations: dict[str, dict[str, Any]] = {}
    for operation_id, operation in operations.items():
        _validate_hex_id(operation_id, "operation_id")
        if not isinstance(operation, dict) or set(operation) != {
            "edge_count",
            "episode_uuid",
            "input_digest",
        }:
            raise ValueError("Graphiti completed operation has an invalid shape")
        normalized_operations[operation_id] = {
            "edge_count": _required_int(operation.get("edge_count"), "edge_count"),
            "episode_uuid": _required_text(
                operation.get("episode_uuid"), "episode_uuid"
            ),
            "input_digest": _validate_hex_id(
                operation.get("input_digest"), "input_digest"
            ),
        }
    sessions = value.get("sessions")
    if not isinstance(sessions, dict):
        raise ValueError("Graphiti sessions must be an object")
    normalized_sessions: dict[str, dict[str, list[str]]] = {}
    for key, session in sessions.items():
        _required_text(key, "session key")
        if not isinstance(session, dict) or set(session) != {
            "edge_uuids",
            "episode_uuids",
        }:
            raise ValueError("Graphiti session state has an invalid shape")
        normalized_sessions[key] = {
            "edge_uuids": _validate_string_list(
                session.get("edge_uuids"), "edge_uuids"
            ),
            "episode_uuids": _validate_string_list(
                session.get("episode_uuids"), "episode_uuids"
            ),
        }
    return {
        "contract_version": GRAPHITI_STATE_SCHEMA_VERSION,
        "isolation_key": isolation_key,
        "episode_to_turn": normalized_episode_to_turn,
        "operations": normalized_operations,
        "sessions": normalized_sessions,
    }


def _iso_or_none(value: Any) -> str | None:
    """把 upstream datetime/null 转成稳定 ISO 字符串。"""

    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError("Graphiti temporal edge field must be datetime or null")
    return value.isoformat()


class _ObservedCompletions:
    """只包裹真实 Chat Completions endpoint 并记录成功 response usage。"""

    def __init__(self, engine: "_WorkerEngine", real: Any) -> None:
        """保存 worker 与真实 endpoint。"""

        self._engine = engine
        self._real = real

    async def create(self, **kwargs: Any) -> Any:
        """保持请求参数，仅追加已锁 provider compatibility body。"""

        if self._engine.config["api_provider"] == "opencodego":
            if (
                self._engine.config["llm_model"]
                in _OPENCODEGO_REASONING_EFFORT_LOW_MODELS
            ):
                if "reasoning_effort" in kwargs:
                    raise RuntimeError(
                        "Graphiti caller already supplied reasoning_effort"
                    )
                kwargs["reasoning_effort"] = "low"
            else:
                extra_body = dict(kwargs.get("extra_body") or {})
                if "thinking" in extra_body:
                    raise RuntimeError(
                        "Graphiti caller already supplied thinking control"
                    )
                extra_body["thinking"] = {"type": "disabled"}
                kwargs["extra_body"] = extra_body
        response = await self._real.create(**kwargs)
        usage = getattr(response, "usage", None)
        input_tokens = getattr(usage, "prompt_tokens", None)
        output_tokens = getattr(usage, "completion_tokens", None)
        if type(input_tokens) is not int or input_tokens < 0:
            raise RuntimeError("Graphiti build response lacks exact prompt token usage")
        if type(output_tokens) is not int or output_tokens < 0:
            raise RuntimeError("Graphiti build response lacks exact completion token usage")
        self._engine.llm_observations.append(
            {"input_tokens": input_tokens, "output_tokens": output_tokens}
        )
        return response


class _ObservedOpenAI:
    """满足 OpenAIGenericClient 所需的最窄 ``chat.completions`` 对象。"""

    def __init__(self, engine: "_WorkerEngine", real: Any) -> None:
        """安装带精确 usage 观测的 completions 包装。"""

        self.chat = SimpleNamespace(
            completions=_ObservedCompletions(engine, real.chat.completions)
        )


class _WorkerEngine:
    """串行管理一个 Graphiti worker 与多个 conversation 物理 roots。"""

    def __init__(self) -> None:
        """初始化尚未装配第三方依赖的空 worker 状态。"""

        self.config: dict[str, Any] = {}
        self.state_root: Path | None = None
        self.graphiti_class: Any = None
        self.episode_type: Any = None
        self.entity_edge_class: Any = None
        self.async_falkor_class: Any = None
        self.falkor_driver_class: Any = None
        self.cross_encoder_client_class: Any = None
        self.llm_client_class: Any = None
        self.llm_config_class: Any = None
        self.embedder_client_class: Any = None
        self.sentence_transformer_class: Any = None
        self.openai_class: Any = None
        self.active_isolation_key: str | None = None
        self.active_root: Path | None = None
        self.active_state: dict[str, Any] | None = None
        self.graphiti: Any = None
        self.driver: Any = None
        self.lite: Any = None
        self.embedder: Any = None
        self.llm_observations: list[dict[str, int]] = []
        self.embedding_observations: list[dict[str, Any]] = []
        self._secret_values: tuple[str, ...] = ()

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """按 command 分派一个严格 JSON 请求。"""

        command = _required_text(request.get("command"), "command")
        payload = request.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if command == "initialize":
            return await self.initialize(payload)
        self._require_ready()
        if command == "ingest":
            return await self.ingest(payload)
        if command == "retrieve":
            return await self.retrieve(payload)
        if command == "session_memories":
            return await self.session_memories(payload)
        if command == "delete_conversation":
            return await self.delete_conversation(payload)
        if command == "shutdown":
            return await self.shutdown()
        raise ValueError(f"unknown Graphiti worker command: {command}")

    async def initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """加载 source-locked runtime 与本地模型，不调用外部 LLM。"""

        if self.state_root is not None:
            raise RuntimeError("Graphiti worker is already initialized")
        raw_config = payload.get("config")
        if not isinstance(raw_config, dict):
            raise ValueError("initialize config must be an object")
        self.config = self._validate_config(raw_config)
        state_root = Path(_required_text(payload.get("state_root"), "state_root"))
        state_root.mkdir(parents=True, exist_ok=True)
        self.state_root = state_root.resolve()
        api_key = os.environ.get("MEMORY_BENCHMARK_GRAPHITI_BUILD_API_KEY", "")
        if not api_key.strip():
            raise RuntimeError("Graphiti build API key is missing from worker environment")
        self._secret_values = tuple(
            value
            for value in (api_key, self.config.get("api_base_url"))
            if isinstance(value, str) and value
        )

        from redislite.async_falkordb_client import AsyncFalkorDB
        from graphiti_core.cross_encoder.client import CrossEncoderClient
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from graphiti_core.edges import EntityEdge
        from graphiti_core.embedder.client import EmbedderClient
        from graphiti_core.graphiti import Graphiti
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        from graphiti_core.nodes import EpisodeType
        from openai import AsyncOpenAI
        from sentence_transformers import SentenceTransformer

        self.graphiti_class = Graphiti
        self.episode_type = EpisodeType
        self.entity_edge_class = EntityEdge
        self.async_falkor_class = AsyncFalkorDB
        self.falkor_driver_class = FalkorDriver
        self.cross_encoder_client_class = CrossEncoderClient
        self.llm_client_class = OpenAIGenericClient
        self.llm_config_class = LLMConfig
        self.embedder_client_class = EmbedderClient
        self.sentence_transformer_class = SentenceTransformer
        self.openai_class = AsyncOpenAI
        self.embedder = self._build_embedder()
        return {
            "adapter_version": GRAPHITI_ADAPTER_VERSION,
            "product_surface": GRAPHITI_PRODUCT_SURFACE,
            "status": "ready",
            "telemetry_enabled": os.environ.get(
                "GRAPHITI_TELEMETRY_ENABLED", "true"
            ).lower()
            not in {"0", "false", "no", "off"},
        }

    @staticmethod
    def _validate_config(raw: dict[str, Any]) -> dict[str, Any]:
        """校验来自 adapter 的公开运行配置。"""

        expected = {
            "api_base_url",
            "api_max_retries",
            "api_provider",
            "api_timeout_seconds",
            "embedding_dimension",
            "embedding_model_path",
            "embedding_normalize",
            "llm_max_tokens",
            "llm_model",
            "llm_temperature",
            "max_coroutines",
            "query_limit",
            "structured_output_mode",
        }
        if set(raw) != expected:
            raise ValueError("Graphiti initialize config has an invalid shape")
        structured = _required_text(
            raw.get("structured_output_mode"), "structured_output_mode"
        )
        if structured not in {"json_object", "json_schema"}:
            raise ValueError("unsupported Graphiti structured_output_mode")
        dimension = _required_int(
            raw.get("embedding_dimension"), "embedding_dimension", minimum=1
        )
        if dimension != 384:
            raise ValueError("Graphiti worker requires embedding_dimension=384")
        normalize = _required_bool(
            raw.get("embedding_normalize"), "embedding_normalize"
        )
        if not normalize:
            raise ValueError("Graphiti worker requires normalized embeddings")
        query_limit = _required_int(raw.get("query_limit"), "query_limit", minimum=1)
        if query_limit != 20:
            raise ValueError("Graphiti worker requires query_limit=20")
        return {
            "api_base_url": _optional_text(raw.get("api_base_url"), "api_base_url"),
            "api_max_retries": _required_int(
                raw.get("api_max_retries"), "api_max_retries"
            ),
            "api_provider": _required_text(raw.get("api_provider"), "api_provider"),
            "api_timeout_seconds": _required_float(
                raw.get("api_timeout_seconds"), "api_timeout_seconds", positive=True
            ),
            "embedding_dimension": dimension,
            "embedding_model_path": _required_text(
                raw.get("embedding_model_path"), "embedding_model_path"
            ),
            "embedding_normalize": normalize,
            "llm_max_tokens": _required_int(
                raw.get("llm_max_tokens"), "llm_max_tokens", minimum=1
            ),
            "llm_model": _required_text(raw.get("llm_model"), "llm_model"),
            "llm_temperature": _required_float(
                raw.get("llm_temperature"),
                "llm_temperature",
                non_negative=True,
            ),
            "max_coroutines": _required_int(
                raw.get("max_coroutines"), "max_coroutines", minimum=1
            ),
            "query_limit": query_limit,
            "structured_output_mode": structured,
        }

    def _build_embedder(self) -> Any:
        """经公开 EmbedderClient extension point 构造受控 MiniLM。"""

        engine = self
        model = self.sentence_transformer_class(
            self.config["embedding_model_path"],
            local_files_only=True,
        )
        expected_dimension = self.config["embedding_dimension"]
        actual_dimension = model.get_sentence_embedding_dimension()
        if actual_dimension != expected_dimension:
            raise RuntimeError(
                "Graphiti embedding dimension mismatch: "
                f"{actual_dimension}!={expected_dimension}"
            )

        class _LocalEmbedder(self.embedder_client_class):
            """序列化调用本地 SentenceTransformer 并记录真实输入。"""

            def __init__(self) -> None:
                """保存本地模型并建立进程内串行锁。"""

                self.model = model
                self._lock = asyncio.Lock()

            async def create(self, input_data: Any) -> list[float]:
                """编码单条 Graphiti embedding 输入。"""

                texts = _normalize_embedding_input(input_data)
                vectors = await self._encode(texts)
                if len(vectors) != 1:
                    raise RuntimeError(
                        "Graphiti EmbedderClient.create expected exactly one vector"
                    )
                return vectors[0]

            async def create_batch(self, input_data_list: list[str]) -> list[list[float]]:
                """编码一批 Graphiti embedding 输入。"""

                texts = _normalize_embedding_input(input_data_list)
                return await self._encode(texts)

            async def _encode(self, texts: list[str]) -> list[list[float]]:
                """在串行临界区执行模型并记录 tokenizer 与延迟。"""

                started = perf_counter_ns()
                async with self._lock:
                    encoded = await asyncio.to_thread(
                        self.model.encode,
                        texts,
                        normalize_embeddings=engine.config["embedding_normalize"],
                        convert_to_numpy=True,
                    )
                vectors = encoded.tolist()
                if len(vectors) != len(texts) or any(
                    len(vector) != expected_dimension for vector in vectors
                ):
                    raise RuntimeError("Graphiti local embedder returned invalid shape")
                engine.embedding_observations.append(
                    {
                        "input_tokens": _embedding_token_count(self.model, texts),
                        "latency_ms": max(
                            0.0, (perf_counter_ns() - started) / 1_000_000
                        ),
                        "text_count": len(texts),
                    }
                )
                return vectors

        return _LocalEmbedder()

    def _build_llm_client(self) -> Any:
        """构造官方 OpenAIGenericClient 与纯观测 endpoint wrapper。"""

        api_key = os.environ["MEMORY_BENCHMARK_GRAPHITI_BUILD_API_KEY"]
        real = self.openai_class(
            api_key=api_key,
            base_url=self.config["api_base_url"],
            timeout=self.config["api_timeout_seconds"],
            max_retries=self.config["api_max_retries"],
        )
        observed = _ObservedOpenAI(self, real)
        config = self.llm_config_class(
            api_key=api_key,
            base_url=self.config["api_base_url"],
            model=self.config["llm_model"],
            small_model=self.config["llm_model"],
            temperature=self.config["llm_temperature"],
            max_tokens=self.config["llm_max_tokens"],
        )
        return self.llm_client_class(
            config=config,
            client=observed,
            max_tokens=self.config["llm_max_tokens"],
            structured_output_mode=self.config["structured_output_mode"],
        )

    def _build_unused_cross_encoder(self) -> Any:
        """构造满足 upstream nominal type、调用即失败的 rerank sentinel。"""

        base = self.cross_encoder_client_class

        class _RuntimeUnusedCrossEncoder(base):
            """默认 RRF 主轨不得触发的 cross-encoder 实例。"""

            async def rank(
                self,
                query: str,
                passages: list[str],
            ) -> list[tuple[str, float]]:
                """一旦 upstream search recipe 漂移即停止。"""

                del query, passages
                raise RuntimeError(
                    "Graphiti default RRF search unexpectedly used cross encoder"
                )

        return _RuntimeUnusedCrossEncoder()

    def _require_ready(self) -> None:
        """拒绝 initialize 前的业务命令。"""

        if self.state_root is None:
            raise RuntimeError("Graphiti worker is not initialized")

    def _conversation_root(self, isolation_key: str) -> Path:
        """返回 state_root 内的独占 conversation 目录。"""

        if self.state_root is None:
            raise RuntimeError("Graphiti worker is not initialized")
        return self.state_root / _state_dir_name(isolation_key)

    def _cleanup_paths(self, isolation_key: str) -> tuple[Path, Path, Path]:
        """返回 live root、外置 marker 与固定 tombstone 路径。"""

        root = self._conversation_root(isolation_key)
        marker = self.state_root / f".{root.name}.cleanup.json"
        tombstone = self.state_root / f".{root.name}.cleanup-tombstone"
        return root, marker, tombstone

    async def _activate(self, isolation_key: str) -> None:
        """切换到一个独占物理 DB，并验证 sidecar 与 product episode 一致。"""

        isolation_key = _required_text(isolation_key, "isolation_key")
        if self.active_isolation_key == isolation_key:
            return
        await self._close_active()
        root, cleanup_marker, tombstone = self._cleanup_paths(isolation_key)
        if cleanup_marker.exists() or tombstone.exists():
            raise RuntimeError(
                "Graphiti conversation has an incomplete physical cleanup; "
                "clean retry must finish before activation"
            )
        root.mkdir(parents=True, exist_ok=True)
        marker = root / GRAPHITI_CONVERSATION_MARKER
        if marker.exists():
            if marker.read_text(encoding="utf-8").strip() != isolation_key:
                raise RuntimeError("Graphiti conversation marker mismatch")
        else:
            marker.write_text(isolation_key + "\n", encoding="utf-8")
        state_path = root / "state.json"
        if state_path.exists():
            state = _validate_state(_read_json(state_path), isolation_key)
        else:
            state = _empty_state(isolation_key)
            _atomic_write_json(state_path, state)
        lite = self.async_falkor_class(dbfilename=str(root / "falkordb.db"))
        self.active_isolation_key = isolation_key
        self.active_root = root
        self.active_state = state
        self.lite = lite
        try:
            driver = self.falkor_driver_class(
                falkor_db=lite,
                database=GRAPHITI_DATABASE,
            )
            self.driver = driver
            graphiti = self.graphiti_class(
                graph_driver=driver,
                llm_client=self._build_llm_client(),
                embedder=self.embedder,
                cross_encoder=self._build_unused_cross_encoder(),
                store_raw_episode_content=True,
                max_coroutines=self.config["max_coroutines"],
            )
            self.graphiti = graphiti
            await graphiti.build_indices_and_constraints()
            product_episode_uuids = await self._product_episode_uuids()
            sidecar_episode_uuids = set(state["episode_to_turn"])
            if product_episode_uuids != sidecar_episode_uuids:
                raise RuntimeError(
                    "Graphiti product/sidecar episode mismatch; "
                    "physical clean retry required"
                )
        except BaseException as activation_error:
            try:
                await self._close_active()
            except BaseException as cleanup_error:
                raise RuntimeError(
                    "Graphiti activation failed and embedded runtime cleanup also failed: "
                    f"{type(cleanup_error).__name__}: {cleanup_error}"
                ) from activation_error
            raise

    async def _product_episode_uuids(self) -> set[str]:
        """读取当前物理 graph 的全部 Episodic UUID。"""

        records, _, _ = await self.driver.execute_query(
            "MATCH (e:Episodic) RETURN e.uuid AS uuid"
        )
        return {
            _required_text(record.get("uuid"), "product episode uuid")
            for record in records
        }

    def _begin_observations(self) -> None:
        """重置当前业务操作的逐调用 observation buffer。"""

        self.llm_observations = []
        self.embedding_observations = []

    def _finish_observations(
        self,
    ) -> tuple[list[dict[str, int]], list[dict[str, Any]]]:
        """复制并清空当前 operation observation。"""

        llm = [dict(item) for item in self.llm_observations]
        embedding = [dict(item) for item in self.embedding_observations]
        self._begin_observations()
        return llm, embedding

    async def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        """逐条 await product add_episode，并在成功后原子提交 sidecar。"""

        isolation_key = _required_text(payload.get("isolation_key"), "isolation_key")
        operation_id = _validate_hex_id(payload.get("operation_id"), "operation_id")
        input_digest = _validate_hex_id(payload.get("input_digest"), "input_digest")
        turn_id = _required_text(payload.get("turn_id"), "turn_id")
        session_id = _optional_text(payload.get("session_id"), "session_id")
        episode_body = _required_text(payload.get("episode_body"), "episode_body")
        reference_time_raw = _required_text(
            payload.get("reference_time"), "reference_time"
        )
        reference_time = datetime.fromisoformat(reference_time_raw)
        if reference_time.tzinfo is None:
            raise ValueError("reference_time must be timezone-aware")
        await self._activate(isolation_key)
        state = self.active_state
        root = self.active_root
        if state is None or root is None:
            raise RuntimeError("Graphiti active state is missing")
        existing = state["operations"].get(operation_id)
        if existing is not None:
            if existing["input_digest"] != input_digest:
                raise RuntimeError("Graphiti operation id was reused with different input")
            return {
                "edge_count": existing["edge_count"],
                "embedding_observations": [],
                "episode_uuid": existing["episode_uuid"],
                "llm_observations": [],
                "reused_operation": True,
            }
        self._begin_observations()
        result = await self.graphiti.add_episode(
            name=turn_id,
            episode_body=episode_body,
            source_description="memoryBenchmark canonical public turn",
            reference_time=reference_time,
            source=self.episode_type.message,
            group_id=GRAPHITI_DATABASE,
            update_communities=False,
        )
        episode_uuid = _required_text(result.episode.uuid, "episode_uuid")
        if episode_uuid in state["episode_to_turn"]:
            raise RuntimeError("Graphiti returned a duplicate product episode uuid")
        edge_uuids: list[str] = []
        for edge in result.edges:
            edge_uuid = _required_text(edge.uuid, "edge uuid")
            episodes = _validate_string_list(list(edge.episodes), "edge.episodes")
            if episode_uuid in episodes and edge_uuid not in edge_uuids:
                edge_uuids.append(edge_uuid)
        llm, embedding = self._finish_observations()
        state["episode_to_turn"][episode_uuid] = turn_id
        session = state["sessions"].setdefault(
            _session_key(session_id),
            {"edge_uuids": [], "episode_uuids": []},
        )
        session["episode_uuids"].append(episode_uuid)
        for edge_uuid in edge_uuids:
            if edge_uuid not in session["edge_uuids"]:
                session["edge_uuids"].append(edge_uuid)
        state["operations"][operation_id] = {
            "edge_count": len(edge_uuids),
            "episode_uuid": episode_uuid,
            "input_digest": input_digest,
        }
        _atomic_write_json(root / "state.json", state)
        return {
            "edge_count": len(edge_uuids),
            "embedding_observations": embedding,
            "episode_uuid": episode_uuid,
            "llm_observations": llm,
            "reused_operation": False,
        }

    async def retrieve(self, payload: dict[str, Any]) -> dict[str, Any]:
        """调用默认 edge RRF search，并把 product episode lineage 转成 turn ids。"""

        isolation_key = _required_text(payload.get("isolation_key"), "isolation_key")
        query = _required_text(payload.get("query"), "query")
        limit = _required_int(payload.get("limit"), "limit", minimum=1)
        if limit > self.config["query_limit"]:
            raise ValueError("Graphiti retrieve limit exceeds configured query_limit")
        await self._activate(isolation_key)
        state = self.active_state
        if state is None:
            raise RuntimeError("Graphiti active state is missing")
        self._begin_observations()
        started = perf_counter_ns()
        edges = await self.graphiti.search(
            query=query,
            group_ids=[GRAPHITI_DATABASE],
            num_results=limit,
        )
        latency_ms = max(0.0, (perf_counter_ns() - started) / 1_000_000)
        llm, embedding = self._finish_observations()
        if llm:
            raise RuntimeError("Graphiti product search unexpectedly called build LLM")
        items: list[dict[str, Any]] = []
        for edge in edges:
            source_turn_ids: list[str] = []
            for episode_uuid in _validate_string_list(
                list(edge.episodes), "edge.episodes"
            ):
                turn_id = state["episode_to_turn"].get(episode_uuid)
                if turn_id is None:
                    raise RuntimeError(
                        "Graphiti search returned an episode absent from sidecar lineage"
                    )
                if turn_id not in source_turn_ids:
                    source_turn_ids.append(turn_id)
            if not source_turn_ids:
                raise RuntimeError("Graphiti search edge has no source episodes")
            items.append(_edge_payload(edge, source_turn_ids))
        return {
            "embedding_observations": embedding,
            "items": items,
            "latency_ms": latency_ms,
        }

    async def session_memories(self, payload: dict[str, Any]) -> dict[str, Any]:
        """返回当前 session 首见且仍 active 的 fact edge 文本。"""

        isolation_key = _required_text(payload.get("isolation_key"), "isolation_key")
        session_id = _optional_text(payload.get("session_id"), "session_id")
        await self._activate(isolation_key)
        state = self.active_state
        if state is None:
            raise RuntimeError("Graphiti active state is missing")
        session = state["sessions"].get(_session_key(session_id))
        if session is None:
            return {"memories": []}
        edge_uuids = session["edge_uuids"]
        if not edge_uuids:
            return {"memories": []}
        edges = await self.entity_edge_class.get_by_uuids(self.driver, edge_uuids)
        edge_by_uuid = {edge.uuid: edge for edge in edges}
        if set(edge_by_uuid) != set(edge_uuids):
            raise RuntimeError("Graphiti session edge set is incomplete")
        session_episodes = set(session["episode_uuids"])
        memories: list[str] = []
        for edge_uuid in edge_uuids:
            edge = edge_by_uuid[edge_uuid]
            if edge.invalid_at is not None or edge.expired_at is not None:
                continue
            if not session_episodes.intersection(edge.episodes):
                continue
            fact = _required_text(edge.fact, "session edge fact")
            if fact not in memories:
                memories.append(fact)
        return {"memories": memories}

    async def delete_conversation(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按外置 marker + tombstone 可重入删除一个 conversation root。"""

        isolation_key = _required_text(payload.get("isolation_key"), "isolation_key")
        root, cleanup_marker, tombstone = self._cleanup_paths(isolation_key)
        if self.active_isolation_key == isolation_key:
            await self._close_active()
        if not cleanup_marker.exists() and not root.exists() and not tombstone.exists():
            return {"deleted": True}
        expected_cleanup = {
            "contract_version": GRAPHITI_CLEANUP_SCHEMA_VERSION,
            "isolation_key": isolation_key,
            "live_dir": root.name,
            "tombstone_dir": tombstone.name,
        }
        if cleanup_marker.exists():
            if _read_json(cleanup_marker) != expected_cleanup:
                raise RuntimeError("Graphiti external cleanup marker mismatch")
        else:
            if tombstone.exists():
                raise RuntimeError(
                    "Graphiti cleanup tombstone exists without its identity marker"
                )
            identity_marker = root / GRAPHITI_CONVERSATION_MARKER
            if (
                not identity_marker.is_file()
                or identity_marker.read_text(encoding="utf-8").strip()
                != isolation_key
            ):
                raise RuntimeError("Graphiti clean retry marker mismatch")
            _atomic_write_json(cleanup_marker, expected_cleanup)
        if root.exists() and tombstone.exists():
            raise RuntimeError("Graphiti cleanup has both live root and tombstone")
        if root.exists():
            identity_marker = root / GRAPHITI_CONVERSATION_MARKER
            if (
                not identity_marker.is_file()
                or identity_marker.read_text(encoding="utf-8").strip()
                != isolation_key
            ):
                raise RuntimeError("Graphiti live root identity changed during cleanup")
            os.replace(root, tombstone)
            _fsync_directory(self.state_root)
        if tombstone.exists():
            shutil.rmtree(tombstone)
        if root.exists() or tombstone.exists():
            raise RuntimeError("Graphiti conversation root survived physical deletion")
        cleanup_marker.unlink(missing_ok=False)
        _fsync_directory(self.state_root)
        return {"deleted": True}

    async def _close_active(self) -> None:
        """关闭 Graphiti driver，并补齐 falkordblite 0.10.0 embedded 进程清理。"""

        graphiti = self.graphiti
        driver = self.driver
        lite = self.lite
        if graphiti is None and driver is None and lite is None:
            self._reset_active()
            return
        async_client = getattr(lite, "client", None)
        sync_client = getattr(async_client, "_sync_client", None)
        if graphiti is not None:
            await graphiti.close()
        elif driver is not None:
            await driver.close()
        if sync_client is None:
            raise RuntimeError("FalkorDB Lite sync cleanup handle is unavailable")
        sync_client._async_managed = False
        sync_client._cleanup()
        async_client._async_managed = True
        is_running = getattr(sync_client, "_is_redis_running", None)
        if callable(is_running) and is_running():
            raise RuntimeError("FalkorDB Lite embedded process survived close")
        self._reset_active()

    def _reset_active(self) -> None:
        """仅在没有资源或 exact close 成功后丢弃当前对象引用。"""

        self.active_isolation_key = None
        self.active_root = None
        self.active_state = None
        self.graphiti = None
        self.driver = None
        self.lite = None

    async def shutdown(self) -> dict[str, Any]:
        """关闭当前 embedded runtime，并确认无活动对象。"""

        await self._close_active()
        return {"status": "closed"}

    def sanitize_error(self, message: str) -> str:
        """去除 secret/base URL 并限制错误文本长度。"""

        sanitized = message
        for secret in self._secret_values:
            sanitized = sanitized.replace(secret, "<redacted>")
        return sanitized[:2000]


def _normalize_embedding_input(input_data: Any) -> list[str]:
    """把 Graphiti EmbedderClient 输入规范成非空字符串列表。"""

    if isinstance(input_data, str):
        texts = [input_data]
    elif isinstance(input_data, list) and all(isinstance(item, str) for item in input_data):
        texts = list(input_data)
    else:
        raise TypeError("Graphiti local embedder only accepts string or list[str]")
    if not texts or any(not text.strip() for text in texts):
        raise ValueError("Graphiti local embedder input must be non-blank")
    return texts


def _embedding_token_count(model: Any, texts: list[str]) -> int:
    """按模型 tokenizer 与真实 truncation 计算本地 embedding 输入 token。"""

    encoded = model.tokenizer(
        texts,
        add_special_tokens=True,
        max_length=model.max_seq_length,
        truncation=True,
        return_attention_mask=True,
    )
    masks = encoded.get("attention_mask")
    if not isinstance(masks, list):
        raise RuntimeError("Graphiti embedding tokenizer omitted attention_mask")
    return sum(sum(int(value) for value in mask) for mask in masks)


def _edge_payload(edge: Any, source_turn_ids: list[str]) -> dict[str, Any]:
    """把 product EntityEdge 转成严格公开 worker payload。"""

    return {
        "expired_at": _iso_or_none(edge.expired_at),
        "fact": _required_text(edge.fact, "edge.fact"),
        "invalid_at": _iso_or_none(edge.invalid_at),
        "reference_time": _iso_or_none(edge.reference_time),
        "source_turn_ids": source_turn_ids,
        "uuid": _required_text(edge.uuid, "edge.uuid"),
        "valid_at": _iso_or_none(edge.valid_at),
    }


def _prepare_protocol_stream() -> Any:
    """保留原 stdout 给协议，把第三方 stdout 噪声重定向到 stderr。"""

    protocol_stream = os.fdopen(os.dup(sys.stdout.fileno()), "w", buffering=1)
    sys.stdout.flush()
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    return protocol_stream


def main() -> int:
    """运行同步 stdin loop，并为每条请求执行一个 async command。"""

    protocol = _prepare_protocol_stream()
    engine = _WorkerEngine()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for raw in sys.stdin:
            request_id: Any = None
            try:
                request = json.loads(raw)
                if not isinstance(request, dict):
                    raise ValueError("request must be an object")
                request_id = request.get("request_id")
                if type(request_id) is not int or request_id < 1:
                    raise ValueError("request_id must be a positive integer")
                result = loop.run_until_complete(engine.dispatch(request))
                response = {"request_id": request_id, "ok": True, "result": result}
            except BaseException as exc:
                response = {
                    "request_id": request_id,
                    "ok": False,
                    "error_type": type(exc).__name__,
                    "error": engine.sanitize_error(str(exc)),
                }
                traceback.print_exc(file=sys.stderr)
            protocol.write(json.dumps(response, ensure_ascii=False) + "\n")
            protocol.flush()
            if (
                response.get("ok") is True
                and isinstance(response.get("result"), dict)
                and response["result"].get("status") == "closed"
            ):
                break
    finally:
        if any(
            resource is not None
            for resource in (engine.graphiti, engine.driver, engine.lite)
        ):
            try:
                loop.run_until_complete(engine._close_active())
            except BaseException:
                traceback.print_exc(file=sys.stderr)
        loop.close()
        protocol.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
