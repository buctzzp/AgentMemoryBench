# API runtime smoke 支线

## 范围

把低预算 `smoke` 与正式 `official_full` 的 provider/model/transport 身份显式化，
确保 prediction、resume、evaluate 与 artifact 不会因 `.env` 或默认模型变化而静默漂移。
本支线不改变 benchmark prompt/metric，也不重跑已冻结 method 的效果实验。

## 稳定入口

- 长期政策：
  [`docs/reference/api-runtime-profiles.md`](../../../../reference/api-runtime-profiles.md)
- 实施与验收：
  [`notes/opencodego-smoke-runtime-implementation.md`](notes/opencodego-smoke-runtime-implementation.md)
- 当前 economy 模型迁移：
  [`notes/2026-08-21-muse-to-mimo-runtime-ruling.md`](notes/2026-08-21-muse-to-mimo-runtime-ruling.md)

状态与最终 test/commit 快照只写父
[`ws02.7 README`](../../README.md)；本页不复制活状态。
