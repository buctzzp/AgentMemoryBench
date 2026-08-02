"""测试 LangMem 独立 worker 的原子状态、重试与产品排序契约。"""

from __future__ import annotations

import asyncio
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from memory_benchmark.methods import langmem_worker as worker_module
from memory_benchmark.methods.langmem_worker import (
    _WorkerEngine,
    _atomic_write_json,
    _empty_state,
    _input_digest,
    _usage_from_llm_result,
    _validate_state,
)


pytestmark = pytest.mark.unit
NAMESPACE_ID = "a" * 32


class _FakeStore:
    """按 namespace 保留插入顺序的最小 async BaseStore 替身。"""

    def __init__(self, engine: _WorkerEngine) -> None:
        """保存 engine，并初始化可注入失败点。"""

        self.engine = engine
        self.rows: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
        self.fail_delete_once = False

    async def aput(
        self,
        namespace: tuple[str, str],
        key: str,
        value: dict[str, Any],
    ) -> None:
        """模拟一次带 embedding 的 product put。"""

        self.engine._record_embedding_observation(
            {"input_tokens": 3, "latency_ms": 0.5, "text_count": 1}
        )
        self.rows.setdefault(namespace, {})[key] = deepcopy(value)

    async def adelete(self, namespace: tuple[str, str], key: str) -> None:
        """删除 key；可在一次调用上注入失败。"""

        if self.fail_delete_once:
            self.fail_delete_once = False
            raise RuntimeError("injected delete failure")
        self.rows.setdefault(namespace, {}).pop(key, None)

    async def asearch(
        self,
        namespace: tuple[str, str],
        *,
        query: str | None,
        limit: int,
    ) -> list[Any]:
        """query=None 时按当前插入顺序返回 exact key/value。"""

        del query
        return [
            SimpleNamespace(key=key, value=deepcopy(value), score=None)
            for key, value in list(self.rows.get(namespace, {}).items())[:limit]
        ]


class _FakeManager:
    """模拟 LangMem manager 对 current memory 的 insert/update。"""

    def __init__(self, engine: _WorkerEngine, store: _FakeStore) -> None:
        """保存依赖与调用账。"""

        self.engine = engine
        self.store = store
        self.calls = 0
        self.fail_after_write = False
        self.search_items: list[Any] = []

    async def ainvoke(
        self,
        payload: dict[str, Any],
        *,
        config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """写一条 evolved memory，并产生精确 usage。"""

        self.calls += 1
        namespace_id = config["configurable"]["langgraph_user_id"]
        messages = payload["messages"]
        content = " | ".join(message["content"] for message in messages)
        self.engine._record_llm_observation(
            {"input_tokens": 11, "output_tokens": 4}
        )
        await self.store.aput(
            ("memories", namespace_id),
            "memory-1",
            {"kind": "Memory", "content": {"content": content}},
        )
        if self.fail_after_write:
            raise RuntimeError("injected manager failure")
        return [
            {
                "namespace": ("memories", namespace_id),
                "key": "memory-1",
                "value": {"kind": "Memory", "content": {"content": content}},
            }
        ]

    async def asearch(
        self,
        *,
        query: str,
        limit: int,
        config: dict[str, Any],
    ) -> list[Any]:
        """返回预设 product order，并记录 query embedding。"""

        del query, config
        self.engine._record_embedding_observation(
            {"input_tokens": 2, "latency_ms": 0.25, "text_count": 1}
        )
        return list(self.search_items[:limit])


def _engine(tmp_path: Path) -> tuple[_WorkerEngine, _FakeStore, _FakeManager]:
    """构造不导入第三方依赖的已就绪 worker engine。"""

    engine = _WorkerEngine()
    engine.config = {"max_steps": 1}
    engine.state_root = tmp_path
    store = _FakeStore(engine)
    manager = _FakeManager(engine, store)
    engine.store = store
    engine.manager = manager
    engine.embedding_model = object()
    engine.usage_callback = object()
    return engine, store, manager


def _ingest_payload(*, content: str = "Alice moved to Boston") -> dict[str, Any]:
    """构造稳定 session ingest 请求。"""

    return {
        "namespace_id": NAMESPACE_ID,
        "operation_id": "operation-1",
        "messages": [{"role": "user", "content": content}],
        "max_steps": 1,
    }


def test_langmem_worker_atomic_state_and_result_loss_retry(tmp_path: Path) -> None:
    """成功状态与 journal 同文件提交；同输入重试不再调用 manager。"""

    engine, store, manager = _engine(tmp_path)

    first = asyncio.run(engine.ingest(_ingest_payload()))
    second = asyncio.run(engine.ingest(_ingest_payload()))

    assert manager.calls == 1
    assert first["reused_operation"] is False
    assert second["reused_operation"] is True
    assert first["changed_memory_keys"] == ["memory-1"]
    assert first["llm_observations"] == [
        {"input_tokens": 11, "output_tokens": 4}
    ]
    assert first["embedding_observations"] == [
        {"input_tokens": 3, "latency_ms": 0.5, "text_count": 1}
    ]
    state = json.loads((tmp_path / f"{NAMESPACE_ID}.json").read_text())
    assert list(state["completed_operations"]) == ["operation-1"]
    assert state["entries"] == [
        {
            "key": "memory-1",
            "value": {
                "content": {"content": "Alice moved to Boston"},
                "kind": "Memory",
            },
        }
    ]
    assert list(store.rows[("memories", NAMESPACE_ID)]) == ["memory-1"]


def test_langmem_worker_rejects_same_operation_id_with_changed_input(
    tmp_path: Path,
) -> None:
    """operation id 相同但 payload 漂移时 fail-fast，不调用算法第二次。"""

    engine, _store, manager = _engine(tmp_path)
    asyncio.run(engine.ingest(_ingest_payload()))

    with pytest.raises(RuntimeError, match="different input"):
        asyncio.run(engine.ingest(_ingest_payload(content="different")))

    assert manager.calls == 1


def test_langmem_worker_manager_failure_rolls_back_store_and_state(
    tmp_path: Path,
) -> None:
    """manager 写后失败时恢复调用前 store，且不提交 operation journal。"""

    engine, store, manager = _engine(tmp_path)
    manager.fail_after_write = True

    with pytest.raises(RuntimeError, match="manager failure"):
        asyncio.run(engine.ingest(_ingest_payload()))

    assert store.rows[("memories", NAMESPACE_ID)] == {}
    assert not (tmp_path / f"{NAMESPACE_ID}.json").exists()
    assert engine._llm_observations is None
    assert engine._embedding_observations is None


def test_langmem_worker_persist_failure_rolls_back_product_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """原子文件提交失败不能留下只有 store、没有 journal 的半成功。"""

    engine, store, _manager = _engine(tmp_path)

    def _fail_write(_path: Path, _payload: Any) -> None:
        """注入持久化失败。"""

        raise OSError("injected persist failure")

    monkeypatch.setattr(worker_module, "_atomic_write_json", _fail_write)

    with pytest.raises(OSError, match="persist failure"):
        asyncio.run(engine.ingest(_ingest_payload()))

    assert store.rows[("memories", NAMESPACE_ID)] == {}
    assert not (tmp_path / f"{NAMESPACE_ID}.json").exists()


def test_langmem_worker_rehydrates_exact_entries_without_business_attribution(
    tmp_path: Path,
) -> None:
    """resume 恢复用公开 put 重建 vector，但开销不混入 ingest observation。"""

    state = _empty_state(NAMESPACE_ID)
    state["entries"] = [
        {
            "key": "old",
            "value": {"kind": "Memory", "content": {"content": "old fact"}},
        }
    ]
    _atomic_write_json(tmp_path / f"{NAMESPACE_ID}.json", state)
    engine, store, _manager = _engine(tmp_path)

    result = asyncio.run(engine.ingest(_ingest_payload()))

    assert result["rehydrated_entry_count"] == 1
    assert result["rehydration_embedding_calls"] == 1
    assert result["embedding_observations"] == [
        {"input_tokens": 3, "latency_ms": 0.5, "text_count": 1}
    ]
    assert list(store.rows[("memories", NAMESPACE_ID)]) == ["old", "memory-1"]


def test_langmem_worker_cleanup_tombstone_is_retryable(tmp_path: Path) -> None:
    """删除中断后 active 已移出，tombstone 保留并可精确重试。"""

    state = _empty_state(NAMESPACE_ID)
    state["entries"] = [
        {
            "key": "old",
            "value": {"kind": "Memory", "content": {"content": "old fact"}},
        }
    ]
    active = tmp_path / f"{NAMESPACE_ID}.json"
    tombstone = tmp_path / f"{NAMESPACE_ID}.cleanup.json"
    _atomic_write_json(active, state)
    engine, store, _manager = _engine(tmp_path)
    store.fail_delete_once = True

    with pytest.raises(RuntimeError, match="delete failure"):
        asyncio.run(engine.delete_namespace({"namespace_id": NAMESPACE_ID}))

    assert not active.exists()
    assert tombstone.is_file()
    result = asyncio.run(
        engine.delete_namespace({"namespace_id": NAMESPACE_ID})
    )
    assert result == {"deleted": True, "deleted_entry_count": 1}
    assert not active.exists()
    assert not tombstone.exists()
    assert store.rows[("memories", NAMESPACE_ID)] == {}


def test_langmem_worker_namespace_write_and_cleanup_never_cross_isolation(
    tmp_path: Path,
) -> None:
    """同 worker 的两个 namespace 写入分区，单空间 clean 不删除另一方。"""

    engine, store, _manager = _engine(tmp_path)
    other_namespace = "b" * 32
    asyncio.run(engine.ingest(_ingest_payload(content="namespace A")))
    asyncio.run(
        engine.ingest(
            {
                "namespace_id": other_namespace,
                "operation_id": "operation-2",
                "messages": [{"role": "assistant", "content": "namespace B"}],
                "max_steps": 1,
            }
        )
    )

    assert store.rows[("memories", NAMESPACE_ID)]["memory-1"]["content"] == {
        "content": "namespace A"
    }
    assert store.rows[("memories", other_namespace)]["memory-1"]["content"] == {
        "content": "namespace B"
    }

    asyncio.run(engine.delete_namespace({"namespace_id": NAMESPACE_ID}))

    assert store.rows[("memories", NAMESPACE_ID)] == {}
    assert store.rows[("memories", other_namespace)]["memory-1"]["content"] == {
        "content": "namespace B"
    }
    assert not (tmp_path / f"{NAMESPACE_ID}.json").exists()
    assert (tmp_path / f"{other_namespace}.json").is_file()


def test_langmem_worker_retrieve_preserves_product_order_score_and_zero_hit(
    tmp_path: Path,
) -> None:
    """worker 不重排 product asearch，score 原样保留，zero hit 仍是列表。"""

    engine, _store, manager = _engine(tmp_path)
    manager.search_items = [
        SimpleNamespace(
            key="m2",
            value=SimpleNamespace(
                model_dump=lambda **_kwargs: {"content": "second first"}
            ),
            score=0.9,
        ),
        SimpleNamespace(
            key="m1",
            value={"kind": "Memory", "content": {"content": "first second"}},
            score=0.4,
        ),
    ]

    result = asyncio.run(
        engine.retrieve({"namespace_id": NAMESPACE_ID, "query": "q", "limit": 5})
    )

    assert [item["key"] for item in result["items"]] == ["m2", "m1"]
    assert [item["score"] for item in result["items"]] == [0.9, 0.4]
    assert result["embedding_observations"] == [
        {"input_tokens": 2, "latency_ms": 0.25, "text_count": 1}
    ]
    manager.search_items = []
    zero = asyncio.run(
        engine.retrieve({"namespace_id": NAMESPACE_ID, "query": "q", "limit": 5})
    )
    assert zero["items"] == []


def test_langmem_worker_state_validation_rejects_adapter_and_digest_drift() -> None:
    """resume 文件的 adapter/version/input digest 不能宽松接受。"""

    state = _empty_state(NAMESPACE_ID)
    state["adapter_version"] = "old"
    with pytest.raises(ValueError, match="adapter version"):
        _validate_state(state, expected_namespace_id=NAMESPACE_ID)

    state = _empty_state(NAMESPACE_ID)
    state["completed_operations"]["op"] = {
        "changed_memory_keys": [],
        "embedding_observations": [],
        "input_digest": "",
        "llm_observations": [],
        "memory_count": 0,
    }
    with pytest.raises(ValueError, match="input_digest"):
        _validate_state(state, expected_namespace_id=NAMESPACE_ID)


def test_langmem_worker_input_digest_is_order_and_max_steps_sensitive() -> None:
    """session role/content 顺序与 max_steps 都属于 operation identity。"""

    first = _input_digest(
        [
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ],
        1,
    )
    reversed_messages = _input_digest(
        [
            {"role": "assistant", "content": "a"},
            {"role": "user", "content": "u"},
        ],
        1,
    )
    changed_steps = _input_digest(
        [
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "a"},
        ],
        2,
    )
    assert len({first, reversed_messages, changed_steps}) == 3


def test_langmem_worker_reads_exact_usage_from_message_or_llm_output() -> None:
    """LangChain message usage 与兼容 llm_output usage 都映射到精确字段。"""

    response = SimpleNamespace(
        generations=[
            [
                SimpleNamespace(
                    message=SimpleNamespace(
                        usage_metadata={"input_tokens": 12, "output_tokens": 5}
                    )
                )
            ]
        ],
        llm_output=None,
    )
    assert _usage_from_llm_result(response) == {
        "input_tokens": 12,
        "output_tokens": 5,
    }
    fallback = SimpleNamespace(
        generations=[],
        llm_output={"token_usage": {"prompt_tokens": 7, "completion_tokens": 2}},
    )
    assert _usage_from_llm_result(fallback) == {
        "input_tokens": 7,
        "output_tokens": 2,
    }


def test_langmem_worker_rejects_missing_exact_usage() -> None:
    """provider 不回 usage 时不得用 tokenizer 估算冒充 API usage。"""

    response = SimpleNamespace(generations=[], llm_output={})
    with pytest.raises(RuntimeError, match="omitted exact token usage"):
        _usage_from_llm_result(response)
