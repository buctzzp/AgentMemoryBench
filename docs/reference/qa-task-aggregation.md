# Phase 1 QA 任务类型与聚合契约

> 当前版本：`qa-task-aggregation-v1`（2026-08-26）。这是主实验报告的稳定入口；研究证据与
> 备选方案见 [ws05 支线 note](../workstreams/ws05-experiment-reporting/branches/qa-task-aggregation/notes/2026-08-26-qa-task-aggregation-research.md)。

## 1. 主榜边界

主榜只比较五个 benchmark 的 QA/readout 效果：LoCoMo、LongMemEval、BEAM、MemBench、
HaluMem QA。Recall/Precision/NDCG、HaluMem Extraction/Updating/memory-type 均另表报告；
N/A 不扣 QA 分，也不得为填榜伪造能力。

## 2. 报告结构

1. **Overall QA**：五 benchmark 各一票，固定十家 method 内平均名次归一到 0–100。
2. **Capability profile**：按下表的 primary capability 跨 benchmark 聚合。
3. **Native task detail**：保留每家原生命名、raw metric、样本数与原生聚合。
4. **Coverage/guardrail**：缺 run、失败、parse-failed、HaluMem H/O、身份不一致。
5. **Efficiency/cost**：单独报告，必要时画 quality-cost Pareto；不混进质量总分。

## 3. Primary capability 映射

| capability | LoCoMo | LongMemEval | BEAM | MemBench | HaluMem |
|---|---|---|---|---|---|
| direct recall | 4 | single-session-user, single-session-assistant | information_extraction | simple | Basic Fact Recall |
| multi-evidence reasoning | 1 | multi-session | multi_session_reasoning | conditional, comparative, aggregative, post_processing, lowlevel_rec, RecMultiSession | Multi-hop Inference |
| temporal/sequence reasoning | 2 | temporal-reasoning | temporal_reasoning, event_ordering | — | — |
| dynamic update | — | knowledge-update | knowledge_update | knowledge_update | Dynamic Update |
| memory-grounded inference/application | 3 | single-session-preference | preference_following | highlevel, highlevel_rec | Generalization & Application |
| conflict resolution | — | — | contradiction_resolution | — | Memory Conflict |
| epistemic boundary | — | question_id suffix `_abs` | abstention | — | Memory Boundary |
| instruction following | — | — | instruction_following | — | — |
| summarization | — | — | summarization | — | — |
| noise robustness | — | — | — | noisy | — |

每题恰好一个 primary capability。instruction following 不与 personalization 合并；role、speaker、
单/多 session、source role、fact/preference/event 和 noise/conflict/abstention 只作为 secondary
diagnostic axis。

## 4. 公式

固定 roster 为十家 method；同分取平均名次：

```text
benchmark_rank_score = (10 - rank) / 9
overall_qa            = 100 * 五个 benchmark_rank_score 的平均
```

能力族先在每个 benchmark 内对原生 task 做宏平均，再在该 benchmark 内对十家 method 排名，
最后对 contributing benchmarks 等权平均。一个 benchmark 对一个能力族最多一票。只有一家
benchmark 的能力只作 diagnostic，不产生 cross-benchmark capability score。

## 5. QA primary score

- LoCoMo：F1；LongMemEval：官方 judge accuracy；MemBench：choice accuracy；HaluMem：QA Correct。
- BEAM 普通 ability 用 float rubric score；event_ordering 用官方报告实际消费的 `tau_norm`。
- 五个 raw score 只在各自 benchmark 内比较，不直接相加。

## 6. 发布门

- 主排名只接受 `formal` 完整 10×5 cohort；pilot/smoke 只验管线。
- 同一 benchmark 的 variant、data/question cohort、answer model/prompt/transport、judge
  model/prompt/transport 必须相同。
- 缺格为 incomplete：不补零、不缩分母、不借旧 artifact 拼榜。
- raw score、rank、rank-score、question/native-task 数、coverage 与 contract version 必须同时落盘。
- 95% CI 采用 isolation-level paired cluster bootstrap；API 随机性不在该区间内，需另做 repeat。
