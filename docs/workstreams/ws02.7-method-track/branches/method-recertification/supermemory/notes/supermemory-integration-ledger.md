# Supermemory Method Integration Ledger v1

> 本账在 adapter 代码之前创建。当前停在 source availability 门；公开文档、SDK 与 binary
> API 不能冒充缺失的 server/engine source。完整判据见
> [Method 接入标准清单](../../../../../../reference/method-integration-checklist.md)。

<!-- method-integration-ledger
contract_version: method-integration-ledger-v1
method_id: supermemory
display_name: Supermemory
ledger_state: blocked
integration_page: docs/reference/integration/supermemory.md
dossier: none
frozen_note: none
-->

## 必填检查点

<!-- ledger-checkpoints:start -->
| ID | 完成判据 | Status | 证据、裁决与下一动作 |
| --- | --- | --- | --- |
| B0-OFFICIAL-BENCHMARKS | 当前官方 repo 实际跑过的 benchmark、入口和版本已穷举，未跑过者标 framework extension | PASS | evidence=[M1 §3](./supermemory-current-source-product-m1-ruling.md); ruling=官方 MemoryBench 覆盖 LoCoMo/LME/ConvoMem，HaluMem 有 benchmark 官方 wrapper，BEAM/MemBench 无 harness; next=none |
| B0-FINAL-PAYLOAD | 每个官方 harness 展开后的 add 次数、batch、role、namespace、时间、模型参数和 search 最终 payload 已锁 | PASS | evidence=[M1 §3](./supermemory-current-source-product-m1-ruling.md); ruling=MemoryBench session-document/hybrid-30 与 HaluMem batch20/rerank/rewrite/top10或20 payload 已锁，均为 hosted 默认 endpoint; next=none |
| B0-DIFFERENCE-RULING | 主轨、author 轨、framework extension、upstream bug 的每项差异已唯一归类 | PASS | evidence=[M1 §3.3](./supermemory-current-source-product-m1-ruling.md); ruling=LoCoMo/LME 为 cloud author candidate，HaluMem 为 external official cloud candidate，BEAM/MemBench 为 framework extension；local 主轨被 source 门阻断; next=none |
| B1-SOURCE-LOCK | 官方 repo、tag、commit、license、vendored 路径、patch 和更新策略已锁定 | BLOCKED | evidence=[M1 §2](./supermemory-current-source-product-m1-ruling.md); ruling=公开 MIT tree 与 stable binary checksum 已锁，但 runtime server/engine source、build workflow、明确 source license 均不可得，不满足 local OSS; next=等待 upstream 开源或用户明确放宽/替换范围 |
| B1-PRODUCT-SURFACE | ingest/retrieve 采用通用产品接口，并解释为何不用 chat、ask、eval、cloud 或 HTTP 专用入口 | BLOCKED | evidence=[M1 §4-6](./supermemory-current-source-product-m1-ruling.md); ruling=文档暴露 local HTTP product API，但其实现只有 binary；cloud 不得替代 local OSS; next=先完成用户范围裁决 |
| B1-LIFECYCLE-CALLGRAPH | prepare、ingest、retrieve、finalize、cleanup 的 runner 真实调用点和早失败路径已逐一闭合 | PENDING | evidence=[M1 §6](./supermemory-current-source-product-m1-ruling.md); ruling=adapter 尚未授权; next=source 门解锁后实现独占进程、双终态与 cleanup 调用图 |
| B2-GRANULARITY | 原生输入单元、consume_granularity、placeholder、session 边界和尾部残项处理已裁定 | PENDING | evidence=[M1 §3-4](./supermemory-current-source-product-m1-ruling.md); ruling=官方候选是 session raw document，但 local 主轨未获准; next=解锁后按五格 payload 强反例裁定 |
| B3-ISOLATION-CLEAN | 物理或逻辑隔离的写入、过滤、单空间删除和 clean-retry 等价性已证明 | PENDING | evidence=[M1 §4-6](./supermemory-current-source-product-m1-ruling.md); ruling=文档只声明 containerTag 与 bulk delete，MemoryBench clear 仍 no-op; next=解锁后实证四项等价或采用独占 data-dir |
| B3-PARALLEL-OWNERSHIP | process-global 缓存、client、DB、线程和 worker 所有权已审，W1/W2 资格有反例或实证 | PENDING | evidence=[M1 §6](./supermemory-current-source-product-m1-ruling.md); ruling=binary 内部 queue/graph/model ownership 不可审; next=解锁后做 W1/W2 进程与端口/data-dir 强反例 |
| B4-INPUT-VISIBILITY | role、speaker、content、turn/session time、place、image caption、source id 均沿算法可见链核实 | PENDING | evidence=[M1 §3-4](./supermemory-current-source-product-m1-ruling.md); ruling=官方 wrapper 只证明最终文本 payload，不能证明 binary extraction 可见链; next=解锁后以 black-box output 加限制声明逐格验证 |
| B4-READOUT-COMPLETENESS | 产品答题前实际检索的全部记忆层、顺序和时间字段均进入 formatted_memory | PENDING | evidence=[M1 §4-5](./supermemory-current-source-product-m1-ruling.md); ruling=hybrid 文档声称 memory+chunk，内部层与顺序不可审; next=解锁后锁原始 response 与 formatter |
| B5-PROVENANCE | 当前检索条目的 semantic source lineage 资格按运行时事实判 valid、N/A 或 pending | PENDING | evidence=[M1 §5](./supermemory-current-source-product-m1-ruling.md); ruling=response id/metadata 不足以证明 evolved memory semantic lineage; next=source 解锁或 binary probe 后判 N/A/valid |
| B5-RANKING-TOPK | 检索 item 粒度、top-k 总量或分路、dedup、rerank、稳定顺序和 NDCG 资格已锁 | PENDING | evidence=[M1 §4-5](./supermemory-current-source-product-m1-ruling.md); ruling=hybrid 两路合并与稳定排序实现不可审; next=source 门解锁后实证并诚实降级 |
| B5-LOSSLESS-RETROFIT | provenance 与 HaluMem 缺口已评估直接支持、可无损观测改造或不可改造 | PENDING | evidence=[M1 §3.2、§6](./supermemory-current-source-product-m1-ruling.md); ruling=HaluMem hosted wrapper 可按 response id 读 extraction，但 local binary 等价未证; next=解锁后测本 session delta 与 current update state |
| B6-FLUSH-COMPLETION | flush、update、summary、后台任务和“何时完成”的边界已接线并能传播失败 | PENDING | evidence=[M1 §3-4](./supermemory-current-source-product-m1-ruling.md); ruling=候选为 document+memory 双 done，官方 MemoryBench 却只 warn failed; next=解锁后实现 timeout 与 failed fail-fast |
| B7-OBSERVABILITY | build、retrieve、answer、judge 的 LLM、embedding、token、latency 和 scope 可观测 | PENDING | evidence=[M1 §5-6](./supermemory-current-source-product-m1-ruling.md); ruling=binary 未公开内部 usage hook; next=解锁后评估模型 proxy observation 与本地 embedding 诚实缺口 |
| B8-RETRIEVAL-SIDE-EFFECTS | 检索读副作用与污染写入已区分，算法固有状态变化不被误删 | PENDING | evidence=[M1 §5](./supermemory-current-source-product-m1-ruling.md); ruling=binary search side effect 不可由 docs 证明; next=解锁后做前后 state 黑箱差分并限制声明 |
| B8-RESILIENCE-RESUME | 全部外部调用有 timeout、retry、失败语义、半写清理、安全 resume 与 secret 边界 | PENDING | evidence=[M1 §3-6](./supermemory-current-source-product-m1-ruling.md); ruling=官方 harness polling 无总 deadline且 clear no-op，binary 内部半写未知; next=解锁后补 adapter 边界超时、journal、clean 与 secret 扫描 |
| B9-MODEL-IDENTITY | build LLM、embedding、revision、dimension、normalization、distance 与本地模型身份已声明 | PENDING | evidence=[M1 §4](./supermemory-current-source-product-m1-ruling.md); ruling=文档声明 BYO LLM 与 bge-base-en-v1.5/768d，但 binary revision/normalization/distance 不可审; next=解锁后锁 runtime 输出与诚实 pending 字段 |
| B10-TOML-MANIFEST | smoke 和 official_full 主配置、稀疏 author section、解析配置与 resume identity 已锁 | PENDING | evidence=[M1 §6](./supermemory-current-source-product-m1-ruling.md); ruling=未授权 binary/cloud profile; next=用户裁决 surface 后设计 TOML 与 manifest |
| B10-ANSWER-JUDGE-BUILDER | benchmark 主 builder 与作者完整 builder 的变量、messages、decoding、judge 和私有边界已核 | PENDING | evidence=[M1 §3](./supermemory-current-source-product-m1-ruling.md); ruling=MemoryBench 有 provider answer builder 但属于 cloud author candidate；主轨仍应 benchmark builder; next=source 门解锁后完成私有边界测试 |
| GRID-LOCOMO | 稳定异常、双 speaker、image、时间、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=[LoCoMo 稳定页](../../../../../../reference/integration/locomo.md) / payload=[M1 §3.1](./supermemory-current-source-product-m1-ruling.md) / metric=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / privacy=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / smoke=none; ruling=官方 cloud session-document 仅作候选，local OSS 未解锁; next=解锁后闭合 payload/metric/privacy/smoke |
| GRID-LONGMEMEVAL | 稳定异常、role 异形、时间、完整 haystack、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=[LongMemEval 稳定页](../../../../../../reference/integration/longmemeval.md) / payload=[M1 §3.1](./supermemory-current-source-product-m1-ruling.md) / metric=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / privacy=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / smoke=none; ruling=官方 cloud 每 session document 仅作候选，local OSS 未解锁; next=解锁后闭合完整 haystack 与五门 |
| GRID-MEMBENCH | first/third、尾部 time/place、missing-time noise、gold 异常、最终 payload、指标与 smoke 独立闭合 | PENDING | evidence=stable=[MemBench 稳定页](../../../../../../reference/integration/membench.md) / payload=[M1 §3.3](./supermemory-current-source-product-m1-ruling.md) / metric=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / privacy=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / smoke=none; ruling=无官方 harness且 local OSS 未解锁; next=解锁后按 framework extension 闭合 |
| GRID-BEAM | variant、时间、10M orphan/mismatch、最终 payload、abstention、指标与 smoke 独立闭合 | PENDING | evidence=stable=[BEAM 稳定页](../../../../../../reference/integration/beam.md) / payload=[M1 §3.3](./supermemory-current-source-product-m1-ruling.md) / metric=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / privacy=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / smoke=none; ruling=无官方 harness且 local OSS 未解锁; next=解锁后按 framework extension 闭合 |
| GRID-HALUMEM | 固定 shape、session-local delta、四类 operation、最终 payload、指标、隐私与 UUID worker-lane 独立闭合 | PENDING | evidence=stable=[HaluMem 稳定页](../../../../../../reference/integration/halumem.md) / payload=[M1 §3.2](./supermemory-current-source-product-m1-ruling.md) / metric=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / privacy=[M1 §5](./supermemory-current-source-product-m1-ruling.md) / smoke=none / operations=extraction pending, update pending, qa pending, memory_type pending; ruling=hosted wrapper 给出候选但 local binary 等价与 source 均未证; next=解锁后逐 operation 裁定 |
| B11-DOSSIER | 一份 living dossier 已按五 benchmark 分章并链接承重 note、异常处置和失效触发器 | PENDING | evidence=[M1](./supermemory-current-source-product-m1-ruling.md); ruling=source 门前不制造伪 dossier; next=adapter 获准后创建 |
| B11-SMOKE-PLAN | 每个 concrete variant 的 smoke-plan-v1 已无 API 生成、审阅并保存，命令未手写 | PENDING | evidence=[M1 §6](./supermemory-current-source-product-m1-ruling.md); ruling=registry 尚无 Supermemory; next=adapter 与 registry 完成后生成 |
| B11-REAL-SMOKE | planner 生成的全部 predict 与适用 evaluator 已真实执行，固定 shape 未误传裁剪参数 | PENDING | evidence=[M1 §6](./supermemory-current-source-product-m1-ruling.md); ruling=零 API 且 source blocked; next=范围与预算均批准后执行 |
| B11-ARTIFACT-GATE | manifest、prediction、formatted_memory、private labels、efficiency、state 与 summary 已逐 run 开箱 | PENDING | evidence=[M1 §6](./supermemory-current-source-product-m1-ruling.md); ruling=依赖真实 smoke; next=真实 smoke 后开箱 |
| B11-PARALLEL-GATE | 每个适用 variant 的 W2 最小竞态哨兵已实测；若产品确有硬 cap，源码/真实反例与 CLI 预启动拒绝已证明；不得把 W2 或 execution 默认值冒充能力上限 | PENDING | evidence=[M1 §5-6](./supermemory-current-source-product-m1-ruling.md); ruling=binary process/queue/model ownership未知; next=解锁后先离线/本地 W1W2 实证 |
| B11-REGRESSION-GATE | 定向强反例、全量 pytest、compileall、diff check 与第三方 patch identity 均通过 | PENDING | evidence=[M1](./supermemory-current-source-product-m1-ruling.md); ruling=本批仅来源裁决; next=adapter 实现后运行完整门 |
| B11-FREEZE-SYNC | frozen note、integration page、总表、workstream README、roadmap 和 ledger 状态已同步 | PENDING | evidence=[Supermemory integration page](../../../../../../reference/integration/supermemory.md); ruling=当前只能同步 blocked 状态，不能冻结; next=全部门关闭后执行 |
<!-- ledger-checkpoints:end -->

## 架构师最终签字

- 当前 ledger 状态：`blocked`
- 最后一次一手证据复核 commit：public tree
  `566be208981aa23ef20a85fd50a737861b1b10b2`；runtime source：不可得
- 架构师判词：`BLOCKED_SUPERMEMORY_SOURCE_UNAVAILABLE_LOCAL_BINARY`。
