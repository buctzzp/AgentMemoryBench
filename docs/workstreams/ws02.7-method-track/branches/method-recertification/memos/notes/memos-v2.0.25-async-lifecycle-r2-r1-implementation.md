# MemOS v2.0.25 async lifecycle R2-R1 返工记录

日期：2026-07-26
执行者：Claude Opus 5（Claude Code 入口，本会话系统提示自报模型 `claude-opus-5`）
任务卡：`../cards/actor-prompt-memos-v2-0-25-async-lifecycle-r2-r1.md`
被返工对象：首轮 `d1a0178`（判词已撤回，见
[R2 首轮 note](memos-v2.0.25-async-lifecycle-r2-implementation.md) 顶部横幅）

---

## 0. 唯一总判词

```text
READY_FOR_MEMOS_ADAPTER(
  product reader failures are observable;
  full async chain reaches one exact terminal state;
  patch and report are self-consistent
)
```

---

## 1. 首轮四项缺口的复现与关闭

| # | 架构师复现的缺口 | 本批复现结果 | 关闭方式 |
| --- | --- | --- | --- |
| 1 | `git show --check d1a0178` exit 2，patch 有 23 处尾随空白 | 逐字复现：`exit=2`，`grep -c "trailing whitespace"` = **23** | 改用 `git diff --unified=0` 重新生成；新 patch 尾随空白计数 **0** |
| 2 | happy-path trace 只有 handler-only 五步，未过 fast reader/write、submit、queue、dispatcher/tracker，也无 `completed` | 复现（首轮用例从 `text_mem.get(raw-1)` 起算） | 新增 `test_full_async_product_chain_single_shared_trace`，见 §3 |
| 3 | `_get_llm_response()` 把 LLM/JSON 异常改写成“原文即 UserMemory”；`_embed_memory_items()` 全 fallback 失败仍返回且 `embedding=None` | 复现（`multi_modal_struct.py:503-517`、`:111-119`） | 见 §2.1 |
| 4 | `merged_from` 的 `graph_db.update_node()` 失败仍只 warning，随后删 raw、refresh、正常返回 | 复现（`mem_read_handler.py` archive 循环） | 见 §2.2 |

开工前 source identity 与 dirty 校验：

```text
$ git -C third_party/methods/MemOS rev-parse HEAD
e820406269537b97d270687e3e40eea2f015f81a
$ git -C third_party/methods/MemOS describe --tags --exact-match
v2.0.25
$ git -C third_party/methods/MemOS apply --unidiff-zero --reverse --check \
    scripts/patches/memos-product-runtime-observability.patch
REVERSE_CHECK_OK (dirty 恰好等于首轮 patch)
```

---

## 2. patch 新增触及的 upstream 函数

首轮已覆盖的函数不再重复（见首轮 note §4.1）。**本批新增**：

| 函数 | 文件 | 改动 | success path 影响 |
| --- | --- | --- | --- |
| `MultiModalStructMemReader._get_llm_response` | `multi_modal_struct.py` | 删除“原文伪造成 `UserMemory`”的 fallback，改为 `raise` | 无：LLM 成功且可解析时不进 except |
| `MultiModalStructMemReader._process_one_item`（Stage 1 LLM 调用 catch） | 同上 | `return fine_items`（空）改为 `raise` | 无 |
| `MultiModalStructMemReader._process_one_item`（两处 memory-item 构造 catch） | 同上 | `logger.error` 后 `raise` | 无 |
| `MultiModalStructMemReader._embed_memory_items` | 同上 | batch→逐项 fallback **完全保留**；仅当**任一逐项 fallback 也失败**时，尝试完其余项后 aggregate raise | 无：batch 成功、或 batch 失败但逐项全成功，两种情况行为逐字不变 |
| `MultiModalStructMemReader._process_multi_modal_data`（parser futures） | 同上 | 收集失败，settle 后 aggregate raise | 无 |
| `MultiModalStructMemReader._process_string_fine`（fine worker futures） | 同上 | 收集失败，settle 后 aggregate raise | 无 |
| `MultiModalStructMemReader._read_memory`（scene futures） | 同上 | 收集失败，settle 后 aggregate raise | 无 |
| `MemReadMessageHandler._process_memories_with_reader`（merged_from archive） | `mem_read_handler.py` | 所有 old id 都先尝试 archive，任一失败则 aggregate raise；`merged_from` 存在但 `graph_db is None` 时 fail-fast | 无：无 `merged_from` 时该分支不执行 |

### 2.1 「合法零抽取」边界（卡 §2.1）

只有 **LLM 调用成功 + 解析成功 + 明确产出空 memory list** 才算合法零抽取并 completed
（用例 `test_successful_empty_llm_result_still_completes`，走完整 async 链）。
LLM transport/parse 异常、parser/fine worker 异常、memory item 构造或 embedding 异常、
逐项 embedding fallback 失败、`merged_from` 无法 archive —— 全部判失败。

### 2.2 守恒判词

**patch 仍然只在既有 exception / invalid-result 分支上动作**：要么把「吞掉后继续」改成
「先让所有并行/逐项工作 settle 再聚合 raise」，要么删掉「用伪造结果冒充成功」的 fallback。
成功路径的调用顺序、memory 内容、返回 ID、metadata、search 行为与调度拓扑零变化；
未把 async 改成 sync，未触碰 tool trajectory、memory-version-on、文档/图片 vision 路径，
也未改成功态的 chunk fallback。

### 2.3 Patch 卫生（卡 §5）

```text
$ grep -c ' $' scripts/patches/memos-product-runtime-observability.patch
0

# 1) clean v2.0.25 checkout 上 forward-check
FORWARD_CHECK_OK (clean v2.0.25 可应用)
# 2) 实际 apply
APPLY_OK
# 3) 幂等：第二次 reverse-check 判为 already applied（fetch 脚本据此 skip）
IDEMPOTENT_OK
# 4) clean+patch 与当前 vendored 树逐字比对
diff -r -q <clean+patch>/src/memos <vendored>/src/memos  →  无差异
```

`fetch_third_party_methods.sh` 与 `MANIFEST.md` 语义无变化，本批未改动（不制造空 diff）。

新 patch 规模：

```text
 src/memos/graph_dbs/neo4j_community.py                                     |   4 +
 src/memos/mem_reader/multi_modal_struct.py                                 |  60 ++++++--
 src/memos/mem_scheduler/task_schedule_modules/handlers/mem_read_handler.py | 104 +++++++++++--
 src/memos/memories/textual/tree.py                                         |   6 +
 src/memos/memories/textual/tree_text_memory/organize/manager.py            |  11 +
 src/memos/multi_mem_cube/single_cube.py                                    |   3 +
 6 files changed, 167 insertions(+), 21 deletions(-)
```

---

## 3. 完整 async product chain（卡 §4.1）

用例：`test_full_async_product_chain_single_shared_trace`

真实实现（**未**被覆写）：`SingleCubeView.add_memories`、`_process_text_mem`、
`_schedule_memory_tasks`、`BaseSchedulerQueueMixin.submit_messages`、
`ScheduleTaskQueue` / `SchedulerLocalQueue`、`BaseScheduler._message_consumer`、
`SchedulerDispatcher.execute_task` + `_create_task_wrapper`、`MemReadMessageHandler`、
`MultiModalStructMemReader`（fast + fine）、`TreeTextMemory.add/get/delete`、
`MemoryManager.add/_add_memories_batch/remove_and_refresh_memory`、
framework `MemosLocalTaskTracker` 的真实 callback。

hermetic fake 只有最低层叶子：LLM、embedder、chunker、graph store。
**product-default `enable_parallel_dispatch=true` 保持不变**，测试等待真实 executor
future，未把 dispatcher 改成同步。

### 3.1 一手 trace 原文

```text
TERMINAL_STATUS: completed
TRACE_BEGIN
== add:begin ==
embed:n=1
graph.add_nodes_batch:n=1
== add:returned ==
graph.get_node:2af722c7-d406-4764-8b20-1da2b53f3f39
llm.generate
embed:n=1
graph.add_nodes_batch:n=1
graph.delete_node:2af722c7-d406-4764-8b20-1da2b53f3f39
graph.get_grouped_counts
== wait:returned ==
TRACE_END
```

环节映射：

| trace 行 | 链路环节 |
| --- | --- |
| `embed:n=1`（首次） | fast reader（parser → 滑窗 → `_embed_memory_items`） |
| `graph.add_nodes_batch:n=1`（首次） | fast `TreeTextMemory.add` → `MemoryManager._add_memories_batch` |
| `== add:returned ==` | async add 返回（此后为后台阶段） |
| `graph.get_node:<uuid>` | `MemReadMessageHandler` 回读 raw memory |
| `llm.generate` | fine reader 抽取 |
| `embed:n=1`（第二次） | fine memory embedding |
| `graph.add_nodes_batch:n=1`（第二次） | fine write |
| `graph.delete_node:<uuid>` | raw 清理（与回读同一 id） |
| `graph.get_grouped_counts` | `remove_and_refresh_memory` → `_refresh_memory_size` |
| `== wait:returned ==` | `wait_for_business_task` 按 business task 返回，终态 `completed` |

断言的严格全序：
`fast_write < add_returned < fine_write < raw_delete < refresh < wait_returned`，
外加 `tracker.assert_no_pending_tasks()`。

**说明**：`remove_oldest_memory` 未出现在 trace 中是 **product 正常行为**——
`_cleanup_memories_if_needed` 只在占用达到容量 80% 阈值时才触发，本用例节点数远低于阈值。
因此 refresh 环节以 `get_grouped_counts` 为锚，不虚构一个不该发生的调用。

**scheduler submit 与 dispatcher 环节**由链路本身保证：MEM_READ 是非 LEVEL_1 task，
必须经 local queue + consumer 线程 + dispatcher wrapper 才可能产生 tracker 终态；
`== wait:returned ==` 与 `completed` 就是这段链路的唯一出口。

---

## 4. 新增强反例

### 4.1 Reader / archive（卡 §4.2）

| 卡项 | 用例 | 注入点（真实最低层叶子） |
| --- | --- | --- |
| 1 LLM generation 抛错，不再生成 raw fallback | `test_llm_generation_failure_no_raw_fallback` | fake LLM `generate()` 抛错；断言 add 返回后**无任何 fine write**，且 raw memory 保留 |
| 2 batch embedding 失败、逐项全成功仍通过 | `test_embedding_batch_failure_with_all_item_fallbacks_ok` | fake embedder 只让 batch 失败 |
| 3 batch 与某个逐项都失败 → 全部尝试后 raise | `test_embedding_all_item_fallbacks_attempted_then_raise` | fake embedder 按索引失败；断言 trace 为 `batch, item0, item1, item2`（失败项之后仍继续） |
| 4 initial parser 一失败一成功 → settle 后整体失败且无 partial fast memory | `test_initial_parser_partial_failure_settles_then_fails` | 真实 `MultiModalParser` 位置替身按 content 抛错；断言两条消息都被解析、store 为空 |
| 5 fine worker 一失败一成功 → settle 后 task failed | `test_fine_worker_partial_failure_settles_then_task_failed` | `_get_llm_response` 层按 fast item 内容抛错；断言两个 worker 都被调用 |
| 6 fine memory item 构造/embedding 失败不算合法零抽取 | 同 4.1-1 与 `test_mem_read_failures_propagate` | — |
| 7 成功且空的 LLM result 仍 completed | `test_successful_empty_llm_result_still_completes` | fake LLM 返回 `{"memory list": []}`，走完整链 |
| 8 `merged_from` archive 一失败一成功 → 两个 old id 都尝试且 task failed | `test_merged_from_archive_partial_failure_fails_task` | fake `graph_db.update_node` 对 `old-2` 抛错；断言 `attempted == ["old-1", "old-2"]` |
| 9 `merged_from` + `graph_db=None` fail-fast | `test_merged_from_without_graph_db_fails_fast` | — |

### 4.2 Tracker anti-corruption（卡 §4.3）

| 卡项 | 用例 |
| --- | --- |
| `failed → completed` 不得改写 | `test_failed_terminal_is_not_overwritten_by_completed` |
| `completed → failed` 不得改写 | `test_completed_terminal_is_not_overwritten_by_failed` |
| 相同身份重复 submit 幂等、不退回 waiting | `test_identical_resubmit_is_idempotent_and_keeps_terminal` |
| 改绑另一个 business id fail-fast、旧 index 不污染 | `test_rebinding_item_to_other_business_task_fails_fast` |
| 未 submit 的 started/completed/failed fail-fast、不建 orphan | `test_unsubmitted_transitions_fail_fast[started/completed/failed]` |

首轮的并发、namespace、数量、timeout、shutdown 用例**全部保留**，未删改。

---

## 5. Mutation 证明（卡 §4.4，临时变体未提交）

```text
[RED (good)] reader LLM fallback（_get_llm_response 伪造原文）
    test: tests/test_memos_lifecycle.py::test_llm_generation_failure_no_raw_fallback
    tail: 1 failed, 2 warnings in 4.32s
[RED (good)] embedding per-item fallback aggregate
    test: tests/test_memos_lifecycle.py::test_embedding_all_item_fallbacks_attempted_then_raise
    tail: 1 failed in 3.53s
[RED (good)] fine worker aggregate（_process_string_fine futures）
    test: tests/test_memos_lifecycle.py::test_fine_worker_partial_failure_settles_then_task_failed
    tail: 1 failed in 3.50s
[RED (good)] merged-from archive aggregate
    test: tests/test_memos_lifecycle.py::test_merged_from_archive_partial_failure_fails_task
    tail: 1 failed in 3.54s
```

每次变体后立即恢复文件；结束后 reverse-check 重新通过。

---

## 6. 测试计数与历史一致性（卡 §5）

首轮 note 写「32 passed」，而首轮 commit `d1a0178` 的真实自检输出是
`37 passed, 4 warnings in 6.44s`（`tests/test_memos_lifecycle.py` +
`tests/test_documentation_standards.py` 两个文件合跑）。差异原因：**32 是
`test_memos_lifecycle.py` 单文件在补齐 docstring 之前的中间态计数**，首轮 note §6 标题
误把它写成最终值，而回报里给的是两文件合跑的 37。两个数字都真实出现过，但 note 里的
那个不是最终自检值。此处如实更正，不改写首轮 note 的历史正文（只在顶部加撤回横幅）。

本批最终计数见 §7。

`PytestUnraisableExceptionWarning` 已消除（计数 0）：测试构造的 `MemoryManager`
（经 `__new__`）现在显式初始化 `reorganizer`（`_NullReorganizer`，同时提供
`wait_until_current_task_done()` 与 `stop()`），完整满足
`__del__ → close() → wait_reorganizer() + reorganizer.stop()` 的析构依赖。

---

## 7. 自检输出（卡 §6）

```text
$ uv run pytest -q tests/test_memos_lifecycle.py tests/test_documentation_standards.py
53 passed, 9 warnings in 5.52s

$ git diff d1a0178..HEAD --check
exit=0

$ git show --check --oneline HEAD
exit=0
```

（9 个 warning 全部是 vendored MemOS 自身的 Pydantic 序列化提示与
`datetime.utcnow()` DeprecationWarning，非本批引入；`PytestUnraisableExceptionWarning`
计数为 **0**。）

---

## 8. 本批边界声明

- 零真实 LLM / embedding / Neo4j / Qdrant / Redis / Docker / HTTP / 网络 / 模型下载；
- 未启动 host，未 import `server_router`；
- 未改 async 成 sync，未改 fast/fine/reorganize/search 成功态算法；
- nested repo 只改卡 §3 允许的 6 个文件，全部由 patch 表达，未 commit；
- 软链 `third_party/methods/MemOS` 未暂存；
- 未 push、未 amend/rebase/merge、未清 worktree、未更新 README/roadmap、未开始 adapter。
