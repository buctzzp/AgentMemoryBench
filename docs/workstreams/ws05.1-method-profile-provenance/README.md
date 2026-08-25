---
id: ws05.1
parent: ws05
status: done
created: 2026-08-24
---
# ws05.1 十家 method prompt 与参数 provenance

## 恢复胶囊

- **目标**：在扩大 pilot 前，逐家确认主 method 配置保留完整算法机制，并为作者实际跑过的
  benchmark 找到可复现的完整 answer builder、effective 参数与明确 source identity。
- **当前批次**：M0/M0.5、M1-M10 十家证据与 M11 横向实现均已完成。十家 main/source/embedding
  identity 已闭合；没有一格通过完整 `AUTHOR_READY` 门，因此零 author profile 注册。
- **当前判据**：[`spec.md`](spec.md)。参数是否承重只由有效调用语义判定，不按 bool/number
  分类；paper identity、author-reported identity、current product default 与 framework main
  identity 必须分栏，不得揉成一个“官方默认”。
- **禁止事项**：本任务零真实 API、零参数 sweep、零效果调优；不得因为找到模板就宣称完整
  prompt parity，不得把 method 官方 judge 暗换进 benchmark 主表，也不得以非官方 fork 冒充
  author source。
- **调查并行策略**：2026-08-25 起，本支线的 source/paper/harness 只读取证可由架构师主动派发
  `gpt-5.6-luna` / `reasoning_effort=max`；每个回报先作为候选事实，按架构师手册 §4.3 做
  claim-evidence 收据门与承重抽锚。subagent 不实施配置/代码，也不因第三方方案与现行政策不同
  就预设其错误。
- **当前动作**：本支线停止施工并交回父 ws05。用户重新批准预算、规模和 run-id 前不恢复真实
  pilot；后续作者校准按 method×benchmark 逐格新开，不回滚本支线为 in-progress。
- **最近验收**：M11 承重定向门 `469 passed in 12.81s`；最终零 API 全量门
  `2297 passed, 3 deselected, 25 warnings, 29 subtests passed in 269.11s`；`git diff --check`
  干净。九家 controlled MiniLM 的实际本地加载为 384 维 Transformer→Pooling→Normalize；Letta
  embedding=N/A。完整实现与重建收据见
  [`m11-effective-config-source-embedding-implementation.md`](notes/m11-effective-config-source-embedding-implementation.md)。

## 为什么单独立项

2026-08-24 的配置所有权迁移已经把 method 算法参数、API runtime、benchmark evaluation 与
execution 分开，但它没有逐项证明“当前值为什么是这个值”。同时
`src/memory_benchmark/prompts/author/` 只有 LightMem、Mem0、MemoryOS 三家资产，A-Mem 等方法
在独立评测仓库中存在官方 prompt 的可能性尚未系统闭合。若直接扩大 pilot，可能用关闭核心
阶段的产品默认或不完整 builder 生成一批身份错误的结果。

本任务只关闭这道研究身份门，不重做十家 B1-B11，不重跑已经冻结的 smoke，也不借机优化分数。

## 稳定输出与长期读取入口

- 永久政策：[`method-toml-and-answer-builder-policy.md`](../../reference/method-toml-and-answer-builder-policy.md)
- 每家稳定结论：`docs/reference/integration/<method>.md`
- 当前进度与断点：本 README + 父 [`ws05 README`](../ws05-experiment-reporting/README.md)
- 一手长证据：本目录 `notes/<method>-profile-provenance.md`
- 十家对表：[`method-profile-provenance-matrix.md`](notes/method-profile-provenance-matrix.md)；每完成一家立即更新，
  不等十家结束后凭记忆补写。
- 每家统一记录格式：[`method-profile-provenance-note-template.md`](notes/method-profile-provenance-note-template.md)，
  先画算法阶段图再填参数表。
- LightMem M1：[`lightmem-profile-provenance.md`](notes/lightmem-profile-provenance.md)；稳定判词为
  `M1_EVIDENCE_COMPLETE / AUTHOR_NOT_READY / SOURCE_DRIFT_REVIEW_REQUIRED`。
- A-Mem M2：[`amem-profile-provenance.md`](notes/amem-profile-provenance.md)；稳定判词为
  `M2_EVIDENCE_COMPLETE / PRODUCT_SOURCE_RULING_REQUIRED / AUTHOR_NOT_READY`。
- Mem0 M3：[`mem0-profile-provenance.md`](notes/mem0-profile-provenance.md)；稳定判词为
  `M3_EVIDENCE_COMPLETE / PAPER_CURRENT_ALGORITHM_VARIANT / CURRENT_HARNESS_SOURCE_LOCKED /
  AUTHOR_NOT_READY / SOURCE_DRIFT_REVIEW_REQUIRED`。
- MemoryOS M4：[`memoryos-profile-provenance.md`](notes/memoryos-profile-provenance.md)；稳定判词为
  `M4_EVIDENCE_COMPLETE / CURRENT_PRODUCT_SOURCE_LOCKED / EVAL_PRODUCT_IMPLEMENTATION_VARIANT /
  FINAL_MESSAGE_TEMPLATE_PARITY_PASS / AUTHOR_NOT_READY`。
- MemOS M5：[`memos-profile-provenance.md`](notes/memos-profile-provenance.md)；稳定判词为
  `M5_EVIDENCE_COMPLETE / V2_0_25_PRODUCT_SOURCE_LOCKED / PAPER_1031_SOURCE_UNRESOLVED /
  OFFICIAL_LME_HARNESS_BROKEN / OMNIMEMEVAL_BEAM_HALUMEM_EXTENSION_IDENTIFIED / AUTHOR_NOT_READY`。
- SimpleMem M6：[`simplemem-profile-provenance.md`](notes/simplemem-profile-provenance.md)；稳定判词为
  `M6_EVIDENCE_COMPLETE / CURRENT_PRODUCT_SOURCE_LOCKED / PAPER_CURRENT_IMPLEMENTATION_VARIANT /
  FRAMEWORK_SERIAL_MAIN_VALID / PAPER_AUTHOR_SOURCE_UNRESOLVED / AUTHOR_NOT_READY`。
- Letta M7：[`letta-profile-provenance.md`](notes/letta-profile-provenance.md)；稳定判词为
  `M7_EVIDENCE_COMPLETE / LEGACY_V1_ARCHIVE_SOURCE_LOCKED /
  FRAMEWORK_SLEEPTIME_CORE_BLOCK_MAIN_VALID / ARCHIVED_LOCOMO_HARNESS_IDENTIFIED /
  SOURCE_LOCK_SCOPE_REVIEW_REQUIRED / AUTHOR_NOT_READY`。
- LangMem M8：[`langmem-profile-provenance.md`](notes/langmem-profile-provenance.md)；稳定判词为
  `M8_EVIDENCE_COMPLETE / NO_FORMAL_METHOD_PAPER_IN_SEARCH_BOUNDARY /
  CURRENT_PRODUCT_SOURCE_LOCKED / FRAMEWORK_ASYNC_SESSION_MAIN_VALID /
  OFFICIAL_PHASE1_HARNESS_UNAVAILABLE / AUTHOR_NOT_READY`。
- EverOS M9：[`everos-profile-provenance.md`](notes/everos-profile-provenance.md)；稳定判词为
  `M9_EVIDENCE_COMPLETE / CURRENT_PRODUCT_SOURCE_LOCKED /
  OFFICIAL_HISTORICAL_LOCOMO_LME_HARNESS_IDENTIFIED / CURRENT_LOCOMO_AUTHOR_BUILDER_READY /
  HISTORICAL_LME_CODE_READY / PAPER_AUTHOR_REPRO_NOT_READY /
  EFFECTIVE_PROFILE_EXTRACTION_GAP / SOURCE_LOCK_SCOPE_REVIEW_REQUIRED`。
- Graphiti M10：[`graphiti-profile-provenance.md`](notes/graphiti-profile-provenance.md)；稳定判词为
  `M10_EVIDENCE_COMPLETE / GRAPHITI_OSS_COMMIT_IDENTITY_LOCKED /
  RELATED_ZEP_PAPER_AND_HOSTED_IDENTITY_SEPARATED / FRAMEWORK_BASIC_RRF_CONTROLLED_MAIN_VALID /
  OFFICIAL_LME_BUILD_PAYLOAD_ANCHOR_ONLY / OFFICIAL_BUILD_EVAL_JUDGE_CONTRACT_CONFLICT /
  AUTHOR_NOT_READY / SOURCE_LOCK_SCOPE_REVIEW_REQUIRED / MINILM_REVISION_LOCAL_UNPINNED /
  REMOTE_SOURCE_DRIFT_REVIEW_REQUIRED`。
- 第三方框架配置比较：[`third-party-framework-config-strategy-audit.md`](notes/third-party-framework-config-strategy-audit.md)；只深读
  真正同时覆盖多 method/多 benchmark 且暴露有效配置链的框架，避免把整个参考目录机械倾倒。
- 新取得的官方仓库：先核 owner/license/commit，再登记
  `third_party/methods/MANIFEST.md` 与可重放 fetch 入口；孤立 clone 不算项目资产。

## 完成判据

1. 十家各有 current source identity 与官方 benchmark 覆盖清单；找不到也记录搜索边界和
   `SOURCE_UNAVAILABLE`，不虚构。
2. 每个官方 benchmark 的最终 answer messages、变量来源、decode 参数与读取/解析链已闭合，
   或诚实标 pending/unavailable；只找到模板不算完成。
3. method harness 中出现的 judge prompt 已盘点，但是否进入框架由独立 metric tier 裁决；
   benchmark 主 judge 不被暗换。
4. 全部 method-owned 开关/枚举与高影响数值都有 upstream default、paper role、official
   effective value、current main value、调用点、重建影响和裁决。
   每家在参数表之前先完成论文/技术报告算法阶段图与 current source 对应关系；无正式论文时明确
   官方替代材料和证据等级。
5. 主配置跨五 benchmark 固定；作者值只进入显式、稀疏、可运行且可审计的
   `author_<benchmark>`。若 harness 改变双写/namespace/算法拓扑，不能伪装成普通 TOML 覆盖。
6. 配置或 builder 修改通过零 API 定向门、manifest/resume identity 门和最终无 API全量门；
   用户重新批准预算、规模、run_id 前不恢复真实 pilot。

## 决策记录

- 2026-08-24 用户：论文算法图、README 与 method 官方 benchmark 代码是必要证据；缺失的专门
  评测仓库应主动寻找，实在不可得才诚实停在 unavailable。
- 2026-08-24 架构裁决：参数类型不是语义；论文完整算法、作者实际实验与 current product
  默认回答三个不同问题。作者复现用来验证框架 fidelity，跨五格固定主配置用来保证主表公平。
- 2026-08-24 用户：`第三方框架参考/` 如何选择同一 method 的跨 benchmark 配置，是本项目主
  配置设计的重要比较输入，必须列入计划。架构裁决：这些框架可证明一种工程策略如何落地，
  但除非它本身就是 method 官方评测入口，否则不能升级为 author-reported 参数证据。
- 2026-08-24 用户：参数裁决前必须先理解每家 method 的算法机制；优先读匹配版本论文，没有论文
  再查官方技术报告/架构文档。架构裁决：每家 note 先画算法阶段图并追到 current source，再讨论
  开关和数值，不能从 README 参数表或 constructor default 反推完整算法。
- 2026-08-24 架构裁决：YAML 常因嵌套结构、深合并和生态工具被采用，但这不等于配置更公平；
  第三方框架已出现 benchmark override 与隐藏 fallback。当前强类型、浅层 method schema 继续用
  TOML，只有出现真实深层组合需求时才重新评估格式。
- 2026-08-24 LightMem M1：论文完整算法锁定 pre-compress/topic/STM extraction/direct insert；
  current product 的 `extract_threshold` 无消费者，paper `th` 实为 STM capacity。现行 source
  identity 还漏掉若干被 patch 的 product 文件，且 upstream 2026-07-26 已改变
  `topic_segment=false` 行为，因此 source 更新、identity 扩展和 author profile 都留给 M11
  显式实施，不用一份 TOML 注释掩盖版本差异。
- 2026-08-24 A-Mem M2：论文核心是 note construction、candidate retrieval、link generation、
  memory evolution 与 query retrieval；MiniLM 有论文依据，但 GPT-4o-mini LoCoMo 的 author k
  是按类别 `40/40/50/50/40`，不能由 main `retrieve_k=10` 冒充。论文链接的
  `WujiangXu/A-mem-sys` 与 current framework 使用的 `agiresearch/A-mem` 在邻居 id、embedding
  document 与 auto-analysis 上存在算法差异；M11 前只登记，不静默换源。
- 2026-08-25 Mem0 M3：paper 的 summary/recent-context + per-fact
  `ADD/UPDATE/DELETE/NOOP` 与 current 2.0.4 additive/hash/entity pipeline 是算法变体；old
  LoCoMo 双 namespace 是为 user-only hosted v2 保住双方事实的完整 topology，不因不同于主配置
  就判错，也不能压成 TOML bool。current memory-benchmarks source 已锁到 `4b61c5d…`，但其
  runtime branch 不可重建；现行三家 author 文件只是 template parity 资产，统一留 M11 施工。
- 2026-08-25 MemoryOS M4：paper 的 segment-length/recency/keyword 机制、官方 LoCoMo eval 与
  current PyPI product 存在不能由普通参数覆盖的差异。官方固定 speaker→QA-page 与角色扮演
  builder 的目的成立，但 exact harness 跨 session 回填并覆盖 61 个已有 assistant response，另有
  93 个单侧 page 不进 MTM；main 保留真实 turn 的 corrected topology，author 数字复现须另列
  `repo_eval_exact` identity。现行 author helper 只通过最终模板 parity，未闭合变量格式化/parser/
  registry，故仍为 `AUTHOR_NOT_READY`。
- 2026-08-25 MemOS M5：paper `MemOS-1031`、v2.0.25 product、repo内 LoCoMo/LME harness、
  OmniMemEval later extension 与 framework main 是五种可区分身份。官方 LoCoMo 双视角有明确的
  role-direction 目标，main 保留；LME wrapper 的 `reference_time` 路径不可运行；同owner
  OmniMemEval 用统一 client/batch20/top20/prompt 横评 BEAM/HaluMem 的设计服务产品可操作性，
  但未锁 MemOS runtime，且HaluMem只评retrieval+QA，故只记
  `PUBLIC_OFFICIAL_FRAMEWORK_EXTENSION`，不注册paper author profile。current reader真实窗口为
  1024/200，表面1600/10/2是未被concrete reader消费的hidden/dead配置。
- 2026-08-25 SimpleMem M6：论文三阶段是 compression、online semantic synthesis 与
  intent-aware retrieval；current product以 `previous_entries` 条件化新entry生成、固定25/5/5及
  独立reflection实现相近目标，但不与paper formulation逐项等价。official LoCoMo一次
  `add_dialogues()` 可能触发parallel topology；main逐turn串行是为保存窗口因果链，两者分
  identity而不互相判错。锁定text repo没有完整LongMemEval-S runner，category5又把private
  adversarial answer放入回答选项，故当前不注册任何SimpleMem author profile。
- 2026-08-25 Letta M7：MemGPT paper 的 recall/archival/FIFO/heartbeat 与 official SDK
  sleeptime core-block learner是算法变体；main显式embedding None只适用于不写raw passage、
  query-independent block readout。current repo已把V1搬到archive，active Letta Code另分identity；
  official archived leaderboard 的LoCoMo files/search harness改正了“所有official source均无”的旧
  绝对断言，但因dataset/server/search/decode链不完整仍`AUTHOR_NOT_READY`。现行20-file source hash
  漏prompt/tool/compaction等真实消费者，且compaction注释100%与实现90%冲突，统一留M11修锁。
- 2026-08-25 LangMem M8：LangMem 是 composable memory primitives 而非“论文对应一份固定
  benchmark 实现”。main 锁 public async background store manager：session transaction、默认
  `Memory(content)`、insert/update开、delete关、query-model none、query-limit5、steps1、phases空。
  `query_limit` 同时影响写入前 old-memory query windows 与 candidate cap，不能和最终 QA top-k
  混写；conceptual guide 的 importance/strength 是设计指导，不是 current concrete scorer。第三方
  MemoryData 的逐 message/delete-on 设计服务统一 layer API 和逐调用归因，值得借鉴其显式控制面，
  但 effective JSON 又覆盖 schema defaults，且其 session context/estimand 与 main 不同，不能升级为
  author source，也不能因与我们不同而判错。
- 2026-08-25 EverOS M9：paper 的 boundary→Episode/AtomicFact→MemScene→agentic recollection、
  official historical EverCore@29d、v1.2.3 product 与 framework hybrid main 是四种不同 estimand。
  current official LoCoMo 的 single-owner/agentic/Qwen/product `.65/7` 与 paper `.70/7` 不得混成
  一个 author profile；29d LongMemEval 的 synthetic speaker/session time、8000-char truncation、
  shared answer chain 已闭合，但 exact paper source/data/payload 未锁。framework hybrid/no-rerank
  是有效 product-controlled variant，不是 paper-complete。M11-A 已在 adapter v8 显式锁
  profile clustering on / extraction off，并对 official lifespan 后的最终 StrategyMeta 验真；
  algorithm source closure 仍进入 M11-B 修复门。
- 2026-08-25 Graphiti M10：Graphiti OSS、Zep architecture paper 与 Zep hosted experiments 是三个
  不同 source/product identity。framework 的 direct-core + controlled MiniLM + edge BM25/cosine/RRF
  是有效的 OSS controlled main，但不是 hosted nodes+edges/cross-encoder parity；官方 Graphiti
  LongMemEval 文件只验证 build payload/topology，且 `candidate_is_worse` 字段描述、judge prompt 与
  scorer 极性冲突，禁止把其分数当 author quality evidence。当前 source hash 漏 prompts、node/edge
  operations、search recipes 等真实消费者，MiniLM revision 也仍为 local-unpinned，统一进入 M11。
- 2026-08-25 M11 收口（supersedes 上述各条“留 M11”动作，不改写其历史取证）：dead/hidden
  config、EverOS effective strategy、九家本地 MiniLM content identity、Letta N/A、十家组件化
  source closure 与 v1→v2 resume 边界均已关闭；source upgrade/agentic/author topology 没有被
  偷偷夹带。全部 author 格仍未通过完整就绪门，因此零 skeleton。定向门 469 passed，最终零 API
  全量 2297 passed；重建矩阵与 subagent 验收见
  [`m11-effective-config-source-embedding-implementation.md`](notes/m11-effective-config-source-embedding-implementation.md)。
