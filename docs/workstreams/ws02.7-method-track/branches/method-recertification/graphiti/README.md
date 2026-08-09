# Graphiti method 重认证支线

状态：`M1_SOURCE_PRODUCT_LOCKED`

## 范围

Graphiti 经用户 2026-08-09 裁定接替 source-unavailable 的 Supermemory，成为 Phase 1 第十家
method。这里接入的是 **Graphiti OSS**，不是 Zep hosted product，也不宣称 Zep parity。

## 恢复入口

1. 父级 [`ws02.7 README`](../../../README.md) 热胶囊；
2. [`Graphiti v0.29.3 source/product M1`](notes/graphiti-v0.29.3-source-product-m1-ruling.md)；
3. [`Graphiti integration ledger`](notes/graphiti-integration-ledger.md)；
4. 稳定页 [`docs/reference/integration/graphiti.md`](../../../../../reference/integration/graphiti.md)。

## 当前动作

M2 只做 product-runtime 审计与离线 adapter：direct `Graphiti.add_episode/search`、嵌入式
FalkorDB Lite、OpenAI-compatible build LLM、本地 embedding、RRF search、namespace clean、
五格输入与 metric 资格。未经 Graphiti 自己的预算/plan 批准，不调用真实 LLM、answer 或 judge
API；Letta/LangMem/EverOS 已获批的 smoke 额度不自动扩张到本支线。

## 稳定依赖顺序

```text
M1 source/product/harness
  → M2 runtime/config/lineage audit
  → M3 adapter + five-grid counterexamples
  → machine plan/preflight
  → user-approved B11 smoke
  → artifact gate + frozen sync
```
