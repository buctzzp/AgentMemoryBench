---
id: ws05-qa-task-aggregation
parent: ws05
status: accepted
created: 2026-08-26
---
# QA 任务类型与跨 benchmark 聚合

## 范围

本支线只解决五个 benchmark 的 **QA/readout 效果如何公平汇总**。主榜不纳入
Recall@K、Precision@K、HaluMem Extraction、HaluMem Updating 或 memory-type；这些能力仍按
`valid / N/A / pending` 独立报告，不能因某家 method 不具备细粒度 provenance 而污染 QA 总分。

## 当前裁决

- 主报告同时给出：五 benchmark 等权总榜、跨 benchmark 能力画像、原生 task 明细、覆盖率、
  不确定性与成本/效率旁表。
- 五 benchmark 总榜采用固定十家 roster 的 benchmark 内平均名次；不直接平均异构 raw metric。
- 能力榜先在单个 benchmark 内对映入同一能力族的原生 task 做宏平均，再做 benchmark 内排名，
  最后跨 benchmark 等权平均。一个 benchmark 对一个能力族最多一票。
- 同一道题恰好一个 primary capability。role、speaker、single/multi-session、source role、noise 等
  是 secondary axis，只作切片；不得再次进入总榜。
- 缺 run、失败 run、identity 不可比都记 incomplete；不补零、不按剩余格平均。最终榜只接受
  10 method × 5 benchmark 全覆盖的正式 cohort。
- 单 benchmark 独有能力只作 diagnostic，不伪装成“跨 benchmark 能力分”。
- 现行算法与映射见 [稳定契约](../../../../reference/qa-task-aggregation.md)。

## 当前断点

M0 已验收：稳定 taxonomy、artifact-only 聚合内核、BEAM event-ordering 有效 score selector、
固定 roster/identity 完成门和强反例均已落盘。真实 API 与 pilot 仍暂停；下一步是 M1，在首批
formal 前补 machine-readable cohort receipt 与报告写出面，再把 paired cluster bootstrap 接到
完整 cohort，而不是让 smoke/pilot 先生成方法排名。

## 文档索引

- [spec.md](spec.md)：研究问题、estimand、公式与验收边界。
- [plan.md](plan.md)：M0 实施与验证步骤。
- [研究与裁决证据](notes/2026-08-26-qa-task-aggregation-research.md)：五家 task census、外部方法学、
  备选方案与取舍。
- [M0 实现验收](notes/2026-08-26-qa-task-aggregation-m0-implementation.md)：实现范围、测试与发布边界。
