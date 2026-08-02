# Machine-readable smoke plan / preflight M0

日期：2026-07-29
状态：accepted

## 1. 问题与裁决

HaluMem smoke 是固定的 `1 user / 4 sessions / 1 QA / workers=1` operation-level
哨兵，不能接受 `rounds/turns/sessions/sources/conversations/questions` 裁剪。此前这条
事实虽然写在 benchmark policy、测试和文档里，但架构师仍会手写命令，再靠 CLI 报错纠正。

这不是“上下文记性不好”可以解释掉的问题，而是约束没有成为命令生成的单一事实源。裁决：

1. `BenchmarkSmokePolicy` 显式声明 `shape_mode=croppable|fixed`；
2. HaluMem 注册 `fixed`，直接 CLI 继续在 command service 前拒绝全部裁剪旗标；
3. 新增 `plan-smoke`，只读 benchmark/method/evaluator registry 与 method TOML，
   自动生成精确 `predict_argv + evaluate_argv`；
4. B11 禁止手写正式 smoke 命令。先生成 plan、审阅 JSON，再执行其中 argv；
5. planner 不读 `.env`、不构造 method/runtime、不开 DB、不调用 API。

## 2. 机器契约

入口：

```bash
uv run memory-benchmark plan-smoke \
  --root . \
  --method mem0 \
  --benchmark halumem \
  --variant medium \
  --run-id mem0-halumem-smoke
```

输出契约 `smoke-plan-v1` 包含：

- benchmark fixed/croppable shape、注册历史轴和预算；
- method TOML 配置 worker、最终 worker、是否发出 CLI override；
- concrete variant、base run-id 与真实 prediction child run-id；
- 当前 benchmark 全部已注册 evaluator 及 `requires_api`；
- shell-safe 人读命令和作为事实源的 argv 数组。

HaluMem 的 `predict_argv` **不得出现**：

```text
--rounds --turns --sessions --sources --conversations
--questions-per-conversation
```

planner 仍在 JSON 中展示固定 `4 sessions / 1 isolation / 1 question`，但不会把这些
值伪装成可覆盖 CLI 参数。HaluMem W2 同样在规划/CLI 层拒绝，不进入 runtime/API。

## 3. 额外关闭的重复踩坑

- 多 variant benchmark 的 `--run-id` 是 base id；真实 child 会追加 variant suffix。
  planner 与 prediction runner 共用
  `resolve_explicit_prediction_run_id()`，因此 evaluate 自动消费真实 child id。
- evaluator 不再由人回忆逐条拼接；planner 从 evaluator registry 生成完整适用集合，
  只要其中任一需要 API，就为 evaluate 命令加入 `--allow-api`。
- worker 不再从“上次命令”复制：默认取 method smoke TOML；显式覆盖必须同时通过
  method registry 资格与 operation-level W1 门。

## 4. Resume / identity 影响

`shape_mode` 进入 `BenchmarkSmokePolicy.to_dict()`，因此进入 benchmark policy manifest。
旧 manifest 缺少该字段时与新 run 严格不匹配，这是有意的 identity 收紧：旧 artifact
不能声称自己执行过当前显式 fixed/croppable shape contract。

## 5. 验证

定向测试：

```text
uv run pytest -q tests/test_smoke_plan.py tests/test_main_cli.py \
  tests/test_benchmark_registry.py tests/test_prediction_cli.py \
  tests/test_method_registry.py
255 passed in 33.74s
```

无 secret 实机只读探针：

```text
mem0 × HaluMem plan: exit 0；predict argv 零裁剪旗标；
evaluate run-id = planner-halumem-demo-medium
MemOS × LoCoMo --workers 2: exit 2；
Error: MemOS does not support smoke worker override from configured 1 to 2
```

`git diff --check`：exit 0。

主树关闭门：

```text
uv run pytest -q
1917 passed, 3 deselected, 13 warnings, 29 subtests passed in 160.69s

uv run python -m compileall -q src/memory_benchmark tests
exit 0

uv run pytest -q tests/test_documentation_standards.py
5 passed in 0.95s
```

warnings 画像未新增：vendored LightMem Pydantic V2 deprecation、MemOS
`datetime.utcnow()` deprecation 与 MemOS Pydantic serialization warning。

## 6. 关闭门

- [x] shape 是 benchmark 注册事实，不是 benchmark-name 分支；
- [x] HaluMem 固定 shape 与 W1 在 API/runtime 前 fail-fast；
- [x] planner 无 `.env` / API / runtime 依赖；
- [x] predict/evaluate 命令与 multi-variant child id 同源；
- [x] B11 与架构师热手册写入“不得手写”；
- [x] 主树全量 pytest + compileall；
- [ ] commit + push。
