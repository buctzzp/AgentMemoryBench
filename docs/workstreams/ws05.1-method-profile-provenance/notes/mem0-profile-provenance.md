# Mem0 profile provenance（M3）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M3 一手证据，不改写成新 run 收据。

> 判词：`M3_EVIDENCE_COMPLETE / PAPER_CURRENT_ALGORITHM_VARIANT /
> CURRENT_HARNESS_SOURCE_LOCKED / AUTHOR_NOT_READY /
> SOURCE_DRIFT_REVIEW_REQUIRED`。
>
> 本文只关闭论文、current product、两代 official harness、framework main 四种身份的证据门。
> 不在本批升级 source、修改 TOML、注册 author profile、调用真实 API 或调优效果；施工统一留到 M11。

## 0. 身份与范围

- method：Mem0 OSS（不是 Mem0 Platform，也不是论文中的 Mem0g graph variant）。
- 审计日期：2026-08-25。
- paper identity：arXiv `2504.19413v1`（2025-04-28）；本机 PDF
  `third_party/methods/mem0-main/Chhikara 等 - 2025 - Mem0 Building Production-Ready AI Agents with Scalable Long-Term Memory.pdf`，
  SHA-256=`bec870b657aa73405275a6d8fe27bcd4271799e028bc62986ab9c4cd27a3712d`。
  PDF 是用户未跟踪资产，只能作为本机阅读证据，不属于 fetch 恢复合同。
- framework current product：vendored `mem0ai/mem0` package `2.0.4`；当前 identity 共 146 个
  文件（产品 core + LoCoMo/LME 两份 harness prompt），SHA-256=
  `debda89ed60d9f104ab6fa65d6178d5f146b3216158f3dc2fdba2ee16a3ff08e`；
  adapter=`conversation-qa-v3`。
- upstream current product：2026-08-25 现场读取 `mem0ai/mem0@39bc02330563764e7d4465f1ecff5f002d94da1a`，
  package `2.0.19`。它是漂移比较源，不是现行 framework runtime。
- current official evaluation：`mem0ai/memory-benchmarks@4b61c5d31b9c668a12b4f5e78064248a02c82d2b`；
  本地 `third_party/methods/mem0-main/memory-benchmarks/` 与该 commit 逐文件一致。
- old paper-era evaluation：vendored `evaluation/src/memzero/`，使用 hosted `MemoryClient`/v2
  双 namespace 拓扑；它不是 current `memory-benchmarks` 的旧名字。
- 本次不覆盖：真实 API 效果复现、Mem0 Platform 云端私有实现、Mem0g 图实现、source 升级施工、
  参数 sweep、三家 author builder 注册以及官方 judge 是否进入 framework metric tier。

## 1. 算法机制先行

### 1.1 论文阶段图

| 阶段 | 输入 | 状态/输出 | 是否可选 | 一手出处 |
| --- | --- | --- | --- | --- |
| 上下文组装 | 新消息对 `(m[t-1], m[t])`、conversation summary `S`、最近 `m` 条消息 | extraction 上下文 | 论文核心 | PDF pp.3-5，Figure 2 |
| fact extraction | 上述上下文 | 候选记忆 `Omega={omega_i}` | 论文核心 | PDF pp.4-5 |
| candidate retrieval | 每个 `omega_i` | 已有记忆 top-`s` | 论文核心 | PDF p.5、p.21 |
| operation decision | `omega_i` + 相似已有记忆 | `ADD/UPDATE/DELETE/NOOP` | 论文核心 | PDF p.5、Algorithm 1（p.21） |
| state mutation | operation + memory DB | 可增加、替换、删除或保持的记忆集合 | 论文核心 | PDF p.21 |
| Mem0g（独立变体） | message → entities/relations | Neo4j temporal knowledge graph | 不是 Base Mem0 必选阶段 | PDF pp.5-6，Figure 3 |

论文明确报告 `m=10`、`s=10`、方法 LLM=`GPT-4o-mini`，适用处 temperature=`0`；只说明
dense embedding，没有披露 Base Mem0 的 embedding model/dimension。RAG baseline 的 chunk、top-k、
embedding 不是 Mem0 方法参数，禁止抄进 Mem0 profile。论文 judge model 未明确披露，记 `PENDING`。

### 1.2 current 2.0.4 source 对应关系

```text
Memory.add(messages, infer=True)
  -> raw recent messages(limit=10)
  -> existing-memory vector search(top_k=10)
  -> ADDITIVE_EXTRACTION_PROMPT
  -> parse {"memory": [...]}
  -> batch embedding
  -> exact MD5 text dedup
  -> vector-store ADD
  -> entity extraction/linking
  -> raw-message persistence
```

| 论文阶段 | current module/function | 控制参数 | 版本漂移/缺失 | 判词 |
| --- | --- | --- | --- | --- |
| summary + recent context | `mem0/memory/main.py:699-714` | recent limit 与 existing top-k 均硬编码 10 | 没有论文的异步 summary generator；主要消费 raw recent messages | `ALGORITHM_VARIANT` |
| fact extraction | `main.py:725-763` + `configs/prompts.py:468-516,918-944` | `infer`、build LLM/model/decode | current prompt 只输出 ADD facts、speaker attribution、可选 linked ids | `ALGORITHM_VARIANT` |
| per-fact operation classifier | 当前 V3 add 路径无消费者 | N/A | 没有论文式 `ADD/UPDATE/DELETE/NOOP` LLM decision | `MISSING_FROM_CURRENT_V3` |
| update/delete | 显式 `Memory.update/delete` API | 外部调用 | `add()` 不会因冲突自动触发 | `NOT_AUTOMATIC` |
| no-op | `main.py:785-803` | MD5 完全文本 hash | 只跳过精确重复，不等于语义 NOOP | `NOT_EQUIVALENT` |
| graph | entity store linking/search boost | entity extraction/boost 内部值 | 不是论文 Mem0g 的 relation-triplet/Neo4j 图 | `NOT_MEM0G` |
| query retrieval | `main.py:1126-1237,1343-1499` | top-k、threshold、rerank | vector + BM25 + entity boost；论文未定义这套 reader | `CURRENT_PRODUCT` |

current `add()` 的 docstring/旧 prompt 仍提到四操作，但生产 V3 调用链没有调用旧 operation prompt。
判断行为必须看调用图，不能由残留符号或 docstring 反推。`linked_memory_ids` 虽由 extraction prompt
生成，却没有作为 memory record 的同名 metadata 持久化；entity store 另行维护实体→memory-id 链。

### 1.3 论文、old harness 与 current product 不可互换

```text
paper s=10
  != current query top_k=20
  != current add-stage hardcoded existing-memory top_k=10

paper summary + recent m=10
  != current raw last_messages(limit=10)

paper ADD/UPDATE/DELETE/NOOP classifier
  != current additive extraction + exact hash dedup

paper Mem0g relation graph
  != current OSS entity linking/boost
```

因此论文结果只能作为 `paper identity`；current 2.0.4 主运行不能标成 paper reproduction。

## 2. 官方 benchmark 覆盖

| benchmark | 论文报告 | 公开 harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | Base Mem0/Mem0g 主实验 | old `evaluation/src/memzero/` + current `memory-benchmarks` | current 下载 `locomo10.json`，未锁 dataset commit/hash | old=双 namespace/正反 role；current=单 namespace、turn add | `IMPLEMENTATION_VARIANT` |
| LongMemEval | 论文 v1 未报告 Phase 1 LME | current `memory-benchmarks` | `longmemeval_s_cleaned.json`，未锁 HF revision/hash | question 独立 namespace；session 排时后 position-pair add | `IMPLEMENTATION_VARIANT` |
| HaluMem | 未报告 | 无公开 Mem0 harness | N/A | framework extension | `SOURCE_UNAVAILABLE` |
| BEAM | 论文 v1 未报告 | current `memory-benchmarks` | BEAM 100K/500K/1M/10M，未锁 HF revision/hash | conversation namespace；position-pair add | `IMPLEMENTATION_VARIANT` |
| MemBench | 未报告 | 无公开 Mem0 harness | N/A | framework extension | `SOURCE_UNAVAILABLE` |

current `memory-benchmarks` 的 harness source 已锁，但它的 Docker requirements 指向已经无法从 current
remote 重建的 `feat/v3-pipeline` branch。故“harness 文件 exact”不等于“harness + runtime 完整可复现”。

### 2.1 old LoCoMo 双 namespace 的设计理由

old harness 给两位 speaker 各建一个逻辑库：A 库映射 `A=user/B=assistant`，B 库反向映射，
同时用 user-only extraction instruction；检索时两库各取 top-10，再放进 answer prompt 的两个槽位。
这不是无意义的重复：它通过“每位 speaker 各作为一次 user”适配当时只抽 user 的 hosted v2
产品假设，使双方事实都有机会被保留。

但迁入 current V3 会改变双写次数、抽取调用、namespace、角色语义、检索融合、成本与 provenance。
因此本项目不因方案不同而判它“错”，也不把它硬塞成一个 TOML bool；正确分类是独立
`IMPLEMENTATION_VARIANT`，若复现必须建完整 topology identity。

### 2.2 current memory-benchmarks 三格拓扑

- LoCoMo：`CHUNK_SIZE=1`，固定 speaker_a→user、speaker_b→assistant，content 保留 speaker 名；
  单 conversation namespace；每 session timestamp 传 client；search 默认 top-200。
- LongMemEval：`CHUNK_SIZE=2`，保留 role，按完整时间排序 session，position-pair add；任一消息 blank
  时 current harness 丢整个 pair；每 question 独立 namespace；search 默认 top-200。
- BEAM：`CHUNK_SIZE=2`，user/human→user，其余→assistant；去 blank 后 position-pair；batch 首个
  time anchor；每 conversation 独立 namespace。已知 10M 的两个 orphan window 会令 position-pair
  产生 role-mismatched chunk；这是 harness 的真实 variant，不应被美化成 role-aware pairing。

三格都通过 `Mem0Client` 发送 timestamp；vendored Docker `AddRequest` 没有 timestamp 字段，故 OSS
server 路径会丢弃它。client 的 search body 用 `limit`，vendored 2.0.4 `Memory.search()` 消费的是
`top_k`；在这组 runtime 下 top-200 是否真正生效尚不闭合，不能把 CLI 值直接写成 effective 值。

## 3. Prompt / judge 合同

### 3.1 共同 transport

current harness 的 `LLMClient.generate()` 默认 temperature=0、max tokens=4096；GPT-5/o-series
实际不发送 temperature，并使用 `max_completion_tokens=4096`；其他模型发送 `temperature=0`、
`max_tokens=4096`。`top_p` 与 `n=1` 不在实际 payload。system 为空时最终只有一个 user message。

`src/memory_benchmark/prompts/author/mem0.py` 的三家模板与官方 prompt 常量逐字一致，但它只有
dataclass/静态 dict，没有完成 cutoff、排序、日期/profile/evidence 格式化、最终 messages、decode、
answer/judge parser 或 registry reachability。它只能叫 `official template parity asset`，不能叫
可运行 author builder。

adapter `_reader_messages()` 仍能构造三家官方 prompt，属于 legacy/native 兼容资产；新 registered
run 会由 `_resolve_registered_answer_builder()` 强制选择 benchmark builder，并在
`prediction_answer._answer_prompt_from_retrieval_result()` 覆盖 method `prompt_messages`。因此不能因
adapter 中存在 builder 就宣称新 author profile 可达。

### 3.2 LoCoMo

- official answer：score top-200 后再按 `created_at` 升序；`reference_date` 取最后 session；最终
  `[{role:"user", content:<完整 prompt>}]`；parser 取最后 `ANSWER:` 后文本。
- official judge：system + JSON user prompt；category 3 gold 在首个分号截断；JSON `label==CORRECT`
  得 1。`--with-evidence` 会把 private evidence 给 judge，是补充 judge variant，绝不可达 method。
- framework current author status：`AUTHOR_NOT_READY`。

### 3.3 LongMemEval

- official answer：score cutoff 后按 `created_at` 升序；实际传入 oldest-first，虽然模板文字声称
  newest-first；最终只有 user message；parser 删除 `<mem_thinking>...</mem_thinking>` 后取最后
  `ANSWER:`。
- answerer judge：无 system，普通文本 yes/no，不是 JSON；gold answer 与 question date 只给 judge。
- retrieval mode：另有 JSON retrieval judge，不能与 answerer judge 混成一个 profile。
- framework current author status：`AUTHOR_NOT_READY`。

### 3.4 BEAM

- official answer：score cutoff → chronological order → numbered/date memory；最终只有 user message；
  parser 取最后 `ANSWER:`。
- official judge：每个 private rubric nugget 单独 JSON judge，阈值映射为 0/0.5/1 后求均值；
  event-ordering 还增加 event extraction、alignment 与 Kendall tau-b 调用拓扑。
- `prompts/author/mem0.py` 未覆盖 event-ordering 两类额外 prompt/parser。
- framework current author status：`AUTHOR_NOT_READY`。

method harness judge 只完成 provenance 盘点；是否进入 framework evaluator 是独立 metric-tier 裁决，
本批不改主 judge。

## 4. 参数矩阵

| parameter path | upstream default | paper role | official effective values | current main | call site/最终 payload | 分类 | state/rebuild impact | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| source/package | vendored 2.0.4；upstream 2.0.19 | paper 未锁 package | current harness runtime branch 不可重建 | 2.0.4/source hash | registry source identity | build | 源变化须重建 | `SOURCE_DRIFT_REVIEW_REQUIRED` |
| build LLM | framework runtime 注入 | GPT-4o-mini | current Docker default GPT-4o-mini/temp .1 | runtime model + hardcoded temp .1 | `build_backend_config()` | build | 模型/decode 变化须重建 | main 与 paper temp 不同 |
| embedding | product default OpenAI | dense，model 未披露 | Docker `text-embedding-3-small` | MiniLM/384 | final embedder config | build | 任一 identity 变化须重建 | `MAIN_CONFIRMED_CONTROLLED` |
| `infer` | True | 抽取为核心 | harness add 默认 inference | true | `Memory.add(... infer=True)` | build | 关闭会换算法路径 | 保持 true |
| recent messages | 10（source hardcode） | `m=10`，含 summary 语义 | current product raw messages | 10 hardcode | `db.get_last_messages(... limit=10)` | internal build | 改变须重建 | 不暴露成伪 paper 等价参数 |
| add existing top-k | 10（source hardcode） | `s=10` per candidate | current V3 batch-level search | 10 hardcode | `_search_vector_store(... top_k=10)` | internal build | 改变须重建 | 与 query top-k 分开记 |
| extraction mode | additive V3 | four-operation | current harness runtime unresolved | additive V3 | `ADDITIVE_EXTRACTION_PROMPT` | build | 改变须重建 | `ALGORITHM_VARIANT` |
| query `top_k` | 20 | 非 paper s | harness 意图 200；OSS effective unresolved | 20 | `Memory.search(top_k=...)` | readout | 不重建；新 retrieval/answer identity | `MAIN_CONFIRMED_CONTROLLED` |
| search threshold | 0.1 | 未披露 | client/server 未显式一致传递 | 省略→产品 0.1 | `Memory.search()` default | readout | 不重建；影响检索 artifact | M11 显式登记 effective 值 |
| `rerank` | false | 未披露 | harness 未启用 | false | `Memory.search(rerank=False)` | readout | 不重建；启用还需 reranker identity | 保持 false；true 当前 fail-fast |
| `ingestion_chunk_size` | N/A | paper 新消息 pair | LoCoMo=1，LME/BEAM=2 | TOML=1，但只作 validation | 真正 topology 由 registry+adapter 决定 | topology | 变化须重建 | `DEAD_AS_GLOBAL_CONTROL`，M11 退出/改名 |
| observation-time instruction | N/A | paper 未披露 | current Docker timestamp 会丢 | framework 按公开 source time 注入 prompt/content | adapter `_observation_time_prompt()` | build extension | 变化须重建 | `FRAMEWORK_COMPAT_EXTENSION` |
| vector store | product可配 | dense DB | Docker Qdrant | Qdrant | product config | build/storage | 变化须重建 | identity 必须保留 |

数值型参数也可能是算法机制；bool 也可能只是 dormant。裁定基于是否到达最终调用面，而不是数据类型。

## 5. 配置流与强反例

- TOML → `Mem0Config`：MiniLM/384、top-k20、`infer=true`、`rerank=false` 进入强类型配置；未知、
  非正 top-k、非 1 `ingestion_chunk_size`、`rerank=true` 会在 API 前 fail-fast。
- factory → product：embedding provider/model/dimension、build LLM 与 temp .1 进入 Mem0 config；
  Qdrant state 按 run/worker 隔离。
- retrieval：普通 QA 使用 profile top-k20；HaluMem update probe 才忠实采用 query top-k10，两者在
  artifact metadata 分别记 `top_k_source`。
- `ingestion_chunk_size=1` 不是有效全局控制：LoCoMo/MemBench=turn、BEAM=pair、LongMemEval/HaluMem=
  session；LongMemEval adapter 内再 position-pair，HaluMem 整 session。这是 M11 必须清理的假控制。
- current source identity 覆盖产品 core，却只任意加了 LoCoMo/LME prompts，漏掉 BEAM prompt/run、
  common client 与 framework author asset。M11 应拆成 product source identity 与独立
  harness/answer-builder identity，而不是继续追加任意文件。

## 6. 主配置与作者配置裁决

- framework main：暂时维持 2.0.4 + MiniLM/384 + infer=true + query top-k20 + rerank=false；
  这是受控 current-product identity，不是 paper reproduction，也不是 current harness parity。
- `author_locomo/author_longmemeval/author_beam`：均 `AUTHOR_NOT_READY`。必须完整闭合
  retrieval cutoff/order → variables → final messages → decode → parser；只复制模板不能注册。
- product-default：应作为显式补充身份，不能暗中替换主比较 embedding/LLM。
- old LoCoMo dual namespace 与 current harness 的 topology/OSS runtime 偏差：均为
  `IMPLEMENTATION_VARIANT`，不能仅靠 TOML scalar 表达。
- M3 不修改 TOML。M11 统一裁决 source upgrade、假控制退出、hidden effective values、source
  identity 分层以及 author profile，避免十家形成十套配置模型。

## 7. Manifest / resume / artifact

必须锁：product source/package、adapter version、build LLM/transport/decode、embedding 全 identity、
infer、实际 ingestion topology、observation-time instruction、vector store、namespace 策略、query
top-k/threshold/rerank、answer builder/harness source 与 parser identity。

- source/prompt/build LLM/decode、embedding、infer、topology、time instruction、storage 变化：全量重建。
- 仅 query top-k/threshold/rerank 变化：通常不重建 memory，但必须产生新的 retrieval/answer artifact
  identity；reranker construction/model 变化另锁 model/source。
- paper-era hosted、current memory-benchmarks、framework local 2.0.4 artifact 不得相互 resume。
- 旧 artifact 永久按原 manifest 回读，不回填新 identity。
- gold/evidence/rubric/judge labels 只可达 evaluator private label；method/harness builder 不得读取。

## 8. 未闭合项与停工点

| item | status | 已查范围 | M11 下一条证据/动作 |
| --- | --- | --- | --- |
| 2.0.4→2.0.19 upgrade | `PENDING_RULING` | package、核心 hash、LLM failure 语义已确认漂移 | 逐项 source diff + migration/rebuild plan；禁止盲目 fast-forward |
| current harness runtime | `SOURCE_UNAVAILABLE` | Docker requirements 指向不存在 branch | 找 release/container digest；找不到就诚实标不可完整复现 |
| dataset identity | `PENDING` | URL/shape 已知，官方未锁 revision/hash | author profile 必须锁 framework source-lock |
| 三家 complete author builder | `AUTHOR_NOT_READY` | template/harness/final payload 已盘点 | 实现完整 builder + fake-client parity tests |
| official judge adoption | `PENDING_METRIC_TIER` | 三家 judge 拓扑已盘点 | 独立 metric policy；不得在此批暗换 |
| search threshold/temp/source identity | `PENDING_IMPLEMENTATION` | effective source 已定位 | 显式 manifest/build identity；不借机调优 |

本批没有需要提前修改生产代码的停工点；上述项均进入 M11，而非边查边改。

## 9. 验证记录

- 两名独立 `gpt-5.6-luna` / `reasoning_effort=max` 调研者分别审计 paper/current product 与
  current official harness；均只读、零 API、零文件改动。架构师没有按模型投票：亲自复核了
  PDF hash/机制页、2.0.4 add/search 调用链、current upstream version/hash、official harness
  commit/hash、registered answer-builder 覆盖接缝与 TOML 最终消费面。
- 调研分歧已在接缝处消解：adapter official `prompt_messages` 存在，但新 registered run 使用
  benchmark builder 覆盖；故它们是 dormant compatibility asset，不是可达 author profile。
- source probe：`package_version=2.0.4`、`file_count=146`、
  `source_sha256=debda89ed60d9f104ab6fa65d6178d5f146b3216158f3dc2fdba2ee16a3ff08e`；
  输出尾部明确包含 LoCoMo/LME prompt，证实当前 identity 是混合口径。
- official harness 三个 run hash：LoCoMo=`4f104079…`、LongMemEval=`99bd3d6d…`、
  BEAM=`c13ed846…`；common LLM client=`b0dc8f41…`、Docker server=`7fcab8b4…`、
  OpenAI config=`897c4164…`，与 official `4b61c5d…` 对齐。
- 零 API命令：
  `uv run pytest -q tests/test_mem0_adapter.py tests/test_locomo_registered_prediction.py
  tests/test_longmemeval_registered_prediction.py tests/test_membench_registered_prediction.py
  tests/test_beam_registered_prediction.py tests/test_halumem_registered_prediction.py
  tests/test_mem0_native_prompts.py tests/test_method_registry.py
  tests/test_documentation_standards.py tests/test_codex_project_hooks.py`。
- 真实尾行：`198 passed in 16.89s`；`git diff --check` 无输出。
- 架构验收：`ACCEPTED`。第一次 source probe 使用了错误的内部导入路径、第二次错误地手工构造
  `PathSettings`，均以 traceback 明确作废；最终使用生产 `load_path_settings(Path.cwd())` 成功，
  不把失败中间态伪装成验收证据。
