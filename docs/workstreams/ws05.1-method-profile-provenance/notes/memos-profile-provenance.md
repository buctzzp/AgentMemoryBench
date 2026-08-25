# MemOS profile provenance（M5）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M5 一手证据，不改写成新 run 收据。

> 判词：`M5_EVIDENCE_COMPLETE / V2_0_25_PRODUCT_SOURCE_LOCKED /
> PAPER_1031_SOURCE_UNRESOLVED / OFFICIAL_LOCOMO_TOPOLOGY_PARITY /
> OFFICIAL_LME_HARNESS_BROKEN / OMNIMEMEVAL_BEAM_HALUMEM_EXTENSION_IDENTIFIED /
> AUTHOR_NOT_READY /
> CURRENT_UPSTREAM_DRIFT_REVIEW_REQUIRED`。
>
> 本文把论文、作者公开评测、v2.0.25 current product 与 framework main 四种身份分栏。
> 本批不修改 TOML、adapter、第三方源码或 prompt registry，不调用真实 API，也不把论文的完整
> Memory OS 愿景重标为当前只运行 plaintext/tree-text 路径的产品事实。

## 0. 身份与范围

- method：MemOS（MemTensor/MemOS；不是 BAI-LAB/MemoryOS）。
- 审计日期：2026-08-25。
- paper：`MemOS: A Memory OS for AI System`，arXiv `2507.03724v4`（2025-12-03）。本机
  `third_party/methods/MemOS/MemOS.pdf` 共 37 页、4,753,104 bytes，SHA-256=
  `9b9b71b61487ce9f01d2de014b80201d9a30c4fd43effa33e84ef7d2db824977`。该 PDF 被 Git
  ignore，属于 local-only 阅读证据，不在 fetch 恢复合同内。
- framework product source：`MemTensor/MemOS@v2.0.25/e820406269537b97d270687e3e40eea2f015f81a`
  （Apache-2.0）+ 可重放
  `scripts/patches/memos-product-runtime-observability.patch`。
- framework source identity：product 17-file=
  `a436c8e48e85a7b8425895cc44971bef169949e7942a45366b3811ff85111ed3`；patch=
  `69c564ef3ecee1d629ee534865f55b9e88be2c3bd0e65c0b6ffddeb43769f595`；product+patch+
  wrapper=`a1c71f357bceead95a767bcd501566d312d562a4035731f1e532387603fdea8d`。
- official evaluation：同一 v2.0.25 仓库的 `evaluation/scripts/`；Phase 1 的 LoCoMo/LME 13-file
  length-delimited identity=
  `759b02d106a54a8089f4f29d944635776436ae3908b53daf4f203ab78b38493f`。
- later official framework extension：同一 MemTensor owner 的 `MemTensor/OmniMemEval`，本地锁
  `0b1ea8d28aa2d3e03ac4a6aee17b3006a131da7d`；BEAM/HaluMem 首次共同加入于
  `9e1ea9ebe601afc75fe5bc7cd50a4cedbcd689a5`（2026-07-01）。它同时支持 MemOS cloud 与
  self-host product HTTP，但没有锁实际 MemOS server/source/config，故只能证明“官方团队后来如何
  横向评测产品”，不能证明 v2.0.25 或 paper `MemOS-1031` 的作者复现身份。
- current upstream：2026-08-25 `main=9119efe5554e61a94b669df5eb84cc1b8ef3c0ab`，最新 package
  release 为 v2.0.31（版本提交 `e1380b84…`）。framework 继续锁 v2.0.25；不得用 current-main
  默认倒推论文或静默替换已有实验身份。
- paper experiment identity：表格只写 `MemOS-1031`，并说明共同使用 GPT-4o-mini、按 validation
  选择配置；公开材料没有把 `1031` 映射到可重放 commit/server env。2025-10-31 附近的 repo
  commit 只能是日期候选，不是 source lock，故记 `PAPER_1031_SOURCE_UNRESOLVED`。
- 本次不覆盖：真实数据库/API、论文效果复现、参数 sweep、current-upstream upgrade、HaluMem/
  BEAM/MemBench 调优、author profile 注册或 method judge 进入主表。OmniMemEval 只作公开 official
  framework extension 取证，不把它的通用 benchmark prompt 误标为 MemOS 论文专属 prompt。

## 1. 算法机制先行

### 1.1 论文阶段图

| 阶段 | 输入 | 状态/输出 | 是否可选 | 一手出处 |
| --- | --- | --- | --- | --- |
| Memory Interface / MemReader | 原始 interaction、文件或多模态观察 | 结构化 MemoryCall、类型/时间/entity/context anchor | 核心 | paper §5.1-§5.3 |
| MemCube / storage | plaintext、activation、parameter memory | 带 payload、metadata、provenance/version/governance 的统一容器 | 核心 | paper §5.1-§5.2 |
| MemOperator | 新旧 memory、query/context | tag、merge、activation、graph/hierarchy、跨类型操作 | 核心 | paper §5.2、§5.4 |
| MemScheduler | operation/task/state | 调度、依赖、资源与跨类型迁移 | 核心 | paper §5.2、§5.4 |
| MemLifecycle | generated/activated/merged/archived/expired/frozen 等状态 | 生命周期、归档、版本与回滚 | 核心愿景；状态枚举正文有冲突 | paper §5.2、§5.4.3 |
| Governance / Vault / Loader / Dumper / Store | memory 资产与权限/版本 | 治理、加载、导出、存储抽象 | 系统层核心 | paper §5.1、§5.5 |

论文是三类 memory 的 OS 架构，不是“调用一次向量库”。但论文同一版本对 lifecycle 状态数有
不同描述，因此本文只记录明确出现的状态，不伪造唯一枚举。

### 1.2 v2.0.25 current product 与 framework main

```text
canonical SessionBatch
  -> APIADDRequest(async_mode="async", mode=None)
  -> AddHandler / SingleCubeView
  -> fast plaintext memory write
  -> local scheduler MEM_READ task
  -> MultiModalStructMemReader fine LLM extraction
  -> fine graph/vector write -> raw cleanup/archive -> refresh
  -> exact business-task terminal

RetrievalQuery
  -> APISearchRequest(fast, top_k=query.top_k, relativity=.45,
                      dedup=mmr, rerank=true, optional memories=false)
  -> SearchHandler -> graph/vector recall -> product rerank/MMR/filter/formatter
  -> adapter consumes text_mem -> framework answer builder
```

| paper 阶段 | current module/function | framework main | 版本/语义边界 | 判词 |
| --- | --- | --- | --- | --- |
| MemReader | `MultiModalStructMemReader` | multimodal_struct，但主输入为 canonical text/image-caption messages | current product 的 concrete reader；不是论文完整多模态实验身份 | `CURRENT_PRODUCT` |
| Plaintext generation | `SingleCubeView._process_text_mem` + tree-text memory | async add 先 fast 后 MEM_READ fine | `APIADDRequest.mode` 在 async 下被清空；不能用它选择 fine | `CORE_ACTIVE` |
| Scheduler/lifecycle | local queue、dispatcher、`MemReadMessageHandler` | scheduler on、parallel dispatch on、逐 task 等 terminal | product 内部并行不等于 framework conversation workers | `CORE_ACTIVE` |
| Graph/vector storage | Neo4j community + nested Qdrant | controlled MiniLM/384/cosine | 改 identity 必须 fresh rebuild | `CORE_ACTIVE` |
| Activation/parameter/preference | product config surface | main 全部关闭 | 当前 adapter 只声明 plaintext/tree-text 子集；不能宣称论文三类 memory 全开 | `DORMANT_VARIANT` |
| Reorganize | tree manager/scheduler | false | graph/vector 写入仍存在；额外 reorganize task 不提交 | `OPTIONAL_OFF` |
| Search/rerank | `Searcher`、SearchHandler、formatter | fast + cosine_local + MMR + relativity | internal rerank active，但 final formatter 对 knowledge memory 按 relativity 排序 | `ACTIVE_WITH_FINAL_OVERRIDE` |
| Answer | product chat 可生成 answer | framework 只取 memory，由 benchmark builder 答题 | 隔离 memory quality；author builder 只能作补充校准 | `FRAMEWORK_READOUT_BOUNDARY` |

### 1.3 两个容易误判的 hidden config

1. `APIConfig.get_reader_config()` 暴露 `chunk_length=1600 / chunk_session=10 /
   chunk_overlap=2`，并作为 `chat_chunker` 进入 reader config；但 current
   `MultiModalStructMemReader._process_multi_modal_data()` 调用自己覆写的
   `_concat_multi_modal_memories()`，真实窗口来自 `chat_window_max_tokens` 缺省 1024 和函数默认
   overlap 200。`1600/10/2` 是 StrategyStruct/旧路径参数，不是 current main 的有效窗口。
2. `TreeTextMemory.config.mode` 默认 `sync` 与请求 `APIADDRequest.async_mode="async"` 是两个不同
   轴。前者影响 memory manager 的内部 cleanup 方式，后者决定 fast 写入及 scheduler fine task；
   不能把二者都缩写成一个“async=true”。

## 2. 官方 benchmark 覆盖

| benchmark | 论文报告 | 公开 harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | 是；表中系统为 MemOS-1031 | `evaluation/scripts/locomo/*` | vendored `locomo10.json`；恢复身份需另锁 data hash | 双 namespace、正反 role、每路 positional batch=2、双路各 top-20 | `PUBLIC_IMPLEMENTATION_VARIANT` |
| LongMemEval | 是 | `evaluation/scripts/longmemeval/*` | `longmemeval_s.json`，文件不随 repo 完整恢复 | 每题 namespace、session 保序、每条截 8000 chars、positional batch=2 | `PUBLIC_BUT_BROKEN` |
| HaluMem | 否 | `OmniMemEval/scripts/halumem/*` | Medium/Long，本地 framework data | user namespace；每 session 原 role/order、统一 session end/start time；MemOS client 默认 batch=20；top-20 | `PUBLIC_OFFICIAL_FRAMEWORK_EXTENSION` |
| BEAM | 否 | `OmniMemEval/scripts/beam/*` | 100k/500k/1m/10m，本地 framework data | conversation namespace；每 session 原 role/order，时间取首 message anchor；MemOS client 默认 batch=20；top-20 | `PUBLIC_OFFICIAL_FRAMEWORK_EXTENSION` |
| MemBench | 否 | 无 | N/A | framework extension | `SOURCE_UNAVAILABLE` |

论文另报告 PrefEval 与 PersonaMem；它们不在 Phase 1。官方 LoCoMo/LME harness 到 current upstream
main 仍逐字一致，但这只锁住 wrapper，不等于论文 `MemOS-1031` 的 server/runtime 参数已公开。

### 2.3 OmniMemEval：为什么它值得参考、又不能直接叫 author parity

OmniMemEval 的目标是用同一套 `ingest → search → answer → judge → report` 流水线横向比较许多
memory product，因此把 method client 收敛成 `add(messages,user_id,conv_id)` 与
`search(query,user_id,top_k)`，benchmark 统一使用 workers=2、LLM workers=10、top-k=20、judge
runs=1。对 MemOS self-host，它最终发送 `/product/add` 与 `/product/search`；add payload 包含
`user_id == mem_cube_id`、`writable_cube_ids`、可选 `session_id/conversation_id` 与
`MEMOS_ASYNC_MODE`，search 默认 preference=true/pref-top-k=6、fast、context-format=memory，
tool/skill=false。这个设计的合理目标是**产品横向可操作性与统一流水线**，不是论文数字复现。

runner 以 session 调用 `add()`，client 再按最多 20 messages / 40,000 chars 切请求；BEAM 与
HaluMem 都只保留 role/content，并给本 session 每条 message 注入同一个 `chat_time`，image 与
HaluMem memory-point metadata 不进入 MemOS。generic search 最终把 memory拼成一个 context字符串，
不保留结构化 rank/provenance。当前 `.env.memos` 模板走 cloud、async=true、preference=true/9、
relativity=0、context=mixed；这些又与 local client defaults及framework main不同，必须分开记录。

其代价也必须保留：

- client 默认 `MEMOS_MODE=cloud`；local 默认 `async_mode="sync"`，与 framework main 的 typed-handler
  async fast→fine 不同；若把 cloud 模板的 `MEMOS_ASYNC_MODE=true` 原样复制给 local，client会在
  add 前 fail-fast；
- 通用 runner 虽暴露 `--wait-after-ingest`，默认 0 秒，没有 v2.0.25 business-task exact terminal
  门，不能证明 async fine 已完成；
- batch=20、preference=true 与统一 benchmark prompt 都是 framework-level effective policy，不能
  反推 `MemOS-1031`；
- HaluMem 这条 later extension 只评 **retrieval + QA**：answer 后计算 LLM judge、lexical/semantic、
  question category/difficulty；没有 HaluMem 原始 extraction、update、memory-type 评测。因此它不能
  改判 framework 当前四格的资格。

### 2.1 LoCoMo：为什么官方双视角设计合理

官方把 speaker A/B 分成两个 user/cube namespace，并对同一 utterance 做正反 role 映射：A 视角
`A=user/B=assistant`，B 视角反转；每个 session 的全部消息使用同一 ISO time，每路 positional
`batch_size=2`，奇数尾 singleton。检索时每路独立 top-20，再按真实 speaker 放入两个槽位，**不做
跨路 global rank**。

它的目标不是无意义复制，而是对冲产品对 user/assistant 语义的方向敏感，让两位真实 speaker 都有
一个以自己为 user 的 memory view。framework 已保留这项 topology；差异是主表关闭 preference、
按 query metric top-k 运行，并通过 typed handler 而非 HTTP host。故：

- ingestion/readout topology 可称 `OFFICIAL_TOPOLOGY_PARITY`；
- 不能由此宣称论文参数或最终分数 parity；
- 单 namespace 的“更简洁”方案反而会改变官方 estimand。

### 2.2 LongMemEval：公开 wrapper 与主表目标不同

官方 wrapper 保留 raw role/order，但把每条 content 截成 `[:8000]`，按位置每两条调用一次 add，
并对单 session ingest 异常 catch 后继续。search 想传 `reference_time=question_date`，而同一仓库
`MemosApiClient.search(query, user_id, top_k)` 不接收该参数；current公开路径会在真正 HTTP 请求前
抛 `TypeError`。因此它不是一个可直接运行的 author identity。

framework main 保留完整 session、原始 role/顺序/content，由产品 reader 自己切窗；不吞 session
失败，也不声称 question-time filter。这个选择优化的是跨 benchmark 的 lossless controlled
estimand；官方 `batch=2 + 8000-char truncation` 优化的是作者 wrapper 的固定输入/成本。两者都有
可解释目标，但必须分 identity，不能把差异简化成“谁对谁错”。

## 3. Prompt / judge 合同

### 3.1 LoCoMo author asset

- template：`evaluation/scripts/locomo/prompts.py::ANSWER_PROMPT_MEMOS`。
- 变量：公开 `context`（双路 search 形成的两个 speaker memory 槽）与 public `question`。
- final messages：**一条 system message**，content 为完整 formatted prompt；没有 user message。
- decode：`model=os.getenv("CHAT_MODEL")`，`temperature=0`；未显式发送 max_tokens/top_p/
  response_format/reasoning。
- parser：直接取 `response.choices[0].message.content or ""`，不解析 `ANSWER:`/JSON。
- 特殊路由：category 5 在 answer 阶段被过滤；gold/evidence 不进入 method/answer。
- method judge：`locomo_eval.py` 另用 system+user JSON judge，默认 run 3 次；它是 method harness
  自带 metric 资产，不能暗换 benchmark 主 judge。
- current status：模板与最终消息链可复刻，但完整 author profile 还缺 MemOS-1031 runtime/effective
  config、preference-enabled search 与 source identity，故 `AUTHOR_NOT_READY`。

### 3.2 LongMemEval author asset

- template：`evaluation/scripts/utils/prompts.py::LME_ANSWER_PROMPT`。
- 变量：公开 search context、`question_date`、question；gold/answer session 只进入 evaluation。
- final messages：**一条 system message**；无 user message。
- decode：`model=os.getenv("CHAT_MODEL")`、`temperature=0`；未显式 max_tokens/top_p/parser。
- parser：直接取 content；无 `ANSWER:`/JSON parser。
- judge：system+user，model 固定 `gpt-4o-mini`、temperature=0，期望 JSON `label`；脚本还计算
  ROUGE/BLEU/METEOR/semantic/BERTScore。这些是 author harness 资产，不自动成为主表 metric。
- current status：search 在 `reference_time` 签名处先报错，且完整 effective product config 未公开，
  故 `PUBLIC_HARNESS_BROKEN / AUTHOR_NOT_READY`。

### 3.3 OmniMemEval BEAM/HaluMem official extension

- 两格 answer 都由 benchmark 共享 `scripts/utils/prompts.py` 构造；最终 messages 均为**一条 user
  message**，`temperature=0`，未显式发送 max-tokens/top-p/response-format/reasoning，直接消费
  response content，不做 `ANSWER:`/JSON parser。
- BEAM judge：system=`You are a precise and fair evaluation judge.` + user rubric prompt；普通维度逐
  rubric item 解析 `score` 并离散为 `1/0.5/0`，event-ordering 另用 positions JSON 计算
  Kendall tau-b × coverage。
- HaluMem judge：共享 grader system + user prompt，解析 JSON `label`；报告另算 F1、ROUGE-1/2/L、
  BLEU-1..4、METEOR、BERT-F1、similarity，并按六种 question category 与 difficulty 聚合。
- 这些 prompt/judge 是 `OmniMemEval@0b1ea8d…` 的 benchmark-level public asset，不是
  v2.0.25 `evaluation/` 或 paper `MemOS-1031` 专属资产。可作为本项目 benchmark prompt 的一手
  对照，但不能据此注册 `author_beam`/`author_halumem` MemOS profile。

## 4. 参数矩阵

| parameter path | upstream default | paper/official role | official effective | current main | 最终 call site | 分类 / rebuild | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| product/source | latest product 漂移中 | paper=`MemOS-1031` | source unresolved | v2.0.25+patch | registry/source identity | topology；全量重建 | 锁 v2.0.25，升级另审 |
| memory backend | tree_text | paper覆盖 plaintext/activation/parameter | 未完整披露 | tree_text | GeneralMemCube→TreeText | core；全量重建 | current-product subset |
| reader backend | multimodal_struct | MemReader 为论文核心 | harness 沿 server effective env | multimodal_struct | factory→reader | core；全量重建 | main confirmed |
| request async/mode | async / None | scheduler/lifecycle 核心 | HTTP client未显式，server默认 | async / None | APIADDRequest→SingleCubeView | core；全量重建 | main confirmed |
| scheduler enable | product env默认 false | MemScheduler 核心 | server env未公开 | true | init_server | core compatibility | main 必须 true |
| internal parallel | true；pool50 | 无论文数值 | env未公开 | true | dispatcher | runtime/ordering | 保留产品默认 |
| framework workers | N/A | N/A | shell workers=10 | 1 | runner capability | execution | 与产品线程池分离 |
| redis queue | false | 未披露 | 未披露 | false | scheduler queue | runtime/恢复 | local main |
| reorganize | false | graph/hierarchy 属论文机制 | 未披露 | false | MemoryManager | optional core；重建 | product-default main |
| chat window | 实际 1024 tokens / overlap200 | 论文未披露 | server env表面1600/10/2但该 reader不消费 | 实际1024/200 | `_concat_multi_modal_memories` | core；重建 | hidden effective value |
| doc chunker | 512 / 128 | 未披露 | 未披露 | 512/128 | sentence chunker | file/oversize path；重建 | source-locked internal |
| build/reader LLM | gpt-4o-mini；top-level .8/8000/.9/50，reader .6/8000/.95/20 | paper共同用 GPT-4o-mini | MemOS-1031完整 decode未公开 | runtime模型注入，双 client decode沿 product | APIConfig→LLMFactory | build；全量重建 | manifest 要分 client role |
| embedding backend | Ollama/nomic | 论文未公开 | 未公开 | sentence_transformer | EmbedderFactory | build；全量重建 | controlled main |
| embedding model | sentence seam默认 MiniLM | 未公开 | 未公开 | local all-MiniLM-L6-v2 | reader/tree/search/MMR | build；全量重建 | model revision等仍缺口 |
| embedding dimension | graph/vector默认1024；ST本身忽略显式 dims | 未公开 | 未公开 | Qdrant/Neo4j=384；模型实维度校验后为384 | graph config + ST model | build；全量重建 | 不能说 ST 由字段裁维 |
| embedding max tokens | base 8192；API seam省略时显式 None | 未公开 | 未公开 | 8192 | BaseEmbedder truncation | build；全量重建 | main controlled |
| reranker backend | http_bge | 未公开 | 未公开 | cosine_local | Searcher | retrieval | controlled main |
| search mode | fast | hybrid retrieval愿景 | fast | fast | APISearchRequest | retrieval | main/official一致 |
| request top-k | 10 | paper只给 ablation，不给唯一 final值 | v2.0.25 shell与OmniMemEval通用 runner均为20 | query.top_k | SearchHandler | retrieval | 来源目标不同；不得压成paper唯一值 |
| official-eval add batch | current product client可变 | paper未给唯一值 | v2.0.25 LoCoMo/LME positional batch=2；Omni MemOS client默认20 | 普通四格完整session；LoCoMo双视角batch=2 | reader输入 | topology/build；全量重建 | batching改变reader上下文，不能静默统一 |
| relativity | .45 | 未公开 | client未显式，server default .45 | .45 | filter | retrieval | product-default main |
| dedup/rerank | mmr/true | 未公开 | client未显式 | mmr/true | Searcher+SearchHandler | retrieval | active；stable ranking pending |
| preference | API默认 true | heterogeneous memory愿景 | official true, pref_top_k6 | false | SearchHandler | topology/readout | official/main variant |
| tool/skill/internet/neighbor | tool/skill默认 true，其余 false | broader OS能力 | harness未闭合 | 全 false | SearchHandler | topology/readout | controlled main |
| reference_time | schema字段 | temporal memory愿景 | LME wrapper尝试传入 | 传入但 v2.0.25未消费 | APISearchRequest only | dead/unwired | artifact显式声明 |
| lifecycle version switch | off | paper强调 version/governance | 未公开 | off | reader config | dormant | 不宣称论文 parity |

论文 Figure 9 报告 top-k 与 memory-token/chunk 变化的 ablation，但没有给公开 source 对应的唯一 final
profile；不能从图中“挑一个最好值”写入 main/author。

## 5. 配置流与强反例

```text
configs/methods/memos.toml
  -> MemOSConfig（算法）+ runtime/execution composition
  -> _memos_environment()
  -> APIConfig / GeneralMemCubeConfig / MOSConfig
  -> init_server()
  -> HandlerDependencies.from_init_server()
  -> AddHandler + SearchHandler（同一 scheduler/cube/tracker）
  -> APIADDRequest / APISearchRequest final payload
```

- unknown/type/range：adapter 在 API 前拒绝未知 backend、非正 dimension/token/timeout、越界
  relativity、非 async/非 fast、错误 flags 与 workers≠1。
- active mutation：关闭 scheduler 会使 async fine 没有可信完成门；改变 reader/backend/window/
  embedding 会改变 memory；改变 mode/top-k/relativity/dedup/rerank/flags 会改变 retrieval。
- hidden/dead：`MEM_READER_CHAT_CHUNK_*` 对当前 MultiModal chat window 无效；`reference_time`
  v2.0.25 未消费；async 下 request `mode` 被清空；Omni 的 `MEMOS_CUSTOM_INSTRUCTIONS` 只有定义、
  没有 MemOS 调用点；不得因为字段出现在 schema/manifest 就称 active。
- rerank 不是 dead：Searcher 内部会执行 cosine rerank；但 knowledge formatter 忽略传入 reranker并按
  `metadata.relativity` 再排序，故最终 stable ranking 仍 pending。
- embedding：受控 MiniLM 被 reader、tree/searcher 和 MMR 缺失 embedding 补算真实消费；但现行
  manifest 还缺 model revision/hash、tokenizer、normalization、instruction，M11 必须补齐。
- source patch：只传播失败、暴露原有 sentence-transformer seam、补观测/兼容；成功 memory 算法
  未改。patch/source hash 必须共同进入 resume identity。

## 6. 主配置与作者配置裁决

- framework main：继续 v2.0.25 typed product、plaintext/tree-text、async fast→fine、controlled
  MiniLM、fast/MMR/.45/cosine-local、可选 memory 全关、benchmark builder。它回答“同一公开产品子集
  跨五 benchmark 的 controlled 表现”。
- `author_locomo`：官方 dual namespace/role/batching topology 已进入 adapter；完整 author profile
  仍需 preference=true/pref6/top20、system-only builder、judge inventory 与可重放 MemOS-1031/runtime
  身份。未闭合前不注册。
- `author_longmemeval`：必须先裁定并修复/忠实记录 `reference_time` TypeError；8000-char truncation、
  batch2、吞 session 异常都属于 exact-wrapper identity，不能暗进 main。
- OmniMemEval BEAM/HaluMem：保留为 `official_framework_extension` 对照身份。它说明官方团队接受
  通过公共 product client 横向扩展 benchmark，但其 batch20、preference与统一 prompt服务于另一个
  estimand，不转成 MemOS `author_*` profile，也不取代本项目 HaluMem 四格 evaluator。
- product-default 补充身份：Ollama embedding、HTTP BGE、API默认 optional-memory flags 与 current
  product LLM decode。它可用于产品研究，但不是论文或主表身份。
- topology variants：论文三类 memory 全开、当前 product plaintext 子集、官方 LoCoMo双视角、
  official LME wrapper、framework lossless main 是不同 estimand；不能只用 TOML 名称抹平。
- 禁止配置化：内部线程池/批次和 source-locked prompt常量除非一手证据要求调节，否则不为“齐全”
  暴露；runtime credential/timeout/workers仍留独立配置根。

## 7. Manifest / resume / artifact

- build identity：source/tag/patch/wrapper、reader/backend、async/scheduler/reorganize、完整 LLM client
  roles+decode、embedding全身份、window、graph/vector backend与维度、optional memory flags。
- retrieval identity：source、mode、request top-k、MMR expansion、relativity、dedup、rerank/backend、
  preference/tool/skill/internet/neighbor、dual-view strategy与reference-time effect。
- 任一 build 字段变化必须 fresh namespace/graph/Qdrant 重建；只改变 readout参数可复用 memory，但必须
  生成新的 retrieval/answer artifact identity。
- 旧 artifact 永久按原 manifest 回读，不把 v2.0.25 state 重标成 current main/v2.0.31，也不把
  ox-alpha smoke 与 GPT-4o-mini official 直接比较。
- secret：Neo4j/Qdrant/OpenAI credential只读 env，artifact只存变量名/provider/base-url identity
  的非secret部分；gold/evidence/answer session ids不得到 method。

## 8. 未闭合项与 M11 最小施工

| item | status | 已查范围 | M11 动作 |
| --- | --- | --- | --- |
| MemOS-1031 exact source/env | `UNRESOLVED` | paper、v2.0.25 harness、repo历史 | 找公开 artifact/release；找不到则永久不可复现 |
| author LoCoMo | `AUTHOR_NOT_READY` | topology、search、final message、judge已闭合 | 实现完整 builder/profile/manifest，不只复制模板 |
| author LME | `BROKEN/NOT_READY` | ingest/search/answer/judge已闭合 | 对 reference_time mismatch做显式 implementation ruling |
| Omni BEAM/HaluMem extension | `IDENTIFIED/NOT_AUTHOR` | client final payload、ingest/search/answer/judge/report已闭合 | 只作公开横评设计对照；不注册 paper author profile |
| current upstream upgrade | `PENDING` | main 9119efe、v2.0.31 与 relevant diff 已盘点 | 独立 source-upgrade gate，不混入 profile 实施 |
| chat-window config | `HIDDEN_EFFECTIVE_VALUE` | factory→reader→覆写路径已闭合 | 删除/改名 dead 1600/10/2 声明，显式锁 1024/200 |
| embedding identity | `INCOMPLETE` | model/dim/distance/tokenizer消费链 | 补 revision/hash/normalization/instruction/tokenizer |
| dual LLM clients | `INCOMPLETE_IDENTITY` | top-level与reader decode已闭合 | manifest按 client role记录完整 payload |
| semantic provenance/stable ranking | `PENDING/N/A` | generated window memory与final排序链 | 不因 sources lineage伪造Recall；保持资格判词 |

M11 只做上述可证实的身份/配置迁移，不参数调优、不升级 source、不把论文所有能力强行打开。尤其
不能为了“完整算法”打开 activation/parameter memory：当前 Phase 1 adapter与 metric没有证明这条
产品路径可比、可观测或可恢复。

## 9. 验证记录

- source：nested `HEAD=e820406…`、exact tag `v2.0.25`；dirty files恰为可重放 patch覆盖面。
- upstream：fresh current `HEAD=9119efe…`；v2.0.25→current 的 LoCoMo/LME harness逐字一致，relevant
  product source存在 release drift，故只登记、不升级。
- later official framework：OmniMemEval current `0b1ea8d…`，BEAM/HaluMem initial add
  `9e1ea9e…`；架构师抽查 client、ingest、answer、judge与metric最终调用，确认 HaluMem仅QA而非
  原始四格。该 source 不声明 MemOS server commit，故没有升级为paper/runtime identity。
- later official framework 精确锚点：
  `scripts/client_factory/memos_client.py:13-49,113-158,160-302` 锁 cloud/local endpoint、add
  payload、search flags与字符串化 readout；`scripts/beam/beam_ingestion.py:24-99,128-177` 与
  `scripts/halumem/hm_ingestion.py:29-105` 锁 session级调用、client二次分批、role/content与统一
  `chat_time`；`scripts/beam/beam_responses.py:34-43`、`scripts/halumem/hm_responses.py:30-42`
  锁最终 answer request；`scripts/beam/beam_eval.py:26-68,104-156` 锁 rubric与event-ordering
  judge；`scripts/halumem/hm_eval.py:39-69`、`scripts/halumem/hm_metric.py:16-23,175-240`
  锁 HaluMem JSON judge、六类 QA与difficulty汇总。这里的路径均相对本地
  `第三方框架参考/OmniMemEval@0b1ea8d…`。
- paper：本地 SHA/metadata与 arXiv v4 一致；论文机制按正文而非 constructor defaults重建。
- subagent 验收：paper/product Luna-max 调查仅作为候选事实；架构师独立抽锚 source identity、
  reader有效窗口、embedding维度语义、typed-handler config、官方拓扑与prompt final messages。
  调查中“1600/10/2 vs 1024/200”的冲突已沿 factory→concrete reader消解为后者有效。
- 零 API回归与文档门：
  `uv run pytest -q tests/test_memos_adapter.py tests/test_memos_registered_prediction.py
  tests/test_memos_lifecycle.py tests/test_config_profiles.py tests/test_method_registry.py
  tests/test_documentation_standards.py tests/test_codex_project_hooks.py` →
  `336 passed, 12 warnings in 12.93s`；warning 均来自 vendored MemOS 的
  `datetime.utcnow()` deprecation 与既有 Pydantic serialization warning。
- 架构验收：`M5_EVIDENCE_COMPLETE`；作者校准和current upgrade均未解锁。
