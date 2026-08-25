# Letta / MemGPT profile provenance（M7）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M7 一手证据，不改写成新 run 收据。

> 当前判词候选：`M7_EVIDENCE_COMPLETE / LEGACY_V1_ARCHIVE_SOURCE_LOCKED /
> OFFICIAL_SDK_CONTRACT_LOCKED / PAPER_PRODUCT_ALGORITHM_VARIANT /
> FRAMEWORK_SLEEPTIME_CORE_BLOCK_MAIN_VALID / ARCHIVED_LOCOMO_HARNESS_IDENTIFIED /
> EMBEDDING_NOT_APPLICABLE_FOR_MAIN / ACTIVE_PRODUCT_SEPARATE /
> SOURCE_LOCK_SCOPE_REVIEW_REQUIRED / AUTHOR_NOT_READY`。
>
> 本文把 MemGPT 论文、legacy Letta V1、官方 `ai-memory-sdk` 产品契约、活跃 Letta Code 与
> framework main 分开记录。它们同属一个演化谱系，但不是可由一组 TOML 参数互相替换的同一
> 算法身份。本批只闭合证据，不修改 TOML、adapter、第三方源码或 prompt registry，也不调用
> 真实 API。

## 0. 身份与范围

- 审计日期：2026-08-25。
- 论文：`MemGPT: Towards LLMs as Operating Systems`，本机 local-only PDF
  `third_party/methods/letta/Packer 等 - 2024 - MemGPT Towards LLMs as Operating Systems.pdf`，
  SHA-256=`9f674bcff69c86f11c813dcfad613d8841f5f8ed17979e3c4df06a91df7762e0`。
- framework runtime：`letta-ai/letta@b76da9092518cbaa2d09042e52fdcbde69243e18`，
  package version `0.16.8`、Apache-2.0；release tag `0.16.8`=
  `1131535716e8a31c9a437f8695e25ac98f203a24`。
- current source status：2026-08-25 官方 `letta-ai/letta` 的 `main`=
  `4511fa0bc91f68fbab32b91f694617271ea9012b`，现为 landing repository；退休的 V1 source
  保存在 `archive`=`56ba9c25552605eec89de8ed3dc6394b625c1993`。framework source lock 中的 20 个
  runtime 文件与该 archive branch 对应文件逐字一致。
- 官方产品契约：`letta-ai/ai-memory-sdk@4494e00410469082bf298b8b03b7c9f93e244f14`
  = tag `v0.2.0`；2026-08-25 current main 仍是同一 commit。
- 活跃新产品：`letta-ai/letta-code@6d8cfabb0f95a665c9cf165110de0bb918508446`
  （2026-08-25 main）。它是新的完整 agent/product surface，不是 legacy V1 的无损升级。
- current eval sources：`letta-evals@f6855fed1dbca208dd603e930d8cf558bc6555f4`；
  `letta-research-onsite@c4f132e5dee8971e7d35ad8296662b1058b251bb`。
- framework current source identity：`source_sha256=98b621ca88b68304c9f119476dec49eb88615ea23fdcb5fbdcff9759fef6be47`；
  `vendored_source_sha256=823e2a22693b61287021c3aad78e1a9a5849b62833dced46ae9d7182ed647c31`；
  20 个 upstream 文件加 adapter/worker/transport/bootstrap 四个 wrapper hash 进入 identity。
- 该 20-file 集与 `archive` branch 逐字一致，但**不是完整行为文件集**：实际调用链还消费
  `sleeptime_v2.py`、`prompt_generator.py`、`core_tool_executor.py`、summarizer/compaction、
  message/archive/embedding/settings 等未入 hash 的文件。Git commit pin 仍标识完整 checkout，
  但对本地局部漂移的 content hash 门不完整，M11 必须扩锁。
- `ai-memory-sdk` 源码没有 vendored 到项目恢复资产；本批从上述 pinned/current commit 的临时只读
  checkout 复核了 formatter、batch、block 与 search 分支。URL+commit 已锁，M11 再决定是否把
  SDK source/hash 纳入可重放 fetch 合同。
- 本次不覆盖：真实结果复现、Letta Code 新 adapter、archival-RAG diagnostic profile、真实
  PostgreSQL/API smoke、参数 sweep、旧 artifact 重标或 method judge 注册。

## 1. 算法机制先行

### 1.1 MemGPT 论文阶段图

| 阶段 | 输入 | 状态/输出 | 是否可选 | 一手出处 |
| --- | --- | --- | --- | --- |
| Main context | system instructions、working context、FIFO queue | LLM 当前可见的有限上下文 | 核心 | paper §2、Figure 1 |
| Recall memory | 历史 messages/events | 可按时间与文本回看的外部 context | 核心层 | paper §2-§3 |
| Archival memory | documents / durable facts | embedding-backed semantic store；论文实验使用 `text-embedding-ada-002` + PostgreSQL | 核心层 | paper §2、§3、Appendix |
| Memory pressure / queue eviction | token pressure、new messages | warning 后由 agent/function calls 把内容移往外部 context，再从 FIFO 淘汰 | 核心 | paper §2.1-§2.2 |
| Agent-controlled memory functions | 当前 query/state | recall/archival search、insert 与 core-memory edit；heartbeat 支持连续工具步骤 | 核心 | paper §2.2-§2.3 |
| Readout / answer | main context + agent检索回的外部 memory | agent 在同一 loop 中继续回答 | 核心 | paper §2-§3 |

论文实验是 deep-memory retrieval、nested key-value 与 document QA，不是 Phase 1 的五个
benchmark。论文的“虚拟上下文管理”包含 recall、archival、队列与 agent 主动 search；不能把
后来的 background sleeptime core-block learner 直接写成论文等价实现。

### 1.2 current product 与 framework main

| 论文/产品阶段 | current module/function | 控制参数 | 分叉 | 判词 |
| --- | --- | --- | --- | --- |
| official memory-only product | `ai-memory-sdk.Memory._create_sleeptime_agent()` | `agent_type=sleeptime_agent`、默认 `openai/gpt-4.1` | 论文不是独立 background memory-only agent | `PRODUCT_EXTENSION` |
| message learning | SDK `format_messages()` → `agents.messages.create_async()` | 建议 5-10 messages/batch；`skip_vector_storage=True` | 整批 role/content 被包成一条 user message；raw message 默认不进 archival | `OFFICIAL_PRODUCT_CONTRACT` |
| core-memory edit | `sleeptime_v2.PROMPT` + `BASE_SLEEPTIME_TOOLS` | human/summary block limit、max steps、LLM config | 只允许 replace/insert/rethink/finish；standalone sleeper 不含 archival/conversation search | `ALGORITHM_VARIANT_FROM_PAPER` |
| completion | SDK `wait_for_run()`；framework worker 走真实 `AgentLoop.step` 并等待终态 | max_steps、worker lifecycle | SDK cloud async，framework local direct core + PostgreSQL worker | `CONFIG_EQUIVALENT_RUNTIME_VARIANT` |
| readout | SDK `get_user_memory/get_summary`；framework `read_blocks()` | attached blocks | query-independent；不执行 passage search | `OFFICIAL_PRODUCT_READOUT` |
| optional raw-vector path | SDK `skip_vector_storage=False` + `search()` | embedding + tags | 会改变写入内容与 readout，可排名但绕过 main core-block estimand | `SEPARATE_PROFILE_REQUIRED` |
| context compaction | V3 token estimate → `compact()` → rebuild system prompt | context window、source constant | docstring 声称非 GPT-5 为 100%，实现却无条件返回 `0.9 * context_window` | `SOURCE_DOC_CONFLICT / EFFECTIVE_90_PERCENT` |

framework 的主 profile 选择 official `ai-memory-sdk` 所定义的 sleeptime-memory 产品意图：对
conversation observations 维护有限 core blocks，再由统一 reader 使用这些 blocks。它不是
“因为 archival 比较难所以关闭”的简化，而是一个明确的 estimand：测 background learned memory，
而不是 raw-message vector RAG。

### 1.3 `embedding=None` 的准确含义

- official SDK 创建 cloud agent 时**省略** embedding config；省略不等于服务端对象一定是
  `None`。framework local direct-core profile 则显式构造 `embedding_config=None` 并在读回时
  校验。
- main profile 的 raw messages 因 `skip_vector_storage=True` 不写 archival passages；standalone
  sleeptime tools 也不含 archival/conversation search；retrieve 只读 attached blocks。因此当前
  algorithm output 不消费 embedding，controlled embedding 身份应为 N/A，而不是虚填 MiniLM。
- initializer passage 只用于 subject 初始化与恢复识别，framework 强制 `embedding is None`，不参与
  retrieval。
- 未来只要启用 raw passage、archival semantic search、files 或 Letta Code memory，就必须新建
  profile、显式选择 embedding、全量重建并重开 metric/observability；不能把旧 artifact 原地重标。

## 2. 官方 benchmark 覆盖

| benchmark | 论文报告 | current official harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | 否 | current `letta`/`letta-evals` 无；官方 owner 已归档 `letta-leaderboard@802a794…` 有 files/search harness | bundled `locomo10.json`，无独立 upstream revision lock | 每 sample agent + session files + `search_files` + agent-native answer | `ARCHIVED_OFFICIAL / INCOMPLETE` |
| LongMemEval | 否 | current、archived leaderboard 与 evals 均无 | N/A | framework session extension | `SOURCE_UNAVAILABLE` |
| HaluMem | 否 | 同上 | N/A | framework session extension | `SOURCE_UNAVAILABLE` |
| BEAM | 否 | 同上；依赖中的 Apache Beam 不算该 benchmark | N/A | framework session extension | `SOURCE_UNAVAILABLE` |
| MemBench | 否 | 同上 | N/A | framework session extension | `SOURCE_UNAVAILABLE` |

current repo 对五格仍为零，但旧稳定页“所有官方 source 都没有 LoCoMo”的绝对表述已被 archived
leaderboard 反证。归档 harness 已停止维护且完整 effective server defaults 不可还原，所以它只把
LoCoMo 从 `SOURCE_UNAVAILABLE` 提升为历史 author candidate，不足以进入主表；其余四格的
“未找到”只覆盖上述公开 official repos/branches/tags 与关键词，不证明作者从未做过私有实验。

## 3. Prompt / judge 合同

- current 五格没有 Letta/MemGPT harness；但 archived leaderboard 的 LoCoMo 是一条不同的
  author topology：按 session 生成 timestamped files（caption 用 `[Image: ...]`），每 sample 一个
  `locomo_agent`，硬编码 `text-embedding-3-large/1536`，要求先 `search_files`，最终用
  `answer_question` tool return 作预测。它跳过 category 5。
- archived LoCoMo system prompt 要求基于文件、按 timestamp 解析相对时间、冲突时最新事实优先并
  输出精确短答；model config 只锁 `gpt-4o-mini-2024-07-18` 与 context window 100000，未锁
  temperature/max_tokens/top_p/response format/search 默认。judge 使用 GPT-4.1、temperature 0、
  max_tokens 2048 的 A/B/C grader。数据 upstream revision 与完整 Letta server payload仍不完整。
- 因此 archived prompt 是历史 author 候选证据，不是可以直接注册的完整 builder；它还让 Letta
  agent 自己 search+answer，与 framework 统一 reader 的主表 estimand不同。
- `sleeptime_v2.PROMPT` 是 **memory build system prompt**：要求 background agent 保持 blocks
  comprehensive/readable/up-to-date、使用绝对日期、选择性写入且追求高 recall。它不是 benchmark
  answer prompt，不能放进 `src/memory_benchmark/prompts/author/`。
- SDK message wrapper 的最终 payload 是一条 user message：

  ```text
  <messages>The following message interactions have occured:
  user: ...
  assistant: ...
  </messages>
  ```

  framework 复用其逐 role 格式与拼写，不要求 user/assistant 严格交替，也不补 placeholder。
- framework main 的最终回答与 judge 继续使用 benchmark-owned builder/metric contract；这不是
  author parity，而是 Phase 1 的 controlled readout policy。
- 裁决：LoCoMo=`ARCHIVED_OFFICIAL / INCOMPLETE / AUTHOR_NOT_READY`；其余四格=
  `SOURCE_UNAVAILABLE / AUTHOR_NOT_READY`。

## 4. 参数矩阵

| parameter path | upstream/product value | paper role | current main | final call | 分类 | rebuild impact | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `agent_type` | SDK=`sleeptime_agent` | 论文无此独立角色 | `sleeptime_agent` | `CreateAgent.agent_type` | topology | 是 | main 锁定 |
| `enable_sleeptime` | standalone agent create 省略 | 论文无 | `None`，读回要求 false-ish | `CreateAgent.enable_sleeptime` | topology | 是 | 与 chat+sleeptime 双 agent 分轨 |
| `skip_vector_storage` | SDK default `True` | 论文 archival 用 embedding | `True` | ingest metadata / 无 raw passage insert | topology | 是 | main 锁定 |
| `context_window` | SDK 服务端/default；旧 product 可配 | main context 有限是论文核心 | `128000` | `LLMConfig.context_window` | method LLM | 是 | controlled main |
| `max_tokens` | SDK未显式 | N/A | `4096` | `LLMConfig.max_tokens` | method LLM | 是 | controlled main |
| `temperature` | SDK未显式 | N/A | `0.0` | `LLMConfig.temperature` | method LLM | 是 | deterministic controlled main |
| `max_steps` | SDK run wait；未给该本地字段值 | heartbeat/多步工具调用属论文机制 | `50` | `AgentLoop.step(max_steps=...)` | algorithm budget | 是 | 保留多步编辑，不可无证缩为1 |
| `max_messages_per_batch` | README 建议 5-10 | 论文无 SDK batching | `10` | session 内 positional chunks | topology/cost | 是 | official上界；不跨session |
| `human_block_limit` | SDK `10000` | 论文 core memory limited | `10000` | `CreateBlock.limit` | capacity | 是 | official contract |
| `summary_block_limit` | SDK `1000` | 论文 core memory limited | `1000` | `CreateBlock.limit` | capacity | 是 | official contract |
| `embedding_config` | SDK省略 | paper archival=`ada-002` | explicit `None` | `CreateAgent.embedding_config` | state backend | 是 | main N/A；archival profile另建 |
| tools | V1 standalone sleeptime set | paper含search/insert/edit | replace/insert/rethink/finish | exact tool set validation | topology | 是 | product identity锁定 |
| compaction trigger | source实现=`0.9 * context_window` | paper warning/flush示例为约70%/100% | effective 90% | V3 step 后 `compact()` 门 | algorithm/context | 是 | 以代码90%为事实；修doc或改行为须新裁决 |
| `postgres_image` | legacy V1正式路径依赖 PostgreSQL | paper使用PostgreSQL | `ankane/pgvector:v0.5.1` | local runtime lifecycle | runtime/state | 是 | method state owner，非LLM参数 |
| `max_workers` | SDK无跨worker保证 | N/A | `1` | registry/preflight | execution safety | 否 | 证据不足前W1-only |

`max_steps`、block capacity、batch size 与 tool set 都会改变 learned state，必须进入 build identity。
timeout、credential 与 conversation workers 继续由 runtime/execution composition 管理，不复制回
method TOML。

## 5. 配置流与强反例

- TOML → `LettaConfig` → registry factory → runtime payload → worker `LLMConfig/CreateAgent` →
  product object；worker 在 subject 已存在时逐字段反查 LLM config、agent type、tools、tags、block
  description/limit、archive 与 initializer。
- `max_messages_per_batch>10`、非正整数、block limit 偏离、`max_workers!=1`、空 model/image 与非法
  temperature 在启动产品/API 前 fail-fast。
- source identity 既包含 upstream release/SDK commit，也包含真实行为文件集与四个 wrapper hash；
  active Letta Code 漂移不会静默改变 legacy artifact；但当前 20-file content hash 漏掉 prompt/tool/
  compaction 等实际消费者，不能把“commit 已锁”误写成“局部 source hash 已完整”。
- current adapter 的 `consume_granularity=session`；session 内原序分批，尾 singleton 合法，不跨
  session、不补 placeholder。LoCoMo 只在 canonical 层做稳定 speaker→role map并在 content 保留
  speaker；其余四格保留 canonical role 异形。
- retrieve 忽略 query、读全部 attached blocks，`items=None`，因此五格 qrel/rank metric 诚实 N/A；
  lineage 不能用来伪造当前 block 对 source fact 的逐项承载。

## 6. 主配置与作者配置裁决

- framework main：legacy V1 0.16.8 + official SDK v0.2.0 contract + standalone
  sleeptime core-block learner + benchmark-owned reader。它是 product-faithful framework extension。
- `author_<benchmark>`：当前不建立。LoCoMo 有 archived official candidate，但 dataset revision、
  server defaults、search payload 与完整 decode/runtime未闭合，且 files+agent-native answer 是独立
  topology；其余四格没有公开完整 harness。
- product-default 补充身份：SDK build model `openai/gpt-4.1` 只可作为显式 product calibration；它
  不是五格 author result，也不能暗换 controlled main runtime。
- topology variants：
  1. original MemGPT recall+archival agent loop；
  2. official SDK sleeptime core blocks（current main）；
  3. direct archival insert/search；
  4. active Letta Code/MemFS agent。
  四者不得靠一个 bool 或同名 `native` profile混装。

## 7. 第三方框架：先重建目标，再判断迁移

### 7.1 OmniMemEval

它面向多 memory product 的统一、可操作横评：cloud API、每 conversation 一个 agent，允许
`files/archival/messages` 三种 ingest、`direct/rag` 两种 eval、passages/archival 两种 search；示例
默认 archival + RAG、batch20、top-k20、`gpt-4.1`、`text-embedding-3-small`。

- 收益：把产品 surface 暴露得非常完整；direct 与 RAG 可显式分 estimand；archival 路径便宜、
  deterministic、可排名，便于跨产品统一。
- 代价：默认路径不运行 sleeptime memory learner，测到的是 Letta 托管 archival RAG，而不是
  framework 当前 core-block learned memory；cloud server version 也没有被该 env file 锁定。
- 可借鉴：显式 mode 枚举、一个 conversation 一个 namespace、对不同 ingest/readout 组合分
  identity。不可直接迁入 main 的不是“它设计错了”，而是它回答的问题不同。
- 它的公开 adapter 覆盖 LoCoMo、LongMemEval、BEAM、HaluMem，不含 MemBench；这些是 MemTensor
  comparison harness，不是 Letta author harness。LoCoMo Letta 分支未携带 caption，BEAM/HaluMem
  时间解析失败会分别回填固定日期或 wall clock，结果文档又缺对应 effective config snapshot；
  若将来复现，必须把 ingest/eval/search mode、server版本、时间策略、top-k、模型和 embedding
  全部锁进 identity。

### 7.2 MemoryData

它面向本地可复现的 agent answering：Qwen3-8B、Qwen3 embedding 4B/2560、32768 context、
insert mode、chunk2048、archival page size3，并在 query 前用数据库快照恢复状态。

- 收益：本地模型/embedding、上下文预算、snapshot isolation 和工具输出 page size 被显式配置；
  对有限 context 的 agent answer 是合理工程取舍。
- 代价：direct archival insert/search 与 method-owned answer 把 memory build、retrieve 和 answer
  agent耦合，且属于另一个 vendored Letta generation；不等价于本项目只比较 memory quality 的
 统一 reader。
- 可借鉴：snapshot-before-query、上下文预算与 final effective config 的可观测性；若未来建立
  archival diagnostic profile，可参考其 page-size/context 联动。

## 8. 未闭合项与重读触发器

| item | status | 已查范围 | 下一条一手证据 |
| --- | --- | --- | --- |
| archived LoCoMo author topology | `INCOMPLETE` | `letta-leaderboard@802a794…` 的 files/search/agent/judge链 | 锁 dataset hash/server defaults/search payload 后再评估 |
| 其余四格 author harness | `SOURCE_UNAVAILABLE` | current/archive/SDK/evals/research repos 与关键词扫描 | 新公开 official repo/harness 才重开 |
| active Letta Code parity | `ALGORITHM_VARIANT` | current repo identity与产品定位 | 用户决定新增method/profile时专项审计 |
| archival diagnostic | `PENDING` | official SDK opt-in + 两个第三方框架 | 独立spec、embedding与metric身份后再做 |
| product-default GPT-4.1效果 | `PENDING` | SDK默认值 | 用户批准真实校准run后再做 |
| content source lock coverage | `REVIEW_REQUIRED` | current 20-file list 与真实 prompt/tool/compaction调用链 | M11 扩展行为文件清单并加mutation |

机制卡以后可直接回答 MemGPT/Letta 的 memory hierarchy、sleeptime、embedding 与 core-block问题。
只有 paper/version 改变、上游 archive/source 漂移、引入 archival/Letta Code 或现有 locator 失效时
才定点重读，不再从头调查。

## 9. 验证记录

- current remote：`git ls-remote` 锁定 `letta main/archive`、`letta-code main`、
  `ai-memory-sdk main/tag`、`letta-evals main`、`letta-research-onsite main`；另锁
  `letta-leaderboard@802a794…` archived LoCoMo source。
- source：本地 pin/version/license、PDF hash、SDK call graph 已复核；20 个已声明文件与 archive
  branch比对为 `count=20, diffs=0`，同时从实际调用链确认 source-hash scope 不完整。
- 零 API baseline：
  `uv run pytest -q tests/test_letta_adapter.py tests/test_letta_worker.py
  tests/test_letta_registered_prediction.py tests/test_config_profiles.py
  tests/test_method_registry.py tests/test_documentation_standards.py
  tests/test_codex_project_hooks.py` → `218 passed in 2.99s`；`git diff --check` clean。
- 架构验收：两路 Luna/max 只读收据已做范围门；paper/product、archived LoCoMo、source-lock
  缺口、compaction冲突与第三方 estimand 已由架构师按本地/remote一手锚复核。仍须复跑文档门后
  盖章；subagent 回报本身不构成 stable fact。
