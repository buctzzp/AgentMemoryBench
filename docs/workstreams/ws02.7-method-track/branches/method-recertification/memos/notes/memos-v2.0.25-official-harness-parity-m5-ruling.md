# MemOS v2.0.25 官方 harness parity 与五格 M5 裁决

日期：2026-07-27

架构师：GPT-5.6 sol
source lock：`MemTensor/MemOS v2.0.25@e820406`

## 0. 判词

```text
RULING_MEMOS_M5_INPUT_IDENTITY(
  locomo_main =
    official dual namespace
    + forward/reverse roles
    + per-view positional batch_size=2
    + dual search/per-view top_k
    + speaker-partitioned merge;

  longmemeval_main =
    full canonical session
    + lossless content
    + raw role/order preservation;

  author_longmemeval =
    pending calibration profile, not main;

  membench/beam/halumem =
    framework extensions using the same product typed handlers;

  no benchmark anomaly is repaired inside MemOS
  unless the canonical benchmark contract already resolved it
)
```

这次改判推翻 M4 的一项局部口径：LoCoMo 不再只写 speaker_a 单视角。M4 的
typed-handler、async lifecycle、failure propagation、runtime owner、其余四格输入与
metric 资格继续有效。

## 1. 为什么必须先看最终 payload

只看到：

```python
client.add(messages, user_id, conv_id)
```

不能推出“一整个 session 一次 add”。当前 `MemosApiClient.add()` 在
`evaluation/scripts/utils/client.py:150-172` 内再次按 `batch_size` 切片并逐次发
`/product/add`。因此 parity 必须沿 wrapper 追到最终请求；README、函数名和外层调用都
不是最终事实。

此遗漏已升级进
`docs/reference/method-integration-checklist.md` 的 **B0 官方评测 harness parity
matrix**。以后 adapter 施工前必须先锁 product surface、真实 batching、namespace/view、
async completion、build/search 参数与完整 answer builder。

## 2. LoCoMo：主轨采用官方双视角

### 2.1 一手事实

官方 ingestion：

- `locomo_ingestion.py:34-45` 同一 turn 同时生成两份 message；
- speaker_a 视角：`speaker_a→user`、`speaker_b→assistant`；
- speaker_b 视角：上述 role 完全反转；
- content 为 `"{speaker}: {text}"`；
- `locomo_ingestion.py:47-63` 两个 user id 分别调用 `client.add(...,
  batch_size=2)`；
- `client.py:150-172` 证明 `batch_size=2` 最终变成多个真实 HTTP add payload，
  奇数尾自然是 singleton，没有 placeholder。

官方 retrieve/readout：

- `locomo_search.py:99-106` 对两个 user id 各 search 一次；
- 每一路都使用同一个 `top_k`，所以总候选上限是 `2 × top_k`，不是把总 k 平分；
- `locomo_search.py:108-122` 先保持各路内部顺序，再放入真实 speaker 的两个
  `TEMPLATE_MEMOS` 槽位；没有跨 namespace 的全局 rank。

### 2.2 主轨裁决

用户要求主轨与官方双视角保持一致；架构师接受，理由不是“作者代码天然正确”，而是：

1. LoCoMo 的两个角色都是对等真实 speaker，单独把 speaker_a 永久设成 user 会让
   MemOS 的 user/assistant 语义偏向其中一人；
2. 双视角正好把这种方向性对称化；
3. MemOS 产品原生支持逻辑 namespace，双库不需要改算法核心；
4. 官方双路 readout 提供了一手可复现的合并语义。

实现口径：

```text
namespace A = deterministic(conversation isolation + speaker_a view)
namespace B = deterministic(conversation isolation + speaker_b view)

每 session:
  构造 A/B 两份同 turn 列表，role 互反
  每视角按位置切 2 条；奇数尾 singleton
  全部 async add 先提交
  再逐 business_task_id 等待唯一 terminal

每 question:
  A/B 各 SearchHandler(top_k=query.top_k)
  各路保持产品顺序
  formatted_memory 按真实 speaker 两槽位合并
```

caption 仍走共享
`[Sharing image that shows: {caption}]`；`message_id` 与更细的
`turn→session→None` source time 是 additive 审计字段。HTTP transport 被 typed handler
直调替代，但两者最终委托同一 `AddHandler/SearchHandler`，不构成算法差异。

### 2.3 仍不等于论文数字 parity

主轨仍有以下有意差异，必须诚实披露：

- answer 走 benchmark 统一 builder，不走 MemOS 官方 method-specific answer builder；
- framework 当前 `query.top_k=10`，官方 shell 口径为 20；LoCoMo 两路均各取该 k；
- 主轨 `include_preference=false`，官方 search payload 在
  `client.py:174-187` 显式请求 preference；但官方公开 eval 环境没有证明
  `ENABLE_PREFERENCE_MEMORY` 实际开启；
- tool/skill/history 仍按 framework 主轨关闭/空历史；
- 论文只说配置经 validation 选择，没有公开足够信息证明精确 server env、embedding/
  chunk/window 组合。

所以新 LoCoMo 是“官方输入与双路 readout parity”，不是“paper-number parity”。

## 3. LongMemEval：主轨保留完整 session

### 3.1 官方 wrapper 的真实行为

`lme_ingestion.py:16-42`：

- 保留 raw `role`；
- 每条 content 强制 `[:8000]`；
- session 内 messages 交给 `client.add(..., batch_size=2)`，最终是双 message 请求；
- assistant-first、连续同 role、singleton、奇数尾都只是**按位置切片**，没有 role 修复。

当前 wrapper 还存在 release 内部漂移：

- `lme_search.py:44-48` 把 `reference_time` 传给 `MemosApiClient.search()`；
- `client.py:174` 的当前签名只有 `(query, user_id, top_k)`；
- 因而 current `memos-api` LongMemEval search 会在调用层 `TypeError`；
- ingestion payload 写 `conversation_id`，而 current product model 的 typed 主字段是
  `session_id`；旧 HTTP schema 对额外字段的实际处理不能替代产品契约证明。

### 3.2 主轨裁决

主 `smoke/official_full` 保持：

```text
一个 canonical SessionBatch → 一个 APIADDRequest
原 role / 原顺序 / 全 content 无损保留
session_id 显式进入 current typed product model
assistant-first / same-role / singleton / odd-tail 不修、不补 placeholder
```

理由：

1. current product typed API 原生接受 message list，未声明必须二条一组；
2. MemOS `MultiModalStructMemReader` 自己负责窗口与 fine extraction；
3. 双 message 是 evaluation wrapper 的选择，不是产品输入硬约束；
4. `[:8000]` 会无损性失败，不能暗中进入跨 benchmark 主表；
5. LongMemEval 的 role/content 异形没有 upstream 根因证据，canonical 层已按结构化 role
   保留；MemOS 不再做第二套“异常修复”。

这一路径方法学上更适合主表，但**不能与官方论文数字直接对表**。

### 3.3 `author_longmemeval` 状态

后续单独实现稀疏校准 profile，候选身份包含：

- positional `batch_size=2`；
- content `[:8000]`；
- per-query top-k 20；
- 官方 method-specific formatted context / answer builder；
- 修复后才可使用的 reference-time 路径；
- 已证实的 server env/build 参数。

在 wrapper 的 `reference_time` TypeError、公开 server env 与 validation-selected config
未闭合前，只能写 `pending calibration`，不得命名为 paper parity。

## 4. 三个官方未覆盖 benchmark

### 4.1 MemBench

- 一、三人称 canonical role 原样进入一个完整 session；
- first-person pair 展开后的 user/assistant 不重新合并；
- third-person user-only 合法，MemOS 不要求交替，**不加 placeholder**；
- 原 content 的 place/time 尾注逐字保留，canonical 抽取出的时间同时进入
  `chat_time`；
- 100k noise 无时间时显式 `chat_time=None`；
- `target_step_id=[]` 与越界 gold 只在 evaluator-private 层处理，method 不可见。

### 4.2 BEAM

- 使用 canonical session/turn id，不信 raw 重复/跳跃 id；
- 100k/500k/1M 正常 role 顺序原样保留；
- 10M 两处 dangling/misaligned window 同样原样保留，不跨 session 修复、不造回复；
- session source time 按 canonical `turn→session→None` 传入；
- BEAM official 不提供 MemOS harness，因此该格是 framework extension。

### 4.3 HaluMem

- 每个 session 一个 add + 一个精确 business-task completion；
- 不把后续 session 与前一 session 配对或合并；
- QA 与 update 可走 current-state retrieve，等待真实 DB smoke；
- async tracker 只公开 terminal status，不公开本 task 产出的 fine memory 集合，故
  extraction 继续 N/A；
- MemOS memory type 不等价于 Event/Persona/Relationship，memory-type 继续 N/A。

## 5. Metric 与公平性边界

- MemOS fine memory 是 window-generated item；`sources[].message_id` 只证明 source
  参加过生成，不能证明 current memory 仍承载每个 source fact。
- 因此五格 Recall/NDCG semantic provenance 继续 `pending/none`；LoCoMo 双库不会
  自动升级资格。
- 两个 LoCoMo namespace 没有可解释的跨库全局 rank，stable ranking 继续 pending。
- LoCoMo 的每题检索条目数可达 `2×query.top_k`，manifest/metadata 必须标
  `per_locomo_speaker_view`，报告不得写成“总 top-k”。

## 6. M5 验收范围

零 API 强反例必须覆盖：

1. 双 namespace 隔离、正反 role、batch `[2,2,...,1]`；
2. caption/time/message_id 在双写中逐字守恒；
3. 全部 async add 先提交再 wait；
4. 两路 search 各自 top-k、speaker 槽位 merge、sidecar resume；
5. 双 namespace clean 的全局 pending preflight 与双路 readback；
6. LongMemEval 全 session、不截断、不修 role；
7. MemBench/BEAM/HaluMem 已冻结特殊形状；
8. adapter version/manifest/resume 重建门。

真实 B11 只有在 Neo4j、Qdrant、API 与 budget gate 都满足后执行。真实 smoke 用来验证
product runtime、隔离、current-state readout、效率记录和合法 zero-hit；不会用极小 smoke
答对率评价方法效果，也不会用 add 数猜 LLM 调用数。
