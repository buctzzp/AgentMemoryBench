# ox 完整 isolation pilot 矩阵账

> 状态：首格完成后暂停（2026-08-25）。本文是旧 source/run identity 下的运行账与历史收据，
> 不是效果榜单；其余 49 格不按旧身份续跑。权威当前动作仍在父 README。

## 1. 固定身份与边界

- runtime：`opencodego/ox-alpha-free`，Chat Completions，顶层
  `reasoning_effort="low"`；
- public profile：`pilot`；method TOML section：`smoke`；manifest 必须同时诚实记录二者；
- `official_full`、作者校准和历史 smoke 不在本批；ox 分数不得进入正式效果对比；
- 预测与适用 evaluator 都开 efficiency observation；API token 优先使用 response usage，
  不把 tokenizer estimate 冒充 API 真值；
- 全局 API 并发上限 4；重型本地 runtime 与产品内部会并行发请求的 method 进一步降并发；
- 每格使用新 base run id：`ws05-ox-pilot-<method>-<benchmark>-<variant>-r1`。多 variant
  benchmark 的 runner 可在末尾再追加 variant；账内以实际 manifest run id 为准；
- 不对失败的旧 smoke 做 resume。pilot 若后续演练 resume，必须由单独批准的 failure-recovery
  批次执行，不能与本轮首次完整样本混在一起。

## 2. 五个完整 isolation

| benchmark | variant | 本批 isolation | 现场规模 |
| --- | --- | --- | --- |
| LoCoMo | `locomo10` | 第一条完整 conversation，全部 QA | `conv-26`；19 sessions / 419 turns / 152 questions |
| LongMemEval | `m_cleaned` | 第一条完整 instance，完整 haystack 与全部 QA | `7161e7e2`；482 sessions / 5057 turns / 1 question |
| MemBench | `0_10k` | 一个 run 内四条默认 source lane 各第一条完整 tid | 26 + 328 + 11 + 20 turns；共 4 questions |
| BEAM | `100k` | 第一条完整 conversation，全部 QA | conversation `1`；3 sessions / 188 turns / 20 questions |
| HaluMem | `medium` | 第一条完整 UUID，固定 operation-level 全形状 | `2f1f897e-d67f-dbc5-6a7b-b7634a9e294f`；65 sessions / 2806 turns / 164 questions |

MemBench 四个 tid 保持各自 conversation namespace/state isolation，但不为了四个很小的 tid
启动四份进程。HaluMem 的 CLI 形状由 benchmark 固定，不传 rounds/conversations/question
裁剪参数。

## 3. 10×5 暂停快照

状态枚举：`PENDING`、`PREDICT_PASS`、`EVAL_PASS`、`FAILED(<stage>)`、`N/A(<reason>)`。
`EVAL_PASS` 只表示所有**有资格**的 metric 完成；method × metric 的 N/A 是诚实能力结果。
表中 `PENDING` 只描述本轮暂停时未执行，不是当前恢复队列；M11 后的 source/embedding/run
identity 已变化，后续实验必须使用新 run，不得把这些格子直接 resume 成新身份。

| method | LoCoMo | LongMemEval | MemBench | BEAM | HaluMem |
| --- | --- | --- | --- | --- | --- |
| LightMem | PENDING | PENDING | PENDING | PENDING | PENDING |
| Mem0 | PENDING | PENDING | PENDING | PENDING | PENDING |
| MemoryOS | PENDING | PENDING | PENDING | PENDING | PENDING |
| A-Mem | PENDING | PENDING | PENDING | PENDING | PENDING |
| SimpleMem | PENDING | PENDING | PENDING | PENDING | PENDING |
| MemOS | PENDING | PENDING | PENDING | PENDING | PENDING |
| Letta | PENDING | PENDING | PENDING | PENDING | PENDING |
| EverOS | PENDING | PENDING | PENDING | **EVAL_PASS** | PENDING |
| LangMem | PENDING | PENDING | PENDING | PENDING | PENDING |
| Graphiti | PENDING | PENDING | PENDING | PENDING | PENDING |

## 4. 首格资格证据

EverOS × BEAM actual run：
`ws05-ox-pilot-everos-beam-100k-r1-100k`。

- 1/1 conversation、188 turns、20/20 questions、0 failed；
- 35 memory-build LLM calls + 20 framework answer calls，全部
  `token_measurement_source=api_usage` 且 input/output token 为正；
- 178 memory-build + 20 retrieval embedding calls，均有 exact API observation；
- manifest：`run_scope=pilot`，`profile.name=pilot`，`profile.section=smoke`，
  API runtime model=`ox-alpha-free`；
- `.env` 的 API key 与 base URL 在完整 run tree 和 terminal log 中精确命中数均为 0；
- BEAM recall：20 条均为诚实 `N/A`（EverOS 不声明 exact BEAM source-message qrel），没有
  回落成 0；rubric judge：20 条 score rows，产生 79 次 LLM 调用。79 不是重复计费 bug：
  每条问题先按 rubric item 数逐项打分，event-ordering 再按实际 prediction 行数执行官方
  greedy semantic-equivalence 调用；逐 question 的 observation 数均不少于 rubric_count，
  非 event-ordering 恰等于 rubric_count。79 次均为 `api_usage`，input/output token 为正；
- prediction + evaluation 完整树及两份 terminal log 对 `.env` key/base URL 的精确命中数为 0。

## 5. 每格完成门

1. manifest 的 method、benchmark、variant、run scope、profile/section、provider/model 与 source
   identity 全部正确；
2. isolation/turn/session/question 数与第 2 节固定口径一致，completed=total，failed=0；
3. build、embedding、retrieval、answer 以及适用 judge 的 observation 不缺调用，source 与实际
   transport 匹配；API LLM 成功返回 usage 时必须是 `api_usage`；
4. public prediction 不含 gold/evidence/private label；key/base URL 不进入 artifact/log；
5. 只运行 registry 判定有资格的 metric，N/A 不回落为 0，也不伪造 source lineage；
6. 失败先分类为共因 transport、method 产品行为、benchmark shape 或外部服务，再决定是否扩大
   同波；不得为了让矩阵变绿修改算法核心。
