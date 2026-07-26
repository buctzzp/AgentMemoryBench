# MemOS v2.0.25 async lifecycle R2 架构师验收

日期：2026-07-26

被验 actor commits：`d1a0178`、`2830c32`

source lock：`MemOS v2.0.25@e820406269537b97d270687e3e40eea2f015f81a`

## 0. 判词

```text
ACCEPTED_FOR_MEMOS_ADAPTER(
  async+fast→MEM_READ→fine product chain is preserved;
  reader and storage failures reach one exact terminal state;
  local tracker rejects terminal corruption and orphan callbacks;
  patch identity is reproducible;
  architect test-isolation repair is included
)
```

首轮 `d1a0178` 单独仍不成立；本判词只适用于 `d1a0178 + 2830c32` 以及本 note
§4 记录的架构师测试修正后的整体状态。

## 1. 生产 diff 复核

### 1.1 成功路径

patch 没有把主 profile 改成 `sync+fine`，仍是：

```text
SingleCubeView.add_memories
→ fast reader
→ fast TreeTextMemory/MemoryManager write
→ _schedule_memory_tasks
→ local queue
→ parallel dispatcher
→ MemReadMessageHandler
→ fine reader/write
→ raw delete
→ refresh
→ tracker.completed
```

新增行为只发生在已有 exception/invalid-result 分支：

- LLM/JSON 失败不再伪造 raw `UserMemory`；
- parser、scene、fine worker 先全部 settle，再传播首个异常；
- batch embedding 失败后仍保留逐项 fallback；只有逐项仍失败才最终抛错；
- memory-item 构造失败不再缩短结果；
- `merged_from` archive 全部尝试后聚合失败，缺 graph DB 时 fail-fast；
- raw delete、graph/vector write、refresh 与 scheduler submit 的既有吞错被改成失败可见。

`MultiModalStructMemReader` 的部分 exception handler 是 chat/doc 共用函数，因此这些改动也会
让共享路径上的同类失败变得可见；这里验收的是 **success-neutral failure semantics**，
不据此宣称 document/image 的算法或 vision parity 已验证。

### 1.2 Tracker

`MemosLocalTaskTracker` 现已锁住：

- identical submit 幂等且不重置 started/terminal；
- 同一 `(user_id, item_id)` 改绑 business/task type/cube 时 fail-fast；
- `failed` 与 `completed` 单调，冲突终态 callback 不能覆盖；
- 未 submit 的 started/completed/failed 不能创建 orphan record。

正常 dispatcher 的 submit → started → 单一 terminal 行为保持不变。

## 2. Full-chain 真实性

架构师逐层核对 current source：

- `SingleCubeView._schedule_memory_tasks()` 必经
  `BaseSchedulerQueueMixin.submit_messages()`；
- `MEM_READ` 不是 LEVEL_1 immediate task，进入 local queue；
- consumer 只通过 `SchedulerDispatcher.dispatch()/execute_task()` 调 handler；
- product-default `enable_parallel_dispatch=true` 时进入真实 executor；
- tracker 的 `completed` 只在 handler 正常返回后的真实 wrapper 写入。

因此测试中的 `add:returned` 后出现 fine write/delete/refresh，并最终由
`wait_for_business_task()` 读到 `completed`，不是高层 fake 可以绕出的旁路。

actor trace：

```text
== add:begin ==
embed:n=1
graph.add_nodes_batch:n=1
== add:returned ==
graph.get_node:<raw-id>
llm.generate
embed:n=1
graph.add_nodes_batch:n=1
graph.delete_node:<same-raw-id>
graph.get_grouped_counts
== wait:returned ==
```

严格顺序为：

```text
fast_write < add_returned < fine_write < raw_delete < refresh < wait_returned
```

## 3. Patch identity 与卫生

架构师独立验证：

```text
git diff d1a0178..2830c32 --check                 # exit 0
git show --check --oneline 2830c32                # exit 0
current nested tree reverse-check                 # exit 0
clean v2.0.25 checkout forward-check + apply      # exit 0
clean+patch 六个文件与 current nested tree hash    # 全部一致
临时 nested worktree                              # 已移除
```

新 patch 为 zero-context，首轮 23 处尾随空白已消失。`fetch_third_party_methods.sh`
仍通过既有 `--unidiff-zero` 幂等应用该 patch。

## 4. 架构师合流修正

生产代码无需第二次返工；测试侧补了两项：

1. actor 的 full-chain helper 原先直接改写 vendored MemOS 的进程级
   `LLMFactory/EmbedderFactory/ChunkerFactory.from_config`，退出后不恢复。它可能污染同一
   pytest 进程里未来新增的 MemOS adapter/registry 测试。现改为
   `pytest.MonkeyPatch.context()`，reader 构造结束即恢复，并加反例锁定；
2. actor 的 fine-worker partial-failure 用例原先直接覆写 `_get_llm_response`，并非卡要求
   的最低 LLM leaf；memory-item construction failure 也没有独立正式用例。架构师先用
   临时探针确认两条 production path 均传播失败，再把它们改成/补成真实
   `LLM.generate` 与 `_make_memory_item → embedder.embed` 叶子反例。

这两项只增强测试真实性和进程隔离，不改 MemOS patch 或 framework lifecycle 生产语义。

## 5. 架构师复验

定向：

```text
uv run pytest -q tests/test_memos_lifecycle.py tests/test_documentation_standards.py
55 passed, 10 warnings in 11.43s
```

无 API 全量：

```text
uv run pytest -q
1735 passed, 3 deselected, 11 warnings, 29 subtests passed in 139.11s
```

语法与 whitespace：

```text
uv run python -m compileall -q src/memory_benchmark tests
exit 0

git diff --check
exit 0

git diff --cached --check
exit 0
```

warning 由既有 LightMem Pydantic、MemOS `datetime.utcnow()` 与 MemOS config
serialization 产生；没有 `PytestUnraisableExceptionWarning`。

## 6. 下一步边界

R2 只关闭 **async lifecycle 完成门与失败传播**，不提前宣称：

- 真实 Neo4j/Qdrant 的跨 namespace 隔离与 stable ranking；
- image/vision 输入 parity；
- HaluMem session fine-output 的公开可观测性；
- `delete_by_memory_ids` 的 namespace 安全性；
- 空 content turn 的 exact lineage。

下一批是一张 MemOS v3 adapter 实现卡，加五个 benchmark 的强反例。adapter 必须：

- 调 typed product handler/对象接口，不启动 host；
- 显式装配 local tracker，并为每次 add 等待本 business task 的精确终态；
- failed ingest 的 clean retry 只走带 namespace filter 的删除路径，并以重新检索为空复核；
- 对上述 pending 能力逐格写 `valid/N/A/pending`，不得为了填满 metric 矩阵伪造资格。
