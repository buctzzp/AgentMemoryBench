# Graphiti method-frozen-v1

日期：2026-08-12

架构师：GPT-5.6 sol

方法版本：`getzep/graphiti v0.29.3@021d3a57`

adapter：`graphiti-oss-product-v1`

状态账：[Graphiti Method Integration Ledger v1](./graphiti-integration-ledger.md)

## 0. 冻结判词

```text
GRAPHITI_METHOD_FROZEN_V1(
  identity = Graphiti OSS, not Zep hosted,
  product_surface = direct Graphiti.add_episode + Graphiti.search,
  storage = one isolated FalkorDB Lite root per conversation,
  input = one nonblank canonical turn per episode, no placeholder or reordering,
  readout = product edge facts in stable RRF order,
  provenance = valid turn lineage through edge.episodes + atomic sidecar,
  workers = W1 and W2 live-verified where the benchmark shape permits,
  halumem = extraction + update + QA + memory-type valid,
  membench_100k = N/A because product reference_time is mandatory
)
```

`method-frozen-v1` 表示 current source、adapter、TOML、五格 contract、真实极小 smoke、
artifact gate 与整仓回归已经闭合；它不表示这些极小样本可用于效果排名，也不把 Graphiti
结果冒充 Zep cloud 产品或论文数字。

## 1. 冻结身份

| 项 | 值 |
| --- | --- |
| upstream | `https://github.com/getzep/graphiti.git` |
| release / commit | `v0.29.3` / `021d3a57d511f21b10adaf7fa923bd5c1fce5e9d` |
| license | Apache-2.0 |
| local source | `third_party/methods/graphiti` |
| source identity | `graphiti-v0.29.3-source-v1` |
| adapter | `graphiti-oss-product-v1` |
| product surface | direct `Graphiti.add_episode()` + `Graphiti.search()` |
| storage | 每 conversation 独占 FalkorDB Lite 物理 root |
| build LLM | smoke=`opencodego/deepseek-v4-flash`；official-full=`primary/gpt-4o-mini` |
| embedding | local `all-MiniLM-L6-v2`，384 维、L2 normalize、cosine |
| answer/judge | benchmark unified builder；Graphiti 无完整官方 answer harness |

direct core 与官方 server 委托的是同一个 Graphiti 产品实现；本项目绕过的是 HTTP transport，
不是 graph build/search 算法。current 官方 repo 只有 LongMemEval graph-build payload anchor，
没有完整 search/answer/judge harness；因此 LongMemEval 输入面可称 official-compatible，完整评测
仍是 framework extension，其余四家全部明确标 framework extension。

## 2. B0-B11 对表

| 门 | 结论 | 冻结证据 |
| --- | --- | --- |
| B0 official harness | `closed` | current repo 仅 LongMemEval graph-build；逐 message `role: content` + session date；无完整 answer/judge |
| B1 source/product | `closed` | Apache-2.0 source lock；只用公开 `add_episode/search`，不直写 node/edge |
| B2 granularity | `closed` | 五格统一 turn episode；不补 placeholder、不配对、不重排，blank 走 benchmark canonical policy |
| B3 isolation/parallel | `closed` | 每 conversation 独占 worker/client/FalkorDB root；全部 croppable variant 的 W1/W2 已真实通过 |
| B4 input/readout | `closed` | role/speaker/content/place/image/time 从 canonical event 到真实 Episodic node 字节级复核；product edge fact/time 全进入 readout |
| B5 provenance/rank | `closed` | active edge 的 `episodes` + atomic sidecar 回映 public turn；RRF product order stable；unknown lineage fail-fast |
| B6 completion | `closed` | 每次 `add_episode` 串行 await 即 terminal；无 server queue；close 未确认永久 fail-closed |
| B7 observability | `closed` | build LLM exact API usage；local embedding tokenizer estimate；retrieval/answer/judge scope 全落盘 |
| B8 side effects/retry | `closed` | search 只读；root marker→tombstone→可重入清理；operation digest 与失败 checkpoint 已验 |
| B9 identity | `closed` | source/build/embedding/search/API runtime/answer compatibility 均进 manifest；secret/base URL 不落公开 artifact |
| B10 TOML/builder | `closed for main` | 单 TOML 的 smoke/official-full 主配置；无虚构 author section；LoCoMo OpenCodeGo cap 显式盖章 |
| B11 smoke/freeze | `closed` | 18 份 planner v2 run、35 conversation/35 question、88 product episodes、两道机器门及最终整仓回归 |

## 3. 五 benchmark 主轨与真实 smoke

| Benchmark | current 主轨 | 真实运行 | 资格与边界 |
| --- | --- | --- | --- |
| LoCoMo | `speaker_a→user`、`speaker_b→assistant`；真实 speaker 前缀、caption wrapper、逐 turn time | `locomo10` W1/W2 | provenance/rank valid；6 metric 均 ok |
| LongMemEval | raw role/order、逐 turn；assistant-first/same-role/singleton 不修复 | S/M 各 W1/W2 | S 六项 ok；M 所选官方 no-target 题的 Recall/rank 为 N/A，不是 provider 失败 |
| MemBench | First pair 拆 canonical children；Third 单 user；原 place/time 文本保留且 typed time 另传 | `0-10k` W1/W2 | 三项 metric ok；`100k` mandatory source time 缺失，API/runtime/output 前 N/A |
| BEAM | 四 variant 按 canonical positional id 原序逐 turn写入；不位置配对 | 100k/500k/1m/10m 各 W1/W2 | rubric ok；默认 smoke 是 abstention，Recall N/A；provider evidence 仍 valid/turn/stable |
| HaluMem | 固定四 session、逐 turn add、session-local current active edge report | Medium/Long 固定 W1 | extraction/update/QA/memory-type 与三个离线 answer metric 全部落盘 |

v2 machine plan 是
[`graphiti-smoke-plans-v2.json`](./graphiti-smoke-plans-v2.json)。旧 v1 LoCoMo W1 在首个
build request 命中过 OpenCodeGo 403；`predict smoke` 不支持 resume，故旧 run 只保存失败阶段
证据，v2 使用新 run identity，未拼接或改写旧 checkpoint。

## 4. 两道真实验货门

### 4.1 Artifact / 隐私 / 效率 / 物理隔离

18 份 plan 与 run root 一一对应，机器逐项检查 manifest、public question、prediction、完整
answer prompt、private label 负空间、全部 evaluator summary/score、prediction/judge efficiency、
model inventory、conversation state、W1/W2 worker root 与 secret/base URL 负空间：

```text
GRAPHITI_V2_ARTIFACT_GATE_PASS
  runs=18 conversations=35 questions=35 episodes=88
  halumem_top_k=legacy_artifact_gap_fixed_in_current_serializer

JUDGE_CALLS {
  "beam_rubric_judge": 14,
  "halumem_extraction": 112,
  "halumem_qa": 2,
  "halumem_update": 14,
  "locomo_judge_accuracy": 3,
  "longmemeval_judge_accuracy": 6
}
```

所有 croppable W2 run 都同时存在 `worker_0/worker_1` 独立物理 state；W1 不制造 worker
子目录。每个 question 有一条 answer LLM 与 question-efficiency observation；每个 conversation
至少一条 build LLM `api_usage` 与 build embedding tokenizer observation；付费 evaluator 的
observation 全是 judge stage，且 runner-internal observation 不泄露进 score/summary。

### 4.2 Product payload parity

机器把每个 FalkorDB root 复制到临时只读验货区，直接读真实 `Episodic` node，再由 v2 plan
重建 canonical event，逐项比较 `name/content/valid_at`：

```text
GRAPHITI_PRODUCT_PAYLOAD_PARITY_PASS runs=18 conversations=35 episodes=88
```

这道门覆盖 LoCoMo speaker-role/caption/time、LongMemEval raw role/order/time、MemBench
First/Third/place/time、BEAM 四 variant 以及 HaluMem 全部 session，不靠 fake provider 推断
真实产品写入。

## 5. 运行中发现并关闭的框架问题

1. **LoCoMo answer cap**：OpenCodeGo + LoCoMo 的小上限改为显式 4096 safety cap，manifest
   写 `opencodego_locomo_explicit_completion_cap_4096_v3`；primary 正式轨仍保留官方 32。
2. **HaluMem judge JSON**：OpenCodeGo Chat Completions 显式发送
   `response_format={"type":"json_object"}`；只收紧 transport，不改评分 prompt/公式。
3. **metric 依赖顺序**：`halumem-memory-type` 在 registry 声明 extraction/update artifact
   prerequisite；planner 和直接 `evaluate` executor 都做同一稳定拓扑排序并拒绝重复 metric。
4. **operation top-k artifact**：HaluMem 产品请求本来就是 update=10、QA=20；旧 v2 artifact
   serializer 漏写 `retrieval_query_top_k`，current serializer 与强反例已修。既有付费 artifact
   不回写，冻结记录明确保留历史边界。

上述四项都是共用 framework 修复，不是 Graphiti 特判。

## 6. 冻结后声明缺口

1. MemBench 100k 缺可靠 source time，继续 N/A；不得用 question/sibling/wall clock 造时。
2. BEAM 默认 smoke 没有命中 10M 两处 orphan/mismatch 的真实位置；current canonical/data census
   与生产强反例覆盖该形状，若要 live sentinel 必须另立预算和 run identity。
3. LongMemEval M smoke 当前选到 official no-target 问题，故 retrieval metric N/A；不能把 N/A
   写成 0，也不能据此评价 Graphiti 检索能力。
4. BEAM 默认问题是 abstention，故 Recall N/A；rubric judge 与 provider evidence 均正常。
5. local MiniLM revision 仍是 `local_unpinned`；模型目录内容变化会触发解冻重验。
6. Graphiti 官方没有完整 answer harness，故没有 `author_<benchmark>`；未来若 upstream 新增，
   需作为稀疏作者校准独立审计，不能暗改主表。
7. formal/full resume、真实效果 full run、成本 pilot 与论文/产品效果对表均尚未做。
8. Graphiti source lock、default search recipe、edge lineage、API runtime、adapter 或 benchmark
   canonical contract 任一变化，都必须版本化解冻并做影响分析。

## 7. 最终验收门

最终回归结果在同批 commit 前现场写入本节：

- Graphiti/CLI/evaluator/operation 定向门：`367 passed in 29.36s`；
- ledger/doc 门：`11 passed in 2.12s`；ledger validator `methods=5` PASS；
- 全量 pytest：`2142 passed, 3 deselected, 13 warnings, 29 subtests passed in 176.65s`；
- compileall：`exit 0`；
- `git diff --check`：`exit 0`；
- Graphiti worker/FalkorDB/Redis 进程残留：`0`。

冻结分数只证明 pipeline 与 evaluator 可达；极小样本分数不得进入效果排名或预算结论。
