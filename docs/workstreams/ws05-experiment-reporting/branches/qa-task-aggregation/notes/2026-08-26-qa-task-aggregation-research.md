# 2026-08-26 QA 任务聚合研究与裁决证据

> 历史 v1 证据：聚合方法学仍有效；capability 名称与映射已被
> [v2 裁决](2026-08-26-qa-task-taxonomy-v2-ruling.md) 取代，禁止按本文 §4 的旧表启动新报告。

## 1. 为什么不能直接平均五个分数

五家 QA primary 的测量尺度不同：token-F1、二元/分级 LLM judge、MCQ accuracy、HaluMem
Correct/Hallucination/Omission、BEAM rubric 与 sequence score。即使都落在 `[0,1]`，0.7 的统计含义、
下界与难度也不相同。直接平均会把“数字长得一样”误当成“测量尺度一样”。

主榜因此采用固定 roster 内 average rank；raw score 永远伴随展示。BIG-bench 的锚点归一化
`100*(raw-low)/(high-low)` 是有 lower/upper anchor 时的可解释方案，但我们目前五家没有统一、稳定、
可审计的 no-memory/random 与 oracle/human anchors，所以只登记为未来 sensitivity，不做 table min/max。

## 2. 方法学来源

- Demšar, 2006 在跨多个 dataset 比较多个算法时以 dataset 内 rank 和 average rank 为主，并建议
  非参数检验；本项目采其“先同场排序、再跨场聚合”的核心思想，但只有五个顶层 benchmark，
  不夸大显著性检验功效：<https://www.jmlr.org/papers/volume7/demsar06a/demsar06a.pdf>。
- BIG-bench 的 preferred metric 允许 task 作者声明 low/high anchor 后归一化，再跨 task 取均；它也
  明确提醒单一 human-performance 数字很危险。本项目保留 anchored sensitivity 的扩展位，但不在
  没有可信 anchor 时硬造：<https://github.com/google/BIG-bench/blob/main/docs/paper/BIG-bench.tex>。
- HELM 强调 taxonomy、标准化条件、多指标和透明 coverage，而不是用一个均值吞掉所有差异；本项目
  因此把 overall、capability、native task、coverage、cost 分面报告：
  <https://crfm.stanford.edu/2022/11/17/helm.html>。

## 3. Current adapter 全量 category census

以下来自 current production adapter、零 API：

| benchmark | QA 数 | 原生类型分布 |
|---|---:|---|
| LoCoMo | 1540 | `1=282, 2=321, 3=96, 4=841`；Phase 1 不含 adversarial category 5 |
| LongMemEval S | 500 | update 78, multi-session 133, assistant 56, preference 30, user 70, temporal 133；其中 `_abs=30` |
| BEAM 100k | 400 | 10 abilities 各 40 |
| MemBench 0-10k | 3400 | simple 350, conditional 350, comparative 250, aggregative 250, post_processing 350, update 200, lowlevel_rec 150, RecMultiSession 50, highlevel 800, highlevel_rec 300, noisy 350 |
| HaluMem Medium | 3467 | fact 746, multi-hop 198, update 180, boundary 828, conflict 769, generalization 746 |

## 4. Primary capability v1 映射

| capability | LoCoMo | LongMemEval | BEAM | MemBench | HaluMem |
|---|---|---|---|---|---|
| `direct_recall` | 4 | single-session-user/assistant | information_extraction | simple | Basic Fact Recall |
| `multi_evidence_reasoning` | 1 | multi-session | multi_session_reasoning | conditional, comparative, aggregative, post_processing, lowlevel_rec, RecMultiSession | Multi-hop Inference |
| `temporal_sequence_reasoning` | 2 | temporal-reasoning | temporal_reasoning, event_ordering | — | — |
| `dynamic_update` | — | knowledge-update | knowledge_update | knowledge_update | Dynamic Update |
| `memory_grounded_inference_application` | 3 | single-session-preference | preference_following | highlevel, highlevel_rec | Generalization & Application |
| `conflict_resolution` | — | — | contradiction_resolution | — | Memory Conflict |
| `epistemic_boundary` | — | `_abs` 覆盖原 question_type | abstention | — | Memory Boundary |
| `instruction_following` | — | — | instruction_following | — | — |
| `summarization` | — | — | summarization | — | — |
| `noise_robustness` | — | — | — | noisy | — |

`instruction_following` 与个性化/偏好使用明确分开。前三个单 benchmark 独有切片只作 diagnostic；
其他至少两家 benchmark，可计算跨 benchmark capability score。

## 5. Secondary axes

每题只进上表一个 primary capability；以下可重叠但只作诊断：

- `source_role=user/assistant/mixed`：例如 LME assistant 与 MemBench recommendation recall；
- `evidence_scope=single/multi`、`session_scope=single/multi`；
- `memory_target=fact/preference/event/instruction`；
- `robustness=clean/abstention/conflict/noise`。

LongMemEval `_abs` 是官方显式任务身份，v1 让它优先成为 `epistemic_boundary`，原
`question_type` 仍保留为 secondary native source；MemBench `noisy` 同理。这样既不丢官方信息，
又保证 primary 分区互斥。

## 6. BEAM 承重勘误

官方 `report_results.py` 对九类读取 `llm_judge_score`，对 `event_ordering` 读取 `tau_norm`。
current score artifact 已保存 `details.event_ordering_tau_norm`，但旧 summary 的
`beam_rubric_judge_mean` 仍把十类都按 rubric `score` 平均。QA aggregation v1 不消费该旧字段，
而从逐题 artifact 按 type-aware selector 重算；旧 artifact 无需重跑。

## 7. 未采用方案

- **raw 0-1 mean**：尺度异构，只保留 sensitivity。
- **z-score**：受 roster/outlier 影响且难向导师解释。
- **table min-max**：加入/删除 method 会改所有历史分数，没有外部语义 anchor。
- **题级 micro-average across benchmarks**：让题多的 HaluMem/MemBench 吞掉其他 benchmark。
- **能力分再平均回 overall**：同题重复计权。
- **缺格补零/缩分母**：把工程失败与算法质量混为一谈，或奖励只跑容易 benchmark 的 method。
