# Letta/MemGPT sleeptime-memory adapter M2 检查点

日期：2026-08-02
状态：`READY_FOR_B11_REAL_SMOKE_APPROVAL`
用途：跨 task / compaction 的最小恢复入口；完整证据见 M1、M2 实现记录与五格安全档案。

## 1. 已锁身份

- 主轨 = legacy Letta V1 `0.16.8` core + official `ai-memory-sdk v0.2.0`
  sleeptime-memory contract；五格均为 framework extension，无 `author_*`。
- 不启动 HTTP host，不 direct archival insert/search；独立 Python worker 内直接调用
  `SyncServer`、manager 与 `AgentLoop`。
- `consume_granularity=session`，session 内最多 10 message 一批，不跨 session、不补
  placeholder、不按位置重配 role。
- raw turn 不写 vector store；产品记忆是持续演化的 attached `human/summary` core blocks；
  retrieve 不消费 query，读取全部 blocks。
- W1-only；TOML、registry 与 `plan-smoke` 都在 runtime/API 前拒绝 W2。

## 2. M2 已完成

1. `scripts/bootstrap_letta_runtime.sh` 用 vendored lock 构建 Python 3.12 runtime，并显式固定
   `asyncpg/pg8000/pgvector/asn1crypto/scramp` 补充依赖；
2. `LettaRuntime` 拥有 labeled pgvector volume/container、migration、worker 与 close；worker
   env 采用 allowlist，build key 只在一次 agent step 内临时暴露；
3. 真实 sleeptime agent、四个 memory tools、两 core blocks、无 embedding initializer、
   terminal/usage/steps 验收、query-independent readout 已接线；
4. sidecar 两阶段 operation journal 关闭“产品可能已写、checkpoint 尚未提交”的重放窗口；
   pending 必须 namespace clean retry，completed replay 不重写；
5. generic 与 operation runner 已接 `prepare()`；isolated worker 收到真实 `RunContext`，且协议/
   粒度校验先于资源启动；
6. 五格 payload、异常、隐私与 metric 资格已收进
   [安全档案](letta-five-benchmark-safety-dossier.md)。

## 3. Metric 最终裁决

- 五格 Recall/Precision/F1@k、LongMemEval NDCG、stable ranking：`N/A`；
- HaluMem extraction：`N/A`；
- HaluMem update：`valid`；
- HaluMem QA：`valid`；
- HaluMem memory type：`N/A`。

**M1 初判勘误**：update 不要求 session-local `SessionMemoryReport`。HaluMem 官方路径在当前
session 写入后，用更新后的 memory content 查询当前系统记忆并 judge；演化 core blocks 正是
被评对象。session-local delta 只阻塞 extraction，不能因 retrieval evidence N/A 连坐 update。

## 4. 当前验证锚

真实零 API product proof：

```text
LETTA_ZERO_API_PRODUCT_CHAIN_PASSED
{'agent_id_stable': True, 'block_labels': ['human', 'summary'], 'namespace_deleted': True}
```

证明覆盖 Docker pgvector、extension、Alembic、`SyncServer`、agent/blocks、initializer、readout、
namespace delete、`close_db` 与 owned Docker 收尾；没有 LLM/embedding 请求。

11 个 concrete variant 的 `smoke-plan-v1` 已生成审阅：LoCoMo 1、LongMemEval 2、MemBench 2、
BEAM 4、HaluMem 2；全部 W1。croppable 格为 history/isolation/question=1，HaluMem 保持 fixed
4 sessions / 1 isolation / 1 QA。原始 planner 输出见
[`letta-smoke-plans-v1.json`](letta-smoke-plans-v1.json)。

最新门：扩展定向 `458 passed in 9.94s`；主树全量
`1968 passed, 3 deselected, 13 warnings, 29 subtests passed in 131.45s`；compileall、diff、
ledger、plan JSON、vendored source identity 与零 API product chain 全通过。完整命令/警告归因见
[M2 实现记录](letta-m2-adapter-implementation.md#8-验证记录)，不得从本热层猜旧数字。

## 5. 当前唯一主动作

1. 把 planner 生成的预算、规模、run ids 交用户批准；
2. 真实 B11 predict/evaluate → artifact gate → frozen note；
3. 未获新批准前不得调用真实 API。

## 6. 压缩后恢复顺序

1. `git status --short`
2. `git log -5 --oneline`
3. 父 README 顶部恢复胶囊
4. 本检查点
5. 当前若在 B11，只定点读 M2 实现记录 §8-10 与安全档案 §8

禁止重新做 Letta source survey、五 benchmark raw census 或产品初始化探针；只有 source/hash/
stable contract 漂移才重开对应门。
