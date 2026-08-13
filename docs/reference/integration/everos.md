# EverOS 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 当前状态：**`method-frozen-v1`**；18 份 current v6 真实 smoke、W1/W2、artifact、效率、
> 隐私与产品状态门均已关闭。冻结证书见
> [`everos-frozen-v1.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-frozen-v1.md)。

- 主 source：官方稳定版 `EverOS v1.2.3@48fc9084888bc17100053227284f939a5aca5e91`，
  Apache-2.0；本地路径 `third_party/methods/EverOS/` 为 local-only，可由
  `scripts/fetch_third_party_methods.sh` 恢复。
- 算法依赖：该 release 的 `uv.lock` 固定 `everalgo-*` 包；对应版本均能在官方
  `EverMind-AI/EverAlgo` Apache-2.0 monorepo找到精确 tag/source，source gate 已通过。
- 产品调用面：在隔离 worker 内进入官方 `create_app()` lifespan，直接调用与
  `/api/v2/memory/add|flush|search|get` 相同的 typed DTO/service。它仅省去 HTTP transport，
  不绕过 boundary、Episode、Cascade、OME、SQLite、LanceDB 或产品搜索算法。
- adapter：`everos-product-chat-v6`；provider v3、worker protocol v2、sidecar v2、
  `consume_granularity=session`。每个
  provider 独占 Python 3.12 worker，每个 conversation 使用独立 product root；worker 进入
  official lifespan 后直接调用 typed `memorize/search/get`。
- 官方 benchmark：current EverOS 与 EverAlgo 的公开 harness 只覆盖 LoCoMo；论文另报告
  LongMemEval，但没有公开 loader/final payload。HaluMem、BEAM、MemBench 均为 framework
  extension。

## 已关闭

- **B0 official identity**：current product LoCoMo harness 与 research `v93.05` harness
  分开记录，不拼成一条不存在的复现链；LongMemEval 诚实标
  `paper-reported / public-harness-unavailable`。
- **B1 source lock**：EverOS、EverAlgo runtime packages、license、local-only 恢复方式与
  用户本地 PDF 的负空间均已锁定。
- **B1 product surface**：主轨采用 typed product service；直接 EverAlgo stages、直接写库、
  单纯 sleep 或额外启动 HTTP host 均不进入主轨。
- **B8 retrieval side effect**：current SearchManager/service 是只读检索；telemetry 不计作
  memory mutation。

- **B1 lifecycle**：独立 worker 进入 official `create_app()` lifespan；项目 patch 只让所有
  provider shutdown settle 后聚合上抛失败，不改变成功路径。
- **B2/B4 input**：session 粒度、每 canonical event 一条产品 message。LoCoMo 沿 official
  all-user + real speaker sender；其他四格保留 canonical role/order。纯 assistant session 只加
  空且无 source identity 的结构 user anchor，不伪造回复。
- **B4 time/image**：source time 只按 turn→当前 session 读取；LoCoMo 唯一允许沿官方 harness
  在 session source time 上按 utterance `+30s` 生成排序时间。其余缺失 source time 一律在
  runtime/API/output 前 fail-fast，不借 question/兄弟 turn/墙钟，不制造会被 Episode prompt
  写进记忆的伪日期。因此 MemBench `0-10k` 可用，`100k` 明确 unsupported/N/A。LoCoMo image
  走共享 `[Sharing image that shows: ...]` helper，locator 不可见。历史 v2/v3 的 operational
  sentinel 只保留诊断价值，未进入冻结矩阵。
- **B3/B6/B8 resilience**：每 conversation 物理 root；OME terminal + Cascade health/failure +
  有 deadline 的 event-loop yield + 双稳定零 exact drain。completed-operation sidecar 与 root
  cleanup marker/tombstone 支持安全
  resume/clean retry，清理和 shutdown 失败可见。
- **B4/B5 readout**：public HYBRID search 保留 Episode/atomic facts、score 与稳定 rank；主轨
  多 owner 以 score→owner→product rank 合并。zero hit 与 backend failure 分开。
- **B7 observability**：product response exact LLM/embedding usage 由透传 wrapper 收集，只有
  operation 成功才回放。reranker capability 同样在 lazy SearchManager 前被纯透传包装；current
  chat/Episode HYBRID 预期零调用，任一非空 rerank 观测均 fail-fast；answer/judge 沿框架公共观测。
- **B7 smoke transport**：OpenCodeGo 只承担 build/answer/judge Chat Completions；smoke 的
  `Qwen/Qwen3-Embedding-4B`/1024 由 OpenRouter OpenAI-compatible embeddings 承载，模型、维度、
  LanceDB L2 与产品 pipeline 不变。provider 与 credential 变量名进入 manifest；key/base URL 不落
  artifact。official-full 仍使用产品默认 DeepInfra transport。HYBRID Episode 主轨允许未配置
  reranker 启动，但若未来路径实际触发 rerank，会因 capability 缺失或非空观测立即失败。
- **B9 artifact 边界**：v6 不再把 upstream `default.toml` 复制成 run-local `everos.toml`；产品
  继续从 vendored package 读取默认值并接受受限环境覆盖，root 只保留运行时实际 watch 的
  `ome.toml`。18 个 run 对 `.env` key/base URL 与 upstream endpoint 的精确值扫描均为零命中。

## Metric 资格

| 能力 | 状态 |
| --- | --- |
| stable product ranking | valid |
| semantic provenance | N/A：current Episode 是合成记忆，无 lossless source mapping |
| Recall/Precision/F1@k、NDCG | N/A |
| HaluMem extraction | valid：session-filtered public get；Medium/Long 真实评分均已落盘 |
| HaluMem update | valid：probe query 读取累计 current state；Medium/Long 各 7 点 |
| HaluMem QA | valid：Medium/Long 各 1 题 |
| HaluMem memory type | valid：这是 extraction/update 已评分记录按 gold `memory_type` 的官方共享分母汇总，不要求产品输出 taxonomy |

2026-08-13/14 Medium、Long 真实 B11 已确认 extraction/update/QA 与 memory-type 三类分组均可落盘。
此前把产品 `Conversation` kind 与 evaluator 的 gold-side 分组标签混为一谈、误判 memory-type
为 N/A；该口径现已撤回。不会为了填满矩阵改造算法。

## 证据入口

- [EverOS 接入 ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-integration-ledger.md)
- [v1.2.3 source drift M1-R1](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-v1.2.3-source-drift-m1-r1.md)
- [current source / product / official harness M1 裁决](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-current-source-product-m1-ruling.md)
- [M2 adapter 实现记录](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-m2-adapter-implementation.md)
- [五 benchmark 安全档案](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-five-benchmark-safety-dossier.md)
- [M2 检查点](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-m2-adapter-checkpoint.md)
- [机器 smoke plans](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-smoke-plans-v1.json)
- [method-frozen-v1 证书](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-frozen-v1.md)
- [EverOS 接入支线](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/README.md)

当前判词：`EVEROS_METHOD_FROZEN_V1`。smoke 证明产品链、产物与资格边界可达，不把极小样本
分数解释成效果排名；official-full、作者 LoCoMo calibration、真实 resume 与 full 成本 pilot
仍是冻结后声明缺口。
