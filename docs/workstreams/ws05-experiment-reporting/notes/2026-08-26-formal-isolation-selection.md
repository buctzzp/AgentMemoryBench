# Formal 精确 isolation 选择（2026-08-26）

## 1. 问题与裁决

预算实验需要先锁定一组由公开输入形状选择的代表 isolation，再按 `1 + 2 (+ 2)` 分批推进。
此前 runner 已有 `PredictionRunPolicy.conversation_ids`、有序选择、未知 id 拒绝、generic/HaluMem
双 runner 消费和 manifest/resume identity，但正式 CLI 没有入口；操作者只能按 dataset 默认顺序
取下一个 isolation。

本批不新增 calibration runner、不修改 worker/state 拓扑，也不调用 API。只增加可重复的
`predict formal --isolation-id <id>`：CLI 名称使用 benchmark-neutral 的 isolation，内部继续复用
既有 `conversation_ids` 字段。

## 2. 合同

- `--isolation-id` 只允许 `predict formal` / `run formal`；smoke、pilot 和 legacy 写法拒绝。
- 可重复传入，参数出现顺序就是 cohort 顺序；空白与重复值在 CLI 层 fail-fast。
- 未知 id 由既有 runner 选择门拒绝，不回退到 dataset 首项。
- 完整有序名单进入 manifest policy，属于实验 cohort identity；resume 必须原样重复。
- `--conversation-budget` 仍只属于单次命令预算，可在相同 run/cohort 上由 1 改成 2。
- 推荐一次只选择一个 concrete variant；multi-variant child 不共享 id 时会按既有未知 id 门拒绝。

## 3. 非目标

- 不允许 resume 时修改 worker 数，也不迁移 `worker_N` method state。
- 不创建矩阵总调度器、自动选样器或第二套 cohort schema。
- 不用 gold、答案、method 输出或历史得分选样。
- 不启动 LightMem 或其他 method 的真实运行。

## 4. 验证

- CLI：formal 重复参数按序进入 `PredictCommand`；smoke/pilot、空白和重复值均拒绝。
- command service：名单透传 registered prediction。
- registered generic 与 HaluMem operation-level：两条链的 `PredictionRunPolicy` 均收到原名单。
- runner/resume：同名单可稳定恢复；只改变顺序即在任何新增工作前报 manifest mismatch。
- 定向门：
  `uv run pytest -q tests/test_main_cli.py tests/test_prediction_cli.py tests/test_prediction_runner.py tests/test_operation_level_runner.py`
  → `319 passed, 12 warnings in 10.16s`。
- 文档 + 定向联合门：`326 passed, 12 warnings in 9.35s`；`git diff --check` 无输出。
- current 全量零 API 门：
  `2338 passed, 3 deselected, 25 warnings, 29 subtests passed in 154.92s`。
