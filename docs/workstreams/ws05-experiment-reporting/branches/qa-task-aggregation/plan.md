# QA Task Aggregation v3 Plan

## M0 — 开跑前合同

- [x] 逐一核查五家官方 task type、current adapter category 和 score artifact。
- [x] 比较 raw mean、anchored normalization、average rank 与多维报告的适用边界。
- [x] 冻结 QA-only taxonomy、唯一 primary mapping、secondary axes 与缺失策略。
- [x] 实现 artifact-only taxonomy/score selector/benchmark slice/rank aggregation 内核。
- [x] 增加强反例：重复计权、缺 roster、BEAM event-ordering、tie、宏/微平均、未知类型。
- [x] 更新 ws05/roadmap/稳定索引并通过定向测试、文档门与 `git diff --check`。

## M0-R1 — 五家任务调查与用户裁决（已完成）

- [x] 五家全量/官方 task taxonomy 复核并给每类补真实 locator 与通俗定义。
- [x] 建立五份独立 benchmark task 文档与一份 aggregation discussion draft。
- [x] 修正 MemBench noisy：原生 task 是 query 前缀碎碎念；100K 历史 NoiseData 是另一条轴。
- [x] 修正 boundary：retrieval boundary 与 answer abstention 分层；记录 `None`/空 tuple 可观测缺口。
- [x] 用户确认 update、错误前提纠正、历史内部矛盾消解拆分。
- [x] 用户确认 personalization/instruction 分离。
- [x] 用户确认 lowlevel_rec=事实回顾，noisy 不进入聚合。
- [x] 用户确认 abstention M0 只看固定 answer LLM 输出，retrieval boundary 延后。
- [x] 用户确认题目级 pooled micro，不做 benchmark 等权。
- [x] 用户确认 BEAM 普通题与 event ordering 均使用 framework-standardized 三档 question credit；
  event ordering 的整题 judge 同时检查内容与顺序，native F1/tau/rubric 继续保留。
- [x] 稳定合同、裁决 note 与 spec v3 落盘。

## M0-R2 — 可执行合同升级（当前）

- [x] 新增 BEAM event-ordering ordered compound-rubric judge 输出与 evaluator identity。
- [x] 为 BEAM 普通题实现确定性的 question-level 三档 selector。
- [x] 把 executable taxonomy 从 `v2-draft` 升级为 v3：拆分三类 revision/conflict、移除 noisy。
- [x] 把主 selector 改为 answer-correctness + question pooled micro；旧 v2 artifact 只读不 resume。
- [x] 增加强反例：倒序但内容齐全、部分错序、混合 rubric、abstention 只读 answer、题数权重。
- [x] 定向测试、文档门与架构验收通过；全量仅保留基线已复现的两个 ws02.7 ledger 失败，
  M0-R2 相对基线零回归。下一步可进入 M1。

## M1 — 正式 cohort 组装（首批 formal 前）

- [ ] 从 run manifests 生成 cohort receipt，验证 data/question/answer/judge identity。
- [ ] 锁十家×五家 run-id 清单；pilot 只验证管线，不发布方法排名。
- [ ] 输出 machine-readable QA report artifact 与人类可读表格。

## M2 — 不确定性与报告（完整 cohort 后）

- [ ] isolation-level paired cluster bootstrap（固定 seed、次数与 method 共用抽样）。
- [ ] 输出 overall、capability、native task、coverage/guardrail、cost/efficiency 五个表面。
- [ ] 如需显著性主张，预先登记比较集合与多重比较校正；否则只作描述性排序。
