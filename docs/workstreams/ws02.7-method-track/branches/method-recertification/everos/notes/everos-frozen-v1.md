# EverOS method-frozen-v1

日期：2026-08-14

架构师：GPT-5.6 sol

方法身份：官方 `EverMind-AI/EverOS v1.2.3@48fc908`

adapter：`everos-product-chat-v6`

状态账：[EverOS Method Integration Ledger v1](./everos-integration-ledger.md)

## 0. 冻结判词

```text
EVEROS_METHOD_FROZEN_V1(
  product_surface = create_app lifespan + typed memorize/search/get,
  input = one canonical session + internal batch 25 + explicit flush,
  readout = public HYBRID synthesized Episode,
  isolation = one Python worker and physical product root per conversation,
  source_time = exact source time + LoCoMo official 30s order only,
  semantic_provenance = N/A,
  stable_ranking = valid,
  halumem = extraction/update/QA/memory-type valid,
  membench_100k = unsupported because source time is absent
)
```

`method-frozen-v1` 证明 current source、typed 产品调用链、五格输入、18 份真实 smoke、W1/W2
ownership、全部适用 evaluator、artifact/效率/隐私/产品状态与代码回归闭合。它不表示极小样本
可以用于效果排名，也不把合成 Episode 的输入 sidecar 冒充 lossless semantic lineage。

## 1. 冻结身份与运行配置

| 项 | 冻结值 |
| --- | --- |
| upstream | `https://github.com/EverMind-AI/EverOS.git` |
| commit / package | `48fc9084888bc17100053227284f939a5aca5e91` / `1.2.3` |
| license | Apache-2.0；精确锁定的 EverAlgo runtime 亦有公开 Apache-2.0 source |
| product entry | official `create_app()` lifespan 内 typed `memorize/search/get` service |
| ingest granularity | canonical session；内部 add batch 25；session 末显式 flush + exact drain |
| adapter / worker / state | `everos-product-chat-v6` / `everos-worker-protocol-v2` / `everos-conversation-sidecar-v2` |
| adapter / worker SHA-256（18 份 run manifest） | `ab465ee7974e918fa5710243a68d565d38229ecd5dad26ff8c44e4d3e34e6cdf` / `8a393c35b915a78de6641b709386f9f2f8a5597bdbbf3a33305e63a54f0ec5b6` |
| build/answer/judge | smoke=`opencodego/deepseek-v4-flash`；official-full=`primary/gpt-4o-mini` |
| embedding | `Qwen/Qwen3-Embedding-4B`，1024 dimension，LanceDB L2；smoke 用 OpenRouter OpenAI-compatible transport |
| rerank | smoke=`disabled-zero-call`；official-full=`configured` DeepInfra；current chat/Episode 主轨实测零调用 |

worker 进入产品 lifespan，不启动 HTTP host，也不绕过 boundary、Episode、OME、Cascade、SQLite 或
LanceDB。run-local root 只复制产品运行时实际 watch 的 `ome.toml`；upstream `default.toml` 继续从
vendored package 读取，再由受限环境覆盖 transport。v6 不把含 endpoint 默认值的模板复制进
`outputs/`。

## 2. B0-B11 对表

| 门 | 结论 | 冻结证据 |
| --- | --- | --- |
| B0 official harness | `closed` | current public harness 只有 LoCoMo；LongMemEval 仅论文报告、无公开最终 payload；另三格为 framework extension |
| B1 source/product | `closed` | v1.2.3、EverAlgo source、runtime lock、official lifespan typed service 与最小 shutdown observability patch 均锁定 |
| B2 granularity | `closed` | session 原序；每个 canonical 非空 event 一条 message；纯 assistant session 只加无 source identity 的空 user owner anchor |
| B3 isolation/parallel | `closed` | 35 个 conversation 各有物理 product root；8 份 W2 run 均有 `worker_0/worker_1` 独立 owner/root |
| B4 input/readout | `closed` | role/speaker/content/time/place/caption 无损；HYBRID Episode 的 subject/summary/episode/atomic facts/score/rank 进入 formatted memory |
| B5 provenance/rank | `closed` | synthesized Episode semantic provenance=N/A；product/merge stable rank=valid；Recall/NDCG 不硬算 |
| B6 completion | `closed` | OME terminal + Cascade health/failure + deadline/event-loop yield + 双稳定零 + 传递 OME 再验 |
| B7 observability | `closed` | build/answer/judge LLM 与 build/retrieval embedding exact usage；rerank zero-call；scope 全落 artifact |
| B8 side effects/resume | `closed` | search 只读；completed journal、digest drift 拒绝、tombstone clean retry 与 shutdown failure 可见 |
| B9 identity/privacy | `closed` | source/wrapper/API/embedding/transport 盖 manifest；secret/base URL/upstream endpoint 精确值负空间为零 |
| B10 TOML/builder | `closed for main` | smoke/official-full 主 section 与 benchmark unified builder；author LoCoMo 未混入主表 |
| B11 smoke/freeze | `closed` | 18 plan、35 question/conversation、全部 evaluator、状态/产物机器门、W1/W2 与全量回归 |

## 3. 五 benchmark 主轨与真实 smoke

| Benchmark | 主轨输入与异常处置 | current 真实 run | 资格边界 |
| --- | --- | --- | --- |
| LoCoMo | official all-user + 真实 speaker owner；session source time 起点后按 utterance `+30s`；共享 caption wrapper；多 owner 稳定合并 | `everos-locomo-v6-r1-w1`、`everos-locomo-v6-r1-w2` | semantic recall N/A；stable rank、answer/judge valid |
| LongMemEval | S/M 完整 session；assistant-first、same-role、singleton/odd tail 原序；纯 assistant 只加空结构 owner anchor | S/M 各 W1+W2，共 4 run | Recall/NDCG N/A；answer/judge valid |
| MemBench | First canonical child role 与 Third user-only；原 time/place 不删不重拼 | `0-10k` W1+W2，共 2 run | 100k 缺 source time，API/output 前拒绝；Recall N/A |
| BEAM | 100k/500k/1m/10m canonical id/role/order；10M orphan/mismatch 不修 raw、不位置重配 | 四 variant 各 W1+W2，共 8 run | Recall N/A；rubric judge valid |
| HaluMem | fixed 四 session；每 session flush+exact drain 后按 session public get，并以累计 search 做 update/QA | Medium/Long 各 fixed W1，共 2 run | extraction/update/QA/memory-type 均 valid |

current machine plan 是 [everos-smoke-plans-v1.json](./everos-smoke-plans-v1.json)：8 个 croppable
concrete variant 各跑 W1/W2，2 个 HaluMem fixed variant 各跑 W1，共 18 份 fresh v6 run、35 个
conversation、35 个 public question。所有命令消费 planner 原始 `argv`；HaluMem 未误加通用裁剪
参数，smoke 未使用 resume。

HaluMem 数值仅作为 artifact 可达性记录，不作小样本效果结论：

| variant | extraction F1 | update C ratio | QA C ratio | memory-type mean |
| --- | ---: | ---: | ---: | ---: |
| Medium | `0.0192307692` | `0.4285714286`（3/7） | `1.0`（1/1） | `0.1461251167` |
| Long | `0.0190476190` | `0.1428571429`（1/7） | `1.0`（1/1） | `0.0952380952` |

## 4. Artifact、效率、隐私与产品状态门

冻结前从 18 个 current root 独立重算，而非抄执行器摘要：

```text
EVEROS_V6_FREEZE_RECOUNT_PASS
plans=18, runs=18, conversations=35, questions=35
sidecars=35, completed_operations=44, product_sessions=44, source_rows=88
source-exact=85, locomo-official-30s-order=3, synthetic_owner_anchors=0
llm_calls: memory_build=186, answer=35, judge=257
embedding_calls: memory_build=704, retrieval=89
product_roots=35, OME_run_records=142, memcells=44, unprocessed_buffer=0
```

- 35 条 prediction prompt 都有非空 `formatted_memory`、非空 retrieved items，且公开
  `answer_context == formatted_memory`；top-k 为 HaluMem 20、其他 benchmark 10。
- 35 条 RetrievalEvidence 全部是 semantic provenance
  `n_a/everos_episode_is_synthesized_not_source_exact`，stable ranking `valid`，没有因“能检索”
  就伪造 source qrel 资格。
- judge scope 实数为：HaluMem extraction 218、update 14、QA 2；BEAM rubric 14；LongMemEval
  judge 6；LoCoMo judge 3。BEAM 多出的两次来自 evaluator 的 equivalence 分支，不是重复记账。
- 35 个 sidecar、44 个 operation/session、88 个 source row 与 44 个 SQLite memcell 一一闭合；
  `unprocessed_buffer=0`。每份 W2 run 的状态实际分布在 `worker_0` 与 `worker_1`，不是只看
  manifest 的 `max_workers=2`。
- 142 条 OME run record 中 141 success、1 failed；唯一失败是
  `everos-beam-v6-r1-w2-1m` 的 `extract_atomic_facts` attempt 0 timeout，同 event/strategy 的
  attempt 1 success。exact drain 允许这种已恢复 retry chain，并拒绝任何无后继成功的 failure。
- 每个 product root 有 `ome.toml`、没有 `everos.toml`。对 `.env` OpenCodeGo/OpenRouter key、
  base URL 与 upstream OpenRouter/DeepInfra endpoint 的精确值扫描均为 0 命中；不能用泛搜
  `base_url`，因为 benchmark 对话本身可合法讨论该字段。

## 5. 冻结前纠错与版本链

1. v2/v3 曾试图用 operational timestamp 支持缺时 turn。MemBench 100k 首先暴露毫秒判别问题；
   继续追到 Episode prompt 后确认，即使合法 sentinel 也会成为记忆事实。最终 v6 删除 fallback，
   明确拒绝该 variant；不是为了填满矩阵而造时间。
2. v5 exact drain 用固定 100 次紧循环。真实 background worker 已 claim Cascade row 时，前台可在
   它再次获得 event-loop 时间片前耗尽循环。v6 改为同一 wall-clock deadline 内显式 yield，仍以
   terminal/health/双零作为完成条件，没有改产品调度拓扑。
3. v5 复制 upstream `default.toml` 到 run root，虽无 secret value，却会把公开 provider endpoint
   固化进 artifact。v6 只复制必须 root-local watch 的 `ome.toml`，并用精确值负空间锁住边界。
4. Medium 首次产生 memory-type 数值时曾被误暂停。复核 evaluator 后改判：该指标消费
   extraction/update scores，再按 evaluator-private gold taxonomy 聚合，不要求 method 输出
   Event/Persona/Relationship 类型；Medium/Long 均已实证。

## 6. 冻结后声明缺口与解冻条件

1. synthesized Episode 没有 lossless semantic source mapping，Recall/Precision/F1@k 与
   LongMemEval NDCG 继续 N/A；stable ranking 不自动赋予 provenance 资格。
2. MemBench 100k 的 noise turn 缺 source time，而 EverOS typed product/prompt 会消费并渲染时间；
   在出现官方无损 missing-time 表达前保持 unsupported，不用 sentinel、墙钟或 question time 补齐。
3. current public harness 只覆盖 LoCoMo；LongMemEval paper-reported 但 public payload 缺失，
   HaluMem/BEAM/MemBench 是 product-faithful framework extension。
4. smoke 只证明可达性、产物与运行边界。official-full、作者 LoCoMo calibration、真实 resume、
   成本 pilot、效果 full 与论文/产品数字对表尚未执行。
5. upstream source/runtime lock、typed service、OME/Cascade completion、Episode/readout、message/time
   policy、root config、embedding/rerank transport、wrapper hash、benchmark canonical contract 或
   metric 资格任一实质变化，触发版本化解冻。

## 7. 最终验收门

冻结前现场结果：

- ledger validator 与 doc 门在冻结同步后通过；
- 扩展定向：`294 passed`；
- 全量 pytest：`2158 passed, 3 deselected, 13 warnings, 29 subtests passed in 147.45s`；
- compileall：`exit 0`；
- `git diff --check`：`exit 0`；
- 18 份 frozen run 的 adapter/worker source SHA-256 全部一致；冻结后只做文档同步，不再改生产
  wrapper；
- current source pin：`48fc9084888bc17100053227284f939a5aca5e91`。

13 个 warning 均来自既有 LightMem Pydantic deprecation 与 MemOS datetime/Pydantic serialization，
无 EverOS 新 warning。冻结证书只为上述 current identity 背书。
