# Artifact judge 有界并行与 token 守恒 M1

日期：2026-08-26

## 1. 问题与边界

首批 LightMem evaluate 证明普通逐题 runner 会消费 `--max-eval-workers`，但 BEAM rubric
以及 HaluMem extraction/update/QA 的 artifact-level evaluator 只是接收 `max_workers` 参数，
内部仍串行等待远端 judge。该缺口不影响首批分数与 token 数，只影响扩大评测的耗时和终端
可见性。

本批只修 evaluator 执行面：不改 prompt、评分公式、rubric 路由、HaluMem 分母、artifact
schema 或模型配置，也不调用真实 API、不重跑已付费的首批结果。用户已裁定 HaluMem
extraction/memory-type 不进入当前横向实验；extraction 同步获得并行能力只是消除参数假象，
不代表恢复该指标。

## 2. 实现合同

- `LLMJudgeEvaluator._map_artifact_judge_units()` 按真实评测单元做有界线程并行；实际 worker
  数取 `min(max_workers, unit_count)`，非正整数 fail-fast。
- 每个单元建立独立 `EvaluatorEfficiencyObservationSink`。共享 collector 继续使用现有
  `ContextVar` 隔离 conversation/question scope，coordinator 按输入 index 归并结果与
  observation，远端完成先后不改变 score row 顺序或 token 归属。
- OpenAI SDK client 仍是一份共享连接池；懒加载增加锁，避免首批并发时重复构造 client。
- BEAM 以公开 question 为并行单元；同一 question 内 rubric items、event equivalence 与整题
  ordering judge 仍串行且共用一个 scope，官方语义不变。
- HaluMem QA 以公开 question、update 以实际进入官方 update judge 的 gold point、extraction
  以 session report 为并行单元。空 retrieval 的 update point 仍在并行调度前跳过。
- 每个 evaluator 在真实终端显示一条 `Evaluate <metric>` 进度条；不覆盖 prediction 的
  `checkpoints/progress.json`，也不新增持久 artifact。

## 3. Token 与成本口径

并行只改变等待拓扑，不改变 observation 粒度。每次 judge LLM 调用仍写：

- `model_id/model_name`；
- input/output token；
- `token_measurement_source`（API 提供 usage 时必须是 `api_usage`）；
- conversation/question 或 evaluator-unit scope；
- append-only failed attempt。

便宜模型实验的 token 数可用于按同一 prompt/call topology 外推 GPT-4o-mini 价格，但必须在
报告生成时使用目标模型的当期单价重新计算；不得把 Mimo 分数、速度或单价冒充 GPT-4o-mini
实测结果。后续每个 method 的 calibration 收据都必须分别汇总 memory build、retrieval 内部
LLM、answer LLM 与 judge LLM，不能只给总 token。

## 4. 零 API 验收

两条 barrier 强反例要求两个 fake Responses 调用同时抵达；旧串行实现会超时失败：

- BEAM 两个 question 在 `max_workers=2` 下真实并发，score row 仍按输入顺序；两条
  observation 的 input/output token 总和分别为 22/4。
- HaluMem 两个 QA 在 `max_workers=2` 下真实并发，score row 仍按输入顺序；两条
  observation 的 input/output token 总和分别为 26/6。

定向测试：

```text
93 passed in 5.71s
```

覆盖：`test_beam_rubric_judge.py`、`test_halumem_evaluators.py`、
`test_judge_efficiency_observations.py`、`test_artifact_evaluation_runner.py` 与
`test_documentation_standards.py`；`git diff --check` 干净。

current 全量零 API 回归：

```text
2360 passed, 3 deselected, 25 warnings, 29 subtests passed in 217.64s (0:03:37)
```

## 5. 下一步

保持五个既有 run 的 runtime、profile、ordered cohort、`workers=10` 与 run id 不变，第二批
prediction 使用 `--resume`：普通四格增量 budget=2，MemBench 四 lane 增量 budget=8。
prediction 验货后再评测适用指标，并把首批与累计批次的 token、失败尝试、wall time 与分数
波动分开报告。HaluMem extraction/memory-type 继续缺席。
