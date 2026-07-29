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

首轮
[MemOS v2.0.25 async lifecycle 完成门 R2](cards/actor-prompt-memos-v2-0-25-async-lifecycle-r2.md)
产出 `d1a0178`，架构师强验收随后复现出 reader 内部 LLM/parser/embedding 吞错、
`merged_from` archive 吞错、handler-only trace 冒充完整 async trace，以及 patch whitespace
问题；首轮 `READY` 因而撤回。R2-R1 follow-up `2830c32` 关闭这些缺口，架构师另补 Factory
作用域隔离和两条最低叶子强反例后，以
[R2 最终验收](notes/memos-v2.0.25-async-lifecycle-r2-architect-acceptance.md)
接收并在 `14ece4c` 合流。

MemOS v2.0.25 product v3 adapter M4 已由 `a87353a + de29c4c + f6e725e` 完成，并在线性
主线映射为 `dff8185 + 02ffc9d + 3e1d621`。最终
[架构师验收](notes/memos-v2.0.25-product-adapter-m4-architect-acceptance.md)
确认 typed-handler adapter、MiniLM config、search failure、generic lifecycle owner、
namespace-safe clean retry、stop failure 永久 fail-closed 与五格强反例成立；主树全量
无 API 门为 `1863 passed, 3 deselected, 11 warnings, 29 subtests passed`。

M5 又补做了官方 harness parity 门。架构师一手追到最终 payload 后确认：

- LoCoMo 官方实际是双 namespace、正/反 role、每视角 `batch_size=2`、双路各取
  top-k 再按 speaker 合并；用户裁定该拓扑进入主 profile；
- LongMemEval 官方 wrapper 同样位置切 pair 并 `[:8000]`，但 current
  `reference_time` 调用与 client 签名冲突；主 profile 继续完整 session、无损 content，
  wrapper 只进入待实现 `author_longmemeval` 校准身份。

完整裁决见
[M5 harness parity ruling](notes/memos-v2.0.25-official-harness-parity-m5-ruling.md)。
该中间版本 adapter 升级为 `product-v2`，离线强反例覆盖双库
add/search/readout/resume/clean 与其余四格稳定特殊形状；当时定向门
`390 passed, 10 warnings`，文档门 `5 passed`。

M5 随后完成 product-v3 五格真实服务 smoke；product-v4 只增加成功 response usage
callback 与 async completion-buffered observation replay，不改变 memory 算法/payload/
search，因此以 LoCoMo 和 HaluMem 两条真实哨兵补证 B7，其余功能资产守恒继承。
最终状态见 [method-frozen-v1](notes/memos-frozen-v1.md)。

2026-07-27 已关闭 M5 的 API provider 前置：新 smoke 使用显式
`opencodego/deepseek-v4-flash`，Chat Completions 普通、judge 与 JSON mode 均已最小真调用
通过，Responses 明确不可用；provider/model/transport 已进入 manifest/resume，正式
`official_full` 仍保持 primary。实现见
[`../../api-runtime-smoke/README.md`](../../api-runtime-smoke/README.md)。
MemOS B11 已执行；这些 provider/runtime 身份均进入 manifest。

## 冻结边界

- MMR/rerank stable-ranking；
- window-generated memory 的 semantic provenance 与 Recall/NDCG 资格；
- async `MEM_READ` 未公开 task-scoped fine output，因此 HaluMem extraction 先诚实 N/A；
- HaluMem update 非空命中哨兵；
- author LoCoMo / LongMemEval 的 paper-number calibration；
- framework W2：真实 LME 反例触发 shared tokenizer `Already borrowed`，已判
  `N/A/unsupported`，不是待补；产品内部 async dispatcher 不变。

下一家 method 不重造 MemOS 或 benchmark 调查；从父级恢复胶囊进入 Letta/MemGPT。
