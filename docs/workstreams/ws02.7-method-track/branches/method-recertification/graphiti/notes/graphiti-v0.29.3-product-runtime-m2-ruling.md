# Graphiti v0.29.3 产品运行时 M2 裁决

日期：2026-08-09

状态：`READY_FOR_M3_ADAPTER_IMPLEMENTATION`

前置：[M1 source/product 裁决](./graphiti-v0.29.3-source-product-m1-ruling.md)

## 1. 总判词

Graphiti OSS v0.29.3 可以在不启动 HTTP host 的前提下进入 Phase 1：主轨直接调用公开
`Graphiti.add_episode()` 与 `Graphiti.search()`，运行在每个 conversation 独占的
FalkorDB Lite 文件上；build LLM 使用项目 runtime profile 选择的 OpenAI-compatible Chat
Completions，本地 embedding 通过公开 `EmbedderClient` extension point 注入锁定的
MiniLM。该组合是 `PRODUCT_EQUIVALENT + PRODUCT_SUPPORTED_CONFIGURATION`，不是 direct
graph insert，也不是 Zep hosted parity。

M2 同时锁死两条负边界：

1. Graphiti 的 `reference_time` 是必填 `datetime`。MemBench `100k` 的缺时间 noise 不得用
   question time、相邻 turn 或 wall clock 补造；该 method × variant 必须在 runtime/API 和
   output 建立前 fail-fast。
2. Graphiti 对传入的新 `uuid=` 会先按已有 episode 查询，而不是以该 UUID 新建。因此
   adapter 不向产品伪造 UUID；它读取返回的 product episode UUID，再以原子 sidecar 映射到
   public turn id。

## 2. 一手 product runtime

### 2.1 Direct core 与 embedded store

最窄真实链已在 Python 3.12 隔离环境实跑：

```text
AsyncFalkorDB(dbfilename)
  -> FalkorDriver(client)
  -> Graphiti(graph_driver=driver, llm_client=fake, embedder=fake)
  -> build_indices_and_constraints()
  -> add_episode()
  -> search()
  -> clear_data()
```

零 API 探针实际写入一个 `Episodic` node、检索零命中、清理后 node 数为零：

```text
GRAPHITI_M2_ZERO_API_PRODUCT_CHAIN_PASS {
  'llm_response_models': ['ExtractedEntities', 'ExtractedEdges'],
  'episode_uuid_shape': 36,
  'nodes_before_clear': 1,
  'nodes_after_clear': 0
}
```

`add_episode()` 本身串行 await extraction、resolution、embedding、DB save；成功返回就是该
episode 的业务完成门。官方 server 只是把相同调用放进无 per-message terminal id 的 queue，
因此本项目不启动 host。

### 2.2 FalkorDB Lite close 缺口

锁定依赖 `falkordblite==0.10.0` 的 async close 存在资源所有权缺口：driver close 后，底层
sync client 被标记为 async-managed，embedded Redis 进程可能未被清理。M2 验证过的窄 wrapper
收尾顺序为：

```python
async_client = lite.client
sync_client = async_client._sync_client
await driver.close()
sync_client._async_managed = False
sync_client._cleanup()
async_client._async_managed = True
```

实测 `before=True -> after=False`。这是 lifecycle wrapper，不改变 Graphiti 算法；adapter 测试
必须锁住成功 close、失败可见和幂等性，不能靠析构器碰运气。

### 2.3 并行与 ownership

- 一个 worker 进程只服务一个 provider；一个 provider 同时只激活一个 conversation；
- 每个 conversation 使用独占物理目录、FalkorDB 文件与固定 graph database/group id；
- conversation W2 由 framework 的 isolated provider 进程完成，不共享 embedded Redis、driver、
  Graphiti client 或 module-global search recipe；
- `supports_shared_instance_parallelism=false`，但 `allow_smoke_worker_override=true`。

Graphiti `search()` 会原地修改 module-global `EDGE_HYBRID_SEARCH_RRF.limit`。上述进程隔离使不同
conversation 不竞争该对象；同一 worker 的 JSON 请求仍严格串行。

## 3. Model 与观测身份

### 3.1 Build LLM

Graphiti 的 `OpenAIGenericClient` 是官方 OpenAI-compatible Chat Completions surface；DeepSeek
走 `structured_output_mode=json_object`，schema 注入 prompt；正式 OpenAI profile 可走
`json_schema`。两个 profile 的 model/provider/structured mode/max tokens/temperature 都进入
TOML 与 manifest/resume identity。

upstream client 丢弃 response usage，因此 worker 在传给 Graphiti 的 `AsyncOpenAI` endpoint
上做纯观测包装：每次实际成功 response 必须带精确 usage，按一次真实 HTTP response 记录
`prompt_tokens/completion_tokens`；不得从 prompt 字符估算 API token，也不得重复计算 Graphiti
的 tenacity 重试。OpenCodeGo 请求继续使用项目已验证的 `thinking=disabled` compatibility body。

### 3.2 Local embedding

MCP 文档声称支持 sentence-transformer，但 v0.29.3 factory 没有对应 case；这是一处 upstream
docs/code drift。主轨不调用不存在的 factory 配置，而是使用 Graphiti 公开
`EmbedderClient.create/create_batch` extension point，注入：

```text
models/all-MiniLM-L6-v2
dimension=384
normalize_embeddings=true
distance=FalkorDB cosine
```

worker 用模型 tokenizer 对真实输入做 truncation 后计 token，记录 build/retrieval embedding
次数、文本数、token 与 latency。默认 `search()` 不调用 cross encoder；注入 fail-fast sentinel，
一旦未来 recipe 漂移就停止而不是暗中产生 rerank。

## 4. 输入、时间与五格

主轨 `consume_granularity=turn`，每个 nonblank canonical event 恰好调用一次
`add_episode(source=message)`；不补 placeholder、不重排、不跨 session 配对。

| Benchmark | episode body | reference time | 身份 |
| --- | --- | --- | --- |
| LoCoMo | `speaker_name (user|assistant): content`；固定 metadata 中 speaker_a→user、speaker_b→assistant；共享 image wrapper | turn→session | framework extension |
| LongMemEval | 官方相同的 `role: content`、raw 顺序、逐 turn add | turn→本 session | official-compatible payload；完整 QA 仍 extension |
| MemBench 0-10k | `role: 原始 content`，保留尾部 place/time；caption 仍走共享 wrapper | 抽取的 turn time | framework extension |
| MemBench 100k | 不运行 | 缺失，禁止伪造 | method × variant N/A |
| BEAM | `role: content`，保留 orphan/mismatch 原序 | turn→本 session | framework extension |
| HaluMem | `role: content`，逐 turn add | turn→本 session | framework extension |

时间解析只接受 benchmark 已知格式并转为 timezone-aware UTC。非空但不可解析的 source time
fail-fast；没有时间则只在 MemBench 100k 由通用 variant gate 预先拒绝，不能落到运行时猜测。
question time 永不进入 ingest。

图片从 event 的 `original_content + turn_images` 重建，统一产生
`[Sharing image that shows: ...]`；不把 locator/query 暴露给 method，也不重复 event_stream
的旧 `(image description:)` 文本。

## 5. Lineage、排序与 readout

Graphiti 的 `EntityEdge.episodes` 是 fact edge 的 source episode 集合。current resolution code 在
new edge、exact duplicate 与 LLM duplicate 三条仍表示同一 fact 的路径上，把当前 episode UUID
加入 resolved edge；invalidated old edge 不会被当作当前新 fact 的命中。由此 M2 裁定：

- retrieval `semantic_provenance=valid/turn`；每个 edge 的全部 episode UUID 必须逐个命中
  atomic sidecar，转换为去重保序的 public turn ids，未知 UUID fail-fast；
- 默认 product search 返回的 edge 顺序就是 RRF rank，`stable_ranking=valid`；Graphiti 不公开
  可校准 RRF score，因此 `RetrievedItem.score=None`，绝不伪造分数；
- formatted memory 按 product rank 包含 fact、`valid_at/invalid_at/reference_time`，不把 private
  gold 或 source ids 写进答题 prose；zero-hit 使用稳定 sentinel；
- retrieval 必须只读，测试以 graph node/edge/episode 状态前后相同锁住。

## 6. HaluMem operation 资格

adapter 在 sidecar 中保存每个 session 的 product episode UUID，以及该 session ingest 返回的
edge UUID 首次出现顺序。`end_session()` 重新读取这些 edge 的 current state，只报告：

1. 当前仍 active（`invalid_at is None` 且 `expired_at is None`）；
2. `episodes` 与当前 session episode UUID 有交集；
3. 按 first-seen edge UUID 去重保序。

这使 extraction 报告只覆盖当前 session 的 current fact，既不把前 session 的旧 fact 混入，
也不把同 session 后续已 invalidated 的旧版本当新 memory。资格裁定：

- extraction：`valid`（session-local current edge observation）；
- update：`valid`（产品 `search()` 可做公开 probe，top-k 由 query 传入）；
- QA：`valid`；
- memory type：`valid`。这里的 evaluator 是按 gold memory point 自带的
  Event/Persona/Relationship 类别，对 extraction/update 已有 score 做分组汇总；它不要求
  Graphiti 自己预测 memory type。M2 初稿把“method 不输出分类”误当成指标 N/A，现更正。

统一 profile 的 `query_limit=20` 是容量上限而非每次强取 20：普通 QA、Recall 与 update probe
仍传各自的 `query.top_k`（当前多为 10），HaluMem QA 的既有契约传 20。若把 profile 锁成 10，
会在 HaluMem QA 静默截断或错误拒绝，因此 M3 已用 operation runner 强反例锁死 20 上限与逐请求
真实 top-k。

## 7. Failure、resume 与 clean retry

worker sidecar 是算法外纯观测/恢复层，原子记录：operation id + input digest、product episode
UUID→turn id、session episode ids 与 edge first-seen order。提交顺序固定为：

```text
await add_episode success -> validate result -> atomically commit sidecar -> reply success
```

若进程在 product write 与 sidecar commit 之间失联，下一次启动时 DB episode 集合与 sidecar
不一致，必须 fail-fast；runner 的 failed-conversation clean hook 用 **state root 外置** cleanup
marker 连接 `live root → 固定 tombstone → deleted`，任一阶段中断都从 marker 续删。每个
conversation 独占整个物理 DB root，因此不另做一遍 product `clear_data()`；关闭 embedded
runtime 后原子改名并递归删除整个 root，才是等价且可审计的物理清空。禁止在不确定写入结果时
重放单 turn。

同 operation id + 同 digest 是幂等读取；同 id + 不同 digest fail-fast。normal cleanup 只 exact
close、保留 DB/sidecar 供 artifact 与 resume；failed clean 才物理删除。telemetry 在 worker import
Graphiti 前强制 `GRAPHITI_TELEMETRY_ENABLED=false`，secret/base URL 不进 manifest、sidecar、日志。

## 8. M2 判词

```text
READY_FOR_GRAPHITI_M3_ADAPTER_IMPLEMENTATION(
  direct add_episode/search product chain is runnable on FalkorDB Lite;
  local MiniLM is a public extension-point configuration;
  source time, lineage, stable rank and HaluMem boundaries are decided;
  MemBench 100k must fail before runtime without timestamp fabrication;
  worker isolation, journal and exact cleanup are mandatory implementation gates
)
```

本裁决写成时 Graphiti 尚未获得独立真实 API smoke 批准；2026-08-09 用户随后已明确批准，且
指定使用 `.env` 的 OpenCodeGo smoke profile。M3 仍必须先完成离线门和 machine plan，真实
调用只能逐字执行 planner 产出的命令。
