# Graphiti OSS profile provenance（M10）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M10 一手证据，不改写成新 run 收据。

> 状态：`M10_EVIDENCE_COMPLETE`。本文先由架构师按 vendored v0.29.3 源码、官方 README、公开
> release、Zep paper/official hosted source、current remote 与 framework call path 建立证据骨架；
> 两路 scheduler 接受 `gpt-5.6-luna/max` 的调查回执只作为候选证据，通过回执完整性门和承重锚点
> 复核后才进入本文。subagent 会话只能自报 generic Codex/GPT-5，无法反证或细化 scheduler identity，
> 故不猜测更细模型名。
>
> 本批零真实 API、零 source upgrade、零参数 sweep；不修改 TOML、adapter、prompt registry、旧
> artifact 或第三方 source。Graphiti OSS、Zep hosted product 与 Zep 论文实验严格分栏，禁止把后
> 两者的数字或 prompt 冒充 Graphiti OSS author profile。

## 0. 身份与范围

- method：Apache-2.0 Graphiti OSS temporal context graph engine；不是 Zep hosted Context Graph，
  也不声明 hosted product parity。
- 审计日期：2026-08-25。
- framework pin：`getzep/graphiti@v0.29.3/021d3a57d511f21b10adaf7fa923bd5c1fce5e9d`，
  detached clean nested repo，Apache-2.0。
- current remote：2026-08-25 `main=993e081a6d7948a0d8851c12a5fbdbeb49fed862`；最新稳定
  release 仍是 `v0.29.3`，`v0.30.0` 只有 prerelease。相对 stable 的 current main 有代码变化，
  GitHub compare 显示 25 commits / 11 files，但 framework 本批不机械升级，也不凭文件数猜测语义。
- paper/technical-report identity：官方 Graphiti README 指向
  `Zep: A Temporal Knowledge Graph Architecture for Agent Memory`，arXiv `2501.13956`。它是
  Graphiti 机制的重要一手材料，但论文实验对象和产品读出是 Zep architecture/product；未获得
  exact OSS payload parity 前，不能把论文结果写成 Graphiti OSS author result。
- current official evaluation：`tests/evals/eval_e2e_graph_building.py` 使用 LongMemEval 数据检查
  **候选建图回归**；它不执行 question search、final answer 或 benchmark judge，而且其 judge 字段
  schema、自然语言指令与计分分支互相矛盾，不能直接当可靠质量分数。
- framework main：direct `Graphiti.add_episode()` + basic `Graphiti.search()`，每 conversation 独占
  FalkorDB Lite 物理 root，controlled MiniLM384，framework benchmark answer/judge。
- 本次不覆盖：Zep cloud 私有实现、真实效果、source upgrade、参数 sweep、作者 full 结果复现、
  新 API run、旧 artifact 重标或十家横向代码迁移。

## 1. 算法机制先行

### 1.1 可复用机制卡

```text
ordered public episode
  -> EpisodicNode(raw content + reference_time + group_id)
  -> LLM entity extraction
  -> embedding candidate search + LLM entity deduplication
  -> entity summary / attribute update
  -> LLM relation/fact extraction
  -> BM25 + vector candidate search over existing edges
  -> LLM duplicate / contradiction resolution
       exact duplicate -> append current episode lineage
       new compatible fact -> create EntityEdge
       contradiction -> invalidate/expire older fact window
  -> entity/fact embeddings + graph persistence

query
  -> edge BM25 + cosine similarity
  -> reciprocal-rank fusion (RRF)
  -> ordered EntityEdge facts
  -> episode UUID lineage -> canonical turn ids
  -> framework formatted_memory -> benchmark answer builder
```

这张卡是以后回答“Graphiti 如何工作”的热入口；具体 prompt、内部常量和版本差异仍回到 source
identity 对应的本文或源码，不能把机制卡当逐字实现。

### 1.2 机制阶段与证据

| 阶段 | 输入 | 状态/输出 | 可选性 | 一手出处 |
| --- | --- | --- | --- | --- |
| episode ingestion | message/json/text + reference time | EpisodicNode + episode provenance | 核心 | official README；`graphiti_core/graphiti.py::add_episode` |
| entity extraction | current + recent episodes | extracted EntityNode candidates | 核心 | `utils/maintenance/node_operations.py::extract_nodes` |
| entity resolution | candidates + graph | deduplicated nodes + summaries/attributes | 核心 | `resolve_extracted_nodes`、`extract_attributes_from_nodes` |
| fact extraction | episode + resolved nodes | EntityEdge candidates | 核心 | `utils/maintenance/edge_operations.py::extract_edges` |
| contradiction resolution | new + candidate existing edges | resolved/new/invalidated edges | 核心 | `resolve_extracted_edges` |
| temporal state | reference time + extraction | valid/invalid/expired fact windows | 核心 | official README；edge operations |
| provenance | episode/entity/fact | edge `episodes[]` lineage | 核心 | official README；`EntityEdge.episodes` |
| communities | graph nodes/edges | community summaries | optional | `update_communities`，public default false |
| basic retrieval | query + group | BM25/cosine edge candidates + RRF rank | public out-of-box path | `Graphiti.search` + `EDGE_HYBRID_SEARCH_RRF` |
| advanced retrieval | query + richer config | node/edge/episode/community + optional BFS/cross encoder | optional product capability | `Graphiti._search/search_` recipes |

### 1.3 paper/current/framework 三栏映射

| related Zep/Graphiti stage | current v0.29.3 source | framework main | 判词 |
| --- | --- | --- | --- |
| episode-based incremental graph construction | `add_episode()` 逐 episode await | 每 nonblank canonical turn 一次调用 | `PRODUCT_PATH_VERIFIED` |
| entity/fact extraction and graph evolution | public core node/edge operations | 未旁路、未自行写图 | `PRODUCT_PATH_VERIFIED` |
| bi-temporal fact invalidation | edge resolution + temporal fields | 原样保留；readout 显示 valid/invalid time | `PRODUCT_PATH_VERIFIED` |
| episode provenance | episodic/entity edges + `episodes[]` | sidecar 只把 UUID 映射回公开 turn id | `PRODUCT_PATH_VERIFIED` |
| hybrid retrieval | basic edge BM25+cosine+RRF；advanced recipes另存 | 只走 basic `search()`，center node=None | `PRODUCT_DEFAULT_VARIANT` |
| hosted context assembly / product response | Zep product层，OSS core不提供同一完整合同 | benchmark-owned answer builder | `NOT_ZEP_PARITY` |
| Zep paper benchmark readout | exact hosted payload未由 OSS source闭合 | 不复用论文数字/prompt | `IDENTITY_SEPARATED` |

current main 相对 basic OSS 只替换了公开 extension seams：LLM transport、embedding client、graph
driver 与 storage ownership；node/edge extraction、resolution、temporal invalidation和 basic search recipe
仍由 upstream 执行。替换 embedding 会改变候选集合与图状态，所以它是 controlled comparison identity，
不是“无影响的 runtime 参数”。

相关 Zep 论文描述 build 时最近 `n=4` 条 message 上下文；v0.29.3 current source 的
`RELEVANT_SCHEMA_LIMIT=10`。这是 paper→current 的实现漂移，不应把 paper 值倒灌进 current main，
也不应把 current 值误称论文参数。current main 沿 source 10，M11 将它纳入完整 source lock。

## 2. 官方 benchmark 覆盖

| benchmark | Zep paper报告 | Graphiti OSS公开 harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | 不用 Zep 论文身份替 Graphiti 盖章 | 无完整 build/search/answer/judge harness | N/A | framework extension | `N/A_AUTHOR` |
| LongMemEval | Zep paper有相关产品实验，但不是已证 OSS parity | v0.29.3 只有 graph-building quality eval | local file path only，revision未锁 | 逐 message add；candidate build vs baseline build 的 LLM判别 | `BUILD_ONLY / AUTHOR_QA_NOT_READY` |
| HaluMem | 无 Graphiti OSS author source | 无 | N/A | framework extension | `N/A_AUTHOR` |
| BEAM | 无 Graphiti OSS author source | 无 | N/A | framework extension | `N/A_AUTHOR` |
| MemBench | 无 Graphiti OSS author source | 无 | N/A | framework extension | `N/A_AUTHOR` |

current LongMemEval eval 的可复用事实只有：

- `episode_body=f'{role}: {content}'`；
- `reference_time` 来自对应 session date，并转 timezone-aware UTC；
- 每个 evaluation user 使用一个 group；
- 每条 message 串行 `await add_episode()`；
- baseline 和 candidate 的 `AddEpisodeResults` 由另一个 LLM 判断 candidate 是否更差。

它没有 query、top-k、final answer message、answer parser 或 benchmark judge。把这条 build-only anchor
称为 `author_longmemeval` 会把“建图单元一致”偷换成“完整实验可复现”，因此禁止。

此外，官方 build eval 自身有一处承重矛盾：

- `EvalAddEpisodeResults.candidate_is_worse` 的字段描述要求“baseline 更好时为 true”；
- prompt 却要求“baseline 更好时返回 false”；
- scorer 又以 `candidate_is_worse=True -> 0`、false -> 1 计候选分。

三者不可能同时成立。架构师已直接复核
`graphiti_core/prompts/eval.py:41-45,127-156` 与
`tests/evals/eval_e2e_graph_building.py:173-174`。因此它当前只可作为 ingest payload 和 eval
topology anchor，quality score 标 `JUDGE_CONTRACT_CONFLICT`；两份 subagent 回执均未主动发现该点，
也再次证明“调查回执不是验收判词”。

### 2.1 同 owner Zep experiments：可学习，但身份不同

`getzep/zep-papers@d7401e89325dd5e4bd1d52cf1bb47782caf84aef` 提供了 LoCoMo 与
LongMemEval 的 hosted pipeline。它有重要参考价值，但入口明确是 `zep_cloud.AsyncZep` 和
`api.getzep.com` / development hosted endpoint，不是 Graphiti OSS direct core：

| item | Zep hosted source | 为什么不升级为 Graphiti author profile |
| --- | --- | --- |
| LoCoMo search | nodes RRF top-20 + edges cross-encoder top-20，context含 entity summary与带事件时间 fact | 没有闭合 ingest source/data revision；产品 search scope 不同 |
| LoCoMo answer | GPT-4o-mini、temperature 0、system+user 两消息、时间解释 prompt | builder 依赖 hosted nodes+edges context，不是 basic edge RRF readout |
| LoCoMo judge | GPT-4o-mini structured `CORRECT/WRONG`，一次/题，分母硬编码1540 | method-owned hosted judge，不是 benchmark 主 judge |
| LME ingest | 只 ingest `single-session-assistant`，每 raw message 一次 hosted `memory.add`，content截8000 | 过滤后又遍历全500题，pipeline自身不完整；不是 OSS `add_episode` |
| LME search | question_date拼进query、query截255；edges cross-encoder 20 + nodes RRF 20 | 论文/hosted retrieval identity，不是 framework basic search |
| LME answer/judge | GPT-4o-mini answer；question-type judge，temperature 0 | 论文写 GPT-4o question-specific evaluation，与 notebook 仍有模型口径冲突 |

Zep 论文说明实验通过 Zep APIs、BGE-m3 embedding/reranking、nodes+edges top-20 形成 context，并在
AWS hosted Zep 上测 LME。这些选择针对作者产品效果与完整 context constructor；framework main 的
edge-only basic RRF + controlled MiniLM 针对跨十家控制变量。二者 estimand 不同，各自可能合理，
不能通过“与我们不同”直接否定 hosted 设计，也不能借 hosted 数字证明 OSS main parity。

## 3. Prompt / judge 合同

### 3.1 build prompts

Graphiti 的 method-owned prompt 是 entity extraction、node resolution/summary、edge/fact extraction、
duplicate/contradiction resolution 与 timestamp extraction 等内部 build prompts。它们位于
`graphiti_core/prompts/` 并由 `prompt_library` 调用；framework 没有改写模板，只通过 official
`LLMClient` seam 提供模型和结构化输出 transport。

这些 prompt 是算法 source identity，不是 benchmark final answer builder。当前
`GRAPHITI_SOURCE_FILES` 没有覆盖 prompt 目录和若干真实 consumer，导致局部 source hash 对未提交
prompt 漂移不完备；M11 必须扩锁。

### 3.2 final answer / judge

- Graphiti OSS current stable repo 没有 Phase 1 五格的完整 final answer builder。
- LongMemEval graph-building eval 的 `prompt_library.eval.eval_add_episode_results(...)` 是**建图回归
  judge**，比较 candidate `AddEpisodeResults` 与 GPT-4.1-mini baseline；它不是 LongMemEval QA judge。
- framework main 使用 benchmark-owned answer builder 与 judge，符合主表“只让 memory 变化”的
  estimand，但只能标 `framework main`，不能标 Graphiti author parity。
- `src/memory_benchmark/prompts/author/` 不应为 Graphiti 虚构模板；M10 候选裁决是五格均
  `AUTHOR_NOT_READY`。
- `zep-papers` 的 hosted builder/judge 作为 external provenance 保留；只有未来闭合同一 Graphiti
  OSS source、ingest/search context与dataset revision，才重新审议是否形成 author calibration。

## 4. 参数矩阵

| parameter path | upstream default | related paper/official role | current official effective | framework main | final consumer | 分类 | state/rebuild impact | 暂定裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `LLMConfig.model` | generic client fallback `gpt-4.1-mini` | build extraction/reasoning | LME build eval显式 GPT-4.1-mini | runtime profile 注入 | internal build prompts | model component | fresh graph rebuild | main runtime-controlled；author未就绪 |
| `LLMConfig.temperature` | `1.0` | build generation | eval未覆盖即沿 client default | `1.0` | LLM client payload | core stochastic build | fresh rebuild | 显式锁 upstream default |
| `LLMConfig.max_tokens` | `16384` | build response ceiling | eval沿 default | `16384` | LLM client/prompt calls | high-impact build | fresh rebuild | 显式锁 upstream default |
| structured output | OpenAI path依 client；generic default json_schema | extraction schema | LME eval用 OpenAI client | runtime选 json_object/json_schema | final chat payload | compatibility transport | provider identity；fresh build | manifest锁；不冒充算法值 |
| embedder provider/model | OpenAI `text-embedding-3-small` | candidate search + graph embeddings | LME eval沿 default | local MiniLM-L6-v2 | public `EmbedderClient` | controlled method component | fresh rebuild | main controlled；product-default补充候选 |
| embedding dimension | `EMBEDDING_DIM=1024` env default | vector index | eval沿 default | 384 | embedder/graph schema | build/index identity | fresh rebuild | main controlled identity |
| embedding normalization | provider/model dependent | cosine geometry | 未显式 | true | local encode | retrieval geometry | fresh rebuild | main显式锁 |
| `store_raw_episode_content` | true | source provenance | constructor default | true | EpisodicNode persistence | core provenance | fresh rebuild / metric资格 | 保留 |
| episode source | message default | conversation episode | eval `message` | `message` | add_episode | input identity | fresh rebuild | 保留 |
| `reference_time` | required | bi-temporal validity | session date | canonical source time | add_episode | core temporal input | fresh rebuild | 缺失时fail-fast，不造时 |
| `group_id` | provider default if None | graph partition | one evaluation user+suffix | physical conversation root内固定 DB group | graph driver | isolation/topology | fresh rebuild | main更强物理隔离；非author parity |
| add ordering | docs要求 sequential await | incremental evolution | LME eval逐 message await | 逐 turn await | add_episode | core invocation topology | fresh rebuild | 保留 |
| recent episode context | internal source default | extraction context | 未覆盖 | upstream internal | retrieve_episodes | source-locked core | fresh rebuild | 不暴露 TOML，纳 source hash |
| `update_communities` | false | optional community layer | eval省略=false | false | add_episode | optional build stage | fresh rebuild | off，因basic edge readout不消费 |
| custom entity/edge types | None | optional ontology | eval None | None | extraction/schema | optional topology | fresh rebuild | 不为五格强造 schema |
| custom extraction instructions | None | optional task steering | eval None | None | build prompt | optional topology | fresh rebuild | 禁止 benchmark 特判 |
| `max_coroutines` | source env default20；README声称10 | throughput，不改依赖图目标 | eval未显式 | 10 | `semaphore_gather` | execution + possible API concurrency | same semantics；cost/ordering risk | main显式10；记录doc/source冲突 |
| basic search recipe | edge BM25+cosine+RRF | hybrid retrieval | LME build eval不检索 | same | `Graphiti.search` | core retrieve | retrieval rerun | 保留 out-of-box recipe |
| `num_results` | 10 | result depth | N/A | query top_k，上限20 | search config limit | readout | rerun retrieval | query-owned；上限进identity |
| center node | None | optional graph-proximity rank | N/A | None | recipe selection | optional retrieve topology | rerun retrieval | off；不暗切 node-distance |
| search filter | empty default | optional temporal/type filters | N/A | empty | search | readout policy | rerun retrieval | 不做 benchmark gold/time cutoff |
| cross encoder | constructor default OpenAI reranker存在 | advanced recipe capability | N/A | fail-fast unused sentinel | only advanced recipe | dormant capability | new retrieval identity | basic main不得调用 |
| raw source rendering | official eval `role: content` | episode semantics | LME `role: content` | public speaker/role + rendered content | episode_body | input contract | fresh rebuild | 五格保持可审计 speaker/time/image政策 |

第三方/作者 per-dataset 参数与本项目跨五格固定值回答不同问题。若某个框架按 dataset 调 search recipe、
embedding 或 schema，它可能是在追求“每格作者最佳有效实现”，而非设计错误；本项目 main 固定值追求
控制变量。未来若找到一手 author effective values，应放入稀疏 `author_<benchmark>`，不需要靠否定
第三方目标来维护 main。

## 5. 配置流与强反例

- TOML → typed config：`configs/methods/graphiti.toml` → `GraphitiConfig`，unknown key/type 由统一
  profile loader 与 dataclass validation 拒绝。
- typed config → worker：registry 注入 runtime model/transport/execution scope；adapter initialize
  payload 将 model、temperature、max tokens、embedding、query limit、max coroutines 传入 worker。
- worker → product：`Graphiti(graph_driver=..., llm_client=..., embedder=...,
  cross_encoder=sentinel, store_raw_episode_content=True, max_coroutines=10)`。
- ingest final payload：`name=turn_id`、`episode_body=rendered public turn`、source description固定、
  timezone-aware reference time、source=message、physical DB内固定 group、communities=false。
- retrieve final payload：`query`、当前 group、`num_results=query.top_k`；basic RRF recipe，LLM 调用必须
  为零，embedding 调用必须被观测。
- controlled embedder 用 official `EmbedderClient` seam；384/normalize/model path 任何变化都改变
  graph build identity并要求 fresh state。
- cross encoder sentinel 是漂移守卫：若 basic recipe将来静默改用 cross encoder，必须 fail-fast，
  不能在未观测的情况下继续跑。

## 6. 主配置与作者配置裁决

### 6.1 framework main

当前 main 的合理目标是：使用 Graphiti OSS out-of-box basic graph memory algorithm，在十家 controlled
embedding、统一 benchmark answer/judge 下比较 memory quality。它不是 source-default reproduction，
但其公开 seam 替换不会跳过 entity/fact/temporal graph 核心阶段。

### 6.2 author / product-default

- `author_longmemeval`：`AUTHOR_NOT_READY`。只有 build payload anchor，没有完整 search/answer/judge、
  dataset revision 和 exact result identity。
- 其余四格：`N/A_AUTHOR`。
- `product_default` 可在未来作为补充 profile：OpenAI text-embedding-3-small/1024 + basic RRF；需要
  fresh graph，且不得与 controlled main 分数直接混比。
- Zep paper/hosted profile：不能靠 Graphiti TOML 表达；source/product identity 未闭合，禁止建立。

### 6.3 topology variant

Zep hosted Context Graph、Graphiti MCP/server queue、direct core、basic search与advanced search不是同一个
名字下可随意互换的 payload。当前 direct core保留核心算法且提供精确完成门，避免 MCP/host transport
成为额外变量；它不因此获得 hosted product parity。

## 7. Manifest / resume / artifact

- 必须进入 build identity：upstream commit、完整算法 source hash、adapter/worker/bootstrap、LLM
  provider/model/structured-output contract、temperature/max tokens、embedding全 identity、raw episode、
  group/storage topology、communities/ontology/instructions、max coroutines。
- 必须进入 retrieval identity：search recipe、center/filter policy、query limit、cross-encoder unused
  contract、formatted-memory版本、lineage/provenance contract。
- 任一 build identity 变化要求 fresh graph；仅 answer/judge变化可从 artifact重评，但不得改写旧 manifest。
- secret/base URL 不落 artifact；private gold/question answer 不可达 Graphiti。
- 旧 artifact 按自己的 source/runtime manifest 只读回放，不能因 M11 扩 source lock而重标成新 identity。

## 8. 未闭合项与停工点

| item | status | 已查范围 | M11/后续动作 |
| --- | --- | --- | --- |
| Graphiti OSS独立 paper identity | `N/A / RELATED_ZEP_PAPER` | official README + arXiv identity | 机制可引用，结果不借用 |
| Phase1 author final builder | `SOURCE_UNAVAILABLE` | current stable repo/evals/docs | 不建 author section |
| LME dataset revision | `PENDING` | eval只有相对数据路径 | 若做作者build校准再锁数据 |
| current remote algorithm drift | `REVIEW_REQUIRED` | stable vs remote main commit/compare | 升级另开source review，不在M11偷换 |
| complete source lock | `INCOMPLETE` | 当前11-file list | 扩到真实 prompt、operations、search、queries/helpers消费者 |
| product-default calibration | `OPTIONAL` | upstream constructor/search defaults | controlled main不阻塞；若运行则fresh build |
| Zep hosted parity | `SOURCE_UNAVAILABLE` | public OSS与paper边界 | 不宣称、不伪造 |
| official build eval polarity | `CONFLICT` | response model/prompt/scorer三锚 | 不用其分数证明算法质量 |
| MiniLM revision/tokenizer lock | `LOCAL_UNPINNED` | build identity当前显式如此 | M11锁revision/hash/tokenizer或保持pending |

当前 `GRAPHITI_SOURCE_FILES` 至少漏掉下列承重消费者：

- `graphiti_core/utils/maintenance/{node_operations,edge_operations,combined_extraction}.py`；
- `graphiti_core/utils/bulk_utils.py` 与 graph persistence helpers；
- `graphiti_core/prompts/**`；
- `graphiti_core/search/{search,search_config,search_filters}.py`；
- graph query/driver operation consumers；
- LLM/embedder config/default 与 model schema；
- worker实际依赖的 FalkorDB Lite/runtime glue。

git commit pin能识别 committed upstream版本，但当前局部 hash不能发现这些文件的工作树漂移。M11应优先
改成可维护的 tracked-source lock或扩完整清单，而不是手抄又一份脆弱的少量列表。

## 9. 验证记录

- 两份候选回执：一份负责 mechanism/source/config，一份负责 official benchmark/prompt/Zep hosted
  identity；均提供 claim→evidence→边界→pending 和可定位源码/URL，收据门通过。
- 架构师亲核：local pin/remote/release、`add_episode` node/edge/temporal call path、basic RRF search、
  LME build eval、Zep paper、hosted LoCoMo/LME最终 payload。额外发现两份回执都漏掉的 official eval
  polarity conflict，并据此把 build eval 从“质量证据”降为“payload/topology anchor”。
- M10 directed zero-API command：
  `uv run pytest -q tests/test_graphiti_adapter.py tests/test_graphiti_worker.py
  tests/test_graphiti_registered_prediction.py tests/test_config_profiles.py
  tests/test_method_registry.py tests/test_documentation_standards.py tests/test_codex_project_hooks.py`。
- directed tail：`217 passed in 16.22s`。
- `git diff --check`：在 M10 稳定页/状态回填后统一执行。
- 架构验收：

```text
M10_EVIDENCE_COMPLETE
GRAPHITI_OSS_COMMIT_IDENTITY_LOCKED
RELATED_ZEP_PAPER_AND_HOSTED_IDENTITY_SEPARATED
FRAMEWORK_BASIC_RRF_CONTROLLED_MAIN_VALID
OFFICIAL_LME_BUILD_PAYLOAD_ANCHOR_ONLY
OFFICIAL_BUILD_EVAL_JUDGE_CONTRACT_CONFLICT
AUTHOR_NOT_READY
SOURCE_LOCK_SCOPE_REVIEW_REQUIRED
MINILM_REVISION_LOCAL_UNPINNED
REMOTE_SOURCE_DRIFT_REVIEW_REQUIRED
```
