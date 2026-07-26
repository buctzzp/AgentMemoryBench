"""MemOS async lifecycle 完成门强反例。

覆盖两层：

1. **patched current MemOS 生产函数**：`SingleCubeView._schedule_memory_tasks`、
   `MemReadMessageHandler.{process_grouped_messages,batch_handler,process_message,
   _process_memories_with_reader}`、`TreeTextMemory.delete`、
   `MemoryManager.{_add_memories_batch,_cleanup_working_memory,_cleanup_memories_if_needed}`、
   `Neo4jCommunityGraphDB.add_nodes_batch`——只对**外部 I/O SDK** 做 hermetic fake，
   不 stub `memos.*` 算法函数来跳过被测的 catch 边界；
2. **框架侧** `memory_benchmark.methods.memos_lifecycle` 的 tracker 与 waiter 语义。

零真实 LLM / embedding / Neo4j / Qdrant / Redis / HTTP / 网络。
"""

from __future__ import annotations

import json
import logging.handlers
import subprocess
import sys
import threading
import types

from pathlib import Path

import pytest

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.methods.memos_lifecycle import (
    MEM_READ_TASK_LABEL,
    MemosLocalTaskTracker,
    install_local_tracker,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MEMOS_ROOT = REPO_ROOT / "third_party" / "methods" / "MemOS"
PATCH_PATH = REPO_ROOT / "scripts" / "patches" / "memos-product-runtime-observability.patch"
FETCH_SCRIPT = REPO_ROOT / "scripts" / "fetch_third_party_methods.sh"

_IO_CLIENT_STUBS = (
    "ollama",
    "neo4j",
    "redis",
    "nebula3",
    "pymysql",
    "volcenginesdkarkruntime",
    "markitdown",
    "chonkie",
    "langchain_text_splitters",
    "prometheus_client",
    "pymilvus",
    "elasticsearch",
    "boto3",
    "oss2",
    "schedule",
    "apscheduler",
    "fastapi",
    "starlette",
    "pika",
)


class _StubMeta(type):
    """让占位类的任意属性访问继续返回占位类（满足 `Message.ToolCall` 之类嵌套引用）。"""

    def __getattr__(cls, name):
        """返回下一层占位类。"""
        return _make_stub_attr(name)


def _make_stub_attr(name: str):
    """生成可继续取属性、可实例化、可作基类的占位对象。"""
    body = {
        "__init__": lambda self, *a, **kw: None,
        "__getattr__": lambda self, attr: _make_stub_attr(attr)(),
        # 返回下一层占位实例而非 None，链式调用（如 prometheus 的
        # `COUNTER.labels(...).inc()`）才不会在占位层炸开。
        "__call__": lambda self, *a, **kw: _make_stub_attr("result")(),
    }
    return _StubMeta(name, (), body)


class _LazyStubFinder:
    """只为允许清单内、且本机确实缺失的外部 SDK 提供占位模块。"""

    def find_spec(self, fullname, path=None, target=None):
        """匹配到允许清单的 root package 时返回占位 spec，否则放行真实 import。"""
        import importlib.machinery
        import importlib.util

        root = fullname.split(".")[0]
        if root not in _IO_CLIENT_STUBS:
            return None
        if importlib.util.find_spec is None:  # pragma: no cover - 防御分支
            return None
        return importlib.machinery.ModuleSpec(fullname, _StubLoader())


class _StubLoader:
    """构造任意属性都返回占位对象的模块。"""

    def create_module(self, spec):
        """创建占位模块。"""
        mod = types.ModuleType(spec.name)
        mod.__getattr__ = _make_stub_attr
        mod.__path__ = []
        return mod

    def exec_module(self, module):
        """占位模块无需执行任何代码。"""
        return None


def _bootstrap_memos(tmp_path: Path) -> None:
    """让 memos 在无外部服务、不安装依赖的前提下可导入。"""
    import importlib.util
    import os

    os.environ.setdefault("MEMOS_BASE_PATH", str(tmp_path))

    if "concurrent_log_handler" not in sys.modules:
        stub = types.ModuleType("concurrent_log_handler")
        stub.ConcurrentTimedRotatingFileHandler = logging.handlers.TimedRotatingFileHandler
        sys.modules["concurrent_log_handler"] = stub

    if "cachetools" not in sys.modules and importlib.util.find_spec("cachetools") is None:
        cache_stub = types.ModuleType("cachetools")

        class _Cache(dict):
            """最小占位缓存：忽略容量/TTL，仅满足导入与构造。"""

            def __init__(self, maxsize=0, ttl=None, *a, **kw):
                """接受任意构造参数。"""
                super().__init__()

        cache_stub.LRUCache = _Cache
        cache_stub.TTLCache = _Cache
        sys.modules["cachetools"] = cache_stub

    if not any(isinstance(f, _LazyStubFinder) for f in sys.meta_path):
        sys.meta_path.append(_LazyStubFinder())

    src = str(MEMOS_ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)


@pytest.fixture(scope="module")
def memos_modules(tmp_path_factory):
    """导入 patched current MemOS 的被测模块。"""
    if not MEMOS_ROOT.exists():
        pytest.skip("third_party/methods/MemOS 未就位（local-only），跳过 MemOS 生产链用例")
    _bootstrap_memos(tmp_path_factory.mktemp("memos_home"))

    # 先经 api 包导入，避免 multi_mem_cube 的部分初始化循环导入。
    from memos.api.handlers.add_handler import AddHandler  # noqa: F401
    from memos.mem_scheduler.task_schedule_modules.handlers import mem_read_handler
    from memos.memories.textual import tree
    from memos.memories.textual.tree_text_memory.organize import manager
    from memos.multi_mem_cube.single_cube import SingleCubeView

    return types.SimpleNamespace(
        mem_read_handler=mem_read_handler,
        tree=tree,
        manager=manager,
        single_cube_view=SingleCubeView,
        tree_text_memory=tree.TreeTextMemory,
    )


# --------------------------------------------------------------------------------------
# 1. patch 可复现性
# --------------------------------------------------------------------------------------


def test_patch_reverse_check_matches_vendored_tree():
    """patch 与当前 vendored MemOS 工作树逐字一致（reverse-check 通过）。"""
    if not MEMOS_ROOT.exists():
        pytest.skip("third_party/methods/MemOS 未就位（local-only）")
    assert PATCH_PATH.exists(), "observability patch 必须随仓库提交"
    result = subprocess.run(
        [
            "git",
            "-C",
            str(MEMOS_ROOT.resolve()),
            "apply",
            "--unidiff-zero",
            "--reverse",
            "--check",
            str(PATCH_PATH),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"reverse-check 失败，vendored 工作树与 patch 不一致：{result.stderr}"
    )


def test_fetch_script_applies_memos_patch_exactly_once():
    """fetch 脚本对 MemOS patch 有且只有一次幂等 apply。"""
    text = FETCH_SCRIPT.read_text(encoding="utf-8")
    occurrences = text.count("memos-product-runtime-observability.patch")
    assert occurrences == 1, f"MemOS patch 应只被 apply 一次，实际出现 {occurrences} 次"
    assert 'apply_method_patch "MemOS"' in text
    assert text.index('fetch_method "MemOS"') < text.index('apply_method_patch "MemOS"'), (
        "必须先 checkout 再 apply patch"
    )


def test_manifest_records_patched_source_identity():
    """MANIFEST 把 MemOS 身份写成 tag + 本项目 patch。"""
    manifest = (REPO_ROOT / "third_party" / "methods" / "MANIFEST.md").read_text(
        encoding="utf-8"
    )
    memos_line = next(line for line in manifest.splitlines() if "| MemOS |" in line)
    assert "e820406269537b97d270687e3e40eea2f015f81a" in memos_line
    assert "patch" in memos_line


# --------------------------------------------------------------------------------------
# 生产链公共替身（只替换外部 I/O 叶子，不替换 memos 算法函数）
# --------------------------------------------------------------------------------------


#: 全链用例使用的确定性 namespace（user_id == 唯一 cube_id）。
NS = "run7:locomo:v1:conv-chain"


class _NullReorganizer:
    """reorganizer 占位：满足 MemoryManager.__del__ -> close() -> wait_reorganizer() 依赖。

    直接把属性留空会在 GC 时抛 AttributeError 并被 pytest 记为
    PytestUnraisableExceptionWarning，因此测试构造的 MemoryManager 必须显式初始化它。
    """

    is_reorganize = False

    def wait_until_current_task_done(self):
        """无后台任务，立即返回。"""
        return None

    def stop(self):
        """无后台线程，停止即空操作（MemoryManager.close 会调用）。"""
        return None

    def add_message(self, message):
        """本用例不启用 reorganize，不应被调用。"""
        raise AssertionError("reorganize 未启用时不应产生 reorganizer 消息")


class _RecordingGraphStore:
    """记录型 graph store，可在指定操作上抛错。"""

    def __init__(self, fail_on: set[str] | None = None):
        """构造并声明需要失败的操作名集合。"""
        self.fail_on = fail_on or set()
        self.calls: list[str] = []
        self.deleted: list[str] = []

    def add_nodes_batch(self, nodes, user_name=None):
        """批量写图节点。"""
        self.calls.append("add_nodes_batch")
        if "add_nodes_batch" in self.fail_on:
            raise RuntimeError("PROBE_GRAPH_WRITE_FAILURE")

    def delete_node(self, node_id, user_name=None):
        """删除单个节点。"""
        self.calls.append(f"delete_node:{node_id}")
        if "delete_node" in self.fail_on:
            raise RuntimeError("PROBE_DELETE_FAILURE")
        self.deleted.append(node_id)

    def remove_oldest_memory(self, memory_type=None, keep_latest=None, user_name=None):
        """容量清理。"""
        self.calls.append(f"remove_oldest_memory:{memory_type}")
        if "remove_oldest_memory" in self.fail_on:
            raise RuntimeError("PROBE_CLEANUP_FAILURE")


def _make_trace_text_mem_cls(base):
    """基于真实 TreeTextMemory 构造记录型子类。

    必须真的继承 `TreeTextMemory`，否则会被 handler 的 isinstance 守卫直接拒绝——
    那正是本批 patch 新增的失败分支，不能靠替身绕过。
    """

    class _TraceTextMem(base):
        """记录型 TreeTextMemory 子类，写入共享 trace。"""

        def __init__(self, trace: list[str], fail_on: set[str] | None = None):
            """构造记录型 text memory（不调用父类 __init__，避免真实后端依赖）。"""
            self.trace = trace
            self.fail_on = fail_on or set()
            self.memory_manager = _TraceMemoryManager(trace, self.fail_on)
            self.raw_items: dict[str, object] = {}
            self.added_fine: list[list[object]] = []

        def get(self, mem_id, user_name=None):
            """按 id 回读 raw memory。"""
            self.trace.append(f"text_mem.get:{mem_id}")
            if "get" in self.fail_on:
                raise RuntimeError("PROBE_GET_FAILURE")
            return self.raw_items[mem_id]

        def add(self, memories, user_name=None):
            """写入 fine memory。"""
            self.trace.append(f"text_mem.add:n={len(memories)}")
            if "fine_add" in self.fail_on:
                raise RuntimeError("PROBE_FINE_WRITE_FAILURE")
            self.added_fine.append(list(memories))
            return [f"fine-{i}" for i in range(len(memories))]

        def delete(self, memory_ids, user_name=None):
            """删除 raw memory。"""
            self.trace.append(f"text_mem.delete:{list(memory_ids)}")
            if "delete" in self.fail_on:
                raise RuntimeError("PROBE_DELETE_FAILURE")

    return _TraceTextMem


class _TraceMemoryManager:
    """记录型 memory manager 替身。"""

    def __init__(self, trace: list[str], fail_on: set[str]):
        """构造记录型 memory manager。"""
        self.trace = trace
        self.fail_on = fail_on
        self.reorganizer = None

    def remove_and_refresh_memory(self, user_name=None):
        """容量清理 + size 刷新。"""
        self.trace.append("memory_manager.remove_and_refresh_memory")
        if "refresh" in self.fail_on:
            raise RuntimeError("PROBE_REFRESH_FAILURE")


class _FakeServices:
    """scheduler handler services 替身：记录而不外发 web log。"""

    def __init__(self):
        """初始化 web log 收集列表。"""
        self.web_logs: list[object] = []

    def submit_web_logs(self, events, additional_log_info=None):
        """收集 web log，不做任何外部调用。"""
        self.web_logs.extend(events)

    def validate_messages(self, messages, label):
        """upstream 会在 __call__ 里先做校验。"""
        return None

    def create_event_log(self, **kwargs):
        """返回一个可写属性的占位 event。"""
        return types.SimpleNamespace()

    def map_memcube_name(self, mem_cube_id):
        """返回 cube 名。"""
        return mem_cube_id

    def submit_messages(self, messages):
        """organize task 提交。"""
        return None


def _make_mem_read_handler(memos_modules, text_mem, mem_reader, trace):
    """构造真实 MemReadMessageHandler，只注入替身 context。"""
    mem_cube = types.SimpleNamespace(text_mem=text_mem)
    context = types.SimpleNamespace(
        get_mem_cube=lambda: mem_cube,
        get_mem_reader=lambda: mem_reader,
        services=_FakeServices(),
    )
    return memos_modules.mem_read_handler.MemReadMessageHandler(context)


class _FakeMemReader:
    """记录型 mem reader：控制 fine transfer 的成功/失败/零抽取。"""

    save_rawfile = False
    memory_version_switch = "off"
    graph_db = None

    def __init__(self, trace, outcome="ok"):
        """构造记录型 reader；outcome 取值 ok / empty / raise，分别对应成功、零抽取、抛错。"""
        self.trace = trace
        self.outcome = outcome

    def fine_transfer_simple_mem(self, memory_items, **kwargs):
        """模拟 fine 抽取。"""
        self.trace.append("mem_reader.fine_transfer_simple_mem")
        if self.outcome == "raise":
            raise RuntimeError("PROBE_FINE_TRANSFER_FAILURE")
        if self.outcome == "empty":
            return []
        source_id = getattr(memory_items[0], "id", "unknown") if memory_items else "unknown"
        item = types.SimpleNamespace(
            id="fine-item",
            memory=f"FINE::{source_id}",
            metadata=types.SimpleNamespace(
                memory_type="LongTermMemory", info={}, file_ids=[]
            ),
        )
        return [[item]]


def _mem_read_message(memos_modules, mem_ids, user_id="ns-A", task_id="biz-1"):
    """构造一条真实 ScheduleMessageItem（MEM_READ）。"""
    from memos.mem_scheduler.schemas.message_schemas import ScheduleMessageItem

    return ScheduleMessageItem(
        user_id=user_id,
        task_id=task_id,
        session_id="s1",
        mem_cube_id=user_id,
        label=MEM_READ_TASK_LABEL,
        content=json.dumps(mem_ids),
        user_name=user_id,
    )


def _run_handler(handler, messages):
    """走 upstream `__call__` → process_grouped_messages → batch_handler 全链。"""
    handler(messages)


# --------------------------------------------------------------------------------------
# 2-11. patched MemOS 生产链失败传播
# --------------------------------------------------------------------------------------


def test_async_mem_read_happy_path_shared_trace(memos_modules):
    """happy path：fine transfer → fine write → raw delete → refresh，顺序写同一条 trace。"""
    trace: list[str] = []
    text_mem = _make_trace_text_mem_cls(memos_modules.tree_text_memory)(trace)
    text_mem.raw_items["raw-1"] = types.SimpleNamespace(
        id="raw-1", memory="RAW", metadata=types.SimpleNamespace(background="", info={})
    )
    handler = _make_mem_read_handler(
        memos_modules, text_mem, _FakeMemReader(trace, "ok"), trace
    )

    _run_handler(handler, [_mem_read_message(memos_modules, ["raw-1"])])

    assert trace == [
        "text_mem.get:raw-1",
        "mem_reader.fine_transfer_simple_mem",
        "text_mem.add:n=1",
        "text_mem.delete:['raw-1']",
        "memory_manager.remove_and_refresh_memory",
    ]


def test_legal_zero_extraction_still_completes(memos_modules):
    """合法的“fine 抽取零条 memory”仍走完清理与 refresh，不算失败。"""
    trace: list[str] = []
    text_mem = _make_trace_text_mem_cls(memos_modules.tree_text_memory)(trace)
    text_mem.raw_items["raw-1"] = types.SimpleNamespace(
        id="raw-1", memory="RAW", metadata=types.SimpleNamespace(background="", info={})
    )
    handler = _make_mem_read_handler(
        memos_modules, text_mem, _FakeMemReader(trace, "empty"), trace
    )

    _run_handler(handler, [_mem_read_message(memos_modules, ["raw-1"])])

    assert "text_mem.delete:['raw-1']" in trace
    assert "memory_manager.remove_and_refresh_memory" in trace


@pytest.mark.parametrize(
    ("fail_on", "reader_outcome", "expected_marker"),
    [
        (set(), "raise", "PROBE_FINE_TRANSFER_FAILURE"),
        ({"fine_add"}, "ok", "PROBE_FINE_WRITE_FAILURE"),
        ({"delete"}, "ok", "PROBE_DELETE_FAILURE"),
        ({"refresh"}, "ok", "PROBE_REFRESH_FAILURE"),
        ({"get"}, "ok", "PROBE_GET_FAILURE"),
    ],
)
def test_mem_read_failures_propagate(memos_modules, fail_on, reader_outcome, expected_marker):
    """fine transfer / fine write / raw delete / refresh / raw 回读失败都必须抛出。"""
    trace: list[str] = []
    text_mem = _make_trace_text_mem_cls(memos_modules.tree_text_memory)(
        trace, fail_on=fail_on
    )
    text_mem.raw_items["raw-1"] = types.SimpleNamespace(
        id="raw-1", memory="RAW", metadata=types.SimpleNamespace(background="", info={})
    )
    handler = _make_mem_read_handler(
        memos_modules, text_mem, _FakeMemReader(trace, reader_outcome), trace
    )

    with pytest.raises(Exception) as excinfo:
        _run_handler(handler, [_mem_read_message(memos_modules, ["raw-1"])])
    assert expected_marker in str(excinfo.value)


def test_missing_mem_cube_is_failure(memos_modules):
    """缺 mem cube 必须失败，而不是静默 return。"""
    context = types.SimpleNamespace(
        get_mem_cube=lambda: None,
        get_mem_reader=lambda: None,
        services=_FakeServices(),
    )
    handler = memos_modules.mem_read_handler.MemReadMessageHandler(context)
    with pytest.raises(Exception) as excinfo:
        _run_handler(handler, [_mem_read_message(memos_modules, ["raw-1"])])
    assert "mem_cube is None" in str(excinfo.value)


def test_wrong_text_memory_type_is_failure(memos_modules):
    """text_mem 不是 TreeTextMemory 时必须失败。"""
    mem_cube = types.SimpleNamespace(text_mem=object())
    context = types.SimpleNamespace(
        get_mem_cube=lambda: mem_cube,
        get_mem_reader=lambda: None,
        services=_FakeServices(),
    )
    handler = memos_modules.mem_read_handler.MemReadMessageHandler(context)
    with pytest.raises(Exception) as excinfo:
        _run_handler(handler, [_mem_read_message(memos_modules, ["raw-1"])])
    assert "TreeTextMemory" in str(excinfo.value)


def test_batch_partial_failure_waits_and_aggregates(memos_modules):
    """batch 中一项失败、另一项完成时，等其余收尾后聚合抛出。"""
    trace: list[str] = []

    class _SelectiveTextMem(_make_trace_text_mem_cls(memos_modules.tree_text_memory)):
        """只让来源为 raw-bad 的 fine write 失败。

        判定依据放在 fine memory 内容里，而不是实例上的共享可变状态——
        batch_handler 会并发处理两条消息，共享状态会产生竞态。
        """

        def add(self, memories, user_name=None):
            """按 fine memory 携带的来源 id 决定是否失败。"""
            self.trace.append(f"text_mem.add:n={len(memories)}")
            if any(getattr(m, "memory", "").endswith("raw-bad") for m in memories):
                raise RuntimeError("PROBE_ITEM_FAILURE")
            self.added_fine.append(list(memories))
            return ["fine-0"]

    text_mem = _SelectiveTextMem(trace)
    for mid in ("raw-good", "raw-bad"):
        text_mem.raw_items[mid] = types.SimpleNamespace(
            id=mid, memory="RAW", metadata=types.SimpleNamespace(background="", info={})
        )
    handler = _make_mem_read_handler(
        memos_modules, text_mem, _FakeMemReader(trace, "ok"), trace
    )

    messages = [
        _mem_read_message(memos_modules, ["raw-good"]),
        _mem_read_message(memos_modules, ["raw-bad"]),
    ]
    with pytest.raises(Exception) as excinfo:
        _run_handler(handler, messages)

    assert "PROBE_ITEM_FAILURE" in str(excinfo.value)
    # 好的那条必须已经完整跑完（证明没有 fail-fast 掐断其余 item）
    assert "text_mem.delete:['raw-good']" in trace


def test_tree_delete_partial_failure_raises(memos_modules):
    """TreeTextMemory.delete 逐 id 失败必须最终抛出（不再吞错）。"""
    tree_mod = memos_modules.tree
    store = _RecordingGraphStore(fail_on={"delete_node"})
    tree_obj = tree_mod.TreeTextMemory.__new__(tree_mod.TreeTextMemory)
    tree_obj.graph_store = store
    with pytest.raises(RuntimeError, match="PROBE_DELETE_FAILURE"):
        tree_mod.TreeTextMemory.delete(tree_obj, ["a", "b"], user_name="ns-A")
    # 每个 id 都被尝试过，才聚合抛出
    assert store.calls == ["delete_node:a", "delete_node:b"]


def test_manager_graph_write_failure_does_not_return_phantom_ids(memos_modules):
    """graph batch write 失败时不得返回预生成 ID。"""
    manager_mod = memos_modules.manager
    store = _RecordingGraphStore(fail_on={"add_nodes_batch"})
    mgr = manager_mod.MemoryManager.__new__(manager_mod.MemoryManager)
    mgr.graph_store = store
    mgr.is_reorganize = False
    mgr.reorganizer = _NullReorganizer()
    mgr.memory_size = {"WorkingMemory": 20, "LongTermMemory": 1500, "UserMemory": 480}

    memory = types.SimpleNamespace(
        id="m1",
        memory="hello",
        metadata=types.SimpleNamespace(
            memory_type="LongTermMemory",
            model_dump=lambda exclude_none=True: {"memory_type": "LongTermMemory", "tags": []},
            model_copy=lambda update=None: types.SimpleNamespace(
                model_dump=lambda exclude_none=True: {"memory_type": "WorkingMemory"}
            ),
        ),
    )
    with pytest.raises(RuntimeError, match="PROBE_GRAPH_WRITE_FAILURE"):
        manager_mod.MemoryManager._add_memories_batch(mgr, [memory], user_name="ns-A")


def test_manager_capacity_cleanup_failures_raise(memos_modules):
    """容量清理失败不再只 warning。"""
    manager_mod = memos_modules.manager
    store = _RecordingGraphStore(fail_on={"remove_oldest_memory"})
    mgr = manager_mod.MemoryManager.__new__(manager_mod.MemoryManager)
    mgr.graph_store = store
    mgr.reorganizer = _NullReorganizer()
    mgr.memory_size = {"WorkingMemory": 20}
    mgr.current_memory_size = {"WorkingMemory": 100}

    with pytest.raises(RuntimeError, match="PROBE_CLEANUP_FAILURE"):
        manager_mod.MemoryManager._cleanup_working_memory(mgr, user_name="ns-A")
    with pytest.raises(RuntimeError, match="PROBE_CLEANUP_FAILURE"):
        manager_mod.MemoryManager._cleanup_memories_if_needed(mgr, user_name="ns-A")


def test_neo4j_community_vector_write_failure_raises(memos_modules, monkeypatch):
    """vector batch write 失败不得继续 graph write 并报成功。"""
    from memos.graph_dbs import neo4j_community

    db = neo4j_community.Neo4jCommunityGraphDB.__new__(neo4j_community.Neo4jCommunityGraphDB)
    db.config = types.SimpleNamespace(use_multi_db=True, user_name="ns-A", embedding_dimension=4)

    class _FailingVecDB:
        """向量库写入失败。"""

        def add(self, items):
            """抛出写入失败。"""
            raise RuntimeError("PROBE_VECTOR_WRITE_FAILURE")

    db.vec_db = _FailingVecDB()
    db.driver = None
    db.db_name = "neo4j"

    node_uuid = "3f2504e0-4f89-41d3-9a0c-0305e82c3301"
    nodes = [
        {
            "id": node_uuid,
            "memory": "hello",
            "metadata": {
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "created_at": "2026-07-26T00:00:00",
                "updated_at": "2026-07-26T00:00:00",
                "memory_type": "LongTermMemory",
            },
        }
    ]
    with pytest.raises(RuntimeError, match="PROBE_VECTOR_WRITE_FAILURE"):
        db.add_nodes_batch(nodes, user_name="ns-A")


def test_async_scheduler_submit_failure_propagates(memos_modules):
    """async MEM_READ submit 失败必须抛回 add 调用方（不再 log-and-success）。"""
    SingleCubeView = memos_modules.single_cube_view

    class _FailingScheduler:
        """submit 恒失败。"""

        def submit_messages(self, messages):
            """抛出提交失败。"""
            raise RuntimeError("PROBE_SUBMIT_FAILURE")

    view = SingleCubeView(
        cube_id="ns-A",
        naive_mem_cube=types.SimpleNamespace(text_mem=None),
        mem_reader=None,
        mem_scheduler=_FailingScheduler(),
        logger=logging.getLogger("probe"),
        searcher=None,
    )
    from memos.types.general_types import UserContext

    add_req = types.SimpleNamespace(
        user_id="ns-A",
        task_id="biz-1",
        session_id="s1",
        info={},
        chat_history=None,
        is_upload_skill=False,
    )
    with pytest.raises(RuntimeError, match="PROBE_SUBMIT_FAILURE"):
        view._schedule_memory_tasks(
            add_req=add_req,
            user_context=UserContext(user_id="ns-A", mem_cube_id="ns-A", session_id="s1"),
            mem_ids=["raw-1"],
            sync_mode="async",
        )


# --------------------------------------------------------------------------------------
# 12-15. 框架 tracker / waiter 语义
# --------------------------------------------------------------------------------------


def _submit_and_complete(tracker, user_id, business_id, item_id, status="completed"):
    """登记一条 MEM_READ item 并推进到指定终态。"""
    tracker.task_submitted(
        task_id=item_id,
        user_id=user_id,
        task_type=MEM_READ_TASK_LABEL,
        mem_cube_id=user_id,
        business_task_id=business_id,
    )
    tracker.task_started(task_id=item_id, user_id=user_id)
    if status == "completed":
        tracker.task_completed(task_id=item_id, user_id=user_id)
    else:
        tracker.task_failed(task_id=item_id, user_id=user_id, error_message="boom")


def test_waiter_returns_on_expected_completion():
    """本 business task 的 MEM_READ 完成后 waiter 正常返回。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-A", "biz-1", "item-1")
    payloads = tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=1.0)
    assert len(payloads) == 1
    assert payloads[0]["status"] == "completed"


def test_other_business_task_does_not_unlock():
    """business task A 完成不能解锁 B。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-A", "biz-A", "item-A")
    tracker.task_submitted(
        task_id="item-B",
        user_id="ns-A",
        task_type=MEM_READ_TASK_LABEL,
        mem_cube_id="ns-A",
        business_task_id="biz-B",
    )
    with pytest.raises(ConfigurationError, match="超时"):
        tracker.wait_for_business_task("ns-A", "biz-B", timeout_seconds=0.2)


def test_other_namespace_does_not_unlock():
    """另一个 namespace 的同名 business task 不能解锁。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-B", "biz-1", "item-1")
    with pytest.raises(ConfigurationError, match="从未登记任何 task"):
        tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=0.2)


def test_failed_task_raises_with_original_error():
    """失败任务立即抛 ConfigurationError 并保留原始 error。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-A", "biz-1", "item-1", status="failed")
    with pytest.raises(ConfigurationError, match="boom"):
        tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=1.0)


def test_missing_task_fails_fast():
    """查无任务时 fail-fast，并明确指出未提交后台任务。"""
    tracker = MemosLocalTaskTracker()
    with pytest.raises(ConfigurationError, match="从未登记任何 task"):
        tracker.wait_for_business_task("ns-A", "biz-none", timeout_seconds=0.2)


def test_more_than_expected_mem_read_fails_fast():
    """主 MEM_READ 数量多于预期时 fail-fast。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-A", "biz-1", "item-1")
    _submit_and_complete(tracker, "ns-A", "biz-1", "item-2")
    with pytest.raises(ConfigurationError, match="数量超出预期"):
        tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=1.0)


def test_non_mem_read_labels_are_not_counted():
    """同一 business task 下的非 MEM_READ task 不计入完成门。"""
    tracker = MemosLocalTaskTracker()
    tracker.task_submitted(
        task_id="item-add",
        user_id="ns-A",
        task_type="add",
        mem_cube_id="ns-A",
        business_task_id="biz-1",
    )
    tracker.task_completed(task_id="item-add", user_id="ns-A")
    with pytest.raises(ConfigurationError, match="从未登记任何 task"):
        tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=0.2)


def test_unknown_status_fails_fast():
    """未知状态 fail-fast。"""
    tracker = MemosLocalTaskTracker()
    tracker.task_submitted(
        task_id="item-1",
        user_id="ns-A",
        task_type=MEM_READ_TASK_LABEL,
        mem_cube_id="ns-A",
        business_task_id="biz-1",
    )
    tracker._records[("ns-A", "item-1")].status = "weird"
    with pytest.raises(ConfigurationError, match="未知状态"):
        tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=1.0)


def test_waiter_wakes_up_from_background_thread():
    """后台线程完成 task 时 waiter 被唤醒（不靠 polling sleep 猜）。"""
    tracker = MemosLocalTaskTracker()
    tracker.task_submitted(
        task_id="item-1",
        user_id="ns-A",
        task_type=MEM_READ_TASK_LABEL,
        mem_cube_id="ns-A",
        business_task_id="biz-1",
    )

    def _finish():
        """在后台把任务推进到 completed。"""
        tracker.task_started(task_id="item-1", user_id="ns-A")
        tracker.task_completed(task_id="item-1", user_id="ns-A")

    threading.Timer(0.05, _finish).start()
    payloads = tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=5.0)
    assert payloads[0]["status"] == "completed"


def test_tracker_is_thread_safe_under_concurrency():
    """多线程并发登记/推进时状态不丢。"""
    tracker = MemosLocalTaskTracker()
    total = 60

    def _worker(idx: int) -> None:
        """并发登记并完成一条 task。"""
        _submit_and_complete(tracker, "ns-A", f"biz-{idx}", f"item-{idx}")

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(total)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    for i in range(total):
        agg = tracker.get_task_status_by_business_id(f"biz-{i}", "ns-A")
        assert agg is not None and agg["status"] == "completed"
    assert tracker.pending_tasks() == []


def test_shutdown_guard_rejects_pending_tasks():
    """关闭前仍有 pending task 时 fail-fast；全部完成后可关闭。"""
    tracker = MemosLocalTaskTracker()
    tracker.task_submitted(
        task_id="item-1",
        user_id="ns-A",
        task_type=MEM_READ_TASK_LABEL,
        mem_cube_id="ns-A",
        business_task_id="biz-1",
    )
    with pytest.raises(ConfigurationError, match="拒绝静默关闭"):
        tracker.assert_no_pending_tasks()

    tracker.task_completed(task_id="item-1", user_id="ns-A")
    tracker.assert_no_pending_tasks()


def test_install_local_tracker_shares_one_instance():
    """同一个 tracker 必须同时挂到 scheduler 与 dispatcher。"""
    dispatcher = types.SimpleNamespace(status_tracker=None)
    scheduler = types.SimpleNamespace(dispatcher=dispatcher, status_tracker=None)
    tracker = install_local_tracker(scheduler)
    assert scheduler.status_tracker is tracker
    assert dispatcher.status_tracker is tracker


def test_install_local_tracker_requires_dispatcher():
    """没有 dispatcher 时安装必须 fail-fast。"""
    scheduler = types.SimpleNamespace(dispatcher=None, status_tracker=None)
    with pytest.raises(ConfigurationError, match="没有 dispatcher"):
        install_local_tracker(scheduler)


def test_dispatcher_marks_task_failed_through_real_wrapper(memos_modules):
    """真实 dispatcher wrapper 在 handler 抛错时把 task 标 failed 并写入本 tracker。"""
    from memos.mem_scheduler.task_schedule_modules.dispatcher import SchedulerDispatcher

    tracker = MemosLocalTaskTracker()
    dispatcher = SchedulerDispatcher.__new__(SchedulerDispatcher)
    dispatcher.status_tracker = tracker
    dispatcher.submit_web_logs = None
    dispatcher.metrics = types.SimpleNamespace(
        observe_task_wait_duration=lambda *a, **kw: None,
        observe_task_duration=lambda *a, **kw: None,
        task_completed=lambda **kw: None,
        task_failed=lambda *a, **kw: None,
    )
    dispatcher._task_lock = threading.RLock()
    dispatcher._running_tasks = {}
    dispatcher.memos_message_queue = None

    msg = _mem_read_message(memos_modules, ["raw-1"])
    tracker.task_submitted(
        task_id=msg.item_id,
        user_id=msg.user_id,
        task_type=msg.label,
        mem_cube_id=msg.mem_cube_id,
        business_task_id=msg.task_id,
    )
    task_item = types.SimpleNamespace(
        item_id="running-1",
        mark_completed=lambda result: None,
        mark_failed=lambda err: None,
        get_execution_info=lambda: "probe",
    )

    def _boom(messages):
        """模拟 handler 抛错。"""
        raise RuntimeError("PROBE_HANDLER_FAILURE")

    wrapped = dispatcher._create_task_wrapper(_boom, task_item)
    with pytest.raises(RuntimeError, match="PROBE_HANDLER_FAILURE"):
        wrapped([msg])

    status = tracker.get_task_status(msg.item_id, msg.user_id)
    assert status["status"] == "failed"
    assert "PROBE_HANDLER_FAILURE" in status["error"]
    with pytest.raises(ConfigurationError, match="PROBE_HANDLER_FAILURE"):
        tracker.wait_for_business_task(msg.user_id, msg.task_id, timeout_seconds=1.0)


# --------------------------------------------------------------------------------------
# R2-R1 §4.1  完整 async product chain（单一共享 trace）
# --------------------------------------------------------------------------------------


class _ChainGraphStore:
    """记录型 graph store：单一共享 trace + 内存节点表，可按操作注入失败。"""

    def __init__(self, trace: list[str], fail_on: set[str] | None = None):
        """构造共享 trace 的 graph store。"""
        self.trace = trace
        self.fail_on = fail_on or set()
        self.nodes: dict[str, dict] = {}

    def add_nodes_batch(self, nodes, user_name=None):
        """批量写图节点（真实 MemoryManager._add_memories_batch 调用）。"""
        self.trace.append(f"graph.add_nodes_batch:n={len(nodes)}")
        if "add_nodes_batch" in self.fail_on:
            raise RuntimeError("PROBE_GRAPH_WRITE_FAILURE")
        for node in nodes:
            self.nodes[node["id"]] = node

    def get_node(self, node_id, user_name=None):
        """按 id 回读节点。"""
        self.trace.append(f"graph.get_node:{node_id}")
        return self.nodes.get(node_id)

    def delete_node(self, node_id, user_name=None):
        """删除节点。"""
        self.trace.append(f"graph.delete_node:{node_id}")
        self.nodes.pop(node_id, None)

    def update_node(self, node_id, fields, user_name=None):
        """更新节点字段（merged_from archive 用）。"""
        self.trace.append(f"graph.update_node:{node_id}")
        if "update_node" in self.fail_on:
            raise RuntimeError("PROBE_ARCHIVE_FAILURE")

    def remove_oldest_memory(self, memory_type=None, keep_latest=None, user_name=None):
        """容量清理。"""
        self.trace.append(f"graph.remove_oldest_memory:{memory_type}")

    def get_all_memory_items(self, scope=None, user_name=None, **kwargs):
        """按 scope 返回节点（refresh 用）。"""
        return []

    def get_memory_count(self, memory_type=None, user_name=None, **kwargs):
        """返回该类型节点数。"""
        return 0

    def get_grouped_counts(self, group_fields=None, user_name=None, **kwargs):
        """按 memory_type 汇总当前节点数（真实 _refresh_memory_size 调用）。"""
        self.trace.append("graph.get_grouped_counts")
        counts: dict[str, int] = {}
        for node in self.nodes.values():
            mtype = (node.get("metadata") or {}).get("memory_type", "LongTermMemory")
            counts[mtype] = counts.get(mtype, 0) + 1
        return [{"memory_type": k, "count": v} for k, v in counts.items()]


def _build_chain(memos_modules, trace, *, reader_outcome="ok", store_fail=None):
    """组装真实 add 链：MemoryManager + TreeTextMemory + SingleCubeView + 真实 scheduler。

    只有 LLM / embedder / chunker / graph store 是 hermetic fake；
    MemoryManager、TreeTextMemory、SingleCubeView、BaseScheduler、ScheduleTaskQueue、
    SchedulerDispatcher、MemReadMessageHandler、MultiModalStructMemReader 全部是真实实现。
    """
    from memos.configs.mem_scheduler import SchedulerConfigFactory
    from memos.mem_scheduler.scheduler_factory import SchedulerFactory
    from memos.mem_scheduler.schemas.task_schemas import MEM_READ_TASK_LABEL as _LABEL

    manager_mod = memos_modules.manager
    tree_mod = memos_modules.tree

    store = _ChainGraphStore(trace, fail_on=store_fail)

    mgr = manager_mod.MemoryManager.__new__(manager_mod.MemoryManager)
    mgr.graph_store = store
    mgr.is_reorganize = False
    mgr.reorganizer = _NullReorganizer()
    mgr.memory_size = {"WorkingMemory": 20, "LongTermMemory": 1500, "UserMemory": 480}
    mgr.current_memory_size = {"WorkingMemory": 0, "LongTermMemory": 0, "UserMemory": 0}

    text_mem = tree_mod.TreeTextMemory.__new__(tree_mod.TreeTextMemory)
    text_mem.graph_store = store
    text_mem.memory_manager = mgr
    text_mem.mode = "async"

    reader = _build_chain_reader(trace, reader_outcome)
    mem_cube = types.SimpleNamespace(text_mem=text_mem, act_mem=None, para_mem=None)

    scheduler_config = SchedulerConfigFactory(
        backend="general_scheduler",
        config={
            "top_k": 10,
            "enable_parallel_dispatch": True,
            "use_redis_queue": False,
            "thread_pool_max_workers": 4,
            "consume_interval_seconds": 0.01,
        },
    )
    scheduler = SchedulerFactory.from_config(scheduler_config)
    tracker = install_local_tracker(scheduler)

    handler_context = types.SimpleNamespace(
        get_mem_cube=lambda: mem_cube,
        get_mem_reader=lambda: reader,
        services=_FakeServices(),
    )
    handler = memos_modules.mem_read_handler.MemReadMessageHandler(handler_context)
    scheduler.dispatcher.register_handler(_LABEL, handler)

    view = memos_modules.single_cube_view(
        cube_id=NS,
        naive_mem_cube=mem_cube,
        mem_reader=reader,
        mem_scheduler=scheduler,
        logger=logging.getLogger("chain"),
        searcher=None,
    )
    return types.SimpleNamespace(
        scheduler=scheduler, tracker=tracker, view=view, store=store, reader=reader
    )


def _build_chain_reader(trace, outcome="ok"):
    """构造真实 MultiModalStructMemReader，只替换 LLM / embedder / chunker 叶子。"""
    import memos.mem_reader.multi_modal_struct as mms_mod
    import memos.mem_reader.simple_struct as ss_mod
    from memos.configs.mem_reader import MultiModalStructMemReaderConfig

    class _ChainLLM:
        """记录型 LLM，写入共享 trace。"""

        def generate(self, messages, **kwargs):
            """返回一条固定抽取结果，或按 outcome 抛错/返回空。"""
            trace.append("llm.generate")
            if outcome == "llm_raise":
                raise RuntimeError("PROBE_LLM_FAILURE")
            if outcome == "empty":
                return json.dumps({"memory list": [], "summary": ""})
            return json.dumps(
                {
                    "memory list": [
                        {
                            "key": "k",
                            "memory_type": "LongTermMemory",
                            "value": "FINE_FACT",
                            "tags": [],
                        }
                    ],
                    "summary": "s",
                }
            )

    class _ChainEmbedder:
        """确定性 embedder，写入共享 trace。"""

        def embed(self, texts):
            """返回常量向量。"""
            trace.append(f"embed:n={len(texts)}")
            return [[0.1, 0.2, 0.3, 0.4] for _ in texts]

    class _ChainChunkerConfig:
        """chunker 配置占位。"""

        save_rawfile = False

    class _ChainChunker:
        """chunker 占位，chat 路径不使用。"""

        config = _ChainChunkerConfig()

        def chunk(self, text, **kwargs):
            """原样返回。"""
            return [text]

    cfg = MultiModalStructMemReaderConfig.model_validate(
        {
            "llm": {
                "backend": "openai",
                "config": {"model_name_or_path": "probe", "api_key": "probe"},
            },
            "embedder": {
                "backend": "universal_api",
                "config": {
                    "provider": "openai",
                    "api_key": "probe",
                    "model_name_or_path": "probe",
                },
            },
            "chunker": {"backend": "sentence", "config": {}},
        }
    )
    # Factory 是 vendored MemOS 的进程级类属性。构造 reader 后立即恢复，避免本文件的
    # hermetic fake 污染同一 pytest 进程里随后执行的 adapter / registry 用例。
    with pytest.MonkeyPatch.context() as patcher:
        patcher.setattr(
            ss_mod.LLMFactory,
            "from_config",
            staticmethod(lambda *a, **k: _ChainLLM()),
        )
        patcher.setattr(
            ss_mod.EmbedderFactory,
            "from_config",
            staticmethod(lambda *a, **k: _ChainEmbedder()),
        )
        patcher.setattr(
            ss_mod.ChunkerFactory,
            "from_config",
            staticmethod(lambda *a, **k: _ChainChunker()),
        )
        return mms_mod.MultiModalStructMemReader(cfg)


def test_chain_reader_factory_overrides_are_scoped(memos_modules):
    """全链 fake factory 只在 reader 构造期间生效，退出后恢复真实全局入口。"""
    import memos.mem_reader.simple_struct as ss_mod

    original_llm_factory = ss_mod.LLMFactory.__dict__["from_config"]
    original_embedder_factory = ss_mod.EmbedderFactory.__dict__["from_config"]
    original_chunker_factory = ss_mod.ChunkerFactory.__dict__["from_config"]

    _build_chain_reader([], "ok")

    assert ss_mod.LLMFactory.__dict__["from_config"] is original_llm_factory
    assert ss_mod.EmbedderFactory.__dict__["from_config"] is original_embedder_factory
    assert ss_mod.ChunkerFactory.__dict__["from_config"] is original_chunker_factory


def _chain_add_request(business_task_id="biz-chain-1"):
    """构造 product-default async add 请求。"""
    from memos.api.product_models import APIADDRequest

    return APIADDRequest(
        user_id=NS,
        session_id="sess-1",
        task_id=business_task_id,
        writable_cube_ids=[NS],
        messages=[
            {
                "role": "user",
                "content": "Where did I go last summer?",
                "chat_time": "2023-05-20 10:00:00",
                "message_id": f"{NS}:sess-1:turn-1",
            },
            {
                "role": "assistant",
                "content": "You went to Kyoto.",
                "chat_time": "2023-05-20 10:00:05",
                "message_id": f"{NS}:sess-1:turn-2",
            },
        ],
        async_mode="async",
        mode=None,
    )


def test_full_async_product_chain_single_shared_trace(memos_modules):
    """完整 async 链在一条共享 trace 上到达唯一终态 completed。

    product-default `enable_parallel_dispatch=true`，真实 local queue + 真实 consumer
    线程 + 真实 dispatcher wrapper；不把 dispatcher 改成同步。
    """
    trace: list[str] = []
    chain = _build_chain(memos_modules, trace)
    chain.scheduler.start_consumer()
    try:
        trace.append("== add:begin ==")
        result = chain.view.add_memories(_chain_add_request())
        trace.append("== add:returned ==")
        assert result, "async add 必须返回 fast memory"

        payloads = chain.tracker.wait_for_business_task(
            NS, "biz-chain-1", timeout_seconds=30.0
        )
        trace.append("== wait:returned ==")
    finally:
        chain.scheduler.stop()

    assert payloads[0]["status"] == "completed"

    # 单一共享 trace 覆盖 fast reader → fast write → submit → dispatcher → fine → delete → refresh
    joined = "\n".join(trace)
    for marker in (
        "== add:begin ==",
        "embed:n=1",
        "graph.add_nodes_batch:n=1",
        "== add:returned ==",
        "graph.get_node:",
        "llm.generate",
        "graph.delete_node:",
        # refresh = remove_and_refresh_memory -> _refresh_memory_size -> get_grouped_counts。
        # remove_oldest_memory 只在超过 80% 容量阈值时触发，本用例节点数远低于阈值，
        # 因此不断言它——那是 product 的正常行为，不是链路缺失。
        "graph.get_grouped_counts",
        "== wait:returned ==",
    ):
        assert marker in joined, f"缺少链路环节 {marker}\n实际 trace:\n{joined}"

    # 严格前后序：fast write 先于 add 返回；fine write 与 raw delete 在 add 返回之后
    i_fast_write = trace.index("graph.add_nodes_batch:n=1")
    i_fine_write = trace.index("graph.add_nodes_batch:n=1", i_fast_write + 1)
    i_returned = trace.index("== add:returned ==")
    i_delete = next(i for i, s in enumerate(trace) if s.startswith("graph.delete_node:"))
    i_refresh = trace.index("graph.get_grouped_counts")
    i_wait = trace.index("== wait:returned ==")
    assert i_fast_write < i_returned < i_fine_write < i_delete < i_refresh < i_wait
    chain.tracker.assert_no_pending_tasks()


# --------------------------------------------------------------------------------------
# R2-R1 §4.2  Reader / archive 强反例（异常注入到真实最低层叶子）
# --------------------------------------------------------------------------------------


def _chain_fail(memos_modules, trace, **kwargs):
    """跑一次完整 async 链并返回 (chain, 抛出的异常或 None)。"""
    chain = _build_chain(memos_modules, trace, **kwargs)
    chain.scheduler.start_consumer()
    err = None
    try:
        trace.append("== add:begin ==")
        chain.view.add_memories(_chain_add_request())
        trace.append("== add:returned ==")
        chain.tracker.wait_for_business_task(NS, "biz-chain-1", timeout_seconds=30.0)
    except Exception as e:  # noqa: BLE001
        err = e
    finally:
        chain.scheduler.stop()
    return chain, err


def test_llm_generation_failure_no_raw_fallback(memos_modules):
    """LLM 抛错时真实 _get_llm_response 不再伪造“原文即 UserMemory”。"""
    trace: list[str] = []
    chain, err = _chain_fail(memos_modules, trace, reader_outcome="llm_raise")
    assert err is not None, "LLM 失败必须让 MEM_READ task 失败"
    assert "PROBE_LLM_FAILURE" in str(err)

    # async add 先写一条 raw/fast memory 是产品正常行为；关键是 LLM 失败后
    # **不得再产生任何 fine write**——旧行为会把原文伪造成 UserMemory 抽取结果写进去。
    i_returned = trace.index("== add:returned ==")
    fine_writes = [
        t for t in trace[i_returned:] if t.startswith("graph.add_nodes_batch")
    ]
    assert fine_writes == [], f"LLM 失败后不得写入任何 fine memory：{fine_writes}"

    # 且 raw memory 不得被删除（失败任务不能留下“既没 fine 也没 raw”的空洞）
    assert chain.store.nodes, "任务失败时 raw memory 必须保留，便于 clean retry"


def test_successful_empty_llm_result_still_completes(memos_modules):
    """LLM 调用成功、解析成功、明确产出空 memory list —— 合法零抽取，仍 completed。"""
    trace: list[str] = []
    chain = _build_chain(memos_modules, trace, reader_outcome="empty")
    chain.scheduler.start_consumer()
    try:
        chain.view.add_memories(_chain_add_request())
        payloads = chain.tracker.wait_for_business_task(
            NS, "biz-chain-1", timeout_seconds=30.0
        )
    finally:
        chain.scheduler.stop()
    assert payloads[0]["status"] == "completed"


class _FlakyEmbedder:
    """batch 失败、逐项按索引选择性失败的 embedder（真实最低层叶子）。"""

    def __init__(self, trace, fail_batch=True, fail_item_indices=()):
        """记录调用并按配置抛错。"""
        self.trace = trace
        self.fail_batch = fail_batch
        self.fail_item_indices = set(fail_item_indices)
        self.item_calls = 0

    def embed(self, texts):
        """batch 与逐项使用同一入口，按长度区分。"""
        if len(texts) > 1:
            self.trace.append(f"embed.batch:n={len(texts)}")
            if self.fail_batch:
                raise RuntimeError("PROBE_EMBED_BATCH_FAILURE")
            return [[0.1, 0.2, 0.3, 0.4] for _ in texts]
        idx = self.item_calls
        self.item_calls += 1
        self.trace.append(f"embed.item:{idx}")
        if idx in self.fail_item_indices:
            raise RuntimeError(f"PROBE_EMBED_ITEM_FAILURE:{idx}")
        return [[0.1, 0.2, 0.3, 0.4]]


def _embed_items(memos_modules, embedder, count=3):
    """用真实 _embed_memory_items 处理若干 memory item。"""
    import memos.mem_reader.multi_modal_struct as mms_mod

    reader = mms_mod.MultiModalStructMemReader.__new__(mms_mod.MultiModalStructMemReader)
    reader.embedder = embedder
    items = [
        types.SimpleNamespace(
            memory=f"text-{i}",
            metadata=types.SimpleNamespace(embedding=None),
        )
        for i in range(count)
    ]
    mms_mod.MultiModalStructMemReader._embed_memory_items(reader, items)
    return items


def test_embedding_batch_failure_with_all_item_fallbacks_ok(memos_modules):
    """batch embedding 失败但所有逐项 fallback 成功 —— 行为不变，不抛错。"""
    trace: list[str] = []
    embedder = _FlakyEmbedder(trace, fail_batch=True)
    items = _embed_items(memos_modules, embedder, count=3)
    assert all(i.metadata.embedding is not None for i in items)
    assert trace == ["embed.batch:n=3", "embed.item:0", "embed.item:1", "embed.item:2"]


def test_embedding_all_item_fallbacks_attempted_then_raise(memos_modules):
    """batch 与某个逐项 fallback 都失败：其余项仍尝试完，最后 aggregate raise。"""
    trace: list[str] = []
    embedder = _FlakyEmbedder(trace, fail_batch=True, fail_item_indices=(1,))
    with pytest.raises(RuntimeError, match="PROBE_EMBED_ITEM_FAILURE:1"):
        _embed_items(memos_modules, embedder, count=3)
    # 失败项之后的项也必须被尝试过，才是 settle-then-aggregate
    assert trace == ["embed.batch:n=3", "embed.item:0", "embed.item:1", "embed.item:2"]


class _SelectiveParser:
    """按 message content 选择性抛错的真实 parser 替身（最低层叶子）。"""

    def __init__(self, trace, bad_marker="BAD"):
        """记录并按 marker 抛错。"""
        self.trace = trace
        self.bad_marker = bad_marker

    def parse(self, message, info, mode="fast", **kwargs):
        """成功项返回一个 memory item，失败项抛错。"""
        content = message.get("content", "") if isinstance(message, dict) else str(message)
        self.trace.append(f"parser.parse:{content[:12]}")
        if self.bad_marker in content:
            raise RuntimeError("PROBE_PARSER_FAILURE")
        return [
            types.SimpleNamespace(
                memory=content,
                metadata=types.SimpleNamespace(
                    embedding=None,
                    sources=[],
                    user_id="u",
                    session_id="s",
                    info={},
                    internal_info=None,
                    file_ids=[],
                    memory_type="LongTermMemory",
                ),
            )
        ]


def test_initial_parser_partial_failure_settles_then_fails(memos_modules):
    """initial parser 一项失败一项成功：两项都跑完后整体失败，且不写 partial fast memory。"""
    trace: list[str] = []
    chain = _build_chain(memos_modules, trace)
    chain.reader.multi_modal_parser = _SelectiveParser(trace)

    req = _chain_add_request()
    req.messages[1]["content"] = "BAD message"

    with pytest.raises(RuntimeError, match="PROBE_PARSER_FAILURE"):
        chain.view.add_memories(req)

    parsed = [t for t in trace if t.startswith("parser.parse:")]
    assert len(parsed) == 2, f"两条消息都必须被尝试解析：{parsed}"
    assert not chain.store.nodes, "整体失败时不得留下 partial fast memory"


def test_fine_worker_partial_failure_settles_then_task_failed(memos_modules):
    """最低层 LLM 一项失败一项成功：两个 fine worker 都 settle 后整体失败。"""
    import memos.mem_reader.multi_modal_struct as mms_mod

    reader = mms_mod.MultiModalStructMemReader.__new__(mms_mod.MultiModalStructMemReader)
    reader.memory_version_switch = "off"
    reader.save_rawfile = False
    reader.searcher = None
    reader.graph_db = None
    reader.config = types.SimpleNamespace(remove_prompt_example=False)

    calls: list[str] = []

    class _SelectiveLLM:
        """在真实 ``_get_llm_response`` 的最低 LLM 叶子按 prompt 选择性失败。"""

        def generate(self, messages, **kwargs):
            """记录两个 worker 的真实 prompt，仅让 BAD worker 抛错。"""
            prompt = messages[0]["content"]
            calls.append(prompt)
            if "BAD two" in prompt:
                raise RuntimeError("PROBE_FINE_WORKER_FAILURE")
            return json.dumps({"memory list": [], "summary": ""})

    reader.llm = _SelectiveLLM()

    fast_items = [
        types.SimpleNamespace(
            memory=txt,
            metadata=types.SimpleNamespace(sources=[], file_ids=[]),
        )
        for txt in ("GOOD one", "BAD two")
    ]
    with pytest.raises(RuntimeError, match="PROBE_FINE_WORKER_FAILURE"):
        mms_mod.MultiModalStructMemReader._process_string_fine(
            reader, fast_items, {"user_id": "u", "session_id": "s"}, None
        )
    assert len(calls) == 2, f"两个 fine worker 都必须被尝试：{calls}"


def test_fine_memory_item_embedding_failure_is_not_legal_zero(memos_modules):
    """memory-item 构造时的最低层 embedding 失败必须向上抛出，不能降成零抽取。"""
    import memos.mem_reader.multi_modal_struct as mms_mod

    class _MemoryLLM:
        """返回一条需要构造并 embedding 的合法 fine memory。"""

        def generate(self, messages, **kwargs):
            """返回固定的结构化抽取结果。"""
            return json.dumps(
                {
                    "memory list": [
                        {
                            "key": "k",
                            "memory_type": "LongTermMemory",
                            "value": "fact",
                            "tags": [],
                        }
                    ],
                    "summary": "s",
                }
            )

    class _FailingEmbedder:
        """在 ``SimpleStructMemReader._make_memory_item`` 的真实 embedding 叶子失败。"""

        def embed(self, texts):
            """稳定抛出探针异常。"""
            raise RuntimeError("PROBE_CONSTRUCTION_EMBED_FAILURE")

    reader = mms_mod.MultiModalStructMemReader.__new__(mms_mod.MultiModalStructMemReader)
    reader.memory_version_switch = "off"
    reader.save_rawfile = False
    reader.searcher = None
    reader.graph_db = None
    reader.config = types.SimpleNamespace(remove_prompt_example=False)
    reader.llm = _MemoryLLM()
    reader.embedder = _FailingEmbedder()
    fast_items = [
        types.SimpleNamespace(
            memory="ONE",
            metadata=types.SimpleNamespace(sources=[], file_ids=[]),
        )
    ]

    with pytest.raises(RuntimeError, match="PROBE_CONSTRUCTION_EMBED_FAILURE"):
        mms_mod.MultiModalStructMemReader._process_string_fine(
            reader,
            fast_items,
            {"user_id": "u", "session_id": "s"},
            None,
        )


def test_merged_from_archive_partial_failure_fails_task(memos_modules):
    """merged_from archive 一项失败一项成功：两个 old id 都尝试，最终 task failed。"""
    trace: list[str] = []
    text_mem = _make_trace_text_mem_cls(memos_modules.tree_text_memory)(trace)
    text_mem.raw_items["raw-1"] = types.SimpleNamespace(
        id="raw-1", memory="RAW", metadata=types.SimpleNamespace(background="", info={})
    )

    attempted: list[str] = []

    class _ArchiveGraphDB:
        """第二个 old id archive 失败。"""

        def update_node(self, node_id, fields, user_name=None):
            """记录尝试并对 old-2 抛错。"""
            attempted.append(node_id)
            if node_id == "old-2":
                raise RuntimeError("PROBE_ARCHIVE_FAILURE")

    class _MergedReader(_FakeMemReader):
        """产出带 merged_from 的 fine memory。"""

        def fine_transfer_simple_mem(self, memory_items, **kwargs):
            """返回两条各自 merged_from 的 fine item。"""
            self.trace.append("mem_reader.fine_transfer_simple_mem")
            return [
                [
                    types.SimpleNamespace(
                        id="fine-1",
                        memory="FINE1",
                        metadata=types.SimpleNamespace(
                            memory_type="LongTermMemory",
                            info={"merged_from": "old-1"},
                            file_ids=[],
                        ),
                    ),
                    types.SimpleNamespace(
                        id="fine-2",
                        memory="FINE2",
                        metadata=types.SimpleNamespace(
                            memory_type="LongTermMemory",
                            info={"merged_from": "old-2"},
                            file_ids=[],
                        ),
                    ),
                ]
            ]

    reader = _MergedReader(trace, "ok")
    reader.graph_db = _ArchiveGraphDB()
    handler = _make_mem_read_handler(memos_modules, text_mem, reader, trace)

    with pytest.raises(Exception, match="PROBE_ARCHIVE_FAILURE"):
        _run_handler(handler, [_mem_read_message(memos_modules, ["raw-1"])])
    assert attempted == ["old-1", "old-2"], f"两个 old id 都必须尝试 archive：{attempted}"


def test_merged_from_without_graph_db_fails_fast(memos_modules):
    """出现 merged_from 但 graph_db 为 None 时 fail-fast，不得完成。"""
    trace: list[str] = []
    text_mem = _make_trace_text_mem_cls(memos_modules.tree_text_memory)(trace)
    text_mem.raw_items["raw-1"] = types.SimpleNamespace(
        id="raw-1", memory="RAW", metadata=types.SimpleNamespace(background="", info={})
    )

    class _MergedNoDbReader(_FakeMemReader):
        """产出带 merged_from 的 fine memory，但没有 graph_db。"""

        graph_db = None

        def fine_transfer_simple_mem(self, memory_items, **kwargs):
            """返回一条 merged_from item。"""
            self.trace.append("mem_reader.fine_transfer_simple_mem")
            return [
                [
                    types.SimpleNamespace(
                        id="fine-1",
                        memory="FINE1",
                        metadata=types.SimpleNamespace(
                            memory_type="LongTermMemory",
                            info={"merged_from": "old-1"},
                            file_ids=[],
                        ),
                    )
                ]
            ]

    handler = _make_mem_read_handler(
        memos_modules, text_mem, _MergedNoDbReader(trace, "ok"), trace
    )
    with pytest.raises(Exception, match="graph_db is "):
        _run_handler(handler, [_mem_read_message(memos_modules, ["raw-1"])])


# --------------------------------------------------------------------------------------
# R2-R1 §4.3  Tracker anti-corruption
# --------------------------------------------------------------------------------------


def test_failed_terminal_is_not_overwritten_by_completed():
    """failed 是单调终态，后来的 completed 不得把失败改成成功。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-A", "biz-1", "item-1", status="failed")
    with pytest.raises(ConfigurationError, match="拒绝被改写"):
        tracker.task_completed(task_id="item-1", user_id="ns-A")
    assert tracker.get_task_status("item-1", "ns-A")["status"] == "failed"
    with pytest.raises(ConfigurationError, match="boom"):
        tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=0.5)


def test_completed_terminal_is_not_overwritten_by_failed():
    """completed 同样单调，不得被后来的 failed 覆盖。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-A", "biz-1", "item-1")
    with pytest.raises(ConfigurationError, match="拒绝被改写"):
        tracker.task_failed(task_id="item-1", user_id="ns-A", error_message="late")
    assert tracker.get_task_status("item-1", "ns-A")["status"] == "completed"


def test_identical_resubmit_is_idempotent_and_keeps_terminal():
    """完全相同身份的重复 submit 幂等，不把 completed 退回 waiting。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-A", "biz-1", "item-1")
    tracker.task_submitted(
        task_id="item-1",
        user_id="ns-A",
        task_type=MEM_READ_TASK_LABEL,
        mem_cube_id="ns-A",
        business_task_id="biz-1",
    )
    assert tracker.get_task_status("item-1", "ns-A")["status"] == "completed"
    payloads = tracker.wait_for_business_task("ns-A", "biz-1", timeout_seconds=0.5)
    assert payloads[0]["status"] == "completed"


def test_rebinding_item_to_other_business_task_fails_fast():
    """同一 item id 改绑另一个 business id 必须 fail-fast，且旧 index 不被污染。"""
    tracker = MemosLocalTaskTracker()
    _submit_and_complete(tracker, "ns-A", "biz-1", "item-1")
    with pytest.raises(ConfigurationError, match="被改绑到不同身份"):
        tracker.task_submitted(
            task_id="item-1",
            user_id="ns-A",
            task_type=MEM_READ_TASK_LABEL,
            mem_cube_id="ns-A",
            business_task_id="biz-2",
        )
    assert tracker.get_task_status_by_business_id("biz-2", "ns-A") is None
    agg = tracker.get_task_status_by_business_id("biz-1", "ns-A")
    assert agg["status"] == "completed" and agg["item_count"] == 1


@pytest.mark.parametrize("transition", ["started", "completed", "failed"])
def test_unsubmitted_transitions_fail_fast(transition):
    """未 submit 的 started/completed/failed 必须 fail-fast，不创建 orphan record。"""
    tracker = MemosLocalTaskTracker()
    with pytest.raises(ConfigurationError, match="从未登记"):
        if transition == "started":
            tracker.task_started(task_id="ghost", user_id="ns-A")
        elif transition == "completed":
            tracker.task_completed(task_id="ghost", user_id="ns-A")
        else:
            tracker.task_failed(task_id="ghost", user_id="ns-A", error_message="x")
    assert tracker.get_task_status("ghost", "ns-A") is None
    assert tracker.pending_tasks() == []
