---
id: ws05-qa-task-aggregation
parent: ws05
status: in-progress
created: 2026-08-26
---
# QA 任务类型与跨 benchmark 聚合

## 范围

本支线只解决五个 benchmark 的 **QA/readout 效果如何公平汇总**。主榜不纳入
Recall@K、Precision@K、HaluMem Extraction、HaluMem Updating 或 memory-type；这些能力仍按
`valid / N/A / pending` 独立报告，不能因某家 method 不具备细粒度 provenance 而污染 QA 总分。

## 已确认边界

- 主报告同时给出：固定题池 pooled-micro 总榜、跨 benchmark 能力画像、原生 task 明细、覆盖率、
  不确定性与成本/效率旁表；不再做 benchmark 等权 headline。
- 缺 run、失败 run、identity 不可比都记 incomplete；不补零、不按剩余格平均。最终榜只接受
  10 method × 5 benchmark 全覆盖的正式 cohort。
- Recall/Precision/NDCG 与 HaluMem operation 指标不混进 QA raw score。
- 五家原生 task、横向 taxonomy、abstention M0 与题目级 pooled 权重均已确认。
- Abstention M0 只按固定 answer LLM 输出判分；retrieval boundary 是后续增强，本合同不宣称已测。
- 当前可执行映射版本是 `qa-task-aggregation-v2-draft`，只供强反例和讨论，不得用于 formal 排名。

## 当前断点

M0-R1 讨论已闭合，正式人类可读合同与 spec v3 已落盘；现有 Python 仍是
`qa-task-aggregation-v2-draft`，不得 formal 排名。下一批 M0-R2 实现 BEAM 整题顺序 judge、三档
selector、最终 taxonomy 与 pooled-micro artifact；真实 API 与 pilot 继续暂停。

## 文档索引

- [spec.md](spec.md)：研究问题、estimand、公式与验收边界。
- [plan.md](plan.md)：M0 实施与验证步骤。
- [研究与裁决证据](notes/2026-08-26-qa-task-aggregation-research.md)：五家 task census、外部方法学、
  备选方案与取舍。
- [M0 实现验收](notes/2026-08-26-qa-task-aggregation-m0-implementation.md)：实现范围、测试与发布边界。
- [五家独立任务类型调查](../../../../survey/qa-task-types/README.md)：用户审阅入口。
- [正式聚合合同](../../../../survey/qa-task-types/aggregation.md)：最终 taxonomy、题分、边界与权重。
- [已归档讨论稿](../../../../survey/qa-task-types/aggregation-draft.md)：三种旧候选与裁决过程。
- [v3 最终裁决](notes/2026-08-26-qa-task-aggregation-v3-ruling.md)：用户确认与一手证据摘要。
- [M0-R1 v2 候选记录](notes/2026-08-26-qa-task-taxonomy-v2-ruling.md)：一手复核与被用户重开的旧候选。
- [Boundary/文档拆分重开](notes/2026-08-26-boundary-and-document-split-reopen.md)：本轮用户纠正、
  typed zero-hit 缺口与新交付结构。
