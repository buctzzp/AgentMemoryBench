"""测试 EverOS 独立 worker 的协议、稳定合并与 exact completion。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

from memory_benchmark.methods.everos_worker import (
    EVEROS_ADAPTER_VERSION,
    _LocalSentenceTransformerEmbeddingProvider,
    _ObservedLLMClient,
    _WorkerEngine,
)


pytestmark = pytest.mark.unit


class _RunStatus(Enum):
    """模拟 EverOS RunStatus 的字符串值。"""

    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    CRASHED = "crashed"


@dataclass
class _Run:
    """最小 OME run record。"""

    event_id: str | None
    run_id: str
    status: _RunStatus


class _Registry:
    """返回一个注册 strategy。"""

    @staticmethod
    def all() -> list[Any]:
        """返回命名元数据。"""

        return [SimpleNamespace(name="extract_atomic_facts")]


class _Engine:
    """模拟 OME idle 与 run history。"""

    def __init__(self, rows: list[_Run], *, idle: bool = True) -> None:
        """保存 rows。"""

        self._registry = _Registry()
        self.rows = rows
        self.idle = idle
        self.wait_calls = 0

    async def wait_idle(self, *, timeout: float) -> bool:
        """记录 exact idle wait。"""

        assert timeout == 20.0
        self.wait_calls += 1
        return self.idle

    async def list_runs(self, name: str, *, limit: int) -> list[_Run]:
        """返回完整 strategy history。"""

        assert name == "extract_atomic_facts"
        assert limit == 100_000
        return list(self.rows)


class _Cascade:
    """模拟 Cascade sync/health。"""

    def __init__(
        self,
        processed: list[int],
        *,
        healthy: bool = True,
        pending: int = 0,
        failed_retryable: int = 0,
        failed_permanent: int = 0,
    ) -> None:
        """保存同步序列与 health。"""

        self.processed = list(processed)
        self.healthy = healthy
        self.pending = pending
        self.failed_retryable = failed_retryable
        self.failed_permanent = failed_permanent
        self.calls = 0

    async def sync_once(self) -> int:
        """按序返回处理量。"""

        self.calls += 1
        if self.processed:
            return self.processed.pop(0)
        return 0

    async def health(self) -> Any:
        """返回 worker 使用的 readiness 字段。"""

        return SimpleNamespace(
            healthy=self.healthy,
            reasons=[] if self.healthy else ["drain loop stopped"],
            pending=self.pending,
            failed_retryable=self.failed_retryable,
            failed_permanent=self.failed_permanent,
        )


def _install_run_status_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 worker 的 lazy EverOS import 替换成最小 enum module。"""

    module = ModuleType("everos.infra.ome.records")
    module.RunStatus = _RunStatus  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "everos.infra.ome.records", module)


def _ready_engine(ome: _Engine, cascade: _Cascade) -> _WorkerEngine:
    """构造无需真实 lifespan 的 ready worker engine。"""

    engine = _WorkerEngine()
    engine.app = SimpleNamespace(
        state=SimpleNamespace(lifespan_data={"ome": ome, "cascade": cascade})
    )
    engine.lifespan = SimpleNamespace()
    engine.config = {
        "add_batch_size": 25,
        "app_id": "memorybenchmark",
        "drain_timeout_seconds": 20.0,
        "project_id": "phase1",
        "search_method": "hybrid",
    }
    return engine


def test_worker_message_contract_only_allows_one_first_empty_user_anchor() -> None:
    """结构锚是唯一合法空消息，其他空白/role/shape 一律 fail-fast。"""

    messages = [
        {
            "content": "",
            "role": "user",
            "sender_id": "owner",
            "sender_name": None,
            "timestamp": 1,
        },
        {
            "content": "assistant fact",
            "role": "assistant",
            "sender_id": "assistant",
            "sender_name": "assistant",
            "timestamp": 2,
        },
    ]

    assert _WorkerEngine._validate_messages(messages) == messages
    with pytest.raises(ValueError, match="only the first structural"):
        _WorkerEngine._validate_messages([messages[1], messages[0]])
    with pytest.raises(ValueError, match="unsupported"):
        _WorkerEngine._validate_messages(
            [{**messages[1], "role": "system"}]
        )
    with pytest.raises(ValueError, match="invalid shape"):
        _WorkerEngine._validate_messages(
            [{**messages[1], "private_gold": "must not enter"}]
        )


def test_exact_drain_accepts_recovered_attempt_and_requires_two_stable_zero_passes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """同 event 的 failed→success 可恢复；Cascade 必须 settle 到双零。"""

    _install_run_status_module(monkeypatch)
    ome = _Engine(
        [
            _Run("event-1", "run-1", _RunStatus.FAILED),
            _Run("event-1", "run-2", _RunStatus.SUCCESS),
        ]
    )
    cascade = _Cascade([3, 0, 0])
    engine = _ready_engine(ome, cascade)

    result = asyncio.run(engine._exact_drain())

    assert result == {
        "cascade_processed": 3,
        "cascade_stable_zero_passes": 2,
        "ome_run_count_before_cascade": 2,
        "ome_run_count_after_cascade": 2,
    }
    assert ome.wait_calls == 2
    assert cascade.calls == 3


def test_exact_drain_yields_for_product_background_processing_until_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已被后台 worker claim 的行须获调度机会，不能被固定紧循环误判超时。"""

    _install_run_status_module(monkeypatch)

    class _BackgroundCascade(_Cascade):
        """首轮把行交给后台 task，只有 event-loop yield 后才完成。"""

        def __init__(self) -> None:
            """从一个 processing 行开始。"""

            super().__init__([], pending=1)
            self.release_task: asyncio.Task[None] | None = None

        async def sync_once(self) -> int:
            """模拟 foreground drain 看见行已被 background claim。"""

            self.calls += 1
            if self.release_task is None:

                async def _release() -> None:
                    """等调用者显式 yield 后提交后台完成。"""

                    await asyncio.sleep(0)
                    self.pending = 0

                self.release_task = asyncio.create_task(_release())
            return 0

    cascade = _BackgroundCascade()
    engine = _ready_engine(_Engine([]), cascade)

    result = asyncio.run(engine._exact_drain())

    assert result["cascade_stable_zero_passes"] == 2
    assert cascade.pending == 0
    assert cascade.calls >= 3


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([_Run("e", "r", _RunStatus.RUNNING)], "remains running"),
        ([_Run("e", "r", _RunStatus.DEAD_LETTER)], "dead_letter"),
        ([_Run("e", "r", _RunStatus.CRASHED)], "crashed"),
        ([_Run("e", "r", _RunStatus.FAILED)], "without success"),
    ],
)
def test_exact_drain_rejects_nonterminal_or_unrecovered_ome_chain(
    monkeypatch: pytest.MonkeyPatch,
    rows: list[_Run],
    message: str,
) -> None:
    """running/dead-letter/crash/孤立失败都不得冒充已完成。"""

    _install_run_status_module(monkeypatch)
    engine = _ready_engine(_Engine(rows), _Cascade([0, 0]))

    with pytest.raises(RuntimeError, match=message):
        asyncio.run(engine._exact_drain())


@pytest.mark.parametrize(
    ("cascade", "message"),
    [
        (_Cascade([0], healthy=False), "operationally unhealthy"),
        (_Cascade([0], failed_retryable=1), "retryable failures"),
        (_Cascade([0], failed_permanent=1), "permanent failures"),
    ],
)
def test_exact_drain_rejects_cascade_health_failures(
    monkeypatch: pytest.MonkeyPatch,
    cascade: _Cascade,
    message: str,
) -> None:
    """Cascade operational 与 data-quality failure 都必须向父进程可见。"""

    _install_run_status_module(monkeypatch)
    engine = _ready_engine(_Engine([]), cascade)

    with pytest.raises(RuntimeError, match=message):
        asyncio.run(engine._exact_drain())


def test_multi_owner_search_merge_is_score_first_stable_and_deduplicated() -> None:
    """LoCoMo owner fan-out 按 score→owner→product-rank 合并且去重复 Episode。"""

    engine = _ready_engine(_Engine([]), _Cascade([0, 0]))

    async def _search_owner(
        owner_id: str,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """返回两个 owner 的有序结果。"""

        assert query == "where"
        assert top_k == 3
        shared = {
            "id": f"{owner_id}-shared",
            "session_id": "s1",
            "timestamp": "2024-01-01T00:00:00Z",
            "episode": "shared",
            "score": 0.8,
        }
        if owner_id == "owner-a":
            return [
                {**shared, "id": "a-high", "episode": "high", "score": 0.9},
                shared,
            ]
        return [
            {**shared, "id": "b-shared"},
            {**shared, "id": "b-low", "episode": "low", "score": 0.7},
        ]

    engine._search_owner = _search_owner  # type: ignore[method-assign]

    result = asyncio.run(
        engine.retrieve(
            {"owner_ids": ["owner-a", "owner-b"], "query": "where", "top_k": 3}
        )
    )

    assert [item["episode"] for item in result["items"]] == [
        "high",
        "shared",
        "low",
    ]
    assert [item["owner_merge_index"] for item in result["items"]] == [0, 0, 1]
    assert result["llm_observations"] == []
    assert result["embedding_observations"] == []
    assert result["rerank_observations"] == []


def test_observation_wrappers_record_api_llm_and_local_embedding_usage(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """LLM exact usage 与本地 tokenizer/墙钟 embedding 观测必须同时成立。"""

    engine = _WorkerEngine()
    engine.begin_observations()
    llm_response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=3)
    )

    class _LLM:
        """返回固定 ChatResponse。"""

        model = "fake-model"

        async def chat(self, *args: Any, **kwargs: Any) -> Any:
            """确认参数透传。"""

            assert args == ("prompt",)
            assert kwargs == {"temperature": 0}
            return llm_response

    class _Encoded(list):
        """模拟 numpy array 的 tolist。"""

        def tolist(self) -> list[list[float]]:
            """返回二维向量。"""

            return list(self)

    class _Tokenizer:
        """按文本长度返回可预测 token id。"""

        @staticmethod
        def encode(text: str, **kwargs: Any) -> list[int]:
            """验证截断参数并返回稳定 token 数。"""

            assert kwargs == {
                "add_special_tokens": True,
                "truncation": True,
                "max_length": 8,
            }
            return list(range(len(text) + 1))

    class _Model:
        """模拟本地 3 维 SentenceTransformer。"""

        tokenizer = _Tokenizer()
        max_seq_length = 8

        @staticmethod
        def get_embedding_dimension() -> int:
            """返回固定维度。"""

            return 3

        @staticmethod
        def encode(texts: list[str], **kwargs: Any) -> _Encoded:
            """验证 production encode 参数并返回稳定向量。"""

            assert kwargs == {
                "convert_to_numpy": True,
                "show_progress_bar": False,
            }
            return _Encoded([[1.0, 0.0, 0.0] for _ in texts])

    sentence_transformers = ModuleType("sentence_transformers")
    sentence_transformers.SentenceTransformer = (  # type: ignore[attr-defined]
        lambda *args, **kwargs: _Model()
    )
    monkeypatch.setitem(sys.modules, "sentence_transformers", sentence_transformers)
    model_path = tmp_path / "model"
    model_path.mkdir()

    observed_llm = _ObservedLLMClient(_LLM(), engine)
    observed_embedding = _LocalSentenceTransformerEmbeddingProvider(
        model_path=model_path,
        dimension=3,
        engine=engine,
    )

    assert asyncio.run(observed_llm.chat("prompt", temperature=0)) is llm_response
    assert observed_llm.model == "fake-model"
    assert asyncio.run(observed_embedding.embed_batch(["a", "bb"])) == [
        [1.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
    ]
    llm, embedding, rerank = engine.finish_observations()
    assert llm == [{"input_tokens": 11, "output_tokens": 3}]
    assert embedding[0]["input_tokens"] == 5
    assert embedding[0]["text_count"] == 2
    assert embedding[0]["latency_ms"] >= 0
    assert rerank == []


def test_everos_observed_llm_uses_low_reasoning_for_ox(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EverOS 产品 client 在 ox runtime 上显式注入 low reasoning。"""

    engine = _WorkerEngine()
    engine.begin_observations()
    calls: list[dict[str, Any]] = []

    class _LLM:
        """记录最终 kwargs 的异步 fake。"""

        async def chat(self, *args: Any, **kwargs: Any) -> Any:
            """返回带 exact usage 的稳定响应。"""

            assert args == ("prompt",)
            calls.append(dict(kwargs))
            return SimpleNamespace(
                usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2)
            )

    monkeypatch.setenv("EVEROS_LLM__MODEL", "ox-alpha-free")
    asyncio.run(_ObservedLLMClient(_LLM(), engine).chat("prompt", temperature=0))

    assert calls == [{"temperature": 0, "reasoning_effort": "low"}]
    llm, _embedding, _rerank = engine.finish_observations()
    assert llm == [{"input_tokens": 5, "output_tokens": 2}]


def test_install_controlled_embedding_provider_uses_upstream_capability_seam(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """本地 MiniLM 必须经 upstream capability 注入，且不允许二次初始化。"""

    @dataclass(frozen=True)
    class _Capability:
        """模拟 upstream frozen capability。"""

        provider: Any

    class _Tokenizer:
        """提供最小 tokenizer 契约。"""

        @staticmethod
        def encode(text: str, **kwargs: Any) -> list[int]:
            """返回稳定 token id。"""

            return [1]

    class _Model:
        """提供最小 SentenceTransformer 契约。"""

        tokenizer = _Tokenizer()
        max_seq_length = 8

        @staticmethod
        def get_embedding_dimension() -> int:
            """返回受控维度。"""

            return 3

    sentence_transformers = ModuleType("sentence_transformers")
    sentence_transformers.SentenceTransformer = (  # type: ignore[attr-defined]
        lambda *args, **kwargs: _Model()
    )
    everos_package = ModuleType("everos")
    component_package = ModuleType("everos.component")
    embedding_package = ModuleType("everos.component.embedding")
    for package in (everos_package, component_package, embedding_package):
        package.__path__ = []  # type: ignore[attr-defined]
    accessor = ModuleType("everos.component.embedding.accessor")
    accessor._capability = None  # type: ignore[attr-defined]
    capability = ModuleType("everos.component.embedding.capability")
    capability.EmbeddingCapability = _Capability  # type: ignore[attr-defined]
    everos_package.component = component_package  # type: ignore[attr-defined]
    component_package.embedding = embedding_package  # type: ignore[attr-defined]
    embedding_package.accessor = accessor  # type: ignore[attr-defined]
    embedding_package.capability = capability  # type: ignore[attr-defined]
    for module in (
        sentence_transformers,
        everos_package,
        component_package,
        embedding_package,
        accessor,
        capability,
    ):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    model_path = tmp_path / "model"
    model_path.mkdir()
    monkeypatch.setenv("EVEROS_LOCAL_EMBEDDING_MODEL_PATH", str(model_path))
    engine = _WorkerEngine()
    engine.config = {"embedding_dimension": 3}

    engine._install_controlled_embedding_provider()

    assert isinstance(
        accessor._capability.provider,  # type: ignore[attr-defined]
        _LocalSentenceTransformerEmbeddingProvider,
    )
    with pytest.raises(RuntimeError, match="initialized before controlled provider"):
        engine._install_controlled_embedding_provider()


def test_install_observers_accepts_controlled_provider_before_search_manager_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """observer 只包装 LLM，并锁本地 embedder/rerank-disabled/search-manager 时序。"""

    @dataclass(frozen=True)
    class _Capability:
        """模拟 embedding/rerank frozen capability。"""

        provider: Any

    everos_module = ModuleType("everos")
    component_module = ModuleType("everos.component")
    embedding_package = ModuleType("everos.component.embedding")
    llm_package = ModuleType("everos.component.llm")
    rerank_package = ModuleType("everos.component.rerank")
    service_package = ModuleType("everos.service")
    for package in (
        everos_module,
        component_module,
        embedding_package,
        llm_package,
        rerank_package,
        service_package,
    ):
        package.__path__ = []  # type: ignore[attr-defined]

    llm_client = SimpleNamespace(model="llm")
    embedding_provider = object.__new__(
        _LocalSentenceTransformerEmbeddingProvider
    )
    embedding_accessor = ModuleType("everos.component.embedding.accessor")
    embedding_accessor.get_embedding_capability = (  # type: ignore[attr-defined]
        lambda: _Capability(provider=embedding_provider)
    )
    llm_accessor = ModuleType("everos.component.llm.client")
    llm_accessor._llm_client = llm_client  # type: ignore[attr-defined]
    rerank_accessor = ModuleType("everos.component.rerank.accessor")
    rerank_accessor._capability = _Capability(provider=None)  # type: ignore[attr-defined]
    rerank_accessor.get_rerank_capability = (  # type: ignore[attr-defined]
        lambda: rerank_accessor._capability  # type: ignore[attr-defined]
    )
    search_module = ModuleType("everos.service.search")
    search_module._manager = None  # type: ignore[attr-defined]

    everos_module.component = component_module  # type: ignore[attr-defined]
    everos_module.service = service_package  # type: ignore[attr-defined]
    component_module.embedding = embedding_package  # type: ignore[attr-defined]
    component_module.llm = llm_package  # type: ignore[attr-defined]
    component_module.rerank = rerank_package  # type: ignore[attr-defined]
    embedding_package.accessor = embedding_accessor  # type: ignore[attr-defined]
    llm_package.client = llm_accessor  # type: ignore[attr-defined]
    rerank_package.accessor = rerank_accessor  # type: ignore[attr-defined]
    service_package.search = search_module  # type: ignore[attr-defined]
    for module in (
        everos_module,
        component_module,
        embedding_package,
        embedding_accessor,
        llm_package,
        llm_accessor,
        rerank_package,
        rerank_accessor,
        service_package,
        search_module,
    ):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    engine = _WorkerEngine()
    engine._install_observers()

    assert isinstance(llm_accessor._llm_client, _ObservedLLMClient)  # type: ignore[attr-defined]
    assert embedding_accessor.get_embedding_capability().provider is embedding_provider  # type: ignore[attr-defined]
    assert rerank_accessor._capability.provider is None  # type: ignore[attr-defined]

    llm_accessor._llm_client = llm_client  # type: ignore[attr-defined]
    search_module._manager = object()  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="initialized before rerank observer"):
        _WorkerEngine()._install_observers()
    assert llm_accessor._llm_client is llm_client  # type: ignore[attr-defined]
    assert rerank_accessor._capability.provider is None  # type: ignore[attr-defined]


def test_install_observers_rejects_ambient_reranker_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """controlled 主轨若意外装入 reranker，必须在搜索 manager 构造前失败。"""

    @dataclass(frozen=True)
    class _Capability:
        """模拟可空 capability。"""

        provider: Any

    module_names = (
        "everos",
        "everos.component",
        "everos.component.embedding",
        "everos.component.llm",
        "everos.component.rerank",
        "everos.service",
    )
    packages = {name: ModuleType(name) for name in module_names}
    for package in packages.values():
        package.__path__ = []  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, package.__name__, package)
    embedding_accessor = ModuleType("everos.component.embedding.accessor")
    embedding_provider = object.__new__(
        _LocalSentenceTransformerEmbeddingProvider
    )
    embedding_accessor.get_embedding_capability = (  # type: ignore[attr-defined]
        lambda: _Capability(provider=embedding_provider)
    )
    llm_accessor = ModuleType("everos.component.llm.client")
    llm_accessor._llm_client = SimpleNamespace(model="llm")  # type: ignore[attr-defined]
    rerank_accessor = ModuleType("everos.component.rerank.accessor")
    rerank_accessor._capability = _Capability(provider=object())  # type: ignore[attr-defined]
    rerank_accessor.get_rerank_capability = (  # type: ignore[attr-defined]
        lambda: rerank_accessor._capability  # type: ignore[attr-defined]
    )
    search_module = ModuleType("everos.service.search")
    search_module._manager = None  # type: ignore[attr-defined]
    for module in (
        embedding_accessor,
        llm_accessor,
        rerank_accessor,
        search_module,
    ):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    engine = _WorkerEngine()
    with pytest.raises(RuntimeError, match="rerank capability"):
        engine._install_observers()

    assert not isinstance(llm_accessor._llm_client, _ObservedLLMClient)  # type: ignore[attr-defined]


def test_initialize_enter_failure_preserves_original_error_and_never_calls_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """lifespan 进入失败不得被错误的 __aexit__ 二次异常遮蔽。"""

    root = tmp_path / "product-root"
    root.mkdir()
    marker = {"identity": "test"}
    (root / ".memory-benchmark-everos-root.json").write_text(
        json.dumps(marker), encoding="utf-8"
    )
    monkeypatch.setenv("EVEROS_ROOT", str(root))

    class _Lifespan:
        """进入失败且退出若被误调会抛另一错误。"""

        exit_calls = 0

        async def __aenter__(self) -> None:
            """抛承重原始异常。"""

            raise RuntimeError("original startup failure")

        async def __aexit__(self, *args: Any) -> None:
            """不应执行。"""

            type(self).exit_calls += 1
            raise RuntimeError("masked cleanup failure")

    lifespan = _Lifespan()
    app = SimpleNamespace(
        router=SimpleNamespace(lifespan_context=lambda _: lifespan)
    )
    module = ModuleType("everos.entrypoints.api.app")
    module.create_app = lambda: app  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "everos.entrypoints.api.app", module)
    engine = _WorkerEngine()
    monkeypatch.setattr(
        engine,
        "_install_controlled_embedding_provider",
        lambda: None,
    )

    with pytest.raises(RuntimeError, match="original startup failure"):
        asyncio.run(
            engine.initialize(
                {
                    "adapter_version": EVEROS_ADAPTER_VERSION,
                    "add_batch_size": 25,
                    "app_id": "memorybenchmark",
                    "drain_timeout_seconds": 20.0,
                    "embedding_dimension": 384,
                    "embedding_provider": "sentence-transformers-local",
                    "project_id": "phase1",
                    "root_marker": marker,
                    "search_method": "hybrid",
                }
            )
        )
    assert _Lifespan.exit_calls == 0
    assert engine.app is None
    assert engine.lifespan is None


def test_ingest_session_uses_typed_add_batches_flush_drain_and_public_get(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 worker 调用图须为 typed batch25→flush→drain→session get。"""

    _install_run_status_module(monkeypatch)
    engine = _ready_engine(_Engine([]), _Cascade([0, 0]))
    calls: list[tuple[dict[str, Any], bool]] = []

    class _MemorizeAddRequest:
        """记录 typed add DTO 构造参数。"""

        def __init__(self, **kwargs: Any) -> None:
            """保存原始字段。"""

            self.kwargs = kwargs

        def model_dump(self, *, mode: str) -> dict[str, Any]:
            """模拟 Pydantic 的 python dump。"""

            assert mode == "python"
            return dict(self.kwargs)

    route_module = ModuleType("everos.entrypoints.api.routes.memorize")
    route_module.MemorizeAddRequest = _MemorizeAddRequest  # type: ignore[attr-defined]
    service_module = ModuleType("everos.service")

    async def _memorize(payload: dict[str, Any], *, is_final: bool = False) -> Any:
        """记录 product service payload。"""

        calls.append((dict(payload), is_final))
        return SimpleNamespace(status="extracted")

    service_module.memorize = _memorize  # type: ignore[attr-defined]
    monkeypatch.setitem(
        sys.modules,
        "everos.entrypoints.api.routes.memorize",
        route_module,
    )
    monkeypatch.setitem(sys.modules, "everos.service", service_module)

    async def _session_items(
        owner_ids: list[str],
        session_id: str,
    ) -> list[dict[str, Any]]:
        """验证 flush 后的 public-get scope。"""

        assert owner_ids == ["owner"]
        assert session_id == "session-1"
        return []

    engine._get_session_items = _session_items  # type: ignore[method-assign]
    messages = [
        {
            "content": f"message-{index}",
            "role": "user" if index % 2 == 0 else "assistant",
            "sender_id": "owner" if index % 2 == 0 else "assistant",
            "sender_name": "user" if index % 2 == 0 else "assistant",
            "timestamp": index + 1,
        }
        for index in range(26)
    ]

    result = asyncio.run(
        engine.ingest_session(
            {
                "messages": messages,
                "operation_id": "operation-1",
                "owner_ids": ["owner"],
                "session_id": "session-1",
            }
        )
    )

    assert [len(payload["messages"]) for payload, _ in calls] == [25, 1, 0]
    assert [is_final for _, is_final in calls] == [False, False, True]
    assert all(payload["session_id"] == "session-1" for payload, _ in calls)
    assert result["operation_id"] == "operation-1"
    assert result["exact_drain"] is True
    assert result["session_items"] == []


def test_search_and_get_construct_exact_public_typed_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """search/get 必须使用公开 DTO 字段，不偷换 direct repository 查询。"""

    engine = _ready_engine(_Engine([]), _Cascade([0, 0]))
    search_requests: list[dict[str, Any]] = []
    get_requests: list[dict[str, Any]] = []

    class _SearchRequest:
        """记录 public SearchRequest。"""

        def __init__(self, **kwargs: Any) -> None:
            """保存参数。"""

            search_requests.append(dict(kwargs))

    class _GetRequest:
        """记录 public GetRequest。"""

        def __init__(self, **kwargs: Any) -> None:
            """保存参数。"""

            get_requests.append(dict(kwargs))

    search_module = ModuleType("everos.memory.search")
    search_module.SearchRequest = _SearchRequest  # type: ignore[attr-defined]
    get_module = ModuleType("everos.memory.get")
    get_module.GetRequest = _GetRequest  # type: ignore[attr-defined]
    service_module = ModuleType("everos.service")

    async def _search(request: Any) -> Any:
        """返回一个公开 Episode。"""

        del request
        return SimpleNamespace(
            model_dump=lambda **_: {
                "data": {
                    "episodes": [
                        {
                            "id": "episode-1",
                            "episode": "memory",
                            "score": 0.8,
                        }
                    ]
                }
            }
        )

    async def _get(request: Any) -> Any:
        """返回一页空 public get。"""

        del request
        return SimpleNamespace(
            model_dump=lambda **_: {
                "data": {
                    "episodes": [],
                    "count": 0,
                    "total_count": 0,
                }
            }
        )

    service_module.search = _search  # type: ignore[attr-defined]
    service_module.get = _get  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "everos.memory.search", search_module)
    monkeypatch.setitem(sys.modules, "everos.memory.get", get_module)
    monkeypatch.setitem(sys.modules, "everos.service", service_module)

    episodes = asyncio.run(engine._search_owner("owner", "where", 7))
    listed = asyncio.run(engine._get_session_items(["owner"], "session-1"))

    assert episodes[0]["id"] == "episode-1"
    assert listed == []
    assert search_requests == [
        {
            "user_id": "owner",
            "app_id": "memorybenchmark",
            "project_id": "phase1",
            "query": "where",
            "method": "hybrid",
            "top_k": 7,
            "include_profile": False,
            "enable_llm_rerank": False,
            "filters": None,
        }
    ]
    assert get_requests == [
        {
            "user_id": "owner",
            "app_id": "memorybenchmark",
            "project_id": "phase1",
            "memory_type": "episode",
            "page": 1,
            "page_size": 100,
            "sort_by": "timestamp",
            "sort_order": "asc",
            "filters": {"session_id": "session-1"},
        }
    ]
