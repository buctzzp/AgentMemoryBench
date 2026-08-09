# Third-Party Method Sources

| 目录名 | upstream URL | 版本锚点 | 管理方式 |
| --- | --- | --- | --- |
| A-mem-product | https://github.com/agiresearch/A-mem | ceffb860f0712bbae97b184d440df62bc910ca8d | git-tracked；Phase 1 通用产品 |
| A-mem | https://github.com/WujiangXu/AgenticMemory | 上游 revision 未留存；本仓库 97e9d44 导入 | git-tracked；论文实验/复现参照 |
| LightMem | https://github.com/zjunlp/LightMem | 以本仓库提交历史为准 | git-tracked（随本仓库提交） |
| MemoryOS-main | https://github.com/BAI-LAB/MemoryOS | 以本仓库提交历史为准 | git-tracked（随本仓库提交） |
| mem0-main | https://github.com/mem0ai/mem0 | 以本仓库提交历史为准 | git-tracked（随本仓库提交） |
| MemOS | https://github.com/MemTensor/MemOS.git | v2.0.25 / e820406269537b97d270687e3e40eea2f015f81a + 本项目 failure-observability / benchmark-adaptation patch | local-only；按 fetch 脚本恢复（幂等应用 `scripts/patches/memos-product-runtime-observability.patch`；覆盖 reader/storage/scheduler 失败传播、`sentence_transformer` factory、search failure、opencodego JSON output 与成功 response usage callback，不改变成功路径 memory 算法） |
| SimpleMem | https://github.com/aiming-lab/SimpleMem.git | 60a48e83a7fef10d386e1f438589047d3a4257bc | local-only；按 fetch 脚本恢复 |
| cognee | https://github.com/topoteretes/cognee.git | f7e2267cf02f5df15c4b60bf196b30ac2c06b32d | local-only；按 fetch 脚本恢复 |
| LangMem | https://github.com/langchain-ai/langmem.git | 56d85939d80bb731bd5e237567148d817d7bfd16（package 0.0.30） | local-only；按 fetch 脚本恢复；current remote 相对旧 pin 仅 `uv.lock` 依赖维护漂移，产品源码未变 |
| letta | https://github.com/letta-ai/letta.git | b76da9092518cbaa2d09042e52fdcbde69243e18 | local-only；按 fetch 脚本恢复 |
| graphiti | https://github.com/getzep/graphiti.git | v0.29.3 / 021d3a57d511f21b10adaf7fa923bd5c1fce5e9d | local-only；按 fetch 脚本恢复。Graphiti 是 Apache-2.0 temporal context graph engine，不冒充 Zep 托管产品；Phase 1 用 direct core product surface，source/product 裁决见 ws02.7 |
| EverOS | https://github.com/EverMind-AI/EverOS.git | v1.2.3 / 48fc9084888bc17100053227284f939a5aca5e91 | local-only；按 fetch 脚本恢复并应用 `scripts/patches/everos-product-runtime-observability.patch`。patch 只让 lifespan shutdown 失败在全部 provider settle 后向调用方可见，不改成功路径或算法。运行算法依赖由该版本 `uv.lock` 固定，公开源码对应 EverMind-AI/EverAlgo 的精确 package tags。用户本地 `EverMemOS.pdf` 不属于恢复资产 |

## 已退出 Phase 1 的 source-gate 快照

- `supermemoryai/supermemory@server-v0.0.6/566be208` 曾作为第十格候选；其公开 control/docs
  repo 不含 self-host memory engine/server source，稳定 runtime 只发布 executable。2026-08-09
  用户裁定由 Graphiti 接替，因此 fetch 脚本不再恢复它；完整证据保留在 ws02.7 Supermemory
  M1 note，禁止把残留本地 checkout 当成 active method source。
