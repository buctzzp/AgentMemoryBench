# LightMem × Mimo calibration 实验支线

状态：`in-progress`

父任务：[ws05 experiment reporting](../../README.md)

## 目标与边界

本支线负责 LightMem 在五个 Phase 1 benchmark 上的 `calibration` 实验：固定公开
shape cohort，分批推进 prediction/resume，验收运行身份、公开 artifact 与效率观测，
再执行适用的 evaluator 并形成预算外推收据。

这不是 LightMem 第三方源码整治支线。只要 upstream 瑕疵不改变当前实验结果、成本或
框架公开契约，就记录边界而不扩修；框架自己的进度、artifact、resume 与 evaluator
缺口必须闭合。

## 稳定身份

- method：`lightmem`
- API runtime：`opencodego/mimo-v2.5`，thinking disabled
- profile：`calibration`，复用 LightMem 主 `[method]` 算法参数
- execution identity：`workers=10`
- ordered cohort、run id、分批预算与完整命令：见 [cohort](notes/cohort.md)
- 首批 prediction 只推进 p50；MemBench 为四条 source lane 各推进一个 isolation。

## 当前进度（2026-08-26）

### 首批 prediction

| benchmark | run id | 首批完成 | 问题 | 失败 | 状态 |
| --- | --- | ---: | ---: | ---: | --- |
| MemBench 0-10k | `lm-cal-mimo25-membench-0-10k-p5x4-v1-0-10k` | 4 | 4 | 0 | completed |
| LongMemEval-S | `lm-cal-mimo25-lme-s-p5-v1-s-cleaned` | 1 | 1 | 0 | completed |
| BEAM-100k | `lm-cal-mimo25-beam-100k-p5-v1-100k` | 1 | 20 | 0 | completed |
| LoCoMo | `lm-cal-mimo25-locomo-p5-v1` | 1 | 158 | 0 | completed |
| HaluMem-Medium | `lm-cal-mimo25-halumem-medium-p5-v1-medium` | 1 | 169 | 0 | completed |

HaluMem 同时写出 70 条 session memory report、171 条 update probe 与 4,855 条
prediction efficiency observation。五个 manifest 均已初验为 `calibration`、
`opencodego/mimo-v2.5`、thinking disabled、workers 10；完整字段合理性验收已通过，
artifact 瘦身/分批 evaluator 合同后的 current 全量零 API 门为
`2358 passed, 3 deselected, 25 warnings, 29 subtests passed`。

### 当前施工

- [x] 锁定公开 shape cohort、run id 与 `1 + 2 (+2)` / `4 + 8 (+8)` 预算。
- [x] 完成首批五格 prediction，全部 conversation/question 零失败。
- [x] 给通用 Rich progress 增加轻量 activity 细节。
- [x] 给 HaluMem operation-level runner 接入 session/turn/question 进度与
  `checkpoints/progress.json`。
- [x] 完成五格 manifest、answer/readout、效率、时间/speaker、空值与边界字段
  [验货收据](notes/first-batch-prediction-receipt.md)。
- [x] 完成 HaluMem top-k、artifact 体积与分批 evaluator 对齐预检；主 QA/update
  均消费 LightMem 自然 top-60 `formatted_memory`，不套 Mem0 wrapper 的 20/10。
- [x] 对当前五格 answer artifact 与 BEAM private label 做无 API 确定性瘦身，合计减少
  19,689,199 bytes；未来 prediction 默认写 compact shape。
- [x] 完成除 HaluMem extraction/memory-type 外的全部适用 evaluator；用户基于
  2,889 次调用成本与跨 method 低覆盖裁定本轮不测 extraction，memory-type 因依赖它同步缺席。
- [x] 完成 score/summary/model inventory/efficiency/失败成本机器门，见
  [首批 evaluate 收据](notes/first-batch-evaluation-receipt.md)。
- [x] 闭合 BEAM/HaluMem artifact judge 的内部有界并行、逐单元进度与 token 守恒，见
  [M1 实现收据](notes/artifact-judge-parallelism-m1.md)。
- [ ] 按既有 identity 推进第二批 prediction resume，并形成增量成本/波动收据。

## 已知边界

- 当前 vendored LightMem 在多 extraction batch 时会把合法全局 `source_id` 用错误的
  局部上界修正后解析 `topic_id`。原始 `source_id` 仍用于 time、speaker 与 external
  lineage，且 `topic_id` 在当前 profile 只写 payload、不参与更新、检索或 answer readout。
  用户已裁定不扩修不影响结果的 method 内部瑕疵；本支线只保留此审计边界。
- HaluMem operation-level 首批运行约 40 分钟。旧终端黑屏来自 runner 没接
  `ProgressReporter`，不是 API 或 method 停滞；该框架缺口正在本批修复。
- 首批 artifact-level BEAM/HaluMem judge 曾接收但未消费 `max_workers`；M1 已闭合内部
  有界并行与逐单元进度。该修复不改变首批分数，也未用付费重跑来证明。

## 当前断点

进度 M0、首批 artifact 字段门、首批 evaluate 与 artifact judge 并行 M1 均已通过。HaluMem 的 20/10 已核实为官方
Mem0 wrapper 参数而非 benchmark-wide scorer contract；LightMem product top-60 是本 method
的自然 `formatted_memory`，无需另做 parity 裁决或重跑 prediction。用户已批准按既有 cohort
identity 推进第二批 prediction resume；下一步先做 resume 预检再启动真实 API，而不是补跑不可横向比较的
extraction；不得改变既有 run 的 profile、worker、cohort 顺序或 runtime 后强行 resume。
