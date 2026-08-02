# LangMem background-manager product adapter M2 实现记录

日期：2026-08-02
状态：`READY_FOR_B11_REAL_SMOKE_APPROVAL`
adapter：`langmem-background-product-v1`

## 1. 结论

LangMem current product surface 已实现为 provider v3：每个 canonical session 经独立 Python
worker 调用官方 `create_memory_store_manager().ainvoke()`，答题前调用同一
`MemoryStoreManager.asearch()`。framework 没有启动 HTTP host、没有让 React answer agent
决定是否记忆，也没有用 `BaseStore.put(raw turn)` 绕过 extraction/update。

当前结论是“离线接线完整，可申请 B11 真实 smoke”，不是 frozen。真实 build/answer/judge
API、artifact 开箱和最终冻结仍在用户预算批准门之后。

## 2. 主调用图

```text
generic / operation-level runner
  └─ LangMem.prepare()                         有工作项时每 provider 一次
      └─ LangMemRuntime.ensure_started()
          ├─ source-locked Python 3.12 worker
          ├─ local SentenceTransformer MiniLM-384 normalized
          ├─ official LangGraph InMemoryStore(index=embedding)
          ├─ ChatOpenAI(Chat Completions)
          └─ create_memory_store_manager(
               insert=true, delete=false, query_model=None, query_limit=5)

SessionBatch ingest
  ├─ canonical events → role/content messages
  ├─ namespace_id + deterministic operation_id
  ├─ restore exact state when needed
  ├─ await manager.ainvoke(messages, max_steps=1)
  ├─ snapshot exact store key/value/order
  └─ atomic state + completed-operation journal commit

RetrievalQuery
  └─ manager.asearch(query, limit)
      └─ product key/content/score/order → RetrievedItem → formatted_memory

failed retry / cleanup
  └─ active state → cleanup tombstone → namespace-only delete → empty check

provider.cleanup()
  └─ worker shutdown；成功后才提交 provider cleaned
```

worker 的 stdio JSON-lines 是本机依赖隔离协议，不是第二套算法服务。第三方 imports 与模型加载
只发生在 worker；主框架 import `registry` 时不会吸收 LangChain 依赖树或启动资源。

## 3. 配置与 source identity

`configs/methods/langmem.toml` 有且只有 `smoke` 与 `official_full`。两者共同锁定：

- official unstructured `Memory(content)` schema；
- insert/update 开、delete 关；
- `query_model=None`、old-memory `query_limit=5`、`max_steps=1`；
- `models/all-MiniLM-L6-v2`、dimension 384、external L2 normalization、
  LangGraph InMemoryStore cosine；
- session 粒度与 framework benchmark answer builder。

差异只有 API runtime/model 与 full worker 上限：smoke 是
`opencodego/deepseek-v4-flash`，official_full 是 `primary/gpt-4o-mini`。五家官方 harness
集为空，不建立 `author_*` section。

source identity 覆盖 current commit/package、M1 的 9 个 selected product 文件、vendored
`uv.lock`、adapter、worker、bootstrap 与补充 requirements。当前稳定锚：

```text
commit=56d85939d80bb731bd5e237567148d817d7bfd16
package_version=0.0.30
vendored_source_sha256=50999bd9675304d514d86218033898ac1930a57958aeda95cb967f22f59753fb
runtime_lock_sha256=b5031c66951bf52265ab300a51403728f37e2a6939be31ed75f023eaa5d49a66
```

`source_sha256` 还包含本项目 wrapper 内容，因此每次 adapter/worker 改动都会自动变化，不在
文档复制一个会立即过时的最终值。

## 4. 五格 payload

共同规则：一个 session 一次 manager 调用；一个 canonical 非空 event 恰好一条 message；
不补 placeholder、不重新配对、不跨 session。source time 只按
`turn → 当前 session → None` 前置，question time、兄弟 turn 和 wall clock 不可达。

| Benchmark | 最终 role/content | 差量处置 |
| --- | --- | --- |
| LoCoMo | 固定 `speaker_a→user`、`speaker_b→assistant`，真实 speaker name 留在 content | shared image helper；caption 可见，path/query 不可见；奇数尾合法 |
| LongMemEval | canonical user/assistant 原序、完整 session | assistant-first、same-role、singleton/odd tail 原样；不按 question date filter |
| MemBench | FirstAgent child role 与 ThirdAgent user-only 原序 | 尾部 place/time 原文保留且不重复 header；100k noise 为 None |
| BEAM | 四 variant canonical role/order | 10M orphan/mismatch 不修 raw、不位置重配、不跨 session 排序 |
| HaluMem | 每 session 一次完整 messages | `ainvoke` 返回即 current state 可检索；private memory points 不进 build |

完整异常、隐私、指标与失效触发器在
[五格安全档案](langmem-five-benchmark-safety-dossier.md)。

## 5. 原子状态、resume 与 clean

每个 namespace 的单一 JSON 同时保存：

```text
adapter/schema identity
exact entries = [{key, value}, ...]              # 保留插入顺序
completed_operations[operation_id] = {
  input_digest,
  changed_memory_keys,
  memory_count,
  llm_observations,
  embedding_observations
}
```

operation id 由 adapter version、namespace、session id、完整 role/content messages 与 max_steps
确定。调用前保存 store exact snapshot；manager、输出校验或原子文件提交任一失败，就经公开
`adelete/aput` 恢复调用前 key/value/order。只有算法写入与 journal 同文件原子提交成功，才向
runner 返回。结果丢失后同输入重试直接复用已完成结果；相同 operation id 配不同 input digest
立即失败。

恢复 state 时，entry 仍经同一 `store.aput()` 重建 vector；其 entry 数与 embedding call 数作为
rehydration metadata 明示，不冒充某个业务 conversation 的 build observation。效率 artifact
按稳定 observation id 幂等合并，因此同 operation 的 journal replay 不会重复计费事实。

clean 先把 active state 原子复制到 `.cleanup.json` tombstone 再删除 active；随后只恢复/删除
目标 namespace，复核为空后才移除 tombstone。中途失败时 tombstone 留存，下一次 clean 可继续；
另一 namespace 的 store/state 不受影响。

## 6. 并行 ownership

一个 provider 独占一个 worker、event loop、ChatOpenAI、SentenceTransformer、InMemoryStore 与
state root。generic isolated runner 的 W2 会创建两个 provider，测试现场证明 runtime 对象、
storage root 与 namespace 均不同，cleanup 各一次；没有 process-global tokenizer/store。

因此 LangMem 允许 smoke W2 override。`official_full.max_workers=10` 仍是同样的 isolated-provider
拓扑，不共享模型对象；它会增加本机模型副本和内存开销，但不改变算法。HaluMem operation
runner 自身固定 W1，不能用该结论强行并行化固定 shape。

## 7. Readout 与 metric

worker 保留 `asearch()` 返回的 product order、key、score 和 current content；adapter 不二次
排序。InMemoryStore cosine 排序使用稳定 sort；候选插入顺序随 state snapshot 原序恢复，tie
在 resume 前后保持稳定。zero hit 返回 `items=()` 与非空 sentinel；worker/backend/协议失败
抛错，绝不伪装为 zero hit。

| 能力 | 裁决 |
| --- | --- |
| stable product ranking | valid |
| semantic provenance | N/A：current memory 可融合/覆盖旧事实，无 lossless source mapping |
| Recall/Precision/F1@k、NDCG | N/A：source qrel 前提不成立 |
| HaluMem extraction | N/A：changed put 可融合旧 memory，不是严格 session-local point |
| HaluMem update | valid：judge 消费写入后 current evolved state |
| HaluMem QA | valid：framework answer builder 消费 product search readout |
| HaluMem memory type | N/A：依赖 extraction point，不能从 free text 猜类型 |

## 8. 效率与 secret

- build LLM：LangChain callback 从每次成功 response 读取 exact API usage；缺失/非法 usage 让
  operation 失败，不用 tokenizer estimate 冒充。
- embedding：实际 SentenceTransformer 调用以其 tokenizer 统计 input tokens，以 framework
  timer 记录 latency；ingest 与 retrieval 分 scope，rehydration 单独披露。
- answer/judge：沿用 framework 已有观测。
- worker env 只透传最小系统变量与当前 build key；宿主其他 provider secret 不继承。
  key 不进 JSON request、manifest、state；stderr 和协议错误做 secret 替换。
- `opencodego` 追加 `thinking={type: disabled}` 且锁 Chat Completions；primary 不追加 provider
  私有字段。transport/model 进入 run identity，不能混分。

## 9. 当前离线验证

隔离 runtime 初始化、本地模型加载、真实 product `asearch()` zero-hit、namespace 删除与关闭，
零 API：

```text
LANGMEM_ZERO_API_PRODUCT_READOUT_PASSED
```

adapter、worker transaction、五格 registered runner 与 registry 当前定向：

```text
107 passed in 1.58s
```

扩展 generic/operation/CLI runner 回归：

```text
395 passed in 7.69s
```

架构师最终扩展定向：

```text
473 passed in 9.12s
```

主树无 API 全量：

```text
2021 passed, 3 deselected, 13 warnings, 29 subtests passed in 132.29s
```

13 个 warning 全是既有 vendored LightMem Pydantic deprecation 与 MemOS datetime/Pydantic
serialization warning；没有 LangMem warning。其余门：

```text
PASS method integration ledger: contract=method-integration-ledger-v1, methods=langmem, letta, count=2
smoke-plan JSON: 20 entries / 9 croppable W2 / 2 fixed HaluMem W1, jq exit 0
compileall: exit 0
git diff --check: exit 0
nested LangMem: clean main@56d85939d80bb731bd5e237567148d817d7bfd16
```

阶段性 `107/395 passed` 保留为施工轨迹；最终门以上述 473 与 2021 为准。

## 10. 当前未关闭项

1. 真实 build/answer/judge API 未获本批明确预算、规模与 run id 批准；
2. planner child run 的 manifest、prediction、formatted_memory、efficiency/state/summary 尚未开箱；
3. official_full 与效果型 run 未执行；
4. extraction/source-qrel 指标为机制性 N/A，不会为了填表改算法；
5. 真实 W2 的资源峰值和吞吐尚待 smoke 观测，离线门只证明 ownership 与接线。

判词：

```text
READY_FOR_B11_REAL_SMOKE_APPROVAL(
  async background manager and product asearch are wired directly;
  exact state, result-loss retry, rollback and namespace cleanup are closed;
  five payloads and metric eligibility are truthful;
  real API artifacts are not yet claimed
)
```
