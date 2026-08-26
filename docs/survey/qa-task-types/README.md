# Phase 1 QA 任务类型调查索引

更新日期：2026-08-26。

本目录按用户要求把五个 benchmark **各自拆成一份独立任务类型文档**。这些文件回答“该
benchmark 原生有哪些题、每类题到底在测什么、真实例子是什么、官方怎样计分”；不会先把五家
硬压成一套已经定稿的横向 taxonomy。

## 阅读顺序

1. [LoCoMo](locomo.md)
2. [LongMemEval](longmemeval.md)
3. [BEAM](beam.md)
4. [MemBench](membench.md)
5. [HaluMem](halumem.md)
6. [跨 benchmark 聚合讨论稿](aggregation-draft.md)

## 状态边界

- 五份单家文档中的 source identity、原生类型、计数、例子和 scorer 是已复核的调查事实。
- “候选横向能力”以及聚合公式仍是**待用户与架构师讨论的草案**，不得作为正式方法排名合同。
- 检索级 Recall/NDCG、HaluMem extraction/update/memory-type 仍与 QA/readout 分开。
- 可答性边界目前明确拆成“memory retrieval boundary”与“answer abstention”两个可观测面；两者
  是否共同进入最终能力分，留在 aggregation draft 讨论，不提前代裁。

单家完整 schema、异常与 adapter 处置仍看 `docs/survey/benchmarks/`、`datasets/`、
`workflows/` 三联页；本目录不复制与 task type 无关的接入细节。
