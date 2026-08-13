# EverOS 五 benchmark 安全档案

日期：2026-08-09
状态：`FROZEN_WITH_EVEROS_PRODUCT_CHAT_V6`
适用实现：`everos-product-chat-v6`

## 0. 使用方式

这是 EverOS 一家 method 的 living dossier，不拆成五份零散文档：

- 改 role/owner/time/image/payload：先读 §1 与对应 benchmark 小节；
- 改 retrieval/metric/HaluMem：先读 §7；
- 生成或验收 smoke：只读 §8 与 machine plan 原文；
- upstream、product DTO、completion 或 source hash 漂移：按 §9 重开 ledger。

benchmark 异常直接引用稳定页，不重做 raw census。完整 product callgraph、patch、sidecar 与
observability 证据见 [M2 实现记录](everos-m2-adapter-implementation.md)。

## 1. 全格共同契约

| 维度 | 锁定值 |
| --- | --- |
| product | EverOS v1.2.3 chat mode；official lifespan + typed memorize/search/get |
| unit | `SessionBatch`；内部 batch=25，session 末 flush + exact drain |
| message | 每个 canonical 非空 event 一条 message；不位置重配 |
| readout | public HYBRID Episode search；多 owner 稳定合并 |
| source time | turn → 当前 session；LoCoMo 允许官方 `+30s` 排序，其他缺失一律 fail-fast |
| memory | synthesized Episode + atomic facts |
| isolation | 每 conversation 物理 root；每 provider 独占 Python worker/lifespan |
| workers | croppable benchmark isolated W1/W2；HaluMem fixed W1 |

private gold、memory point、target id、abstention 和 judge label 不进入产品。sidecar 的 turn/time
只用于审计和恢复，不进入 memory extraction prompt，也不把合成 Episode 冒充 source-exact。

## 2. LoCoMo

稳定入口：[`docs/reference/integration/locomo.md`](../../../../../../reference/integration/locomo.md)。

1. current official EverOS harness 把两位 speaker 都发成 `role=user`，sender id/name 保留真实
   speaker；adapter 同样处理，不把首发者猜成 user，也不制造 assistant。
2. 一个 LoCoMo session 对应一个 product session，按 25 条 add 后 flush。时间沿 official
   session 起点 + 每 utterance 30 秒；sidecar 诚实区分首条 source exact 与后续派生排序时间。
3. 官方 harness 丢弃 image-only turn；主框架按共享无损契约保留 caption，文本+caption 组合，
   path/query 不可见。这是已披露的 framework extension，不冒充作者字节 parity。
4. 主轨搜索全部 speaker owner 并按 score/owner/rank 合并；官方 author harness 只选一个
   `eval_owner`。主表采用前者避免由 speaker 选择制造不可比缺失，author calibration 后续另建。
5. gold evidence 的坏 token、分号多引用和空 evidence 全在 evaluator-private group 层处置，
   不改 method 输入。

检索排序 valid；Episode semantic provenance 与 Recall/NDCG N/A。

## 3. LongMemEval

稳定入口：[`docs/reference/integration/longmemeval.md`](../../../../../../reference/integration/longmemeval.md)。

1. assistant-first、same-role、singleton 与 odd tail 全按 canonical 原序进入同一个 session；
   EverOS 不需要 user/assistant 成对。
2. 产品 user-memory 必须存在 user owner。若一个 session 纯 assistant，只在开头加一条空
   `role=user` 结构锚；它没有 source id/time/content，不伪造自然语言回复。真实 assistant
   message 的 role/content/sender 均不变。
3. blank/role-content 可疑项由 benchmark canonical contract 处理，method 不二次猜 role。
4. question date 只进 answer builder；不截 history、不补 message time。公开树没有 EverOS
   LongMemEval 最终 harness，所以完整 session 是 framework extension，不冒充论文 parity。
5. 每题 smoke history 由 benchmark planner 裁剪，EverOS 不看 `has_answer`、answer session id
   或 gold。

LME turn/session qrel 存在，但当前 Episode 无 lossless source 映射，因此 Recall/NDCG 仍 N/A。

## 4. MemBench

稳定入口：[`docs/reference/integration/membench.md`](../../../../../../reference/integration/membench.md)。

1. FirstAgent step 已在 canonical 层拆成 user/assistant child turn；ThirdAgent 保持 user-only。
   EverOS 收完整 session，不把两条重新粘回一条，也不为 ThirdAgent 补假 assistant。
2. 正常 message 尾部已有 `(place: ...; time: ...)`，原 content 原样保留；抽出的时间同时进入
   typed timestamp，但不再拼第二份 header。
3. 100k noise 没有 place/time，source time 为 None；EverOS Episode prompt 会把 typed
   timestamp 写进记忆，任何 transport sentinel 都会成为 answer-visible 伪事实。因此该 variant
   在 runtime/API/output 前明确拒绝，状态为 unsupported/N/A。
4. `target_step_id=[]` 和等于 message 长度的 OOB gold 只由 evaluator-private evidence group
   处理，不影响 ingestion 或 smoke 选样。

First/Third 的正常 source-time 数据与 W1/W2 进入 machine plan；Recall 类指标因 Episode
synthesis 为 N/A。100k 由 registry variant gate 关闭，不生成命令。

## 5. BEAM

稳定入口：[`docs/reference/integration/beam.md`](../../../../../../reference/integration/beam.md)。

1. raw id 可重复、跳跃；EverOS 只消费 canonical event，不按 raw id 去重或重排。
2. 100k/500k/1m 规整；10m 两处 orphan/mismatch 按 canonical 原序保留。session 接口不要求
   pair，所以不补 placeholder、不把下一组 assistant 拉回来错配。
3. batch/叙事时间可能回退；只用当前 session 内 source time，不跨 session 排序。
4. abstention/rubric 是 evaluator-private，永不进入 product messages。

BEAM gold 是单 message，EverOS Episode 是合成单元，故 recall N/A；rubric judge/答案指标仍可用。

## 6. HaluMem

稳定入口：[`docs/reference/integration/halumem.md`](../../../../../../reference/integration/halumem.md)。

HaluMem 是固定 4-session / 1 isolation / 1 QA / W1 operation shape。planner 命令不得附加通用
history/conversation/question 裁剪。每 session 完整 add+flush+exact drain 后，public get 使用
`session_id` filter 读取该 session Episode；累计 QA/update 则走 public HYBRID search。

| Operation | 资格 | 理由 |
| --- | --- | --- |
| extraction | valid candidate | session-filtered public get；不是全库差分猜测 |
| update | valid candidate | probe query 读取写入后的累计 current state |
| QA | valid candidate | framework builder 消费同一 public search |
| memory type | valid | 从合法 extraction/update score artifact 按 evaluator-private gold `memory_type` 分组；不要求产品输出 taxonomy |

2026-08-13 Medium 真实 B11 已同时产出 extraction/update/QA 与 Event/Persona/Relationship
memory-type breakdown。旧口径把产品 `Conversation` kind 与 gold-side 聚合标签混淆，现撤回；
memory-type 不读取 method 自报类型，也不要求 EverOS 模拟 HaluMem taxonomy。

## 7. Retrieval evidence 与时间

每题 evidence 固定为：

```text
semantic_provenance = n_a / everos_episode_is_synthesized_not_source_exact
provenance_granularity = none
stable_ranking = valid
```

`items=()` 是真实 zero hit；backend/protocol failure 抛错。stable rank 仅证明 product/merge 顺序
可复现，不足以计算 source-qrel metric。任何 operational、LoCoMo +30s 派生或无法回指 session 的
Episode 都不向 answer builder 渲染产品时间。

## 8. B11 machine plan

2026-08-12 live preflight 将 smoke embedding transport 从缺失 credential 的 DeepInfra 改为
OpenRouter OpenAI-compatible endpoint；精确请求已返回官方同名
`Qwen/Qwen3-Embedding-4B`、1024 维与 usage。OpenCodeGo 仍只承担 Chat Completions，official-full
仍保留 DeepInfra。首轮 B11 又在 MemBench 100K 暴露 operational sentinel 会进入产品时间语义；
最终裁决不是换一个更大的伪时间，而是取消这条不诚实能力。v6 同时修复 exact drain 的
event-loop 饥饿与 run-local endpoint template 泄漏，最终 run 全部 fresh，未 resume v1-v5。

机器计划保存在 [everos-smoke-plans-v1.json](everos-smoke-plans-v1.json)。总数 18：LoCoMo 2、
LongMemEval 4、MemBench `0-10k` 2、BEAM 8、HaluMem 2。8 个 croppable concrete variant各 W1
与包含 2 isolation 的 W2；HaluMem 两 variant 只生成 fixed W1。MemBench `100k` 由 registry
variant gate 在任何 API/output 前拒绝。

`predict_argv/evaluate_argv` 全部来自 `plan-smoke` 原始输出，禁止手写修饰。planner 保留所有
注册 evaluator；N/A 由 runtime evidence/evaluator 写 null/N/A，不从命令暗删。18 份 current
v6 plan 已全部执行并由 [frozen-v1](everos-frozen-v1.md) 开箱冻结。

## 9. 失效触发器

以下任一变化必须重开对应 ledger 门：

1. EverOS tag/commit、`uv.lock`、EverAlgo package、typed DTO/service 或 official harness；
2. `create_app` lifespan、OME/Cascade status/health/drain 或 shutdown ownership；
3. chat boundary/Episode/atomic-fact schema、HYBRID rank/dedup/search flags；
4. embedding model/dimension/distance/transport、reranker 行为或 API usage shape；
5. role/owner/time/image renderer、assistant-only anchor、consume granularity；
6. root config、sidecar/tombstone、worker protocol、W2 ownership；
7. benchmark source lock、canonical anomaly contract、metric eligibility 或 HaluMem operation order。

## 10. 当前判词

```text
LOCOMO_FROZEN_V1
LONGMEMEVAL_FROZEN_V1
MEMBENCH_0_10K_FROZEN_V1_AND_100K_UNSUPPORTED
BEAM_FROZEN_V1
HALUMEM_FROZEN_V1
EVEROS_METHOD_FROZEN_V1
```
