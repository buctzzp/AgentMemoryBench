# Letta/MemGPT 五 benchmark 安全档案

日期：2026-08-02
状态：`PAUSED_EXTERNAL_OPENCODEGO_REGION_OPT_IN`
适用实现：`letta-sleeptime-product-v2`

## 0. 怎么使用这份档案

这是 Letta 一家 method 的 living dossier，不复制成五份零散文档。以后出现以下动作时，先读
对应小节，再读链接的一份稳定 benchmark 页；不要重扫 raw dataset：

- 改 Letta payload/role/time/image：读 §1 + 对应 benchmark 小节；
- 改 retrieval/metric：读 §7；
- 生成或验收 smoke：读 §8；
- upstream/tag/SDK/config 变化：读 §9 并重开 ledger 对应门。

完整源码行号、产品初始化与失败路径在
[M2 实现记录](letta-m2-adapter-implementation.md)；本页只保存跨会话仍需快速定位的五格
判据、反例与处置。

## 1. 全格共同产品契约

| 维度 | 锁定值 |
| --- | --- |
| product | legacy Letta V1 `0.16.8` + official `ai-memory-sdk v0.2.0` sleeptime-memory |
| runtime | 独立 Python 3.12 worker 内 direct `SyncServer/AgentLoop`，无 HTTP host |
| unit | `SessionBatch`；session 内最多 10 message；不跨 session |
| message | canonical `role/content`；不补 placeholder、不按位置重配 role |
| build sink | official wrapper 作为一条 user `MessageCreate` 送入 memory-only agent |
| stored memory | 演化后的 attached `human/summary` core blocks；raw turn 不写 archival vector store |
| readout | query-independent 全部 blocks，按 `(label,id)` 稳定展示 |
| source time | turn → session → None；从不借 question time/wall clock |
| namespace | run storage identity + conversation isolation key → opaque subject/agent |
| framework workers | W1-only；planner 预启动拒绝 W2 |

私有 gold answer、gold evidence、target step、memory point label、abstention label 与 judge label
均不进入 message、subject tags、sidecar、worker request 或 Letta database。

## 2. LoCoMo

稳定数据事实入口：[`docs/reference/integration/locomo.md`](../../../../../../reference/integration/locomo.md)。

### 2.1 风险

1. 两个说话人都是真实人物，不等于天然 user/assistant；不能按首发猜 role。
2. turn 可能同时含文本与 image caption；只传文本会丢事实，泄露 image path/query 又越过公开边界。
3. session 有时间、turn 通常无时间；时间必须让 memory learner 可见。
4. gold evidence 存在分号挤在单字符串、坏 token、空 evidence 等异常；这些只属于 evaluator-private
   qrel，不能为了修 gold 改写 method 输入。

### 2.2 Letta 处置

- 从公开 `conversation_metadata` 读取 `speaker_a/speaker_b`，固定
  `speaker_a→user / speaker_b→assistant`；缺失、相同或第三 speaker fail-fast。
- 每条 content 保留真实 speaker 前缀，例如
  `user: [Session time: ...] Caroline: ...`。这不是双 namespace/正反视角；Letta official SDK
  没有 Phase 1 harness，主轨按一个 subject 的标准二元 conversation 产品语义扩展。
- image 只通过共享 helper 追加 `[Sharing image that shows: {caption}]`；path、query 与 locator
  不进入 content。
- 奇数 session 尾部是一条合法 message，不补空 assistant；wrapper 支持任意长度。
- Recall/F1@k/NDCG 为 N/A；LoCoMo answer F1/judge/EM 类指标仍可从 prediction artifact 计算。

锁定反例：Alice/Bob 映射不依首发、caption-only/文本+caption、session-time fallback、未知
speaker 拒绝、gold 字段负空间。

## 3. LongMemEval

稳定数据事实入口：[`docs/reference/integration/longmemeval.md`](../../../../../../reference/integration/longmemeval.md)。

### 3.1 风险

1. assistant-first、连续同 role、singleton 与奇数尾都真实存在；position-pair 会错配内容。
2. blank turn 与 role/content 可疑标注已由 benchmark canonical contract 裁定；method 不应二次
   猜测“谁说了这句话”。
3. question date 是答题变量，不是 message 缺失时间的回填源；history 不按 question date 截断。
4. 每题的完整 haystack 可很长，smoke history 裁剪必须由 benchmark planner 完成。

### 3.2 Letta 处置

- 保留 canonical user/assistant role 与原始 session 顺序，session 内最多 10 message 分批；
  batch 边界不改变 role，不制造 placeholder。
- turn 有时间用 turn time；否则使用当前 session time；同日 question/history 顺序不修改。
- 一个 question isolation 对应一个 subject；gold answer/session ids 与 has_answer 不进 worker。
- core blocks 没有 source unit 与 query rank，LongMemEval Recall/rank evaluator应从 evidence 得到
  N/A；不能因为官方数据有 turn qrel 就反向给 blocks 伪造 lineage。

锁定反例：assistant-first、连续 assistant、singleton、blank 已清理后的相邻 role、私有
has_answer/answer_session_ids 负空间。

## 4. MemBench

稳定数据事实入口：[`docs/reference/integration/membench.md`](../../../../../../reference/integration/membench.md)。

### 4.1 风险

1. FirstAgent 一个 step 是 `{user, agent}` pair，但 canonical contract 已拆成两个 child turn；
   method 若再次把 step 当单 turn 会丢 role 边界。
2. ThirdAgent 是 user-only message 序列，不能为了“像对话”伪造 assistant 回复。
3. 正常消息的 place/time 藏在 content 尾部；100k noise 没有二者，时间应为 None。
4. `target_step_id=[]` 与等于 `len(message_list)` 的越界 gold 由 evaluator-private evidence group
   处理，不得影响 ingestion。

### 4.2 Letta 处置

- SessionBatch 中 FirstAgent 的两个 canonical child 各成为一条 user/assistant message；
  ThirdAgent 每条保持 user，绝不插入 “I get it” 一类假内容。
- 原 content 的 place/time 尾部逐字保留。canonical adapter 的严格 boolean marker=True 时，
  Letta 不再前置 `[Turn time]`；字符串 `"true"` 等强反例不算 marker。
- noise 的 source time 为 None；不从 session、question 或相邻消息制造时间。
- choice/source accuracy 可从 prediction/private label artifact 计算；MemBench Recall 因 Letta
  readout 无 source item 而 N/A。

锁定反例：First/Third 两形、marker 三态、100k missing-time、place 保留、gold 越界负空间。

## 5. BEAM

稳定数据事实入口：[`docs/reference/integration/beam.md`](../../../../../../reference/integration/beam.md)。

### 5.1 风险

1. raw message id 在同一 chat 可重复、跳跃，不能作为全局 canonical turn identity。
2. 100k/500k/1m 结构规整；10m 有两处 orphan/mismatch，位置二元 chunk 会产生级联错配。
3. batch/叙事时间可能回退；框架不能跨 session 排序。
4. abstention gold 与 rubric 是 evaluator 私有信息。

### 5.2 Letta 处置

- 复用 benchmark 已生成的稳定 canonical turn id；adapter 不读取 raw id 做 dedup 或配对。
- 保留当前 session 内原 role/顺序。10m orphan user 是单条合法 message；下一组 assistant 不被
  拉回来组成假 pair。
- 有 source time 才进入 content；没有则 None；不按 batch 间时间重排。
- `beam-recall` 因 block 无单-message qrel mapping 而 N/A；`beam-rubric-judge` 仍可对 framework
  answer 评分。

锁定反例：重复 raw id、orphan user、相邻 mismatch、跨 batch 时间回退、abstention label
负空间。

## 6. HaluMem

稳定数据事实入口：[`docs/reference/integration/halumem.md`](../../../../../../reference/integration/halumem.md)。

### 6.1 固定运行形状

HaluMem 是 operation-level runner：每个 session 执行
`ingest → extraction（若 method 支持）→ update probes → 当前 session QA`，最后
`end_conversation → cleanup`。smoke 固定 4 sessions / 1 isolation / 1 QA / W1；禁止传
rounds/conversations/questions 通用裁剪旋钮。

### 6.2 Letta 四类 operation

| Operation | 资格 | 实际路径 |
| --- | --- | --- |
| extraction | N/A | Letta 没有 session-local delta，`session_memory_report=False`，artifact 写 `status=n/a` |
| update | valid | 写入 session 后读取当前全部 core blocks；官方 judge 检查旧事实是否被替换，不要求 source lineage |
| QA | valid | 同一累计 subject 的 blocks 进入官方 HaluMem unified answer builder |
| memory type | N/A | 官方 composite 依赖 extraction；且 Letta block label 不对应三类 gold memory type |

generated QA session 仍只 ingest，不运行 update/QA，沿用 benchmark frozen contract。private
memory points 只由 runner 构造 update query/judge artifact，绝不进入 build message。

## 7. 跨格 metric 与 artifact 规则

每题 readout 都盖：

```text
semantic_provenance = n_a / letta_core_blocks_are_evolved_query_independent_memory
provenance_granularity = none
stable_ranking = n_a / letta_core_blocks_are_not_query_ranked_retrieval_items
```

这只控制依赖 source qrel 或 rank 的 retrieval metrics。HaluMem update 是 current-state quality
judge，不依赖这两个条件，必须独立判 valid；不要再把“Recall N/A”误写成“update N/A”。

`formatted_memory`、answer prompt、prediction、efficiency 与 evaluator-private labels 必须各自
落标准 artifact；zero hit 用非空 sentinel，不能与 backend/worker error 混淆。

## 8. B11 machine plan（已生成；首份真实请求被外部 opt-in 门拒绝）

所有计划 `contract_version=smoke-plan-v1`，method=`letta`，profile=`smoke`，W1。
11 份未经手写改造的原始 planner 输出保存在
[`letta-smoke-plans-v1.json`](letta-smoke-plans-v1.json)。表中的 run id 是 planner 生成的
**prediction child run id**；LongMemEval/MemBench/BEAM/HaluMem 的命令输入使用各自共同 base
run id，variant 后缀由 planner 自动追加：

| Benchmark | Variant | prediction run id | Shape |
| --- | --- | --- | --- |
| LoCoMo | locomo10 | `letta-locomo-v1-r1` | rounds=1, isolation=1, question=1 |
| LongMemEval | s_cleaned | `letta-longmemeval-v1-r1-s-cleaned` | planner rounds=1, isolation=1, question=1 |
| LongMemEval | m_cleaned | `letta-longmemeval-v1-r1-m-cleaned` | planner rounds=1, isolation=1, question=1 |
| MemBench | 0_10k | `letta-membench-v1-r1-0-10k` | planner rounds=1, isolation=1, question=1 |
| MemBench | 100k | `letta-membench-v1-r1-100k` | planner rounds=1, isolation=1, question=1 |
| BEAM | 100k | `letta-beam-v1-r1-100k` | planner rounds=1, isolation=1, question=1 |
| BEAM | 500k | `letta-beam-v1-r1-500k` | planner rounds=1, isolation=1, question=1 |
| BEAM | 1m | `letta-beam-v1-r1-1m` | planner rounds=1, isolation=1, question=1 |
| BEAM | 10m | `letta-beam-v1-r1-10m` | planner rounds=1, isolation=1, question=1 |
| HaluMem | medium | `letta-halumem-v1-r1-medium` | fixed 4 sessions / 1 isolation / 1 QA |
| HaluMem | long | `letta-halumem-v1-r1-long` | fixed 4 sessions / 1 isolation / 1 QA |

Planner 仍列出 benchmark 的全部已注册 evaluator；不适用的 retrieval/extraction/memory-type
指标必须由 artifact/evidence 诚实输出 N/A，而不是从命令里暗删。涉及 API 的 judge 与 build/
answer 一样，待用户单独批准后才执行。

W2 负门已实测在 runtime/API 前拒绝：

```text
Error: Letta/MemGPT does not support smoke worker override from configured 1 to 2
```

## 9. 失效触发器

任一条件发生都必须重开相应 ledger 门，而不是沿用本 dossier：

1. vendored Letta commit、official SDK tag/formatter、agent tools 或默认 system prompt 漂移；
2. readout 改为 archival/search、启用 embedding 或 `skip_vector_storage=False`；
3. block label/limit、max message batch、role 映射或 time policy 变化；
4. operation journal schema、namespace identity、Postgres volume ownership 或 clean 顺序变化；
5. 开放 W2、切换 DB backend、改 worker transport/usage 观测；
6. benchmark stable contract、concrete variant/source lock 或 evaluator metric 资格变化。

## 10. 当前判词

五格离线 payload、安全与 metric 资格已经闭合。第一份真实 LoCoMo plan 已揪出并修复
Postgres ready 竞态与 official run lifecycle 缺失，但 OpenCodeGo 随后以 workspace 未完成
China-hosted model opt-in 的 HTTP 403 拒绝请求；因此真实 B11 仍未完成：

```text
LOCOMO_READY_FOR_B11
LONGMEMEVAL_READY_FOR_B11
MEMBENCH_READY_FOR_B11
BEAM_READY_FOR_B11
HALUMEM_READY_FOR_B11
LETTA_NOT_FROZEN_UNTIL_REAL_SMOKE_AND_ARTIFACT_GATE
```

恢复与失败资产见
[`letta-b11-first-live-attempt-r1.md`](letta-b11-first-live-attempt-r1.md)。
