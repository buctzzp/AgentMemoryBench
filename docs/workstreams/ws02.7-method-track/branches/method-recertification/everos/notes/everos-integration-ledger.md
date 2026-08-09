# EverOS Method Integration Ledger v1

> 本账在 adapter 代码前建立。五家 benchmark 的稳定事实直接链接既有页，只登记 EverOS 的
> method 差量；完整判据见
> [Method 接入标准清单](../../../../../../reference/method-integration-checklist.md)。

<!-- method-integration-ledger
contract_version: method-integration-ledger-v1
method_id: everos
display_name: EverOS
ledger_state: in_progress
integration_page: docs/reference/integration/everos.md
dossier: none
frozen_note: none
-->

## 必填检查点

<!-- ledger-checkpoints:start -->
| ID | 完成判据 | Status | 证据、裁决与下一动作 |
| --- | --- | --- | --- |
| B0-OFFICIAL-BENCHMARKS | 当前官方 repo 实际跑过的 benchmark、入口和版本已穷举，未跑过者标 framework extension | PASS | evidence=[M1 §3](./everos-current-source-product-m1-ruling.md); ruling=current EverOS/EverAlgo 公开 harness 仅 LoCoMo；LongMemEval 只有论文结果、无公开最终 payload；HaluMem/BEAM/MemBench 为 framework extension; next=none |
| B0-FINAL-PAYLOAD | 每个官方 harness 展开后的 add 次数、batch、role、namespace、时间、模型参数和 search 最终 payload 已锁 | PASS | evidence=[M1 §3.1-3.3](./everos-current-source-product-m1-ruling.md); ruling=current product 与 research v93.05 两套 LoCoMo payload 分开锁定，LongMemEval 公开 payload 缺失诚实标 pending author parity; next=none |
| B0-DIFFERENCE-RULING | 主轨、author 轨、framework extension、upstream bug 的每项差异已唯一归类 | PASS | evidence=[M1 §3-5](./everos-current-source-product-m1-ruling.md); ruling=typed product service=主轨，LoCoMo product harness=author candidate，research stages=calibration not product，LME paper-only，三家 extension，caption loss=upstream harness drift; next=none |
| B1-SOURCE-LOCK | 官方 repo、tag、commit、license、vendored 路径、patch 和更新策略已锁定 | PASS | evidence=[M1-R1 §2-4](./everos-v1.2.3-source-drift-m1-r1.md); ruling=EverOS v1.2.3@48fc908 与 exact EverAlgo 0.4.0 tags/PyPI lock 均为 Apache-2.0 public source；无 patch，PDF local-only；M1 payload 文件 byte-stable; next=none |
| B1-PRODUCT-SURFACE | ingest/retrieve 采用通用产品接口，并解释为何不用 chat、ask、eval、cloud 或 HTTP 专用入口 | PASS | evidence=[M1 §4](./everos-current-source-product-m1-ruling.md); ruling=official lifespan 内 typed memorize/search/get 与 HTTP route 同业务实现，transport-equivalent；direct EverAlgo与直接写库排除; next=none |
| B1-LIFECYCLE-CALLGRAPH | prepare、ingest、retrieve、finalize、cleanup 的 runner 真实调用点和早失败路径已逐一闭合 | PENDING | evidence=[M1 §4、§8](./everos-current-source-product-m1-ruling.md); ruling=目标调用图已锁但 framework 接线未实现; next=M2 实现 worker/lifespan/exact drain/cleanup 并锁强反例 |
| B2-GRANULARITY | 原生输入单元、consume_granularity、placeholder、session 边界和尾部残项处理已裁定 | PENDING | evidence=[M1 §6](./everos-current-source-product-m1-ruling.md); ruling=session+内部 batch+session flush 候选；assistant-only owner 仍是硬门; next=生产链验证空 user anchor 或诚实能力缺口 |
| B3-ISOLATION-CLEAN | 物理或逻辑隔离的写入、过滤、单空间删除和 clean-retry 等价性已证明 | PENDING | evidence=[M1 §8.2](./everos-current-source-product-m1-ruling.md); ruling=独占 worker/root 物理隔离已裁方向，尚未实现; next=证明 exit→tombstone/rmtree、失败保引用与 A/B 不互伤 |
| B3-PARALLEL-OWNERSHIP | process-global 缓存、client、DB、线程和 worker 所有权已审，W1/W2 资格有反例或实证 | PENDING | evidence=[M1 §8.2](./everos-current-source-product-m1-ruling.md); ruling=process-global singleton 已识别；W2 必须两套 worker/root/DB/lifecycle; next=M2 运行强反例和 planner 资格 |
| B4-INPUT-VISIBILITY | role、speaker、content、turn/session time、place、image caption、source id 均沿算法可见链核实 | PENDING | evidence=[M1 §6](./everos-current-source-product-m1-ruling.md); ruling=产品 DTO 与官方 LoCoMo 口径已锁，missing-time 与 assistant-only 尚未闭合; next=逐格 production payload 反例与 source-time sidecar |
| B4-READOUT-COMPLETENESS | 产品答题前实际检索的全部记忆层、顺序和时间字段均进入 formatted_memory | PENDING | evidence=[M1 §7](./everos-current-source-product-m1-ruling.md); ruling=Episodes-only 主 readout 候选；formatter 与 owner merge 未实现; next=锁所有 episode 字段、score/order/time、zero-hit/error |
| B5-PROVENANCE | 当前检索条目的 semantic source lineage 资格按运行时事实判 valid、N/A 或 pending | PENDING | evidence=[M1 §7](./everos-current-source-product-m1-ruling.md); ruling=reflection-off 时 Episode→memcell→message 为纯观测 valid candidate; next=M2 证明跨 batch/flush/cascade/resume 与 merged fail-safe |
| B5-RANKING-TOPK | 检索 item 粒度、top-k 总量或分路、dedup、rerank、稳定顺序和 NDCG 资格已锁 | PENDING | evidence=[M1 §7](./everos-current-source-product-m1-ruling.md); ruling=HYBRID/AGENTIC 产品顺序与 score 可见，双 owner merge/tie/top-k 尚未裁; next=M2 不重排强反例与资格矩阵 |
| B5-LOSSLESS-RETROFIT | provenance 与 HaluMem 缺口已评估直接支持、可无损观测改造或不可改造 | PENDING | evidence=[M1 §7](./everos-current-source-product-m1-ruling.md); ruling=internal ledger sidecar与session-filtered get均为无损候选; next=M2 实证后逐 operation 判 valid/N/A |
| B6-FLUSH-COMPLETION | flush、update、summary、后台任务和“何时完成”的边界已接线并能传播失败 | PENDING | evidence=[M1 §8.1](./everos-current-source-product-m1-ruling.md); ruling=memorize 返回不等于 Cascade/OME 终态，官方 polling 仍需收紧 scope/late-task/failure; next=M2 exact drain 状态机 |
| B7-OBSERVABILITY | build、retrieve、answer、judge 的 LLM、embedding、token、latency 和 scope 可观测 | PENDING | evidence=[M1 §8.3](./everos-current-source-product-m1-ruling.md); ruling=调用点已枚举方向，exact usage wrapper 未实现; next=M2 按 stage/scope 接线且不估算 |
| B8-RETRIEVAL-SIDE-EFFECTS | 检索读副作用与污染写入已区分，算法固有状态变化不被误删 | PASS | evidence=[M1 §7](./everos-current-source-product-m1-ruling.md); ruling=current SearchManager/service 只读 LanceDB/Markdown/SQLite buffer，query 不触发 memorize/OME write；telemetry 不算 memory mutation; next=none |
| B8-RESILIENCE-RESUME | 全部外部调用有 timeout、retry、失败语义、半写清理、安全 resume 与 secret 边界 | PENDING | evidence=[M1 §8](./everos-current-source-product-m1-ruling.md); ruling=upstream 各调用已有部分 retry，但 framework operation journal/ambiguous replay/clean retry 未实现; next=M2 完成原子 state 与 secret negative-space |
| B9-MODEL-IDENTITY | build LLM、embedding、revision、dimension、normalization、distance 与本地模型身份已声明 | PENDING | evidence=[M1 §2、§5、§8.3](./everos-current-source-product-m1-ruling.md); ruling=官方 Qwen4B/1024/reranker 与 smoke LLM 已知，主 product-default embedding transport 尚待可运行配置; next=M2 TOML+runtime preflight+manifest |
| B10-TOML-MANIFEST | smoke 和 official_full 主配置、稀疏 author section、解析配置与 resume identity 已锁 | PENDING | evidence=[M1 §5](./everos-current-source-product-m1-ruling.md); ruling=main fixed cross-five 与 author boundary 已裁方向，尚未实现; next=M2 配置解析、强反例与 resume mismatch |
| B10-ANSWER-JUDGE-BUILDER | benchmark 主 builder 与作者完整 builder 的变量、messages、decoding、judge 和私有边界已核 | PENDING | evidence=[M1 §3、§5](./everos-current-source-product-m1-ruling.md); ruling=主轨 framework builder；current LoCoMo product/research builders 不同，author target待唯一实现; next=M2 builder identity与private negative-space |
| GRID-LOCOMO | 稳定异常、双 speaker、image、时间、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=[LoCoMo 稳定页](../../../../../../reference/integration/locomo.md) / payload=[M1 §3.1-3.2](./everos-current-source-product-m1-ruling.md) / metric=[M1 §7](./everos-current-source-product-m1-ruling.md) / privacy=[M1 §6.3](./everos-current-source-product-m1-ruling.md) / smoke=none; ruling=官方双 user-owner/单 owner search 与两套 caption/time 口径已知，adapter未实现; next=M2 完成 payload/lineage/readout/plan |
| GRID-LONGMEMEVAL | 稳定异常、role 异形、时间、完整 haystack、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=[LongMemEval 稳定页](../../../../../../reference/integration/longmemeval.md) / payload=[M1 §3.3、§6](./everos-current-source-product-m1-ruling.md) / metric=[M1 §7](./everos-current-source-product-m1-ruling.md) / privacy=[M1 §6.3](./everos-current-source-product-m1-ruling.md) / smoke=none; ruling=paper-only author parity，assistant-only owner 未闭合; next=M2 完整 session 异形强反例与资格 |
| GRID-MEMBENCH | first/third、尾部 time/place、missing-time noise、gold 异常、最终 payload、指标与 smoke 独立闭合 | PENDING | evidence=stable=[MemBench 稳定页](../../../../../../reference/integration/membench.md) / payload=[M1 §6](./everos-current-source-product-m1-ruling.md) / metric=[M1 §7](./everos-current-source-product-m1-ruling.md) / privacy=[M1 §6.3](./everos-current-source-product-m1-ruling.md) / smoke=none; ruling=原文 time/place 保留，missing-time 与产品 timestamp>0 冲突是硬门; next=M2 裁 operational time 或最小产品扩展并锁 sentinel |
| GRID-BEAM | variant、时间、10M orphan/mismatch、最终 payload、abstention、指标与 smoke 独立闭合 | PENDING | evidence=stable=[BEAM 稳定页](../../../../../../reference/integration/beam.md) / payload=[M1 §6](./everos-current-source-product-m1-ruling.md) / metric=[M1 §7](./everos-current-source-product-m1-ruling.md) / privacy=[M1 §6.3](./everos-current-source-product-m1-ruling.md) / smoke=none; ruling=canonical 原序不修 raw，cell-level provenance 与 single-message gold 资格 pending; next=M2 四 variant payload/abstention/plan |
| GRID-HALUMEM | 固定 shape、session-local delta、四类 operation、最终 payload、指标、隐私与 W1 独立闭合 | PENDING | evidence=stable=[HaluMem 稳定页](../../../../../../reference/integration/halumem.md) / payload=[M1 §6-8](./everos-current-source-product-m1-ruling.md) / metric=[M1 §7](./everos-current-source-product-m1-ruling.md) / privacy=[M1 §6.3](./everos-current-source-product-m1-ruling.md) / smoke=none / operations=extraction pending, update pending, qa pending, memory_type N/A candidate; ruling=session flush/get delta可行候选，必须等 exact drain; next=M2 逐 operation production readout |
| B11-DOSSIER | 一份 living dossier 已按五 benchmark 分章并链接承重 note、异常处置和失效触发器 | PENDING | evidence=[M1](./everos-current-source-product-m1-ruling.md); ruling=M1 不是五格完成档案; next=M2 创建 living dossier并逐格回链 |
| B11-SMOKE-PLAN | 每个 concrete variant 的 smoke-plan-v1 已无 API 生成、审阅并保存，命令未手写 | PENDING | evidence=none; ruling=registry/TOML尚未实现; next=M2 完成后运行 planner并保存原始 JSON |
| B11-REAL-SMOKE | planner 生成的全部 predict 与适用 evaluator 已真实执行，固定 shape 未误传裁剪参数 | PENDING | evidence=未获本 method 新预算批准; ruling=本批零 API; next=离线门完成后请求用户批准 |
| B11-ARTIFACT-GATE | manifest、prediction、formatted_memory、private labels、efficiency、state 与 summary 已逐 run 开箱 | PENDING | evidence=依赖真实 smoke; ruling=零报错不等于通过; next=真实 smoke 后逐 run 开箱 |
| B11-PARALLEL-GATE | 每个适用 variant 的 W1/W2 已实测，或 W1-only 的产品硬约束和 CLI 预启动拒绝已证明 | PENDING | evidence=[M1 §8.2](./everos-current-source-product-m1-ruling.md); ruling=独占 worker 是 W2 候选，不以 singleton 风险直接判 valid; next=M2 offline ownership + B11 real W1/W2 |
| B11-REGRESSION-GATE | 定向强反例、全量 pytest、compileall、diff check 与第三方 patch identity 均通过 | PENDING | evidence=本批仅 M1; ruling=尚无 adapter diff; next=M2 完成后跑扩展定向、full、compileall、source lock |
| B11-FREEZE-SYNC | frozen note、integration page、总表、workstream README、roadmap 和 ledger 状态已同步 | PENDING | evidence=[EverOS integration page](../../../../../../reference/integration/everos.md); ruling=当前仅 M1，不得冻结; next=全部门关闭后同步 |
<!-- ledger-checkpoints:end -->

## 架构师最终签字

- 当前 ledger 状态：`in_progress`
- 最后一次一手证据复核 commit：EverOS
  `48fc9084888bc17100053227284f939a5aca5e91`；EverAlgo runtime tags 见 M1-R1 §3
- 架构师判词：`EVEROS_V1_2_3_SOURCE_DRIFT_ACCEPTED_READY_FOR_M2`。
