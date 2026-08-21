# Letta/MemGPT 接入参考（legacy V1 sleeptime-memory product）

> 稳定页：只记录经架构师复核的承重结论。完整证据、争议、零 API stdout 与五格反例见
> `docs/workstreams/ws02.7-method-track/branches/method-recertification/letta/`。
>
> 状态：`method-frozen-v1`。current v3 的 11 份真实 smoke、17 个 conversation/question、
> 全部适用 evaluator、artifact/效率/隐私/外部状态机器门与最终回归均已闭合。历史首跑的
> Docker、PostgreSQL readiness、Run lifecycle 与区域 opt-in 失败资产只作阶段证据，不混入
> current run，也不冒充可 resume smoke。

## 1. Source identity

| 项 | 值 |
| --- | --- |
| upstream | `https://github.com/letta-ai/letta.git` |
| legacy release | `0.16.8`，release commit `1131535716e8a31c9a437f8695e25ac98f203a24` |
| vendored pin | `b76da9092518cbaa2d09042e52fdcbde69243e18` |
| product contract | `https://github.com/letta-ai/ai-memory-sdk.git` `v0.2.0@4494e004...` |
| license | Apache-2.0 |
| 本地路径 | `third_party/methods/letta` |
| adapter | `src/memory_benchmark/methods/letta_adapter.py` |
| worker | `src/memory_benchmark/methods/letta_worker.py` |
| adapter version | `letta-sleeptime-product-v2` |

active Letta Code `v0.30.1` 是完整 agent harness，与本项目要复现的 legacy MemGPT/Letta V1
sleeptime-memory 产品链属于 `ALGORITHM_VARIANT`，不能静默替换。Phase 1 五 benchmark 在
current official repos 中都没有 harness，因此五格均为 product-faithful framework extension，
不建立伪 `author_<benchmark>` section。

## 2. 运行身份

```text
product entry      direct SyncServer + managers + AgentLoop（不启动 HTTP host）
agent              每个 conversation subject 一个 standalone sleeptime_agent
core blocks        human(limit=10000) + summary(limit=1000)
tools              memory_finish_edits / memory_insert / memory_replace / memory_rethink
embedding          None
raw vector copy    disabled（skip_vector_storage=True）
input granularity  session；session 内最多 10 message 一批；不跨 session
readout            query-independent 全部 attached core blocks
database           owned ankane/pgvector:v0.5.1 PostgreSQL volume/container
framework workers  1（TOML、registry 与 planner 三处锁死）
answer             framework benchmark unified builder
```

依赖树与主框架冲突，因此使用 vendored `uv.lock` 的独立 Python 3.12 worker。worker 只是本机
stdio 依赖隔离层，算法仍直接调用同一产品内核，不是 HTTP/cloud 远端服务，也不是自行重写。

### 2.1 Prepare 与初始化

有待处理工作时，generic/operation runner 对每个 provider runtime 调一次
`prepare(RunContext)`：

```text
校验独立 venv
→ 创建/验证带 owner/runtime label 的 volume + container
→ CREATE EXTENSION IF NOT EXISTS vector
→ alembic upgrade head
→ worker initialize
→ SyncServer(init_with_default_org_and_user=False)
→ default organization / actor / base tools
```

显式跳过 provider model sync，避免 prepare 阶段联网。subject 首次出现时创建
`AgentType.sleeptime_agent`、两块 core memory 与唯一 initializer passage；
`embedding_config=None` 且 initializer embedding 实测为 None。

### 2.2 Ingest

每个 session 的 canonical messages 先按原序构造 official SDK formatter：

```text
<messages>The following message interactions have occured:
user: ...
assistant: ...</messages>
```

注意 `occured` 是 upstream v0.2.0 的原始拼写，字节级保留。每个 formatter batch 作为一条
`MessageCreate(role="user", content=wrapper, otid=operation_id)` 送入真实 `AgentLoop.step()`。
只有 stop reason 为 `end_turn/tool_rule`，且 `step_count` 与逐调用 provider usage 一致时才算
成功；failed/cancelled/timeout/max-step 或 usage 缺失均不可伪装完成。

### 2.3 Retrieve

adapter **不把 query 送入 Letta**。它按 sidecar agent id 读取全部 attached blocks，按
`(label,id)` 稳定排序后构造：

```text
<memory_block label="human" description="...">...</memory_block>

<memory_block label="summary" description="...">...</memory_block>
```

`RetrievalResult.items=None`；没有 top-k、向量 search 或跨层 rerank。direct archival
insert/search 会绕过 core-memory learning，只能作为以后显式 diagnostic variant，禁止进入
主表。

## 3. 五格输入

共同规则：一个 canonical 非空 event 恰好一条 role/content message；不补 placeholder、不按
位置重新配对、不跨 session。时间只用 `turn → session → None`，不借 question time、相邻
消息或 wall clock。

- **LoCoMo**：从公开 metadata 固定 `speaker_a→user / speaker_b→assistant`，content 保留
  真实 speaker 前缀；共享 image helper 追加 `[Sharing image that shows: ...]`，不泄露 path/
  query。映射不依首发，未知 speaker fail-fast。
- **LongMemEval**：assistant-first、连续同 role、singleton 与奇数尾原序保留；不补空角色，
  不按 question date 改写 history。
- **MemBench**：FirstAgent pair 已在 canonical 层拆为两个 child turn；ThirdAgent user-only
  保持原样。尾部 place/time 原文保留，严格 marker 防止重复前缀；100k noise 的时间为 None。
- **BEAM**：使用 benchmark canonical turn identity；10m orphan/mismatch 原样保留，不按 raw
  id 或位置重配；跨 batch 时间不排序。
- **HaluMem**：session 顺序交错运行；private memory point 不进 build。extraction N/A，
  current-state update 与 QA valid，memory-type composite N/A。

完整异常矩阵、反例和 smoke 形状见
[五格安全档案](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-five-benchmark-safety-dossier.md)。

## 4. Metric 资格

| 指标/operation | 判词 | 依据 |
| --- | --- | --- |
| 五格 Recall/Precision/F1@k | N/A | 演化 block 不能无损映射到 source gold unit |
| LongMemEval NDCG / stable ranking | N/A | 全 block readout 不是 query rank |
| HaluMem extraction | N/A | 无 product-level session-local delta |
| HaluMem update | valid | 官方评当前 readout 是否正确替换旧事实，不要求 source lineage |
| HaluMem QA | valid | framework answer builder 消费当前 blocks |
| HaluMem memory type | N/A | composite 依赖 extraction，block label 也不等于三类 gold type |

逐题 evidence 固定为 semantic provenance N/A、granularity none、stable ranking N/A。该 evidence
只否定 qrel/rank 指标；不能连坐否定 HaluMem current-state update。

## 5. Namespace、resume 与清理

subject id 由 `storage_root_relative + isolation_key` 哈希生成；sidecar 严格保存 agent、两个
block、archive 与 operation journal 身份，不含 absolute path、API key 或 gold。

每个 build batch 采用两阶段 journal：调用前写 pending，terminal/usage/steps 验收后写
completed。completed replay 跳过产品写；pending 表示可能半写，禁止直接重放，必须先走
conversation namespace clean retry。clean 会验证真实 owner 集，再删除 agent、独占 archive、
orphan blocks并反查 subject 已消失；成功后才删 sidecar。

正常 cleanup 关闭 worker/DB并删除 owned container，保留 labeled PostgreSQL volume 供同 run
resume。named volume 是本机外部状态：跨机器只复制 outputs 不足以 resume；缺失时 identity
冲突会 fail-fast，不会静默新建另一份记忆。

## 6. API runtime 与观测

- smoke：`opencodego/muse-spark-1.2-contributor`，Chat Completions，显式
  `thinking={type: disabled}`；
- official_full：`primary/gpt-4o-mini`，provider default Chat Completions 行为；
- build LLM 每次真实 response usage 逐调用记录；缺 usage fail-fast；
- retrieval 记录 wall-clock latency，LLM/embedding 调用应为零；
- worker env 是 allowlist，build key 只在一次 agent step 的最窄作用域临时变成
  `OPENAI_API_KEY`；
- worker 在产品构造前给现有 logging handler 安装 key/base URL redaction filter，并把
  `httpx/httpcore` 降到 warning；parent stderr tail 再做一次同口径脱敏；
- generic 与 operation runner 使用同一 efficiency-observability manifest contract；BEAM/HaluMem
  的 builder 明确落 `answer_context`，内容与实际 `formatted_memory` 一致且不改变 prompt 字节。

两 profile 的 model/provider/transport 与 wrapper/source hash 均进入 manifest/resume identity；
分数不可直接混比。

## 7. 当前验收状态

零 API 产品链与 current 真实链都已通过。current
[`letta-smoke-plans-v3.json`](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-smoke-plans-v3.json)
覆盖 LoCoMo 1、LongMemEval 2、MemBench 2、BEAM 4、HaluMem 2 个 concrete variant；全部固定 W1，
共 17 个 conversation/question。机器验货实数为 build LLM 45、answer 17、judge 24；current
11 个 owned volume 与 superseded 19 个保留 volume 分账，owned container 残留为 0。公开和历史
Letta artifact/log 对 API key、base URL、私有 workspace URL 的命中均为 0。

五格 retrieval qrel/rank、HaluMem extraction/memory-type 继续诚实 N/A；HaluMem update/QA
valid。冻结只证明 current product pipeline 与评测可达，不代表 smoke 分数具有排名意义。

## 8. 证据入口

- [Method integration ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-integration-ledger.md)
- [Current product identity M1](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-current-product-identity-m1-ruling.md)
- [M2 implementation](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-m2-adapter-implementation.md)
- [Five-benchmark safety dossier](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-five-benchmark-safety-dossier.md)
- [11 current concrete variant machine plans](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-smoke-plans-v3.json)
- [B11 first live attempt and R1 fixes](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-b11-first-live-attempt-r1.md)
- [method-frozen-v1](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-frozen-v1.md)
