# Graphiti 五 benchmark 安全档案

日期：2026-08-09

身份：Graphiti OSS `v0.29.3@021d3a57`，不是 Zep hosted product

实现入口：[M3](./graphiti-v0.29.3-product-adapter-m3-implementation.md)

本文件只保存 Graphiti 的 method 差量；benchmark 全量 census 与异常原文仍以各稳定页为准，
避免第十家 method 再造一遍 raw 调查。

## 1. 共用产品契约

- 每个 nonblank canonical turn 恰好一个 `add_episode(source=message)`，逐条 await；
- 不补 placeholder、不重排、不跨 session 配对；
- 每 conversation 独占 worker、FalkorDB Lite root 与 atomic sidecar；
- `reference_time` 只来自 canonical turn→本 session 的公开 source time；question time、兄弟 turn
  与 wall clock 不可用于补造；
- readout 是默认 `Graphiti.search()` 返回的有序 active EntityEdge facts；fact 时间字段进入
  formatted memory，source ids 只留 artifact，不进答题 prose；
- gold answer/evidence/judge label 只在 evaluator-private artifact，永不到 adapter/worker。

## 2. LoCoMo

稳定异常见 [LoCoMo integration](../../../../../../reference/integration/locomo.md)。Graphiti 不把
双 speaker 猜成自然 user/assistant 交替，而是使用 conversation metadata 的稳定声明：
`speaker_a→user`、`speaker_b→assistant`，最终 body 为
`<speaker_name> (<role>): <content>`。奇数尾部和同 speaker 连续发言仍各自是一个 episode。

图片用共享 `[Sharing image that shows: {caption}]` wrapper 与原 content 拼接；path/query 等
locator 不可见。Gold evidence 的分号、坏 locator 与空 evidence 不参与 ingest，只由 evaluator
的 Gold Evidence Group 规则吸收。LoCoMo source time 归一为 UTC；检索 provenance
`valid/turn`，RRF rank `valid`，故适用 Recall；计划含 W1/W2。

## 3. LongMemEval

稳定异常见 [LongMemEval integration](../../../../../../reference/integration/longmemeval.md)。current
官方 Graphiti harness 本身就是逐 message `role: content` + session date 的 turn episode；主轨
保持完整 canonical history、raw session/turn 顺序与原 role。assistant-first、same-role、
single-role session、odd tail 都不配对，因此无需 placeholder，也不会把一条真实消息丢给相邻
消息。

blank turn 沿 benchmark canonical 稳定规则处理；question date 不参与 ingest 或 retrieval
cutoff。adapter 的逐 turn payload 与官方 graph-build payload compatible，但完整 search/answer/
judge 是 framework extension。检索 provenance `valid/turn`、rank `valid`；Recall 与 retrieval
rank evaluator 按公开 qrel/资格运行。S/M 两 variant 均有 W1/W2 plan。

## 4. MemBench

稳定异常见 [MemBench integration](../../../../../../reference/integration/membench.md)。FirstAgent 的
pair-step 已由 canonical adapter 拆为 user/assistant 两个 child turn；ThirdAgent 是单 user turn，
Graphiti 都逐 turn 写入，无 placeholder。原 content 尾部的 place/time 保留不删，同时已抽取的
turn time 走 typed `reference_time`，不会再在 content 前重复渲染。

`0-10k` 有可用 source time，支持 provenance `valid/turn` 与 stable rank。`100k` noise turn
可能没有 time，而 Graphiti product 必填 `reference_time`；该 variant 在 cost、`.env`、runtime、
output 前明确 N/A。`target_step_id=[]` 与越界 gold 仍只由 evaluator-private benchmark policy
处理，不泄露给 method。0-10k 有 W1/W2 plan，100k 无命令。

## 5. BEAM

稳定异常见 [BEAM integration](../../../../../../reference/integration/beam.md)。Graphiti 使用
canonical positional turn id，规避 raw id 重复/跳跃；100k/500k/1m 的标准交替与 10m 的两处
orphan/mismatch 都严格保持原序逐 turn 写入，不做 positional pair，也不制造回复。source time
沿 canonical turn→session 回落，不重排跨 batch 时间线。

abstention/rubric 私有字段只在 evaluator 侧。检索 edge 的 episode sidecar 回映 public turn id，
provenance `valid/turn`，rank `valid`；BEAM recall 仍是 framework supplementary metric，不冒充
官方 BEAM 指标。四 variant 均有 W1/W2 plan。

## 6. HaluMem

稳定契约见 [HaluMem integration](../../../../../../reference/integration/halumem.md)。runner 固定
4-session/1-QA/W1，Graphiti 每个 canonical turn 逐条 add；每次 session 结束时，sidecar 记录
本 session episode UUID 与首次出现 edge UUID，重新读 product current state，只返回仍 active 且
source episodes 与本 session 有交集的 facts。

- extraction：session-local current edge observation，`valid`；
- update：公开 `search()` probe，按 query 请求的 top-k 运行，`valid`；
- QA：累计 product search + framework reader，`valid`；
- memory-type：对 extraction/update 已有分数按 gold type 分组，`valid`，不要求 Graphiti 预测
  Event/Persona/Relationship。

medium/long 各一份固定 W1 plan，任何 rounds/conversations/questions/workers override 都由 planner
拒绝。

## 7. 失效触发器

出现下列任一项必须重开本 dossier 对应格，不得沿用绿灯：

1. Graphiti source lock、default search recipe、EntityEdge.episodes 维护或 FalkorDB driver 漂移；
2. benchmark source lock/canonical role、time、image 或 Gold Evidence Group contract 改变；
3. local embedding model/revision/dimension/normalization 或 build runtime profile 改变；
4. search 开始调用 cross encoder/build LLM，或 product rank 不再是稳定返回序；
5. sidecar/operation digest/cleanup schema/adapter version 改变；
6. MemBench 100k 获得真实 source timestamp 契约——届时只能重新审计，不得直接解除 N/A。

真实 smoke、artifact 开箱与冻结状态只看 integration ledger；本文件的离线安全结论不替代 B11。
