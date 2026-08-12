# LangMem method-frozen-v1

日期：2026-08-12

架构师：GPT-5.6 sol

方法身份：官方 `langchain-ai/langmem` package `0.0.30@56d8593`

adapter：`langmem-background-product-v1`

状态账：[LangMem Method Integration Ledger v1](./langmem-integration-ledger.md)

## 0. 冻结判词

```text
LANGMEM_METHOD_FROZEN_V1(
  product_surface = create_memory_store_manager().ainvoke() + asearch(),
  input = one canonical session per manager invocation,
  store = LangGraph InMemoryStore + exact atomic snapshot/journal,
  isolation = one provider/worker/store/state root per framework worker,
  placeholders = none,
  ranking = valid product order,
  semantic_provenance = N/A for evolved memories,
  workers = W1 and W2 for every croppable concrete variant,
  halumem = extraction N/A, update and QA valid, memory-type N/A
)
```

`method-frozen-v1` 证明 current source、产品调用链、五格输入、20 份真实 smoke、W1/W2
ownership、artifact/效率/隐私门和代码回归闭合。它不表示极小样本可用于效果排名，也不把
hot-path agent、raw store put、未来 LangMem main 或 source lineage 推断冒充本轨算法。

## 1. 冻结身份与 source drift

| 项 | 冻结值 |
| --- | --- |
| upstream | `https://github.com/langchain-ai/langmem.git` |
| commit / package | `56d85939d80bb731bd5e237567148d817d7bfd16` / `0.0.30` |
| license | MIT |
| product entry | `create_memory_store_manager()`；async `ainvoke()` + `asearch()` |
| ingest granularity | canonical session |
| store | `langgraph.store.memory.InMemoryStore` + adapter atomic state/journal |
| build LLM | smoke=`opencodego/deepseek-v4-flash`；official-full=`primary/gpt-4o-mini` |
| embedding | local `all-MiniLM-L6-v2`，384 dimension，external L2，cosine |
| answer/judge | benchmark unified builder；五格均无 LangMem 官方 harness |

冻结前现场 `git ls-remote` 显示 upstream main 为 `29cbe41e58528f92e9efa773c12e15c47be3808c`。
从冻结 pin 到该 HEAD 共有 4 个依赖维护提交，`git diff --stat` 唯一变化是 `uv.lock`
（136 insertions / 139 deletions）；package source、background manager、store/search、prompt 与公共
API 均未变。因此保留已经通过真实 B11 的 `56d8593`，不为 lock-only drift 重烧或偷偷升级算法
身份。未来若产品代码或 runtime lock 的实际依赖闭包改变，再按 B1/B9 解冻。

## 2. B0-B11 对表

| 门 | 结论 | 冻结证据 |
| --- | --- | --- |
| B0 official harness | `closed / N/A payload` | current repo 对五家 Phase-1 benchmark 均无 harness，五格诚实标 framework extension |
| B1 source/product | `closed` | 0.0.30 pin、MIT、selected source hash、async background manager 与变体边界均锁定 |
| B2 granularity | `closed` | session 原序；assistant-first、same-role、singleton、odd tail 合法；不补 placeholder、不跨 session |
| B3 isolation/parallel | `closed` | 47 个 conversation 对应 47 个独立 namespace/state；每个 W2 run 实际落到 `worker_0` 与 `worker_1` 两套 owner |
| B4 input/readout | `closed` | 五格 role/speaker/content/time/place/caption 进入产品；82 条 current readout 以 XML-safe 格式完整进入 answer context |
| B5 provenance/rank | `closed` | evolved memory semantic provenance=N/A；product score/order=valid；Recall/NDCG 不硬算 |
| B6 completion | `closed` | `ainvoke()` 等待 insert/update/delete；成功后才原子写 snapshot+journal；rollback/clean retry 有强反例 |
| B7 observability | `closed` | build/answer/judge 精确 API usage，本地 build/retrieval embedding tokenizer+timer，retrieval latency 全进入 artifact |
| B8 side effects/resume | `closed` | `asearch()` 只读；operation journal、result-loss reuse、payload drift 拒绝、tombstone clean 均闭合 |
| B9 identity | `closed` | source/wrapper/runtime/API/embedding/transport 进入 manifest；secret/base URL 负空间为零 |
| B10 TOML/builder | `closed for main` | smoke/official-full 两主 section；五格统一 benchmark builder；无虚构 author section |
| B11 smoke/freeze | `closed` | 20 plan、47 conversation/question、全 evaluator、artifact machine gate、W1/W2 与最终代码门 |

## 3. 五 benchmark 主轨与真实 smoke

| Benchmark | 主轨输入与异常处置 | current 真实 run | 资格边界 |
| --- | --- | --- | --- |
| LoCoMo | 固定 `speaker_a→user`、`speaker_b→assistant`；真实 speaker 前缀、source time 与共享 caption wrapper；奇数尾不补 placeholder | `langmem-locomo-v1-r1-w1`、`langmem-locomo-v1-r1-w2` | recall N/A；stable rank valid；answer/judge 可算 |
| LongMemEval | S/M 完整 session；assistant-first、连续同 role、singleton/odd tail 保持原序 | S/M 各 W1+W2，共 4 run | Recall/NDCG N/A；judge 与 answer 指标可算 |
| MemBench | First canonical child role 保真；Third user-only；原 place/time 不删不重复；100k missing time 保持 None | 0-10k/100k 各 W1+W2，共 4 run | recall N/A；choice/source accuracy 可算 |
| BEAM | 100k/500k/1m/10m 原 canonical id/role/order；10M orphan/mismatch 不补写或位置重配 | 四 variant 各 W1+W2，共 8 run | recall N/A；rubric judge 可算 |
| HaluMem | fixed 四 session 原序；每 session 一次 async manager 完成；private memory point 不进 build | Medium/Long 各固定 W1，共 2 run | extraction/type N/A；update/QA valid |

current machine plan 是 [`langmem-smoke-plans-v1.json`](./langmem-smoke-plans-v1.json)。9 个
croppable concrete variant 各跑 W1/W2，2 个 HaluMem fixed variant 各跑 W1，共 20 份 run、47 个
conversation、47 个 public question。所有命令消费 planner 原始 `argv`；HaluMem 未误加通用裁剪参数，
smoke 未使用 resume。

## 4. Artifact、效率、隐私与状态机器门

逐 run 核对 plan/root、manifest/source/wrapper、API runtime、公开 question/prediction、真实
formatted memory、private-label 负空间、RetrievalEvidence、score/summary、efficiency、state、日志与
W1/W2 ownership：

```text
LANGMEM_B11_CURRENT_ARTIFACT_GATE_PASS
{"answer_llm_calls": 47, "build_embedding_calls": 150,
 "conversations": 47, "judge_llm_calls": 39,
 "memory_build_llm_calls": 56, "namespaces": 47,
 "questions": 47, "retrieval_embedding_calls": 61,
 "retrieved_items": 82, "runs": 20,
 "secret_or_endpoint_hits": 0, "state_entries": 91}
```

- 47 份 state 各有非空 current entry 与 completed-operation journal；namespace 全部唯一。
- W1 state 直接位于 run-owned `method_state/langmem_state/`；每份 W2 state 实际分布在
  `worker_0` 与 `worker_1`，不是只看 manifest 中的 workers 数字。
- 82 条 retrieved item 的 `product_rank` 连续且 score 非增；`source_turn_ids=[]` 与
  `semantic_provenance=n_a/langmem_evolved_memory_not_source_exact` 一致，不伪造 lineage。
- 每题的 `answer_context` 与真实 `formatted_memory` 相同且非空；question efficiency 47 条、answer
  API usage 47 条、retrieval embedding 至少逐题可见。
- HaluMem 两个 run 均写 4 条 N/A session report、7 条非空 update probe；update judge 共 14 次、QA
  judge 共 2 次，extraction/type 为 0 行 + null，不以 0 分冒充能力。
- BEAM 12 题产生 14 次 judge：1M 的两题按官方 evaluator 条件分支额外调用 equivalence judge，
  不是重复计费或 observation double-count。
- MemBench source accuracy 每 run 是固定四 cell + total 的 5 行聚合，不误套“一题一 score”规则。
- 20 个 current run 的文件、terminal log、state 与公开 artifact 中，OpenCodeGo key/base URL 命中为 0。

## 5. 本批执行与验货勘误

1. 首份 LoCoMo W1 的 predict/evaluate 都已成功，外层 zsh 包装却在事后给只读变量 `status` 赋值而
   返回 1；没有重跑 API，只归档既有成功日志并以 summary/artifact 判定。
2. LoCoMo W2 两份 terminal log 被执行器按含 variant 的旧路径猜法写到孤立目录；机器门发现后仅
   移到 manifest 所在真实 run root，没有修改实验产物或重跑 API。
3. 初版验货脚本先后错误假设所有 benchmark 的 `max_tokens=4096`、专用 runner 必须在 metadata
   重复顶层 evidence 字段、所有 evaluator 都“一题一 score/judge”。三处均按 builder/evaluator
   当前契约改正，未为迁就脚本修改正确产物；这些勘误本身不构成 method regression。

## 6. 冻结后声明缺口与解冻条件

1. evolved memory 无 lossless semantic source mapping，Recall/Precision/F1@k 与 LongMemEval NDCG
   继续 N/A；稳定产品 ranking 不会自动赋予 provenance 资格。
2. HaluMem changed puts 可能融合旧 memory，不能当成严格本-session extraction point；extraction 与
   memory-type N/A，current-state update/QA 不受连坐。
3. 五格无 official harness，当前主表是 product-faithful framework extension。未来出现官方 harness
   时单独审计 author calibration，不暗改主配置。
4. smoke 只证明可达性、完整产物与运行边界，不证明效果。official-full、真实 smoke resume、成本
   pilot、全量效果与论文/产品数字对表尚未执行。
5. upstream product source、factory 默认、store/ranking、message/time policy、runtime lock、wrapper
   hash、benchmark canonical contract 或 metric 资格任一实质变化，触发版本化解冻。

## 7. 最终验收门

冻结提交前现场结果：

- ledger validator：`PASS method integration ledger: contract=method-integration-ledger-v1,
  methods=everos, graphiti, langmem, letta, supermemory, count=5`；
- ledger/doc 门：`11 passed in 1.19s`；
- 全量 pytest：`2145 passed, 3 deselected, 13 warnings, 29 subtests passed in 157.91s`；
- compileall：`exit 0`；
- `git diff --check`：`exit 0`；
- current source pin：`56d8593`；upstream HEAD：`29cbe41`，影响面仅 `uv.lock`。

13 个 warning 均来自既有 LightMem Pydantic deprecation 与 MemOS datetime/Pydantic serialization，
无 LangMem 新 warning。冻结证书只为 current identity 背书。
