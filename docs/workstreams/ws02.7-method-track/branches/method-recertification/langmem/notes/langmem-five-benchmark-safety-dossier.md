# LangMem 五 benchmark 安全档案

日期：2026-08-02
状态：`READY_FOR_B11_REAL_SMOKE_APPROVAL`
适用实现：`langmem-background-product-v1`

## 0. 使用方式

这是 LangMem 一家 method 的 living dossier，不复制成五份顶层文档。以后：

- 改 role/time/image/payload：读 §1 与对应 benchmark 小节；
- 改 retrieval/metric：读 §7；
- 生成或验收 smoke：读 §8 与机器 plan 原文；
- upstream、`uv.lock`、factory/store/config 漂移：按 §9 重开 ledger。

benchmark 异常只引用其稳定页，不重做 raw census。完整 worker transaction、observability 与
源码身份见 [M2 实现记录](langmem-m2-adapter-implementation.md)。

## 1. 全格共同契约

| 维度 | 锁定值 |
| --- | --- |
| product | LangMem 0.0.30 async background MemoryStoreManager |
| runtime | provider 独占 Python 3.12 worker；direct product API，无 HTTP host |
| unit | `SessionBatch`；一个 session 一次 `ainvoke()` |
| message | canonical `role/content` 原序；不补 placeholder、不重配 |
| memory | LLM 抽取并可 update/consolidate 的 current `Memory(content)` |
| readout | `MemoryStoreManager.asearch(query, limit)` product score/order |
| source time | turn → 当前 session → None；不借 question/wall clock |
| namespace | worker 内 `("memories", opaque_namespace)`；atomic state + journal |
| workers | croppable benchmark 支持 isolated W1/W2；HaluMem 固定 W1 |

gold answer、gold evidence、target step/session、memory point、abstention 与 judge label 均不进入
messages、namespace、state 或 worker request。source turn id 只参与 framework operation identity，
不塞进 memory prompt，也不冒充 evolved memory lineage。

## 2. LoCoMo

稳定入口：[`docs/reference/integration/locomo.md`](../../../../../../reference/integration/locomo.md)。

### 风险与处置

1. 两人都是真实 speaker，不可按首发猜 user/assistant。adapter 只读公开
   `speaker_a/speaker_b`，固定 `speaker_a→user / speaker_b→assistant`；真实名字仍前置 content。
   speaker 缺失、相同或出现第三人均 fail-fast。
2. 文本与图片 caption 可并存。共享 helper 生成
   `[Sharing image that shows: {caption}]`；caption-only 仍可见，path/query/locator 不进入算法。
3. turn 通常无时间、session 有时间。每条 message 使用当前 session time；有真实 turn time 时
   优先 turn time。奇数尾是合法单条 message，不补空 assistant。
4. 分号挤在单 evidence、坏 token、空 evidence 等只属于 evaluator-private gold group；不改写
   method 输入，也不向 worker泄漏。

检索资格：product rank valid；semantic provenance 与 Recall/F1@k/NDCG N/A。answer F1/judge/EM
类指标仍可从 prediction artifact 离线或经批准计算。

## 3. LongMemEval

稳定入口：[`docs/reference/integration/longmemeval.md`](../../../../../../reference/integration/longmemeval.md)。

### 风险与处置

1. assistant-first、连续同 role、singleton 与 odd tail 都是合法 canonical 形状；完整 session
   原序一次传入。LangMem 自己的 `merge_message_runs()` 可能在 prompt 展示层合并同 role，
   adapter 不提前合并、配对或制造 placeholder。
2. blank 与 role/content 可疑标注由 benchmark stable contract 处理；method 不二次猜 speaker。
3. question date 只属于答题 prompt；不回填 message time、不截断 future history。turn 无时间时只
   回落所属 session time。
4. 每题完整 haystack 的 smoke 裁剪由 benchmark adapter/planner 执行；LangMem 不偷看
   `has_answer`、answer session ids 或 gold 来选 history。

当前 memory 没有 source unit 映射，所以即使数据有 turn/session qrel，Recall 与 NDCG 仍 N/A；
不能反向给 evolved text 贴全部参与 source ids。

## 4. MemBench

稳定入口：[`docs/reference/integration/membench.md`](../../../../../../reference/integration/membench.md)。

### 风险与处置

1. FirstAgent pair 已由 canonical 层拆成 user/assistant 两个 child turn；LangMem 收完整 session，
   每个 child 恰好一条 message。ThirdAgent user-only 保持 user，不插入假 assistant。
2. 正常消息的 place/time 在原 content 尾部；严格 boolean marker=True 时不再前置同一 turn time，
   但原文不删除。字符串 `"true"` 等不能冒充 marker。
3. 100k noise 没有 place/time，source time 保持 None；不从 question、相邻 turn 或 wall clock
   制造时间。
4. `target_step_id=[]` 与等于 message 长度的越界 gold 只由 evaluator-private evidence group
   contract 处理，不影响 ingestion 或 smoke 选择。

First/Third、marker 三态、missing-time 与 private negative-space 均有 production-path 强反例。

## 5. BEAM

稳定入口：[`docs/reference/integration/beam.md`](../../../../../../reference/integration/beam.md)。

### 风险与处置

1. raw id 可重复/跳跃；adapter 只消费 benchmark 已建立的 canonical event，不用 raw id 做
   dedup、排序或 operation identity。
2. 100k/500k/1m 规整；10m 有两处 orphan/mismatch。LangMem session 接口接受任意 role 序列，
   因此按 canonical 原序保留，不位置二元 chunk、不跨组拉回 assistant、不补 placeholder。
3. batch/叙事时间可回退；只按 raw canonical session 顺序，不跨 session 重新排序。
4. abstention/rubric 是 evaluator-private；不会进入 memory manager。

BEAM recall 依赖单-message qrel，而 evolved memory 无 semantic mapping，故 N/A；rubric judge 仍
适用于 framework answer。

## 6. HaluMem

稳定入口：[`docs/reference/integration/halumem.md`](../../../../../../reference/integration/halumem.md)。

HaluMem 是固定 operation-level shape：4 sessions / 1 isolation / 1 QA / W1；planner 命令不得
携带通用 history/conversation/question/worker 裁剪参数。每个 session 完整 messages 调一次
`ainvoke()`，返回时 current store 已完成更新。

| Operation | 资格 | 原因与路径 |
| --- | --- | --- |
| extraction | N/A | changed puts 可能融合旧 memory，不是严格本 session memory point；`session_memory_report=False` |
| update | valid | 写完 session 后以 probe query 搜 current evolved state，再交官方 update judge |
| QA | valid | 同一累计 namespace 的 product search readout 进入 HaluMem unified builder |
| memory type | N/A | composite 依赖 extraction point；不能从自由文本猜 Event/Persona/Relationship |

generated QA session、private memory points 与 type label 延续 benchmark stable contract，不进入
build messages。

## 7. 跨格 retrieval evidence

每题 runtime evidence 固定表达两件彼此独立的事实：

```text
semantic_provenance = n_a / langmem_evolved_memory_not_source_exact
provenance_granularity = none
stable_ranking = valid
```

`items=()` 表示真实 zero hit；`items=None` 不会由 LangMem 返回。stable rank 只说明
`asearch()` 的当前 memory 顺序与 score 被保留，不足以越过 semantic-qrel 门。因此五格
Recall/Precision/F1@k 与 LongMemEval NDCG 都是 N/A，不记 0 分。

## 8. B11 machine plan

机器计划保存在 [langmem-smoke-plans-v1.json](langmem-smoke-plans-v1.json)。每个 croppable
concrete variant 各生成 W1 与真正包含 2 isolation 的 W2；HaluMem 两 variant 只生成固定 W1。
已生成总数 20：LoCoMo 2、LongMemEval 4、MemBench 4、BEAM 8、HaluMem 2。

所有 `predict_argv/evaluate_argv` 均来自 `plan-smoke` 原始输出，不能手写修饰。planner 会保留
benchmark 注册的全部 evaluator；N/A 指标由 runtime evidence/evaluator 输出 null/N/A，不从命令
暗删。当前计划只供预算核对，尚未授权执行真实 API。

## 9. 失效触发器

以下任一变化必须重开 ledger 对应门：

1. vendored commit、package、`uv.lock`、public factory signature 或 sync duplicate-search 行为；
2. Memory schema、insert/delete/query model/query limit/max steps；
3. InMemoryStore index/distance/tie behavior、snapshot/journal/cleanup schema；
4. message role、speaker/time/image renderer 或 consume granularity；
5. worker transport、provider usage 字段、本地 tokenizer/model normalization、W2 ownership；
6. benchmark source lock、canonical/stable anomaly contract、metric eligibility 或 HaluMem operation order。

## 10. 当前判词

```text
LOCOMO_READY_FOR_B11
LONGMEMEVAL_READY_FOR_B11
MEMBENCH_READY_FOR_B11
BEAM_READY_FOR_B11
HALUMEM_READY_FOR_B11
LANGMEM_NOT_FROZEN_UNTIL_REAL_SMOKE_AND_ARTIFACT_GATE
```
