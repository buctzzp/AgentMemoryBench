# Graphiti v0.29.3 source / product identity M1 裁决

日期：2026-08-09
状态：`READY_FOR_M2_PRODUCT_RUNTIME_AUDIT`
范围：替换 Phase 1 method 槽位、锁 current stable source/product/official harness；不实现 adapter、
不安装 runtime、不调用模型 API。

## 1. 总判词

Supermemory 的 stable self-host runtime 只有预编译 executable，公开仓库没有可审计的
server/engine source；用户因此批准用 Graphiti 接替该槽位。Graphiti 的 public repository 提供
完整 `graphiti_core/`、FastAPI `server/`、MCP server、tests/examples 与 Apache-2.0 license，
通过 local OSS source gate。

但名称必须严格区分：

```text
Phase 1 method = Graphiti OSS
Phase 1 method != Zep hosted product
Graphiti result != Zep parity/result
```

upstream 自己也把二者分开：Graphiti 是开源 temporal context graph engine、自行提供 graph DB
与 user/conversation management；Zep 是托管基础设施并使用 proprietary Context Graph Engine
（`third_party/methods/graphiti/README.md:86-122`）。

## 2. Source lock

| 项 | 锁定值 |
| --- | --- |
| upstream | `https://github.com/getzep/graphiti.git` |
| vendored path | `third_party/methods/graphiti` |
| latest stable | `v0.29.3` |
| stable commit | `021d3a57d511f21b10adaf7fa923bd5c1fce5e9d` |
| remote main（2026-08-09） | `425bf2481b51437e43455e09d241c5f46e3d95f3` |
| license | Apache-2.0 |
| package | `graphiti-core==0.29.3`；Python `>=3.10,<4` |

GitHub 把 v0.29.3 标为 latest immutable release；release commit 与 vendored detached HEAD
逐字一致。main 可继续前进，但主轨不追 prerelease/main 漂移；新 stable、source security fix、
public API 或算法默认变化才重开 M1。

`scripts/fetch_third_party_methods.sh` 已从 Supermemory pin 改为上述 Graphiti pin；
`third_party/methods/MANIFEST.md` 同步声明 Graphiti/Zep 身份边界。Supermemory 的旧 M1 note 继续
保留为 source-gate 历史，不再由 fetch 脚本恢复。

## 3. Product surface

### 3.1 通用写入接口

`Graphiti.add_episode(...)` 是 current core 的公开产品入口
（`graphiti_core/graphiti.py:980-1224`）：

- 必填 `name`、`episode_body`、`source_description`、`reference_time`；
- `source=EpisodeType.message` 明确要求 body 使用 actor/role + content 语义；
- `group_id` 是 graph partition；`uuid` 可由调用者固定 source episode identity；
- 返回 `AddEpisodeResults`，包括原始 `episode`、episodic edges、resolved nodes/entity edges；
- 官方 docstring 要求 episodes sequentially add 且逐次 await，不能并发写同一时间线。

这不是把 raw 数据直塞图数据库：函数执行 extraction、dedup、temporal edge resolution、
embedding 与 invalidation，是算法本体。

### 3.2 通用检索接口

`Graphiti.search(query, group_ids, num_results, ...) -> list[EntityEdge]`
（`graphiti_core/graphiti.py:1527-1591`）是公开 out-of-box hybrid search。默认 recipe 为 edge
BM25 + cosine + reciprocal-rank fusion，返回有序 fact edges；每条 edge 含 `fact`、时间窗、
`episodes: list[str]` source episode ids（`graphiti_core/edges.py:263-287`）。

高级 `search_()` 可跨 nodes/edges/episodes/communities 和 cross-encoder，但它不是默认简单
product search。Phase 1 主轨先以 `search()` 为候选，避免暗中换成更贵的高级 recipe；M2 必须
锁定 limit、排序稳定性、zero-hit 与 episode lineage 语义后才能裁 metric 资格。

### 3.3 为什么 direct core，而不是启动 host

官方 FastAPI `/messages` 只是把每条 request message 排入进程内 queue，再调用同一个
`graphiti.add_episode()`（`server/graph_service/routers/ingest.py:52-69`）；`/search` 也直接调用
`graphiti.search()`（`server/graph_service/routers/retrieve.py:18-26`）。HTTP 并不增加算法。

相反，`/messages` 返回 202 后没有 per-message terminal id；worker shutdown 会取消 task，再把
未处理 queue 取出，不能为 benchmark 提供 exact completion。direct core 逐条 await 同一产品
方法，既保持算法，又让失败/完成可见。因此分类为：

```text
DIRECT_CORE = PRODUCT_EQUIVALENT
FASTAPI_HOST = transport wrapper with weaker completion contract
```

不得绕过 `add_episode()` 直接创建 node/edge；那才是 mechanism bypass。

## 4. Official benchmark/harness matrix

current stable tree 对 Phase 1 名称的源码普查只找到一份 LongMemEval 入口：
`tests/evals/eval_e2e_graph_building.py`。LoCoMo、HaluMem、BEAM、MemBench 均无 current official
harness。

### 4.1 LongMemEval current harness

`build_subgraph()` 按原 session/turn 顺序遍历，每个 message 一次 `add_episode()`：

```python
episode_body = f'{msg["role"]}: {msg["content"]}'
reference_time = session_date
source = EpisodeType.message
group_id = user_id + '_' + group_id_suffix
```

同一 user 内顺序 await，不补 placeholder、不重配 assistant-first/连续同 role/singleton；多个 user
才由 `semaphore_gather` 并行（`tests/evals/eval_e2e_graph_building.py:32-100`）。这为 Graphiti ×
LongMemEval 的 turn episode payload 提供 official parity anchor。

但该文件**不是完整 LongMemEval QA/retrieval evaluator**。它将 candidate `AddEpisodeResults` 与
预先用 `gpt-4.1-mini` 建的 baseline graph 交给 LLM 判断 candidate 是否更差，没有执行
question search、answer builder、LongMemEval judge 或 NDCG。因此：

- 主配置可采用官方 turn payload；
- 不得宣称复现了 Graphiti/LongMemEval 论文分数；
- 若未来保留作者 build model/graph-quality evaluator，只能另建稀疏
  `author_longmemeval`，不混入主表。

### 4.2 其余四格

| benchmark | current official coverage | Phase 1 分类 |
| --- | --- | --- |
| LoCoMo | 无；podcast example 仅提供 speaker+role+timestamp product 用法 | framework extension |
| LongMemEval | turn-level graph-build quality harness；无 QA/search parity | main payload official-compatible；完整评测仍为 framework extension |
| HaluMem | 无 | framework extension |
| BEAM | 无 | framework extension |
| MemBench | 无 | framework extension |

README 的 Zep paper/blog 宣传不是 Graphiti current benchmark harness，不能用来补空格。

## 5. Runtime/config 一手边界

### 5.1 数据库

core 支持 Neo4j、FalkorDB、Neptune；Kuzu 已 deprecated。v0.29.3 明确支持
`graphiti-core[falkordblite]`，官方 podcast/quickstart 用
`AsyncFalkorDB(dbfilename=...) → FalkorDriver → Graphiti`，可提供不启动 HTTP host 的本地
文件型 product runtime。

M2 候选是每 worker 独占 FalkorDB Lite 文件；每 conversation 用独占 group/database。必须先
实证：group clone、search、clear/close、crash retry、W2 ownership 与残留文件清理，不能仅因
example 能启动就盖章。

### 5.2 Build LLM

core 默认 `OpenAIClient` 使用 OpenAI-specific Responses structured parse；current README 明确
要求 OpenAI-compatible endpoint 使用 `OpenAIGenericClient`。DeepSeek 等 provider 可能不支持
`json_schema`，官方提供 `structured_output_mode='json_object'`，把 schema 注入 prompt。

因此 `smoke` 候选为项目已锁的 `opencodego/deepseek-v4-flash + Chat Completions +
json_object`；`official_full` 候选为 `primary/gpt-4o-mini`。两者属于 runtime profile 差异，
不是 Graphiti 算法参数调优；仍须进入 TOML/manifest/resume。

### 5.3 Embedding 与 reranker 缺口

Graphiti core 默认 `OpenAIEmbedder(text-embedding-3-small)`，默认截取维度来自
`EMBEDDING_DIM=1024`。默认 `search()` 需要 query embedding，但只用 RRF，不调用
cross-encoder。

current MCP README 宣称 `sentence_transformers/all-MiniLM-L6-v2` 是 local 推荐；然而
v0.29.3 的 `EmbedderFactory.create()` 实际只有 openai/azure/gemini/voyage，根本没有
`sentence_transformers` case（`mcp_server/README.md:176-194` 对比
`mcp_server/src/services/factories.py:301-411`）。这是 upstream 文档/实现漂移，不能照 README
写一个不存在的配置。

M2 必须二选一并实证：

1. 通过公开 `EmbedderClient` extension point 注入项目锁定的本地 MiniLM，并显式分类为
   product-supported framework configuration；或
2. 使用有可用 endpoint 的公开 OpenAI-compatible embedding model，并单独获得预算授权。

当前不假定 OpenCodeGo 提供 embeddings endpoint，也不为省钱静默改模型。默认 `search()` 不用
cross-encoder；M2 应注入 fail-fast unused sentinel，防未来 recipe 漂移后暗中产生 rerank API。

## 6. 五格初步输入裁决（M2 必须用强反例再锁）

- 原生单位是单 episode/message，主 `consume_granularity=turn`；不为 user/assistant 配对补
  placeholder。
- LoCoMo：body 必须保留 speaker name + canonical role + content + shared image caption，
  reference time 用 turn→session；podcast example 的 `speaker_name (role): content` 是产品锚。
- LongMemEval：严格复用 official turn payload与原序；同 session timestamp 相同合法。
- MemBench：content 保留原尾部 place/time，结构化 reference time 另填提取值；不得删原文。
  100k 的 missing-time noise 与 `reference_time: datetime` 必填冲突，目前标
  `PENDING_METHOD_VARIANT`，禁止用 wall clock/question/邻居时间伪造。
- BEAM/HaluMem：canonical role/content 原序，turn time 缺失时只回落本 session time；不按 raw
  id 重排。

## 7. Metric 初判（不是最终资格）

- `search()` 返回有序 fact edges，stable ranking 是可验证候选；
- edge 的 `episodes` 是 public source lineage 候选，但必须确认 dedup/update/invalidation 后，
  当前 fact 与 episode ids 仍满足 semantic lineage，而不是只证明“参与过生成”；
- 若 lineage 成立，可把一个 edge 映射到多个 source turn id，按 Gold Evidence Group 计分；
- HaluMem extraction 可观察 `AddEpisodeResults.edges` 的 session-local 聚合候选，必须确认其中
  existing/resolved/invalidated edge 的语义；update/QA 是 valid 候选；memory-type 暂 N/A 候选。

在 M2 关闭上述语义前，Recall/NDCG/extraction 一律 `pending`，不先写“Graphiti 天然支持”。

## 8. M1 判词

```text
READY_FOR_GRAPHITI_M2_PRODUCT_RUNTIME_AUDIT(
  Graphiti v0.29.3 is complete Apache-2.0 source and replaces Supermemory;
  Graphiti is not Zep and carries no Zep parity claim;
  direct add_episode/search is the product-equivalent surface;
  only LongMemEval has a current official turn-ingest anchor;
  FalkorDB Lite, embedding, completion, lineage and missing-time semantics remain M2 gates
)
```
