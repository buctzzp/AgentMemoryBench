# EverOS 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 当前状态：历史 **`method-frozen-v1`** 证据仍有效；18 份 v6 真实 smoke、W1/W2、artifact、
> 隐私与产品状态门均已关闭。2026-08-25 主 build identity 已升级到 controlled MiniLM v8，
> 并显式关闭不进入主表 readout 的 build-time user-profile extraction；v8 真实 smoke 尚待
> 以新 run-id 重建。这里的 frozen 只证明
> 产品调用、输入安全、生命周期和 artifact 合同；ws05.1 M9 新发现的 hybrid/agentic、后台 profile
> extraction 与 source-lock coverage 已由 M11 显式裁清；agentic 仍是另一个 estimand，不混入主轨。
> 冻结证书见
> [`everos-frozen-v1.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-frozen-v1.md)。

- 主 source：官方稳定版 `EverOS v1.2.3@48fc9084888bc17100053227284f939a5aca5e91`，
  Apache-2.0；本地路径 `third_party/methods/EverOS/` 为 local-only，可由
  `scripts/fetch_third_party_methods.sh` 恢复。
- 算法依赖：该 release 的 `uv.lock` 固定 `everalgo-*` 包；对应版本均能在官方
  `EverMind-AI/EverAlgo` Apache-2.0 monorepo找到精确 tag/source，source gate 已通过。
- 产品调用面：在隔离 worker 内进入官方 `create_app()` lifespan，直接调用与
  `/api/v2/memory/add|flush|search|get` 相同的 typed DTO/service。它仅省去 HTTP transport，
  不绕过 boundary、Episode、Cascade、OME、SQLite、LanceDB 或产品搜索算法。
- adapter：`everos-product-chat-v8`；provider v3、worker protocol v4、sidecar v2、
  `consume_granularity=session`。每个
  provider 独占 Python 3.12 worker，每个 conversation 使用独立 product root；worker 进入
  official lifespan 后直接调用 typed `memorize/search/get`。
- 官方 benchmark：current v1.2.3 product tree 的公开 harness 只覆盖 LoCoMo；官方历史 commit
  `5f70b071…`/`29d555c…` 曾公开 LoCoMo、LongMemEval 与 PersonaMem evaluation，包括 LME
  converter/final answer chain，但该历史不在 current main ancestry，也未证明是 exact paper commit。
  HaluMem、BEAM、MemBench 均为 framework extension。

## 算法机制卡与 profile 身份

EverMemOS paper（arXiv `2601.02163v2`）的核心链是：semantic boundary → narrative Episode →
Atomic Facts/Foresight → embedding/time MemScene clustering → dense+BM25/RRF scene recall → Episode
cross-encoder rerank → LLM sufficiency → 必要时三 query rewrite。LoCoMo/LongMemEval quantitative 主表
读取 Episodes，不读取 Profile；LoCoMo 使用 `.70/7 days`，LongMemEval 使用 `.50/30 days`，说明
作者在同一 pipeline 下按 dialogue structure 校准 memory-organization scale。

必须区分四种身份：

- **paper/author reported**：Qwen3-Embedding-4B + Qwen3-Reranker-4B + agentic retrieval，按 benchmark
  使用不同 clustering；exact paper source commit 尚不可得。
- **official historical evaluation**：29d EverCore agentic harness，有公开 LoCoMo/LME converter、
  method answer prompt 与 parser，但 effective clustering 是 `.65/7`，且若配置
  `max_content_length=8000` 会逐 message 字符截断；不是 exact paper implementation。
- **v1.2.3 product**：chat/agent、keyword/vector/hybrid/agentic、OME/Cascade、LanceDB 等通用产品
  能力；product default 优先可部署性，不等于 paper experiment preset。
- **framework current v8**：chat/session、batch25、controlled MiniLM384、hybrid、reranker
  disabled、profile extraction disabled、framework unified answer。它是低依赖且可比较的 product variant，不是
  paper-complete EverMemOS。

v8 在 upstream `default_ome.toml` 上生成 run-local override，明确锁定 Atomic Facts 开、Foresight
关、profile clustering 开、**user profile extraction 关**、Reflection 关。worker 不以 TOML 文本
代替生效证据，而是在 official lifespan 启动后等待并读取最终 `StrategyMeta.enabled`；任一值不符即
fail-fast。`SearchRequest(include_profile=False)` 仍锁 readout 边界，但不再被误当成 build 侧关闭证据。
该变化会改变构建状态和 LLM 成本，因此 adapter v7→v8，旧状态不得重标或 resume。

current LoCoMo official harness 还只查询 `eval_owner=speaker_a`；framework 为通用双 speaker readout
会查询全部 owner 后稳定合并。二者各有目标：前者复现作者 intended topology，后者避免遗漏任一
speaker partition。若建立 `author_locomo`，single-owner/multi-owner 必须进入显式 topology identity，
不能伪装成普通 top-k 覆盖。

## 产品接口契约（参数、返回与批次）

跨 method 粒度矩阵见
[`../method-interface-inventory.md`](../method-interface-inventory.md)。EverOS 五格统一接收
`SessionBatch`。adapter 先构造整个 session 的 typed message list，独立 worker 再按产品
`add_batch_size=25` 分批调用 memorize，所有分批仍属于同一个 session operation，末尾只 flush
一次并等待 exact drain。

### 写入与 session readout

```python
runtime.ingest_session(
    *,
    isolation_key: str,
    operation_id: str,
    session_id: str,
    messages: list[dict[str, Any]],
    owner_ids: list[str],
) -> dict[str, Any]
```

每条 message 的精确 shape 为：`sender_id: str`、`sender_name: str | None`、
`role: Literal["user", "assistant"]`、`timestamp: int`（Unix milliseconds）、
`content: str`。worker 每批构造
`MemorizeAddRequest(session_id: str, app_id: str, project_id: str,
messages: list[MessageItemDTO])` 并调用 `service.memorize(dict) -> MemorizeResult`；随后用空
messages+`is_final=True` flush。runtime 对 adapter 返回：

```text
{
  operation_id: str,
  exact_drain: True,
  exact_drain_details: dict[str, Any],
  session_items: list[dict[str, Any]],
  llm_observations: list[dict],
  embedding_observations: list[dict],
  rerank_observations: list[dict],
}
```

`session_items` 来自 public `GetRequest(..., memory_type="episode",
filters={"session_id": session_id}) -> GetResponse`，不是 raw message echo。adapter 将其作为
可选 `SessionMemoryReport`，同时把 operation identity/drain/count 放入 `IngestResult.metadata`。

### 检索

```python
runtime.retrieve(
    *, isolation_key: str, owner_ids: list[str], query: str, top_k: int
) -> dict[str, Any]
```

worker 对每个 owner 调
`SearchRequest(user_id: str, app_id: str, project_id: str, query: str,
method: str, top_k: int, include_profile=False, enable_llm_rerank=False,
filters=None) -> SearchResponse`。返回 episode list 先保持各 owner 产品 rank，再按
`score desc → owner order → product rank → id` 稳定合并和去重，最终 runtime dict 含
`items: list[dict]`、`latency_ms: float` 与三类 observation list；adapter 映射成
`tuple[RetrievedItem, ...]`、`formatted_memory` 与 `RetrievalEvidence`。

list 并未改变 framework session 粒度。唯一结构补位是 pure-assistant session 的首个空 user
anchor：它没有 source identity，只满足 EverOS Episode 边界；其他 singleton/odd/连续 role
均不重配。产品会把 timestamp 写进 Episode，因此缺 source time 的 MemBench 100k 在 runtime
前明确 unsupported，不用墙钟伪造。

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
- **B7 observability**：product response exact LLM usage 由透传 wrapper 收集；本地 MiniLM 记录
  真实 tokenizer 输入量与 wall-clock latency，失败尝试进入 append-only attempt ledger。reranker
  capability 固定为 `None`；若 ambient 配置意外启用，worker 在 lazy SearchManager 构造前
  fail-fast。answer/judge 沿框架公共观测。
- **B7 controlled embedding**：OpenCodeGo/primary 只承担 build/answer/judge LLM。v8 经 upstream
  `EmbeddingProvider`/`EmbeddingCapability` seam 注入本地 `all-MiniLM-L6-v2`/384；项目 patch 只让
  provider 与六张 LanceDB schema 共读公开 dimension，默认仍为 upstream 1024。模型 pipeline L2
  normalize + LanceDB cosine 进入 manifest，rerank 保持 disabled-zero-call。旧 v6 Qwen/1024 状态必须
  全量重建，不能 resume 或重标。
- **M11 source/strategy identity**：v8 现显式锁 atomic facts on、foresight/profile extraction/
  reflection off、profile clustering on，并在 config reloader 后读取最终 `StrategyMeta` 验真；296-file
  `everos-api-main-v2` 闭包覆盖 product、prompt/config assets、lock、adapter/worker/patch。新 run
  使用 identity v2/fresh-state；完整收据见
  [M11 implementation](../../workstreams/ws05.1-method-profile-provenance/notes/m11-effective-config-source-embedding-implementation.md)。
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
- [ws05 M1 controlled embedding 实现](../../workstreams/ws05-experiment-reporting/branches/runtime-config-and-observability/notes/2026-08-24-m1-implementation.md)
- [ws05.1 M9 paper/product/author profile provenance](../../workstreams/ws05.1-method-profile-provenance/notes/everos-profile-provenance.md)

当前判词：`EVEROS_V7_INTERFACE_AND_SAFETY_FROZEN / M9_EVIDENCE_COMPLETE /
CURRENT_LOCOMO_AUTHOR_BUILDER_READY / HISTORICAL_LME_CODE_READY / PAPER_AUTHOR_REPRO_NOT_READY`。v6 smoke
继续证明既有产品链、输入、产物与资格边界，不把极小样本分数解释成效果排名；v8 controlled build
已通过 patch 重放、本地模型、schema 维度、effective profile 与 source closure 零 API 门；agentic
仍是独立算法分叉，且不能借旧 v6 run 宣称新 embedding 实跑完成。
current product LoCoMo builder 已闭合但 raw dataset revision 未锁；29d LongMemEval 只能命名为官方
历史代码身份，不能冒充 exact paper reproduction。
