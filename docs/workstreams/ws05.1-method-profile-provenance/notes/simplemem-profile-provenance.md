# SimpleMem profile provenance（M6）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M6 一手证据，不改写成新 run 收据。

> 判词：`M6_EVIDENCE_COMPLETE / CURRENT_PRODUCT_SOURCE_LOCKED /
> PAPER_CURRENT_IMPLEMENTATION_VARIANT / FRAMEWORK_SERIAL_MAIN_VALID /
> PAPER_AUTHOR_SOURCE_UNRESOLVED / REPO_EVAL_LOCOMO_VARIANT /
> AUTHOR_NOT_READY / SOURCE_DRIFT_REVIEW_REQUIRED`。
>
> 本文分开记录论文、作者公开 LoCoMo harness、current product 与 framework main。论文把
> compression、online semantic synthesis、intent-aware retrieval 都定义为核心阶段；current
> product 保留相近的三段拓扑，但窗口、索引、检索深度和 synthesis 的具体实现并不与论文逐项
> 等价。本批只完成证据与裁决，不修改 TOML、adapter、第三方源码或 prompt registry，也不调用
> 真实 API。

## 0. 身份与范围

- method：SimpleMem（`aiming-lab/SimpleMem` 的 text product；不把后续 EvolveMem 或其他同 owner
  工程混成论文 identity）。
- 审计日期：2026-08-25。
- paper：`SimpleMem: Efficient Lifelong Memory for LLM Agents`，arXiv
  `2601.02553v3`，14 页；本机 local-only PDF：
  `third_party/methods/SimpleMem/Liu 等 - 2026 - SimpleMem Efficient Lifelong Memory for LLM Agents.pdf`，
  SHA-256=`8752aa223e004ca286995bc1e8cbde8e89e67ad3aeb9ba0266f3ccab3cc11078`。
- framework product source：`aiming-lab/SimpleMem@60a48e83a7fef10d386e1f438589047d3a4257bc`
  + `scripts/patches/simplemem-product-compat.patch`，patch SHA-256=
  `77606efb5a1d24bbf6aa6d8227cab6044b8c8ed17ea1d29798608346d30ea8d2`。
- framework current identity：vendored text files=
  `2c9653d20b04bfceca2da54f19bf78279d79cf80d085d51e0c72c8314ae6333d`；wrapper=
  `4ad61ed5f42fc3d6442d6e9276c9e66822bb6151ec3c2df0d92b80f0c4a87f18`；组合
  `source_sha256=612d2f65d128f74bbc934f34fd22440d80e3f6518a260895df9870d83193589a`。
  组合 hash 反映最终 patched bytes，但当前 schema 没有单独落 upstream commit 与 patch hash，M11
  仍须补齐可解释 identity。
- current upstream：2026-08-25 `main=db80b6a7c591e0ea730a058e9f5fc4eb06572299`；最新公开
  tag `v0.3.0=c830efa3fd2614bc4eb0b4a80bc5836ece9ded96`。framework pin 已落后；current
  增加 dense-vector backend、Omni/MCP/security 等能力，升级前必须作 text product 差量审计，不能
  只凭版本号 fast-forward。
- license：repo `LICENSE` 与 README 声明 MIT；`setup.py` classifier 却写 Apache，属于 package
  metadata 冲突。项目以实际 LICENSE 为 source license，并保留冲突披露。
- official evaluation：锁定 repo 只公开完整 `test_locomo10.py` text harness。论文报告
  LongMemEval-S，但该论文 text pipeline 的完整公开 LME runner/source identity 没有找到；后续
  EvolveMem 的 LME/MemBench 支持只能列为同 owner extension。
- 本次不覆盖：真实效果复现、current-upstream 升级、LanceDB 真实版本/索引重建、参数 sweep、
  author profile 注册、method judge 进入主表或对旧 artifact 重新标注。

## 1. 算法机制先行

### 1.1 论文阶段图

| 阶段 | 输入 | 状态/输出 | 是否可选 | 一手出处 |
| --- | --- | --- | --- | --- |
| Semantic Structured Compression | 对话滑窗、即时历史与 speaker/time | 去指代、去线性化、带实体/topic/time/salience 的 context-independent memory units；低密度窗口可为空 | 核心 | paper §2.1、Appendix prompt |
| Online Semantic Synthesis | 当前 session observations + 已有语义上下文 | `F_syn` 聚合 related fragments，形成更高密度 abstraction | 核心 | paper §2.2、消融 |
| Multi-view Indexing | synthesized memory units | dense semantic、sparse lexical、symbolic metadata 三视图 | 核心 | paper §2.2-§2.3 |
| Intent-Aware Retrieval Planning | query + history | semantic/lexical/symbolic queries 与 adaptive depth，再三路检索、union、去重 | 核心 | paper §2.3、planner prompt |
| Reconstructive Readout | retrieved abstracts/details + question | 处理时间冲突并生成答案 | answer 阶段核心；不属于 memory build | paper Appendix readout prompt |

论文消融把 synthesis 与 retrieval planning 都当作方法贡献；因此不能因为 current source 暴露开关或
默认值，就在 framework main 中关闭它们后仍称“完整 SimpleMem”。

### 1.2 current source 对应关系

| 论文阶段 | current module/function | 控制参数 | 版本漂移/缺失 | 判词 |
| --- | --- | --- | --- | --- |
| compression | `MemoryBuilder.process_window()` → `_generate_memory_entries()` | window/overlap、LLM | current prompt 强调完整覆盖，不存在论文式显式 density threshold；parser仍接受空 list | `IMPLEMENTATION_VARIANT` |
| online synthesis | extraction prompt 的 `previous_entries` 上下文 + 新 entry append | serial/parallel build、previous context | 没有独立 update/merge/delete existing entry 的 consumer；作者把 2026-02 的 previous-context 实现称 Stage 2，但它不是论文公式的逐项可证复刻 | `IMPLEMENTATION_VARIANT` |
| multi-view index | `VectorStore.add_entries()` 与 semantic/keyword/structured search | embedding、LanceDB/FTS | 论文 Qwen/BM25/IVF-PQ；main MiniLM/native FTS/未显式 IVF-PQ | `CONFIG_AND_BACKEND_VARIANT` |
| planner | `HybridRetriever._retrieve_with_planning()` | planning、reflection、三路 top-k | current 两段 planner、固定 25/5/5、最多 4 semantic queries；没有论文 query-dependent depth `d` | `IMPLEMENTATION_VARIANT` |
| reflection | completeness check → missing query → semantic retry | true、rounds=2 | 论文没有独立 reflection stage/round 参数 | `CURRENT_PRODUCT_EXTENSION` |
| readout | native `AnswerGenerator` / framework `formatted_memory` | answer builder | framework main 不走 `ask()`，由 benchmark builder 统一回答 | `FRAMEWORK_READOUT_BOUNDARY` |

“current source 没有独立 merge consumer”不能缩写成“SimpleMem 没有 Stage 2”：论文与作者 commit 都把
previous-context 方案称为 Stage 2；准确说法是 **paper formulation 与 current concrete
implementation 不完全等价**。

### 1.3 串行窗口为何是 main 的必要裁决

`add_dialogue()` 达到窗口阈值后同步处理；`process_window()` 以
`step=window_size-overlap_size` 前进，并把刚生成的 entries 作为下一窗口
`previous_entries`。这形成窗口 1 → 窗口 2 的因果链。

`add_dialogues_parallel()` 虽然切出相同 overlap 窗口，但所有 futures 在提交时共享旧的
`previous_entries`；结果又按 `as_completed()` 顺序聚合，最后 10 条 completion-order entries 成为
后续上下文。因此并行不仅是速度开关，还会改变 build dependency 与写入顺序。

framework 每个 canonical turn 调 `add_dialogue()`，并显式
`enable_parallel_processing=false`。这是为了保留 current product 的串行因果链，而不是为了省事；
retrieval multi-query parallelism 不改变 memory build，继续启用。

## 2. 官方 benchmark 覆盖

| benchmark | 论文报告 | 公开 harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | 是 | `test_locomo10.py` | repo/CLI 指定 LoCoMo10；未单独锁 dataset hash | session 排序；原 speaker、session timestamp；全部 Dialogue 一次 `add_dialogues()`，最后 finalize | `PUBLIC_IMPLEMENTATION_VARIANT` |
| LongMemEval | 是，S split | 锁定 text repo 无完整 runner | paper dataset 说明 | paper 只给 prompt/参数片段，最终 ingestion/answer/parser source 不完整 | `PAPER_REPORTED_SOURCE_UNAVAILABLE` |
| HaluMem | 否 | 无 | N/A | framework extension | `SOURCE_UNAVAILABLE` |
| BEAM | 否 | 无 | N/A | framework extension | `SOURCE_UNAVAILABLE` |
| MemBench | 否 | 原始 text repo 无；后续 EvolveMem 有 extension | extension dataset | 不属于论文 text identity | `LATER_OFFICIAL_EXTENSION` |

### 2.1 LoCoMo harness 与 framework main 的目标差异

官方 LoCoMo harness 一次构造全部 `Dialogue` 并调用 `add_dialogues(dialogues)`；在 repo default
`enable_parallel_processing=true` 且数据量超过阈值时，会进入并行窗口。framework main 逐 turn
调用 `add_dialogue()` 并关闭 build parallel，保留因果链。两者是 topology variant，不能用同一
TOML 数字掩盖。

图片格式也不同：官方写 `[Image: caption] text`；framework 统一用
`[Sharing image that shows: caption]`，目的是跨 method 保持同一无损 caption contract。它是 main
controlled input policy，不冒充 author byte parity。

## 3. Prompt / judge 合同

### 3.1 LoCoMo normal answer

- template/source：current `SimpleMemSystem.answer_generator.generate_answer()` 与
  `test_locomo10.py` 的调用路径。
- variables：public question + retrieved `MemoryEntry` list；不需要 gold/evidence。
- final messages：native `AnswerGenerator` 组装一条 system + 一条 user message，user message包含
  memories 与 question。
- decode：normal answer `temperature=0.1`；JSON mode 是否发送由产品
  `USE_JSON_FORMAT` 控制，默认 false；没有最终可重放的 paper-only model payload identity。
- parser：若返回 JSON，读取 `.answer`；兼容普通文本/产品 parser。
- framework main：不走 native `ask()`，只取 `formatted_memory`，由 benchmark LoCoMo builder
  统一回答；因此 native prompt 只可用于显式 author calibration。
- 裁决：模板和 current repo 调用可重建，但 build topology、paper parameters、source identity 与
  image format未闭合为 paper exact，故 `AUTHOR_NOT_READY`。

### 3.2 LoCoMo category 5 与 judge 隐私边界

- category 5 单独提高 answer temperature 到 0.5、关闭 reflection，并把私有
  `adversarial_answer` 与 “Not mentioned…” 随机排列成选项。
- `adversarial_answer` 是 gold-derived private label，若进入 answer builder 会破坏主表隐私边界；
  所以这条 author harness 路径只能登记，不能注册进 framework main 或 author profile。
- optional method judge 使用 question/reference/prediction，temperature=0.3，可选 JSON；它是 method
  harness 的 metric 资产，不会自动替换 benchmark 主 judge。

### 3.3 LongMemEval

- paper 附录提供 LME judge prompt，并报告 GPT-4.1-mini、temperature=0 等配置片段。
- 公开 text repo 没有闭合 ingestion、final `PromptMessage[]`、decode、parser 与重复策略的完整
  LongMemEval-S runner。
- 后续 EvolveMem 的 LME support 是同 owner extension，不能反向冒充原始论文 author harness。
- 裁决：`SOURCE_UNAVAILABLE / AUTHOR_NOT_READY`，不创建半成品 `author_longmemeval`。

## 4. 参数矩阵

| parameter path | upstream default | paper role | official effective values | current main | call site/最终 payload | 分类 | state/rebuild impact | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| source | checkout 60a48e8 | 未给 exact commit | repo current harness | 60a48e8+patch | source identity/factory | topology | 变更需全量重建 | 当前 pin 保持，升级 M11 审 |
| window size | 40 | 20 turns | current harness沿产品设置 | 40 | `MemoryBuilder` | core build | fresh rebuild | current-product main |
| overlap/stride | overlap=2、step=38 | 表写 stride=5，同时写 25% overlap；两种文字有歧义 | current harness沿产品设置 | overlap=2 | `process_window()` | core build | fresh rebuild | 不伪造 paper exact |
| build parallel | true/workers16 | 未报告 | official LoCoMo batch可能触发 | false | `add_dialogue(s)` | topology | fresh rebuild | main保留串行因果链 |
| previous context | 上一窗口前3条；parallel末10条 | synthesis context核心 | 随 topology | serial previous entries | extraction prompt | core build | fresh rebuild | active |
| embedding | Qwen3-0.6B/1024 | Qwen3-0.6B/1024 | repo default | MiniLM/384/internal-L2 | VectorStore schema/search | controlled build | fresh rebuild | main controlled variant |
| semantic top-k | 25 | overall retrieval k约3-20 | repo current 25 | 25 | semantic search | retrieval | rerun retrieval | current product value |
| keyword top-k | 5 | separate n未公开 | 5 | 5 | native FTS | retrieval | rerun retrieval | current product value |
| structured top-k | 5 | separate n未公开 | 5 | 5 | metadata filter | retrieval | rerun retrieval | current product value |
| planning | true | 核心 | true | true | query planner | core retrieval | rerun retrieval | 必须保持开启 |
| reflection | true | 无独立论文参数 | true | true | completeness/missing query | product extension | rerun retrieval | 保留current product，非paper值 |
| reflection rounds | 2 | 未报告 | 2 | 2 | reflection loop | retrieval | rerun retrieval | current product value |
| retrieval parallel | true/workers8 | 三路并行 | true | true | semantic/reflection futures | runtime+ordering | rerun retrieval | active；ranking pending |
| build LLM | GPT-4.1-mini | GPT-4.1-mini/temp0 | current code固定不同 callsite temperatures | runtime profile model；extraction temp0.1 | `LLMClient.chat_completion` | build | fresh rebuild | runtime variant需 manifest |
| planner LLM | 同一产品 model | GPT-4.1-mini | callsite temp0.1-0.3 | runtime profile model | hybrid retriever | retrieval | rerun retrieval | runtime variant |
| JSON/streaming | JSON false、streaming true | strict JSON schema | harness沿 repo | adapter未改产品 bool | LLM request | build/runtime | 相关 stage重跑 | source-locked；别用未消费配置冒充 |
| Lance lexical/index | native FTS；版本 lower bound | BM25 + LanceDB 0.4.5 IVF-PQ | current repo | compatibility-patched native FTS | VectorStore | backend | fresh rebuild | implementation variant |
| final query top-k | product hybrid结果 | paper adaptive range | harness按调用 | framework `query.top_k` 最后截断 | adapter | readout | rerun retrieval | 不等同三路 top-k |

数值型参数也可能是算法语义；bool 也可能只是 runtime。上表按最终消费者与状态影响分类，不按数据类型
裁决。

## 5. 配置流与强反例

- TOML → typed config → product：`configs/methods/simplemem.toml` 由 registry/factory 校验，再写入
  SimpleMem settings 与构造器；主配置为 W40/O2、25/5/5、planning/reflection on、build serial、
  retrieval parallel。
- unknown/type validation：现有 config schema 对未知字段 fail-fast；M11 需保持，不用任意 dict
  把 paper/current 两种 identity 混在一起。
- dead/overridden config：`MAX_TOKENS` 没进入现行 LLM request；`structured_output_mode` 也不能
  直接证明产品 `USE_JSON_FORMAT` 已开启。M11 应删除或更正假控制面。
- build parallel mutation：切 true 不只是吞吐变化；会让各窗口共享旧 context，并按完成序写入，
  必须作为 topology identity。
- missing time：`timestamp=None` 从 adapter → Dialogue → extraction/storage/readout 合法保留；不回填
  wall clock。
- finalize：只 flush residual buffer；HaluMem session boundary 另清 `previous_entries`，不清 LTM。
- embedding identity：controlled MiniLM/384 改变 schema/vector，任何切换都要求 fresh state。

## 6. 主配置与作者配置裁决

### 6.1 framework main

保留 current product 的 compression/planning/reflection，统一 controlled MiniLM，并显式关闭 build
parallel，原因是当前 adapter 的逐 turn 输入应保持窗口间 previous-context 因果链。五 benchmark 共用
一份主算法配置；benchmark 差异只在公开输入 shape、answer builder 与 metric eligibility。

### 6.2 author 候选

- `author_locomo`：只有在同时闭合 repo exact topology、paper/current 参数身份、native final
  messages/parser 与私有 category-5 隔离后才可注册；当前 `AUTHOR_NOT_READY`。
- `author_longmemeval`：完整 public runner/source identity 不可得，当前不创建。
- HaluMem/BEAM/MemBench：原始 SimpleMem text repo未报告，保持 framework extension。

### 6.3 topology variant

official LoCoMo 的 batch `add_dialogues()`/可能 parallel 与 main per-turn serial 不是普通 TOML 数值差异；
category-5 gold-derived routing也不是 prompt 文件选择。未来 author calibration 必须显式命名 topology，
不能暗中按 benchmark 自动切换。

## 7. Manifest / resume / artifact

- build identity 必须包含：upstream commit、patch hash、effective source hash、window/overlap、build
  parallel、embedding完整身份、build model与产品请求模式。
- retrieval identity 必须包含：planning/reflection/rounds、三路 top-k、retrieval parallel、最终 query
  top-k、检索模型/runtime。
- upstream/patch/window/embedding/build-model 变化要求 fresh-state rebuild；只改 answer builder 或
  evaluator可从保存完整公开 output 的 artifact重算，但必须生成新 evaluation identity。
- 旧 artifact按其 manifest只读回放；不得把 60a48e8+patch 的结果重标为 current upstream或paper run。
- gold、evidence、adversarial answer、judge label只在 evaluator-private侧；method ingest/retrieve、
  planning/reflection都不可达。

## 8. 第三方框架：先还原目标，再裁决

### 8.1 MemEval

它显式把所有 system 的 embedding统一为 `text-embedding-3-small/1536`，并统一 LLM；目标是控制
模型能力差异、突出 memory system差异。这个目标与本项目 controlled main高度相容，不能因为它
不是 author default就判错。

其代价是：SimpleMem只沿 product default运行其他高影响参数；缺时间时写当前 wall clock；native
answer coupling也削弱了 source-time 与 reader公平性。因此我们借鉴“共同 embedding”的实验设计，
但保留 missing time=None、framework answer边界和逐字段 provenance。

### 8.2 MemoryData

它把大量 SimpleMem参数显式放入 YAML（W8/O2、Qwen3-4B/2560、25/5/5、planning/reflection、
build/retrieval parallel），目标是让跨方法实验、消融和部署覆盖可见、可改。它还用 sidecar补 source
mapping，这是值得借鉴的可审计设计。

代价是 method/runtime/evaluation配置混在一份文件、时间被替换为运行时 wall clock、一些算法参数按
profile变化。我们的选择不是“证明 YAML错”，而是保留其显式配置和 sidecar优点，同时继续用类型较
浅的 TOML ownership分层，且不伪造 source time。

## 9. 未闭合项与验证记录

| item | status | 已查范围 | 下一条一手证据 |
| --- | --- | --- | --- |
| paper结果对应 exact source | `UNRESOLVED` | paper、repo历史、tags/current harness | 作者发布 commit/artifact |
| original text LongMemEval-S runner | `SOURCE_UNAVAILABLE` | 锁定repo、EvolveMem扩展 | 作者公开原 runner |
| paper `F_syn` 与 current previous-context等价性 | `IMPLEMENTATION_VARIANT` | memory builder、history commit、paper公式 | 作者实现说明/对应 source |
| LanceDB 0.4.5 IVF-PQ/BM25 exact runtime | `UNRESOLVED` | setup lower bound、current VectorStore、compat patch | lockfile/index creation artifact |
| current upstream upgrade | `PENDING_M11` | remote main/tag与 text差量入口 | 逐文件算法差量 + mutation |
| complete source identity | `PENDING_M11` | current hash function与 patch | pin/patch/package files进入manifest |
| author LoCoMo profile | `AUTHOR_NOT_READY` | public harness、native answer/judge | topology/source/final payload强反例 |

验证命令：

```text
uv run pytest -q tests/test_simplemem_adapter.py \
  tests/test_simplemem_registered_prediction.py \
  tests/test_config_profiles.py tests/test_method_registry.py \
  tests/test_documentation_standards.py tests/test_codex_project_hooks.py
git diff --check
```

真实尾行：`192 passed in 4.38s`；`git diff --check` clean。

架构验收边界：两路 Luna/max 只读调查提供候选 claim-evidence；架构师已独立抽查
`MemoryBuilder`窗口/previous-context、`HybridRetriever`合并顺序、官方 LoCoMo
`add_dialogues/category-5`、主 TOML与 source identity。未使用 agent结论替代 current source。
