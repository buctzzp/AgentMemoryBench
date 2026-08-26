# BEAM QA 任务类型

更新日期：2026-08-26。以下 100K 计数为 20 conversations × 10 abilities × 每类 2 题 =
400 道。例子除 temporal 外均来自
`data/BEAM/beam_dataset/100K/data-00000-of-00001.arrow` row 0、`conversation_id=1`；
temporal 使用无 answer/rubric 冲突的 10M row 0。

## 十类原生 ability

| ability | 数量 | 定义与真实例子 | 官方/现行主分 |
| --- | ---: | --- | --- |
| `information_extraction` | 40 | 精确抽取事实；“first sprint 何时结束？”→ `March 29` | float rubric mean |
| `multi_session_reasoning` | 40 | 跨 session 聚合；统计 transactions table 新增 `category`、`notes` 两列 | float rubric mean |
| `temporal_reasoning` | 40 | 计算时间间隔；10M 例中 `2025-02-15` 到 `2025-03-01`→`14 days` | float rubric mean |
| `event_ordering` | 40 | 恢复话题在对话中的提及顺序；列出 budget tracker 三项开发活动 | 官方 report 消费 `tau_norm`，不是普通 rubric mean |
| `knowledge_update` | 40 | 使用明确更新后的当前值；dashboard API response time→`250ms` | float rubric mean |
| `contradiction_resolution` | 40 | 发现“从未写 Flask route”与“实现过 homepage route”的矛盾并要求澄清 | float rubric mean |
| `preference_following` | 40 | 根据 lightweight/minimal dependencies 偏好调整工具建议 | float rubric mean |
| `instruction_following` | 40 | 很久以后仍遵守代码必须 syntax-highlighted 的格式指令 | float rubric mean |
| `abstention` | 40 | 历史没说明 user feedback 如何影响 UI/UX，应明确无相关信息 | float rubric mean |
| `summarization` | 40 | 概括 budget tracker 的功能、错误处理、安全、部署等长期演变 | float rubric mean |

rubric 明确允许 `1.0/0.5/0.0`。官方历史代码对普通 ability 使用 `int(score)` 会把 0.5 截成 0；
框架保留 float 主分，同时保存 official-int parity。event ordering 另做 LLM 等价对齐和 Kendall
tau，主报告按官方有效消费面读取 `tau_norm`。

## 横向映射（2026-08-26 裁定）

- extraction→事实回顾；multi-session→多证据；temporal+ordering→时间/顺序。
- update→记忆更新；contradiction→历史内部矛盾消解。二者不合并。
- preference 与 instruction 不合并：官方 preference prompt 也明确只考虑 preference。
- abstention 进入 answer-only 可答性边界；不自动证明 retrieval boundary。
- summarization 是把长历史压缩成主题、进展、变化、时间线和未决事项的整体叙述，不是一个
  多跳短答案；它进入 overall，同时单列长期总结能力分，不能因只有 BEAM 覆盖而冒充跨家验证。

逐题 credit 分两条路径：普通九类将 rubric item 分数规约为三档——全为 1 得 1、全为 0 得 0、
其余得 0.5；event ordering 使用 framework-standardized 整题 ordered-rubric judge，同时检查事件
集合和相对顺序，输出 `0/0.5/1`。原生 rubric mean、F1、`tau_norm`、official `final_score` 全部
保留旁报；新整题 judge 不冒充 BEAM 官方 `tau_norm`。

## 需要保留的争议

- `contradiction_resolution` 有些题没有可选“最新值”，只要求识别尚未解决的矛盾。即使最终与
  update 共享父能力，也不能删除其 native task。
- 100K row 0 的 temporal `answer` 与 rubric 有 4/8 weeks 冲突，正式例子改用 10M；官方 scorer
  身份仍以冻结 rubric 为准。
- BEAM abstention 同样需要拆分 memory retrieval boundary 与 final answer abstention；v3 M0 只
  使用后者，前者等待 typed zero-hit/no-relevant-memory artifact 后再独立设计。

完整数据/异常/流程入口：[benchmark 卡](../benchmarks/BEAM.md)、
[dataset 卡](../datasets/BEAM.md)、[workflow 卡](../workflows/BEAM.md)。
