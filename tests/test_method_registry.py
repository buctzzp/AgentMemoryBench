"""测试统一 method registry 的能力声明、profile 和 system factory 装配。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import (
    ConfigurationError,
    Conversation,
    MethodCapability,
    TaskFamily,
    validate_compatibility,
)
from memory_benchmark.methods.everos_adapter import EverOSConfig
from memory_benchmark.methods.graphiti_adapter import GraphitiConfig
from memory_benchmark.methods.langmem_adapter import LangMemConfig
from memory_benchmark.methods.letta_adapter import LettaConfig
from memory_benchmark.methods.lightmem_adapter import LightMemConfig
from memory_benchmark.methods.mem0_adapter import Mem0Config
from memory_benchmark.methods.memoryos_adapter import MemoryOSPaperConfig
from memory_benchmark.methods.memos_adapter import MemOSConfig
from memory_benchmark.methods.simplemem_adapter import SimpleMemConfig
from memory_benchmark.methods.registry import (
    MethodBuildContext,
    get_method_registration,
    list_methods,
    load_method_profile,
    resolve_method_profile,
)


pytestmark = pytest.mark.unit


def test_registry_lists_conversation_qa_methods() -> None:
    """统一入口应暴露当前已接入的 conversation-QA method。"""

    assert list_methods() == [
        "amem",
        "everos",
        "graphiti",
        "langmem",
        "letta",
        "lightmem",
        "mem0",
        "memoryos",
        "memos",
        "simplemem",
    ]


@pytest.mark.parametrize("method_name", list_methods())
def test_pilot_profile_reuses_smoke_section_with_distinct_public_identity(
    method_name: str,
) -> None:
    """十家 pilot 只复用 smoke TOML 参数，不伪造第三份算法 section。"""

    resolved = resolve_method_profile(
        method_name,
        "pilot",
        project_root=load_path_settings().project_root,
    )

    assert resolved.public_name == "pilot"
    assert resolved.section_name == "smoke"
    assert resolved.config.profile_name == "smoke"


def test_mem0_registration_declares_capabilities_factory_and_api_boundary() -> None:
    """Mem0 registration 应声明通用能力和 factory，不持有运行期 secret。"""

    registration = get_method_registration("mem0")

    assert registration.task_families == frozenset({TaskFamily.CONVERSATION_QA})
    assert registration.provided_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.MEMORY_RETRIEVAL,
        }
    )
    assert registration.profile_names == frozenset(
        {"smoke", "pilot", "official-full"}
    )
    assert registration.requires_api is True
    assert registration.profile_relative_path == Path("configs/methods/mem0.toml")
    assert registration.system_factory is not None
    assert registration.source_identity_factory is not None
    assert registration.model_name_getter is not None
    assert registration.max_workers_getter is not None
    assert registration.supports_shared_instance_parallelism is False
    assert not hasattr(registration, "supported_benchmarks")
    assert not hasattr(registration, "predictor")
    assert not hasattr(registration, "api_key")


def test_mem0_registration_model_inventory_excludes_unused_answer_llm() -> None:
    """Mem0 inventory 不应声明 registered 主路径从不调用的 legacy reader。

    registered v3 主路径的最终回答由 framework reader 生成；Mem0
    ``get_answer()`` 里的 ``mem0-answer-llm`` 只在直接调用兼容接口时产生
    observation，不能混入 registered run 的预声明 inventory。
    """

    registration = get_method_registration("mem0")

    assert registration.efficiency_model_inventory_getter is not None
    assert registration.efficiency_instrumentation_identity_getter is not None
    inventory = registration.efficiency_model_inventory_getter(Mem0Config.smoke())
    model_ids = [model.model_id for model in inventory]

    assert model_ids == ["mem0-memory-llm", "mem0-embedding"]
    assert "mem0-answer-llm" not in model_ids


def test_memoryos_registration_uses_generic_contract() -> None:
    """MemoryOS registration 应声明统一 runner 所需的完整静态契约。"""

    registration = get_method_registration("memoryos")

    assert registration.config_type is MemoryOSPaperConfig
    assert registration.profile_names == frozenset(
        {"smoke", "pilot", "official-full"}
    )
    assert registration.task_families == frozenset({TaskFamily.CONVERSATION_QA})
    assert registration.provided_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.MEMORY_RETRIEVAL,
        }
    )
    assert registration.profile_relative_path == Path("configs/methods/memoryos.toml")
    assert registration.requires_api is True


def test_simplemem_registration_declares_text_backend_contract() -> None:
    """SimpleMem registration 应声明 v3 retrieve-first text backend 契约。"""

    registration = get_method_registration("simplemem")

    assert registration.config_type is SimpleMemConfig
    assert registration.profile_names == frozenset(
        {"smoke", "pilot", "official-full"}
    )
    assert registration.task_families == frozenset({TaskFamily.CONVERSATION_QA})
    assert registration.provided_capabilities == frozenset(
        {
            MethodCapability.CONVERSATION_ADD,
            MethodCapability.MEMORY_RETRIEVAL,
        }
    )
    assert registration.profile_relative_path == Path("configs/methods/simplemem.toml")
    assert registration.requires_api is True
    assert registration.allow_smoke_worker_override is True
    assert registration.supports_shared_instance_parallelism is False
    assert registration.provenance_granularity == "none"
    assert registration.retrieval_evidence_contract_version == "v1"
    assert registration.efficiency_model_inventory_getter is not None
    inventory = registration.efficiency_model_inventory_getter(
        SimpleMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/Qwen3-Embedding-0.6B",
            embedding_dimension=1024,
            window_size=40,
            overlap_size=2,
            semantic_top_k=25,
            keyword_top_k=5,
            structured_top_k=5,
            max_workers=1,
        )
    )
    assert [model.model_id for model in inventory] == [
        "simplemem-llm",
        "simplemem-embedding",
    ]


def test_lightmem_registration_model_inventory_excludes_unused_answer_llm() -> None:
    """LightMem model inventory 不应声明 registered 主路径从不调用的 answer_llm。

    registered v3 主路径只调 `ingest()`/`retrieve()`，最终 answer LLM 由 framework
    `FrameworkAnswerReader` 调用并单独追加进 model inventory；`LightMem.get_answer()`
    内部记录的 `lightmem-answer-llm` 只在直接调用该 legacy 接口时才会产生
    observation，不属于 registered 主路径实际引用的模型。instrumentation identity
    getter 必须同时保留，不能因为裁掉一个模型条目就连带丢失。
    """

    registration = get_method_registration("lightmem")

    assert registration.efficiency_model_inventory_getter is not None
    assert registration.efficiency_instrumentation_identity_getter is not None
    inventory = registration.efficiency_model_inventory_getter(
        LightMemConfig(
            llm_model="gpt-4o-mini",
            embedding_model_path="models/all-MiniLM-L6-v2",
            llmlingua_model_path=(
                "models/llmlingua-2-bert-base-multilingual-cased-meetingbank"
            ),
            retrieve_limit=60,
            max_workers=1,
        )
    )
    model_ids = [model.model_id for model in inventory]

    assert model_ids == ["lightmem-memory-llm", "lightmem-embedding"]
    assert "lightmem-answer-llm" not in model_ids


def test_built_in_methods_advertise_memory_retrieval_capability() -> None:
    """retrieve-first prediction 要求内置 method 声明 memory_retrieval。"""

    for method_name in (
        "mem0",
        "memoryos",
        "amem",
        "everos",
        "graphiti",
        "langmem",
        "letta",
        "lightmem",
        "simplemem",
        "memos",
    ):
        registration = get_method_registration(method_name)

        assert MethodCapability.CONVERSATION_ADD in registration.provided_capabilities
        assert MethodCapability.MEMORY_RETRIEVAL in registration.provided_capabilities
        assert (
            MethodCapability.ANSWER_GENERATION
            not in registration.provided_capabilities
        )


@pytest.mark.parametrize(
    ("method_name", "benchmark_name", "expected"),
    [
        ("amem", "membench", "turn"),
        ("simplemem", "halumem", "turn"),
        ("mem0", "longmemeval", "session"),
        ("mem0", "halumem", "session"),
        ("mem0", "beam", "pair"),
        ("mem0", "membench", "turn"),
        ("lightmem", "locomo", "turn"),
        ("lightmem", "membench", "pair"),
        ("lightmem", "longmemeval", "pair"),
        ("lightmem", "beam", "pair"),
        ("lightmem", "halumem", "session"),
        ("memoryos", "longmemeval", "pair"),
        ("memoryos", "membench", "session"),
        ("everos", "locomo", "session"),
        ("everos", "longmemeval", "session"),
        ("everos", "membench", "session"),
        ("everos", "beam", "session"),
        ("everos", "halumem", "session"),
        ("memos", "locomo", "session"),
        ("memos", "longmemeval", "session"),
        ("memos", "membench", "session"),
        ("memos", "beam", "session"),
        ("memos", "halumem", "session"),
        ("letta", "locomo", "session"),
        ("letta", "longmemeval", "session"),
        ("letta", "membench", "session"),
        ("letta", "beam", "session"),
        ("letta", "halumem", "session"),
        ("langmem", "locomo", "session"),
        ("langmem", "longmemeval", "session"),
        ("langmem", "membench", "session"),
        ("langmem", "beam", "session"),
        ("langmem", "halumem", "session"),
        ("graphiti", "locomo", "turn"),
        ("graphiti", "longmemeval", "turn"),
        ("graphiti", "membench", "turn"),
        ("graphiti", "beam", "turn"),
        ("graphiti", "halumem", "turn"),
    ],
)
def test_registration_resolves_concrete_consume_granularity(
    method_name: str,
    benchmark_name: str,
    expected: str,
) -> None:
    """注册级 resolver 应锁定各 method 已裁定的 benchmark 消费粒度。"""

    registration = get_method_registration(method_name)

    assert registration.resolve_consume_granularity(benchmark_name) == expected


def test_clean_retry_support_is_only_declared_by_methods_with_safe_state_cleanup() -> None:
    """只有能安全清理单个 conversation 状态的内置 method 才声明 clean retry。

    输入:
        registry 中四个内置 method。

    输出:
        五个内置 method 均有经审计的 conversation 级 clean hook；Mem0 的 hook
        同时按 run_id 清 Qdrant、recent messages 和 provenance sidecar。
    """

    assert get_method_registration("amem").clean_failed_ingest_state is not None
    assert get_method_registration("lightmem").clean_failed_ingest_state is not None
    assert get_method_registration("memoryos").clean_failed_ingest_state is not None
    assert get_method_registration("mem0").clean_failed_ingest_state is not None
    assert get_method_registration("simplemem").clean_failed_ingest_state is not None
    assert get_method_registration("memos").clean_failed_ingest_state is not None
    assert get_method_registration("letta").clean_failed_ingest_state is not None
    assert get_method_registration("langmem").clean_failed_ingest_state is not None
    assert get_method_registration("everos").clean_failed_ingest_state is not None
    assert get_method_registration("graphiti").clean_failed_ingest_state is not None


def test_graphiti_registration_declares_direct_core_product_contract() -> None:
    """Graphiti 注册应固定 turn 粒度、embedded store 与受控 MiniLM。"""

    registration = get_method_registration("graphiti")
    config = load_method_profile(
        "graphiti",
        "smoke",
        project_root=load_path_settings().project_root,
    )

    assert isinstance(config, GraphitiConfig)
    assert registration.profile_names == frozenset(
        {"smoke", "pilot", "official-full"}
    )
    assert registration.profile_relative_path == Path("configs/methods/graphiti.toml")
    assert registration.requires_api is True
    assert registration.allow_smoke_worker_override is True
    assert registration.supports_shared_instance_parallelism is False
    assert registration.provenance_granularity == "turn"
    assert registration.retrieval_evidence_contract_version == "v1"
    assert registration.resolve_consume_granularity("locomo") == "turn"
    assert registration.efficiency_model_inventory_getter is not None
    inventory = registration.efficiency_model_inventory_getter(config)
    assert [entry.model_id for entry in inventory] == [
        "graphiti-build-llm",
        "graphiti-embedding",
    ]
    assert [entry.model_role for entry in inventory] == [
        "memory_build_llm",
        "embedding",
    ]
    declaration = registration.build_identity_resolver(config.to_manifest())
    assert declaration.implementation_variant == "product"
    assert declaration.embedding_profile == "controlled_embedding_v1"
    assert declaration.embedding.dimension == 384
    assert declaration.embedding.normalization == "l2-normalized"
    assert declaration.embedding.distance == "falkordb-cosine"
    registration.validate_variant("membench", "0_10k")
    with pytest.raises(ConfigurationError, match="does not support MemBench"):
        registration.validate_variant("membench", "100k")


def test_letta_registration_declares_sleeptime_product_contract() -> None:
    """Letta 注册应固定 session 粒度、W1 与唯一 build LLM。"""

    registration = get_method_registration("letta")
    config = load_method_profile(
        "letta",
        "smoke",
        project_root=load_path_settings().project_root,
    )

    assert isinstance(config, LettaConfig)
    assert registration.profile_names == frozenset(
        {"smoke", "pilot", "official-full"}
    )
    assert registration.profile_relative_path == Path("configs/methods/letta.toml")
    assert registration.requires_api is True
    assert registration.allow_smoke_worker_override is False
    assert registration.supports_shared_instance_parallelism is False
    assert registration.provenance_granularity == "none"
    assert registration.retrieval_evidence_contract_version == "v1"
    assert registration.resolve_consume_granularity("locomo") == "session"
    assert registration.efficiency_model_inventory_getter is not None
    inventory = registration.efficiency_model_inventory_getter(config)
    assert [entry.model_id for entry in inventory] == ["letta-build-llm"]
    assert [entry.model_role for entry in inventory] == ["memory_build_llm"]


def test_langmem_registration_declares_background_product_contract() -> None:
    """LangMem 注册应固定 session 粒度、async manager 与两类 build model。"""

    registration = get_method_registration("langmem")
    config = load_method_profile(
        "langmem",
        "smoke",
        project_root=load_path_settings().project_root,
    )

    assert isinstance(config, LangMemConfig)
    assert registration.profile_names == frozenset(
        {"smoke", "pilot", "official-full"}
    )
    assert registration.profile_relative_path == Path("configs/methods/langmem.toml")
    assert registration.requires_api is True
    assert registration.allow_smoke_worker_override is True
    assert registration.supports_shared_instance_parallelism is False
    assert registration.provenance_granularity == "none"
    assert registration.retrieval_evidence_contract_version == "v1"
    assert registration.resolve_consume_granularity("locomo") == "session"
    assert registration.efficiency_model_inventory_getter is not None
    inventory = registration.efficiency_model_inventory_getter(config)
    assert [entry.model_id for entry in inventory] == [
        "langmem-build-llm",
        "langmem-embedding",
    ]
    assert [entry.model_role for entry in inventory] == [
        "memory_build_llm",
        "embedding",
    ]
    declaration = registration.build_identity_resolver(config.to_manifest())
    assert declaration.implementation_variant == "product"
    assert declaration.embedding_profile == "controlled_embedding_v1"
    assert declaration.embedding.dimension == 384
    assert declaration.embedding.normalization == "external_l2"
    assert declaration.embedding.distance == "langgraph-inmemory-cosine"


def test_everos_registration_declares_typed_product_session_contract() -> None:
    """EverOS 注册应锁 official lifespan、session 粒度和三类模型身份。"""

    registration = get_method_registration("everos")
    config = load_method_profile(
        "everos",
        "smoke",
        project_root=load_path_settings().project_root,
    )

    assert isinstance(config, EverOSConfig)
    assert registration.profile_names == frozenset(
        {"smoke", "pilot", "official-full"}
    )
    assert registration.profile_relative_path == Path("configs/methods/everos.toml")
    assert registration.requires_api is True
    assert registration.allow_smoke_worker_override is True
    assert registration.supports_shared_instance_parallelism is False
    assert registration.provenance_granularity == "none"
    assert registration.retrieval_evidence_contract_version == "v1"
    assert registration.resolve_consume_granularity("locomo") == "session"
    assert registration.efficiency_model_inventory_getter is not None
    inventory = registration.efficiency_model_inventory_getter(config)
    assert [entry.model_id for entry in inventory] == [
        "everos-build-llm",
        "everos-embedding",
        "everos-reranker",
    ]
    assert [entry.model_role for entry in inventory] == [
        "memory_build_llm",
        "embedding",
        "reranker",
    ]
    declaration = registration.build_identity_resolver(config.to_manifest())
    assert declaration.implementation_variant == "product"
    assert declaration.embedding_profile == "product_canonical_required_config_v1"
    assert declaration.embedding.provider == "openrouter-openai-compatible"
    assert declaration.embedding.model == "Qwen/Qwen3-Embedding-4B"
    assert declaration.embedding.dimension == 1024
    assert declaration.embedding.distance == "lancedb-l2"
    registration.validate_variant("membench", "0_10k")
    with pytest.raises(ConfigurationError, match="timestamp fabrication is forbidden"):
        registration.validate_variant("membench", "100k")

    official = load_method_profile(
        "everos",
        "official-full",
        project_root=load_path_settings().project_root,
    )
    official_declaration = registration.build_identity_resolver(
        official.to_manifest()
    )
    assert official_declaration.embedding_profile == "product_default_v1"
    assert official_declaration.embedding.provider == (
        "deepinfra-openai-compatible"
    )
    assert config.rerank_capability_mode == "disabled-zero-call"
    assert official.rerank_capability_mode == "configured"


def test_clean_retry_hook_uses_failed_worker_state_for_isolated_runs(
    tmp_path: Path,
) -> None:
    """isolated worker 失败重试时，应清理上次失败 worker 的 state 目录。

    输入:
        MethodBuildContext.storage_root 指向 run 级 `method_state/`，failed_state
        带 `worker_idx=2`。

    输出:
        A-Mem clean hook 删除 `method_state/worker_2/<conversation>/`，不会误删
        run 根目录下同名 conversation state。
    """

    root_state = tmp_path / "method_state" / "conv_1"
    worker_state = tmp_path / "method_state" / "worker_2" / "conv_1"
    root_state.mkdir(parents=True)
    worker_state.mkdir(parents=True)
    (root_state / "marker.txt").write_text("root", encoding="utf-8")
    (worker_state / "marker.txt").write_text("worker", encoding="utf-8")
    context = MethodBuildContext(
        config=None,
        openai_settings=None,
        path_settings=None,
        storage_root=tmp_path / "method_state",
    )
    conversation = Conversation(conversation_id="conv/1")

    clean_hook = get_method_registration("amem").clean_failed_ingest_state
    assert clean_hook is not None
    clean_hook(context, conversation, {"worker_idx": 2})

    assert root_state.exists()
    assert not worker_state.exists()


def test_compatibility_requires_task_family_and_capabilities() -> None:
    """兼容性校验应接受匹配的 task family 与 capability 子集。"""

    validate_compatibility(
        benchmark_task_family=TaskFamily.CONVERSATION_QA,
        required_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
        method_task_families=frozenset({TaskFamily.CONVERSATION_QA}),
        provided_capabilities=frozenset(
            {
                MethodCapability.CONVERSATION_ADD,
                MethodCapability.MEMORY_RETRIEVAL,
            }
        ),
    )


def test_compatibility_rejects_unsupported_task_family() -> None:
    """method 不支持 benchmark task family 时应抛配置错误。"""

    with pytest.raises(ConfigurationError, match="task family"):
        validate_compatibility(
            benchmark_task_family=TaskFamily.CONVERSATION_QA,
            required_capabilities=frozenset(),
            method_task_families=frozenset(),
            provided_capabilities=frozenset(),
        )


def test_compatibility_rejects_missing_capabilities() -> None:
    """method 缺少 benchmark 所需 capability 时应抛配置错误。"""

    with pytest.raises(ConfigurationError, match="required capabilities"):
        validate_compatibility(
            benchmark_task_family=TaskFamily.CONVERSATION_QA,
            required_capabilities=frozenset(
                {
                    MethodCapability.CONVERSATION_ADD,
                    MethodCapability.MEMORY_RETRIEVAL,
                }
            ),
            method_task_families=frozenset({TaskFamily.CONVERSATION_QA}),
            provided_capabilities=frozenset({MethodCapability.CONVERSATION_ADD}),
        )


def test_load_method_profile_returns_strongly_typed_mem0_config(
    tmp_path: Path,
) -> None:
    """registry 应通过 TOML loader 构造 owner method 的强类型配置。"""

    profile_path = tmp_path / "configs" / "methods" / "mem0.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
[smoke]
extraction_model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
embedding_dimensions = 1536
reader_model = "gpt-4o-mini"
top_k = 200
max_workers = 1
ingestion_chunk_size = 1
infer = true
""",
        encoding="utf-8",
    )

    config = load_method_profile(
        method_name="mem0",
        profile_name="smoke",
        project_root=tmp_path,
    )

    assert isinstance(config, Mem0Config)
    assert config.profile_name == "smoke"
    assert config.top_k == 200


def test_load_method_profile_maps_public_name_to_toml_section(
    tmp_path: Path,
) -> None:
    """registry 应集中维护 CLI profile 名与 TOML section 的映射。"""

    profile_path = tmp_path / "configs" / "methods" / "mem0.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
[official_full]
extraction_model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
embedding_dimensions = 1536
reader_model = "gpt-4o-mini"
top_k = 200
max_workers = 10
ingestion_chunk_size = 1
infer = true
""",
        encoding="utf-8",
    )

    config = load_method_profile(
        method_name="mem0",
        profile_name="official-full",
        project_root=tmp_path,
    )

    assert config.profile_name == "official_full"
    assert config.top_k == 200


def test_load_method_profile_returns_strongly_typed_simplemem_config(
    tmp_path: Path,
) -> None:
    """registry 应能从 SimpleMem TOML 构造强类型 text backend 配置。"""

    profile_path = tmp_path / "configs" / "methods" / "simplemem.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
[smoke]
llm_model = "gpt-4o-mini"
embedding_model_path = "models/Qwen3-Embedding-0.6B"
embedding_dimension = 1024
window_size = 40
overlap_size = 2
semantic_top_k = 25
keyword_top_k = 5
structured_top_k = 5
max_workers = 1
""",
        encoding="utf-8",
    )

    config = load_method_profile(
        method_name="simplemem",
        profile_name="smoke",
        project_root=tmp_path,
    )

    assert isinstance(config, SimpleMemConfig)
    assert config.profile_name == "smoke"
    assert config.llm_model == "gpt-4o-mini"
    assert config.embedding_model_path == "models/Qwen3-Embedding-0.6B"


@pytest.mark.parametrize("method_name", tuple(list_methods()))
@pytest.mark.parametrize("profile_name", ("smoke", "official-full"))
def test_registered_profiles_declare_benchmark_answer_builder(
    method_name: str,
    profile_name: str,
) -> None:
    """十家主 section 都必须由 TOML 显式选择 benchmark builder。"""

    resolved = resolve_method_profile(
        method_name=method_name,
        profile_name=profile_name,
        project_root=Path(__file__).resolve().parents[1],
    )

    assert resolved.public_name == profile_name
    assert resolved.section_name == profile_name.replace("-", "_")
    assert resolved.answer_builder == "benchmark"
    assert resolved.config.profile_name == resolved.section_name


def test_new_run_profile_requires_answer_builder_without_weakening_config_loader(
    tmp_path: Path,
) -> None:
    """新 run 缺 builder 应失败，旧 config-only loader 仍可读取同一 section。"""

    profile_path = tmp_path / "configs" / "methods" / "mem0.toml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(
        """
[smoke]
extraction_model = "gpt-4o-mini"
embedding_model = "text-embedding-3-small"
embedding_dimensions = 1536
reader_model = "gpt-4o-mini"
top_k = 200
max_workers = 1
ingestion_chunk_size = 1
infer = true
""",
        encoding="utf-8",
    )

    assert load_method_profile("mem0", "smoke", tmp_path).profile_name == "smoke"
    with pytest.raises(ConfigurationError, match="answer_builder"):
        resolve_method_profile("mem0", "smoke", tmp_path)


def test_unknown_method_is_rejected() -> None:
    """未知 method 必须由 registry 给出明确错误。"""

    with pytest.raises(ConfigurationError, match="Unknown method"):
        get_method_registration("unknown")

def test_unknown_profile_is_rejected_by_registry() -> None:
    """未知 method profile 必须在读取 TOML 前失败。"""

    with pytest.raises(ConfigurationError, match="Unknown Mem0 profile"):
        load_method_profile(
            method_name="mem0",
            profile_name="cheap-ish",
            project_root=".",
        )


def _memos_registry_config(**overrides) -> MemOSConfig:
    """构造与主 profile 同口径的 MemOSConfig，供 registry 断言使用。"""

    base = {
        "llm_model": "gpt-4o-mini",
        "embedding_backend": "sentence_transformer",
        "embedding_model_path": "models/all-MiniLM-L6-v2",
        "embedding_dimension": 384,
        "embedding_max_tokens": 8192,
        "embedding_trust_remote": False,
        "memory_backend": "tree_text",
        "reader_backend": "multimodal_struct",
        "add_async_mode": "async",
        "add_mode": None,
        "use_redis_queue": False,
        "parallel_dispatch": True,
        "reorganize": False,
        "reranker_backend": "cosine_local",
        "search_mode": "fast",
        "search_relativity": 0.45,
        "search_dedup": "mmr",
        "search_rerank": True,
        "include_preference": False,
        "search_tool_memory": False,
        "include_skill_memory": False,
        "neighbor_discovery": False,
        "internet_search": False,
        "task_timeout_seconds": 600.0,
        "max_workers": 1,
        "graph_db_backend": "neo4j-community",
        "graph_db_uri": "bolt://localhost:7687",
        "graph_db_user": "neo4j",
        "graph_db_name": "neo4j",
        "graph_db_credential_env": "MEMOS_NEO4J_PASSWORD",
        "vector_db_host": "localhost",
        "vector_db_port": 6333,
        "vector_db_credential_env": "MEMOS_QDRANT_API_KEY",
    }
    base.update(overrides)
    return MemOSConfig(**base)


def test_memos_registration_declares_product_typed_handler_contract() -> None:
    """MemOS registration 应锁定 v3 session product typed-handler 契约。"""

    registration = get_method_registration("memos")

    assert registration.config_type is MemOSConfig
    assert registration.profile_names == frozenset(
        {"smoke", "pilot", "official-full"}
    )
    assert registration.protocol_version == "v3"
    assert registration.profile_relative_path == Path("configs/methods/memos.toml")
    assert registration.requires_api is True
    assert registration.provenance_granularity == "none"
    assert registration.retrieval_evidence_contract_version == "v1"
    # isolated provider 仍共享进程级 runtime/embedder，真实 W2 已证不安全。
    assert registration.allow_smoke_worker_override is False
    assert registration.supports_shared_instance_parallelism is False
    assert registration.max_workers_getter(_memos_registry_config()) == 1


def test_memos_model_inventory_separates_llm_embedding_and_local_reranker() -> None:
    """model inventory 必须区分 API build LLM / 本地 embedding / 本地 reranker。"""

    registration = get_method_registration("memos")
    inventory = registration.efficiency_model_inventory_getter(_memos_registry_config())

    assert [model.model_id for model in inventory] == [
        "memos-build-llm",
        "memos-embedding",
        "memos-reranker",
    ]
    by_id = {model.model_id: model for model in inventory}
    assert by_id["memos-build-llm"].execution_mode == "api"
    assert by_id["memos-build-llm"].model_name == "gpt-4o-mini"
    assert by_id["memos-embedding"].execution_mode == "local"
    assert by_id["memos-embedding"].embedding_dimension == 384
    # cosine_local reranker 是本地算法，不得伪装成 LLM。
    assert by_id["memos-reranker"].execution_mode == "local"
    assert by_id["memos-reranker"].model_role == "reranker"


def test_memos_instrumentation_identity_declares_async_usage_bridge() -> None:
    """B7 身份必须声明 API usage 拦截层与跨 async scope 的回放协议。"""

    registration = get_method_registration("memos")
    identity = registration.efficiency_instrumentation_identity_getter(
        load_path_settings(),
        _memos_registry_config(),
        {"source_sha256": "source-lock"},
    )

    assert identity["exact_api_usage"] == "patched_response_callback"
    assert identity["async_scope_bridge"] == "completion_buffered_replay_v1"
    assert (
        identity["embedding_token_source"]
        == "sentence_transformer_tokenizer_estimate"
    )
    assert identity["method_source_sha256"] == "source-lock"


def test_memos_build_identity_declares_source_proven_normalization() -> None:
    """build identity 必须声明 product/controlled embedding 与 source-proven 归一化。"""

    registration = get_method_registration("memos")
    declaration = registration.build_identity_resolver(
        _memos_registry_config().to_manifest()
    )

    assert declaration.implementation_variant == "product"
    assert declaration.embedding_profile == "controlled_embedding_v1"
    assert declaration.historical_controlled_build_equivalent_to_current_main is False
    assert declaration.embedding.dimension == 384
    assert declaration.embedding.revision_status == "local_unpinned"
    assert declaration.embedding.normalization == "model_pipeline_l2"
    assert declaration.embedding.distance == "qdrant-cosine"


def test_memos_profiles_only_differ_in_budget_model_and_are_both_serial() -> None:
    """两 profile 仅允许 LLM runtime 身份不同，非 LLM 参数保持一致。"""

    import dataclasses

    smoke = load_method_profile("memos", "smoke")
    official = load_method_profile("memos", "official-full")

    # profile 与 budget-only LLM 身份不同；其余 build/search 参数必须全等。
    smoke_fields = dataclasses.asdict(smoke)
    official_fields = dataclasses.asdict(official)
    assert smoke_fields.pop("profile_name") == "smoke"
    assert official_fields.pop("profile_name") == "official_full"
    assert smoke_fields.pop("llm_model") == "ox-alpha-free"
    assert official_fields.pop("llm_model") == "gpt-4o-mini"
    assert smoke_fields == official_fields
    assert smoke.max_workers == 1
    assert official.max_workers == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"llm_model": "gpt-4o"},
        {"embedding_model_path": "models/other"},
        {"embedding_dimension": 768},
        {"search_relativity": 0.9},
        {"search_dedup": "sim"},
        {"search_rerank": False},
        {"task_timeout_seconds": 30.0},
    ],
)
def test_memos_manifest_changes_break_resume_identity(overrides) -> None:
    """embedding/model/search/lifecycle 任一参数变化都必须改变 resume 身份。"""

    baseline = _memos_registry_config().to_manifest()
    mutated = _memos_registry_config(**overrides).to_manifest()

    assert baseline != mutated


def test_memos_manifest_carries_adapter_version_and_no_absolute_paths() -> None:
    """manifest 必须带 adapter version，且零 secret / 零绝对路径。"""

    manifest = _memos_registry_config().to_manifest()

    assert manifest["adapter_version"] == "memos-v2.0.25-product-v4"
    assert manifest["implementation_identity"] == "typed-product-handler"
    assert manifest["build_llm_response_contract"] == (
        "provider-aware-v2:"
        "opencodego=model_aware_json_reasoning_control;"
        "primary=provider_default"
    )
    assert manifest["reference_time_effect"] == "declared_but_unwired_v2.0.25"
    for key, value in manifest.items():
        assert "password" not in key or key.endswith("_env")
        assert not (isinstance(value, str) and value.startswith("/"))
