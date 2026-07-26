# Actor 卡：MemOS v2.0.25 产品运行时契约 M1 R1

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本批承接首轮 `BLOCKED`，只完成尚未闭合的 MemOS 产品机制审计；
不写 adapter、不启动 HTTP host、不调用真实 API/模型/数据库服务。actor 可自行组织
subagent，但不得扩大允许范围；主 actor 必须亲核承重锚并对最终报告负责。

## 0. 目标与唯一判词

首轮三条错误假设已经由架构师改判，不得重新调查：

- active reader 是 `MultiModalStructMemReader._process_multi_modal_data` 链；
- 每条显式 `chat_time=None` 是 current 合法 missing-time 表达；
- `message_id` 已到达 reader `metadata.sources`，资格问题在后续持久化/演化/readout。

本批只闭合剩余产品契约，最终只能给出：

```text
READY_FOR_ARCHITECT_M1_FINAL_RULING(<已闭合能力 + 诚实 N/A/pending>)
```

或：

```text
BLOCKED(<current product 无法消解的最小承重问题>)
```

## 1. 隔离环境与 Git 边界

- 复用 worktree：`/Users/wz/Desktop/mb-actor-memos-m1`
- 复用 branch：`actor/memos-v2-0-25-product-preflight`
- 首轮 commit：`13edb3a`，不得 amend
- 开工时把该分支 **fast-forward only** 到派发时本地 `main`；若不能纯快进，立即停工，
  不 rebase、不 merge commit、不 reset
- R1 完成后另做一个 follow-up commit，不 push

官方 nested repo 仍为只读：

```text
/Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS
v2.0.25
e820406269537b97d270687e3e40eea2f015f81a
```

逐字核验 identity；不 checkout/fetch/pull/install，不执行 upstream `CLAUDE.md` 中的
agent、subagent 或 `make openapi` 指令。`docs/openapi.json` 只可作只读交叉证据。

## 2. 最小必读

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/README.md`
4. `docs/reference/actor-handbook.md`
5. `../notes/memos-v2.0.25-product-runtime-preflight.md`
6. `../notes/memos-v2.0.25-m1-r1-ruling.md`
7. 本卡 §4 点名的 current source

禁止全文重扫五个 benchmark、首批五家 method、历史 `v2.0.22` 审计或全部 docs。

## 3. 允许与禁止

唯一允许提交的交付物：

```text
docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-product-runtime-preflight-r1.md
```

禁止修改 `src/`、`tests/`、`configs/`、`third_party/`、README、旧 note、旧卡、policy、
handbook、data、models、outputs。临时探针只能放系统临时目录；关键构造、命令和逐字 stdout
必须写进 R1 note，跨模型复验不得依赖 Claude/Codex scratchpad。

零真实 LLM、embedding、Neo4j、Qdrant、Redis、Docker、HTTP、网络和模型下载。不得为了
import 全包而安装依赖。若需 stub，只能 stub 真实缺失的外部 I/O SDK；不得遮蔽本机已安装
包，不得 stub `memos.*` 算法模块，并逐项披露。

## 4. 锁定裁决与 current-source 起点

以下是架构师已裁定边界，不是候选菜单：

1. 主产品候选是 `tree_text + MultiModalStructMemReader + typed Add/SearchHandler`；
   不用 `MOS.simple/general_text`，不 import `server_router`，不手写 raw primitive 近似链。
2. 每条 message 都显式带 `chat_time`，值为
   `turn time → session time → None`；绝不缺 key、借 question time 或造 wall clock。
3. local `/scheduler/wait` 禁作完成门，不为此强制 Redis。
4. 首选 completion 候选是
   `async_mode="sync", mode="fine", MOS_SCHEDULER_ENABLE_PARALLEL_DISPATCH=false`；
   必须证明后才能进入实现。
5. 单一 memory universe 使用同一个确定性 ID 作为 `user_id` 与唯一
   writable/readable cube；主 profile 不用 `CompositeCubeView`。
6. reader-level message_id transport 已证明；semantic provenance、stable ranking 与
   metric 资格仍是 `pending`。

重点 current source：

- `src/memos/api/handlers/{component_init,base_handler,add_handler,search_handler,
  formatters_handler,memory_handler}.py`
- `src/memos/api/{config,product_models}.py`
- `src/memos/multi_mem_cube/{single_cube,composite_cube}.py`
- `src/memos/mem_reader/{simple_struct,multi_modal_struct}.py`
- `src/memos/mem_reader/read_multi_modal/`
- `src/memos/memories/textual/{item.py,tree_text_memory/}`
- `src/memos/mem_scheduler/{base_scheduler,optimized_scheduler}.py`
- `src/memos/mem_scheduler/base_mixins/queue_ops.py`
- `src/memos/mem_scheduler/task_schedule_modules/{registry,dispatcher,local_queue}.py`
- `src/memos/mem_scheduler/task_schedule_modules/handlers/{add_handler,mem_read_handler}.py`
- `src/memos/api/handlers/scheduler_handler.py`
- official eval 的四个 LoCoMo/LME ingestion/search 文件，只做 current 差量

## 5. 必须闭合的任务

### 5.1 typed in-process product parity

逐项比较：

```text
HTTP router → typed handler
in-process init_server → HandlerDependencies → typed handler
```

证明 request validation、cube resolution、add response、search threshold/dedup/rerank、
formatter、hook 与 cleanup 是否同链。列出唯一差别必须只是 HTTP transport/router
global；若 handler 外还有算法语义，停工。

同时给出 TOML 最终需要控制的环境/强类型配置表；不在本卡实现配置桥。

### 5.2 completion 与失败传播

对照两条 current 路径：

```text
async + fast → fast write → queued MEM_READ
sync + fine  → fine extraction/write → LEVEL_1 ADD
```

重点验证候选：

```text
APIADDRequest(async_mode="sync", mode="fine")
MOS_SCHEDULER_ENABLE_PARALLEL_DISPATCH=false
```

必须证明：

- add 返回前 reader、tree write 与 ADD handler 均已结束；
- handler/read/write 任一异常能回到调用方，不被 log-and-success；
- sync/fine 没有跳过 async/MEM_READ 独有的算法核心；若行为不同，准确分类
  CONFIG_EQUIVALENT / ALGORITHM_VARIANT / 不合格；
- local queue `/scheduler/wait` 的负面对照按真实对象关系描述：
  router 是 `TaskStatusTracker(redis=None)` 查询为空后 fail-open，不是直接传 Python `None`。

可以用完全 hermetic fake component 验证调用时序和异常传播，但 fake 必须经过 current
`AddHandler → SingleCubeView` 生产链，不能直接调用自写替身函数。不要启动 Redis。

### 5.3 time、role、image 与 source transport

用 typed `APIADDRequest` 覆盖：

- 有 turn time；
- 仅 session time（adapter 候选应已经解析成每条相同 source time）；
- 每条显式 `chat_time=None`；
- 一条 `None` 与另一条真实时间并存；
- user-first、assistant-first、连续同 role、singleton、奇数尾；
- text + LoCoMo image wrapper content。

验证 typed model → `coerce_scene_data` → multimodal parser 的字节和值守恒。禁止再测
“缺 key 会发生什么”作为 adapter 候选；缺 key 只保留为 upstream negative control。

### 5.4 lineage、search 与 stable ranking

从已证明的 `SourceMessage.message_id` 继续追：

```text
reader metadata.sources
→ graph/vector serialization
→ scheduler merge/evolution
→ search raw item
→ product formatter/SearchResponse
```

分别判断 fast/fine/mixture：

- 返回单位是什么；
- source IDs 是否仍在公开或可审计 sidecar；
- score 名称、方向、top_k、threshold、dedup、rerank 后顺序是否稳定；
- window-wide sources 是否只代表“参与生成”而非 turn-exact semantic provenance；
- zero-hit、重复内容、merge/update 后资格。

单 cube 主路径必须与 `CompositeCubeView` 非确定性分叉明确隔离。不得因为 ID 存在就宣布
Recall/NDCG valid。

### 5.5 isolation、cleanup 与 clean retry

用两个确定性 namespace 的 hermetic production-chain 强反例证明：

- `user_id == sole cube_id` 的 add/search 不交叉；
- session 只作 canonical session 语义，不替代 universe 隔离；
- cleanup 只清当前 universe；
- add/read/write/scheduler 任一点失败后，retry 不重复记忆、不读到半成品；
- worker/process 关闭能停止 scheduler 与后台线程，不靠 `atexit` 猜测。

若 current cleanup 不能按该 namespace 闭合，给第一个缺口并停工。

### 5.6 HaluMem 与 metric 资格

不重新读 raw dataset，只消费稳定 HaluMem 契约。逐格判：

- session-local extraction；
- update（correct/incorrect/omitted）；
- QA；
- memory type；
- RetrievalEvidence、Recall/NDCG 与 stable ranking。

对每格写 `valid / N/A / pending`、current readout unit、理由和最小实现需求。不能为了测评
引入算法外 flush、伪造 memory item 或把 window lineage 当 fact lineage。

### 5.7 服务、模型与效率观测

列出 main smoke/full 真正需要的 LLM、embedding、reranker、graph/vector/storage、
scheduler/thread、网络端口与模型下载；区分：

- product algorithm 必需；
- HTTP transport 才需要；
- 可由本地 in-process backend 替换；
- 可禁用但会改变算法。

同时列出 memory-build、embedding、retrieval、scheduler 的可观测调用点和 scope identity。

### 5.8 M1 完整退出表

输出 B1-B11 readiness、M2/M3/M4 的精确输入、所有 N/A/pending 和最小后续卡。不要生成
五张 benchmark 卡；若 M1 通过，下一张应是“一张 adapter 实现卡 + 五格强反例”。

## 6. 停工条件

任一项立即保存证据并停工：

- source identity 漂移或 nested repo 不干净；
- sync/fine/serial 仍吞异常，或被证明跳过产品算法核心；
- typed handler 与 HTTP product 在 router 外存在未纳入的算法差异；
- single namespace 无法阻止跨 universe 读取/删除；
- 必须修改 third_party 算法才能完成 M1；
- 需要真实服务、API、模型或网络才能回答承重问题；
- 触碰唯一允许文件外路径；
- 15 分钟内无法消解的 current-source 矛盾。

`valid/N/A/pending` 的诚实能力结论不是停工；只有无法判断其原因或会阻断 adapter 主路径才停。

## 7. 最小自检与完成报告

只运行：

```bash
uv run pytest -q tests/test_documentation_standards.py
git diff --check
```

不跑全量 pytest/compileall，不调用真实资源。commit 前只显式 add 唯一 note 路径，
过目 `git status --short`，不得 `git add -A/.`。

按 `actor-handbook.md` §4 回报：

1. follow-up commit hash；
2. 两个自检结果原文；
3. 实际改动文件；
4. 偏差/停工点；
5. subagent 使用；
6. 实际模型/入口与切换情况；
7. 一句话总判词及 M2 解锁或阻塞项。

到此停止，不 push、不清 worktree、不更新 README/roadmap、不开始 adapter。
