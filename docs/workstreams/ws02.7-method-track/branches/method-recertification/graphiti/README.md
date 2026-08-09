# Graphiti method 重认证支线

状态：`M3_ACCEPTED；B11_PAUSED_EXTERNAL_OPENCODEGO_REGION_OPT_IN`

## 范围

Graphiti 经用户 2026-08-09 裁定接替 source-unavailable 的 Supermemory，成为 Phase 1 第十家
method。这里接入的是 **Graphiti OSS**，不是 Zep hosted product，也不宣称 Zep parity。

## 恢复入口

1. 父级 [`ws02.7 README`](../../../README.md) 热胶囊；
2. [`Graphiti v0.29.3 M3 implementation`](notes/graphiti-v0.29.3-product-adapter-m3-implementation.md)；
3. [`B11 首次真实尝试`](notes/graphiti-b11-first-live-attempt.md)；
4. [`Graphiti 五格 dossier`](notes/graphiti-five-benchmark-safety-dossier.md)；
5. [`Graphiti integration ledger`](notes/graphiti-integration-ledger.md)；
6. 稳定页 [`docs/reference/integration/graphiti.md`](../../../../../reference/integration/graphiti.md)。

## 当前动作

M3 离线 adapter、五格强反例与 18 份 machine plan 已闭合。首个 LoCoMo W1 已到达
OpenCodeGo product build 请求，但 workspace 因区域模型尚未显式 opt-in 返回 HTTP 403；其余
计划没有继续。当前不得重复请求相同外部门。opt-in 完成后按
[`B11 首次真实尝试`](notes/graphiti-b11-first-live-attempt.md) 的恢复命令，从既有 failed-ingest
run 执行 physical clean + retry；成功后再逐 run artifact gate。MemBench 100k 是明确 N/A，
没有命令，也不得补造时间。

## 稳定依赖顺序

```text
M1 source/product/harness
  → M2 runtime/config/lineage audit
  → M3 adapter + five-grid counterexamples
  → machine plan/preflight
  → user-approved B11 smoke
  → artifact gate + frozen sync
```
