# Runtime 配置与观测 M0-M5 计划

每一批均先完成 current-source 审计、再施工、再跑直接相关的无 API 门。真实 pilot 在 M5 完成且
用户重新确认规模/run_id 前保持暂停。

## M0：裁决与身份基线

- [x] 核查 Letta `embedding=None` 的官方 SDK、vendored server 与 current adapter 语义。
- [x] 固化配置所有权、controlled embedding、效率账和 HaluMem extraction 判据。
- [x] 将 ws05 恢复胶囊从“继续扩大 pilot”改为“pilot 暂停，先做本支线”。
- [x] 当前十家配置字段 census 与迁移清单写入 M1 note。

## M1：配置组合根与 embedding identity

- [x] 建立独立 runtime/execution 强类型配置，method loader 只接收 method-owned 字段。
- [x] 主 method 参数单源化；旧 `smoke/official_full` section 只读兼容并有退出门。
- [x] 兼容 method 迁到 MiniLM-384 controlled identity；EverOS 先闭合 provider/dimension/
  normalization/distance 与真实 public seam，Letta 明确 N/A。
- [x] manifest/resume 对完整 runtime、method、embedding 和 answer/judge identity fail-fast。

## M2：效率观测

- [x] 修 SimpleMem operation-level retrieval stage 误标。
- [x] 补 MemoryOS embedding build/retrieval observation。
- [x] 修 LangMem retrieval callback 守门和 Letta 无 collector 静默丢 usage。
- [x] 给 Mem0 reranker 建启用即必须被观测的门。
- [x] 新增失败尝试成本账，算法 artifact 回滚不得抹掉已发生 spend。

## M3：HaluMem session extraction

- [x] LangMem：验证并暴露产品 `ainvoke` changed items，而非只留 keys。
- [x] MemoryOS：验证 STM/MTM/LPM 边界；raw STM 不合格且强制迁移会改算法，维持 N/A。
- [x] Letta：验证 attached core blocks 的 session before/after changed-unit 快照。
- [x] MemOS：async business task 终态后完整 GetMemory stable-ID delta 成立，升级 valid。
- [x] 每家独立盖 valid/N/A，未用“一套 sidecar 全部补齐”。

## M4：资源画像与隔离

- [x] 用零 API、真实 benchmark loader + 真实本地 MiniLM 完成单 run、同 benchmark 双 run、
  跨 benchmark 双 run 画像；记录 RSS/USS、模型副本、dataset materialization 与阶段耗时。
  macOS 本机未暴露 PSS，产品 DB/HTTP 连接、queue 与端到端吞吐留给真实 pilot，均明确记
  N/A，未用估算冒充实测。
- [x] 区分 product-native namespace、混合隔离与当前必须物理隔离的方法；namespace 不等于
  runtime、tokenizer 或 mutable store 可安全共享。
- [x] 实测确认每个 run 会重复 materialize dataset/model，但尚无跨 method 共享的并发安全与
  语义守恒证据；本批不造全局 singleton，先保留 bounded admission control，服务化 embedder/
  dataset cache 只作为真实 pilot 后的候选优化。

## M5：无 API 验收

- [x] 定向测试、架构门、文档门、compileall 与全量无 API 回归。
- [x] 零成本 fake/sentinel 验证 manifest/resume、阶段、失败账、session delta 与 secret 负空间。
- [x] 输出真实 pilot 前的重建矩阵与新 run-id 计划；真实 API pilot 仍停在用户重新批准门前。
