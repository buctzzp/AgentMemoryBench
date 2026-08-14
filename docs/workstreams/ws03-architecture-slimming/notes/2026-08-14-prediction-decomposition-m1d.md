# M1-D：prediction 编排按责任拆分

日期：2026-08-14

范围：`runners/prediction.py` 的 planning / preflight / ingest / answer / parallel

性质：零 API、零 schema、零实验语义变化的结构减重

## 1. 裁决

原 `prediction.py` 同时拥有范围选择、resume identity、provider 生命周期、事件流写入、
retrieve-first answer、isolated worker 调度与效率收口，存在多个独立变化原因。M1-D 按依赖
方向抽成六个叶模块：

| owner | 唯一职责 |
| --- | --- |
| `prediction_planning.py` | 公开运行策略、checkpoint 状态解释、conversation/question work plan |
| `prediction_observability.py` | prediction 效率摘要与单调耗时换算 |
| `prediction_preflight.py` | manifest/resume、公开身份、provider 协议与 prepare/cleanup 边界 |
| `prediction_ingest.py` | event aggregation、ingest、turn checkpoint、session report |
| `prediction_answer.py` | retrieve-first、answer builder/reader、answer prompt artifact 与回答校验 |
| `prediction_parallel.py` | 稳定分片、isolated worker 生命周期、局部失败与协调线程提交 |

原 `memory_benchmark.runners.prediction` 保留兼容 façade，只定义
`PredictionRunSummary` 与 `run_predictions()`。顶层运行仍在同一处按原顺序编排上述责任，
没有新建第二套 runner 或 method × benchmark 特判。

## 2. 依赖方向

内部依赖是单向 DAG：

```text
planning ──→ preflight ──→ answer ──────────┐
    └──────────────→ ingest ────────────────┼──→ parallel
observability ─────→ ingest / answer ───────┘

planning / preflight / ingest / answer / parallel
                         └────────────────────→ prediction façade / orchestration
```

准确允许集由 `tests/test_architecture_boundaries.py` 锁定。六个叶模块均不得 import
`memory_benchmark.runners.prediction`；façade 可以组合和重新导出叶实现。这样叶函数不依赖
组合根，既避免循环 import，也避免未来把实现悄悄塞回 façade。

## 3. 兼容边界

### 3.1 保留

- `PredictionRunPolicy`、`PredictionRunSummary`、`run_predictions` 的原 import 路径；
- 仓库当前使用的 `_build_prediction_work_plan`、`_method_manifest_with_protocol`、
  `_answer_question_retrieve_first`、`_isolated_worker` 等内部 private import；
- private 名称从 façade 取得时与 canonical leaf 是同一 Python object，不复制 wrapper；
- run manifest、resume compare、artifact 文件名/字段/排序、prompt、metric 与 provider 调用顺序；
- shared 与 isolated provider 的 prepare/cleanup、失败状态、checkpoint 与效率观测语义。

### 3.2 未承诺

项目仍为 `0.1.0`，这些下划线名称不是新公共 API。façade 是有退出预算的内部迁移兼容层；
本批只保证现有消费者不被结构迁移打断，不承诺永久公开所有 private symbol。

## 4. 自动边界门

新增三类架构断言：

1. 每个 `prediction_*` 叶模块的内部依赖必须精确符合 §2；
2. façade 顶层只能定义 summary 与 orchestration，不能重新吸回叶实现；
3. planning/preflight/ingest/answer/parallel 的代表性旧 import 与 canonical leaf identity 相同。

这三类门检查真实 AST/import 与 object identity，不以文件行数、命名整齐或人工 code review
冒充边界证明。

## 5. 文件与行为守恒

生产改动限于：

- 新增六个 `runners/prediction_*.py` 叶模块；
- `prediction.py` 删除迁出的唯一实现并显式 re-export，保留顶层 orchestration；
- 增加 architecture tests。

`prediction.py` 从 3,337 行降到 584 行，顶层定义从多个责任收敛为 2 个；拆分后的总代码行数
不是减重 KPI，因为模块 docstring、明确 import 与兼容 re-export 会增加少量结构代码。真正的
验收是定义单源、依赖单向和全量行为守恒。

本批没有修改 registry、method adapter、benchmark policy、metric、prompt、TOML、resume
schema、third-party、data/models/outputs，也没有调用真实 API。

## 6. 分层验证

叶模块每迁出一层即执行直接相关门：

- planning：`16 passed, 140 deselected in 0.34s`；
- preflight/manifest/resume：`151 passed, 246 deselected in 1.81s`；
- ingest/checkpoint/session report：`28 passed, 153 deselected in 0.47s`；
- answer/retrieval/token/prompt：`158 passed, 38 deselected in 3.04s`；
- parallel/isolated worker：`199 passed, 14 deselected in 1.47s`。

收口门：

- 对 `main@a75f5e3` 原文件与当前 façade + 六叶模块做去 docstring 的 top-level AST 对表：
  `old=79 current=79 missing=[] extra=[] changed=[]`；迁移定义 79/79 单源且语义树一致；
- architecture + prediction/CLI/registry/operation/evaluation 承重集：
  `441 passed, 12 warnings in 9.50s`；
- architecture + 文档门：`15 passed in 2.39s`；
- `uv run python -m compileall -q src/memory_benchmark tests`：exit 0；
- 无 API 全量：
  `2228 passed, 3 deselected, 25 warnings, 29 subtests passed in 154.30s`；
- `git diff --check`：通过。

全量门使用 primary/OpenCodeGo dummy key 与本机拒绝端口，并排除 `api` marker；没有真实网络
调用。25 个 warning 与前批画像一致：LightMem Pydantic、legacy CLI FutureWarning、MemOS
datetime/Pydantic，不是本批新增运行错误。

## 7. 停手线

M1-A 至 M1-D 的四条承重线均已完成：依赖倒置、TOML profile、isolated transport 与
prediction 拆责。按 M1 原裁决，ws03 在此停止施工，不顺手拆 registry、不启动 M1-E，也不把
结构治理无限延长。为保证 compact hook 仍能定位唯一热胶囊，ws03 暂时保留为唯一
`in-progress/P0` **决策门**，但没有在途实现；用户选定下一主线后再原子切换状态。
