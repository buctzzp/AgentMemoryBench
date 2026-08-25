# SimpleMem 接入实例（B1-B11）

> adapter：`src/memory_benchmark/methods/simplemem_adapter.py`
>
> 状态：**B1-B11 已按 current text product 重认证，`method-frozen-v1`。**
>
> 当前新 smoke/ws05 pilot 使用 `opencodego/ox-alpha-free`；既有冻结 run 仍按
> `gpt-4o-mini` 历史身份解释。现行运行身份见
> [`../api-runtime-profiles.md`](../api-runtime-profiles.md)。

## 接口调用面

| framework | SimpleMem 产品调用 | 裁决 |
|---|---|---|
| `ingest(TurnEvent)` | `add_dialogue(speaker, content, timestamp)` | turn；不配 pair、不造 placeholder |
| `end_session` | HaluMem 下 `finalize()` + 新 entry delta | extraction 可测；长期记忆不清空 |
| `end_conversation` | `finalize()` | 处理未满窗口的尾部 |
| `retrieve` | `hybrid_retriever.retrieve(query)` | framework 自己回答，不走 `ask()` |
| clean retry | 删除 conversation 独占 state dir | 物理隔离 |

## 产品接口契约（参数、返回与批次）

完整粒度矩阵见
[`../method-interface-inventory.md`](../method-interface-inventory.md)。SimpleMem 五格均为
`consume_granularity="turn"`；虽然产品另有 `add_dialogues(List[Dialogue])`，主轨并不调用它，
而是让每个 canonical turn 独立进入 `add_dialogue()`，从而保留产品窗口、overlap 与
`previous_entries` 的串行链。

| 产品调用 | 参数类型与本项目传值 | 产品返回 | adapter 映射 |
| --- | --- | --- | --- |
| `SimpleMemSystem.add_dialogue(speaker: str, content: str, timestamp: Optional[str] = None) -> None` | `speaker=event.speaker_name or event.role`；`content` 为原文+共享 caption；`timestamp` 经产品可接受格式解析，源缺失保持 `None` | 无显式 return，即 `None`；内部把一条 `Dialogue` 放入 buffer，窗口满时同步 synthesis | `IngestResult` 只报告公开 turn/time；不把 `None` 当写入失败 |
| `SimpleMemSystem.finalize() -> None` | 无参数；处理不足一个窗口的残余 buffer | 无显式 return，即 `None` | conversation 末尾调用；HaluMem 每个 session 边界调用后读取新 entry delta，并只清 extraction context，不删长期 memory |
| `HybridRetriever.retrieve(query: str, enable_reflection: Optional[bool] = None) -> list[MemoryEntry]` | `query=query.query_text`；主配置保留产品 reflection/planning；adapter 最终按 `query.top_k` 截公开结果 | 有序 `MemoryEntry` 列表；entry 含 `entry_id/lossless_restatement/timestamp/location/persons/entities/topic/keywords` 等产品字段 | 转为 `tuple[RetrievedItem, ...]` 与包含全部 reader 字段的 `formatted_memory`；绕开会自行答题的 `ask()` |

这里的 `list[MemoryEntry]` 是**检索返回容器**，不是 ingest 粒度。SimpleMem 不要求
user/assistant 交替，也不要求偶数条；LoCoMo speaker、LongMemEval 异形 role、MemBench
ThirdAgent 与 BEAM orphan 都逐 turn 原样写入，不造 placeholder。

## B1-B11

- **B1 ✅**：官方 repo 快照 `third_party/methods/SimpleMem`，upstream
  `60a48e83a7fef10d386e1f438589047d3a4257bc`，MIT；使用 text product。
- **B2 ✅**：五格均 turn ingest；原生 speaker/content/timestamp 覆盖具名 speaker 与 role。
- **B3 ✅**：每 conversation 独占 product system、LanceDB 与 state dir。
- **B4 ✅**：五种 source-time 格式与 None 强校验；MemBench 尾注原文保留；readout 回带产品
  timestamp/location/persons/entities/topic。
- **B5 ✅（N/A/pending 是通过）**：语义融合没有 exact source membership，provenance none，
  Recall/NDCG=N/A；多查询并行合并无全局 score/rerank，stable ranking=pending。
- **B6 ✅**：conversation 尾部 finalize；HaluMem 每 session finalize 后只清 extraction context，
  不删长期 memory。
- **构建并行裁决**：主配置显式 `enable_parallel_processing=false`。当前 adapter 逐 turn
  调用 `add_dialogue()`，窗口达到阈值后按顺序同步处理；不进入产品
  `add_dialogues_parallel()`，从而保留 overlap window 与上一窗口
  `previous_entries` 的链式依赖。检索阶段的 multi-query parallelism 属官方 Stage 3，
  与 build 连贯性无关，继续启用。
- **B7 ✅**：memory LLM、embedding、retrieval 与 framework answer 真实 observation 可落盘。
  官方 LLM client 使用 streaming；共享 transport 会请求 usage 尾块，并在完整消费后把
  SDK 精确 usage 记为 `api_usage`。真实 run `ws05-ox-p1-simplemem-locomo-r3` 已观测到
  9 次 LLM 调用，memory-build、retrieval、answer 均为 exact usage；tokenizer estimate
  只保留给没有 raw SDK response 的 fake/兼容 client。官方构造器打印 custom base URL 的
  行为已用可复现 patch 改为 `[configured]`，避免 terminal log 泄露 endpoint。
- **B8 ✅**：hybrid retrieval 不写 memory；endpoint/timeout/product retry 映射已锁强反例。
- **B9 ✅（controlled）**：当前主 build 为 MiniLM-384/internal-L2 + LanceDB L2；不是官方
  Qwen3 product-default，manifest 不冒充。
- **B10 ✅**：主 TOML 跨五 benchmark 固定；作者 builder/效果参数后续稀疏 section 处理。
- **B11 ✅**：五 benchmark 共 11 个正式真实 run，覆盖 LoCoMo/LME/MemBench 的 W1/W2、
  BEAM 100K/10M 的 W1/W2 与 HaluMem operation-level；state、worker 隔离、适用 evaluator、
  122 个 HaluMem judge scope 和效率 observation 全部通过机器门。冻结记录见
  [`simplemem-frozen-v1.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/simplemem/notes/simplemem-frozen-v1.md)。

实现与算法证据见
[`simplemem-text-v2-implementation.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/simplemem/notes/simplemem-text-v2-implementation.md)。

## ws05.1 M6 profile provenance（2026-08-25）

完整一手证据见
[`simplemem-profile-provenance.md`](../../workstreams/ws05.1-method-profile-provenance/notes/simplemem-profile-provenance.md)。

- **current product identity**：`aiming-lab/SimpleMem@60a48e83…` +
  `simplemem-product-compat.patch`；现行组合 source hash=`612d2f65…`。patch 只处理新版
  LanceDB native FTS、检索线程的观测上下文传播和 endpoint 日志脱敏，不改变成功路径的
  window/memory/retrieval topology。2026-08-25 upstream main 已到 `db80b6a7…`；M11 裁定不把该
  source upgrade 夹带进配置清理，若升级仍须独立算法审计。
- **论文与 current source 是 implementation variant**：论文三阶段是 Semantic Structured
  Compression、Online Semantic Synthesis、Intent-Aware Retrieval Planning；current source以
  `previous_entries` 条件化新 entry生成并 append，没有可独立识别的 existing-entry merge/update
  consumer。论文 W20/stride-or-overlap 5、Qwen3-1024、adaptive retrieval depth也不等于 main
  W40/O2、MiniLM-384、固定25/5/5。
- **构建串行是算法身份**：`add_dialogues_parallel()` 会让同批窗口共享提交前 context并按
  completion order聚合；main逐 turn调用 `add_dialogue()` 且显式关闭 build parallel，保留窗口间
  previous-context 因果链。retrieval parallel仍开，是不同的轴。
- **官方覆盖**：锁定 text repo只公开完整 LoCoMo harness；论文报告 LongMemEval-S，但没有闭合
  原始 text pipeline的公开 runner。后续 EvolveMem 的 LME/MemBench support只作同owner extension。
- **author profile**：LoCoMo current repo的 normal answer可重建，但 batch/parallel topology、
  paper effective config和source identity尚未闭合；category 5还把私有 `adversarial_answer` 放进
  answer选项，不能进入 framework。故 LoCoMo/LME均为 `AUTHOR_NOT_READY`；M11 未注册空壳 profile。
- **metric资格不变**：synthesized entry没有 exact source membership，semantic provenance继续
  N/A；multi-query completion-order合并且无global score/rerank，stable ranking继续 pending。

M6只新增证据与长期判词，不改变本页 B1-B11冻结状态，也不重标既有artifact。

M11 已把当前本地 MiniLM 锁为 bytes/tokenizer/pipeline/runtime identity，并以 20-file
`simplemem-text-main-v2` 组件闭包覆盖 product、lock、adapter 与 compat patch。新 run 使用 identity
v2/fresh-state；旧 artifact 只读。完整收据见
[M11 implementation](../../workstreams/ws05.1-method-profile-provenance/notes/m11-effective-config-source-embedding-implementation.md)。
