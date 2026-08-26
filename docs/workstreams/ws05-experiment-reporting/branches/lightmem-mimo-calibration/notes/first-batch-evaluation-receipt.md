# LightMem × Mimo calibration 首批 evaluate 收据

日期：2026-08-26

## 1. 判词

`FIRST_BATCH_EVALUATION_PASS_WITH_DECLARED_EXTRACTION_OMISSION`

五格首批已完成全部当前适用的离线指标与 answer/update/rubric judge。HaluMem extraction
需要 2,889 次额外 judge，且多数 method 没有 session-local extraction readout，用户裁定本轮
不测；`halumem-memory-type` 依赖 extraction/update 共享分母，因此同步不生成。该缺席是明确
scope 决策，不是 evaluator 失败或 N/A 伪装。

## 2. 分数

| benchmark | metric | score | 分母/状态 |
| --- | --- | ---: | --- |
| LoCoMo | generic F1 | 0.4638410107 | 158 |
| LoCoMo | official-style LoCoMo F1 | 0.4821729530 | 158 |
| LoCoMo | normalized EM | 0.2341772152 | 158 |
| LoCoMo | substring EM | 0.3481012658 | 158 |
| LoCoMo | retrieval recall | 0.6518987342 | 158 / valid turn |
| LoCoMo | LLM judge accuracy | 0.6708860759 | 106/158 |
| LongMemEval-S | generic F1 | 0.0571428571 | 1 |
| LongMemEval-S | normalized EM | 0 | 1 |
| LongMemEval-S | substring EM | 1 | 1 |
| LongMemEval-S | LLM judge accuracy | 1 | 1/1 |
| LongMemEval-S | recall / retrieval rank | null | N/A：LightMem pair lineage 非 turn-exact |
| BEAM-100K | rubric judge mean | 0.5279761905 | 20 |
| BEAM-100K | recall | null | N/A：gold single-message、LightMem pair 过粗 |
| MemBench 0-10K | choice/source accuracy | 0.5 | 2/4；四 source lane 各 1 |
| MemBench 0-10K | recall | 0.5833333333 | 4 / valid turn |
| HaluMem-Medium | generic F1 | 0.3378274439 | 169 |
| HaluMem-Medium | normalized EM | 0.0828402367 | 169 |
| HaluMem-Medium | substring EM | 0.1242603550 | 169 |
| HaluMem-Medium | QA judge | 0.6094674556 | 103/169 |
| HaluMem-Medium | update judge | 0.6842105263 | 117/171 |

以上是单 isolation calibration 结果，不作正式排名；LongMemEval 只有一题、MemBench 每 lane
一题，分数波动尤其大。

## 3. Judge 成本与身份

| evaluator | calls | input tokens | output tokens | failed attempts |
| --- | ---: | ---: | ---: | ---: |
| LoCoMo judge | 158 | 101,846 | 1,558 | 0 |
| LongMemEval judge | 1 | 430 | 2 | 0 |
| BEAM rubric/event judge | 83 | 65,752 | 5,832 | 0 |
| HaluMem QA | 169 | 191,077 | 17,787 | 0 |
| HaluMem update | 171 | 601,488 | 22,721 | 0 |
| **合计** | **582** | **960,593** | **47,900** | **0** |

五份 evaluator model inventory 均为逻辑 `model_id=judge-llm`、实际
`model_name=mimo-v2.5`；每条 observation 的 token measurement source 都是 `api_usage`。

## 4. 本轮暴露并修复的框架缺口

HaluMem formal cohort 会预写五个 UUID 的完整 session labels，而每个 UUID 都从 `s1` 开始。
旧 update/extraction evaluator 只按 `session_id` 建索引，update 在任何 API 调用前报
`duplicate HaluMem session label: s1`。现改为 `(conversation_id, session_id)` 复合索引，再用
`session_ref.isolation_key` 唯一定位当前 UUID；348 labels、171 update probes、70 reports 全量
预检只映射到已完成 UUID。首次失败发生在 API 前，修复后的 run 才产生 171 次真实调用。

另确认：通用逐题 runner 的 LoCoMo judge 消费 `workers=32`，158 次约 28 秒；BEAM/HaluMem
artifact evaluator 当前忽略内部 `max_workers`，本轮通过三个独立 evaluator 进程并行、各自
内部串行完成。运行时两个活跃进程各约 40 MB RSS，系统 memory-pressure 可用比例约 38–45%，
没有本地资源压力；慢点来自远端串行网络等待。扩大 judge 前应补 artifact-level 内部并行与
逐题进度，但不得以重跑本批付费调用来证明。

## 5. 机器门

```text
SUMMARY_SET_OK locomo 6
SUMMARY_SET_OK longmemeval 6
SUMMARY_SET_OK beam 2
SUMMARY_SET_OK membench 3
SUMMARY_SET_OK halumem 5
JUDGE_TOTAL 582 input 960593 output 47900
HALUMEM_EXTRACTION_AND_MEMORY_TYPE_INTENTIONALLY_ABSENT
LIGHTMEM_CALIBRATION_EVALUATION_GATE_PASS
```

复合 session 身份、artifact runner、registry 与文档定向门：`82 passed in 4.06s`。
current 全量零 API 回归：

```text
2358 passed, 3 deselected, 25 warnings, 29 subtests passed in 162.88s (0:02:42)
```
