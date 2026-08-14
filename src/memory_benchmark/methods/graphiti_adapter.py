"""Graphiti OSS v0.29.3 的 provider v3 adapter。

主轨在独立 Python 3.12 worker 中调用公开 ``Graphiti.add_episode`` 与
``Graphiti.search``，使用每个 conversation 独占的 FalkorDB Lite 文件。adapter
只负责 canonical turn 渲染、source-time 校验、公开 lineage/readout、效率观测与
精确生命周期；不直接写 graph node/edge，也不启动 Graphiti HTTP server。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import selectors
import subprocess
import threading
from time import perf_counter_ns
from typing import Any, Protocol

from memory_benchmark.config import OpenAISettings, PathSettings, load_path_settings
from memory_benchmark.core import ConfigurationError, ImageRef, Turn
from memory_benchmark.core.provider_protocol import (
    EvidenceAssertion,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalEvidence,
    RetrievalQuery,
    RetrievalResult,
    RetrievedItem,
    SessionMemoryReport,
    SessionRef,
    TurnEvent,
)
from memory_benchmark.methods.image_text import turn_text_with_images
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
)


GRAPHITI_ADAPTER_VERSION = "graphiti-oss-product-v1"
GRAPHITI_METHOD_DIRECTORY = "graphiti"
GRAPHITI_UPSTREAM_URL = "https://github.com/getzep/graphiti.git"
GRAPHITI_VERSION = "v0.29.3"
GRAPHITI_COMMIT = "021d3a57d511f21b10adaf7fa923bd5c1fce5e9d"
GRAPHITI_PRODUCT_SURFACE = "Graphiti.add_episode+Graphiti.search"
GRAPHITI_IMPLEMENTATION_IDENTITY = "direct-core-falkordblite"
GRAPHITI_LLM_MODEL_ID = "graphiti-build-llm"
GRAPHITI_EMBEDDING_MODEL_ID = "graphiti-embedding"
GRAPHITI_EMPTY_MEMORY_SENTINEL = "(No Graphiti facts retrieved)"
GRAPHITI_WORKER_LOGICAL_PATH = "src/memory_benchmark/methods/graphiti_worker.py"
GRAPHITI_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/graphiti_adapter.py"
GRAPHITI_BOOTSTRAP_LOGICAL_PATH = "scripts/bootstrap_graphiti_runtime.sh"
GRAPHITI_SOURCE_MODE = "vendored-graphiti-plus-isolated-product-wrapper"
GRAPHITI_BUILD_LLM_RESPONSE_CONTRACT = (
    "provider-aware-v1:"
    "opencodego=chat_completions+json_object+thinking_disabled;"
    "primary=chat_completions+json_schema;exact_usage_required"
)
GRAPHITI_SOURCE_FILES = (
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "graphiti_core/graphiti.py",
    "graphiti_core/edges.py",
    "graphiti_core/nodes.py",
    "graphiti_core/driver/falkordb_driver.py",
    "graphiti_core/embedder/client.py",
    "graphiti_core/llm_client/openai_generic_client.py",
    "graphiti_core/search/search_config_recipes.py",
    "tests/evals/eval_e2e_graph_building.py",
)
_ALLOWED_ROLES = frozenset({"user", "assistant"})
_LOCOMO_TIMESTAMP_PATTERN = re.compile(
    r"^\s*(?P<hour>\d{1,2}):(?P<minute>\d{2})\s*"
    r"(?P<period>am|pm)\s+on\s+"
    r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]+),\s*"
    r"(?P<year>\d{4})\s*$",
    re.IGNORECASE,
)
_MONTHS = {
    name.lower(): index
    for index, name in enumerate(
        (
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ),
        start=1,
    )
}
_WORKER_PASSTHROUGH_ENV_NAMES = frozenset(
    {
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LC_ALL",
        "NO_PROXY",
        "PATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "TMPDIR",
        "TZ",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)


@dataclass(frozen=True)
class GraphitiConfig:
    """Graphiti OSS 主 profile 的强类型配置。"""

    llm_model: str
    structured_output_mode: str
    llm_temperature: float
    llm_max_tokens: int
    embedding_model_path: str
    embedding_dimension: int
    embedding_normalize: bool
    query_limit: int
    max_coroutines: int
    worker_request_timeout_seconds: float
    max_workers: int
    profile_name: str = "product-falkordblite-v1"

    def __post_init__(self) -> None:
        """拒绝未声明的模型、embedding、search 与生命周期漂移。"""

        for field_name in ("llm_model", "embedding_model_path", "profile_name"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"Graphiti {field_name} is required")
        if self.structured_output_mode not in {"json_object", "json_schema"}:
            raise ConfigurationError(
                "Graphiti structured_output_mode must be json_object or json_schema"
            )
        if (
            isinstance(self.llm_temperature, bool)
            or not isinstance(self.llm_temperature, (int, float))
            or not math.isfinite(float(self.llm_temperature))
            or float(self.llm_temperature) < 0
        ):
            raise ConfigurationError(
                "Graphiti llm_temperature must be finite and non-negative"
            )
        for field_name in (
            "llm_max_tokens",
            "embedding_dimension",
            "query_limit",
            "max_coroutines",
            "max_workers",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 1:
                raise ConfigurationError(
                    f"Graphiti {field_name} must be a positive integer"
                )
        if self.embedding_dimension != 384:
            raise ConfigurationError(
                "Graphiti controlled MiniLM profile requires embedding_dimension=384"
            )
        if self.embedding_normalize is not True:
            raise ConfigurationError(
                "Graphiti controlled MiniLM profile requires normalized embeddings"
            )
        if self.query_limit != 20:
            raise ConfigurationError(
                "Graphiti five-benchmark profile requires query_limit=20"
            )
        if (
            isinstance(self.worker_request_timeout_seconds, bool)
            or not isinstance(self.worker_request_timeout_seconds, (int, float))
            or not math.isfinite(float(self.worker_request_timeout_seconds))
            or self.worker_request_timeout_seconds <= 0
        ):
            raise ConfigurationError(
                "Graphiti worker_request_timeout_seconds must be positive and finite"
            )

    def validate_required_local_resources(self, path_settings: PathSettings) -> None:
        """校验 vendored runtime 与受控本地 embedding 均存在。"""

        root = path_settings.resolve_third_party_method_path(
            GRAPHITI_METHOD_DIRECTORY
        )
        python = root / ".venv" / "bin" / "python"
        if not python.is_file():
            raise ConfigurationError(
                "Graphiti isolated runtime is missing. Run "
                "scripts/bootstrap_graphiti_runtime.sh first."
            )
        model = _resolve_project_relative_path(
            self.embedding_model_path,
            path_settings.project_root,
        )
        if model is None or not model.is_dir():
            raise ConfigurationError(
                "Graphiti local embedding model is missing: "
                f"{self.embedding_model_path}"
            )

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 API key/base URL/绝对状态路径的 build 身份。"""

        return {
            **asdict(self),
            "adapter_version": GRAPHITI_ADAPTER_VERSION,
            "implementation_identity": GRAPHITI_IMPLEMENTATION_IDENTITY,
            "product_surface": GRAPHITI_PRODUCT_SURFACE,
            "consume_granularity": "turn",
            "storage": "falkordblite-per-conversation",
            "search_recipe": "edge-bm25+cosine+rrf",
            "embedding_provider": "sentence-transformers-local",
            "embedding_distance": "falkordb-cosine",
            "cross_encoder": None,
            "build_llm_response_contract": GRAPHITI_BUILD_LLM_RESPONSE_CONTRACT,
            "telemetry": "disabled",
        }


class GraphitiRuntimeProtocol(Protocol):
    """adapter 使用的最窄 Graphiti worker 协议。"""

    def ensure_started(self) -> None:
        """启动 worker，并完成不调用 LLM 的握手。"""

    def ingest(
        self,
        *,
        isolation_key: str,
        operation_id: str,
        input_digest: str,
        turn_id: str,
        session_id: str | None,
        episode_body: str,
        reference_time: str,
    ) -> dict[str, Any]:
        """逐 turn 调用 product add_episode。"""

    def retrieve(
        self,
        *,
        isolation_key: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        """调用 product search。"""

    def session_memories(
        self,
        *,
        isolation_key: str,
        session_id: str | None,
    ) -> dict[str, Any]:
        """读取当前 session 的 active fact delta。"""

    def delete_conversation(self, *, isolation_key: str) -> dict[str, Any]:
        """物理删除一个精确 conversation root。"""

    def close(self) -> None:
        """关闭独占 worker。"""


RuntimeFactory = Callable[..., GraphitiRuntimeProtocol]


class GraphitiRuntime:
    """一个 provider 独占的 Graphiti JSON-lines worker。"""

    def __init__(
        self,
        *,
        config: GraphitiConfig,
        openai_settings: OpenAISettings,
        path_settings: PathSettings,
        storage_root: Path,
    ) -> None:
        """保存启动依赖；第三方 import 与模型加载保持 lazy。"""

        self.config = config
        self.openai_settings = openai_settings
        self.path_settings = path_settings
        self.storage_root = storage_root
        self._worker: subprocess.Popen[str] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=80)
        self._request_lock = threading.Lock()
        self._request_sequence = 0
        self._closed = False
        self._close_failed = False
        self._close_error: BaseException | None = None

    def _graphiti_root(self) -> Path:
        """返回 source-locked Graphiti 根目录。"""

        return self.path_settings.resolve_third_party_method_path(
            GRAPHITI_METHOD_DIRECTORY
        )

    def _worker_python(self) -> Path:
        """返回独立 runtime Python，不允许回落主框架解释器。"""

        python = self._graphiti_root() / ".venv" / "bin" / "python"
        if not python.is_file():
            raise ConfigurationError(
                "Graphiti isolated runtime is missing. Run "
                "scripts/bootstrap_graphiti_runtime.sh first."
            )
        return python

    def _embedding_model_path(self) -> Path:
        """解析并限制本地 embedding 路径不逃逸项目根。"""

        path = _resolve_project_relative_path(
            self.config.embedding_model_path,
            self.path_settings.project_root,
        )
        if path is None or not path.is_dir():
            raise ConfigurationError(
                "Graphiti embedding model path is missing: "
                f"{self.config.embedding_model_path}"
            )
        return path

    def _worker_environment(self) -> dict[str, str]:
        """只传必要系统变量和 build API key，并强制关闭 upstream telemetry。"""

        environment = {
            name: value
            for name, value in os.environ.items()
            if name in _WORKER_PASSTHROUGH_ENV_NAMES
        }
        environment.update(
            {
                "GRAPHITI_TELEMETRY_ENABLED": "false",
                "HF_HUB_OFFLINE": "1",
                "MEMORY_BENCHMARK_GRAPHITI_BUILD_API_KEY": (
                    self.openai_settings.api_key
                ),
                "PYTHONUNBUFFERED": "1",
                "TOKENIZERS_PARALLELISM": "false",
                "TRANSFORMERS_OFFLINE": "1",
            }
        )
        return environment

    def ensure_started(self) -> None:
        """启动 worker，并完成不触发 build API 的 initialize。"""

        if self._closed:
            raise ConfigurationError("Graphiti runtime is already closed")
        if self._worker is not None:
            if self._worker.poll() is None:
                return
            raise ConfigurationError(self._worker_failure_text("exited"))
        worker_path = self.path_settings.project_root / GRAPHITI_WORKER_LOGICAL_PATH
        if not worker_path.is_file():
            raise ConfigurationError(f"Graphiti worker file missing: {worker_path}")
        state_root = (self.storage_root / "graphiti_state").resolve()
        state_root.mkdir(parents=True, exist_ok=True)
        self._worker = subprocess.Popen(
            [str(self._worker_python()), str(worker_path)],
            cwd=self._graphiti_root(),
            env=self._worker_environment(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._stderr_thread = threading.Thread(
            target=self._drain_worker_stderr,
            name=f"graphiti-worker-{id(self)}-stderr",
            daemon=True,
        )
        self._stderr_thread.start()
        try:
            result = self._request(
                "initialize",
                {
                    "config": {
                        "api_base_url": self.openai_settings.base_url,
                        "api_max_retries": self.openai_settings.max_retries,
                        "api_provider": self.openai_settings.provider,
                        "api_timeout_seconds": self.openai_settings.timeout_seconds,
                        "embedding_dimension": self.config.embedding_dimension,
                        "embedding_model_path": str(self._embedding_model_path()),
                        "embedding_normalize": self.config.embedding_normalize,
                        "llm_max_tokens": self.config.llm_max_tokens,
                        "llm_model": self.config.llm_model,
                        "llm_temperature": self.config.llm_temperature,
                        "max_coroutines": self.config.max_coroutines,
                        "query_limit": self.config.query_limit,
                        "structured_output_mode": self.config.structured_output_mode,
                    },
                    "state_root": str(state_root),
                },
            )
        except BaseException:
            self._terminate_worker()
            raise
        if (
            result.get("status") != "ready"
            or result.get("adapter_version") != GRAPHITI_ADAPTER_VERSION
            or result.get("product_surface") != GRAPHITI_PRODUCT_SURFACE
            or result.get("telemetry_enabled") is not False
        ):
            self._terminate_worker()
            raise ConfigurationError("Graphiti worker initialize identity mismatch")

    def _drain_worker_stderr(self) -> None:
        """持续排空并脱敏保存 stderr 尾部。"""

        worker = self._worker
        if worker is None or worker.stderr is None:
            return
        for line in worker.stderr:
            self._stderr_tail.append(
                line.rstrip().replace(self.openai_settings.api_key, "<redacted>")
            )

    def _request(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送串行 JSON-lines 请求并强校验响应身份。"""

        worker = self._worker
        if worker is None or worker.stdin is None or worker.stdout is None:
            raise ConfigurationError("Graphiti worker is not running")
        with self._request_lock:
            if worker.poll() is not None:
                raise ConfigurationError(self._worker_failure_text("exited"))
            self._request_sequence += 1
            request_id = self._request_sequence
            worker.stdin.write(
                json.dumps(
                    {
                        "request_id": request_id,
                        "command": command,
                        "payload": payload,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            worker.stdin.flush()
            selector = selectors.DefaultSelector()
            selector.register(worker.stdout, selectors.EVENT_READ)
            try:
                ready = selector.select(self.config.worker_request_timeout_seconds)
            finally:
                selector.close()
            if not ready:
                self._terminate_worker()
                raise ConfigurationError(
                    f"Graphiti worker command timed out: {command}; "
                    "failed-conversation physical cleanup is required before retry"
                )
            raw = worker.stdout.readline()
            if not raw:
                raise ConfigurationError(self._worker_failure_text("closed stdout"))
            try:
                response = json.loads(raw)
            except json.JSONDecodeError as exc:
                self._terminate_worker()
                raise ConfigurationError(
                    f"Graphiti worker protocol was polluted: {raw[:200]!r}"
                ) from exc
            if not isinstance(response, dict) or response.get("request_id") != request_id:
                self._terminate_worker()
                raise ConfigurationError("Graphiti worker response identity mismatch")
            if response.get("ok") is not True:
                raise ConfigurationError(
                    "Graphiti worker "
                    f"{command} failed [{response.get('error_type')}]: "
                    f"{response.get('error')}"
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise ConfigurationError("Graphiti worker result must be an object")
            return result

    def _worker_failure_text(self, state: str) -> str:
        """构造不含 secret 的 worker 失败摘要。"""

        return f"Graphiti worker {state}; stderr tail: " + "\n".join(
            self._stderr_tail
        )[-3000:]

    def ingest(
        self,
        *,
        isolation_key: str,
        operation_id: str,
        input_digest: str,
        turn_id: str,
        session_id: str | None,
        episode_body: str,
        reference_time: str,
    ) -> dict[str, Any]:
        """经 worker 执行一个 product episode。"""

        self.ensure_started()
        return self._request(
            "ingest",
            {
                "episode_body": episode_body,
                "input_digest": input_digest,
                "isolation_key": isolation_key,
                "operation_id": operation_id,
                "reference_time": reference_time,
                "session_id": session_id,
                "turn_id": turn_id,
            },
        )

    def retrieve(
        self,
        *,
        isolation_key: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        """经 worker 执行 product search。"""

        self.ensure_started()
        return self._request(
            "retrieve",
            {"isolation_key": isolation_key, "query": query, "limit": limit},
        )

    def session_memories(
        self,
        *,
        isolation_key: str,
        session_id: str | None,
    ) -> dict[str, Any]:
        """经 worker 读取当前 session 的 active facts。"""

        self.ensure_started()
        return self._request(
            "session_memories",
            {"isolation_key": isolation_key, "session_id": session_id},
        )

    def delete_conversation(self, *, isolation_key: str) -> dict[str, Any]:
        """经 worker 删除独占 conversation root。"""

        self.ensure_started()
        return self._request(
            "delete_conversation",
            {"isolation_key": isolation_key},
        )

    def close(self) -> None:
        """关闭 worker；失败后永久拒绝复用，绝不冒充完整关闭。"""

        if self._closed:
            return
        if self._close_failed:
            raise ConfigurationError(
                "Graphiti runtime is permanently unusable after a prior "
                "shutdown failure"
            ) from self._close_error
        worker = self._worker
        if worker is not None:
            try:
                if worker.poll() is not None:
                    raise ConfigurationError(
                        "Graphiti worker exited before confirming product shutdown"
                    )
                result = self._request("shutdown", {})
                if result.get("status") != "closed":
                    raise ConfigurationError(
                        "Graphiti worker did not confirm shutdown"
                    )
                worker.wait(timeout=10)
            except BaseException as exc:
                self._close_failed = True
                self._close_error = exc
                try:
                    self._terminate_worker()
                except BaseException as cleanup_error:
                    raise ConfigurationError(
                        "Graphiti shutdown failed and worker termination also failed"
                    ) from cleanup_error
                raise
        self._terminate_worker()
        self._closed = True

    def _terminate_worker(self) -> None:
        """尽力终止 worker，不冒充 Graphiti lifecycle 成功。"""

        worker = self._worker
        if worker is None:
            return
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        for stream in (worker.stdin, worker.stdout, worker.stderr):
            if stream is not None and not stream.closed:
                stream.close()


class GraphitiOSS(MemoryProvider):
    """Graphiti OSS 的 turn-level 产品 provider。"""

    consume_granularity = "turn"
    provenance_granularity = "turn"

    def __init__(
        self,
        *,
        config: GraphitiConfig,
        path_settings: PathSettings,
        storage_root: Path,
        openai_settings: OpenAISettings,
        benchmark_name: str | None,
        session_memory_report: bool = False,
        efficiency_collector: EfficiencyCollector | None = None,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        """保存依赖，强校验 runtime/model 身份并保持 worker lazy。"""

        if config.llm_model != openai_settings.model:
            raise ConfigurationError(
                "Graphiti config llm_model must match selected API runtime model"
            )
        if benchmark_name not in {
            "locomo",
            "longmemeval",
            "membench",
            "beam",
            "halumem",
        }:
            raise ConfigurationError(
                "Graphiti benchmark_name must be one of the five Phase-1 benchmarks"
            )
        config.validate_required_local_resources(path_settings)
        self.config = config
        self.path_settings = path_settings
        self.storage_root = storage_root
        self.openai_settings = openai_settings
        self.benchmark_name = benchmark_name
        self.session_memory_report = session_memory_report
        self.efficiency_collector = efficiency_collector
        self._runtime_factory = runtime_factory or GraphitiRuntime
        self._runtime: GraphitiRuntimeProtocol | None = None
        self._observed_operation_ids: set[str] = set()
        self._cleaned = False

    def prepare(self, run_context: Any) -> None:
        """在首个 ingest 前启动独立 worker；initialize 不调用 build API。"""

        del run_context
        self._require_runtime().ensure_started()

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """把一个 canonical turn 逐字可审计地写入一个 product episode。"""

        if not isinstance(unit, TurnEvent):
            raise ConfigurationError("Graphiti provider only accepts TurnEvent")
        episode_body = self._episode_body(unit)
        reference_time = _reference_time(unit.timestamp)
        input_digest = _input_digest(
            isolation_key=unit.isolation_key,
            turn_id=unit.turn_id,
            session_id=unit.session_id,
            episode_body=episode_body,
            reference_time=reference_time,
        )
        operation_id = hashlib.sha256(
            f"{GRAPHITI_ADAPTER_VERSION}|{input_digest}".encode("utf-8")
        ).hexdigest()
        result = self._require_runtime().ingest(
            isolation_key=unit.isolation_key,
            operation_id=operation_id,
            input_digest=input_digest,
            turn_id=unit.turn_id,
            session_id=unit.session_id,
            episode_body=episode_body,
            reference_time=reference_time,
        )
        self._record_build_observations(operation_id, result)
        return IngestResult(
            metadata={
                "method": "graphiti",
                "operation_id": operation_id,
                "operation_reused": _required_bool(
                    result.get("reused_operation"), "reused_operation"
                ),
                "product_episode_uuid": _required_text(
                    result.get("episode_uuid"), "episode_uuid"
                ),
                "resolved_edge_count": _required_non_negative_int(
                    result.get("edge_count"), "edge_count"
                ),
                "source_turn_id": unit.turn_id,
            }
        )

    def _episode_body(self, event: TurnEvent) -> str:
        """按 benchmark 稳定 role/speaker/caption 规则生成 message episode body。"""

        rendered = _render_event_content(event)
        if not rendered.strip():
            raise ConfigurationError(
                f"Graphiti turn has no visible content: {event.turn_id}"
            )
        if self.benchmark_name == "locomo":
            roles = _locomo_speaker_roles(event)
            speaker = event.speaker_name or event.role
            role = roles.get(speaker)
            if role is None:
                raise ConfigurationError(
                    f"Graphiti LoCoMo speaker is not declared: {speaker!r}"
                )
            return f"{speaker} ({role}): {rendered}"
        if event.role not in _ALLOWED_ROLES:
            raise ConfigurationError(
                "Graphiti only accepts canonical user/assistant roles outside "
                f"LoCoMo: {event.role!r}"
            )
        return f"{event.role}: {rendered}"

    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """HaluMem 仅报告当前 session 仍 active 的 product fact edges。"""

        if not self.session_memory_report:
            return None
        result = self._require_runtime().session_memories(
            isolation_key=ref.isolation_key,
            session_id=ref.session_id,
        )
        memories = _required_text_list(result.get("memories"), "memories")
        return SessionMemoryReport(
            session_ref=ref,
            memories=memories,
            metadata={
                "method": "graphiti",
                "memory_scope": "active_current_session_fact_edges",
                "edge_count": len(memories),
            },
        )

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """调用默认 Graphiti edge hybrid search，并保留 product rank。"""

        if query.top_k > self.config.query_limit:
            raise ConfigurationError(
                "Graphiti query top_k exceeds configured query_limit: "
                f"{query.top_k}>{self.config.query_limit}"
            )
        started_ns = perf_counter_ns()
        result = self._require_runtime().retrieve(
            isolation_key=query.isolation_key,
            query=query.query_text,
            limit=query.top_k,
        )
        total_latency_ms = max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)
        embeddings = _validated_observations(
            result.get("embedding_observations"), "embedding"
        )
        if self.efficiency_collector is not None:
            with self.efficiency_collector.operation_stage(EfficiencyStage.RETRIEVAL):
                for observation in embeddings:
                    _record_embedding_observation(
                        self.efficiency_collector,
                        observation,
                    )
            self.efficiency_collector.record_retrieval_result_if_question_scope(
                latency_ms=total_latency_ms,
                injected_memory_context_tokens=None,
            )
        raw_items = result.get("items")
        if not isinstance(raw_items, list):
            raise ConfigurationError("Graphiti retrieve result has no items list")
        items = tuple(
            _retrieved_item(rank, raw)
            for rank, raw in enumerate(raw_items, start=1)
        )
        formatted = _format_graphiti_items(items)
        return RetrievalResult(
            formatted_memory=formatted or GRAPHITI_EMPTY_MEMORY_SENTINEL,
            items=items,
            metadata={
                "method": "graphiti",
                "prompt_track": "unified",
                "product_surface": GRAPHITI_PRODUCT_SURFACE,
                "query_consumed_by_method": True,
                "stable_product_ranking": True,
                "provenance_granularity": "turn",
                "search_recipe": "edge-bm25+cosine+rrf",
                "worker_search_latency_ms": _required_non_negative_number(
                    result.get("latency_ms"), "latency_ms"
                ),
            },
            evidence=_graphiti_retrieval_evidence(),
        )

    def _record_build_observations(
        self,
        operation_id: str,
        result: dict[str, Any],
    ) -> None:
        """把成功 product operation 的 API/local observation 写入当前 scope 一次。"""

        llm = _validated_observations(result.get("llm_observations"), "llm")
        embeddings = _validated_observations(
            result.get("embedding_observations"), "embedding"
        )
        if operation_id in self._observed_operation_ids:
            return
        if self.efficiency_collector is not None:
            for observation in llm:
                self.efficiency_collector.record_llm_call(
                    model_id=GRAPHITI_LLM_MODEL_ID,
                    input_tokens=_required_non_negative_int(
                        observation.get("input_tokens"), "input_tokens"
                    ),
                    output_tokens=_required_non_negative_int(
                        observation.get("output_tokens"), "output_tokens"
                    ),
                    token_measurement_source=MeasurementSource.API_USAGE,
                )
            for observation in embeddings:
                _record_embedding_observation(
                    self.efficiency_collector,
                    observation,
                )
        self._observed_operation_ids.add(operation_id)

    def cleanup(self) -> None:
        """关闭独占 worker；成功后才提交 provider cleaned 状态。"""

        if self._cleaned:
            return
        runtime = self._runtime
        if runtime is None:
            self._cleaned = True
            return
        runtime.close()
        self._runtime = None
        self._cleaned = True

    def _require_runtime(self) -> GraphitiRuntimeProtocol:
        """懒构造并复用当前 provider 的唯一 runtime。"""

        if self._cleaned:
            raise ConfigurationError("Graphiti provider is already cleaned")
        if self._runtime is None:
            self._runtime = self._runtime_factory(
                config=self.config,
                openai_settings=self.openai_settings,
                path_settings=self.path_settings,
                storage_root=self.storage_root,
            )
        return self._runtime


def validate_graphiti_variant(benchmark_name: str, variant: str) -> None:
    """在 runtime/API 前拒绝 Graphiti 无法诚实表达的 benchmark variant。"""

    if benchmark_name == "membench" and variant == "100k":
        raise ConfigurationError(
            "Graphiti does not support MemBench variant '100k': source turns may "
            "lack timestamps while Graphiti add_episode requires reference_time; "
            "question, sibling and wall-clock timestamp fabrication is forbidden"
        )


def clean_graphiti_conversation_state(
    *,
    provider: GraphitiOSS,
    isolation_key: str,
) -> None:
    """物理删除 failed-ingest conversation 的独占 Graphiti root。"""

    result = provider._require_runtime().delete_conversation(
        isolation_key=isolation_key
    )
    if result.get("deleted") is not True:
        raise ConfigurationError(
            "Graphiti worker did not confirm physical conversation deletion"
        )


def _render_event_content(event: TurnEvent) -> str:
    """从 original content + public captions 重建唯一可见文本。"""

    turn_metadata = event.metadata.get("turn_metadata")
    if not isinstance(turn_metadata, dict):
        turn_metadata = {}
    original = event.metadata.get("original_content")
    content = original if isinstance(original, str) else event.content
    original_turn_time = event.metadata.get("original_turn_time")
    turn = Turn(
        turn_id=event.turn_id,
        speaker=event.speaker_name or event.role,
        normalized_role=event.role if event.role in _ALLOWED_ROLES else None,
        content=content,
        turn_time=(
            original_turn_time if isinstance(original_turn_time, str) else None
        ),
        metadata=dict(turn_metadata),
        images=_images_from_event(event),
    )
    return turn_text_with_images(turn)


def _images_from_event(event: TurnEvent) -> list[ImageRef]:
    """恢复公开 image caption，不向 Graphiti 暴露 locator/query。"""

    raw_images = event.metadata.get("turn_images")
    if not isinstance(raw_images, list):
        return []
    return [
        ImageRef(
            image_id=raw.get("image_id"),
            path=raw.get("path"),
            caption=raw.get("caption"),
            metadata={},
        )
        for raw in raw_images
        if isinstance(raw, dict)
    ]


def _locomo_speaker_roles(event: TurnEvent) -> dict[str, str]:
    """固定读取 LoCoMo speaker_a→user、speaker_b→assistant 声明。"""

    metadata = event.metadata.get("conversation_metadata")
    if not isinstance(metadata, dict):
        raise ConfigurationError(
            "Graphiti LoCoMo event is missing conversation_metadata"
        )
    speaker_a = metadata.get("speaker_a")
    speaker_b = metadata.get("speaker_b")
    if not isinstance(speaker_a, str) or not speaker_a.strip():
        raise ConfigurationError("Graphiti LoCoMo metadata is missing speaker_a")
    if not isinstance(speaker_b, str) or not speaker_b.strip():
        raise ConfigurationError("Graphiti LoCoMo metadata is missing speaker_b")
    if speaker_a == speaker_b:
        raise ConfigurationError("Graphiti LoCoMo speakers must be distinct")
    return {speaker_a: "user", speaker_b: "assistant"}


def _reference_time(raw: str | None) -> str:
    """把 source time 转为 UTC ISO；缺失或不可解析都 fail-fast。"""

    if raw is None or not raw.strip():
        raise ConfigurationError(
            "Graphiti requires source reference_time; timestamp fabrication is forbidden"
        )
    value = raw.strip()
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        pass
    if parsed is None:
        for timestamp_format in (
            "%Y/%m/%d (%a) %H:%M",
            "%B-%d-%Y",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        ):
            try:
                parsed = datetime.strptime(value, timestamp_format)
                break
            except ValueError:
                continue
    if parsed is None:
        match = _LOCOMO_TIMESTAMP_PATTERN.match(value)
        if match is not None:
            month = _MONTHS.get(match.group("month").lower())
            if month is not None:
                hour = int(match.group("hour"))
                minute = int(match.group("minute"))
                if 1 <= hour <= 12 and 0 <= minute <= 59:
                    if match.group("period").lower() == "pm" and hour != 12:
                        hour += 12
                    elif match.group("period").lower() == "am" and hour == 12:
                        hour = 0
                    try:
                        parsed = datetime(
                            int(match.group("year")),
                            month,
                            int(match.group("day")),
                            hour,
                            minute,
                        )
                    except ValueError:
                        parsed = None
    if parsed is None:
        raise ConfigurationError(
            f"Graphiti cannot parse source reference_time: {value!r}"
        )
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat(timespec="seconds")


def _input_digest(
    *,
    isolation_key: str,
    turn_id: str,
    session_id: str | None,
    episode_body: str,
    reference_time: str,
) -> str:
    """计算一次 turn episode 的稳定公开输入摘要。"""

    payload = json.dumps(
        {
            "adapter_version": GRAPHITI_ADAPTER_VERSION,
            "episode_body": episode_body,
            "isolation_key": isolation_key,
            "reference_time": reference_time,
            "session_id": session_id,
            "turn_id": turn_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _retrieved_item(rank: int, raw: Any) -> RetrievedItem:
    """把 worker edge 结果转换为公开 RetrievedItem。"""

    expected = {
        "expired_at",
        "fact",
        "invalid_at",
        "reference_time",
        "source_turn_ids",
        "uuid",
        "valid_at",
    }
    if not isinstance(raw, dict) or set(raw) != expected:
        raise ConfigurationError("Graphiti search item has an invalid shape")
    source_turn_ids = tuple(
        _required_text_list(raw.get("source_turn_ids"), "source_turn_ids")
    )
    if not source_turn_ids:
        raise ConfigurationError(
            "Graphiti semantic provenance item must have source_turn_ids"
        )
    return RetrievedItem(
        item_id=_required_text(raw.get("uuid"), "item.uuid"),
        content=_required_text(raw.get("fact"), "item.fact"),
        score=None,
        timestamp=_optional_text(raw.get("reference_time"), "reference_time"),
        source_turn_ids=source_turn_ids,
        metadata={
            "product_rank": rank,
            "valid_at": _optional_text(raw.get("valid_at"), "valid_at"),
            "invalid_at": _optional_text(raw.get("invalid_at"), "invalid_at"),
            "expired_at": _optional_text(raw.get("expired_at"), "expired_at"),
        },
    )


def _format_graphiti_items(items: tuple[RetrievedItem, ...]) -> str:
    """按 product rank 原序生成 benchmark answer builder 的 memory 文本。"""

    parts: list[str] = []
    for rank, item in enumerate(items, start=1):
        attributes = [
            f'rank="{rank}"',
            f'id="{html.escape(item.item_id, quote=True)}"',
        ]
        for key in ("valid_at", "invalid_at"):
            value = item.metadata.get(key)
            if isinstance(value, str):
                attributes.append(f'{key}="{html.escape(value, quote=True)}"')
        if item.timestamp is not None:
            attributes.append(
                f'reference_time="{html.escape(item.timestamp, quote=True)}"'
            )
        parts.append(
            f"<fact {' '.join(attributes)}>{html.escape(item.content)}</fact>"
        )
    return "\n\n".join(parts)


def _graphiti_retrieval_evidence() -> RetrievalEvidence:
    """声明 edge episode lineage 与 product RRF rank 均为 valid。"""

    return RetrievalEvidence(
        semantic_provenance=EvidenceAssertion(status="valid"),
        provenance_granularity="turn",
        stable_ranking=EvidenceAssertion(status="valid"),
    )


def _validated_observations(value: Any, label: str) -> list[dict[str, Any]]:
    """校验 worker observation 是对象列表。"""

    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ConfigurationError(
            f"Graphiti {label} observations must be a list of objects"
        )
    return list(value)


def _record_embedding_observation(
    collector: EfficiencyCollector,
    observation: dict[str, Any],
) -> None:
    """记录一次本地 MiniLM 调用。"""

    collector.record_embedding_call(
        model_id=GRAPHITI_EMBEDDING_MODEL_ID,
        input_tokens=_required_non_negative_int(
            observation.get("input_tokens"), "input_tokens"
        ),
        latency_ms=_required_non_negative_number(
            observation.get("latency_ms"), "latency_ms"
        ),
        token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
        latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
    )


def _required_text(value: Any, label: str) -> str:
    """读取非空文本。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"Graphiti {label} must be non-blank text")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    """读取可空文本；空白字符串不是合法 null。"""

    if value is None:
        return None
    return _required_text(value, label)


def _required_text_list(value: Any, label: str) -> list[str]:
    """读取允许为空、元素非空且去重的字符串列表。"""

    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ConfigurationError(
            f"Graphiti {label} must be a list of non-blank text"
        )
    if len(value) != len(set(value)):
        raise ConfigurationError(f"Graphiti {label} must not contain duplicates")
    return list(value)


def _required_non_negative_int(value: Any, label: str) -> int:
    """读取非负整数，布尔值不合法。"""

    if type(value) is not int or value < 0:
        raise ConfigurationError(
            f"Graphiti {label} must be a non-negative integer"
        )
    return value


def _required_bool(value: Any, label: str) -> bool:
    """读取严格布尔值。"""

    if type(value) is not bool:
        raise ConfigurationError(f"Graphiti {label} must be boolean")
    return value


def _required_non_negative_number(value: Any, label: str) -> float:
    """读取非负有限数值。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"Graphiti {label} must be numeric")
    resolved = float(value)
    if not math.isfinite(resolved) or resolved < 0:
        raise ConfigurationError(
            f"Graphiti {label} must be non-negative and finite"
        )
    return resolved


def _resolve_project_relative_path(value: str, project_root: Path) -> Path | None:
    """解析项目内路径并拒绝逃逸。"""

    candidate = Path(value)
    resolved = (
        candidate.resolve(strict=False)
        if candidate.is_absolute()
        else (project_root / candidate).resolve(strict=False)
    )
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return None
    return resolved


def build_graphiti_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored Graphiti、uv.lock 与 wrapper/bootstrap 的稳定身份。"""

    settings = path_settings or load_path_settings()
    root = settings.resolve_third_party_method_path(GRAPHITI_METHOD_DIRECTORY)
    source_files = [root / relative for relative in GRAPHITI_SOURCE_FILES]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        raise ConfigurationError(
            "Graphiti source files missing: "
            + ", ".join(str(path) for path in missing)
        )
    vendored_sha256, relative_paths = _hash_relative_files(root, source_files)
    runtime_lock = root / "uv.lock"
    if not runtime_lock.is_file():
        raise ConfigurationError(
            f"Graphiti runtime lock file missing: {runtime_lock}"
        )
    wrapper_paths = [
        settings.project_root / GRAPHITI_WRAPPER_LOGICAL_PATH,
        settings.project_root / GRAPHITI_WORKER_LOGICAL_PATH,
        settings.project_root / GRAPHITI_BOOTSTRAP_LOGICAL_PATH,
    ]
    missing_wrappers = [path for path in wrapper_paths if not path.is_file()]
    if missing_wrappers:
        raise ConfigurationError(
            "Graphiti wrapper files missing: "
            + ", ".join(str(path) for path in missing_wrappers)
        )
    wrapper_hashes = {
        path.relative_to(settings.project_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in wrapper_paths
    }
    identity = {
        "upstream_url": GRAPHITI_UPSTREAM_URL,
        "version": GRAPHITI_VERSION,
        "commit": GRAPHITI_COMMIT,
        "implementation_identity": GRAPHITI_IMPLEMENTATION_IDENTITY,
        "product_surface": GRAPHITI_PRODUCT_SURFACE,
        "source_mode": GRAPHITI_SOURCE_MODE,
        "vendored_source_sha256": vendored_sha256,
        "runtime_lock_sha256": hashlib.sha256(runtime_lock.read_bytes()).hexdigest(),
        "wrapper_hashes": wrapper_hashes,
    }
    source_sha256 = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "source_sha256": source_sha256,
        **identity,
        "file_count": len(relative_paths),
        "files": relative_paths,
    }


def _hash_relative_files(root: Path, files: list[Path]) -> tuple[str, list[str]]:
    """按相对路径和内容 bytes 计算 selected-source hash。"""

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for path in files:
        relative = path.relative_to(root).as_posix()
        relative_paths.append(relative)
        relative_bytes = relative.encode("utf-8")
        content = path.read_bytes()
        digest.update(len(relative_bytes).to_bytes(8, "big"))
        digest.update(relative_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest(), relative_paths


__all__ = [
    "GRAPHITI_ADAPTER_VERSION",
    "GRAPHITI_BUILD_LLM_RESPONSE_CONTRACT",
    "GRAPHITI_EMBEDDING_MODEL_ID",
    "GRAPHITI_LLM_MODEL_ID",
    "GraphitiConfig",
    "GraphitiOSS",
    "GraphitiRuntime",
    "build_graphiti_source_identity",
    "clean_graphiti_conversation_state",
    "validate_graphiti_variant",
]
