# A-Mem profile provenance（M2）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M2 一手证据，不改写成新 run 收据。

> 判词：**`M2_EVIDENCE_COMPLETE / PRODUCT_SOURCE_RULING_REQUIRED /
> AUTHOR_NOT_READY`**。本批只闭合论文机制、三套官方 source identity、LoCoMo harness 与
> effective 参数；不更换产品源码、不注册 author profile、不调用真实 API。

## 0. 身份与范围

- method：A-Mem / A-MEM。
- 审计日期：2026-08-24。
- paper identity：*A-Mem: Agentic Memory for LLM Agents*，arXiv:2502.12110v11，
  2025-10-08，NeurIPS 2025；本地 28 页 PDF SHA-256
  `fec32b521c4a1f793442bf1aeb26139c583078350d1cd4ab8f4eccc54a0694f0`。
- official evaluation source：当前公开仓库 `WujiangXu/A-mem@0c8039f28fdcc08189a23c07a3437d9d2482f9c2`
  （旧 URL `WujiangXu/AgenticMemory` 会重定向），MIT；本地
  `third_party/methods/A-mem` 与该 revision 逐文件一致，额外项只有本地 PDF、`.DS_Store`
  和 `__pycache__`。
- current framework product source：`agiresearch/A-mem@ceffb860f0712bbae97b184d440df62bc910ca8d`，
  MIT；本地 `third_party/methods/A-mem-product` 与该 revision 逐文件一致（忽略
  `__pycache__`）。
- paper-linked product source：PDF v11 明确链接
  `WujiangXu/A-mem-sys@f303dfc71e07bdc787f4bc135d4cea328ae30e99`，MIT。它与上条不是
  URL 别名，而是行为不同的 source tree；本批只读下载到临时目录对表，未纳入项目 vendor。
- 本次不覆盖：真实模型结果复现、DialSim 数据/评测恢复、产品源码迁移、author builder 注册、
  A-Mem qrel metric 资格重判及任何参数 sweep。

### 0.1 为什么必须分成三种 identity

论文首页把 benchmark code 指向 `WujiangXu/AgenticMemory`、production code 指向
`WujiangXu/A-mem-sys`；当前 production README 又把论文复现引回 benchmark repo，且
`A-mem-sys` 的 package metadata/clone 示例仍写 `agiresearch/A-mem`。这些交叉链接只能证明
同一项目谱系，不能证明代码等价。

逐函数对表确认至少有四个算法承重差异：

1. `agiresearch/A-mem` 的 `find_related_memories()` 返回 Chroma 命中在结果数组中的位置
   `0..k-1`，随后 `process_memory()` 把它当成全局 memory list 下标更新；
   `A-mem-sys` 返回真实 memory id，并按 id 更新命中邻居。
2. `agiresearch/A-mem` 的 Chroma document 只嵌入 `note.content`；`A-mem-sys` 把
   content、context、keywords、tags 合成 enhanced document 后嵌入，更接近论文的结构化 note
   检索描述。
3. `A-mem-sys.add_note()` 会在 metadata 缺失时自动执行 LLM note analysis；
   `agiresearch/A-mem.add_note()` 不会。当前 framework wrapper 为后者显式先调
   `analyze_content()`，因此当前 profile 可运行，但调用拓扑属于 wrapper 组合身份。
4. 两者 LLM controller 的公开 backend/默认 temperature 已漂移（`.7` 与 `1.0`），不能只凭
   “当前更新”决定谁代表论文实验。

因此 M11 前不得把 current framework product 写成“论文实现”，也不得只因
`A-mem-sys` 是论文最新链接就静默替换：源码迁移会改变 build memory 与检索排序，必须重建并
重新跑五格门。

## 1. 算法机制先行

### 1.1 论文阶段图

| 阶段 | 输入 | 状态/输出 | 是否可选 | 一手出处 |
| --- | --- | --- | --- | --- |
| note construction | 原始 experience/content + time | content、timestamp、LLM context/keywords/tags、embedding、links 的 atomic note | 否 | paper §3.1、Appendix B.1 |
| candidate retrieval | 新 note embedding | top-k historical candidate notes | 否 | paper §3.2 |
| link generation | 新 note + candidate notes | LLM 决定有意义的 links | 论文核心 | paper §3.2、Appendix B.2 |
| memory evolution | 新 note + linked/neighbor notes | 更新新 note links/tags，并可更新旧 note context/tags | 论文核心 | paper §3.3、Appendix B.3 |
| query retrieval | query embedding | cosine top-k current notes/related memory context | 否 | paper §3.4 |
| answer generation | question + retrieved memory | task answer | benchmark harness | paper §4、eval harness |

论文 Table 3 的消融分别移除 Link Generation 与 Memory Evolution，二者都影响效果；因此不能把
“能存入 Chroma、能向量检索”误判成完整 A-Mem。论文阶段图还说明 evolution 后的 current note
不是 raw turn 的无损副本，这与当前 retrieval qrel=N/A 裁决一致。

### 1.2 current source 对应关系

| 论文阶段 | current framework/product 调用 | 控制参数 | 漂移/缺失 | 判词 |
| --- | --- | --- | --- | --- |
| note construction | wrapper `analyze_content(content)` → `add_note(..., **analysis)` | build LLM、embedding model | wrapper 补上 org product 不自动执行的 analysis | `CONFIGURED_WRAPPER_TOPOLOGY` |
| candidate retrieval | `process_memory()` → `find_related_memories(..., k=5)` | hardcoded 5 | 未暴露；org product 有 positional-id bug | `SOURCE_RULING_REQUIRED` |
| link generation | `process_memory()` evolution prompt，action=`strengthen` | build LLM | 仍会运行；非法/错位 id 风险取决于 source | `CORE_STAGE_ACTIVE` |
| memory evolution | `process_memory()` action=`update_neighbor` | build LLM；`evo_threshold=100` | threshold 只控制 periodic reindex，不控制是否 evolution；org product 更新目标可能错位 | `CORE_STAGE_ACTIVE_BUT_SOURCE_AMBIGUOUS` |
| index/reindex | Chroma `add_document()`；每 100 次 positive evolution `consolidate_memories()` | MiniLM；evo threshold 100 | org product content-only；paper-linked product enhanced content | `SOURCE_VARIANT` |
| main query retrieval | `search_agentic(query, k)` | `retrieve_k` | framework 用 product public API；非论文 eval `find_related_memories_raw()` | `CONTROLLED_MAIN` |
| author query/answer | adapter legacy Question path | query LLM、category prompt、k | 尚未注册；system role、产品 engine 与 official harness 不同 | `AUTHOR_NOT_READY` |

### 1.3 robust harness 不是无害 parser 替换

当前 README 推荐 `test_advanced_robust.py` 兼容非 JSON-schema backend，但 robust memory layer
把一次 evolution structured-output 调用拆成“decision → strengthen details → update neighbors”
最多三次串行调用，并在 parse 失败时使用 heuristic metadata。它保留 A-Mem 的高层阶段，却改变
prompt、调用次数和失败退化语义。因此：

- current robust harness 是官方 current compatibility variant；
- 它不能无证据地当成 2025 论文报告值的 exact implementation；
- paper-author profile 应优先锚定论文时期 structured-output 路径，robust 另列
  `IMPLEMENTATION_VARIANT`。

## 2. 官方 benchmark 覆盖

| benchmark | 论文报告 | 公开 harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | 是，五类 QA、六种 backbone | `test_advanced.py`；current 推荐另有 `test_advanced_robust.py` | repo `data/locomo10.json` | 每 conversation 独立 memory；逐 turn add；query LLM → memory retrieval → category prompt | `OFFICIAL_SOURCE_AVAILABLE` |
| LongMemEval | 否 | 无 | N/A | framework extension | `NO_AUTHOR_PROFILE` |
| HaluMem | 否 | 无 | N/A | framework extension | `NO_AUTHOR_PROFILE` |
| BEAM | 否 | 无 | N/A | framework extension | `NO_AUTHOR_PROFILE` |
| MemBench | 否 | 无 | N/A | framework extension | `NO_AUTHOR_PROFILE` |

论文另报告 DialSim，但它不属于 Phase 1；current eval repo 没有 DialSim harness，不能用论文表格
反向补出公开调用链。

## 3. Prompt / judge 合同

### 3.1 LoCoMo structured-output harness（最接近 paper-reported）

- source：`test_advanced.py`、`load_dataset.py`、`memory_layer.py`。
- build input：每个 raw utterance 单独调用 `add_note()`；content 字节为
  `"Speaker " + speaker + "says : " + text`，time 使用 session `date_time`。
- image：loader 用 `[Image: {blip_caption}]` 前缀；这与 framework 共享的
  `[Sharing image that shows: ...]` 语义接近但字节不等价。
- query rewrite：一条 user prompt，要求从 question 生成 keywords；原 harness 同时出现
  “use cosmos as separator”和 JSON example 的逗号，最终读取 JSON `keywords`，属于上游自身
  文案不一致，framework 不应擅自修成“paper exact”。
- retrieval：`find_related_memories_raw(keywords, k)`；返回 direct hit 与 link-expanded 文本。
- answer final message：OpenAI-compatible controller 只发送一条 `user` message，无 system。
  category 1/4 用 short phrase，category 2 要用 conversation date，category 3 要尽量取 context
  原词；temperature 均 `.7`。
- category 5：把 private gold answer 与 `Not mentioned in the conversation` 随机组成二选一，
  temperature 默认 `.5`。gold 进入 method 是框架隐私红线，因此该类别不能进入 author profile。
- structured response：JSON schema `{answer: string}`，parser 先读 JSON `answer`，失败才保留 raw。
- judge：repo 只计算 EM/F1/ROUGE/BLEU/BERT/METEOR/SBERT 等离线指标，没有 Phase 1 benchmark
  主 LLM judge；不得暗换 judge。
- 裁决：`INCOMPLETE_FOR_AUTHOR_PROFILE`。category 1–4 的公开 builder 可实现，但必须同时锁
  exact user-only messages、decode、parser、paper product/eval engine；category 5 永久不能照抄。

### 3.2 current robust harness

- query prompt 改成逗号分隔 plain text，parser 支持 JSON/markdown/plain text。
- answer category 文本基本相同，但只发送 user message并直接解析 plain text。
- build/evolution prompt 和失败退化已在 §1.3 改变。
- 裁决：`IMPLEMENTATION_VARIANT`，可作为 backend compatibility 校准，不是 paper parity。

### 3.3 current framework 资产差异

adapter 里已有 legacy Question 路径，但尚未注册到 `prompts/author/`：

1. 它采用 robust query keywords 形态；
2. LoCoMo answer messages 额外增加 synthetic system
   `Follow the format specified...`，official harness 没有；
3. 它读取通用产品 `find_related_memories_raw()`，不是 eval repo 的 SimpleEmbeddingRetriever；
4. 它正确拒绝 category 5 gold 泄漏；
5. LongMemEval 复用 LightMem reader，属于 framework extension，不是 A-Mem author prompt。

所以“代码里已经有类似 prompt”不等于 `AUTHOR_READY`。M11 若实现作者 LoCoMo profile，应新增
独立完整 builder/engine identity，而不是把当前 legacy helper 直接改名。

## 4. 参数矩阵

| parameter path | upstream default | paper role | official effective values | current main | call site/最终 payload | 分类 | state/rebuild impact | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| embedding model | MiniLM | note/query embedding | `all-MiniLM-L6-v2`，paper 明示全部实验 | MiniLM | SentenceTransformer/Chroma | core identity | 改向量与排序；全量重建 | `MAIN_CONFIRMED` |
| build LLM | gpt-4o-mini product default | note/link/evolution | paper 六种 backbone；LoCoMo harness CLI 选择 | runtime profile | LLM controller | core identity | 改 note/link/evolution；全量重建 | runtime 已独立；author 必须锁模型 |
| query/answer LLM | harness 与 build 同 model | query rewrite + answer | 同 backbone | framework answer runtime；main native retrieval不调用 query LLM | author harness/wrapper | evaluation/topology | 影响 query、answer、成本 | main 与 author 分离 |
| `retrieve_k` | eval/harness default 10；product public default 5 | query top-k | paper GPT-4o-mini/GPT-4o 按 cat=`40/40/50/50/40`；其他模型见 Table 8 | 10 | native `min(query.top_k, config.retrieve_k)`；legacy固定 config | high-impact | 不改 build；改 retrieved context | main 10 合理但非 GPT author parity |
| evolution candidate k | source hardcoded 5 | Link Generation/Memory Evolution candidate set | public harness/product=5 | 5（不可配置） | `process_memory(...find_related_memories(k=5))` | core internal constant | 改 links/evolution；全量重建 | 不放 TOML；进入 source identity |
| `evo_threshold` | 100 | 论文未单列 | eval/product=100 | product default 100，TOML 未暴露 | positive evolution 计数满足 100 时 reindex | high-impact implementation | 改旧 note metadata何时反映进 index；全量重建 | 保持 source default；manifest/source hash锁定 |
| build temperature | org product `.7`；paper-linked product `1.0` | LLM note/link/evolution decode | paper正文未给唯一值；structured eval `.7` | org product `.7` | `get_completion()` default | source-dependent high-impact | 改结构化 note/evolution；重建 | `SOURCE_RULING_REQUIRED` |
| answer temperature | `.7` | LoCoMo reader | category 1–4=.7，category 5=.5 | framework benchmark runtime | final answer request | evaluation | 不改 memory；改答案 | author仅1–4=.7；main走 benchmark policy |
| structured output | JSON schema | note/link/evolution与answer parsing | paper-era harness structured；robust plain text | ox transport对指定模型降为 json_object | final LLM payload | compatibility/topology | 可能改算法失败语义；重建 | identity 必须记录，不能混分 |
| `use_product_layer` | framework-only | N/A | N/A | true | adapter construction gate | implementation selector | false不可运行 | 后续移出算法配置或保留强制常量 |

`evo_threshold` 的源码 docstring 把它描述成“触发 evolution”，但实际每个新 note 都调用
`process_memory()`；它只控制累计 positive evolution 后何时 `consolidate_memories()`。参数裁决以
调用语义为准，不沿用误导性注释。

## 5. 配置流与强反例

- current main：`configs/methods/amem.toml` → `AMemConfig` → registry →
  `AgenticMemorySystem(model_name=embedding_model, ...)` → per-conversation persistent Chroma。
- `retrieve_k`：native retrieval 取 `min(query.top_k, config.retrieve_k)`；legacy author-like path
  始终取 `config.retrieve_k`。配置不是无条件的最终 top-k，manifest 应保留 framework query cap。
- `embedding_model` 已进入 product constructor与 model inventory；MiniLM/384 为 paper 与 controlled
  主表交集，变更要求 fresh state。
- `evo_threshold`、candidate k、product temperature 没有 TOML field，但不是“不存在”；它们由
  source identity 固定。若更换 product source，必须 bump adapter/source identity 并重建。
- current source hash覆盖 README、pyproject、`memory_system.py`、`retrievers.py`、
  `llm_controller.py` 与 package init，能够捕获本批三处算法分叉；M11 迁移时应继续保留此覆盖。
- 当前 adapter test 已锁 invalid `retrieve_k`、source files、统一 category k、adversarial gold 拒绝、
  `search_agentic()` swallow-error fail-fast 和 evidence N/A。缺少的强反例是“paper-linked source 与
  org source 不可复用同一 manifest”及 author final-message parity。

## 6. 主配置与作者配置裁决

- framework main：继续保持跨五 benchmark 的 MiniLM + `retrieve_k=10`，并明确它是
  `controlled current-product profile`，不是 paper score reproduction。
- `author_locomo`：当前不创建。候选必须至少锁定 GPT-4o-mini、category 1–4 的
  `k=40/40/50/50`、user-only answer message、structured JSON parser、eval content/image renderer，
  并决定使用 paper eval engine还是 paper-linked product engine。
- category 5：官方 harness 需要 gold，永久不得进入 method。可继续由 benchmark unified安全
  builder 评测，但不能声称作者 prompt parity。
- product-default补充身份：org product `ceffb860` 与 paper-linked `A-mem-sys@f303dfc` 必须分开。
- topology variants：eval SimpleEmbeddingRetriever、org Chroma content-only、paper-linked Chroma
  enhanced-content 是三条 build/retrieval topology，不能靠一份 TOML 注释揉平。
- 禁止进入 TOML 的内部常量：evolution candidate `k=5`；它属于算法 source identity，除非 upstream
  正式暴露 public seam，否则 framework 不应深入改成可调旋钮。

## 7. Manifest / resume / artifact

- identity 必须包含：product repo/commit/source hash、adapter/wrapper hash、embedding完整身份、
  build LLM transport/model、structured-output mode、retrieve cap、candidate-k/source、
  `evo_threshold` effective value、answer/query builder identity。
- product source、embedding、build LLM、build decode、candidate k、evo threshold 任一变化都要求
  全量重建 memory；answer-only builder/decode 变化可重用 build，但必须生成新 answer artifact身份。
- `retrieve_k` 只改 query/readout，不改 build；旧 retrieval/answer artifact 不得重标。
- 旧 `conversation-qa-v2-product` artifact继续按当时 `agiresearch/A-mem@ceffb860` 与 manifest回读，
  不因未来迁移而改写。
- private gold只能到 evaluator；official category 5 prompt是已知禁止拓扑。source sidecar只用于审计，
  不把 evolved note重标成 raw evidence。

## 8. 未闭合项与停工点

| item | status | 已查范围 | 下一条一手证据/动作 |
| --- | --- | --- | --- |
| framework main product选 org还是 paper-linked source | `RULING_REQUIRED` | 三 repo current source逐函数对表 | M11 明确 estimand；若迁移，写 source-update实现批并全量重建 |
| 论文报告精确 commit | `SOURCE_UNAVAILABLE` | PDF v11、current repo、README、current history head | 只把 current original harness写“closest public anchor”，不伪造 commit |
| LoCoMo author category 1–4 | `INCOMPLETE` | final message、parser、k、renderer已闭合 | M11 builder + engine identity + parity tests |
| LoCoMo category 5 | `N/A_PRIVACY` | official prompt逐行确认 gold注入 | 永久走 benchmark安全builder，不复制 author prompt |
| robust harness与paper结果关系 | `IMPLEMENTATION_VARIANT` | current robust code/README闭合 | 可另报 compatibility profile，不宣称 paper parity |
| DialSim harness | `SOURCE_UNAVAILABLE` | paper报告；current eval repo无入口 | Phase 1 不阻塞 |

本批没有代码停工；停点是**禁止在 M2 直接改 source/TOML/author builder**。十家证据完成后由 M11
统一裁决，避免每家边查边改导致 profile schema漂移。

## 9. 验证记录

- PDF：完整提取 28 页；视觉抽验 methodology、hyperparameter、prompt appendix 页 4/5/6/8/
  18/19/20/21。
- local/current source：eval repo与 `0c8039f…` 逐文件一致；org product与 `ceffb860…`
  逐文件一致；paper-linked product只读 snapshot=`f303dfc…`。
- source hashes：eval `memory_layer.py=b9a5b579…`、`test_advanced.py=7559e34c…`、
  `test_advanced_robust.py=83fadc17…`；org product `memory_system.py=fa58c3ed…`、
  `retrievers.py=a4cd9645…`；paper-linked product对应为 `df3d0697…`、`286eab1d…`。
- 零 API定向门：`uv run pytest -q tests/test_amem_adapter.py
  tests/test_amem_registered_prediction.py tests/test_method_registry.py
  tests/test_documentation_standards.py tests/test_codex_project_hooks.py`。
- 真实尾行：`143 passed in 11.78s`。
- `git diff --check`：无输出。
- 架构验收：M2 evidence batch 通过；product source、TOML 与 author builder 仍按本 note停在
  M11，不因文档门通过而提前宣称论文 parity。
