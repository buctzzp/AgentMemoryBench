# Letta/MemGPT 接入支线

## 范围

本支线只处理 Letta/MemGPT 的 current official product 接口、五 benchmark 差量适配、
metric 资格、真实 smoke 与冻结。五家 benchmark 的 raw schema、canonical id、已知异常和
私有边界复用稳定文档；除非 source lock 或共享契约漂移，不重做数据 census。

## 强制入口与顺序

1. [接入 ledger](notes/letta-integration-ledger.md)：先填 B0/B1 source 与 official harness，
   再写 adapter；任何 `BLOCKED` 立即停工。
2. M1 一手取证与架构裁决：算法、产品 surface、lifecycle、namespace、readout、官方
   benchmark harness。
3. M2 adapter + 五格 production-path 强反例。
4. `plan-smoke` 机器计划 → 用户批准真实 API → B11 artifact gate → frozen note。

父级 `../../README.md` 保存 method 重认证的权威顺序；本页只负责支线索引，不复制动态
commit、测试数或在途 actor 状态。
