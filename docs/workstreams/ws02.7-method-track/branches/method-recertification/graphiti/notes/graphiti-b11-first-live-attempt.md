# Graphiti B11 首次真实尝试

日期：2026-08-09

状态：`PAUSED_EXTERNAL_OPENCODEGO_REGION_OPT_IN`

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

## 4. 恢复方式

外部区域 opt-in 完成后，先恢复这个既有 run，不创建同名新 run：

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
  --questions-per-conversation 1 \
  --resume \
  --retry-failed-conversations
```

该恢复必须先看到 physical clean hook 删除旧 conversation root，再重新 ingest。predict 成功后才
执行 machine plan 自带的 evaluate 命令和逐 run artifact gate；随后继续剩余计划。若区域门仍为
403，再次停止，不把相同错误当新证据反复付费。

## 5. 当前关系

- M3 离线 adapter 结论保持有效；
- Graphiti ledger 仍为 `ready_for_smoke`，但 B11 外部状态为
  `PAUSED_EXTERNAL_OPENCODEGO_REGION_OPT_IN`；
- Graphiti 尚未 frozen；
- Letta、LangMem、EverOS 与 Graphiti 共用同一外部门。解除后按已记录的队列先恢复 Letta，
  再 LangMem、EverOS，最后恢复本 run，避免四条支线各自发明新的顺序。
