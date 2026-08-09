# Graphiti Method Integration Ledger v1

<!-- method-integration-ledger
contract_version: method-integration-ledger-v1
method_id: graphiti
display_name: Graphiti
ledger_state: in_progress
integration_page: docs/reference/integration/graphiti.md
dossier: none
frozen_note: none
-->

## 必填检查点

<!-- ledger-checkpoints:start -->
| ID | 完成判据 | Status | 证据、裁决与下一动作 |
| --- | --- | --- | --- |
| B0-OFFICIAL-BENCHMARKS | 当前官方 repo 实际跑过的 benchmark、入口和版本已穷举，未跑过者标 framework extension | PASS | evidence=[M1 §4](./graphiti-v0.29.3-source-product-m1-ruling.md#4-official-benchmarkharness-matrix); ruling=current stable 仅有 LongMemEval graph-build eval，LoCoMo/HaluMem/BEAM/MemBench 均为 framework extension; next=none |
| B0-FINAL-PAYLOAD | 每个官方 harness 展开后的 add 次数、batch、role、namespace、时间、模型参数和 search 最终 payload 已锁 | PASS | evidence=[M1 §4.1](./graphiti-v0.29.3-source-product-m1-ruling.md#41-longmemeval-current-harness); ruling=official LME 每 turn 一次 add_episode(role: content, session date, user group)，同 user 串行；官方 eval 无 search/answer payload并已显式披露; next=none |
| B0-DIFFERENCE-RULING | 主轨、author 轨、framework extension、upstream bug 的每项差异已唯一归类 | PASS | evidence=[M1 §4-5](./graphiti-v0.29.3-source-product-m1-ruling.md); ruling=Graphiti OSS 不冒充 Zep；LME main payload official-compatible但完整评测仍 extension；其余四格 extension；MCP sentence-transformer 文档/实现漂移是 upstream gap; next=none |
| B1-SOURCE-LOCK | 官方 repo、tag、commit、license、vendored 路径、patch 和更新策略已锁定 | PASS | evidence=[M1 §2](./graphiti-v0.29.3-source-product-m1-ruling.md#2-source-lock); ruling=Apache-2.0 v0.29.3@021d3a5 vendored/fetch-pinned，main 漂移不自动进入主轨; next=none |
| B1-PRODUCT-SURFACE | ingest/retrieve 采用通用产品接口，并解释为何不用 chat、ask、eval、cloud 或 HTTP 专用入口 | PASS | evidence=[M1 §3](./graphiti-v0.29.3-source-product-m1-ruling.md#3-product-surface); ruling=direct add_episode/search 与官方 server 同 core且 completion 更强；禁止 direct node/edge insert；Zep hosted 不在范围; next=none |
| B1-LIFECYCLE-CALLGRAPH | prepare、ingest、retrieve、finalize、cleanup 的 runner 真实调用点和早失败路径已逐一闭合 | PENDING | evidence=[M1 §5](./graphiti-v0.29.3-source-product-m1-ruling.md#5-runtimeconfig-一手边界); ruling=direct async 候选已定，尚未闭合 framework runner 与 failure paths; next=M2 实证 FalkorDB Lite lifecycle/cleanup/worker ownership |
| B2-GRANULARITY | 原生输入单元、consume_granularity、placeholder、session 边界和尾部残项处理已裁定 | PENDING | evidence=[M1 §4.1、§6](./graphiti-v0.29.3-source-product-m1-ruling.md); ruling=turn episode、无 placeholder 是候选，五格特殊形状尚待 production payload 强反例; next=M2 五格 canonical event probes |
| B3-ISOLATION-CLEAN | 物理或逻辑隔离的写入、过滤、单空间删除和 clean-retry 等价性已证明 | PENDING | evidence=[M1 §5.1](./graphiti-v0.29.3-source-product-m1-ruling.md#51-数据库); ruling=独占 FalkorDB Lite file + group database 是候选; next=跨 group 写搜删与失败重试实证 |
| B3-PARALLEL-OWNERSHIP | process-global 缓存、client、DB、线程和 worker 所有权已审，W1/W2 资格有反例或实证 | PENDING | evidence=[M1 §5.1](./graphiti-v0.29.3-source-product-m1-ruling.md#51-数据库); ruling=embedded server/client 生命周期与并发尚未证; next=process ownership 审计后决定 W1/W2 |
| B4-INPUT-VISIBILITY | role、speaker、content、turn/session time、place、image caption、source id 均沿算法可见链核实 | PENDING | evidence=[M1 §6](./graphiti-v0.29.3-source-product-m1-ruling.md#6-五格初步输入裁决m2-必须用强反例再锁); ruling=五格候选已列，MemBench 100k missing-time 仍是硬缺口; next=逐格 payload/docstring+fake product probes |
| B4-READOUT-COMPLETENESS | 产品答题前实际检索的全部记忆层、顺序和时间字段均进入 formatted_memory | PENDING | evidence=[M1 §3.2](./graphiti-v0.29.3-source-product-m1-ruling.md#32-通用检索接口); ruling=default search 返回 edge facts 候选; next=锁完整字段、顺序、zero-hit 与多层是否应读 |
| B5-PROVENANCE | 当前检索条目的 semantic source lineage 资格按运行时事实判 valid、N/A 或 pending | PENDING | evidence=[M1 §7](./graphiti-v0.29.3-source-product-m1-ruling.md#7-metric-初判不是最终资格); ruling=EntityEdge.episodes 是候选但未证明 evolution 后语义承载; next=读 resolve/invalidation code并做冲突/merge反例 |
| B5-RANKING-TOPK | 检索 item 粒度、top-k 总量或分路、dedup、rerank、稳定顺序和 NDCG 资格已锁 | PENDING | evidence=[M1 §3.2、§7](./graphiti-v0.29.3-source-product-m1-ruling.md); ruling=edge RRF order/top-k 是候选; next=锁 candidate depth、ties、stable ranking 与 per-edge score语义 |
| B5-LOSSLESS-RETROFIT | provenance 与 HaluMem 缺口已评估直接支持、可无损观测改造或不可改造 | PENDING | evidence=[M1 §7](./graphiti-v0.29.3-source-product-m1-ruling.md#7-metric-初判不是最终资格); ruling=AddEpisodeResults 可能提供纯观测 sidecar; next=判 existing/resolved/invalidated edge 的 session-local extraction语义 |
| B6-FLUSH-COMPLETION | flush、update、summary、后台任务和“何时完成”的边界已接线并能传播失败 | PENDING | evidence=[M1 §3.1、§3.3](./graphiti-v0.29.3-source-product-m1-ruling.md); ruling=direct add_episode awaited 是候选 exact completion; next=所有内部 gather/DB/LLM failure 传播与 close实证 |
| B7-OBSERVABILITY | build、retrieve、answer、judge 的 LLM、embedding、token、latency 和 scope 可观测 | PENDING | evidence=[M1 §5.2-5.3](./graphiti-v0.29.3-source-product-m1-ruling.md); ruling=core 有 token_tracker但 embedding/latency/scope 尚未接 framework artifact; next=逐调用 observation contract |
| B8-RETRIEVAL-SIDE-EFFECTS | 检索读副作用与污染写入已区分，算法固有状态变化不被误删 | PENDING | evidence=[M1 §3.2](./graphiti-v0.29.3-source-product-m1-ruling.md#32-通用检索接口); ruling=search 表面只读，尚未做 DB mutation negative-space; next=前后 graph state 强反例 |
| B8-RESILIENCE-RESUME | 全部外部调用有 timeout、retry、失败语义、半写清理、安全 resume 与 secret 边界 | PENDING | evidence=[M1 §5](./graphiti-v0.29.3-source-product-m1-ruling.md#5-runtimeconfig-一手边界); ruling=LLM/embedding/DB均为外部点; next=timeout/retry/half-write journal/secret scan逐点关闭 |
| B9-MODEL-IDENTITY | build LLM、embedding、revision、dimension、normalization、distance 与本地模型身份已声明 | PENDING | evidence=[M1 §5.2-5.3](./graphiti-v0.29.3-source-product-m1-ruling.md); ruling=build runtime候选已定，embedding 文档/实现漂移未裁; next=M2 锁 local extension 或另批付费 embedding |
| B10-TOML-MANIFEST | smoke 和 official_full 主配置、稀疏 author section、解析配置与 resume identity 已锁 | PENDING | evidence=[M1 §4-5](./graphiti-v0.29.3-source-product-m1-ruling.md); ruling=尚无 Graphiti TOML/manifest; next=完成 runtime/embedding裁决后新增两个主 section |
| B10-ANSWER-JUDGE-BUILDER | benchmark 主 builder 与作者完整 builder 的变量、messages、decoding、judge 和私有边界已核 | PENDING | evidence=[M1 §4](./graphiti-v0.29.3-source-product-m1-ruling.md#4-official-benchmarkharness-matrix); ruling=current official LME 只有 graph-build evaluator、无完整 answer builder; next=五格统一 benchmark builder + 私有负空间反例 |
| GRID-LOCOMO | 稳定异常、双 speaker、image、时间、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=[LoCoMo 稳定页](../../../../../../reference/integration/locomo.md) / payload=[M1 §6](./graphiti-v0.29.3-source-product-m1-ruling.md#6-五格初步输入裁决m2-必须用强反例再锁) / metric=[M1 §7](./graphiti-v0.29.3-source-product-m1-ruling.md#7-metric-初判不是最终资格) / privacy=pending / smoke=pending; ruling=speaker(role)+caption+source time候选; next=M2五格档案与强反例 |
| GRID-LONGMEMEVAL | 稳定异常、role 异形、时间、完整 haystack、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=[LongMemEval 稳定页](../../../../../../reference/integration/longmemeval.md) / payload=[M1 §4.1](./graphiti-v0.29.3-source-product-m1-ruling.md#41-longmemeval-current-harness) / metric=[M1 §7](./graphiti-v0.29.3-source-product-m1-ruling.md#7-metric-初判不是最终资格) / privacy=pending / smoke=pending; ruling=official turn episode payload候选; next=M2异常/metric/privacy闭合 |
| GRID-MEMBENCH | first/third、尾部 time/place、missing-time noise、gold 异常、最终 payload、指标与 smoke 独立闭合 | PENDING | evidence=stable=[MemBench 稳定页](../../../../../../reference/integration/membench.md) / payload=[M1 §6](./graphiti-v0.29.3-source-product-m1-ruling.md#6-五格初步输入裁决m2-必须用强反例再锁) / metric=[M1 §7](./graphiti-v0.29.3-source-product-m1-ruling.md#7-metric-初判不是最终资格) / privacy=pending / smoke=pending; ruling=0-10k有时输入候选，100k missing-time unresolved; next=先裁 mandatory datetime 不造假边界 |
| GRID-BEAM | variant、时间、10M orphan/mismatch、最终 payload、abstention、指标与 smoke 独立闭合 | PENDING | evidence=stable=[BEAM 稳定页](../../../../../../reference/integration/beam.md) / payload=[M1 §6](./graphiti-v0.29.3-source-product-m1-ruling.md#6-五格初步输入裁决m2-必须用强反例再锁) / metric=[M1 §7](./graphiti-v0.29.3-source-product-m1-ruling.md#7-metric-初判不是最终资格) / privacy=pending / smoke=pending; ruling=turn episode原序候选; next=M2 variant/10m强反例 |
| GRID-HALUMEM | 固定 shape、session-local delta、四类 operation、最终 payload、指标、隐私与 W1 独立闭合 | PENDING | evidence=stable=[HaluMem 稳定页](../../../../../../reference/integration/halumem.md) / payload=[M1 §6](./graphiti-v0.29.3-source-product-m1-ruling.md#6-五格初步输入裁决m2-必须用强反例再锁) / metric=[M1 §7](./graphiti-v0.29.3-source-product-m1-ruling.md#7-metric-初判不是最终资格) / privacy=pending / smoke=pending / operations=extraction pending, update pending, qa pending, memory_type N/A candidate; ruling=AddEpisodeResults/session delta与current edge search待证; next=M2 operation probes |
| B11-DOSSIER | 一份 living dossier 已按五 benchmark 分章并链接承重 note、异常处置和失效触发器 | PENDING | evidence=[M1](./graphiti-v0.29.3-source-product-m1-ruling.md); ruling=尚未创建; next=M2/M3完成后写五格dossier |
| B11-SMOKE-PLAN | 每个 concrete variant 的 smoke-plan-v1 已无 API 生成、审阅并保存，命令未手写 | PENDING | evidence=[M1 §8](./graphiti-v0.29.3-source-product-m1-ruling.md#8-m1-判词); ruling=adapter/registry尚不存在; next=离线门后用planner生成 |
| B11-REAL-SMOKE | planner 生成的全部 predict 与适用 evaluator 已真实执行，固定 shape 未误传裁剪参数 | PENDING | evidence=[M1 §8](./graphiti-v0.29.3-source-product-m1-ruling.md#8-m1-判词); ruling=未获Graphiti真实API预算; next=离线门与plan通过后单独向用户申请 |
| B11-ARTIFACT-GATE | manifest、prediction、formatted_memory、private labels、efficiency、state 与 summary 已逐 run 开箱 | PENDING | evidence=[M1 §8](./graphiti-v0.29.3-source-product-m1-ruling.md#8-m1-判词); ruling=无真实run; next=B11 smoke后逐run开箱 |
| B11-PARALLEL-GATE | 每个适用 variant 的 W1/W2 已实测，或 W1-only 的产品硬约束和 CLI 预启动拒绝已证明 | PENDING | evidence=[M1 §5.1](./graphiti-v0.29.3-source-product-m1-ruling.md#51-数据库); ruling=FalkorDB Lite ownership未证; next=M2决定worker资格后实测 |
| B11-REGRESSION-GATE | 定向强反例、全量 pytest、compileall、diff check 与第三方 patch identity 均通过 | PENDING | evidence=[M1 §2](./graphiti-v0.29.3-source-product-m1-ruling.md#2-source-lock); ruling=只有source lock; next=adapter完成后跑全量门 |
| B11-FREEZE-SYNC | frozen note、integration page、总表、workstream README、roadmap 和 ledger 状态已同步 | PENDING | evidence=[Graphiti stable page](../../../../../../reference/integration/graphiti.md); ruling=M1页已建但不可提前冻结; next=B0-B11全部PASS/N/A后同步 |
<!-- ledger-checkpoints:end -->

## 架构师签字

- 当前 ledger 状态：`in_progress`
- 最后一次一手证据复核 commit：`v0.29.3@021d3a57`
- 架构师判词：`GRAPHITI_M1_ACCEPTED_READY_FOR_M2_PRODUCT_RUNTIME_AUDIT`
