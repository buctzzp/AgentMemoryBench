# LangMem 接入支线

## 范围

本支线只处理 current LangMem 产品接口、五 benchmark 差量适配、metric 资格、真实
smoke 与冻结。五家 benchmark 的 raw schema、canonical id、已知异常和私有边界复用稳定
文档；只有 source lock、shared contract 漂移或新一手反证才重开 benchmark census。

## 强制入口与顺序

1. [接入 ledger](notes/langmem-integration-ledger.md)：任何 adapter 代码前先逐格登记
   `PASS/N/A/PENDING/BLOCKED`，不得靠旧审计惯性跳格。
2. M1 已完成：current source/product/official-harness、background manager、
   store/namespace、完成门与五格 metric 资格见
   [M1 ruling](notes/langmem-current-product-identity-m1-ruling.md)。
3. M2 离线门已完成：provider v3 adapter、独立 runtime、原子状态、五格 production-path
   强反例、living dossier 与 20 份机器 smoke plan 均已验收；最小恢复入口见
   [M2 检查点](notes/langmem-m2-adapter-checkpoint.md)。
4. 当前停在 B11 真实 smoke 批准门；真实 API 仍须用户另行批准预算、规模与 run id。

Letta/MemGPT 已完成离线 M2，仍独立停在真实 B11 批准门；LangMem 的离线施工不代替也不
取消该批准门。LangMem 当前 ledger 也已为 `ready_for_smoke`，但不是 frozen；父级
`../README.md` 与 ws02.7 恢复胶囊保存权威动态状态，本页只作支线索引。
