# LangMem profile provenance（M8）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M8 一手证据，不改写成新 run 收据。

> 架构验收判词：`M8_EVIDENCE_COMPLETE / NO_FORMAL_METHOD_PAPER_IN_SEARCH_BOUNDARY /
> CURRENT_PRODUCT_SOURCE_LOCKED / FRAMEWORK_ASYNC_SESSION_MAIN_VALID /
> OFFICIAL_PHASE1_HARNESS_UNAVAILABLE / AUTHOR_NOT_READY`。
>
> LangMem 不是一篇论文对应一个固定实验实现，而是一组长期记忆 primitives。本文把官方概念
> 文档、current product source、第三方横评策略与 framework main 分开：概念文档用于解释目标，
> effective 算法由匹配 commit 的 public factory、最终 object 与调用点裁定。本批只做零 API 证据
> 闭合，不升级 source、不修改 TOML/adapter/prompt registry，也不恢复 pilot。

## 0. 身份与范围

- method：LangMem background memory store manager；不把 hot-path agent tools、prompt optimizer、
  short-term summarizer 或外部框架的 wrapper 混成同一算法身份。
- 审计日期：2026-08-25。
- framework product source：`langchain-ai/langmem@56d85939d80bb731bd5e237567148d817d7bfd16`，
  package `0.0.30`，MIT；selected 9-file source hash=
  `50999bd9675304d514d86218033898ac1930a57958aeda95cb967f22f59753fb`，runtime lock hash=
  `b5031c66951bf52265ab300a51403728f37e2a6939be31ed75f023eaa5d49a66`，当前 wrapper 组合
  identity=`0d60a70c3d675de607609725a74234d992c1b14bec007ae2be181d8b30d43e91`。
- current remote：2026-08-25 `main=29cbe41e58528f92e9efa773c12e15c47be3808c`；相对 framework
  pin 的四个 commit 只修改 `uv.lock`（136 insertions / 139 deletions），产品 Python、README、
  docs 与 package metadata 零变化。它是 runtime dependency drift，不是算法 source drift；是否升级
  留 M11，不机械 fast-forward。
- 正式论文/技术报告：official repo、README、docs、package metadata 无 citation/arXiv/paper 身份；
  arXiv exact `"LangMem"` 搜索命中的是外部使用/评测论文，不是 LangMem method paper。因此本文以
  official conceptual guide、quickstarts、API docstring 与 current source 为最高可得机制材料，状态
  `NO_FORMAL_METHOD_PAPER_FOUND_WITHIN_SEARCH_BOUNDARY`，不是对所有未公开材料的绝对不存在证明。
- official evaluation：current main/release tree 对 LoCoMo、LongMemEval、HaluMem、BEAM、MemBench
  均无完整 build/search/answer/judge harness。外部论文、MemoryData 或其他多方法框架不升级为
  method-author source。
- 本次不覆盖：真实效果、参数 sweep、remote dependency upgrade、author builder 实施、外部论文
  的结果复现、旧 artifact 重标或 metric tier 改判。

## 1. 算法机制先行

### 1.1 官方技术材料的目标图

官方 conceptual guide 给的是可组合设计空间，不是一份固定论文算法。其共同模式是：接收新对话与
当前 memory state，提示 LLM 决定如何扩展或整合 state，再返回更新后的 state。

| 阶段/选择 | 输入 | 状态/输出 | 是否固定 | 一手出处 |
| --- | --- | --- | --- | --- |
| memory type | conversation、应用目标 | semantic facts、episodic examples 或 procedural rules | 应用选择 | `docs/docs/concepts/conceptual_guide.md` 的 Types of Memory |
| representation | 新信息、已有 state | collection 多条记录或 profile 单文档 | 应用选择 | conceptual guide 的 Collection / Profiles |
| formation timing | chat trajectory | hot-path conscious tools 或 background reflection | topology 选择 | conceptual guide Writing memories、两份 quickstart |
| old-memory recall | current messages、namespace store | 与本轮相关的 existing memories | stateful manager 核心 | `background_quickstart.md`、`knowledge/extraction.py` |
| enrichment | messages + existing memories | insert/update/consolidate，允许时 delete | background manager 核心；具体 CRUD 可配 | `_MEMORY_INSTRUCTIONS`、`MemoryManager` |
| persistence | changed memories | BaseStore put/delete 与 namespace state | stateful manager 核心；backend 可插拔 | public factory、BaseStore contract |
| readout | query + namespace | ranked `SearchItem` | stateful retrieval 核心 | `MemoryStoreManager.search/asearch` |

概念页还说理想 relevance 应结合 similarity、importance 与 memory strength（含 recency/frequency）。
current default source没有自动实现一套 importance/strength scorer；framework 的 concrete
`InMemoryStore` 是受控 embedding 相似度检索。因此这句话属于**设计指导**，不能冒充当前主轨的
effective ranking 公式。

### 1.2 current background manager 调用图

```text
canonical SessionBatch
  -> list[{role, content}]（原序；一个 session 一次）
  -> MemoryStoreManager.ainvoke(max_steps=1, namespace config)
       -> 生成 old-memory search query
          query_model=None:
          get_dialated_windows(messages, query_limit // 4)
       -> BaseStore.asearch(namespace, query)
       -> top query_limit old memories（score 降序、stable tie）
       -> MemoryManager.ainvoke(messages + existing)
          -> system: "You are a memory subroutine for an AI."
          -> user: source-locked enrichment instructions + conversation
          -> trustcall structured parallel tool call
          -> insert / update / optional removal
       -> optional phases（main=[]）
       -> await all BaseStore.aput/adelete
       -> changed puts

question
  -> MemoryStoreManager.asearch(query, limit)
  -> product key/value/score/order
  -> framework formatted_memory
  -> benchmark-owned answer builder
```

承重点：

1. public factory 默认 `query_limit=5`，且 `query_model=None` 时把 `5 // 4` 传给窗口生成器，
   effective 为只拿 session **最后一条 message** 生成一条 old-memory search query；完整 session 仍
   进入 enrichment LLM。`query_limit` 因此同时影响 candidate cap 与隐式 query-window 数，不只是
   普通 top-k。
2. `MemoryStoreManager.ainvoke()` 返回前会 await 全部 put/delete；它是精确完成门。sync
   `invoke()` 的 current implementation 对无 query model 路径重复执行 search，framework 选择 async
   是避免 upstream duplicate search，不是另写算法。
3. source 的 update 没有对应 public `enable_updates` 参数。public store-manager 把
   `enable_inserts/deletes` 传进内部 `create_memory_manager()`，后者的 `enable_updates=True` 默认继续
   生效。因此 main 是 **insert=true + update=true + delete=false**。
4. `max_steps=1` 是 `MemoryManager` 的 input default：一次 structured multi-tool call；大于 1 才会
   进入带 `Done` tool 的继续精炼回合。它是算法/成本参数，不是 worker 并发参数。
5. `phases=[]` 表示没有第二轮自定义 consolidation phase；这不关闭第一轮 manager 自带的 compare、
   update 与 consolidate。

### 1.3 其他官方 surface 不是 main 的理由

| surface | 官方目标 | 为什么不与 main 混写 | 分类 |
| --- | --- | --- | --- |
| hot-path memory tools | answer agent 自己决定何时存/搜 | tool policy 与回答能力进入 estimand | `ALGORITHM_VARIANT` |
| core `create_memory_manager` | 无 storage side effect 的 state transformation | framework 若直接用它还需自写检索、写入与删除语义 | `LOWER_LEVEL_PRIMITIVE` |
| prompt optimizer | 从 feedback/trajectory 学 procedural prompt | 不是当前 semantic collection memory | `SEPARATE_METHOD_SURFACE` |
| short-term summarizer | 压缩单线程上下文 | 不等于跨 session long-term store | `SEPARATE_METHOD_SURFACE` |
| direct `store.put(raw turn)` | 只写原始记录 | 绕过 old-memory search 和 LLM enrichment | `MECHANISM_BYPASS` |

### 1.4 current source 对应关系

| 技术材料概念 | current module/function | main effective control | 判词 |
| --- | --- | --- | --- |
| background formation | `create_memory_store_manager` / `MemoryStoreManager.ainvoke` | async、session transaction | `CONFIG_EQUIVALENT` |
| collection memory | default `Memory(content)` schema | `schemas=None` | `PRODUCT_DEFAULT` |
| old-memory recall | `get_dialated_windows` + `BaseStore.asearch` | query model none、limit 5 | `PRODUCT_DEFAULT_WITH_HIDDEN_COUPLING` |
| enrichment | `MemoryManager._prepare_messages` + trustcall extractor | insert/update on、delete off、steps 1 | `PRODUCT_DEFAULT` |
| extra consolidation phases | `_build_phase_manager` | `phases=[]` | `OPTIONAL_DORMANT` |
| storage | LangGraph `InMemoryStore` | namespace + controlled MiniLM | `PUBLIC_BACKEND_EXTENSION` |
| product search | `MemoryStoreManager.asearch` | framework query top-k | `CONFIG_EQUIVALENT` |
| importance/strength retrieval | conceptual guidance only | 无 concrete scorer | `NOT_IMPLEMENTED_BY_MAIN_SURFACE` |
| final answer | quickstart app-specific LLM | framework benchmark builder | `FRAMEWORK_READOUT_BOUNDARY` |

## 2. 官方 benchmark 覆盖

| benchmark | method paper 报告 | current official harness | topology/source | source status |
| --- | --- | --- | --- | --- |
| LoCoMo | 无 method paper | 无 | framework session-level extension | `SOURCE_UNAVAILABLE` |
| LongMemEval | 无 method paper | 无 | framework session-level extension | `SOURCE_UNAVAILABLE` |
| HaluMem | 无 method paper | 无 | framework operation/session extension | `SOURCE_UNAVAILABLE` |
| BEAM | 无 method paper | 无 | framework session-level extension | `SOURCE_UNAVAILABLE` |
| MemBench | 无 method paper | 无 | framework session-level extension | `SOURCE_UNAVAILABLE` |

搜索边界包括：pinned/current main tracked tree、README/docs/examples/tests/package metadata、公开 remote
heads/tags 与 exact benchmark 关键词。`pyproject.toml` 虽声明 workspace member `evals/gen`，current
tracked tree 没有该目录，也没有可用 harness；不能据一个未发布 workspace entry 推断作者参数。

外部论文或框架报告 LangMem 结果，最多证明某个**外部 integration identity**；只有完整锁定它的
LangMem version、build/search topology、prompt、dataset、answer/judge 后才能作为对照，不能生成
`author_<benchmark>`。

## 3. Prompt / judge 合同

### 3.1 Method-owned build prompt

- source：`third_party/methods/langmem/src/langmem/knowledge/extraction.py` 的
  `_MEMORY_INSTRUCTIONS` 与 `MemoryManager._prepare_messages()`。
- final logical messages：一条 system `You are a memory subroutine for an AI.`；一条 user，包含
  source-locked enrichment instructions、insert/update/consolidate要求和 `<session_UUID>` 包住的
  `merge_message_runs()` conversation。UUID 是每次调用生成的 prompt 内容，属于产品随机身份；
  operation retry 由 framework journal 避免重跑，而不是试图复现 UUID。
- old memories：作为 trustcall `existing` structured state 交给 extractor，不由 framework拼入
  benchmark answer prompt。
- tool policy：一次 parallel multi-tool call；insert/update/delete 工具由有效 flags 决定。
- build decode：framework `ChatOpenAI` 只显式传 provider/model/timeout/retry/transport 与需要的
  reasoning override；temperature、max_tokens、top_p、response_format 不在 method TOML，也未在
  final `ChatOpenAI` constructor 显式设置，effective 是 SDK/provider default + trustcall tool schema。
  M11 必须把“省略”本身作为请求身份，不能在文档里伪写成 0/4096。

### 3.2 Answer / judge

LangMem package 是 memory primitive；current repo 没有 Phase 1 benchmark answer/judge harness，也
没有可复现的 method-native final answer builder。quickstart 中的 generic assistant messages 只演示
如何消费 memory，不是 benchmark author prompt。

- framework main：product `asearch()` → `formatted_memory` → benchmark-owned answer builder。
- `src/memory_benchmark/prompts/author/`：无 LangMem builder是正确的 `N/A_BY_PRODUCT_SCOPE`，不是
  需要凭空补齐的模板遗漏。
- author profile：五格均 `AUTHOR_NOT_READY / SOURCE_UNAVAILABLE`。
- judge：没有 method-owned Phase 1 judge 可盘点；benchmark 主 judge 不变。

## 4. 参数矩阵

| parameter path | upstream/public default | official effective | current main | 最终 consumer | 分类 | state/rebuild impact | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| product surface | core/hot/background均公开 | 无 benchmark harness | background store manager async | worker factory/ainvoke | topology | fresh rebuild | main 保留 |
| schema | `Memory(content)` | 无 | unstructured default | `MemoryManager.schemas` | core representation | fresh rebuild | generic五格合理 |
| instructions | `_MEMORY_INSTRUCTIONS` | 无 | source default | `_prepare_messages` | core build prompt | fresh rebuild | source-lock |
| `enable_inserts` | true | 无 | true | trustcall insert tool | core build | fresh rebuild | active |
| update | internal manager default true；store public API无独立 knob | 无 | true | trustcall update tool | core build | fresh rebuild | active；勿造假 TOML key |
| `enable_deletes` | public factory false；class default/docstring一度写 true | 无 | false | trustcall RemoveDoc tool | core build/safety | fresh rebuild | public-default main；冲突披露 |
| `query_model` | None | 无 | None | old-memory query pipeline | retrieval topology/cost | fresh rebuild | direct embedding path |
| `query_limit` | 5 | 无 | 5 | old search windows + candidate cap | core retrieval | fresh rebuild | 保留；隐藏双重含义 |
| `max_steps` | input absent→1 | 无 | 1 | manager loop | core build/cost | fresh rebuild | 保留公开 default |
| `phases` | None→[] | 无 | [] | post-manager loops | optional algorithm | fresh rebuild | dormant，不伪装核心关闭 |
| `default/default_factory` | None | 无 | None | zero-old-memory initialization | optional state | fresh rebuild | dormant |
| namespace | `("memories","{langgraph_user_id}")` | 无 | 同模板，opaque isolation id | NamespaceTemplate/BaseStore | isolation | fresh state | active |
| store | public BaseStore；quickstart InMemoryStore | 无 | InMemoryStore + atomic snapshot | worker | backend/durability | fresh rebuild | public seam extension |
| embedding | quickstart示例 OpenAI 1536，不是 factory default | 无 | controlled MiniLM/384/normalized | InMemoryStore index | controlled build | fresh rebuild | Phase 1 main policy |
| indexed fields | store default | 无 | 未覆盖 fields | InMemoryStore | retrieval representation | fresh rebuild | 与官方 quickstart一致 |
| consume granularity | docs演示逐interaction；delayed guide建议debounce完整context | 无 | one canonical session | adapter/manager | topology/cost | fresh rebuild | official delayed pattern |
| final retrieval limit | `asearch` default10 | 无 | `RetrievalQuery.top_k` | manager.asearch | readout | rerun retrieval | benchmark/evaluator request，不进method TOML |
| build LLM model/runtime | application supplied | 无 | runtime profile composition | ChatOpenAI | runtime+build | fresh rebuild | method TOML不重复 |
| temperature/max tokens | application/SDK default | 无 | omitted | ChatOpenAI/provider | build decode | fresh rebuild | M11记录省略身份 |
| timeout/retry/workers | 非算法 factory 参数 | 无 | runtime/execution configs | transport/runner | framework runtime | 不改变method state语义 | 已移出 TOML |

### 4.1 delete=false 是否“关闭论文核心”

这里没有论文可把 delete 定义为不可关闭阶段。官方 conceptual guide 认为 collection 要通过
delete/invalidate **或** update/consolidate处理冲突；public store-manager 和 core-manager factory 都
默认 delete=false，而 update 继续开启。若应用需要 hard removal，官方示例会显式 enable；MemoryData
也这样选择。main 保持 false 的理由是 current public safe default，而不是“bool默认都不能动”。

切成 true 会改变旧 memory 的存亡、未来检索集合与后续 update context，必须作为新 build identity
全量重建；不能把两边结果混表。

## 5. 配置流与强反例

- flow：`configs/methods/langmem.toml` → profile loader → `LangMemConfig` → registry 注入 runtime
  model/timeout/retry/workers → JSON-lines worker → `ChatOpenAI`、observed embeddings、
  `InMemoryStore` → `create_memory_store_manager()`。
- typed gate：main 强制 MiniLM384 normalized、query_limit5、max_steps1、insert true、delete false；
  类型/未知字段与偏离值 fail-fast。runtime/credential/execution 不回流 method TOML。
- effective-object gate：worker 再校验相同值，并把它们逐项传入 public factory；`query_model`、schema、
  phases、default 都因省略保持 exact public default。
- async mutation：sync 无-query路径会重复 old-memory search；main只有 async。该差异已有零 API
  product probe，不应为了“接口对称”退回 sync。
- message shapes：LangChain `merge_message_runs()` 支持 assistant-first、same-role、singleton、odd
  tail；同 role 只在 prompt展示层合并，content不丢失。无需 placeholder。
- source time/image：adapter按 turn→session→None 渲染；MemBench已有尾部时间不重复，LoCoMo caption
  用共享 wrapper；private gold 不进 manager。
- identity：selected product source、`uv.lock`、adapter/worker/shared transport/bootstrap/overlay lock
  均进入 source identity；embedding完整 identity另进 build manifest。

## 6. 主配置、作者配置与外部设计裁决

### 6.1 framework main

固定为：background async manager、session transaction、unstructured collection、insert/update on、
delete off、query model none、query limit5、steps1、phases empty、controlled MiniLM。它回答的是：
“同一通用 LangMem product surface 在五个 benchmark 上的可比表现”，不是论文复现。

### 6.2 author profile

五格没有公开 official harness，因此不创建 `author_*`。如果未来出现作者完整 runner，必须同时锁
dataset revision、ingest batching、namespace、schema/instructions、search、answer messages、decode、
parser 与 judge；只抄一段 prompt 不算 author parity。

### 6.3 MemoryData：先还原目标，再比较

本地 `第三方框架参考/MemoryData` 用 LangMem 0.0.29 wrapper。其 Python schema 默认
MiniLM384、GPT-4o-mini、query model none、query limit5、insert/delete on；但真正 checked-in
`configs/LangMem.json` 又覆盖为 OpenAI `text-embedding-3-small`/1536、GPT-4.1-mini、
`query_limit=40`，未覆盖的 delete 仍为 true。`add_messages(message_level=True)` 默认逐 message
调用同步 manager，并要求 timestamp 追加到 content。这里必须以“schema default → JSON override →
final constructor”三层为准，不能拿第一层默认值冒充该框架的 effective evaluation profile。

它在优化的目标不是“复现 LangMem paper”（没有 method paper），而是：

1. 让多方法共享 message-level layer API，便于逐条成本/调用归因和统一 save/load；
2. 把 CRUD、retriever 与 model knob 显式暴露，便于横评和消融；
3. delete=true 让矛盾/过时 memory可真正移除；MiniLM让 embedding成本与能力受控。

收益是配置可见、layer API统一、token sidecar较完整；代价是逐 message processing增加调用并让
manager看不到完整 session context，且 delete=true、时间强制要求与 public quickstart default形成不同
estimand。我们的 main 借鉴它的 controlled embedding、显式配置与观测思路，选择官方 delayed
processing 的 session context 和 public delete=false；这叫**目标不同的两套有效设计**，不是证明
外部框架错误。

## 7. Manifest / resume / artifact

- 必须进入 build identity：upstream commit/package、selected source hash、runtime lock、wrapper、
  product surface、schema/instructions identity、insert/update/delete effective值、query model/limit、
  max steps/phases/default、namespace算法、embedding完整identity、build model/runtime/request omission。
- source、prompt、schema、CRUD、old-memory query、steps/phases、embedding或granularity变化要求 fresh-state
  rebuild；只改 answer/evaluator可在公开 artifact完整时重算，但生成新 evaluation identity。
- 旧 artifact只按原 manifest回读；`langmem-background-product-v1` 不能重标为 v2，也不能把
  56d8593结果重标为29cbe41 runtime。
- secret/base URL只从 runtime environment进入 worker；gold/evidence/judge label只在 evaluator-private。

## 8. 未闭合项与停工点

| item | status | 已查范围 | 下一条一手证据 |
| --- | --- | --- | --- |
| LangMem method paper | `NO_FORMAL_METHOD_PAPER_IN_SEARCH_BOUNDARY` | official repo/docs/metadata、arXiv exact keyword | owner正式发布的paper/report |
| Phase1 official harness | `SOURCE_UNAVAILABLE` | pinned/current tree、remote refs、五关键词 | owner公开完整runner |
| author answer/judge | `N/A_BY_PRODUCT_SCOPE` | quickstarts与repo | 未来官方benchmark harness |
| provider-default decode | `PENDING_M11_IDENTITY_EXPLICITNESS` | worker ChatOpenAI constructor | manifest强反例锁 omitted values |
| current remote upgrade | `PENDING_M11` | 56d8593..29cbe41 仅uv.lock | dependency/runtime regression |
| importance/strength ranking | `GUIDANCE_NOT_CURRENT_IMPLEMENTATION` | conceptual guide/source search | 未来concrete scorer implementation |
| external LangMem benchmark configs | `EXTERNAL_EVIDENCE_ONLY` | MemoryData；其他公开论文仅定位 | exact external repo/commit/config审计 |

## 9. 验证记录

当前证据批次定向门：

```text
uv run pytest -q tests/test_langmem_adapter.py tests/test_langmem_worker.py \
  tests/test_langmem_registered_prediction.py tests/test_config_profiles.py \
  tests/test_method_registry.py tests/test_documentation_standards.py \
  tests/test_codex_project_hooks.py
git diff --check
```

真实尾行：`219 passed in 2.36s`；`git diff --check` clean。

远端差量：

```text
56d8593..29cbe41
uv.lock | 275 ++++++++++++++++++++++++++++++++--------------------------------
1 file changed, 136 insertions(+), 139 deletions(-)
```

架构师完成下述 subagent receipt、承重源码抽锚和零 API门后，已把 stable summary 回填
`docs/reference/integration/langmem.md`、矩阵与 ws05.1 状态页。

### 9.1 Luna/max 调查回执验收

- 回执范围符合授权：只读 source/paper/harness/config 取证；未改文件、未调用 API、未加载模型或数据。
- 架构师独立复核了承重 locator：public factory 与 constructor 的 delete 默认冲突、隐式
  `enable_updates=True`、`query_limit // 4`、async write completion、worker final constructor 和
  MemoryData wrapper/JSON override。它们均支持主判词。
- 回执新增的有效证据是 MemoryData checked-in JSON 覆盖；初稿只写了 wrapper schema default，现已
  订正为三层 effective config。回执中写出的 `configs/LangMem.json` 是相对 memory-toolkit 根的路径，
  稳定定位为
  `第三方框架参考/MemoryData/methods/lightmem/source/lightmem/memory_toolkits/configs/LangMem.json`。
- 回执把 SocialMemBench 等外部研究明确降为 external evidence，没有把它们升级成 method owner
  harness。没有出现需要第二 reviewer 的身份冲突；本批按“一份候选回执 + 架构师不同证据抽锚”
  停止，避免仪式化重复调查。
