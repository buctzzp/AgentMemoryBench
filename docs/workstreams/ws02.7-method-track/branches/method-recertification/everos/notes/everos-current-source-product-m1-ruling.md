# EverOS current source / product / official harness M1 裁决

日期：2026-08-02
状态：`ARCHITECT_ACCEPTED_READY_FOR_M2`
范围：锁 current stable source、公开算法依赖、官方 benchmark 覆盖、产品 surface 与 M2
边界；本批不实现 adapter、不调用模型/API、不宣称真实 smoke 或冻结完成。

## 1. 结论

EverOS 主轨采用官方 **EverOS product service**，但不额外启动 HTTP host：在隔离 worker 内
进入官方 FastAPI lifespan，直接调用与 `/api/v2/memory/add|flush|search|get` 相同的 typed
DTO 和 service functions。这样保留 ingest、boundary、Episode、Cascade、OME、SQLite、
LanceDB 与搜索算法的真实产品调用图，同时去掉无关的 socket/port 层；直接调用 EverAlgo
research stages 或自己写入 Markdown/LanceDB 都属于机制绕行，不进入主轨。

source gate 通过。EverOS 本体和它锁定的 `everalgo-*` 算法包都能在同一官方组织的 Apache-2.0
仓库找到对应源码 tag；不是 Supermemory 那种只能下载不可审 runtime binary 的情况。

官方证据必须分三层：

1. current EverOS repo 有一个 LoCoMo **产品 HTTP harness**；
2. EverAlgo `benchmarks/v93.05` 有一个 LoCoMo **research direct-algorithm harness**；
3. 论文报告 LoCoMo、LongMemEval、PersonaMem-v2，但 current 两个公开 repo 只有 LoCoMo
   dataset adapter。LongMemEval 的论文数字是真实作者结果，公开最终 payload 却不可得。

因此 Phase 1 五格中 LoCoMo 是 official-covered；LongMemEval 是
`paper-reported / public-harness-unavailable`；HaluMem、BEAM、MemBench 是 framework
extensions。不得把论文表格、current product harness 和 research reproduction harness 拼成一条
并不存在的“完整官方复现链”。

## 2. Current source lock

### 2.1 EverOS 产品仓库

- upstream：`https://github.com/EverMind-AI/EverOS.git`
- local-only vendored path：`third_party/methods/EverOS`
- latest stable：`v1.2.1`
- commit：`4256419595f63fe307147dc19e379477cecdc44f`
- package：`everos==1.2.1`，Python `>=3.12`
- license：Apache-2.0；`LICENSE` SHA-256：
  `748007f17980117469390a385c37423c4bea2b0627cb6be00be315f9e64fc020`
- patch：无；本项目不得把 benchmark 适配直接改进 nested tree，除非 M2 证明存在无法从公开
  product extension/观测 sidecar 关闭的缺口并另行留痕。

2026-08-02 现场 `origin/main=6d62ecbd6f7e2cf96cd162d5ead14ce07a2037ab`，比稳定 tag 多四个
commit：文档/示例、安全说明和 `everalgo-user-memory/agent-memory 0.4.0` 依赖升级；没有
EverOS `src/` 产品逻辑 diff，但依赖升级会改变算法身份。主轨因此锁**最新稳定 release**，不追
未发布 main。

`v1.2.1` 还包含对 `v1.2.0` regression/CWE-22 的正式修复线，并把 embedding/rerank 改为
分层 soft capability；锁旧 `v1.1.3` 或有已知回归的 `v1.2.0` 均无理由。

承重文件 SHA-256：

```text
252586cd...  pyproject.toml
8188863c...  benchmarks/run.py
67844972...  benchmarks/config.toml
3ea2b4bc...  src/everos/service/memorize.py
19ab8e7c...  src/everos/service/search.py
d78599b7...  src/everos/memory/search/manager.py
d1c976da...  src/everos/memory/search/agentic.py
903ffa79...  src/everos/entrypoints/api/routes/memorize.py
a600ed61...  src/everos/memory/search/dto.py
```

完整 64 位 hash 以本地 `shasum -a 256` 与 source commit 为准；本表只用于快速漂移定位。

用户放入 `third_party/methods/EverOS/EverMemOS.pdf` 的论文附件保持 local-only、未跟踪；它是
论文证据，不改变 nested source identity，也不得由 fetch/cleanup 删除。

### 2.2 EverAlgo 算法源码不是黑箱

EverOS `pyproject.toml` 明确把算法拆为 PyPI 包；`uv.lock` 锁 sdist/wheel hash。官方
`https://github.com/EverMind-AI/EverAlgo.git` 为 Apache-2.0 monorepo，以下 runtime 版本均有
公开 tag/source：

| package | EverOS lock | official source tag / commit |
| --- | --- | --- |
| everalgo-user-memory | 0.3.2 | `everalgo-user-memory/v0.3.2@0b4b5874` |
| everalgo-agent-memory | 0.3.1 | `everalgo-agent-memory/v0.3.1@1b0fcf6` |
| everalgo-rank | 0.4.1 | `everalgo-rank/v0.4.1@673ace5` |
| everalgo-knowledge | 0.1.1 | `everalgo-knowledge/v0.1.1@61e9ff9` |
| everalgo-boundary | 0.2.1 | `everalgo-boundary/v0.2.1@088102d` |
| everalgo-clustering | 0.2.1 | `everalgo-clustering/v0.2.1@088102d` |
| everalgo-core | 0.3.0 | `everalgo-core/v0.3.0@1152725` |
| everalgo-parser | 0.2.1 | `everalgo-parser/v0.2.1@088102d` |

例如 `everalgo-user-memory 0.3.2` 的 sdist SHA-256 是
`9aa66a29dbd53176fe99a6482ca4d428158e085d146e14830e44cdd7a67840d6`；其余包同样以
EverOS `uv.lock` 的完整 hash 为安装校验，不靠本摘要截断值。实际恢复由该 lockfile 完成，M2
的 source identity 必须同时记录 EverOS commit、上述 package version 和 lockfile hash。
EverAlgo 无需再复制为第二个长期 nested tree，避免制造两份可漂移源码；公开 tag 是审计锚，
PyPI hash 是运行锚。

## 3. B0：官方 benchmark 覆盖

### 3.1 Current EverOS LoCoMo product harness

`third_party/methods/EverOS/benchmarks/run.py` 是 current `v1.2.1` 唯一 benchmark runner。
它只加载 LoCoMo；未出现 LongMemEval、HaluMem、BEAM 或 MemBench adapter。

最终 payload（不是 README 概述）为：

| 维度 | current product harness |
| --- | --- |
| surface | HTTP legacy alias `/api/v1/memory/add|flush|search`；v1/v2 挂同一 router，current canonical 是 v2 |
| runtime | README 要求 `[memorize] mode="chat"`，关闭 foresight/profile，保留 Episode、atomic facts、clustering |
| ingest unit | 每 LoCoMo session 独立 `session_id`，25 messages/add，session 末 flush |
| role/owner | 两位真实 speaker **全部 role=user**；`sender_id=<speaker>_conv<N>`，`sender_name` 保留原名 |
| content/image | 只用 `text`；空 text（含 image-only）直接跳过，`blip_caption` 不进入 payload |
| time | session time 按 UTC 解析；第 i 条人工加 `i*30s` |
| isolation | `app_id=locomo_benchmark`，`project_id=run_name`，owner 为 speaker+conversation |
| completion | add+flush 后轮询 Cascade 与 OME SQLite，连续两次 pending=0；OME failed 直接失败 |
| search | 默认只搜 `speaker_a` owner；`method=agentic`，`top_k=10`，不带 filters/profile |
| answer/judge | answer GPT-4.1-mini、temp 0、max_tokens 32768；judge GPT-4o-mini、temp 0、3 runs |
| smoke | 2 conversations；每个前 50 条消息；每个 10 QA；judge 1 run |

该 harness 对 LoCoMo 的 role/owner 与 search-owner 选择是必须显式记录的作者产品口径，但它的
caption 丢失与固定 30 秒属于 current harness 行为，不自动成为 framework 主配置的“正确数据
语义”。

### 3.2 EverAlgo LoCoMo research harness

EverAlgo official tag `benchmarks/v93.05` 指向
`fe7eaccd7c9db37f61ed7a9db0728d2b0c324bfe`，包含 LoCoMo 93.05 复现结果。它直接调用
EverAlgo stages，不经过 EverOS product service/storage：

- 两位 speaker 仍全部映射 `role=user`，保留 `sender_id/sender_name`；
- image 渲染为 `[{speaker} shared an image: {caption}] {text}`；
- 每 session 优先 30 秒间隔，若会越过下一 session，则压缩到可用间隔的 90%；
- boundary → Episode/AtomicFact → clustering/index → agentic retrieve → answer → judge；
- Qwen3-Embedding-4B，server-side `dimensions=1024`；Qwen3-Reranker-4B；
- clustering threshold 0.70，max gap 7 天，cluster top-k 10，最终 episode top-k 10；
- answer GPT-4.1-mini、temperature 0.3、max_tokens 16384；judge GPT-4o-mini、temperature 0、
  3 runs。

产品 harness 与 research harness 的 caption、时间 spacing、answer decoding 与调用面并不相同。
`author_locomo` 在 M2 只能选择并声明一个复现目标；不得把两边各取有利项后仍叫“官方原样”。

### 3.3 论文报告不等于公开 harness

用户提供的 `EverMemOS.pdf` 报告：LoCoMo、LongMemEval、PersonaMem-v2；Phase 1 只关心前两者。
Appendix A.1 明确：

- LoCoMo / LongMemEval clustering threshold 分别 0.70 / 0.50；max gap 7 / 30 天；
- dense Qwen3-Embedding-4B + BM25 RRF，Qwen3-Reranker-4B；
- top-10 MemScenes，再选 10 Episodes；
- 默认是 Episodes-only Memory-Augmented Reasoning；
- final answer backbone 统一；judge 为 GPT-4o-mini，多次评判。

但 current EverOS 与 EverAlgo 公开树都没有 LongMemEval loader、角色处理、batch、namespace、
time fallback、answer builder 或完整最终 payload。故它是 `paper-reported`，不能创建一个声称
完整复现的 `author_longmemeval` section；只可在未来拿到公开 harness 后解锁。

### 3.4 Phase 1 唯一分类

| Benchmark | 官方证据 | M1 分类 |
| --- | --- | --- |
| LoCoMo | current product harness + research `v93.05` | official-covered；M2 需选清 author target |
| LongMemEval | 论文 Table 2 / Appendix 参数，无公开 payload | paper-reported，public author harness pending；主轨为 framework extension |
| HaluMem | 无 | framework extension |
| BEAM | 无 | framework extension |
| MemBench | 无 | framework extension |

## 4. 产品 surface 裁决

### 4.1 主轨：typed product service inside official lifespan

`create_app()` 的 lifespan 顺序启动 LLM、SQLite、LanceDB、Cascade、OME 等官方组件；HTTP v2
route 只是 Pydantic validation + service dispatch。M2 使用同一 DTO 和
`everos.service.memorize/search/get`，并进入 `app.router.lifespan_context(app)`：

```text
prepare -> create_app -> lifespan enter
ingest  -> MemorizeAddRequest -> service.memorize
finalize(session) -> MemorizeFlushRequest -> service.memorize(is_final=True)
drain   -> Cascade + OME exact terminal
retrieve -> SearchRequest -> service.search
session readout -> GetRequest -> service.get
cleanup -> lifespan exit + isolated root removal/tombstone
```

它与 HTTP 共享业务实现，不需要 uvicorn、端口和 auth。分类
`TRANSPORT_EQUIVALENT_PRODUCT_SURFACE`，不是另写算法。

### 4.2 明确排除

- 直接调用 EverAlgo benchmark stages：research calibration，不是 current product storage/lifecycle；
- 直接写 Markdown/LanceDB/SQLite：`MECHANISM_BYPASS`；
- 让 EverOS 自带 answer prompt 参与主表：违反 framework reader 隔离；只可放
  `author_locomo`；
- 只调用 add 后 sleep：不能证明 Cascade/OME 完成；
- 启动 HTTP host：功能可行，但为同一 typed service 额外引入端口、进程和网络故障面。

## 5. 主配置与 author 配置边界

跨五 benchmark 的 `smoke` / `official_full` 必须固定同一产品配置，不按 benchmark 暗调参数：

- `memorize.mode=chat`：五家都是对话 memory，不启用 agent case/skill；
- Episode + atomic facts + clustering；foresight/profile 关闭；reflection 保持官方默认关闭；
- 搜索主候选用 public default `hybrid`，adapter 把 `query.top_k` 传给产品，不在外层二次截断；
- build LLM、embedding、distance、dimension、rerank/runtime 身份全部进 manifest；
- framework 自带 benchmark answer/judge builder。

LoCoMo `author_locomo` 必须在 M2 明确选择 current product harness 或 research 93.05 作为唯一
目标。当前建议：产品 adapter 的 author section 对齐 **current product harness**（agentic/top10/
batch25/单 owner/官方 builder），同时显式声明它不等于 paper 93.05 direct-algorithm pipeline；
research 93.05 保留为效果校准证据，不绕 product service 进入主矩阵。

LongMemEval 只有 paper 参数（0.50/30 天），没有完整 public harness；暂不创建
`author_longmemeval`。HaluMem/BEAM/MemBench 不创建 author section。

## 6. 输入、owner 与时间：M2 不能跳过的门

### 6.1 原生粒度

产品 `/add` 接受 1..500 条 messages，boundary buffer 以 session_id 聚合，`/flush` 关闭 session
tail。主轨候选 `consume_granularity=session`；adapter 内可按固定 batch size 分多次 add，但只在
canonical session 末 flush，禁止跨 session 配对或合并。

assistant-first、连续同 role、singleton、odd tail 都可进入 chat boundary。真正的产品约束是：
UserMemoryPipeline 只把 `role=user` 的 sender 作为 Episode owner；assistant-only cell/session
没有 owner，不会写 Episode。M2 必须用生产链反例裁定 assistant-only LongMemEval/BEAM 形状：
要么证明无损空 user anchor，不把 placeholder 当事实；要么明确 role-preserving 路径的能力缺口；
不得静默把 assistant 改成 user 或伪造一句自然语言回复。

LoCoMo 不是 user/assistant 对话。official path 已锁“所有 speaker role=user + 原 sender identity”；
M2 应沿用，并验证单 owner 检索是否会漏掉只归属于另一 speaker 的 cell。若改为双 owner 检索合并，
必须标 framework extension；若按官方只搜 speaker_a，必须把这一差异写入 main/author 身份。

### 6.2 时间

`MessageItemDTO.timestamp` 强制 Unix milliseconds 且 `>0`；内部 message id 也含 timestamp。
本项目 source-time 裁决则要求 missing time 保持 None，禁止偷用 question、相邻 session、墙钟或
未标注的人工序号。

所以 MemBench 100k missing-time 是 M2 硬停点：不能直接塞 0（DTO 拒绝），也不能把人造排序
时间冒充 source time。可接受方向只有两种：

1. 纯 transport-operational timestamp，稳定、单独命名/manifest，source-time sidecar 仍为 None，
   readout 不渲染成人类事实；必须证明算法不会把它当真实时间做 clustering/answer；或
2. 最小产品扩展让缺失 timestamp 可达并保持 None，若全算法/storage 强依赖 datetime 则判不可行。

在 production-path probe 证明前，本门保持 PENDING。

### 6.3 content、place 与 image

- canonical content 原文不删除；MemBench 尾部 place/time 继续留在 content，结构化 time 另传；
- LoCoMo 使用项目共享 `[Sharing image that shows: {caption}]` 契约，保留原 text；current product
  harness 的 caption 丢失是 upstream harness drift，不作为主轨损失；
- `img_url`、query、gold、evidence、judge labels 不进入 memory content；caption 是 benchmark
  已公开语义，不是私有 gold。

## 7. Retrieval、ranking 与 provenance 初判

`SearchManager` 明确是 read-only；user owner 的 product readout 是 ranked Episodes，HYBRID 会
并行 sparse+dense、RRF/hierarchy、按 score 降序输出，positive `top_k` 直接控制最终最大条数。
adapter 不得重排、跨 owner 合并后偷偷超出 k，zero hit 与 backend failure 必须区分。

Episode DTO 有 `id/session_id/timestamp/sender_ids/score`，但没有 source message ids；内部 Episode
Markdown/LanceDB row 保留 `parent_id=memcell_id`，SQLite memcell ledger 保留原 message ids。
reflection 默认关闭时，可用**纯观测 sidecar**把 Episode → memcell → canonical source turn ids
闭合，而不改写 memory 内容或 rank。这只是 `valid candidate`：M2 必须证明跨 add batch、flush、
Cascade、W2/resume 后仍一一可达，且 merged/reflected episode 自动降 N/A。

按 benchmark 的初始资格：

| 能力 | M1 初判 |
| --- | --- |
| stable product ranking | valid candidate；M2 锁 tie/order/top-k/owner merge |
| LoCoMo/MemBench turn provenance | valid candidate；依赖 Episode→memcell→message sidecar |
| LongMemEval | 至少 session provenance candidate；turn exact 取决于 cell lineage 与 gold group |
| BEAM | gold 是单 message，但产品 Episode 是 cell；先 pending，不为填表强行宣称 turn exact |
| HaluMem extraction | valid candidate；flush+drain 后 `/get episode` 按 session_id 读 session delta |
| HaluMem update / QA | valid candidate；读取 current product Episode/search |
| HaluMem memory_type | N/A candidate；Episode/Profile 不能偷换 Event/Persona/Relationship gold taxonomy |

## 8. Completion、isolation、resume 与观测门

### 8.1 exact completion

`memorize()` 返回只证明 boundary + Episode Markdown 同步阶段完成；atomic fact、clustering、Cascade
索引和 OME 是后台工作。official harness 轮询两个 SQLite DB，但使用“两次空闲”启发式。M2 要
把 task scope、terminal/failure、迟到任务和 shutdown 全部锁死；不能只 sleep，也不能在失败后
把半写 state 标 completed。

### 8.2 isolation / W2

EverOS 的 settings、LLM/embedding/rerank capability、service manager、SQLite/LanceDB connection
和 OME/Cascade 都是进程全局 singleton。主轨因此必须每个 provider 独占 worker process 与
`EVEROS_ROOT`；app_id/project_id/owner_id 继续做逻辑过滤，但不拿逻辑过滤冒充进程资源隔离。
W2 只有在两个 worker/root/DB/lifespan 实证独立后才 valid。

产品无 user-memory namespace-safe delete endpoint；clean 不能用不带 scope 的内部批量删除。
最窄方案是独占 root 的物理清理，先正常退出 lifespan，再 tombstone/rmtree root；失败时保留引用
允许 clean retry，不能先标 cleaned。

### 8.3 observability / retry

M2 必须枚举 boundary、Episode、atomic fact、agentic rewrite/sufficiency、embedding、rerank 的全部
外部调用；通过 client wrapper 记录真实 usage/latency/scope，不估算。OpenAI-compatible build
LLM 可接 smoke `opencodego/deepseek-v4-flash`；embedding/rerank 是否由同一 provider 支持不得
猜，需在预算批准前只做能力预检。secret/base URL 不落 manifest/error。

## 9. M2 强制门

1. 独占 worker/root + official lifespan + typed service，证明不启动 HTTP host且调用图等价；
2. 五格 final payload 强反例：LoCoMo owner/role/caption/time，LME role 异形，MemBench
   first/third/place/missing-time，BEAM variants/orphan，HaluMem fixed session；
3. assistant-only owner 与 MemBench missing-time 两个承重停点先裁定，禁止靠“能跑”掩盖；
4. Cascade+OME exact scoped drain、failure propagation、cleanup retry、crash/resume；
5. Search 全层 readout、top-k/order/score/zero-hit/backend error；
6. Episode→memcell→message lineage sidecar与 merged/reflection fail-safe；
7. HaluMem extraction/update/QA/type 四格分别判，不把 `/get` 全库列表冒充 session delta；
8. model/runtime/source/transport/配置全部进入 manifest；
9. build/embedding/rerank exact observations，answer/judge 复用 framework；
10. 生成 machine smoke plans、跑定向+full+compileall 后才请求真实 API 预算。

最终判词：

```text
READY_FOR_EVEROS_M2(
  latest stable EverOS and exact public EverAlgo source are locked;
  only LoCoMo has a public official harness;
  LongMemEval is paper-reported but public-payload unavailable;
  the main surface is typed product service inside the official lifespan;
  assistant-only ownership, missing timestamps, exact drain, lineage,
  isolation and five-grid payload remain implementation gates
)
```
