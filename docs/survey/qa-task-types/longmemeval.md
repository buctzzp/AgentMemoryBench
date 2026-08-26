# LongMemEval QA 任务类型

更新日期：2026-08-26。`s_cleaned` 与 `m_cleaned` 均为同一批 500 个 question identity；variant
改变 haystack 长度，不应当作两批独立问题重复计权。

## 原生类型

| effective task | 数量 | 定义 | S 数据真实例子 | 官方/现行主分 |
| --- | ---: | --- | --- | --- |
| `single-session-user` | 70 | 从一个 session 的 user 发言回忆事实 | item 0 / `e47becba`：取得什么学位？→ `Business Administration` | common yes/no judge |
| `single-session-assistant` | 56 | 从 assistant 回复回忆建议或安排 | item 444 / `7161e7e2`：Admon 周日轮班→`8 am - 4 pm` | common yes/no judge |
| `single-session-preference` | 30 | 根据用户偏好给出合适建议，不是短事实复述 | item 132 / `8a2466db`：推荐 video-editing 资源；rubric 偏向 Premiere Pro 高级设置 | preference rubric judge |
| `multi-session` | 133 | 综合多个 session 的事实 | item 70 / `0a995998`：需取回或退回几件衣服？→`3` | common yes/no judge |
| `knowledge-update` | 78 | 旧信息后来更新，回答当前/最终值 | item 366 / `6a1eabeb`：5K 最佳成绩由 `27:12` 更新为 `25:50` | update-specific judge |
| `temporal-reasoning` | 133 | 根据多次事件日期计算间隔或先后 | item 233 / `gpt4_59149c77`：两次博物馆参观间隔→`7 days` | temporal judge，允许指定 off-by-one |
| `abstention` (`*_abs`) | 30 | 历史没有所问信息，应说明未提及 | item 64 / `0862e8bf_abs`：仓鼠叫什么？历史只提到猫 Luna | abstention judge |

前六行合计为 500 个原生 `question_type`；30 个 `_abs` 是覆盖其中原类型的有效身份，不是额外
30 道题。横向聚合时一题只能计一次，原 question type 可保留为 secondary axis。

## 候选横向理解（未定稿）

- user/assistant single-session：事实回顾；source role 另作诊断。
- multi-session：多证据回忆/推理。
- temporal：时间与事件顺序。
- knowledge-update：记忆更新/修订。
- preference：个性化。
- `_abs`：可答性边界候选。

## Boundary 的两个观测面

LongMemEval 官方 abstention scorer 只判断**最终回答**是否正确识别不可回答，因此它证明的是
`answer_abstention`，不证明 memory provider 检索为空。若项目要专门测记忆模块，还应另记：

1. `retrieval_boundary`：provider 是否返回 typed `no_relevant_memory`/真实 0-hit；
2. `answer_abstention`：framework reader 最终是否拒绝编造。

当前协议中 `RetrievalResult.items=None` 与 `items=()` 在 answer artifact 都会被序列化成空 list，
前者可能只是 method 无结构化 items，后者才是真实 0-hit。因此在修复该可观测性之前，不能仅凭
artifact `retrieved_items=[]` 给 memory module 边界打满分。

完整数据/异常/流程入口：[benchmark 卡](../benchmarks/LongMemEval.md)、
[dataset 卡](../datasets/longmemeval.md)、[workflow 卡](../workflows/longmemeval.md)。
