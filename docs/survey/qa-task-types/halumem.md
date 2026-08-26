# HaluMem QA 任务类型

更新日期：2026-08-26。Medium 与 Long 使用相同的 3,467 个 QA identity，只改变 context
variant；不能合并成 6,934 道独立题重复计权。

## 六类原生 QA

例子均来自 `data/halumem/HaluMem-Medium.jsonl` 的 UUID
`2f1f897e-d67f-dbc5-6a7b-b7634a9e294f`。

| question_type | 数量 | 定义与真实例子 | 官方/现行主分 |
| --- | ---: | --- | --- |
| `Basic Fact Recall` | 746 | 回忆明确事实；`s1:q2`：出生日期→`1996-08-02` | QA judge C/H/O；Correct=1 |
| `Multi-hop Inference` | 198 | 综合 2–3 个 memory point；`s8:q5`：哪次角色转变改善心理健康？ | QA judge C/H/O |
| `Dynamic Update` | 180 | 追踪 current/latest 状态；`s30:q7`：截至指定日期心理状态→`Abnormal` | QA judge C/H/O |
| `Memory Conflict` | 769 | 题目含错误前提，回答须纠正；`s1:q3`：并没有 partner，只是计划建立项目 | QA judge C/H/O |
| `Memory Boundary` | 828 | 所问信息从未提供；`s1:q1`：middle name→`Unknown; not provided`，gold evidence 为空 | QA judge C/H/O |
| `Generalization & Application` | 746 | 将已知偏好/特征用于新情境；`s5:q3`：Golden Retriever 偏好如何影响压力期选宠？ | QA judge C/H/O |

QA judge 输出 `Correct / Hallucination / Omission`：当前主 score 仅把 Correct 映射为 1，另外
保留 Hallucination/Omission ratio。它与 HaluMem extraction、operation-level update、FMR 是四个
不同观测面，不能互相代替。

## 横向映射（2026-08-26 裁定）

- Basic Fact→事实回顾；Multi-hop→多证据推理；Generalization→泛化应用。
- Dynamic Update→记忆更新；Memory Conflict→错误前提纠正。后者是 question premise 与一致历史
  冲突，不等同 BEAM 的 history-internal contradiction。
- Memory Boundary→answer-only 可答性边界；官方 QA score 只证明 final answer，不证明 retrieval
  为空。

## Boundary 与 FMR 的区别

- QA Memory Boundary：问一个历史未提供的信息，期望最终回答 unknown。
- Extraction FMR：检查干扰/假记忆是否被写入 memory；不是 QA refusal。
- 对“只测记忆模块”的严格 boundary，项目以后还应观察 retrieve 是否返回 typed 0-hit/
  `no_relevant_memory`。若检索出无关 memory，即使 reader 最终拒答，也只能算 answer 层正确，不能
  算 memory retrieval boundary 正确。

旧 artifact 可能把 `RetrievalResult.items=None`（method 没有结构化 items）和 `items=()`（真实
0-hit）都写成 `retrieved_items=[]`，因此严格 retrieval boundary 尚不可可靠复算；它后置为独立
增强，不阻塞 v3 answer-only QA 聚合。

完整数据/异常/流程入口：[benchmark 卡](../benchmarks/HaluMem.md)、
[dataset 卡](../datasets/halumem.md)、[workflow 卡](../workflows/halumem.md)。
