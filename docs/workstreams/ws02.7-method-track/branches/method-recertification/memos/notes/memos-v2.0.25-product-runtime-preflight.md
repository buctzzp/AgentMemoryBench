# MemOS v2.0.25 进程内产品运行时契约 M1 预检（停工回报）

日期：2026-07-26
执行者：Claude Opus 5（Claude Code 入口，本会话系统提示自报模型 `claude-opus-5`）
任务卡：`../cards/actor-prompt-memos-v2-0-25-product-runtime-preflight.md`

> **本 note 是停工回报，不是完整 M1 交付。** 命中任务卡 §7 停工条件第 2 条：
> §3 承重事实中有三条被 current `v2.0.25` 源码实质推翻。按 `actor-handbook.md` §3
> 「承重事实被当前生产源码推翻即已命中停工，即使其余表格还能填完」，保存已完成证据后
> 立即交回架构师，不自行把卡的目标改写成验证意外行为。
>
> 未闭合的 §5.6 search/ranking、§5.7 isolation/clean-retry、§5.8 HaluMem 四格、
> §5.9 服务观测表，以及 §6 要求的完整 B1-B11 矩阵，全部留待 R1。
>
> **架构师强验收勘误（2026-07-26）**：停工判词与三条 active-reader/time/lineage
> 反证成立；§4.2 的最终风险也成立，但首轮把 scheduler 内部 tracker 与 router 独立
> 构造的 tracker 混成了一个对象。current router 无论 Redis 是否启用都会构造
> `TaskStatusTracker(redis_client)`；默认 `redis_client=None` 时，该对象的查询返回空集合，
> 随后 `/scheduler/wait` fail-open 为 idle。下文已按真实对象关系订正。后续裁决见
> [`memos-v2.0.25-m1-r1-ruling.md`](memos-v2.0.25-m1-r1-ruling.md)。

---

## 0. 唯一总判词

```text
BLOCKED(active reader 不是卡 §3 假定的 SimpleStructMemReader 链：
        默认 multimodal_struct 覆写了 _read_memory/窗口/抽取，_iter_chat_windows 为死代码；
        message_id 未在该链被丢弃，显式 chat_time=None 会被保留；
        且 /scheduler/wait 在无 Redis 时静默 fail-open 判 idle。
        以上推翻 §3.1.2 / §3.4.4 / §3.4.2，并使 §5.3/§5.4/§5.5 的探针目标失去前提，
        请架构师重裁 M1 R1 的 reader 基线与 drain 完成门。)
```

---

## 1. Source identity（一手原始输出）

```text
$ LC_ALL=C git -C third_party/methods/MemOS status --short --branch
## HEAD (no branch)

$ LC_ALL=C git -C third_party/methods/MemOS status --porcelain | wc -l
       0

$ git -C third_party/methods/MemOS rev-parse HEAD
e820406269537b97d270687e3e40eea2f015f81a

$ git -C third_party/methods/MemOS describe --tags --exact-match
v2.0.25
```

逐字命中任务卡 §1 的三项要求（`## HEAD (no branch)`、无变更条目、commit/tag 一致）。
nested repo 全程只读：未 checkout / fetch / pull / 安装依赖 / 修改 / 暂存。

隔离环境：

```text
worktree  /Users/wz/Desktop/mb-actor-memos-m1
branch    actor/memos-v2-0-25-product-preflight
base      main @ a1a0ebe  docs(memos): target in-process product parity
```

---

## 2. §3 承重事实逐条复核结论

| 卡条款 | 判定 | 一手锚点 |
| --- | --- | --- |
| §3.1.1 `/product` 初始化 `SimpleTreeTextMemory`，默认 cube `text_mem.backend="tree_text"` | **成立** | `src/memos/api/handlers/component_init.py:229-240`；`src/memos/api/config.py:1222,1303` |
| §3.1.2 active reader 默认 `MEM_READER_BACKEND="multimodal_struct"` → `MultiModalStructMemReader` | **成立（前半）** | `src/memos/api/config.py:656` |
| §3.1.2 「它继承 `SimpleStructMemReader` 的 chat coercion、滑窗与 fine/fast extraction」 | **部分推翻** | 见 §3.1 |
| §3.1.3 官方 LoCoMo/LME 脚本走 `/product/add`、`/product/search` | **成立** | `evaluation/scripts/utils/client.py:154,176` |
| §3.1.4 router 非算法边界；`init_server()` + `HandlerDependencies.from_init_server()` 构造 handler | **成立** | `src/memos/api/routers/server_router.py:74,77,80,81`；`src/memos/api/handlers/base_handler.py:76-92` |
| §3.1.5 手写 `mem_reader.get_memory()+text_mem.add/search()` 会绕开 handler 编排 | **成立** | `src/memos/multi_mem_cube/single_cube.py:702-767` |
| §3.2.1 `MemosApiClient.add()` 仍发 `mem_cube_id`/`conversation_id`，不发 `async_mode` | **成立** | `evaluation/scripts/utils/client.py:150-172` |
| §3.2.2 `APIADDRequest.async_mode` 默认 `"async"`；sync 下未显式 `mode` 才走 fine | **成立** | `src/memos/api/product_models.py:642-659`；`single_cube.py:686-689` |
| §3.2.3 `lme_search.py::memos_search()` 传 `reference_time=` 会 `TypeError` | **成立** | `evaluation/scripts/longmemeval/lme_search.py:44-47` vs `client.py:174` |
| §3.2.4 新字段 `writable_cube_ids` / `readable_cube_ids` | **成立** | `product_models.py:637,377` |
| §3.3.1 `_process_text_mem()` 请求线程内做 extraction + 写图 + submit | **成立** | `single_cube.py:702-767` |
| §3.3.2 async 先 fast 再 `MEM_READ`；sync 先 fine/fast 再 `ADD` | **成立** | `single_cube.py:686-689,520-561` |
| §3.3.3 scheduler 总会初始化；`API_SCHEDULER_ON`（默认 true）决定是否 start，与 `MOS_ENABLE_SCHEDULER` 不同开关 | **成立** | `component_init.py:282-307`；`src/memos/mem_os/core.py:72` |
| §3.3.4 `/scheduler/wait` 按名为 `user_name` 的值查 tracker，需核清真实 key | **已闭合：真实 key 是请求 `user_id`** | 见 §4 |
| §3.3.5 wait 把 `completed/failed/cancelled` 都当 idle | **成立，且比卡描述更危险** | 见 §4 |
| §3.4.1 `coerce_scene_data()` 缺时注入 wall clock；同组部分缺时会backfill | **成立（但触发条件是「缺 key」而非「缺值」）** | 见 §3.2 |
| §3.4.2 显式 `chat_time=None` 仍进 wall-clock 分支，不是合法 preserve-none | **推翻** | 见 §3.2 |
| §3.4.3 `SourceMessage` 支持 `message_id`，user/assistant/system parser 有相关字段 | **成立** | `src/memos/memories/textual/item.py:41` |
| §3.4.4 active chat 路径经 `_iter_chat_windows()` 丢掉 `message_id` | **推翻** | 见 §3.1、§3.3 |
| §3.4.5 fine extraction 把整窗 sources 赋给窗内每条 memory | **成立（在 multimodal 链上同样成立）** | `src/memos/mem_reader/multi_modal_struct.py:727` |

---

## 3. 被推翻的三条：一手证据

### 3.1 §3.1.2 后半 / §3.4.4 —— active reader 不走 `_iter_chat_windows`

`MultiModalStructMemReader` **覆写**了 `_read_memory` 与 `get_scene_data_info`，并改用自己的
窗口聚合与抽取；`SimpleStructMemReader._iter_chat_windows()` 在默认配置下是**死代码**。

调用可达性（一手 grep）：

```text
$ rg -n "_iter_chat_windows" src/memos/
src/memos/mem_reader/multi_modal_struct.py:199:        `_iter_chat_windows` in simple_struct:   <- 仅注释
src/memos/mem_reader/multi_modal_struct.py:280:            # ... (same logic as _iter_chat_windows)  <- 仅注释
src/memos/mem_reader/multi_modal_struct.py:290:                # (same logic as _iter_chat_windows)  <- 仅注释
src/memos/mem_reader/multi_modal_struct.py:301:            # ... (same as _iter_chat_windows)        <- 仅注释
src/memos/mem_reader/simple_struct.py:315:    def _iter_chat_windows(self, ...)              <- 定义
src/memos/mem_reader/simple_struct.py:361:        windows = list(self._iter_chat_windows(...))  <- 唯一真实调用

$ rg -n "_process_chat_data" src/memos/
src/memos/mem_reader/simple_struct.py:359:    def _process_chat_data(...)
src/memos/mem_reader/simple_struct.py:688:            processing_func = self._process_chat_data   <- 仅 SimpleStruct._read_memory
```

`simple_struct.py:361` 在 `_process_chat_data` 内，`_process_chat_data` 只在
`SimpleStructMemReader._read_memory`（`simple_struct.py:688`）被选中；而
`multi_modal_struct.py:1272` 覆写了 `_read_memory`，转而调用
`_process_multi_modal_data`（`multi_modal_struct.py:957`）。因此默认
`MEM_READER_BACKEND="multimodal_struct"` 下 `_process_chat_data` / `_iter_chat_windows`
**永不执行**。

**current active add 链（更正后）**：

```text
AddHandler.handle_add_memories                  api/handlers/add_handler.py:42
  → _build_cube_view → SingleCubeView           add_handler.py:130-160
  → SingleCubeView.add_memories                 multi_mem_cube/single_cube.py:59
  → _process_text_mem                           single_cube.py:662
  → mem_reader.get_memory(...)                  single_cube.py:703
      → SimpleStructMemReader.get_memory        simple_struct.py:479   （继承，未覆写）
      → coerce_scene_data                       simple_struct.py:529
      → MultiModalStructMemReader._read_memory  multi_modal_struct.py:1272 （覆写）
      → get_scene_data_info == 原样返回          multi_modal_struct.py:1257 （覆写）
      → _process_multi_modal_data               multi_modal_struct.py:957
          → _expand_multimodal_messages         multi_modal_struct.py:977
          → multi_modal_parser.parse(逐条消息)   multi_modal_struct.py:984
              → UserParser/AssistantParser.parse_fast
          → _concat_multi_modal_memories(滑窗)   multi_modal_struct.py:1005 / 定义 194
              → _build_window_from_items         multi_modal_struct.py:316
          → [fine] _process_string_fine          multi_modal_struct.py:1021 / 定义 615
                 + _process_tool_trajectory_fine / process_skill_memory_fine / process_preference_fine
          → [fine] per-source process_transfer   multi_modal_struct.py:1066-1079
  → naive_mem_cube.text_mem.add(...)            single_cube.py:734
  → _schedule_memory_tasks                      single_cube.py:762 / 定义 502
```

即：**继承的只有 `get_memory` 外壳与 `coerce_scene_data`；滑窗与 fine/fast extraction 全部被覆写。**

### 3.2 §3.4.2 —— 显式 `chat_time=None` 会被保留

`coerce_scene_data`（`src/memos/mem_reader/read_multi_modal/utils.py:243-259`）的两段循环：

- 探测循环按 **key 是否存在** 取第一个 `chat_time`（`"chat_time" in item`，line 246），
  取到的值可能是 `None`；
- wall clock 只在 `chat_time_value is None` 时**计算**（line 251-254）；
- 注入循环同样按 **key 是否存在** 判断（`"chat_time" not in m`，line 258）。

因此显式写了 `chat_time: None` 的消息**永远不会被 wall clock 覆盖**——wall clock 被算出来，
但只会落到「压根没有该 key」的兄弟消息上。卡 §3.4.2 的「不是合法的 preserve-none」不成立：
**逐条显式 `chat_time=None` 就是 current 产品下的合法 preserve-none 表达。**

### 3.3 §3.4.4 —— `message_id` 在 active 链上不丢

`UserParser.create_source`（`read_multi_modal/user_parser.py:59,91,102,127,140`）与
`AssistantParser` 都从消息取 `message_id` 并写入 `SourceMessage`。该 `SourceMessage` 对象随后：

- 被 `_build_window_from_items` **按对象引用**收集进窗口（`multi_modal_struct.py:348-350,417`）；
- 被 `_process_string_fine` 原样传给 `_make_memory_item(sources=sources)`（`multi_modal_struct.py:640,727`）；
- `_make_memory_item` 直接放进 `TreeNodeTextualMemoryMetadata.sources`（`simple_struct.py:248`）。

全链无字段裁剪。**卡假设的「第一个 drop 点在 chat window source dict」只存在于非 active 的
`simple_struct` 链上。**

---

## 4. §3.3.4 / §3.3.5 闭合结论：drain 完成门比卡描述更弱

### 4.1 tracker 的真实 key 是请求 `user_id`

提交侧（`src/memos/mem_scheduler/base_mixins/queue_ops.py:58-68`）：

```python
self.status_tracker.task_submitted(
    task_id=msg.item_id,
    user_id=msg.user_id,          # ← 注册键
    task_type=msg.label,
    mem_cube_id=msg.mem_cube_id,
    business_task_id=msg.task_id,
)
```

而 `_schedule_memory_tasks` 构造消息时 **同时** 写了两个字段
（`src/memos/multi_mem_cube/single_cube.py:523-539,550-560`）：

```python
ScheduleMessageItem(
    user_id=add_req.user_id,   # ← 进 tracker
    ...
    mem_cube_id=self.cube_id,
    user_name=self.cube_id,    # ← 不进 tracker
)
```

存储键（`src/memos/mem_scheduler/utils/status_tracker.py:19-23`）：

```python
def _get_key(self, user_id: str) -> str:
    if not self.redis:
        return
    return f"memos:task_meta:{user_id}"
```

查询侧（`src/memos/api/handlers/scheduler_handler.py:375-405`）把参数名 `user_name` 原样
当 `user_id` 用：

```python
def handle_scheduler_wait(user_name: str, status_tracker, ...):
    ...
    status_response = handle_scheduler_status(user_id=user_name, status_tracker=status_tracker)
```

**结论：adapter 必须用请求 `user_id` 去 drain，不是 cube id。** 二者只在
`mem_cube_id == user_id` 时才恰好等价——这正是官方 harness 的写法
（`client.py:162` `"mem_cube_id": user_id`），所以官方脚本掩盖了这个差异。若 Phase 1 采用
「每 sample 唯一 cube ≠ user」的隔离方案，照抄官方 wait 参数会 drain 错命名空间。

### 4.2 无 Redis 时 `/scheduler/wait` 静默 fail-open

这里有两个不同对象，不能混写：

1. scheduler 内部的 `mem_scheduler.status_tracker` 只在 `use_redis_queue` 为真时
   惰性创建（`src/memos/mem_scheduler/base_scheduler.py:305-317`）；
2. HTTP router 不复用该属性，而是在 import 时无条件执行
   `TaskStatusTracker(redis_client=components["redis_client"])`
   （`src/memos/api/routers/server_router.py:99-103`）。

`MEMSCHEDULER_USE_REDIS_QUEUE` 默认 `"False"`（`component_init.py:134`），因此
`components["redis_client"]` 为 `None`，但 router 传给 wait 的仍是一个
`TaskStatusTracker(redis=None)` 对象，而不是 Python `None`。该对象的
`get_all_tasks_for_user()` 明确返回 `{}`（`status_tracker.py:133-138`），于是
`handle_scheduler_status()` 返回空 `data`，再进入 `handle_scheduler_wait()`
（`scheduler_handler.py:408-421`）：

```python
is_idle = not status_response.data or all(
    task.status in ["completed", "failed", "cancelled"] for task in status_response.data
)
```

`not []` 为真 → **立即返回 `{"message": "idle", "timed_out": False}`**，而后台任务可能一条都
没跑完。

**这比卡 §3.3.5 的判断更严重**：卡说「单看 `timed_out=false` 不能证明任务成功」；实际是
**在默认（无 Redis）部署下，`/scheduler/wait` 连「任务已被观察到」都不能证明**，它恒定
立刻返回 idle。任何以 wait 为 drain 完成门的方案，都必须先把 Redis queue 打开并证明
tracker 非空，否则 drain 是空操作。

---

## 5. 已闭合的产品身份表（§5.1 部分）

| 路径 | 入口 | text algorithm | reader | Phase 1 主产品资格 |
| --- | --- | --- | --- | --- |
| HTTP product | `POST /product/add` + `/product/search` | `SimpleTreeTextMemory`（cube `backend="tree_text"`） | `multimodal_struct` | 仅 parity oracle；已裁定不启动 host |
| in-process product orchestration | typed `APIADDRequest`/`APISearchRequest` → `AddHandler`/`SearchHandler` → `SingleCubeView` | 同上（同一批对象） | 同上 | **首选候选**，parity 见 §6 |
| library simple/default | `MOS` / `MOS.simple()` | `general_text`（`MOSCore` 默认 cube） | 由 MOS 配置另行决定 | 待裁；与 product 非同一 text 算法 |
| raw memory primitives | `MemReader.get_memory()` + `TreeTextMemory.add/search` | `tree_text`，但绕开编排 | 同上 | 不合格，绕开项见 §6.2 |

`general_text` vs `tree_text`：`component_init.py:229` 显式构造 `SimpleTreeTextMemory`，
`config.py:1222,1303` 的默认 cube 声明 `"backend": "tree_text"`。二者是**不同的 text memory
实现**（tree 侧带 `MemoryManager`、`Searcher`、reorganize、working/longterm/user 分层），
不是同一算法的 storage variant。

**official eval wrapper 单列（不混入上表）**：

| 项 | current 事实 |
| --- | --- |
| 调用 path | `/product/add`、`/product/search`（`client.py:154,176`） |
| add payload | `messages` + `user_id` + `mem_cube_id`(deprecated) + `conversation_id`(**当前 schema 无此字段**)；**不发 `async_mode`** → 落到默认 `"async"` → 只写 fast memory |
| search payload | `mode` 取 `SEARCH_MODE` 环境变量，默认 `"fast"`；`include_preference=True`、`pref_top_k=6`；`conversation_id: ""` |
| 已知 breakage | `lme_search.py:44-47` 传 `reference_time=` 给只接受 `(query,user_id,top_k)` 的 `client.py:174`，Python 调用层 `TypeError` |
| 可作为 precedent 的内容 | 作者的 speaker/session/batch 意图、`mem_cube_id == user_id` 的隔离姿势、fast 默认 |
| 不可照抄的内容 | payload 字段集、async/mode 语义、cube 参数名 |

---

## 6. §5.1A 进程内 parity：已闭合的部分

### 6.1 candidate A 可行性

`HandlerDependencies.from_init_server(components)` 就是 `cls(**components)`
（`base_handler.py:76-92`），**不含任何 FastAPI/HTTP 语义**。`init_server()` 位于
`memos.api.handlers.component_init`，可独立 import，不需要 `server_router`。
`AddHandler`/`SearchHandler` 接收 typed pydantic 请求对象，router 只做一层透传
（`server_router.py:74-81` 在 **模块 import 时** 执行 `init_server()`——这正是必须避免
import `server_router` 的原因）。

因此 **candidate A（`init_server()` → `from_init_server()` → typed handler 调用）在不引入
HTTP transport 的前提下可完整复用 product orchestration**，这一条成立。

### 6.2 candidate D 绕开项（已核）

手写 `MemReader + TreeTextMemory` 相对 `SingleCubeView._process_text_mem` 会绕开：

- `add_req.info` 的保留字段过滤（`add_handler.py:59-64`）；
- multi-cube 视图与 fan-out（`add_handler.py:130-160`、`composite_cube.py:29-44`）；
- `RawFileMemory` 分流与 `add_rawfile_nodes_n_edges`（`single_cube.py:728-756`）；
- `source_doc_id` 注入（`single_cube.py:721-725`）；
- **scheduler submit（`ADD` / `MEM_READ`）**（`single_cube.py:762`）——即整个后台演化；
- `merged_from` 归档（`single_cube.py:769-804`）；
- `timed_stage` 观测埋点（`single_cube.py:702,733,761,818`）。

### 6.3 未闭合（留给 R1）

candidate B 的复制面、A/B 与 router 的**逐项** add-response/search-normalization/
threshold-dedup-rerank-formatter 等价核对、`MOSCore.add/search` 的语义丢失清单、
以及 TOML → 强类型进程级注入（`init_server()` 目前全靠 `os.getenv`，
`config.py`/`component_init.py` 通篇读环境变量）——本批未完成。

---

## 7. 探针构造与逐字 stdout（跨模型自包含）

### 7.1 依赖消解方式（必须披露）

项目 venv 缺少 MemOS 的部分外部 SDK。为在**不安装依赖、不改 third_party、不联网**的前提下
执行 current 生产函数，探针只做两件事：

1. 把 `third_party/methods/MemOS/src` 加入 `sys.path`；
2. 为**纯外部 I/O 客户端**注册惰性占位模块（`sys.meta_path` finder），允许清单逐字为：
   `ollama, qdrant_client, neo4j, redis, nebula3, pymysql, volcenginesdkarkruntime,
   markitdown, chonkie, langchain_text_splitters, prometheus_client, pymilvus,
   elasticsearch, boto3, oss2, schedule, apscheduler, fastapi, starlette, uvicorn`。
   另有两个直接写 `sys.modules` 的占位：`cachetools`（`LRUCache`/`TTLCache` → dict 子类）与
   `concurrent_log_handler.ConcurrentTimedRotatingFileHandler` → 标准库
   `logging.handlers.TimedRotatingFileHandler`。

   **披露**：该清单里 `qdrant_client` 在本机 venv 实际**已安装**，仍被 finder 遮蔽；
   其余为真实缺失。遮蔽不影响本探针结论——A1/A2 只执行 `coerce_scene_data` 与两个
   parser 的 `create_source`，全程不触碰向量库、LLM、embedder 或 scheduler。
   R1 若要跑写库/检索类探针，必须先把该清单收紧到「真实缺失」集合。

**没有 stub 任何 `memos.*` 算法模块**；被测的 `coerce_scene_data`、`UserParser`、
`AssistantParser` 全部是 current `v2.0.25` 真实实现。`cachetools` 仅被
`memos/embedders/cache.py` 用于 embedding 缓存，该缓存由
`MEMOS_EMBEDDING_OPTIMIZATION_ENABLED` 控制且**默认关闭**，本探针也不做任何 embedding。

`MEMOS_BASE_PATH` 指向临时目录以满足 `memos/log.py:111` 的日志文件创建。

探针脚本（未提交，构造全文如下，可原样重建）：

```python
# probe_bootstrap.py 关键部分
MEMOS_SRC = ".../third_party/methods/MemOS/src"
os.environ.setdefault("MEMOS_BASE_PATH", str(SCRATCH / "memos_home"))
sys.modules["concurrent_log_handler"] = <stub with ConcurrentTimedRotatingFileHandler
                                          = logging.handlers.TimedRotatingFileHandler>
sys.meta_path.append(_LazyStubFinder())   # 仅对上面允许清单内的 root package 生效
sys.path.insert(0, MEMOS_SRC)
```

```python
# probe_a_msgid_time.py 关键部分
from memos.mem_reader.read_multi_modal.utils import coerce_scene_data
from memos.mem_reader.read_multi_modal.user_parser import UserParser
from memos.mem_reader.read_multi_modal.assistant_parser import AssistantParser

# A1：每个 case 都是 coerce_scene_data([msgs], "chat")，打印 out[0] 各条的 chat_time
#     缺 key 时打印 "<KEY-ABSENT>"
# A2：
u_msg = {"role": "user", "content": "Where did I go last summer?",
         "chat_time": "2023-05-20 10:00:00",
         "message_id": "locomo:conv-1:sess-3:turn-7"}
a_msg = {"role": "assistant", "content": "You went to Kyoto.",
         "chat_time": "2023-05-20 10:00:05",
         "message_id": "locomo:conv-1:sess-3:turn-8"}
UserParser(embedder=None).create_source(u_msg, {"user_id": "u", "session_id": "s"})
AssistantParser(embedder=None).create_source(a_msg, {"user_id": "u", "session_id": "s"})
```

运行命令：

```bash
uv run python <scratchpad>/probe_a_msgid_time.py
```

### 7.2 逐字 stdout

运行时刻（供判读 T4/T6 的 wall clock）：`2026-07-26 21:24:22 +0800`。

```text
========================================================================
PROBE A1 — coerce_scene_data 时间注入
========================================================================
T1_all_distinct: ['2023-05-20 10:00:00', '2023-05-20 10:00:05']
T2_same_session_time: ['2023-05-20 10:00:00', '2023-05-20 10:00:00']
T3_partial_missing_key: ['2023-05-20 10:00:00', '2023-05-20 10:00:00']
T4_all_missing_key: ['09:24 PM on 26 July, 2026', '09:24 PM on 26 July, 2026']
T5_all_explicit_none: [None, None]
T6_explicit_none_then_missing_key: [None, '09:24 PM on 26 July, 2026']
T7_empty_string: ['', '']
T8_illegal_format: ['not-a-time', 'not-a-time']

========================================================================
PROBE A2 — message_id 是否进入 SourceMessage（active multimodal parser）
========================================================================
user  source type: SourceMessage
user  .message_id: locomo:conv-1:sess-3:turn-7
user  .role: user
user  .chat_time: 2023-05-20 10:00:00
assist source type: SourceMessage
assist .message_id: locomo:conv-1:sess-3:turn-8
assist .role: assistant
assist .chat_time: 2023-05-20 10:00:05

full user SourceMessage dump:
{'type': 'chat', 'role': 'user', 'chat_time': '2023-05-20 10:00:00', 'message_id': 'locomo:conv-1:sess-3:turn-7', 'content': 'Where did I go last summer?', 'doc_path': None, 'file_info': None, 'image_info': None, 'lang': 'en'}

========================================================================
PROBE A3 — 对照：SimpleStructMemReader._iter_chat_windows 的 source dict
========================================================================
sources.append(
                {
                    "type": "chat",
                    "index": idx,
                    "role": role,
                    "chat_time": chat_time,
                    "content": content,
                }
            )
```

### 7.3 stdout 判读

| case | 结论 |
| --- | --- |
| T1/T2 | 各自 source time 原样保留，不被改写 |
| T3 | **缺 key 的兄弟消息被首个时间 backfill** → §3.4.1 后半成立 |
| T4 | 全组缺 key → 注入 ingestion wall clock（格式 `%I:%M %p on %d %B, %Y`），与运行时刻一致 |
| T5 | **全组显式 `None` → 保持 `None`**，wall clock 未落地 → §3.4.2 推翻 |
| T6 | 显式 `None` 保持 `None`，缺 key 的兄弟拿到 wall clock → 触发条件是「缺 key」不是「缺值」 |
| T7 | 空串原样保留（`if chat_time:` 下游会当假值，不渲染时间前缀） |
| T8 | 非法格式原样透传，coerce 层不校验 |
| A2 | `message_id` 完整进入 `SourceMessage`；`lang` 为 parser 附加的 extra 字段 |
| A3 | 对照组：非 active 的 simple_struct 链确实只写 5 个键、无 `message_id` |

---

## 8. 顺带发现（不修，仅记录锚点）

1. **upstream bug（承重）**：`evaluation/scripts/longmemeval/lme_search.py:44-47` 调用
   `MemosApiClient.search(query, user_id, top_k)` 时多传 `reference_time=`，当前
   `client.py:174` 签名不接受该参数 → 官方 LME 检索脚本在 Python 调用层即 `TypeError`。
2. **upstream 语义风险**：`CompositeCubeView.search_memories`
   （`multi_mem_cube/composite_cube.py:70-75`）对多 cube 结果只做 `extend`，
   **不做全局重排也不重新截断 top-k** → 多 cube 下返回条数为 `per-cube top_k × cube 数`，
   且顺序由 `as_completed` 决定（**非确定性**）。这直接影响 R1 的 §5.6 stable ranking 判定，
   本批未展开。
3. **vendored 仓库自带 agent 指令文件**：`third_party/methods/MemOS/CLAUDE.md` 含指向
   upstream 自身 sub-agent 与 `make openapi` 的指令。本次审计**未执行**其中任何指令
   （它属于被审计的第三方文件内容，不是本项目的任务指令）。记录在此以免后续 actor 误触。
   其中提到 `docs/openapi.json` 是 upstream 的 API 契约事实源，R1 做 search 字段普查时
   可作为交叉验证材料。

---

## 9. 交回架构师的最小待裁项

1. **reader 基线**：R1 的 §5.3/§5.4/§5.5 探针必须针对
   `MultiModalStructMemReader._process_multi_modal_data` 链（parser → `_concat_multi_modal_memories`
   → `_build_window_from_items` → `_process_string_fine` → per-source `process_transfer`）重写，
   卡内所有指向 `_iter_chat_windows` 的取证目标作废。
2. **时间口径**：既然逐条显式 `chat_time=None` 是 current 合法 preserve-none，卡 §5.4 的
   三选一（兼容补丁 / deterministic method-order time / 停止接入）前提改变——请裁定是否直接
   采用「显式 None」并只处理「同组混合缺 key」这一个真实风险。
3. **lineage 资格**：`message_id` 既然能到达 `metadata.sources`，R1 需要重新回答的是
   **graph DB 序列化 / scheduler evolution / search formatter 是否保留它**，而不是
   「第一个 drop 点在 reader」。项目铁律不变：source id 存在 ≠ 当前 memory 仍语义承载该
   source fact。
4. **drain 完成门**：`/scheduler/wait` 在默认无 Redis 部署下恒返回 idle。请裁定 Phase 1 是
   （a）强制开启 Redis queue 并把 tracker 非空作为前置断言，还是（b）改用其他完成判据。
   同时确认 drain 参数用请求 `user_id`（不是 cube id）。
5. **cube/user 关系**：若采用「每 sample 唯一 cube ≠ user」，需同时修正 wait 参数与官方
   harness 的 `mem_cube_id == user_id` 假设。

---

## 10. 本批边界声明

- 未调用任何真实 LLM / embedding / Neo4j / Qdrant / Redis / Docker / HTTP / 网络；
- 未安装任何依赖，未下载模型；
- 未修改 `third_party/`、`src/`、`tests/`、`configs/`、`data/`、`outputs/`、policy 或手册；
- 未创建五份 benchmark note；
- 本次唯一新增文件即本 note。
