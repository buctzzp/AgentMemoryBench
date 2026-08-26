# Phase 1 QA 任务类型与跨 Benchmark 聚合

更新日期：2026-08-26。本文是五家 QA task 的稳定横向入口；每类真实题目、官方字段与 scorer
细节见五张 benchmark 卡。计算合同与 artifact 实现另见
[`docs/reference/qa-task-aggregation.md`](../reference/qa-task-aggregation.md)。

## 1. 聚合回答什么

主聚合只回答：十家 method 在五个 benchmark 的 **QA/readout 能力**如何横向比较。
Recall/Precision/NDCG、HaluMem session extraction、operation-level updating 和 memory-type
资格并不齐全，继续独立报告，不进入 QA 总分，也不因 N/A 扣分。

报告保留三层，禁止只剩一个总分：

1. 五个 benchmark 的官方/主 QA raw score；
2. 跨 benchmark 的能力画像；
3. 五 benchmark 等权 overall rank-score。

## 2. QA 能力类型 v2

每道题只进入一个 primary capability。official native task 名仍保留在明细中，但不会因一个
benchmark 划得更细就获得更多跨 benchmark 权重。

| 能力 | LoCoMo | LongMemEval | BEAM | MemBench | HaluMem | 聚合解释 |
| --- | --- | --- | --- | --- | --- | --- |
| `factual_recall_extraction` 事实回顾与信息抽取 | category 4 | single-session-user / assistant | information_extraction | simple / lowlevel_rec | Basic Fact Recall | 从历史中恢复明确出现过的事实、细节或曾给出的具体推荐 |
| `multi_evidence_recall_reasoning` 跨会话与组合回忆/推理 | category 1 | multi-session | multi_session_reasoning | conditional / comparative / aggregative / post_processing / RecMultiSession | Multi-hop Inference | 需要多条、跨片段证据的过滤、比较、聚合或推导 |
| `temporal_event_reasoning` 时间与事件顺序 | category 2 | temporal-reasoning | temporal_reasoning / event_ordering | — | — | 计算时间间隔、判断先后或恢复事件顺序 |
| `memory_revision` 记忆更新 | — | knowledge-update | knowledge_update / contradiction_resolution | knowledge_update | Dynamic Update / Memory Conflict | 新旧信息变化或冲突时维护正确的当前状态；不另设 conflict 能力分 |
| `personalization` 个性化 | — | single-session-preference | preference_following | highlevel / highlevel_rec | — | 记住用户偏好、状态或习惯，并据此调整答案/推荐 |
| `instruction_following` 长期指令遵循 | — | — | instruction_following | — | — | 在很久以后仍遵守用户明确给出的格式、禁忌或行为约束 |
| `answerability_boundary` 可答性与记忆边界 | — | question id suffix `_abs` | abstention | — | Memory Boundary | 证据不足时识别“无法回答”，而不是用无关记忆编造答案 |
| `generalization_application` 常识推断与泛化应用 | category 3 | — | — | — | Generalization & Application | 基于已记住事实作未被逐字陈述的新推断或情境应用 |
| `long_horizon_summarization` 概括与长期总结 | — | — | summarization | — | — | 把长历史中的主题、进展、变化、目标与未决事项压缩成整体表述 |
| `noise_robustness` 噪声鲁棒性 | — | — | — | noisy | — | 正确证据仍存在但被无关信息包围时，仍能找到并回答 |

可跨 benchmark 发布的七类是：事实回顾、多证据回忆/推理、时间/顺序、记忆修订、个性化、
可答性边界和泛化应用。`instruction_following`、`long_horizon_summarization` 与
`noise_robustness` 当前只作单 benchmark diagnostic。单家覆盖不是能力不重要，而是证据不足以
叫“跨 benchmark 分数”。MemBench `lowlevel_rec` 是回忆助手曾明确给出的具体推荐，因此进入
事实回顾；只有跨域、多 session 汇总推荐的 `RecMultiSession` 才进入多证据能力。

### 2.1 三个容易混淆的边界

- **Conflict 属于记忆更新**：动态覆盖和矛盾消解都要求维护当前可信状态。BEAM/HaluMem 的
  official task 名继续出现在明细中，但总报告不再创建独立 conflict capability。
- **个性化不等于指令遵循**：偏好描述用户希望什么；指令规定系统必须怎样行动。两者可能共同
  影响回答，却有不同失败语义，因此不合并。
- **边界题不要求检索为空**：方法可能检索到大量无关记忆。评分看最终回答能否识别证据不足，
  不能把 `retrieved_items == []` 当作正确性的必要条件。

## 3. 为什么不能把所有题直接混在一起平均

题级 pooled micro-average 的 estimand 是：从合并后的题池随机抽一道题时，方法的期望得分。
它只有在以下条件同时成立时才可解释：

- 使用同一个 metric 和 rubric；
- 每个数值有相同含义与上下界；
- 题目来自可以合并的抽样总体；
- 题量本身就是预先声明的目标权重，而不是数据生成方便程度造成的数量差。

所以“必须都是 F1 或必须都是同一 LLM judge”只对**直接汇总 raw question score**成立；对现行
average-rank 主榜不是前提。现行做法先在同一 benchmark、同一 scorer 下比较十家 method，再只
跨 benchmark 汇总相对名次，因此不会把 BEAM 的 0.5 当成 LongMemEval 的半个 `yes`。即便未来
五家都改叫 F1，也仍需核验 tokenizer、normalizer、gold 结构与题目总体一致，不能只看 metric 名称。

Phase 1 不满足这些条件。LoCoMo 是 token F1，LongMemEval 多为二元 judge，BEAM rubric 可保留
部分正确分且 event-ordering 另用顺序分，MemBench 是选择题 accuracy，HaluMem 是
Correct/Hallucination/Omission judge。数据量也从 400/500 到数千题不等。直接按题数混池会让
题多的 benchmark 自动控制总榜，并把不同评分尺度误当成同一把尺。

题多应主要体现为估计更稳定、置信区间更窄，而不是拥有更多 benchmark 投票权。若未来得到一组
真正同 rubric、同抽样总体的跨 benchmark 题，可把 pooled micro-average 作为补充 sensitivity，
但不回写现行主总分。

当前完整 QA 题量若直接混池，隐含权重如下：

| benchmark | QA 题数 | pooled-micro 隐含权重 | 主榜权重 |
| --- | ---: | ---: | ---: |
| LoCoMo | 1,540 | 16.55% | 20% |
| LongMemEval | 500 | 5.37% | 20% |
| BEAM | 400 | 4.30% | 20% |
| MemBench | 3,400 | 36.53% | 20% |
| HaluMem | 3,467 | 37.25% | 20% |

所以“把所有逐题分数相加再除以题数”会让 MemBench 与 HaluMem 合计控制 73.78% 的结果。
这不是错公式，而是在回答另一个问题：从五家**已发布题池**随机抽一题时的期望得分。由于五家
题分语义并不相同，且发布题量不是预先定义的目标人群权重，它不能成为本项目主总分。

## 4. 主聚合算法

### 4.1 单个 benchmark 内

1. 每个 official native task 先对其逐题 primary score 求均值；
2. 若多个 native task 映入同一能力，在该 benchmark 内对 native-task mean 宏平均；
3. 固定 Phase 1 十家 method 同场排序，并列使用平均名次；
4. 把名次转换为 `rank_score = (10 - rank) / 9`。

因此 BEAM 同时拥有 knowledge-update 与 contradiction-resolution、HaluMem 同时拥有 Dynamic
Update 与 Memory Conflict，也只对“记忆更新”贡献一个 benchmark vote；两种 official task 在
benchmark 内各占一半，不由题数多少决定权重。

### 4.2 跨 benchmark 能力分

```text
capability_score(method, capability)
  = 100 * contributing benchmarks 的 rank_score 等权平均
```

至少两家 benchmark 才发布 cross-benchmark capability score。每家贡献同等权重，同时展示各自
raw score、native task mean、题数和 rank，避免 rank 掩盖胜负幅度。

### 4.3 Overall QA

```text
overall_qa(method)
  = 100 * 五个 benchmark overall rank_score 的等权平均
```

Overall 不再平均能力分，否则同一道题会先进入 benchmark overall、再经 capability 回灌而重复计权。

## 5. 完整性与不确定性

- 正式排名固定十家 method × 五家 benchmark；缺格、失败或 data/question/answer/judge identity
  不一致即 `incomplete`，不补零、不缩分母。
- smoke/pilot 只验证管线，不能发布方法排名。
- 95% 区间按 isolation 做 paired cluster bootstrap：同一次重抽样对十家方法使用相同
  conversation/instance/tid/UUID。题多的 benchmark 因此通常得到更窄区间。
- API 随机性不在一次 dataset bootstrap 内；若需要评估，另做固定配置的 repeat sensitivity。
- 质量总分与成本/延迟分开报告，并用 Pareto 图观察权衡，不把价格偷偷加进质量分。
