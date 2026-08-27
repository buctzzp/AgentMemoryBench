# Answer prompt artifact v2 与现有 calibration 迁移收据

日期：2026-08-27

范围：prediction serializer / resume readback / 现有 LightMem、SimpleMem calibration artifact

真实 API：零

## 1. 问题与裁决

旧 `answer_prompts.prediction.jsonl` 每道题都保存完整 `prompt_messages`。在 benchmark-owned
builder 下，完整 prompt 只是固定模板与逐题动态字段的渲染结果；同一 run 又只允许一个
`answer_builder` identity，因此逐题复制模板正文既浪费空间，也淹没真正需要审计的
retrieval payload。

新合同定为 `answer-prompt-artifact v2`：

- run manifest 只保存一次 `answer_prompt_artifact`，当前主表为
  `answer_builder=benchmark`、`prompt_track=unified`、
  `per_question_prompt_messages=false`；未来作者校准仍由 run identity 的 builder 名称区分，
  不允许同一 run 混用两种 builder；
- 每道题保留 `formatted_memory`、结构化 `retrieved_items`、请求的 `top_k`、
  `retrieval_evidence` 与必要 metadata；这些是每题真正不同、且 retrieval metric/resume
  必须消费的动态事实；
- 注册 builder 路径不再保存完整 `prompt_messages`。answer 失败后 resume 使用 source-locked
  public `Question`（含 question time/options）+ 已保存 `RetrievalResult` + manifest 锁定的
  builder 重建请求，不重新调用 method `retrieve()`；
- 旧 v1 行若仍含 `prompt_messages`，继续逐字回读；没有可调用 builder 的真实
  provider-native 兼容路径仍保存精确 messages，不能为了减小文件破坏可恢复性。

这次只改 serializer 投影与 readback，不删除 canonical Dataset 事实、不改 prompt 模板、
answer、retrieval、score 或 token observation。

## 2. 现有十个 run 的迁移门

迁移前对 10 个 calibration run 的 2,176 条记录逐题执行：

1. 从 `public_questions.jsonl` 重建公开 `Question`；MemBench options 从公开
   `metadata.choices` 恢复；
2. 从旧 answer artifact 重建 `RetrievalResult`；
3. 调用 current registered benchmark builder；
4. 新生成的 `prompt_messages` 与旧行逐字比较；任一不一致即停止，不写文件；
5. 全部通过后才原子删除逐题 `prompt_messages`，并给 manifest 写 v2 marker；
6. 除 manifest 与目标 answer artifact 外，run 内每个文件的 SHA-256 前后必须相同。

结果：`ALL_REBUILD_MATCH rows=2176`，10/10 run 通过，protected artifact 无改动。

| Method | Benchmark | 行数 | 迁移前 bytes | 迁移后 bytes | 节省 bytes |
| --- | --- | ---: | ---: | ---: | ---: |
| LightMem | BEAM | 60 | 2,072,806 | 1,627,197 | 445,609 |
| LightMem | HaluMem | 517 | 19,243,969 | 14,384,471 | 4,859,498 |
| LightMem | LoCoMo | 488 | 15,232,973 | 12,119,023 | 3,113,950 |
| LightMem | LongMemEval | 3 | 106,693 | 85,170 | 21,523 |
| LightMem | MemBench | 20 | 342,956 | 267,798 | 75,158 |
| SimpleMem | BEAM | 60 | 821,016 | 596,825 | 224,191 |
| SimpleMem | HaluMem | 517 | 12,759,529 | 8,715,444 | 4,044,085 |
| SimpleMem | LoCoMo | 488 | 6,281,801 | 4,651,103 | 1,630,698 |
| SimpleMem | LongMemEval | 3 | 43,086 | 31,653 | 11,433 |
| SimpleMem | MemBench | 20 | 251,018 | 179,935 | 71,083 |
| **合计** |  | **2,176** | **57,155,847** | **42,658,619** | **14,497,228 (25.4%)** |

迁移后再次直接运行 artifact-only consumer：10 个 run 全部可读，LoCoMo Recall、
LongMemEval Recall/rank、MemBench Recall 与 BEAM Recall 共 10 组逐题 score records 与迁移前
既有文件精确相同；HaluMem 517+517 行公开/private/answer id 对齐。

## 3. 顺带发现的独立旧账

LightMem MemBench 的 `membench_source_accuracy` 是累计到 12 道题时生成的派生 summary，
但该 run 后续 resume 已达到 20 道题，旧 summary 没有重跑。这与 prompt 迁移无关：该 evaluator
只读 `membench_choice_accuracy`，完全不消费 answer prompt artifact。

已用现有 choice score 零 API重算：四 lane 各 5 题，总计 `14/20`，accuracy=`0.70`；
对应 source score/summary 已更新。它是“分批 prediction 后所有派生 evaluator 都要再覆盖完整
completed cohort”的新反例，不得把旧 summary 的存在当成 freshness 证明。

## 4. 自检收据

- 目标 runner/十家 registered workflow/文档门：`329 passed in 19.68s`；
- v2 compact resume 强反例：首次 answer 在 retrieve 后失败，resume 重建逐字 prompt、第一题
  不再 retrieve，只检索下一题；
- 旧 v1 native prompt 行继续精确复用；
- 现有 2,176 行迁移：`MIGRATION_OK`，零 API；
- artifact-only 等价门：`COMPACT_ARTIFACT_CONSUMERS_OK runs=10 exact_metric_checks=10`。
- current 全量零 API门：`2365 passed, 3 deselected, 25 warnings, 29 subtests passed in
  184.24s`。

## 5. 下一停点

当前不能直接把 Mimo token 数按价格换成 GPT-4o-mini 预算。用户将补充 GPT-4o-mini 经费后，
应在同一批代表 isolation、同一 method/benchmark/stage 上取得两边真实 SDK `api_usage`，先测
input/output token 与调用拓扑比例；比例若不稳定，只能报告区间与假设。未获新的真实 API
授权前不启动该实验，也不生成简单比例外推表。
