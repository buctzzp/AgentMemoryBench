# Letta/MemGPT 接入事实页

## 当前边界

Letta/MemGPT 已完成 M1 source/product identity 裁决，尚未完成 adapter 与真实 smoke：

- runtime source 锁为 Apache-2.0 的 legacy Letta V1 server `0.16.8` 产品内核；本地 pin
  `b76da9092518cbaa2d09042e52fdcbde69243e18` 与 current release/main 的产品代码无漂移。
- active Letta Code `v0.30.1` 是完整 agent harness，分类为 `ALGORITHM_VARIANT`，不能静默
  替换 legacy MemGPT/Letta V1。
- 主轨采用官方 `ai-memory-sdk v0.2.0` 的产品语义：role/content message batch 驱动
  memory-only sleeptime agent，等待 run 完成后读取 learned core blocks；框架在进程内调用
  同一 Letta 内核，不启动 HTTP host。
- direct archival insert/search 会绕过 core-memory learning，只可作以后显式 diagnostic
  profile，不能进入主表。
- current official repositories 对 Phase 1 五 benchmark 的 harness 覆盖为零，五格均是
  framework extension，不建立伪 `author_<benchmark>` 配置。

主轨的 retrieval readout 是演化后的 core blocks，初判不具备逐 source item 的 Recall/NDCG
资格；HaluMem QA 初判可测，extraction/update/memory_type 初判 N/A。上述 metric 判词仍须由
M2 生产路径与无损观测评估最终盖章。

## 证据入口

- [Method integration ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-integration-ledger.md)
- [Current product identity M1 裁决](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-current-product-identity-m1-ruling.md)
- [Letta/MemGPT 接入支线](../../workstreams/ws02.7-method-track/branches/method-recertification/letta/README.md)

完成 M1 架构师验收后，只把稳定结论回填本页；完整命令、源码行号、探针 stdout 与争议保留在
workstream note，避免稳定页变成施工流水账。
