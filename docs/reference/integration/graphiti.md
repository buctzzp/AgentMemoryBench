# Graphiti integration

状态：`method-frozen-v1`

## 身份

| 项 | 当前锁定 |
| --- | --- |
| method id | `graphiti` |
| upstream | `https://github.com/getzep/graphiti.git` |
| version | `v0.29.3@021d3a57d511f21b10adaf7fa923bd5c1fce5e9d` |
| license | Apache-2.0 |
| local source | `third_party/methods/graphiti` |
| Phase 1 身份 | Graphiti OSS；不是 Zep hosted/product parity |
| adapter | `graphiti-oss-product-v1` |
| product surface | direct `Graphiti.add_episode()` + `Graphiti.search()` |
| storage | 每 conversation 独占 FalkorDB Lite 物理 root |
| embedding | local `all-MiniLM-L6-v2`，384 维、L2 normalize、cosine |

Graphiti 于 2026-08-09 经用户裁定接替 source-unavailable 的 Supermemory。2026-08-09 再核远端
tag：`v0.29.3` 仍是最新稳定版，`v0.30.0` 仅有 pre-release。Supermemory 旧 blocked note
保留为 source-gate 判例，但不再占 Phase 1 第十格。

## 产品与配置

- ingest：每个 nonblank canonical turn 一次 `add_episode(source=message)`，逐条 await；
- retrieve：默认 edge BM25 + cosine + RRF；返回有序 EntityEdge fact 与 temporal validity；
- runtime：不启动 HTTP host，独立 Python 3.12 worker 直调与官方 server 相同的 core；
- smoke：`.env` 的 `opencodego/mimo-v2.5`，Chat Completions + `json_object` +
  `thinking=disabled`，成功 response 必须带 exact usage；
- official_full：`primary/gpt-4o-mini` + `json_schema`；
- cross encoder：主 search 不调用；官方基类 sentinel 一旦被调用即 fail-fast；
- cleanup：root 外 marker → 固定 tombstone → resumable rmtree，embedded Redis 必须 exact stop；
  shutdown 未确认后 runtime 永久 fail-closed。

current stable repo 只含 LongMemEval graph-building eval：逐 message `role: content`、session date、
单 user group。它没有完整 question search/answer/judge，因此只提供 payload parity；LoCoMo、
HaluMem、BEAM、MemBench 都是 framework extension。Graphiti OSS 也不等于 Zep cloud 产品。

## 五格资格

| Benchmark | 输入与异常边界 | Retrieval metric | 运行状态 |
| --- | --- | --- | --- |
| LoCoMo | speaker_a→user、speaker_b→assistant；真实 speaker 前缀；caption wrapper；逐 turn time | provenance valid/turn；rank valid | W1/W2 live passed |
| LongMemEval | raw role/order；逐 turn；不配对、不补 placeholder | provenance valid/turn；rank valid | S/M W1/W2 live passed |
| MemBench 0-10k | First/Third canonical turn；原文 place/time 保留，typed time 另传 | provenance valid/turn；rank valid | W1/W2 live passed |
| MemBench 100k | source time 可能缺失，Graphiti reference_time 必填 | N/A；禁止造时 | pre-runtime rejected |
| BEAM | 四 variant 原序；10M orphan/mismatch 不位置配对 | provenance valid/turn；rank valid | 四 variant W1/W2 live passed |
| HaluMem | 逐 turn add；session-local current active edge report | extraction/update/QA/memory-type valid | Medium/Long fixed W1 passed |

HaluMem memory-type 是 gold category breakdown，不要求 method 自己输出 Event/Persona/Relationship；
早期 M2 草稿中的 N/A 已更正。统一 `query_limit=20` 只是容量上限：普通 query 仍用自身 top-k，
HaluMem QA 的既有请求可完整取 20。

## 证据入口

- source/product：[M1 ruling](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-v0.29.3-source-product-m1-ruling.md)
- runtime/lineage：[M2 ruling](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-v0.29.3-product-runtime-m2-ruling.md)
- adapter/product probes：[M3 implementation](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-v0.29.3-product-adapter-m3-implementation.md)
- 五格安全档案：[dossier](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-five-benchmark-safety-dossier.md)
- 状态单一事实源：[integration ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-integration-ledger.md)
- 首次真实运行：[B11 first live attempt](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-b11-first-live-attempt.md)
- 冻结验收：[method-frozen-v1](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-frozen-v1.md)

18 份 v2 plan 已于 2026-08-12 全部真实完成：35 conversation、35 question、88 个真实
Graphiti product episode。artifact gate 与 FalkorDB payload parity 均机器通过，所有 croppable
variant 的 W1/W2 都有真实物理隔离证据；旧 v1 403 run 仅保留为失败边界历史。MemBench 100k、
默认 BEAM abstention 与 LongMemEval M no-target 的 N/A 边界，以及 full/cost/author calibration
等声明缺口，均见 frozen note，不从极小 smoke 分数推断效果。
