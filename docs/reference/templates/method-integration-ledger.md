# Method Integration Ledger v1 模板

> 这是每家**新 method** 的必填执行账，不是 B0–B11 政策原文的副本。先复制到
> `docs/workstreams/ws02.7-method-track/branches/method-recertification/<method>/notes/`
> 并命名为 `<method>-integration-ledger.md`，再开始 M-1 取证。政策含义仍以
> [Method 接入标准清单](../method-integration-checklist.md)为准。

<!-- method-integration-ledger
contract_version: method-integration-ledger-v1
method_id: <method-id>
display_name: <display-name>
ledger_state: in_progress
integration_page: docs/reference/integration/<method-id>.md
dossier: none
frozen_note: none
-->

## 使用规则

1. 每格只能写 `PASS`、`N/A`、`PENDING`、`BLOCKED`。`N/A` 是有一手依据的能力裁决，
   不是“没做”；`PENDING` 必须有具体下一动作；有停工点必须把整份 ledger 状态改成
   `blocked`，禁止藏在 `in_progress` 里。
2. 最后一列固定采用
   `evidence=...; ruling=...; next=...`。`PASS/N/A` 的 evidence 必须至少含一个可点击
   Markdown 证据链接，且 `next=none`；`PENDING/BLOCKED` 必须给出可执行的 next。
3. `GRID-*` 五格的 evidence 还必须显式包含
   `stable=`、`payload=`、`metric=`、`privacy=`、`smoke=`；HaluMem 另含
   `operations=extraction/update/qa/memory_type`。这是防止只证明“能跑”却漏掉输入、指标或
   私有边界。
4. 状态转换：`in_progress` → `ready_for_smoke` → `frozen`。进入
   `ready_for_smoke` 前，除真实 smoke、artifact、并行、回归、冻结同步五格外不得残留
   `PENDING`；`frozen` 不得残留 `PENDING/BLOCKED`，且 dossier/frozen note 必须存在并回链。
5. 校验命令：
   `uv run python scripts/validate_method_integration_ledgers.py --root .`。机器只检查完整性与
   状态自洽；架构师仍须亲读一手证据，不能把“校验通过”冒充方法学验收。

## 必填检查点

<!-- ledger-checkpoints:start -->
| ID | 完成判据 | Status | 证据、裁决与下一动作 |
| --- | --- | --- | --- |
| B0-OFFICIAL-BENCHMARKS | 当前官方 repo 实际跑过的 benchmark、入口和版本已穷举，未跑过者标 framework extension | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B0-FINAL-PAYLOAD | 每个官方 harness 展开后的 add 次数、batch、role、namespace、时间、模型参数和 search 最终 payload 已锁 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B0-DIFFERENCE-RULING | 主轨、author 轨、framework extension、upstream bug 的每项差异已唯一归类 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B1-SOURCE-LOCK | 官方 repo、tag、commit、license、vendored 路径、patch 和更新策略已锁定 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B1-PRODUCT-SURFACE | ingest/retrieve 采用通用产品接口，并解释为何不用 chat、ask、eval、cloud 或 HTTP 专用入口 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B1-LIFECYCLE-CALLGRAPH | prepare、ingest、retrieve、finalize、cleanup 的 runner 真实调用点和早失败路径已逐一闭合 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B2-GRANULARITY | 原生输入单元、consume_granularity、placeholder、session 边界和尾部残项处理已裁定 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B3-ISOLATION-CLEAN | 物理或逻辑隔离的写入、过滤、单空间删除和 clean-retry 等价性已证明 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B3-PARALLEL-OWNERSHIP | process-global 缓存、client、DB、线程和 worker 所有权已审，W1/W2 资格有反例或实证 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B4-INPUT-VISIBILITY | role、speaker、content、turn/session time、place、image caption、source id 均沿算法可见链核实 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B4-READOUT-COMPLETENESS | 产品答题前实际检索的全部记忆层、顺序和时间字段均进入 formatted_memory | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B5-PROVENANCE | 当前检索条目的 semantic source lineage 资格按运行时事实判 valid、N/A 或 pending | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B5-RANKING-TOPK | 检索 item 粒度、top-k 总量或分路、dedup、rerank、稳定顺序和 NDCG 资格已锁 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B5-LOSSLESS-RETROFIT | provenance 与 HaluMem 缺口已评估直接支持、可无损观测改造或不可改造 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B6-FLUSH-COMPLETION | flush、update、summary、后台任务和“何时完成”的边界已接线并能传播失败 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B7-OBSERVABILITY | build、retrieve、answer、judge 的 LLM、embedding、token、latency 和 scope 可观测 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B8-RETRIEVAL-SIDE-EFFECTS | 检索读副作用与污染写入已区分，算法固有状态变化不被误删 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B8-RESILIENCE-RESUME | 全部外部调用有 timeout、retry、失败语义、半写清理、安全 resume 与 secret 边界 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B9-MODEL-IDENTITY | build LLM、embedding、revision、dimension、normalization、distance 与本地模型身份已声明 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B10-TOML-MANIFEST | smoke 和 official_full 主配置、稀疏 author section、解析配置与 resume identity 已锁 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B10-ANSWER-JUDGE-BUILDER | benchmark 主 builder 与作者完整 builder 的变量、messages、decoding、judge 和私有边界已核 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| GRID-LOCOMO | 稳定异常、双 speaker、image、时间、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=<填写> / payload=<填写> / metric=<填写> / privacy=<填写> / smoke=<填写>; ruling=<填写>; next=<填写> |
| GRID-LONGMEMEVAL | 稳定异常、role 异形、时间、完整 haystack、最终 payload、检索指标、隐私与 smoke 独立闭合 | PENDING | evidence=stable=<填写> / payload=<填写> / metric=<填写> / privacy=<填写> / smoke=<填写>; ruling=<填写>; next=<填写> |
| GRID-MEMBENCH | first/third、尾部 time/place、missing-time noise、gold 异常、最终 payload、指标与 smoke 独立闭合 | PENDING | evidence=stable=<填写> / payload=<填写> / metric=<填写> / privacy=<填写> / smoke=<填写>; ruling=<填写>; next=<填写> |
| GRID-BEAM | variant、时间、10M orphan/mismatch、最终 payload、abstention、指标与 smoke 独立闭合 | PENDING | evidence=stable=<填写> / payload=<填写> / metric=<填写> / privacy=<填写> / smoke=<填写>; ruling=<填写>; next=<填写> |
| GRID-HALUMEM | 固定 shape、session-local delta、四类 operation、最终 payload、指标、隐私与 W1 独立闭合 | PENDING | evidence=stable=<填写> / payload=<填写> / metric=<填写> / privacy=<填写> / smoke=<填写> / operations=extraction/update/qa/memory_type; ruling=<填写>; next=<填写> |
| B11-DOSSIER | 一份 living dossier 已按五 benchmark 分章并链接承重 note、异常处置和失效触发器 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B11-SMOKE-PLAN | 每个 concrete variant 的 smoke-plan-v1 已无 API 生成、审阅并保存，命令未手写 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B11-REAL-SMOKE | planner 生成的全部 predict 与适用 evaluator 已真实执行，固定 shape 未误传裁剪参数 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B11-ARTIFACT-GATE | manifest、prediction、formatted_memory、private labels、efficiency、state 与 summary 已逐 run 开箱 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B11-PARALLEL-GATE | 每个适用 variant 的 W1/W2 已实测，或 W1-only 的产品硬约束和 CLI 预启动拒绝已证明 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B11-REGRESSION-GATE | 定向强反例、全量 pytest、compileall、diff check 与第三方 patch identity 均通过 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
| B11-FREEZE-SYNC | frozen note、integration page、总表、workstream README、roadmap 和 ledger 状态已同步 | PENDING | evidence=<填写>; ruling=<填写>; next=<填写> |
<!-- ledger-checkpoints:end -->

## 架构师最终签字

- 当前 ledger 状态：`in_progress`
- 最后一次一手证据复核 commit：`<填写>`
- 架构师判词：`<填写>`
