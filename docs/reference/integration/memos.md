# MemOS 接入参考（v2.0.25 product）

> 稳定页：只记录经架构师验收的承重结论。完整一手证据、争议与施工记录见
> `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/`。
>
> 状态：M4 adapter 已实现并通过零 API 强反例；**真实服务 smoke（B11）尚未执行**，
> 下方标记 `pending` 的能力一律不得当作已验证。

## 1. Source identity

| 项 | 值 |
| --- | --- |
| upstream | `https://github.com/MemTensor/MemOS.git` |
| release | `v2.0.25` |
| commit | `e820406269537b97d270687e3e40eea2f015f81a` |
| 本地路径 | `third_party/methods/MemOS`（gitignored，local-only） |
| patch | `scripts/patches/memos-product-runtime-observability.patch`（zero-context，`--unidiff-zero` 幂等应用） |
| adapter | `src/memory_benchmark/methods/memos_adapter.py` |
| adapter version | `memos-v2.0.25-product-v1` |
| 实现身份 | `typed-product-handler` |

判据：`clean v2.0.25 checkout + patch` 与当前 vendored 树逐字节一致。

## 2. 运行身份（主 profile，不得在 TOML 放宽）

```text
backend                 tree_text
reader                  MultiModalStructMemReader
entry                   init_server → HandlerDependencies.from_init_server
                        → typed AddHandler / SearchHandler
HTTP host/server_router 禁止（不得 import memos.api.routers.server_router）
add                     APIADDRequest(async_mode="async", mode=None)
scheduler queue         local（MEMSCHEDULER_USE_REDIS_QUEUE=false）
parallel dispatch       product default true（MemOS 内部并行，非 framework 并行）
reorganize              false
cube topology           一个 conversation 一个 namespace / 一个 cube
framework granularity   session
framework max_workers   1（smoke 与 official_full 都是 1）
answer                  framework benchmark unified builder
```

`smoke` 与 `official_full` 除 `profile_name` 外参数完全相同；成本控制只通过
conversation/question/turn 规模裁剪。

## 3. 本项目对 MemOS 的修改（patch 内容）

patch 只改**失败可见性**与**已支持能力的暴露**，成功路径算法零变化：

1. R2 六处：reader/LLM/parser/embedding、graph/vector write、fine transfer、
   raw delete、refresh、scheduler submit 的既有吞错改为失败可见；
2. M4 `APIConfig.get_embedder_config()`：新增 `sentence_transformer` 分支，
   暴露 `EmbedderFactory` 已原生支持的 backend，使受控 MiniLM 可作主配置
   embedding；未知 backend 不再静默落入 Ollama，改为显式 fail-fast；
3. M4 `SingleCubeView._search_text()`：真实 graph/vector/search 失败与非法
   search mode 不再返回 `[]`，改为记录后上抛——合法 backend 空结果仍是 zero-hit。

## 4. 输入语义

每个保留的 canonical event 恰好生成一条 message：

```text
role        canonical role（LoCoMo 例外，见下）
content     原 content + 共享 [Sharing image that shows: {caption}] 契约
chat_time   event.timestamp（turn → session → None；key 始终存在）
message_id  canonical public turn_id
```

- **LoCoMo**：从公开 `conversation_metadata` 读 `speaker_a/speaker_b`，固定
  `speaker_a → user`、`speaker_b → assistant`，与谁先发言无关；content 前缀是
  真实 speaker 名。缺声明、两者相同、第三 speaker 一律 fail-fast。
  官方 `locomo_ingestion.py` 的「双 user_id + 正反 role 双写 + 双路检索合并」
  是 reproduction harness，**未**混入主 profile。
- **其余四家**：只接受 canonical `user/assistant`，原顺序逐条保留；
  assistant-first、连续同 role、singleton、奇数尾部都合法，不重新配对、不排序、
  不补假回复。
- **MemBench**：原文尾部 place/time 保留，同时把 canonical 时间写入 `chat_time`，
  不重复拼时间 header；100k noise 无时间时 `chat_time=None`。
- 空 content event 一律 fail-fast，不制造 placeholder。

## 5. Readout

`SearchResponse.data["text_mem"]` 按产品返回顺序扁平化，不二次排序、不截断：

| RetrievedItem | 来源 |
| --- | --- |
| `item_id` | memory `id`（缺/空 fail-fast） |
| `content` | memory `memory` 文本（缺/空 fail-fast） |
| `score` | `metadata.relativity`（None 合法，非数值 fail-fast） |
| `timestamp` | `metadata.created_at`（唯一一手定义的时间字段；其余不猜） |
| `source_turn_ids` | `metadata.sources[].message_id`，保序去重 |

`formatted_memory` 只按产品顺序连接 memory 文本；零命中用非空 sentinel
`(No relevant memories found)`。embedding 与不可序列化对象不进 artifact。

**`reference_time`**：v2.0.25 schema 有该字段，但 current search 代码零消费
（全仓仅 `product_models.py` 一处出现）。adapter 仍忠实传入 question time，并在公开
metadata 标记 `reference_time_effect="declared_but_unwired_v2.0.25"`；
**不得宣称时间过滤已生效**。

## 6. Metric 资格（首版）

| 格 | 结论 |
| --- | --- |
| 五 benchmark Recall / NDCG / stable ranking | `pending` |
| HaluMem QA | `valid` 候选，待真实服务 smoke |
| HaluMem extraction | `N/A`（async `MEM_READ` 未公开 task-scoped fine output） |
| HaluMem update | `pending`（待 current-state readout 真实 DB 链） |
| HaluMem memory type | `N/A`（MemOS `Working/LongTerm/User/Outer` ≠ Event/Persona/Relationship） |

逐题 `RetrievalEvidence` 一律：

```text
semantic_provenance.status = pending
  reason_code = memos_generated_memory_semantic_lineage_unverified
provenance_granularity     = none
stable_ranking.status      = pending
  reason_code = memos_product_rerank_stability_unverified
```

理由：MemOS fine memory 是**窗口生成物**，`sources[].message_id` 只证明该 source
进入了生成窗口，**不**证明生成后的 memory 仍语义承载每个 source fact；真实
Neo4j/Qdrant + MMR/rerank 的稳定次序也尚未一手验证。
**不得因 `source_turn_ids` 存在就把 Recall/NDCG 升为 valid**；零命中也不改变这一静态事实。

## 7. Namespace 与 clean retry

namespace = `mb + isolation_key 安全前缀 + sha256(storage_root_relative|isolation_key)[:32]`。
`storage_root_relative` 已编码 `benchmark/variant/run_id`，因此同一 conversation 的
add/search/clean 得到同一 namespace，跨 conversation / run / worker 必然不同；
不含绝对机器路径、gold、question id 或随机 UUID。

clean retry 只走 namespace-scoped 路径：

```text
DeleteMemoryRequest(writable_cube_ids=[ns], user_id=ns)
→ handle_delete_memories → data.status 必须 == "success"
→ handle_get_memories(mem_cube_id=ns, preference/tool/skill 全 false)
→ text_mem 为空且 total_nodes == 0
```

前置条件：本 process tracker 中该 namespace 没有 pending task。
**绝不**调用 `delete_by_memory_ids()`，**绝不**无 namespace 清全库。

## 8. Build identity 与观测

```text
implementation_variant = product
embedding_profile      = controlled_embedding_v1
embedding              = sentence_transformer / models/all-MiniLM-L6-v2 / 384
                         / local_unpinned / model_pipeline_l2 / qdrant-cosine
historical_controlled_build_equivalent_to_current_main = false
```

`normalization=model_pipeline_l2` 是 source-proven，不是猜测：current
`SenTranEmbedder.embed()` 调 `model.encode()` 时**不**传 `normalize_embeddings`
（MemOS 自身不归一化），而受控 MiniLM 模型目录的 `modules.json` 带
`2_Normalize` 模块，L2 由模型 pipeline 提供。

model inventory 区分三类，本地 reranker 不伪装成 LLM：

| model_id | role | mode |
| --- | --- | --- |
| `memos-build-llm` | memory build/extraction LLM（`gpt-4o-mini`） | api |
| `memos-embedding` | 本地 MiniLM 384 | local |
| `memos-reranker` | `cosine_local` 本地算法 | local |

**精确 per-call token/cost 是 M5 preflight 的公开 pending**：MemOS current
`OpenAILLM.generate()` 只返回纯文本并丢掉 response usage，async worker 又脱离
framework question context。不得用 add pair 数或 `len(text)/4` 伪造 exact API usage。

## 9. 仍然 pending 的边界

- 真实 Neo4j/Qdrant 跨 namespace 隔离与 MMR/rerank stable ranking；
- window-generated memory 的 semantic provenance 与 Recall/NDCG 资格；
- HaluMem update current-state 与 QA 的真实服务 smoke；
- MemOS async worker 的精确 per-call token/cost 观测；
- official LoCoMo 双 namespace reproduction harness（主 profile 仍是一 conversation 一 cube）；
- 跨 conversation 并行资格（首版 `max_workers=1`、禁 smoke override、禁共享实例并行）。
