# LangMem Method Integration Ledger v1

> 本账在任何 adapter 代码之前创建。旧 ws02 审计只作待复核线索，不把 README 宣传、
> 第三方 baseline 或历史 pin 冒充 current product 事实。完整判据见
> [Method 接入标准清单](../../../../../../reference/method-integration-checklist.md)。

<!-- method-integration-ledger
contract_version: method-integration-ledger-v1
method_id: langmem
display_name: LangMem
ledger_state: in_progress
integration_page: docs/reference/integration/langmem.md
dossier: none
frozen_note: none
-->

## 必填检查点

<!-- ledger-checkpoints:start -->
| ID | 完成判据 | Status | 证据、裁决与下一动作 |
| --- | --- | --- | --- |
| B0-OFFICIAL-BENCHMARKS | 当前官方 repo 实际跑过的 benchmark、入口和版本已穷举，未跑过者标 framework extension | PASS | evidence=[M1 §3](./langmem-current-product-identity-m1-ruling.md); ruling=current official repo 对五家 benchmark 均无 harness，五格全为 framework extension，第三方 baseline 不冒充官方; next=none |
| B0-FINAL-PAYLOAD | 每个官方 harness 展开后的 add 次数、batch、role、namespace、时间、模型参数和 search 最终 payload 已锁 | N/A | evidence=[M1 §3](./langmem-current-product-identity-m1-ruling.md); ruling=官方 Phase 1 harness 集为空，不存在 author benchmark payload；产品 payload 由 M1/M2 另锁; next=none |
| B0-DIFFERENCE-RULING | 主轨、author 轨、framework extension、upstream bug 的每项差异已唯一归类 | PASS | evidence=[M1 §4-6](./langmem-current-product-identity-m1-ruling.md); ruling=async background manager=主轨，hot-path agent=ALGORITHM_VARIANT，direct put=MECHANISM_BYPASS，sync duplicate search=UPSTREAM BUG，当前无 author 轨; next=none |
| B1-SOURCE-LOCK | 官方 repo、tag、commit、license、vendored 路径、patch 和更新策略已锁定 | PASS | evidence=[M1 §2](./langmem-current-product-identity-m1-ruling.md); ruling=current 56d8593/package 0.0.30/MIT/selected hash 已锁，MANIFEST 与 fetch 已更新，无 patch; next=none |
| B1-PRODUCT-SURFACE | ingest/retrieve 采用通用产品接口，并解释为何不用 chat、ask、eval、cloud 或 HTTP 专用入口 | PASS | evidence=[M1 §4-6](./langmem-current-product-identity-m1-ruling.md); ruling=主轨用 create_memory_store_manager().ainvoke + asearch，避开 answer agent 与 raw-store bypass; next=none |
| B1-LIFECYCLE-CALLGRAPH | prepare、ingest、retrieve、finalize、cleanup 的 runner 真实调用点和早失败路径已逐一闭合 | PENDING | evidence=待实现; ruling=不得从协议声明反推 runner 已接线; next=adapter 阶段闭合 |
| B2-GRANULARITY | 原生输入单元、consume_granularity、placeholder、session 边界和尾部残项处理已裁定 | PASS | evidence=[M1 §7](./langmem-current-product-identity-m1-ruling.md); ruling=session 粒度，assistant-first/same-role/singleton/odd tail 原序合法，不补 placeholder、不跨 session; next=none |
| B3-ISOLATION-CLEAN | 物理或逻辑隔离的写入、过滤、单空间删除和 clean-retry 等价性已证明 | PENDING | evidence=待 namespace/store 探针; ruling=不能只凭 namespace 参数宣称隔离; next=闭合四项等价门 |
| B3-PARALLEL-OWNERSHIP | process-global 缓存、client、DB、线程和 worker 所有权已审，W1/W2 资格有反例或实证 | PENDING | evidence=待 runtime 设计与 W2 探针; ruling=未证前不宣称并行; next=闭合 worker/store/model ownership |
| B4-INPUT-VISIBILITY | role、speaker、content、turn/session time、place、image caption、source id 均沿算法可见链核实 | PENDING | evidence=待五格 production-path; ruling=typed metadata 不等于 LLM 可见; next=锁最终 message payload |
| B4-READOUT-COMPLETENESS | 产品答题前实际检索的全部记忆层、顺序和时间字段均进入 formatted_memory | PENDING | evidence=待 store search/readout 实现; ruling=只消费 product-ranked current memories; next=闭合格式与零命中 |
| B5-PROVENANCE | 当前检索条目的 semantic source lineage 资格按运行时事实判 valid、N/A 或 pending | N/A | evidence=[M1 §11](./langmem-current-product-identity-m1-ruling.md); ruling=current memory 经 old-memory search + LLM update/consolidation，无 lossless output-to-source mapping，source 参与关系不得冒充 semantic provenance; next=none |
| B5-RANKING-TOPK | 检索 item 粒度、top-k 总量或分路、dedup、rerank、稳定顺序和 NDCG 资格已锁 | PENDING | evidence=待 BaseStore search 探针; ruling=rank 可稳定不代表 provenance 有资格; next=分开裁定 ranking 与指标 |
| B5-LOSSLESS-RETROFIT | provenance 与 HaluMem 缺口已评估直接支持、可无损观测改造或不可改造 | PASS | evidence=[M1 §11](./langmem-current-product-identity-m1-ruling.md); ruling=provenance 与 HaluMem extraction/type 不可无损改造故 N/A；update/QA 走 current state 产品接口直接支持候选; next=none |
| B6-FLUSH-COMPLETION | flush、update、summary、后台任务和“何时完成”的边界已接线并能传播失败 | PENDING | evidence=待 async manager/worker 实证; ruling=await 返回候选完成门; next=锁失败传播与持久化顺序 |
| B7-OBSERVABILITY | build、retrieve、answer、judge 的 LLM、embedding、token、latency 和 scope 可观测 | PENDING | evidence=待 callback/embedder wrapper; ruling=API usage 优先、本地 embedding 用 tokenizer estimate; next=实现逐调用 observation |
| B8-RETRIEVAL-SIDE-EFFECTS | 检索读副作用与污染写入已区分，算法固有状态变化不被误删 | PASS | evidence=[M1 §8-9](./langmem-current-product-identity-m1-ruling.md); ruling=retrieve 只调用 manager.asearch/BaseStore.asearch，query 不进入 manager.ainvoke、不触发 put/delete/LLM; next=none |
| B8-RESILIENCE-RESUME | 全部外部调用有 timeout、retry、失败语义、半写清理、安全 resume 与 secret 边界 | PENDING | evidence=待 worker/persistence 设计; ruling=InMemoryStore 重启丢失不能冒充可 resume; next=实现精确 snapshot 或明确阻断 |
| B9-MODEL-IDENTITY | build LLM、embedding、revision、dimension、normalization、distance 与本地模型身份已声明 | PENDING | evidence=待 TOML/runtime 锁定; ruling=主轨候选 controlled MiniLM-384 + runtime profile LLM; next=验证本地模型与 store index |
| B10-TOML-MANIFEST | smoke 和 official_full 主配置、稀疏 author section、解析配置与 resume identity 已锁 | PENDING | evidence=待实现; ruling=五格共用主 section，当前无证据不建 author section; next=新增强类型 TOML 与 manifest |
| B10-ANSWER-JUDGE-BUILDER | benchmark 主 builder 与作者完整 builder 的变量、messages、decoding、judge 和私有边界已核 | PENDING | evidence=待五格 dossier; ruling=LangMem 只提供 memory，不参与 framework answer/judge; next=闭合五格公开输入 |
| GRID-LOCOMO | 稳定异常、双 speaker、image、时间、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=待引用稳定页 / payload=待实现 / metric=待裁 / privacy=待强反例 / smoke=待计划; ruling=复用 benchmark 稳定事实; next=完成 LangMem 差量 |
| GRID-LONGMEMEVAL | 稳定异常、role 异形、时间、完整 haystack、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=待引用稳定页 / payload=待实现 / metric=待裁 / privacy=待强反例 / smoke=待计划; ruling=不重扫 raw census; next=完成 LangMem 差量 |
| GRID-MEMBENCH | first/third、尾部 time/place、missing-time noise、gold 异常、最终 payload、指标与 smoke 独立闭合 | PENDING | evidence=stable=待引用稳定页 / payload=待实现 / metric=待裁 / privacy=待强反例 / smoke=待计划; ruling=不删原文 time/place、不伪造 missing time; next=完成 LangMem 差量 |
| GRID-BEAM | variant、时间、10M orphan/mismatch、最终 payload、abstention、指标与 smoke 独立闭合 | PENDING | evidence=stable=待引用稳定页 / payload=待实现 / metric=待裁 / privacy=待强反例 / smoke=待计划; ruling=保留 canonical 原序与异常形状; next=完成 LangMem 差量 |
| GRID-HALUMEM | 固定 shape、session-local delta、四类 operation、最终 payload、指标、隐私与 W1 独立闭合 | PENDING | evidence=stable=待引用稳定页 / payload=待实现 / metric=待裁 / privacy=待强反例 / smoke=待计划 / operations=extraction/update/qa/memory_type; ruling=四项逐一判资格; next=完成 session delta 审计 |
| B11-DOSSIER | 一份 living dossier 已按五 benchmark 分章并链接承重 note、异常处置和失效触发器 | PENDING | evidence=待创建; ruling=一 method 一 dossier，不制造五份顶层文档; next=M2 后填写 |
| B11-SMOKE-PLAN | 每个 concrete variant 的 smoke-plan-v1 已无 API 生成、审阅并保存，命令未手写 | PENDING | evidence=待 registry 接入; ruling=禁止凭记忆复制旧命令; next=M2 后运行 planner |
| B11-REAL-SMOKE | planner 生成的全部 predict 与适用 evaluator 已真实执行，固定 shape 未误传裁剪参数 | PENDING | evidence=尚未获用户批准; ruling=真实 API 需新预算、规模、run id 批准; next=离线门完成后请求批准 |
| B11-ARTIFACT-GATE | manifest、prediction、formatted_memory、private labels、efficiency、state 与 summary 已逐 run 开箱 | PENDING | evidence=依赖真实 smoke; ruling=零报错不等于通过; next=真实 smoke 后开箱 |
| B11-PARALLEL-GATE | 每个适用 variant 的 W1/W2 已实测，或 W1-only 的产品硬约束和 CLI 预启动拒绝已证明 | PENDING | evidence=待并行资格裁决; ruling=以 runtime/store ownership 事实决定; next=M2 强反例与真实 smoke |
| B11-REGRESSION-GATE | 定向强反例、全量 pytest、compileall、diff check 与第三方 patch identity 均通过 | PENDING | evidence=待实现; ruling=最终由架构师亲自复跑; next=M2 后执行 |
| B11-FREEZE-SYNC | frozen note、integration page、总表、workstream README、roadmap 和 ledger 状态已同步 | PENDING | evidence=未到冻结门; ruling=真实 B11 前不得冻结; next=完成其余全部检查点 |
<!-- ledger-checkpoints:end -->

## 架构师最终签字

- 当前 ledger 状态：`in_progress`
- 最后一次一手证据复核 commit：`56d85939d80bb731bd5e237567148d817d7bfd16`
- 架构师判词：`READY_FOR_LANGMEM_M2`。
