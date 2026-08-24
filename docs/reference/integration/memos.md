# MemOS 接入参考（v2.0.25 product）

> 稳定页：只记录经架构师验收的承重结论。完整一手证据、争议与施工记录见
> `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/`。
>
> 状态：current product adapter 已完成五格真实服务 smoke、B7 观测补证与 B1-B11
> 对表，冻结为 `method-frozen-v1`。下方 `pending/N/A` 是能力资格边界，不代表接入失败。

## 1. Source identity

| 项 | 值 |
| --- | --- |
| upstream | `https://github.com/MemTensor/MemOS.git` |
| release | `v2.0.25` |
| commit | `e820406269537b97d270687e3e40eea2f015f81a` |
| 本地路径 | `third_party/methods/MemOS`（gitignored，local-only） |
| patch | `scripts/patches/memos-product-runtime-observability.patch`（zero-context，`--unidiff-zero` 幂等应用） |
| adapter | `src/memory_benchmark/methods/memos_adapter.py` |
| adapter version | `memos-v2.0.25-product-v5` |
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
cube topology           通常一个 conversation 一个 namespace / cube；
                        LoCoMo 为官方 speaker A/B 双视角、两个 namespace / cube
framework granularity   session
framework max_workers   1（smoke 与 official_full 都是 1）
answer                  framework benchmark unified builder
```

两 profile 的非 LLM build/search 参数完全相同。新 `smoke` 的 LLM runtime 是
`opencodego/ox-alpha-free`，`official_full` 是
`primary/gpt-4o-mini`；该预算型 smoke 不与正式结果比较。运行身份和 transport 见
[`../api-runtime-profiles.md`](../api-runtime-profiles.md)。

### 2.1 直接 typed product 接口调用图

本项目**不启动 HTTP host**，但也没有绕开产品逻辑重写算法。调用的是 host router
最终委托的同一组 typed handler：

```text
首次 ingest/retrieve
  → 在受控环境变量作用域内 init_server()
  → HandlerDependencies.from_init_server(components)
  → AddHandler(dependencies) + SearchHandler(dependencies)
  → 两个 handler 共用同一 scheduler / naive_mem_cube / tracker
```

`init_server()` 对同一 config identity 在进程内只执行一次；provider 构造本身是 lazy，
clean-only 路径不会为了清理反向创建 runtime。禁止 import
`memos.api.routers.server_router`，因为它会在 import 期创建另一套全局 components。

#### Ingest

framework 先按 `consume_granularity="session"` 聚合成 `SessionBatch`。adapter 为每个
canonical event 构造一条 message。LongMemEval/MemBench/BEAM/HaluMem 每个 session
发一个请求；LoCoMo 为官方正/反 speaker 视角各构造一份列表，并在每个视角内按
`batch_size=2` 发多个请求（奇数尾 singleton、无 placeholder）：

```python
APIADDRequest(
    user_id=namespace,
    writable_cube_ids=[namespace],
    session_id=unit.session_id,
    task_id=business_task_id,
    messages=[
        {
            "role": "user | assistant",
            "content": "...",
            "chat_time": "source time | None",
            "message_id": "canonical turn id",
        },
        ...
    ],
    async_mode="async",
    mode=None,
)
AddHandler.handle_add_memories(request)
```

`namespace == user_id == cube_id`；除 LoCoMo 双视角外，一个 conversation 一个
namespace。`task_id` 由 namespace、session id 与 adapter 内递增序号确定性生成。
LoCoMo 的全部 pair/singleton add 先提交，再逐 task 等待，避免把官方 async 入口暗改为
pair 间同步。`handle_add_memories()` 返回不代表 fine memory 已完成，adapter 随后必须调用：

```text
local_tracker.wait_for_business_task(
  user_id=namespace,
  business_task_id=task_id,
  timeout_seconds=config.task_timeout_seconds
)
```

只有 tracker 抵达唯一 terminal success 才算该 session ingest 完成；reader、storage、
archive、raw delete、refresh 或 scheduler submit 任一失败都必须传播。

HaluMem profile 在提交前经同一 product `GetMemory` handler 读取完整 text-memory baseline；全部
business task 唯一 terminal success 后再次读取同一 namespace。两个快照都必须是未分页全量、
唯一 stable ID、非空 current text，adapter 才按 ID 报出新增或内容变化后的 memory。task 未到
终态、GetMemory 不完整或 namespace 不一致都 fail-fast，不用 raw messages 或 scheduler 日志
冒充 extraction。

#### Retrieve

通常每题只调用一次 typed `SearchHandler`；LoCoMo 对 A/B 两个 namespace 各调用一次：

```python
APISearchRequest(
    query=query.query_text,
    user_id=namespace,
    readable_cube_ids=[namespace],
    mode="fast",
    top_k=query.top_k,
    relativity=...,
    dedup=...,
    rerank=...,
    include_preference=False,
    search_tool_memory=False,
    include_skill_memory=False,
    neighbor_discovery=...,
    internet_search=False,
    chat_history=[],
    filter=None,
    session_id=None,
    reference_time=query.question_time,
)
SearchHandler.handle_search_memories(request)
```

adapter 只消费 `SearchResponse.data["text_mem"]`，按 bucket/memory 产品返回顺序扁平化；
不会自行查底层 Qdrant/Neo4j、重排或二次截断。LoCoMo 每一路各取
`query.top_k`，保留各路内部产品顺序后放进真实 speaker 的两个槽位；没有跨库全局 rank。
`reference_time` 在 v2.0.25 只是 schema 字段，current search 未消费，故不能宣称按
question time 过滤。

#### Failed-ingest clean 与 runtime close

clean retry 不走危险的 `delete_by_memory_ids()`，而是直接调用产品 memory handler：

```text
DeleteMemoryRequest(writable_cube_ids=[namespace], user_id=namespace)
  → handle_delete_memories(...)
  → GetMemoryRequest(mem_cube_id=namespace, user_id=namespace, 三类附加 memory=false)
  → handle_get_memories(...)
  → text_mem 为空且 total_nodes == 0
```

LoCoMo 删除前先对两个 namespace **全部**完成 pending preflight，再逐路 delete/readback；
成功后删除 speaker sidecar。其余格仍是单 namespace。run 收尾先执行
`tracker.assert_no_pending_tasks()` 再 `scheduler.stop()`；pending refusal 可在 task
终态后重试，`stop()` partial failure 则永久 fail-closed，既不标 closed，也不构造第二套
runtime。

实现入口：
[`memos_adapter.py`](../../../src/memory_benchmark/methods/memos_adapter.py)；
生命周期补丁：
[`memos-product-runtime-observability.patch`](../../../scripts/patches/memos-product-runtime-observability.patch)。

## 产品接口契约（参数、返回与批次）

跨 method 粒度矩阵见
[`../method-interface-inventory.md`](../method-interface-inventory.md)。本项目直接调用 typed
handler，不启动 HTTP host；`APIADDRequest`/`APISearchRequest` 是 Pydantic request model，
不是“已经发出 HTTP”的标志。

| typed 调用 | 关键参数类型与本项目取值 | handler 返回/完成语义 | adapter 映射 |
| --- | --- | --- | --- |
| `AddHandler.handle_add_memories(request: APIADDRequest)` | `user_id: str`；`writable_cube_ids: list[str]`；`session_id: Optional[str]`；`task_id: str`；`messages: list[dict]`，每项 `role/content: str`、`chat_time: Optional[str]`、`message_id: str`；`async_mode="async"`；`mode=None` | immediate response 只证明任务已提交，不证明 fine memory 完成 | adapter 保存 `(namespace, task_id)`，逐个 `wait_for_business_task(...)` 到唯一 terminal success 后才返回 `IngestResult` |
| `SearchHandler.handle_search_memories(request: APISearchRequest)` | `query/user_id: str`；`readable_cube_ids: list[str]`；`mode="fast"`；`top_k: int`；`relativity/dedup/rerank/neighbor_discovery: bool`；其余 include/tool/filter/history/reference-time 字段见 §2.1 | `SearchResponse`；adapter 只消费 `response.data["text_mem"]` 的 bucket/memory list | 按产品 bucket→memory 原序生成 `tuple[RetrievedItem, ...]` 与 `formatted_memory`；LoCoMo 两 namespace 分槽，不伪造跨库 global rank |
| `local_tracker.wait_for_business_task(user_id: str, business_task_id: str, timeout_seconds: float)` | 与 add 的 namespace/task 完全相同 | terminal task record；失败/超时抛错 | 是 async build 的真实完成门，不是额外算法步骤 |

framework 五格统一给 MemOS `SessionBatch`。普通四格的整个 session 对应一个
`APIADDRequest.messages` list；LoCoMo 按官方双 namespace/正反 role 映射，每路再按
`batch_size=2` 切多个 list，奇数尾为 singleton，**不补 placeholder**。因此这里同时存在
“framework session 粒度”和“产品 pair-size batch”，两者不矛盾。

`retrieve(RetrievalQuery) -> RetrievalResult` 的 `items` 保留产品 text-memory 元素；当前
MemOS 没有 lossless source mapping，semantic provenance 仍按资格页声明 pending/N/A，不能因
`SearchResponse` 是 list 就自动解锁 Recall。完整请求示例、namespace 与返回消费边界见 §2.1。

## 3. 本项目对 MemOS 的修改（patch 内容）

patch 只改**失败可见性**与**已支持能力的暴露**，成功路径算法零变化：

1. R2 六处：reader/LLM/parser/embedding、graph/vector write、fine transfer、
   raw delete、refresh、scheduler submit 的既有吞错改为失败可见；
2. M4 `APIConfig.get_embedder_config()`：新增 `sentence_transformer` 分支，
   暴露 `EmbedderFactory` 已原生支持的 backend，使受控 MiniLM 可作主配置
   embedding；未知 backend 不再静默落入 Ollama，改为显式 fail-fast；
3. M4 `SingleCubeView._search_text()`：真实 graph/vector/search 失败与非法
   search mode 不再返回 `[]`，改为记录后上抛——合法 backend 空结果仍是 zero-hit。
4. M5 runtime compatibility：关闭 internet 时不再构造不可达的 internet retriever；
   opencodego build reader 显式关闭 thinking 并要求 JSON object。LLM transport/解析失败
   不得伪装成 raw-text `UserMemory`；合法 `{"memory list":[]}` 仍是零抽取成功。
5. B7 `OpenAILLM.response_callback`：只在成功 response 完成解析后暴露原
   response/request/result，primary 与 successful backup 各恰好一次；未安装 callback
   时返回值不变。adapter 用它读取真实 API usage，不改变 prompt、请求参数或 memory。

## 4. 输入语义

每个保留的 canonical event 恰好生成一条 message：

```text
role        canonical role（LoCoMo 例外，见下）
content     原 content + 共享 [Sharing image that shows: {caption}] 契约
chat_time   event.timestamp（turn → session → None；key 始终存在）
message_id  canonical public turn_id
```

- **LoCoMo**：从公开 `conversation_metadata` 读 `speaker_a/speaker_b`，主轨已按
  官方 harness 改为双 namespace：
  - A 视角 `speaker_a→user / speaker_b→assistant`；
  - B 视角 role 完全反转；
  - 两路 content 都保留真实 speaker 前缀；
  - 每路按位置 `batch_size=2`，奇数尾 singleton，不造 placeholder；
  - 所有 add 先提交再按 task 精确等待。
  缺声明、两者相同、第三 speaker 一律 fail-fast。speaker identity 以原子 sidecar
  持久化，resume 缺失时拒绝猜测。
- **LongMemEval**：主轨保留完整 session、原 role/顺序与全 content；assistant-first、
  连续同 role、singleton、奇数尾都合法。官方 evaluation wrapper 的
  `batch_size=2 + content[:8000]` 是待实现 `author_longmemeval` 校准身份，不进入主表；
  current wrapper 的 `reference_time` 调用还与 client 签名冲突，不能宣称 paper parity。
- **其余三家**：只接受 canonical `user/assistant`，原顺序逐条保留；
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

`formatted_memory` 通常只按产品顺序连接 memory 文本。LoCoMo 对两个 namespace
分别检索，各路均使用完整 `query.top_k`，再按官方槽位格式输出：

```text
Memories for user {speaker_a}: ...
Memories for user {speaker_b}: ...
```

这不是一个跨 namespace 的总 top-k/global rank；公开 metadata 标为
`retrieval_top_k_semantics=per_locomo_speaker_view`。两路都零命中时仍用非空 sentinel
`(No relevant memories found)`。embedding 与不可序列化对象不进 artifact。

**`reference_time`**：v2.0.25 schema 有该字段，但 current search 代码零消费
（全仓仅 `product_models.py` 一处出现）。adapter 仍忠实传入 question time，并在公开
metadata 标记 `reference_time_effect="declared_but_unwired_v2.0.25"`；
**不得宣称时间过滤已生效**。

## 6. Metric 资格（首版）

| 格 | 结论 |
| --- | --- |
| 五 benchmark Recall / NDCG / stable ranking | `pending` |
| HaluMem QA | `valid`，真实 smoke 已通过 |
| HaluMem extraction | `valid`（精确 terminal 后完整 product GetMemory stable-ID delta） |
| HaluMem update | evaluator contract `valid`；本次极小 smoke 因 7 个 current-state probe 全部 zero-hit，结果诚实为 `N/A/no_nonempty_retrieval` |
| HaluMem memory type | `valid`（复合 evaluator 消费 extraction/update artifact；Event/Persona/Relationship 是 evaluator-private gold 分组，不要求 method 使用同名 taxonomy） |

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

LoCoMo 把稳定的 `speaker_a/speaker_b view` 追加到 namespace identity 后分别哈希；
两个 namespace 逻辑隔离，同一公开 turn 在每个视角恰好出现一次。clean 对两路统一做
pending preflight，再逐路删空并验空，避免 view A 已删、view B 仍 pending 的可避免半清理。

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
| `memos-build-llm` | memory build/extraction LLM（smoke=`ox-alpha-free`；official=`gpt-4o-mini`） | api |
| `memos-embedding` | 本地 MiniLM 384 | local |
| `memos-reranker` | `cosine_local` 本地算法 | local |

product-v4 已关闭 B7：

- patched `OpenAILLM` 在 primary/backup 成功响应上暴露原始 API usage；
- MemOS async worker 不继承 framework ContextVar，因此后台 callback 只写入
  provider 的线程安全原始缓冲；精确 business task 完成后，由发起 ingest/retrieve 的
  原线程回放到当前 conversation/question scope；
- build LLM token 来源为 `api_usage`；本地 SentenceTransformer embedding 复用真实
  tokenizer、`max_seq_length` 与 upstream 字符预截断，来源诚实标
  `tokenizer_estimate`；latency 使用实际调用 wall timer；
- 操作失败会丢弃本操作未提交缓冲，不能污染下一 scope。

product-v5 在成功路径只增加 HaluMem 的 terminal 前后 `GetMemory` 快照与 session report，
不改变 reader、scheduler、fine memory 或 search 算法；它同时意味着旧 v4 method state/artifact
不能重标为 v5，下一次真实运行必须新 run 全量重建。

真实 B7 哨兵：

| run | build LLM | build embedding | retrieval embedding |
| --- | ---: | ---: | ---: |
| `memos-locomo-v4-b7-r1q1-w1` | 2 次，3286 input / 325 output，全部 `api_usage` | 4 | 2（双 namespace） |
| `memos-halumem-v4-b7-r1-w1-medium` | 4 次，全部 `api_usage` | 9 | 8（7 update probe + 1 QA） |

不得用 add pair 数或 `len(text)/4` 猜调用数；真实 observation 才是成本事实。

## 9. 五格真实 smoke 与版本继承

product-v3 已完成五 benchmark current product runtime：

| benchmark | run |
| --- | --- |
| LoCoMo | `memos-locomo-v3-r3q1-w1` |
| LongMemEval S-cleaned | `memos-lme-v3-r1q1-w1-s-cleaned` |
| MemBench 0-10k / 100k | `memos-membench-v3-r1q1-ps1-w1-0-10k`；`memos-membench-v3-r1q1-ps1-w1-100k` |
| BEAM 100K / 10M | `memos-beam-v3-r1q1-w1-100k`；`memos-beam-v3-r1q1-w1-10m` |
| HaluMem Medium | `memos-halumem-v3-r1-w1-medium` |

product-v4 只新增成功 response callback 与 adapter 侧纯观测回放，不改变五格
payload、搜索、memory 内容或返回值。零 callback、primary callback、backup callback、
跨线程 build/retrieval scope 与 tokenizer 均有强反例；再以 LoCoMo（双 namespace）
和 HaluMem（operation-level）两个真实 B7 哨兵补证。因此其余四格继承 product-v3 的
功能 smoke，不为纯观测版本重复烧 API。

current v4 结果：

- LoCoMo：F1=`0.6667`、judge=`0`、normalized/substring EM=`0`；
  Recall=`null/pending`。极小分数不作效果判断。
- HaluMem（历史 v4）：QA=`1.0`；extraction=`null/N/A`；update=`null/N/A`
  （7 个 probe 均 zero-hit）；memory type=`null/N/A`。
- 所有 v3 五格 predict/evaluate/machine gate 通过；MemBench 100k 的
  `chat_time=None`、BEAM 两 variant、LoCoMo 双 namespace 与 HaluMem 精确 terminal
  均由真实 state/artifact 验货。

## 10. 冻结后保留的边界

- MMR/rerank stable ranking；
- window-generated memory 的 semantic provenance 与 Recall/NDCG 资格；
- HaluMem v5 的 session-local extraction 已由 terminal GetMemory stable-ID delta 闭合；真实 API
  pilot 尚待 M5 后新 run 补证。memory-type 按 composite contract 继承该资格，不另要求 MemOS
  暴露 Event/Persona/Relationship taxonomy；
- HaluMem update 的非空 current-state 命中尚未由极小 smoke 覆盖；这不把 zero-hit
  改写成 0 分，也不影响 QA 已验证；
- author LoCoMo 的 preference/top-k/server-env/paper-number parity；
- `author_longmemeval` 的 pair batching、8000 截断、官方 builder 与已坏
  reference-time 路径；
- framework conversation W2 已由真实 `Already borrowed` 反例判为
  `N/A/unsupported`：两个 isolated provider 仍共享进程级 MemOS runtime/embedder。
  `max_workers=1`、禁 smoke override；MemOS 产品内部 async dispatcher 保持开启。

一次 LoCoMo W2 成功不能推翻 LongMemEval W2 的真实竞态。失败 run
`memos-lme-v4-r1q1-c2-w2-s-cleaned` 为 1/2 completed，且无 conversation budget；
现行 summary 会记录 `failed_conversations`，CLI 返回非零，`run` 子命令也不会继续给
失败 child 评分。完整裁决见 frozen note §5。

## 11. 调查与裁决资产索引

日常查“当前 MemOS 怎么调用”只读本页；需要复核某个承重结论再下钻：

| 问题 | 一手证据 / 裁决 |
| --- | --- |
| source lock、release 与 PDF/源码身份 | [source lock](../../workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/memos-v2.0.25-source-lock.md) |
| product reader、时间、lineage、host/handler、scheduler 机制 | [runtime preflight R1](../../workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/memos-v2.0.25-product-runtime-preflight-r1.md) |
| async fast→fine 完成链与失败传播 | [R2 architect acceptance](../../workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/memos-v2.0.25-async-lifecycle-r2-architect-acceptance.md) |
| typed adapter、五格 payload、namespace、readout | [M4 implementation](../../workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/memos-v2.0.25-product-adapter-m4-implementation.md) |
| cleanup 四态与最终接收边界 | [M4 architect acceptance](../../workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/memos-v2.0.25-product-adapter-m4-architect-acceptance.md) |
| 官方 LoCoMo/LME harness parity、五格主/作者身份 | [M5 harness ruling](../../workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/memos-v2.0.25-official-harness-parity-m5-ruling.md) |
| 五格 smoke、B7 观测与最终冻结 | [frozen-v1](../../workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/memos-frozen-v1.md) |

根目录未跟踪的 `MemOS.md` 是用户提供的外部调研草稿，可作线索，**不是**本项目稳定事实
源；本页与上表 notes 才是跨模型可恢复入口。
