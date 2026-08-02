# LangMem 接入说明

状态：`M1 current source/product identity accepted；M2 adapter pending`。本页只承接经架构师验收的稳定摘要；
完整检查点与下一动作见
[LangMem integration ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/langmem/notes/langmem-integration-ledger.md)。

## Current source 与官方覆盖

- 官方来源：`langchain-ai/langmem`，current vendored commit
  `56d85939d80bb731bd5e237567148d817d7bfd16`，包版本 `0.0.30`，MIT。
- current repo 对 LoCoMo、LongMemEval、MemBench、BEAM、HaluMem 均无官方 harness；五格
  统一是 framework extension，当前不存在 author benchmark profile。
- 完整一手命令、source hash 与差异裁决见
  [M1 ruling](../../workstreams/ws02.7-method-track/branches/method-recertification/langmem/notes/langmem-current-product-identity-m1-ruling.md)。

## 产品 surface

- 主轨：官方 `create_memory_store_manager()` 的 async `ainvoke()`，每个 canonical session
  一次；retrieve 用同一 manager 的 `asearch()`，framework reader 独立答题。
- hot-path react agent 是会混入 agent tool policy 的算法变体；direct `BaseStore.put(raw
  turn)` 会绕过 extraction/update，均不进主轨。
- 主轨保留 public factory 默认：unstructured `Memory(content)`、insert/update 开、delete
  关、`query_model=None`、`query_limit=5`。current sync `invoke()` 会重复执行 old-memory
  search，故锁无此 bug 的 async surface。
- LangMem message contract 不要求 user-first、交替或偶数；assistant-first、same-role、
  singleton、odd tail 均合法，所以不补 placeholder。

## Metric 边界

- current memories 会被 LLM update/consolidate；source id 只能证明参与生成，不能证明当前
  content 的 semantic lineage。Recall/Precision/F1@k 与 NDCG 均 N/A。
- BaseStore 的实际 score/rank 可保留，stable ranking 待 M2 对 tie/resume 做强反例。
- HaluMem update/QA 是 valid 候选；extraction 与 memory-type 因不具备严格
  session-local memory point 而 N/A。

## 当前门

adapter 尚未实现；当前不得宣称五格 ready 或 B11 可运行。M2 必须闭合独立 runtime、
InMemoryStore 原子持久化/clean retry、W2 ownership、五格 payload、API/embedding 观测与
机器 smoke plans。
