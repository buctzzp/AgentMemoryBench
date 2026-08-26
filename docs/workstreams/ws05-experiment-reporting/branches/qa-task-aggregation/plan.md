# QA Task Aggregation v1 Plan

## M0 — 开跑前合同（当前）

- [x] 逐一核查五家官方 task type、current adapter category 和 score artifact。
- [x] 比较 raw mean、anchored normalization、average rank 与多维报告的适用边界。
- [x] 冻结 QA-only taxonomy、唯一 primary mapping、secondary axes 与缺失策略。
- [x] 实现 artifact-only taxonomy/score selector/benchmark slice/rank aggregation 内核。
- [x] 增加强反例：重复计权、缺 roster、BEAM event-ordering、tie、宏/微平均、未知类型。
- [x] 更新 ws05/roadmap/稳定索引并通过定向测试、文档门与 `git diff --check`。

## M1 — 正式 cohort 组装（首批 formal 前）

- [ ] 从 run manifests 生成 cohort receipt，验证 data/question/answer/judge identity。
- [ ] 锁十家×五家 run-id 清单；pilot 只验证管线，不发布方法排名。
- [ ] 输出 machine-readable QA report artifact 与人类可读表格。

## M2 — 不确定性与报告（完整 cohort 后）

- [ ] isolation-level paired cluster bootstrap（固定 seed、次数与 method 共用抽样）。
- [ ] 输出 overall、capability、native task、coverage/guardrail、cost/efficiency 五个表面。
- [ ] 如需显著性主张，预先登记比较集合与多重比较校正；否则只作描述性排序。
