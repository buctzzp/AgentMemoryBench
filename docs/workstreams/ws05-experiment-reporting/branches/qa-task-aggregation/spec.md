# QA Task Aggregation v3 Spec

状态：**taxonomy/score/weight 已于 2026-08-26 获用户确认；M0-R2 实现已验收，正式 cohort
receipt 尚待 M1。**
稳定的人类可读合同见 `docs/survey/qa-task-types/aggregation.md`。

## 1. Estimand

本合同回答：在固定 Phase 1 question cohort、相同 answer/judge identity 下，从纳入题池随机抽一题，
method 的期望 QA correctness credit 是多少；以及该期望值在十一项能力上的分解。

Recall/Precision/NDCG、HaluMem extraction/update/memory-type 与成本效率不属于 QA estimand。

## 2. 输入资格

- 只读不可变 prediction/evaluation artifacts；聚合本身不调用 method 或 answer LLM。
- 新增 BEAM event-ordering 三档 judge 属 evaluation 生成步骤，必须在聚合前完成并锁 evaluator
  identity。
- 正式 cohort 必须锁 method roster、benchmark variant、dataset/question identity、answer/judge
  transport、prompt/model/decode identity 与完整 question coverage。
- 缺格、失败、旧 identity、重复 question 或覆盖不一致均为 `incomplete`，不补零、不缩分母排名。

## 3. 唯一能力映射

正式能力为：

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

LoCoMo category 5 与 MemBench noisy 不进入本合同；未知 native task 必须 fail-loud 并 bump 合同。

## 4. Question credit selector

- LoCoMo：冻结 semantic judge 的 correct/wrong `0/1`；F1 只作 native metric。
- LongMemEval：官方 task-specific yes/no `0/1`。
- HaluMem：Correct=1，Hallucination/Omission=0。
- MemBench：choice exact `0/1`。
- BEAM 普通九类：all rubric items=1 → 1；all=0 → 0；其他 → 0.5。
- BEAM event ordering：整题 ordered-rubric judge 输出 0/0.5/1。输入必须包含问题、完整有序
  reference criterion 与回答；1=内容完整且顺序完全正确，0.5=部分正确/局部错序，0=根本错误。
  原生 rubric/F1/tau/final score 不作为该三档分的替代物，但继续并列落盘。

Abstention M0 只按 fixed answer reader 输出判分；retrieval zero-hit/sufficiency 不进入 v3。

## 5. 聚合

```text
capability_score(m,c) = sum(q.credit for q in fixed_Q[c]) / len(fixed_Q[c])
overall_qa(m)          = sum(q.credit for q in fixed_Q)    / len(fixed_Q)
```

- 一题一票，不做 benchmark 等权或 native-task macro。
- effective abstention 覆盖原 task，一题不得重复进入两个能力。
- LME S/M、HaluMem Medium/Long 的同 identity variant 在一个 cohort 中不得重复计权。
- 同屏报告 question/benchmark/capability 构成；题量权重是固定题池 estimand 的显式组成。

## 6. 不确定性与报告

- 区间按 isolation 做 paired cluster bootstrap：LoCoMo conversation、LME instance、BEAM
  conversation、MemBench tid、HaluMem UUID。
- 报告必须含 overall、capability、benchmark-native metrics、task/count/coverage、guardrail 与成本。
- overall 不替代原生表；framework-standardized BEAM 三档不得重标为官方分。

## 7. 硬反例

实现必须拒绝：

1. 把 retrieval/HaluMem operation 指标混进 QA；
2. 使用旧 benchmark-equal rank 公式；
3. 同一题按多个 metric 重复投票；
4. 把 LoCoMo F1 与 judge score直接混合；
5. 把 BEAM event-ordering 的逐 item rubric mean当成顺序正确性；
6. 删除 BEAM native F1/tau/rubric receipt；
7. 把 answer abstention 宣称为 retrieval zero-hit；
8. 缺格后缩分母，或重复计算同 identity 的不同长度 variant；
9. 把 MemBench noisy 或 LoCoMo category 5 偷带进固定题池；
10. 在 evaluator/answer identity 不一致时发布排名。
