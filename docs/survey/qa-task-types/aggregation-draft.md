# Phase 1 QA 任务类型与聚合讨论稿（已归档）

状态：**已由 [正式合同](aggregation.md) 取代，不得用于 formal 排名**。更新日期：2026-08-26。

本页保留当时三种权重与未决问题，作为裁决过程记录；当前实现与报告只能以正式合同为准。

本文只把五份单家调查摆到同一张桌上，列出候选映射、权重方案和未决问题。单家事实见同目录
LoCoMo、LongMemEval、BEAM、MemBench、HaluMem 五份文档。

## 1. 当前候选能力（不是最终名单）

| 候选能力 | LoCoMo | LongMemEval | BEAM | MemBench | HaluMem |
| --- | --- | --- | --- | --- | --- |
| 事实回顾/信息抽取 | category 4 | single-session user/assistant | information_extraction | simple；lowlevel_rec 是否并入待讨论 | Basic Fact Recall |
| 多证据回忆/推理 | category 1 | multi-session | multi_session_reasoning | conditional/comparative/aggregative/post_processing/RecMultiSession | Multi-hop Inference |
| 时间与事件顺序 | category 2 | temporal-reasoning | temporal_reasoning/event_ordering | — | — |
| 记忆修订 | — | knowledge-update | knowledge_update/contradiction_resolution | knowledge_update | Dynamic Update/Memory Conflict |
| 个性化 | — | single-session-preference | preference_following | highlevel/highlevel_rec | — |
| 指令遵循 | — | — | instruction_following | — | — |
| 可答性/记忆边界 | category 5 尚未接入 | `_abs` | abstention | — | Memory Boundary |
| 泛化应用 | category 3 | — | — | — | Generalization & Application |
| 长期总结 | — | — | summarization | — | — |
| noisy-query 鲁棒性 | — | — | — | noisy | — |

候选思路是 Conflict 保留 native task、在父层与 update 共享“记忆修订”；personalization 与
instruction following 分开。但这两项仍等待用户确认，不再把代码中的草案映射称作最终合同。

## 2. Boundary 必须拆成两层

用户提出的目标是评测**记忆模块**，因此仅看 answer LLM 最后拒答确实不够。建议至少同时报告：

| 层 | 问题 | 成功条件候选 | 当前可复算性 |
| --- | --- | --- | --- |
| `retrieval_boundary` | memory retrieve 是否知道“没有相关记忆” | `items=()` 的真实 0-hit，或 adapter 给出 typed `no_relevant_memory`；返回无关记忆判失败 | 旧 artifact 不可靠 |
| `answer_abstention` | reader 是否在证据不足时拒绝编造 | 官方 abstention/boundary judge 判正确 | LME/BEAM/HaluMem 可算 |
| strict end-to-end boundary | 两层是否都正确 | 两者同时成功 | 等 retrieval outcome 修复后再定 |

不能解析 free-form `"No relevant memories"` 字符串来计分，应该由 adapter 转成 typed outcome。
当前 `_retrieved_items_payload()` 会把 `items=None` 与 `items=()` 都序列化成 `[]`：前者可能只是
method 不提供结构化 items，后者才是真 0-hit。正式 retrieval-boundary metric 前必须先消除该
不可观测性；否则会把 N/A 误判成满分。

## 3. 三种权重方案

### 方案 A：五 benchmark 等权 average-rank（当前候选主方案）

1. 每家 benchmark 用自己的合法 primary scorer 比较固定十家 method；
2. 同分取平均名次，转成 `(10-rank)/9`；
3. overall 对五家各取 20%；
4. capability 在 benchmark 内先对 native-task mean 宏平均，再排名、跨 benchmark 等权。

优点：不直接混合 F1、binary judge、choice accuracy、BEAM partial rubric/tau。缺点：丢失分差，
并依赖固定 roster；必须同屏报告 raw score 与 paired cluster CI。

### 方案 B：五 benchmark raw score 等权

直接平均五个 `[0,1]` raw score。优点是直观；缺点是“都在 0–1”不代表同一测量尺度：0.7 token
F1、0.7 choice accuracy 和 0.7 rubric mean 含义不同。当前不建议作 headline，可做 sensitivity。

### 方案 C：按全部题数 pooled micro（用户提出的简单方案）

当前题数与隐含权重：

| benchmark | QA 题数 | 权重 |
| --- | ---: | ---: |
| LoCoMo | 1,540 | 16.55% |
| LongMemEval | 500 | 5.37% |
| BEAM | 400 | 4.30% |
| MemBench | 3,400 | 36.53% |
| HaluMem | 3,467 | 37.25% |

它回答“从五家已发布题池随机抽一题时的期望得分”，会让 MemBench+HaluMem 合计占 73.78%。
只有当所有题使用同一 metric/rubric/score 语义、来自可合并的目标 population，且题量就是预先
声明的目标权重时，才适合作主方案。即使都叫 F1，也要继续核 tokenizer、normalizer、gold
结构和抽样总体；metric 名相同不是充分条件。

## 4. 当前建议的报告形状

无论最终选择哪种 headline，都不要只剩一个总分：

1. 五家 benchmark 官方/主 raw score；
2. 每家 native task 明细与样本数；
3. 经确认后的跨 benchmark capability profile；
4. retrieval boundary、answer abstention、HaluMem H/O 等 guardrail；
5. isolation-level paired cluster CI；
6. 成本/延迟另表，不偷偷混进质量分。

## 5. 等待讨论的具体问题

1. Conflict 是否确认与 update 共享父能力“记忆修订”？
2. Instruction following 是否确认独立于 personalization？
3. MemBench `lowlevel_rec` 应归事实回顾，还是保留单家 recommendation-recall diagnostic？
4. MemBench noisy 是 primary capability，还是 query-noise overlay diagnostic？
5. Boundary headline 是只看 `retrieval_boundary`，还是同时报告 retrieval 与 answer 两层，并把
   strict conjunction 作为端到端 guardrail？
6. 主 headline 是否采用方案 A；方案 B/C 是否保留为 sensitivity？

上述问题经用户确认后，才把 `qa-task-aggregation-v2-draft` 升为正式 contract version。
