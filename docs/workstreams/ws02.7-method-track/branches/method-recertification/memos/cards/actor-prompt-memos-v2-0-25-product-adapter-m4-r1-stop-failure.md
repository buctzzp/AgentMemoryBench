# Actor follow-up：MemOS M4-R1 stop failure 必须永久 fail-closed

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**继续使用原 worktree/branch，在 `de29c4c` 之上追加一个 follow-up
commit；不得 amend、rebase、merge、push：

```text
worktree  /Users/wz/Desktop/mb-actor-memos-adapter
branch    actor/memos-v2-0-25-product-adapter-m4
base      de29c4c
```

`de29c4c` 已关闭 pending-refusal、clean-hook handoff、runner early cleanup、环境恢复和 typed
handler 装配缺口；这些裁决全部保留。本 follow-up 只修 actor 主动交回架构师裁决的
`scheduler.stop()` 失败后状态，不重开任何其他实现。

## 1. 一手事实与最终裁决

current MemOS v2.0.25：

```text
src/memos/mem_scheduler/base_mixins/queue_ops.py

stop():
  if not self._running:
      return
  self.stop_consumer()        # 这里先写 self._running = False
  ...
  self.dispatcher.shutdown()  # 后续仍可能抛错
  self.dispatcher_monitor.stop()
```

所以：

1. 如果 `dispatcher.shutdown()` 或更后的步骤抛错，scheduler 已可能只关闭了一部分；
2. 第二次调用 upstream `stop()` 会因 `_running=False` 直接返回；
3. 因而“第二次 cleanup 不再调用 stop、直接把 runtime 标成 closed 并从 owner 删除”不是
   幂等，而是把**未证实完全关闭**伪装成成功。

架构师最终裁决：

```text
stop() 成功
→ runtime.closed = true
→ owner/provider 释放引用

stop() 首次抛错
→ 原异常可见
→ runtime.closed = false
→ runtime.close_failed = true
→ owner/provider 保留同一 runtime
→ 禁止 acquire/reuse/构造第二个 runtime

之后再次 cleanup/close
→ 不再调用 stop
→ 必须稳定 fail-fast，并链回/披露首次 stop failure
→ 永远不得标 closed、不得从 owner/provider 清引用
```

这是永久 poisoned/close-failed 状态，只能让当前 run 失败并退出进程；不得假装可恢复。测试
专用 `owner.reset()` 仍可清 fixture，但生产路径不得靠 reset 掩盖失败。

## 2. 允许修改

仅：

```text
src/memory_benchmark/methods/memos_adapter.py
tests/test_memos_adapter.py
docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-product-adapter-m4-implementation.md
```

不得再改 runner、registry、CLI、patch、vendored MemOS、TOML 或其他文件。若必须扩大，
停工回报。

## 3. 实现边界

- 可把 `_stop_attempted` 收敛为明确的 close state，或新增 `_stop_failure`/
  `_close_failed`；名称由 actor 选择，但运行期语义必须强类型、可审计。
- 首次 `stop()` 异常不得吞掉或改写成成功。
- 后续 close/cleanup 必须抛 `ConfigurationError`（或同层明确错误），错误要说明该 runtime
  已因先前 stop failure 不可安全复用，并用 `raise ... from first_error` 保留因果链。
- `_MemosRuntimeOwner.acquire()` 遇到同 config 的 close-failed runtime 必须 fail-fast；
  不能像普通 open runtime 一样返回，也不能构造第二份。
- `release()` 与 `release_current_for_config()` 遇到 close-failed runtime 都必须保持引用并
  fail-fast。
- pending-task refusal 不是 close failure，仍保持 `de29c4c` 已证实的
  pending→terminal→cleanup 成功路径。
- 正常 stop 成功、重复 successful cleanup、owner-empty cleanup 行为字节/对象语义不变。
- 不把异常文本、API key 或 DB secret 存入公开 manifest/artifact。

## 4. 必测强反例

至少锁死：

1. 首次 scheduler stop 抛错：异常可见，stop_calls=1，runtime/provider/owner 引用保留，
   `closed=False`、`close_failed=True`；
2. 第二、第三次 cleanup：每次均 fail-fast，stop_calls 仍为 1，所有引用仍保留，
   `closed=False`；
3. close-failed 后 `owner.acquire(same_config)` 拒绝复用，runtime factory 调用数不增加；
4. `release_current_for_config(same_config)` 同样拒绝并保留；
5. pending refusal 后 task terminal 的正常重试仍成功，不能误标成 close-failed；
6. stop 正常成功后重复 cleanup 幂等且 stop 恰好一次；
7. 现有 runner cleanup-failure 用例仍证明 summary/run_completed 不会落成成功。

做一次窄 mutation：删掉 close-failed 的二次拒绝门、恢复 `de29c4c` 的“第二次标 closed”
行为时，至少一条新用例必须转红；恢复后全绿，临时变体不提交。

## 5. 自检与回报

只跑：

```bash
uv run pytest -q \
  tests/test_memos_adapter.py \
  tests/test_prediction_runner.py::test_cleanup_failure_is_visible_and_run_is_not_completed \
  tests/test_prediction_runner.py::test_cleanup_failure_preserves_primary_exception_context
git diff de29c4c..HEAD --check
git show --check --oneline HEAD
```

implementation note 只追加一节，明确撤回 `de29c4c` 中“stop failure 第二次 cleanup 可成功”的
口径，不能改写历史。

回报 follow-up commit、测试尾行、状态机、mutation、偏差/subagent/真实模型。唯一判词：

```text
READY_FOR_MEMOS_M4_FINAL_ARCHITECT_ACCEPTANCE(
  stop failure is permanently fail-closed;
  no false closed state or runtime reuse remains
)
```

到此停止，不开始 M5。
