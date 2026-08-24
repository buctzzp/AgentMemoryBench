"""统一 method 注册表。

本模块声明 method 支持的任务族、能力、profile 类型和实例 factory。registry 不保存
API key、method 实例、benchmark 白名单或运行状态。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields
import hashlib
from pathlib import Path
from typing import Any

from memory_benchmark.config import (
    OpenAISettings,
    PathSettings,
    RunComposition,
    load_path_settings,
    load_run_composition,
)
from memory_benchmark.config.profiles import (
    FRAMEWORK_PROFILE_KEYS,
    ProfileSection,
    build_typed_profile,
    load_profile_section,
)
from memory_benchmark.core import (
    ConfigurationError,
    Conversation,
    MethodCapability,
    TaskFamily,
)
from memory_benchmark.core.provider_protocol import ConsumeGranularity, MemoryProvider
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    ModelDescriptor,
    RetrievalObservationContract,
)

from .amem_adapter import (
    AMem,
    AMemConfig,
    build_amem_source_identity,
    clean_amem_conversation_state,
)
from .run_identity import BuildIdentityDeclaration, EmbeddingIdentity
from .everos_adapter import (
    EVEROS_EMBEDDING_MODEL_ID,
    EVEROS_LLM_MODEL_ID,
    EverOS,
    EverOSConfig,
    build_everos_source_identity,
    clean_everos_conversation_state,
    validate_everos_variant,
)
from .graphiti_adapter import (
    GRAPHITI_BUILD_LLM_RESPONSE_CONTRACT,
    GRAPHITI_EMBEDDING_MODEL_ID,
    GRAPHITI_LLM_MODEL_ID,
    GraphitiConfig,
    GraphitiOSS,
    build_graphiti_source_identity,
    clean_graphiti_conversation_state,
    validate_graphiti_variant,
)
from .lightmem_adapter import (
    LightMem,
    LightMemConfig,
    build_lightmem_source_identity,
    clean_lightmem_conversation_state,
)
from .letta_adapter import (
    LETTA_BUILD_LLM_RESPONSE_CONTRACT,
    LETTA_LLM_MODEL_ID,
    Letta,
    LettaConfig,
    build_letta_source_identity,
    clean_letta_conversation_state,
)
from .langmem_adapter import (
    LANGMEM_BUILD_LLM_RESPONSE_CONTRACT,
    LANGMEM_EMBEDDING_MODEL_ID,
    LANGMEM_LLM_MODEL_ID,
    LangMem,
    LangMemConfig,
    build_langmem_source_identity,
    clean_langmem_conversation_state,
)
from .mem0_adapter import Mem0, Mem0Config, build_mem0_source_identity
from .memos_adapter import (
    MEMOS_EMBEDDING_MODEL_ID,
    MEMOS_LLM_MODEL_ID,
    MEMOS_RERANKER_MODEL_ID,
    MemOS,
    MemOSConfig,
    build_memos_source_identity,
    clean_memos_conversation_state,
)
from .memoryos_adapter import (
    MemoryOS,
    MemoryOSPaperConfig,
    build_memoryos_source_identity,
    clean_memoryos_conversation_state,
)
from .simplemem_adapter import (
    SIMPLEMEM_LLM_MODEL_ID,
    SimpleMem,
    SimpleMemConfig,
    build_simplemem_source_identity,
    clean_simplemem_conversation_state,
)


_OPENAI_TRANSPORT_SUPPORT_PATH = Path(
    "src/memory_benchmark/methods/openai_transport.py"
)


def _openai_transport_support_identity(
    path_settings: PathSettings,
) -> dict[str, object]:
    """返回共享 OpenAI-compatible 请求覆写层的公开身份。"""

    return {
        "transport_support_path": _OPENAI_TRANSPORT_SUPPORT_PATH.as_posix(),
        "transport_support_sha256": _sha256_file(
            path_settings.project_root / _OPENAI_TRANSPORT_SUPPORT_PATH
        ),
    }


@dataclass(frozen=True)
class MethodBuildContext:
    """构造一次运行所需 method 实例的依赖集合。

    字段:
        config: 从 method TOML profile 加载的强类型配置。
        openai_settings: 需要外部 API 时的 OpenAI-compatible 连接配置；离线
            method 为 `None`。
        path_settings: 项目路径配置。
        storage_root: 当前 run 独占的 method 状态目录。
        benchmark_name: 当前 benchmark registry 名，用于按 benchmark profile 特化
            method 实例级协议声明。
        completed_conversations: resume 时已确认完成写入的 conversation。
        efficiency_collector: runner 创建的可选效率 observation collector。
        diagnostic_log_path: 当前 run 的第三方诊断日志；只作输出治理，不进入
            method 配置、manifest 或算法输入。
    """

    config: Any
    openai_settings: OpenAISettings | None
    path_settings: PathSettings
    storage_root: Path
    benchmark_name: str | None = None
    completed_conversations: tuple[Conversation, ...] = ()
    efficiency_collector: EfficiencyCollector | None = None
    diagnostic_log_path: Path | None = None


@dataclass(frozen=True)
class ResolvedMethodProfile:
    """一次新 run 已解析的 TOML profile envelope。

    ``config`` 只含 method 算法参数；``answer_builder`` 属于 framework 运行选择，
    不再由 adapter 的 ``to_manifest()`` 硬编码。公开 profile 名与 TOML section 名
    分开保存，避免 ``official-full``/``official_full`` 被静默混用。
    """

    public_name: str
    section_name: str
    answer_builder: str
    config: Any
    composition: RunComposition
    method_config_manifest: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        """拒绝空白 builder 和与 section 不一致的强类型配置。"""

        for label, value in (
            ("public profile name", self.public_name),
            ("profile section", self.section_name),
            ("answer_builder", self.answer_builder),
        ):
            if type(value) is not str or not value.strip() or value != value.strip():
                raise ConfigurationError(f"{label} must be a non-blank trimmed string")
        config_profile_name = getattr(self.config, "profile_name", None)
        if config_profile_name != self.section_name:
            raise ConfigurationError(
                "Resolved method profile config.profile_name must equal its TOML section: "
                f"{config_profile_name!r} != {self.section_name!r}"
            )
        if not isinstance(self.composition, RunComposition):
            raise ConfigurationError(
                "Resolved method profile composition must be RunComposition"
            )
        if self.method_config_manifest is not None and not isinstance(
            self.method_config_manifest,
            dict,
        ):
            raise ConfigurationError(
                "Resolved method profile method_config_manifest must be a dict or None"
            )


@dataclass(frozen=True)
class MethodRegistration:
    """一个统一 CLI method 的静态注册信息。

    字段:
        name: CLI 使用的 method 名称。
        task_families: method 支持的 benchmark 任务族。
        provided_capabilities: method 对 runner 提供的稳定能力。
        profile_sections: `(CLI profile 名, TOML section 名)` 的稳定映射。
        profile_relative_path: 相对项目根的 TOML profile 路径。
        config_type: profile 加载后构造的强类型配置类。
        requires_api: prediction 是否需要外部 API。
        system_factory: 根据运行上下文构造统一 memory system。
        source_identity_factory: 生成第三方 method 源码身份。
        model_name_getter: 从强类型配置读取生成模型名。
        max_workers_getter: 从强类型配置读取 conversation 并发数。
        display_name: 用于 CLI、manifest 和报错的人类可读 method 名称。
        protocol_version: method 显式声明的 provider 协议版本，供 manifest 盖章与
            worker 运行时交叉校验使用。
        consume_granularity_resolver: 按当前 benchmark 解析实例实际消费粒度的纯函数；
            factory 与 manifest 必须复用同一 resolver，避免运行身份与实例漂移。
        provenance_granularity: 可选静态 provenance 粒度；为空时沿用实例声明。
        retrieval_evidence_contract_version: 可选逐题 retrieval evidence 契约版本；
            非空时写入 method manifest 作为 resume 身份，声明该 run 的 answer prompt
            artifact 携带 per-question `retrieval_evidence`。
        workload_estimator: 可选的公开工作量估算 hook。
        allow_smoke_worker_override: 是否允许 smoke worker 覆盖（CLI `--workers`）配置值。
        efficiency_model_inventory_getter: 启用效率观测时生成模型清单。
        efficiency_instrumentation_identity_getter: 启用观测时生成插桩身份。
        retrieval_observation_contract_getter: 启用观测时生成 retrieval 强契约。
        clean_failed_ingest_state: 可选 clean retry hook；只有内置 method 能证明可
            conversation 级安全清理半写入状态时才声明。
        build_identity_resolver: 可选回调，从 ``config.to_manifest()`` 解析当前 build
            的完整身份声明。method/profile 分类与 concrete embedding 事实只在注册表
            维护一次；新 run 与 TOML profile 选择组合，旧 config-track 仅供历史
            artifact 回读。
        variant_validator: 可选 method × benchmark × concrete variant 预运行校验；
            必须在 output/runtime/API 构造前调用，用于拒绝无法诚实表达的组合。
    """

    name: str
    task_families: frozenset[TaskFamily]
    provided_capabilities: frozenset[MethodCapability]
    profile_sections: tuple[tuple[str, str], ...]
    profile_relative_path: Path
    config_type: type[Any]
    requires_api: bool
    system_factory: Callable[[MethodBuildContext], MemoryProvider]
    source_identity_factory: Callable[[PathSettings], dict[str, Any]]
    model_name_getter: Callable[[Any], str]
    max_workers_getter: Callable[[Any], int]
    display_name: str
    protocol_version: str
    consume_granularity_resolver: (
        Callable[[str | None], ConsumeGranularity] | None
    ) = None
    provenance_granularity: str | None = None
    retrieval_evidence_contract_version: str | None = None
    workload_estimator: Callable[[Conversation, Any], int] | None = None
    allow_smoke_worker_override: bool = False
    efficiency_model_inventory_getter: (
        Callable[[Any], tuple[ModelDescriptor, ...]] | None
    ) = None
    efficiency_instrumentation_identity_getter: (
        Callable[[PathSettings, Any, dict[str, Any]], dict[str, object]] | None
    ) = None
    retrieval_observation_contract_getter: (
        Callable[[Any], RetrievalObservationContract] | None
    ) = None
    supports_shared_instance_parallelism: bool = False
    clean_failed_ingest_state: (
        Callable[[MethodBuildContext, Conversation, dict[str, Any]], None] | None
    ) = None
    build_identity_resolver: (
        Callable[[dict[str, Any]], BuildIdentityDeclaration] | None
    ) = None
    variant_validator: Callable[[str, str], None] | None = None
    max_parallel_workers: int = 10

    def __post_init__(self) -> None:
        """校验 registration 的执行能力声明。"""

        if type(self.max_parallel_workers) is not int or self.max_parallel_workers < 1:
            raise ConfigurationError(
                "MethodRegistration.max_parallel_workers must be a positive integer"
            )

    @property
    def profile_names(self) -> frozenset[str]:
        """返回 method 对外公开的 CLI profile 名称。"""

        return frozenset(profile_name for profile_name, _ in self.profile_sections)

    def resolve_profile_section(self, profile_name: str) -> str:
        """把公开 profile 名解析为 TOML section，未知名称时显式报错。"""

        for public_name, section_name in self.profile_sections:
            if public_name == profile_name:
                return section_name
        supported = ", ".join(sorted(self.profile_names))
        raise ConfigurationError(
            f"Unknown {self.display_name} profile '{profile_name}'. "
            f"Supported: {supported}"
        )

    def resolve_consume_granularity(
        self,
        benchmark_name: str | None,
    ) -> ConsumeGranularity:
        """解析当前 method × benchmark 的 concrete 消费粒度。"""

        if self.consume_granularity_resolver is None:
            raise ConfigurationError(
                f"Registered method '{self.name}' does not declare "
                "consume_granularity_resolver"
            )
        return self.consume_granularity_resolver(benchmark_name)

    def validate_variant(self, benchmark_name: str, variant: str) -> None:
        """执行可选 method-specific variant 门；未声明时保持 no-op。"""

        if self.variant_validator is not None:
            self.variant_validator(benchmark_name, variant)


def _turn_consume_granularity(_benchmark_name: str | None) -> ConsumeGranularity:
    """返回固定 turn 消费粒度。"""

    return "turn"


def _mem0_consume_granularity(
    benchmark_name: str | None,
) -> ConsumeGranularity:
    """按 benchmark 返回 Mem0 的消费粒度。"""

    if benchmark_name in {"longmemeval", "halumem"}:
        return "session"
    if benchmark_name == "beam":
        return "pair"
    return "turn"


def _lightmem_consume_granularity(
    benchmark_name: str | None,
) -> ConsumeGranularity:
    """按 benchmark 返回 LightMem 的消费粒度。"""

    if benchmark_name == "halumem":
        return "session"
    if benchmark_name in {"longmemeval", "membench", "beam"}:
        return "pair"
    return "turn"


def _memoryos_consume_granularity(
    benchmark_name: str | None,
) -> ConsumeGranularity:
    """按 benchmark 返回 MemoryOS 的消费粒度。"""

    return "pair" if benchmark_name == "longmemeval" else "session"


def _build_mem0_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造本地 OSS Mem0 adapter。"""

    if not isinstance(context.config, Mem0Config):
        raise ConfigurationError("Mem0 factory requires Mem0Config")
    if context.openai_settings is None:
        raise ConfigurationError("Mem0 factory requires OpenAI settings")
    return Mem0(
        config=context.config,
        openai_settings=context.openai_settings,
        storage_root=context.storage_root,
        path_settings=context.path_settings,
        existing_conversation_ids={
            conversation.conversation_id
            for conversation in context.completed_conversations
        },
        efficiency_collector=context.efficiency_collector,
        consume_granularity=_mem0_consume_granularity(context.benchmark_name),
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
    )


def _session_consume_granularity(_benchmark_name: str | None) -> ConsumeGranularity:
    """返回固定 session 消费粒度。"""

    return "session"


def _build_letta_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 Letta sleeptime-memory adapter。"""

    if not isinstance(context.config, LettaConfig):
        raise ConfigurationError("Letta factory requires LettaConfig")
    if context.openai_settings is None:
        raise ConfigurationError("Letta factory requires OpenAI settings")
    return Letta(
        config=context.config,
        path_settings=context.path_settings,
        storage_root=context.storage_root,
        openai_settings=context.openai_settings,
        efficiency_collector=context.efficiency_collector,
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )


def _build_langmem_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 LangMem background-manager adapter。"""

    if not isinstance(context.config, LangMemConfig):
        raise ConfigurationError("LangMem factory requires LangMemConfig")
    if context.openai_settings is None:
        raise ConfigurationError("LangMem factory requires OpenAI settings")
    return LangMem(
        config=context.config,
        path_settings=context.path_settings,
        storage_root=context.storage_root,
        openai_settings=context.openai_settings,
        efficiency_collector=context.efficiency_collector,
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )


def _build_everos_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 EverOS typed-product adapter。"""

    if not isinstance(context.config, EverOSConfig):
        raise ConfigurationError("EverOS factory requires EverOSConfig")
    if context.openai_settings is None:
        raise ConfigurationError("EverOS factory requires OpenAI settings")
    return EverOS(
        config=context.config,
        path_settings=context.path_settings,
        storage_root=context.storage_root,
        openai_settings=context.openai_settings,
        efficiency_collector=context.efficiency_collector,
        benchmark_name=context.benchmark_name,
        session_memory_report=context.benchmark_name == "halumem",
        completed_conversation_ids={
            conversation.conversation_id
            for conversation in context.completed_conversations
        },
        diagnostic_log_path=context.diagnostic_log_path,
    )


def _build_graphiti_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 Graphiti OSS product adapter。"""

    if not isinstance(context.config, GraphitiConfig):
        raise ConfigurationError("Graphiti factory requires GraphitiConfig")
    if context.openai_settings is None:
        raise ConfigurationError("Graphiti factory requires OpenAI settings")
    return GraphitiOSS(
        config=context.config,
        path_settings=context.path_settings,
        storage_root=context.storage_root,
        openai_settings=context.openai_settings,
        benchmark_name=context.benchmark_name,
        session_memory_report=context.benchmark_name == "halumem",
        efficiency_collector=context.efficiency_collector,
        diagnostic_log_path=context.diagnostic_log_path,
    )


def _everos_model_name(config: Any) -> str:
    """从 EverOS 配置读取 memory build LLM 名称。"""

    if not isinstance(config, EverOSConfig):
        raise ConfigurationError("EverOS model getter requires EverOSConfig")
    return config.llm_model


def _everos_max_workers(config: Any) -> int:
    """从 EverOS 配置读取 conversation worker 上限。"""

    if not isinstance(config, EverOSConfig):
        raise ConfigurationError("EverOS worker getter requires EverOSConfig")
    return config.max_workers


def _everos_efficiency_model_inventory(
    config: Any,
) -> tuple[ModelDescriptor, ...]:
    """返回 EverOS build LLM 与实际消费的本地 embedding 身份。"""

    if not isinstance(config, EverOSConfig):
        raise ConfigurationError(
            "EverOS model inventory getter requires EverOSConfig"
        )
    return (
        ModelDescriptor(
            model_id=EVEROS_LLM_MODEL_ID,
            model_name=config.llm_model,
            model_role="memory_build_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id=EVEROS_EMBEDDING_MODEL_ID,
            model_name=config.embedding_model,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model,
            embedding_dimension=config.embedding_dimension,
            tokenizer_name=config.embedding_model,
        ),
    )


def _everos_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 EverOS worker 纯观测 wrapper 身份。"""

    if not isinstance(config, EverOSConfig):
        raise ConfigurationError(
            "EverOS instrumentation identity getter requires EverOSConfig"
        )
    worker = Path("src/memory_benchmark/methods/everos_worker.py")
    return {
        "collector_schema": 1,
        "wrapper_path": worker.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / worker),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model,
        "method_source_sha256": source_identity.get("source_sha256"),
        "exact_api_usage": "llm-product-response-proxy-v1",
        "embedding_observation": "local-tokenizer+wall-clock-v1",
        "async_scope_bridge": "exact-drain-buffered-replay-v1",
    }


def _clean_everos_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """物理 root 级清理 EverOS failed-ingest conversation 状态。"""

    run_id = context.storage_root.parent.name
    storage_root = _resolve_clean_retry_storage_root(context, failed_state)
    clean_context = MethodBuildContext(
        config=context.config,
        openai_settings=context.openai_settings,
        path_settings=context.path_settings,
        storage_root=storage_root,
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    system = _build_everos_system(clean_context)
    if not isinstance(system, EverOS):
        raise ConfigurationError("EverOS clean hook failed to build adapter")
    isolation_key = f"{run_id}_{conversation.conversation_id}"
    try:
        clean_everos_conversation_state(
            provider=system,
            isolation_key=isolation_key,
        )
    finally:
        system.cleanup()


def _everos_build_identity(
    config_manifest: dict[str, Any],
) -> BuildIdentityDeclaration:
    """解析 EverOS controlled MiniLM、本地 provider 与 LanceDB build。"""

    provider = _manifest_text(config_manifest, "embedding_provider")
    model = _manifest_text(config_manifest, "embedding_model")
    dimension = _manifest_dimension(config_manifest, "embedding_dimension")
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    if (
        provider == "sentence-transformers-local"
        and model_key == "all-minilm-l6-v2"
        and dimension == 384
    ):
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="controlled_embedding_v1",
            historical_controlled_build_equivalent_to_current_main=False,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=dimension,
                revision=None,
                revision_status="local_unpinned",
                normalization="model-internal-l2",
                instruction=None,
                distance="lancedb-l2",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider=provider,
        model=model,
        dimension=dimension,
    )


def _graphiti_model_name(config: Any) -> str:
    """从 Graphiti 强类型配置读取 build LLM 名称。"""

    if not isinstance(config, GraphitiConfig):
        raise ConfigurationError("Graphiti model getter requires GraphitiConfig")
    return config.llm_model


def _graphiti_max_workers(config: Any) -> int:
    """从 Graphiti 强类型配置读取 conversation worker 数。"""

    if not isinstance(config, GraphitiConfig):
        raise ConfigurationError("Graphiti worker getter requires GraphitiConfig")
    return config.max_workers


def _graphiti_efficiency_model_inventory(
    config: Any,
) -> tuple[ModelDescriptor, ...]:
    """返回 Graphiti build LLM 与本地 embedding 身份。"""

    if not isinstance(config, GraphitiConfig):
        raise ConfigurationError(
            "Graphiti model inventory getter requires GraphitiConfig"
        )
    return (
        ModelDescriptor(
            model_id=GRAPHITI_LLM_MODEL_ID,
            model_name=config.llm_model,
            model_role="memory_build_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id=GRAPHITI_EMBEDDING_MODEL_ID,
            model_name=config.embedding_model_path,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_path,
            embedding_dimension=config.embedding_dimension,
            tokenizer_name=config.embedding_model_path,
        ),
    )


def _graphiti_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 Graphiti endpoint/embedder worker 的纯观测身份。"""

    if not isinstance(config, GraphitiConfig):
        raise ConfigurationError(
            "Graphiti instrumentation identity getter requires GraphitiConfig"
        )
    adapter_path = Path("src/memory_benchmark/methods/graphiti_adapter.py")
    worker_path = Path("src/memory_benchmark/methods/graphiti_worker.py")
    bootstrap_path = Path("scripts/bootstrap_graphiti_runtime.sh")
    return {
        "collector_schema": 1,
        "wrapper_path": adapter_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / adapter_path),
        "worker_path": worker_path.as_posix(),
        "worker_sha256": _sha256_file(path_settings.project_root / worker_path),
        "bootstrap_path": bootstrap_path.as_posix(),
        "bootstrap_sha256": _sha256_file(
            path_settings.project_root / bootstrap_path
        ),
        "method_source_sha256": source_identity.get("source_sha256"),
        "exact_api_usage": "chat-completions-response-usage-required-v1",
        "embedding_observation": "sentence-transformer-tokenizer+wall-clock-v1",
        "build_llm_response_contract": GRAPHITI_BUILD_LLM_RESPONSE_CONTRACT,
        "retrieval_observation": "product-search-wall-clock-v1",
    }


def _clean_graphiti_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """物理 root 级清理 Graphiti failed-ingest conversation。"""

    run_id = context.storage_root.parent.name
    storage_root = _resolve_clean_retry_storage_root(context, failed_state)
    clean_context = MethodBuildContext(
        config=context.config,
        openai_settings=context.openai_settings,
        path_settings=context.path_settings,
        storage_root=storage_root,
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    system = _build_graphiti_system(clean_context)
    if not isinstance(system, GraphitiOSS):
        raise ConfigurationError("Graphiti clean hook failed to build adapter")
    isolation_key = f"{run_id}_{conversation.conversation_id}"
    try:
        clean_graphiti_conversation_state(
            provider=system,
            isolation_key=isolation_key,
        )
    finally:
        system.cleanup()


def _graphiti_build_identity(
    config_manifest: dict[str, Any],
) -> BuildIdentityDeclaration:
    """解析 Graphiti controlled MiniLM + FalkorDB cosine build。"""

    provider = _manifest_text(config_manifest, "embedding_provider")
    model = _manifest_text(config_manifest, "embedding_model_path")
    dimension = _manifest_dimension(config_manifest, "embedding_dimension")
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    if (
        provider == "sentence-transformers-local"
        and model_key == "all-minilm-l6-v2"
        and dimension == 384
    ):
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="controlled_embedding_v1",
            historical_controlled_build_equivalent_to_current_main=False,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=dimension,
                revision=None,
                revision_status="local_unpinned",
                normalization="l2-normalized",
                instruction=None,
                distance="falkordb-cosine",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider=provider,
        model=model,
        dimension=dimension,
    )


def _langmem_model_name(config: Any) -> str:
    """从 LangMem 强类型配置读取 memory build LLM 名称。"""

    if not isinstance(config, LangMemConfig):
        raise ConfigurationError("LangMem model getter requires LangMemConfig")
    return config.llm_model


def _langmem_max_workers(config: Any) -> int:
    """从 LangMem 强类型配置读取 conversation worker 数。"""

    if not isinstance(config, LangMemConfig):
        raise ConfigurationError("LangMem worker getter requires LangMemConfig")
    return config.max_workers


def _langmem_efficiency_model_inventory(
    config: Any,
) -> tuple[ModelDescriptor, ...]:
    """返回 LangMem build LLM 与本地 embedding 身份。"""

    if not isinstance(config, LangMemConfig):
        raise ConfigurationError(
            "LangMem model inventory getter requires LangMemConfig"
        )
    return (
        ModelDescriptor(
            model_id=LANGMEM_LLM_MODEL_ID,
            model_name=config.llm_model,
            model_role="memory_build_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id=LANGMEM_EMBEDDING_MODEL_ID,
            model_name=config.embedding_model_path,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_path,
            embedding_dimension=config.embedding_dimension,
            tokenizer_name=config.embedding_model_path,
        ),
    )


def _langmem_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 LangMem worker 逐调用 usage/embedding 插桩身份。"""

    if not isinstance(config, LangMemConfig):
        raise ConfigurationError(
            "LangMem instrumentation identity getter requires LangMemConfig"
        )
    adapter_path = Path("src/memory_benchmark/methods/langmem_adapter.py")
    worker_path = Path("src/memory_benchmark/methods/langmem_worker.py")
    requirements_path = Path("scripts/requirements/langmem-runtime.txt")
    return {
        "collector_schema": 1,
        "wrapper_path": adapter_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / adapter_path),
        "worker_path": worker_path.as_posix(),
        "worker_sha256": _sha256_file(path_settings.project_root / worker_path),
        "runtime_requirements_path": requirements_path.as_posix(),
        "runtime_requirements_sha256": _sha256_file(
            path_settings.project_root / requirements_path
        ),
        "method_source_sha256": source_identity.get("source_sha256"),
        "exact_api_usage": "langchain-response-usage-required-v1",
        "embedding_observation": "sentence-transformer-tokenizer+wall-clock-v1",
        "build_llm_response_contract": LANGMEM_BUILD_LLM_RESPONSE_CONTRACT,
        "retrieval_observation": "product-asearch-wall-clock-v1",
    }


def _letta_model_name(config: Any) -> str:
    """从 Letta 强类型配置读取 memory build LLM 名称。"""

    if not isinstance(config, LettaConfig):
        raise ConfigurationError("Letta model getter requires LettaConfig")
    return config.llm_model


def _letta_max_workers(config: Any) -> int:
    """从 Letta 强类型配置读取 conversation worker 数。"""

    if not isinstance(config, LettaConfig):
        raise ConfigurationError("Letta worker getter requires LettaConfig")
    return config.max_workers


def _letta_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 Letta 唯一的 API memory-build LLM 身份。"""

    if not isinstance(config, LettaConfig):
        raise ConfigurationError("Letta model inventory getter requires LettaConfig")
    return (
        ModelDescriptor(
            model_id=LETTA_LLM_MODEL_ID,
            model_name=config.llm_model,
            model_role="memory_build_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
    )


def _letta_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 Letta worker 逐调用 API usage 插桩身份。"""

    if not isinstance(config, LettaConfig):
        raise ConfigurationError(
            "Letta instrumentation identity getter requires LettaConfig"
        )
    adapter_path = Path("src/memory_benchmark/methods/letta_adapter.py")
    worker_path = Path("src/memory_benchmark/methods/letta_worker.py")
    return {
        "collector_schema": 1,
        "wrapper_path": adapter_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / adapter_path),
        "worker_path": worker_path.as_posix(),
        "worker_sha256": _sha256_file(path_settings.project_root / worker_path),
        "llm_tokenizer": config.llm_model,
        "method_source_sha256": source_identity.get("source_sha256"),
        "exact_api_usage": "worker_openai_response_usage_v1",
        "build_llm_response_contract": LETTA_BUILD_LLM_RESPONSE_CONTRACT,
        "retrieval_observation": "core_block_read_wall_clock_v1",
    }


def _clean_letta_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """namespace-scoped 清理 Letta failed-ingest conversation 的产品状态。"""

    run_id = context.storage_root.parent.name
    storage_root = _resolve_clean_retry_storage_root(context, failed_state)
    clean_context = MethodBuildContext(
        config=context.config,
        openai_settings=context.openai_settings,
        path_settings=context.path_settings,
        storage_root=storage_root,
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    system = _build_letta_system(clean_context)
    if not isinstance(system, Letta):
        raise ConfigurationError("Letta clean hook failed to build Letta adapter")
    isolation_key = f"{run_id}_{conversation.conversation_id}"
    try:
        clean_letta_conversation_state(
            provider=system,
            isolation_key=isolation_key,
        )
    finally:
        system.cleanup()


def _clean_langmem_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """namespace-scoped 清理 LangMem failed-ingest conversation 状态。"""

    run_id = context.storage_root.parent.name
    storage_root = _resolve_clean_retry_storage_root(context, failed_state)
    clean_context = MethodBuildContext(
        config=context.config,
        openai_settings=context.openai_settings,
        path_settings=context.path_settings,
        storage_root=storage_root,
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    system = _build_langmem_system(clean_context)
    if not isinstance(system, LangMem):
        raise ConfigurationError("LangMem clean hook failed to build LangMem adapter")
    isolation_key = f"{run_id}_{conversation.conversation_id}"
    try:
        clean_langmem_conversation_state(
            provider=system,
            isolation_key=isolation_key,
        )
    finally:
        system.cleanup()


def _build_memos_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 MemOS product typed-handler adapter。"""

    if not isinstance(context.config, MemOSConfig):
        raise ConfigurationError("MemOS factory requires MemOSConfig")
    if context.openai_settings is None:
        raise ConfigurationError("MemOS factory requires OpenAI settings")
    return MemOS(
        config=context.config,
        path_settings=context.path_settings,
        storage_root=context.storage_root,
        openai_settings=context.openai_settings,
        efficiency_collector=context.efficiency_collector,
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
    )


def _memos_model_name(config: Any) -> str:
    """从 MemOS 强类型配置读取 memory build LLM 名称。"""

    if not isinstance(config, MemOSConfig):
        raise ConfigurationError("MemOS model getter requires MemOSConfig")
    return config.llm_model


def _memos_max_workers(config: Any) -> int:
    """从 MemOS 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, MemOSConfig):
        raise ConfigurationError("MemOS worker getter requires MemOSConfig")
    return config.max_workers


def _memos_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 MemOS 观测会引用的模型身份，区分 API LLM / 本地 embedding / 本地 rerank。"""

    if not isinstance(config, MemOSConfig):
        raise ConfigurationError("MemOS model inventory getter requires MemOSConfig")
    return (
        ModelDescriptor(
            model_id=MEMOS_LLM_MODEL_ID,
            model_name=config.llm_model,
            model_role="memory_build_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id=MEMOS_EMBEDDING_MODEL_ID,
            model_name=config.embedding_model_path,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_path,
            embedding_dimension=config.embedding_dimension,
            tokenizer_name=config.embedding_model_path,
        ),
        ModelDescriptor(
            # cosine_local reranker 是本地纯算法打分，不是 LLM，也不产生 API 调用。
            model_id=MEMOS_RERANKER_MODEL_ID,
            model_name=config.reranker_backend,
            model_role="reranker",
            execution_mode="local",
        ),
    )


def _memos_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 MemOS 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, MemOSConfig):
        raise ConfigurationError(
            "MemOS instrumentation identity getter requires MemOSConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/memos_adapter.py")
    return {
        "collector_schema": 1,
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model_path,
        "method_source_sha256": source_identity.get("source_sha256"),
        # patch 在成功 response 尚在手时暴露 usage；adapter 的线程安全原始缓冲
        # 等 business task 精确完成后，再回放到原 conversation/question scope。
        "exact_api_usage": "patched_response_callback",
        "async_scope_bridge": "completion_buffered_replay_v1",
        "embedding_token_source": "sentence_transformer_tokenizer_estimate",
    }


def _clean_memos_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """namespace-scoped 清理 MemOS failed_ingest conversation 的算法可见状态。"""

    storage_root = _resolve_clean_retry_storage_root(context, failed_state)
    clean_context = MethodBuildContext(
        config=context.config,
        openai_settings=context.openai_settings,
        path_settings=context.path_settings,
        storage_root=storage_root,
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    system = _build_memos_system(clean_context)
    if not isinstance(system, MemOS):
        raise ConfigurationError("MemOS clean hook failed to build MemOS adapter")
    run_id = context.storage_root.parent.name
    isolation_key = f"{run_id}_{conversation.conversation_id}"
    clean_memos_conversation_state(provider=system, isolation_key=isolation_key)


def _memos_build_identity(config_manifest: dict[str, Any]) -> BuildIdentityDeclaration:
    """解析 MemOS controlled MiniLM + Qdrant cosine build。"""

    provider = _manifest_text(config_manifest, "embedding_provider")
    model = _manifest_text(config_manifest, "embedding_model_path")
    dimension = _manifest_dimension(config_manifest, "embedding_dimension")
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    if (
        provider == "sentence-transformers-local"
        and model_key == "all-minilm-l6-v2"
        and dimension == 384
    ):
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="controlled_embedding_v1",
            # MemOS 是本支线首次接入，没有可对表的历史受控 build。
            historical_controlled_build_equivalent_to_current_main=False,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=dimension,
                revision=None,
                revision_status="local_unpinned",
                # current `SenTranEmbedder.embed()` 调 `model.encode()` 时不传
                # `normalize_embeddings`，MemOS 自身不做归一化；受控 MiniLM 模型
                # 目录的 `modules.json` 带 `2_Normalize`，故 L2 由模型 pipeline
                # 提供。这是 source-proven 值，不是猜的 `internal_l2`。
                normalization="model_pipeline_l2",
                instruction=None,
                distance="qdrant-cosine",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider=provider,
        model=model,
        dimension=dimension,
    )


def _build_simplemem_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 SimpleMem text backend adapter。"""

    if not isinstance(context.config, SimpleMemConfig):
        raise ConfigurationError("SimpleMem factory requires SimpleMemConfig")
    if context.openai_settings is None:
        raise ConfigurationError("SimpleMem factory requires OpenAI settings")
    return SimpleMem(
        config=context.config,
        path_settings=context.path_settings,
        storage_root=context.storage_root,
        openai_settings=context.openai_settings,
        efficiency_collector=context.efficiency_collector,
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
    )


def _simplemem_model_name(config: Any) -> str:
    """从 SimpleMem 强类型配置读取 LLM 名称。"""

    if not isinstance(config, SimpleMemConfig):
        raise ConfigurationError("SimpleMem model getter requires SimpleMemConfig")
    return config.llm_model


def _simplemem_max_workers(config: Any) -> int:
    """从 SimpleMem 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, SimpleMemConfig):
        raise ConfigurationError("SimpleMem worker getter requires SimpleMemConfig")
    return config.max_workers


def _simplemem_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 SimpleMem efficiency observation 会引用的模型身份。"""

    if not isinstance(config, SimpleMemConfig):
        raise ConfigurationError(
            "SimpleMem model inventory getter requires SimpleMemConfig"
        )
    return (
        ModelDescriptor(
            model_id=SIMPLEMEM_LLM_MODEL_ID,
            model_name=config.llm_model,
            model_role="memory_and_retrieval_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="simplemem-embedding",
            model_name=config.embedding_model_path,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_path,
            embedding_dimension=config.embedding_dimension,
            tokenizer_name=config.embedding_model_path,
        ),
    )


def _simplemem_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 SimpleMem 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, SimpleMemConfig):
        raise ConfigurationError(
            "SimpleMem instrumentation identity getter requires SimpleMemConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/simplemem_adapter.py")
    return {
        "collector_schema": 1,
        **_openai_transport_support_identity(path_settings),
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model_path,
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _build_amem_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 A-Mem adapter。"""

    if not isinstance(context.config, AMemConfig):
        raise ConfigurationError("A-Mem factory requires AMemConfig")
    if context.openai_settings is None:
        raise ConfigurationError("A-Mem factory requires OpenAI settings")
    system = AMem(
        config=context.config,
        openai_settings=context.openai_settings,
        storage_root=context.storage_root,
        path_settings=context.path_settings,
        efficiency_collector=context.efficiency_collector,
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    for conversation in context.completed_conversations:
        system.load_existing_conversation_state(conversation)
    return system


def _amem_model_name(config: Any) -> str:
    """从 A-Mem 强类型配置读取回答模型名。"""

    if not isinstance(config, AMemConfig):
        raise ConfigurationError("A-Mem model getter requires AMemConfig")
    return config.llm_model


def _amem_max_workers(config: Any) -> int:
    """从 A-Mem 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, AMemConfig):
        raise ConfigurationError("A-Mem worker getter requires AMemConfig")
    return config.max_workers


def _amem_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 A-Mem efficiency observation 会引用的模型身份。"""

    if not isinstance(config, AMemConfig):
        raise ConfigurationError(
            "A-Mem model inventory getter requires AMemConfig"
        )
    return (
        ModelDescriptor(
            model_id="amem-memory-llm",
            model_name=config.llm_model,
            model_role="memory_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="amem-embedding",
            model_name=config.embedding_model,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model,
            embedding_dimension=384,
            tokenizer_name=config.embedding_model,
        ),
    )


def _amem_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 A-Mem 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, AMemConfig):
        raise ConfigurationError(
            "A-Mem instrumentation identity getter requires AMemConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/amem_adapter.py")
    return {
        "collector_schema": 1,
        **_openai_transport_support_identity(path_settings),
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model,
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _mem0_model_name(config: Any) -> str:
    """从 Mem0 强类型配置读取 reader 模型名。"""

    if not isinstance(config, Mem0Config):
        raise ConfigurationError("Mem0 model getter requires Mem0Config")
    return config.reader_model


def _build_lightmem_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 LightMem adapter。"""

    if not isinstance(context.config, LightMemConfig):
        raise ConfigurationError("LightMem factory requires LightMemConfig")
    if context.openai_settings is None:
        raise ConfigurationError("LightMem factory requires OpenAI settings")
    system = LightMem(
        config=context.config,
        openai_settings=context.openai_settings,
        storage_root=context.storage_root,
        path_settings=context.path_settings,
        efficiency_collector=context.efficiency_collector,
        consume_granularity=_lightmem_consume_granularity(context.benchmark_name),
        session_memory_report=context.benchmark_name == "halumem",
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    for conversation in context.completed_conversations:
        system.load_existing_conversation_state(conversation)
    return system


def _lightmem_model_name(config: Any) -> str:
    """从 LightMem 强类型配置读取回答模型名。"""

    if not isinstance(config, LightMemConfig):
        raise ConfigurationError("LightMem model getter requires LightMemConfig")
    return config.llm_model


def _lightmem_max_workers(config: Any) -> int:
    """从 LightMem 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, LightMemConfig):
        raise ConfigurationError("LightMem worker getter requires LightMemConfig")
    return config.max_workers


def _lightmem_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 LightMem efficiency observation 会引用的模型身份。

    不声明 `lightmem-answer-llm`：registered v3 主路径只调用
    `ingest()`/`retrieve()`，最终 answer LLM 调用由 framework `FrameworkAnswerReader`
    执行并单独追加到 model inventory（见 `cli/run_prediction.py`
    `_append_framework_answer_model_inventory`）；`LightMem.get_answer()` 内部记录的
    `lightmem-answer-llm` 只在直接调用该 legacy 接口时才会产生 observation，不属于
    registered 主路径实际引用的模型。
    """

    if not isinstance(config, LightMemConfig):
        raise ConfigurationError(
            "LightMem model inventory getter requires LightMemConfig"
        )
    return (
        ModelDescriptor(
            model_id="lightmem-memory-llm",
            model_name=config.llm_model,
            model_role="memory_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="lightmem-embedding",
            model_name=config.embedding_model_path,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_path,
            embedding_dimension=config.embedding_dimensions,
            tokenizer_name=config.embedding_model_path,
        ),
    )


def _lightmem_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 LightMem 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, LightMemConfig):
        raise ConfigurationError(
            "LightMem instrumentation identity getter requires LightMemConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/lightmem_adapter.py")
    return {
        "collector_schema": 1,
        **_openai_transport_support_identity(path_settings),
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model_path,
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _mem0_max_workers(config: Any) -> int:
    """从 Mem0 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, Mem0Config):
        raise ConfigurationError("Mem0 worker getter requires Mem0Config")
    return config.max_workers


def _mem0_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 Mem0 registered 主路径实际会引用的模型身份。

    不声明 ``mem0-answer-llm``：registered v3 主路径只调用
    ``ingest()``/``retrieve()``，最终 answer LLM 由 framework
    ``FrameworkAnswerReader`` 执行并另行追加到 model inventory。Mem0
    ``get_answer()`` 的 reader observation 只属于直接调用 legacy 接口的路径。
    """

    if not isinstance(config, Mem0Config):
        raise ConfigurationError("Mem0 model inventory getter requires Mem0Config")
    return (
        ModelDescriptor(
            model_id="mem0-memory-llm",
            model_name=config.extraction_model,
            model_role="memory_llm",
            execution_mode="api",
            tokenizer_name=config.extraction_model,
        ),
        ModelDescriptor(
            model_id="mem0-embedding",
            model_name=config.embedding_model,
            model_role="embedding",
            execution_mode="api",
            embedding_dimension=config.embedding_dimensions,
            tokenizer_name=config.embedding_model,
        ),
    )


def _mem0_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 Mem0 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, Mem0Config):
        raise ConfigurationError(
            "Mem0 instrumentation identity getter requires Mem0Config"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/mem0_adapter.py")
    return {
        "collector_schema": 1,
        **_openai_transport_support_identity(path_settings),
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "extraction_llm_hook": "mem0-openai-response-callback",
        "embedding_hook": "wrapped-embedding-model-methods",
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _separable_retrieval_contract(config: Any) -> RetrievalObservationContract:
    """当前官方集成均声明可精确拆分 retrieval 边界。"""

    return RetrievalObservationContract(
        required_by_profile=True,
        supported_by_method=True,
    )


def _build_memoryos_system(context: MethodBuildContext) -> MemoryProvider:
    """根据统一 build context 构造 MemoryOS adapter，并恢复已完成 conversation。"""

    if not isinstance(context.config, MemoryOSPaperConfig):
        raise ConfigurationError("MemoryOS factory requires MemoryOSPaperConfig")
    if context.openai_settings is None:
        raise ConfigurationError("MemoryOS factory requires OpenAI settings")
    system = MemoryOS(
        openai_api_key=context.openai_settings.api_key,
        openai_base_url=context.openai_settings.base_url,
        storage_root=context.storage_root,
        config=context.config,
        efficiency_collector=context.efficiency_collector,
        # 按 benchmark 设消费粒度（与 LightMem/A-Mem 既有模式一致）：
        # LongMemEval 数据 role=user/assistant 适合 pair 聚合；LoCoMo 数据
        # role=speaker 名，pair 聚合失效，用 session 粒度由 adapter 内部按
        # speaker 配对成 add_memory。详见 plan-memoryos-migration.md T2。
        consume_granularity=_memoryos_consume_granularity(context.benchmark_name),
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    for conversation in context.completed_conversations:
        system.load_existing_conversation_state(conversation)
    return system


def _clean_amem_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 A-Mem 单个 failed_ingest conversation 的 method state。"""

    clean_amem_conversation_state(
        _resolve_clean_retry_storage_root(context, failed_state),
        conversation.conversation_id,
    )


def _clean_mem0_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 Mem0 failed_ingest namespace 的全部算法可见状态。"""

    storage_root = _resolve_clean_retry_storage_root(context, failed_state)
    clean_context = MethodBuildContext(
        config=context.config,
        openai_settings=context.openai_settings,
        path_settings=context.path_settings,
        storage_root=storage_root,
        benchmark_name=context.benchmark_name,
        diagnostic_log_path=context.diagnostic_log_path,
    )
    system = _build_mem0_system(clean_context)
    if not isinstance(system, Mem0):
        raise ConfigurationError("Mem0 clean hook failed to build Mem0 adapter")
    run_id = context.storage_root.parent.name
    isolation_key = f"{run_id}_{conversation.conversation_id}"
    system.clean_failed_ingest_state(isolation_key)


def _clean_lightmem_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 LightMem 单个 failed_ingest conversation 的 method state。"""

    clean_lightmem_conversation_state(
        _resolve_clean_retry_storage_root(context, failed_state),
        conversation.conversation_id,
    )


def _clean_memoryos_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 MemoryOS 单个 failed_ingest conversation 的 method state。"""

    clean_memoryos_conversation_state(
        _resolve_clean_retry_storage_root(context, failed_state),
        conversation.conversation_id,
    )


def _clean_simplemem_failed_ingest_state(
    context: MethodBuildContext,
    conversation: Conversation,
    failed_state: dict[str, Any],
) -> None:
    """清理 SimpleMem 单个 failed_ingest conversation 的 isolation 状态。"""

    clean_simplemem_conversation_state(
        _resolve_clean_retry_storage_root(context, failed_state),
        conversation.conversation_id,
    )


def _resolve_clean_retry_storage_root(
    context: MethodBuildContext,
    failed_state: dict[str, Any],
) -> Path:
    """根据失败 checkpoint 定位 clean retry 应清理的 method state 根目录。

    isolated worker 失败时 checkpoint 会记录 `worker_idx`，真实脏状态位于
    `method_state/worker_<idx>/`；非 isolated 路径没有该字段，直接使用 run 级
    `method_state/`。
    """

    worker_idx = failed_state.get("worker_idx")
    if isinstance(worker_idx, int) and not isinstance(worker_idx, bool):
        return context.storage_root / f"worker_{worker_idx}"
    return context.storage_root


def _memoryos_model_name(config: Any) -> str:
    """从 MemoryOS 强类型配置读取回答模型名。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError("MemoryOS model getter requires MemoryOSPaperConfig")
    return config.llm_model


def _memoryos_max_workers(config: Any) -> int:
    """从 MemoryOS 强类型配置读取 conversation 并发数。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError("MemoryOS worker getter requires MemoryOSPaperConfig")
    return config.max_workers


def _memoryos_efficiency_model_inventory(config: Any) -> tuple[ModelDescriptor, ...]:
    """返回 MemoryOS efficiency observation 会引用的模型身份。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError(
            "MemoryOS model inventory getter requires MemoryOSPaperConfig"
        )
    return (
        ModelDescriptor(
            model_id="memoryos-chat-llm",
            model_name=config.llm_model,
            model_role="memory_answer_llm",
            execution_mode="api",
            tokenizer_name=config.llm_model,
        ),
        ModelDescriptor(
            model_id="memoryos-embedding",
            model_name=config.embedding_model_name,
            model_role="embedding",
            execution_mode="local",
            revision_or_path=config.embedding_model_name,
        ),
    )


def _memoryos_efficiency_instrumentation_identity(
    path_settings: PathSettings,
    config: Any,
    source_identity: dict[str, Any],
) -> dict[str, object]:
    """返回 MemoryOS 观测 wrapper 身份，不包含 secret。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError(
            "MemoryOS instrumentation identity getter requires MemoryOSPaperConfig"
        )
    wrapper_relative_path = Path("src/memory_benchmark/methods/memoryos_adapter.py")
    return {
        "collector_schema": 1,
        **_openai_transport_support_identity(path_settings),
        "wrapper_path": wrapper_relative_path.as_posix(),
        "wrapper_sha256": _sha256_file(path_settings.project_root / wrapper_relative_path),
        "llm_tokenizer": config.llm_model,
        "embedding_tokenizer": config.embedding_model_name,
        "embedding_observer": "vendored-get-embedding-success-hook-v1",
        "method_source_sha256": source_identity.get("source_sha256"),
    }


def _estimate_memoryos_update_batches(
    conversation: Conversation,
    config: Any,
) -> int:
    """估算单个 conversation 在 MemoryOS add 阶段的 update batch 数。"""

    if not isinstance(config, MemoryOSPaperConfig):
        raise ConfigurationError(
            "MemoryOS workload estimator requires MemoryOSPaperConfig"
        )
    return MemoryOS.estimate_add_workload(
        conversation,
        config,
    ).update_batch_count


def _manifest_text(config_manifest: dict[str, Any], key: str) -> str | None:
    """读取 config manifest 可空文本，不做宽松字符串转换。"""

    value = config_manifest.get(key)
    return value if type(value) is str else None


def _manifest_dimension(config_manifest: dict[str, Any], key: str) -> int | None:
    """读取 config manifest 可空维度；布尔值不得伪装成整数。"""

    value = config_manifest.get(key)
    return value if type(value) is int else None


def _pending_build_identity(
    *,
    provider: str | None,
    model: str | None,
    dimension: int | None,
) -> BuildIdentityDeclaration:
    """构造保留已知 concrete 字段但不臆造语义的 pending build 声明。"""

    return BuildIdentityDeclaration(
        implementation_variant="product",
        embedding_profile="unclassified_pending",
        historical_controlled_build_equivalent_to_current_main=False,
        embedding=EmbeddingIdentity(
            provider=provider,
            model=model,
            dimension=dimension,
            revision=None,
            revision_status="pending",
            normalization=None,
            instruction=None,
            distance=None,
            identity_status="pending",
        ),
    )


def _letta_build_identity(config_manifest: dict[str, Any]) -> BuildIdentityDeclaration:
    """声明 Letta current core-block profile 的 embedding 不适用。"""

    if config_manifest.get("embedding_provider") is not None:
        raise ConfigurationError(
            "Letta sleeptime core-block profile must not declare an embedding provider"
        )
    return BuildIdentityDeclaration(
        implementation_variant="product",
        embedding_profile="not_applicable_v1",
        historical_controlled_build_equivalent_to_current_main=False,
        embedding=EmbeddingIdentity(
            provider=None,
            model=None,
            dimension=None,
            revision=None,
            revision_status="not_applicable",
            normalization=None,
            instruction=None,
            distance=None,
            identity_status="not_applicable",
        ),
    )


def _langmem_build_identity(
    config_manifest: dict[str, Any],
) -> BuildIdentityDeclaration:
    """解析 LangMem controlled MiniLM + InMemoryStore cosine build。"""

    provider = _manifest_text(config_manifest, "embedding_provider")
    model = _manifest_text(config_manifest, "embedding_model_path")
    dimension = _manifest_dimension(config_manifest, "embedding_dimension")
    normalization = config_manifest.get("embedding_normalize")
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    if (
        provider == "sentence-transformers-local"
        and model_key == "all-minilm-l6-v2"
        and dimension == 384
        and normalization is True
    ):
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="controlled_embedding_v1",
            historical_controlled_build_equivalent_to_current_main=False,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=dimension,
                revision=None,
                revision_status="local_unpinned",
                normalization="external_l2",
                instruction=None,
                distance="langgraph-inmemory-cosine",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider=provider,
        model=model,
        dimension=dimension,
    )


def _mem0_build_identity(config_manifest: dict[str, Any]) -> BuildIdentityDeclaration:
    """按当前 Mem0 config 解析 controlled 或真实 product-default build。"""

    provider = _manifest_text(config_manifest, "embedding_provider")
    model = _manifest_text(config_manifest, "embedding_model")
    dimension = _manifest_dimension(config_manifest, "embedding_dimensions")
    provider_key = "" if provider is None else provider.strip().lower()
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    if provider_key == "huggingface" and model_key == "all-minilm-l6-v2" and dimension == 384:
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="controlled_embedding_v1",
            historical_controlled_build_equivalent_to_current_main=False,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=dimension,
                revision=None,
                revision_status="local_unpinned",
                normalization=None,
                instruction=None,
                distance="qdrant-cosine",
                identity_status="declared",
            ),
        )
    if provider_key == "openai" and model_key == "text-embedding-3-small" and dimension == 1536:
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="product_default_v1",
            historical_controlled_build_equivalent_to_current_main=False,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=dimension,
                revision=None,
                revision_status="provider_managed_unpinned",
                normalization=None,
                instruction=None,
                distance="qdrant-cosine",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider=provider,
        model=model,
        dimension=dimension,
    )


def _lightmem_build_identity(config_manifest: dict[str, Any]) -> BuildIdentityDeclaration:
    """按当前 LightMem config 解析 canonical-required MiniLM build。"""

    provider = _manifest_text(config_manifest, "embedding_provider")
    model = _manifest_text(config_manifest, "embedding_model_path")
    dimension = _manifest_dimension(config_manifest, "embedding_dimensions")
    provider_key = "" if provider is None else provider.strip().lower()
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    if (
        provider_key == "huggingface-local"
        and model_key == "all-minilm-l6-v2"
        and dimension == 384
    ):
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="product_canonical_required_config_v1",
            historical_controlled_build_equivalent_to_current_main=True,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=dimension,
                revision=None,
                revision_status="local_unpinned",
                normalization=None,
                instruction=None,
                distance="qdrant-cosine",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider=provider,
        model=model,
        dimension=dimension,
    )


def _memoryos_build_identity(config_manifest: dict[str, Any]) -> BuildIdentityDeclaration:
    """解析当前 memoryos-pypi 产品 build；ChromaDB fork 不得冒充当前 run。"""

    model = _manifest_text(config_manifest, "embedding_model_name")
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    engine = _manifest_text(config_manifest, "engine")
    if engine is not None and engine != "memoryos-pypi":
        raise ConfigurationError(
            "MemoryOS track identity only supports the product engine "
            "'memoryos-pypi'; non-product forks require a separate reproduction "
            f"variant, got engine={engine!r}"
        )
    if engine == "memoryos-pypi" and model_key == "all-minilm-l6-v2":
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="product_default_v1",
            historical_controlled_build_equivalent_to_current_main=True,
            embedding=EmbeddingIdentity(
                provider="sentence-transformers",
                model=model,
                dimension=384,
                revision=None,
                revision_status="local_unpinned",
                normalization="external_l2",
                instruction=None,
                distance="faiss-inner-product",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider="sentence-transformers" if model is not None else None,
        model=model,
        dimension=None,
    )


def _amem_build_identity(config_manifest: dict[str, Any]) -> BuildIdentityDeclaration:
    """解析 A-Mem 产品默认 MiniLM + Chroma cosine build。"""

    provider = _manifest_text(config_manifest, "embedding_provider")
    model = _manifest_text(config_manifest, "embedding_model")
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    if provider == "sentence-transformers" and model_key == "all-minilm-l6-v2":
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="product_default_v1",
            historical_controlled_build_equivalent_to_current_main=True,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=384,
                revision=None,
                revision_status="local_unpinned",
                normalization="none",
                instruction=None,
                distance="chroma-cosine",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider=provider,
        model=model,
        dimension=None,
    )


def _simplemem_build_identity(config_manifest: dict[str, Any]) -> BuildIdentityDeclaration:
    """解析 SimpleMem controlled MiniLM + LanceDB L2 build。"""

    provider = _manifest_text(config_manifest, "embedding_provider")
    model = _manifest_text(config_manifest, "embedding_model_path")
    dimension = _manifest_dimension(config_manifest, "embedding_dimension")
    model_key = "" if model is None else model.strip().split("/")[-1].lower()
    if (
        provider == "sentence-transformers-local"
        and model_key == "all-minilm-l6-v2"
        and dimension == 384
    ):
        return BuildIdentityDeclaration(
            implementation_variant="product",
            embedding_profile="controlled_embedding_v1",
            historical_controlled_build_equivalent_to_current_main=True,
            embedding=EmbeddingIdentity(
                provider=provider,
                model=model,
                dimension=dimension,
                revision=None,
                revision_status="local_unpinned",
                normalization="internal_l2",
                instruction=None,
                distance="lancedb-l2",
                identity_status="declared",
            ),
        )
    return _pending_build_identity(
        provider=provider,
        model=model,
        dimension=dimension,
    )


_MAIN_PROFILE_SECTIONS = (
    ("smoke", "method"),
    ("pilot", "method"),
    ("official-full", "method"),
)

_REGISTRATIONS = {
    "amem": MethodRegistration(
        name="amem",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/amem.toml"),
        config_type=AMemConfig,
        requires_api=True,
        system_factory=_build_amem_system,
        source_identity_factory=build_amem_source_identity,
        model_name_getter=_amem_model_name,
        max_workers_getter=_amem_max_workers,
        display_name="A-Mem",
        protocol_version="v3",
        consume_granularity_resolver=_turn_consume_granularity,
        provenance_granularity="none",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_amem_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _amem_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        clean_failed_ingest_state=_clean_amem_failed_ingest_state,
        build_identity_resolver=_amem_build_identity,
    ),
    "everos": MethodRegistration(
        name="everos",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/everos.toml"),
        config_type=EverOSConfig,
        requires_api=True,
        system_factory=_build_everos_system,
        source_identity_factory=build_everos_source_identity,
        model_name_getter=_everos_model_name,
        max_workers_getter=_everos_max_workers,
        display_name="EverOS",
        protocol_version="v3",
        consume_granularity_resolver=_session_consume_granularity,
        provenance_granularity="none",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_everos_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _everos_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        supports_shared_instance_parallelism=False,
        clean_failed_ingest_state=_clean_everos_failed_ingest_state,
        build_identity_resolver=_everos_build_identity,
        variant_validator=validate_everos_variant,
    ),
    "graphiti": MethodRegistration(
        name="graphiti",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/graphiti.toml"),
        config_type=GraphitiConfig,
        requires_api=True,
        system_factory=_build_graphiti_system,
        source_identity_factory=build_graphiti_source_identity,
        model_name_getter=_graphiti_model_name,
        max_workers_getter=_graphiti_max_workers,
        display_name="Graphiti OSS",
        protocol_version="v3",
        consume_granularity_resolver=_turn_consume_granularity,
        provenance_granularity="turn",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_graphiti_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _graphiti_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        supports_shared_instance_parallelism=False,
        clean_failed_ingest_state=_clean_graphiti_failed_ingest_state,
        build_identity_resolver=_graphiti_build_identity,
        variant_validator=validate_graphiti_variant,
    ),
    "mem0": MethodRegistration(
        name="mem0",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/mem0.toml"),
        config_type=Mem0Config,
        requires_api=True,
        system_factory=_build_mem0_system,
        source_identity_factory=build_mem0_source_identity,
        model_name_getter=_mem0_model_name,
        max_workers_getter=_mem0_max_workers,
        display_name="Mem0",
        protocol_version="v3",
        consume_granularity_resolver=_mem0_consume_granularity,
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_mem0_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _mem0_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        provenance_granularity="turn",
        retrieval_evidence_contract_version="v1",
        clean_failed_ingest_state=_clean_mem0_failed_ingest_state,
        supports_shared_instance_parallelism=False,
        build_identity_resolver=_mem0_build_identity,
    ),
    "lightmem": MethodRegistration(
        name="lightmem",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/lightmem.toml"),
        config_type=LightMemConfig,
        requires_api=True,
        system_factory=_build_lightmem_system,
        source_identity_factory=build_lightmem_source_identity,
        model_name_getter=_lightmem_model_name,
        max_workers_getter=_lightmem_max_workers,
        display_name="LightMem",
        protocol_version="v3",
        consume_granularity_resolver=_lightmem_consume_granularity,
        provenance_granularity="turn",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_lightmem_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _lightmem_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        clean_failed_ingest_state=_clean_lightmem_failed_ingest_state,
        build_identity_resolver=_lightmem_build_identity,
    ),
    "memoryos": MethodRegistration(
        name="memoryos",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/memoryos.toml"),
        config_type=MemoryOSPaperConfig,
        requires_api=True,
        system_factory=_build_memoryos_system,
        source_identity_factory=build_memoryos_source_identity,
        model_name_getter=_memoryos_model_name,
        max_workers_getter=_memoryos_max_workers,
        display_name="MemoryOS",
        protocol_version="v3",
        consume_granularity_resolver=_memoryos_consume_granularity,
        provenance_granularity="turn",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        workload_estimator=_estimate_memoryos_update_batches,
        efficiency_model_inventory_getter=_memoryos_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _memoryos_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        clean_failed_ingest_state=_clean_memoryos_failed_ingest_state,
        build_identity_resolver=_memoryos_build_identity,
    ),
    "letta": MethodRegistration(
        name="letta",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/letta.toml"),
        config_type=LettaConfig,
        requires_api=True,
        system_factory=_build_letta_system,
        source_identity_factory=build_letta_source_identity,
        model_name_getter=_letta_model_name,
        max_workers_getter=_letta_max_workers,
        display_name="Letta/MemGPT",
        protocol_version="v3",
        consume_granularity_resolver=_session_consume_granularity,
        provenance_granularity="none",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=False,
        efficiency_model_inventory_getter=_letta_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _letta_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        supports_shared_instance_parallelism=False,
        clean_failed_ingest_state=_clean_letta_failed_ingest_state,
        build_identity_resolver=_letta_build_identity,
        max_parallel_workers=1,
    ),
    "langmem": MethodRegistration(
        name="langmem",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/langmem.toml"),
        config_type=LangMemConfig,
        requires_api=True,
        system_factory=_build_langmem_system,
        source_identity_factory=build_langmem_source_identity,
        model_name_getter=_langmem_model_name,
        max_workers_getter=_langmem_max_workers,
        display_name="LangMem",
        protocol_version="v3",
        consume_granularity_resolver=_session_consume_granularity,
        provenance_granularity="none",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_langmem_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _langmem_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        supports_shared_instance_parallelism=False,
        clean_failed_ingest_state=_clean_langmem_failed_ingest_state,
        build_identity_resolver=_langmem_build_identity,
    ),
    "memos": MethodRegistration(
        name="memos",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/memos.toml"),
        config_type=MemOSConfig,
        requires_api=True,
        system_factory=_build_memos_system,
        source_identity_factory=build_memos_source_identity,
        model_name_getter=_memos_model_name,
        max_workers_getter=_memos_max_workers,
        display_name="MemOS",
        protocol_version="v3",
        consume_granularity_resolver=_session_consume_granularity,
        provenance_granularity="none",
        retrieval_evidence_contract_version="v1",
        # runner 的 isolated worker 只能隔离 provider 对象；MemOSRuntimeOwner
        # 仍会按同一 config 复用进程级 runtime/embedder。真实 LME W2 已触发
        # tokenizer `Already borrowed`，故必须在 runtime/API 启动前拒绝覆盖。
        allow_smoke_worker_override=False,
        efficiency_model_inventory_getter=_memos_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _memos_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        supports_shared_instance_parallelism=False,
        clean_failed_ingest_state=_clean_memos_failed_ingest_state,
        build_identity_resolver=_memos_build_identity,
        max_parallel_workers=1,
    ),
    "simplemem": MethodRegistration(
        name="simplemem",
        task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        profile_sections=_MAIN_PROFILE_SECTIONS,
        profile_relative_path=Path("configs/methods/simplemem.toml"),
        config_type=SimpleMemConfig,
        requires_api=True,
        system_factory=_build_simplemem_system,
        source_identity_factory=build_simplemem_source_identity,
        model_name_getter=_simplemem_model_name,
        max_workers_getter=_simplemem_max_workers,
        display_name="SimpleMem",
        protocol_version="v3",
        consume_granularity_resolver=_turn_consume_granularity,
        provenance_granularity="none",
        retrieval_evidence_contract_version="v1",
        allow_smoke_worker_override=True,
        efficiency_model_inventory_getter=_simplemem_efficiency_model_inventory,
        efficiency_instrumentation_identity_getter=(
            _simplemem_efficiency_instrumentation_identity
        ),
        retrieval_observation_contract_getter=_separable_retrieval_contract,
        supports_shared_instance_parallelism=False,
        clean_failed_ingest_state=_clean_simplemem_failed_ingest_state,
        build_identity_resolver=_simplemem_build_identity,
    ),
}


def list_methods() -> list[str]:
    """返回统一入口当前支持的 method 名称。"""

    return sorted(_REGISTRATIONS)


def get_method_registration(method_name: str) -> MethodRegistration:
    """读取 method 注册信息，未知名称时给出支持列表。"""

    try:
        return _REGISTRATIONS[method_name]
    except KeyError as exc:
        supported = ", ".join(list_methods())
        raise ConfigurationError(
            f"Unknown method '{method_name}'. Supported: {supported}"
        ) from exc


def resolve_registered_factory_provenance_granularity(
    system_factory: Callable[[MethodBuildContext], MemoryProvider],
) -> str | None:
    """按注册 factory 身份返回静态 provenance 粒度，未注册时返回 None。"""

    for registration in _REGISTRATIONS.values():
        if registration.system_factory is system_factory:
            return registration.provenance_granularity
    return None


def resolve_registered_factory_retrieval_evidence_contract_version(
    system_factory: Callable[[MethodBuildContext], MemoryProvider],
) -> str | None:
    """按注册 factory 身份返回逐题 retrieval evidence 契约版本，未注册时返回 None。

    该解析与 `resolve_registered_factory_provenance_granularity` 同构：只靠
    `system_factory` 身份匹配，无需构造真实 method 实例，因此 workers>1 的根进程也能
    在不实例化 method 的前提下为 manifest 盖章。
    """

    for registration in _REGISTRATIONS.values():
        if registration.system_factory is system_factory:
            return registration.retrieval_evidence_contract_version
    return None


def resolve_registered_factory_consume_granularity(
    system_factory: Callable[[MethodBuildContext], MemoryProvider],
    benchmark_name: str | None,
) -> ConsumeGranularity | None:
    """按注册 factory 与 benchmark 返回 concrete 消费粒度。"""

    for registration in _REGISTRATIONS.values():
        if registration.system_factory is system_factory:
            return registration.resolve_consume_granularity(benchmark_name)
    return None


def resolve_registered_build_identity(
    method_name: str,
    config_manifest: dict[str, Any],
) -> BuildIdentityDeclaration:
    """按注册方法名从当前 config manifest 解析完整 build 身份。

    输入:
        method_name: method registry 名。
        config_manifest: ``method.config.to_manifest()`` 产生的公开配置字典。

    输出:
        完整不可变声明；值必须与 ``method.config`` 同一真实值，未知语义用 pending
        与 null 表达，不得提前写入未来配置。
    """

    registration = get_method_registration(method_name.strip().lower())
    if registration.build_identity_resolver is None:
        raise ConfigurationError(
            f"Registered method '{method_name}' does not declare build identity"
        )
    return registration.build_identity_resolver(config_manifest)


def _legacy_main_section_name(profile_name: str) -> str | None:
    """返回单一 `[method]` 迁移前的主 section 名；非主 profile 返回 None。"""

    normalized = profile_name.strip().lower()
    if normalized in {"smoke", "pilot"}:
        return "smoke"
    if normalized in {"official-full", "official_full"}:
        return "official_full"
    return None


def _load_registered_method_section(
    *,
    registration: MethodRegistration,
    profile_name: str,
    profile_path: Path,
) -> tuple[ProfileSection, bool]:
    """读取 current 单一 section，或严格回退到迁移前 legacy section。

    返回值第二项只在实际读取 `[method]` 时为 True。回退仅用于旧 fixture/旧 checkout
    兼容；current TOML 一旦存在 `[method]` 就不会再读取旧双 section。
    """

    requested = registration.resolve_profile_section(profile_name)
    try:
        section = load_profile_section(profile_path, requested)
        return section, requested == "method"
    except ConfigurationError as exc:
        if requested != "method" or "Missing profile section 'method'" not in str(exc):
            raise
        legacy_name = _legacy_main_section_name(profile_name)
        if legacy_name is None:
            raise
        return load_profile_section(profile_path, legacy_name), False


def _framework_owned_config_bindings(
    *,
    config_type: type[Any],
    composition: RunComposition,
) -> dict[str, Any]:
    """为 legacy adapter dataclass 注入 runtime/execution 所有字段。

    method TOML 不再重复这些值；在十家 adapter dataclass 完成逐家 schema 瘦身前，
    组合根仍以显式字段名做兼容绑定。只注入目标 dataclass 真实声明的字段，未知字段
    继续由 `build_typed_profile` fail-fast。
    """

    declared = {field.name for field in fields(config_type) if field.init}
    runtime = composition.runtime
    execution = composition.execution
    candidates: dict[str, Any] = {
        "llm_model": runtime.model,
        "extraction_model": runtime.model,
        "reader_model": runtime.model,
        "api_timeout_seconds": runtime.timeout_seconds,
        "api_max_retries": runtime.max_retries,
        "api_retry_wait_seconds": runtime.retry_wait_seconds,
        "api_retry_backoff_multiplier": runtime.retry_backoff_multiplier,
        "api_retry_max_wait_seconds": runtime.retry_max_wait_seconds,
        "structured_output_mode": runtime.structured_output_mode,
        "max_workers": composition.resolved_max_workers,
        "worker_request_timeout_seconds": execution.worker_request_timeout_seconds,
        "drain_timeout_seconds": execution.drain_timeout_seconds,
        "task_timeout_seconds": execution.task_timeout_seconds,
        "postgres_startup_timeout_seconds": (
            execution.service_startup_timeout_seconds
        ),
        "suppress_official_stdout": execution.suppress_method_stdout,
    }
    return {key: value for key, value in candidates.items() if key in declared}


def _build_current_method_config(
    *,
    section: ProfileSection,
    registration: MethodRegistration,
    composition: RunComposition,
) -> tuple[Any, dict[str, Any]]:
    """把单一 method 参数与 framework bindings 组合成现有 adapter config。"""

    bindings = _framework_owned_config_bindings(
        config_type=registration.config_type,
        composition=composition,
    )
    overlap = sorted(set(section.values).intersection(bindings))
    if overlap:
        raise ConfigurationError(
            "Single-source method section must not redeclare framework-owned key(s): "
            + ", ".join(overlap)
        )
    merged = ProfileSection(
        source_path=section.source_path,
        name=section.name,
        values={**section.values, **bindings},
    )
    config = build_typed_profile(merged, registration.config_type)
    manifest = config.to_manifest()
    if not isinstance(manifest, dict):
        raise ConfigurationError("method config to_manifest() must return a dict")
    method_manifest = {
        key: value for key, value in manifest.items() if key not in bindings
    }
    return config, method_manifest


def load_method_profile(
    method_name: str,
    profile_name: str,
    project_root: str | Path | None = None,
) -> Any:
    """从 method 的 TOML 文件构造强类型 profile。

    输入:
        method_name: registry 中的 method 名称。
        profile_name: TOML section 名称。
        project_root: 用于定位 `configs/` 的项目根目录。

    输出:
        Any: registration 声明的强类型 method 配置实例。
    """

    registration = get_method_registration(method_name)
    root = load_path_settings(project_root).project_root
    profile_path = root / registration.profile_relative_path
    section, current_single_source = _load_registered_method_section(
        registration=registration,
        profile_name=profile_name,
        profile_path=profile_path,
    )
    if not current_single_source:
        return build_typed_profile(
            section,
            registration.config_type,
            reserved_keys=FRAMEWORK_PROFILE_KEYS,
        )
    composition = load_run_composition(
        project_root=root,
        profile_name=profile_name,
        method_max_workers_cap=registration.max_parallel_workers,
    )
    config, _ = _build_current_method_config(
        section=section,
        registration=registration,
        composition=composition,
    )
    return config


def resolve_method_profile(
    method_name: str,
    profile_name: str,
    project_root: str | Path | None = None,
) -> ResolvedMethodProfile:
    """解析新 run 的 TOML section、完整 answer builder 与 method config。

    ``answer_builder`` 是每个已注册 section 的必填 framework 字段。该函数先把它
    从原始 section 中分离，再让 method dataclass 对剩余字段保持原有严格校验；因此
    不会为迁移而放宽任意未知 key。
    """

    registration = get_method_registration(method_name)
    root = load_path_settings(project_root).project_root
    profile_path = root / registration.profile_relative_path
    section, current_single_source = _load_registered_method_section(
        registration=registration,
        profile_name=profile_name,
        profile_path=profile_path,
    )
    section_name = section.name
    answer_builder = section.values.get(
        "answer_builder",
        "benchmark" if current_single_source else None,
    )
    if type(answer_builder) is not str or not answer_builder.strip():
        raise ConfigurationError(
            f"Profile '{section_name}' in {section.source_path} must declare a "
            "non-blank answer_builder"
        )
    if answer_builder != answer_builder.strip():
        raise ConfigurationError(
            f"Profile '{section_name}' answer_builder must not contain outer whitespace"
        )
    composition = load_run_composition(
        project_root=root,
        profile_name=profile_name,
        method_max_workers_cap=registration.max_parallel_workers,
    )
    method_config_manifest: dict[str, Any] | None = None
    if current_single_source:
        if "answer_builder" in section.values:
            raise ConfigurationError(
                "Main [method] section must not declare answer_builder; benchmark "
                "evaluation owns the main builder"
            )
        config, method_config_manifest = _build_current_method_config(
            section=section,
            registration=registration,
            composition=composition,
        )
    else:
        config = build_typed_profile(
            section,
            registration.config_type,
            reserved_keys=FRAMEWORK_PROFILE_KEYS,
        )
    return ResolvedMethodProfile(
        public_name=profile_name,
        section_name=section_name,
        answer_builder=answer_builder,
        config=config,
        composition=composition,
        method_config_manifest=method_config_manifest,
    )


def _sha256_file(path: Path) -> str:
    """计算文件 SHA-256，用于 wrapper 插桩身份。"""

    if not path.is_file():
        raise ConfigurationError(f"Instrumentation wrapper file missing: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


__all__ = [
    "MethodBuildContext",
    "MethodRegistration",
    "ResolvedMethodProfile",
    "get_method_registration",
    "list_methods",
    "load_method_profile",
    "resolve_method_profile",
    "resolve_registered_factory_consume_granularity",
    "resolve_registered_factory_provenance_granularity",
    "resolve_registered_factory_retrieval_evidence_contract_version",
    "resolve_registered_build_identity",
]
