# QA task aggregation M0-R2 实现记录

日期：2026-08-26。范围：零真实 API 的 v3 可执行合同升级。

## 1. 实现结果

- `qa-task-aggregation-v3` 取代可执行 `v2-draft`；LoCoMo primary selector 改读冻结的
  `locomo_judge_accuracy`，F1 继续作为 native metric。
- taxonomy 拆开 `memory_update`、`false_premise_correction`、
  `history_contradiction_resolution`；MemBench noisy 与 LoCoMo category 5 显式排除并记账。
- capability、benchmark 与 overall 全部按纳入题目 pooled micro；输出分子、分母、均值和排名，
  排名不参与分数。
- BEAM 普通九类由纯内核把 rubric items 规约成 `0/0.5/1`；event ordering 在原生 item rubric、
  LLM equivalence、F1/tau 之外新增一个有序整题 judge。旧原生字段保持不变。
- BEAM question credit 由 `beam-question-credit-v1`、source 与 profile 盖章；聚合 loader 对旧字段、
  错版本、错 profile 与非三档分 fail-loud。

## 2. 一手运行路径

```text
BEAM evaluator
  official per-item rubric calls
  + official event equivalence/F1/tau (event only)
  + framework ordered compound-rubric call (event only)
  -> immutable beam_rubric_judge score row
  -> aggregation_question_credit + version/profile receipt

artifact-only aggregation
  public_questions + selected answer-score artifact + manifest/inventory/summary
  -> effective native task
  -> exactly one primary capability
  -> question pooled micro
```

聚合阶段不读取 retrieval artifact，也不调用 method、answer LLM 或 judge。LongMemEval `_abs`、
BEAM abstention 与 HaluMem Memory Boundary 因此严格是 fixed-reader answer utility，不冒充纯
retrieval boundary。

## 3. 强反例

- event 内容齐全但完全倒序：逐 item 均为 1 仍不能继承整题满分；整题 credit 可为 0。
- event 内容齐全但局部错序：整题 credit 可为 0.5。
- event judge 返回 0.75：fail-loud。
- 旧 BEAM row 只有 rubric/tau、没有 v3 receipt：fail-loud，不回落。
- MemBench conditional 题数更多：capability 得分按 10/14，而不是五个 native subtype 等权 1/5。
- 一家 benchmark 有 10 题、另外四家各 1 题：overall 按 14 题 pooled，能推翻 benchmark 等权多数。
- MemBench noisy 仍可有原生 score row，但从 v3 question scores 与分母排除。
- LongMemEval abstention loader 在没有 retrieval artifact 时仍只从 answer judge 得到边界题分。

## 4. 兼容与发布边界

- 旧 prediction artifact 不修改；新增 evaluator 可以独立生成新 BEAM score artifact。
- 旧 `qa-task-aggregation-v2-draft` 结果不得混入 v3，也不存在 resume 到 v3 的路径。
- 本批只完成计算内核与 artifact receipt；正式 10×5 cohort IDs、固定 question receipt、报告写出
  与 paired cluster bootstrap 仍属于 M1/M2。
- 未运行真实 API 或实验；所有 LLM 分支均由 fake client 验证。

## 5. 验证

- 核心 + 扩大 evaluator/runner 回归：`110 passed in 8.93s`。
- 架构/文档/注册/runner/BEAM/聚合承重集：`125 passed in 13.96s`。
- 全量：`2 failed, 2326 passed, 3 deselected, 25 warnings, 29 subtests passed in 198.35s`。
  两个失败均来自 `tests/test_method_integration_ledgers.py` 的 EverOS/Letta ledger requirement 与
  v1 template 漂移。受影响五条路径相对本批基线 `3e801fc` 零 diff；在该 commit 的 detached
  隔离 worktree 复跑同文件仍为 `2 failed, 5 passed in 0.08s`，证明是预存债务而非 M0-R2 回归。
- `ruff` 不在当前 workspace 依赖中，调用结果为 `No such file or directory`，未据此改动代码；
  后续以 pytest、Python 编译、文档门与全量回归为准。
