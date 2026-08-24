"""LangMem background memory manager 的 provider v3 adapter。

主轨按 canonical session 调用官方 ``create_memory_store_manager().ainvoke``，
检索调用同一 ``MemoryStoreManager.asearch``。第三方依赖在独立 Python 3.12
worker 中运行；adapter 只负责 benchmark 公共字段渲染、namespace、协议校验、
效率观测与最终 ``formatted_memory``。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import html
import json
import math
import os
from pathlib import Path
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
    SessionBatch,
    SessionMemoryReport,
    SessionRef,
)
from memory_benchmark.methods.image_text import turn_text_with_images
from memory_benchmark.methods.worker_transport import (
    JsonLinesWorkerTransport,
    WORKER_TRANSPORT_LOGICAL_PATH,
    WorkerCommandError,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
)


LANGMEM_ADAPTER_VERSION = "langmem-background-product-v2"
LANGMEM_METHOD_DIRECTORY = "langmem"
LANGMEM_UPSTREAM_URL = "https://github.com/langchain-ai/langmem.git"
LANGMEM_COMMIT = "56d85939d80bb731bd5e237567148d817d7bfd16"
LANGMEM_PACKAGE_VERSION = "0.0.30"
LANGMEM_IMPLEMENTATION_IDENTITY = "async-background-memory-store-manager"
LANGMEM_PRODUCT_SURFACE = "create_memory_store_manager+ainvoke+asearch"
LANGMEM_LLM_MODEL_ID = "langmem-build-llm"
LANGMEM_EMBEDDING_MODEL_ID = "langmem-embedding"
LANGMEM_EMPTY_MEMORY_SENTINEL = "(No LangMem memories retrieved)"
LANGMEM_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/langmem_adapter.py"
LANGMEM_WORKER_LOGICAL_PATH = "src/memory_benchmark/methods/langmem_worker.py"
LANGMEM_BOOTSTRAP_LOGICAL_PATH = "scripts/bootstrap_langmem_runtime.sh"
LANGMEM_REQUIREMENTS_LOGICAL_PATH = "scripts/requirements/langmem-runtime.txt"
LANGMEM_SOURCE_MODE = "vendored-langmem-plus-isolated-product-wrapper"
LANGMEM_NAMESPACE_ALGORITHM = "sha256(langmem-background-product-v2|isolation_key)[:32]"
LANGMEM_BUILD_LLM_RESPONSE_CONTRACT = (
    "provider-aware-v2:"
    "opencodego=chat_completions+model_aware_reasoning;"
    "primary=chat_completions+provider_default;"
    "exact_usage_required"
)
LANGMEM_SOURCE_FILES = (
    "LICENSE",
    "README.md",
    "pyproject.toml",
    "src/langmem/__init__.py",
    "src/langmem/knowledge/extraction.py",
    "src/langmem/knowledge/tools.py",
    "src/langmem/utils.py",
    "docs/docs/background_quickstart.md",
    "docs/docs/guides/delayed_processing.md",
)
_ALLOWED_ROLES = frozenset({"user", "assistant"})
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
class LangMemConfig:
    """LangMem background-manager 主 profile 的强类型配置。"""

    llm_model: str
    embedding_model_path: str
    embedding_dimension: int
    embedding_normalize: bool
    query_limit: int
    max_steps: int
    enable_inserts: bool
    enable_deletes: bool
    worker_request_timeout_seconds: float
    max_workers: int
    profile_name: str = "product-background-v1"

    def __post_init__(self) -> None:
        """拒绝偏离 M1 已锁产品边界的配置。"""

        for field_name in ("llm_model", "embedding_model_path", "profile_name"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"LangMem {field_name} is required")
        for field_name in (
            "embedding_dimension",
            "query_limit",
            "max_steps",
            "max_workers",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 1:
                raise ConfigurationError(
                    f"LangMem {field_name} must be a positive integer"
                )
        for field_name in (
            "embedding_normalize",
            "enable_inserts",
            "enable_deletes",
        ):
            if type(getattr(self, field_name)) is not bool:
                raise ConfigurationError(f"LangMem {field_name} must be boolean")
        if self.embedding_dimension != 384:
            raise ConfigurationError(
                "LangMem controlled MiniLM profile requires embedding_dimension=384"
            )
        if self.embedding_normalize is not True:
            raise ConfigurationError(
                "LangMem controlled MiniLM profile requires normalized embeddings"
            )
        if self.query_limit != 5:
            raise ConfigurationError(
                "LangMem main profile preserves the public factory query_limit=5"
            )
        if self.max_steps != 1:
            raise ConfigurationError(
                "LangMem main profile preserves MemoryStoreManager max_steps=1"
            )
        if self.enable_inserts is not True or self.enable_deletes is not False:
            raise ConfigurationError(
                "LangMem main profile requires enable_inserts=true and "
                "enable_deletes=false"
            )
        if (
            isinstance(self.worker_request_timeout_seconds, bool)
            or not isinstance(self.worker_request_timeout_seconds, (int, float))
            or not math.isfinite(float(self.worker_request_timeout_seconds))
            or self.worker_request_timeout_seconds <= 0
        ):
            raise ConfigurationError(
                "LangMem worker_request_timeout_seconds must be positive and finite"
            )

    def validate_required_local_resources(self, path_settings: PathSettings) -> None:
        """校验受控 embedding 模型存在；worker 环境由 runtime 启动时核。"""

        model_path = _resolve_project_relative_path(
            self.embedding_model_path,
            path_settings.project_root,
        )
        if model_path is None or not model_path.is_dir():
            raise ConfigurationError(
                "LangMem required local embedding model missing: "
                f"{self.embedding_model_path}"
            )

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret、base URL 和机器绝对状态路径的公开身份。"""

        return {
            **asdict(self),
            "adapter_version": LANGMEM_ADAPTER_VERSION,
            "implementation_identity": LANGMEM_IMPLEMENTATION_IDENTITY,
            "product_surface": LANGMEM_PRODUCT_SURFACE,
            "consume_granularity": "session",
            "namespace_template": ["memories", "{langgraph_user_id}"],
            "store": "langgraph.InMemoryStore+atomic-state-v1",
            "persistence_contract": "exact-key-value-order+operation-journal-v1",
            "embedding_provider": "sentence-transformers-local",
            "embedding_distance": "langgraph-inmemory-cosine",
            "query_model": None,
            "build_llm_response_contract": LANGMEM_BUILD_LLM_RESPONSE_CONTRACT,
        }


class LangMemRuntimeProtocol(Protocol):
    """adapter 所需的最窄 worker runtime 协议。"""

    def ensure_started(self) -> None:
        """确保独立 worker、本地模型和 product manager 已就绪。"""

    def ingest(
        self,
        *,
        namespace_id: str,
        operation_id: str,
        messages: list[dict[str, str]],
        max_steps: int,
    ) -> dict[str, Any]:
        """执行一次 session 级 async background manager。"""

    def retrieve(
        self,
        *,
        namespace_id: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        """执行一次产品 asearch。"""

    def delete_namespace(self, *, namespace_id: str) -> dict[str, Any]:
        """幂等删除一个 conversation namespace。"""

    def close(self) -> None:
        """关闭当前 provider 独占 worker。"""


RuntimeFactory = Callable[..., LangMemRuntimeProtocol]


class LangMemRuntime:
    """一个 provider 实例独占的 LangMem JSON-lines worker。"""

    def __init__(
        self,
        *,
        config: LangMemConfig,
        openai_settings: OpenAISettings,
        path_settings: PathSettings,
        storage_root: Path,
        diagnostic_log_path: Path | None = None,
    ) -> None:
        """保存依赖；第三方 import 与模型加载推迟到 ``ensure_started``。"""

        self.config = config
        self.openai_settings = openai_settings
        self.path_settings = path_settings
        self.storage_root = storage_root
        self._transport = JsonLinesWorkerTransport(
            product_label="LangMem",
            request_timeout_seconds=config.worker_request_timeout_seconds,
            timeout_detail="the operation journal remains the only resume authority",
            stderr_tail_char_limit=3000,
            terminate_on_timeout=True,
            terminate_on_protocol_error=True,
            forget_process_on_terminate=False,
            diagnostic_log_path=diagnostic_log_path,
        )
        self._closed = False

    def _langmem_root(self) -> Path:
        """返回 source-locked vendored LangMem 根目录。"""

        return self.path_settings.resolve_third_party_method_path(
            LANGMEM_METHOD_DIRECTORY
        )

    def _worker_python(self) -> Path:
        """返回独立 runtime Python，不允许回落主框架解释器。"""

        python = self._langmem_root() / ".venv" / "bin" / "python"
        if not python.is_file():
            raise ConfigurationError(
                "LangMem isolated runtime is missing. Run "
                "scripts/bootstrap_langmem_runtime.sh first."
            )
        return python

    def _embedding_model_path(self) -> Path:
        """解析受控本地 embedding 目录。"""

        model_path = _resolve_project_relative_path(
            self.config.embedding_model_path,
            self.path_settings.project_root,
        )
        if model_path is None or not model_path.is_dir():
            raise ConfigurationError(
                "LangMem embedding model path is missing: "
                f"{self.config.embedding_model_path}"
            )
        return model_path

    def _worker_environment(self) -> dict[str, str]:
        """构造最小环境，只显式传 build secret 与必要系统变量。"""

        environment = {
            name: value
            for name, value in os.environ.items()
            if name in _WORKER_PASSTHROUGH_ENV_NAMES
        }
        environment.update(
            {
                "HF_HUB_OFFLINE": "1",
                "MEMORY_BENCHMARK_LANGMEM_BUILD_API_KEY": (
                    self.openai_settings.api_key
                ),
                "PYTHONUNBUFFERED": "1",
                "TOKENIZERS_PARALLELISM": "false",
                "TRANSFORMERS_OFFLINE": "1",
            }
        )
        return environment

    def ensure_started(self) -> None:
        """启动 worker 并完成无 API initialize handshake。"""

        if self._closed:
            raise ConfigurationError("LangMem runtime is already closed")
        if self._transport.has_process:
            if self._transport.is_running:
                return
            raise ConfigurationError(self._worker_failure_text("exited"))
        worker_path = self.path_settings.project_root / LANGMEM_WORKER_LOGICAL_PATH
        if not worker_path.is_file():
            raise ConfigurationError(f"LangMem worker file missing: {worker_path}")
        state_root = (self.storage_root / "langmem_state").resolve()
        state_root.mkdir(parents=True, exist_ok=True)
        self._transport.start(
            argv=[str(self._worker_python()), str(worker_path)],
            cwd=self._langmem_root(),
            env=self._worker_environment(),
            stderr_thread_name=f"langmem-worker-{id(self)}-stderr",
            stderr_redactor=self._worker_stderr_redactor(),
        )
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
                        "enable_deletes": self.config.enable_deletes,
                        "enable_inserts": self.config.enable_inserts,
                        "llm_model": self.config.llm_model,
                        "max_steps": self.config.max_steps,
                        "query_limit": self.config.query_limit,
                    },
                    "state_root": str(state_root),
                },
            )
        except BaseException:
            self._terminate_worker()
            raise
        if (
            result.get("status") != "ready"
            or result.get("adapter_version") != LANGMEM_ADAPTER_VERSION
            or result.get("product_surface") != LANGMEM_PRODUCT_SURFACE
        ):
            self._terminate_worker()
            raise ConfigurationError("LangMem worker initialize identity mismatch")

    def _worker_stderr_redactor(self) -> Callable[[str], str]:
        """冻结 build key 并返回逐行脱敏器。"""

        build_key = self.openai_settings.api_key
        return lambda line: line.replace(build_key, "<redacted>")

    def _request(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """经共享 transport 发送请求；LangMem payload 保持本地显式。"""

        return self._transport.request(command, payload)

    def _worker_failure_text(self, state: str) -> str:
        """构造不含 secret 的 worker 失败摘要。"""

        return self._transport.failure_text(state)

    def ingest(
        self,
        *,
        namespace_id: str,
        operation_id: str,
        messages: list[dict[str, str]],
        max_steps: int,
    ) -> dict[str, Any]:
        """经 worker 执行一次 session 级 background manager。"""

        self.ensure_started()
        return self._request(
            "ingest",
            {
                "namespace_id": namespace_id,
                "operation_id": operation_id,
                "messages": messages,
                "max_steps": max_steps,
            },
        )

    def retrieve(
        self,
        *,
        namespace_id: str,
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        """经 worker 执行产品 asearch。"""

        self.ensure_started()
        return self._request(
            "retrieve",
            {"namespace_id": namespace_id, "query": query, "limit": limit},
        )

    def delete_namespace(self, *, namespace_id: str) -> dict[str, Any]:
        """经 worker 执行 namespace-scoped clean retry。"""

        self.ensure_started()
        return self._request("delete_namespace", {"namespace_id": namespace_id})

    def close(self) -> None:
        """关闭 worker；重复成功 cleanup 保持幂等。"""

        if self._closed:
            return
        worker = self._transport.process
        if worker is not None and worker.poll() is None:
            try:
                result = self._request("shutdown", {})
                if result.get("status") != "closed":
                    raise ConfigurationError(
                        "LangMem worker did not confirm shutdown"
                    )
                self._transport.wait(timeout=10)
            except BaseException:
                self._terminate_worker()
                raise
        self._terminate_worker()
        self._closed = True

    def _terminate_worker(self) -> None:
        """尽力终止 worker 并关闭 pipe，不冒充业务操作成功。"""

        self._transport.terminate()


class LangMem(MemoryProvider):
    """LangMem async background-manager 的 session 粒度 provider。"""

    consume_granularity = "session"
    session_memory_report = False
    provenance_granularity = "none"

    def __init__(
        self,
        *,
        config: LangMemConfig,
        path_settings: PathSettings,
        storage_root: Path,
        openai_settings: OpenAISettings,
        efficiency_collector: EfficiencyCollector | None = None,
        session_memory_report: bool = False,
        benchmark_name: str | None = None,
        diagnostic_log_path: Path | None = None,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        """保存构造依赖并保持 runtime lazy。"""

        if config.llm_model != openai_settings.model:
            raise ConfigurationError(
                "LangMem config llm_model must match selected API runtime model"
            )
        config.validate_required_local_resources(path_settings)
        self.config = config
        self.path_settings = path_settings
        self.storage_root = storage_root
        self.openai_settings = openai_settings
        self.efficiency_collector = efficiency_collector
        if not isinstance(session_memory_report, bool):
            raise ConfigurationError("LangMem session_memory_report must be bool")
        self.session_memory_report = session_memory_report
        self.benchmark_name = benchmark_name
        self.diagnostic_log_path = diagnostic_log_path
        self._runtime_factory = runtime_factory or LangMemRuntime
        self._runtime: LangMemRuntimeProtocol | None = None
        self._observed_operation_ids: set[str] = set()
        self._session_report_memories: dict[tuple[str, str | None], list[str]] = {}
        self._cleaned = False

    def prepare(self, run_context: Any) -> None:
        """在 ingest 前加载本地 runtime；初始化本身不调用外部 LLM。"""

        del run_context
        self._require_runtime().ensure_started()

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """把完整 canonical session 原序交给官方 async manager。"""

        if not isinstance(unit, SessionBatch):
            raise ConfigurationError("LangMem provider only accepts SessionBatch")
        if not unit.events:
            if self.session_memory_report:
                self._session_report_memories[
                    (unit.isolation_key, unit.session_id)
                ] = []
            return IngestResult(
                unit_ref=unit.ref,
                metadata={
                    "method": "langmem",
                    "source_message_count": 0,
                    "changed_memory_count": 0,
                },
            )
        messages = self._build_messages(unit)
        namespace_id = _namespace_id(unit.isolation_key)
        operation_id = _operation_id(
            namespace_id=namespace_id,
            session_id=unit.session_id,
            messages=messages,
            max_steps=self.config.max_steps,
        )
        try:
            result = self._require_runtime().ingest(
                namespace_id=namespace_id,
                operation_id=operation_id,
                messages=messages,
                max_steps=self.config.max_steps,
            )
        except WorkerCommandError as exc:
            self._record_failed_worker_observations(
                exc.details,
                stage=EfficiencyStage.MEMORY_BUILD,
            )
            raise
        self._record_operation_observations(operation_id, result)
        changed_keys = _required_text_list(
            result.get("changed_memory_keys"),
            "changed_memory_keys",
        )
        memory_count = _required_non_negative_int(
            result.get("memory_count"), "memory_count"
        )
        if self.session_memory_report:
            changed_memories = _required_changed_memories(
                result.get("changed_memories"),
                expected_keys=changed_keys,
            )
            self._session_report_memories[
                (unit.isolation_key, unit.session_id)
            ] = [
                _format_langmem_session_memory(item["value"])
                for item in changed_memories
            ]
        return IngestResult(
            unit_ref=unit.ref,
            metadata={
                "method": "langmem",
                "namespace_id": namespace_id,
                "operation_id": operation_id,
                "operation_reused": _required_bool(
                    result.get("reused_operation"), "reused_operation"
                ),
                "source_message_count": len(messages),
                "changed_memory_count": len(changed_keys),
                "memory_count": memory_count,
                **_rehydration_metadata(result),
            },
        )

    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """报告该 session 事务实际创建或改写后的 current product memories。"""

        if not self.session_memory_report:
            return None
        memories = self._session_report_memories.pop(
            (ref.isolation_key, ref.session_id),
            [],
        )
        return SessionMemoryReport(
            session_ref=ref,
            memories=memories,
            metadata={
                "method": "langmem",
                "memory_unit": "current_changed_product_memory",
                "changed_memory_count": len(memories),
            },
        )

    def _build_messages(self, unit: SessionBatch) -> list[dict[str, str]]:
        """按五格已冻结公共语义构造 LangChain role/content messages。"""

        locomo_roles = (
            self._locomo_speaker_roles(unit)
            if self.benchmark_name == "locomo"
            else None
        )
        messages: list[dict[str, str]] = []
        for event in unit.events:
            if locomo_roles is None:
                role = event.role
                if role not in _ALLOWED_ROLES:
                    raise ConfigurationError(
                        "LangMem only accepts canonical user/assistant roles: "
                        f"{role!r}"
                    )
            else:
                speaker = event.speaker_name or event.role
                role = locomo_roles.get(speaker)
                if role is None:
                    raise ConfigurationError(
                        f"LangMem LoCoMo speaker is not declared: {speaker!r}"
                    )
            rendered = _render_event_content(event, unit.session_time)
            if locomo_roles is not None:
                time_prefix, source_content = _split_source_time_prefix(rendered)
                rendered = (
                    f"{time_prefix}{event.speaker_name or event.role}: "
                    f"{source_content}"
                )
            if not rendered.strip():
                raise ConfigurationError(
                    f"LangMem turn has no visible content: {event.turn_id}"
                )
            messages.append({"role": role, "content": rendered})
        return messages

    @staticmethod
    def _locomo_speaker_roles(unit: SessionBatch) -> dict[str, str]:
        """固定映射 speaker_a→user、speaker_b→assistant，与首发顺序无关。"""

        metadata: dict[str, Any] = {}
        for event in unit.events:
            candidate = event.metadata.get("conversation_metadata")
            if isinstance(candidate, dict):
                metadata = candidate
                break
        speaker_a = metadata.get("speaker_a")
        speaker_b = metadata.get("speaker_b")
        if not isinstance(speaker_a, str) or not speaker_a.strip():
            raise ConfigurationError("LangMem LoCoMo metadata is missing speaker_a")
        if not isinstance(speaker_b, str) or not speaker_b.strip():
            raise ConfigurationError("LangMem LoCoMo metadata is missing speaker_b")
        if speaker_a == speaker_b:
            raise ConfigurationError("LangMem LoCoMo speakers must be distinct")
        return {speaker_a: "user", speaker_b: "assistant"}

    def _record_operation_observations(
        self,
        operation_id: str,
        result: dict[str, Any],
    ) -> None:
        """把 worker 的逐调用 build facts 写入当前 conversation scope 一次。"""

        llm = _validated_observations(result.get("llm_observations"), "llm")
        embedding = _validated_observations(
            result.get("embedding_observations"), "embedding"
        )
        if operation_id in self._observed_operation_ids:
            return
        collector = self.efficiency_collector
        if collector is not None:
            for observation in llm:
                collector.record_llm_call(
                    model_id=LANGMEM_LLM_MODEL_ID,
                    input_tokens=_required_non_negative_int(
                        observation.get("input_tokens"), "input_tokens"
                    ),
                    output_tokens=_required_non_negative_int(
                        observation.get("output_tokens"), "output_tokens"
                    ),
                    token_measurement_source=MeasurementSource.API_USAGE,
                )
            for observation in embedding:
                _record_embedding_observation(collector, observation)
        self._observed_operation_ids.add(operation_id)

    def _record_failed_worker_observations(
        self,
        details: dict[str, Any] | None,
        *,
        stage: EfficiencyStage,
    ) -> None:
        """把失败 worker command 已完成的调用交给当前失败 scope。"""

        if details is None or self.efficiency_collector is None:
            return
        if set(details) != {"llm_observations", "embedding_observations"}:
            raise ConfigurationError(
                "LangMem worker failure observation fields are malformed"
            )
        llm = _validated_observations(details["llm_observations"], "llm")
        embedding = _validated_observations(
            details["embedding_observations"], "embedding"
        )
        with self.efficiency_collector.operation_stage(stage):
            for observation in llm:
                self.efficiency_collector.record_llm_call(
                    model_id=LANGMEM_LLM_MODEL_ID,
                    input_tokens=_required_non_negative_int(
                        observation.get("input_tokens"), "input_tokens"
                    ),
                    output_tokens=_required_non_negative_int(
                        observation.get("output_tokens"), "output_tokens"
                    ),
                    token_measurement_source=MeasurementSource.API_USAGE,
                )
            for observation in embedding:
                _record_embedding_observation(
                    self.efficiency_collector,
                    observation,
                )

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """调用 product asearch 并保留原 rank、score 与零命中。"""

        namespace_id = _namespace_id(query.isolation_key)
        started_ns = perf_counter_ns()
        try:
            result = self._require_runtime().retrieve(
                namespace_id=namespace_id,
                query=query.query_text,
                limit=query.top_k,
            )
        except WorkerCommandError as exc:
            self._record_failed_worker_observations(
                exc.details,
                stage=EfficiencyStage.RETRIEVAL,
            )
            raise
        total_latency_ms = max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)
        embedding = _validated_observations(
            result.get("embedding_observations"), "embedding"
        )
        if self.efficiency_collector is not None:
            with self.efficiency_collector.operation_stage(
                EfficiencyStage.RETRIEVAL
            ):
                for observation in embedding:
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
            raise ConfigurationError("LangMem worker retrieve result has no items list")
        items = tuple(
            _retrieved_item(index, raw)
            for index, raw in enumerate(raw_items, start=1)
        )
        formatted_memory = _format_langmem_items(items)
        return RetrievalResult(
            formatted_memory=formatted_memory or LANGMEM_EMPTY_MEMORY_SENTINEL,
            items=items,
            metadata={
                "method": "langmem",
                "prompt_track": "unified",
                "namespace_id": namespace_id,
                "product_surface": LANGMEM_PRODUCT_SURFACE,
                "query_consumed_by_method": True,
                "stable_product_ranking": True,
                "provenance_granularity": "none",
                "worker_search_latency_ms": _required_non_negative_number(
                    result.get("latency_ms"), "latency_ms"
                ),
                **_rehydration_metadata(result),
            },
            evidence=_langmem_retrieval_evidence(),
        )

    def cleanup(self) -> None:
        """关闭独占 worker；成功后才提交 provider 清理状态。"""

        if self._cleaned:
            return
        runtime = self._runtime
        if runtime is None:
            self._cleaned = True
            return
        runtime.close()
        self._runtime = None
        self._cleaned = True

    def _require_runtime(self) -> LangMemRuntimeProtocol:
        """懒构造并复用当前 provider 的唯一 runtime。"""

        if self._cleaned:
            raise ConfigurationError("LangMem provider is already cleaned")
        if self._runtime is None:
            runtime_kwargs: dict[str, Any] = dict(
                config=self.config,
                openai_settings=self.openai_settings,
                path_settings=self.path_settings,
                storage_root=self.storage_root,
            )
            if self.diagnostic_log_path is not None:
                runtime_kwargs["diagnostic_log_path"] = self.diagnostic_log_path
            self._runtime = self._runtime_factory(**runtime_kwargs)
        return self._runtime


def clean_langmem_conversation_state(
    *,
    provider: LangMem,
    isolation_key: str,
) -> None:
    """清理 failed-ingest conversation 的独占 namespace，供 runner retry。"""

    result = provider._require_runtime().delete_namespace(
        namespace_id=_namespace_id(isolation_key)
    )
    if result.get("deleted") is not True:
        raise ConfigurationError("LangMem worker did not confirm namespace deletion")


def _namespace_id(isolation_key: str) -> str:
    """从公开 isolation key 生成 runtime 内 opaque namespace。"""

    if not isinstance(isolation_key, str) or not isolation_key.strip():
        raise ConfigurationError("LangMem isolation_key is required")
    return hashlib.sha256(
        f"{LANGMEM_ADAPTER_VERSION}|{isolation_key}".encode("utf-8")
    ).hexdigest()[:32]


def _operation_id(
    *,
    namespace_id: str,
    session_id: str | None,
    messages: list[dict[str, str]],
    max_steps: int,
) -> str:
    """生成同 payload 重试稳定、payload 漂移必变化的 operation id。"""

    encoded = json.dumps(
        {
            "adapter_version": LANGMEM_ADAPTER_VERSION,
            "namespace_id": namespace_id,
            "session_id": session_id,
            "messages": messages,
            "max_steps": max_steps,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _render_event_content(event: Any, session_time: str | None) -> str:
    """重建 caption，并按 turn→session→None 唯一渲染 source time。"""

    turn_metadata = event.metadata.get("turn_metadata")
    if not isinstance(turn_metadata, dict):
        turn_metadata = {}
    original = event.metadata.get("original_content")
    content = original if isinstance(original, str) else event.content
    turn_time = event.metadata.get("original_turn_time")
    if not isinstance(turn_time, str):
        turn_time = None
    turn = Turn(
        turn_id=event.turn_id,
        speaker=event.speaker_name or event.role,
        normalized_role=event.role if event.role in _ALLOWED_ROLES else None,
        content=content,
        turn_time=turn_time,
        metadata=dict(turn_metadata),
        images=_images_from_event(event),
    )
    rendered = turn_text_with_images(turn)
    prefix = _effective_time_prefix(
        turn_time=turn.turn_time,
        session_time=session_time,
        source_timestamp_embedded=turn_metadata.get(
            "source_timestamp_embedded_in_content"
        ),
    )
    return f"{prefix}{rendered}"


def _effective_time_prefix(
    *,
    turn_time: str | None,
    session_time: str | None,
    source_timestamp_embedded: object,
) -> str:
    """按 turn→session→None 前置时间；严格 True marker 才去重。"""

    if isinstance(turn_time, str) and turn_time.strip():
        if source_timestamp_embedded is True:
            return ""
        return f"[Turn time: {turn_time.strip()}] "
    if isinstance(session_time, str) and session_time.strip():
        return f"[Session time: {session_time.strip()}] "
    return ""


def _split_source_time_prefix(content: str) -> tuple[str, str]:
    """拆出框架生成的 source-time 前缀，让 LoCoMo speaker 位于其后。"""

    if not content.startswith("["):
        return "", content
    marker_end = content.find("] ")
    if marker_end < 0:
        return "", content
    prefix = content[: marker_end + 2]
    if not prefix.startswith(("[Turn time: ", "[Session time: ")):
        return "", content
    return prefix, content[marker_end + 2 :]


def _images_from_event(event: Any) -> list[ImageRef]:
    """从公开 event metadata 恢复 image caption，不向算法暴露 locator/query。"""

    raw_images = event.metadata.get("turn_images")
    if not isinstance(raw_images, list):
        return []
    return [
        ImageRef(
            image_id=raw.get("image_id"),
            path=raw.get("path"),
            caption=raw.get("caption"),
            metadata=dict(raw.get("metadata") or {}),
        )
        for raw in raw_images
        if isinstance(raw, dict)
    ]


def _retrieved_item(rank: int, raw: Any) -> RetrievedItem:
    """把 worker 的 product search item 转成公开协议实体。"""

    if not isinstance(raw, dict) or set(raw) != {"content", "key", "kind", "score"}:
        raise ConfigurationError("LangMem worker search item has an invalid shape")
    key = _required_text(raw.get("key"), "item.key")
    content = _required_text(raw.get("content"), "item.content")
    kind = _required_text(raw.get("kind"), "item.kind")
    score_raw = raw.get("score")
    score = None
    if score_raw is not None:
        score = _required_finite_number(score_raw, "item.score")
    return RetrievedItem(
        item_id=key,
        content=content,
        score=score,
        timestamp=None,
        source_turn_ids=(),
        metadata={"kind": kind, "product_rank": rank},
    )


def _format_langmem_items(items: tuple[RetrievedItem, ...]) -> str:
    """按产品 rank 原序生成 framework answer builder 的 memory 文本。"""

    return "\n\n".join(
        (
            f'<memory rank="{rank}" id="{html.escape(item.item_id, quote=True)}"'
            + (
                f' score="{item.score:.12g}"'
                if item.score is not None
                else ""
            )
            + f">{html.escape(item.content)}</memory>"
        )
        for rank, item in enumerate(items, start=1)
    )


def _required_changed_memories(
    value: Any,
    *,
    expected_keys: list[str],
) -> list[dict[str, Any]]:
    """校验 worker 返回的 current changed-memory 快照与 key 顺序一致。"""

    if not isinstance(value, list):
        raise ConfigurationError("LangMem changed_memories must be a list")
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict) or set(item) != {"key", "value"}:
            raise ConfigurationError(
                f"LangMem changed_memories[{index}] must contain exactly key/value"
            )
        key = _required_text(item.get("key"), f"changed_memories[{index}].key")
        current_value = item.get("value")
        if not isinstance(current_value, dict):
            raise ConfigurationError(
                f"LangMem changed_memories[{index}].value must be an object"
            )
        try:
            json.dumps(current_value, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ConfigurationError(
                f"LangMem changed_memories[{index}].value must be JSON serializable"
            ) from exc
        normalized.append({"key": key, "value": current_value})
    if [item["key"] for item in normalized] != expected_keys:
        raise ConfigurationError(
            "LangMem changed_memories must match changed_memory_keys in product order"
        )
    return normalized


def _format_langmem_session_memory(value: dict[str, Any]) -> str:
    """把 current product value 转为 HaluMem judge 可消费的确定性文本。"""

    raw_content = value.get("content", value)
    if isinstance(raw_content, dict):
        content = raw_content.get("content")
        if isinstance(content, str) and content.strip():
            return content
        return json.dumps(raw_content, ensure_ascii=False, sort_keys=True)
    if isinstance(raw_content, str) and raw_content.strip():
        return raw_content
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _langmem_retrieval_evidence() -> RetrievalEvidence:
    """声明 evolved current memory 的 provenance N/A 与真实稳定 rank。"""

    return RetrievalEvidence(
        semantic_provenance=EvidenceAssertion(
            status="n_a",
            reason_code="langmem_evolved_memory_not_source_exact",
            reason=(
                "LangMem can update and consolidate an existing memory with a new "
                "session; the current memory text has no lossless semantic mapping "
                "to benchmark source evidence units."
            ),
        ),
        provenance_granularity="none",
        stable_ranking=EvidenceAssertion(status="valid"),
    )


def _validated_observations(value: Any, label: str) -> list[dict[str, Any]]:
    """校验 worker observation 是对象列表。"""

    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ConfigurationError(f"LangMem {label} observations must be a list of objects")
    return list(value)


def _record_embedding_observation(
    collector: EfficiencyCollector,
    observation: dict[str, Any],
) -> None:
    """把 worker 本地 embedding 事实写入当前 build/retrieval scope。"""

    collector.record_embedding_call(
        model_id=LANGMEM_EMBEDDING_MODEL_ID,
        input_tokens=_required_non_negative_int(
            observation.get("input_tokens"), "input_tokens"
        ),
        latency_ms=_required_non_negative_number(
            observation.get("latency_ms"), "latency_ms"
        ),
        token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
        latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
    )


def _rehydration_metadata(result: dict[str, Any]) -> dict[str, int]:
    """读取 worker 明示的 resume 恢复开销，不把它混入业务 scope。"""

    return {
        "rehydrated_entry_count": _required_non_negative_int(
            result.get("rehydrated_entry_count"), "rehydrated_entry_count"
        ),
        "rehydration_embedding_calls": _required_non_negative_int(
            result.get("rehydration_embedding_calls"),
            "rehydration_embedding_calls",
        ),
    }


def _required_text(value: Any, label: str) -> str:
    """读取非空文本。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"LangMem {label} must be non-blank text")
    return value


def _required_text_list(value: Any, label: str) -> list[str]:
    """读取允许为空、元素非空且无重复的文本列表。"""

    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ConfigurationError(f"LangMem {label} must be a list of non-blank text")
    if len(value) != len(set(value)):
        raise ConfigurationError(f"LangMem {label} must not contain duplicates")
    return list(value)


def _required_non_negative_int(value: Any, label: str) -> int:
    """读取非负整数，布尔值不合法。"""

    if type(value) is not int or value < 0:
        raise ConfigurationError(f"LangMem {label} must be a non-negative integer")
    return value


def _required_bool(value: Any, label: str) -> bool:
    """读取严格布尔值。"""

    if type(value) is not bool:
        raise ConfigurationError(f"LangMem {label} must be boolean")
    return value


def _required_finite_number(value: Any, label: str) -> float:
    """读取有限浮点数。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"LangMem {label} must be numeric")
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ConfigurationError(f"LangMem {label} must be finite")
    return resolved


def _required_non_negative_number(value: Any, label: str) -> float:
    """读取非负有限数值。"""

    resolved = _required_finite_number(value, label)
    if resolved < 0:
        raise ConfigurationError(f"LangMem {label} must be non-negative")
    return resolved


def _resolve_project_relative_path(value: str, project_root: Path) -> Path | None:
    """解析项目相对路径，拒绝逃逸；绝对路径只允许已位于项目根内。"""

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


def build_langmem_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 current vendored source 与 adapter/runtime/bootstrap 的稳定身份。"""

    settings = path_settings or load_path_settings()
    langmem_root = settings.resolve_third_party_method_path(LANGMEM_METHOD_DIRECTORY)
    source_files = [langmem_root / relative for relative in LANGMEM_SOURCE_FILES]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        raise ConfigurationError(
            "LangMem source files missing: " + ", ".join(str(path) for path in missing)
        )
    vendored_sha256, relative_paths = _hash_relative_source_files(
        root=langmem_root,
        source_files=source_files,
    )
    runtime_lock_path = langmem_root / "uv.lock"
    if not runtime_lock_path.is_file():
        raise ConfigurationError(
            f"LangMem runtime lock file missing: {runtime_lock_path}"
        )
    wrapper_paths = [
        settings.project_root / LANGMEM_WRAPPER_LOGICAL_PATH,
        settings.project_root / LANGMEM_WORKER_LOGICAL_PATH,
        settings.project_root / WORKER_TRANSPORT_LOGICAL_PATH,
        settings.project_root / LANGMEM_BOOTSTRAP_LOGICAL_PATH,
        settings.project_root / LANGMEM_REQUIREMENTS_LOGICAL_PATH,
    ]
    missing_wrappers = [path for path in wrapper_paths if not path.is_file()]
    if missing_wrappers:
        raise ConfigurationError(
            "LangMem wrapper files missing: "
            + ", ".join(str(path) for path in missing_wrappers)
        )
    wrapper_hashes = {
        path.relative_to(settings.project_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in wrapper_paths
    }
    identity = {
        "upstream_url": LANGMEM_UPSTREAM_URL,
        "commit": LANGMEM_COMMIT,
        "package_version": LANGMEM_PACKAGE_VERSION,
        "implementation_identity": LANGMEM_IMPLEMENTATION_IDENTITY,
        "product_surface": LANGMEM_PRODUCT_SURFACE,
        "source_mode": LANGMEM_SOURCE_MODE,
        "vendored_source_sha256": vendored_sha256,
        "runtime_lock_sha256": hashlib.sha256(
            runtime_lock_path.read_bytes()
        ).hexdigest(),
        "wrapper_hashes": wrapper_hashes,
    }
    source_sha256 = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "source_sha256": source_sha256,
        **identity,
        "file_count": len(relative_paths),
        "files": list(relative_paths),
    }


def _hash_relative_source_files(
    *,
    root: Path,
    source_files: list[Path],
) -> tuple[str, list[str]]:
    """按相对路径与内容 bytes 计算 selected source hash。"""

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative = source_file.relative_to(root).as_posix()
        relative_paths.append(relative)
        path_bytes = relative.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest(), relative_paths


__all__ = [
    "LANGMEM_ADAPTER_VERSION",
    "LANGMEM_BUILD_LLM_RESPONSE_CONTRACT",
    "LANGMEM_EMBEDDING_MODEL_ID",
    "LANGMEM_EMPTY_MEMORY_SENTINEL",
    "LANGMEM_IMPLEMENTATION_IDENTITY",
    "LANGMEM_LLM_MODEL_ID",
    "LangMem",
    "LangMemConfig",
    "LangMemRuntime",
    "build_langmem_source_identity",
    "clean_langmem_conversation_state",
]
