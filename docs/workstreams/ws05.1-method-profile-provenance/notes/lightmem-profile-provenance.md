# LightMem profile provenance（M1）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M1 一手证据，不改写成新 run 收据。

> **架构判词（2026-08-24）**：LightMem 主算法必须保留预压缩、主题切分、STM
> 聚合抽取和 LTM direct insert 四段；现行主配置的 `pre_compress=true`、
> `topic_segment=true`、`compression_rate=0.7`、`stm_threshold=512` 与论文完整机制一致。
> 但 `extract_threshold` 是 current product 的 dead config，`stm_threshold` 也尚未真正从
> framework config 传入产品。LoCoMo/LongMemEval 作者 answer 资产存在，但参数多行、
> decode 差异和 current-source 漂移尚未闭合，因此本批不创建 `author_*` profile，判为
> `M1_EVIDENCE_COMPLETE / AUTHOR_NOT_READY / SOURCE_DRIFT_REVIEW_REQUIRED`。

## 0. 身份与范围

- method：LightMem。
- 审计日期：2026-08-24。
- paper identity：*LightMem: Lightweight and Efficient Memory-Augmented Generation*，
  arXiv:2510.18866v4，ICLR 2026，24 页；本地 PDF
  `third_party/methods/LightMem/lightmem.pdf`，SHA-256
  `7e9a8e9f39c616528d543ce8520606d47d56032eb004b55d452d0dce5725c23e`。
- paper 一手入口：<https://arxiv.org/abs/2510.18866>；arXiv 显示 v4 于 2026-02-28
  修订。
- official product/evaluation repo：<https://github.com/zjunlp/LightMem>，MIT。
- 审计时 upstream `main`：
  [`b4ef1dd289880d4e7ecb88c503e2d51bb9ffdfaf`](https://github.com/zjunlp/LightMem/commit/b4ef1dd289880d4e7ecb88c503e2d51bb9ffdfaf)
  （2026-08-21）。
- 本仓库 initial import 的 core/eval 基线：九个承重文件与 upstream
  [`02e675b1ee68808eac3c895017df4a7a69b3363d`](https://github.com/zjunlp/LightMem/commit/02e675b1ee68808eac3c895017df4a7a69b3363d)
  逐字一致；随后本项目为 lineage、缺失 timestamp、hybrid role 和 forced flush 追加了可追
  commits `058428d`、`915f73c`、`3968373`、`d86b22a`、`8879af9` 等。
- current vendored 8-file identity：
  `a44d7d99790496337270058d71f38737375ff4b2763495ed2b02baa43698d7e5`。
- 同一 8-file 算法在审计时 upstream main 的 identity：
  `c92016a810447b418341a280085f7df3739c87b7153a9ef5620845c65f9b0b5d`。
- 本次覆盖：论文机制、current source、LoCoMo/LongMemEval 官方 ingest/retrieve/answer/judge、
  current main 参数与 author-profile 可运行性。
- 本次不覆盖：真实 API、效果复现、参数 sweep、把 StructMem/EM²Mem 混入 LightMem 主身份、
  立即升级 vendored source 或修改 TOML/adapter。

## 1. 算法机制先行

### 1.1 论文阶段图

| 阶段 | 输入 | 状态/输出 | 是否可选 | 一手出处 |
| --- | --- | --- | --- | --- |
| incremental turn feeding | 原始 `user/model` turn | 一次一 turn 进入 memory construction | 论文实验固定，不是 session 一次灌入 | paper §5.1 |
| Light1 pre-compress | 原始 message tokens | LLMLingua-2 保留率 `r` 后的压缩消息 | 论文完整流程与全部实验均启用 | paper §3.1、§5.1、Table 4/5 |
| Light1 topic segmentation | 压缩后的 user sentences | `{topic, message turns}`；用 LLMLingua-2 attention 候选边界 + MiniLM 相邻语义相似度 | 论文完整流程固定；实现为了产品易用性暴露开关 | paper §3.1、Appendix C.1 |
| Light2 STM aggregation | topic segments | token 累积到阈值 `th` 后形成一次 extraction batch | 阈值是承重超参数，不是可关闭的装饰 | paper §3.2、§4、Tables 2/3/8/9 |
| Light2 LLM extraction/summary | STM batch | `{topic, summary, user, model}` memory entries + summary embedding | 论文完整流程固定 | paper §3.2、Table 4/5 |
| Light3 soft update | 新 memory entry | 在线 test-time 直接插入 LTM | 论文 online-soft 行固定 | paper §3.3 |
| Light3 sleep-time update | 全库 entries | timestamp 约束的近邻 update queue；并行 add/delete/update/merge | 论文 offline 行/LoCoMo headline 使用；与 online-soft 是不同结果身份 | paper §3.3、Tables 2/3 |
| retrieval/usage | question | cosine top-k memories → answer model | memory 评测必需；论文把 chat/retrieve 视为跨方法固定消费面 | paper §2.1、§5.1、Table 5 |

承重解释：论文 §5.1 明说全部实验都使用 LLMLingua-2 预压缩；Appendix C.1 还规定
segmentation 只读 user sentences、压缩成空时保留原文、超 512 时反复以 0.5 压缩、注意力取
8–11 层。因而 `pre_compress=false` 或 `topic_segment=false` 不是“沿 repo default”，而是关闭
论文命名阶段。`messages_use=hybrid` 则属于框架对五格 role-completeness 的显式扩展；它不会把
segmentation 改成 assistant-anchored，topic boundary 仍沿 user 侧形成。

### 1.2 current source 对应关系

| 论文阶段 | current module/function | 控制参数 | 版本漂移/缺失 | 判词 |
| --- | --- | --- | --- | --- |
| normalize/time | `MessageNormalizer.normalize_messages()` | adapter `missing_timestamp_policy` | upstream 不接受显式 `None`；本项目只为 online-soft missing-time 扩展 preserve-none | `FRAMEWORK_COMPAT_EXTENSION` |
| pre-compress | `LightMemory.add_memory()` → `LlmLingua2Compressor.compress()` | `pre_compress`、`compression_rate` | current main 真实到达；非 dead | `CORE_STAGE` |
| topic segmentation | `SenMemBufferManager.add_messages()` / `cut_with_segmenter()` | `topic_segment`、`precomp_topic_shared` | vendored old core 在 false 时早退；upstream 2026-07-26 已改成单 segment 后继续流水线 | `CORE_STAGE + SOURCE_DRIFT` |
| STM threshold | `ShortMemBufferManager.add_segments()` | 产品构造处 `max_tokens=512` | framework `stm_threshold` 只校验/记 manifest，未传入 product | `CORE_VALUE_FIXED_512` |
| extraction/summary | `manager.meta_text_extract()` | `messages_use`、`metadata_generate`、`text_summary`、`extraction_mode` | local old core 只有两个 bool 同为 true 才定义 `extracted_results`；主配置保持 true | `CORE_STAGE` |
| direct insert | `add_memory()` → `offline_update(memory_entries)` | upstream `update="offline"` | 名称容易误导；此函数实际是 embed+insert，不等于全库 consolidation | `ONLINE_SOFT_IMPLEMENTATION` |
| offline consolidation | `construct_update_queue_all_entries()` + `offline_update_all_entries()` | adapter `lifecycle_profile`、score threshold | 主 profile 不调用；只准显式 LoCoMo 补充身份 | `AUTHOR_TOPOLOGY_VARIANT` |
| embedding retrieval | `text_embedder.embed()` + Qdrant `search(return_full=True)` | embedding identity、retrieve limit | adapter 绕过会丢 payload 的字符串出口，但复用同一官方内部检索链 | `PRODUCT_EQUIVALENT_READOUT_EXTENSION` |
| answer | official benchmark harness / framework builder | answer builder + evaluation runtime | 不属于 `LightMemory` 产品构建参数 | `EVALUATION_IDENTITY` |

### 1.3 current upstream 漂移

upstream
[`2c5abfb1d251327c4a25df2a80e40aa5a9437f3f`](https://github.com/zjunlp/LightMem/commit/2c5abfb1d251327c4a25df2a80e40aa5a9437f3f)
（2026-07-26）至少改变了以下 current-product 行为：

1. `topic_segment=false` 不再直接返回 segmentation dict，而是把全部消息当一个 segment 后继续
   extraction/store；
2. `extracted_results=[]` 预先初始化，使 metadata/summary 关闭时从潜在未绑定变量变成零 entry；
3. sensory buffer 增加若干空内容、超长内容与 role 防御。

主 profile 目前固定 `topic_segment=true`，所以第一项不是现行五格已跑行为的直接回归；但它证明
本仓 vendored source 已不等于 current product。upstream current 同时没有本项目 missing-time、
lineage、placeholder/flush 等 patch，因此不能盲目 fast-forward。M11 必须逐 hunk 三方合并、重跑
五格零 API/真实 smoke 门并 bump source identity；本批只登记，不替换源码。

## 2. 官方 benchmark 覆盖

| benchmark | 论文报告 | 公开 harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | Table 3 | `experiments/locomo/{add_locomo,search_locomo,llm_judge,prompts}.py` | LoCoMo；category 1–4，跳 5 | 每 utterance `[real user, blank assistant]`；post-build full consolidation；combined top-60 | `OFFICIAL_SOURCE_AVAILABLE` |
| LongMemEval | Table 2，LongMemEval-S | `experiments/longmemeval/run_lightmem_{gpt,qwen}.py` | cleaned S；论文另记五个坏样本 74/183/278/351/380 | positional user/assistant pair；非合规/odd tail 丢弃；per-question store | `OFFICIAL_SOURCE_AVAILABLE` |
| HaluMem | 否 | 无 Phase 1 官方 harness | N/A | framework extension | `NO_AUTHOR_PROFILE` |
| BEAM | 否 | 无 Phase 1 官方 harness | N/A | framework extension | `NO_AUTHOR_PROFILE` |
| MemBench | 否 | 无 Phase 1 官方 harness | N/A | framework extension | `NO_AUTHOR_PROFILE` |

审计时 upstream 另有 EgoLife/EM²Mem，但它不属于 Phase 1 五 benchmark，也不是 LightMem
conversation-QA 主身份；不能用它补后三格 author source。

## 3. Prompt / judge 合同

### 3.1 LongMemEval

- template/call path：`experiments/longmemeval/run_lightmem_gpt.py:181-199`。
- 变量：公开 `question_date`、`question` 和 `lightmem.retrieve(..., limit=20)` 的字符串列表。
- final messages：
  1. `system = "You are a helpful assistant."`；
  2. `user = "Question time:{question_date} and question:{question}\nPlease answer the question based on the following memories: {joined_memories}"`。
- answer decode：`temperature=0.0`、`max_tokens=2000`、`top_p=0.8`、`stream=False`。
- parser：直接读取 `choices[0].message.content`。
- judge：同一个 `LLMModel` decode；按 question type 选择 LongMemEval `get_anscheck_prompt()`，
  解析首行 yes/no。paper Appendix E.1 给出五类 judge prompt。
- framework 资产：`src/memory_benchmark/prompts/author/lightmem.py` 的 LME final-message 结构和
  decode 与该 harness 一致，但新 run 的 builder registry 目前只接受 `benchmark`，尚不可选。
- 裁决：`PROMPT_PARITY_EVIDENCE_READY / PROFILE_NOT_REGISTERED`。judge 只登记，不替换主
  LongMemEval evaluator。

### 3.2 LoCoMo

- template/call path：`experiments/locomo/prompts.py:148-190`、
  `search_locomo.py:240-282,441-465`。
- 变量：公开 question；Qdrant top-60 entries 按 `speaker_name` 分成两个槽位；每条 memory 带
  method 时间与文本。无 memory 时填官方 `No memories available.`。
- final messages：**一条 system message**，content 是填完 speaker names、speaker memories、
  question 的完整 `ANSWER_PROMPT`；不是 `[system instruction, user question]` 两条。
- answer decode：只显式传 `temperature=0.0`。`max_tokens`、`top_p`、response format 均使用
  OpenAI SDK/provider 默认；不能借 LME 的 `2000/0.8` 补上。
- parser：直接读取 `choices[0].message.content`。
- judge：一条 user message，`response_format={"type":"json_object"}`、temperature 0，读取
  JSON `label`；category 5 跳过。它是 method harness judge 资产，不自动成为主表 judge。
- framework 资产：LoCoMo prompt 与单 system message 结构已经存在，但
  `LIGHTMEM_NATIVE_ANSWER_SETTINGS` 被 LME/LoCoMo 共用，错误地给 LoCoMo 声明了
  `max_tokens=2000, top_p=0.8`；且 builder 尚未注册给新 run。
- 裁决：`INCOMPLETE`。M11 必须拆开两家 decode settings，并做最终 messages parity 后才可
  `AUTHOR_READY`。

### 3.3 author judge 与主表边界

LightMem paper 用 GPT-4o-mini judge，LoCoMo harness 还自带更宽松的 JSON judge。它们只用于
作者复现报告，不能随 `author_<benchmark>` 自动替换 framework benchmark judge。若未来要同时
报告 method-harness judge，需单独 metric identity/tier，不能改写主分数。

## 4. 参数矩阵

| parameter path | upstream default | paper role | official effective values | current main | 最终调用点 | 分类 | state/rebuild impact | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pre_compress` | false | Light1 核心阶段；全部实验启用 | LME/LoCoMo=true | true | compressor factory + `compress()` | core stage | 改 memory 内容；全量重建 | `MAIN_CONFIRMED_TRUE` |
| `compression_rate` | .8 | 论文 `r`；与 `th` 联合影响效果/成本 | paper：LME GPT .5/.6/.7、Qwen .4/.6/.8；LoCoMo GPT .7/.7/.8、Qwen .6/.8。current public scripts：LME 省略该键→.8；LoCoMo=.6 | .7 | `compress_config.rate` | high-impact | 改压缩文本；全量重建 | `.7` 是 paper-supported main；public script 不等于 paper table；author 需逐 row |
| `topic_segment` | false | Light1 核心阶段 | LME/LoCoMo=true | true | segmenter/buffer branch | core stage | 改分段/抽取；全量重建 | `MAIN_CONFIRMED_TRUE` |
| `precomp_topic_shared` | false | 共享 LLMLingua 模型/分词器的实现策略 | LME/LoCoMo=true | factory 固定 true | segmenter factory | implementation/core resource | 可能改 tokenization/资源；重建 | 保持 true，后续显式 identity |
| `messages_use` | user_only | 决定 STM token count 与 extraction prompt 角色 | 官方两格均 user_only | hybrid | STM + manager role filter | framework extension | 改 memory 内容与 calls；重建 | 主表 hybrid；author 必须 user_only |
| `metadata_generate` | true | summary/extraction 入口之一 | 官方两格 true | factory 固定 true | `meta_text_extract()` gate | core stage | 关闭可产零 memory；重建 | `MAIN_CONFIRMED_TRUE` |
| `text_summary` | true | summary/extraction 入口之一 | 官方两格 true | true | 与 metadata 联合 gate | core stage | 改 memory 内容；重建 | `MAIN_CONFIRMED_TRUE` |
| `extraction_mode` | flat | LightMem factual extraction；event 属 StructMem | LoCoMo CLI 默认 flat；LME flat | flat | extraction prompt normalization/manager | topology enum | event 改条目结构；重建 | 主表仅 flat；event 另 method variant |
| STM `max_tokens` / `stm_threshold` | product class default 2000，但 `LightMemory` 构造硬编码 512 | 论文 `th` 核心超参数 | LME 256/512/768/1024；LoCoMo 512/768/1024 | 配置写 512，product 实际 512 | `ShortMemBufferManager(max_tokens=512)` | high-impact | 改 extraction batch；重建 | 512 真实；非 512 当前不可表达 |
| `extract_threshold` | .5 | 论文没有把该字段作为 extraction 阈值；paper `th` 是 STM capacity | harness 写 .1 | .5 | **无产品消费者** | dead config | 改值不改 state | `DEAD_CONFIG`；M11 退出 active identity |
| `index_strategy` | None | summary embedding 入 LTM | 官方 embedding | factory 固定 embedding | embed+insert | core enum | 改存储/index；重建 | `MAIN_CONFIRMED_EMBEDDING` |
| embedding model/dim | None | Table 5 MiniLM cosine | MiniLM/384 | controlled MiniLM/384 | HuggingFace embedder + Qdrant schema | controlled core identity | 改向量/维度；全量重建 | confirmed |
| `retrieve_strategy` | embedding | Table 5 cosine vector retrieval | embedding | embedding | Qdrant search | core enum | 改 candidate/ranking；build 可能可复用但 run identity 必变 | confirmed |
| `retrieve_limit` | API default 10 | paper 说跨方法固定数量，未给一个跨表唯一 k | LME 20；LoCoMo combined 60 | 60 | Qdrant `search(limit=...)` | readout hyperparameter | 不重建 build；答案/metric identity 变 | main 60；author per benchmark |
| upstream `update` | offline | soft insert + optional sleep-time update | harness 均 offline/direct insert | factory 固定 offline | `offline_update(memory_entries)` | misleading enum | direct insert 本身改变 LTM | 不把字段名解释为 consolidation |
| `lifecycle_profile` | framework field | paper online-soft / offline 两行 | LME 两类；LoCoMo headline=post-update | online_soft | adapter 是否另跑全库 queue/update | topology identity | consolidation 改写/删 entry；重建/不可共用 state | main online_soft；author LoCoMo需 consolidated |
| `offline_update_score_threshold` | function .9；README tutorial .8 | offline update merge gate | current LoCoMo script .9 | .8，但主 profile dormant | 仅 consolidated 调用 | dormant in main | 主 profile无影响；author改变合并 | 主身份标 inactive；author LoCoMo=.9 |
| `summary_retriever` | optional None | 不属于 LightMem headline | LoCoMo脚本创建但标准 search 不启 summary | factory创建 | 只有显式 `summarize()`/StructMem消费 | dormant/product extension | 主 build无 summary state | 不作为 main 算法阶段 |
| `kv_cache` | false | paper future optimization，不是 headline | 未启用 | false/未暴露 | KV branch | non-headline variant | 可能改资源/推理 | 不进入 main TOML |
| `graph_mem` | false | 非 LightMem headline | 未启用 | false/未暴露 | GraphMem factory | algorithm variant | 改存储/retrieval | 不进入 main TOML |
| `missing_timestamp_policy` | upstream 无 preserve-none | 非论文算法 | 官方两格都有时间 | preserve_none | adapter preflight + patched normalizer | compatibility extension | timestamp 缺失格改变可运行性；重建 | 主五格保留，author consolidated=require |
| `force_segment/force_extract` | false per call | flush STM/sensory boundary | harness 最后一批 true | conversation/session 边界派生 | `add_memory()` call kwargs | execution-derived semantic flag | 决定尾部是否落库 | 不做用户超参数；由 runner精确派生 |
| memory manager max tokens | backend default 2000 | extraction 输出上限，论文未给统一配置字段 | official两格=16000 | factory=16000 | OpenAI manager payload | upstream exposed build LLM parameter | 可改 memory output；重建 | 保持 official exposed value；记录而非调优 |

特别勘误：current README 仍把 `extract_threshold` 描述成“决定内容是否值得提取”的阈值，
`LightMemConfig` docstring 也沿用了这句话；静态调用链只发现 schema、harness 和 framework
pass-through，没有任何产品读取。README/schema 的意图描述不能覆盖 current executable semantics。

## 5. 配置流与强反例

### 5.1 effective config

```text
configs/methods/lightmem.toml
  → profile loader / LightMemConfig
  → _default_backend_factory(config, runtime, state path)
  → BaseMemoryConfigs(**dict)
  → LightMemory(product object)
  → add_memory()/Qdrant search
```

已确认：

- `pre_compress`、`compression_rate`、`topic_segment`、`messages_use`、`text_summary`、embedding
  identity 和 lifecycle 均能追到有效 branch/payload；
- `stm_threshold` 只进入 validation、`lightmem_profile` 诊断字段和 manifest，真正产品构造仍是
  512；
- `extract_threshold` 只进入 `BaseMemoryConfigs` 对象，没有下游读取；
- `offline_update_score_threshold` 在 main `online_soft` 下没有调用点；
- runtime credential/base URL、timeout/retry 和 workers 已由 composition root 注入，不应回流
  method TOML。

### 5.2 source identity 缺口

`build_lightmem_source_identity()` 目前只 hash 8 个文件。以下会改变产品行为且已被本项目 patch 的
文件不全部在清单：

- `src/lightmem/factory/memory_buffer/short_term_memory.py`；
- `src/lightmem/factory/memory_manager/openai.py`；
- `src/lightmem/factory/pre_compressor/llmlingua_2.py`；
- `src/lightmem/memory/utils.py`。

因此当前 `a44d7d99…` 是历史有效 run 的既有身份，但**不是完整 source lock**。M11 扩清单后必须
bump contract/source identity，并拒绝新 identity resume 旧 build；不能改写旧 artifact 的 hash。

## 6. 主配置与作者配置裁决

### 6.1 framework main

主表继续固定：

- LightMem flat pipeline；预压缩、topic segmentation、metadata/summary 均启用；
- `compression_rate=0.7`、真实 STM=512；这是论文明确报告的组合，不是 demo default；
- `messages_use=hybrid`，保证五格 assistant 信息不被静默丢弃；该项明确标
  `framework role-complete extension`，不冒充 paper parity；
- controlled MiniLM/384 + cosine embedding retrieval；
- `retrieve_limit=60` 作为跨五格主 readout；
- `online_soft` direct insert；缺失时间只在官方确实无 time 的数据上 preserve-none；
- StructMem event/summary、graph memory、KV cache 不混入主身份。

### 6.2 author profile 为什么本批不创建

LightMem paper 不是每个 benchmark 一个唯一配置，而是每个 backbone 有多组 `(r, th)`，且 online
soft / OP-update 也是两种结果身份。当前 public product 又把 STM 固定在 512，无法表达论文中的
256/768/1024。更关键的是，current public LongMemEval script 没有写 `compress_config`，effective
`r` 继承 schema 默认 .8；LoCoMo script 则写 .6。两者都固定 product STM=512，所以它们本身也
不能逐字复现 paper headline tables。一个笼统 `author_longmemeval` 或 `author_locomo` 会把
paper rows、current script 与 backbone 压成假唯一值。

当前只能确认两组 current-product 可表达的 paper rows：

- LongMemEval GPT `r=.7, th=512`，online-soft 或对应 OP-update；
- LoCoMo GPT `r=.7, th=512`，Table 3 ACC 是 post-update。

但正式作者复现还要同时锁 backbone、dataset 清理、role policy、retrieve k、answer decode、judge
identity 和坏样本处理。M11 应先裁定是只注册一个明确命名的 canonical row，还是支持
`author_longmemeval_gpt_r07_th512_online` 这类显式多 profile；在此之前不造单一
`author_<benchmark>`。

### 6.3 topology variant

- LoCoMo post-update 会全库构造 queue 并更新/删除/合并，不是普通数值 override；必须 fresh
  state + 显式 topology identity。
- StructMem `event` extraction、summary retrieval 是另一个算法变体。
- main hybrid vs author user-only 会改变抽取内容与 token count，也要求重建。

## 7. Manifest / resume / artifact

- 必须进入 identity：完整 source lock、compression model/revision、`r`、真实 `th`、role policy、
  extraction mode、metadata/summary、embedding 全身份、retrieve strategy/k、lifecycle/topology、
  missing-time policy、answer builder/decode、API runtime identity。
- build-affecting任一字段变化均 fresh-state 重建；retrieve k / answer builder 变化至少要求新 run
  identity，不得 silent resume。
- 旧 `a44d7d99…` artifact 永久按原 8-file hash 回读，不追认成扩展 source lock。
- gold answer/evidence/judge label 不得进入 LightMem；official author builder 只能读公开 question、
  question time、speaker metadata 与 method retrieval output。

## 8. 未闭合项与停工点

| item | status | 已查范围 | 下一条一手证据/动作 |
| --- | --- | --- | --- |
| vendored vs upstream current 合并 | `SOURCE_DRIFT_REVIEW_REQUIRED` | base/current tarball + full relevant diff | M11 三方合并、五格门、source bump |
| `extract_threshold` 退出 | `DEAD_CONFIG_CONFIRMED` | schema/harness/全 source references | M11 从新 main config/identity 删除；旧 artifact兼容读取 |
| 非 512 STM | `UNEXPRESSIBLE_CURRENT_PRODUCT` | paper rows + product constructor | 若要复现其他 rows，先新增 upstream seam并证明算法守恒 |
| LoCoMo author decode | `INCOMPLETE` | final API call + current asset | 拆分 LME/LoCoMo settings，final-message parity |
| author profile 命名 | `PENDING_ARCHITECT_RULING` | paper多行 + current schema | 十家横向 M11 决定单 canonical row 或显式多 row |
| complete source lock | `INCOMPLETE` | current 8-file list + framework patch history | 扩 hash 文件列表；strict resume mismatch |
| paper坏样本复现 | `AUTHOR_ONLY_PENDING` | paper Appendix D.1 | author LME profile 明确 drop+score-false；主表不改 dataset |

这些 pending 不推翻 current main 五格 smoke 的行为冻结；它们阻止的是“当前配置已经等于任一篇
作者报告结果”以及“可以在扩大 pilot 前忽略 source drift”两种过度声明。

## 9. 验证记录

零 API证据命令：

```bash
sha256sum third_party/methods/LightMem/lightmem.pdf
.venv/bin/python -c 'from memory_benchmark.methods.lightmem_adapter import build_lightmem_source_identity; print(build_lightmem_source_identity())'
rg -n "extract_threshold" third_party/methods/LightMem src/memory_benchmark
cmp <upstream-02e675-file> <initial-import-file>
diff -u third_party/methods/LightMem/src/lightmem/memory/lightmem.py \
  /tmp/lightmem-b4ef1dd-current/src/lightmem/memory/lightmem.py
```

事实输出：

- local PDF SHA-256：`7e9a8e9f…c23e`；
- vendored 8-file SHA-256：`a44d7d99…d7e5`；
- upstream-main 8-file SHA-256：`c92016a8…b5d`；
- 九个承重 core/eval 文件 initial import vs upstream `02e675b1…`：全部 `MATCH_BASE`；
- `extract_threshold`：无 product call-site consumer；
- 本批不调用真实 API、不写 output、不修改 raw data/third_party source/config/code。

最终门：`tests/test_documentation_standards.py + tests/test_codex_project_hooks.py` =
`13 passed in 1.90s`；`git diff --check` 无输出。架构判词为
`M1_EVIDENCE_COMPLETE / AUTHOR_NOT_READY / SOURCE_DRIFT_REVIEW_REQUIRED`。
