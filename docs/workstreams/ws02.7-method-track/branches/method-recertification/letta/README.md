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
   ownership、产品 ingest/readout、五格 production-path 与离线门。
4. [method-frozen-v1](notes/letta-frozen-v1.md)：current v3 的 11 份真实 smoke、17 个
   conversation/question、全 evaluator 与 artifact/效率/隐私/外部状态机器门均已闭合；ledger
   已转 `frozen`。后续只有 source/contract 漂移、official-full、真实 resume 或效果实验才重开。

父级 `../../README.md` 保存 method 重认证的权威顺序；本页只负责支线索引，不复制动态
commit、测试数或在途 actor 状态。
