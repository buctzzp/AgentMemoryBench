# 2026-08-26 QA task aggregation M0 实现验收

## 1. 交付

- `memory_benchmark.analysis.qa_task_aggregation` 从标准不可变 artifact 重建逐题 QA 分数、原生
  task 宏平均、capability slice、benchmark rank 与五格 overall。
- 固定 Phase 1 十家 roster；缺格、非 `formal`、question coverage 不全或 answer/evaluator/data
  identity 不一致均使 cohort `incomplete`，不补零、不缩分母。
- BEAM `event_ordering` 从逐题 `details.event_ordering_tau_norm` 读取，其余 ability 保留 float
  rubric；不消费旧 summary 的误导性十类同算均值。
- 输出显式列出 retrieval、HaluMem extraction/update/memory-type 为主 QA aggregate 的排除面。

## 2. 强反例

测试锁住了：个性化与指令遵循分离、LongMemEval abstention 唯一归类、未知类型 fail-fast、
BEAM event-ordering selector、native-task macro 而非题数 micro、五 benchmark 等权、平均并列名次、
缺格不排名、smoke 不发布、answer identity mismatch 阻断，以及非 QA surface 显式排除。

另用 current 已有五家 MemOS smoke artifact 做只读开箱：loader 可以读取标准目录，但因 scope 与
题型覆盖不足全部保持不可发布，不会把旧 smoke 误包装成排行榜。

## 3. 验收

```text
uv run pytest -q tests/test_qa_task_aggregation.py tests/test_run_cost_report.py \
  tests/test_beam_rubric_judge.py tests/test_halumem_evaluators.py \
  tests/test_artifact_evaluation_runner.py tests/test_documentation_standards.py
99 passed in 7.63s
```

`py_compile` 与 `git diff --check` 通过。环境未安装 `ruff`，因此未把不存在的可选工具伪报为通过；
本批无真实 API、无 artifact 改写。

## 4. 后续门

M1 只补 cohort receipt 与 machine-readable/human-readable report writer；M2 对完整固定 cohort 做
isolation-level paired cluster bootstrap。pilot/smoke 仍只证明管线与观测，不发布方法排名。
