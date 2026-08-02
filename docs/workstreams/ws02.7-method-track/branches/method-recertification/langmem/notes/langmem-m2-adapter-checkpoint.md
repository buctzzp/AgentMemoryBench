# LangMem background-manager adapter M2 检查点

日期：2026-08-02
状态：`READY_FOR_B11_REAL_SMOKE_APPROVAL`
用途：跨 task / compaction 的最小恢复入口；完整证据见 M1、M2 实现记录与五格安全档案。

## 1. 已锁身份

- current source：官方 `langchain-ai/langmem` commit
  `56d85939d80bb731bd5e237567148d817d7bfd16`，package `0.0.30`，MIT；五个 Phase-1
  benchmark 均无官方 harness，全部是 framework extension。
- 主轨：官方 background `create_memory_store_manager()` + async `ainvoke()` + 同一
  `MemoryStoreManager.asearch()`；不启动 HTTP host、不让 React agent 决定是否记忆、不用
  direct raw store put 绕过 extraction/update。
- `consume_granularity=session`；一个 canonical session 一次 manager 调用，role/content 原序，
  不补 placeholder、不跨 session 重配。
- 主配置锁 public factory 默认：`Memory(content)`、insert/update 开、delete 关、
  `query_model=None`、`query_limit=5`、`max_steps=1`；本地 MiniLM-384 normalized +
  LangGraph InMemoryStore cosine。

## 2. M2 已完成

1. 每个 provider 独占 Python 3.12 worker、event loop、ChatOpenAI、SentenceTransformer、store 与
   state root；主框架 import 不吸收 LangChain 依赖树；
2. product store exact key/value/插入顺序与 completed-operation journal 同文件原子提交；
   result-loss retry、payload drift、manager/persist rollback 均有强反例；
3. failed-ingest clean 使用 active→tombstone→namespace delete→empty verify，失败可重试且不跨空间；
4. 五格 role/speaker/time/place/image/异常/private negative-space 已收进
   [安全档案](langmem-five-benchmark-safety-dossier.md)；
5. build exact API usage、本地 embedding tokenizer/latency、product retrieval latency 与
   rehydration metadata 均接线；secret 只经 worker env allowlist 传递；
6. W2 为两个真实 isolated provider/worker/state owner；HaluMem operation runner 固定 W1。

## 3. Metric 最终裁决

- stable product ranking：`valid`；
- semantic provenance：`N/A / langmem_evolved_memory_not_source_exact`；
- 五格 Recall/Precision/F1@k 与 LongMemEval NDCG：`N/A`；
- HaluMem extraction：`N/A`；update：`valid`；QA：`valid`；memory type：`N/A`。

这里的 N/A 来自 current memory 可 update/consolidate、没有 lossless semantic source mapping，
不是缺少检索接口；不得把“某 source 参与过生成”升级成“当前 memory 仍承载该 gold unit”。

## 4. 当前验证锚

真实零 API product readout：

```text
LANGMEM_ZERO_API_PRODUCT_READOUT_PASSED
```

它覆盖隔离 worker、本地 MiniLM、真实 InMemoryStore、官方 manager `asearch()` zero-hit、
namespace clean 与关闭；没有 build/answer/judge 请求。

最新门：扩展定向 `473 passed in 9.12s`；主树全量
`2021 passed, 3 deselected, 13 warnings, 29 subtests passed in 132.29s`；compileall、diff、
ledger validator、20-entry plan JSON 与 nested source identity 均通过。warning 仅来自既有
LightMem/MemOS 第三方代码。

机器计划见 [`langmem-smoke-plans-v1.json`](langmem-smoke-plans-v1.json)：9 个 croppable
concrete variant 各 W1/W2，2 个 HaluMem fixed variant 各 W1，共 20 份；禁止手写替代 planner
输出，也不得给 HaluMem 命令追加通用裁剪参数。

## 5. 当前唯一批准门

1. 用户批准 LangMem B11 的预算、20 份 planner run 与 run id；
2. 逐 plan 真实 predict/evaluate，并开箱 manifest、prediction、formatted memory、private
   negative-space、efficiency、state、summary 与 W1/W2 ownership；
3. 全部通过后写 frozen note、把 ledger 转为 frozen 并同步父状态页。

未获批准前不得调用真实 build/answer/judge API。official_full、效果参数与 full 成本 pilot 不属于
本批准门，后续另议。

## 6. 压缩后恢复顺序

1. `git status --short`
2. `git log -5 --oneline`
3. 父 README 顶部恢复胶囊
4. 本检查点
5. 当前若在 B11，只定点读 M2 §9-10、安全档案 §8 与 machine plan 原文

禁止重新做 LangMem source survey 或五 benchmark raw census；只有 source/hash、product factory、
store/ranking、wrapper identity 或 benchmark stable contract 漂移才重开对应 ledger 门。
