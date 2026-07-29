"""MemOS v2.0.25 product v4 adapter 强反例。

覆盖四层，全部零真实 API / DB / 模型 / 网络：

1. **新增 patch hunk 的 current MemOS 真实行为**：
   `APIConfig.get_embedder_config()` 的 `sentence_transformer` 分支与 unknown
   backend fail-fast；`SingleCubeView._search_text()` 的失败可见性与非法 mode
   fail-fast——直接调用 patched 生产函数，不 stub 掉被测的 catch 边界；
2. **五个 benchmark 的生产输入形状**：复用生产
   `build_turn_events` + `GranularityAggregator("session")`，断言最终
   `APIADDRequest`（真实 product model）的 role/content/chat_time/message_id；
3. **retrieve / metric 资格 / clean retry**：真实 `APISearchRequest`、真实
   readout 映射与真实 evidence 断言；
4. **namespace / runtime owner / source identity**。

只 fake 外部 I/O 叶子（typed handler 的调用出口），不 fake adapter 自身、
event stream 聚合器或 product 请求模型。
"""

from __future__ import annotations

import os
import sys
import threading
import types
from pathlib import Path

import pytest

from memory_benchmark.core import ConfigurationError, ImageRef, Session, Turn
from memory_benchmark.core.entities import Conversation
from memory_benchmark.core.provider_protocol import (
    RetrievalQuery,
    SessionBatch,
    TurnEvent,
)
from memory_benchmark.methods.memos_adapter import (
    MEMOS_EMPTY_MEMORY_SENTINEL,
    MEMOS_REFERENCE_TIME_EFFECT,
    MemOS,
    MemOSConfig,
    _MemosRuntimeOwner,
    build_memos_namespace,
    build_memos_source_identity,
    clean_memos_conversation_state,
)
from memory_benchmark.methods.memos_lifecycle import MemosLocalTaskTracker
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    EmbeddingCallObservation,
    LLMCallObservation,
    MeasurementSource,
)
from memory_benchmark.runners.event_stream import (
    GranularityAggregator,
    build_turn_events,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_memos_lifecycle import MEMOS_ROOT, _bootstrap_memos  # noqa: E402


# --------------------------------------------------------------------------------------
# 公共夹具
# --------------------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="module")
def _bootstrap_memos_for_module(tmp_path_factory):
    """整个模块共享一次 MemOS import 引导。

    provider 级用例会在 `ingest()`/`retrieve()` 里 lazy import
    `memos.api.product_models`；若只有请求 `memos_product_models` 的用例才引导，
    其余用例就隐式依赖同文件内的执行顺序（单独按 node id 跑会 ModuleNotFoundError）。
    这里显式消除该顺序依赖。
    """

    if not MEMOS_ROOT.exists():
        pytest.skip("third_party/methods/MemOS 未就位（local-only）")
    _bootstrap_memos(tmp_path_factory.mktemp("memos_adapter_module"))


@pytest.fixture(scope="module")
def memos_product_models(tmp_path_factory):
    """导入 patched current MemOS 的真实 product 请求模型与被测函数。"""

    if not MEMOS_ROOT.exists():
        pytest.skip("third_party/methods/MemOS 未就位（local-only）")
    _bootstrap_memos(tmp_path_factory.mktemp("memos_adapter_home"))
    # 先经 api 包导入，避免 multi_mem_cube 的部分初始化循环导入。
    from memos.api.handlers.add_handler import AddHandler  # noqa: F401
    from memos.api.config import APIConfig
    from memos.api.product_models import APIADDRequest, APISearchRequest
    from memos.multi_mem_cube.single_cube import SingleCubeView

    return types.SimpleNamespace(
        api_config=APIConfig,
        add_request=APIADDRequest,
        search_request=APISearchRequest,
        single_cube_view=SingleCubeView,
    )


def _make_config(**overrides) -> MemOSConfig:
    """构造与 configs/methods/memos.toml 主 profile 同口径的强类型配置。"""

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


class _FakeAddHandler:
    """捕获 adapter 真正发出的 `APIADDRequest`，并驱动 tracker 到终态。"""

    def __init__(self, tracker: MemosLocalTaskTracker, mem_read_label: str):
        """记录 tracker 与 MEM_READ label。"""
        self.tracker = tracker
        self.mem_read_label = mem_read_label
        self.requests: list = []
        self.terminal = "completed"
        self.emit_task_count = 1

    def handle_add_memories(self, add_req):
        """记录请求，并按配置产生 MEM_READ 终态。"""
        self.requests.append(add_req)
        for index in range(self.emit_task_count):
            item_id = f"{add_req.task_id}-item{index}"
            self.tracker.task_submitted(
                task_id=item_id,
                user_id=add_req.user_id,
                task_type=self.mem_read_label,
                business_task_id=add_req.task_id,
                mem_cube_id=add_req.user_id,
            )
            self.tracker.task_started(task_id=item_id, user_id=add_req.user_id)
            if self.terminal == "completed":
                self.tracker.task_completed(item_id, add_req.user_id)
            elif self.terminal == "failed":
                self.tracker.task_failed(item_id, add_req.user_id, "reader exploded")
        return types.SimpleNamespace(message="ok")


class _FakeSearchHandler:
    """捕获 adapter 发出的 `APISearchRequest` 并返回产品形状 response。"""

    def __init__(self, response_data):
        """保存待返回的 product response data。"""
        self.response_data = response_data
        self.requests: list = []

    def handle_search_memories(self, search_req):
        """记录请求并返回预置 response。"""
        self.requests.append(search_req)
        return types.SimpleNamespace(data=self.response_data)


class _FakeRuntime:
    """替身 runtime：只替换 typed handler 出口，tracker 与语义仍是真实实现。"""

    def __init__(self, *, config, openai_settings, path_settings, mem_read_label="mem_read"):
        """构造带真实 tracker 的替身 runtime。"""
        self.config = config
        self.identity = config.runtime_identity()
        self.tracker = MemosLocalTaskTracker()
        self.add_handler = _FakeAddHandler(self.tracker, mem_read_label)
        self.search_handler = _FakeSearchHandler({"text_mem": []})
        self.naive_mem_cube = object()
        self.scheduler = types.SimpleNamespace(stop_calls=0)
        self.stop_calls = 0
        self._closed = False
        # 与真实 MemosRuntime 同构的永久 fail-closed 状态。
        self.fail_stop = False
        self._close_failed = False
        self._close_error = None

    @property
    def closed(self) -> bool:
        """返回是否已关闭。"""
        return self._closed

    @property
    def close_failed(self) -> bool:
        """返回是否已因 stop 失败而永久不可复用。"""
        return self._close_failed

    @property
    def close_error(self):
        """返回首次 stop 失败的原始异常。"""
        return self._close_error

    def close(self) -> None:
        """镜像真实 close：pending refusal 可重试；stop 失败永久 fail-closed。"""
        if self._close_failed:
            raise ConfigurationError(
                "MemOS runtime is permanently unusable: a previous "
                "scheduler.stop() failed"
            ) from self._close_error
        if self._closed:
            return
        self.tracker.assert_no_pending_tasks()
        self.stop_calls += 1
        if self.fail_stop:
            error = RuntimeError("scheduler stop exploded")
            self._close_failed = True
            self._close_error = error
            raise error
        self._closed = True


def _make_provider(
    tmp_path,
    *,
    benchmark_name=None,
    config=None,
    runtime_factory=None,
    efficiency_collector=None,
):
    """构造挂在独立 runtime owner 上的 MemOS provider。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings

    path_settings = load_path_settings()
    storage_root = (
        path_settings.project_root
        / "outputs"
        / "unit-test-run"
        / tmp_path.name
        / "method_state"
    )
    provider = MemOS(
        config=config or _make_config(),
        path_settings=path_settings,
        storage_root=storage_root,
        openai_settings=OpenAISettings(api_key="unit-test-key", base_url=None),
        efficiency_collector=efficiency_collector,
        benchmark_name=benchmark_name,
        runtime_owner=_MemosRuntimeOwner(),
        runtime_factory=runtime_factory or _FakeRuntime,
    )
    return provider


def _session_batches(conversation: Conversation, isolation_key: str):
    """用生产事件流 + session 聚合器产出 SessionBatch，不手造漂亮输入。"""

    aggregator = GranularityAggregator("session")
    events = build_turn_events(conversation, isolation_key)
    return [
        signal
        for signal in aggregator.aggregate(events, isolation_key)
        if isinstance(signal, SessionBatch)
    ]


def _ingest_all(provider: MemOS, conversation: Conversation, isolation_key: str):
    """按生产聚合顺序 ingest 全部 session，返回捕获的 APIADDRequest 列表。"""

    for batch in _session_batches(conversation, isolation_key):
        provider.ingest(batch)
    return provider._require_runtime().add_handler.requests


# --------------------------------------------------------------------------------------
# 1. 新增 patch hunk：embedder config
# --------------------------------------------------------------------------------------


def test_sentence_transformer_branch_returns_exact_controlled_fields(
    memos_product_models, monkeypatch
):
    """`sentence_transformer` 分支必须精确暴露 factory 原生支持的四个字段。"""

    monkeypatch.setenv("MOS_EMBEDDER_BACKEND", "sentence_transformer")
    monkeypatch.setenv("MOS_EMBEDDER_MODEL", "models/all-MiniLM-L6-v2")
    monkeypatch.setenv("MOS_EMBEDDER_DIMS", "384")
    monkeypatch.setenv("MOS_EMBEDDER_MAX_TOKENS", "8192")
    monkeypatch.setenv("MOS_EMBEDDER_TRUST_REMOTE_CODE", "false")

    config = memos_product_models.api_config.get_embedder_config()

    assert config == {
        "backend": "sentence_transformer",
        "config": {
            "model_name_or_path": "models/all-MiniLM-L6-v2",
            "embedding_dims": 384,
            "max_tokens": 8192,
            "trust_remote_code": False,
        },
    }


def test_sentence_transformer_config_is_accepted_by_real_factory_schema(
    memos_product_models, monkeypatch
):
    """新分支产出的 config 必须能通过 current EmbedderConfigFactory 校验。"""

    monkeypatch.setenv("MOS_EMBEDDER_BACKEND", "sentence_transformer")
    monkeypatch.setenv("MOS_EMBEDDER_MODEL", "models/all-MiniLM-L6-v2")
    monkeypatch.setenv("MOS_EMBEDDER_DIMS", "384")
    monkeypatch.setenv("MOS_EMBEDDER_MAX_TOKENS", "8192")

    from memos.configs.embedder import EmbedderConfigFactory

    validated = EmbedderConfigFactory.model_validate(
        memos_product_models.api_config.get_embedder_config()
    )

    assert validated.backend == "sentence_transformer"
    assert validated.config.model_name_or_path == "models/all-MiniLM-L6-v2"
    assert validated.config.embedding_dims == 384


def test_unknown_embedder_backend_fails_fast(memos_product_models, monkeypatch):
    """未知 backend 不得继续静默落入 Ollama。"""

    monkeypatch.setenv("MOS_EMBEDDER_BACKEND", "totally-unknown-backend")

    with pytest.raises(ValueError, match="Unsupported MOS_EMBEDDER_BACKEND"):
        memos_product_models.api_config.get_embedder_config()


def test_existing_ollama_and_universal_branches_are_preserved(
    memos_product_models, monkeypatch
):
    """既有 ollama（含 env 未设的默认）与 universal_api 分支必须对象守恒。"""

    monkeypatch.delenv("MOS_EMBEDDER_BACKEND", raising=False)
    monkeypatch.delenv("MOS_EMBEDDER_MODEL", raising=False)
    monkeypatch.delenv("OLLAMA_API_BASE", raising=False)
    default_config = memos_product_models.api_config.get_embedder_config()
    assert default_config == {
        "backend": "ollama",
        "config": {
            "model_name_or_path": "nomic-embed-text:latest",
            "api_base": "http://localhost:11434",
        },
    }

    monkeypatch.setenv("MOS_EMBEDDER_BACKEND", "ollama")
    assert memos_product_models.api_config.get_embedder_config() == default_config

    monkeypatch.setenv("MOS_EMBEDDER_BACKEND", "universal_api")
    universal = memos_product_models.api_config.get_embedder_config()
    assert universal["backend"] == "universal_api"
    assert universal["config"]["provider"] == "openai"
    assert universal["config"]["model_name_or_path"] == "text-embedding-3-large"


def test_memreader_default_has_no_provider_specific_extra_body(
    memos_product_models, monkeypatch
):
    """primary runtime 不得被 opencodego 的结构化输出参数污染。"""

    monkeypatch.delenv("MEMRADER_PROVIDER_COMPATIBILITY", raising=False)

    config = memos_product_models.api_config.get_memreader_config()["config"]

    assert "extra_body" not in config


def test_memreader_opencodego_compatibility_is_exact(
    memos_product_models, monkeypatch
):
    """opencodego smoke 必须同时关闭 thinking 并要求 JSON object。"""

    monkeypatch.setenv(
        "MEMRADER_PROVIDER_COMPATIBILITY",
        "opencodego_json_non_thinking_v1",
    )

    config = memos_product_models.api_config.get_memreader_config()["config"]

    assert config["extra_body"] == {
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
    }


def test_memreader_unknown_provider_compatibility_fails_fast(
    memos_product_models, monkeypatch
):
    """未知 provider compatibility 不得静默退化成默认请求。"""

    monkeypatch.setenv(
        "MEMRADER_PROVIDER_COMPATIBILITY",
        "unknown-contract",
    )

    with pytest.raises(
        ValueError,
        match="Unsupported MEMRADER_PROVIDER_COMPATIBILITY",
    ):
        memos_product_models.api_config.get_memreader_config()


# --------------------------------------------------------------------------------------
# 1.5. B7：OpenAI usage 暴露与 async scope 回放
# --------------------------------------------------------------------------------------


def _fake_chat_completion(content: str, *, input_tokens: int, output_tokens: int):
    """构造 OpenAILLM._parse_response 可消费的最小 Chat Completion。"""

    return types.SimpleNamespace(
        choices=[
            types.SimpleNamespace(
                message=types.SimpleNamespace(
                    content=content,
                    tool_calls=None,
                )
            )
        ],
        usage=types.SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        ),
        model_dump_json=lambda: "{}",
    )


def _fake_openai_llm(openai_llm_type, *, primary, backup=None):
    """绕过 SDK 构造，给真实 patched OpenAILLM.generate 注入 hermetic client。"""

    llm = object.__new__(openai_llm_type)
    llm.config = types.SimpleNamespace(
        model_name_or_path="build-model",
        temperature=0.0,
        max_tokens=32,
        top_p=1.0,
        extra_body={},
        remove_think_prefix=False,
        backup_model_name_or_path="backup-model",
    )
    llm.client = types.SimpleNamespace(
        chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(create=primary)
        )
    )
    llm.use_backup_client = backup is not None
    llm.backup_client = (
        types.SimpleNamespace(
            chat=types.SimpleNamespace(
                completions=types.SimpleNamespace(create=backup)
            )
        )
        if backup is not None
        else None
    )
    llm.response_callback = None
    return llm


def test_patched_openai_llm_exposes_success_response_usage_to_callback(
    memos_product_models,
):
    """primary 成功时 callback 必须看到原 response/body/result，返回文本不变。"""

    from memos.llms.openai import OpenAILLM

    response = _fake_chat_completion("structured", input_tokens=11, output_tokens=3)
    llm = _fake_openai_llm(OpenAILLM, primary=lambda **kwargs: response)
    observed: list[tuple[Any, dict[str, Any], str]] = []
    llm.response_callback = (
        lambda owner, raw, body, result: observed.append((raw, body, result))
    )

    result = llm.generate([{"role": "user", "content": "remember this"}])

    assert result == "structured"
    assert len(observed) == 1
    assert observed[0][0] is response
    assert observed[0][1]["model"] == "build-model"
    assert observed[0][1]["messages"] == [
        {"role": "user", "content": "remember this"}
    ]
    assert observed[0][1]["temperature"] == 0.0
    assert observed[0][1]["max_tokens"] == 32
    assert observed[0][1]["top_p"] == 1.0
    assert observed[0][1]["extra_body"] == {}
    assert observed[0][2] == "structured"


def test_patched_openai_llm_without_callback_preserves_success_result(
    memos_product_models,
):
    """未安装观测 callback 时，patched product success path 的返回值必须不变。"""

    from memos.llms.openai import OpenAILLM

    response = _fake_chat_completion("unchanged", input_tokens=7, output_tokens=2)
    llm = _fake_openai_llm(OpenAILLM, primary=lambda **kwargs: response)

    assert llm.response_callback is None
    assert llm.generate([{"role": "user", "content": "remember"}]) == "unchanged"


def test_patched_openai_llm_reports_only_successful_backup_response(
    memos_product_models,
):
    """primary 失败、backup 成功时只记录实际成功的 backup body/usage。"""

    from memos.llms.openai import OpenAILLM

    def _primary(**kwargs):
        """模拟 primary transport failure。"""

        raise RuntimeError("primary unavailable")

    backup_response = _fake_chat_completion(
        "backup result",
        input_tokens=13,
        output_tokens=4,
    )
    llm = _fake_openai_llm(
        OpenAILLM,
        primary=_primary,
        backup=lambda **kwargs: backup_response,
    )
    observed: list[tuple[Any, dict[str, Any], str]] = []
    llm.response_callback = (
        lambda owner, raw, body, result: observed.append((raw, body, result))
    )

    assert llm.generate([{"role": "user", "content": "x"}]) == "backup result"
    assert len(observed) == 1
    assert observed[0][0] is backup_response
    assert observed[0][1]["model"] == "backup-model"
    assert observed[0][2] == "backup result"


class _ObservedEmbeddingModel:
    """带真实 tokenizer 形状的最小 SentenceTransformer 替身。"""

    def __init__(self) -> None:
        """创建 tokenizer/max_seq_length 与调用记录。"""

        self.calls: list[list[str]] = []
        self.model = types.SimpleNamespace(
            tokenizer=types.SimpleNamespace(
                encode=lambda text, **kwargs: str(text).split()[
                    : kwargs.get("max_length")
                ]
            ),
            max_seq_length=3,
        )

    def _truncate_texts(self, texts):
        """镜像 upstream 字符预截断入口。"""

        return list(texts)

    def embed(self, texts):
        """记录输入并返回固定向量。"""

        normalized = [str(text) for text in texts]
        self.calls.append(normalized)
        return [[0.0, 1.0] for _ in normalized]


def test_async_model_calls_are_replayed_into_original_framework_scopes(tmp_path):
    """后台线程无 ContextVar 时，LLM/embedding 仍归属原 build/retrieval scope。"""

    collector = EfficiencyCollector(run_id="memos-efficiency", enabled=True)
    provider = _make_provider(
        tmp_path,
        benchmark_name="longmemeval",
        efficiency_collector=collector,
    )
    llm = types.SimpleNamespace(response_callback=None)
    embedder = _ObservedEmbeddingModel()
    runtime = types.SimpleNamespace(
        components={
            "llm": llm,
            "mem_reader": types.SimpleNamespace(
                llm=llm,
                general_llm=llm,
                embedder=embedder,
            ),
            "embedder": embedder,
        }
    )
    provider._install_efficiency_observers(runtime)

    with collector.conversation_scope("conv-1") as build_scope:
        assert provider._begin_efficiency_capture(EfficiencyStage.MEMORY_BUILD)

        def _background_build() -> None:
            """模拟 scheduler worker 内完成 LLM 与 embedding。"""

            response = _fake_chat_completion(
                '{"memory list":[]}',
                input_tokens=17,
                output_tokens=5,
            )
            llm.response_callback(
                llm,
                response,
                {"messages": [{"role": "user", "content": "alpha beta"}]},
                '{"memory list":[]}',
            )
            embedder.embed(["one two three four"])

        worker = threading.Thread(target=_background_build)
        worker.start()
        worker.join()
        provider._finish_efficiency_capture(EfficiencyStage.MEMORY_BUILD)
        collector.record_memory_build_total_latency(latency_ms=1.0)

    build_llm = [
        record
        for record in build_scope.records
        if isinstance(record, LLMCallObservation)
    ]
    build_embeddings = [
        record
        for record in build_scope.records
        if isinstance(record, EmbeddingCallObservation)
    ]
    assert len(build_llm) == 1
    assert build_llm[0].stage is EfficiencyStage.MEMORY_BUILD
    assert build_llm[0].conversation_id == "conv-1"
    assert build_llm[0].question_id is None
    assert build_llm[0].input_tokens == 17
    assert build_llm[0].output_tokens == 5
    assert build_llm[0].token_measurement_source is MeasurementSource.API_USAGE
    assert len(build_embeddings) == 1
    assert build_embeddings[0].stage is EfficiencyStage.MEMORY_BUILD
    assert build_embeddings[0].input_tokens == 3

    with collector.question_scope("conv-1", "q1") as question_scope:
        assert provider._begin_efficiency_capture(EfficiencyStage.RETRIEVAL)
        worker = threading.Thread(target=lambda: embedder.embed(["query tokens"]))
        worker.start()
        worker.join()
        provider._finish_efficiency_capture(EfficiencyStage.RETRIEVAL)
        collector.record_retrieval_result(
            latency_ms=2.0,
            injected_memory_context_tokens=0,
        )
        collector.record_answer_generation(latency_ms=3.0)

    retrieval_embeddings = [
        record
        for record in question_scope.records
        if isinstance(record, EmbeddingCallObservation)
    ]
    assert len(retrieval_embeddings) == 1
    assert retrieval_embeddings[0].stage is EfficiencyStage.RETRIEVAL
    assert retrieval_embeddings[0].conversation_id == "conv-1"
    assert retrieval_embeddings[0].question_id == "q1"


# --------------------------------------------------------------------------------------
# 2. 新增 patch hunk：search 失败可见性
# --------------------------------------------------------------------------------------


def _search_text_probe(memos_product_models, *, mode, fast_search):
    """用最小替身对象直接驱动 patched `_search_text`，不绕开被测 catch。"""

    view = object.__new__(memos_product_models.single_cube_view)
    view.logger = types.SimpleNamespace(error=lambda *a, **kw: None)
    view._fast_search = fast_search
    return memos_product_models.single_cube_view._search_text(
        view,
        search_req=types.SimpleNamespace(),
        user_context=types.SimpleNamespace(),
        search_mode=mode,
    )


def test_search_backend_failure_propagates_instead_of_zero_hit(memos_product_models):
    """真实 graph/vector 失败必须上抛，不得被伪装成合法 zero-hit。"""

    def _boom(search_req, user_context):
        """模拟 backend 抛错。"""
        raise RuntimeError("qdrant unavailable")

    with pytest.raises(RuntimeError, match="qdrant unavailable"):
        _search_text_probe(memos_product_models, mode="fast", fast_search=_boom)


def test_legal_empty_search_result_is_still_zero_hit(memos_product_models):
    """合法的 backend 空结果仍是 zero-hit，不受失败可见性 patch 影响。"""

    result = _search_text_probe(
        memos_product_models,
        mode="fast",
        fast_search=lambda search_req, user_context: [],
    )

    assert result == []


def test_unsupported_search_mode_fails_fast(memos_product_models):
    """非法 search mode 不得返回 []。"""

    with pytest.raises(ValueError, match="Unsupported search mode"):
        _search_text_probe(
            memos_product_models,
            mode="not-a-mode",
            fast_search=lambda search_req, user_context: [],
        )


# --------------------------------------------------------------------------------------
# 3. lazy import 与 runtime 单例
# --------------------------------------------------------------------------------------


def test_importing_adapter_does_not_import_server_router():
    """adapter import 不得触发 `memos.api.routers.server_router`。"""

    import sys

    assert "memos.api.routers.server_router" not in sys.modules


def test_runtime_owner_reuses_same_config_and_rejects_conflict(tmp_path):
    """同 config 复用同一 runtime；冲突 config fail-fast。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings

    owner = _MemosRuntimeOwner()
    settings = load_path_settings()
    openai = OpenAISettings(api_key="k", base_url=None)
    config = _make_config()

    first = owner.acquire(
        config=config,
        openai_settings=openai,
        path_settings=settings,
        runtime_factory=_FakeRuntime,
    )
    second = owner.acquire(
        config=_make_config(),
        openai_settings=openai,
        path_settings=settings,
        runtime_factory=_FakeRuntime,
    )
    assert first is second

    with pytest.raises(ConfigurationError, match="different config identity"):
        owner.acquire(
            config=_make_config(search_relativity=0.9),
            openai_settings=openai,
            path_settings=settings,
            runtime_factory=_FakeRuntime,
        )


def test_runtime_owner_refuses_to_reuse_closed_runtime():
    """已关闭 runtime 不得跨 run 复用。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings

    owner = _MemosRuntimeOwner()
    settings = load_path_settings()
    openai = OpenAISettings(api_key="k", base_url=None)
    config = _make_config()

    runtime = owner.acquire(
        config=config,
        openai_settings=openai,
        path_settings=settings,
        runtime_factory=_FakeRuntime,
    )
    runtime.close()
    owner._runtime = runtime  # 模拟 close 后仍被持有的边界

    with pytest.raises(ConfigurationError, match="already been closed"):
        owner.acquire(
            config=config,
            openai_settings=openai,
            path_settings=settings,
            runtime_factory=_FakeRuntime,
        )


def test_runtime_owner_is_thread_safe():
    """并发 acquire 只能产生一个 runtime。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings

    owner = _MemosRuntimeOwner()
    settings = load_path_settings()
    openai = OpenAISettings(api_key="k", base_url=None)
    config = _make_config()
    seen: list = []
    barrier = threading.Barrier(8)

    def _acquire():
        """并发获取 runtime。"""
        barrier.wait()
        seen.append(
            owner.acquire(
                config=config,
                openai_settings=openai,
                path_settings=settings,
                runtime_factory=_FakeRuntime,
            )
        )

    threads = [threading.Thread(target=_acquire) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len({id(runtime) for runtime in seen}) == 1


def test_provider_builds_one_runtime_shared_by_add_and_search(tmp_path):
    """一个 provider 只构造一个 runtime，Add/Search 共用同一 tracker。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    conversation = _longmemeval_conversation()
    _ingest_all(provider, conversation, "run1_conv1")
    runtime_after_add = provider._require_runtime()

    provider._require_runtime().search_handler.response_data = {"text_mem": []}
    provider.retrieve(
        RetrievalQuery(
            query_text="q",
            isolation_key="run1_conv1",
            question_time=None,
            top_k=5,
            purpose="qa",
        )
    )

    assert provider._require_runtime() is runtime_after_add
    assert runtime_after_add.add_handler.tracker is runtime_after_add.tracker


# --------------------------------------------------------------------------------------
# 4. lifecycle：完成门与 cleanup
# --------------------------------------------------------------------------------------


def test_one_session_batch_emits_one_add_request_and_one_terminal(tmp_path):
    """一个 SessionBatch 只发一个 APIADDRequest / 一个 business task / 一条终态。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    conversation = _longmemeval_conversation()
    batches = _session_batches(conversation, "run1_conv1")
    result = provider.ingest(batches[0])

    runtime = provider._require_runtime()
    assert len(runtime.add_handler.requests) == 1
    assert result.metadata["terminal_task_count"] == 1
    assert result.metadata["add_request_count"] == 1
    assert result.metadata["source_message_count"] == 5
    assert result.metadata["written_message_count"] == 5
    assert runtime.add_handler.requests[0].task_id == result.metadata["business_task_ids"][0]


def test_failed_background_task_propagates(tmp_path):
    """后台 MEM_READ 失败必须原样 fail-fast。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    batches = _session_batches(_longmemeval_conversation(), "run1_conv1")
    provider._require_runtime().add_handler.terminal = "failed"

    with pytest.raises(ConfigurationError, match="失败"):
        provider.ingest(batches[0])


def test_missing_background_task_times_out(tmp_path):
    """add 未提交后台任务时必须超时 fail-fast，不得静默成功。"""

    provider = _make_provider(
        tmp_path,
        benchmark_name="longmemeval",
        config=_make_config(task_timeout_seconds=0.05),
    )
    batches = _session_batches(_longmemeval_conversation(), "run1_conv1")
    provider._require_runtime().add_handler.emit_task_count = 0

    with pytest.raises(ConfigurationError, match="从未登记任何 task"):
        provider.ingest(batches[0])


def test_multiple_terminals_for_one_business_task_fails_fast(tmp_path):
    """一个 business task 出现多条 MEM_READ 终态必须 fail-fast。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    batches = _session_batches(_longmemeval_conversation(), "run1_conv1")
    provider._require_runtime().add_handler.emit_task_count = 2

    with pytest.raises(ConfigurationError, match="数量超出预期"):
        provider.ingest(batches[0])


def test_cleanup_stops_scheduler_exactly_once_and_is_idempotent(tmp_path):
    """cleanup 恰好 stop 一次；重复 cleanup 不二次 stop。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    _ingest_all(provider, _longmemeval_conversation(), "run1_conv1")
    runtime = provider._require_runtime()

    provider.cleanup()
    provider.cleanup()
    provider.cleanup()

    assert runtime.stop_calls == 1


def test_cleanup_refuses_to_close_with_pending_tasks(tmp_path):
    """仍有未完成 task 时 cleanup 必须拒绝静默关闭。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    runtime = provider._require_runtime()
    runtime.tracker.task_submitted(
        task_id="dangling",
        user_id=provider._namespace("run1_conv1"),
        task_type="mem_read",
        business_task_id="biz",
        mem_cube_id=provider._namespace("run1_conv1"),
    )

    with pytest.raises(ConfigurationError, match="拒绝静默关闭"):
        provider.cleanup()


# --------------------------------------------------------------------------------------
# 5. 五个 benchmark 的生产输入形状
# --------------------------------------------------------------------------------------


def _locomo_conversation() -> Conversation:
    """LoCoMo：speaker_b 首发，覆盖正文+caption / caption-only / 多 caption。"""

    return Conversation(
        conversation_id="locomo1",
        metadata={"speaker_a": "Caroline", "speaker_b": "Melanie"},
        sessions=[
            Session(
                session_id="s1",
                session_time="2023-05-01 10:00:00",
                turns=[
                    Turn(turn_id="t1", speaker="Melanie", content="Hi there"),
                    Turn(
                        turn_id="t2",
                        speaker="Caroline",
                        content="Look at this",
                        images=[ImageRef(image_id="i1", path="/x/a.jpg?q=1", caption="a red bike")],
                    ),
                    Turn(
                        turn_id="t3",
                        speaker="Melanie",
                        content="",
                        images=[ImageRef(image_id="i2", path="/x/b.jpg", caption="a blue car")],
                    ),
                    Turn(
                        turn_id="t4",
                        speaker="Caroline",
                        content="Two of them",
                        images=[
                            ImageRef(image_id="i3", path="/x/c.jpg", caption="first"),
                            ImageRef(image_id="i4", path="/x/d.jpg", caption="second"),
                        ],
                    ),
                ],
            )
        ],
    )


def _longmemeval_conversation() -> Conversation:
    """LongMemEval：assistant 开头、连续同 role、奇数尾、singleton session。"""

    return Conversation(
        conversation_id="lme1",
        sessions=[
            Session(
                session_id="s1",
                session_time="2023-01-01T00:00:00",
                turns=[
                    Turn(turn_id="t1", speaker="assistant", normalized_role="assistant", content="A1"),
                    Turn(turn_id="t2", speaker="user", normalized_role="user", content="U1"),
                    Turn(turn_id="t3", speaker="user", normalized_role="user", content="U2"),
                    Turn(
                        turn_id="t4",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="A2",
                        turn_time="2023-01-01T00:05:00",
                    ),
                    Turn(turn_id="t5", speaker="user", normalized_role="user", content="U3"),
                ],
            ),
            Session(
                session_id="s2",
                turns=[
                    Turn(turn_id="t6", speaker="user", normalized_role="user", content="solo"),
                ],
            ),
        ],
    )


def _membench_conversation() -> Conversation:
    """MemBench：尾部 place/time 原文 + 100k noise 无时间。"""

    return Conversation(
        conversation_id="mb1",
        sessions=[
            Session(
                session_id="s1",
                turns=[
                    Turn(
                        turn_id="t1",
                        speaker="user",
                        normalized_role="user",
                        content="I went hiking. (Place: Alps, Time: 2023-06-01)",
                        turn_time="2023-06-01",
                    ),
                    Turn(
                        turn_id="t2",
                        speaker="assistant",
                        normalized_role="assistant",
                        content="Nice!",
                        turn_time="2023-06-01",
                    ),
                    Turn(turn_id="t3", speaker="user", normalized_role="user", content="noise turn"),
                ],
            )
        ],
    )


def _beam_conversation() -> Conversation:
    """BEAM：正常 pair + 已知 dangling 尾部。"""

    return Conversation(
        conversation_id="beam1",
        sessions=[
            Session(
                session_id="s1",
                session_time="2024-02-02",
                turns=[
                    Turn(turn_id="raw_9", speaker="user", normalized_role="user", content="B-U1"),
                    Turn(turn_id="raw_3", speaker="assistant", normalized_role="assistant", content="B-A1"),
                    Turn(turn_id="raw_7", speaker="assistant", normalized_role="assistant", content="B-dangling"),
                ],
            )
        ],
    )


def _halumem_conversation() -> Conversation:
    """HaluMem：整 session 一批。"""

    return Conversation(
        conversation_id="hm1",
        sessions=[
            Session(
                session_id="s1",
                session_time="2024-03-03",
                turns=[
                    Turn(turn_id="t1", speaker="user", normalized_role="user", content="H-U1"),
                    Turn(turn_id="t2", speaker="assistant", normalized_role="assistant", content="H-A1"),
                ],
            ),
            Session(
                session_id="s2",
                session_time="2024-03-04",
                turns=[
                    Turn(turn_id="t3", speaker="user", normalized_role="user", content="H-U2"),
                ],
            ),
        ],
    )


def test_locomo_payload_uses_declared_roles_real_names_and_shared_caption(tmp_path):
    """LoCoMo：官方双视角、反向 role、batch=2、真实 speaker/caption。"""

    provider = _make_provider(tmp_path, benchmark_name="locomo")
    requests = _ingest_all(provider, _locomo_conversation(), "run1_locomo1")

    namespace_a = provider._namespace("run1_locomo1", locomo_view="speaker_a")
    namespace_b = provider._namespace("run1_locomo1", locomo_view="speaker_b")
    assert namespace_a != namespace_b
    assert [len(request.messages) for request in requests] == [2, 2, 2, 2]
    assert [request.user_id for request in requests] == [
        namespace_a,
        namespace_a,
        namespace_b,
        namespace_b,
    ]
    messages_a = [
        message
        for request in requests[:2]
        for message in request.messages
    ]
    messages_b = [
        message
        for request in requests[2:]
        for message in request.messages
    ]
    assert [m["role"] for m in messages_a] == [
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert [m["role"] for m in messages_b] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]
    assert [m["message_id"] for m in messages_a] == ["t1", "t2", "t3", "t4"]
    assert [m["message_id"] for m in messages_b] == ["t1", "t2", "t3", "t4"]
    assert messages_a[0]["content"] == "Melanie: Hi there"
    assert messages_a[1]["content"] == (
        "Caroline: Look at this [Sharing image that shows: a red bike]"
    )
    # caption-only turn 仍非空，且不带 path/query。
    assert messages_a[2]["content"] == "Melanie: [Sharing image that shows: a blue car]"
    assert "a.jpg" not in messages_a[1]["content"]
    assert "?q=1" not in messages_a[1]["content"]
    # 多 caption 按顺序全部保留，且没有事件流的 `(image description: ...)` 双拼。
    assert messages_a[3]["content"] == (
        "Caroline: Two of them [Sharing image that shows: first] "
        "[Sharing image that shows: second]"
    )
    assert "(image description:" not in " ".join(m["content"] for m in messages_a)
    assert all(m["chat_time"] == "2023-05-01 10:00:00" for m in messages_a + messages_b)


def test_locomo_role_mapping_is_independent_of_who_speaks_first(tmp_path):
    """speaker_a 首发与 speaker_b 首发必须得到同一份 speaker→role 映射。"""

    conversation = _locomo_conversation()
    conversation.sessions[0].turns = list(reversed(conversation.sessions[0].turns))
    provider = _make_provider(tmp_path, benchmark_name="locomo")
    requests = _ingest_all(provider, conversation, "run1_locomo1")

    roles_a = {
        message["message_id"]: message["role"]
        for request in requests[:2]
        for message in request.messages
    }
    roles_b = {
        message["message_id"]: message["role"]
        for request in requests[2:]
        for message in request.messages
    }
    assert roles_a["t1"] == "assistant"  # Melanie == speaker_b
    assert roles_a["t2"] == "user"  # Caroline == speaker_a
    assert roles_b["t1"] == "user"
    assert roles_b["t2"] == "assistant"


def test_locomo_odd_tail_is_singleton_in_both_views_without_placeholder(tmp_path):
    """官方 batch=2 的奇数尾在双视角都保持真实 singleton，不造空回复。"""

    conversation = _locomo_conversation()
    conversation.sessions[0].turns.append(
        Turn(turn_id="t5", speaker="Caroline", content="odd tail")
    )
    provider = _make_provider(tmp_path, benchmark_name="locomo")
    requests = _ingest_all(provider, conversation, "run1_locomo1")

    assert [len(request.messages) for request in requests] == [2, 2, 1, 2, 2, 1]
    assert requests[2].messages == [
        {
            "role": "user",
            "content": "Caroline: odd tail",
            "chat_time": "2023-05-01 10:00:00",
            "message_id": "t5",
        }
    ]
    assert requests[5].messages[0]["role"] == "assistant"
    assert requests[5].messages[0]["content"] == "Caroline: odd tail"


def test_locomo_submits_all_async_batches_before_waiting(tmp_path, monkeypatch):
    """双视角全部 add 先提交，再等待；不得暗改成 pair 间同步 fine。"""

    provider = _make_provider(tmp_path, benchmark_name="locomo")
    runtime = provider._require_runtime()
    original_wait = runtime.tracker.wait_for_business_task
    request_counts_at_wait: list[int] = []

    def _wait(**kwargs):
        """记录首次 wait 时已提交的 add 数量。"""
        request_counts_at_wait.append(len(runtime.add_handler.requests))
        return original_wait(**kwargs)

    monkeypatch.setattr(runtime.tracker, "wait_for_business_task", _wait)
    _ingest_all(provider, _locomo_conversation(), "run1_locomo1")

    assert request_counts_at_wait == [4, 4, 4, 4]


def test_locomo_undeclared_third_speaker_fails_fast(tmp_path):
    """未声明的第三 speaker 一律 fail-fast。"""

    conversation = _locomo_conversation()
    conversation.sessions[0].turns.append(
        Turn(turn_id="t5", speaker="Stranger", content="who am I")
    )
    provider = _make_provider(tmp_path, benchmark_name="locomo")

    with pytest.raises(ConfigurationError, match="not declared in speaker_a/speaker_b"):
        _ingest_all(provider, conversation, "run1_locomo1")


@pytest.mark.parametrize(
    "metadata",
    [
        {"speaker_a": "", "speaker_b": "B"},
        {"speaker_a": "A"},
        {"speaker_a": "Same", "speaker_b": "Same"},
    ],
)
def test_locomo_missing_or_identical_speaker_declaration_fails_fast(tmp_path, metadata):
    """缺声明或两者相同必须 fail-fast。"""

    conversation = _locomo_conversation()
    conversation.metadata = metadata
    provider = _make_provider(tmp_path, benchmark_name="locomo")

    with pytest.raises(ConfigurationError):
        _ingest_all(provider, conversation, "run1_locomo1")


def test_longmemeval_preserves_original_order_without_repairing_pairs(tmp_path):
    """assistant 开头 / 连续同 role / 奇数尾 / singleton 全部原样保留。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    requests = _ingest_all(provider, _longmemeval_conversation(), "run1_lme1")

    assert len(requests) == 2  # 同 session 一个 batch，跨 session 不合并
    first = requests[0].messages
    assert [m["role"] for m in first] == [
        "assistant",
        "user",
        "user",
        "assistant",
        "user",
    ]
    assert [m["message_id"] for m in first] == ["t1", "t2", "t3", "t4", "t5"]
    # 逐 turn time 优先，其余回落 session time。
    assert first[3]["chat_time"] == "2023-01-01T00:05:00"
    assert first[0]["chat_time"] == "2023-01-01T00:00:00"
    # 无 turn time 也无 session time 时写显式 None，key 仍在。
    second = requests[1].messages
    assert len(second) == 1
    assert "chat_time" in second[0]
    assert second[0]["chat_time"] is None


def test_membench_keeps_place_time_suffix_and_extracts_chat_time(tmp_path):
    """MemBench 尾注原文保留，同时 canonical 时间进入 chat_time；无时间写 None。"""

    provider = _make_provider(tmp_path, benchmark_name="membench")
    requests = _ingest_all(provider, _membench_conversation(), "run1_mb1")

    messages = requests[0].messages
    assert messages[0]["content"] == "I went hiking. (Place: Alps, Time: 2023-06-01)"
    assert messages[0]["chat_time"] == "2023-06-01"
    # 没有二次拼接的时间 header。
    assert not messages[0]["content"].startswith("[Turn time]")
    assert messages[2]["chat_time"] is None


def test_beam_keeps_canonical_turn_ids_and_dangling_tail(tmp_path):
    """BEAM：canonical turn id 进 message_id，dangling 尾部不被重排或配对。"""

    provider = _make_provider(tmp_path, benchmark_name="beam")
    requests = _ingest_all(provider, _beam_conversation(), "run1_beam1")

    messages = requests[0].messages
    assert [m["message_id"] for m in messages] == ["raw_9", "raw_3", "raw_7"]
    assert [m["role"] for m in messages] == ["user", "assistant", "assistant"]


def test_halumem_sends_one_batch_per_session_with_session_local_task(tmp_path):
    """HaluMem：整 session 一批、task 与 session 一一对应，且不上报 session report。"""

    provider = _make_provider(tmp_path, benchmark_name="halumem")
    requests = _ingest_all(provider, _halumem_conversation(), "run1_hm1")

    assert len(requests) == 2
    assert [r.session_id for r in requests] == ["s1", "s2"]
    assert len({r.task_id for r in requests}) == 2
    assert provider.session_memory_report is False
    assert provider.end_session(
        __import__("memory_benchmark.core.provider_protocol", fromlist=["SessionRef"]).SessionRef(
            isolation_key="run1_hm1", session_id="s1"
        )
    ) is None


@pytest.mark.parametrize(
    "conversation_factory,benchmark_name,isolation_key",
    [
        (_locomo_conversation, "locomo", "run1_locomo1"),
        (_longmemeval_conversation, "longmemeval", "run1_lme1"),
        (_membench_conversation, "membench", "run1_mb1"),
        (_beam_conversation, "beam", "run1_beam1"),
        (_halumem_conversation, "halumem", "run1_hm1"),
    ],
)
def test_every_canonical_event_is_sent_exactly_once_without_leakage(
    tmp_path, conversation_factory, benchmark_name, isolation_key
):
    """五格共同契约：按声明视角精确投递、无跨 session、无私有 key。"""

    conversation = conversation_factory()
    provider = _make_provider(tmp_path, benchmark_name=benchmark_name)
    requests = _ingest_all(provider, conversation, isolation_key)

    expected_ids = [
        turn.turn_id for session in conversation.sessions for turn in session.turns
    ]
    sent_ids = [m["message_id"] for request in requests for m in request.messages]
    if benchmark_name == "locomo":
        # 官方双视角：每个真实 event 在每个 namespace 各出现一次。
        assert sent_ids == expected_ids + expected_ids
        assert len({request.user_id for request in requests}) == 2
        assert all(len(request.messages) <= 2 for request in requests)
    else:
        assert sent_ids == expected_ids
        # 其余四格每个 session 恰好一个 request。
        for request, session in zip(requests, conversation.sessions, strict=True):
            assert [m["message_id"] for m in request.messages] == [
                turn.turn_id for turn in session.turns
            ]
            assert request.session_id == session.session_id

    assert all(
        request.session_id in {session.session_id for session in conversation.sessions}
        for request in requests
    )
    assert all(
        "chat_time" in message
        for request in requests
        for message in request.messages
    )

    forbidden = {"gold_answers", "evidence", "answer", "answer_session_ids"}
    for request in requests:
        payload = request.model_dump()
        assert forbidden.isdisjoint(payload)
        assert not (request.info or {})


def test_empty_content_event_fails_fast_instead_of_placeholder(tmp_path):
    """空 content event 必须 fail-fast，不制造 placeholder，也不走上游丢字段分支。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    batch = SessionBatch(
        isolation_key="run1_conv1",
        session_id="s1",
        events=(
            TurnEvent(
                role="user",
                speaker_name="user",
                content="placeholder",
                timestamp=None,
                isolation_key="run1_conv1",
                session_id="s1",
                turn_id="t1",
                metadata={"original_content": "   ", "turn_images": []},
            ),
        ),
    )

    with pytest.raises(ConfigurationError, match="empty turn content"):
        provider.ingest(batch)


def test_non_locomo_rejects_non_canonical_role(tmp_path):
    """非 LoCoMo 只接受 canonical user/assistant role。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    batch = SessionBatch(
        isolation_key="run1_conv1",
        session_id="s1",
        events=(
            TurnEvent(
                role="Melanie",
                speaker_name="Melanie",
                content="hello",
                timestamp=None,
                isolation_key="run1_conv1",
                session_id="s1",
                turn_id="t1",
                metadata={},
            ),
        ),
    )

    with pytest.raises(ConfigurationError, match="canonical user/assistant roles"):
        provider.ingest(batch)


def test_provider_rejects_non_session_units(tmp_path):
    """provider 只接受 SessionBatch。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    event = TurnEvent(
        role="user",
        speaker_name="user",
        content="hi",
        timestamp=None,
        isolation_key="run1_conv1",
        session_id="s1",
        turn_id="t1",
    )

    with pytest.raises(ConfigurationError, match="only accepts SessionBatch"):
        provider.ingest(event)


def test_add_request_locks_product_async_lifecycle_fields(tmp_path):
    """APIADDRequest 必须锁死 namespace / cube / async 生命周期字段。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    requests = _ingest_all(provider, _longmemeval_conversation(), "run1_lme1")
    namespace = provider._namespace("run1_lme1")

    request = requests[0]
    assert request.user_id == namespace
    assert request.writable_cube_ids == [namespace]
    assert request.async_mode == "async"
    assert request.mode is None


# --------------------------------------------------------------------------------------
# 6. retrieve / readout / metric 资格
# --------------------------------------------------------------------------------------


def _product_search_data():
    """构造两个 bucket、多条 memory 的产品形状 response data。"""

    return {
        "text_mem": [
            {
                "cube_id": "cube-a",
                "total_nodes": 2,
                "memories": [
                    {
                        "id": "m1",
                        "memory": "Alice likes hiking",
                        "metadata": {
                            "relativity": 0.91,
                            "memory_type": "LongTermMemory",
                            "created_at": "2024-01-01T00:00:00",
                            "embedding": [0.1] * 384,
                            "sources": [
                                {"message_id": "t1", "role": "user"},
                                {"message_id": "t1", "role": "user"},
                                {"message_id": "t2", "role": "assistant"},
                            ],
                        },
                    },
                    {
                        "id": "m2",
                        "memory": "Alice lives in Berlin",
                        "metadata": {
                            "relativity": 0.42,
                            "memory_type": "UserMemory",
                            "embedding": [],
                            "sources": [],
                        },
                    },
                ],
            },
            {
                "cube_id": "cube-b",
                "total_nodes": 1,
                "memories": [
                    {
                        "id": "m3",
                        "memory": "Alice works nights",
                        "metadata": {"relativity": None, "memory_type": "WorkingMemory"},
                    }
                ],
            },
        ]
    }


def test_search_request_locks_all_product_switches(tmp_path):
    """APISearchRequest 的 namespace/top_k/六个开关/空 chat_history/reference_time 精确。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    runtime = provider._require_runtime()
    runtime.search_handler.response_data = {"text_mem": []}

    provider.retrieve(
        RetrievalQuery(
            query_text="where does Alice live",
            isolation_key="run1_conv1",
            question_time="2024-05-05T00:00:00",
            top_k=7,
            purpose="qa",
        )
    )

    request = runtime.search_handler.requests[0]
    namespace = provider._namespace("run1_conv1")
    assert request.query == "where does Alice live"
    assert request.user_id == namespace
    assert request.readable_cube_ids == [namespace]
    assert request.mode == "fast"
    assert request.top_k == 7
    assert request.relativity == 0.45
    assert request.dedup == "mmr"
    assert request.rerank is True
    assert request.include_preference is False
    assert request.search_tool_memory is False
    assert request.include_skill_memory is False
    assert request.neighbor_discovery is False
    assert request.internet_search is False
    assert request.chat_history == []
    assert request.filter is None
    assert request.session_id is None
    assert request.reference_time == "2024-05-05T00:00:00"


def test_locomo_retrieve_searches_both_views_and_merges_official_speaker_slots(
    tmp_path,
):
    """LoCoMo 双路各取 top_k，按 A/B speaker 槽位合并且不伪造全局 rank。"""

    provider = _make_provider(tmp_path, benchmark_name="locomo")
    _ingest_all(provider, _locomo_conversation(), "run1_locomo1")
    runtime = provider._require_runtime()
    responses = [
        {
            "text_mem": [
                {
                    "cube_id": "a",
                    "memories": [
                        {
                            "id": "a1",
                            "memory": "Caroline likes cycling",
                            "metadata": {"relativity": 0.9, "sources": []},
                        }
                    ],
                }
            ]
        },
        {
            "text_mem": [
                {
                    "cube_id": "b",
                    "memories": [
                        {
                            "id": "b1",
                            "memory": "Melanie saw the blue car",
                            "metadata": {"relativity": 0.8, "sources": []},
                        }
                    ],
                }
            ]
        },
    ]

    def _search(search_req):
        """按调用顺序返回 A/B 两路产品结果。"""
        runtime.search_handler.requests.append(search_req)
        return types.SimpleNamespace(data=responses.pop(0))

    runtime.search_handler.requests.clear()
    runtime.search_handler.handle_search_memories = _search
    result = provider.retrieve(
        RetrievalQuery(
            query_text="What do they remember?",
            isolation_key="run1_locomo1",
            question_time=None,
            top_k=7,
            purpose="qa",
        )
    )

    namespace_a = provider._namespace("run1_locomo1", locomo_view="speaker_a")
    namespace_b = provider._namespace("run1_locomo1", locomo_view="speaker_b")
    assert [request.user_id for request in runtime.search_handler.requests] == [
        namespace_a,
        namespace_b,
    ]
    assert [request.readable_cube_ids for request in runtime.search_handler.requests] == [
        [namespace_a],
        [namespace_b],
    ]
    assert [request.top_k for request in runtime.search_handler.requests] == [7, 7]
    assert [item.item_id for item in result.items] == ["a1", "b1"]
    assert [item.metadata["memos_locomo_view"] for item in result.items] == [
        "speaker_a",
        "speaker_b",
    ]
    assert result.formatted_memory == (
        "Memories for user Caroline:\n\n"
        "    Caroline likes cycling\n\n"
        "Memories for user Melanie:\n\n"
        "    Melanie saw the blue car"
    )
    assert result.metadata["retrieval_top_k_semantics"] == "per_locomo_speaker_view"


def test_locomo_resume_requires_persisted_speaker_sidecar(tmp_path):
    """resume 后新 provider 必须从 sidecar 恢复真实 speaker，缺失不能猜。"""

    first = _make_provider(tmp_path, benchmark_name="locomo")
    _ingest_all(first, _locomo_conversation(), "run1_locomo1")

    resumed = _make_provider(tmp_path, benchmark_name="locomo")
    resumed._require_runtime().search_handler.response_data = {"text_mem": []}
    result = resumed.retrieve(
        RetrievalQuery(
            query_text="q",
            isolation_key="run1_locomo1",
            question_time=None,
            top_k=2,
            purpose="qa",
        )
    )
    assert result.formatted_memory == MEMOS_EMPTY_MEMORY_SENTINEL
    assert len(resumed._require_runtime().search_handler.requests) == 2

    resumed._locomo_view_sidecar_path("run1_locomo1").unlink()
    missing = _make_provider(tmp_path, benchmark_name="locomo")
    missing._require_runtime().search_handler.response_data = {"text_mem": []}
    with pytest.raises(ConfigurationError, match="missing its speaker sidecar"):
        missing.retrieve(
            RetrievalQuery(
                query_text="q",
                isolation_key="run1_locomo1",
                question_time=None,
                top_k=2,
                purpose="qa",
            )
        )


def test_retrieve_flattens_buckets_in_product_order_without_resorting(tmp_path):
    """两个 bucket 按产品返回顺序扁平化，不二次排序、不截断。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    provider._require_runtime().search_handler.response_data = _product_search_data()

    result = provider.retrieve(
        RetrievalQuery(
            query_text="q",
            isolation_key="run1_conv1",
            question_time=None,
            top_k=2,
            purpose="qa",
        )
    )

    assert [item.item_id for item in result.items] == ["m1", "m2", "m3"]
    assert [item.score for item in result.items] == [0.91, 0.42, None]
    assert result.items[0].timestamp == "2024-01-01T00:00:00"
    assert result.items[1].timestamp is None
    assert result.formatted_memory == (
        "Alice likes hiking\n\nAlice lives in Berlin\n\nAlice works nights"
    )
    assert result.metadata["reference_time_effect"] == MEMOS_REFERENCE_TIME_EFFECT


def test_retrieve_dedups_source_message_ids_stably(tmp_path):
    """sources 中重复 message_id 稳定去重并保持产品顺序。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    provider._require_runtime().search_handler.response_data = _product_search_data()

    result = provider.retrieve(
        RetrievalQuery(
            query_text="q",
            isolation_key="run1_conv1",
            question_time=None,
            top_k=5,
            purpose="qa",
        )
    )

    assert result.items[0].source_turn_ids == ("t1", "t2")


def test_retrieve_strips_embeddings_from_artifact_metadata(tmp_path):
    """embedding 与不可序列化对象不得进入 artifact。"""

    data = _product_search_data()
    data["text_mem"][0]["memories"][0]["metadata"]["opaque"] = object()
    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    provider._require_runtime().search_handler.response_data = data

    result = provider.retrieve(
        RetrievalQuery(
            query_text="q",
            isolation_key="run1_conv1",
            question_time=None,
            top_k=5,
            purpose="qa",
        )
    )

    assert "embedding" not in result.items[0].metadata
    assert "opaque" not in result.items[0].metadata
    assert result.items[0].metadata["memory_type"] == "LongTermMemory"


def test_zero_hit_returns_sentinel_and_empty_items(tmp_path):
    """零命中返回非空 sentinel + 空 items。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    provider._require_runtime().search_handler.response_data = {
        "text_mem": [{"cube_id": "c", "memories": [], "total_nodes": 0}]
    }

    result = provider.retrieve(
        RetrievalQuery(
            query_text="q",
            isolation_key="run1_conv1",
            question_time=None,
            top_k=5,
            purpose="qa",
        )
    )

    assert result.items == ()
    assert result.formatted_memory == MEMOS_EMPTY_MEMORY_SENTINEL


def test_backend_failure_does_not_become_zero_hit(tmp_path):
    """search handler 抛错必须传播，不得退化成 zero-hit。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")

    def _boom(search_req):
        """模拟 backend 失败。"""
        raise RuntimeError("neo4j down")

    provider._require_runtime().search_handler.handle_search_memories = _boom

    with pytest.raises(RuntimeError, match="neo4j down"):
        provider.retrieve(
            RetrievalQuery(
                query_text="q",
                isolation_key="run1_conv1",
                question_time=None,
                top_k=5,
                purpose="qa",
            )
        )


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda d: d["text_mem"][0]["memories"][0].pop("id"), "missing a non-empty id"),
        (
            lambda d: d["text_mem"][0]["memories"][0].update({"memory": "  "}),
            "missing non-empty memory text",
        ),
        (
            lambda d: d["text_mem"][0]["memories"][0]["metadata"].update(
                {"relativity": "high"}
            ),
            "non-numeric relativity",
        ),
        (lambda d: d.update({"text_mem": {"not": "a list"}}), "must be a list"),
        (lambda d: d.update({"text_mem": ["not-a-mapping"]}), "must be a mapping"),
    ],
)
def test_malformed_search_payload_fails_fast(tmp_path, mutate, expected):
    """id/content 缺失、非数值 score、非法 bucket shape 一律 fail-fast。"""

    data = _product_search_data()
    mutate(data)
    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    provider._require_runtime().search_handler.response_data = data

    with pytest.raises(ConfigurationError, match=expected):
        provider.retrieve(
            RetrievalQuery(
                query_text="q",
                isolation_key="run1_conv1",
                question_time=None,
                top_k=5,
                purpose="qa",
            )
        )


@pytest.mark.parametrize("response_data", [_product_search_data(), {"text_mem": []}])
def test_retrieval_evidence_is_pending_regardless_of_hits(tmp_path, response_data):
    """无论命中与否，两项 evidence 都是 pending / provenance none。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    provider._require_runtime().search_handler.response_data = response_data

    result = provider.retrieve(
        RetrievalQuery(
            query_text="q",
            isolation_key="run1_conv1",
            question_time=None,
            top_k=5,
            purpose="qa",
        )
    )

    evidence = result.evidence
    assert evidence.semantic_provenance.status == "pending"
    assert (
        evidence.semantic_provenance.reason_code
        == "memos_generated_memory_semantic_lineage_unverified"
    )
    assert evidence.provenance_granularity == "none"
    assert evidence.stable_ranking.status == "pending"
    assert (
        evidence.stable_ranking.reason_code
        == "memos_product_rerank_stability_unverified"
    )


def test_memory_update_probe_uses_declared_top_k(tmp_path):
    """HaluMem update probe 忠实使用 query.top_k，不在 adapter 写 benchmark 特判。"""

    provider = _make_provider(tmp_path, benchmark_name="halumem")
    runtime = provider._require_runtime()
    runtime.search_handler.response_data = {"text_mem": []}

    provider.retrieve(
        RetrievalQuery(
            query_text="probe",
            isolation_key="run1_hm1",
            question_time=None,
            top_k=13,
            purpose="memory_update_probe",
        )
    )

    assert runtime.search_handler.requests[0].top_k == 13


# --------------------------------------------------------------------------------------
# 7. clean retry
# --------------------------------------------------------------------------------------


class _CleanProbe:
    """记录 delete/get 调用的 namespace-scoped clean 替身。"""

    def __init__(self, *, delete_status="success", remaining=0):
        """配置 delete 结果与 readback 剩余条数。"""
        self.delete_status = delete_status
        self.remaining = remaining
        self.delete_requests: list = []
        self.get_requests: list = []

    def delete(self, request, mem_cube):
        """模拟 handle_delete_memories。"""
        self.delete_requests.append(request)
        return types.SimpleNamespace(data={"status": self.delete_status})

    def get(self, request, mem_cube):
        """模拟 handle_get_memories。"""
        self.get_requests.append(request)
        memories = [{"id": f"m{i}"} for i in range(self.remaining)]
        return types.SimpleNamespace(
            data={
                "text_mem": [
                    {
                        "cube_id": request.mem_cube_id,
                        "memories": memories,
                        "total_nodes": self.remaining,
                    }
                ]
            }
        )


def _install_clean_probe(monkeypatch, probe: _CleanProbe) -> None:
    """把 clean probe 装到真实 memory_handler 模块入口上。"""

    import memos.api.handlers.memory_handler as memory_handler

    monkeypatch.setattr(memory_handler, "handle_delete_memories", probe.delete)
    monkeypatch.setattr(memory_handler, "handle_get_memories", probe.get)


def test_clean_deletes_only_target_namespace_and_verifies_empty(
    tmp_path, memos_product_models, monkeypatch
):
    """clean 只删目标 namespace，且以 readback 为空作为后置条件。"""

    probe = _CleanProbe()
    _install_clean_probe(monkeypatch, probe)
    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    namespace = provider._namespace("run1_conv1")

    clean_memos_conversation_state(provider=provider, isolation_key="run1_conv1")

    delete_request = probe.delete_requests[0]
    assert delete_request.writable_cube_ids == [namespace]
    assert delete_request.user_id == namespace
    assert delete_request.memory_ids is None  # 绝不走 delete_by_memory_ids
    get_request = probe.get_requests[0]
    assert get_request.mem_cube_id == namespace
    assert get_request.include_preference is False
    assert get_request.include_tool_memory is False
    assert get_request.include_skill_memory is False


def test_locomo_clean_deletes_both_views_after_global_pending_preflight(
    tmp_path,
    memos_product_models,
    monkeypatch,
):
    """LoCoMo clean 必须覆盖双 namespace，并在首个 delete 前检查完两路 pending。"""

    probe = _CleanProbe()
    _install_clean_probe(monkeypatch, probe)
    provider = _make_provider(tmp_path, benchmark_name="locomo")
    batch = _session_batches(_locomo_conversation(), "run1_locomo1")[0]
    provider._register_locomo_view_sidecar(batch)
    sidecar = provider._locomo_view_sidecar_path("run1_locomo1")
    assert sidecar.is_file()

    namespace_a = provider._namespace("run1_locomo1", locomo_view="speaker_a")
    namespace_b = provider._namespace("run1_locomo1", locomo_view="speaker_b")
    clean_memos_conversation_state(
        provider=provider,
        isolation_key="run1_locomo1",
    )

    assert [request.user_id for request in probe.delete_requests] == [
        namespace_a,
        namespace_b,
    ]
    assert [request.mem_cube_id for request in probe.get_requests] == [
        namespace_a,
        namespace_b,
    ]
    assert not sidecar.exists()

    blocked = _make_provider(tmp_path, benchmark_name="locomo")
    blocked._register_locomo_view_sidecar(batch)
    blocked._require_runtime().tracker.task_submitted(
        task_id="pending-b",
        user_id=namespace_b,
        task_type="mem_read",
        business_task_id="biz-b",
        mem_cube_id=namespace_b,
    )
    probe.delete_requests.clear()
    probe.get_requests.clear()
    with pytest.raises(ConfigurationError, match="still pending"):
        clean_memos_conversation_state(
            provider=blocked,
            isolation_key="run1_locomo1",
        )
    assert probe.delete_requests == []
    assert probe.get_requests == []


def test_clean_rejects_handler_failure(tmp_path, memos_product_models, monkeypatch):
    """handler 返回 failure 不得当成功。"""

    _install_clean_probe(monkeypatch, _CleanProbe(delete_status="failure"))
    provider = _make_provider(tmp_path, benchmark_name="longmemeval")

    with pytest.raises(ConfigurationError, match="delete failed"):
        clean_memos_conversation_state(provider=provider, isolation_key="run1_conv1")


def test_clean_rejects_non_empty_readback(tmp_path, memos_product_models, monkeypatch):
    """readback 非空必须 fail-fast。"""

    _install_clean_probe(monkeypatch, _CleanProbe(remaining=2))
    provider = _make_provider(tmp_path, benchmark_name="longmemeval")

    with pytest.raises(ConfigurationError, match="still holds memories"):
        clean_memos_conversation_state(provider=provider, isolation_key="run1_conv1")


def test_clean_refuses_when_namespace_has_pending_tasks(
    tmp_path, memos_product_models, monkeypatch
):
    """该 namespace 仍有 pending task 时拒绝删除。"""

    probe = _CleanProbe()
    _install_clean_probe(monkeypatch, probe)
    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    namespace = provider._namespace("run1_conv1")
    provider._require_runtime().tracker.task_submitted(
        task_id="still-running",
        user_id=namespace,
        task_type="mem_read",
        business_task_id="biz",
        mem_cube_id=namespace,
    )

    with pytest.raises(ConfigurationError, match="still pending"):
        clean_memos_conversation_state(provider=provider, isolation_key="run1_conv1")

    assert probe.delete_requests == []


# --------------------------------------------------------------------------------------
# 8. namespace 与 source identity
# --------------------------------------------------------------------------------------


def test_namespace_is_deterministic_isolated_and_path_free():
    """namespace 稳定、跨 conversation/run 隔离、只含安全字符、不含绝对路径。"""

    first = build_memos_namespace(
        storage_root_relative="outputs/run-a/method_state", isolation_key="run1_conv1"
    )
    same = build_memos_namespace(
        storage_root_relative="outputs/run-a/method_state", isolation_key="run1_conv1"
    )
    other_conversation = build_memos_namespace(
        storage_root_relative="outputs/run-a/method_state", isolation_key="run1_conv2"
    )
    other_run = build_memos_namespace(
        storage_root_relative="outputs/run-b/method_state", isolation_key="run1_conv1"
    )
    other_worker = build_memos_namespace(
        storage_root_relative="outputs/run-a/method_state/worker_1",
        isolation_key="run1_conv1",
    )

    assert first == same
    assert len({first, other_conversation, other_run, other_worker}) == 4
    assert first.isalnum() and first.islower() or first.isalnum()
    assert "/" not in first and "\\" not in first


def test_same_conversation_shares_namespace_across_add_search_and_clean(tmp_path):
    """同一 conversation 的 add/search/clean 必须得到同一 namespace。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    runtime = provider._require_runtime()
    runtime.search_handler.response_data = {"text_mem": []}
    _ingest_all(provider, _longmemeval_conversation(), "run1_conv1")
    provider.retrieve(
        RetrievalQuery(
            query_text="q",
            isolation_key="run1_conv1",
            question_time=None,
            top_k=1,
            purpose="qa",
        )
    )

    add_namespace = runtime.add_handler.requests[0].user_id
    search_namespace = runtime.search_handler.requests[0].user_id
    assert add_namespace == search_namespace == provider._namespace("run1_conv1")


def test_source_identity_declares_upstream_patch_and_implementation():
    """source identity 必须含 upstream/tag/commit/patch/wrapper/实现身份。"""

    identity = build_memos_source_identity()

    assert identity["upstream_url"] == "https://github.com/MemTensor/MemOS.git"
    assert identity["release_tag"] == "v2.0.25"
    assert identity["commit"] == "e820406269537b97d270687e3e40eea2f015f81a"
    assert identity["patch_path"] == (
        "scripts/patches/memos-product-runtime-observability.patch"
    )
    assert len(identity["patch_sha256"]) == 64
    assert identity["wrapper_path"] == "src/memory_benchmark/methods/memos_adapter.py"
    assert len(identity["wrapper_sha256"]) == 64
    assert identity["implementation_identity"] == "typed-product-handler"
    assert "src/memos/llms/openai.py" in identity["files"]
    # 不得声称 native LoCoMo harness。
    assert "locomo" not in identity["source_mode"].lower()


# --------------------------------------------------------------------------------------
# 9. config 守门
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides,expected",
    [
        ({"add_async_mode": "sync"}, "async"),
        ({"add_mode": "fine"}, "add_mode=None"),
        ({"memory_backend": "general_text"}, "tree_text"),
        ({"search_mode": "fine"}, "search_mode='fast'"),
        ({"use_redis_queue": True}, "local scheduler queue"),
        ({"parallel_dispatch": False}, "parallel dispatcher"),
        ({"reorganize": True}, "reorganize=false"),
        ({"include_preference": True}, "include_preference=false"),
        ({"internet_search": True}, "internet_search=false"),
        ({"max_workers": 4}, "max_workers 必须为 1"),
        ({"task_timeout_seconds": 0}, "task_timeout_seconds must be positive"),
    ],
)
def test_config_rejects_profile_drift(overrides, expected):
    """任何偏离主 profile 身份的配置都必须 fail-fast。"""

    with pytest.raises(ConfigurationError, match=expected):
        _make_config(**overrides)


def test_manifest_never_leaks_secrets_or_absolute_paths():
    """manifest 只写环境变量名，不写 secret 值或绝对路径。"""

    manifest = _make_config().to_manifest()

    assert manifest["adapter_version"] == "memos-v2.0.25-product-v4"
    assert manifest["build_llm_response_contract"] == (
        "provider-aware-v1:"
        "opencodego=json_object+thinking_disabled;"
        "primary=provider_default"
    )
    assert manifest["graph_db_credential_env"] == "MEMOS_NEO4J_PASSWORD"
    assert manifest["vector_db_credential_env"] == "MEMOS_QDRANT_API_KEY"
    assert "graph_db_password" not in manifest
    assert "vector_db_api_key" not in manifest
    for value in manifest.values():
        assert not (isinstance(value, str) and value.startswith("/"))


# --------------------------------------------------------------------------------------
# 10. M4-R1：cleanup refusal 必须可重试（成功后才提交状态）
# --------------------------------------------------------------------------------------


class _StopCountingRuntime(_FakeRuntime):
    """命名清晰的别名：close/stop 语义完全由 `_FakeRuntime` 提供。

    保留独立名称是为了让 stop-failure 反例的意图一眼可读；注入方式是
    `runtime.fail_stop = True`。
    """


def _pending_task(provider: MemOS, runtime, isolation_key="run1_conv1") -> str:
    """在 tracker 上登记一个未终结的 MEM_READ task，返回 item id。"""

    namespace = provider._namespace(isolation_key)
    runtime.tracker.task_submitted(
        task_id="biz-item0",
        user_id=namespace,
        task_type="mem_read",
        business_task_id="biz",
        mem_cube_id=namespace,
    )
    return "biz-item0"


def test_cleanup_refusal_keeps_every_retryable_reference(tmp_path):
    """pending 拒绝后 provider/owner/runtime 引用必须原样保留，可再次重试。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    runtime = provider._require_runtime()
    owner = provider._runtime_owner
    _pending_task(provider, runtime)

    with pytest.raises(ConfigurationError, match="拒绝静默关闭"):
        provider.cleanup()

    # 关键：拒绝之后一切引用不变，runtime 没有变成"仍在跑却无人持有"的孤儿。
    assert provider._cleaned is False
    assert provider._runtime is runtime
    assert owner._runtime is runtime
    assert runtime.closed is False
    assert runtime.stop_calls == 0


def test_cleanup_succeeds_after_task_reaches_terminal_with_single_stop(tmp_path):
    """pending task 转终态后重试 cleanup 必须真正关闭，且 stop 总计恰好一次。"""

    provider = _make_provider(tmp_path, benchmark_name="longmemeval")
    runtime = provider._require_runtime()
    owner = provider._runtime_owner
    namespace = provider._namespace("run1_conv1")
    item_id = _pending_task(provider, runtime)

    with pytest.raises(ConfigurationError):
        provider.cleanup()

    runtime.tracker.task_started(task_id=item_id, user_id=namespace)
    runtime.tracker.task_completed(item_id, namespace)

    provider.cleanup()

    assert provider._cleaned is True
    assert provider._runtime is None
    assert owner._runtime is None
    assert runtime.closed is True
    assert runtime.stop_calls == 1

    # 再次 cleanup 幂等，不二次 stop。
    provider.cleanup()
    assert runtime.stop_calls == 1


def test_scheduler_stop_failure_is_visible_and_owner_keeps_reference(tmp_path):
    """scheduler stop 抛错必须可见，且 owner 不得把 runtime 丢成孤儿。"""

    provider = _make_provider(
        tmp_path,
        benchmark_name="longmemeval",
        runtime_factory=_StopCountingRuntime,
    )
    runtime = provider._require_runtime()
    owner = provider._runtime_owner
    runtime.fail_stop = True

    with pytest.raises(RuntimeError, match="scheduler stop exploded"):
        provider.cleanup()

    assert owner._runtime is runtime
    assert provider._runtime is runtime
    assert provider._cleaned is False
    assert runtime.closed is False
    assert runtime.close_failed is True
    assert runtime.stop_calls == 1


def test_real_runtime_close_commits_state_only_after_success(tmp_path):
    """真实 MemosRuntime.close 的状态机同样是"成功后提交"。"""

    from memory_benchmark.methods.memos_adapter import MemosRuntime

    runtime = object.__new__(MemosRuntime)
    runtime._closed = False
    runtime._close_failed = False
    runtime._close_error = None
    runtime.tracker = MemosLocalTaskTracker()
    stop_calls: list[int] = []
    runtime.scheduler = types.SimpleNamespace(
        stop=lambda: stop_calls.append(1)
    )
    runtime.tracker.task_submitted(
        task_id="i0",
        user_id="ns",
        task_type="mem_read",
        business_task_id="biz",
        mem_cube_id="ns",
    )

    with pytest.raises(ConfigurationError, match="拒绝静默关闭"):
        runtime.close()
    assert runtime.closed is False
    assert stop_calls == []

    runtime.tracker.task_started(task_id="i0", user_id="ns")
    runtime.tracker.task_completed("i0", "ns")
    runtime.close()

    assert runtime.closed is True
    assert stop_calls == [1]
    runtime.close()
    assert stop_calls == [1]


# --------------------------------------------------------------------------------------
# 11. M4-R1：clean hook → 根 provider 的单 runtime 交接
# --------------------------------------------------------------------------------------


def test_root_provider_closes_runtime_created_by_clean_hook(tmp_path):
    """clean hook 建好 runtime、根 provider 从未 acquire 时，根 cleanup 必须接管关闭。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings

    owner = _MemosRuntimeOwner()
    path_settings = load_path_settings()
    storage_root = path_settings.project_root / "outputs" / "unit-test-run" / "method_state"
    config = _make_config()
    shared = dict(
        config=config,
        path_settings=path_settings,
        storage_root=storage_root,
        openai_settings=OpenAISettings(api_key="k", base_url=None),
        runtime_owner=owner,
        runtime_factory=_FakeRuntime,
    )
    # clean hook 用的临时 provider 先 lazy 建好共享 runtime。
    hook_provider = MemOS(benchmark_name="longmemeval", **shared)
    runtime = hook_provider._require_runtime()
    # 根 provider 同 config，但自己从未 _require_runtime()。
    root_provider = MemOS(benchmark_name="longmemeval", **shared)
    assert root_provider._runtime is None

    root_provider.cleanup()

    assert runtime.closed is True
    assert runtime.stop_calls == 1
    assert owner._runtime is None


def test_root_cleanup_with_empty_owner_does_not_build_runtime(tmp_path):
    """owner 为空的 no-work run，cleanup 不得反向构造 runtime。"""

    built: list[str] = []

    def _tracking_factory(**kwargs):
        """记录是否被调用。"""
        built.append("built")
        return _FakeRuntime(**kwargs)

    provider = _make_provider(
        tmp_path,
        benchmark_name="longmemeval",
        runtime_factory=_tracking_factory,
    )

    provider.cleanup()

    assert built == []
    assert provider._runtime_owner._runtime is None
    assert provider._cleaned is True


def test_root_cleanup_fails_fast_on_conflicting_owner_identity(tmp_path):
    """owner 持有另一份 config identity 时必须 fail-fast，且不关闭对方。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings

    owner = _MemosRuntimeOwner()
    path_settings = load_path_settings()
    storage_root = path_settings.project_root / "outputs" / "unit-test-run" / "method_state"
    openai = OpenAISettings(api_key="k", base_url=None)

    other = MemOS(
        config=_make_config(search_relativity=0.9),
        path_settings=path_settings,
        storage_root=storage_root,
        openai_settings=openai,
        runtime_owner=owner,
        runtime_factory=_FakeRuntime,
    )
    other_runtime = other._require_runtime()

    root = MemOS(
        config=_make_config(),
        path_settings=path_settings,
        storage_root=storage_root,
        openai_settings=openai,
        runtime_owner=owner,
        runtime_factory=_FakeRuntime,
    )

    with pytest.raises(ConfigurationError, match="different config identity"):
        root.cleanup()

    assert other_runtime.closed is False
    assert other_runtime.stop_calls == 0
    assert owner._runtime is other_runtime


# --------------------------------------------------------------------------------------
# 12. M4-R1：环境作用域恢复
# --------------------------------------------------------------------------------------


def _fake_component_bundle(scheduler=None, naive_cube=None):
    """返回真实 Add/SearchHandler 构造所需的最小外部组件叶子集合。

    条目来自 current `AddHandler._validate_dependencies` 与
    `SearchHandler._validate_dependencies`；全部是惰性占位对象，不连任何真实服务。
    """

    return {
        "mem_scheduler": scheduler if scheduler is not None else types.SimpleNamespace(
            dispatcher=types.SimpleNamespace(status_tracker=None),
            status_tracker=None,
        ),
        "naive_mem_cube": naive_cube if naive_cube is not None else object(),
        "mem_reader": object(),
        "feedback_server": object(),
        "searcher": object(),
        "deepsearch_agent": object(),
        "llm": object(),
    }


def _install_fake_init_server(monkeypatch, observer, *, boom=False):
    """把 component_init.init_server 换成只观察环境的替身。"""

    import memos.api.handlers.component_init as component_init

    def _fake_init_server():
        """在作用域内快照环境，然后按需抛错。"""
        observer.update(
            {
                key: os.environ.get(key)
                for key in (
                    "MOS_CHAT_MODEL",
                    "MOS_EMBEDDER_BACKEND",
                    "MOS_EMBEDDER_DIMS",
                    "MEMSCHEDULER_USE_REDIS_QUEUE",
                    "MOS_ENABLE_REORGANIZE",
                    "ENABLE_CHAT_API",
                    "NACOS_ENABLE_WATCH",
                    "OPENAI_API_KEY",
                    "MEMRADER_MODEL",
                    "MEMRADER_API_KEY",
                    "MEMRADER_API_BASE",
                    "MEMRADER_PROVIDER_COMPATIBILITY",
                    "NEO4J_PASSWORD",
                    "MEMOS_ONLY_PREEXISTING",
                )
            }
        )
        if boom:
            raise RuntimeError("init_server exploded")
        return _fake_component_bundle()

    monkeypatch.setattr(component_init, "init_server", _fake_init_server)


@pytest.mark.parametrize("boom", [False, True])
def test_scoped_environment_restores_exactly_on_success_and_failure(
    tmp_path, memos_product_models, monkeypatch, boom
):
    """init_server 成功与抛错都必须逐字恢复原环境，且 secret 不外泄。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings
    from memory_benchmark.methods.memos_adapter import MemosRuntime

    # 一组"将被覆盖"的预置值 + 一组"原先不存在"的键。
    monkeypatch.setenv("MOS_CHAT_MODEL", "preexisting-model")
    monkeypatch.setenv("MEMSCHEDULER_USE_REDIS_QUEUE", "true")
    monkeypatch.setenv("MEMOS_ONLY_PREEXISTING", "keep-me")
    monkeypatch.setenv("MEMOS_NEO4J_PASSWORD", "super-secret-neo4j")
    monkeypatch.delenv("MOS_EMBEDDER_BACKEND", raising=False)
    monkeypatch.delenv("MOS_EMBEDDER_DIMS", raising=False)
    monkeypatch.delenv("NACOS_ENABLE_WATCH", raising=False)
    monkeypatch.delenv("NEO4J_PASSWORD", raising=False)
    monkeypatch.delenv("MEMRADER_PROVIDER_COMPATIBILITY", raising=False)

    before = dict(os.environ)
    observed: dict[str, str | None] = {}
    _install_fake_init_server(monkeypatch, observed, boom=boom)

    def _build():
        """构造真实 MemosRuntime（init_server 已被替身接管）。"""
        return MemosRuntime(
            config=_make_config(),
            openai_settings=OpenAISettings(api_key="sk-super-secret", base_url=None),
            path_settings=load_path_settings(),
        )

    if boom:
        with pytest.raises(RuntimeError) as excinfo:
            _build()
        # secret 不得进入异常文本。
        assert "sk-super-secret" not in str(excinfo.value)
        assert "super-secret-neo4j" not in str(excinfo.value)
    else:
        _build()

    # 作用域内：config / OpenAI / secret 值精确可见。
    assert observed["MOS_CHAT_MODEL"] == "gpt-4o-mini"
    assert observed["MOS_EMBEDDER_BACKEND"] == "sentence_transformer"
    assert observed["MOS_EMBEDDER_DIMS"] == "384"
    assert observed["MEMSCHEDULER_USE_REDIS_QUEUE"] == "false"
    assert observed["MOS_ENABLE_REORGANIZE"] == "false"
    assert observed["ENABLE_CHAT_API"] == "false"
    assert observed["NACOS_ENABLE_WATCH"] == "false"
    assert observed["OPENAI_API_KEY"] == "sk-super-secret"
    assert observed["MEMRADER_MODEL"] == "gpt-4o-mini"
    assert observed["MEMRADER_API_KEY"] == "sk-super-secret"
    assert observed["MEMRADER_API_BASE"] == "https://api.openai.com/v1"
    assert observed["MEMRADER_PROVIDER_COMPATIBILITY"] is None
    assert observed["NEO4J_PASSWORD"] == "super-secret-neo4j"
    # 与本 config 无关的预置键不受影响。
    assert observed["MEMOS_ONLY_PREEXISTING"] == "keep-me"

    # 作用域外：逐字恢复，被覆盖的回到原值、原先不存在的重新消失。
    assert dict(os.environ) == before
    assert os.environ["MOS_CHAT_MODEL"] == "preexisting-model"
    assert os.environ["MEMSCHEDULER_USE_REDIS_QUEUE"] == "true"
    assert "MOS_EMBEDDER_BACKEND" not in os.environ
    assert "NEO4J_PASSWORD" not in os.environ


def test_memos_environment_reads_secrets_only_from_declared_env_names(tmp_path):
    """secret 只从声明的环境变量名读取；缺失时 fail-fast。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings
    from memory_benchmark.methods.memos_adapter import _memos_environment

    config = _make_config()
    settings = load_path_settings()
    openai = OpenAISettings(api_key="sk-x", base_url=None)

    saved = os.environ.pop(config.graph_db_credential_env, None)
    try:
        with pytest.raises(ConfigurationError, match="password environment variable"):
            _memos_environment(config, openai, settings)
    finally:
        if saved is not None:
            os.environ[config.graph_db_credential_env] = saved


def test_memos_environment_selects_opencodego_reader_contract(
    tmp_path, monkeypatch
):
    """smoke provider 只在初始化作用域内选择对应 reader 请求契约。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings
    from memory_benchmark.methods.memos_adapter import _memos_environment

    config = _make_config()
    monkeypatch.setenv(config.graph_db_credential_env, "unit-test-password")
    openai = OpenAISettings(
        api_key="sk-opencodego-unit-test",
        base_url="https://example.invalid/v1",
        model="deepseek-v4-flash",
        provider="opencodego",
        judge_transport="chat_completions",
    )

    values = _memos_environment(config, openai, load_path_settings())

    assert (
        values["MEMRADER_PROVIDER_COMPATIBILITY"]
        == "opencodego_json_non_thinking_v1"
    )
    assert "sk-opencodego-unit-test" not in repr(
        {
            "compatibility": values["MEMRADER_PROVIDER_COMPATIBILITY"],
            "model": values["MEMRADER_MODEL"],
        }
    )


# --------------------------------------------------------------------------------------
# 13. M4-R1：真实 MemosRuntime 装配面（只 fake 外部组件叶子）
# --------------------------------------------------------------------------------------


def test_real_runtime_inits_once_and_shares_one_dependencies_bundle(
    tmp_path, memos_product_models, monkeypatch
):
    """穿过真实 MemosRuntime.__init__：init_server 恰好一次，两 handler 共用同一 bundle。"""

    import memos.api.handlers.component_init as component_init
    from memory_benchmark.config import OpenAISettings, load_path_settings
    from memory_benchmark.methods import memos_adapter as adapter_module
    from memory_benchmark.methods.memos_adapter import MemosRuntime

    monkeypatch.setenv("MEMOS_NEO4J_PASSWORD", "pw")
    init_calls: list[int] = []
    scheduler = types.SimpleNamespace(
        dispatcher=types.SimpleNamespace(status_tracker=None),
        status_tracker=None,
    )
    naive_cube = object()

    def _fake_init_server():
        """只返回外部组件叶子，不连任何真实服务。"""
        init_calls.append(1)
        return _fake_component_bundle(scheduler=scheduler, naive_cube=naive_cube)

    monkeypatch.setattr(component_init, "init_server", _fake_init_server)
    # install_local_tracker 走真实实现（scheduler/dispatcher 是叶子替身）。
    runtime = MemosRuntime(
        config=_make_config(),
        openai_settings=OpenAISettings(api_key="sk", base_url=None),
        path_settings=load_path_settings(),
    )

    assert init_calls == [1], "每个 runtime 只允许 init_server 一次"
    # 真实 AddHandler / SearchHandler 必须共用同一 HandlerDependencies 对象
    # （current BaseHandler 把它存成 `.deps`）。
    assert runtime.add_handler.deps is runtime.search_handler.deps
    assert runtime.add_handler.deps is runtime.dependencies
    # scheduler / naive cube / tracker 都来自同一 bundle。
    assert runtime.scheduler is scheduler
    assert runtime.naive_mem_cube is naive_cube
    assert scheduler.status_tracker is runtime.tracker
    assert scheduler.dispatcher.status_tracker is runtime.tracker
    assert isinstance(runtime.tracker, MemosLocalTaskTracker)
    # 仍然不得触发 server_router。
    assert "memos.api.routers.server_router" not in sys.modules
    assert adapter_module.MEMOS_ADAPTER_VERSION == "memos-v2.0.25-product-v4"


# --------------------------------------------------------------------------------------
# 14. M4-R1 follow-up：scheduler.stop() 失败必须永久 fail-closed
# --------------------------------------------------------------------------------------
#
# 一手依据（current MemOS v2.0.25
# `src/memos/mem_scheduler/base_mixins/queue_ops.py`）：
#   stop() → stop_consumer() 先把 `_running=False` → 再 dispatcher.shutdown()
#            → 再 dispatcher_monitor.stop()
# 因此后半段抛错时 scheduler 可能只关掉一部分，而第二次调用 upstream stop()
# 会因 `_running=False` 直接返回。"第二次 cleanup 跳过 stop 并标 closed" 会把
# 未证实的关闭伪装成成功，故本节锁死永久 fail-closed 语义。


def _stop_failing_provider(tmp_path):
    """构造一个已注入 stop 失败的 provider，返回 (provider, runtime, owner)。"""

    provider = _make_provider(
        tmp_path,
        benchmark_name="longmemeval",
        runtime_factory=_StopCountingRuntime,
    )
    runtime = provider._require_runtime()
    runtime.fail_stop = True
    return provider, runtime, provider._runtime_owner


def test_first_stop_failure_is_visible_and_marks_close_failed(tmp_path):
    """首次 stop 抛错：异常可见、stop 恰一次、引用全保留、closed=False。"""

    provider, runtime, owner = _stop_failing_provider(tmp_path)

    with pytest.raises(RuntimeError, match="scheduler stop exploded"):
        provider.cleanup()

    assert runtime.stop_calls == 1
    assert runtime.closed is False
    assert runtime.close_failed is True
    assert provider._cleaned is False
    assert provider._runtime is runtime
    assert owner._runtime is runtime


def test_subsequent_cleanups_after_stop_failure_keep_failing_closed(tmp_path):
    """第二、三次 cleanup 必须稳定 fail-fast，且不再调用 stop、不标 closed。"""

    provider, runtime, owner = _stop_failing_provider(tmp_path)

    with pytest.raises(RuntimeError, match="scheduler stop exploded"):
        provider.cleanup()

    for _ in range(2):
        with pytest.raises(ConfigurationError, match="permanently unusable"):
            provider.cleanup()
        # 永远不得标 closed、不得清引用、不得二次 stop。
        assert runtime.stop_calls == 1
        assert runtime.closed is False
        assert runtime.close_failed is True
        assert provider._cleaned is False
        assert provider._runtime is runtime
        assert owner._runtime is runtime


def test_stop_failure_error_chain_links_back_to_first_failure(tmp_path):
    """后续 fail-fast 必须用 `raise ... from` 链回首次 stop failure。"""

    provider, runtime, _ = _stop_failing_provider(tmp_path)

    with pytest.raises(RuntimeError):
        provider.cleanup()

    with pytest.raises(ConfigurationError) as excinfo:
        provider.cleanup()

    assert excinfo.value.__cause__ is runtime.close_error
    assert "scheduler stop exploded" in str(excinfo.value.__cause__)


def test_acquire_refuses_close_failed_runtime_without_building_a_second(tmp_path):
    """close-failed 后 acquire 同 config 必须拒绝，且不新建 runtime。"""

    from memory_benchmark.config import OpenAISettings, load_path_settings

    built: list[str] = []

    def _counting_factory(**kwargs):
        """记录 runtime 构造次数。"""
        built.append("built")
        return _StopCountingRuntime(**kwargs)

    provider = _make_provider(
        tmp_path,
        benchmark_name="longmemeval",
        runtime_factory=_counting_factory,
    )
    runtime = provider._require_runtime()
    runtime.fail_stop = True
    owner = provider._runtime_owner
    assert built == ["built"]

    with pytest.raises(RuntimeError, match="scheduler stop exploded"):
        provider.cleanup()

    with pytest.raises(ConfigurationError, match="previously failed to close"):
        owner.acquire(
            config=_make_config(),
            openai_settings=OpenAISettings(api_key="k", base_url=None),
            path_settings=load_path_settings(),
            runtime_factory=_counting_factory,
        )

    # 既不复用、也不构造第二份。
    assert built == ["built"]
    assert owner._runtime is runtime
    assert runtime.closed is False


def test_release_current_for_config_refuses_close_failed_runtime(tmp_path):
    """根 provider 的交接路径遇到 close-failed 同样拒绝并保留引用。"""

    provider, runtime, owner = _stop_failing_provider(tmp_path)

    with pytest.raises(RuntimeError, match="scheduler stop exploded"):
        provider.cleanup()

    with pytest.raises(ConfigurationError, match="permanently unusable"):
        owner.release_current_for_config(provider.config)

    assert owner._runtime is runtime
    assert runtime.closed is False
    assert runtime.stop_calls == 1


def test_pending_refusal_is_not_a_close_failure(tmp_path):
    """pending refusal 不得被误判成 close-failed；终态后仍能正常关闭。"""

    provider = _make_provider(
        tmp_path,
        benchmark_name="longmemeval",
        runtime_factory=_StopCountingRuntime,
    )
    runtime = provider._require_runtime()
    namespace = provider._namespace("run1_conv1")
    item_id = _pending_task(provider, runtime)

    with pytest.raises(ConfigurationError, match="拒绝静默关闭"):
        provider.cleanup()

    assert runtime.close_failed is False
    assert runtime.stop_calls == 0

    runtime.tracker.task_started(task_id=item_id, user_id=namespace)
    runtime.tracker.task_completed(item_id, namespace)
    provider.cleanup()

    assert runtime.closed is True
    assert runtime.close_failed is False
    assert runtime.stop_calls == 1


def test_successful_stop_keeps_idempotent_cleanup_unchanged(tmp_path):
    """stop 正常成功时，重复 cleanup 仍幂等且 stop 恰好一次（行为不变）。"""

    provider = _make_provider(
        tmp_path,
        benchmark_name="longmemeval",
        runtime_factory=_StopCountingRuntime,
    )
    runtime = provider._require_runtime()

    provider.cleanup()
    provider.cleanup()
    provider.cleanup()

    assert runtime.closed is True
    assert runtime.close_failed is False
    assert runtime.stop_calls == 1
    assert provider._runtime_owner._runtime is None


def test_real_runtime_stop_failure_is_permanently_fail_closed():
    """穿过真实 MemosRuntime.close：stop 失败后永久 fail-closed，绝不二次 stop。"""

    from memory_benchmark.methods.memos_adapter import MemosRuntime

    runtime = object.__new__(MemosRuntime)
    runtime._closed = False
    runtime._close_failed = False
    runtime._close_error = None
    runtime.tracker = MemosLocalTaskTracker()
    stop_calls: list[int] = []

    def _boom():
        """模拟 dispatcher.shutdown() 阶段失败。"""
        stop_calls.append(1)
        raise RuntimeError("dispatcher shutdown exploded")

    runtime.scheduler = types.SimpleNamespace(stop=_boom)

    with pytest.raises(RuntimeError, match="dispatcher shutdown exploded") as first:
        runtime.close()
    assert runtime.closed is False
    assert runtime.close_failed is True
    assert stop_calls == [1]

    for _ in range(2):
        with pytest.raises(ConfigurationError, match="permanently unusable") as again:
            runtime.close()
        assert again.value.__cause__ is first.value
        # upstream stop() 第二次会因 _running=False 直接返回，因此绝不能再调用。
        assert stop_calls == [1]
        assert runtime.closed is False
