# MemOS v2.0.25 产品运行时契约 M1 R1

日期：2026-07-26
执行者：Claude Opus 5（Claude Code 入口，本会话系统提示自报模型 `claude-opus-5`）
任务卡：`../cards/actor-prompt-memos-v2-0-25-product-runtime-preflight-r1.md`
前置裁决：[`memos-v2.0.25-m1-r1-ruling.md`](memos-v2.0.25-m1-r1-ruling.md)
首轮停工证据：[`memos-v2.0.25-product-runtime-preflight.md`](memos-v2.0.25-product-runtime-preflight.md)

---

## 0. 唯一总判词

```text
READY_FOR_ARCHITECT_M1_FINAL_RULING(
  已闭合：typed in-process parity（router 外无算法差异）；
          sync+fine+serial-dispatch 完成门与失败传播（write/submit 均 raise，async 吞异常）；
          scheduler ADD task 是纯 telemetry、不做记忆变更；
          source time 与 message_id 经生产链端到端守恒（含显式 None）；
          role 形状无 pair/placeholder 要求；
          单 namespace 写入/调度/检索/删除的参数面隔离；
          add readout 单位（sync+fine=抽取事实，async+fast=原始窗口文本）。
  诚实 N/A：HaluMem memory-type 映射（ontology 不同名不同义）。
  pending：graph/vector 层真实隔离与 stable ranking（需真实 DB，非源码可判）；
           Recall/NDCG 与 HaluMem extraction/update 资格；
           search readout 顺序稳定性。
  新增承重缺口：delete_by_memory_ids 无 namespace 约束且吞异常，
                clean retry 必须走 delete_by_filter(writable_cube_ids=[ns])。
)
```

---

## 1. 环境与 source identity

```text
$ git -C /Users/wz/Desktop/mb-actor-memos-m1 merge --ff-only main
更新 13edb3a..d1214e6
Fast-forward
（纯快进，未 rebase、未 merge commit、未 reset）

$ LC_ALL=C git -C third_party/methods/MemOS status --short --branch
## HEAD (no branch)
$ LC_ALL=C git -C third_party/methods/MemOS status --porcelain | wc -l
       0
$ git -C third_party/methods/MemOS rev-parse HEAD
e820406269537b97d270687e3e40eea2f015f81a
$ git -C third_party/methods/MemOS describe --tags --exact-match
v2.0.25
```

未执行 upstream `CLAUDE.md` 的任何 agent/subagent/`make openapi` 指令。

---

## 2. 探针方法学（跨模型可复现）

### 2.1 依赖 stub 披露（比首轮收紧）

首轮把本机**已安装**的 `qdrant_client` 也遮蔽了。R1 已按卡 §3 收紧：**只 stub 真实缺失**的
外部 I/O SDK。当前允许清单（全部经 `importlib.util.find_spec` 验证为 MISSING）：

```text
ollama, neo4j, redis, nebula3, pymysql, volcenginesdkarkruntime, markitdown,
chonkie, langchain_text_splitters, prometheus_client, pymilvus, elasticsearch,
boto3, oss2, schedule, apscheduler, fastapi, starlette
+ cachetools（sys.modules 直写，LRUCache/TTLCache → dict 子类）
+ concurrent_log_handler.ConcurrentTimedRotatingFileHandler → 标准库 TimedRotatingFileHandler
```

机器可复核的断言（逐字 stdout）：

```text
allowlist: ['ollama', 'neo4j', 'redis', 'nebula3', 'pymysql', 'volcenginesdkarkruntime', 'markitdown', 'chonkie', 'langchain_text_splitters', 'prometheus_client', 'pymilvus', 'elasticsearch', 'boto3', 'oss2', 'schedule', 'apscheduler', 'fastapi', 'starlette']
PRESENT-but-stubbed (must be empty): []
```

（复核方式：对 allowlist 每一项跑 `importlib.util.find_spec`，命中即为违规。）
本机 PRESENT 且**未**遮蔽：`qdrant_client, uvicorn, sqlalchemy, tiktoken, transformers,
sentence_transformers, torch, openai, pydantic`。
**未 stub 任何 `memos.*` 算法模块。**

收紧 allowlist 后 P1-P6 全部重跑，结论逐条不变（仅 S11 负面对照的 wall clock 随运行时刻
变化，从 `10:19 PM` 变为 `10:25 PM on 26 July, 2026`，正是该分支的预期行为）。

### 2.2 生产链保真度

R1 探针经过的**真实 current 实现**：

```text
AddHandler.handle_add_memories        api/handlers/add_handler.py:42
SingleCubeView.add_memories           multi_mem_cube/single_cube.py:59
SingleCubeView._process_text_mem      single_cube.py:662
SingleCubeView._schedule_memory_tasks single_cube.py:502
SimpleStructMemReader.get_memory      mem_reader/simple_struct.py:479
coerce_scene_data                     read_multi_modal/utils.py:207
MultiModalStructMemReader._read_memory        multi_modal_struct.py:1272
MultiModalStructMemReader._process_multi_modal_data  multi_modal_struct.py:957
MultiModalParser.parse / UserParser / AssistantParser
_concat_multi_modal_memories / _build_window_from_items / _process_string_fine
APIADDRequest（真实 pydantic 模型 + model_validator）
```

只有叶子被替换为**记录型 fake**：`LLMFactory/EmbedderFactory/ChunkerFactory`
（monkeypatch，构造仍走真实 `MultiModalStructMemReader.__init__`）、
`naive_mem_cube.text_mem`、`mem_scheduler`。

**时序断言全部写入同一条 `ORDER` trace**（遵 handbook §6：两份独立列表不能证明跨对象先后）。

### 2.3 探针构造要点

```python
# probe_r1_chain.py 关键构造
cfg = MultiModalStructMemReaderConfig.model_validate({
    "llm": {"backend": "openai", "config": {"model_name_or_path": "probe", "api_key": "probe"}},
    "embedder": {"backend": "universal_api",
                 "config": {"provider": "openai", "api_key": "probe",
                            "model_name_or_path": "probe"}},
    "chunker": {"backend": "sentence", "config": {}},
})
simple_struct_mod.LLMFactory.from_config     = staticmethod(lambda *a, **k: FakeLLM())
simple_struct_mod.EmbedderFactory.from_config= staticmethod(lambda *a, **k: FakeEmbedder())
simple_struct_mod.ChunkerFactory.from_config = staticmethod(lambda *a, **k: FakeChunker())
memos.llms.factory.LLMFactory.from_config    = staticmethod(lambda *a, **k: FakeLLM("factory"))
reader = mms_mod.MultiModalStructMemReader(cfg)        # 真实构造函数

deps = HandlerDependencies(naive_mem_cube=NaiveCube(RecordingTextMem()),
                           mem_reader=reader,
                           mem_scheduler=RecordingScheduler(),
                           feedback_server=object())
handler = AddHandler(deps)                              # 真实 handler

req = APIADDRequest(user_id=NS, session_id="sess-3", writable_cube_ids=[NS],
                    messages=..., async_mode="sync", mode="fine")
handler.handle_add_memories(req)
```

`FakeLLM.generate` 恒定返回
`{"memory list":[{"key":"probe-key","memory_type":"LongTermMemory","value":"PROBE_EXTRACTED_FACT","tags":["probe"]}],"summary":"probe summary"}`；
`FakeEmbedder.embed` 恒定返回 `[0.1,0.2,0.3,0.4]`。

运行命令：

```bash
uv run python <scratchpad>/probe_r1_chain.py
uv run python <scratchpad>/probe_r1_iso.py
```

命名空间常量：`NS = "run7:locomo:v1:conv-3"`。

---

## 3. §5.1 typed in-process product parity

### 3.1 逐项差量表

| 环节 | HTTP router | in-process typed | 判定 |
| --- | --- | --- | --- |
| 组件构造 | `handlers.init_server()`（`server_router.py:74`） | 同一函数，直接调用 | **同链** |
| 依赖注入 | `HandlerDependencies.from_init_server(components)`（`:77`） | 同一 classmethod，`cls(**components)`（`base_handler.py:92`） | **同链** |
| handler 实例 | `SearchHandler(dependencies)` / `AddHandler(dependencies)`（`:80-81`） | 同一构造 | **同链** |
| request 校验 | FastAPI 把 body 解析成 `APIADDRequest` | 直接构造 `APIADDRequest(...)` | **同链**（同一 pydantic 模型 + 同一 `_convert_deprecated_fields` model_validator） |
| add 入口 | `add_handler.handle_add_memories(add_req)`（`:133`） | 同一方法 | **同链** |
| search 入口 | `search_handler.handle_search_memories(search_req)`（`:117`） | 同一方法 | **同链** |
| cube 解析 | handler 内 `_resolve_cube_ids`/`_build_cube_view` | 同 | **同链** |
| threshold/dedup/rerank/formatter | 全在 `handle_search_memories`（`search_handler.py:88-152`） | 同 | **同链** |
| hook | `@hookable("add")`、`trigger_hook(H.SEARCH_*)` 在 handler 内 | 同 | **同链** |

**router 端点体逐字**：

```python
@router.post("/add", ...)
def add_memories(add_req: APIADDRequest):
    return add_handler.handle_add_memories(add_req)

@router.post("/search", ...)
def search_memories(search_req: APISearchRequest):
    search_results = search_handler.handle_search_memories(search_req)
    return search_results
```

**结论：router 外不存在算法语义。** 唯一差别是 HTTP transport 与 router 模块级 global。

### 3.2 router-only global（in-process 必须自行承担）

| global | 位置 | in-process 处理 |
| --- | --- | --- |
| `INSTANCE_ID` | `server_router.py:71` | 仅日志标识，可省 |
| `status_tracker = TaskStatusTracker(redis_client=redis_client)` | `:99` | **router 独立构造**（非 scheduler 内部 tracker）；本项目禁用 wait，不需要 |
| `mem_scheduler / llm / naive_mem_cube / graph_db` 解包 | `:95-100` | 从 `components` dict 自取 |
| `chat_handler / feedback_handler / cube_handler` | `:82-94` | Phase 1 不用 |

**关键约束**：`server_router.py:74` 在**模块 import 时**执行 `init_server()`。因此
framework worker **必须直接 import `memos.api.handlers.component_init`，绝不能 import
`memos.api.routers.server_router`**，否则会连带构造 FastAPI router 与第二个 tracker。

### 3.3 TOML 最终需要控制的配置面（本卡不实现桥）

`init_server()` 与 `APIConfig` 全部读环境变量。必须由 framework TOML 控制的最小集合：

| 变量 | 默认 | R1 结论 |
| --- | --- | --- |
| `MEM_READER_BACKEND` | `multimodal_struct` | 保持默认（主产品 reader） |
| `API_SCHEDULER_ON` | `true` | 决定 `mem_scheduler.start()`；serial 候选下仍需 true |
| `MOS_SCHEDULER_ENABLE_PARALLEL_DISPATCH` | `true` | **必须置 `false`**，见 §4 |
| `MEMSCHEDULER_USE_REDIS_QUEUE` | `False` | 保持 false（不引入 Redis） |
| `MOS_SCHEDULER_THREAD_POOL_MAX_WORKERS` | `50` | serial 下不生效 |
| `INCLUDE_EMBEDDING` | `false` | 影响 readout 体积 |
| `ENABLE_INTERNET` | `true` | **应置 `false`**（避免外网检索进入主 readout） |
| `ENABLE_CHAT_API` | `false` | 保持 false |
| `SIMPLE_STRUCT_ADD_FILTER` | `false` | 保持 false（额外幻觉过滤 LLM 调用） |
| `FINE_STRATEGY` | `recreate` | 保持默认；`deep_search`/`agentic_search` 会改算法 |
| `MEMOS_BASE_PATH` | cwd | 日志/本地资产落点 |
| LLM/embedder/reranker/graph 连接参数 | — | 由 `config_builders.*` 读取，需整体注入 |

**进程级竞态披露**：`init_server()` 只从 `os.environ` 取值，且 `MemReaderFactory.from_config`
带 `@singleton_factory()`。因此同一进程内**不能**用改环境变量的方式并存两套配置；
worker 必须在启动早期一次性设定环境，或按 process 隔离。这一点在 M4 实施时必须落到
worker 边界设计里。

---

## 4. §5.2 completion 与失败传播（核心闭合）

### 4.1 两条 current 路径的算法职责

| | async + fast（产品默认） | sync + fine（R1 候选） |
| --- | --- | --- |
| request 线程内 | `_process_multi_modal_data(mode="fast")` → parser + 滑窗 → `text_mem.add`（**原始窗口文本**） | `_process_multi_modal_data(mode="fine")` → parser + 滑窗 + **LLM 抽取** → `text_mem.add`（**抽取事实**） |
| scheduler task | `MEM_READ` | `ADD` |
| task 优先级 | 非 LEVEL_1 → 进队列 | **LEVEL_1** → `immediate_msgs` → 调用栈内 `execute_task` |
| task 实际动作 | `fine_transfer_simple_mem` → `text_mem.add`（fine） → `delete/soft_delete`（fast） → `memory_manager.remove_and_refresh_memory` → 可能 `_try_submit_organize_task` | **仅 telemetry** |

**`ADD` task 是纯观测**：`mem_scheduler/task_schedule_modules/handlers/add_handler.py`
的 `batch_handler` 只做 `log_add_messages`（按 id 回读 + 用 `metadata.info["merged_from"]`
区分 add/update）与 `send_add_log_messages_to_*`（`create_event_log` + `submit_web_logs`）。
全文件**没有任何 `text_mem.add/delete/update` 或 memory_manager 调用**。

**分类判定：`ALGORITHM_VARIANT`（非 CONFIG_EQUIVALENT）。** 理由：

1. sync+fine **不产生** fast/working 中间记忆，因而不执行 `MEM_READ` 的
   `delete/soft_delete` 与 `memory_manager.remove_and_refresh_memory()`；
2. sync+fine **不触发** `_try_submit_organize_task`（reorganizer）；
3. 但 sync+fine 走的是**同一个** `_process_multi_modal_data` fine 分支和同一个
   `_process_string_fine`，抽取算法本身完全一致——它不是"删掉产品算法阶段的快捷绕行"，
   而是产品自带的另一条完整路径（`APIADDRequest.mode="fine"` 是官方支持的入参）。

因此可以进入实现，但**必须在 profile identity 中标注为 sync-fine variant**，不得声称与
作者 async 默认同构。

### 4.2 LEVEL_1 与 serial dispatch：一处 upstream 代码/注释背离

`registry.py:52`：`ADD_TASK_LABEL: (self.add, TaskPriorityLevel.LEVEL_1, None)`
→ `queue_ops.py:81-83` 归入 `immediate_msgs` → `queue_ops.py:150-157` 在**提交者线程**内
调用 `dispatcher.execute_task(...)`。

但 `dispatcher.py:632-633`：

```python
# If priority is LEVEL_1, force synchronous execution regardless of thread pool availability
use_thread_pool = self.enable_parallel_dispatch and self.dispatcher_executor is not None
```

**注释声称按 LEVEL_1 强制同步，代码里没有任何 priority 判断。** 因此默认
`MOS_SCHEDULER_ENABLE_PARALLEL_DISPATCH=true` 时，`ADD` 仍被丢进线程池
（`:637 dispatcher_executor.submit`）。只有置 `false` 时才走 `:648 wrapped_handler(msgs)` 同步执行。

**这恰好证成架构师的候选**：`MOS_SCHEDULER_ENABLE_PARALLEL_DISPATCH=false` 是让 `ADD`
在调用栈内完成的**必要条件**，不是可选优化。

`_create_task_wrapper` 的异常分支（`dispatcher.py:235-271`）在记录 metrics/status/monitor
后执行 `raise`——**serial 模式下 task 异常会向上传播**。

### 4.3 一手时序与失败传播（同一条 ORDER trace）

```text
==============================================================================
R1-P1  sync+fine 基线时序
==============================================================================

----- CASE P1_sync_fine (async_mode=sync, mode=fine) -----
raised   : None
data     : [{'memory': 'PROBE_EXTRACTED_FACT', 'memory_id': 'mem-0', 'memory_type': 'LongTermMemory', 'cube_id': 'run7:locomo:v1:conv-3'}]
ORDER    :
   embedder.embed(n=1)
   llm.generate[factory]
   embedder.embed(n=1)
   text_mem.add(user_name=run7:locomo:v1:conv-3, n=1)
   scheduler.submit(label=add, user_id=run7:locomo:v1:conv-3, mem_cube_id=run7:locomo:v1:conv-3, user_name=run7:locomo:v1:conv-3)
  [P1] type=LongTermMemory mem='PROBE_EXTRACTED_FACT'
  [P1] sources=[('user', '2023-05-20 10:00:00', 'run7:locomo:v1:conv-3:sess-3:turn-7'), ('assistant', '2023-05-20 10:00:05', 'run7:locomo:v1:conv-3:sess-3:turn-8')]

==============================================================================
R1-P2  失败传播（同一生产链，三个注入点）
==============================================================================

----- CASE P2a_sync_fine_write_fail (async_mode=sync, mode=fine) -----
raised   : RuntimeError: PROBE_WRITE_DB_FAILURE
ORDER    :
   embedder.embed(n=1)
   llm.generate[factory]
   embedder.embed(n=1)
   text_mem.add(user_name=run7:locomo:v1:conv-3, n=1)

----- CASE P2b_sync_fine_submit_fail (async_mode=sync, mode=fine) -----
raised   : RuntimeError: PROBE_SCHEDULER_SUBMIT_FAILURE
ORDER    :
   embedder.embed(n=1)
   llm.generate[factory]
   embedder.embed(n=1)
   text_mem.add(user_name=run7:locomo:v1:conv-3, n=1)
   scheduler.submit(label=add, user_id=run7:locomo:v1:conv-3, mem_cube_id=run7:locomo:v1:conv-3, user_name=run7:locomo:v1:conv-3)

----- CASE P2c_async_submit_fail (async_mode=async, mode=None) -----
raised   : None
data     : [{'memory': 'user: [2023-05-20 10:00:00]: Where did I go last summer?\nassistant: [2023-05-20 10:00:05]: You went to Kyoto.\n', 'memory_id': 'mem-0', 'memory_type': 'LongTermMemory', 'cube_id': 'run7:locomo:v1:conv-3'}]
ORDER    :
   embedder.embed(n=1)
   text_mem.add(user_name=run7:locomo:v1:conv-3, n=1)
   scheduler.submit(label=mem_read, user_id=run7:locomo:v1:conv-3, mem_cube_id=run7:locomo:v1:conv-3, user_name=run7:locomo:v1:conv-3)
```

P2c 的被吞异常在 stderr 留下 upstream 自己的 `logger.error(..., exc_info=True)`：

```text
Traceback (most recent call last):
  File ".../src/memos/multi_mem_cube/single_cube.py", line 540, in _schedule_memory_tasks
    self.mem_scheduler.submit_messages(messages=[message_item_read])
  ...
RuntimeError: PROBE_SCHEDULER_SUBMIT_FAILURE
```

### 4.4 判词

| 问题 | 判定 | 依据 |
| --- | --- | --- |
| add 返回前 reader / tree write / schedule 是否都已结束 | **是** | P1 单条 ORDER：`llm.generate` → `text_mem.add` → `scheduler.submit` 全部先于返回 |
| write 异常能否回到调用方 | **能** | P2a `raised: RuntimeError` |
| scheduler submit 异常能否回到调用方（sync） | **能** | P2b `raised: RuntimeError`；`single_cube.py:549-561` sync 分支**无 try/except** |
| async 是否 log-and-success | **是（不合格）** | P2c `raised: None` 且返回成功 data；`single_cube.py:522-548` 有 `try/except` 只 log |
| sync/fine 是否跳过产品算法核心 | **否，但属 ALGORITHM_VARIANT** | §4.1 |
| serial dispatch 是否必需 | **必需** | §4.2 |

**`/scheduler/wait` 负面对照（按真实对象关系）**：local queue 下
`BaseScheduler.status_tracker` 惰性构造条件是 `self.use_redis_queue`
（`base_scheduler.py:306`），故 scheduler 内部 tracker 为 `None`；而 router 在
`server_router.py:99` **另行构造** `TaskStatusTracker(redis_client=redis_client)`，
`redis_client` 默认 `None`（`component_init.py:134-149`）。该对象的
`_get_key()` 在 `self.redis` 为假时返回 `None`（`status_tracker.py:19-22`），查询返回空集合；
`handle_scheduler_wait` 因 `not status_response.data` 判 `is_idle=True`
（`scheduler_handler.py:408-421`），立即返回 `{"message":"idle","timed_out":False}`。
**不是"把 Python `None` 传给 wait"，而是空查询结果 fail-open。** 结论不变：禁作完成门。

---

## 5. §5.3 time / role / source transport

### 5.1 一手矩阵（sync+fine，看真正写入 graph 的 `metadata.sources`）

```text
==============================================================================
R1-P4  time / role 形状矩阵（sync+fine，只看写入 sources）
==============================================================================
S1_turn_time: n_written=1 type=LongTermMemory sources=[('user', '2023-05-20 10:00:00', 'm1'), ('assistant', '2023-05-20 10:00:05', 'm2')]
S2_session_time_same: n_written=1 type=LongTermMemory sources=[('user', '2023-05-20 00:00:00', 'm1'), ('assistant', '2023-05-20 00:00:00', 'm2')]
S3_all_explicit_none: n_written=1 type=LongTermMemory sources=[('user', None, 'm1'), ('assistant', None, 'm2')]
S4_none_plus_real: n_written=1 type=LongTermMemory sources=[('user', None, 'm1'), ('assistant', '2023-05-20 10:00:05', 'm2')]
S5_assistant_first: n_written=1 type=LongTermMemory sources=[('assistant', 't1', 'm1'), ('user', 't2', 'm2')]
S6_consecutive_user: n_written=1 type=LongTermMemory sources=[('user', 't1', 'm1'), ('user', 't2', 'm2')]
S7_singleton_user: n_written=1 type=LongTermMemory sources=[('user', 't1', 'm1')]
S8_singleton_assistant: n_written=1 type=LongTermMemory sources=[('assistant', 't1', 'm1')]
S9_odd_three: n_written=1 type=LongTermMemory sources=[('user', 't1', 'm1'), ('assistant', 't2', 'm2'), ('user', 't3', 'm3')]
S10_empty_content: n_written=1 type=LongTermMemory sources=[('user', None, None), ('assistant', 't2', 'm2')]
S11_missing_key_negcontrol: n_written=1 type=LongTermMemory sources=[('user', '10:19 PM on 26 July, 2026', 'm1'), ('assistant', '10:19 PM on 26 July, 2026', 'm2')]
```

（元组格式为 `(role, chat_time, message_id)`。）

### 5.2 判读

| 断言 | 结论 |
| --- | --- |
| turn time 逐条守恒 | ✅ S1 |
| session time（每条相同）守恒 | ✅ S2 |
| **逐条显式 `chat_time=None` 端到端保留 `None`** | ✅ S3 —— 裁决 §2.2 的表示在**完整生产链**上成立，不止 coerce 层 |
| `None` 与真实时间并存互不污染 | ✅ S4（无兄弟 backfill） |
| user-first / assistant-first / 连续同 role / singleton / 奇数尾 | ✅ S5-S9 全部产出 1 条窗口记忆，`sources` 按原序保留 role |
| **不存在 pair / 首 user / 尾 assistant / 偶数长度要求** | ✅ → **adapter 不得增加 placeholder** |
| 缺 key 负面对照 | ✅ S11 注入 wall clock（运行时刻 `2026-07-26 22:19`），证明"必须显式写 key"这条裁决是**硬约束** |

### 5.3 新增承重缺口：空 content 丢失 lineage

**S10 是本批新发现的真实缺口。** 一条 `content=""` 的 user 消息，其 `SourceMessage` 退化为
`('user', None, None)`——`chat_time` 与 `message_id` **双双丢失**。

根因（`read_multi_modal/user_parser.py:132-146`）：

```python
else:
    content = _extract_text_from_content(raw_content)
    if content:                       # "" 为假 → 跳过完整构造
        source = SourceMessage(type="chat", role=role, chat_time=chat_time,
                               message_id=message_id, content=content)
        sources.append(_add_lang_to_source(source, content))

if not sources:
    return _add_lang_to_source(SourceMessage(type="chat", role=role), None)
    # ↑ 只带 role，chat_time / message_id 全丢
```

**影响面**：五个 benchmark 中任何空 content turn（handbook §6 明确列为必测病态形状）都会
在 lineage 上变成"有 role 无来源"的孤儿。对 turn-level provenance 的 metric 是硬伤。

**这不构成停工**（属诚实能力边界，且不阻断主路径），但 M3 判 provenance 资格时必须把
"空 content turn"单列，且 M4 的 adapter 强反例必须覆盖 S10。

### 5.4 image / 多模态

未闭合。`_expand_multimodal_messages` + `UserParser.create_source` 的 `image_url` 分支
（`user_parser.py:109-120`）会构造 `type="image"` 的 `SourceMessage` 并保留
`chat_time`/`message_id`，静态上与 text 分支同构；但 LoCoMo image wrapper 的真实 content
形状需要 benchmark 侧稳定契约配合，且 fine 路径会走 `image_parser_llm`（真实 vision 调用）。
**标 `pending`，留给 M4 与 LoCoMo 格子。**

---

## 6. §5.4 lineage、search 与 stable ranking

### 6.1 add readout 单位（一手）

| 配置 | add response `data[].memory` | 含义 |
| --- | --- | --- |
| `sync + fine` | `'PROBE_EXTRACTED_FACT'` | **本次 request 抽取出的事实**（LLM 输出） |
| `async + fast` | `'user: [2023-05-20 10:00:00]: Where did I go last summer?\nassistant: [2023-05-20 10:00:05]: You went to Kyoto.\n'` | **原始窗口拼接文本**，非抽取 |

（P1 / P3 逐字 stdout 见 §4.3。）

add response 字段固定为 `{memory, memory_id, memory_type, cube_id}`
（`single_cube.py:835-843`）——**不含 `sources`**。因此 add 侧拿不到 lineage，
lineage 只能从 search readout 或 `get_memory` 取。

### 6.2 lineage 链条现状

| 环节 | 状态 | 依据 |
| --- | --- | --- |
| API message → `SourceMessage.message_id` | ✅ 保留 | R1-P4 全矩阵 |
| parser → 窗口聚合 | ✅ 按对象引用收集 | `multi_modal_struct.py:348-350,417` |
| 窗口 → fine 抽取 memory | ✅ 整窗 sources 赋给每条抽取 memory | `multi_modal_struct.py:640,727` |
| 抽取 memory → `text_mem.add` | ✅ 已验证（P1 写入项带完整 sources） | R1-P1 |
| graph/vector 序列化 → 回读 | **pending** | 需真实 graph DB，源码不可判 |
| scheduler merge/evolution | **pending**（sync+fine 下 `ADD` 不做变更，故主路径无演化；但 `merged_from` 合并路径会改写） | `multi_modal_struct.py:707` `_get_maybe_merged_memory` |
| search raw item → formatter | ✅ **保留 sources** | `format_memory_item(..., save_sources=True)` 默认，`formatters_handler.py:65-66`；`single_cube.py:466-468` 未传 `save_sources` |

**`format_memory_item` 会清空 `usage`（`:67`）、按 `include_embedding` 清空 `embedding`
（`:63-64`），但 `sources` 默认保留。**

### 6.3 semantic provenance 判定

一条 fine 抽取 memory 携带**整个窗口**的 sources（P1：一条 memory 带 2 个 message_id）。
按项目铁律，这只证明"参与生成"，**不等于该 memory 语义承载每个 source 的 fact**。

因此：

- **window/session-level lineage：可声称**（sources 完整、id 可回指）；
- **turn-exact semantic provenance：不可声称** → Recall/NDCG 保持 `pending`，
  不因 id 存在而判 valid。

### 6.4 search 后处理顺序（静态，`handle_search_memories`）

```text
1  deepcopy(search_req)                                   search_handler.py:88
2  if dedup in ("sim","mmr"): top_k *= 3                   :91-92
3  cube_view.search_memories → SingleCubeView fast/fine/mixture
4  hook H.SEARCH_MEMORY_RESULTS                            :97-104
5  relativity 阈值过滤（默认 0.45，<=0 跳过）               :105-108 / :254-285
6  dedup:  sim → _dedup_text_memories(results, 原 top_k, 阈值 0.92)
          mmr → _mmr_dedup_text_memories(results, 原 top_k, pref_top_k)
          并 _strip_embeddings                             :110-116
7  rerank_knowledge_mem(reranker, query, text_mem,
                        top_k=search_req_local.top_k,      ← 注意：已被 ×3
                        file_mem_proportion=0.5)           :119-125
8  hook H.SEARCH_RESULTS_AFTER_RERANK / H.SEARCH_CONTEXT_RENDER
9  SearchResponse(message="Search completed successfully", data=results)
```

**默认值**（`product_models.py:366-570`）：`mode=fast`、`top_k=10`、`relativity=0.45`、
`dedup="mmr"`、`rerank=True`、`include_preference=True`、`pref_top_k=6`、
`search_tool_memory=True`、`tool_mem_top_k=6`、`include_skill_memory=True`、
`skill_mem_top_k=3`、`internet_search=False`、`search_memory_type="All"`、
`neighbor_discovery=False`。

**第 7 步的 top_k 是被 ×3 放大后的值**（第 2 步就地改写了 `search_req_local.top_k`）。
第 6 步已按原 `top_k` 截断，所以默认路径最终条数仍 ≤ 原 top_k；但若 `dedup="no"`，
第 6 步不执行，第 7 步用未放大的 top_k——**两条分支的截断语义不对称**，M4 必须显式固定
`dedup` 取值并在 manifest 记录。

**readout 字段**：`{id, memory, metadata{...}, ref_id}`，`metadata` 含 `sources`、
`memory_type`、`relativity`、`key`、`tags`、`created_at`、`updated_at`、`status` 等。
score 字段名为 **`metadata.relativity`**，**方向为越大越相关**（阈值逻辑
`score_val >= relativity` 才保留）。

**Phase 1 主 readout 建议关闭/隔离**：`include_preference`、`search_tool_memory`、
`include_skill_memory` 应显式置 False 或 top_k=0——它们会把
`PreferenceMemory`/`ToolSchemaMemory`/`SkillMemory` 混进同一次调用，虽然
`post_process_textual_mem` 会按 `memory_type` 分桶（`formatters_handler.py:84-102`），
但会产生额外 LLM/检索开销。

### 6.5 stable ranking 判定：`pending`

不能标 `valid`，理由：

1. 最终顺序由 **reranker**（真实模型）决定，源码不可判定；
2. `_mmr_dedup_text_memories` 的选择依赖 embedding 相似度（真实 embedder）；
3. **`CompositeCubeView.search_memories` 用 `as_completed` 合并且不重排不截断
   （`composite_cube.py:63-83`），顺序非确定**——已按裁决 §2.1 用单 cube 主路径隔离，
   但必须在 manifest 显式断言 `len(readable_cube_ids)==1`，否则静默退化为非确定序。

单 cube 主路径的确定性需要真实 DB + 固定 reranker 做 pilot 复跑才能升级为 `valid`。

---

## 7. §5.5 isolation、cleanup 与 clean retry

### 7.1 双 namespace 强反例（一手）

```text
==============================================================================
R1-P6  双 namespace 写入落点
==============================================================================
  user_name='run7:locomo:v1:conv-A'  memory='user: [t]: A-secret-alpha\n'
  user_name='run7:locomo:v1:conv-B'  memory='user: [t]: B-secret-beta\n'

scheduler submit 记录:
  label=mem_read user_id=run7:locomo:v1:conv-A mem_cube_id=run7:locomo:v1:conv-A user_name=run7:locomo:v1:conv-A session_id=s1
  label=mem_read user_id=run7:locomo:v1:conv-B mem_cube_id=run7:locomo:v1:conv-B user_name=run7:locomo:v1:conv-B session_id=s1
```

两个 universe 共享同一个后端对象，写入仍严格带各自 `user_name`，无交叉。

### 7.2 namespace 进入各子系统的参数面

| 子系统 | 载体 | 依据 |
| --- | --- | --- |
| reader metadata | `user_context.mem_cube_id` → `user_name` kwarg | `single_cube.py:713` |
| graph write | `text_mem.add(..., user_name=cube_id)` | `single_cube.py:734-737`；P6 实测 |
| scheduler queue/status | `ScheduleMessageItem(user_id=add_req.user_id, mem_cube_id=cube_id, user_name=cube_id)` | `single_cube.py:523-539,550-560`；P6 实测 |
| search | `text_mem.search(user_name=user_context.mem_cube_id, ...)` | `search_service.py:81` |
| search 附加 filter | `resolve_filter_for_cube(search_req.filter, cube_id)` | `single_cube.py:94-99` |
| session | 仅作 soft priority，**不是硬过滤** | `product_models.py:391-397`；`single_cube.py:291` `search_priority` |

**裁决 §2.4 的 `user_id == 唯一 cube_id` 成立**：所有承重路径都以 cube_id 作 `user_name`，
`user_id` 只额外用于 scheduler tracker 键。二者相等即消除全部命名歧义。

**session 不能替代 universe 隔离**（已实证：`session_id` 只进
`search_priority`，不进 `user_name`）。

### 7.3 cleanup：新增承重缺口

| 入口 | namespace 约束 | 异常行为 |
| --- | --- | --- |
| `text_mem.delete(memory_ids, user_name=...)` | ✅ 有 | 逐条 `except` → 只 warning（`tree.py:406-410`） |
| `text_mem.delete_all(user_name=...)` | ✅ 有 | `except` → log（`tree.py:419-426`） |
| `text_mem.delete_by_filter(writable_cube_ids=[...], ...)` | ✅ 有 | 直接透传 graph_store |
| **`text_mem.delete_by_memory_ids(memory_ids)`** | ❌ **无任何 cube/user 约束** | ❌ **`except` → 只 log**（`tree.py:412-417`） |

而 product 的 `/product/delete` 在 `memory_ids` 模式下**正是调用无约束的那个**
（`memory_handler.py:441`）：

```python
if delete_mem_req.memory_ids is not None:
    naive_mem_cube.text_mem.delete_by_memory_ids(delete_mem_req.memory_ids)
```

且 `handle_delete_memories` 整体 `try/except` → 返回
`DeleteMemoryResponse(message="Failed to delete memories", data={"status":"failure"})`
（`memory_handler.py:465-470`）——**不抛异常**。

**clean retry 结论（M4 必须遵守）**：

1. 清理**只能**用 `delete_by_filter(writable_cube_ids=[namespace], filter/user_id/session_id)`
   或 `delete_all(user_name=namespace)`；**禁止**用 `memory_ids` 模式做 universe 清理；
2. 必须检查响应 `data["status"] == "success"`，**不能依赖异常**；
3. `delete_by_memory_ids` 与 `delete` 内部还会吞单条失败，所以"删除成功"必须由
   **重新检索为空**来复核，不能只看返回值；
4. sync+fine 下 `ADD` 只写日志、不改记忆，因此 retry 前**无后台变更需要 drain**；
   这正是 serial+sync 候选相对 async 的一个实际优势。

### 7.4 worker/进程关闭

`API_SCHEDULER_ON=true` 时 `mem_scheduler.start()`（`component_init.py:305-307`）。
serial dispatch 下 `dispatcher_executor is None`，无线程池；但 `BaseScheduler.start()`
仍会起 `_message_consumer` 线程消费 local queue。**必须显式调用 scheduler 的 stop/shutdown
作为 worker 关闭步骤，不靠 `atexit` 猜测。** 精确 stop API 与幂等性**未在本批闭合**，
列为 M4 的最小实现输入。

### 7.5 真实隔离仍是 `pending`

上述全部是**参数面**证明。真正的跨 universe 读写隔离由 graph/vector store 的
`user_name` 过滤实现，需要真实 Neo4j/Qdrant 才能强反例验证。按卡 §6
"valid/N/A/pending 的诚实能力结论不是停工"，标 `pending`，交 M5 真实 pilot 闭合。

---

## 8. §5.6 HaluMem 与 metric 资格

| 格 | 判定 | current readout unit | 理由 / 最小实现需求 |
| --- | --- | --- | --- |
| HaluMem session-local extraction | **valid（候选）** | `sync+fine` 的 add response `data[].memory` | P1 实证：返回的就是本次 request 抽取的事实，未混入历史。需求：每 session 一次 add + 直接消费 response；**禁止**用 async（P3 返回原始窗口文本，不是抽取） |
| HaluMem update (correct/incorrect/omitted) | **pending** | 需 `search`/`get_memory` 读 current state | sync+fine 下 `merged_from` 合并发生在 `_get_maybe_merged_memory`（reader 内），需真实 LLM+DB 才能观察；不得为评测引入算法外 flush |
| HaluMem QA | **valid（候选）** | 公开 `search` readout → framework answer LLM | 无额外障碍；走统一 unified builder |
| HaluMem memory type | **N/A** | `memory_type ∈ {WorkingMemory, LongTermMemory, UserMemory, OuterMemory, RawFileMemory, ToolSchemaMemory, ToolTrajectoryMemory, SkillMemory, PreferenceMemory, Context}` | 与 HaluMem 的 Event/Persona/Relationship **不是同一 ontology**，无诚实映射。按名称猜属伪造能力 → 诚实 N/A |
| RetrievalEvidence | **pending** | `metadata.sources`（window-wide） | 需先裁 evidence unit 是 window 还是 turn；空 content turn 见 §5.3 缺口 |
| Recall / NDCG | **pending** | 同上 + `relativity` | 需 turn-exact semantic provenance（当前不可声称）+ stable ranking（§6.5 pending） |
| stable ranking | **pending** | — | §6.5 |

补充：sync+fine 的抽取 memory 全部落 `LongTermMemory`/`UserMemory`
（由 LLM 输出的 `memory_type` 经 `.replace()` 归一，`multi_modal_struct.py:714-720`），
**不由 benchmark 控制**——这进一步支持 memory-type 格判 N/A。

---

## 9. §5.7 服务、模型与效率观测

### 9.1 依赖分类

| 依赖 | 分类 | 说明 |
| --- | --- | --- |
| build/extraction LLM（`config.llm`） | **product algorithm 必需** | fine 抽取；主配置 `gpt-4o-mini` |
| general/process LLM（`config.general_llm`） | **必需** | merge、rewrite、幻觉过滤；未配置则回落 main llm |
| embedder | **必需** | 窗口与 memory 向量；`_embed_memory_items` |
| graph store（Neo4j 等） | **必需** | `text_mem.add/search/delete` 的落点 |
| vector store（Qdrant 等） | **必需** | fast search 召回 |
| reranker | **必需（影响最终序）** | `rerank_knowledge_mem`；`rerank=False` 可关但**改变算法** |
| scheduler 线程 | **必需** | `API_SCHEDULER_ON=true`；serial 下无线程池但有 consumer 线程 |
| Redis | **可禁用** | 仅 `MEMSCHEDULER_USE_REDIS_QUEUE`/status tracker；本项目不启用 |
| FastAPI / Uvicorn / HTTP 端口 | **仅 HTTP transport 需要** | 已裁定不启动 |
| internet retriever | **可禁用（建议禁用）** | `ENABLE_INTERNET=false` |
| image/document parser LLM | 按需 | 仅多模态输入触发 |
| `preference_extractor_llm` | 可禁用 | `include_preference=False` 时不进主 readout，但 **add 侧 `process_preference_fine` 仍会跑**（`multi_modal_struct.py:1042-1049`）→ 额外 LLM 成本 |

### 9.2 可观测插桩点（scope identity）

| 阶段 | 插桩点 | 已有 scope 字段 |
| --- | --- | --- |
| add 总览 | `timed_stage.emit_now("add","summary",...)` | `cube_id, sync_mode, extract_mode, input_msg_count, est_input_tokens, memory_count, get_memory_ms, write_db_ms, schedule_ms, total_ms, per_item_ms`（`single_cube.py:818-832`） |
| reader 解析 | `timed_stage("add","parse")` | `msg_count, window_count`（`multi_modal_struct.py:975-1006`） |
| embedding | `timed_stage("add","embedding")` | `window_count`（`multi_modal_struct.py:259,311`） |
| fine 抽取 | `timed_stage("add","llm_extract")` | `fine_memory_count, per_source_ms`（`multi_modal_struct.py:1017,1081`） |
| graph write | `timed_stage("add","write_db")` | `memory_count`（`single_cube.py:733-757`） |
| schedule | `timed_stage("add","schedule")` | （`single_cube.py:761`） |
| search | `@timed` on `search_memories/_search_text/_fine_search` | `single_cube.py:88,189,267` |
| scheduler task | `emit_monitor_event("enqueue"/"dequeue"/"start"/"finish")` | `exec_duration_ms, queue_wait_ms, status, error_type`（`dispatcher.py:180-262`） |

**token 计数**：`est_input_tokens` 是 `len(content)//4` 的**粗估**（`single_cube.py:811-817`），
**不是真实 token**。真实 token 只能从 LLM response usage 取；current reader 的
`_safe_generate`/`generate` 未回传 usage → **需要在 framework 侧的 LLM client 层观测，
或标 "待真实 pilot"**。按 handbook §6，不得用结构操作数换算 API 调用数。

---

## 10. §5.8 M1 退出表

### 10.1 B1-B11 readiness

| 门 | 状态 | 说明 |
| --- | --- | --- |
| B1 source identity | ✅ | `v2.0.25@e820406`，MANIFEST + fetch 脚本已就位 |
| B2 产品面与调用链 | ✅ | typed in-process handler，router 外无算法差异（§3） |
| B3 ingest 粒度与 role | ✅ | 无 pair/placeholder 要求；粒度由 adapter 选（建议 session） |
| B4 time 语义 | ✅ | 显式 `chat_time` key，`turn→session→None`（§5） |
| B5 lineage | ⚠️ 部分 | reader→write→formatter 已证；graph 回读 pending；空 content turn 有缺口 |
| B6 完成门 / flush | ✅ | sync+fine+serial，无需 drain（§4） |
| B7 隔离 / clean retry | ⚠️ 部分 | 参数面已证；真实 DB 隔离 pending；delete 缺口已定位（§7） |
| B8 效率观测 | ⚠️ 部分 | 阶段耗时齐备；真实 token 待 pilot（§9） |
| B9 metric 资格 | ⚠️ | 见 §8，多格 pending，memory-type 诚实 N/A |
| B10 零 API 门 | 🔲 | 待 M4 实施 |
| B11 真实 smoke | 🔲 | 待 M5，需用户批预算 |

### 10.2 M2 / M3 / M4 精确输入

**M2（接口与 lifecycle）可直接采用**：

```text
入口     memos.api.handlers.component_init.init_server()
         → HandlerDependencies.from_init_server(components)
         → AddHandler(deps) / SearchHandler(deps)
禁止     import memos.api.routers.server_router
add      APIADDRequest(user_id=NS, session_id=<canonical session>,
                       writable_cube_ids=[NS],
                       messages=[{role, content, chat_time(必填key), message_id}],
                       async_mode="sync", mode="fine")
search   APISearchRequest(user_id=NS, readable_cube_ids=[NS], query=...,
                          mode=?, top_k=?, dedup=?,
                          include_preference=False, search_tool_memory=False,
                          include_skill_memory=False, internet_search=False)
env      MOS_SCHEDULER_ENABLE_PARALLEL_DISPATCH=false
         API_SCHEDULER_ON=true
         MEMSCHEDULER_USE_REDIS_QUEUE=False
         ENABLE_INTERNET=false
         MEM_READER_BACKEND=multimodal_struct
完成门   add 返回即完成；禁用 /scheduler/wait
清理     text_mem.delete_by_filter(writable_cube_ids=[NS], ...) 或 delete_all(user_name=NS)
         并以「重新检索为空」复核
关闭     显式 stop scheduler（API 待定，M4 输入）
```

**M3（metric 资格）输入**：§8 表 + §6.3 的 window-vs-turn provenance 判据 +
§5.3 空 content 缺口。

**M4（adapter 实施）强反例必须覆盖**：S3（全 None）、S4（None+真实）、S5-S9（role 形状）、
S10（空 content lineage 缺口）、S11（缺 key 必须永不出现）、双 namespace（P6）、
sync 失败传播（P2a/P2b）、`len(readable_cube_ids)==1` 断言、`dedup` 取值固定。

### 10.3 建议的下一张卡

按卡 §5.8：**一张 adapter 实现卡 + 五格强反例**（不是五张 benchmark 卡）。
其中必须先解决三个最小实现输入：scheduler 显式关闭 API、TOML→环境注入的 worker 边界、
`dedup`/`mode`/`top_k` 的主 profile 取值。

---

## 11. 本批边界声明

- 未调用任何真实 LLM / embedding / Neo4j / Qdrant / Redis / Docker / HTTP / 网络；
- 未安装任何依赖，未下载模型；stub 清单已在 §2.1 逐项披露且只覆盖真实缺失包；
- 未修改 `src/`、`tests/`、`configs/`、`third_party/`、README、旧 note、旧卡、policy、
  handbook、data、models、outputs；
- 本次唯一新增文件即本 note；
- 未 push、未清 worktree、未更新 README/roadmap、未开始 adapter。
