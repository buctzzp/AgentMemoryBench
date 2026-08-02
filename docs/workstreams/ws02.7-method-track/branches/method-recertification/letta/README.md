# Letta/MemGPT 接入支线

## 范围

本支线只处理 Letta/MemGPT 的 current official product 接口、五 benchmark 差量适配、
metric 资格、真实 smoke 与冻结。五家 benchmark 的 raw schema、canonical id、已知异常和
私有边界复用稳定文档；除非 source lock 或共享契约漂移，不重做数据 census。

## 强制入口与顺序

1. [接入 ledger](notes/letta-integration-ledger.md)：先填 B0/B1 source 与 official harness，
   再写 adapter；任何 `BLOCKED` 立即停工。
2. [M1 current product identity 裁决](notes/letta-current-product-identity-m1-ruling.md)：已锁
   source、官方五格覆盖、Letta Code 分轨与 sleeptime-memory 主产品接口；lifecycle、namespace、
   readout 和 metric 的生产证据继续由 M2 闭合。
3. [M2 adapter 检查点](notes/letta-m2-adapter-checkpoint.md)：独立 worker、PostgreSQL
   ownership、产品 ingest/readout、五格 production-path、离线全量与 11 份 machine plan 已闭合；
   ledger 现为 `ready_for_smoke`。
4. 当前只等用户批准 planner 中的真实 API 预算与 run ids，再执行 B11 predict/evaluate、artifact
   gate 与 frozen note。

父级 `../../README.md` 保存 method 重认证的权威顺序；本页只负责支线索引，不复制动态
commit、测试数或在途 actor 状态。
