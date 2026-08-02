# EverOS 接入实例（B1-B11 逐项）

> 判据模板：`../method-integration-checklist.md` §B；勾选总表：`../integration-status.md`。
> 当前状态：**M1 已验收，进入 M2 离线 adapter 门**；尚未运行真实 API smoke，也未冻结。

- 主 source：官方稳定版 `EverOS v1.2.1@4256419595f63fe307147dc19e379477cecdc44f`，
  Apache-2.0；本地路径 `third_party/methods/EverOS/` 为 local-only，可由
  `scripts/fetch_third_party_methods.sh` 恢复。
- 算法依赖：该 release 的 `uv.lock` 固定 `everalgo-*` 包；对应版本均能在官方
  `EverMind-AI/EverAlgo` Apache-2.0 monorepo找到精确 tag/source，source gate 已通过。
- 产品调用面：在隔离 worker 内进入官方 `create_app()` lifespan，直接调用与
  `/api/v2/memory/add|flush|search|get` 相同的 typed DTO/service。它仅省去 HTTP transport，
  不绕过 boundary、Episode、Cascade、OME、SQLite、LanceDB 或产品搜索算法。
- adapter：待 M2 实现。
- 官方 benchmark：current EverOS 与 EverAlgo 的公开 harness 只覆盖 LoCoMo；论文另报告
  LongMemEval，但没有公开 loader/final payload。HaluMem、BEAM、MemBench 均为 framework
  extension。

## 已关闭

- **B0 official identity**：current product LoCoMo harness 与 research `v93.05` harness
  分开记录，不拼成一条不存在的复现链；LongMemEval 诚实标
  `paper-reported / public-harness-unavailable`。
- **B1 source lock**：EverOS、EverAlgo runtime packages、license、local-only 恢复方式与
  用户本地 PDF 的负空间均已锁定。
- **B1 product surface**：主轨采用 typed product service；直接 EverAlgo stages、直接写库、
  单纯 sleep 或额外启动 HTTP host 均不进入主轨。
- **B8 retrieval side effect**：current SearchManager/service 是只读检索；telemetry 不计作
  memory mutation。

## M2 硬门

1. `consume_granularity=session` 候选必须经真实 product-chain 反例确认；assistant-first、连续
   role、singleton、odd tail 与 assistant-only session 不得通过改 role 或伪造自然语言回复掩盖。
2. 产品 timestamp 要求正整数毫秒，而框架要求缺失 source time 保持 `None`。MemBench 100k
   必须证明独立 transport-order time 不会变成可见事实，或做最小 preserve-none 扩展；不得借
   question time、相邻消息或墙钟伪造 source time。
3. LoCoMo 沿 official “两位 speaker 均 role=user、保留 sender identity”口径，但主轨仍须
   无损渲染共享 image caption；需裁定单 owner search 与双 owner 合并的资格和 top-k。
4. add/flush 返回不等于 Cascade/OME 完成。必须锁 exact scoped drain、失败传播、迟到任务、
   cleanup retry、resume 与独占 root/process ownership。
5. 检索 readout 必须保留产品返回的 Episode 顺序、score、time、session/sender；zero hit 与
   backend failure 分开。Episode→memcell→message lineage 只有在 reflection-off 且 sidecar
   一一可证时才可宣称 valid。
6. HaluMem extraction/update/QA/memory-type 四格分别裁定；`get` 全库结果不能冒充本 session
   delta，memory-type 当前仅是 N/A 候选。
7. build、embedding、rerank、answer、judge 观测和 model/runtime/source/transport 身份均须落
   manifest；真实 B11 前只做零 API preflight。

## 证据入口

- [EverOS 接入 ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-integration-ledger.md)
- [current source / product / official harness M1 裁决](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/notes/everos-current-source-product-m1-ruling.md)
- [EverOS 接入支线](../../workstreams/ws02.7-method-track/branches/method-recertification/everos/README.md)

M1 判词：`EVEROS_M1_ACCEPTED_READY_FOR_M2`。
