# Supermemory current source / product identity M1 裁决

日期：2026-08-02
状态：`BLOCKED_SOURCE_UNAVAILABLE_LOCAL_BINARY`
范围：锁定当前官方来源、stable self-host release、官方 benchmark harness 与 Phase 1
资格边界；不实现 adapter，不下载/启动 binary，不调用 cloud 或模型 API。

## 1. 结论

Supermemory 当前提供的是**可本机运行、但运行时核心源码不可得的预编译 server binary**。
公开仓库有 MIT license、SDK/validation/docs/UI/MCP 代码，也明确宣传 self-host/open source；然而
最新稳定 `server-v0.0.6` 的实际 ingest/extract/update/search/storage engine 不在公开 tree，
release 也没有 source/build workflow，只发布各平台 executable。

项目 Phase 1 锁的是 Supermemory `self-host/local OSS`，不是“能在本机启动即可”。因此当前
不能把 hosted API 偷换进矩阵，也不能把 source-unavailable binary 盖章为 OSS 后先写 adapter。
M1 在此停工；这不是算法能力判负，而是来源与可审计性资格不满足。

## 2. 一手 source lock

### 2.1 公开控制仓库

- upstream：`https://github.com/supermemoryai/supermemory.git`
- vendored：`third_party/methods/supermemory`
- license：MIT，见 `third_party/methods/supermemory/LICENSE`
- 最新 remote main（2026-08-02 现场）：
  `a787041ca7a1be48b3f7ba5b0a1ffc62e4159879`
- 最新稳定 self-host release：`server-v0.0.6`，发布于 2026-07-19，tag/commit：
  `566be208981aa23ef20a85fd50a737861b1b10b2`
- 更新较新的 `server-v0.0.7-rc.2@816b85d7` 是 prerelease，不替代稳定主锁。

本项目把 vendored public tree 与 fetch pin 从 2026-07-03 的 `acd2fea9` 更新到稳定 tag 对应
commit `566be208`。这是**控制仓库/文档/API schema 锁**，不是 runtime source 锁。

### 2.2 Release 真实内容

GitHub release API 现场列出的稳定资产只有：

```text
install.sh                              11,138 bytes
manifest.json                              566 bytes
supermemory-server-darwin-arm64     203,273,920 bytes
supermemory-server-darwin-x64       215,164,592 bytes
supermemory-server-linux-arm64      216,604,098 bytes
supermemory-server-linux-x64        242,800,223 bytes
supermemory-server-windows-x64.exe  292,644,864 bytes
```

darwin-arm64 官方 checksum：

```text
da76cc35f6d04807585826bfb91a1cb51c1702fe0b610731a4010717c2ef9681
```

`install.sh` 的实现是：解析 stable release → 下载对应 binary → 对 manifest checksum → 放入
`~/.supermemory/bin` → 生成 wrapper；它没有获取 source 或执行 build。稳定 tag 的公开 tree：

```text
server implementation candidates excluding docs/mcp/web: 0
release/build workflow refs: 0
```

仓库的 `.github/workflows/` 只有 web/SDK/MCP 等 CI/publish workflow，没有 server release
build。GitHub 自动生成的 source archive 因此仍只是这个不含 engine 的公开 tree。

### 2.3 宣传与可验证事实冲突

稳定文档
`third_party/methods/supermemory/apps/docs/self-hosting/overview.mdx:8-31,59-72` 声称：

- self-host binary 与 hosted 使用相同 memory engine/API；
- binary 包含 graph engine、local embedding 与完整 Memory API；
- self-hosted “free, open source”。

但 “open source” 链接 `https://git.new/memory` 只重定向回同一公开仓库。官方 issue
[#1299](https://github.com/supermemoryai/supermemory/issues/1299) 于 2026-07-17 精确询问
server source/build instructions 在哪里；截至 2026-08-02 仍 open，仅有自动 issue tracker
comment，没有 maintainer 技术答复。

裁决使用最窄、可证表述：

```text
source-unavailable self-hosted binary
```

不宣称它一定是 proprietary，也不接受仅凭文档标签把它判成完整 OSS。

## 3. B0 官方 benchmark harness matrix

### 3.1 Supermemory 官方 MemoryBench

官方独立 repo：`supermemoryai/memorybench`，current
`118209a746d97d0d85e5a7234267f0b6962857e9`，MIT，SDK `supermemory@4.0.0`。覆盖 LoCoMo、
LongMemEval、ConvoMem；Phase 1 的 HaluMem、BEAM、MemBench 不在该 repo 的 benchmark roster。

最终 product payload 来自
`第三方框架参考/memorybench/src/providers/supermemory/index.ts:24-140`：

| 维度 | current harness 事实 |
| --- | --- |
| client | `new Supermemory({apiKey})`；`ProviderConfig.baseUrl` 未传入 |
| ingest | 每个 canonical session 一次 `client.add()` |
| content | 可选 session date header + `JSON.stringify(session.messages)`，转义 `<`/`>` |
| namespace | 一个 `containerTag`；metadata 为 sessionId 与可选 ISO date |
| completion | 轮询 document；终态后再读 memory；两者都 `done` 才 complete |
| failed | 收集并 warn，没有把 failed count 传播成 run failure |
| search | hybrid，limit 30，threshold 默认 0.3，include summaries/chunks |
| clean | `clear()` 仅 warning，未实现 |

LoCoMo canonical 在该 repo 固定 `speakerA→user / speakerB→assistant`，同时保留 `speaker` 字段；
LongMemEval 保持每 session 原始 role/content。官方 provider 最终将两者都序列化成 session 文档。

关键裁决：该 harness **不是 self-host parity**。虽然 provider config type 有 `baseUrl?`，实际
initialize 没有消费它，SDK 默认连 hosted endpoint。其结果可作 cloud `author_*` 线索，不能
直接进入本项目 local OSS 主轨。

### 3.2 HaluMem 官方 wrapper

`third_party/benchmarks/HaluMem-main/eval/eval_supermemory.py:31-144,157-248` 是 benchmark
官方侧的 Supermemory wrapper：

- `client=Supermemory(api_key=...)`，仍未传 local base URL；
- 每 session 的 dialogue 按 20 turns 分块；每行渲染
  `[{timestamp}]{role}: {content}`；同一 user namespace；
- 每个 response id 轮询 `memories.get()`，再读取该 response 的 extracted memories；
- update probe：top-10，`rerank=True`、`rewrite_query=True`、threshold 0.7；
- QA：默认 top-20，同样的 search 开关；
- 它能表达 HaluMem extraction/update/QA，但不能证明 local binary 与 hosted pipeline 等价。

### 3.3 唯一分类

| Benchmark | 官方覆盖 | 当前分类 |
| --- | --- | --- |
| LoCoMo | Supermemory MemoryBench，hosted 默认 endpoint | `author_locomo cloud candidate`，非 local 主轨 |
| LongMemEval | Supermemory MemoryBench，hosted 默认 endpoint | `author_longmemeval cloud candidate`，非 local 主轨 |
| HaluMem | HaluMem 官方 wrapper，hosted 默认 endpoint | `external official cloud candidate` |
| BEAM | 无 | framework extension（若 source 门解锁） |
| MemBench | 无 | framework extension（若 source 门解锁） |

## 4. 文档可见的产品契约

稳定版 self-host 文档能锁以下**外部 API 声明**，但不能替代 engine 源码审计：

1. `POST /v3/documents` 接受 raw content、`containerTag`、`customId`、metadata；add 快速返回
   queued，后台 extraction/chunk/embedding/index
   （`self-hosting/configuration.mdx:89-110`）。
2. completion 需要轮询 document status；官方 MemoryBench 还要求对应 memory status 同时 done。
3. hybrid search 同时返回 extracted memory 与 raw chunk，含 similarity/metadata/order；文档
   默认 limit 10、threshold 0.5、rerank false，而 MemoryBench 显式覆盖为 30/0.3。
4. `containerTag` 是公开 namespace；docs 声明支持按 container tag bulk delete documents。
5. local embedding 默认 `Xenova/bge-base-en-v1.5`、768d；build LLM 需外部 provider，可配置
   OpenAI-compatible base URL/model。
6. storage 在 `$SUPERMEMORY_DATA_DIR`；ingestion queue 默认 concurrency 2。

这些足以写未来 black-box contract test 的输入输出规格，却不足以验收：内部 update/forget 的
成功路径、source lineage、稳定 ranking、单 namespace 删除是否覆盖 derived memories、失败半写、
LLM/embedding usage、W2 process ownership、hosted/local 算法等价。

## 5. 为什么现在不能写 adapter

### 5.1 与项目范围直接冲突

`AGENTS.md` 和 `docs/roadmap.md` 明确限定 “Supermemory 只按 self-host/local OSS 口径接入”。
本地可执行不等于开源；MIT license 只覆盖公开仓库中实际提供的 source，不能自动补出不存在的
server source。继续实现会把范围从 local OSS 静默扩大为 binary-only product。

### 5.2 B1-B8 无法靠 API 文档补齐

黑箱可以证明某组 HTTP 请求当次返回什么，不能满足本项目的一手源码审查要求，尤其是：

- extraction/update/forget 的实际算法与模型 prompt；
- hybrid search 的两路总 top-k、dedup、rerank 与 tie order；
- current memory 到 source document/turn 的 semantic lineage；
- document delete 是否同步删除 derived memory/profile/graph；
- queue terminal、失败传播、半写恢复和 crash/restart；
- usage callback、token 归因、local embedding normalization/distance；
- hosted official harness 与 self-host BYO-model 的算法/配置差异。

若为了填满矩阵从 response metadata 反推这些事实，会违反 checklist 的“一手证据”和 metric
eligibility 门。

## 6. 解锁分支（需要用户范围裁决）

### A. 保持现行 local OSS（推荐）

Supermemory ledger 保持 blocked；等待 upstream 发布 server/engine source，或把 Phase 1 的该格
替换成另一家完整 OSS method。替换 10-method 名单属于用户范围决策，架构师不擅自执行。

### B. 放宽为 source-unavailable self-hosted binary

用户若明确接受，M2 才可下载 checksum-pinned `server-v0.0.6`，用独占 data-dir/port/process
构造 direct HTTP adapter。必须额外补：

1. binary checksum、version/help/API contract 和启动健康门；
2. 每 isolation 独占 process/data-dir，或实证 containerTag 四项逻辑隔离；
3. add → document+memory 双终态，failed 必须 fail-fast；
4. clean 后按 document/memory/profile/search 逐层复核为空；
5. build model proxy usage 与 local embedding 的诚实观测缺口；
6. 五格 session payload、image/time/place、HaluMem extraction response-id delta；
7. W1/W2、crash/restart、timeout/retry、secret/error negative-space；
8. 所有报告显式写 binary-only，不宣称 source parity 或完整 OSS。

### C. Cloud 作者校准

hosted API 只能作为单独 `author_locomo/author_longmemeval` 候选；这既改变产品 surface，也改变
数据外发与预算边界，不能替代 local 主轨，当前同样未获授权。

## 7. M1 判词

```text
BLOCKED_SUPERMEMORY_M1(
  public control repository is MIT and pinned to server-v0.0.6;
  stable runtime is distributed only as a checksum-pinned executable;
  server/engine source and reproducible build are absent from the public tree;
  official LoCoMo/LongMemEval/HaluMem harnesses target the hosted endpoint;
  Phase 1 requires local OSS, so adapter work would silently broaden scope;
  user must keep, replace, or explicitly relax this method slot
)
```
