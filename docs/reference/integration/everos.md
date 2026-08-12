# EverOS 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 当前状态：**M2 离线 adapter 门已关闭，B11 真实 smoke 已批准并进入 live 队列**；尚未冻结。

- 主 source：官方稳定版 `EverOS v1.2.3@48fc9084888bc17100053227284f939a5aca5e91`，
  Apache-2.0；本地路径 `third_party/methods/EverOS/` 为 local-only，可由
  `scripts/fetch_third_party_methods.sh` 恢复。
- 算法依赖：该 release 的 `uv.lock` 固定 `everalgo-*` 包；对应版本均能在官方
  `EverMind-AI/EverAlgo` Apache-2.0 monorepo找到精确 tag/source，source gate 已通过。
- 产品调用面：在隔离 worker 内进入官方 `create_app()` lifespan，直接调用与
  `/api/v2/memory/add|flush|search|get` 相同的 typed DTO/service。它仅省去 HTTP transport，
  不绕过 boundary、Episode、Cascade、OME、SQLite、LanceDB 或产品搜索算法。
- adapter：`everos-product-chat-v1`；provider v3、`consume_granularity=session`。每个
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
- **B4 time/image**：source time 只按 turn→当前 session→None；缺失时使用不可见的稳定
  operational ms 满足产品正整数契约，绝不借 question/兄弟 turn/墙钟。LoCoMo image 走共享
  `[Sharing image that shows: ...]` helper，locator 不可见。
- **B3/B6/B8 resilience**：每 conversation 物理 root；OME terminal + Cascade health/failure +
  双稳定零 exact drain。completed-operation sidecar 与 root cleanup marker/tombstone 支持安全
  resume/clean retry，清理和 shutdown 失败可见。
- **B4/B5 readout**：public HYBRID search 保留 Episode/atomic facts、score 与稳定 rank；主轨
  多 owner 以 score→owner→product rank 合并。zero hit 与 backend failure 分开。
- **B7 observability**：product response exact LLM/embedding usage 由透传 wrapper 收集，只有
  operation 成功才回放。reranker capability 同样在 lazy SearchManager 前被纯透传包装；current
  chat/Episode HYBRID 预期零调用，任一非空 rerank 观测均 fail-fast；answer/judge 沿框架公共观测。

## Metric 资格

| 能力 | 状态 |
| --- | --- |
| stable product ranking | valid |
| semantic provenance | N/A：current Episode 是合成记忆，无 lossless source mapping |
| Recall/Precision/F1@k、NDCG | N/A |
| HaluMem extraction | valid candidate：session-filtered public get |
| HaluMem update | valid candidate：probe query 读取累计 current state |
| HaluMem QA | valid candidate |
| HaluMem memory type | N/A：产品 Conversation kind 不等于官方三类 taxonomy |

candidate 仍需真实 B11 artifact gate 才能转为最终通过；不会为了填满矩阵改造算法。

## 证据入口

- [EverOS 接入 ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-integration-ledger.md)
- [v1.2.3 source drift M1-R1](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-v1.2.3-source-drift-m1-r1.md)
- [current source / product / official harness M1 裁决](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-current-source-product-m1-ruling.md)
- [M2 adapter 实现记录](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-m2-adapter-implementation.md)
- [五 benchmark 安全档案](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-five-benchmark-safety-dossier.md)
- [M2 检查点](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-m2-adapter-checkpoint.md)
- [机器 smoke plans](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-smoke-plans-v1.json)
- [EverOS 接入支线](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/README.md)

当前判词：`READY_FOR_B11_REAL_SMOKE / LIVE_QUEUED`。用户已批准 OpenCodeGo smoke；实际启动前
仍须由 machine plan/preflight 复核 current runtime 所需环境，不因旧 note 曾记录缺少
`EVEROS_DEEPINFRA_API_KEY` 就假定今天仍缺，也不在未实跑前升级 B11。
