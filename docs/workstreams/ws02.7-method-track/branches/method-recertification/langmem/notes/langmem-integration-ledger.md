# LangMem Method Integration Ledger v1

> 本账在任何 adapter 代码之前创建。旧 ws02 审计只作待复核线索，不把 README 宣传、
> 第三方 baseline 或历史 pin 冒充 current product 事实。完整判据见
> [Method 接入标准清单](../../../../../../reference/method-integration-checklist.md)。

<!-- method-integration-ledger
contract_version: method-integration-ledger-v1
method_id: langmem
display_name: LangMem
ledger_state: ready_for_smoke
integration_page: docs/reference/integration/langmem.md
dossier: docs/workstreams/ws02.7-method-track/branches/method-recertification/langmem/notes/langmem-five-benchmark-safety-dossier.md
frozen_note: none
-->

## 必填检查点

<!-- ledger-checkpoints:start -->
| ID | 完成判据 | Status | 证据、裁决与下一动作 |
| --- | --- | --- | --- |
| B0-OFFICIAL-BENCHMARKS | 当前官方 repo 实际跑过的 benchmark、入口和版本已穷举，未跑过者标 framework extension | PASS | evidence=[M1 §3](./langmem-current-product-identity-m1-ruling.md); ruling=current official repo 对五家 benchmark 均无 harness，五格全为 framework extension，第三方 baseline 不冒充官方; next=none |
| B0-FINAL-PAYLOAD | 每个官方 harness 展开后的 add 次数、batch、role、namespace、时间、模型参数和 search 最终 payload 已锁 | N/A | evidence=[M1 §3](./langmem-current-product-identity-m1-ruling.md); ruling=官方 Phase 1 harness 集为空，不存在 author benchmark payload；产品 payload 由 M1/M2 另锁; next=none |
| B0-DIFFERENCE-RULING | 主轨、author 轨、framework extension、upstream bug 的每项差异已唯一归类 | PASS | evidence=[M1 §4-6](./langmem-current-product-identity-m1-ruling.md); ruling=async background manager=主轨，hot-path agent=ALGORITHM_VARIANT，direct put=MECHANISM_BYPASS，sync duplicate search=UPSTREAM BUG，当前无 author 轨; next=none |
| B1-SOURCE-LOCK | 官方 repo、tag、commit、license、vendored 路径、patch 和更新策略已锁定 | PASS | evidence=[M1 §2](./langmem-current-product-identity-m1-ruling.md); ruling=current 56d8593/package 0.0.30/MIT/selected hash 已锁，MANIFEST 与 fetch 已更新，无 patch; next=none |
| B1-PRODUCT-SURFACE | ingest/retrieve 采用通用产品接口，并解释为何不用 chat、ask、eval、cloud 或 HTTP 专用入口 | PASS | evidence=[M1 §4-6](./langmem-current-product-identity-m1-ruling.md); ruling=主轨用 create_memory_store_manager().ainvoke + asearch，避开 answer agent 与 raw-store bypass; next=none |
| B1-LIFECYCLE-CALLGRAPH | prepare、ingest、retrieve、finalize、cleanup 的 runner 真实调用点和早失败路径已逐一闭合 | PASS | evidence=[M2 §2](./langmem-m2-adapter-implementation.md); ruling=generic 与 operation runner 有工作项时 prepare，session ingest、query retrieve、failed clean 和 finally cleanup 均穿过生产 adapter；lazy runtime 与 cleanup 重试有强反例; next=none |
| B2-GRANULARITY | 原生输入单元、consume_granularity、placeholder、session 边界和尾部残项处理已裁定 | PASS | evidence=[M1 §7](./langmem-current-product-identity-m1-ruling.md); ruling=session 粒度，assistant-first/same-role/singleton/odd tail 原序合法，不补 placeholder、不跨 session; next=none |
| B3-ISOLATION-CLEAN | 物理或逻辑隔离的写入、过滤、单空间删除和 clean-retry 等价性已证明 | PASS | evidence=[M2 §5](./langmem-m2-adapter-implementation.md); ruling=worker 内官方 namespace 约束 write/search；active→tombstone 的单空间 clean 可重试并复核为空，A 清理不影响 B；state 与 journal 同 namespace 原子提交; next=none |
| B3-PARALLEL-OWNERSHIP | process-global 缓存、client、DB、线程和 worker 所有权已审，W1/W2 资格有反例或实证 | PASS | evidence=[M2 §6](./langmem-m2-adapter-implementation.md); ruling=每个 isolated provider 独占 worker/event-loop/model/store/state root，W2 生产 runner 强反例验证两套 owner 与 cleanup；真实 W2 运行门仍由独立的 B11-PARALLEL-GATE 记录; next=none |
| B4-INPUT-VISIBILITY | role、speaker、content、turn/session time、place、image caption、source id 均沿算法可见链核实 | PASS | evidence=[五格 dossier §2-6](./langmem-five-benchmark-safety-dossier.md); ruling=canonical role/content 逐条进入 manager messages；LoCoMo speaker/caption、MemBench place/time、五格 source-time 与异常原序均锁强反例，source id/private gold 不进 prompt; next=none |
| B4-READOUT-COMPLETENESS | 产品答题前实际检索的全部记忆层、顺序和时间字段均进入 formatted_memory | PASS | evidence=[M2 §7](./langmem-m2-adapter-implementation.md); ruling=主产品唯一 readout 是 MemoryStoreManager.asearch current memories，key/content/score/order 全保留并 XML escape；zero hit 与 error 分离; next=none |
| B5-PROVENANCE | 当前检索条目的 semantic source lineage 资格按运行时事实判 valid、N/A 或 pending | N/A | evidence=[M1 §11](./langmem-current-product-identity-m1-ruling.md); ruling=current memory 经 old-memory search + LLM update/consolidation，无 lossless output-to-source mapping，source 参与关系不得冒充 semantic provenance; next=none |
| B5-RANKING-TOPK | 检索 item 粒度、top-k 总量或分路、dedup、rerank、稳定顺序和 NDCG 资格已锁 | PASS | evidence=[M2 §7](./langmem-m2-adapter-implementation.md); ruling=query.top_k 直达单路 product asearch，adapter 不重排；score/order 与 tie 插入序跨 snapshot 恢复，stable ranking valid；semantic provenance N/A 仍独立阻断 NDCG; next=none |
| B5-LOSSLESS-RETROFIT | provenance 与 HaluMem 缺口已评估直接支持、可无损观测改造或不可改造 | PASS | evidence=[M1 §11](./langmem-current-product-identity-m1-ruling.md); ruling=provenance 与 HaluMem extraction/type 不可无损改造故 N/A；update/QA 走 current state 产品接口直接支持候选; next=none |
| B6-FLUSH-COMPLETION | flush、update、summary、后台任务和“何时完成”的边界已接线并能传播失败 | PASS | evidence=[M2 §2、§5](./langmem-m2-adapter-implementation.md); ruling=async manager 等待 old-memory search、MemoryManager 与全部 store put/delete；返回后再原子提交 state；失败回滚，无 finalize/sleep/后台任务冒充完成; next=none |
| B7-OBSERVABILITY | build、retrieve、answer、judge 的 LLM、embedding、token、latency 和 scope 可观测 | PASS | evidence=[M2 §8](./langmem-m2-adapter-implementation.md); ruling=build 每次 response exact API usage；本地 embedding tokenizer+timer；retrieval 单独 stage；rehydration 不伪装业务 scope；answer/judge 走 framework；真实 artifact 由 B11 再开箱; next=none |
| B8-RETRIEVAL-SIDE-EFFECTS | 检索读副作用与污染写入已区分，算法固有状态变化不被误删 | PASS | evidence=[M1 §8-9](./langmem-current-product-identity-m1-ruling.md); ruling=retrieve 只调用 manager.asearch/BaseStore.asearch，query 不进入 manager.ainvoke、不触发 put/delete/LLM; next=none |
| B8-RESILIENCE-RESUME | 全部外部调用有 timeout、retry、失败语义、半写清理、安全 resume 与 secret 边界 | PASS | evidence=[M2 §5、§8](./langmem-m2-adapter-implementation.md); ruling=provider retry/timeout 显式；exact store+journal 原子提交、result-loss reuse、payload drift 拒绝、失败 rollback 与 tombstone clean 已证；worker env allowlist且错误脱敏; next=none |
| B9-MODEL-IDENTITY | build LLM、embedding、revision、dimension、normalization、distance 与本地模型身份已声明 | PASS | evidence=[M2 §3、§8](./langmem-m2-adapter-implementation.md); ruling=smoke deepseek-v4-flash/opencodego、full gpt-4o-mini/primary；MiniLM local path/dim384/external L2/InMemoryStore cosine 与 runtime locks 全进 identity; next=none |
| B10-TOML-MANIFEST | smoke 和 official_full 主配置、稀疏 author section、解析配置与 resume identity 已锁 | PASS | evidence=[M2 §3](./langmem-m2-adapter-implementation.md); ruling=两主 section 只切 API runtime/model 与 full worker 上限；完整 product/config/source/transport/embedding identity 进 manifest；官方 harness 为空故无 author section; next=none |
| B10-ANSWER-JUDGE-BUILDER | benchmark 主 builder 与作者完整 builder 的变量、messages、decoding、judge 和私有边界已核 | PASS | evidence=[五格 dossier §1-7](./langmem-five-benchmark-safety-dossier.md); ruling=LangMem 只提供 product memory；五格 answer/judge 均走 benchmark framework builder，官方无 author builder，private gold 仅 evaluator 可达; next=none |
| GRID-LOCOMO | 稳定异常、双 speaker、image、时间、最终 payload、检索指标、隐私与 smoke 独立闭合 | PASS | evidence=stable=[LoCoMo 稳定页](../../../../../../reference/integration/locomo.md) / payload=[dossier §2](./langmem-five-benchmark-safety-dossier.md#2-locomo) / metric=[dossier §7](./langmem-five-benchmark-safety-dossier.md#7-跨格-retrieval-evidence) / privacy=[dossier §2](./langmem-five-benchmark-safety-dossier.md#2-locomo) / smoke=[plan JSON](./langmem-smoke-plans-v1.json); ruling=固定 speaker 映射、真实名字/source time/caption，奇数尾无 placeholder，private gold 不进 method，retrieval metrics N/A; next=none |
| GRID-LONGMEMEVAL | 稳定异常、role 异形、时间、完整 haystack、最终 payload、检索指标、隐私与 smoke 独立闭合 | PASS | evidence=stable=[LongMemEval 稳定页](../../../../../../reference/integration/longmemeval.md) / payload=[dossier §3](./langmem-five-benchmark-safety-dossier.md#3-longmemeval) / metric=[dossier §7](./langmem-five-benchmark-safety-dossier.md#7-跨格-retrieval-evidence) / privacy=[dossier §3](./langmem-five-benchmark-safety-dossier.md#3-longmemeval) / smoke=[plan JSON](./langmem-smoke-plans-v1.json); ruling=完整 session 原序，assistant-first/same-role/singleton/odd tail 均不重配，question/gold 私有，Recall/NDCG N/A; next=none |
| GRID-MEMBENCH | first/third、尾部 time/place、missing-time noise、gold 异常、最终 payload、指标与 smoke 独立闭合 | PASS | evidence=stable=[MemBench 稳定页](../../../../../../reference/integration/membench.md) / payload=[dossier §4](./langmem-five-benchmark-safety-dossier.md#4-membench) / metric=[dossier §7](./langmem-five-benchmark-safety-dossier.md#7-跨格-retrieval-evidence) / privacy=[dossier §4](./langmem-five-benchmark-safety-dossier.md#4-membench) / smoke=[plan JSON](./langmem-smoke-plans-v1.json); ruling=First/Third role 保真，原文 place/time 不删不重复，100k missing time 不伪造，gold 异常只进 evaluator-private contract; next=none |
| GRID-BEAM | variant、时间、10M orphan/mismatch、最终 payload、abstention、指标与 smoke 独立闭合 | PASS | evidence=stable=[BEAM 稳定页](../../../../../../reference/integration/beam.md) / payload=[dossier §5](./langmem-five-benchmark-safety-dossier.md#5-beam) / metric=[dossier §7](./langmem-five-benchmark-safety-dossier.md#7-跨格-retrieval-evidence) / privacy=[dossier §5](./langmem-five-benchmark-safety-dossier.md#5-beam) / smoke=[plan JSON](./langmem-smoke-plans-v1.json); ruling=四 variant 复用 canonical id/role/order，10m orphan/mismatch 不位置配对，abstention 私有，recall N/A; next=none |
| GRID-HALUMEM | 固定 shape、session-local delta、四类 operation、最终 payload、指标、隐私与 W1 独立闭合 | PASS | evidence=stable=[HaluMem 稳定页](../../../../../../reference/integration/halumem.md) / payload=[dossier §6](./langmem-five-benchmark-safety-dossier.md#6-halumem) / metric=[dossier §6](./langmem-five-benchmark-safety-dossier.md#6-halumem) / privacy=[dossier §6](./langmem-five-benchmark-safety-dossier.md#6-halumem) / smoke=[plan JSON](./langmem-smoke-plans-v1.json) / operations=extraction N/A, update valid, QA valid, memory_type N/A; ruling=fixed 4-session/W1 shape，session 一次 async 完成；current state 可测 update/QA，changed puts 不冒充 extraction point; next=none |
| B11-DOSSIER | 一份 living dossier 已按五 benchmark 分章并链接承重 note、异常处置和失效触发器 | PASS | evidence=[LangMem 五格安全档案](./langmem-five-benchmark-safety-dossier.md); ruling=五格异常、payload、隐私、metric、计划与失效触发器在一份 living dossier 分章闭合; next=none |
| B11-SMOKE-PLAN | 每个 concrete variant 的 smoke-plan-v1 已无 API 生成、审阅并保存，命令未手写 | PASS | evidence=[20 份原始 machine plan](./langmem-smoke-plans-v1.json); ruling=9 个 croppable variant 各 W1/W2，2 个 HaluMem fixed variant 各 W1；全部由 registry/TOML 生成，child suffix 与 evaluator 清单未手改; next=none |
| B11-REAL-SMOKE | planner 生成的全部 predict 与适用 evaluator 已真实执行，固定 shape 未误传裁剪参数 | PENDING | evidence=用户已批准OpenCodeGo smoke; ruling=真实API可按已保存machine plan进入live队列，但尚无成功artifact; next=执行首份W1并开箱后再继续 |
| B11-ARTIFACT-GATE | manifest、prediction、formatted_memory、private labels、efficiency、state 与 summary 已逐 run 开箱 | PENDING | evidence=依赖真实 smoke; ruling=零报错不等于通过; next=真实 smoke 后开箱 |
| B11-PARALLEL-GATE | 每个适用 variant 的 W1/W2 已实测，或 W1-only 的产品硬约束和 CLI 预启动拒绝已证明 | PENDING | evidence=[W2 offline ownership](./langmem-m2-adapter-implementation.md#6-并行-ownership) / [20 plans](./langmem-smoke-plans-v1.json); ruling=离线 runner 已证两个独占 worker/model/store/state root，9 个 croppable variant 的真实 W1/W2 仍待 B11；HaluMem 固定 W1; next=用户批准后逐 plan 实测并开箱资源与隔离 |
| B11-REGRESSION-GATE | 定向强反例、全量 pytest、compileall、diff check 与第三方 patch identity 均通过 | PASS | evidence=[M2 §9](./langmem-m2-adapter-implementation.md#9-当前离线验证); ruling=扩展定向 473 passed，主树 2021 passed/3 deselected/13 个既有 warning/29 subtests，compileall、diff、ledger、plan JSON、nested source identity 与零 API product readout 全通过; next=none |
| B11-FREEZE-SYNC | frozen note、integration page、总表、workstream README、roadmap 和 ledger 状态已同步 | PENDING | evidence=未到冻结门; ruling=真实 B11 前不得冻结; next=完成其余全部检查点 |
<!-- ledger-checkpoints:end -->

## 架构师最终签字

- 当前 ledger 状态：`ready_for_smoke`
- 最后一次一手证据复核 commit：`56d85939d80bb731bd5e237567148d817d7bfd16`
- 当前事实边界：M1 source/product 与 M2 adapter/runtime/persistence/五格/metric/机器计划已闭合；
  真实 build/answer/judge smoke、artifact 开箱、真实 W1/W2 与 freeze sync 尚未执行。
- 架构师判词：`LANGMEM_M2_OFFLINE_ACCEPTED_B11_LIVE_QUEUED`。
