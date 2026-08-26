# LightMem × Mimo calibration 首批 prediction 验货收据

日期：2026-08-26

范围：五个首批 prediction run；零 evaluator API；不改 raw prediction。

## 1. 判词

`READY_FOR_CALIBRATION_EVALUATE`

五个 run 的 conversation/question 均零失败；runtime、method、source、controlled
embedding、公开 answer builder 与 efficiency inventory 身份一致。公开 question、prediction、
answer prompt、formatted memory、retrieved item、session report/update probe 和原始效率观测均通过
结构与非空门。

该判词只允许进入同一 `calibration + opencodego/mimo-v2.5` 身份下的 evaluator 流通与成本观测；
不把本轮分数冒充 `official_full`、作者复现或正式主表分数。

## 2. 首批完成面

| benchmark | completed isolation | prediction | raw efficiency observation | 失败 |
| --- | ---: | ---: | ---: | ---: |
| LoCoMo `locomo10` | 1 | 158 | 2,267 | 0 |
| LongMemEval `s_cleaned` | 1 | 1 | 851 | 0 |
| HaluMem `medium` | 1 | 169 | 4,855 | 0 |
| BEAM `100k` | 1 | 20 | 731 | 0 |
| MemBench `0_10k` | 4（四条 source lane 各一） | 4 | 454 | 0 |

每个已答问题恰有一条 prediction、answer-prompt 与 `question_efficiency`；answer、prompt、
formatted memory 均非空，question id 三方集合相等且无重复。失败成本账均为空。

## 3. 身份门

五个 manifest 均逐项命中：

- `run_scope=full`、公开 profile=`calibration`、`workers=10`；
- API runtime=`opencodego/mimo-v2.5`、Chat Completions、thinking disabled；
- answer model=`mimo-v2.5`，每家温度/max-token/top-p 继续由 benchmark resolver 决定；
- LightMem 主参数相同：`messages_use=hybrid`、`pre_compress=true`、
  `topic_segment=true`、`text_summary=true`、`retrieve_limit=60`；
- source closure=`lightmem-main-v2`、70 files、
  SHA-256=`860fc055a557f1bc251ded269040c96f3cde10ef134e2b48b1b421edb8210692`；
- controlled embedding=`models/all-MiniLM-L6-v2`、384 维、本地内容与 tokenizer 闭包锁定；
- 模型清单恰有 `lightmem-embedding`、`lightmem-memory-llm=mimo-v2.5`、
  `answer_llm=mimo-v2.5` 三项。

当前回答参数为：LoCoMo `temperature=0/max_tokens=4096/top_p=1`；LongMemEval
`temperature=0/max_tokens=500`；BEAM 与 MemBench `temperature=0` 且不额外覆盖 max tokens；
HaluMem 保持 benchmark 默认空覆盖。上述差异来自 benchmark 统一 resolver，不是 LightMem 特判。

## 4. 输入/readout 字段实证

对七个实际 Qdrant 主 collection 做只读全量 scroll（不读 vector）后得到：

| benchmark | collection | memory payload | source lineage | speaker | timestamp |
| --- | ---: | ---: | --- | --- | --- |
| LoCoMo | 1 | 809 | 每条 1 个 `source_external_id` | Calvin 442 / Dave 367 | 809/809 非空 |
| LongMemEval | 1 | 473 | 每条 2 个 child turn id | pair memory 的公开 speaker=`user` | 473/473 非空 |
| HaluMem | 1 | 2,209 | 每条 2 个 child turn id | pair memory 的公开 speaker=`user` | 2,209/2,209 非空 |
| BEAM | 1 | 363 | 每条 2 个 child turn id | pair memory 的公开 speaker=`user` | 363/363 非空 |
| MemBench | 4 | 224 | 159 条 pair×2 + 65 条 singleton×1 | 公开 speaker=`user` | 224/224 非空 |

所有 payload 的 `memory/speaker_id/speaker_name/time_stamp/source_external_ids/
float_time_stamp/weekday` 均存在，source id 无空白。LoCoMo 当前 p50 conversation `conv-50`
含 125 个 caption turn；125/125 的 `dia_id` 均出现在已写 memory lineage 中，说明当前真实 build
确实覆盖 image-bearing turn。共享 caption wrapper 的字节语义仍由 adapter 强反例锁定；本收据不从
抽取后的事实文本反推 caption 原文。

LongMemEval 当前已答题的 `question_time` 1/1 出现在最终 answer prompt；MemBench 4/4 同样如此。
其余三家当前公开 question time 为空，未伪造时间。所有本轮 retrieved item 都有非空 lineage、
非空 timestamp 与有限 score。

## 5. 检索与 metric 身份

| benchmark | artifact 请求深度 | 实际返回条数 | semantic provenance | stable ranking |
| --- | --- | --- | --- | --- |
| LoCoMo | 10 | 60 | `valid/turn` | `pending` |
| LongMemEval | 10 | 60 | `n_a/none`（pair lineage 不能证明具体 child） | `pending` |
| HaluMem QA | 20（Mem0 wrapper 观测 hint） | 22–60 | `n_a/none`（无 turn qrel） | `pending` |
| BEAM | 10 | 60 | `n_a/none`（gold 是单 message，pair 过粗） | `pending` |
| MemBench | 10 | 20–60 | `valid/turn` | `pending` |

这里必须区分两层：`retrieval_query_top_k` 是 request/metric observation hint；LightMem
当前主算法配置以 `retrieve_limit=60` 调产品 retriever，answer builder 与 update scorer 都消费
产品实际返回的完整 `formatted_memory`/memory list。generic Recall@K 才按 artifact 中的 K
观察前 K 条。HaluMem 官方 Mem0 wrapper 的 QA=20、update=10 不是 shared scorer 上限；Memobase
等 wrapper 也使用不同的原生窗口。因此本轮 top-60 正是 LightMem calibration 的合法 method
输出，不存在需要另裁或重跑的 top-k parity blocker。

## 6. 效率观测

所有 API LLM call 的 token 来源都是 `api_usage`；本地 embedding token 来源都是
`tokenizer_estimate`，latency 来源都是 `framework_timer`。逐格实测：

| benchmark | build LLM calls / in / out | answer calls / in / out | build embedding calls | retrieval embedding calls | injected memory tokens |
| --- | --- | --- | ---: | ---: | ---: |
| LoCoMo | 35 / 88,063 / 27,697 | 158 / 413,818 / 1,441 | 1,757 | 158 | 279,376 |
| LongMemEval | 49 / 114,586 / 16,673 | 1 / 2,914 / 48 | 798 | 1 | 2,039 |
| HaluMem | 143 / 321,555 / 74,394 | 169 / 572,070 / 1,612 | 3,963 | 340 | 338,340 |
| BEAM | 30 / 97,712 / 12,427 | 20 / 56,386 / 1,496 | 640 | 20 | 37,378 |
| MemBench | 17 / 33,417 / 7,408 | 4 / 7,747 / 8 | 421 | 4 | 4,668 |

HaluMem 的 340 次 retrieval embedding = 169 次 QA + 171 次 update probe，调用拓扑闭合。
其 71 条 `conversation_efficiency` 是 70 个 session 构建 scope 加 1 次
`end_conversation` finalize scope，不是 71 个 user/isolation；预算外推必须使用总量或
`by_conversation` 汇总，不能把单条 p50/mean 当成整个 UUID 的耗时。

## 7. HaluMem 专项与本批框架修复

- 70/70 session report 为 `status=ok`，memory count 均非零；元数据包含
  `capture_status/captured_memory_count/force_segment/force_extract/method/source`。
- 171 条 update probe 分布在 64 个 session，formatted memory 均非空；当前每条保存产品 top-60。
- 原始 4,855 条 efficiency observation 完整，但旧 operation runner 漏写三份派生效率 summary。
  当前代码已复用共享 `_write_prediction_efficiency_summaries()`；本 run 已从原始 observation
  纯离线回填 overall/by-conversation/by-question 三份 JSON，未调用 API、未改原始 observation。
- 旧 operation runner 没接 `ProgressReporter`，所以本次已完成 HaluMem run 没有
  `checkpoints/progress.json`，也没有终端 Rich 进度。历史进度不可真实回填；当前代码已加入
  session/turn/question heartbeat、标准 Prediction run 首行和 progress.json，新 run/resume 生效。

通用 Rich UI 同时新增一条轻量 `Activity` 行，只显示 worker、phase、公开 session/question id
和 turn/question 计数；全局完成数仍只由 coordinator 在 checkpoint 提交后推进，不用 heartbeat
伪造完成。

## 8. 验收命令

框架改动的定向回归：

```text
339 passed, 12 warnings in 9.56s
```

覆盖 progress reporter、operation-level direct/W2、HaluMem registered prediction、generic
prediction runner 与 CLI；另跑依赖/文档门：

```text
20 passed in 4.06s
```

五格公开 artifact 机器门尾行：

```text
FIVE_RUN_PUBLIC_ARTIFACT_GATE_PASS
```

HaluMem 派生汇总回填尾行：

```text
OFFLINE_DERIVATION_OK observations=4855
```

current 全量零 API 回归：

```text
2350 passed, 3 deselected, 25 warnings, 29 subtests passed in 188.57s (0:03:08)
```

## 9. 下一动作

在不改变现有 run identity 的前提下生成 calibration evaluator 命令。先列出每格适用 metric、
judge call 数与 N/A 项，再由用户确认后调用 API；evaluate 完成并验货前不进入第二批 resume。
