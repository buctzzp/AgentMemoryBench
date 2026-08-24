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

## 2. Source 与机制材料

| method | current product source | 论文/官方机制材料 | 身份注意事项 | M 批次 |
| --- | --- | --- | --- | --- |
| LightMem | `zjunlp/LightMem`，git-tracked snapshot | `third_party/methods/LightMem/lightmem.pdf` | 论文、LoCoMo/LME scripts 与 current product 需三方对表 | M1 |
| A-Mem | product=`agiresearch/A-mem@ceffb860`；eval=`WujiangXu/AgenticMemory` 本仓导入 97e9d44 | `third_party/methods/A-mem/A-mem.pdf` | eval upstream revision 已丢失；不能把 product current 默认倒推论文结果 | M2 |
| Mem0 | `mem0ai/mem0` git-tracked snapshot | 本地有用户未跟踪 Mem0 PDF；另需锁官方论文 URL/version | current product、current memory-benchmarks 与旧 paper harness 是三种身份 | M3 |
| MemoryOS | `BAI-LAB/MemoryOS` git-tracked snapshot | `third_party/methods/MemoryOS-main/Paper-MemoryOS.pdf` | paper、eval directory、PyPI/product 参数已有不一致判例 | M4 |
| MemOS | `MemTensor/MemOS@v2.0.25/e820406` + 可重放观测/适配 patch | `third_party/methods/MemOS/MemOS.pdf`，但 PDF 不在恢复资产合同 | source lock 已稳；论文附件身份要单独记录，不能由 fetch 保证 | M5 |
| SimpleMem | `aiming-lab/SimpleMem@60a48e8` + product-compat patch | `third_party/methods/SimpleMem/Liu 等 - 2026 - SimpleMem Efficient Lifelong Memory for LLM Agents.pdf` | patch 只适配 FTS/观测/日志；论文三阶段与并行窗口必须对表 | M6 |
| Letta/MemGPT | `letta-ai/letta@b76da90` | `third_party/methods/letta/Packer 等 - 2024 - MemGPT Towards LLMs as Operating Systems.pdf` | legacy MemGPT paper 与 current Letta product 差异大，须分 identity | M7 |
| LangMem | `langchain-ai/langmem@56d8593`，package 0.0.30 | 暂无本地正式论文；先查官方 README/docs/blog/technical report | 五格当前均 framework extension；不可因无 paper 只抄 factory default | M8 |
| EverOS | `EverMind-AI/EverOS@v1.2.3/48fc908` + 两个可重放 patch | 本地 `EverMemOS.pdf` 不属于 fetch 恢复资产；另有 EverAlgo source/tag | product、EverAlgo research 与 paper-reported LME 必须分栏 | M9 |
| Graphiti OSS | `getzep/graphiti@v0.29.3/021d3a5` | 暂无本地正式 paper；先查官方 architecture/docs/technical report | 只声明 Graphiti OSS，不借 Zep hosted product/paper 结果 | M10 |

source identity 以 `third_party/methods/MANIFEST.md` 为准。未跟踪 PDF 可作为当前机器上的阅读材料，
但不是可重放项目资产；正式判词必须补稳定 URL/hash 或明确 `local-only evidence`。

## 3. 官方 benchmark / prompt 资产初始盘点

| method | Phase 1 官方覆盖（既有稳定页，待本批复核） | 当前 author builder | 初始缺口 |
| --- | --- | --- | --- |
| LightMem | LoCoMo、LongMemEval；HaluMem/BEAM/MemBench 身份在 M1 重新核 paper/repo | `author/lightmem.py` | LoCoMo/LME final messages、decode、parser、paper parameter parity 重验 |
| A-Mem | 已知独立 eval repo 含 LoCoMo；其余格待 M2 搜索 | `PROMPT_MISSING` | 已知 LoCoMo prompt 遗漏；eval repo revision provenance 也待补 |
| Mem0 | current/legacy harness 涉及 LoCoMo、LongMemEval，BEAM 覆盖待 M3 一手复核 | `author/mem0.py` | 双 namespace/role reversal 是否 topology variant；各 harness 版本不要拼接 |
| MemoryOS | 官方公开 LoCoMo | `author/memoryos.py` | 角色扮演完整 builder、paper/eval/PyPI effective 参数对表 |
| MemOS | 官方 LoCoMo、LongMemEval harness | `PROMPT_MISSING` | harness batching/readout 与 product typed-handler 差异；是否有完整 answer builder |
| SimpleMem | 论文/repo benchmark 覆盖待 M6 从 paper 与 scripts 重建 | `PROMPT_MISSING` | 三阶段参数、官方 final answer messages 和 parser 尚未系统登记 |
| Letta/MemGPT | current official repo 对五格均无 harness（既有稳定页） | `PROMPT_MISSING` | 若搜索仍无公开 harness，应明确 `SOURCE_UNAVAILABLE`，不造 author section |
| LangMem | current official repo 对五格均无 harness（既有稳定页） | `PROMPT_MISSING` | 官方技术材料与公开 eval 搜索；大概率无 author Phase 1 builder |
| EverOS | public harness 覆盖 LoCoMo；论文报告 LME 但公开 loader/final payload 未找到 | `PROMPT_MISSING` | LoCoMo official builder；LME 若仍无 source 则标 paper-only/unavailable |
| Graphiti OSS | current stable repo 只有 LME graph-building eval，不含完整 search/answer/judge | `PROMPT_MISSING` | 不把 build-only harness 冒充完整 author builder；其余四格为 extension |

这里的“官方覆盖”只用于安排检索优先级。只有 corresponding method note 闭合 repo/commit、dataset、
最终 payload、prompt messages 与 parser 后，才能把格子升级为 `AUTHOR_READY`。

## 4. 当前 TOML 基线

十家 `configs/methods/<method>.toml` 当前都只有单一 `[method]` section；API runtime、benchmark
evaluation 和 execution 已在 ws05 前置批次移出 method TOML。这是结构基线，不代表值已完成
provenance：

| method | TOML | author section | 本任务重点 |
| --- | --- | --- | --- |
| LightMem | `configs/methods/lightmem.toml` | 无 | `pre_compress`、role/profile、segment/summary/update 与高影响数值 |
| A-Mem | `configs/methods/amem.toml` | 无 | evolution/retriever/embedding 与 eval repo effective config |
| Mem0 | `configs/methods/mem0.toml` | 无 | current product config、rerank/graph/extraction 与 topology variant |
| MemoryOS | `configs/methods/memoryos.toml` | 无 | STM/MTM/LPM 容量、阈值、官方 LoCoMo 参数 |
| MemOS | `configs/methods/memos.toml` | 无 | reader/scheduler/search/add mode 与 author batching |
| SimpleMem | `configs/methods/simplemem.toml` | 无 | compression/synthesis/retrieval、window/overlap/parallel semantics |
| Letta | `configs/methods/letta.toml` | 无 | current SDK/product profile、core blocks、embedding omission |
| LangMem | `configs/methods/langmem.toml` | 无 | manager strategy、update/delete、store/search defaults |
| EverOS | `configs/methods/everos.toml` | 无 | Episode extraction/search/flush/group 与 controlled embedding |
| Graphiti | `configs/methods/graphiti.toml` | 无 | episode extraction、graph search/rerank 与 product defaults |

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
- 下一步从 LightMem 开始：完整读 paper，建立算法阶段图，再核 LoCoMo/LME harness 与 current
  config/call path。M1 未验收前不开始 A-Mem。
