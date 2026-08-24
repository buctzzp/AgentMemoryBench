# Runtime 配置、模型身份与效率观测支线

本支线承接 ws05 在扩大 pilot 前暴露的三类共同前置问题：method TOML 混入通用运行参数、
embedding 比较口径尚未最终统一、部分 method 的模型调用/失败成本观测存在缺口。权威进度与
当前动作仍只写父级 [`ws05 README`](../../README.md)，本页只提供范围和文档导航。

## 范围

- 把 method 算法参数、API runtime、benchmark answer/judge、执行器参数分成明确所有权；
- 对所有**实际消费 embedding** 且接口兼容的方法建立 MiniLM-384 controlled 主比较身份；
- 不给不消费 embedding 的产品路径伪造模型配置；
- 修复 retrieval/build 阶段模型调用的阶段归属、漏观测和失败尝试成本账；
- 在改造 HaluMem session extraction 前逐家证明产品级增量可观测性；
- 先测资源画像，再裁逻辑隔离或模型/数据共享，不凭直觉造全局 singleton。

## 文档导航

- [规格与长期边界](spec.md)
- [M0-M5 实施计划](plan.md)
- [M0 架构裁决与 Letta embedding 调研](notes/2026-08-24-m0-ruling.md)
- [M1 配置字段 census](notes/2026-08-24-m1-config-census.md)
- [M1 配置组合根与 controlled embedding 实现](notes/2026-08-24-m1-implementation.md)
- [M2 模型调用观测与失败成本账](notes/2026-08-24-m2-efficiency-observability.md)
- [M3 HaluMem session extraction 裁决与实现](notes/2026-08-24-m3-halumem-session-extraction.md)
- [M4 零 API 资源画像与隔离裁决](notes/2026-08-24-m4-resource-profile.md)
- [M5 无 API 验收与重建矩阵](notes/2026-08-24-m5-no-api-acceptance.md)

## 稳定依赖顺序

```text
M0 裁决与身份
  -> M1 配置组合根/embedding manifest
  -> M2 效率观测与失败成本
  -> M3 HaluMem extraction 资格
  -> M4 资源画像与隔离裁决
  -> M5 无 API 回归/零成本哨兵
  -> 用户重新批准后才恢复真实 pilot
```
