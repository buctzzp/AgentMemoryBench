# Supermemory 接入说明

状态：`BLOCKED(source-unavailable self-hosted binary)`。当前没有 adapter，也没有真实 API
smoke。本页只保存跨会话必须复用的稳定事实；完整命令、官方 harness payload 与停工裁决见
[M1 ruling](../../workstreams/ws02.7-method-track/branches/method-recertification/supermemory/notes/supermemory-current-source-product-m1-ruling.md)，
逐项状态见
[integration ledger](../../workstreams/ws02.7-method-track/branches/method-recertification/supermemory/notes/supermemory-integration-ledger.md)。

## 当前来源边界

- 公开仓库：`supermemoryai/supermemory`，MIT；本项目锁到最新稳定 self-host release tag
  `server-v0.0.6` 对应 commit `566be208981aa23ef20a85fd50a737861b1b10b2`。
- 最新稳定 release 只提供安装脚本、checksum manifest 与各平台约 200–293 MB 的
  `supermemory-server` 可执行文件；公开 Git tree 没有该 server/engine 的实现源码，也没有
  从公开 tree 构建 release binary 的 workflow。
- 官方文档虽称 self-hosted binary 为 open source，但其链接仍回到同一公开仓库；官方
  issue [#1299](https://github.com/supermemoryai/supermemory/issues/1299) 正在询问 server source
  在哪里，截至 2026-08-02 仍开放且没有 maintainer 技术答复。因此当前只能确认
  **免费、可本机运行的 source-unavailable binary**，不能确认完整 OSS。
- Phase 1 对 Supermemory 的范围是 `self-host/local OSS`。在用户明确放宽范围前，不得用 cloud
  API 或这个不可审计 binary 偷换该格。

## 可见产品契约（不能替代源码审计）

稳定版文档声明：`POST /v3/documents` 异步写入 raw content，`containerTag` 负责隔离，返回
queued document；完成需轮询 document/memory 状态。检索走 hybrid search，混合 extracted
memory 与 raw document chunk；本地默认 embedding 是 `Xenova/bge-base-en-v1.5` 768d，build
LLM 可接 OpenAI-compatible endpoint。以上只是公开 API/文档事实，不能证明 binary 内部
extraction/update/storage/cleanup/usage 的实现与失败语义。

## 官方 benchmark 覆盖

- 官方 `supermemoryai/memorybench@118209a` 覆盖 LoCoMo、LongMemEval、ConvoMem；Supermemory
  provider 每 session 一次 raw-document add，完成门为 document 与 memory 双 `done`，检索为
  hybrid、limit 30、threshold 0.3、include summaries/chunks。
- 该 provider 虽有 `ProviderConfig.baseUrl`，初始化时只传 `apiKey`，所以 current harness 实际
  指向 hosted SDK 默认 endpoint，不能冒充 self-host local parity；`clear()` 也仍是 no-op。
- HaluMem 官方仓库另有 Supermemory wrapper：每 session 按 20 turns 分块、时间/role 内嵌，
  extraction 按 response id 读取；update 用 top-10，QA 默认 top-20，均启用 rerank、query
  rewrite、threshold 0.7。它同样只配置 cloud key。
- BEAM、MemBench 没有 Supermemory 官方 harness，若未来解锁均属于 framework extension。

## 解锁条件

满足任一项后重开 M1：

1. upstream 发布与稳定 binary 对应的完整 server/engine 源码及可复现 build；或
2. 用户明确把 Phase 1 口径从 `local OSS` 放宽为 `source-unavailable self-hosted binary`。

若走第 2 项，仍必须先做 binary checksum、进程/端口/data-dir ownership、双状态完成门、
containerTag 写/搜/单空间删除、failed ingest clean、W1/W2、API usage 可观测性和五格 payload
强反例；仅仅“HTTP 能通”不算接入完成。
