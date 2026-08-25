# 十家 method profile provenance 资产矩阵

> 这是 ws05.1 的检索底表，不是十家最终判词。`CONFIRMED` 只表示 source/既有稳定页已确认该事实；
> prompt、参数和论文身份仍须在 M1-M10 按
> [统一模板](method-profile-provenance-note-template.md)逐家闭合。矩阵每完成一家立即更新，禁止十家
> 结束后凭记忆补写。

## 1. 状态说明

- `ASSET_READY`：本地已有可读一手资产，但尚未完成本任务逐字段审计。
- `STABLE_PAGE_CONFIRMED`：现有 integration 页已有架构验收结论；仍需核 current source 是否漂移。
- `PROMPT_PRESENT`：`src/memory_benchmark/prompts/author/` 已有实现，不等于 final-message parity 已通过。
- `PROMPT_MISSING`：当前 author 目录无实现；可能是遗漏，也可能确实没有公开 official builder。
- `SOURCE_UNAVAILABLE`：已完成检索仍无公开一手 source；只能在对应 method 批次结束时裁定。
- `IMPLEMENTATION_VARIANT`：作者 harness 改变双写、namespace、batching、storage/update/retrieval 拓扑，
  不能伪装为普通 TOML override。
- `M_EVIDENCE_COMPLETE`：该家 paper/current-source/harness/effective-config 证据批次已闭合；不表示
  所有 author profile 已可运行。M11 横向实现另看 §2.1 与实施 note。

## 2. Source 与机制材料

| method | current product source | 论文/官方机制材料 | 身份注意事项 | M 批次 |
| --- | --- | --- | --- | --- |
| LightMem | initial core/eval=`zjunlp/LightMem@02e675b1…` + framework patches；vendored 8-file=`a44d7d99…`；upstream main=`b4ef1dd2…` 已漂移 | `lightmem.pdf`=arXiv:2510.18866v4，SHA-256 `7e9a8e9f…` | `M1_EVIDENCE_COMPLETE`；source 三方合并与完整 hash 留 M11 | M1 ✅ |
| A-Mem | framework product=`agiresearch/A-mem@ceffb860`；paper-linked product=`WujiangXu/A-mem-sys@f303dfc`；eval=`WujiangXu/A-mem@0c8039f` | arXiv:2502.12110v11；本地 PDF SHA `fec32b52…` | `M2_EVIDENCE_COMPLETE`；三套 source 有算法差异，product 选择留 M11 | M2 ✅ |
| Mem0 | framework=`mem0ai/mem0` 2.0.4；现行混合 146-file identity=`debda89e…`；upstream main=2.0.19/`39bc0233…` 已漂移 | arXiv:2504.19413v1；本机 PDF SHA `bec870b6…` | `M3_EVIDENCE_COMPLETE`；paper four-op、old hosted 双库、current additive product、current harness 四种身份；source 漂移留 M11 | M3 ✅ |
| MemoryOS | `BAI-LAB/MemoryOS@587ed775` + declared product patches；vendored 12-file=`5a9af420…`；product+adapter=`7c82b269…` | arXiv:2506.06326；本地 PDF SHA `b251fe65…` | `M4_EVIDENCE_COMPLETE`；paper/eval/current product/framework main 四身份，eval/product 为 implementation variants | M4 ✅ |
| MemOS | `MemTensor/MemOS@v2.0.25/e820406` + 可重放观测/适配 patch；product+patch+wrapper=`a1c71f35…`；upstream main=`9119efe…` 已漂移 | arXiv:2507.03724v4；本地 PDF SHA `9b9b71b6…`、local-only | `M5_EVIDENCE_COMPLETE`；paper `MemOS-1031` source unresolved；v2.0.25 harness与Omni extension分 identity | M5 ✅ |
| SimpleMem | `aiming-lab/SimpleMem@60a48e8` + patch=`77606efb…`；product+wrapper=`612d2f65…`；upstream main=`db80b6a7…` 已漂移 | arXiv:2601.02553v3；local-only PDF SHA `8752aa22…` | `M6_EVIDENCE_COMPLETE`；论文三阶段与current previous-context/固定检索深度是implementation variant，升级留M11 | M6 ✅ |
| Letta/MemGPT | legacy V1 `letta@b76da90`；declared 20-file=`823e2a22…`、product+wrapper=`98b621ca…`；V1 archive=`56ba9c2…`；active Letta Code=`6d8cfab…` | arXiv:2310.08560v2；local-only PDF SHA `9f674bcf…`；SDK v0.2.0=`4494e004…` | `M7_EVIDENCE_COMPLETE`；paper/V1 sleeptime/active Code 是算法变体；20-file hash漏真实prompt/tool/compaction消费者，M11扩锁 | M7 ✅ |
| LangMem | `langchain-ai/langmem@56d8593`，package 0.0.30；selected 9-file=`50999bd9…`、runtime lock=`b5031c66…`；remote `29cbe41…` 仅 `uv.lock` 漂移 | official repo/docs/metadata 与精确检索边界内无 method paper；官方 conceptual guide + current source 是最高机制证据 | `M8_EVIDENCE_COMPLETE`；async background session main 有效；update 隐式开启、`query_limit` 双重耦合；五格均 framework extension | M8 ✅ |
| EverOS | `EverMind-AI/EverOS@v1.2.3/48fc908` + 两个可重放 patch；current main=`7864061…` | arXiv:2601.02163v2；local-only PDF SHA `26531479…`；EverAlgo package tags 已抽锚 | `M9_EVIDENCE_COMPLETE`；paper、29d official history、v1.2.3 product 与 framework hybrid 分栏；14-file source lock 漏算法消费者 | M9 ✅ |
| Graphiti OSS | `getzep/graphiti@v0.29.3/021d3a5`；selected 11-file source lock不完整；remote main=`993e081a…` | related Zep paper arXiv:2501.13956v1；不是独立Graphiti OSS论文；official hosted code另分identity | `M10_EVIDENCE_COMPLETE`；basic RRF controlled main有效；LME仅build payload anchor且judge polarity冲突，完整source lock留M11 | M10 ✅ |

source identity 以 `third_party/methods/MANIFEST.md` 为准。未跟踪 PDF 可作为当前机器上的阅读材料，
但不是可重放项目资产；正式判词必须补稳定 URL/hash 或明确 `local-only evidence`。

### 2.1 M11 新 run 身份（2026-08-25）

上表保留 M1-M10 取证时的历史/旧 identity，不能改写成“当时已经具备 M11 合同”。新 registered
run 统一使用 `method-source-closure-v2` 分组件闭包；九家真实 embedding consumer 另用 run identity
v2 锁同一份本地 MiniLM bytes/tokenizer/pipeline/runtime，Letta 明确 N/A。

| method | 新 source recipe / files | embedding artifact | 重建裁决 |
|---|---|---|---|
| LightMem | `lightmem-main-v2` / 70 | local locked | fresh |
| A-Mem | `amem-product-main-v2` / 7 | local locked | fresh；不宣称旧 Hub-style build 等价 |
| Mem0 | `mem0-product-main-v2` / 149 | local locked | fresh；不宣称旧 Hub-style build 等价 |
| MemoryOS | `memoryos-pypi-main-v2` / 12 | local locked | fresh；不宣称旧 Hub-style build 等价 |
| MemOS | `memos-product-main-v2` / 385 | local locked | fresh |
| SimpleMem | `simplemem-text-main-v2` / 20 | local locked | fresh |
| Letta | `letta-sleeptime-main-v2` / 543 + SDK source unavailable 声明 | N/A | source identity 变化，fresh |
| LangMem | `langmem-main-v2` / 31 | local locked | fresh |
| EverOS | `everos-api-main-v2` / 296 | local locked | v8 effective profile + identity，fresh |
| Graphiti | `graphiti-oss-main-v2` / 165 | local locked | fresh |

本地内容摘要为 `9c93593d…72fce`，tokenizer 摘要为 `517a76b5…ab0a`。完整算法、文件 closure、
aggregate hash、旧 v1 只读边界和 subagent 风险验收见
[M11 implementation](m11-effective-config-source-embedding-implementation.md)。

## 3. 官方 benchmark / prompt 资产初始盘点

| method | Phase 1 官方覆盖（既有稳定页，待本批复核） | 当前 author builder | 初始缺口 |
| --- | --- | --- | --- |
| LightMem | 只报告 LoCoMo、LongMemEval-S；后三格为 framework extension | `author/lightmem.py`（代码存在但新 run 未注册） | LME final messages/decode 已闭合；LoCoMo 误共用 LME `max_tokens/top_p`，且 paper 多 `(r,th)`、非 512 当前不可表达，故 `AUTHOR_NOT_READY` |
| A-Mem | 论文/公开 harness 仅覆盖 Phase 1 的 LoCoMo；另报 DialSim（非 Phase 1） | `PROMPT_MISSING` | LoCoMo final messages/k/parser 已闭合；category 5 泄漏 gold，1–4 仍因 engine/system/source identity 不同而 `AUTHOR_NOT_READY` |
| Mem0 | paper 只覆盖 Phase 1 LoCoMo；current harness 覆盖 LoCoMo/LME/BEAM；后两格为 extension | `author/mem0.py`（template/static profile，new run 不可达） | old LoCoMo 双 namespace=`IMPLEMENTATION_VARIANT`；三家 final messages/decode/parser/registry 未闭合，故 `AUTHOR_NOT_READY` |
| MemoryOS | 官方公开仅 LoCoMo；其余四格为 framework extension | `author/memoryos.py`（final-message template parity，new run 不可达） | method-state→变量格式化、parser、TOML/registry 与 build engine 未闭合，故 `AUTHOR_NOT_READY`；官方无 LLM judge |
| MemOS | v2.0.25 repo覆盖LoCoMo/LME；同owner OmniMemEval后续覆盖BEAM/HaluMem | `PROMPT_MISSING` | LoCoMo topology parity；LME wrapper broken；Omni两格是通用横评扩展且HaluMem仅QA；四格均非可运行paper author profile |
| SimpleMem | paper报告LoCoMo/LME-S；锁定text repo只公开完整LoCoMo，LME原始runner不可得；EvolveMem的LME/MemBench属后续extension | `PROMPT_MISSING` | LoCoMo normal answer链可重建，但官方batch/parallel topology、paper source/config未闭合；category5泄漏private adversarial answer，故`AUTHOR_NOT_READY` |
| Letta/MemGPT | current repo/evals五格无harness；official archived `letta-leaderboard@802a794…` 有LoCoMo files/search/agent-native-answer harness | `PROMPT_MISSING` | archived LoCoMo 数据revision/server defaults/search/decode不完整且为独立topology，故`AUTHOR_NOT_READY`；其余四格`SOURCE_UNAVAILABLE` |
| LangMem | current official repo 对五格均无完整 build/search/answer/judge harness | `N/A_BY_PRODUCT_SCOPE` | memory primitive 不提供 Phase 1 final answer/judge；五格 `AUTHOR_NOT_READY/SOURCE_UNAVAILABLE`，外部 SocialMemBench/MemoryData 不升级为 author source |
| EverOS | current product 覆盖 LoCoMo；official historical EverCore@29d 覆盖 LoCoMo/LME；paper 报 LoCoMo/LME | `PROMPT_MISSING` | current LoCoMo builder ready、完整复现待数据 revision；29d LME code ready 但 exact paper source/data/payload 未锁，故 `PAPER_AUTHOR_NOT_READY` |
| Graphiti OSS | current stable 只有 LME build eval；同owner Zep paper/repo另有hosted LoCoMo/LME | `PROMPT_MISSING` | build eval无完整QA且judge schema/prompt/scorer冲突；hosted source身份不匹配；五格均`AUTHOR_NOT_READY/SOURCE_UNAVAILABLE` |

这里的“官方覆盖”只用于安排检索优先级。只有 corresponding method note 闭合 repo/commit、dataset、
最终 payload、prompt messages 与 parser 后，才能把格子升级为 `AUTHOR_READY`。

## 4. 当前 TOML 基线

十家 `configs/methods/<method>.toml` 当前都只有单一 `[method]` section；API runtime、benchmark
evaluation 和 execution 已在 ws05 前置批次移出 method TOML。这是结构基线，不代表值已完成
provenance：

| method | TOML | author section | 本任务重点 |
| --- | --- | --- | --- |
| LightMem | `configs/methods/lightmem.toml` | 无 | 主机制确认；dead `extract_threshold` 已退出，STM=真实硬编码 512、offline score 在 online-soft dormant；source/embedding identity v2 已闭合 |
| A-Mem | `configs/methods/amem.toml` | 无 | MiniLM confirmed；main k=10 是 controlled 值，非 GPT author `40/40/50/50/40`；dead selector 已退出；Chroma 1.5.9 随产品 embedding function 使用 cosine |
| Mem0 | `configs/methods/mem0.toml` | 无 | MiniLM/384+infer=true confirmed controlled main；query top-k20≠paper s10；假 global chunk-size 已退出；temp .1/threshold .1 由 source identity 锁定，不冒充 TOML 调优项 |
| MemoryOS | `configs/methods/memoryos.toml` | 无 | main=current product defaults+controlled MiniLM；paper/eval/product 三岔已闭合；dead prompt 字段已退出，强类型类名已迁到 `MemoryOSConfig` |
| MemOS | `configs/methods/memos.toml` | 无 | current主轨确认；真实reader window=1024/200而非dead 1600/10/2；controlled embedding/source identity v2 已闭合，双 LLM client 继续按最终产品接线记录 |
| SimpleMem | `configs/methods/simplemem.toml` | 无 | main=W40/O2、25/5/5、planning/reflection on、build serial、retrieval parallel、controlled MiniLM；paper=W20/Qwen3/adaptive depth，current synthesis concrete form不同；author profiles均未就绪 |
| Letta | `configs/methods/letta.toml` | 无 | main=V1 sleeptime core blocks、SDK batch10、human10000/summary1000、W1、explicit embedding None；actual compaction 90%与doc冲突；完整 product closure + SDK source-unavailable 声明已闭合 |
| LangMem | `configs/methods/langmem.toml` | 无 | background async/session、unstructured collection、insert/update开、delete关、query-model none、query-limit5、steps1、phases空、controlled MiniLM；`query_limit` 同时控制写入前 old-memory window/candidate，不等于 QA top-k |
| EverOS | `configs/methods/everos.toml` | 无 | main=chat/batch25/MiniLM384/hybrid/no-rerank；v8 已显式锁 profile clustering on / profile extraction off，并在 final StrategyMeta 验真；agentic保持独立 estimand，source/embedding v2 已闭合 |
| Graphiti | `configs/methods/graphiti.toml` | 无 | main=逐turn episode、recent10、communities off、MiniLM384、edge BM25+cosine+RRF、top-k≤20、cross-encoder sentinel；README并发10/source默认20冲突；embedding/source identity v2 已闭合 |

## 5. 每家固定读取顺序

1. 本矩阵与对应 integration 稳定页，用来定位已有资产和避免重复调查；
2. 匹配 source identity 的论文正文、附录、伪代码、消融，先画算法阶段图；
3. 官方 README/config schema/examples，核算法阶段在 current product 的公开开关；
4. 官方 eval/benchmark harness，追到最终 effective 参数、完整 answer messages 与 parser；
5. current factory/call site/final payload + 零 API mutation，排除 dead/overridden config；
6. 回填 method note、integration 页和本矩阵，再裁定 main/author profile。

第三方多方法框架的 preset 只在第 4-5 步作为差异提示使用；比较判词见
[第三方框架配置策略审计](third-party-framework-config-strategy-audit.md)。

## 6. 当前断点

- M0 资产矩阵与统一模板已建立。
- M0.5 对照已证明“YAML/单文件复用”不等于 effective config 统一；本项目保持 TOML。
- M1 LightMem、M2 A-Mem、M3 Mem0、M4 MemoryOS、M5 MemOS、M6 SimpleMem、M7 Letta、M8 LangMem、M9 EverOS 与 M10 Graphiti OSS 证据批次已闭合，详见
  [`lightmem-profile-provenance.md`](lightmem-profile-provenance.md) 与
  [`amem-profile-provenance.md`](amem-profile-provenance.md)、
  [`mem0-profile-provenance.md`](mem0-profile-provenance.md)、
  [`memoryos-profile-provenance.md`](memoryos-profile-provenance.md)、
  [`memos-profile-provenance.md`](memos-profile-provenance.md) 与
  [`simplemem-profile-provenance.md`](simplemem-profile-provenance.md)、
  [`letta-profile-provenance.md`](letta-profile-provenance.md)、
  [`langmem-profile-provenance.md`](langmem-profile-provenance.md) 与
  [`everos-profile-provenance.md`](everos-profile-provenance.md) 与
  [`graphiti-profile-provenance.md`](graphiti-profile-provenance.md)。M11 配置/source/embedding 实现
  已落盘，当前只剩最终零 API 全量门与父 ws05 重建矩阵回填；author profile 仍全部未注册。
