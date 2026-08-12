# Letta/MemGPT Method Integration Ledger v1

> 本账在任何 adapter 代码之前创建。当前只登记已知边界与下一取证动作，**不把旧 MemGPT
> 印象、README 宣传或其他 method 判例冒充 Letta current source 事实**。完整判据见
> [Method 接入标准清单](../../../../../../reference/method-integration-checklist.md)。

<!-- method-integration-ledger
contract_version: method-integration-ledger-v1
method_id: letta
display_name: Letta/MemGPT
ledger_state: frozen
integration_page: docs/reference/integration/letta.md
dossier: docs/workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-five-benchmark-safety-dossier.md
frozen_note: docs/workstreams/ws02.7-method-track/branches/method-recertification/letta/notes/letta-frozen-v1.md
-->

## 必填检查点

<!-- ledger-checkpoints:start -->
| ID | 完成判据 | Status | 证据、裁决与下一动作 |
| --- | --- | --- | --- |
| B0-OFFICIAL-BENCHMARKS | 当前官方 repo 实际跑过的 benchmark、入口和版本已穷举，未跑过者标 framework extension | PASS | evidence=[M1 §2-3](./letta-current-product-identity-m1-ruling.md); ruling=六个 current official repo 对 Phase 1 五 benchmark 均无 harness，五格统一标 framework extension，旧 paper/第三方 MemoryData 不冒充 current harness; next=none |
| B0-FINAL-PAYLOAD | 每个官方 harness 展开后的 add 次数、batch、role、namespace、时间、模型参数和 search 最终 payload 已锁 | N/A | evidence=[M1 §3-4](./letta-current-product-identity-m1-ruling.md); ruling=Phase 1 官方 harness 集为空，故不存在 author benchmark payload；另已锁 official ai-memory-sdk 产品 payload 供 framework extension 设计; next=none |
| B0-DIFFERENCE-RULING | 主轨、author 轨、framework extension、upstream bug 的每项差异已唯一归类 | PASS | evidence=[M1 §1、§3、§5](./letta-current-product-identity-m1-ruling.md); ruling=五格主轨是 product-faithful framework extension；Letta Code 是 ALGORITHM_VARIANT；direct archival 是 MECHANISM_BYPASS；当前无 author 轨; next=none |
| B1-SOURCE-LOCK | 官方 repo、tag、commit、license、vendored 路径、patch 和更新策略已锁定 | PASS | evidence=[M1 §2](./letta-current-product-identity-m1-ruling.md); ruling=Apache-2.0 legacy Letta 0.16.8 product core，保留本地 b76da909 pin；ai-memory-sdk v0.2.0 锁产品契约；只以 product diff 触发重开; next=none |
| B1-PRODUCT-SURFACE | ingest/retrieve 采用通用产品接口，并解释为何不用 chat、ask、eval、cloud 或 HTTP 专用入口 | PASS | evidence=[M1 §4-5](./letta-current-product-identity-m1-ruling.md); ruling=in-process V1 core 复现 official sleeptime-memory call graph，等终态后读全部 core blocks；不用 HTTP/cloud、answer loop 或 direct archival bypass; next=none |
| B1-LIFECYCLE-CALLGRAPH | prepare、ingest、retrieve、finalize、cleanup 的 runner 真实调用点和早失败路径已逐一闭合 | PASS | evidence=[M2 §2、§6](./letta-m2-adapter-implementation.md); ruling=generic 与 operation runner 有工作项时 prepare 一次；协议/粒度先验、ingest/readout、failed clean 与 cleanup 路径均有强反例；isolated worker 收真实 RunContext; next=none |
| B2-GRANULARITY | 原生输入单元、consume_granularity、placeholder、session 边界和尾部残项处理已裁定 | PASS | evidence=[M2 §4](./letta-m2-adapter-implementation.md); ruling=session 粒度，当前 session 内最多 10 message 一批，尾 singleton 合法，不跨 session、不补 placeholder、不重配 role; next=none |
| B3-ISOLATION-CLEAN | 物理或逻辑隔离的写入、过滤、单空间删除和 clean-retry 等价性已证明 | PASS | evidence=[M2 §3.4、§6](./letta-m2-adapter-implementation.md); ruling=一个 isolation 一个 tagged subject/agent，sidecar 验证 agent/block/archive；clean 拒删 shared owner 并反查 subject 消失后才删 sidecar; next=none |
| B3-PARALLEL-OWNERSHIP | process-global 缓存、client、DB、线程和 worker 所有权已审，W1/W2 资格有反例或实证 | PASS | evidence=[M2 §6.2](./letta-m2-adapter-implementation.md); ruling=worker/DB/volume 均归单 storage root，但跨 worker DB ownership 尚无产品实证，故主 profile W1-only；TOML/registry/planner 在资源启动前拒绝 W2，未来只有独立专项可重开; next=none |
| B4-INPUT-VISIBILITY | role、speaker、content、turn/session time、place、image caption、source id 均沿算法可见链核实 | PASS | evidence=[五格 dossier §2-6](./letta-five-benchmark-safety-dossier.md); ruling=role/content 进入 official wrapper；speaker/time/place/caption 按五格裁决保真，source id 不进入产品 prompt且不伪造 lineage; next=none |
| B4-READOUT-COMPLETENESS | 产品答题前实际检索的全部记忆层、顺序和时间字段均进入 formatted_memory | PASS | evidence=[M2 §3.3、§5](./letta-m2-adapter-implementation.md); ruling=主产品可见记忆是全部 attached public core blocks，按(label,id)稳定展示；archival 未写入且不偷读，query 不进 method; next=none |
| B5-PROVENANCE | 当前检索条目的 semantic source lineage 资格按运行时事实判 valid、N/A 或 pending | N/A | evidence=[M2 §5](./letta-m2-adapter-implementation.md); ruling=持续演化 blocks 无法无损拆回 source gold unit，items=None、granularity=none、semantic provenance=N/A; next=none |
| B5-RANKING-TOPK | 检索 item 粒度、top-k 总量或分路、dedup、rerank、稳定顺序和 NDCG 资格已锁 | N/A | evidence=[M2 §5](./letta-m2-adapter-implementation.md); ruling=产品返回全部 blocks，不消费 query/top-k、不形成 relevance ranking；stable ranking 与 NDCG 均 N/A; next=none |
| B5-LOSSLESS-RETROFIT | provenance 与 HaluMem 缺口已评估直接支持、可无损观测改造或不可改造 | PASS | evidence=[M2 §5](./letta-m2-adapter-implementation.md); ruling=为 blocks 附参与 source id 仍不能证明当前语义承载，故 retrieval/extraction 不改造；HaluMem current-state update 与 QA 直接支持，memory-type N/A; next=none |
| B6-FLUSH-COMPLETION | flush、update、summary、后台任务和“何时完成”的边界已接线并能传播失败 | PASS | evidence=[M2 §2、§6](./letta-m2-adapter-implementation.md); ruling=每批直接等待 AgentLoop.step terminal；stop reason、step count、usage 任一异常均失败，没有额外后台 build 被假定完成; next=none |
| B7-OBSERVABILITY | build、retrieve、answer、judge 的 LLM、embedding、token、latency 和 scope 可观测 | PASS | evidence=[M2 §7](./letta-m2-adapter-implementation.md); ruling=build 从每次 provider response 取 exact usage，retrieve 只读 wall-clock 且无 embedding；answer/judge 复用 framework 观测；worker helper 强反例覆盖两种 usage 字段，真实 artifact 由 B11 独立验收; next=none |
| B8-RETRIEVAL-SIDE-EFFECTS | 检索读副作用与污染写入已区分，算法固有状态变化不被误删 | PASS | evidence=[M2 §3.3](./letta-m2-adapter-implementation.md); ruling=retrieve 仅 block_manager 读取，不把 query 交给 agent、不写 messages/passages/blocks; next=none |
| B8-RESILIENCE-RESUME | 全部外部调用有 timeout、retry、失败语义、半写清理、安全 resume 与 secret 边界 | PASS | evidence=[M2 §6](./letta-m2-adapter-implementation.md) / [B11-R1 §3-4](./letta-b11-first-live-attempt-r1.md); ruling=DB readiness 改为最终 TCP SQL 查询，拒绝初始化临时 Unix server 假就绪；worker request/provider retry 受控，official Run 先创建、step 携 id、成功/失败均终态化；两阶段 journal 拒绝 ambiguous replay；clean namespace-safe；worker env allowlist且错误脱敏; next=none |
| B9-MODEL-IDENTITY | build LLM、embedding、revision、dimension、normalization、distance 与本地模型身份已声明 | PASS | evidence=[M2 §7](./letta-m2-adapter-implementation.md); ruling=smoke deepseek-v4-flash/opencodego，official_full gpt-4o-mini/primary；embedding 明确 N/A/None，不虚构 dimension/distance; next=none |
| B10-TOML-MANIFEST | smoke 和 official_full 主配置、稀疏 author section、解析配置与 resume identity 已锁 | PASS | evidence=[M2 §7、§9](./letta-m2-adapter-implementation.md); ruling=两主 section 只切 API runtime/model；adapter/source/wrapper/transport/config 全进 identity；五格无官方 harness故无 author section; next=none |
| B10-ANSWER-JUDGE-BUILDER | benchmark 主 builder 与作者完整 builder 的变量、messages、decoding、judge 和私有边界已核 | PASS | evidence=[五格 dossier §1-7](./letta-five-benchmark-safety-dossier.md); ruling=五格一律 framework benchmark unified answer/judge builder；Letta 不回答问题且无 author builder，private gold 只在 evaluator 侧; next=none |
| GRID-LOCOMO | 稳定异常、双 speaker、image、时间、最终 payload、检索指标、隐私与 smoke 独立闭合 | PASS | evidence=stable=[LoCoMo 稳定页](../../../../../../reference/integration/locomo.md) / payload=[dossier §2](./letta-five-benchmark-safety-dossier.md#2-locomo) / metric=[dossier §7](./letta-five-benchmark-safety-dossier.md#7-跨格-metric-与-artifact-规则) / privacy=[dossier §2](./letta-five-benchmark-safety-dossier.md#2-locomo) / smoke=[frozen §3](./letta-frozen-v1.md#3-五-benchmark-主轨与真实-smoke); ruling=固定 speaker_a→user、speaker_b→assistant，保留 speaker/time/caption，未知 speaker 拒绝，gold evidence 不进 method，retrieval metrics N/A; next=none |
| GRID-LONGMEMEVAL | 稳定异常、role 异形、时间、完整 haystack、最终 payload、检索指标、隐私与 smoke 独立闭合 | PASS | evidence=stable=[LongMemEval 稳定页](../../../../../../reference/integration/longmemeval.md) / payload=[dossier §3](./letta-five-benchmark-safety-dossier.md#3-longmemeval) / metric=[dossier §7](./letta-five-benchmark-safety-dossier.md#7-跨格-metric-与-artifact-规则) / privacy=[dossier §3](./letta-five-benchmark-safety-dossier.md#3-longmemeval) / smoke=[frozen §3](./letta-frozen-v1.md#3-五-benchmark-主轨与真实-smoke); ruling=assistant-first、连续同 role、singleton 与奇数尾保持原序，session 内分批但不重配，question/gold 私有，Recall/NDCG N/A; next=none |
| GRID-MEMBENCH | first/third、尾部 time/place、missing-time noise、gold 异常、最终 payload、指标与 smoke 独立闭合 | PASS | evidence=stable=[MemBench 稳定页](../../../../../../reference/integration/membench.md) / payload=[dossier §4](./letta-five-benchmark-safety-dossier.md#4-membench) / metric=[dossier §7](./letta-five-benchmark-safety-dossier.md#7-跨格-metric-与-artifact-规则) / privacy=[dossier §4](./letta-five-benchmark-safety-dossier.md#4-membench) / smoke=[frozen §3](./letta-frozen-v1.md#3-五-benchmark-主轨与真实-smoke); ruling=FirstAgent child role 与 ThirdAgent user-only 均保真，尾部 place/time 不重复，100k missing time 不伪造，gold 异常只进 evaluator-private contract; next=none |
| GRID-BEAM | variant、时间、10M orphan/mismatch、最终 payload、abstention、指标与 smoke 独立闭合 | PASS | evidence=stable=[BEAM 稳定页](../../../../../../reference/integration/beam.md) / payload=[dossier §5](./letta-five-benchmark-safety-dossier.md#5-beam) / metric=[dossier §7](./letta-five-benchmark-safety-dossier.md#7-跨格-metric-与-artifact-规则) / privacy=[dossier §5](./letta-five-benchmark-safety-dossier.md#5-beam) / smoke=[frozen §3](./letta-frozen-v1.md#3-五-benchmark-主轨与真实-smoke); ruling=四 variant 均复用 canonical id/role/order，10m orphan/mismatch 不补写或位置重配，abstention 私有，beam-recall N/A; next=none |
| GRID-HALUMEM | 固定 shape、session-local delta、四类 operation、最终 payload、指标、隐私与 W1 独立闭合 | PASS | evidence=stable=[HaluMem 稳定页](../../../../../../reference/integration/halumem.md) / payload=[dossier §6](./letta-five-benchmark-safety-dossier.md#6-halumem) / metric=[dossier §6.2](./letta-five-benchmark-safety-dossier.md#62-letta-四类-operation) / privacy=[dossier §6](./letta-five-benchmark-safety-dossier.md#6-halumem) / smoke=[frozen §3](./letta-frozen-v1.md#3-五-benchmark-主轨与真实-smoke) / operations=extraction N/A, update valid, QA valid, memory_type N/A; ruling=fixed 4-session operation 顺序保持，session report 缺失只阻塞 extraction，current-state readout 可测 update/QA，private memory point 不进 build; next=none |
| B11-DOSSIER | 一份 living dossier 已按五 benchmark 分章并链接承重 note、异常处置和失效触发器 | PASS | evidence=[Letta 五格安全档案](./letta-five-benchmark-safety-dossier.md); ruling=五格异常、payload、隐私、metric、机器计划与失效触发器均在同一 living dossier 分章闭合; next=none |
| B11-SMOKE-PLAN | 每个 concrete variant 的 smoke-plan-v1 已无 API 生成、审阅并保存，命令未手写 | PASS | evidence=[11 份 current machine plan](./letta-smoke-plans-v3.json); ruling=LoCoMo 1、LongMemEval 2、MemBench 2、BEAM 4、HaluMem 2 全部由 current registry/TOML 生成；逐字执行 argv，multi-variant 后缀与 HaluMem fixed shape 均由 planner 管理; next=none |
| B11-REAL-SMOKE | planner 生成的全部 predict 与适用 evaluator 已真实执行，固定 shape 未误传裁剪参数 | PASS | evidence=[frozen §3-4](./letta-frozen-v1.md#3-五-benchmark-主轨与真实-smoke); ruling=current v3 的 11 run、17 conversation/question 与全部适用 evaluator 已完成；旧失败 smoke 不 resume、不混入 current 身份; next=none |
| B11-ARTIFACT-GATE | manifest、prediction、formatted_memory、private labels、efficiency、state 与 summary 已逐 run 开箱 | PASS | evidence=[frozen §4](./letta-frozen-v1.md#4-artifact效率隐私与外部状态机器门); ruling=11 roots 的 manifest、question/prediction/context、N/A、summary、API observation、operation sidecar、日志和 30 个 owned volume 账机器闭合，secret/endpoint/private URL 命中为零; next=none |
| B11-PARALLEL-GATE | 每个适用 variant 的 W1/W2 已实测，或 W1-only 的产品硬约束和 CLI 预启动拒绝已证明 | N/A | evidence=[dossier §1、§8](./letta-five-benchmark-safety-dossier.md); ruling=跨 worker 共享数据库 ownership 未获产品证明，主 profile 明确 W1-only；TOML、registry、planner 在 runtime/API 前拒绝 W2，不以复制 runtime 偷换实现; next=none |
| B11-REGRESSION-GATE | 定向强反例、全量 pytest、compileall、diff check 与第三方 patch identity 均通过 | PASS | evidence=[frozen §7](./letta-frozen-v1.md#7-最终验收门); ruling=current Letta/runner/prompt 定向 240 passed；冻结同批的 ledger/doc、全量、compileall 与 diff 门见 frozen 现场记录; next=none |
| B11-FREEZE-SYNC | frozen note、integration page、总表、workstream README、roadmap 和 ledger 状态已同步 | PASS | evidence=[frozen-v1](./letta-frozen-v1.md); ruling=ledger、frozen note、稳定 integration、总表、method branch、父 workstream 与 roadmap 同批同步为 method-frozen-v1; next=none |
<!-- ledger-checkpoints:end -->

## 架构师签字

- 当前 ledger 状态：`frozen`
- 当前事实边界：M1/M2、11 份 current v3 真实 smoke、artifact/效率/隐私/外部状态机器门与最终
  回归全部闭合；W2、source-exact retrieval metric、HaluMem extraction/memory-type 诚实 N/A。
- 架构师判词：`LETTA_METHOD_FROZEN_V1`。
