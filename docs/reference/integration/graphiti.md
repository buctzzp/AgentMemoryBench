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
| embedding | local `models/all-MiniLM-L6-v2`，384 维、模型 pipeline + 显式 L2、cosine |

Graphiti 于 2026-08-09 经用户裁定接替 source-unavailable 的 Supermemory。2026-08-25 再核远端：
`v0.29.3` 仍是最新稳定 release，current `main=993e081a6d7948a0d8851c12a5fbdbeb49fed862`，
相对 stable 为 25 commits / 11 files；`v0.30.0` 仍只有 prerelease。current main 不机械混入 pin。
Supermemory 旧 blocked note
保留为 source-gate 判例，但不再占 Phase 1 第十格。

官方 README 指向的论文是
[`Zep: A Temporal Knowledge Graph Architecture for Agent Memory`](https://arxiv.org/abs/2501.13956)，
其机制材料可用于理解 Graphiti core，但论文实验通过 hosted Zep API、BGE-m3 与 nodes+edges context
运行，不能当成 Graphiti OSS v0.29.3 的 author 数字。完整四身份与参数证据见
[M10 provenance](../../workstreams/ws05.1-method-profile-provenance/notes/graphiti-profile-provenance.md)。

ws05.1 M11 已把本地模型 bytes/tokenizer/pipeline/runtime 锁进 run identity v2，并以 165-file
`graphiti-oss-main-v2` 组件闭包替代旧 11-file source lock，覆盖完整 `graphiti_core`、lock、adapter/
worker/transport/bootstrap。新 run 必须 fresh-state，旧 artifact 不改写；author profile 仍因 hosted
Zep 与 OSS/current payload 身份不等价而不注册。完整收据见
[M11 implementation](../../workstreams/ws05.1-method-profile-provenance/notes/m11-effective-config-source-embedding-implementation.md)。

## 产品与配置

- ingest：每个 nonblank canonical turn 一次 `add_episode(source=message)`，逐条 await；
- retrieve：默认 edge BM25 + cosine + RRF；返回有序 EntityEdge fact 与 temporal validity；
- runtime：不启动 HTTP host，独立 Python 3.12 worker 直调与官方 server 相同的 core；
- smoke：`.env` 的 `opencodego/ox-alpha-free`，Chat Completions + `json_object` +
  `reasoning_effort=low`，成功 response 必须带 exact usage；
- official_full：`primary/gpt-4o-mini` + `json_schema`；
- cross encoder：主 search 不调用；官方基类 sentinel 一旦被调用即 fail-fast；
- cleanup：root 外 marker → 固定 tombstone → resumable rmtree，embedded Redis 必须 exact stop；
  shutdown 未确认后 runtime 永久 fail-closed。

Graphiti README 声称默认 `SEMAPHORE_LIMIT=10`，v0.29.3 `helpers.py` 实际默认是 20；framework
显式 `max_coroutines=10`，所以有效值稳定，但它是显式 framework 值，不是“沿 source default”。
Zep paper build context 写最近 4 条 messages，v0.29.3 source 的 `RELEVANT_SCHEMA_LIMIT` 是 10；main
沿 current source 10，不把 paper 值倒灌进 current product。

current stable repo 只含 LongMemEval graph-building eval：逐 message `role: content`、session date、
单 user group。它没有完整 question search/answer/judge，而且其 `candidate_is_worse` 字段描述、
自然语言 prompt 与 scorer polarity 互相矛盾，因此只提供 ingest payload/topology anchor，不提供可直接
采用的 graph-quality 分数；LoCoMo、
HaluMem、BEAM、MemBench 都是 framework extension。Graphiti OSS 也不等于 Zep cloud 产品。

同 owner `getzep/zep-papers` 的 LoCoMo/LME pipeline 是 hosted Zep external provenance：它使用
nodes RRF + edges cross-encoder、top-20、Zep context constructor 和 method-owned answer/judge。该设计
面向作者产品效果，和本项目受控 edge-only basic RRF 回答不同实验问题；不因不同而判错，也不把它
注册为 Graphiti OSS `author_*`。

## 产品接口契约（参数、返回与批次）

跨 method 粒度矩阵见
[`../method-interface-inventory.md`](../method-interface-inventory.md)。Graphiti 五格均为
`consume_granularity="turn"`；产品入口不是 list batch，每个有可见 content 且有 source time
的 canonical turn 恰好一次 `add_episode()`。

### 写入

```python
await Graphiti.add_episode(
    name: str,
    episode_body: str,
    source_description: str,
    reference_time: datetime,
    source: EpisodeType = EpisodeType.message,
    group_id: str | None = None,
    uuid: str | None = None,
    update_communities: bool = False,
    ...,
) -> AddEpisodeResults
```

adapter 传 `name=turn_id`、`episode_body="speaker/role: rendered content"`、固定公开
source description、timezone-aware source time、`source=message`、conversation 物理库内固定
group，且关闭 communities。worker 从 `AddEpisodeResults.episode.uuid: str` 与
`edges: list[EntityEdge]` 提取本 episode 新解析的 edge ids，返回
`episode_uuid: str`、`edge_count: int`、`reused_operation: bool` 与 LLM/embedding
observations；adapter 映射为 `IngestResult.metadata` 并保存 episode→turn sidecar。

### 检索

```python
await Graphiti.search(
    query: str,
    center_node_uuid: str | None = None,
    group_ids: list[str] | None = None,
    num_results: int = DEFAULT_SEARCH_LIMIT,
    search_filter: SearchFilters | None = None,
    driver: GraphDriver | None = None,
) -> list[EntityEdge]
```

主轨传 `query=query.query_text`、当前 group、`num_results=query.top_k`，保留默认 edge
BM25+cosine+RRF。每个 `EntityEdge` 消费 `uuid/fact/score/valid_at/invalid_at/episodes`；worker
用 episodes 精确反查 source turn ids，返回 `items: list[dict]`、`latency_ms: float` 与 embedding
observations。adapter 不重排，生成 `tuple[RetrievedItem, ...]`、完整 `formatted_memory` 与
valid/turn provenance。Graphiti 没有消息 list 或偶数约束，不配 pair、不造 placeholder；
MemBench 100k 缺 source time 时在产品调用前 fail-fast。

## 五格资格

| Benchmark | 输入与异常边界 | Retrieval metric | 运行状态 |
| --- | --- | --- | --- |
| LoCoMo | speaker_a→user、speaker_b→assistant；真实 speaker 前缀；caption wrapper；逐 turn time | provenance valid/turn；rank valid | W1/W2 live passed |
| LongMemEval | raw role/order；逐 turn；不配对、不补 placeholder | provenance valid/turn；rank valid | S/M W1/W2 live passed |
| MemBench 0-10k | First/Third canonical turn；原文 place/time 保留，typed time 另传 | provenance valid/turn；rank valid | W1/W2 live passed |
| MemBench 100k | source time 可能缺失，Graphiti reference_time 必填 | N/A；禁止造时 | pre-runtime rejected |
| BEAM | 四 variant 原序；10M orphan/mismatch 不位置配对 | provenance valid/turn；rank valid | 四 variant W1/W2 live passed |
| HaluMem | 逐 turn add；session-local current active edge report | extraction/update/QA/memory-type valid | Medium/Long 历史 fixed-shape W1 passed；current runner 可按 UUID 并行 |

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
