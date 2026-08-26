# Phase 1 QA 任务类型与聚合合同

状态：**用户与架构师已于 2026-08-26 对齐；M0-R2 可执行内核为
`qa-task-aggregation-v3`，M1 receipt/write surface 为 `qa-cohort-receipt-v1`。首批 formal
artifact 尚未产生，真正 `status=ok` 的 10×5 receipt 完成前仍不得发布排名；旧
`qa-task-aggregation-v2-draft` 不得混入。**

本文只聚合五个 benchmark 的 QA/readout。Recall@K、Precision@K、NDCG、HaluMem
extraction/update/memory-type 与成本效率均单独报告，不混入 QA 总分。

## 1. 最终能力映射

| 能力 | LoCoMo | LongMemEval | BEAM | MemBench | HaluMem |
| --- | --- | --- | --- | --- | --- |
| 事实回顾/信息抽取 | category 4 | single-session user/assistant | information_extraction | simple、lowlevel_rec | Basic Fact Recall |
| 多证据/跨会话推理 | category 1 | multi-session | multi_session_reasoning | conditional、comparative、aggregative、post_processing、RecMultiSession | Multi-hop Inference |
| 时间与事件顺序 | category 2 | temporal-reasoning | temporal_reasoning、event_ordering | — | — |
| 记忆更新 | — | knowledge-update | knowledge_update | knowledge_update | Dynamic Update |
| 错误前提纠正 | — | — | — | — | Memory Conflict |
| 历史内部矛盾消解 | — | — | contradiction_resolution | — | — |
| 个性化/偏好应用 | — | single-session-preference | preference_following | highlevel、highlevel_rec | — |
| 指令遵循 | — | — | instruction_following | — | — |
| 可答性边界 | category 5 不接入 | `_abs` | abstention | — | Memory Boundary |
| 泛化应用 | category 3 | — | — | — | Generalization & Application |
| 长期总结 | — | — | summarization | — | — |

裁决说明：

- update、HaluMem question-vs-history 错误前提、BEAM history-internal contradiction 是三种不同
  成功行为，不再压进同一个 `memory_revision`。
- preference/personalization 与 instruction following 分开。
- MemBench `lowlevel_rec` 是对 assistant 既往推荐记录的事实回顾；`highlevel_rec` 才是偏好推断。
- LoCoMo category 5 继续排除；MemBench `noisy` 只作单家 query-noise diagnostic，不进入能力分或
  overall。

## 2. M0 逐题分数合同

聚合统计的共同语义是“该题回答获得多少正确性 credit”，不是把 token F1、rubric mean 和
Kendall tau 直接混合。每题只贡献一次。

| benchmark / task | 聚合用题分 | 原生面继续报告 |
| --- | --- | --- |
| LoCoMo | answer LLM 输出经冻结的 LoCoMo semantic judge 判 `0/1` | token F1 |
| LongMemEval | 官方 task-specific yes/no judge 判 `0/1` | 原生 type accuracy |
| HaluMem | `Correct=1`，`Hallucination/Omission=0` | C/H/O 比例 |
| MemBench | A/B/C/D exact 判 `0/1` | choice accuracy |
| BEAM 普通九类 | rubric item 均为 1 → 1；均为 0 → 0；其余 → 0.5 | 每 item `0/0.5/1`、题级 rubric mean、official-int parity |
| BEAM event ordering | 对完整**有序** reference 与回答做整题 LLM judge：完全正确顺序=1，部分内容/局部错序=0.5，根本错误=0 | rubric mean、F1、`tau_norm`、official `final_score` |

BEAM event ordering 的共享 item judge 只检查单个事件是否出现，不能独自判断排列；聚合用的整题
judge 必须把有序 rubric 构造成一个 compound criterion，明确同时检查事件集合和相对顺序。它是
framework-standardized score，不冒充官方 `tau_norm`。

## 3. Abstention M0 边界

本阶段从简：LongMemEval `_abs`、BEAM abstention、HaluMem Memory Boundary **只根据固定
framework answer LLM 的最终输出**，由各自官方/冻结 answer judge 判分。它衡量的是
`memory output -> fixed reader` 的拒答效用，不宣称是纯 retrieval boundary。

typed zero-hit、retrieved-bundle sufficiency 与 `items=None`/`items=()` 可观测性列为后续增强；本批
不实现、不阻塞 QA 聚合，也不得用旧 artifact 的空 list 反推 retrieval 做对了。

## 4. 题目级 pooled micro

对固定 cohort 中全部纳入题目一题一票，不再给 benchmark 人工等权：

```text
capability_score(m, c) = sum(question_credit[m, q] for q in Q[c]) / |Q[c]|
overall_qa(m)           = sum(question_credit[m, q] for q in Q)    / |Q|
```

- `Q[c]` 跨 benchmark 合并相同能力的全部唯一问题；不按 benchmark 再加权。
- LongMemEval S/M 和 HaluMem Medium/Long 的同一 question identity 只能在一个 cohort 中计一次。
- `_abs` 是覆盖原 native type 的 effective task，一题不得同时进入原类型和 boundary。
- 缺 run、失败 run、identity 不一致或 question coverage 不完整均标 `incomplete`，不得缩小分母后
  排名。
- 当前固定题池在排除 LoCoMo category 5 与 MemBench noisy 后为 8,957 题；正式 cohort receipt
  仍须锁 variant、question identity 与 evaluator identity。

## 5. 报告面

正式报告至少同时给出：

1. pooled QA overall 与题目数；
2. 上述十一项能力画像与各 benchmark 贡献数；
3. 五家 benchmark-native 原生 metric/task 明细；
4. answer abstention、HaluMem H/O 等 guardrail；
5. isolation-level paired uncertainty；
6. 成本、延迟、失败与覆盖率旁表。

M1 只消费调用方**显式列出的**标准 run 目录，不扫描 `outputs/` 自动猜测“最新结果”。它固定写出：

- `qa-cohort-receipt.json`：run-id、variant、题池/isolation/task、data、answer、judge 与 score-input
  哈希；
- `qa-aggregate-report.json`：机器可读 pooled-micro、能力、coverage 与阻断原因；
- `qa-aggregate-report.md`：紧凑人工审阅表。

缺格、非 formal scope 或任何身份漂移时三份文件仍可写出诊断，但 status 为 `incomplete`，overall
排名必须留空。生成阶段不调用 method、embedding、answer LLM 或 judge LLM。
