# 2026-08-26 QA task taxonomy v2 候选裁决记录

> **2026-08-26 用户纠正后重开。**五家 task census 与官方 scorer 证据仍有效；横向映射、权重和
> 原 §3.4“boundary 不要求空检索”均未获用户确认。现行讨论入口改为
> [五家独立调查](../../../../../survey/qa-task-types/README.md) 与
> [聚合讨论稿](../../../../../survey/qa-task-types/aggregation-draft.md)。本 note 是候选方案的历史
> 收据，不是正式合同。

## 1. 目标与证据边界

本轮不是重做 benchmark adapter，而是把五家 QA 原生任务翻译成可解释、可审计的横向能力，
并回答用户提出的四个争议：Conflict 是否属于 update、instruction 是否属于 personalization、
boundary 是否等于空检索，以及异构题分能否按题数直接混池。

证据覆盖当前冻结数据与官方 scorer/prompt；三个只读 Luna/max 调查分别覆盖 LoCoMo+LME、
BEAM+MemBench、HaluMem+权重。架构师复核了 current adapter 的公开 category/metadata、聚合器
消费面、BEAM event-ordering selector 和五张稳定 benchmark 卡。调查代理回报只作为候选事实，
本 note 的裁决以本仓 current source/data 为准。

## 2. 五家 task census

| benchmark | 当前 QA cohort | 原生 task 摘要 |
| --- | ---: | --- |
| LoCoMo | 1,540 | category 1=282、2=321、3=96、4=841；category 5=446 当前排除 |
| LongMemEval | 500 | user=70、assistant=56、preference=30、multi=133、update=78、temporal=133；其中 `_abs`=30 |
| BEAM | 400 | 20 conversations × 10 abilities × 2 questions；event ordering 使用 `tau_norm` |
| MemBench 0-10k | 3,400 | 11 个 question type；scenario 是 secondary axis |
| HaluMem | 3,467 | Boundary=828、Fact=746、Conflict=769、Generalization=746、Multi-hop=198、Dynamic=180 |

稳定定义与真实题目不在本 note 重复倾倒，统一见
[五家独立任务类型调查](../../../../../survey/qa-task-types/README.md)。

## 3. v2 候选方案（等待讨论）

### 3.1 七个跨 benchmark 能力

1. `factual_recall_extraction`
2. `multi_evidence_recall_reasoning`
3. `temporal_event_reasoning`
4. `memory_revision`
5. `personalization`
6. `answerability_boundary`
7. `generalization_application`

`instruction_following`、`long_horizon_summarization` 和 `noise_robustness` 当前分别只有 BEAM、
BEAM、MemBench 一家覆盖，因此保留为 diagnostic，不发布伪造的“跨 benchmark 能力分”。

### 3.2 Conflict 并入 memory revision

Dynamic Update 的正确输出是新值；Memory Conflict/contradiction 的正确输出可能是纠正错误前提，
也可能承认两条陈述尚不能消歧。它们不是同一个 native task，却都在测“面对新旧或互斥信息时
维护当前可信记忆”。因此父能力合并，native task 与逐类 raw score继续保留；BEAM/HaluMem
在 benchmark 内先各算 native mean，再各占该 benchmark memory-revision slice 的一半。

### 3.3 Personalization 与 instruction 分离

Personalization 从偏好、习惯或用户状态推断“什么回答更适合这个人”；instruction following
检查“系统是否仍执行用户明确规定的格式/禁忌/行为”。两者的失败语义不同，BEAM 官方
preference prompt 也明确排除 instruction。MemBench `highlevel/emotion` 可作为 personalization
中的 affective-state secondary subtype，但不会被冒充为 instruction。

### 3.4 Boundary 必须区分 retrieval 与 answer

原判词“只要最终拒答，检索到无关记忆也算正确”被用户纠正：那只能说明官方
`answer_abstention` 正确，不能说明记忆模块的 `retrieval_boundary` 正确。若目标是评测 memory
module，返回无关 memory 应判 retrieval boundary 失败；成功应是 typed true-zero-hit 或
`no_relevant_memory`。

current artifact 又把 `RetrievalResult.items=None` 与 `items=()` 都序列化成 `[]`，尚不能可靠
区分“不提供结构化 items”和“真实 0-hit”。因此最终 boundary 公式暂停，先修可观测性，再与用户
讨论 retrieval、answer 两层和 strict conjunction 如何报告。

### 3.5 Generalization 与长期总结

- Generalization：把已记住的事实/偏好用于一个没有逐字出现的新情境。LoCoMo category 3 与
  HaluMem Generalization & Application 进入此类；LoCoMo 其中 4 道空 evidence 题必须单列
  grounding anomaly，不能假称全是 memory-grounded。
- Long-horizon summarization：把许多交互压成主题、进展、变化、时间线、目标与未决事项的
  连贯整体，不是只拼出某个多跳短答案。目前只有 BEAM QA 覆盖，故只作 diagnostic。

### 3.6 MemBench recommendation 边界

`lowlevel_rec` 回忆助手明确给过的具体推荐，进入 factual recall；`RecMultiSession` 跨
movie/book/dish 多段会话汇总推荐，进入 multi-evidence recall/reasoning。`highlevel_rec` 虽然
上下文也含推荐，但答案是抽象偏好，进入 personalization。这样不把三个名字相近、输出语义不同
的任务粗暴合并。

## 4. 权重与 score 语义

题级 pooled micro 的权重由发布题量决定：LoCoMo 16.55%、LME 5.37%、BEAM 4.30%、
MemBench 36.53%、HaluMem 37.25%。它会让后两家合计占 73.78%，且混合 token F1、binary
judge、choice accuracy、BEAM 0/0.5/1 rubric 与 ordering tau。它只能解释“从合并后的发布题池
随机抽一题”，不能解释“五个 benchmark 上总体更好”。

主榜继续采用：

1. 同一 benchmark、同一 task slice 内用其合法 primary score 排固定十家 method；
2. 同分取平均名次，转成 `(10-rank)/9`；
3. 五 benchmark 等权形成 overall；
4. capability 内先对 native-task mean 宏平均，再做 benchmark 内排名，最后对 contributing
   benchmarks 等权；
5. 同屏报告 raw、question/native-task count 与 isolation-level paired cluster CI，弥补 rank
   丢失分差的缺点。

题多的价值主要是缩窄不确定性，不是增加 benchmark 投票权。只有将来存在同 rubric、同 score
语义、同目标 population 且预先声明题量权重的题池，pooled micro 才可升级；当前仅允许明确
标注为 supplementary released-item sensitivity。

## 5. v1 → v2 变更

- capability contract 暂记 `qa-task-aggregation-v2-draft`；用户确认前不得生成 formal 排名。
- `dynamic_update` + `conflict_resolution` → `memory_revision`。
- `memory_grounded_inference_application` 拆成 `personalization` 与
  `generalization_application`。
- direct/multi/temporal/boundary/summarization 更名为语义更清楚的 v2 标识。
- MemBench `lowlevel_rec` 从 multi-evidence 移到 factual；`RecMultiSession` 留在 multi-evidence。

## 6. 非目标与后续

- 本轮不调用真实 API、不生成方法排名、不改任何旧实验 artifact。
- QA 主榜仍不纳入 retrieval metrics、HaluMem extraction/update/memory-type。
- M1 再实现 cohort receipt 与可读/机器报告；M2 在完整 cohort 上做 paired cluster bootstrap。

## 7. 验收收据

架构师用 current 数据独立复算：LoCoMo `1986/1540`、LME S 六类与 `_abs=30`、HaluMem
Medium/Long 六类逐项同数、MemBench 0-10k 四源合计 3,400、BEAM 100K 20 conversations/400
questions 且十 ability 各 40；结果与调查账一致。

零 API 定向门：

```text
uv run python -m py_compile \
  src/memory_benchmark/analysis/qa_task_aggregation.py \
  tests/test_qa_task_aggregation.py

uv run pytest -q \
  tests/test_qa_task_aggregation.py \
  tests/test_run_cost_report.py \
  tests/test_beam_rubric_judge.py \
  tests/test_halumem_evaluators.py \
  tests/test_documentation_standards.py

66 passed in 8.28s
```

`git diff --check` 无输出。未调用真实 API、未读写 outputs、未修改数据或第三方实现。
