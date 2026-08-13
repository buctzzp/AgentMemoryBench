# EverOS 接入支线

## 范围

本支线负责 EverOS current source、公开算法依赖、官方 benchmark harness、产品 surface、
五 benchmark 差量适配、metric 资格、机器化 smoke 与 B1-B11 冻结。五家 benchmark 的 raw
schema、canonical id、异常账和私有边界直接复用稳定文档；除非 source lock 或共享契约漂移，
不得重做 dataset census。

## 当前状态

`EVEROS_METHOD_FROZEN_V1`。

官方稳定版锁为 `EverOS v1.2.3@48fc908`。产品运行时依赖的 `everalgo-*` 并非黑箱：对应
版本在官方 Apache-2.0 EverAlgo monorepo 均有可核 tag/source，因此通过 Phase 1 local OSS
source gate。当前公开 official harness 只覆盖 LoCoMo；论文报告 LongMemEval，但公开树没有
LongMemEval loader 或最终 payload，不能冒充可复现 author harness。

current v6 已完成 official lifespan typed-product adapter、五格输入、exact drain、物理隔离/
cleanup、Episode readout、metric 资格、效率观测与五格安全档案。18 份真实 plan、35 个
conversation/question、8 个 croppable variant 的 W1/W2、HaluMem Medium/Long fixed W1 与全部
artifact/隐私/state 门均已闭合；MemBench 100k 因缺 source time 且产品会把 timestamp 写入 Episode，
诚实标 unsupported。冻结证书见 [everos-frozen-v1](notes/everos-frozen-v1.md)。

## 强制入口与顺序

1. [M2 检查点](notes/everos-m2-adapter-checkpoint.md)：压缩恢复只读的热入口；
2. [接入 ledger](notes/everos-integration-ledger.md)：逐门状态与唯一下一动作；
3. [M2 实现记录](notes/everos-m2-adapter-implementation.md)：产品调用图、completion、state 与
   observability；
4. [五格安全档案](notes/everos-five-benchmark-safety-dossier.md)：role/time/image/异常/metric；
5. [machine plans](notes/everos-smoke-plans-v1.json)：冻结的 18 份 planner 原始 argv；
6. [frozen-v1](notes/everos-frozen-v1.md)：最终 B1-B11、artifact 与声明缺口；
7. 只有 source/product drift 才回读 [M1-R1](notes/everos-v1.2.3-source-drift-m1-r1.md) 与
   [历史 M1](notes/everos-current-source-product-m1-ruling.md)，不得正常恢复时重做 source survey。

冻结后未经用户新批准不得继续烧 official-full、作者校准、resume 或效果 API。HaluMem 是 fixed
shape，禁止给 plan 追加通用裁剪参数。

权威跨 method 状态仍只写父级 [method-recertification README](../README.md) 与
[ws02.7 README](../../../README.md)。
