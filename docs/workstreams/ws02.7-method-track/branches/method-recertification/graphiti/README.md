# Graphiti method 重认证支线

状态：`METHOD_FROZEN_V1`

## 范围

Graphiti 经用户 2026-08-09 裁定接替 source-unavailable 的 Supermemory，成为 Phase 1 第十家
method。这里接入的是 **Graphiti OSS**，不是 Zep hosted product，也不宣称 Zep parity。

## 恢复入口

1. 父级 [`ws02.7 README`](../../../README.md) 热胶囊；
2. [`Graphiti method-frozen-v1`](notes/graphiti-frozen-v1.md)；
3. [`Graphiti integration ledger`](notes/graphiti-integration-ledger.md)；
4. 需要追溯时再读 [`M3 implementation`](notes/graphiti-v0.29.3-product-adapter-m3-implementation.md)、
   [`B11 首次真实尝试`](notes/graphiti-b11-first-live-attempt.md) 或
   [`五格 dossier`](notes/graphiti-five-benchmark-safety-dossier.md)；
5. 稳定页 [`docs/reference/integration/graphiti.md`](../../../../../reference/integration/graphiti.md)。

## 当前动作

18 份 v2 machine plan 已完成真实 predict/evaluate；机器验收覆盖 35 conversation、35 question、
88 个真实 product episode，并对 FalkorDB payload 做字节级反查。所有 croppable variant 的
W1/W2 与 HaluMem Medium/Long 固定 W1 均通过；MemBench 100k 因 mandatory source time
继续 N/A。当前无 Graphiti 施工动作；冻结身份、缺口与解冻触发器以
[`graphiti-frozen-v1.md`](notes/graphiti-frozen-v1.md) 为准。

## 稳定依赖顺序

```text
M1 source/product/harness
  → M2 runtime/config/lineage audit
  → M3 adapter + five-grid counterexamples
  → machine plan/preflight
  → user-approved B11 smoke
  → artifact gate + frozen sync
```
