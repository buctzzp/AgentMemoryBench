# LangMem 接入说明

状态：`method-frozen-v1`。本页只保存
跨会话仍需复用的稳定接口事实；逐格状态与下一动作见
[LangMem integration ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/langmem/notes/langmem-integration-ledger.md)，
五格异常与 payload 见
[安全档案](../../workstreams/ws02.7-method-track/branches/method-recertification/langmem/notes/langmem-five-benchmark-safety-dossier.md)。

## Current source 与官方覆盖

- 官方来源：`langchain-ai/langmem`，current vendored commit
  `56d85939d80bb731bd5e237567148d817d7bfd16`，包版本 `0.0.30`，MIT。
- current repo 对 LoCoMo、LongMemEval、MemBench、BEAM、HaluMem 均无官方 harness；五格
  统一是 framework extension，当前不存在 author benchmark profile。
- 完整一手命令、source hash 与差异裁决见
  [M1 ruling](../../workstreams/ws02.7-method-track/branches/method-recertification/langmem/notes/langmem-current-product-identity-m1-ruling.md)。
- ws05.1 M11 已把本地 MiniLM 的 bytes/tokenizer/pipeline/runtime 锁进 run identity v2，并以
  31-file `langmem-main-v2` 组件闭包覆盖 product、package/lock、adapter/worker/transport/bootstrap。
  新 run 必须 fresh-state，旧 artifact 不改写；完整收据见
  [M11 implementation](../../workstreams/ws05.1-method-profile-provenance/notes/m11-effective-config-source-embedding-implementation.md)。

## 机制与配置 provenance（2026-08-25）

- 在 official repo、README、docs、package metadata 与精确关键词检索边界内，没有找到一篇可与
  current package 对齐的 LangMem method paper；机制最高证据是官方 conceptual guide、quickstart、
  public factory 与匹配 commit 的实现。五个 Phase 1 benchmark 也都没有公开的完整
  build/search/answer/judge harness，因此 author builder 是 `N/A_BY_PRODUCT_SCOPE`，不是看到目录里
  缺文件后凭空补一个模板。
- public `create_memory_store_manager()` 的 effective 主流程是 background collection manager：
  insert 开、内部 update 默认开、delete 关、`query_model=None`、`query_limit=5`、`max_steps=1`、
  `phases=[]`。update 没有 store-manager 顶层开关，但会继承 lower-level manager 的
  `enable_updates=True`；不能因 TOML 没有 `enable_updates` 就误判为未启用。
- `query_limit=5` 同时限制 old-memory candidate，并在 `query_model=None` 时通过
  `query_limit // 4` 决定指数窗口数量；当前值实际只用 session 最后一条 message 生成 old-memory
  search query，完整 session 仍进入 enrichment LLM。它是承重算法参数，不是普通 readout top-k。
- `max_steps=1` 允许一次 structured multi-tool call；大于 1 才进入额外精炼回合。`phases=[]` 只表示
  没有第二轮自定义 phase，不会关闭第一轮自带的 compare/update/consolidate。conceptual guide 提到
  importance/strength/recency/frequency，但 current main 没有一套对应的 concrete ranking scorer，不能
  把设计指导写成现行算法。
- current remote 相对 vendored pin 的四个 commit 只改 `uv.lock`，产品 Python/README/docs/package
  metadata 未变；这仍是 runtime dependency drift，升级留横向实施批次，不把旧 artifact 重标。
- 第三方 MemoryData 选择逐 message 调 manager、delete 开、时间强制写入内容，目标是统一 layer API、
  逐调用归因和可消融配置；其 Python schema 默认 MiniLM384/GPT-4o-mini/query-limit5，实际 checked-in
  JSON 又覆盖成 OpenAI 1536/GPT-4.1-mini/query-limit40。它的优势是控制面清晰，代价是更多调用且
  manager 看不到完整 session context。framework 主轨选择官方 delayed-processing 的 session context
  与 public delete=false，两者服务不同 estimand，不能用“与我们不一致”直接否定前者，也不能只读
  schema default 后误报第三方框架的 effective 参数。

完整算法图、参数矩阵、搜索边界与第三方方案比较见
[M8 provenance note](../../workstreams/ws05.1-method-profile-provenance/notes/langmem-profile-provenance.md)。

## 产品 surface

- 主轨：官方 `create_memory_store_manager()` 的 async `ainvoke()`，每个 canonical session
  一次；retrieve 用同一 manager 的 `asearch()`，framework reader 独立答题。
- hot-path react agent 是会混入 agent tool policy 的算法变体；direct `BaseStore.put(raw
  turn)` 会绕过 extraction/update，均不进主轨。
- 主轨保留 public factory 默认：unstructured `Memory(content)`、insert/update 开、delete
  关、`query_model=None`、`query_limit=5`。current sync `invoke()` 会重复执行 old-memory
  search，故锁无此 bug 的 async surface。
- LangMem message contract 不要求 user-first、交替或偶数；assistant-first、same-role、
  singleton、odd tail 均合法，所以不补 placeholder。

## 产品接口契约（参数、返回与批次）

跨 method 粒度矩阵见
[`../method-interface-inventory.md`](../method-interface-inventory.md)。LangMem 五格统一接收
`SessionBatch`；整个非空 session 映射成**一次** manager transaction，其中
`messages: list[dict[str, str]]` 每项只有 `role/content`，保持 canonical 原序。

### 写入

```python
MemoryStoreManager.ainvoke(
    input={
        "messages": list[dict[str, str]],
        "max_steps": int,
    },
    config={
        "configurable": {"langgraph_user_id": str},
        "callbacks": list[BaseCallbackHandler],
    },
) -> list[dict[str, Any]]
```

主轨 manager 由 `create_memory_store_manager(...)` 构造，namespace template 是
`("memories", "{langgraph_user_id}")`。产品返回 list 中每个 changed item 必须是 dict 且有
`key: str`；它表示本次 insert/update 后发生变化的 current memory，不是逐 source-turn 回声。
worker 随后读取 exact store snapshot，并向 adapter 返回
`changed_memory_keys: list[str]`、与这些 key 同序的
`changed_memories: list[{key: str, value: dict}]`、`memory_count: int`、
`reused_operation: bool`、LLM/embedding observation list 与 rehydration counts；adapter
映射为 `IngestResult.metadata`。`changed_memories` 是事务提交后的真实 current product value，
不是 source turn 回显，也是 HaluMem session report 的唯一输入。

### 检索

```python
MemoryStoreManager.asearch(
    *,
    query: str,
    limit: int,
    config={"configurable": {"langgraph_user_id": str}},
) -> list[StoreItem]
```

每个 `StoreItem` 至少消费 `key: str`、`value: Memory | dict`、`score: float | None`。worker
归一为 `list[{key: str, content: str, kind: str, score: float | None}]`，另返回
`latency_ms: float` 与 embedding observations；adapter 不重排，生成
`tuple[RetrievedItem, ...]` 和 `formatted_memory`。

这里两处 list 含义不同：ingest list 是一个 session 的原始 message 容器，retrieve list 是
evolved current memory 的 ranked result。后者有稳定 key/score/order，却没有 lossless
source semantic mapping，因此 stable ranking=valid 与 provenance=N/A 必须分开声明。

## Runtime 与状态

- framework 主进程不导入 LangMem/LangChain 依赖；每个 provider 独占一个 Python 3.12
  JSON-lines worker。worker 内才创建真实 `ChatOpenAI`、本地
  `SentenceTransformer`、官方 `InMemoryStore` 与 background manager。
- `scripts/bootstrap_langmem_runtime.sh` 先按 vendored `uv.lock` 执行 `uv sync --frozen`，
  再安装 `scripts/requirements/langmem-runtime.txt` 的本地 embedding 补充栈；source identity
  同时锁 current commit、9 个 product 文件、`uv.lock`、adapter、worker、bootstrap 和补充 lock。
- 一个 canonical session 一次 `ainvoke()`；其返回即 insert/update/delete 全部 await 完成。
  `opencodego` smoke 强制 Chat Completions 且关闭 thinking；`primary` official_full 保持
  provider 默认 Chat Completions。每次成功 response 必须提供精确 usage，缺失即失败。
- 一个 worker 内多个 conversation 用 `("memories", namespace_id)` 逻辑隔离；W2 由 generic
  isolated runner 建两个独立 provider/worker/model/store/state root，不共享 tokenizer。
- `InMemoryStore` 的 exact key/value/插入顺序与 completed operation journal 原子写入同一
  namespace JSON。相同 operation/result-loss retry 不重跑算法；同 operation id 配不同输入
  fail-fast；manager 或持久化失败先恢复调用前 store。
- failed-ingest clean 把 active state 原子移到 cleanup tombstone，再只删目标 namespace；删除
  中断可重试，复核为空后才删除 tombstone。secret 只经 allowlist worker 环境传递，不进
  manifest/state/error。

## 五格公共输入

- `consume_granularity=session`；一个 canonical 非空 turn 对应一个 LangChain
  `role/content` message，保持原序，不补 placeholder、不跨 session 重配。
- source time 只按 `turn → 当前 session → None` 渲染；question time、兄弟 turn 与 wall clock
  永不回填。MemBench 原文已含 time/place 时保留原文且不重复 header；100k noise 保持无时间。
- LoCoMo 固定 `speaker_a→user / speaker_b→assistant`，content 保留真实 speaker name；image
  caption 统一使用 `[Sharing image that shows: ...]`，path/query/locator 不可达算法。
- LongMemEval 的 assistant-first、连续同 role、singleton/odd tail，BEAM 10M orphan/mismatch，
  MemBench ThirdAgent user-only 都按 canonical 原序传入；不为“看起来像标准对话”制造假回复。
- HaluMem 每 session 一次 `ainvoke()`；成功事务返回的 changed keys 必须在同一次完整 store
  snapshot 中逐一存在，adapter 才在 session 边界报告对应 current values。结果丢失重放读取
  completed operation journal 中同一份快照，不重新运行算法。当前 evolved state 同时供 update
  probe 与 QA 检索。

## Metric 边界

- current memories 会被 LLM update/consolidate；source id 只能证明参与生成，不能证明当前
  content 的 semantic lineage。Recall/Precision/F1@k 与 NDCG 均 N/A。
- `MemoryStoreManager.asearch(query, limit)` 的原始 key/content/score/order 完整保留；
  state 快照按插入顺序恢复，Python stable sort 在同分时保持候选顺序。因此 product ranking
  assertion 为 `valid`，但 semantic provenance 仍为 `N/A`，不能据此计算 source-qrel 指标。
- 五格 Recall/Precision/F1@k 与 LongMemEval NDCG 均 N/A；这是 evolved memory 的语义映射
  不可证，不是 LangMem 没有检索接口。
- HaluMem extraction 为 valid：报告单元是本次 `ainvoke()` 实际 insert/update 后发生变化的
  current product memory；融合旧 memory 是 LangMem 的更新语义，并不等于跨 session 多报未变化
  单元。update/QA 与依赖 extraction 的 memory-type 也具备 evaluator 资格。该资格不外推为
  source-turn Recall：changed memory 仍不具备 lossless source semantic lineage。

## 配置与 answer/judge

- `configs/methods/langmem.toml` 只有一个 `[method]`，保存算法参数；API runtime、execution 与
  benchmark evaluation 已由各自配置层组合。五格固定 MiniLM-384 normalized、`query_limit=5`、
  `max_steps=1`、insert/update 开、delete 关。官方五格 harness 集为空，故没有伪造
  `author_*` section。
- LangMem 只构建和检索 memory；answer/judge 全部走 benchmark-scoped framework builder，
  gold answer/evidence/target/memory-point label 不进入 worker payload。
- zero hit 返回空 `items=()` 加非空 sentinel；backend/协议失败一律抛错，不降级成空记忆。

## 当前冻结边界

原 product-v1 的 M1/M2 与 B11 已全部闭合，冻结证书见
[LangMem method-frozen-v1](../../workstreams/ws02.7-method-track/branches/method-recertification/langmem/notes/langmem-frozen-v1.md)：
20 份 current run、47 个 conversation/question、9 个 croppable variant 的真实 W1/W2、2 个
HaluMem 历史 fixed-shape W1 以及 artifact/效率/隐私/state 机器门均通过；2026-08-25 后
operation runner 的并行轴已改为 UUID，W1 不再是 current 能力上限。任何 current source/`uv.lock`、
manager factory、store/ranking、message/time policy、wrapper identity 或 benchmark stable contract
的实质漂移，都必须重开 ledger 对应门；lock-only upstream drift 先做影响审计，不机械重烧。

2026-08-24 的 `langmem-background-product-v2` 只增加 completed-operation current-value 快照、
HaluMem session report 与 retrieval callback 守门；零 API 强反例已闭合，但旧 v1 真实 artifact
不能重标为 v2。下一次真实 pilot/smoke 必须使用新 run id 全量重建该 run 的 method state。
