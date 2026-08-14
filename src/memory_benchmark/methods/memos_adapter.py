"""MemOS v2.0.25 product typed-handler 的协议 v3 adapter。

adapter 只走官方 typed handler 对象接口（`init_server` →
`HandlerDependencies.from_init_server` → `AddHandler` / `SearchHandler`），
不启动 HTTP host、不 import `server_router`；成功路径保持 product 默认的
`async + fast → 本地队列 → parallel dispatcher → MEM_READ fine 抽取` 生命周期，
并用 R2 的 `MemosLocalTaskTracker` 等待本次 add 的精确终态。

答题一律交回 framework benchmark answer builder，本文件不调用 MemOS 自带
chat/answer 入口。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import threading
from time import perf_counter_ns
from typing import Any

from memory_benchmark.config import (
    OPENCODEGO_API_PROVIDER,
    OpenAISettings,
    PathSettings,
    load_path_settings,
)
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
    SessionRef,
    TurnEvent,
    UnitRef,
)
from memory_benchmark.methods.image_text import turn_text_with_images
from memory_benchmark.methods.memos_lifecycle import (
    MemosLocalTaskTracker,
    install_local_tracker,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
    extract_api_token_usage,
    resolve_token_usage,
)
from memory_benchmark.storage import atomic_write_json


MEMOS_ADAPTER_VERSION = "memos-v2.0.25-product-v4"
MEMOS_METHOD_DIRECTORY = "MemOS"
MEMOS_UPSTREAM_URL = "https://github.com/MemTensor/MemOS.git"
MEMOS_RELEASE_TAG = "v2.0.25"
MEMOS_COMMIT = "e820406269537b97d270687e3e40eea2f015f81a"
MEMOS_PATCH_LOGICAL_PATH = (
    "scripts/patches/memos-product-runtime-observability.patch"
)
MEMOS_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/memos_adapter.py"
MEMOS_IMPLEMENTATION_IDENTITY = "typed-product-handler"
MEMOS_SOURCE_MODE = "vendored-memos-product-plus-patch-plus-wrapper"
MEMOS_LLM_MODEL_ID = "memos-build-llm"
MEMOS_EMBEDDING_MODEL_ID = "memos-embedding"
MEMOS_RERANKER_MODEL_ID = "memos-reranker"
MEMOS_EMPTY_MEMORY_SENTINEL = "(No relevant memories found)"
# v2.0.25 的 `APISearchRequest.reference_time` 只有 schema 定义，current search
# 代码零消费（全仓仅 product_models.py 一处出现）。仍忠实传入 question time，但
# 公开 metadata 必须显式声明该字段尚未接线，不得宣称时间过滤已生效。
MEMOS_REFERENCE_TIME_EFFECT = "declared_but_unwired_v2.0.25"
MEMOS_BUILD_LLM_RESPONSE_CONTRACT = (
    "provider-aware-v1:"
    "opencodego=json_object+thinking_disabled;"
    "primary=provider_default"
)
MEMOS_OPENCODEGO_READER_COMPATIBILITY = "opencodego_json_non_thinking_v1"
MEMOS_NAMESPACE_ALGORITHM = "sha256(storage_root_relative|isolation_key)[:32]"
MEMOS_LOCOMO_VIEW_SIDECAR_SCHEMA_VERSION = "v1"
MEMOS_LOCOMO_OFFICIAL_BATCH_SIZE = 2
MEMOS_LOCOMO_VIEW_NAMES = ("speaker_a", "speaker_b")
_NAMESPACE_SAFE_PATTERN = re.compile(r"[^0-9a-z]+")
# MemOS product 只按 `role` 分流 chat message，benchmark canonical 也只保证这两种。
_ALLOWED_ROLES = frozenset({"user", "assistant"})
MEMOS_SOURCE_FILES = (
    "src/memos/api/config.py",
    "src/memos/api/handlers/base_handler.py",
    "src/memos/api/handlers/add_handler.py",
    "src/memos/api/handlers/search_handler.py",
    "src/memos/api/handlers/memory_handler.py",
    "src/memos/api/handlers/component_init.py",
    "src/memos/api/handlers/config_builders.py",
    "src/memos/api/handlers/formatters_handler.py",
    "src/memos/api/product_models.py",
    "src/memos/multi_mem_cube/single_cube.py",
    "src/memos/mem_reader/multi_modal_struct.py",
    "src/memos/mem_scheduler/task_schedule_modules/handlers/mem_read_handler.py",
    "src/memos/llms/openai.py",
    "src/memos/memories/textual/tree.py",
    "src/memos/memories/textual/tree_text_memory/organize/manager.py",
    "src/memos/graph_dbs/neo4j_community.py",
    "src/memos/embedders/sentence_transformer.py",
)


@dataclass(frozen=True)
class _MemosRawLLMCall:
    """后台线程完成的一次 MemOS LLM 调用原始观测。"""

    messages: Any
    output_text: str
    usage: Any


@dataclass(frozen=True)
class _MemosRawEmbeddingCall:
    """后台线程完成的一次 MemOS embedding 调用原始观测。"""

    embedder: Any
    texts: tuple[str, ...]
    latency_ms: float


@dataclass
class _MemosEfficiencyCapture:
    """一次 adapter 操作期间跨线程收集的原始调用缓冲。"""

    stage: EfficiencyStage
    llm_calls: list[_MemosRawLLMCall] = field(default_factory=list)
    embedding_calls: list[_MemosRawEmbeddingCall] = field(default_factory=list)


@dataclass(frozen=True)
class MemOSConfig:
    """MemOS v2.0.25 product 运行 profile。

    两个 section（`smoke` / `official_full`）除 `max_workers` 外参数完全相同；
    首版两者都固定为 1，因为 MemOS factory 按 config 缓存单例、reader 还持有构造
    期 graph DB，跨 namespace interleaving 尚未一手验证。
    """

    llm_model: str
    embedding_backend: str
    embedding_model_path: str
    embedding_dimension: int
    embedding_max_tokens: int
    embedding_trust_remote: bool
    memory_backend: str
    reader_backend: str
    add_async_mode: str
    use_redis_queue: bool
    parallel_dispatch: bool
    reorganize: bool
    reranker_backend: str
    search_mode: str
    search_relativity: float
    search_dedup: str
    search_rerank: bool
    include_preference: bool
    search_tool_memory: bool
    include_skill_memory: bool
    neighbor_discovery: bool
    internet_search: bool
    task_timeout_seconds: float
    max_workers: int
    graph_db_backend: str
    graph_db_uri: str
    graph_db_user: str
    graph_db_name: str
    graph_db_credential_env: str
    vector_db_host: str
    vector_db_port: int
    vector_db_credential_env: str
    add_mode: str | None = None
    profile_name: str = "product"

    def __post_init__(self) -> None:
        """强校验影响实验语义的 MemOS 参数，拒绝静默降级。"""

        for field_name in (
            "llm_model",
            "embedding_backend",
            "embedding_model_path",
            "memory_backend",
            "reader_backend",
            "add_async_mode",
            "reranker_backend",
            "search_mode",
            "search_dedup",
            "graph_db_backend",
            "graph_db_uri",
            "graph_db_user",
            "graph_db_name",
            "graph_db_credential_env",
            "vector_db_host",
            "vector_db_credential_env",
        ):
            if not str(getattr(self, field_name)).strip():
                raise ConfigurationError(f"MemOS {field_name} is required")
        if self.add_async_mode != "async":
            raise ConfigurationError(
                "MemOS main profile locks add_async_mode='async'; sync+fine is an "
                "explicit ALGORITHM_VARIANT and must not be the main profile"
            )
        if self.add_mode is not None:
            raise ConfigurationError(
                "MemOS main profile locks add_mode=None; it is ignored under "
                "async_mode='async' and must not be set implicitly"
            )
        if self.memory_backend != "tree_text":
            raise ConfigurationError("MemOS main profile locks memory_backend='tree_text'")
        if self.reader_backend != "multimodal_struct":
            raise ConfigurationError(
                "MemOS main profile locks reader_backend='multimodal_struct'"
            )
        if self.search_mode != "fast":
            raise ConfigurationError("MemOS main profile locks search_mode='fast'")
        if self.use_redis_queue:
            raise ConfigurationError(
                "MemOS main profile requires the local scheduler queue "
                "(use_redis_queue=false)"
            )
        if not self.parallel_dispatch:
            raise ConfigurationError(
                "MemOS main profile keeps the product-default parallel dispatcher "
                "(parallel_dispatch=true)"
            )
        if self.reorganize:
            raise ConfigurationError("MemOS main profile locks reorganize=false")
        for flag_name in (
            "include_preference",
            "search_tool_memory",
            "include_skill_memory",
            "neighbor_discovery",
            "internet_search",
        ):
            if getattr(self, flag_name):
                raise ConfigurationError(f"MemOS main profile locks {flag_name}=false")
        if self.embedding_dimension < 1:
            raise ConfigurationError("MemOS embedding_dimension must be positive")
        if self.embedding_max_tokens < 1:
            raise ConfigurationError("MemOS embedding_max_tokens must be positive")
        if self.task_timeout_seconds <= 0:
            raise ConfigurationError("MemOS task_timeout_seconds must be positive")
        if self.max_workers != 1:
            raise ConfigurationError(
                "MemOS首版不声明跨 conversation 并行资格，max_workers 必须为 1"
            )
        if not 0.0 <= self.search_relativity <= 1.0:
            raise ConfigurationError("MemOS search_relativity must be within [0, 1]")
        if self.vector_db_port < 1:
            raise ConfigurationError("MemOS vector_db_port must be positive")

    def validate_required_local_resources(self, path_settings: PathSettings) -> None:
        """校验本地受控 embedding 模型目录存在。"""

        if self.embedding_backend != "sentence_transformer":
            return
        model_path = _resolve_project_relative_path(
            self.embedding_model_path,
            path_settings.project_root,
        )
        if model_path is not None and not model_path.is_dir():
            raise ConfigurationError(
                "MemOS required local embedding model missing: "
                f"{model_path}. Download the configured embedding model "
                f"({self.embedding_model_path}) to that path before running prediction."
            )

    def runtime_identity(self) -> str:
        """返回本 config 的完整运行身份，用于 runtime 单例复用与冲突判定。"""

        payload = "|".join(
            f"{key}={value!r}" for key, value in sorted(asdict(self).items())
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret 与绝对路径的公开配置。

        password / API key 一律只落环境变量**名称**，绝不写值。
        """

        return {
            **asdict(self),
            "adapter_version": MEMOS_ADAPTER_VERSION,
            "implementation_identity": MEMOS_IMPLEMENTATION_IDENTITY,
            "build_llm_response_contract": MEMOS_BUILD_LLM_RESPONSE_CONTRACT,
            "llm_provider": "openai-compatible",
            "embedding_provider": "sentence-transformers-local",
            "namespace_algorithm": MEMOS_NAMESPACE_ALGORITHM,
            "cube_topology": (
                "one_namespace_one_cube_per_conversation_except_"
                "locomo_dual_speaker_view"
            ),
            "locomo_ingest_strategy": (
                "official_dual_namespace_reverse_roles_batch_size_2"
            ),
            "locomo_retrieval_strategy": (
                "official_dual_search_per_view_top_k_then_speaker_partition_merge"
            ),
            "longmemeval_ingest_strategy": (
                "product_full_session_preserve_order_no_truncation"
            ),
            "reference_time_effect": MEMOS_REFERENCE_TIME_EFFECT,
        }


def _resolve_project_relative_path(value: str, project_root: Path) -> Path | None:
    """把 `models/...` 这类配置解析成项目内路径。"""

    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    if len(candidate.parts) <= 1:
        return None
    return project_root / candidate


def build_memos_namespace(*, storage_root_relative: str, isolation_key: str) -> str:
    """按 run 目录相对身份 + 公开 isolation_key 生成确定性 namespace。

    `storage_root_relative` 已经编码 `benchmark_name/variant/run_id`，因此同一
    conversation 的 add/search/clean 得到同一 namespace，而两个 conversation、
    两个 run 或两个 worker storage root 必然不同。namespace 不含绝对机器路径、
    gold、question id 或随机 UUID，只保留产品可接受的安全字符。
    """

    if not storage_root_relative.strip():
        raise ConfigurationError("MemOS namespace requires a non-empty storage root")
    if not isolation_key.strip():
        raise ConfigurationError("MemOS namespace requires a non-empty isolation_key")
    raw = f"{storage_root_relative}|{isolation_key}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    slug = _NAMESPACE_SAFE_PATTERN.sub("", isolation_key.lower())[:24]
    return f"mb{slug}{digest}"


@contextmanager
def _scoped_environment(values: dict[str, str]) -> Iterator[None]:
    """在作用域内安装环境变量，退出时无论成功失败都恢复原值。"""

    previous: dict[str, str | None] = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, old_value in previous.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


def _memos_environment(
    config: MemOSConfig,
    openai_settings: OpenAISettings,
    path_settings: PathSettings,
) -> dict[str, str]:
    """把强类型 config 展开成 MemOS `init_server()` 读取的环境变量。

    secret 只从已声明的环境变量名读取，绝不写入 manifest/note/测试 stdout。
    Nacos watch、chat API、DingDing、internet、Redis 与 reorganize 全部显式关闭。
    """

    model_path = _resolve_project_relative_path(
        config.embedding_model_path,
        path_settings.project_root,
    )
    graph_password = os.environ.get(config.graph_db_credential_env)
    if graph_password is None:
        raise ConfigurationError(
            "MemOS graph DB password environment variable is not set: "
            f"{config.graph_db_credential_env}"
        )
    values = {
        # ---- build LLM（唯一真实 API 模型） ----
        "MOS_CHAT_MODEL": config.llm_model,
        "OPENAI_API_KEY": openai_settings.api_key,
        # `init_server()` 即使在 `ENABLE_INTERNET=false` 时也会无条件构造
        # internet retriever config；其嵌套 reader 的 Pydantic schema 要求这三项。
        # 这里只复用同一 build LLM 身份以通过产品初始化，internet 能力仍在下方关闭。
        "MEMRADER_MODEL": config.llm_model,
        "MEMRADER_API_KEY": openai_settings.api_key,
        "MEMRADER_API_BASE": (
            openai_settings.base_url or "https://api.openai.com/v1"
        ),
        # ---- 受控本地 embedding ----
        "MOS_EMBEDDER_BACKEND": config.embedding_backend,
        "MOS_EMBEDDER_MODEL": str(model_path or config.embedding_model_path),
        "MOS_EMBEDDER_DIMS": str(config.embedding_dimension),
        "MOS_EMBEDDER_MAX_TOKENS": str(config.embedding_max_tokens),
        "MOS_EMBEDDER_TRUST_REMOTE_CODE": _bool_env(config.embedding_trust_remote),
        "EMBEDDING_DIMENSION": str(config.embedding_dimension),
        # ---- reader / reranker ----
        "MEM_READER_BACKEND": config.reader_backend,
        "MOS_RERANKER_BACKEND": config.reranker_backend,
        # ---- 存储后端 ----
        "GRAPH_DB_BACKEND": config.graph_db_backend,
        "NEO4J_URI": config.graph_db_uri,
        "NEO4J_USER": config.graph_db_user,
        "NEO4J_DB_NAME": config.graph_db_name,
        "NEO4J_PASSWORD": graph_password,
        "QDRANT_HOST": config.vector_db_host,
        "QDRANT_PORT": str(config.vector_db_port),
        # ---- 调度：本地队列 + product 默认并行 dispatcher ----
        "MEMSCHEDULER_USE_REDIS_QUEUE": _bool_env(config.use_redis_queue),
        "MOS_SCHEDULER_ENABLE_PARALLEL_DISPATCH": _bool_env(config.parallel_dispatch),
        "MOS_ENABLE_SCHEDULER": "true",
        "MOS_ENABLE_REORGANIZE": _bool_env(config.reorganize),
        # ---- 显式关闭 benchmark 不测的外部能力 ----
        "ENABLE_INTERNET": "false",
        "ENABLE_CHAT_API": "false",
        "ENABLE_DINGDING_BOT": "false",
        "ENABLE_PREFERENCE_MEMORY": "false",
        "ENABLE_ACTIVATION_MEMORY": "false",
        "NACOS_ENABLE_WATCH": "false",
    }
    qdrant_api_key = os.environ.get(config.vector_db_credential_env)
    if qdrant_api_key:
        values["QDRANT_API_KEY"] = qdrant_api_key
    if openai_settings.base_url:
        values["OPENAI_API_BASE"] = openai_settings.base_url
    if openai_settings.provider == OPENCODEGO_API_PROVIDER:
        values["MEMRADER_PROVIDER_COMPATIBILITY"] = (
            MEMOS_OPENCODEGO_READER_COMPATIBILITY
        )
    return values


def _bool_env(value: bool) -> str:
    """把 Python bool 转成 MemOS 环境变量识别的小写字面量。"""

    return "true" if value else "false"


class MemosRuntime:
    """一个 MemOS product component bundle 及其 typed handler。

    每个 provider 只 `init_server()` 一次，Add/Search handler 共享同一份
    `HandlerDependencies`、同一个 scheduler 和同一个 local tracker；
    绝不一 conversation 一个 runtime。
    """

    def __init__(
        self,
        *,
        config: MemOSConfig,
        openai_settings: OpenAISettings,
        path_settings: PathSettings,
    ) -> None:
        """按 config 构造一次 MemOS runtime，并装配 local task tracker。"""

        self.config = config
        self.identity = config.runtime_identity()
        self._closed = False
        # `scheduler.stop()` 失败后的永久 fail-closed 状态（见 close()）。
        self._close_failed = False
        self._close_error: BaseException | None = None
        _ensure_memos_importable(path_settings)
        # lazy import：绝不 import `memos.api.routers.server_router`，
        # 它会在 module import 期初始化全局 server components。
        from memos.api.handlers.add_handler import AddHandler
        from memos.api.handlers.base_handler import HandlerDependencies
        from memos.api.handlers.component_init import init_server
        from memos.api.handlers.search_handler import SearchHandler

        with _scoped_environment(
            _memos_environment(config, openai_settings, path_settings)
        ):
            components = init_server()
        self.components = components
        self.dependencies = HandlerDependencies.from_init_server(components)
        self.add_handler = AddHandler(self.dependencies)
        self.search_handler = SearchHandler(self.dependencies)
        self.scheduler = self.dependencies.mem_scheduler
        self.naive_mem_cube = self.dependencies.naive_mem_cube
        self.tracker: MemosLocalTaskTracker = install_local_tracker(self.scheduler)

    @property
    def closed(self) -> bool:
        """返回该 runtime 是否已经关闭。"""

        return self._closed

    @property
    def close_failed(self) -> bool:
        """返回该 runtime 是否已因 `scheduler.stop()` 失败而永久不可复用。"""

        return self._close_failed

    @property
    def close_error(self) -> BaseException | None:
        """返回首次 `scheduler.stop()` 失败的原始异常，未失败时为 `None`。"""

        return self._close_error

    def close(self) -> None:
        """收敛 scheduler：先拒绝未完成 task，再 stop 恰好一次。

        **状态只在成功后提交**：pending task 导致拒绝时，本对象不做任何变更，
        因此后台 task 到达终态后同一个 runtime 可以原样重试关闭（pending refusal
        不是 close failure）。

        **`stop()` 失败是永久 fail-closed**：current MemOS
        `BaseSchedulerQueueMixin.stop()` 先由 `stop_consumer()` 把 `_running`
        置 False，再执行 `dispatcher.shutdown()` 与 `dispatcher_monitor.stop()`；
        后两步抛错时 scheduler 可能只关掉了一部分，而第二次调用 upstream
        `stop()` 会因 `_running=False` 直接返回。因此"重试时跳过 stop 并标
        closed"不是幂等，而是把**未证实完全关闭**伪装成成功。这里改为记录
        `_close_failed`/`_close_error`，之后每次 close 都稳定 fail-fast 并链回
        首个异常，绝不标 closed、绝不允许复用。

        Raises:
            ConfigurationError: 该 runtime 先前 `stop()` 已失败，不可安全复用。
        """

        if self._close_failed:
            raise ConfigurationError(
                "MemOS runtime is permanently unusable: a previous "
                "scheduler.stop() failed, so the scheduler may be only partially "
                "shut down and must not be reused or reported as closed"
            ) from self._close_error
        if self._closed:
            return
        # 先拒绝：此调用之前不修改任何状态，保证 pending refusal 完全可重试。
        self.tracker.assert_no_pending_tasks()
        stop = getattr(self.scheduler, "stop", None)
        if callable(stop):
            try:
                stop()
            except BaseException as exc:
                # 首次失败原样上抛（失败必须可见），同时进入永久 poisoned 状态。
                self._close_failed = True
                self._close_error = exc
                raise
        self._closed = True


class _MemosRuntimeOwner:
    """进程内、按完整 config identity 单例的 MemOS runtime 持有者。

    clean retry 可能发生在 provider 构造之前，因此需要一个进程级 owner；但它
    必须：同 config 复用、冲突 config fail-fast、thread-safe、可确定性 reset，
    且不跨 run 复用已关闭 runtime。
    """

    def __init__(self) -> None:
        """创建空的 runtime 持有者。"""

        self._lock = threading.RLock()
        self._runtime: MemosRuntime | None = None

    def acquire(
        self,
        *,
        config: MemOSConfig,
        openai_settings: OpenAISettings,
        path_settings: PathSettings,
        runtime_factory: Any | None = None,
    ) -> MemosRuntime:
        """返回与当前 config 一致的 runtime，冲突或已关闭时 fail-fast。"""

        with self._lock:
            identity = config.runtime_identity()
            existing = self._runtime
            if existing is not None:
                if existing.identity != identity:
                    raise ConfigurationError(
                        "MemOS runtime already exists for a different config "
                        "identity; refusing to build a second runtime in the same "
                        "process"
                    )
                if existing.close_failed:
                    # 永久 fail-closed：既不能像普通 open runtime 那样返回，
                    # 也不能绕过它另建第二份。
                    raise ConfigurationError(
                        "MemOS runtime for this config previously failed to close "
                        "(scheduler.stop() error); refusing to reuse it or build a "
                        "second runtime in the same process"
                    ) from existing.close_error
                if existing.closed:
                    raise ConfigurationError(
                        "MemOS runtime for this config has already been closed; "
                        "refusing to reuse it across runs"
                    )
                return existing
            factory = runtime_factory or MemosRuntime
            runtime = factory(
                config=config,
                openai_settings=openai_settings,
                path_settings=path_settings,
            )
            self._runtime = runtime
            return runtime

    def release(self, runtime: MemosRuntime) -> None:
        """关闭并释放当前 runtime；重复释放对 owner 幂等。

        **只在 `runtime.close()` 成功后才清空引用**：close 因 pending task 被拒绝、
        或 `scheduler.stop()` 抛错时，owner 仍持有该 runtime，异常照常上抛，
        因此不会留下"仍在运行却无人持有"的孤儿。

        已进入永久 fail-closed 的 runtime 由 `close()` 自身稳定 fail-fast，
        因此本方法对它同样是"拒绝并保留引用"，不会误清。

        close 在持锁状态下执行，保证 §2.1.5 的原子性：close 尚未完成时，
        并发 `acquire()` 不会构造第二个同 config runtime。
        """

        with self._lock:
            if self._runtime is not runtime:
                # 已被别处释放：仍要确保该 runtime 自身收敛，且不误清他人引用。
                runtime.close()
                return
            runtime.close()
            self._runtime = None

    def release_current_for_config(self, config: MemOSConfig) -> MemosRuntime | None:
        """关闭并释放 owner 中与该 config 同 identity 的现有 runtime。

        供"clean hook 已 lazy 建好 runtime，但根 provider 自己从未 acquire"的交接
        场景使用（见支线 M4-R1 裁决 §2.2）：

        - owner 为空：no-op 返回 `None`，**不得**为了 cleanup 反向构造 runtime；
        - identity 一致：关闭并释放，返回该 runtime；
        - identity 冲突：fail-fast，绝不关闭别的配置的 runtime；
        - 已永久 fail-closed：由 `close()` 稳定 fail-fast，引用保持不变。

        Returns:
            实际被释放的 runtime；owner 为空时为 `None`。

        Raises:
            ConfigurationError: owner 持有的是另一份 config identity 的 runtime。
        """

        with self._lock:
            runtime = self._runtime
            if runtime is None:
                return None
            if runtime.identity != config.runtime_identity():
                raise ConfigurationError(
                    "MemOS runtime owner holds a different config identity; "
                    "refusing to close another configuration's runtime"
                )
            runtime.close()
            self._runtime = None
            return runtime

    def reset(self) -> None:
        """测试后确定性清空持有者，不调用 scheduler.stop。"""

        with self._lock:
            self._runtime = None


MEMOS_RUNTIME_OWNER = _MemosRuntimeOwner()


def _ensure_memos_importable(path_settings: PathSettings) -> None:
    """把 vendored MemOS 的 `src/` 加入 sys.path，保持 lazy import 语义。"""

    memos_root = path_settings.resolve_third_party_method_path(MEMOS_METHOD_DIRECTORY)
    memos_src = memos_root / "src"
    if not memos_src.is_dir():
        raise ConfigurationError(f"MemOS source directory missing: {memos_src}")
    if str(memos_src) not in sys.path:
        sys.path.insert(0, str(memos_src))


class MemOS(MemoryProvider):
    """MemOS v2.0.25 product typed-handler 协议 v3 provider。"""

    consume_granularity = "session"
    session_memory_report = False
    provenance_granularity = "none"

    def __init__(
        self,
        *,
        config: MemOSConfig,
        path_settings: PathSettings,
        storage_root: Path,
        openai_settings: OpenAISettings | None = None,
        efficiency_collector: EfficiencyCollector | None = None,
        benchmark_name: str | None = None,
        runtime_owner: _MemosRuntimeOwner | None = None,
        runtime_factory: Any | None = None,
    ) -> None:
        """保存构造依赖，延迟到首次 ingest/retrieve 时才构造 MemOS runtime。"""

        config.validate_required_local_resources(path_settings)
        self.config = config
        self.path_settings = path_settings
        self.storage_root = storage_root
        self._openai_settings = openai_settings
        self._efficiency_collector = efficiency_collector
        self.benchmark_name = benchmark_name
        self._runtime_owner = runtime_owner or MEMOS_RUNTIME_OWNER
        self._runtime_factory = runtime_factory
        self._runtime: MemosRuntime | None = None
        self._cleaned = False
        self._task_sequence = 0
        self._sequence_lock = threading.Lock()
        # MemOS async worker 不传播 Python ContextVar。后台 callback 只能先写入
        # 线程安全原始缓冲，待精确 business task 完成后再由调用线程回放到
        # framework collector 的 conversation/question scope。
        self._efficiency_lock = threading.RLock()
        self._efficiency_capture: _MemosEfficiencyCapture | None = None
        self._efficiency_observer_runtime_id: int | None = None

    # ------------------------------------------------------------------
    # runtime / namespace
    # ------------------------------------------------------------------
    def _require_runtime(self) -> MemosRuntime:
        """返回本 provider 的 runtime，必要时构造一次。"""

        if self._runtime is not None:
            self._install_efficiency_observers(self._runtime)
            return self._runtime
        if self._openai_settings is None:
            raise ConfigurationError("MemOS runtime requires OpenAI settings")
        self._runtime = self._runtime_owner.acquire(
            config=self.config,
            openai_settings=self._openai_settings,
            path_settings=self.path_settings,
            runtime_factory=self._runtime_factory,
        )
        self._install_efficiency_observers(self._runtime)
        return self._runtime

    def _install_efficiency_observers(self, runtime: Any) -> None:
        """给 MemOS runtime 安装 LLM/embedding 纯观测钩子。

        MemOS 的 scheduler/reader 会跨多层线程池执行。钩子本身只把成功调用的
        原始事实写入本 provider 的锁保护缓冲，不触碰 framework collector；
        collector 回放由发起 ingest/retrieve 的原线程在精确完成门之后执行。
        """

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        if self._efficiency_observer_runtime_id == id(runtime):
            return
        components = getattr(runtime, "components", None)
        if not isinstance(components, dict):
            # 测试替身 runtime 没有产品 component graph；其算法出口测试不需要
            # 伪造模型调用。真实 MemosRuntime 必有 components。
            return

        mem_reader = components.get("mem_reader")
        llm_candidates = [
            components.get("llm"),
            getattr(mem_reader, "llm", None),
            getattr(mem_reader, "general_llm", None),
            getattr(mem_reader, "image_parser_llm", None),
            getattr(mem_reader, "document_parser_llm", None),
            getattr(mem_reader, "preference_extractor_llm", None),
        ]
        wrapped_llms = 0
        seen: set[int] = set()
        for llm in llm_candidates:
            if llm is None or id(llm) in seen:
                continue
            seen.add(id(llm))
            if not hasattr(llm, "response_callback"):
                continue
            if not getattr(llm, "_memory_benchmark_response_wrapped", False):
                previous_callback = llm.response_callback

                def _response_callback(
                    owner: Any,
                    response: Any,
                    request_body: dict[str, Any],
                    result: Any,
                    *,
                    _previous: Any = previous_callback,
                ) -> None:
                    """保留既有 callback，再把成功响应投递给当前 adapter sink。"""

                    if _previous is not None:
                        _previous(owner, response, request_body, result)
                    sink = getattr(owner, "_memory_benchmark_response_sink", None)
                    if callable(sink):
                        sink(response, request_body, result)

                llm.response_callback = _response_callback
                llm._memory_benchmark_response_wrapped = True
            llm._memory_benchmark_response_sink = self._capture_llm_call
            wrapped_llms += 1

        embedder_candidates = [
            components.get("embedder"),
            getattr(mem_reader, "embedder", None),
            getattr(components.get("searcher"), "embedder", None),
            getattr(components.get("memory_manager"), "embedder", None),
        ]
        wrapped_embedders = 0
        seen.clear()
        for embedder in embedder_candidates:
            if embedder is None or id(embedder) in seen:
                continue
            seen.add(id(embedder))
            original_embed = getattr(embedder, "embed", None)
            if not callable(original_embed):
                continue
            if not getattr(embedder, "_memory_benchmark_embedding_wrapped", False):

                def _wrapped_embed(
                    texts: Any,
                    *args: Any,
                    _owner: Any = embedder,
                    _original: Any = original_embed,
                    **kwargs: Any,
                ) -> Any:
                    """原样调用 embedding，成功后仅投递输入与真实 wall latency。"""

                    started_ns = perf_counter_ns()
                    result = _original(texts, *args, **kwargs)
                    latency_ms = _elapsed_ms(started_ns)
                    normalized = (
                        [texts]
                        if isinstance(texts, str)
                        else list(texts or [])
                    )
                    sink = getattr(
                        _owner,
                        "_memory_benchmark_embedding_sink",
                        None,
                    )
                    if callable(sink):
                        sink(_owner, normalized, latency_ms)
                    return result

                embedder.embed = _wrapped_embed
                embedder._memory_benchmark_embedding_wrapped = True
            embedder._memory_benchmark_embedding_sink = (
                self._capture_embedding_call
            )
            wrapped_embedders += 1

        if wrapped_llms == 0:
            raise ConfigurationError(
                "MemOS efficiency observation requires patched OpenAILLM "
                "response_callback support"
            )
        if wrapped_embedders == 0:
            raise ConfigurationError(
                "MemOS efficiency observation requires at least one product "
                "embedder"
            )
        self._efficiency_observer_runtime_id = id(runtime)

    def _begin_efficiency_capture(self, stage: EfficiencyStage) -> bool:
        """在有匹配 framework scope 时开启一次跨线程原始调用缓冲。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return False
        scope_type = collector.active_scope_type()
        if stage is EfficiencyStage.MEMORY_BUILD:
            if scope_type != "conversation":
                return False
        elif stage is EfficiencyStage.RETRIEVAL:
            if scope_type not in {"conversation", "question"}:
                return False
        else:  # pragma: no cover - 本 adapter 只负责 build/retrieval
            raise ConfigurationError(
                f"MemOS efficiency capture stage is unsupported: {stage.value}"
            )
        with self._efficiency_lock:
            if self._efficiency_capture is not None:
                raise ConfigurationError(
                    "MemOS efficiency capture cannot overlap another operation"
                )
            self._efficiency_capture = _MemosEfficiencyCapture(stage=stage)
        return True

    def _capture_llm_call(
        self,
        response: Any,
        request_body: dict[str, Any],
        result: Any,
    ) -> None:
        """由任意 MemOS 后台线程追加一次成功 LLM 调用。"""

        with self._efficiency_lock:
            capture = self._efficiency_capture
            if capture is None:
                return
            capture.llm_calls.append(
                _MemosRawLLMCall(
                    messages=request_body.get("messages"),
                    output_text=str(result or ""),
                    usage=getattr(response, "usage", None),
                )
            )

    def _capture_embedding_call(
        self,
        embedder: Any,
        texts: list[Any],
        latency_ms: float,
    ) -> None:
        """由任意 MemOS 后台线程追加一次成功 embedding 调用。"""

        with self._efficiency_lock:
            capture = self._efficiency_capture
            if capture is None:
                return
            capture.embedding_calls.append(
                _MemosRawEmbeddingCall(
                    embedder=embedder,
                    texts=tuple(str(text) for text in texts),
                    latency_ms=latency_ms,
                )
            )

    def _discard_efficiency_capture(self, stage: EfficiencyStage) -> None:
        """算法操作失败时丢弃本操作的未提交观测，避免污染下一 scope。"""

        with self._efficiency_lock:
            capture = self._efficiency_capture
            if capture is None:
                return
            if capture.stage is not stage:
                raise ConfigurationError(
                    "MemOS efficiency capture stage changed before discard"
                )
            self._efficiency_capture = None

    def _finish_efficiency_capture(self, stage: EfficiencyStage) -> None:
        """弹出原始缓冲，并在当前调用线程的 framework scope 中精确回放。"""

        collector = self._efficiency_collector
        if collector is None or not collector.enabled:
            return
        with self._efficiency_lock:
            capture = self._efficiency_capture
            if capture is None or capture.stage is not stage:
                raise ConfigurationError(
                    "MemOS efficiency capture is missing or has the wrong stage"
                )
            self._efficiency_capture = None

        with collector.operation_stage(stage):
            for call in capture.llm_calls:
                api_input, api_output = extract_api_token_usage(call.usage)
                usage = resolve_token_usage(
                    api_input_tokens=api_input,
                    api_output_tokens=api_output,
                    prompt_text=_memos_messages_to_text(call.messages),
                    output_text=call.output_text,
                    tokenizer=_TiktokenCounter(self.config.llm_model),
                )
                collector.record_llm_call(
                    model_id=MEMOS_LLM_MODEL_ID,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    token_measurement_source=usage.source,
                )
            for call in capture.embedding_calls:
                collector.record_embedding_call(
                    model_id=MEMOS_EMBEDDING_MODEL_ID,
                    input_tokens=_count_memos_embedding_tokens(
                        call.embedder,
                        call.texts,
                    ),
                    latency_ms=call.latency_ms,
                    token_measurement_source=MeasurementSource.TOKENIZER_ESTIMATE,
                    latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
                )

    def _namespace(self, isolation_key: str, *, locomo_view: str | None = None) -> str:
        """返回该 isolation（及可选 LoCoMo speaker 视角）的确定性 namespace。"""

        namespace_isolation_key = isolation_key
        if locomo_view is not None:
            if locomo_view not in MEMOS_LOCOMO_VIEW_NAMES:
                raise ConfigurationError(
                    f"Unknown MemOS LoCoMo view: {locomo_view!r}"
                )
            namespace_isolation_key = f"{isolation_key}|memos-locomo-{locomo_view}"
        return build_memos_namespace(
            storage_root_relative=self._storage_root_relative(),
            isolation_key=namespace_isolation_key,
        )

    def _conversation_namespaces(self, isolation_key: str) -> tuple[tuple[str, str], ...]:
        """返回本 benchmark 的全部逻辑 namespace。

        LoCoMo 按官方 harness 建两个 speaker 视角；其余四格仍是一
        conversation 一 namespace。
        """

        if self.benchmark_name == "locomo":
            return tuple(
                (
                    view,
                    self._namespace(isolation_key, locomo_view=view),
                )
                for view in MEMOS_LOCOMO_VIEW_NAMES
            )
        return (("default", self._namespace(isolation_key)),)

    def _storage_root_relative(self) -> str:
        """返回 run 独占 storage_root 的项目相对稳定身份，不含绝对机器路径。"""

        try:
            return self.storage_root.relative_to(
                self.path_settings.project_root
            ).as_posix()
        except ValueError as exc:
            raise ConfigurationError(
                "MemOS storage_root must live inside the project root so the "
                f"namespace stays machine-independent: {self.storage_root}"
            ) from exc

    def _next_business_task_id(self, namespace: str, session_id: str | None) -> str:
        """生成本次 add 的唯一、确定性可审计 business task id。"""

        with self._sequence_lock:
            self._task_sequence += 1
            sequence = self._task_sequence
        session_slug = _NAMESPACE_SAFE_PATTERN.sub("", (session_id or "none").lower())
        return f"{namespace}-s{session_slug}-{sequence:06d}"

    # ------------------------------------------------------------------
    # ingest
    # ------------------------------------------------------------------
    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """把一个 session batch 写入 typed `AddHandler`，并等待全部精确终态。

        LoCoMo 忠实复刻官方 product harness 的数据面：同一公开 session 写入
        speaker_a / speaker_b 两个 namespace，两个视角 role 互换；每个视角
        按位置每 2 条发一个 add，奇数尾保持 singleton。全部 add 先提交，再按
        business task 精确等待，避免把官方 async 请求误串行化成
        “上一 pair fine 完成后才提交下一 pair”。

        其余 benchmark 仍以完整 session 发一个 add。尤其 LongMemEval 主轨
        不采用当前官方 evaluation wrapper 的 `batch_size=2` 与 `[:8000]`
        截断；该 wrapper 只属于后续 `author_longmemeval` 校准身份。
        """

        if not isinstance(unit, SessionBatch):
            raise ConfigurationError("MemOS provider only accepts SessionBatch")

        submitted: list[tuple[str, str]] = []
        source_message_count = len(unit.events)
        written_message_count = 0

        if self.benchmark_name == "locomo":
            speaker_identity = self._register_locomo_view_sidecar(unit)
            view_plans = [
                (
                    view,
                    self._namespace(unit.isolation_key, locomo_view=view),
                    self._build_messages(
                        unit,
                        speaker_roles=self._locomo_speaker_roles(
                            speaker_identity,
                            view=view,
                        ),
                    ),
                )
                for view in MEMOS_LOCOMO_VIEW_NAMES
            ]
        else:
            view_plans = [
                (
                    "default",
                    self._namespace(unit.isolation_key),
                    self._build_messages(unit, speaker_roles=None),
                )
            ]

        for view, _, messages in view_plans:
            if not messages:
                raise ConfigurationError(
                    "MemOS session batch produced no message: "
                    f"{unit.isolation_key}/{unit.session_id}/{view}"
                )

        runtime = self._require_runtime()
        from memos.api.product_models import APIADDRequest

        capture_started = self._begin_efficiency_capture(
            EfficiencyStage.MEMORY_BUILD
        )
        try:
            for view, namespace, messages in view_plans:
                chunks = (
                    _message_chunks(messages, MEMOS_LOCOMO_OFFICIAL_BATCH_SIZE)
                    if self.benchmark_name == "locomo"
                    else (messages,)
                )
                for chunk in chunks:
                    business_task_id = self._next_business_task_id(
                        namespace,
                        unit.session_id,
                    )
                    add_request = APIADDRequest(
                        user_id=namespace,
                        writable_cube_ids=[namespace],
                        session_id=unit.session_id,
                        task_id=business_task_id,
                        messages=chunk,
                        async_mode=self.config.add_async_mode,
                        mode=self.config.add_mode,
                    )
                    runtime.add_handler.handle_add_memories(add_request)
                    submitted.append((namespace, business_task_id))
                    written_message_count += len(chunk)

            terminal_task_count = 0
            for namespace, business_task_id in submitted:
                terminal = runtime.tracker.wait_for_business_task(
                    user_id=namespace,
                    business_task_id=business_task_id,
                    timeout_seconds=self.config.task_timeout_seconds,
                )
                terminal_task_count += len(terminal)
        except BaseException:
            if capture_started:
                self._discard_efficiency_capture(EfficiencyStage.MEMORY_BUILD)
            raise
        else:
            if capture_started:
                self._finish_efficiency_capture(EfficiencyStage.MEMORY_BUILD)

        return IngestResult(
            unit_ref=SessionRef(
                isolation_key=unit.isolation_key,
                session_id=unit.session_id,
            ),
            metadata={
                "method": "memos",
                "namespaces": [namespace for _, namespace in self._conversation_namespaces(
                    unit.isolation_key
                )],
                "business_task_ids": [
                    business_task_id for _, business_task_id in submitted
                ],
                "source_message_count": source_message_count,
                "written_message_count": written_message_count,
                "add_request_count": len(submitted),
                "terminal_task_count": terminal_task_count,
            },
        )

    def _build_messages(
        self,
        unit: SessionBatch,
        *,
        speaker_roles: dict[str, str] | None,
    ) -> list[dict[str, Any]]:
        """把 session batch 的每个保留 event 渲染成恰好一条 MemOS message。

        `chat_time` key 始终存在：canonical 契约已是 `turn → session → None`，
        无时间时写显式 `None`，不用 question time、兄弟 turn 或 wall clock 补值。
        """

        messages: list[dict[str, Any]] = []
        for event in unit.events:
            content = self._render_content(event, speaker_roles)
            if not content.strip():
                raise ConfigurationError(
                    "MemOS refuses to ingest an empty turn content "
                    f"(would lose chat_time/message_id upstream): {event.turn_id}"
                )
            messages.append(
                {
                    "role": self._resolve_role(event, speaker_roles),
                    "content": content,
                    "chat_time": event.timestamp,
                    "message_id": event.turn_id,
                }
            )
        return messages

    def _resolve_role(
        self,
        event: TurnEvent,
        speaker_roles: dict[str, str] | None,
    ) -> str:
        """解析该 event 的 MemOS role。

        LoCoMo 固定 `speaker_a → user`、`speaker_b → assistant`，与谁先发言无关；
        其余 benchmark 只接受 canonical `role in {user, assistant}` 并原样保留。
        """

        if speaker_roles is not None:
            speaker = event.speaker_name or event.role
            role = speaker_roles.get(speaker)
            if role is None:
                raise ConfigurationError(
                    "MemOS LoCoMo turn speaker is not declared in "
                    f"speaker_a/speaker_b: {speaker}"
                )
            return role
        if event.role not in _ALLOWED_ROLES:
            raise ConfigurationError(
                f"MemOS only accepts canonical user/assistant roles: {event.role!r} "
                f"({event.turn_id})"
            )
        return event.role

    def _render_content(
        self,
        event: TurnEvent,
        speaker_roles: dict[str, str] | None,
    ) -> str:
        """还原原始 content 并按共享契约拼接 image caption。

        事件流已用 `(image description: ...)` 渲染过一次，因此这里从
        `metadata["original_content"]` + `turn_images` 重建，再交给共享
        `turn_text_with_images()` 统一输出 `[Sharing image that shows: ...]`，
        不二次拼接、也不把 caption 的 path/query/URL 带进 content。
        """

        turn = Turn(
            turn_id=event.turn_id,
            speaker=event.speaker_name or event.role,
            normalized_role=event.role if event.role in _ALLOWED_ROLES else None,
            content=_original_content_from_event(event),
            turn_time=event.timestamp,
            images=_images_from_event(event),
        )
        rendered = turn_text_with_images(turn)
        if speaker_roles is None:
            return rendered
        speaker = event.speaker_name or event.role
        return f"{speaker}: {rendered}"

    @staticmethod
    def _locomo_speaker_identity(unit: SessionBatch) -> dict[str, str]:
        """从 LoCoMo 公开 conversation metadata 读取两个真实 speaker。"""

        metadata: dict[str, Any] = {}
        for event in unit.events:
            candidate = event.metadata.get("conversation_metadata")
            if isinstance(candidate, dict):
                metadata = candidate
                break
        speaker_a = metadata.get("speaker_a")
        speaker_b = metadata.get("speaker_b")
        speaker_a = speaker_a.strip() if isinstance(speaker_a, str) else ""
        speaker_b = speaker_b.strip() if isinstance(speaker_b, str) else ""
        if not speaker_a or not speaker_b:
            raise ConfigurationError(
                "MemOS LoCoMo conversation metadata must declare non-empty "
                "speaker_a and speaker_b"
            )
        if speaker_a == speaker_b:
            raise ConfigurationError(
                "MemOS LoCoMo speaker_a and speaker_b must be distinct"
            )
        return {"speaker_a": speaker_a, "speaker_b": speaker_b}

    @staticmethod
    def _locomo_speaker_roles(
        speaker_identity: dict[str, str],
        *,
        view: str,
    ) -> dict[str, str]:
        """按官方正/反视角构造真实 speaker→MemOS role 映射。"""

        speaker_a = speaker_identity["speaker_a"]
        speaker_b = speaker_identity["speaker_b"]
        if view == "speaker_a":
            return {speaker_a: "user", speaker_b: "assistant"}
        if view == "speaker_b":
            return {speaker_a: "assistant", speaker_b: "user"}
        raise ConfigurationError(f"Unknown MemOS LoCoMo view: {view!r}")

    def _locomo_view_sidecar_path(self, isolation_key: str) -> Path:
        """返回 LoCoMo 双视角 speaker identity 的持久化 sidecar 路径。"""

        digest = hashlib.sha256(isolation_key.encode("utf-8")).hexdigest()
        return self.storage_root / "locomo-view-sidecars" / f"{digest}.json"

    def _register_locomo_view_sidecar(self, unit: SessionBatch) -> dict[str, str]:
        """创建或验证 LoCoMo speaker sidecar，供 resume 后双路 readout 使用。"""

        speaker_identity = self._locomo_speaker_identity(unit)
        payload = {
            "schema_version": MEMOS_LOCOMO_VIEW_SIDECAR_SCHEMA_VERSION,
            "isolation_key": unit.isolation_key,
            **speaker_identity,
        }
        path = self._locomo_view_sidecar_path(unit.isolation_key)
        if path.is_file():
            existing = self._read_locomo_view_sidecar(path)
            if existing != payload:
                raise ConfigurationError(
                    "MemOS LoCoMo speaker identity conflicts with persisted "
                    f"dual-view sidecar: {unit.isolation_key}"
                )
        else:
            atomic_write_json(path, payload)
        return speaker_identity

    def _load_locomo_view_sidecar(self, isolation_key: str) -> dict[str, str]:
        """读取 resume 必需的 LoCoMo 双视角 sidecar，缺失时 fail-fast。"""

        path = self._locomo_view_sidecar_path(isolation_key)
        if not path.is_file():
            raise ConfigurationError(
                "MemOS LoCoMo dual-view state is missing its speaker sidecar; "
                "start a new run instead of silently guessing speaker identity"
            )
        payload = self._read_locomo_view_sidecar(path)
        if payload["isolation_key"] != isolation_key:
            raise ConfigurationError(
                f"MemOS LoCoMo sidecar isolation mismatch: {path}"
            )
        return {
            "speaker_a": payload["speaker_a"],
            "speaker_b": payload["speaker_b"],
        }

    @staticmethod
    def _read_locomo_view_sidecar(path: Path) -> dict[str, str]:
        """读取并强校验 LoCoMo 双视角 sidecar。"""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(
                f"Invalid MemOS LoCoMo dual-view sidecar: {path}"
            ) from exc
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version")
            != MEMOS_LOCOMO_VIEW_SIDECAR_SCHEMA_VERSION
            or not all(
                isinstance(payload.get(key), str) and payload[key].strip()
                for key in ("isolation_key", "speaker_a", "speaker_b")
            )
            or payload["speaker_a"] == payload["speaker_b"]
        ):
            raise ConfigurationError(
                f"Invalid MemOS LoCoMo dual-view sidecar schema: {path}"
            )
        return payload

    # ------------------------------------------------------------------
    # retrieve
    # ------------------------------------------------------------------
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """只调 typed `SearchHandler`，把产品返回顺序原样映射为 RetrievalResult。

        LoCoMo 对两个 speaker namespace 各发一次同参数检索，保留每一路内部
        产品顺序，再按官方 `speaker_a → speaker_b` 分区合并；不伪造跨 namespace
        的全局 rank。其余 benchmark 仍为单路检索。
        """

        speaker_identity = (
            self._load_locomo_view_sidecar(query.isolation_key)
            if self.benchmark_name == "locomo"
            else None
        )
        runtime = self._require_runtime()
        namespaces = self._conversation_namespaces(query.isolation_key)
        items_by_view: dict[str, tuple[RetrievedItem, ...]] = {}
        all_items: list[RetrievedItem] = []
        capture_started = self._begin_efficiency_capture(
            EfficiencyStage.RETRIEVAL
        )
        try:
            for view, namespace in namespaces:
                response = runtime.search_handler.handle_search_memories(
                    self._build_search_request(query, namespace)
                )
                view_items = _items_from_search_response(
                    response,
                    extra_metadata=(
                        {"memos_locomo_view": view}
                        if self.benchmark_name == "locomo"
                        else None
                    ),
                )
                items_by_view[view] = view_items
                all_items.extend(view_items)
        except BaseException:
            if capture_started:
                self._discard_efficiency_capture(EfficiencyStage.RETRIEVAL)
            raise
        else:
            if capture_started:
                self._finish_efficiency_capture(EfficiencyStage.RETRIEVAL)

        items = tuple(all_items)
        if self.benchmark_name == "locomo":
            if speaker_identity is None:  # pragma: no cover - 上方同条件已强加载
                raise ConfigurationError("MemOS LoCoMo speaker identity is unavailable")
            formatted_memory = (
                _format_locomo_dual_view_memory(
                    speaker_identity=speaker_identity,
                    speaker_a_items=items_by_view["speaker_a"],
                    speaker_b_items=items_by_view["speaker_b"],
                )
                if items
                else ""
            )
        else:
            formatted_memory = "\n\n".join(item.content for item in items)
        return RetrievalResult(
            formatted_memory=formatted_memory or MEMOS_EMPTY_MEMORY_SENTINEL,
            items=items,
            metadata={
                "method": "memos",
                "prompt_track": "unified",
                "namespaces": [namespace for _, namespace in namespaces],
                "retrieval_path": "SearchHandler.handle_search_memories",
                "search_mode": self.config.search_mode,
                "retrieval_top_k_semantics": (
                    "per_locomo_speaker_view"
                    if self.benchmark_name == "locomo"
                    else "single_namespace"
                ),
                "reference_time_effect": MEMOS_REFERENCE_TIME_EFFECT,
                "provenance_granularity": "none",
            },
            evidence=_memos_retrieval_evidence(),
        )

    def _build_search_request(
        self,
        query: RetrievalQuery,
        namespace: str,
    ) -> Any:
        """为一个确定 namespace 构造 typed `APISearchRequest`。"""

        from memos.api.product_models import APISearchRequest

        return APISearchRequest(
            query=query.query_text,
            user_id=namespace,
            readable_cube_ids=[namespace],
            mode=self.config.search_mode,
            top_k=query.top_k,
            relativity=self.config.search_relativity,
            dedup=self.config.search_dedup,
            rerank=self.config.search_rerank,
            include_preference=self.config.include_preference,
            search_tool_memory=self.config.search_tool_memory,
            include_skill_memory=self.config.include_skill_memory,
            neighbor_discovery=self.config.neighbor_discovery,
            internet_search=self.config.internet_search,
            # 框架主轨故意不给 method 额外对话历史；官方 wrapper 的 None 口径
            # 留给 author profile，不能暗中进入主表。
            chat_history=[],
            filter=None,
            session_id=None,
            reference_time=query.question_time,
        )

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------
    def cleanup(self) -> None:
        """收敛 runtime：先拒绝 pending task，再对 scheduler stop 恰好一次。

        **状态只在成功后提交**：release 抛错（pending task 拒绝、`stop()` 失败）时，
        `_cleaned` 与 `_runtime` 保持不变，异常照常上抛；后台 task 到达终态后，
        对同一个 provider 再次 `cleanup()` 会真正关闭，且 `scheduler.stop()`
        总计仍只发生一次。

        本 provider 自己从未 `_require_runtime()` 时（例如 failed-ingest clean hook
        用临时 provider 先建好了共享 runtime），仍要接管并关闭 owner 中**同
        identity**的现有 runtime；owner 为空则保持 no-op，绝不为了 cleanup 反向
        构造 runtime。

        重复 cleanup 对 adapter 自身幂等，且不会二次调用 `scheduler.stop()`。
        """

        if self._cleaned:
            return
        runtime = self._runtime
        if runtime is None:
            # 交接路径：owner 里可能有 clean hook 建好的同 config runtime。
            self._runtime_owner.release_current_for_config(self.config)
            self._cleaned = True
            return
        self._runtime_owner.release(runtime)
        # 走到这里说明 release 成功，才允许提交状态。
        self._runtime = None
        self._cleaned = True


def clean_memos_conversation_state(
    *,
    provider: MemOS,
    isolation_key: str,
) -> None:
    """namespace-scoped 清理一个 failed_ingest conversation 的 MemOS 状态。

    只走 `DeleteMemoryRequest(writable_cube_ids=[namespace], user_id=namespace)`；
    LoCoMo 先对两个 namespace 做统一 pending preflight，再逐一删除并读回验空；
    绝不调用 `delete_by_memory_ids()`，绝不无 namespace 清全库，也绝不把 handler
    返回的 failure 当成功。删除前先确认本 process tracker 没有该 namespace 的
    pending task，删除后以重新读取为空作为完成后置条件。
    """

    runtime = provider._require_runtime()
    namespaces = [
        namespace
        for _, namespace in provider._conversation_namespaces(isolation_key)
    ]
    # 必须在第一次 delete 前把全部 namespace 都检查完；否则 view A 已删、
    # view B 仍 pending 时会制造可避免的半清理。
    for namespace in namespaces:
        _require_no_pending_tasks_for_namespace(runtime.tracker, namespace)

    from memos.api.handlers.memory_handler import (
        handle_delete_memories,
        handle_get_memories,
    )
    from memos.api.product_models import DeleteMemoryRequest, GetMemoryRequest

    for namespace in namespaces:
        delete_response = handle_delete_memories(
            DeleteMemoryRequest(
                writable_cube_ids=[namespace],
                user_id=namespace,
            ),
            runtime.naive_mem_cube,
        )
        status = (getattr(delete_response, "data", None) or {}).get("status")
        if status != "success":
            raise ConfigurationError(
                f"MemOS namespace-scoped delete failed for {namespace}: "
                f"status={status!r}"
            )
        get_response = handle_get_memories(
            GetMemoryRequest(
                mem_cube_id=namespace,
                user_id=namespace,
                include_preference=False,
                include_tool_memory=False,
                include_skill_memory=False,
            ),
            runtime.naive_mem_cube,
        )
        _require_empty_text_memory(get_response, namespace)

    if provider.benchmark_name == "locomo":
        provider._locomo_view_sidecar_path(isolation_key).unlink(missing_ok=True)


def _require_no_pending_tasks_for_namespace(
    tracker: MemosLocalTaskTracker,
    namespace: str,
) -> None:
    """拒绝在该 namespace 仍有 pending task 时执行删除。

    `TaskRecord.to_payload()` 不导出 `user_id`，只导出 `mem_cube_id`；本 adapter
    的拓扑里 namespace == user_id == cube_id，因此按 `mem_cube_id` 判定即为
    namespace scope。`mem_cube_id` 缺失时作用域不可判定，对删除守门一律从严拒绝。
    """

    pending = [
        task
        for task in tracker.pending_tasks()
        if task.get("mem_cube_id") in (namespace, None)
    ]
    if pending:
        raise ConfigurationError(
            f"MemOS refuses to clean namespace {namespace}: "
            f"{len(pending)} background task(s) still pending"
        )


def _require_empty_text_memory(get_response: Any, namespace: str) -> None:
    """校验 clean 后该 namespace 的 text memory 确实为空。"""

    data = getattr(get_response, "data", None) or {}
    buckets = data.get("text_mem") or []
    for bucket in buckets:
        memories = bucket.get("memories") or []
        total_nodes = bucket.get("total_nodes")
        if memories or total_nodes:
            raise ConfigurationError(
                f"MemOS namespace {namespace} still holds memories after clean: "
                f"memories={len(memories)}, total_nodes={total_nodes!r}"
            )


def _memos_retrieval_evidence() -> RetrievalEvidence:
    """返回 MemOS 首版逐题 retrieval evidence 陈述。

    MemOS 的 fine memory 是 window 生成物：`metadata.sources[].message_id` 只
    证明该 source 参与了生成窗口，不证明生成后的 current memory 仍语义承载每个
    source fact；真实 Neo4j/Qdrant + MMR/rerank 的稳定次序也尚未 B11 一手验证。
    因此两项一律 pending，不因 `source_turn_ids` 存在就升级 Recall/NDCG。
    """

    return RetrievalEvidence(
        semantic_provenance=EvidenceAssertion(
            status="pending",
            reason_code="memos_generated_memory_semantic_lineage_unverified",
            reason=(
                "MemOS fine memories are generated from a whole read window; "
                "metadata.sources[].message_id proves a source turn entered that "
                "window, not that the resulting memory still semantically carries "
                "each source fact."
            ),
        ),
        provenance_granularity="none",
        stable_ranking=EvidenceAssertion(
            status="pending",
            reason_code="memos_product_rerank_stability_unverified",
            reason=(
                "The product search path combines Neo4j/Qdrant recall with MMR "
                "dedup and reranking; its ordering stability has not been verified "
                "first-hand against real backing services."
            ),
        ),
    )


def _message_chunks(
    messages: list[dict[str, Any]],
    chunk_size: int,
) -> tuple[list[dict[str, Any]], ...]:
    """按位置切分 message，奇数尾保持 singleton，不制造 placeholder。"""

    if chunk_size < 1:
        raise ConfigurationError("MemOS message chunk_size must be positive")
    return tuple(
        messages[index : index + chunk_size]
        for index in range(0, len(messages), chunk_size)
    )


def _format_locomo_dual_view_memory(
    *,
    speaker_identity: dict[str, str],
    speaker_a_items: tuple[RetrievedItem, ...],
    speaker_b_items: tuple[RetrievedItem, ...],
) -> str:
    """按官方 LoCoMo MemOS readout 的双 speaker 槽位格式化检索结果。"""

    speaker_a_memory = "\n".join(item.content for item in speaker_a_items)
    speaker_b_memory = "\n".join(item.content for item in speaker_b_items)
    return (
        f"Memories for user {speaker_identity['speaker_a']}:\n\n"
        f"    {speaker_a_memory}\n\n"
        f"Memories for user {speaker_identity['speaker_b']}:\n\n"
        f"    {speaker_b_memory}"
    )


def _items_from_search_response(
    response: Any,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> tuple[RetrievedItem, ...]:
    """按产品返回顺序扁平化 `data["text_mem"]` 的所有 bucket。

    不做二次排序、不 set 化、不再截断一次；id/content 缺失与非数值 score 一律
    fail-fast，避免把故障伪装成合法结果。
    """

    data = getattr(response, "data", None) or {}
    buckets = data.get("text_mem")
    if buckets is None:
        raise ConfigurationError("MemOS search response has no text_mem bucket list")
    if not isinstance(buckets, list):
        raise ConfigurationError(
            f"MemOS search response text_mem must be a list, got {type(buckets).__name__}"
        )
    items: list[RetrievedItem] = []
    for bucket in buckets:
        if not isinstance(bucket, dict):
            raise ConfigurationError(
                f"MemOS text_mem bucket must be a mapping, got {type(bucket).__name__}"
            )
        memories = bucket.get("memories")
        if memories is None:
            continue
        if not isinstance(memories, list):
            raise ConfigurationError(
                "MemOS text_mem bucket memories must be a list, got "
                f"{type(memories).__name__}"
            )
        for memory in memories:
            items.append(
                _retrieved_item_from_memory(
                    memory,
                    extra_metadata=extra_metadata,
                )
            )
    return tuple(items)


def _retrieved_item_from_memory(
    memory: Any,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> RetrievedItem:
    """把一条产品 memory 映射为公开 RetrievedItem，剥离 embedding 等内部对象。"""

    if not isinstance(memory, dict):
        raise ConfigurationError(
            f"MemOS memory item must be a mapping, got {type(memory).__name__}"
        )
    metadata = memory.get("metadata")
    if not isinstance(metadata, dict):
        raise ConfigurationError("MemOS memory item is missing a metadata mapping")
    item_id = memory.get("id")
    if not isinstance(item_id, str) or not item_id.strip():
        raise ConfigurationError("MemOS memory item is missing a non-empty id")
    content = memory.get("memory")
    if not isinstance(content, str) or not content.strip():
        raise ConfigurationError(
            f"MemOS memory item {item_id} is missing non-empty memory text"
        )
    score = metadata.get("relativity")
    if score is not None and not isinstance(score, (int, float)):
        raise ConfigurationError(
            f"MemOS memory item {item_id} has a non-numeric relativity: {score!r}"
        )
    if isinstance(score, bool):
        raise ConfigurationError(
            f"MemOS memory item {item_id} has a non-numeric relativity: {score!r}"
        )
    return RetrievedItem(
        item_id=item_id,
        content=content,
        score=float(score) if score is not None else None,
        # created_at 是 current metadata 里唯一一手定义的时间字段；其余不猜。
        timestamp=_optional_text(metadata.get("created_at")),
        source_turn_ids=_source_turn_ids(metadata),
        metadata={
            **_public_memory_metadata(metadata),
            **(extra_metadata or {}),
        },
    )


def _source_turn_ids(metadata: dict[str, Any]) -> tuple[str, ...]:
    """按产品顺序读取 `sources[].message_id` 并稳定去重。"""

    sources = metadata.get("sources")
    if not isinstance(sources, list):
        return ()
    ordered: list[str] = []
    seen: set[str] = set()
    for source in sources:
        if not isinstance(source, dict):
            continue
        message_id = source.get("message_id")
        if not isinstance(message_id, str) or not message_id.strip():
            continue
        if message_id in seen:
            continue
        seen.add(message_id)
        ordered.append(message_id)
    return tuple(ordered)


def _public_memory_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    """保留公开审计字段，移除 embedding 与不可序列化内部对象。"""

    public: dict[str, Any] = {}
    for key, value in metadata.items():
        if key == "embedding":
            continue
        if _is_json_safe(value):
            public[key] = value
    return public


def _is_json_safe(value: Any) -> bool:
    """判定该值是否为可直接写入 artifact 的公开 JSON 结构。"""

    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, list):
        return all(_is_json_safe(entry) for entry in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_json_safe(entry)
            for key, entry in value.items()
        )
    return False


def _optional_text(value: Any) -> str | None:
    """把公开时间字段规整为非空字符串或 None。"""

    if isinstance(value, str) and value.strip():
        return value
    return None


def _original_content_from_event(event: TurnEvent) -> str:
    """读取 caption 渲染前的原始 turn 文本。"""

    original = event.metadata.get("original_content")
    return original if isinstance(original, str) else event.content


def _images_from_event(event: TurnEvent) -> list[ImageRef]:
    """从 v3 event metadata 恢复公开图片引用。"""

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


def _elapsed_ms(started_ns: int) -> float:
    """把 perf_counter_ns 起点转换为非负毫秒。"""

    return max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)


def _memos_messages_to_text(messages: Any) -> str:
    """把 MemOS/OpenAI message payload 稳定转成 tokenizer 输入文本。"""

    if isinstance(messages, list):
        parts: list[str] = []
        for message in messages:
            if isinstance(message, dict):
                role = str(message.get("role") or "")
                content = message.get("content")
                if isinstance(content, str):
                    parts.append(f"{role}: {content}")
                else:
                    parts.append(
                        f"{role}: "
                        + json.dumps(
                            content,
                            ensure_ascii=False,
                            sort_keys=True,
                            default=str,
                        )
                    )
            else:
                parts.append(str(message))
        return "\n".join(parts)
    return str(messages or "")


def _count_memos_embedding_tokens(
    embedder: Any,
    texts: tuple[str, ...],
) -> int:
    """按 MemOS 实际 SentenceTransformer 截断链估算本批输入 token。

    先复用 upstream `_truncate_texts()` 的字符上限，再按模型 tokenizer 与
    `max_seq_length` 做和实际 encode 相同的 token 截断；因此来源只能标成
    `tokenizer_estimate`，不能冒充 API usage。
    """

    truncated = list(texts)
    truncate = getattr(embedder, "_truncate_texts", None)
    if callable(truncate):
        truncated = [str(text) for text in truncate(list(texts))]
    model = getattr(embedder, "model", None)
    tokenizer = getattr(model, "tokenizer", None)
    if tokenizer is None or not hasattr(tokenizer, "encode"):
        raise ConfigurationError(
            "MemOS local embedding token counting requires "
            "embedder.model.tokenizer.encode"
        )
    max_length = getattr(model, "max_seq_length", None)
    total = 0
    for text in truncated:
        if isinstance(max_length, int) and max_length > 0:
            encoded = tokenizer.encode(
                text,
                truncation=True,
                max_length=max_length,
            )
        else:
            encoded = tokenizer.encode(text)
        total += len(encoded)
    return total


class _TiktokenCounter:
    """按 OpenAI-compatible 模型名计数 token 的轻量 wrapper。"""

    def __init__(self, model_name: str) -> None:
        """保存模型名，encoding 懒加载以避免无观测路径额外开销。"""

        self.model_name = model_name
        self._encoding: Any | None = None

    def count_tokens(self, text: str) -> int:
        """返回文本 token 数；未知模型回退到 cl100k_base。"""

        if self._encoding is None:
            try:
                import tiktoken
            except Exception as exc:  # pragma: no cover - 依赖由项目锁定
                raise ConfigurationError(
                    "tiktoken is required for MemOS token estimation"
                ) from exc
            try:
                self._encoding = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text or "", disallowed_special=()))


def build_memos_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 MemOS 官方源码 + patch + wrapper 的稳定身份。"""

    settings = path_settings or load_path_settings()
    memos_root = settings.resolve_third_party_method_path(MEMOS_METHOD_DIRECTORY)
    source_files = [memos_root / relative for relative in MEMOS_SOURCE_FILES]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        missing_text = ", ".join(str(path) for path in missing)
        raise ConfigurationError(f"MemOS source files missing: {missing_text}")
    vendored_source_sha256, relative_paths = _hash_relative_source_files(
        root=memos_root,
        source_files=source_files,
    )
    patch_path = settings.project_root / MEMOS_PATCH_LOGICAL_PATH
    if not patch_path.is_file():
        raise ConfigurationError(f"MemOS patch file missing: {patch_path}")
    wrapper_path = settings.project_root / MEMOS_WRAPPER_LOGICAL_PATH
    if not wrapper_path.is_file():
        raise ConfigurationError(f"MemOS wrapper file missing: {wrapper_path}")
    patch_sha256 = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    wrapper_sha256 = hashlib.sha256(wrapper_path.read_bytes()).hexdigest()
    digest = hashlib.sha256()
    for field_name, field_value in (
        ("upstream_url", MEMOS_UPSTREAM_URL),
        ("release_tag", MEMOS_RELEASE_TAG),
        ("commit", MEMOS_COMMIT),
        ("vendored_source_sha256", vendored_source_sha256),
        ("patch_path", MEMOS_PATCH_LOGICAL_PATH),
        ("patch_sha256", patch_sha256),
        ("wrapper_path", MEMOS_WRAPPER_LOGICAL_PATH),
        ("wrapper_sha256", wrapper_sha256),
        ("implementation_identity", MEMOS_IMPLEMENTATION_IDENTITY),
    ):
        field_name_bytes = field_name.encode("utf-8")
        field_value_bytes = field_value.encode("utf-8")
        digest.update(len(field_name_bytes).to_bytes(8, byteorder="big"))
        digest.update(field_name_bytes)
        digest.update(len(field_value_bytes).to_bytes(8, byteorder="big"))
        digest.update(field_value_bytes)
    return {
        "source_sha256": digest.hexdigest(),
        "upstream_url": MEMOS_UPSTREAM_URL,
        "release_tag": MEMOS_RELEASE_TAG,
        "commit": MEMOS_COMMIT,
        "vendored_source_sha256": vendored_source_sha256,
        "file_count": len(relative_paths),
        "files": list(relative_paths),
        "patch_path": MEMOS_PATCH_LOGICAL_PATH,
        "patch_sha256": patch_sha256,
        "wrapper_path": MEMOS_WRAPPER_LOGICAL_PATH,
        "wrapper_sha256": wrapper_sha256,
        "implementation_identity": MEMOS_IMPLEMENTATION_IDENTITY,
        "source_mode": MEMOS_SOURCE_MODE,
    }


def _hash_relative_source_files(
    *,
    root: Path,
    source_files: list[Path],
) -> tuple[str, list[str]]:
    """按相对路径与内容计算源码集合 SHA-256。"""

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative_path = source_file.relative_to(root).as_posix()
        relative_paths.append(relative_path)
        path_bytes = relative_path.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, byteorder="big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, byteorder="big"))
        digest.update(content)
    return digest.hexdigest(), relative_paths


__all__ = [
    "MEMOS_ADAPTER_VERSION",
    "MEMOS_EMPTY_MEMORY_SENTINEL",
    "MEMOS_IMPLEMENTATION_IDENTITY",
    "MEMOS_REFERENCE_TIME_EFFECT",
    "MEMOS_RUNTIME_OWNER",
    "MemOS",
    "MemOSConfig",
    "MemosRuntime",
    "build_memos_namespace",
    "build_memos_source_identity",
    "clean_memos_conversation_state",
]
