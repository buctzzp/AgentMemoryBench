# Actor 卡：MemOS v2.0.25 产品运行时契约 M1

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本批只审计 source-locked MemOS `v2.0.25` 当前 self-host 产品路径的
运行时契约，并把一手证据写成自包含 note；不调用真实 API，不启动服务，不修改生产代码。
actor 可自行组织 subagent，但不得扩大允许范围；主 actor 必须亲核所有承重锚并对最终报告
负责。

## 0. 目标、边界与唯一判词

本卡不是再查五个 benchmark，也不是写 adapter。五个 benchmark 的 raw/canonical/gold、
时间、图片、异常和 evaluator 契约已经冻结，本批直接复用。唯一目标是一次性回答后续五格
都会依赖的 MemOS 产品问题：

1. Phase 1 主配置应绑定哪个公开产品面与算法路径；
2. add 何时真正完成，scheduler 如何 drain，失败任务能否被误判成完成；
3. role、缺失时间、`message_id`、source lineage 在当前 active path 上如何流动；
4. search 返回的 memory、score、排序、source 与 top-k 是否足以支撑各类 metric；
5. cube/user/session 如何隔离和清理，失败 retry 是否会重复或串库；
6. HaluMem session-local extraction/update 是否有不扭曲算法的产品语义；
7. 真实运行需要哪些服务、模型和观测插桩。

最终只能给出：

```text
READY_FOR_ARCHITECT_M1_RULING(<已闭合能力 + 最小待裁项>)
```

或：

```text
BLOCKED(<由 current source 无法闭合的最小承重问题>)
```

actor 不代架构师选择最终 profile，不修改 B1-B11 状态，不生成五张 benchmark 卡。

## 1. 隔离环境与 source identity

- worktree：`/Users/wz/Desktop/mb-actor-memos-m1`
- branch：`actor/memos-v2-0-25-product-preflight`
- 基线：派发时的本地 `main`
- 官方源码为父仓库 gitignored 的 nested Git：
  `/Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS`

开工先现场核验：

```bash
git -C /Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS status --short --branch
git -C /Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS rev-parse HEAD
git -C /Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS describe --tags --exact-match
```

必须逐字命中：

```text
HEAD    e820406269537b97d270687e3e40eea2f015f81a
tag     v2.0.25
status  第一行是 "## HEAD (no branch)"，且没有任何变更条目
```

源码目录只读。可以从 worktree 建不入 Git 的只读软链方便检索，也可直接读绝对路径；不得
checkout、fetch、pull、安装依赖、修改或暂存 nested repo。身份不符立即停工。

## 2. 最小必读顺序

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊与当前动作
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/README.md`
4. `docs/reference/actor-handbook.md`
5. `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
   memos-v2.0.25-source-lock.md`
6. 本卡 §3 点名的 current source

以下旧审计只允许作为风险索引，不得引用旧行号证明 current 行为：

- `docs/workstreams/ws02-phase1-matrix/audits/memos.md`
- `docs/workstreams/ws02-phase1-matrix/audits/mechanism-memos.md`

禁止全文重扫 `docs/survey/`、五个 benchmark 数据或首批五家 method 历史；出现 method
输入需要 benchmark 例子时，只引用现有稳定文档中的最小例子。

## 3. 架构师已亲核的 current-source 承重事实

下列是本卡的锁定起点。actor 要逐项抽锚复核和补全运行时含义，不得重新把它们写成
“待探索的大问题”。任何一项被 current source 推翻，保存已完成证据后立即按停工条件回报。

### 3.1 产品面与算法

1. 当前 self-host `/product` 服务在
   `src/memos/api/handlers/component_init.py` 初始化 `SimpleTreeTextMemory`；默认 cube
   `text_mem.backend="tree_text"`，不是 `MOS.simple()` 的 `general_text`。
2. active reader 默认由 `MEM_READER_BACKEND="multimodal_struct"` 选择
   `MultiModalStructMemReader`；它继承 `SimpleStructMemReader` 的 chat coercion、滑窗与
   fine/fast extraction。
3. 官方 LoCoMo/LongMemEval 脚本走 `/product/add`、`/product/search`，可作为作者评测姿势，
   但不能覆盖当前产品 schema。

### 3.2 official harness 已出现的 drift

1. `evaluation/scripts/utils/client.py::MemosApiClient.add()` 仍发送 deprecated
   `mem_cube_id`、`conversation_id`，不发送 `async_mode`；
2. 当前 `APIADDRequest.async_mode` 默认 `"async"`；sync 下未显式 `mode` 才走 fine；
3. `lme_search.py::memos_search()` 向 `MemosApiClient.search()` 传
   `reference_time=...`，但该 wrapper 的签名没有该参数，当前脚本会在 Python 调用层
   `TypeError`；
4. 当前新字段是 add 的 `writable_cube_ids` 与 search 的 `readable_cube_ids`。

因此 official harness 只能证明作者的 speaker/session/batch 意图，不能逐字照抄为 current
产品 client。

### 3.3 add 与 scheduler

1. `SingleCubeView._process_text_mem()` 在请求线程内执行 reader extraction、写图数据库，再
   submit scheduler task；
2. async add 先写 fast memory，再提交 `MEM_READ`；sync add 先做 fine/fast extraction，再提交
   `ADD`；
3. scheduler 对象总会初始化；服务由 `API_SCHEDULER_ON`（默认 true）决定是否 start，
   这与 `MOS_ENABLE_SCHEDULER` 的配置字段不是同一个开关；
4. `/product/scheduler/wait` 按一个名为 `user_name` 的值查询 status tracker，但必须继续核清
   实际 key 是 request `user_id`、cube id，还是二者恰好相同时才成立；
5. wait 把 `completed/failed/cancelled` 都视为 idle，单看 `timed_out=false` 不能证明任务成功。

### 3.4 时间与 lineage 风险

1. `coerce_scene_data()` 若一组消息没有可用 `chat_time`，会注入当前 wall clock；同组只有部分
   消息带时间时，会把首个时间补给缺键的兄弟消息；
2. 显式 `chat_time=None` 仍会进入 wall-clock 默认分支，不是合法的 preserve-none；
3. `SourceMessage` 模型支持 `message_id`，user/assistant/system parser 也有相关字段；
4. 但 active chat 路径继承的 `SimpleStructMemReader._iter_chat_windows()` 构造 source dict 时
   当前只写 `type/index/role/chat_time/content`，看起来会在进入 memory item 前丢掉
   `message_id`；
5. fine extraction 将整个 window 的 sources 赋给窗口内抽出的每条 memory。即使修复
   `message_id` 传递，也不能自动把“参与生成”宣布成 fact-level semantic provenance。

## 4. 必须亲读的一手链

只读下列 current `v2.0.25` 文件及其直接调用点；若函数移动，用 `rg` 找 current 定义，不得
拿旧 note 行号代替：

### 4.1 产品构造与公开 schema

- `README.md` self-host 段、`docker/docker-compose.yml`
- `src/memos/api/config.py`
  - `get_reader_config()`、`get_product_default_config()`、
    `get_default_cube_config()`、scheduler/model/embedder 配置
- `src/memos/api/handlers/{component_init,config_builders}.py`
- `src/memos/api/product_models.py`
  - `BaseRequest`、`APIADDRequest`、`APISearchRequest`、
    `DeleteMemoryRequest` 与响应模型
- `src/memos/api/routers/server_router.py`

### 4.2 add、reader 与 lifecycle

- `src/memos/api/handlers/add_handler.py`
- `src/memos/multi_mem_cube/{single_cube,composite_cube,views}.py`
- `src/memos/mem_reader/{factory,multi_modal_struct,simple_struct}.py`
- `src/memos/mem_reader/read_multi_modal/`
- `src/memos/memories/textual/item.py`
- `src/memos/memories/textual/tree_text_memory/organize/`
- `src/memos/mem_scheduler/` 中与 `MEM_READ`、`ADD`、status tracker、queue key、失败状态和
  drain 直接相关的最小链

### 4.3 search、readout 与清理

- `src/memos/api/handlers/{search_handler,formatters_handler,memory_handler,
  scheduler_handler}.py`
- `src/memos/memories/textual/tree_text_memory/retrieve/`
- `src/memos/multi_mem_cube/single_cube.py` 的 fast/fine/mixture search
- delete/filter 实现及 cube/user/session 进入图数据库约束的直接调用点

### 4.4 作者评测姿势

- `evaluation/scripts/utils/client.py`
- `evaluation/scripts/locomo/{locomo_ingestion,locomo_search}.py`
- `evaluation/scripts/longmemeval/{lme_ingestion,lme_search}.py`
- `evaluation/scripts/run_{locomo,lme}_eval.sh`

只做 current harness 与 current product 的差量表；不运行它们、不读取数据全量。

## 5. 必须闭合的证据任务

可用 current source、已有 upstream unit tests和 hermetic fake/stub 探针。临时脚本只能放
系统临时目录，关键构造、命令和 stdout 必须逐字抄进 note；“见 Claude/Codex scratchpad”
不构成跨模型证据。禁止真实 LLM、embedding、Neo4j、Qdrant、Redis、Docker、HTTP 服务、
网络和模型下载。

### 5.1 产品身份表

画一张三行身份表：

| 路径 | 入口 | text algorithm | reader | 可作为 Phase 1 主产品吗 |
| --- | --- | --- | --- | --- |
| self-host product API | `/product/add` + `/product/search` | current source | current source | 证据判断 |
| library simple/default | `MOS` / `MOS.simple` | current source | current source | 证据判断 |
| official eval wrapper | HTTP wrapper | 实际落到哪个服务 | payload/mode | 只作何种参考 |

必须明确 `general_text` 与 `tree_text` 是算法路径差异还是单纯 storage variant；说明选择
self-host product 会带来的服务/依赖成本，但不要由 actor 最终裁 profile。

### 5.2 add 完成状态机

用同一张时序图或表写清：

```text
APIADDRequest
→ reader fast/fine extraction
→ graph write
→ add response material
→ scheduler task label/key
→ scheduler mutation
→ status tracker
→ /scheduler/wait
→ stable searchable state
```

强制回答：

1. sync+fine add 返回的 memory 是否只是当前 request 的 session-local extraction；
2. sync 的 `ADD` task 具体会做哪些 mutation，`reorganize=false` 时仍会做什么；
3. adapter 应等待 request `user_id` 还是 cube id；若官方代码命名与真实 key 不同，要用
   submit/status tracker 一手链判定；
4. wait 返回 idle 后如何检查 failed/cancelled，怎样才算强完成；
5. 连续 session 是逐 session drain、conversation end drain，还是 query 前一次 drain；
6. scheduler 未启动、task submit 失败、task 失败、wait timeout 的 fail-fast 行为；
7. add/flush/drain 各自的 LLM、embedding、DB 调用观测点。

不要用“最终搜得到东西”代替状态机闭合。

### 5.3 role、batch 与 placeholder 资格

对 active reader 做零 API、记录型 fake 探针或等价 current unit-test 取证，至少覆盖：

1. `user→assistant`
2. `user→user`
3. `assistant→user`
4. singleton user
5. singleton assistant
6. 三条奇数序列
7. 空 content
8. 缺 role/content 与未知 role

逐层记录：

```text
API messages
→ coerce_scene_data
→ chat window exact rendered text
→ extraction LLM exact payload
→ sources
```

裁清产品是否真的要求 pair、首 user、尾 assistant 或偶数长度。若不要求，明确写
“不得增加 placeholder”；若只因 prompt 质量偏好而非运行契约，也必须分开描述。

### 5.4 source time：不允许 wall-clock 偷渡

用固定 monkeypatch clock 或 current helper 的 hermetic 探针覆盖：

1. 每条消息有不同 source time；
2. 全组同一 session time；
3. 部分有 time、部分缺失；
4. 全部缺失；
5. 显式 `chat_time=None`；
6. 空串/非法格式；
7. 多次 add 的 clock 是否进入持久化 source。

写出缺失时间在 current product 中是否存在合法表达。若没有，只比较下面三种候选的
算法边界与最小改动面，不实施：

- benchmark-extension 兼容补丁：保留真正的 `None`；
- 以 deterministic method-order time 代替 source time，并在 artifact 中明确分层；
- 对缺时 variant 停止接入。

禁止提议把 question time、兄弟 turn time、当前时间或任意 sentinel 冒充 source time。

### 5.5 `message_id` 与 semantic provenance

必须把一个合成 canonical turn id 逐层追到：

```text
API message.message_id
→ coercion/parser
→ chat window source
→ extracted TextualMemoryItem.metadata.sources
→ graph DB serialization
→ scheduler evolution/merge/archive
→ search result
→ formatter response
```

分别回答：

1. current active path 的第一个真实 drop 点；
2. 只把 `message_id` 补入 source dict 是否属于纯观测/benchmark 兼容，是否改变算法；
3. merge/reorganize 如何合并、清空或重建 sources；
4. search/formatter 哪些路径保留 sources，哪些会清空；
5. 一个 memory 带整个 window sources 时，哪些只能声明 window/session lineage，哪些可以
   支持 turn-exact semantic provenance；
6. 对 LoCoMo/MemBench/BEAM 的 turn gold 和 LongMemEval 的 session/turn gold，给出
   `valid/N/A/pending` 的**候选依据**，但把最终 metric 裁决交回架构师。

项目铁律：source id 存在只证明参与生成，不等于 current memory 仍语义承载该 source fact。

### 5.6 search、top-k 与 stable ranking

构造 current search 数据流表，至少记录：

- request `mode/top_k/relativity/dedup/rerank/include_*` 的默认值；
- MMR/sim 扩大候选集、threshold、post-retrieve、enhance、dedup、rerank、最终 truncate 的顺序；
- 返回 memory 的 `id/memory/memory_type/relativity|score/sources/cube_id`；
- fast/fine/mixture 是否调用额外 LLM；
- preference/tool/skill 是否应在 Phase 1 主 readout 中关闭或隔离；
- multi-cube 合并的排序与 top-k 是 per-cube 还是 global。

必须判断：在固定配置与固定后端结果下，公开返回顺序是否足以先标
`stable_ranking=valid`，还是只能 `pending`；不得因为字段名叫 score 就自动宣布 NDCG 合格。

### 5.7 isolation、clean retry 与并行 worker

画出 request `user_id/readable_cube_ids/writable_cube_ids/session_id/task_id` 分别进入：

- reader metadata；
- graph namespace/filter；
- scheduler queue/status；
- search filter；
- delete filter。

回答：

1. 每个 benchmark sample 用唯一 cube + user + session 是否足够逻辑隔离；
2. 同一个 server 上两个 workers 使用独立 namespace 是否会共享 scheduler、默认 cube或检索
   候选；
3. create/register cube 是否是 add 前置，还是任意 cube id 可直接作为逻辑 namespace；
4. retry 前应先 drain/cancel 哪些任务，再按哪些精确约束 delete；
5. delete 是否覆盖 active、archived、working、preference 和 scheduler 尚未落地的任务；
6. 最安全的失败重跑是复用并清理旧 namespace，还是换全新 run namespace；
7. resume identity 必须落哪些产品字段。

### 5.8 HaluMem 与 metric 能力输入

本节只判 MemOS 产品能力，不重查 HaluMem 数据：

1. sync+fine add response 能否作为“只由本 session 输入产生”的 extraction report；
2. scheduler mutation 前后的哪个读出面才对应 HaluMem extraction；
3. update probe 能否在每次 session 后通过公开 search/get-memory 得到 current state；
4. QA 只消费公开 retrieve readout，是否无额外障碍；
5. product `memory_type` 是否能诚实映射 HaluMem Event/Persona/Relationship；若不是同一 ontology，
   必须 N/A，不按名称猜；
6. metric 资格按 extraction/update/QA/memory-type 四格分别写候选，不用一个总开关。

若产品没有 session-local extraction readout，直接判该格 N/A；不得为了评分去清空核心状态、
关闭必要 evolution 或改造算法为 session extractor。

### 5.9 服务、模型与效率观测

列出最小可运行拓扑和每一项的身份：

- MemOS API process；
- graph/vector/storage 服务；
- scheduler 是否需要 Redis；
- build LLM、general/process LLM、reranker、embedding；
- current product default 与项目主配置 `gpt-4o-mini`/待定 embedding 的差异；
- 每一类真实调用可插入 observer 的 current 函数/client 边界；
- 哪些调用可从已有 response/log 得到 token，哪些只能本地 tokenizer fallback。

不安装、不启动、不估算 dollar 成本；这里只给 B8/B11 的观测设计输入。

## 6. 唯一交付物

只新增：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-product-runtime-preflight.md
```

note 必须自包含，至少含：

1. source identity 原始输出；
2. 三路径产品身份表与 official harness drift 表；
3. add/scheduler 状态机；
4. role/batch 与 timestamp 探针构造及关键 stdout；
5. message-id/source/evolution/search 全链；
6. search/top-k/ranking 表；
7. isolation/cleanup 图；
8. HaluMem 四格候选；
9. 服务/模型/observer 表；
10. B1-B11 readiness 矩阵；
11. 明确列出“已闭合 / 最小待裁 / 后续实施候选”；
12. 唯一总判词。

不得修改 README、integration、survey、src、tests、configs、third_party、data、models、outputs、
policy 或 handbook。不得创建五份 benchmark note。

## 7. 停工条件

出现任一情况立即保留已完成证据并停工：

1. source identity 不是本卡锁定 commit/tag，或 nested worktree 不 clean；
2. §3 任一承重事实被 current source 实质推翻；
3. 必须调用真实 API、启动服务、联网、下载依赖/模型才能继续；
4. 需要修改算法 core 或允许清单外文件；
5. hermetic probe 20 分钟内无法消解依赖；此时静态链可标 pending，禁止伪造“实测通过”；
6. 同一公开字段在 add/search/scheduler 三处的含义互相矛盾且无法由 current source 判定。

发现 upstream bug 可以记录精确锚点和影响，不顺手修。

## 8. 自检、commit 与完成报告

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

只显式 `git add` 唯一 note，add 前后都查看 `git status --short`，不得 `git add -A` 或
`git add .`。本地 commit：

```text
docs(memos): audit v2.0.25 product runtime
```

不 push、不 amend、不跑全量 pytest/compileall、不读或软链 `.env`。

按 `docs/reference/actor-handbook.md` §4 回报：commit hash、自检尾行、实际改动文件、
偏差/停工点、subagent 分工，以及真实模型/入口和任何切换。到此停止，等待架构师 full diff、
定向复验与 M1 最终裁决。
