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
| supermemory | https://github.com/supermemoryai/supermemory.git | server-v0.0.6 / 566be208981aa23ef20a85fd50a737861b1b10b2 | local-only public control/docs repo；按 fetch 脚本恢复。注意：同名 self-host runtime 只以 release binary 发布，公开 tree 无 server/engine 源码，当前不满足 Phase 1 local OSS 门 |
| EverOS | https://github.com/EverMind-AI/EverOS.git | v1.2.3 / 48fc9084888bc17100053227284f939a5aca5e91 | local-only；按 fetch 脚本恢复。运行算法依赖由该版本 `uv.lock` 固定，公开源码对应 EverMind-AI/EverAlgo 的精确 package tags；无本项目 patch。用户本地 `EverMemOS.pdf` 不属于恢复资产 |
