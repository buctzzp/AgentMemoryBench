# Graphiti integration

状态：`M1 source/product locked；adapter not implemented`

## 身份

| 项 | 当前锁定 |
| --- | --- |
| method id | `graphiti` |
| upstream | `https://github.com/getzep/graphiti.git` |
| version | `v0.29.3@021d3a57d511f21b10adaf7fa923bd5c1fce5e9d` |
| license | Apache-2.0 |
| local source | `third_party/methods/graphiti` |
| Phase 1 身份 | Graphiti OSS；不是 Zep hosted/product parity |

Graphiti 于 2026-08-09 经用户裁定接替 source-unavailable 的 Supermemory。Supermemory 旧 blocked
note 保留为历史证据，但不再占 Phase 1 第十格。

## 已锁产品接口

- ingest：direct async `Graphiti.add_episode(...)`，每个 source message 一个 episode、逐条 await；
- retrieve：`Graphiti.search(query, group_ids, num_results)`，默认 edge BM25 + cosine + RRF；
- result：有序 `EntityEdge` facts，含 temporal validity 与 `episodes` source ids；
- storage 候选：官方支持的 embedded FalkorDB Lite；
- cleanup 候选：独占 group/database 的精确 clear + empty verification；
- HTTP server 只是相同 core 的异步 queue wrapper，completion 更弱，主轨不用 host。

## Official benchmark 边界

current stable repo 只含 LongMemEval graph-building eval：每个 message 以
`role: content`、session date、单 user group 逐条 add。它没有 question search/answer/judge/NDCG，
因此只能锁 payload，不是完整作者结果复现。LoCoMo/HaluMem/BEAM/MemBench 都是 framework
extension。

## 当前待闭合

1. FalkorDB Lite 文件/进程 ownership、group/database isolation、W1/W2 与 clean retry；
2. OpenCodeGo `OpenAIGenericClient(json_object)` 的结构化输出与 usage/timeout 观测；
3. 本地 embedding extension 的模型/revision/dimension/normalization/distance；
4. `EntityEdge.episodes` 在 dedup/update/invalidation 后的 semantic lineage 资格；
5. HaluMem session-local extraction 与 MemBench 100k missing timestamp；
6. 五格 dossier、machine plan、真实 smoke 与 artifact gate。

完整一手裁决见
[`graphiti-v0.29.3-source-product-m1-ruling.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-v0.29.3-source-product-m1-ruling.md)。
检查点状态只写入
[`graphiti-integration-ledger.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-integration-ledger.md)，
本页只承载已经架构师验收的稳定摘要。
