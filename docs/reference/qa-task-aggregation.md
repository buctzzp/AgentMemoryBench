# Phase 1 QA 任务类型与聚合执行契约

当前版本：`qa-task-aggregation-v3`（2026-08-26）。用户已确认 taxonomy、逐题 score 与权重；
M0-R2 可执行内核已实现。正式方法排名仍须等待 M1 锁定完整 10×5 cohort receipt。

人类可读的完整裁决见 [稳定聚合合同](../survey/qa-task-types/aggregation.md)，五家原生题型、
例子与 scorer 见 [任务类型调查索引](../survey/qa-task-types/README.md)。

## 1. 聚合边界

主榜只比较 LoCoMo、LongMemEval、BEAM、MemBench 与 HaluMem 的 QA/readout。Recall、
Precision、NDCG、HaluMem extraction/update/memory-type 与成本效率均单独报告，不混入 QA。

可答性边界 M0 只看固定 framework answer reader 的最终输出；它不宣称 provider 检索为空。
LoCoMo category 5 与 MemBench noisy 明确排除，后者只保留为单家诊断。

## 2. 十一项能力

1. `factual_recall_extraction`
2. `multi_evidence_recall_reasoning`
3. `temporal_event_reasoning`
4. `memory_update`
5. `false_premise_correction`
6. `history_contradiction_resolution`
7. `personalization`
8. `instruction_following`
9. `answerability_boundary`
10. `generalization_application`
11. `long_horizon_summarization`

记忆更新、HaluMem 错误前提纠正与 BEAM 历史内部矛盾消解是三个不同成功行为；偏好个性化
与显式指令遵循也保持分离。

## 3. 逐题 credit

| benchmark | v3 聚合题分 | 继续旁报的原生面 |
| --- | --- | --- |
| LoCoMo | `locomo_judge_accuracy` 的 `0/1` | `locomo_f1` |
| LongMemEval | 官方 task-specific judge 的 `0/1` | native type accuracy |
| HaluMem | Correct=1，Hallucination/Omission=0 | C/H/O 比例 |
| MemBench | choice exact `0/1` | choice/parse diagnostics |
| BEAM 普通九类 | item 全 1→1、全 0→0、其余→0.5 | float rubric mean、official-int parity |
| BEAM event ordering | 有序整题 judge 的 `0/0.5/1` | item rubric、F1、`tau_norm`、official final |

BEAM 新字段由 `beam-question-credit-v1` 盖章。旧 score row 缺
`aggregation_question_credit`、版本或匹配 profile 时 fail-loud，不回落到 rubric mean 或 tau。
event-ordering 整题 prompt 标为 `framework_ordered_compound_rubric_v1`，不会冒充官方指标。

## 4. 逐题 pooled micro

```text
capability_score(m, c) = sum(question_credit[m, q] for q in Q[c]) / |Q[c]|
overall_qa(m)           = sum(question_credit[m, q] for q in Q)    / |Q|
```

一题一票，不做 benchmark 等权、average-rank 归一化或 native-task macro。machine report 同时
写入 `credit_sum`、`question_count`、均值、benchmark contribution 与基于 pooled score 的并列
平均名次；排名不反向参与分数。

缺格、失败、run scope 错误、dataset/question/answer/evaluator identity 不一致均输出
`incomplete`，不得缩小分母。LongMemEval S/M 与 HaluMem Medium/Long 的同一 question identity
在一个正式 cohort 中只能选择一个 variant。

## 5. 当前发布门

- M0-R2 已完成 deterministic kernel、BEAM evaluator receipt、artifact loader 与 pooled report。
- 旧 `qa-task-aggregation-v2-draft` 只读，不与 v3 混合。
- M1 仍须生成正式 cohort receipt，锁 variant、完整 question IDs、十家 run IDs 与 answer/judge
  identity；在该门完成前不得发布正式排名。
- M2 才加入 isolation-level paired cluster bootstrap 与最终人类可读报告。
