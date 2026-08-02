# Letta/MemGPT current product identity M1 裁决

日期：2026-08-02  
状态：`ACCEPTED_FOR_M2_ADAPTER_DESIGN`  
范围：只裁定 current official source、官方评测覆盖、产品接口与主轨身份；尚未宣称
lifecycle、并行、metric 或真实 smoke 已通过。

## 1. 结论先行

Phase 1 的 Letta/MemGPT 主轨锁为：

> **以 Apache-2.0 的 legacy Letta V1 server 0.16.8 产品内核为可复现 runtime，遵循官方
> `ai-memory-sdk` v0.2.0 的 sleeptime-memory 产品契约：一组 role/content messages 驱动
> memory-only sleeptime agent 学习，等待 run 终态后读取演化后的 core memory blocks。框架
> 在进程内调用同一算法内核，不启动 HTTP host；主轨不把 raw message 直接写 archival
> passages，也不让 Letta answer agent 替框架回答问题。**

这是一条 **framework extension + product-faithful memory surface**，不是 Phase 1 五家中任意
benchmark 的作者复现轨。五家都没有 current official harness，因此不存在可建立的
`author_<benchmark>` section。

以下两条不进入主轨：

1. **Letta Code / Agent SDK**：它是新的完整 agent harness，记忆由 MemFS、skills、prompt、
   compaction 和 agent 行为共同形成；不是 legacy MemGPT/Letta V1 的配置等价升级，分类为
   `ALGORITHM_VARIANT`。
2. **direct archival insert + search**：接口虽公开、可排名、可挂 lineage，但绕过 sleeptime
   agent 对 core blocks 的学习与演化，会把方法退化成 raw-message vector store，分类为
   `MECHANISM_BYPASS`。只可留作以后显式的 diagnostic/archival profile，不能进入主表。

## 2. Current official source lock

2026-08-02 现场用 GitHub remote、release/tag 和只读 checkout 交叉核实：

| 官方资产 | 现场身份 | License | 本项目裁决 |
| --- | --- | --- | --- |
| [`letta-ai/letta`](https://github.com/letta-ai/letta) | latest release `0.16.8`，tag commit `1131535716e8a31c9a437f8695e25ac98f203a24`；main `ff19ffeafeb54bd2a7dc5d4a552f10191732a235` | Apache-2.0 | legacy V1 server；本地 pin `b76da9092518cbaa2d09042e52fdcbde69243e18` 比 release 多 3 commit，但排除 README/agent policy/CI 后 `0.16.8..b76` 与 `0.16.8..current-main` 的 product diff 均为空，保留现有 pin，避免无意义 source churn |
| [`letta-ai/letta-code`](https://github.com/letta-ai/letta-code/tree/v0.30.1) | `v0.30.1@09aff1bb463c9cab16b978e75ef91fc294d47f1e` | Apache-2.0 | 活跃新产品，但为完整 agent harness；不替换本轨 |
| [`letta-ai/letta-agent-sdk`](https://github.com/letta-ai/letta-agent-sdk/tree/v0.6.0) | `v0.6.0@3303f7ecb2da3b11bacf702d110e0c92164e0977` | Apache-2.0 | 管理 Letta Code app server/agent/session；不是 detachable memory provider |
| [`letta-ai/ai-memory-sdk`](https://github.com/letta-ai/ai-memory-sdk/tree/v0.2.0) | `v0.2.0@4494e00410469082bf298b8b03b7c9f93e244f14` | Apache-2.0 | 官方明确的 pluggable memory 产品意图；锁其 call graph 与默认语义，不把 cloud client 当 runtime 依赖 |
| [`letta-ai/letta-evals`](https://github.com/letta-ai/letta-evals) | `e47f167cf5558393e2bfb29a9b48e576ba5e7adc` | Apache-2.0 | current eval 基础设施；Phase 1 五 benchmark 均无入口 |
| [`letta-ai/letta-research-onsite`](https://github.com/letta-ai/letta-research-onsite) | `c4f132e5dee8971e7d35ad8296662b1058b251bb` | Apache-2.0 | 官方 paper experiments 只有 nested K/V 与 NaturalQuestions document QA；不是 Phase 1 harness |

本项目 vendored source 仍是：

- 路径：`third_party/methods/letta`
- commit：`b76da9092518cbaa2d09042e52fdcbde69243e18`
- 恢复入口：`scripts/fetch_third_party_methods.sh`
- nested 状态：detached HEAD；用户放入的论文 PDF 是未跟踪只读资产，不进入 source identity。

更新触发器：每次开始 Letta 真效果 full run 或上游发布新 stable release 时，只比较 product
source diff。README、AGENTS、CI 或 AI policy 单独变化不触发重接入；agent loop、block tool、
storage schema、LLM/embedding client 或 completion semantics 变化才重开 B1/B4/B6/B7/B9。

## 3. 官方 benchmark / harness 覆盖矩阵

在上述六个 official repo 中对 `locomo`、`longmemeval`、`membench`、`halumem` 和 Phase 1
BEAM 入口做文件级与源码级穷举，命中数均为 0。`apache-beam` 依赖文本不是 benchmark
BEAM。故矩阵为：

| Benchmark | current official harness | `author_<benchmark>` | 主轨身份 |
| --- | --- | --- | --- |
| LoCoMo | 无 | 不建立 | framework extension |
| LongMemEval | 无 | 不建立 | framework extension |
| MemBench | 无 | 不建立 | framework extension |
| BEAM | 无 | 不建立 | framework extension |
| HaluMem | 无 | 不建立 | framework extension |

旧 MemGPT 论文和 onsite repo 的 nested K/V、NaturalQuestions document QA 只能帮助理解方法，
不能外推五格 payload 或参数。第三方 MemoryData 的 Letta 0.7 路径同样不是 current official
harness；它直接写 archival passage、随后让 Letta agent 自己检索并回答，与本框架的
retrieve-first 协议均不同。

因此 B0 的严格含义是：**不存在“照抄官方五格 payload”这一步**；adapter 必须服从 current
official product surface，同时逐 benchmark 复用已冻结的公开输入契约。

## 4. Official AI Memory SDK 的最终产品 payload

`ai-memory-sdk` v0.2.0 把 Letta 的 memory-only 意图写得最明确：

1. 每个 `subject_id` 对应一个 `agent_type="sleeptime_agent"` 的 agent；默认模型在 SDK
   源码中写为 `openai/gpt-4.1`。
2. 默认建立 `human` block（10,000 chars）和 `summary` block（1,000 chars）。
3. `add_messages(..., skip_vector_storage=True)` 接受任意数量的 role/content message；格式器
   保留每条 role，把整批变成一个 user message：

   ```text
   <messages>The following message interactions have occured:
   user: ...
   assistant: ...
   </messages>
   ```

4. 该 wrapper 送入 `agents.messages.create_async`，调用方随后必须 `wait_for_run(run_id)`；
   “API 返回”不等于 memory 已可读。
5. 默认 `skip_vector_storage=True`，所以 raw messages **不会**复制进 passages。官方 README
   建议每次 5–10 messages 批量调用，以减少每批一次 agent invocation 的成本。
6. readout 是 attached core blocks：SDK 的 `get_user_memory` 与 `get_summary` 分别读取
   `human` 与 `summary` block。
7. 只有显式 `skip_vector_storage=False` 才逐条创建 archival passage；SDK 的 `search()`
   也明确依赖这一 opt-in 路径。

承重一手锚：

- [sleeptime agent 创建与默认模型](https://github.com/letta-ai/ai-memory-sdk/blob/4494e00410469082bf298b8b03b7c9f93e244f14/src/python/ai_memory_sdk.py#L27-L38)
- [message wrapper 与 async send](https://github.com/letta-ai/ai-memory-sdk/blob/4494e00410469082bf298b8b03b7c9f93e244f14/src/python/ai_memory_sdk.py#L128-L159)
- [role/content formatter](https://github.com/letta-ai/ai-memory-sdk/blob/4494e00410469082bf298b8b03b7c9f93e244f14/src/python/prompt_formatter.py#L13-L26)
- [默认 blocks](https://github.com/letta-ai/ai-memory-sdk/blob/4494e00410469082bf298b8b03b7c9f93e244f14/src/python/ai_memory_sdk.py#L297-L342)
- [core block readout 与 opt-in search](https://github.com/letta-ai/ai-memory-sdk/blob/4494e00410469082bf298b8b03b7c9f93e244f14/src/python/ai_memory_sdk.py#L375-L420)
- [官方 batching 与 completion 提示](https://github.com/letta-ai/ai-memory-sdk/blob/4494e00410469082bf298b8b03b7c9f93e244f14/README.md#adding-memories)

## 5. 主轨接口裁决

### 5.1 Runtime 与生命周期

- runtime 用 vendored Letta V1 server 的 `SyncServer`、manager/agent loop 和本地 PostgreSQL
  数据层；不要求用户启动 Letta HTTP host，也不走 Letta cloud。worker 依赖使用 vendored
  `uv.lock` 的独立 Python 3.12 环境，避免把 Letta 的 250+ 包与主框架依赖扁平合并。
- adapter 复现 §4 的产品 call graph，不复制 SDK 网络层：创建 sleeptime agent 和 blocks，
  发送 formatted batch，等待精确 terminal，再读 blocks。
- `prepare` 创建 runtime/actor/agent/blocks；`ingest` 只负责当前 session 的消息批；
  `finalize` 等待残余 run；`retrieve` 只读 blocks；`cleanup` 删除本 namespace 并关闭 runtime。
- M2 必须证明：初始化、发送、等待失败均可见；早失败 cleanup 不丢 runtime；同 agent 禁并发；
  W2 只能通过不同 run-scoped runtime/agent 实证，不能由“有两个对象”推断。

### 5.2 输入粒度

- `consume_granularity="session"`。每个 session 内按原顺序切成至多 10 条 message 的 batch；
  不跨 session 合批。
- 不补 placeholder：官方 formatter 接受任意 role 次序和奇偶数量，只负责逐行保留 role。
- LoCoMo 没有 user/assistant 真值，采用稳定的 session-level speaker map 把两位 speaker 固定映射
  到 user/assistant，同时在 content 保留真实 speaker name；caption 走共享
  `[Sharing image that shows: ...]` helper。
- 其余四家保留 canonical role 原序；LongMemEval 连续同 role、assistant-first、singleton 与
  BEAM 10M orphan/mismatch 都不重排、不伪造回复。
- source time 对 memory learner 必须可见：有 turn time 用 turn time；仅有 session time 则回落
  session time；两者都无则不制造 wall clock/sentinel。MemBench 原文已有 time/place 时不重复
  拼 time，但仍保留原 content；missing-time noise 不伪造时间。

最后两项只是 M2 的 payload 裁决，尚须由生产路径强反例锁定；不能把本 note 当成 adapter 已完成。

### 5.3 Readout 与 metric 初判

- `formatted_memory` 包含所有 attached、公开的 learned core blocks，至少 `human` 与 `summary`，
  按稳定 label 顺序渲染；query 不送进 Letta agent，避免 retrieval 阶段污染状态。
- 主轨 readout 是演化后的 query-independent blocks，不是可枚举 raw source items。因此五家
  Recall@k、Precision@k、F1@k、NDCG 与 stable ranking 初判均为 `N/A`；不能拿 block 参与过的
  source ids 冒充当前 block 仍逐条承载原事实。
- HaluMem QA 可使用 blocks，初判 `valid`；extraction、update、memory_type 没有 product-level
  session-local point/delta/type 输出，初判 `N/A`。M2 仍须证明无损观测 sidecar 不能在不改变
  算法输出语义的前提下补齐，才可最终盖章。
- `skip_vector_storage=False` 的 archival 条目可排名且可挂 source id，但那是另一配置与另一
  记忆内容，不能用来替主轨 blocks 偷算 retrieval metric。

## 6. 模型与配置身份

官方 SDK 的 `openai/gpt-4.1` 只证明 product default，不自动进入本项目主表：

- `smoke`：项目统一 `opencodego/deepseek-v4-flash` runtime；
- `official_full`：项目统一 `primary/gpt-4o-mini` runtime；
- Letta build LLM 的 provider/model/base URL/transport 与 embedding identity 必须全部进入
  manifest/resume identity；secret 不得落盘。

两条主配置是 controlled product configuration，分数不可与官方默认 GPT-4.1 直接对表。因
五家没有官方 harness，不建立伪 `author_*`；以后若用户要单独研究 GPT-4.1，只新增显式实验
section，不修改主配置含义。

## 7. M2 必须关闭的剩余门

1. 用 current vendored source 走通 in-process sleeptime agent 的真实调用链，而不是 fake-only
   模拟官方 SDK 表面。
2. PostgreSQL、actor、agent、blocks、background run 的所有权与 cleanup/retry 状态机。
3. OpenAI-compatible build LLM 与 embedding 的配置映射、timeout/retry、效率观测和 secret
   负空间。
4. 五格 canonical event 到最终 wrapper 的字节级强反例，尤其 LoCoMo speaker/caption/time、
   LongMemEval role 异形、MemBench time/place 与 missing time、BEAM 10M 两处异常、HaluMem
   session 边界。
5. zero-hit/empty-block、LLM 不更新 block、run failed/cancelled/timed-out、partial initialization
   与 cleanup retry。
6. 完成上述门后建立 living dossier、生成 `smoke-plan-v1`；未经用户另行批准，不运行真实
   Letta smoke/API。

## 8. 架构师判词

`LETTA_M1_PRODUCT_IDENTITY_ACCEPTED`：

- source 已锁；
- Phase 1 官方 harness 覆盖已穷举为零；
- active Letta Code 与 legacy V1 已明确分轨；
- primary product surface 已从 direct archival bypass 改判为 official sleeptime-memory contract；
- M2 可以开始，但 ledger 中 lifecycle、五格、metric 与 B11 仍保持未完成状态。

## 9. M1-R1：真实初始化探针勘误（2026-08-02）

M1 首版把 legacy server 的本地 backend 写成 SQLite，这是被 current production import/初始化
探针推翻的旧印象，现已撤回：

- `settings.database_engine` 在没有 PG env 时确实返回 `SQLite`，但
  `letta/server/db.py:20-21,57-58` 无条件把 `settings.letta_pg_uri` 转成 `asyncpg` URI 并创建
  PostgreSQL engine；它没有 SQLite 分支。
- 在隔离 `HOME`、隔离 `LETTA_DIR`、清空外部 API key 的真实 `SyncServer` 初始化中，第一次
  actor query 仍尝试连接 `localhost:5432`，不是写 SQLite。
- upstream `CONTRIBUTING.md:30-61` 明写开发环境要求 PostgreSQL；`compose.yaml:1-36` 也以
  Postgres/pgvector 为正式数据层。这与真实调用一致，优先级高于残留 enum/config 字段。

同时，`uv pip install --dry-run 'letta[sqlite]==0.16.8'` 会给主环境新增约 178 个包并卸载或
降级 12 个既有包；current 无锁解析还把 `mcp` 解到与 `fastmcp` 不兼容的版本。故 M2 锁定：

1. 不给主项目直接添加 `letta` 依赖；
2. 使用 vendored `pyproject.toml + uv.lock` 的 Python 3.12 独立 runtime；
3. 只额外补 current server 无条件 import/PG runtime 所需且由 upstream lock 已锁版本的
   `asyncpg`、`pg8000` 与 `pgvector`；不启用会强制本机编译 `psycopg2` 的整包 extra；
4. adapter 与 worker 通过本地长驻 stdio 传输结构化命令，worker 内部直接调用 `SyncServer`
   与 agent loop。该进程是依赖隔离边界，不是 HTTP host，也不改变 Letta 算法调用链。

因此 M1 的 product/interface 裁决不变，只有 storage/runtime packaging 从“SQLite 同进程”
勘误为“PostgreSQL + 独立本地 worker”。M2 必须继续证明 DB namespace、进程退出、异常传播与
clean retry，不能把这次 import 成功冒充 lifecycle 已闭合。
