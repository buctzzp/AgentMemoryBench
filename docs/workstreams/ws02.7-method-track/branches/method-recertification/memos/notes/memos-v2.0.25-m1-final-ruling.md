# MemOS v2.0.25 M1 最终架构裁决

日期：2026-07-26

## 0. 判词

```text
ACCEPT_R1_EVIDENCE_BUT_REJECT_SYNC_FINE_AS_MAIN(
  product identity = tree_text + MultiModalStructMemReader + typed handlers;
  main add lifecycle = product-default async + fast -> queued MEM_READ;
  sync + fine is an explicit ALGORITHM_VARIANT, not the main smoke/full profile;
  local /scheduler/wait remains forbidden;
  M1 is not yet allowed to jump directly to the adapter:
  first close success-neutral failure propagation + task-scoped completion in R2.
)
```

`2ea7a39` 的 R1 note 作为一手机制证据验收通过；其中对 typed handler、时间与
`message_id` 传输、role 形状、single-namespace 参数面、search 调用顺序、cleanup 风险和
服务依赖的结论可以继续消费。

但 R1 note 的“`sync+fine+serial` 已关闭 B6，因此下一张直接写 adapter”**不获批准**。
actor 自己已经证明该组合是 `ALGORITHM_VARIANT`；完成门好实现，不能反过来成为替换产品
算法身份的理由。

## 1. 为什么不能把 sync + fine 升为主 profile

current `APIADDRequest` 的公开默认是：

```text
async_mode="async"
mode=None
```

`mode` 在 product model 中被标成 internal，且 async 时会被忽略。两条路径虽然复用同一个
fine extraction 函数，完整 lifecycle 仍不同：

| 路径 | 成功态算法阶段 |
| --- | --- |
| product default `async+fast` | fast/raw write → queued `MEM_READ` → fine transfer/write → fast delete/soft-delete → memory-manager refresh → 可选 reorganize |
| `sync+fine` | request 内直接 fine extraction/write → telemetry-only `ADD` |

当前没有真实 DB 证据证明两条路径最终状态、检索序和 memory-manager 状态等价。相反，
R1 已证明后一条明确省略前一条的中间记忆、清理和 refresh 阶段。因此：

- `sync+fine` 可保留为显式命名的诊断/校准 variant；
- 不得把它写成 `smoke` / `official_full` 的主配置；
- 不得为了获得 HaluMem extraction readout 而暗中切换整个 method 的算法路径。

主表要解决的是 async 产品路径的完成与失败可观测性，而不是绕开它。

## 2. 架构师独立强验收发现的第二层吞错

R1 的 P2a 在 `text_mem.add()` 外层注入异常，只证明“该调用直接 raise 时能向上传”。
它没有覆盖 current 真实实现内部的吞错点：

1. `MemoryManager._add_memories_batch()` 捕获
   `graph_store.add_nodes_batch()` future 异常，只写日志，仍返回预生成 memory IDs；
2. default `neo4j-community.add_nodes_batch()` 的 vector DB batch insert 失败只写
   `vector_sync="failed"`，graph write 继续成功；
3. `MemReadMessageHandler.process_message()` 与
   `_process_memories_with_reader()` 的外层异常只记录、不 re-raise；
4. `fine_transfer_simple_mem()` 失败被改写成 `processed_memories=[]`；
5. raw/working memory 删除失败只 warning；`TreeTextMemory.delete()` 自身也逐项吞错；
6. `_cleanup_memories_if_needed()` 的容量清理失败只 warning；
7. async scheduler submit 失败在 `SingleCubeView._schedule_memory_tasks()` 被吞。

所以“队列空 + dispatcher future 完成”仍可能是假成功；现有 `MONITOR_EVENT` 也会因为
handler 没抛出异常而写成 `status=success`。这是 R2 必须修的**失败语义/观测缺口**，不是
换算法 profile 的理由。

## 3. R2 锁定的主运行身份

### 3.1 不变的成功路径

```text
reader                    MultiModalStructMemReader
backend                   tree_text
entry                     init_server -> HandlerDependencies -> typed Add/SearchHandler
add async_mode            async
add mode                  None
scheduler queue           local, no Redis
parallel dispatch         保持 product default true
reorganize                false（current product default）
internet retrieval        false（benchmark 只测 method memory，不引入外部知识）
cube topology             one deterministic namespace / one cube
```

每次 add 由 adapter 生成唯一 business `task_id`。在同一 worker 进程中安装 thread-safe
in-memory task tracker，挂到 scheduler 与 dispatcher；typed add 返回后，按该
`task_id` 等待真实 `MEM_READ` 终态。其他 namespace、其他 task 或“全局队列刚好为空”
都不能满足当前完成门。

### 3.2 只允许改变失败可见性

R2 patch 必须满足：

- 成功路径的 reader、LLM、embedding、graph/vector write、delete、refresh、调度顺序和
  返回 memory 内容零变化；
- 真实 write/transfer/delete/refresh/submit 失败不得再转成 success；
- 合法的“fine extraction 返回零条 memory”仍是 completed，不可误判为失败；
- timeout、failed、缺少预期 `MEM_READ` 都 fail-fast；
- patch 可由 source lock fetch 脚本确定性重放，并进入 source identity。

这属于 failure propagation + observability compatibility patch，不改变成功态算法核心。

## 4. M2 继续消费的输入语义

- ingest 建议使用 `session` 粒度；MemOS 不要求 user/assistant pair，也不需要 placeholder。
- 每条 message 显式带：

  ```text
  role
  content
  chat_time = turn time -> session time -> None
  message_id = canonical public turn id
  ```

- canonical 空 content 不送入 MemOS；不得制造非空假回复。adapter 仍要用强反例证明不会
  触发 upstream “空 content 丢 `chat_time/message_id`”分支。
- LoCoMo 图片沿用 framework 稳定文本契约
  `[Sharing image that shows: {caption}]`，与原 content 一起走普通 text message；
  主 profile 不为 caption 启动 MemOS vision pipeline。
- clean retry 禁止调用无 namespace 的 `delete_by_memory_ids()`；只走
  `delete_by_filter(writable_cube_ids=[namespace], ...)` 或等价 namespace-scoped clear，
  并以重新检索为空作为完成后置条件。

## 5. Metric 资格保持诚实

R2 只关闭 lifecycle，不提前替 M3 宣判：

| 格 | 当前裁决 |
| --- | --- |
| HaluMem QA | `valid` 候选，待 adapter 零 API链与真实 smoke |
| HaluMem extraction | `pending`；必须从 async `MEM_READ` 的 task-scoped fine output 取本 session 新记忆，不能改走 sync variant |
| HaluMem update | `pending`；待 current-state readout 与真实 DB 链 |
| HaluMem memory type | `N/A`；MemOS ontology 不等于 Event/Persona/Relationship |
| Recall / NDCG / stable ranking | `pending`；window-wide sources 不能自动升级为 turn-exact semantic provenance |

若 async task-scoped fine output 无法用纯观测获得，HaluMem extraction 应降为 `N/A`，而不是
再次改算法。

## 6. 下一步

当前唯一入口是
[`../cards/actor-prompt-memos-v2-0-25-async-lifecycle-r2.md`](../cards/actor-prompt-memos-v2-0-25-async-lifecycle-r2.md)。
R2 通过后才写“一张 adapter 实现卡 + 五格强反例”。
