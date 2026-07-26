# Actor 卡：MemOS v2.0.25 async lifecycle 完成门 R2

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**本批只修 current product `async+fast → MEM_READ` 的失败传播与
task-scoped completion；不写 MemOS adapter、不启动 HTTP host、不调用真实 API/模型/数据库。
actor 可自行组织 subagent，但不得扩大允许范围；主 actor 必须亲核承重锚并对最终报告负责。

## 0. 目标与唯一判词

架构师已驳回把 `sync+fine` 当主 profile。主路径锁定：

```text
typed AddHandler
APIADDRequest(async_mode="async", mode=None)
fast/raw write -> queued MEM_READ -> fine write -> raw cleanup -> refresh
local queue, no Redis
product-default parallel dispatch
```

本批只允许：

```text
READY_FOR_MEMOS_ADAPTER(
  success path unchanged;
  failures are observable;
  business-task completion is exact;
  patch is reproducible
)
```

或：

```text
BLOCKED(<无法在不改成功态算法的前提下闭合的首个问题>)
```

## 1. 隔离环境与 Git

- 新建独立 worktree：`/Users/wz/Desktop/mb-actor-memos-r2`
- branch：`actor/memos-v2-0-25-async-lifecycle-r2`
- 基线：派发时本地 `main`
- 完成后一个本地 commit，不 push

官方 nested repo：

```text
/Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS
v2.0.25
e820406269537b97d270687e3e40eea2f015f81a
```

先逐字核验 identity 与 clean 状态。该目录 local-only，可为生成/验证 patch 暂时应用本卡
patch；不得 commit 到 nested repo，不 fetch/pull/checkout/install。收尾时 nested repo
允许处于“仅本卡 patch 已应用”的可解释 dirty 状态，但必须用 reverse-check 证明与 patch
逐字一致并在报告披露。

新 worktree 不携带 gitignored nested repo 时，可在 worktree 的
`third_party/methods/MemOS` 建指向上述绝对路径的本地软链；软链不得暂存，报告中披露。

## 2. 最小必读

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/README.md`
4. `docs/reference/actor-handbook.md`
5. `../notes/memos-v2.0.25-product-runtime-preflight-r1.md`
6. `../notes/memos-v2.0.25-m1-final-ruling.md`
7. 本卡 §4 点名的 current source

禁止重扫五个 benchmark、前五家 method、旧 MemOS 版本或全部 docs。

## 3. 允许文件

只允许修改/新增：

```text
scripts/patches/memos-product-runtime-observability.patch
scripts/fetch_third_party_methods.sh
third_party/methods/MANIFEST.md
src/memory_benchmark/methods/memos_lifecycle.py
tests/test_memos_lifecycle.py
docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-async-lifecycle-r2-implementation.md
```

为生成 patch 可暂改 nested MemOS 中下列文件，最终改动必须全部由上述 patch 表达：

```text
src/memos/multi_mem_cube/single_cube.py
src/memos/mem_scheduler/task_schedule_modules/handlers/mem_read_handler.py
src/memos/memories/textual/tree.py
src/memos/memories/textual/tree_text_memory/organize/manager.py
src/memos/graph_dbs/neo4j_community.py
```

若必须改 nested repo 其他文件，立即停工，不扩大 patch。禁止修改 registry、runner、
benchmark adapter、evaluator、TOML、outputs、data、models 和其他 third_party method。

## 4. current-source 承重点

必须亲读并验证：

1. `single_cube.py::_schedule_memory_tasks()` 的 async submit catch 只 log 不 raise；
2. `mem_read_handler.py` 的 `batch_handler()`、`process_message()`、
   `_process_memories_with_reader()`、fine-transfer、delete 与 organize submit 存在多层吞错；
3. `organize/manager.py::_add_memories_batch()` 的 graph future 异常只 log，但仍返回
   预生成 IDs；`_cleanup_working_memory()` / `_cleanup_memories_if_needed()` 也吞错；
4. `tree.py::delete()` 逐 memory id 吞错；
5. default `neo4j-community.add_nodes_batch()` 在 vector DB 写失败时只标
   `vector_sync=failed`，graph write 继续；
6. scheduler/dispatcher 已按 internal `item_id` 和 business `task_id` 调用
   `task_submitted/started/completed/failed`，只是 local mode 没有可用 tracker。

若任一事实被 current source 推翻，按停工条件交回，不把卡改写成另一个目标。

## 5. 锁定实现

### 5.1 Reproducible patch

新增 `memos-product-runtime-observability.patch`，并让 fetch 脚本在 MemOS checkout 后幂等
应用；MANIFEST 明确写成 `v2.0.25@e820406 + 本项目 failure-observability patch`。

patch 只能改变**失败可见性**：

- async scheduler submit 失败 re-raise；
- 真实 fine-transfer、graph/vector write、raw delete、refresh、capacity cleanup 和可选
  organize submit 失败最终必须让 dispatcher task 标 `failed`；
- batch 中任一 item 失败，batch handler 等待其余已启动 item 收尾后聚合 raise；
- 缺 mem cube、错误 text memory 类型、已返回 ID 却取不到 raw memory 都是失败；
- `neo4j-community` 的 vector batch write 失败不能再作为成功继续；
- 合法的“fine extraction 成功但抽取零条 memory”仍是 completed；
- 成功路径的调用顺序、memory 内容、IDs、metadata、search 行为和调度拓扑不得改变。

不要“顺手修”无 namespace 的 `delete_by_memory_ids()`；adapter 将禁止调用该入口。

### 5.2 Framework local tracker 与 waiter

`memos_lifecycle.py` 实现不依赖 Redis 的 thread-safe tracker，接口只覆盖 MemOS current
scheduler 真正调用的：

```text
task_submitted
task_started
task_completed
task_failed
get_task_status
get_task_status_by_business_id
```

并提供小而明确的安装/等待 API：

- 同一个 tracker 安装到 scheduler 与 dispatcher；
- adapter 提供唯一 business `task_id`；
- wait 只认该 user + business task 下的预期 `MEM_READ`；
- `failed` 立即抛 `ConfigurationError`（保留原 error）；
- 超时、查无任务、未知状态、0 个或多于预期的主 `MEM_READ` fail-fast；
- 其他 task/user/namespace 的完成不能误解锁；
- shutdown 前有 pending task 时不得静默关闭。

不要解析日志文本，不读取 `/scheduler/wait`，不轮询“全局队列是否为空”，不引入 Redis。

### 5.3 HaluMem 观测边界

本卡不实现 HaluMem evaluator。只在 note 中回答：current strict completion 是否能观察
task-scoped fine output；若现有 handler 不公开 enhanced IDs/content，写成
`pending(adapter 需纯观测 sidecar)`，不得为了这格扩 patch 或改用 sync/fine。

## 6. 强反例

`tests/test_memos_lifecycle.py` 至少覆盖：

1. patch reverse-check 通过，fetch 脚本有且只有一次 MemOS apply；
2. async happy path 的完整共享 trace：
   `fast write → submit → fine transfer/write → raw delete → refresh → completed`；
3. initial fast graph write 失败，add 不得返回伪 IDs/success；
4. vector write失败；
5. scheduler submit 失败；
6. fine-transfer LLM 失败；
7. fine graph write失败；
8. raw delete失败；
9. refresh/cleanup失败；
10. handler batch 一项失败而另一项完成，最终 aggregate failed；
11. 合法零抽取 completed；
12. business task A 完成不能解锁 B；
13. missing/unknown/multiple expected task、timeout、failed error 原因；
14. tracker 多线程并发状态不丢；
15. shutdown 有 pending task fail-fast，全部完成可关闭。

强反例必须穿过 patched current MemOS 的真实相关函数；只测自写 tracker fake 不算关闭
第三方吞错。允许对外部 I/O SDK 做 hermetic fake，但不得 stub `memos.*` 算法函数来跳过
上述 catch 边界。

对每个生产修复，至少选关键 case 做一次“临时反向去掉对应 patch hunk 后测试转红”的
mutation 证明，并把失败测试名写进 implementation note；不要求把临时变体提交。

## 7. 禁止与停工

- 零真实 LLM、embedding、Neo4j、Qdrant、Redis、Docker、HTTP、网络和模型下载；
- 不启动 host，不 import `server_router`；
- 不改 async 成 sync，不改 fast/fine/reorganize/search 算法；
- 不以 polling sleep 猜完成，不把合法零抽取判失败；
- 不为测 metric 扩展本卡。

任一情况立即保存证据并停工：

- 成功路径必须改变才能传播失败；
- 需要修改允许清单外文件；
- source identity 漂移或 nested repo 有无法解释的既有 dirty；
- current scheduler 无法用 business task 精确闭合；
- 需要真实服务才能验证承重行为；
- 15 分钟内无法消解的一手矛盾。

## 8. 自检与报告

只运行：

```bash
uv run pytest -q tests/test_memos_lifecycle.py tests/test_documentation_standards.py
git diff --check
```

不跑全量 pytest/compileall。commit 前只显式 add §3 的真实改动路径，过目
`git status --short`，不得 `git add -A/.`。

按 `actor-handbook.md` §4 回报：

1. commit hash；
2. 定向测试尾行原文；
3. 实际改动文件；
4. patch 触及的 upstream 函数与 success-path 守恒判词；
5. 偏差/停工点；
6. subagent 使用；
7. 实际模型/入口及切换；
8. `READY_FOR_MEMOS_ADAPTER` 或 `BLOCKED`。

到此停止，不 push、不清 worktree、不更新 README/roadmap、不开始 adapter。
