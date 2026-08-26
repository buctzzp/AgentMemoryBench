# MemBench QA 任务类型

更新日期：2026-08-26。以下统计来自 `data/membench/Membenchdata/data2test/0-10k/` 四条主
source lane，共 3,400 个独立 tid/choice QA。每题主分均为 A/B/C/D exact accuracy：正确=1，
错误或无法解析=0。

## 原生 task

| task | 数量 | 定义与真实例子 | 候选理解 |
| --- | ---: | --- | --- |
| `simple` | 350 | 回忆一个明确事实；First/roles/tid=0：niece 的公司→`TechInnovate Systems LLC` | 事实回顾 |
| `conditional` | 350 | 先按条件筛选实体，再回答另一属性；Associate Degree 的人多大？→28 | 多证据筛选 |
| `comparative` | 250 | 比较两个实体的同类属性；Nolan 与 Sophie 谁更年长？ | 比较推理 |
| `aggregative` | 250 | 对满足条件的实体/事件计数；住在 Philadelphia 的有几人？→2 | 聚合推理 |
| `post_processing` | 350 | 筛选后再做 suffix、字符数、数字求和等派生变换 | 派生推理 |
| `knowledge_update` | 200 | 旧事实后来更新，回答当前值；sister 的 hobby→`Camping` | 记忆更新 |
| `lowlevel_rec` | 150 | 回忆助手明确给过的具体 movie/book/dish 推荐列表 | 推荐内容回顾 |
| `RecMultiSession` | 50 | 跨 movie/book/dish 多段会话汇总所有助手推荐 | 跨会话推荐回顾 |
| `highlevel` | 800 | 从电影/食物/书推断偏好；emotion 子类推断给定时刻附近情绪 | 个性化/反思性推断 |
| `highlevel_rec` | 300 | 在推荐、拒绝、喜欢/不喜欢交互中推断抽象偏好；不是列推荐清单 | 个性化/反思性推断 |
| `noisy` | 350 | 在问题前加入无关“碎碎念”，再用转折短语提出真正问题 | noisy-query 鲁棒性诊断 |

`scenario`（roles/events/items/places/hybrid/movie/food/book/emotion）是 secondary subtype，不是
另一套 scorer。`highlevel_rec`、`lowlevel_rec`、`RecMultiSession` 名字都带 rec，但输出语义分别
是抽象偏好、具体推荐、跨会话推荐，不能只因命名相近就合并。

## `noisy` 到底测什么

这是 MemBench 的原生 `noisy` question type。官方生成器
`DialogueGeneration/noise.py` 和 `DialogueGenerationCouple/CoupleNoise.py` 先生成与真实问题
无关的 murmuring，再拼接类似 “Wait, what I really want to know is:” 的转折和真正问题。例如：

```text
I was thinking about going for a hike ... What was that restaurant ...
Oh, what I truly wanted to clarify is,
What position does someone who has rock climbing as a hobby hold?
```

正确答案仍来自历史中的 target steps，评分仍是 choice accuracy。因此它首先测的是**带噪查询的
理解与记忆读取鲁棒性**，不是“检索应该为空”，也不能直接等同 HaluMem False Memory
Resistance。100K 长度变体还会另外向历史注入 NoiseData；那是 context-length/noise injection
轴，与原生 `question_type=noisy` 不是同一个概念。

目前把 `noisy` 作为单 benchmark diagnostic 最诚实。是否把它作为 primary task，还是把
noise 当 overlay 再恢复底层的 factual/conditional 等语义，需等用户与架构师讨论；数据并未提供
一个可直接消费的 underlying-task 标签，不能靠问题文本猜测。

## Retrieval 补充面

MemBench `target_step_id` 可用于 evaluator-private retrieval recall，但它与 choice accuracy 是不同
指标。唯一空 target list 的题仍可算 QA accuracy，却必须把 retrieval recall 记 N/A。任务类型聚合
讨论不应把 target-step recall 偷偷混进 QA raw score。

完整数据/异常/流程入口：[benchmark 卡](../benchmarks/MemBench.md)、
[dataset 卡](../datasets/membench.md)、[workflow 卡](../workflows/membench.md)。
