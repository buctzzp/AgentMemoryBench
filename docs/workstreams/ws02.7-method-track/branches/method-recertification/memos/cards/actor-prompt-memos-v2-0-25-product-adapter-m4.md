# Actor 卡：MemOS v2.0.25 product v3 adapter M4

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**你是施工 actor，不是架构师；按本卡已经裁定的边界实现。actor 可自行
组织 subagent，但不得扩大允许范围；主 actor 必须亲核承重锚并对最终 diff、测试与报告负责。

## 0. 这张卡解决什么

前两批已经把 MemOS current product 的 source identity、typed handler、默认 async lifecycle
和失败传播压实。本卡第一次把它接入 framework v3：

```text
SessionBatch
→ typed AddHandler(APIADDRequest async)
→ fast/raw write
→ local queue + product-default parallel dispatcher
→ MEM_READ fine extraction/write
→ raw cleanup + refresh
→ task-scoped terminal
→ typed SearchHandler(APISearchRequest)
→ RetrievalResult
→ framework benchmark answer builder
```

同时关闭四个 adapter 前置缺口：

1. `APIConfig.get_embedder_config()` 公开的 backend 分支没有暴露 factory 已支持的
   `sentence_transformer`，导致主配置不能忠实使用本项目受控 MiniLM；
2. `SingleCubeView._search_text()` 把真实 graph/vector/search 失败吞成 `[]`，会把故障伪装成
   合法 zero-hit；
3. generic prediction runner 当前不保证 v3 provider 在成功/失败后 `cleanup()` 恰好一次，
   MemOS 的 consumer/monitor/dispatcher 线程会泄漏；
4. MemOS 的 window-wide `sources` 只证明参与过生成，不等于生成后的 memory 对每个 source
   fact 都有 turn-exact semantic provenance；本卡必须诚实陈述逐题 metric 资格。

本卡的唯一成功判词：

```text
READY_FOR_MEMOS_M5_PREFLIGHT(
  product runtime is reached without HTTP host;
  async completion and cleanup are exact;
  five benchmark input shapes are lossless;
  zero-hit is distinct from backend failure;
  metric eligibility is truthful
)
```

否则：

```text
BLOCKED(<首个无法在本卡裁决内闭合的承重问题>)
```

本卡不是 B11、不是 method frozen、不是性能/效果实验；零真实 API、数据库和模型加载。

## 1. 隔离环境与 Git

- 新建 worktree：`/Users/wz/Desktop/mb-actor-memos-adapter`
- branch：`actor/memos-v2-0-25-product-adapter-m4`
- 基线：派发时本地 `main`
- 完成后一个本地 commit，不 push、不清 worktree

source lock：

```text
third_party/methods/MemOS
v2.0.25
e820406269537b97d270687e3e40eea2f015f81a
```

该 nested repo 当前应只带
`scripts/patches/memos-product-runtime-observability.patch` 表达的六个可解释改动。先做
HEAD/tag、porcelain、patch reverse-check；不得 fetch/pull/checkout/install。新 worktree 缺
gitignored nested repo 时，可创建指向主树上述目录的本地软链；不得暂存。

为生成/验证 patch，允许在 nested repo 暂改 §3 明列的两个新增文件和既有六个 patch 文件；
收尾必须证明：

```text
clean v2.0.25 checkout + 新 patch
== current nested repo 的全部可解释 dirty
```

不得读主树 `.env`，不得软链 `.env`，不得启动 Neo4j/Qdrant/Redis/Docker/HTTP host，不得调用
真实 LLM、embedding 或下载模型。

## 2. 最小必读

只按顺序读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/README.md`
4. `docs/reference/actor-handbook.md`
5. `../notes/memos-v2.0.25-m1-final-ruling.md`
6. `../notes/memos-v2.0.25-async-lifecycle-r2-architect-acceptance.md`
7. 本卡 §4 点名的 current source 与允许修改文件

五个 benchmark 的 raw/canonical/gold、异常账、Gold Evidence Group、answer/judge builder
已经冻结。禁止重做 raw census、重新调查前五家 method 或通读全部 docs；五格只复用生产
canonical 事件构造强反例。

## 3. 允许修改文件

父仓只允许：

```text
scripts/patches/memos-product-runtime-observability.patch
scripts/fetch_third_party_methods.sh
third_party/methods/MANIFEST.md
configs/methods/memos.toml
src/memory_benchmark/methods/memos_adapter.py
src/memory_benchmark/methods/__init__.py
src/memory_benchmark/methods/registry.py
src/memory_benchmark/runners/prediction.py
tests/test_memos_lifecycle.py
tests/test_memos_adapter.py
tests/test_memos_registered_prediction.py
tests/test_method_registry.py
tests/test_prediction_runner.py
tests/test_prediction_cli.py
docs/reference/integration/memos.md
docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-product-adapter-m4-implementation.md
```

允许清单中的文件没有真实 diff 就不要 add。fetch 脚本应继续只 apply 同一份 MemOS patch，
不得出现第二个 patch 入口。

为更新上述 patch，nested MemOS 只允许新增改动：

```text
src/memos/api/config.py::APIConfig.get_embedder_config
src/memos/multi_mem_cube/single_cube.py::SingleCubeView._search_text
```

以及保留/重放现有 patch 已覆盖的六个文件，不得顺手继续改它们的成功态行为。若必须修改
其他 nested 文件或父仓允许清单外生产文件，立即停工。

禁止改 benchmark adapter、event stream、provider protocol、evaluator、answer/judge prompt、
Gold Evidence Group、metric 公式、data/models/outputs 和其他 third_party method。

## 4. current-source 承重点

### 4.1 产品身份

主 profile 锁死：

```text
backend                   tree_text
reader                    MultiModalStructMemReader
entry                     init_server → HandlerDependencies.from_init_server
                          → typed AddHandler/SearchHandler
HTTP host/server_router   禁止
add                       APIADDRequest(async_mode="async", mode=None)
scheduler queue           local；MEMSCHEDULER_USE_REDIS_QUEUE=false
parallel dispatch         product default true；不得改成 serial
reorganize                false
internet/context/tool/
preference/skill recall   false
cube topology             one deterministic namespace / one cube / conversation
framework granularity     session
framework max_workers     1（首版不声明跨 conversation 并行资格）
answer                    framework benchmark builder
```

`typed handler` 只是去掉 HTTP transport，不是另一个算法。不得 import
`memos.api.routers.server_router`；它会在 module import 时初始化全局 server components。

MemOS factory 单例按 config 缓存，reader 还持有构造时 graph DB；在真实跨 namespace
interleaving 与 observation scope 未验前，本卡注册：

```text
supports_shared_instance_parallelism = false
allow_smoke_worker_override = false
smoke.max_workers = 1
official_full.max_workers = 1
```

不要让 generic runner 因 `max_workers>1` 在同一进程构造多个相同 config 的 MemOS runtime。
这不改变 MemOS **内部** product-default parallel dispatcher。

### 4.2 Config 与 runtime

新增强类型 `MemOSConfig` 与单个 TOML：

```text
[smoke]
[official_full]
```

两 section 除 `max_workers` 仍都为 1 外，build/search 参数完全相同。至少显式记录并验证：

```text
llm_model                 gpt-4o-mini
embedding_backend         sentence_transformer
embedding_model_path      models/all-MiniLM-L6-v2
embedding_dimension       384
embedding_max_tokens      8192
embedding_trust_remote    false
memory_backend            tree_text
reader_backend            multimodal_struct
add_async_mode            async
add_mode                  null
use_redis_queue           false
parallel_dispatch         true
reorganize                false
reranker_backend          cosine_local
search_mode               fast
search_relativity         0.45
search_dedup              mmr
search_rerank             true
include_preference        false
search_tool_memory        false
include_skill_memory      false
neighbor_discovery        false
internet_search           false
task_timeout_seconds      正数
```

Neo4j/Qdrant endpoint、用户名和 secret 的来源必须显式：非 secret 地址可以由 TOML 或已声明的
环境变量名提供；password/API key 不得进入 manifest、note、测试 stdout。若 config 选择用
`*_env` 字段引用 secret，manifest 只写环境变量**名称**，不写值。不得偷偷依赖 `.env`
覆盖算法配置。

`APIConfig.get_embedder_config()` 增加
`MOS_EMBEDDER_BACKEND=sentence_transformer` 分支，返回 factory 已原生支持的：

```text
backend=sentence_transformer
model_name_or_path
embedding_dims
max_tokens
trust_remote_code
```

unknown backend 不得继续静默落入 Ollama；显式 fail-fast。该 patch 只暴露已有 factory
backend，不改 embedding 算法。

adapter 必须 lazy import MemOS。允许先完成 MemOS config module import，再在调用
`init_server()` 前以**作用域化、可恢复**方式安装本 config 的非 secret 参数与
`OpenAISettings`；构造失败也要恢复进程环境。不得把 API key 写日志/manifest。必须显式关闭
Nacos watch、chat API、DingDing、internet、Redis 与 reorganize。

每个 provider 只初始化一个 component bundle，并从同一
`HandlerDependencies.from_init_server()` 构造 Add/Search handler；不得一 conversation
一个 `init_server()`。

### 4.3 Namespace 与 lifecycle

namespace 必须由 run 独占 `storage_root` 的项目相对稳定身份 +
`benchmark_name/variant` 已编码 run 目录 + public `isolation_key` 确定性生成；不得包含绝对
机器路径、gold、question id 或随机 UUID。合法 namespace 只含产品接受的安全字符，并在
manifest/source note 说明算法。

同一 conversation 的 add/search/clean 必须得到同一 namespace；两个 conversation、两个 run
或两个 worker storage root 必须不同。主 topology 是**一个 conversation 一个 cube**，不是：

- 全 run 共用一个 cube；
- 一 session 一个 cube；
- LoCoMo 两 speaker 各一个 cube；
- 同一 turn 正反 role 双写两个 cube。

每次 session add：

1. 生成唯一、确定性可审计的 business `task_id`；
2. 构造一个 `APIADDRequest`，`user_id=namespace`、
   `writable_cube_ids=[namespace]`、`session_id=public session_id`、
   `async_mode="async"`、`mode=None`；
3. 调 typed `AddHandler.handle_add_memories()`；
4. 立刻用 R2 的同一 local tracker 等待该 `user_id + business task_id` 下**恰好一条**
   `MEM_READ` 终态；
5. failed、timeout、missing/multiple task 全部原样 fail-fast；合法 fine 零抽取仍成功。

`cleanup()` 必须先 `tracker.assert_no_pending_tasks()`，再对 scheduler `stop()` 恰好一次；
不得依赖 atexit。重复 cleanup 对 adapter 自身幂等，但不得二次调用 scheduler.stop。

generic prediction runner 同步补齐：

- shared/non-isolated v3 provider：成功路径必须在写 `Completed` stage、summary 和
  `run_completed` 前 cleanup 恰好一次；异常路径在退出前 cleanup 恰好一次；
- isolated worker 自己创建的 v3 provider：必须在把成功 batch 返回协调线程前 cleanup
  恰好一次，异常路径退出前同样 cleanup 恰好一次；
- legacy `BaseMemorySystem`、`_UnusedRootSystem` 行为不变；
- cleanup 异常不得吞掉。若主异常与 cleanup 异常同时存在，保留主异常因果链并让 cleanup
  失败可见，不得把 run 写成成功；
- operation-level runner 已有 cleanup，不得重复改它或造成双关。

### 4.4 Session 输入语义

provider 只接受 `SessionBatch`，不接受 turn/pair/conversation，不制造 placeholder。每个保留
event 恰好生成一个 message：

```text
role
content
chat_time = event.timestamp（其 canonical 契约已是 turn → session → None）
message_id = canonical public turn_id
```

`chat_time` key 必须始终存在；无时间写显式 `None`，不漏 key、不用 question time、兄弟 turn
或 wall clock 补值。MemBench 原 content 尾部的 place/time 原文保留，同时把 canonical 已解析
的时间写到 `chat_time`；不删除尾注，也不重复拼时间 header。100k noise 没时间就为 None。

非 LoCoMo 只接受 canonical `role in {user,assistant}`，原顺序逐条保留：assistant-first、连续
同 role、singleton、奇数尾部都合法，不重新配对、不排序、不补假回复。

LoCoMo：

1. 从公开 `conversation_metadata` 读取非空、互异的 `speaker_a/speaker_b`；
2. 固定 `speaker_a → user`、`speaker_b → assistant`，与谁先发言无关；
3. content 为 `"{真实 speaker name}: {共享 image helper 渲染的原文}"`；
4. 缺声明、两者相同、第三 speaker 一律 fail-fast；
5. 正文+caption 必须使用共享
   `[Sharing image that shows: {caption}]`，caption path/query/URL 不进 content；
6. 不启动 MemOS vision pipeline。

官方 `evaluation/scripts/locomo/locomo_ingestion.py` 的“双 user_id + 正反 role 双写 + 双路
检索合并”是 LoCoMo reproduction harness。它把同一 source 写两遍，改变 build 数量、namespace
拓扑和 retrieval fusion，不能暗混入跨五 benchmark 的主 product profile。未来若复现，只能建
显式 author implementation variant；本卡不实现。

canonical 空白 turn 已在 benchmark 层处理；若 event content 为空或 image helper 后仍为空，
adapter fail-fast，不把空消息送进 upstream `if content:` 丢失 time/message_id 的分支，也不
制造非空 placeholder。

### 4.5 Search/readout

retrieve 只调 typed `SearchHandler.handle_search_memories()`，请求必须显式：

```text
query                  public query_text
user_id                namespace
readable_cube_ids      [namespace]
mode                   fast
top_k                  query.top_k
relativity             0.45
dedup                  mmr
rerank                 true
include_preference     false
search_tool_memory     false
include_skill_memory   false
neighbor_discovery     false
internet_search        false
chat_history           []
filter/session_id      None
reference_time         query.question_time
```

不得把 private answer/evidence/answer_session_ids 放进 request。`reference_time` 在 v2.0.25
schema 存在但 current search code 未消费；仍忠实传入 question time，并在公开 metadata 写
`reference_time_effect="declared_but_unwired_v2.0.25"`，不得宣称时间过滤已生效。

patch 把 `_search_text()` 的 catch 改为记录后 re-raise；合法 backend `[]` 仍是 zero-hit。非法
search mode 也 fail-fast，不返回 `[]`。这只改变失败可见性，成功结果、顺序和内容零变化。

解析 `SearchResponse.data["text_mem"]` 的产品 bucket，按产品返回顺序扁平化 memory：

- `item_id` 取真实 memory id，缺/空 fail-fast；
- `content` 取真实 `memory` 文本，缺/空 fail-fast；
- `score` 取 `metadata.relativity`，None 合法，非数值 fail-fast；
- `timestamp` 取公开 created/updated/source time 中有一手定义的字段；不清楚就 None，不猜；
- `source_turn_ids` 只可从 current `metadata.sources[].message_id` 读取并保持顺序去重；
- metadata 保留公开 memory_type、sources、score/time 等审计字段，移除 embedding 和内部
  不可序列化对象。

`formatted_memory` 只按产品返回顺序连接 memory text，不调用 MemOS chat/answer prompt；零命中
使用 framework 非空 sentinel。不要按 score 二次排序、set 化或偷偷截断第二次。

### 4.6 RetrievalEvidence 与 HaluMem

首版逐题统一：

```text
semantic_provenance.status = pending
provenance_granularity      = none
reason_code                 = memos_generated_memory_semantic_lineage_unverified
stable_ranking.status       = pending
reason_code                 = memos_product_rerank_stability_unverified
```

理由必须说明：MemOS fine memory 是 window 生成物，`sources[].message_id` 证明 source
参与窗口，不证明生成后的 current memory 仍语义承载每个 source fact；真实
Neo4j/Qdrant + MMR/rerank 的稳定次序也尚未完成 B11 一手验证。不要因 `source_turn_ids`
存在就把 Recall/NDCG 升成 valid；zero-hit 也不改变这一静态事实。

因此 registration：

```text
provenance_granularity = none
retrieval_evidence_contract_version = v1
```

HaluMem：

- QA 可通过普通 retrieve + framework reader，保持候选能力；
- extraction：`session_memory_report=false`。async handler 没公开 task-scoped fine output，
  本卡不改算法/handler 返回值强行取出，诚实 N/A；
- update：普通 `memory_update_probe` 可检索 current memory，但 metric 资格仍待真实 DB smoke；
  不在 adapter 另写 top-k 特判，忠实使用 `query.top_k`；
- memory type：N/A，MemOS `Working/LongTerm/User/Outer` ontology 不等于 HaluMem
  Event/Persona/Relationship。

不得为了补满四格切 sync/fine、读内部临时变量、用 fast raw memory 冒充 session fine output
或从日志解析 memory。

### 4.7 Clean retry

注册 conversation 级 `clean_failed_ingest_state`。只允许：

```text
DeleteMemoryRequest(
  writable_cube_ids=[namespace],
  user_id=namespace,
)
→ handle_delete_memories
→ data.status 必须 == success
→ handle_get_memories(
     mem_cube_id=namespace,
     user_id=namespace,
     include_preference=false,
     include_tool_memory=false,
     include_skill_memory=false,
   )
→ text_mem 为空且 total_nodes==0
```

清理前须确认本 process tracker 没有该 namespace 的 pending task；否则拒绝删除。绝不调用
`delete_by_memory_ids()`，绝不无 namespace 清全库，绝不把 handler 返回 failure 当成功。

clean hook 与 factory 必须复用同一套 config/namespace 算法；不要悄悄 `init_server()` 两次。
若 resume clean 发生在 provider 构造前，允许实现一个进程内、按完整 config identity
单例的 runtime owner，但必须：

- 同 config 复用；
- 冲突 config fail-fast；
- thread-safe；
- tests 后可确定性 cleanup/reset；
- 不跨 run 复用已关闭 runtime。

若 current framework 调用顺序无法在不引入不受控全局 runtime 的前提下闭合，停工交回，不用
直接访问 graph store 绕开 typed handler 语义。

### 4.8 Identity 与观测

adapter version：

```text
memos-v2.0.25-product-v1
```

source identity 必须含 upstream URL、tag、commit、patch logical path + SHA-256、adapter
logical path + SHA-256、实现身份 `typed-product-handler`；不得声称 native LoCoMo harness。

build identity：

```text
implementation_variant = product
embedding_profile = controlled_embedding_v1
embedding = sentence_transformer / models/all-MiniLM-L6-v2 / 384 /
            local_unpinned / internal_l2-or-source-proven-value / cosine
historical_controlled_build_equivalent_to_current_main = false
```

若 current SenTranEmbedder 是否归一化无法从 source 证明，`normalization=None`，不要猜
`internal_l2`。

注册 `requires_api=true`，模型 inventory 至少区分：

- MemOS memory build/extraction LLM：`gpt-4o-mini`；
- local sentence-transformer embedding：MiniLM 384；
- cosine-local reranker：本地算法，不伪装成 LLM。

本卡只要求 runtime/manifest/model inventory 与 framework 已有 build-total/retrieval latency
可观测。MemOS current `OpenAILLM.generate()` 返回纯文本并丢掉 response usage，且 async worker
脱离 framework question context；不得用 add pair 数或 `len(text)/4` 伪造 exact API usage。
把精确 per-call token/cost 记为 M5 preflight 的公开 pending，不在本卡扩大 upstream patch。

## 5. 必测强反例

### 5.1 Patch/config/runtime

1. patch reverse/forward/idempotent，fetch 仍只 apply 一次；
2. clean checkout + patch 与 current nested tree逐字一致；
3. `sentence_transformer` config 精确字段；unknown backend fail-fast；Ollama/universal 既有分支
   字节/对象守恒；
4. search backend 抛错会传播，真实 `[]` 保持合法，unsupported mode fail-fast；
5. lazy import 不触发 `server_router`；config 环境成功/失败都恢复，secret 不进 manifest；
6. provider 只 `init_server()` 一次，Add/Search handler 共用同一 dependencies/runtime/tracker；
7. conflicting runtime config 与已关闭 runtime 复用 fail-fast。

### 5.2 Lifecycle/runner

1. 一个 SessionBatch 只发一个 APIADDRequest、一个 business task、恰好一条 MEM_READ；
2. add 返回后 task 尚未完成不会提前返回 ingest；
3. failed/timeout/missing/multiple terminal 传播；
4.合法零抽取成功；
5. cleanup pending 拒绝；无 pending 时 scheduler.stop 恰一次；重复 cleanup 不二次 stop；
6. generic shared v3 provider 在 run success、ingest failure、answer failure 各 cleanup 一次；
7. isolated worker v3 provider success/failure 各 cleanup 一次；
8. legacy system 与 operation-level runner 不产生新增 cleanup/double-clean；
9. cleanup 自身失败可见，不能留下 completed summary。

### 5.3 五格生产输入

复用五家 canonical fixture/生产 event builder，不手造一个与生产脱节的“漂亮 Conversation”：

- **LoCoMo**：speaker_a 首发与 speaker_b 首发；固定 A/B role 不漂；真实 speaker 前缀；
  session time；正文+caption/caption-only/多 caption/空 caption；无双写/第二 cube/vision；
- **LongMemEval**：assistant-first、连续同 role、singleton、奇数尾、blank 已被 canonical
  drop；同 session 一个 batch；逐 turn time/session fallback/None；不排序、不 placeholder；
- **MemBench**：FirstAgent user/assistant child 与 ThirdAgent user-only；0-10k 尾部 place/time
  原文不删且 chat_time 被提取；100k noise `chat_time=None`；question_time 不进 ingest；
- **BEAM**：正常 pair、10M 两个已知 dangling/mismatched window；原 role/order逐条保留；
  canonical turn id 进入 message_id；不按 raw id 重排/配对；
- **HaluMem**：整 session 一批、session-local task；QA/update retrieve 可达；
  extraction 无 session report、memory-type N/A，不泄漏 gold point/answer/judge label。

每格都断言：每个 canonical 非空 event 恰好一次、无跨 session、无 private key、role/content/
chat_time/message_id 的最终 `APIADDRequest` payload 精确。

### 5.4 Retrieve/metric/clean

1. APISearchRequest 的 namespace、top_k、六个关闭开关、空 chat_history、reference_time 精确；
2. 两个 bucket/多 memory 按产品顺序扁平化；无二次排序/截断；
3. id/content 缺失、非数值 score、非法 bucket shape fail-fast；
4. embedding/不可序列化对象不进 artifact；
5. zero-hit 返回 sentinel + `items=()`，backend failure 不得走 zero-hit；
6. sources 中重复 message_id 稳定去重，但 evidence 仍 pending/none；
7. 五个 benchmark 的 recall/rank evaluator 消费本 evidence 后为 pending/N/A，不得产生 0 分；
8. clean 只删目标 namespace，handler failure、readback 非空、pending task 全部拒绝；
9. namespace 在 run/conversation 之间隔离且不含绝对路径。

### 5.5 Registry/manifest/resume

1. `list_methods()` 含 `memos`，profile 只有 smoke/official-full；
2. protocol v3、consume=session、provenance=none、retrieval evidence v1；
3. `requires_api=true`、workers=1、禁止 smoke worker override、禁止 isolated multi-instance；
4. config/source/patch/adapter/build/model inventory 落 manifest，secret 与绝对路径为零；
5. adapter version、patch hash、embedding/model/search/lifecycle 参数任一变化都 resume mismatch；
6. 五个 registered-prediction fake chain 至少各一条穿过通用 runner，不建 method×benchmark
   runner。

强反例不能只断言自写 fake 的字段；patch 行为穿过 current MemOS 真实函数，framework 行为穿过
真实 registry/runner/adapter boundary。允许 fake 外部 I/O 叶子，不得 stub 掉被测的 MemOS
handler/patch catch 或 framework aggregator。

## 6. 停工条件

任一情况保存证据、提交已完成的自包含 note 后停工：

- current source 推翻 §4 锁定身份；
- 必须改变 async success path、reader/extraction/search/rerank 算法才能接入；
- 必须扩 allowlist；
- source lock/patch/nested dirty 无法解释；
- clean retry 无法做到 namespace-scoped + readback empty；
- generic cleanup 会破坏 legacy/operation-level 语义且 15 分钟内不能消解；
- 需要真实 API/DB/模型/网络才能验证本卡承重逻辑；
- private label 可能进入 method；
- 一手矛盾 15 分钟内无法闭合。

不要把“真实服务隔离、stable ranking、精确 token usage 仍 pending”当停工；这些本来就是 M5
入口，不得提前伪造为 valid。

## 7. 自检

只跑一次直接相关集合：

```bash
uv run pytest -q \
  tests/test_memos_lifecycle.py \
  tests/test_memos_adapter.py \
  tests/test_memos_registered_prediction.py \
  tests/test_method_registry.py \
  tests/test_prediction_runner.py \
  tests/test_prediction_cli.py \
  tests/test_documentation_standards.py
git diff --check
```

不跑全量 pytest、compileall、真实 API 或服务。若某个大测试文件可用 node id 精确收窄到本卡
新增/直接受影响用例，优先在 implementation note 写明 node id 后收窄；不得只跑新文件而漏掉
shared runner/registry 回归。

对 config/search 两个新增 patch hunk与 generic cleanup，至少做一次 mutation：

- 去掉对应修复时强反例转红；
- 恢复后转绿；
- 把失败测试名写入 note；
- 临时变体不提交。

commit 前只显式 add §3 的真实改动路径，过目 `git status --short`，不得
`git add -A/.`。

## 8. 实现记录与回报

implementation note 至少写：

- exact source/patch/adapter identity；
- runtime/handler/namespace/lifecycle 图；
- 五格最终 payload 矩阵；
- search result → RetrievalResult 字段映射；
- clean retry 前后置条件；
- metric valid/N/A/pending 矩阵；
- dependency/service/real smoke pending 清单；
- mutation 结果与定向测试尾行；
- 所有偏差与停工点。

按 `actor-handbook.md` §4 回报：

1. commit hash；
2. 定向测试尾行原文与 `git diff --check`；
3. 实际改动文件；
4. patch 新增函数与 success-path 守恒判词；
5. 五格 payload/metric 结论；
6. 偏差/停工点；
7. subagent 使用；
8. 实际模型/入口及切换；
9. `READY_FOR_MEMOS_M5_PREFLIGHT` 或 `BLOCKED`。

到此停止：不 push、不清 worktree、不更新 README/roadmap、不启动服务、不写 B11 命令。
