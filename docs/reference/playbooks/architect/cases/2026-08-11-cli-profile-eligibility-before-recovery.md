---
id: architect-case-cli-profile-eligibility-before-recovery
date: 2026-08-11
triggers: [smoke, resume, recovery-command, cli-preflight, run-identity]
supersedes: []
---

# 恢复命令先过上层资格，不能从底层能力反推

## 1. 观察到了什么

Graphiti 首次真实 smoke 在 ingest 前命中外部 403。架构师看到 generic prediction runner 已有
failed-ingest physical clean 与 resume 机制，便在恢复 note 里写出
`predict smoke --resume --retry-failed-conversations`。current CLI 实际在
`_normalize_smoke_prediction_args()` 明确拒绝这两个参数，既有强反例也已锁定该行为。

## 2. 原裁决为何不够

原裁决只验证了底层 runner “能做什么”，没有验证当前产品入口、subcommand 与 profile
“允许调用什么”。调用链中的下层能力并不自动向上暴露；把 formal 的恢复能力套给 smoke，
会制造一条看似精确、实际必然在 preflight 阶段失败的命令。

## 3. 新裁决及适用边界

任何恢复命令都必须重新经过当前入口的 parser/normalizer/preflight，优先使用机器生成的
plan 与现有 CLI 强反例。若 smoke 明确不可 resume：

1. 旧失败 run 保留为失败阶段证据，不改写；
2. 修正 identity 后生成全新 run_id；
3. 新 run 与旧 checkpoint/state 不合并；
4. 只有 formal/official 入口明确允许时，才使用底层 clean + resume。

该裁决不否定 generic runner 的 resume 机制；它只约束从底层能力到上层可用命令的推理。

## 4. 一手证据

- `src/memory_benchmark/cli/main.py::_normalize_smoke_prediction_args()`；
- `tests/test_main_cli.py::test_predict_smoke_rejects_resume_and_retry_failed`；
- `docs/workstreams/ws02.7-method-track/branches/method-recertification/graphiti/notes/graphiti-b11-first-live-attempt.md`。

## 5. 什么触发重读

遇到 failed run、准备写 resume/retry/clean 命令、跨 smoke/formal 复用命令，或从 runner
实现推导 CLI 能力时，检索 `cli-profile-eligibility`、`recovery-command`、`resume`。

## 6. 退出条件

只有当 current CLI 明确开放 smoke resume、planner 能生成该命令，并有真实强反例覆盖
failed-ingest → clean → resume 全链时，才能 supersede 本卡中“smoke 换新 run identity”的结论。
