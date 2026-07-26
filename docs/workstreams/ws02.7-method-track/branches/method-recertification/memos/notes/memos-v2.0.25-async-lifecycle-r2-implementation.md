# MemOS v2.0.25 async lifecycle 完成门 R2 实施记录

日期：2026-07-26
执行者：Claude Opus 5（Claude Code 入口，本会话系统提示自报模型 `claude-opus-5`）
任务卡：`../cards/actor-prompt-memos-v2-0-25-async-lifecycle-r2.md`
前置裁决：[`memos-v2.0.25-m1-final-ruling.md`](memos-v2.0.25-m1-final-ruling.md)

---

> **首轮 `READY_FOR_MEMOS_ADAPTER` 判词已被架构师强验收撤回（2026-07-26）。**
> 下文 §0 的判词、§6 的“完整链路”表述与 §7 的 mutation 清单均**不再有效**，仅作首轮
> 施工记录保留。已确认的四项缺口：patch 尾随空白导致 `git show --check` exit 2；
> 本文 §6.1 所谓 “happy path 共享 trace” 实际只从 `text_mem.get(raw-1)` 起算的
> handler-only 五步，**不是**完整 async product chain（未经 fast reader/write、
> scheduler submit、local queue、dispatcher/tracker，也没有 `completed`）；
> `MultiModalStructMemReader._get_llm_response()` 与 `_embed_memory_items()` 的
> silent fallback 未被处理；`merged_from` archive 失败仍只 warning。
> 现行结论见
> [`memos-v2.0.25-async-lifecycle-r2-r1-implementation.md`](memos-v2.0.25-async-lifecycle-r2-r1-implementation.md)。

## 0. 唯一总判词

```text
READY_FOR_MEMOS_ADAPTER(
  success path unchanged;
  failures are observable;
  business-task completion is exact;
  patch is reproducible
)
```

---

## 1. 环境与 source identity

```text
$ LC_ALL=C git -C third_party/methods/MemOS status --short --branch
## HEAD (no branch)
$ LC_ALL=C git -C third_party/methods/MemOS status --porcelain | wc -l
       0            ← 开工前
$ git -C third_party/methods/MemOS rev-parse HEAD
e820406269537b97d270687e3e40eea2f015f81a
$ git -C third_party/methods/MemOS describe --tags --exact-match
v2.0.25
```

worktree：`/Users/wz/Desktop/mb-actor-memos-r2`，branch
`actor/memos-v2-0-25-async-lifecycle-r2`，基线 `main@0be2524`。

**软链披露**：新 worktree 不携带 gitignored 的 nested repo，因此建立本地软链
`third_party/methods/MemOS -> /Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS`。
父仓库 `.gitignore` 忽略的是带斜杠的目录形式，软链会以 `?? third_party/methods/MemOS`
出现在 `git status`；**全程未暂存、未提交**。

**收尾时 nested repo 的可解释 dirty 状态**：

```text
$ LC_ALL=C git -C third_party/methods/MemOS status --short
 M src/memos/graph_dbs/neo4j_community.py
 M src/memos/mem_scheduler/task_schedule_modules/handlers/mem_read_handler.py
 M src/memos/memories/textual/tree.py
 M src/memos/memories/textual/tree_text_memory/organize/manager.py
 M src/memos/multi_mem_cube/single_cube.py

$ git -C third_party/methods/MemOS apply --unidiff-zero --reverse --check \
    scripts/patches/memos-product-runtime-observability.patch
REVERSE_CHECK_OK
```

即工作树 == `v2.0.25@e820406` + 本卡 patch，逐字一致；HEAD 与 tag 未漂移，
未 commit / fetch / pull / checkout / install。

---

## 2. 开工前的一次操作事故与整改（必须披露）

创建 worktree 的第一条命令与「验证 nested identity」的命令在同一批并行执行，
Bash 工作目录发生泄漏，导致

```text
git worktree add /Users/wz/Desktop/mb-actor-memos-r2 -b actor/memos-v2-0-25-async-lifecycle-r2 main
```

**在 nested MemOS 仓库里**执行，产生了一个 MemOS 的 worktree 与同名分支
（内容是 MemOS 自己的 `main@b051e638`，即 v2.0.22）。

立即整改，未继续任何后续动作：

```text
$ git -C <MemOS> worktree remove /Users/wz/Desktop/mb-actor-memos-r2 --force
$ git -C <MemOS> branch -D actor/memos-v2-0-25-async-lifecycle-r2
已删除分支 actor/memos-v2-0-25-async-lifecycle-r2（曾为 b051e638）。
$ git -C <MemOS> worktree prune
$ git -C <MemOS> worktree list
/Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS  e8204062 (detached HEAD)
$ git -C <MemOS> branch --list
* （头指针在 v2.0.25 分离）
  main                       ← 原始 clone 自带，非本次新增
$ LC_ALL=C git -C <MemOS> status --short --branch
## HEAD (no branch)
$ LC_ALL=C git -C <MemOS> status --porcelain | wc -l
       0
```

nested repo 恢复到零改动的 detached `e820406`，随后所有 git 命令一律使用显式
`git -C <path>`，不再依赖 shell cwd。此事故未污染任何被交付内容，但属于纪律偏差，
按 handbook §4 如实披露。

---

## 3. §4 承重点复核（全部成立，无停工）

| # | 承重事实 | 判定 | 锚点 |
| --- | --- | --- | --- |
| 1 | async submit catch 只 log 不 raise | 成立 | `single_cube.py:544-548`（patch 前） |
| 2 | `mem_read_handler` 多层吞错 | 成立 | `batch_handler:47-50`、`process_message:107-108`、`_process_memories_with_reader:444-449`、fine-transfer `181-183`、delete `435-436`、organize submit `560-561` |
| 3 | `_add_memories_batch()` future 异常只 log 但仍返回预生成 IDs | 成立 | `manager.py:229-235` 只 `logger.exception`，`added_ids` 在 `:214` 已构建并于 `:244` 返回 |
| 3b | `_cleanup_working_memory()` / `_cleanup_memories_if_needed()` 吞错 | 成立 | `manager.py:260-261`、`546-547` |
| 4 | `tree.py::delete()` 逐 id 吞错 | 成立 | `tree.py:406-410` |
| 5 | `neo4j-community.add_nodes_batch()` vector 失败只标 `vector_sync=failed` | 成立 | `neo4j_community.py:193-197`，随后 graph write 继续 |
| 6 | dispatcher 已按 item_id / business task_id 调 tracker，只是 local 无可用 tracker | 成立 | `dispatcher.py:139/206/242/329`、`queue_ops.py:58-68`；tracker 仅在 `use_redis_queue` 时惰性建（`base_scheduler.py:306`） |

### 3.1 §4 之外新发现的同层吞错（已在允许文件内处理）

`BaseSchedulerHandler.process_grouped_messages`（`base_handler.py:44-51`）同样
`try/except` 每个 group 并只 `handle_exception` 记录。dispatcher 调的是
`handler(messages)` → `__call__` → `process_grouped_messages`，因此即使
`batch_handler` 抛出，异常仍会在这一层被吞掉。

`base_handler.py` **不在**本卡允许清单内。为不扩大 patch，改为在允许文件
`mem_read_handler.py` 内**覆写** `process_grouped_messages`：保持完全相同的分组与调用
顺序，逐 group 执行完后聚合 raise。**只影响 MEM_READ handler，其他 handler 保持 upstream
行为。**

---

## 4. patch 内容与 success-path 守恒

文件：`scripts/patches/memos-product-runtime-observability.patch`

```text
 src/memos/graph_dbs/neo4j_community.py                                   |  4 +
 src/memos/mem_scheduler/task_schedule_modules/handlers/mem_read_handler.py | 90 ++++++++++++--
 src/memos/memories/textual/tree.py                                       |  6 +
 src/memos/memories/textual/tree_text_memory/organize/manager.py          | 11 +
 src/memos/multi_mem_cube/single_cube.py                                  |  3 +
 5 files changed, 107 insertions(+), 7 deletions(-)
```

### 4.1 逐个 upstream 函数

| 函数 | 改动 | success path 影响 |
| --- | --- | --- |
| `SingleCubeView._schedule_memory_tasks` | async 分支 `except` 末尾加 `raise` | 无：成功时不进 except |
| `MemReadMessageHandler.process_grouped_messages`（新增覆写） | 同样分组/顺序，收集 group 失败后聚合 raise | 无：无失败时行为与父类一致 |
| `MemReadMessageHandler.batch_handler` | 收集 future 失败，等全部 settle 后 raise `MemReadBatchError` | 无：仍是同样的线程池与 `as_completed` |
| `MemReadMessageHandler.process_message` | 外层 `except` 末尾加 `raise`；`mem_cube is None`、`text_mem` 类型错改为 raise | 无：这些分支原本就 `return`，不产生记忆 |
| `MemReadMessageHandler._process_memories_with_reader` | raw 回读失败 raise；raw 全部读不到 raise；fine-transfer 失败 raise（**零抽取仍正常返回**）；delete 失败 raise；外层 `except` 在写完 failure web-log 后 raise；`mem_reader is None` raise | 无：成功路径不触碰任何新增分支 |
| `MemReadMessageHandler._try_submit_organize_task` | `except` 末尾加 `raise` | 无：reorganize 关闭时在函数开头 `return`，根本到不了 |
| `TreeTextMemory.delete` | 收集逐 id 失败，**尝试完所有 id** 后 raise 第一个 | 无：全成功时 `delete_errors` 为空 |
| `MemoryManager._add_memories_batch` | 收集 batch future 失败，等全部 settle 后 raise | 无：全成功时不 raise，返回同样的 `added_ids` |
| `MemoryManager._cleanup_working_memory` / `_cleanup_memories_if_needed` | `except` 末尾加 `raise` | 无 |
| `Neo4jCommunityGraphDB.add_nodes_batch` | vec_db 写失败在标记 `vector_sync=failed` **之后** raise | 无：成功时不进 except |

### 4.2 守恒判词

**patch 只在既有 `except` 分支尾部追加 `raise`，或把「只 log 后继续」改成「先把所有并行/
逐项工作跑完再聚合 raise」。没有任何一处改变成功路径的调用顺序、memory 内容、返回 ID、
metadata、search 行为或调度拓扑；也没有把 async 改成 sync、没有触碰 fast/fine/reorganize/
search 算法。** 合法的「fine extraction 成功但抽取零条 memory」保持 completed（见 §6 用例
`test_legal_zero_extraction_still_completes`）。

按卡要求，**未**顺手修无 namespace 的 `delete_by_memory_ids()`；adapter 将禁止调用该入口。

### 4.3 可复现性

`scripts/fetch_third_party_methods.sh` 在 MemOS checkout 之后新增一行：

```bash
apply_method_patch "MemOS" "${ROOT_DIR}/scripts/patches/memos-product-runtime-observability.patch"
```

复用仓库既有的 `apply_method_patch`（SimpleMem 已有先例），其语义是「先 reverse-check，
已应用则跳过」，因此幂等。`third_party/methods/MANIFEST.md` 的 MemOS 行已改写为
`v2.0.25 / e820406... + 本项目 failure-observability patch`。

---

## 5. 框架 tracker 与 waiter

`src/memory_benchmark/methods/memos_lifecycle.py`：

- `MemosLocalTaskTracker`：`threading.Condition` 保护的进程内状态表，**不依赖 Redis**。
  只实现 current scheduler/dispatcher 真正调用的
  `task_submitted / task_started / task_completed / task_failed /
  get_task_status / get_task_status_by_business_id`；聚合规则与 upstream
  `TaskStatusTracker.get_task_status_by_business_id` 一致（任一 failed → failed；
  仍有 waiting/in_progress → in_progress；全 completed → completed；否则 unknown）。
- `install_local_tracker(scheduler, tracker=None)`：把**同一个实例**装到 scheduler 与
  dispatcher，并复核两侧是同一对象；无 dispatcher 时 `ConfigurationError`。
- `wait_for_business_task(user_id, business_task_id, timeout_seconds,
  expected_task_count=1, task_label="mem_read")`：只认
  **user + business task + label** 三元组；靠 `Condition.wait` 被唤醒，**不 polling sleep**、
  不解析日志、不读 `/scheduler/wait`、不看全局队列。
  - `failed` → 立即 `ConfigurationError`，消息内保留原始 error 文本；
  - 未知状态、数量多于预期、超时、查无任务 → 各自 fail-fast，且「从未登记任何 task」
    与「有 task 但未完成」是两条不同的报错。
- `assert_no_pending_tasks()` / `pending_tasks()`：关闭前置门，有 pending 就
  `ConfigurationError`，不静默关闭。

---

## 6. 强反例（`tests/test_memos_lifecycle.py`，32 passed）

卡 §6 的 15 项覆盖对照：

| 卡项 | 用例 |
| --- | --- |
| 1 patch reverse-check + fetch 只 apply 一次 | `test_patch_reverse_check_matches_vendored_tree`、`test_fetch_script_applies_memos_patch_exactly_once`、`test_manifest_records_patched_source_identity` |
| 2 async happy path 完整共享 trace | `test_async_mem_read_happy_path_shared_trace` |
| 3 initial fast graph write 失败不得返回伪 ID | `test_manager_graph_write_failure_does_not_return_phantom_ids` |
| 4 vector write 失败 | `test_neo4j_community_vector_write_failure_raises` |
| 5 scheduler submit 失败 | `test_async_scheduler_submit_failure_propagates` |
| 6 fine-transfer LLM 失败 | `test_mem_read_failures_propagate[...PROBE_FINE_TRANSFER_FAILURE]` |
| 7 fine graph write 失败 | `test_mem_read_failures_propagate[...PROBE_FINE_WRITE_FAILURE]` |
| 8 raw delete 失败 | `test_mem_read_failures_propagate[...PROBE_DELETE_FAILURE]`、`test_tree_delete_partial_failure_raises` |
| 9 refresh/cleanup 失败 | `test_mem_read_failures_propagate[...PROBE_REFRESH_FAILURE]`、`test_manager_capacity_cleanup_failures_raise` |
| 10 batch 一项失败一项完成 → aggregate failed | `test_batch_partial_failure_waits_and_aggregates` |
| 11 合法零抽取 completed | `test_legal_zero_extraction_still_completes` |
| 12 business task A 不解锁 B | `test_other_business_task_does_not_unlock`、`test_other_namespace_does_not_unlock`、`test_non_mem_read_labels_are_not_counted` |
| 13 missing/unknown/multiple/timeout/failed 原因 | `test_missing_task_fails_fast`、`test_unknown_status_fails_fast`、`test_more_than_expected_mem_read_fails_fast`、`test_failed_task_raises_with_original_error`、`test_waiter_returns_on_expected_completion` |
| 14 tracker 多线程并发 | `test_tracker_is_thread_safe_under_concurrency`、`test_waiter_wakes_up_from_background_thread` |
| 15 shutdown pending fail-fast / 全完成可关 | `test_shutdown_guard_rejects_pending_tasks` |
| 额外：真实 dispatcher wrapper 把失败写进本 tracker | `test_dispatcher_marks_task_failed_through_real_wrapper` |
| 额外：缺 cube / 错类型 | `test_missing_mem_cube_is_failure`、`test_wrong_text_memory_type_is_failure` |
| 额外：安装面 | `test_install_local_tracker_shares_one_instance`、`test_install_local_tracker_requires_dispatcher` |

### 6.1 happy path 的共享 trace（断言原文）

```python
assert trace == [
    "text_mem.get:raw-1",
    "mem_reader.fine_transfer_simple_mem",
    "text_mem.add:n=1",
    "text_mem.delete:['raw-1']",
    "memory_manager.remove_and_refresh_memory",
]
```

单条 trace 同时约束 fast 回读 → fine transfer → fine write → raw delete → refresh 的**全序**，
不是几份独立列表。

### 6.2 替身边界

替身只有：外部 I/O SDK（`ollama/neo4j/redis/...` 共 18 个真实缺失包 + `cachetools` +
`concurrent_log_handler`）、graph store、vec db、mem reader 的 LLM 输出。
**没有 stub 任何 `memos.*` 算法函数**；被测的每个 catch 边界都真实执行。

一个具体证据：记录型 text memory 最初写成独立类，被 patch 新增的
`isinstance(text_mem, TreeTextMemory)` 守卫直接拒绝，因此改为**真实继承
`TreeTextMemory`** 的子类——替身没有绕过守卫，守卫也确实在跑。

---

## 7. Mutation 证明（临时变体未提交）

逐个去掉 patch hunk 后跑对应用例，全部转红：

```text
[RED (good)] single_cube async submit raise
    test: tests/test_memos_lifecycle.py::test_async_scheduler_submit_failure_propagates
    tail: 1 failed, 1 warning in 4.27s
[RED (good)] mem_read fine_transfer raise
    test: tests/test_memos_lifecycle.py::test_mem_read_failures_propagate
    tail: 1 failed, 4 passed in 3.27s
[RED (good)] tree.delete aggregate raise
    test: tests/test_memos_lifecycle.py::test_tree_delete_partial_failure_raises
    tail: 1 failed in 3.35s
[RED (good)] manager batch raise
    test: tests/test_memos_lifecycle.py::test_manager_graph_write_failure_does_not_return_phantom_ids
    tail: 1 failed in 3.39s
[RED (good)] neo4j vector raise
    test: tests/test_memos_lifecycle.py::test_neo4j_community_vector_write_failure_raises
    tail: 1 failed in 3.39s
```

每次变体后立即恢复原文件；结束后 reverse-check 重新通过（见 §1）。

---

## 8. §5.3 HaluMem 观测边界

**判定：`pending(adapter 需纯观测 sidecar)`。**

理由（current source，未为此扩 patch）：

- 本卡的 strict completion 只保证「本次 add 派生的 `MEM_READ` 已到达终态」，
  它让 task-scoped fine 阶段**可等待、可判失败**；
- 但 `MemReadMessageHandler._process_memories_with_reader` 把 `enhanced_mem_ids` 与
  `flattened_memories` 只用于内部日志与 `kb_log_content`，**不返回给调用方**，
  handler 的返回值是 `None`；tracker 记录的也只有状态，不含内容；
- 因此「本 session 新抽取了哪些 memory」目前无法从公开完成门直接读出。

可行方向留给 adapter 卡：在**不改成功态算法**的前提下加一个纯观测 sidecar（例如
在 patch 允许范围内把 `enhanced_mem_ids` 通过既有 observability 通道暴露，或由 adapter
在 wait 返回后按 namespace + 时间窗做只读检索比对）。
按最终裁决 §5，若纯观测无法获得，HaluMem extraction 应降为 `N/A`，**不得**改走
`sync+fine` variant。本卡未做此判定。

---

## 9. 本批边界声明

- 零真实 LLM / embedding / Neo4j / Qdrant / Redis / Docker / HTTP / 网络 / 模型下载；
- 未启动 host，未 import `server_router`；
- 未改 async 成 sync，未改 fast/fine/reorganize/search 算法；
- 未修改 registry、runner、benchmark adapter、evaluator、TOML、outputs、data、models
  或其他 third_party method；
- nested repo 未 commit；软链未暂存；
- 未 push、未清 worktree、未更新 README/roadmap、未开始 adapter。
