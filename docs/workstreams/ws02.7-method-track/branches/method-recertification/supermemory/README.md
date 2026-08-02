# Supermemory 重认证支线

## 范围

本支线负责 Supermemory current source/product/official-harness 取证、五 benchmark adapter、
机器化 smoke 与 B1-B11 冻结。benchmark 稳定事实直接复用 `docs/survey/` 与已冻结契约，不重做
dataset census。

## 当前状态

`BLOCKED(source-unavailable self-hosted binary)`。

公开控制/docs/SDK repo 已锁最新稳定 self-host tag `server-v0.0.6@566be208`，但实际
`supermemory-server` 仅以 release executable 发布，公开 MIT tree 没有 server/engine source
或可复现 build。现行 Phase 1 要求 `self-host/local OSS`，因此 adapter、TOML 与真实 smoke
均不得提前施工。解锁需要 upstream 发布完整 runtime source，或用户明确放宽/替换该 method
范围。

## 文档索引

- [M1 source/product/harness 裁决](notes/supermemory-current-source-product-m1-ruling.md)
- [Method integration ledger](notes/supermemory-integration-ledger.md)
- [稳定 integration page](../../../../../reference/integration/supermemory.md)

权威整体状态与当前跨 method 动作仍只写父级
[method-recertification README](../README.md) 与
[ws02.7 README](../../../README.md)。
