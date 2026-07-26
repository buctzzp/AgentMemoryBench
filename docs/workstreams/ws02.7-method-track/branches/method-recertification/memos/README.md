# MemOS v2.0.25 产品接入

## 范围

本支线接入官方开源仓库
[`MemTensor/MemOS`](https://github.com/MemTensor/MemOS) 的稳定 release
`v2.0.25`。主协议仍是 framework v3 `ingest + retrieve → framework reader`；
不得调用 MemOS 自带答题入口替代 framework reader。

## 当前 source identity

- upstream：`https://github.com/MemTensor/MemOS.git`
- release：`v2.0.25`
- commit：`e820406269537b97d270687e3e40eea2f015f81a`
- release 时间：2026-07-24 16:47:37 +08:00
- 本地路径：`third_party/methods/MemOS`（local-only、父仓库 gitignored）
- 可复现入口：`third_party/methods/MANIFEST.md` +
  `scripts/fetch_third_party_methods.sh`

不锁浮动 `origin/main`。本次核验时 `origin/main@3fd109e7` 比 release 多一个
Yunxiao 同步 preflight commit，与 benchmark 产品语义无关；主线继续前进不应静默改变
本项目的 method build。

完整换锁证据与旧审计失效边界见
[`notes/memos-v2.0.25-source-lock.md`](notes/memos-v2.0.25-source-lock.md)。

## 复用资产

以下结论已经由前五家 method 摊销，本支线只消费，不重新调查：

- 五个 benchmark 的 raw/canonical/gold 异常、公开 ID、时间和图片语义：
  `docs/survey/` 与 ws02.6 frozen/source-lock；
- v3 provider、Gold Evidence Group、RetrievalEvidence、N/A/null、artifact 与
  worker/resume 公共契约；
- benchmark 统一 answer/judge builder、smoke 裁剪轴和 evaluator 资格政策；
- B1-B11 验收门：`docs/reference/method-integration-checklist.md`。

2026-07-05 的
`docs/workstreams/ws02-phase1-matrix/audits/{memos,mechanism-memos}.md`
仅作为 `v2.0.22` 历史基线和风险索引。它们的源码行号与现行行为不能直接作为
`v2.0.25` 结论引用。

只有 benchmark source lock、shared contract 或官方资产变化，或出现能推翻稳定判词的
一手反证，才允许重开 benchmark 调查。

## 当前门与依赖顺序

1. **M1 source-delta 与产品身份裁决**：只复核 `v2.0.22 → v2.0.25` 的承重变化，
   裁定 API/library、`general_text`/`tree_text`、同步/异步 scheduler、服务依赖与
   官方 evaluation 的真实关系；
2. **M2 接口与 lifecycle 裁决**：逐项锁 ingest 粒度、role/time/image、cube/user/session
   隔离、flush/drain、clean retry、readout 与效率观测；
3. **M3 metric 资格裁决**：逐 benchmark 判 provenance unit、stable ranking、
   Recall/NDCG 与 HaluMem extraction/update/QA/memory-type，不为填表伪造能力；
4. **M4 adapter 实施与零 API 门**：代码、强反例、manifest/resume、五格 fake/offline
   production-chain；
5. **M5 B11**：用户批准预算、规模和 run_id 后才执行真实 smoke，开箱、对表并冻结。

M1 未裁定前不写 adapter、不启动服务、不调用真实 API，也不并行派五张 benchmark
调查卡。后续任务卡放 `cards/`，一手审计、裁决与施工记录放 `notes/`；权威当前动作仍只
更新父 ws02.7 README。

首轮 M1 在 `13edb3a` 正确停工：current default reader 推翻旧卡的 SimpleStruct active-chain
假设，并证明显式 `chat_time=None` 与 reader-level `message_id` 传输成立。R1 机制证据在
`2ea7a39` 闭合，但也证明 `sync+fine` 是省略 default async lifecycle 的
`ALGORITHM_VARIANT`。架构师因此
[最终裁定](notes/memos-v2.0.25-m1-final-ruling.md)：主 profile 保留
`async+fast → MEM_READ`，先补成功路径零变化的失败传播与 task-scoped completion，不能以
sync variant 绕过完成门。

**当前唯一施工入口**：
[MemOS v2.0.25 async lifecycle 完成门 R2](cards/actor-prompt-memos-v2-0-25-async-lifecycle-r2.md)。
它只补可复现 patch、local in-memory task tracker 与 strict waiter；不写 adapter、不重做
benchmark census。R2 通过后才进入一张 adapter + 五格强反例卡。

## R2 尚未闭合的 MemOS 专属问题

- initial fast write、fine transfer/write、delete/refresh 与 scheduler submit 的多层吞错；
- local queue 下按 business `task_id` 精确等待 `MEM_READ`，而非全局队列或坏掉的
  `/scheduler/wait`；
- patch 的 source identity、幂等重放与 success-path 守恒；
- task-scoped fine output 是否足以支持 HaluMem extraction 的纯观测 sidecar。

search provenance/stable ranking、真实 graph/vector 隔离与 HaluMem update 继续保持
`pending`，由后续 adapter/M3/真实 smoke 分层关闭，不回头重造 M1 证据。
