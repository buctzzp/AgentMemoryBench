# QA Task Aggregation v2 Draft Plan

## M0 — 开跑前合同

- [x] 逐一核查五家官方 task type、current adapter category 和 score artifact。
- [x] 比较 raw mean、anchored normalization、average rank 与多维报告的适用边界。
- [x] 冻结 QA-only taxonomy、唯一 primary mapping、secondary axes 与缺失策略。
- [x] 实现 artifact-only taxonomy/score selector/benchmark slice/rank aggregation 内核。
- [x] 增加强反例：重复计权、缺 roster、BEAM event-ordering、tie、宏/微平均、未知类型。
- [x] 更新 ws05/roadmap/稳定索引并通过定向测试、文档门与 `git diff --check`。

## M0-R1 — 五家任务调查与用户裁决（当前）

- [x] 五家全量/官方 task taxonomy 复核并给每类补真实 locator 与通俗定义。
- [x] 建立五份独立 benchmark task 文档与一份 aggregation discussion draft。
- [x] 修正 MemBench noisy：原生 task 是 query 前缀碎碎念；100K 历史 NoiseData 是另一条轴。
- [x] 修正 boundary：retrieval boundary 与 answer abstention 分层；记录 `None`/空 tuple 可观测缺口。
- [ ] 用户确认 Conflict/update 的父能力关系。
- [ ] 用户确认 personalization/instruction 是否分离。
- [ ] 用户确认 MemBench recommendation 与 noisy 的归类。
- [ ] 用户确认 boundary headline 与 retrieval outcome 协议修复范围。
- [ ] 用户确认主权重方案及 raw/pooled sensitivity。
- [ ] 根据最终裁决升级正式 contract version、强反例与稳定文档。

## M1 — 正式 cohort 组装（首批 formal 前）

- [ ] 从 run manifests 生成 cohort receipt，验证 data/question/answer/judge identity。
- [ ] 锁十家×五家 run-id 清单；pilot 只验证管线，不发布方法排名。
- [ ] 输出 machine-readable QA report artifact 与人类可读表格。

## M2 — 不确定性与报告（完整 cohort 后）

- [ ] isolation-level paired cluster bootstrap（固定 seed、次数与 method 共用抽样）。
- [ ] 输出 overall、capability、native task、coverage/guardrail、cost/efficiency 五个表面。
- [ ] 如需显著性主张，预先登记比较集合与多重比较校正；否则只作描述性排序。
