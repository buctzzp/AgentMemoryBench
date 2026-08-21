---
id: ws04
parent: null
status: done
created: 2026-07-05
---
# ws04 终端体验与第三方输出治理

## Codex 恢复胶囊（2026-08-21）

- **当前目标**：M1 已关闭。isolated worker 有阶段 heartbeat；Python logging、三家
  in-process stdout/stderr 与四家 JSON-lines worker stderr 均稳定落入 `logs/method.log`。
- **当前批次**：无。达到 heartbeat/output/cosmetic 停手线，不扩 tracing、不继续打磨动画。
- **当前判据**：[spec](spec.md) 与 [plan](plan.md)。已完成前置证据是
  `observability/method_log_scope.py` 及 `tests/test_method_log_scope.py`；它只覆盖 Python
  logging，不等于 stdout/tqdm 已治理。
- **并行支线**：OpenCodeGo economy 模型最初切到 Muse，随后真调用发现空 choice，已在 run
  创建前改判为 `mimo-v2.5`；Muse 只保留旧 artifact 精确回读。runtime 身份与证据见
  `docs/reference/api-runtime-profiles.md`。
- **禁止事项**：零真实 API；不改 method 算法/metric/prompt，不碰 outputs/data/models/
  third_party 与用户未跟踪资产；不把 progress heartbeat 写成高频 artifact 洪泛。
- **完成证据**：[M1 实现与验收](notes/ws04-m1-implementation.md)；最终无 API 全量
  `2243 passed, 3 deselected, 25 warnings, 29 subtests passed`，compileall exit 0。

## 目标

解决两类只影响终端体验、不影响 artifact 正确性的问题：isolated worker 长时间
无中间进度，以及第三方 method 的 stdout/warning/tqdm 插入 Rich 进度区。
完成判据：并行 prediction 期间终端能看到各 worker 的 conversation/阶段级心跳；
第三方输出可靠落入 `logs/run.log`/events 且有终端显示开关。

## 当前断点

- 2026-08-21：**M1 已验收关闭**。2026-07 的 per-run `method.log` 前置其实已经由
  commits `5438064`/`feaa161` 落地，但本页仍写“未开工”，现已纠正。该前置只捕获
  logging；本批补齐 coordinator-owned heartbeat、factory 重配后的 handler 恢复、三家
  in-process 脱敏捕获与四家 JSON-lines worker 全量脱敏 stderr。
- 2026-07-05 的原始现象见
  `../../archive/status/2026-07-04-task-ledger.md` P1 两条。

## 任务清单

- [x] **M1-A** isolated worker 上报 heartbeat / 阶段事件（当前 conversation、阶段、
  已处理 turn/question 数），协调层渲染；不必给每个 worker 单独进度条。
- [x] **历史前置** Python logging 追加落入 `logs/method.log`，run 结束摘 handler；
  不宣称覆盖 stdout/tqdm。
- [x] **M1-B** 框架级 stdout 约束：第三方 `print()` / warning / tqdm 路由到
  `logs/method.log`；in-process 既有显示开关只控制终端镜像，不改变落盘；不得全局压掉用户自定义
  method 的调试输出。
- [x] **M1-C** Rich cosmetic 残留复验：elapsed、worker 交错和 progress-disabled 快照均由
  fake/no-API 并行强反例关闭；真实 API smoke 不是本工程 workstream 的完成门。

## 决策记录

- 2026-06 已确认：这些问题不影响 artifact 正确性，优先级低于主线；
  但不能宣布终端体验完成。
- 2026-08-21：heartbeat 由协调线程拥有状态与落盘；worker 线程只发公开事件。
  这避免多个 worker 争写 `progress.json` 或直接操作 Rich。stdout 治理必须区分
  in-process 与 JSON-lines subprocess；不建立一个全局 `sys.stdout` singleton。
