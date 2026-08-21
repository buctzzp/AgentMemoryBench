# Method 产品接口与注入粒度总账

> 现行版本：2026-08-21；覆盖 Phase 1 的 10 家 method。
>
> 2026-07-09 的五家接口审计原文已归档到
> [`../archive/reference/2026-07-09-method-interface-inventory.md`](../archive/reference/2026-07-09-method-interface-inventory.md)。
> 现行事实以本页、对应 `integration/<method>.md` 与当前代码为准。

本页回答两个跨 method 问题：框架究竟把什么单元交给 adapter，以及产品 API 中的
`list[...]` 究竟装什么。每家产品接口的完整参数、返回类型与 adapter 映射在对应稳定页的
“产品接口契约”小节；本页不重复整份第三方 API 文档。

## 1. 先分清三层

1. **canonical turn**：benchmark adapter 先把原始数据规范成 `TurnEvent`，保留公开
   role、speaker、content、source time、image caption 与稳定 turn id。
2. **framework 消费粒度**：`GranularityAggregator` 根据 method registration，把事件聚合成
   `TurnEvent`、`TurnPair`、`SessionBatch` 或 `ConversationBatch`。这是“何时调用一次
   adapter `ingest()`”的契约。
3. **product call/batch**：adapter 再把一个 framework unit 映射成零个、一个或多个产品
   API 调用。产品参数恰好是 `list[...]`，只说明一次调用可装多条对象，**不决定**调用边界。

因此，`messages: list[dict]` 绝不自动等于 session ingest。一个 turn 可以包装成长度 1 的
list；一个 session 也可以在 adapter 内拆成多个长度 2/10/25 的 list。粒度以 registry 与
manifest 的 `consume_granularity` 为准，产品 batch policy 则必须另行记录。

框架公共类型（`src/memory_benchmark/core/provider_protocol.py`）：

```python
IngestUnit = TurnEvent | TurnPair | SessionBatch | ConversationBatch

MemoryProvider.ingest(unit: IngestUnit) -> IngestResult | None
MemoryProvider.end_session(ref: SessionRef) -> SessionMemoryReport | None
MemoryProvider.end_conversation(ref: UnitRef) -> None
MemoryProvider.retrieve(query: RetrievalQuery) -> RetrievalResult
```

`RetrievalQuery` 的公开字段为 `query_text: str`、`isolation_key: str`、
`question_time: str | None`、`top_k: int`、`purpose: RetrievalPurpose` 与可选公开
`source_question: Question | None`。`RetrievalResult` 至少包含非空
`formatted_memory: str`，并可带 `prompt_messages: tuple[PromptMessage, ...] | None`、
`items: tuple[RetrievedItem, ...] | None`、公开 `metadata: dict[str, Any]` 与逐题
`evidence: RetrievalEvidence | None`。gold answer/evidence/memory point 永不进入这些类型。

## 2. 十家 framework 粒度矩阵

| method | LoCoMo | LongMemEval | MemBench | BEAM | HaluMem |
| --- | --- | --- | --- | --- | --- |
| A-Mem | turn | turn | turn | turn | turn |
| MemoryOS | session | pair | session | session | session |
| MemOS | session | session | session | session | session |
| LightMem | turn | pair | pair | pair | session |
| SimpleMem | turn | turn | turn | turn | turn |
| Mem0 | turn | session | turn | pair | session |
| Letta/MemGPT | session | session | session | session | session |
| EverOS | session | session | session | session | session |
| LangMem | session | session | session | session | session |
| Graphiti | turn | turn | turn | turn | turn |

`pair` 是 user-anchored framework pair：user 开启，随后第一个非 user turn 闭合；orphan
assistant 与 dangling user 都形成单侧 `TurnPair(second=None)`，永不跨 session。是否给产品
补空侧由 method 自己的结构约束决定，不能在公共聚合器里造假回复。

## 3. `list[...]` 在十家里的真实含义

| method | 产品写入容器与一次调用边界 | 单侧/异常策略 |
| --- | --- | --- |
| A-Mem | 产品不是 list：每个 `TurnEvent` 依次 `analyze_content(str)`、`add_note(str, time)` | 不配 pair、不造 placeholder |
| MemoryOS | 产品不是 list：一个产品 page 调一次 `add_memory(user_input, agent_response, ...)`；session unit 在 adapter 内拆 pages | 产品强制双槽；缺一侧用空字符串结构槽，不虚构发言 |
| MemOS | `APIADDRequest.messages: list[dict]`；普通 benchmark 一个完整 session 一次 add；LoCoMo 官方双 namespace，每路按 2 条 positional chunk | singleton 合法，不补 placeholder；LoCoMo 奇数尾长度 1 |
| LightMem | `LightMemory.add_memory(messages)`；turn/pair unit 转成一组 native pair messages，HaluMem 整 session 一次 forced flush | 空侧有显式 placeholder marker，并镜像同 pair 真实 child 的 id/time 以保持 slot 对齐；不创造独立 source unit |
| SimpleMem | 主轨不用批量入口；一个 turn 调一次 `add_dialogue(speaker, content, timestamp)` | 不配 pair、不造 placeholder |
| Mem0 | `Memory.add(messages: str / dict / list[dict])`；turn=长度 1，pair=长度 1/2，LongMemEval session 在 adapter 内按位置每 2 条，HaluMem 整 session一份 list | singleton 原生合法，不造 placeholder |
| Letta/MemGPT | session messages 原序按最多 10 条切块；每块格式化成一个 wrapper 字符串，再作为一条 `MessageCreate` 进入 `AgentLoop.step()` | 不重新配对、不造 placeholder |
| EverOS | 一个 session operation；worker 再按最多 25 条构造 `MemorizeAddRequest.messages`，末尾显式 flush | 仅 pure-assistant session 加一个无 source identity 的空 user anchor，满足 Episode 边界 |
| LangMem | 一个 session 的 `list[{role, content}]` 一次交给 `MemoryStoreManager.ainvoke()` | 原生允许 assistant-first、same-role、singleton、odd tail；不补 placeholder |
| Graphiti | 产品不是 list：每个 turn 调一次 `Graphiti.add_episode(...)` | 不配 pair、不造 placeholder；source time 必填 |

## 4. 产品返回与 framework 返回不是一回事

产品可能返回 `None`、字符串 id、Pydantic response、`list[str]`、`list[dict]` 或内部对象。
adapter 必须先强校产品返回，再统一映射成：

- 写入：`IngestResult | None`；需要 HaluMem session-local extraction 时，边界钩子另返回
  `SessionMemoryReport | None`。
- 检索：`RetrievalResult`；`formatted_memory` 是 framework answer builder 真正消费的完整
  readout，`items` 只在产品有可公开、可稳定表达的逐项结果时提供。
- 资格：`RetrievalEvidence` 独立声明 semantic provenance 与 stable ranking。list 中带 id
  不自动等于可算 Recall；例如 A-Mem/LangMem 的 current memory 已演化，source ids 只能作
  audit lineage。

## 5. 逐家详细入口

- [A-Mem](integration/amem.md#产品接口契约参数返回与批次)
- [MemoryOS](integration/memoryos.md#产品接口契约参数返回与批次)
- [MemOS](integration/memos.md#产品接口契约参数返回与批次)
- [LightMem](integration/lightmem.md#产品接口契约参数返回与批次)
- [SimpleMem](integration/simplemem.md#产品接口契约参数返回与批次)
- [Mem0](integration/mem0.md#产品接口契约参数返回与批次)
- [Letta/MemGPT](integration/letta.md#产品接口契约参数返回与批次)
- [EverOS](integration/everos.md#产品接口契约参数返回与批次)
- [LangMem](integration/langmem.md#产品接口契约参数返回与批次)
- [Graphiti](integration/graphiti.md#产品接口契约参数返回与批次)

维护规则：产品签名、adapter granularity、list batching、placeholder、返回 shape 或
`RetrievalEvidence` 任一变化时，必须在同一个提交更新对应 integration 页和本总账；文档门
会检查十家页面都保留这一标准接口节。
