# QA task aggregation v3 架构裁决

日期：2026-08-26。状态：用户与架构师已确认，等待实现与强反例。

## 最终裁决

1. overall 与 capability 均按固定题池逐题 pooled micro，一题一票，不做 benchmark 等权 rank。
2. update、HaluMem 错误前提纠正、BEAM 历史内部矛盾消解拆成不同能力。
3. personalization 与 instruction following 分开；MemBench `lowlevel_rec` 归事实回顾；`noisy`
   不进聚合；LoCoMo category 5 继续排除。
4. abstention M0 只看固定 framework answer LLM 的最终输出；纯 retrieval boundary 延后。
5. 聚合不混 token F1、连续 rubric mean 与 tau：LoCoMo/LME/HaluMem 使用 answer correctness，
   MemBench exact，BEAM 使用标准化 `0/0.5/1` question credit。
6. BEAM 普通题按 rubric items 生成三档；event ordering 进入聚合，但共享 item rubric 无法判断
   顺序，必须把有序 reference 构成一个 compound criterion，调用整题 LLM judge 输出三档。
7. BEAM 官方 native F1/tau/rubric/final score 全部保留；整题三档明确标 framework-standardized，
   不冒充官方 event-ordering 主分。

## 一手依据摘要

- BEAM 十类 `evaluate_*` 共享 `unified_llm_judge_base_prompt`，task 差异来自 rubric；event ordering
  额外执行 semantic alignment、F1、Kendall tau。
- event-ordering 真实 rubric 是按标准顺序排列的事件名称，逐 item judge 可检查内容但无法识别
  整体倒序；真实数据另有 `ordering_tested` 与标准 `answer`。
- LongMemEval/BEAM/HaluMem abstention 的官方 scorer 均判断最终回答；M0 接受 fixed-reader utility
  口径，检索层增强另批实施。

稳定合同入口：`docs/survey/qa-task-types/aggregation.md`。
