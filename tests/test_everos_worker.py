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
    _ObservedEmbeddingsEndpoint,
    _ObservedLLMClient,
    _ObservedRerankProvider,
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


def test_observation_wrappers_record_only_successful_exact_usage() -> None:
    """LLM/embedding/rerank wrapper 逐字透传并只记录成功调用。"""

    engine = _WorkerEngine()
    engine.begin_observations()
    llm_response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=3)
    )
    embedding_response = SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=7)
    )
    rerank_response = [SimpleNamespace(index=0, score=0.9)]

    class _LLM:
        """返回固定 ChatResponse。"""

        model = "fake-model"

        async def chat(self, *args: Any, **kwargs: Any) -> Any:
            """确认参数透传。"""

            assert args == ("prompt",)
            assert kwargs == {"temperature": 0}
            return llm_response

    class _Embedding:
        """返回固定 embedding response。"""

        async def create(self, *args: Any, **kwargs: Any) -> Any:
            """确认输入透传。"""

            assert args == ()
            assert kwargs == {"input": ["a", "b"]}
            return embedding_response

    class _Rerank:
        """返回固定 rerank response。"""

        model = "fake-reranker"

        async def rerank(self, *args: Any, **kwargs: Any) -> Any:
            """确认 query/documents/instruction 逐字透传。"""

            assert args == ("query", ["doc-a", "doc-b"])
            assert kwargs == {"instruction": "rank passages"}
            return rerank_response

    observed_llm = _ObservedLLMClient(_LLM(), engine)
    observed_embedding = _ObservedEmbeddingsEndpoint(_Embedding(), engine)
    observed_rerank = _ObservedRerankProvider(_Rerank(), engine)

    assert asyncio.run(observed_llm.chat("prompt", temperature=0)) is llm_response
    assert observed_llm.model == "fake-model"
    assert (
        asyncio.run(observed_embedding.create(input=["a", "b"]))
        is embedding_response
    )
    assert (
        asyncio.run(
            observed_rerank.rerank(
                "query",
                ["doc-a", "doc-b"],
                instruction="rank passages",
            )
        )
        is rerank_response
    )
    assert observed_rerank.model == "fake-reranker"
    llm, embedding, rerank = engine.finish_observations()
    assert llm == [{"input_tokens": 11, "output_tokens": 3}]
    assert embedding[0]["input_tokens"] == 7
    assert embedding[0]["text_count"] == 2
    assert embedding[0]["latency_ms"] >= 0
    assert rerank[0]["document_count"] == 2
    assert rerank[0]["latency_ms"] >= 0


def test_install_observers_wraps_rerank_capability_before_search_manager_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """observer 必须在 lazy SearchManager 前原子安装到三类 product 单例。"""

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
    embedding_endpoint = SimpleNamespace(name="embeddings")
    embedding_provider = SimpleNamespace(
        _client=SimpleNamespace(embeddings=embedding_endpoint)
    )
    rerank_provider = SimpleNamespace(model="reranker")
    embedding_accessor = ModuleType("everos.component.embedding.accessor")
    embedding_accessor.get_embedding_capability = (  # type: ignore[attr-defined]
        lambda: _Capability(provider=embedding_provider)
    )
    llm_accessor = ModuleType("everos.component.llm.client")
    llm_accessor._llm_client = llm_client  # type: ignore[attr-defined]
    rerank_accessor = ModuleType("everos.component.rerank.accessor")
    rerank_accessor._capability = _Capability(  # type: ignore[attr-defined]
        provider=rerank_provider
    )
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
    assert isinstance(
        embedding_provider._client.embeddings,
        _ObservedEmbeddingsEndpoint,
    )
    assert isinstance(
        rerank_accessor._capability.provider,  # type: ignore[attr-defined]
        _ObservedRerankProvider,
    )

    llm_accessor._llm_client = llm_client  # type: ignore[attr-defined]
    embedding_provider._client.embeddings = embedding_endpoint
    rerank_accessor._capability = _Capability(  # type: ignore[attr-defined]
        provider=rerank_provider
    )
    search_module._manager = object()  # type: ignore[attr-defined]
    with pytest.raises(RuntimeError, match="initialized before rerank observer"):
        _WorkerEngine()._install_observers()
    assert llm_accessor._llm_client is llm_client  # type: ignore[attr-defined]
    assert embedding_provider._client.embeddings is embedding_endpoint
    assert rerank_accessor._capability.provider is rerank_provider  # type: ignore[attr-defined]


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

    with pytest.raises(RuntimeError, match="original startup failure"):
        asyncio.run(
            engine.initialize(
                {
                    "adapter_version": EVEROS_ADAPTER_VERSION,
                    "add_batch_size": 25,
                    "app_id": "memorybenchmark",
                    "drain_timeout_seconds": 20.0,
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
