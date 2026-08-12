# Graphiti v0.29.3 产品 adapter M3 实现记录

日期：2026-08-09

状态：`M3_ACCEPTED；SUPERSEDED_BY_METHOD_FROZEN_V1`

## 1. 实现判词

Graphiti OSS v0.29.3 已以 provider v3 接入五 benchmark：主轨不启动 HTTP host，不直接写
node/edge，而是在独立 Python 3.12 worker 内调用公开 `Graphiti.add_episode()` 与
`Graphiti.search()`。每个 conversation 独占 FalkorDB Lite 物理 root，本地 MiniLM 走公开
`EmbedderClient` extension point；build LLM 由项目 smoke/official runtime profile 决定。

当前离线判词：

```text
READY_FOR_B11_REAL_SMOKE(
  10 concrete variants are executable;
  MemBench 100k is methodologically N/A before API/runtime/output;
  five-grid payload, lineage, ranking, lifecycle and operation metrics are closed;
  18 machine plans cover W1/W2 where applicable and fixed HaluMem W1
)
```

## 2. 实际实现面

- `graphiti_adapter.py`：强类型配置、五格 turn 渲染、source time、product edge readout、
  RetrievalEvidence、效率观测、生命周期和 physical clean hook；
- `graphiti_worker.py`：telemetry-off JSON-lines worker、Graphiti/FalkorDB Lite 装配、本地
  SentenceTransformer、OpenAI-compatible usage wrapper、atomic sidecar、session-local edge
  report、可恢复物理删除；
- `registry.py` / `run_prediction.py` / `smoke_plan.py`：注册、模型与 source identity、
  pre-runtime variant gate、机器计划；
- `configs/methods/graphiti.toml`：`smoke=opencodego/deepseek-v4-flash+json_object`，
  `official_full=primary/gpt-4o-mini+json_schema`，两者共用 MiniLM-384、cosine 与 product
  search；
- `bootstrap_graphiti_runtime.sh`：按 source-locked `uv.lock` 安装 Python 3.12 runtime，并用
  **真实 import symbol** 校验 `redislite.async_falkordb_client.AsyncFalkorDB`、Graphiti 与
  SentenceTransformer。

## 3. M2 后由强反例修正的事实

1. `falkordblite` 是 distribution 名，实际 async import 在 `redislite`；只验证包安装会产生
   假绿，bootstrap 现验证真实 symbol。
2. Graphiti 构造时 Pydantic 会做 nominal type 校验，未继承官方 `CrossEncoderClient` 的
   duck-typed sentinel 会被拒绝；当前 sentinel 继承官方基类，主 search 一旦真正调用即
   fail-fast。
3. HaluMem memory-type 是 gold-category breakdown，不是 method 分类任务；extraction/update
   有效后该 evaluator 同样有效。
4. HaluMem QA 请求 top-k 20，因此统一 `query_limit` 上限必须是 20；adapter 仍逐请求传递真实
   `query.top_k`，不强行多取。
5. failed clean 不能把 live path 消失当完成。当前用 root 外原子 marker、固定 tombstone 与
   可重入 `rmtree`；部分删除后 activation 继续拒绝，直到 cleanup 完成。
6. worker shutdown 未确认后 runtime 永久 fail-closed；第二次 `close()` 不会把一次失败伪装成
   closed。部分构造失败时 driver/Lite 也会被 exact cleanup。

## 4. 产品链实证（零真实 API）

隔离 runtime 的本地 fake Chat Completions endpoint 实跑真实
`add_episode → search → session_memories → shutdown`，由真实 MiniLM 与 FalkorDB Lite 产出
一个 edge：

```text
GRAPHITI_M3_LOCAL_EDGE_CHAIN_PASS {
  'llm_calls': 2,
  'build_embedding_calls': 6,
  'retrieval_embedding_calls': 1,
  'items': [('Alice moved to Seattle.', ['t1'])],
  'session_memories': ['Alice moved to Seattle.'],
  'http_calls': 2
}
```

测试同时比较 retrieve 前后的 session report 与 atomic sidecar bytes，二者逐字相等；结合
current `search()` call graph 无写入口，B8 判为只读。另有 initialize/shutdown 零 API、
partial-constructor cleanup、cleanup tombstone resume 与 permanent close-failure 强反例。

## 5. 五格与 metric 结果

| Benchmark | 生产输入/异常处置 | RetrievalEvidence | HaluMem operation |
| --- | --- | --- | --- |
| LoCoMo | 固定 speaker_a→user、speaker_b→assistant；真实 speaker 前缀；caption wrapper；逐 turn source time | provenance valid/turn；rank valid | 不适用 |
| LongMemEval | raw role/order；assistant-first、same-role、singleton 均逐 turn，不补 placeholder | valid/turn；rank valid | 不适用 |
| MemBench 0-10k | First/Third canonical turn；原文 place/time 保留，另提取 typed time | valid/turn；rank valid | 不适用 |
| MemBench 100k | source time 可能缺失；禁止 question/sibling/wall clock 造时 | method×variant N/A，pre-runtime fail-fast | 不适用 |
| BEAM | 四 variant 原序；10M orphan/mismatch 不位置配对、不补假回复 | valid/turn；rank valid | 不适用 |
| HaluMem | 逐 turn add；session sidecar 只报告本 session 当前 active edges | valid/turn；rank valid | extraction/update/QA/memory-type 均 valid |

完整格子安全说明见
[五格 dossier](./graphiti-five-benchmark-safety-dossier.md)。

## 6. Machine plan

[graphiti-smoke-plans-v1.json](./graphiti-smoke-plans-v1.json) 保存 18 份原始
`smoke-plan-v1`：10 个可运行 concrete variant 中，8 个 croppable variant 各 W1/W2，
HaluMem medium/long 各固定 W1。MemBench 100k 没有生成命令，而是在 planner 与 predict 入口
同时 N/A fail-fast。

## 7. 离线验收

- Graphiti 五格/registry/planner/product-worker 定向：`131 passed in 20.58s`；
- 扩展 runner/CLI/artifact/ledger/doc 门：`467 passed in 26.65s`；
- planner census：10 个 `READY`，MemBench 100k 一个明确 `N_A`；
- 整仓无 API：`2133 passed, 3 deselected, 13 warnings, 29 subtests passed in 156.70s`；
- compileall：exit 0；`git diff --check`：exit 0；
- Graphiti worker/FalkorDB Lite 进程收尾：零残留（进程查询只命中查询自身）。

13 个 warning 全来自既有 vendored LightMem/MemOS。

## 8. 首次真实 B11 尝试

用户批准后已逐字执行 machine plan 的首个 LoCoMo W1。运行到首次 product build LLM 请求时，
OpenCodeGo 返回区域模型尚未显式 opt-in 的 HTTP 403；其余计划与 evaluator 均未继续执行。
failed-ingest checkpoint、空 sidecar、保留的物理 root、无进程残留与当时恢复说明见
[B11 首次真实尝试](./graphiti-b11-first-live-attempt.md)。M3 离线结论不变，但不得在外部门解除前
把 Graphiti 标为 frozen，也不得重复请求相同 403。

## 9. 2026-08-11 v2 live restart

用户已解除 OpenCodeGo 区域 opt-in。架构师复核 current CLI 后撤回“既有 smoke run
resume+retry”口径：`predict smoke` 在入口明确拒绝两项旗标。旧 v1 run/plan 保持历史证据；
LoCoMo answer compatibility 改为显式 4096 后，已由 `plan-smoke` 重新生成
[18 份 v2 plans](./graphiti-smoke-plans-v2.json)。其中 8 个 croppable variant 各 W1/W2，
HaluMem medium/long 各 fixed W1，无非法裁剪参数；MemBench 100k 继续 N/A。

## 10. 2026-08-12 B11 关闭

18/18 v2 predict/evaluate 已完成。35 conversation、35 question、88 个真实 product episode
通过 artifact/隐私/效率/物理隔离机器门；从 FalkorDB 直接读取的 Episodic
`name/content/valid_at` 又与 production renderer 重建值逐字一致。运行中关闭的 LoCoMo
OpenCodeGo cap、HaluMem JSON transport、metric artifact prerequisite 与 operation-level top-k
serializer 均是通用 framework 修复。最终冻结身份、缺口与回归证据见
[Graphiti method-frozen-v1](./graphiti-frozen-v1.md)。
