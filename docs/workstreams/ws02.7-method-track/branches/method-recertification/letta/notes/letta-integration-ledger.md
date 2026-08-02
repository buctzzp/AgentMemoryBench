# Letta/MemGPT Method Integration Ledger v1

> 本账在任何 adapter 代码之前创建。当前只登记已知边界与下一取证动作，**不把旧 MemGPT
> 印象、README 宣传或其他 method 判例冒充 Letta current source 事实**。完整判据见
> [Method 接入标准清单](../../../../../../reference/method-integration-checklist.md)。

<!-- method-integration-ledger
contract_version: method-integration-ledger-v1
method_id: letta
display_name: Letta/MemGPT
ledger_state: in_progress
integration_page: docs/reference/integration/letta.md
dossier: none
frozen_note: none
-->

## 必填检查点

<!-- ledger-checkpoints:start -->
| ID | 完成判据 | Status | 证据、裁决与下一动作 |
| --- | --- | --- | --- |
| B0-OFFICIAL-BENCHMARKS | 当前官方 repo 实际跑过的 benchmark、入口和版本已穷举，未跑过者标 framework extension | PENDING | evidence=[B0 判据](../../../../../../reference/method-integration-checklist.md#b0-官方评测-harness-parity-matrix写-adapter-前的前置门); ruling=current upstream 尚未联网锁定，不声明官方覆盖范围; next=核实官方组织、仓库、release 后穷举 eval 与 benchmark 入口 |
| B0-FINAL-PAYLOAD | 每个官方 harness 展开后的 add 次数、batch、role、namespace、时间、模型参数和 search 最终 payload 已锁 | PENDING | evidence=[B0 判据](../../../../../../reference/method-integration-checklist.md#b0-官方评测-harness-parity-matrix写-adapter-前的前置门); ruling=尚无 current payload 一手锚; next=从官方 harness 追到最终 product add/search payload 并记录文件行号 |
| B0-DIFFERENCE-RULING | 主轨、author 轨、framework extension、upstream bug 的每项差异已唯一归类 | PENDING | evidence=[配置政策](../../../../../../reference/method-toml-and-answer-builder-policy.md); ruling=没有 payload matrix 前不提前划轨; next=完成 B0 payload 后逐差异裁定唯一身份 |
| B1-SOURCE-LOCK | 官方 repo、tag、commit、license、vendored 路径、patch 和更新策略已锁定 | PENDING | evidence=[来源锁判据](../../../../../../reference/method-integration-checklist.md#b1-来源锁与接口选择); ruling=旧 MemGPT 与 current Letta 身份可能漂移，当前不沿用历史印象; next=联网核实最新官方 GitHub、稳定 release、license 与可复现 commit |
| B1-PRODUCT-SURFACE | ingest/retrieve 采用通用产品接口，并解释为何不用 chat、ask、eval、cloud 或 HTTP 专用入口 | PENDING | evidence=[产品接口判据](../../../../../../reference/method-integration-checklist.md#b1-来源锁与接口选择); ruling=尚未裁定 local core、SDK、server 或 archival-memory surface; next=枚举 current product 写入与只读检索接口及其算法调用链 |
| B1-LIFECYCLE-CALLGRAPH | prepare、ingest、retrieve、finalize、cleanup 的 runner 真实调用点和早失败路径已逐一闭合 | PENDING | evidence=[生命周期判据](../../../../../../reference/method-integration-checklist.md#b1-来源锁与接口选择); ruling=尚未形成 Letta runtime owner 与 runner 调用图; next=在接口选择后反查五个 hook 的真实调用与失败清理路径 |
| B2-GRANULARITY | 原生输入单元、consume_granularity、placeholder、session 边界和尾部残项处理已裁定 | PENDING | evidence=[B2 判据](../../../../../../reference/method-integration-checklist.md#b2-注入粒度consume_granularity); ruling=不从其他 method 的 turn、pair 或 session 结论外推; next=核 product message ingestion 与官方 harness 的真实 batching |
| B3-ISOLATION-CLEAN | 物理或逻辑隔离的写入、过滤、单空间删除和 clean-retry 等价性已证明 | PENDING | evidence=[B3 判据](../../../../../../reference/method-integration-checklist.md#b3-隔离方式物理-vs-逻辑); ruling=namespace 与删除能力未审，暂不宣称并行安全; next=取证 agent/user/block namespace 的写检删三链及失败态清理 |
| B3-PARALLEL-OWNERSHIP | process-global 缓存、client、DB、线程和 worker 所有权已审，W1/W2 资格有反例或实证 | PENDING | evidence=[并行判据](../../../../../../reference/method-integration-checklist.md#b11-主配置-smoke--冻结); ruling=W2 资格未知，不能由独立 provider 实例数量推断; next=审 runtime、DB、client 与 background worker 所有权后设计零 API 与真实哨兵 |
| B4-INPUT-VISIBILITY | role、speaker、content、turn/session time、place、image caption、source id 均沿算法可见链核实 | PENDING | evidence=[B4 判据](../../../../../../reference/method-integration-checklist.md#b4-输入可见性--formatted_memory-完整性含时间地点); ruling=API 字段存在不等于 memory build 算法可见; next=沿 parser、prompt、storage、update 链逐字段追踪五格公开输入 |
| B4-READOUT-COMPLETENESS | 产品答题前实际检索的全部记忆层、顺序和时间字段均进入 formatted_memory | PENDING | evidence=[B4 判据](../../../../../../reference/method-integration-checklist.md#b4-输入可见性--formatted_memory-完整性含时间地点); ruling=尚未确认 archival、recall、core memory 等层的 current 产品语义; next=对照产品 answer 流程锁定全部只读层与公开排序 |
| B5-PROVENANCE | 当前检索条目的 semantic source lineage 资格按运行时事实判 valid、N/A 或 pending | PENDING | evidence=[B5 判据](../../../../../../reference/method-integration-checklist.md#b5-provenance-能力); ruling=尚未看到 current retrieved item 与源消息的语义映射; next=核写入后更新、summary 与检索返回结构再逐 benchmark 裁定 |
| B5-RANKING-TOPK | 检索 item 粒度、top-k 总量或分路、dedup、rerank、稳定顺序和 NDCG 资格已锁 | PENDING | evidence=[B5 判据](../../../../../../reference/method-integration-checklist.md#b5-provenance-能力); ruling=top-k 与多层合并语义未知，不提前承诺 Recall 或 NDCG; next=追产品 search 最终排序、截断、去重和层间合并 |
| B5-LOSSLESS-RETROFIT | provenance 与 HaluMem 缺口已评估直接支持、可无损观测改造或不可改造 | PENDING | evidence=[B5+ 判据](../../../../../../reference/method-integration-checklist.md#b5-能力缺口的无损改造评估2026-07-13-新增导师建议); ruling=任何 sidecar 或观测 patch 都必须先证明不绕过核心算法; next=在 B5 与 HaluMem 接口取证后逐缺口三态裁决 |
| B6-FLUSH-COMPLETION | flush、update、summary、后台任务和“何时完成”的边界已接线并能传播失败 | PENDING | evidence=[B6 判据](../../../../../../reference/method-integration-checklist.md#b6-flush--finalize-时机correctness-关键); ruling=尚不清楚 product 是否有 heartbeat、background summarize 或 explicit flush; next=建立成功与失败时序图并设计 terminal-state 强反例 |
| B7-OBSERVABILITY | build、retrieve、answer、judge 的 LLM、embedding、token、latency 和 scope 可观测 | PENDING | evidence=[B7 判据](../../../../../../reference/method-integration-checklist.md#b7-效率插桩api_usage-优先); ruling=尚未核 Letta build LLM 与 embedding 的调用封装层; next=枚举全部模型调用点并优先接 api_usage 观测 |
| B8-RETRIEVAL-SIDE-EFFECTS | 检索读副作用与污染写入已区分，算法固有状态变化不被误删 | PENDING | evidence=[B8 判据](../../../../../../reference/method-integration-checklist.md#b8-检索副作用--clean-retry); ruling=产品 recall/search 是否更新状态尚未核实; next=对照官方产品与评测流程检查读路径写副作用 |
| B8-RESILIENCE-RESUME | 全部外部调用有 timeout、retry、失败语义、半写清理、安全 resume 与 secret 边界 | PENDING | evidence=[B8+ 判据](../../../../../../reference/method-integration-checklist.md#b8-外部调用韧性超时重试失败兜底用户-2026-07-14-新增); ruling=网络、DB、LLM、embedding 调用点尚未穷举; next=建立调用点清单并对每点锁 timeout、retry、半写恢复和 secret 负空间 |
| B9-MODEL-IDENTITY | build LLM、embedding、revision、dimension、normalization、distance 与本地模型身份已声明 | PENDING | evidence=[B9 判据](../../../../../../reference/method-integration-checklist.md#b9-模型口径); ruling=不把 README 默认或云端漂移模型冒充 pinned identity; next=从 current config schema 与 factory 追到具体产品默认和可控覆盖项 |
| B10-TOML-MANIFEST | smoke 和 official_full 主配置、稀疏 author section、解析配置与 resume identity 已锁 | PENDING | evidence=[TOML 政策](../../../../../../reference/method-toml-and-answer-builder-policy.md); ruling=adapter 与 source identity 未定前不创建伪完整 TOML; next=完成接口裁决后定义主配置并锁 manifest/resume identity |
| B10-ANSWER-JUDGE-BUILDER | benchmark 主 builder 与作者完整 builder 的变量、messages、decoding、judge 和私有边界已核 | PENDING | evidence=[builder 政策](../../../../../../reference/method-toml-and-answer-builder-policy.md); ruling=主表仍用 benchmark builder，author builder 只在官方 harness 有一手证据时建立; next=从 B0 matrix 提取作者完整 builder 变量与 decoding 差异 |
| GRID-LOCOMO | 稳定异常、双 speaker、image、时间、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=[LoCoMo 稳定页](../../../../../../reference/integration/locomo.md) / payload=待 Letta product 取证 / metric=待 readout 与 lineage 裁决 / privacy=gold 与 evidence 继续私有 / smoke=source lock 后由 planner 生成; ruling=复用 benchmark 稳定事实但不复用其他 method payload; next=验证双 speaker、caption、时间与 namespace 的 Letta 映射 |
| GRID-LONGMEMEVAL | 稳定异常、role 异形、时间、完整 haystack、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=[LongMemEval 稳定页](../../../../../../reference/integration/longmemeval.md) / payload=待 Letta product 取证 / metric=待 item 粒度与 rank 裁决 / privacy=question 私有字段不进 method / smoke=source lock 后由 planner 生成; ruling=保留 role 异形与原始顺序，是否 session 注入待接口裁决; next=用稳定异常样本走 canonical 到最终 payload 强反例 |
| GRID-MEMBENCH | first/third、尾部 time/place、missing-time noise、gold 异常、最终 payload、指标与 smoke 独立闭合 | PENDING | evidence=stable=[MemBench 稳定页](../../../../../../reference/integration/membench.md) / payload=待 Letta product 取证 / metric=待 current memory item 资格裁决 / privacy=question time 与 gold 只进允许侧 / smoke=source lock 后由 planner 生成; ruling=正文尾部 time/place 无损保留，typed channel 是否可用待核; next=覆盖 first/third、missing-time noise 与 gold-private 强反例 |
| GRID-BEAM | variant、时间、10M orphan/mismatch、最终 payload、abstention、指标与 smoke 独立闭合 | PENDING | evidence=stable=[BEAM 稳定页](../../../../../../reference/integration/beam.md) / payload=待 Letta product 取证 / metric=单 message gold 与 method item 粒度待裁 / privacy=abstention label 不进 method / smoke=100k 与 10m 需各自 planner; ruling=不按重复 raw id 建公共 turn identity，不修写 10M 原文; next=验证正常 pair 与两个 10M 异形窗口的最终 payload |
| GRID-HALUMEM | 固定 shape、session-local delta、四类 operation、最终 payload、指标、隐私与 W1 独立闭合 | PENDING | evidence=stable=[HaluMem 稳定页](../../../../../../reference/integration/halumem.md) / payload=待 Letta session-local 产物接口取证 / metric=逐 operation 独立裁决 / privacy=memory points 与 gold 仅在 evaluator 私有侧 / smoke=固定 4-session、1-QA、W1 planner / operations=extraction/update/qa/memory_type; ruling=不能因 QA 可测就推定 extraction 或 update 可测; next=核每 session 新记忆 delta、更新探针与 memory type 可见性 |
| B11-DOSSIER | 一份 living dossier 已按五 benchmark 分章并链接承重 note、异常处置和失效触发器 | PENDING | evidence=[dossier 判据](../../../../../../reference/method-integration-checklist.md#b11-主配置-smoke--冻结); ruling=取证尚未完成，当前 ledger 不能替代五格 safety dossier; next=M1 裁决后建立一份 Letta 五格 living dossier |
| B11-SMOKE-PLAN | 每个 concrete variant 的 smoke-plan-v1 已无 API 生成、审阅并保存，命令未手写 | PENDING | evidence=[机器计划门](../../../../../../reference/method-integration-checklist.md#b11-主配置-smoke--冻结); ruling=尚无 Letta registry/TOML，当前不能生成 truthful plan; next=注册与配置落地后逐 concrete variant 运行 plan-smoke 并保存 JSON |
| B11-REAL-SMOKE | planner 生成的全部 predict 与适用 evaluator 已真实执行，固定 shape 未误传裁剪参数 | PENDING | evidence=[smoke 五件套](../../../../../../reference/method-integration-checklist.md#b11-主配置-smoke--冻结); ruling=未经用户单独授权不得启动 Letta 真实 API smoke; next=离线门全绿后提交预算、run id 和机器计划给用户批准 |
| B11-ARTIFACT-GATE | manifest、prediction、formatted_memory、private labels、efficiency、state 与 summary 已逐 run 开箱 | PENDING | evidence=[artifact 判据](../../../../../../reference/method-integration-checklist.md#b11-主配置-smoke--冻结); ruling=没有真实 run 前不以零 API fixture 冒充开箱; next=真实 smoke 后按每个 child run 逐项机器验货与人工抽查 |
| B11-PARALLEL-GATE | 每个适用 variant 的 W1/W2 已实测，或 W1-only 的产品硬约束和 CLI 预启动拒绝已证明 | PENDING | evidence=[并行判据](../../../../../../reference/method-integration-checklist.md#b11-主配置-smoke--冻结); ruling=Letta W2 当前未知; next=先离线锁 owner 隔离，再按 planner 资格执行最小真实 W1/W2 或证明 W1-only |
| B11-REGRESSION-GATE | 定向强反例、全量 pytest、compileall、diff check 与第三方 patch identity 均通过 | PENDING | evidence=[冻结门](../../../../../../reference/method-integration-checklist.md#b11-主配置-smoke--冻结); ruling=尚无 Letta 生产改动可验收; next=实现后先定向、再主树全量与 vendored identity 复验 |
| B11-FREEZE-SYNC | frozen note、integration page、总表、workstream README、roadmap 和 ledger 状态已同步 | PENDING | evidence=[状态维护规则](../../../../../../reference/integration-status.md#三维护约定); ruling=Letta 当前仅为接入起点，严禁提前写 frozen; next=B0-B11 全部 PASS 或 N/A 后执行对表仪式并同步状态 |
<!-- ledger-checkpoints:end -->

## 架构师签字

- 当前 ledger 状态：`in_progress`
- 当前事实边界：仅确认 Letta/MemGPT 是 Phase 1 下一家 method；current upstream 身份尚待联网锁定。
- 架构师判词：`LEDGER_OPENED_BEFORE_SOURCE_AUDIT`。
