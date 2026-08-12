# Graphiti B11 首次真实尝试

日期：2026-08-09

状态：`SUPERSEDED_BY_GRAPHITI_FROZEN_V1；FAILED_SMOKE_NONRESUMABLE`

> **2026-08-11 架构师勘误**：本 note 首版 §4 错把 formal 的 failed-ingest
> resume 能力套给了 `predict smoke`。current CLI 在
> `src/memory_benchmark/cli/main.py::_normalize_smoke_prediction_args()` 明确拒绝
> `--resume` 和 `--retry-failed`，对应强反例也已存在。旧失败 run 只保留作 403 与
> checkpoint 边界证据，不得续跑。区域 opt-in 已由用户解除；LoCoMo answer identity 又从
> 128 改为显式 4096，因此下一次必须使用新 machine plan 与新 run_id。

## 1. 判词

用户已批准使用 `.env` 中的 OpenCodeGo smoke profile。架构师逐字执行 Graphiti machine plan
中的首个 LoCoMo W1；请求到达 Graphiti product build LLM 后，OpenCodeGo 返回 HTTP 403，说明
当前 workspace 尚未显式启用该区域模型。该错误与此前 Letta 首次真实尝试命中的外部门相同。

```text
GRAPHITI_B11_PAUSED_EXTERNAL(
  first product build request reached OpenCodeGo;
  provider returned RegionError 403 before the first turn committed;
  failed-ingest checkpoint and resumable physical state are intact;
  no remaining plan or evaluator was run
)
```

这不是预算未批准、Graphiti adapter 离线失败或“零报错即通过”。在同一账号授权状态未变化前，
继续重试其余 17 份计划只会重复命中同一个外部门，因此本轮按预算纪律停下。

## 2. 实际命令与失败位置

首个计划：

```bash
uv run memory-benchmark predict smoke \
  --root /Users/wz/Desktop/memoryBenchmark \
  --method graphiti \
  --benchmark locomo \
  --variant locomo10 \
  --config-track unified \
  --run-id graphiti-locomo-v1-r1q1-w1 \
  --allow-api \
  --rounds 1 \
  --conversations 1 \
  --questions-per-conversation 1
```

运行已通过 CLI、registry、profile、worker initialize、FalkorDB Lite activation 与本地 embedding
装配，到首个 `Graphiti.add_episode()` 内的 build Chat Completions 请求时停止。provider 错误类型为
`RegionError`、HTTP status 为 `403`；workspace 专属链接/标识不写入仓库文档。

## 3. 失败 run 开箱

run root：

```text
outputs/runs/graphiti/locomo/smoke/unified/graphiti-locomo-v1-r1q1-w1/
```

逐项验货：

- `manifest.json` 已声明 `graphiti-oss-product-v1`、Graphiti
  `v0.29.3@021d3a57`、OpenCodeGo `deepseek-v4-flash`、Chat Completions、
  `thinking=disabled`、local MiniLM-384、turn provenance 与 product RRF rank；
- `checkpoints/conversation_status.json` 中 `conv-26` 为
  `status=failed_ingest, stage=ingest, ingested=false`；
- `checkpoints/progress.json` 为 ingest stage，conversation/question 完成数均为 0；
- `method_state/.../state.json` 的 `episode_to_turn`、`operations`、`sessions` 均为空；首个 turn
  没有被误报为已提交；
- public question 与 evaluator-private label 已分别写入自己的 artifact；没有 prediction、
  efficiency observation 或 evaluation summary，符合失败阶段；
- conversation 物理 root 被保留，供 generic failed-ingest clean hook 在恢复时做精确删除；
  worker、FalkorDB Lite/Redis 进程均已退出，无后台残留。

上述状态不能升级 B11 real-smoke/artifact/parallel gate；它只证明真实 runtime 已到 provider，且
失败边界、checkpoint 与 cleanup 前置状态诚实。

## 4. 恢复方式（首版口径撤回）

`predict smoke` 不能 resume；首版写出的命令会在 CLI 归一化阶段直接报：

```text
predict smoke does not support --resume
```

正确路径是：

1. 保留 `graphiti-locomo-v1-r1q1-w1` 作为失败证据，不删除、不改写；
2. 用 `plan-smoke` 重新生成
   [v2 machine plans](./graphiti-smoke-plans-v2.json)，新 LoCoMo W1 run_id 为
   `graphiti-locomo-v2-r1q1-w1`；
3. 新 run 的物理 root 按 run identity 独立，不复用 v1 的 failed checkpoint 或 state；
4. 先执行 v2 LoCoMo W1，成功开箱后才继续 W2 与其他 variant；
5. 如果同一外部门再次出现，只停一次并记录，不循环重试。

physical clean + retry 仍是 formal failed-ingest resume 的合法能力，但不是 smoke B11 的恢复
机制。两者必须由 CLI/profile 资格决定，不能仅因 runner 底层有 clean hook 就推断上层命令可用。

## 5. 当前关系

- M3 离线 adapter 结论保持有效；
- 当时 Graphiti ledger 仍为 `ready_for_smoke`；区域 opt-in 已解除，B11 进入 v2 新 run 队列；
- 当时 Graphiti 尚未 frozen；2026-08-12 的后续状态见 §6；
- 旧 v1 失败 run 与 v2 新 run 不可合并比较；v2 使用 OpenCodeGo + LoCoMo 显式 4096 answer
  completion cap，manifest 必须写对应 compatibility identity。

## 6. 后续结果（2026-08-12）

本 note 只保留首次失败与 smoke-resume 勘误。区域门解除后，架构师从 planner 生成的全新 v2
identity 执行 18/18 predict/evaluate，随后完成 artifact/隐私/效率/物理隔离与真实 FalkorDB
payload 两道机器门。最终结论、运行规模、N/A 边界与回归证据已迁入
[Graphiti method-frozen-v1](./graphiti-frozen-v1.md)；本页的 failed v1 run 不参与 frozen 结果。
