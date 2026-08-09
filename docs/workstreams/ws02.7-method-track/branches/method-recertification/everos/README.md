# EverOS 接入支线

## 范围

本支线负责 EverOS current source、公开算法依赖、官方 benchmark harness、产品 surface、
五 benchmark 差量适配、metric 资格、机器化 smoke 与 B1-B11 冻结。五家 benchmark 的 raw
schema、canonical id、异常账和私有边界直接复用稳定文档；除非 source lock 或共享契约漂移，
不得重做 dataset census。

## 当前状态

`M1_R1_ACCEPTED_READY_FOR_M2`。

官方稳定版锁为 `EverOS v1.2.3@48fc908`。产品运行时依赖的 `everalgo-*` 并非黑箱：对应
版本在官方 Apache-2.0 EverAlgo monorepo 均有可核 tag/source，因此通过 Phase 1 local OSS
source gate。当前公开 official harness 只覆盖 LoCoMo；论文报告 LongMemEval，但公开树没有
LongMemEval loader 或最终 payload，不能冒充可复现 author harness。

## 强制入口与顺序

1. [接入 ledger](notes/everos-integration-ledger.md)：M2 每关闭一门就原位更新，不靠聊天记忆；
2. [M1-R1 current source lock](notes/everos-v1.2.3-source-drift-m1-r1.md)：锁 current 版本、
   算法依赖和 v1.2.3 completion surface；
3. [历史 M1 source/product/harness 裁决](notes/everos-current-source-product-m1-ruling.md)：只继承
   M1-R1 明确证明 byte-stable 的官方覆盖、产品调用面和 payload；
4. M2 先完成 direct in-process product lifecycle、missing-time、owner/role、exact drain、
   provenance/readout 与五格零 API 强反例；
5. 生成并审阅 machine smoke plans 后停在真实 API 批准门；未经用户新批准不得烧 build、
   embedding、rerank、answer 或 judge API。

权威跨 method 状态仍只写父级 [method-recertification README](../README.md) 与
[ws02.7 README](../../../README.md)。
