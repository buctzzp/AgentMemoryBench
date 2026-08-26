# QA Task Aggregation v1 Spec

## 1. 研究问题

本合同回答两个不同问题，禁止混写：

1. **整体 QA**：在固定五 benchmark、固定十家 method、相同 controlled 运行身份下，哪家 method
   的总体 QA/readout 表现更好？
2. **能力画像**：哪家 method 在直接回忆、多证据整合、时间/顺序推理、动态更新等可跨数据集复现的
   能力上更强？

检索级 lineage、HaluMem session extraction/update 和 memory-type 不属于这两个 estimand。

## 2. 输入与资格

- 输入只能是不可变 prediction/evaluation artifacts；聚合不重新调用 method、answer LLM 或 judge。
- 主榜只接受 `formal`、同 benchmark variant/data fingerprint、相同公开 question cohort、相同
  answer/judge transport 与 prompt identity 的运行。
- 固定 roster 为 Phase 1 十家 method。缺格、失败、旧 identity 或 question coverage 不一致均为
  `incomplete`，不得插值、补零或按较小分母排名。
- 只消费每个 benchmark 的一个 QA primary metric：LoCoMo F1、LongMemEval judge accuracy、
  MemBench choice accuracy、HaluMem QA Correct rate，以及 BEAM 的 type-aware score。

## 3. Score selector

所有题分投影到 `[0, 1]`，但数值语义仍不同，因此只在同一 benchmark/task slice 内排序。

- LoCoMo：`locomo_f1.score`。
- LongMemEval：`longmemeval_judge_accuracy.score`。
- MemBench：`membench_choice_accuracy.score`。
- HaluMem：`halumem_qa.score`；Hallucination/Omission rate 另作 guardrail。
- BEAM：九类普通 ability 用保留 0.5 信息的 float rubric `score`；`event_ordering` 按官方
  `report_results.py` 的有效消费面用 `details.event_ordering_tau_norm`。论文 parity 仍另报官方
  `int()` 对照值，不把截断缺陷带入 controlled 主榜。

## 4. 聚合公式

设固定 roster 大小为 `M=10`，method `m` 在 benchmark `b` 的 raw QA 分为 `s[m,b]`。
同分使用平均名次，名次越小越好：

```text
rank_score(m,b) = (M - rank(m,b)) / (M - 1)
overall_qa(m)   = 100 * mean_b(rank_score(m,b))
```

因此每个 benchmark 恰好 20% 权重。同步报告 `mean_rank`、五个 raw score 和五个 benchmark
rank；总分不能脱离 roster/version 单独解释。

能力族 `t` 在 benchmark `b` 内若含多个原生 task，先宏平均原生 task：

```text
native_mean(m,b,c) = mean(question_score for native task c)
slice(m,b,t)       = mean_c(native_mean(m,b,c))
capability(m,t)    = 100 * mean_b(rank_score(slice(m,b,t)))
```

这避免某 benchmark 因题量或映射进来的子类型更多而增权。一个跨 benchmark capability 至少需要
两家 benchmark；否则只输出 native diagnostic。

## 5. 统计与解释

- 95% 区间按 benchmark 的 isolation unit 做**配对 cluster bootstrap**；同一次抽样对十家 method
  使用相同 isolation id，再完整重算 native mean、rank 与 aggregate。
- LoCoMo=conversation，LongMemEval=instance，BEAM=conversation，MemBench=tid，
  HaluMem=UUID。不得把同一 isolation 内的题当独立样本。
- 区间只覆盖数据抽样不确定性；一次 API 生成/judge 的随机性另行通过 repeat/seed sensitivity 报告。
- 五个顶层 benchmark 对显著性检验功效很低；不把一次 Friedman/Wilcoxon 的 p 值包装成确定性结论。
- Overall 只是一条 headline；能力画像、原生 task、覆盖率、失败率、H/O guardrail 与成本必须同屏。

## 6. 硬反例

实现必须拒绝：

1. 把 Recall/HaluMem extraction/update 混入 QA overall；
2. 对五个 raw metric 直接算术平均；
3. BEAM event-ordering 读取普通 rubric score；
4. 一个问题进入两个 primary capability；
5. 按问题数给 benchmark 或 capability 隐式加权；
6. 缺格后缩小分母、补 0 或用 table min/max normalization；
7. pilot/smoke 与 formal，或不同 model/prompt/judge identity 混成一个 cohort；
8. 把单 benchmark diagnostic 宣称成跨 benchmark 能力分。
