# Actor 返工卡：MemOS v2.0.25 product adapter M4-R1 生命周期闭环

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**继续使用：

```text
worktree  /Users/wz/Desktop/mb-actor-memos-adapter
branch    actor/memos-v2-0-25-product-adapter-m4
base      a87353a
```

在 `a87353a` 之上追加一个 follow-up commit；不得 amend、rebase、merge、push。你是施工
actor，不是架构师；本卡只关闭架构师强验收发现的两个生命周期缺口和两组漏测，不重开
五格输入、MemOS 算法、patch、metric 资格或 M5 pending。

## 0. 为什么返工

`a87353a` 的主实现与 356 条定向回归大体成立，但尚不能获得
`READY_FOR_MEMOS_M5_PREFLIGHT`。架构师用该分支生产类运行了下面的强反例：

```text
FIRST_CLEANUP_ERROR: ConfigurationError MemOS scheduler 仍有 1 个未完成 task，拒绝静默关闭：biz/mem_read=waiting
AFTER_FIRST: {
  'provider_cleaned': True,
  'provider_runtime_is_none': True,
  'owner_runtime_is_none': True,
  'runtime_closed': False,
  'stop_calls': 0
}
AFTER_RETRY: {
  'provider_cleaned': True,
  'provider_runtime_is_none': True,
  'owner_runtime_is_none': True,
  'runtime_closed': False,
  'stop_calls': 0
}
```

根因有两层：

1. `_MemosRuntimeOwner.release()` 在 `runtime.close()` 成功前先清掉 owner 引用，
   `MemOS.cleanup()` 也在成功前先写 `_cleaned=True`、清掉 provider 引用。pending task
   导致 close 拒绝后，runtime 变成仍运行但无人持有的孤儿；后台 task 终结后 cleanup
   也无法重试。
2. generic runner 的 cleanup 保护只包住 ingest/answer；failed-ingest clean hook、
   ingest-checkpoint preflight 和 work-plan 构造发生在保护区之前。MemOS clean hook 会先
   lazy-init 共享 owner runtime，因此这些前置阶段任一失败都可能泄漏线程。clean hook
   成功后，根 provider 尚未 `_require_runtime()` 的边界也必须能接管并关闭 owner 中的
   同 config runtime。

另有两组 M4 卡 §5 明列的承重测试实际上没有覆盖：

- `_scoped_environment` / `_memos_environment` 在 `init_server()` 成功和抛错时恢复原环境；
- 真实 `MemosRuntime.__init__` 装配面只 init 一次，并让 Add/Search handler 共用同一
  `HandlerDependencies`、scheduler 与 local tracker。现有 `_FakeRuntime` provider 测试
  不能替代这两项。

## 1. 最小必读

只读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. 首轮卡 `actor-prompt-memos-v2-0-25-product-adapter-m4.md` 的
   §4.2、§4.3、§4.7、§5.1、§5.2
4. `a87353a` 中：
   - `src/memory_benchmark/methods/memos_adapter.py`
   - `src/memory_benchmark/runners/prediction.py`
   - `tests/test_memos_adapter.py`
   - `tests/test_prediction_runner.py`
   - 首轮 implementation note

不要重读 benchmark 原始数据、五格异常账、其他 method 或全部文档。

## 2. 锁死裁决

### 2.1 cleanup 必须“成功后提交状态”

修复后必须同时满足：

1. pending-task refusal 之前与之后，provider、owner、runtime 的可重试引用保持不变；
2. pending task 转为 terminal 后，同一 provider 再次 cleanup 会真正 close，并且
   scheduler `stop()` 总计恰好一次；
3. owner 只能在 `runtime.close()` 成功后清空当前 runtime；
4. provider 只能在 owner release 成功后写 `_cleaned=True`、清空自己的 runtime；
5. owner release 与 acquire 之间保持原子性：close 尚未完成时，不得并发构造第二个同
   config runtime；
6. scheduler `stop()` 抛错必须可见，且不得把 owner/runtime 静默丢成孤儿。不得用吞错或
   `finally` 强行标 completed 来过测试。

允许为 owner 增加一个“仅返回/释放当前同 identity runtime、为空不构造”的窄方法。identity
不匹配必须 fail-fast，不能关闭别的配置。正常无 runtime 的 no-work run 不得为了 cleanup
反向创建一个新 runtime。

### 2.2 clean-hook → 根 provider 的 owner 交接

当前 CLI 在调用 generic runner 前已经构造根 provider，但 MemOS runtime 是 lazy 的；clean
hook 会用同 config 的临时 provider 先取得 owner runtime。根 provider 在结束时即使自己的
`_runtime is None`，也必须能关闭 owner 中**同 identity**的现有 runtime；owner 为空时保持
no-op，不得 init。

不要把 clean hook 改成成功后立即 close 再让正式 ingest 第二次 `init_server()`；首轮裁决
要求 clean 与正式 run 复用同一 runtime。不要引入第二套全局缓存、弱引用注册表或
benchmark 特判。

### 2.3 generic runner 的保护区

shared/non-isolated v3 provider 的生命周期保护必须从 failed-ingest clean retry **之前**
开始，并且：

- clean hook、checkpoint preflight、work-plan、ingest、answer 任一异常都 cleanup；
- 正常路径仍在写 `Completed` stage、summary、`run_completed` 之前 cleanup；
- cleanup 恰好一次；
- cleanup 失败仍可见，不生成 completed summary；
- isolated worker、legacy bridge、operation-level 语义不变。

可用一个在前置阶段就注册、在现有完成点显式 `close()` 的 `ExitStack`/等价结构：早退或异常
由外层自动执行，正常路径在现有时刻提前执行，context 退出时不重复。不得把 cleanup 延迟到
summary 之后。

### 2.4 环境与真实装配漏测

补 hermetic 强反例：

1. 预置一组将被覆盖的环境变量，并留一组原先不存在；fake `init_server()` 在作用域内断言
   config/OpenAI/secret 值精确可见，构造成功后全部逐字恢复；
2. fake `init_server()` 抛错时同样全部恢复，secret 不得进入异常文本或 stdout；
3. 穿过真实 `MemosRuntime.__init__` 的 lazy import/handler 装配边界，只 fake 外部组件叶子；
   断言 `init_server()` 恰好一次、Add/Search handler 的 `dependencies` 是同一对象、
   scheduler/naive cube/tracker 来自同一 bundle；
4. 继续断言 `memos.api.routers.server_router` 未被 import。

不得连接 Neo4j/Qdrant/Redis，不读或软链 `.env`，不得真实 API/模型加载。

## 3. 允许修改文件

仅：

```text
src/memory_benchmark/methods/memos_adapter.py
src/memory_benchmark/runners/prediction.py
tests/test_memos_adapter.py
tests/test_prediction_runner.py
docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-product-adapter-m4-implementation.md
```

若真实修复必须改 CLI、registry、provider protocol、vendored MemOS、patch、TOML、其他测试或
允许清单外文件，立即停工回报，不自行扩 scope。

## 4. 必测强反例

至少新增并锁死：

1. pending cleanup 首次抛错后引用均保留；task terminal 后重试成功、stop 恰好一次；
2. `runtime.close()` / scheduler stop 抛错时 owner 不丢引用、错误可见；
3. clean hook 已创建 runtime、根 provider 从未 acquire：根 cleanup 关闭同 identity runtime；
4. owner 为空的根 cleanup 不构造 runtime；
5. owner 中为冲突 identity 时 fail-fast、不关闭对方；
6. clean hook 自身抛错时 generic runner 仍 cleanup 根 provider 恰好一次；
7. checkpoint preflight 抛错时同样 cleanup；
8. 正常 success/ingest failure/answer failure 的既有 cleanup 次数不退化；
9. §2.4 的环境成功/失败恢复与真实装配四项。

强反例必须对未修的 `a87353a` 转红；把至少以下 mutation 结果写进 note：

- 恢复“close 前清 owner/provider 引用”时，pending-retry 用例转红；
- 把 runner lifecycle guard 移回 clean hook 之后时，early-failure cleanup 用例转红。

## 5. 自检与交付

只跑：

```bash
uv run pytest -q \
  tests/test_memos_adapter.py \
  tests/test_prediction_runner.py \
  tests/test_memos_registered_prediction.py \
  tests/test_memos_lifecycle.py
git diff a87353a..HEAD --check
git show --check --oneline HEAD
```

不跑全量 pytest、compileall、真实服务/API/模型。首轮 note 只追加 M4-R1 小节，保留
`a87353a` 的历史输出与偏差，不改写成仿佛首轮就正确。

回报：

1. follow-up commit hash；
2. 定向测试尾行与两个 diff check；
3. 实际改动文件；
4. pending→terminal cleanup 前后状态机；
5. clean-hook/runtime-owner/root-provider 的单 runtime 交接；
6. 环境恢复和 handler 共享装配证据；
7. mutation 失败测试名；
8. 偏差/停工点、subagent、真实模型/入口。

唯一通过判词：

```text
READY_FOR_MEMOS_M4_ARCHITECT_RECHECK(
  cleanup refusal is retryable;
  early failures cannot leak the shared runtime;
  environment scope and typed-handler sharing are proven
)
```

到此停止，等待架构师复核；不得开始 M5。
