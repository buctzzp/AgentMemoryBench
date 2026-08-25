# EverOS / EverMemOS profile provenance（M9）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M9 一手证据，不改写成新 run 收据。

> 状态：`M9_EVIDENCE_COMPLETE`。paper、历史 research/evaluation、v1.2.3 product、current
> product 与 framework main 已分栏；两份调查 subagent 回执均只作为候选证据，经架构师按一手
> 源码、论文、运行时有效配置和最终 payload 抽锚后才进入本文。作者配置的可运行施工与 main
> profile 改判统一留到 M11，不在取证批次边查边改。
>
> 本批零真实 API、零参数 sweep、零 source upgrade；不修改 TOML、adapter、prompt registry 或
> 旧 artifact。尤其不能因为 current product tree 只保留 LoCoMo harness，就误写成“官方从未公开
> LongMemEval harness”：官方历史在 2025-11 已加入 LoCoMo/LongMemEval/PersonaMem evaluation，
> 但该历史不在 current main ancestry，exact paper commit 仍须单独裁定。

## 0. 身份与范围

- method：EverMemOS / EverOS 的 user-memory Episode pipeline；不把 agent-memory、knowledge-base、
  hosted product 或第三方 wrapper 混成同一算法身份。
- 审计日期：2026-08-25。
- paper：`EverMemOS: A Self-Organizing Memory Operating System for Structured Long-Horizon
  Reasoning`，arXiv `2601.02163v2`（2026-01-09），本地 PDF
  `third_party/methods/EverOS/EverMemOS.pdf`，SHA-256
  `265314799f9803a841a3aeb6fca949ce5eb6923d1d8a450de26843993e1605fd`。
- framework pin：`EverMind-AI/EverOS@48fc9084888bc17100053227284f939a5aca5e91`，tag
  `v1.2.3`，Apache-2.0；source 通过 framework patch 和独立 Python 3.12 runtime 重放。
- v1.2.3 的 `uv.lock` 还固定了八个 EverAlgo 发布包；架构师对承重组件抽查官方 tag：
  `agent-memory/v0.4.0=d26fb2f…`、`boundary/v0.2.1=088102d…`、
  `core/v0.3.0=1152725…`、`rank/v0.4.1=673ace5…`、
  `user-memory/v0.4.0=6be77fe…`。这些锚证明 package version 有公开官方 source tag；尚不能仅凭
  tag 证明 PyPI wheel/sdist 与 Git tree bytes 完全相同。
- current remote：2026-08-25 `main=786406129582ba18ac65a71086b0417e830de29d`。相对 v1.2.3
  不只是 docs/dependency 漂移：product service 新增 `buffer_messages()` 与 `defer_extraction` seam；
  framework 没有传后者，默认成功路径暂未因此改变，但不得机械 fast-forward。
- 历史 official evaluation source：官方仓库历史 commit
  `5f70b07164ee3e656aaaf650910c028c721103fe`（2025-11-05）加入
  LoCoMo/LongMemEval/PersonaMem；本地完整快照对应后续官方 commit
  `29d555c6e94de3630f314c1f594fc1801377ff5a`（2026-05-12）。GitHub 当前 URL 会从
  `EverMind-AI/EverOS` 重定向到 `EverMind-AI/EverMemOS`；按 hash fetch 成功，证明它是同 owner
  的公开历史，不是第三方 fork。
- 历史分叉：`29d555c…` 不是 current main 的 ancestor。current tree 与历史 evaluation tree
  不能合并成一个“官方默认”；exact paper source commit 与历史 harness 是否逐字对应仍
  `PENDING`。
- 其他资产：EverAlgo research harness、current product `benchmarks/` LoCoMo harness、
  `第三方框架参考/` 中的 EverCore evaluation，以及 framework main v7 都分别记录。
- 本次不覆盖：真实效果、reranker 服务采购、source upgrade、作者 profile 施工、参数 sweep、旧
  run 重标、HaluMem/BEAM/MemBench 效果解释。

## 1. 算法机制先行

### 1.1 paper 三阶段图

```text
连续对话
  -> LLM semantic boundary detection
  -> raw episode history
  -> LLM narrative synthesis -> Episode
  -> LLM structural derivation -> Atomic Facts + time-bounded Foresight
  -> MemCell
  -> embedding nearest-scene lookup
       similarity >= tau 且 time gap <= window -> assimilate / update centroid
       否则 -> new MemScene
  -> optional scene summary + User Profile refresh

question
  -> dense + BM25 over Atomic Facts
  -> RRF
  -> score/select top MemScenes
  -> pool Episodes -> cross-encoder rerank
  -> optional valid-time Foresight filter
  -> LLM sufficiency check
       sufficient -> return context
       insufficient -> generate 3 rewritten queries -> second retrieval/rerank
  -> Episodes-only reasoning answer
```

| 阶段 | 输入 | 状态/输出 | paper 身份 | 一手出处 |
| --- | --- | --- | --- | --- |
| contextual segmentation | continuous dialogue | raw episode history | Phase I 核心 | PDF §3.3 |
| narrative synthesis | episode history | third-person Episode | Phase I 核心 | PDF §3.3 |
| structural derivation | Episode | Atomic Facts + bounded Foresight | Phase I 核心；Foresight 在 reasoning 主表不消费 | PDF §3.3、Appendix A.1 |
| incremental clustering | MemCell embedding/time | MemScene/centroid | Phase II 核心 | PDF §3.4 |
| profile evolution | scene summaries | explicit/implicit user profile | optional mode；Episodes-only 主表不调用 | PDF §3.4、Appendix A.1/A.3 |
| dense+sparse scene selection | query + Atomic Facts | top MemScenes | Phase III 核心 | PDF §3.5 |
| episode rerank | selected-scene Episodes | top Episodes | Phase III 核心 | PDF §3.5、Appendix A.1 |
| sufficiency/rewrite | query + first context | accept or three rewritten queries | Phase III 核心 agentic controller | PDF §3.5、Appendix C |
| downstream mode | reconstructed context | reasoning answer or chat context | benchmark 主表为 Episodes-only | PDF §3.5、Appendix A.1 |

论文明确的实验参数不是“随 dataset 静默变化的偶然 default”，而是作者为不同 dialogue structure
和 time span 有意选择的作者校准值：LoCoMo `tau=0.70 / max gap=7 days`，LongMemEval
`tau=0.50 / max gap=30 days`。两者共用算法 pipeline，但估计的是**各 benchmark 上作者报告的
有效实现**。本项目跨五格固定 main 回答的是另一个问题——同一产品策略在不同 benchmark 上的
可比表现。二者应分 identity，不能用其中一方证明另一方错误。

### 1.2 paper 实验读出与资源

- benchmark：LoCoMo 10 conversations / 1,540 questions；LongMemEval-S 500 dialogue-question
  pairs / 约 115k tokens。
- retrieval：Qwen3-Embedding-4B dense + BM25，经 RRF；Qwen3-Reranker-4B；默认 top-10
  MemScenes，再选 10 Episodes。
- agentic：LoCoMo GPT-4.1-mini 实验中 31.0% questions 触发 second-round query rewrite；因此
  `agentic` 不是装饰性选项，而是实际消费 LLM/reranker、改变检索集合的核心路径。
- default quantitative mode：Memory-Augmented Reasoning / Episodes-only；profile 不调用，
  foresight 只作 qualitative chat case。因此“关闭 profile readout”不等于“build 时仍提取 profile
  也无所谓”：后者会改变状态和构建成本，不是 paper 主表身份。
- answer：LoCoMo 报 GPT-4.1-mini primary 与 GPT-4o-mini comparison；LongMemEval 用
  GPT-4.1-mini。final answer backbone 被统一以隔离 memory management 贡献。
- judge：GPT-4o-mini；论文的 token table 明确三个 judges/question。method-owned judge 只盘点，
  是否进入 framework 主表仍由 benchmark metric policy 裁定。

### 1.3 current v1.2.3 product 图

```text
framework SessionBatch
  -> typed MessageItemDTO list
  -> product memorize() in batches of 25
  -> final empty flush
  -> exact OME/Cascade drain
  -> public get(session_id) for session report

question
  -> SearchRequest(user_id, query, method, top_k, ...)
  -> SearchManager
       keyword | vector | hybrid | agentic
  -> SearchResponse episodes
  -> framework stable multi-owner merge
  -> benchmark-owned answer builder
```

v1.2.3 product 同时公开 `HYBRID` 与 `AGENTIC`。两者不是同一算法的不同拼写：

- HYBRID：dense+sparse hierarchy，RRF 决定扩展优先级，LR-calibrated score 做全局竞争；不调用
  agentic cross-encoder/sufficiency/query rewrite。
- AGENTIC：embedding + reranker + LLM，执行 scene-guided recall、cross-encoder rerank、
  sufficiency 和必要时 multi-query refinement。

所以 current product 的 request default 若为 hybrid，只证明“通用产品默认希望低依赖可运行”，
不能自动证明它等价于 paper 完整算法；official benchmark 选 agentic，也不是无缘无故的
benchmark 特判，而是用完整 retrieval mechanism 测效果。

### 1.4 framework main v7 图与已知差量

framework main 当前是：

- session ingest，chat mode，batch 25，session末 flush + exact drain；
- controlled `all-MiniLM-L6-v2`/384，通过 upstream `EmbeddingProvider` seam；
- `search_method=hybrid`；
- rerank capability 强制 `disabled-zero-call`；
- `include_profile=false`，但 run-local `ome.toml` 复制 upstream default template；
- LoCoMo 沿 official all-user + real speaker sender，session source time 上按 utterance `+30s`；
- 其他 benchmark 保留 canonical role/order，不重新配对；pure-assistant session 只加无 source id 的
  structural user anchor；
- framework benchmark answer/judge，不暗换 method prompt。

已发现两项需 M11 裁定的核心差量：

1. **hybrid/no-rerank 关闭 paper Phase III agentic controller**。它目前是一个可运行的
   product-default/低依赖 variant，但不能继续无注释地称作 paper-complete main。
2. **默认 OME template 的注释不是“全部关闭”**。策略 decorator 默认 enabled；在 current source
   中 atomic fact、profile clustering 与 profile extraction 可能继续运行，foresight/reflection 关闭。
   `include_profile=false` 只影响 search readout，不能阻止 build-time profile extraction。paper 与
   official LoCoMo Episodes-only 要求 profile extraction 关闭、clustering 保留。

## 2. 官方 benchmark 覆盖

| benchmark | paper 报告 | public official source | topology | source status |
| --- | --- | --- | --- | --- |
| LoCoMo | 是 | historical EverCore evaluation + current product benchmark + research EverAlgo | 三个可区分官方实现；均需 agentic/episode top-10 对表 | `SOURCE_AVAILABLE / IDENTITY_SPLIT` |
| LongMemEval | 是，S setting | historical EverCore evaluation/converter；current product tree 已删除 | converter 把每 question 的完整 haystack 转 LoCoMo-like conversation | `HISTORICAL_SOURCE_AVAILABLE / EXACT_PAPER_COMMIT_PENDING` |
| HaluMem | 否 | 无 method-owner paper harness | framework extension | `N/A_AUTHOR` |
| BEAM | 否 | 无 method-owner paper harness | framework extension | `N/A_AUTHOR` |
| MemBench | 否 | 无 method-owner paper harness | framework extension | `N/A_AUTHOR` |

旧稳定页“LongMemEval paper-reported / public-harness-unavailable”只描述当时检查的 current product tree，
在官方历史证据出现后已不再完整。M9 验收时必须回填稳定页并保留 superseded 说明，不能无痕改写。

### 2.1 历史 LongMemEval converter 的可见语义

历史 `longmemeval_converter.py`：

- 用 `question_id` 构造一个 user speaker 和一个 assistant speaker；
- 保留 raw session order，将每条 `role` 映射成对应 speaker；
- session timestamp 转 LoCoMo-style datetime；
- 每个 LongMemEval question 形成一份独立 conversation；
- 把 answer session 内**全部 messages** 标成 evidence，不能据此宣称 turn-exact qrel；
- `max_content_length=8000` 已从 YAML 追到 CLI `load_dataset()` 和 LoCoMo-style loader 的逐消息
  字符级截断；它是历史 harness 的真实输入变换，不是死配置；
- private answer/evidence 只能供 evaluator，不能进入 framework method 输入。

## 3. Prompt / judge 合同

### 3.1 paper/current product LoCoMo

- build prompt：由 EverOS boundary、Episode、atomic-fact 与 OME strategy source 定义，不是
  benchmark answer prompt。
- search：official current product `SearchRequest(method=agentic, top_k=10)`；profile/foresight在
  Episodes-only 应关闭或不进入 context。current harness 的 `eval_owner="speaker_a"` 只检索一个
  owner partition；framework main 逐 owner 搜索后按 score 全局合并。这是 topology 差异，不是
  普通 `top_k` 覆盖，author parity 必须另有单-owner readout identity。
- answer：GPT-4.1-mini，temperature 0，max_tokens 32768。current harness 把完整
  `ANSWER_PROMPT.format(context, question)` 作为**单条 user message**发送；context 是
  `Episodes memories for conversation between {speaker_a} and {speaker_b}:`，每条 Episode 按
  `{subject}: {episode}\n---` 串联，profile 明确省略。parser 依次尝试最后一次出现的
  `## STEP 7: FINAL ANSWER`、`FINAL ANSWER:`、`FINAL ANSWER`，无 marker 时保留完整输出。
- current prompt 源自 historical EverCore prompt，但并非逐字不变：增加 inference confidence 要求，
  重写 contradiction/gap 段，并把最终区段改成 `## STEP 7: FINAL ANSWER`。所以 current official
  LoCoMo builder 与 historical/paper-era builder 必须分 source identity，不能只登记一个
  `everos_locomo` 名称。
- judge：GPT-4o-mini、temperature 0、3 runs，current harness 对每题取 majority vote；只登记候选，
  不暗换 framework benchmark judge。
- 状态：`CURRENT_LOCOMO_AUTHOR_BUILDER_READY / FULL_AUTHOR_REPRO_PENDING_DATA_REVISION`。最终
  messages、decode 与 parser 已闭合；LoCoMo raw source 仍指向未锁 commit 的上游 main，故不能把
  builder-ready 写成完整数字复现 ready。

### 3.2 historical EverCore LoCoMo / LongMemEval

- system config：`search.mode=agentic`；answer LLM `openai/gpt-4.1-mini`。
- dataset judge：GPT-4o-mini，3 runs。
- historical framework 主张“不同 memory system 可使用自己的 official answer prompt”，这与本项目
  主表 unified builder 的 estimand 不同：它试图忠实评估产品 intended usage，本项目则固定 readout
  以隔离 memory quality。两者都可能合理；historical prompt 只进入显式 author calibration 候选。
- LongMemEval 先转 LoCoMo-style 再走 shared pipeline。historical `EverMemOSAdapter.answer()` 对
  LoCoMo/LME 没有 dataset branch：二者都调用同一 `locomo_response()`，把同一个
  `ANSWER_PROMPT.format(context, question)` 交给 provider 的 `generate(prompt=..., temperature=0)`。
  parser 用 `split("FINAL ANSWER:")[1]` 取**第一次** marker 后的文本；无 marker 时保留完整输出，
  没有独立 abstention parser。
- converter 没有把 raw `question_date` 写入 QAPair 或 answer prompt，因此 historical LME answer
  builder **不消费 question time**。`max_content_length=8000` 则不是死 YAML：CLI 读出后传给
  `load_dataset()`，最终在 LoCoMo-style loader 对每条 message content 作字符级截断。该截断改变
  method 输入，属于 historical author harness 身份，不能暗中进入 framework 无损主配置。
- historical YAML 只显式覆盖 `search.mode=agentic`；其 `ExperimentConfig` effective clustering 是
  `.65/7`，并非 paper 表 6 的 LoCoMo `.70/7` 或 LongMemEval `.50/30`。因此“官方历史 harness
  存在”只能纠正 source availability，不能自动升级为 exact paper reproduction。
- historical final answer 是单条 user message；stage4 覆写 temperature 0，实际 provider object 的
  `max_tokens=32768` 会进入最终 OpenAI payload，不能误用另一路 `ExperimentConfig` 的 16384。
  historical parser 取第一次 `FINAL ANSWER:` 后文本；current product 则按 marker 优先级取最后一次。
- historical judge 同为 GPT-4o-mini、temperature 0、3 calls，但保留三次 accuracy 并在报告层计算
  mean/std，不是 current product 的 per-question majority vote。两者必须分别标识。
- 状态：`HISTORICAL_AUTHOR_CODE_READY / PAPER_AUTHOR_NOT_READY`。29d 的 converter、ingest/search、
  answer、parser 与 judge 代码链已闭合，但 exact paper commit、LongMemEval 数据 revision 和 paper
  实际 payload 未锁，不能命名为 `author_longmemeval_paper`。

## 4. 参数矩阵

| parameter path | product default | paper/official role | historical/current official | framework main | final consumer | 分类 | impact | 暂定裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| memory mode | product default agent | reasoning benchmark用user memory | current LoCoMo README要求chat | chat | boundary/pipelines | topology | fresh rebuild | main chat正确 |
| add batch size | product API可分批 | official product 25 | current LoCoMo 25 | 25 | memorize batches | invocation topology | fresh rebuild/cost | 保留 |
| embedding | Qwen3-Embedding-4B | dense recall + clustering | Qwen3-Embedding-4B | MiniLM384 | embedding capability | controlled method component | fresh rebuild | main controlled；author Qwen |
| clustering threshold | 0.65 | scene assimilation | LoCoMo .70 / LME .50 | 隐式 product .65 | clustering strategy | core build | fresh rebuild | main须显式锁；author sparse override |
| clustering time window | 7 days | scene temporal boundary | LoCoMo 7 / LME 30 | 隐式 product 7 | clustering strategy | core build | fresh rebuild | main须显式锁；author sparse override |
| search method | request/product default hybrid | Phase III agentic | official agentic | hybrid | SearchManager | core retrieve | retrieval rerun；build scenes也相关 | M11需改判 |
| reranker | Qwen3-Reranker-4B provider default | episode selection核心 | official Qwen3-Reranker-4B | disabled-zero-call | agentic only | core retrieve/model | retrieval identity | main差量 |
| scene top-k | product agentic internal/official 10 | top scene set | 10 | hybrid无该阶段 | agentic search | high-impact retrieve | retrieval rerun | author 10；main pending |
| episode top-k | request top_k | answer context | 10 | query.top_k | SearchRequest | readout | rerun retrieval | main由benchmark query控制 |
| owner readout | product按user_id隔离 | LoCoMo official只查speaker_a | `eval_owner=speaker_a` | 搜全部owners再合并 | search fan-out/merge | topology | rerun retrieval | author单owner；main扩展 |
| sufficiency/rewrite | agentic内置 | 31% LoCoMo实际触发 | agentic on | absent | agentic controller | core retrieve/LLM | rerun retrieval | main差量 |
| profile extraction | decorator default enabled unless override | main table不调用 | official eval off | template可能effective on | OME strategy | optional build/cost | fresh rebuild | M11必须显式off |
| profile clustering | default enabled unless override | agentic scene结构需要 | official eval保留 | effective on | OME strategy | core build | fresh rebuild | 保留并锁 identity |
| foresight | v1.2.3 default off | qualitative chat only | official eval off | off | OME strategy | optional build | fresh rebuild | off正确 |
| reflection | default off | paper主表未用 | off | off | OME strategy | lossy maintenance | fresh rebuild | off正确 |
| include_profile | request false by framework | reasoning主表Episodes-only | false/off | false | search response | readout | retrieval rerun | false正确但不能替代build off |
| answer LLM | product generic GPT-4.1-mini | standardized backbone | GPT-4.1-mini | benchmark runtime profile | framework answer | runtime/readout | no memory rebuild | main统一；author候选 |
| judge | external evaluation | 3x GPT-4o-mini | 3x GPT-4o-mini | benchmark judge policy | evaluator | metric | artifact-only | 不暗换 |
| timeout/retry/workers | product/framework runtime | 无算法身份 | harness operational | execution/runtime files | transport/runner | runtime | no method state if pure retry | 不回流 method TOML |

## 5. 配置流与强反例

- current flow：`configs/methods/everos.toml` → profile loader → `EverOSConfig` → registry composition
  → isolated worker initialize payload → controlled embedding capability → official lifespan → typed
  memorize/search/get services。
- current typed gate 强制 chat、hybrid、batch25、MiniLM384、reranker disabled；这使配置可审计，但也
  把 M9 新发现的 mechanism gap 固化成了 fail-fast。M11 若改判必须同时修改 config、worker、
  observer、manifest/resume 与 mutation tests，不能只改 TOML 字符串。
- `include_profile=false` mutation 只能证明 response 不返回 profile，不能证明 OME 没产生 profile。
  架构师已用 vendored v1.2.3 runtime 直接读取 strategy metadata，实测为：
  `extract_atomic_facts=True`、`extract_foresight=False`、
  `trigger_profile_clustering=True`、`extract_user_profile=True`、
  `reflect_episodes=False`。run-local `ome.toml` 没有 uncommented strategy override，故这就是 current
  framework main 的 effective build policy。M11 要显式写 `extract_user_profile=false` 并对最终
  registry object 做 mutation，不能只检查 TOML 文本。
- agentic mutation 必须证明：reranker、sufficiency LLM、query rewrite 的调用与 usage 都被观测；不能
  为了跑通把 agentic 名称映射到 hybrid。
- clustering mutation 必须落最终 `load_settings().clustering`，并进入 manifest/resume；省略 product
  default 不是显式锁值。
- embedding 从 MiniLM 切回 Qwen 或改 dimension/model/revision/normalization，要求 fresh-state 全量
  重建；旧 v6/v7 artifact 不得重标。

## 6. 主配置与作者配置裁决

### 6.1 第一性原理：为什么第三方/官方会按 dataset 调参

paper 的目标是报告方法在每个 benchmark 的最佳、可复现实验表现。LoCoMo 是 10 条较短但密集的
长期对话，LongMemEval 是 500 个超长、每题独立的 haystack；相同 scene threshold/time gap 会产生
不同的 over-merge/under-merge 风险。作者按数据结构调 clustering，是在固定算法阶段的前提下校准
记忆组织尺度，有明确方法学理由。

本项目主表的目标则是比较 method 在五个 benchmark 上的可迁移性与统一运行政策，避免未知
benchmark 上暗中调参。因而：

- `main_controlled`：一个显式固定 clustering policy；回答 cross-benchmark transfer/fairness。
- `author_locomo` / `author_longmemeval`：只在公开 source/final payload闭合后使用作者值；回答
  paper/harness fidelity。
- 两类结果不得混表，也不得用“author更高分”反推 main 错，或用“main更统一”否定 author设计。

### 6.2 暂定配置身份

- framework current hybrid/no-rerank 应重命名/保留为显式 `product_hybrid_controlled` 候选，不能继续
  冒充 paper-complete EverMemOS。
- Phase 1 主配置是否切为 `agentic_controlled`：`PENDING_M11_RESOURCE_AND_OBSERVABILITY_RULING`。
  若核心 method identity 以 paper 为准，agentic更合适；但必须有可重放 reranker seam、完整模型
  identity、失败成本观测和运行资源，不能只把 bool 打开。
- `author_locomo_product_v1_2_3`：builder 证据已齐，候选为 current product chat、agentic、Qwen
  embedding/reranker、product `.65/7`、profile extraction off + clustering on、single-owner readout、
  current answer/parser；完整复现仍等待 raw LoCoMo source revision。paper `.70/7` 不得悄悄混入这份
  current-product profile。
- `author_longmemeval_29d_historical`：历史代码 builder/config 可施工，身份必须显式带 29d，不能
  冒充 paper exact。paper `.50/30` 只登记为 paper-reported 候选；在 exact commit、数据 revision 与
  payload 闭合前保持 `PAPER_AUTHOR_NOT_READY`。
- HaluMem/BEAM/MemBench：无 author profile；只用 framework extension，诚实披露算法身份。

## 7. Manifest / resume / artifact

必须进入 identity：

- product repo/commit/tag、framework patch/source hash；
- memory mode、batch、OME strategy effective enablement；
- clustering threshold/time window；
- search method、scene/episode candidate limits、reranker provider/model/revision/instruction；
- embedding provider/model/revision/dimension/normalization/instruction/distance/tokenizer；
- profile/foresight/reflection read/write policy；
- answer/judge runtime与builder来源；
- historical/product/paper/framework identity label。

current `EVEROS_SOURCE_FILES` 只锁了 API/service/DTO/default config/lifespan 等 14 个代表文件，却没有
锁住实际决定算法的 boundary、Episode/AtomicFact/profile strategy、clustering、SearchManager、
agentic controller、embedding/reranker factory 与 prompt。完整 Git commit pin 能识别 clean checkout，
但 `vendored_source_sha256` 无法发现这些未提交漂移；M11 必须按真实调用链扩 source lock 或改成
完整 tracked-source manifest，不能只给 adapter/worker 盖章。

29d historical evaluation 与 paper 三阶段拓扑相近，但仍是 implementation variant：它把 Episode、
Foresight、AtomicFact 分步处理，并在整段 conversation 后批量 clustering/profile；paper 则把
Structural Derivation 与增量 consolidation 描述成更紧密的在线阶段。再加 `.65/7` 与 paper
`.70/7`、`.50/30` 的参数差异，M9 只能裁 `OFFICIAL_HISTORICAL_HARNESS`，不能裁
`EXACT_PAPER_SOURCE`。

build-side字段变化要求 fresh memory state；纯 answer/judge 改动可重用 retrieval artifact但必须产生新
evaluation identity；search method/reranker/top-k 变化可重跑 retrieval，不能覆盖旧结果。secret、base
URL与私有 gold 不落 manifest；provider/base URL只落安全标识，不落 credential。

## 8. 未闭合项与停工点

| item | status | 已查范围 | 下一条一手证据 |
| --- | --- | --- | --- |
| historical harness 是否等于 exact paper pipeline | `PENDING` | 5f70/29d official history、paper v2 | paper-era commit/diff + stage consumers |
| LoCoMo final answer messages/parser | `VERIFIED` | current run.py + historical prompt/stage4 + 独立回执 locator | M11 builder/parser mutation |
| LongMemEval final answer messages/question time/parser | `VERIFIED_HISTORICAL_CODE` | converter→loader→adapter→stage4 + 独立回执 locator | paper exact identity 仍单列 pending |
| current main effective OME profile extraction | `VERIFIED_GAP` | template + decorator + runtime meta probe | M11显式关闭+mutation |
| agentic controlled reranker resource | `PENDING` | public DeepInfra/vLLM/DashScope seams | Phase 1可重放provider/model裁决 |
| main fixed clustering值 | `PENDING_M11` | product .65/7、author两组值 | 横向公平性裁决，不做效果调优 |
| remote current source upgrade | `PENDING` | main vs v1.2.3 product diff | M11 source-drift review |
| selected vendored source hash coverage | `VERIFIED_GAP` | `EVEROS_SOURCE_FILES` vs product call graph | M11扩锁+mutation |

## 9. Subagent 回执与架构验收

### 9.1 派发合同

- model：`gpt-5.6-luna`；`reasoning_effort=max`。
- scope A：paper/current product mechanism、版本和参数链，只读。
- scope B：official historical/current evaluation、LoCoMo/LME final payload/config，只读。
- 每份回执必须列 source identity、覆盖边界、claim→locator、命令、冲突、未闭合项与 confidence；
  不得修改项目文件或把第三方框架值升级为 author source。

### 9.2 架构验收状态

- mechanism/product 回执：调度请求为 `gpt-5.6-luna / reasoning_effort=max`；子会话只能自报
  generic GPT-5、无法看见部署名，故模型身份按**调度器已接受、子会话自报不可独立复核**记录，
  不猜 trailer。收据的 source/version、claim→locator、覆盖、反证和未闭合项齐全，结构门通过。
- 架构师抽锚通过：remote main、annotated `v1.2.3^{}`、五个 EverAlgo tags、paper 阶段与参数、
  current OME strategy effective meta、typed service/HTTP shared service、patch 成功路径边界。
- official evaluation 回执：调度请求同为 `gpt-5.6-luna / reasoning_effort=max`；子会话只能自报
  generic GPT-5。回执完整覆盖 current LoCoMo、historical LoCoMo/LME 的输入转换、ingest、search、
  answer、judge、parser 与未闭合边界，收据门通过。
- 架构师抽锚通过：current LoCoMo all-user/sender、image-only skip、batch25/flush、single-owner
  agentic top10；historical LME synthetic speaker/session-time、8000-char live truncation、agentic 两轮
  具体候选链、32768 answer payload、first-marker parser，以及 historical judge mean/std 与 current
  majority 的差异。
- 架构师已独立抽锚：paper 三阶段与 Appendix 参数；v1.2.3/current product search paths；framework
  hybrid/no-rerank与 OME template；官方历史 commit和 LME converter存在性。
- 两份回执返回后只补充其覆盖范围，不重复做整份探索；承重冲突以 current source/paper/final
  payload复现裁定。

## 10. 验证记录

- PDF extraction/render：PyPDF 提取；视觉复核 paper pp.5、11、14（算法图、实验参数、agentic trace）。
- official history：按 hash fetch `29d555c…`，确认 parent/date/author；`merge-base --is-ancestor`
  对 current main 返回 false；`5f70b071…` 为 2025-11-05 初次加入三 benchmark evaluation。
- OME effective probe（vendored runtime，零 API）：
  `extract_atomic_facts True Immediate`、`extract_foresight False Immediate`、
  `trigger_profile_clustering True Immediate`、`extract_user_profile True Immediate`、
  `reflect_episodes False Cron`。
- 零 API tests：
  `uv run pytest -q tests/test_everos_adapter.py tests/test_everos_worker.py
  tests/test_everos_registered_prediction.py tests/test_config_profiles.py tests/test_method_registry.py
  tests/test_documentation_standards.py tests/test_codex_project_hooks.py` → `232 passed in 2.56s`。
- `git diff --check`：clean。
- 最终判词：

```text
M9_EVIDENCE_COMPLETE
PAPER_PRODUCT_IMPLEMENTATION_VARIANT
CURRENT_PRODUCT_SOURCE_LOCKED
OFFICIAL_HISTORICAL_LOCOMO_LME_HARNESS_IDENTIFIED
CURRENT_LOCOMO_AUTHOR_BUILDER_READY
HISTORICAL_LME_CODE_READY
PAPER_AUTHOR_REPRO_NOT_READY
FRAMEWORK_HYBRID_PRODUCT_VARIANT_VALID_BUT_NOT_PAPER_COMPLETE
EFFECTIVE_PROFILE_EXTRACTION_GAP
SOURCE_LOCK_SCOPE_REVIEW_REQUIRED
```

## 11. M11-A 实施闭环（2026-08-25）

M9 的 `EFFECTIVE_PROFILE_EXTRACTION_GAP` 已由 current source 与最终对象双重闭合：

- upstream 注释模板不等于关闭；`@offline_strategy(..., enabled=True)` 的默认值使
  `extract_user_profile` 实际开启。第三方这样设计有产品理由：Profile 是通用产品的长期用户画像
  能力；但主表只读 Episodes，继续构建 Profile 会改变状态与成本而不进入 readout，故不属于当前
  controlled estimand。
- adapter v8 在 upstream `default_ome.toml` 上追加唯一显式 override：
  `[strategies.extract_user_profile] enabled=false`。若 upstream 日后显式改成 true，renderer
  fail-fast，不靠重复 TOML table 强盖。
- official lifespan 后，worker 等待 ConfigReloader 生效并从最终 `OfflineEngine._registry` 读取五项
  `StrategyMeta.enabled`：Atomic Facts=true、Foresight=false、Profile clustering=true、Profile
  extraction=false、Reflection=false。文本正确但最终对象未生效同样拒绝启动。
- manifest 写入完整 `ome_strategy_profile`；adapter `v7→v8`、worker protocol `v3→v4`。这是
  build-state 变化，旧 v6/v7 状态只读保留，不得 resume 或重标为 v8。
- 同批纠正 EverOS 最终 LanceDB 检索距离身份为 `lancedb-cosine`；产品 recall builder 明确调用
  `.distance_type("cosine")`，不能因 LanceDB 的无参默认而误记成 L2。

零 API定向门：
`tests/test_everos_adapter.py tests/test_everos_worker.py tests/test_method_registry.py
tests/test_everos_registered_prediction.py tests/test_config_track.py` → `216 passed in 11.90s`。

当前判词：`EFFECTIVE_PROFILE_EXTRACTION_GAP_CLOSED_V8`；source closure 与 embedding artifact
identity 仍由 M11-B 继续处理。
