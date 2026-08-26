---
id: ws05
parent: null
status: in-progress
created: 2026-07-05
---
# ws05 全量实验申请材料与前置工程

## Codex 恢复胶囊（2026-08-27）

- **当前目标**：runtime/观测、十家参数/source/embedding provenance、isolation 并行门与 formal
  精确 cohort 选择已关闭；LightMem Mimo calibration 已在自适应样本门收口，当前唯一真实实验
  主线是 [SimpleMem Mimo calibration](branches/simplemem-mimo-calibration/README.md)。
  [QA task aggregation v3](branches/qa-task-aggregation/README.md) 的 taxonomy、
  answer-only abstention M0、BEAM 三档题分、题目级 pooled micro 与 M1 receipt/write surface 已
  实现；M2 paired bootstrap 仍等待更多 method 的 paired formal 结果，不抢跑。
- **当前批次**：
  [runtime 配置与观测 M0-M5](branches/runtime-config-and-observability/plan.md) 已完成无 API验收；
  [ws05.1 method profile provenance](../ws05.1-method-profile-provenance/README.md) 的 M0/M0.5、
  M1 LightMem、M2 A-Mem、M3 Mem0、M4 MemoryOS、M5 MemOS、M6 SimpleMem、M7 Letta、M8
  LangMem、M9 EverOS、M10 Graphiti OSS 与 M11 横向实现均已闭合；ws05.1 状态为 done。
- **当前判据**：[正式聚合合同](../../survey/qa-task-types/aggregation.md) 与可执行
  `qa-task-aggregation-v3`、`qa-cohort-receipt-v1` 已一致；旧 `v2-draft` 只读。真正 10×5
  `status=ok` receipt 完成前不得 formal 排名。Abstention v3 有意只测 fixed-reader answer，
  不宣称 retrieval boundary。
- **现场证据**：十家 method 主 TOML 已单源化，runtime/execution composition 进入严格 resume
  identity v2；九家 controlled MiniLM 锁同一组本地 bytes/tokenizer/runtime，Letta embedding=N/A；
  十家 source closure v2 与 EverOS effective strategy 均已闭合。M11 最终零 API 全量门为
  `2297 passed, 3 deselected, 25 warnings, 29 subtests passed`。M0-R2 承重集为
  `125 passed`；M1 同批已机械同步五份 ledger 的两条模板 requirement，定向 ledger+QA 门为
  `31 passed`，最终文档门为 `38 passed`；artifact 瘦身/分批 evaluator 合同后的 current 全量为
  `2358 passed, 3 deselected, 25 warnings, 29 subtests passed`；该 current 数包含 formal 精确
  isolation 选择与 Mimo calibration profile 的 CLI/config/十家 registry/full-scope 强反例。
  LightMem 最终 current 零 API门为 `2364 passed, 3 deselected, 25 warnings, 29 subtests passed`。
- **并行断点**：[开跑前 isolation 并行门](notes/2026-08-25-pre-experiment-parallelism-gate.md)
  已实现 HaluMem UUID 级稳定 worker lane、Letta 独立 product runtime、MemOS v6 独立
  runtime/embedder；W2 是最小竞态哨兵，不是能力天花板，显式 worker 接受任意正整数，实际
  数量由 selected isolation 与 execution/resource policy 控制。真实 LightMem HaluMem W10 run
  已证明 3 个 UUID 稳定分到独立 worker lane，UUID 内 session 顺序守恒。
- **禁止事项**：当前真实 API 授权只覆盖完成 LightMem 与 SimpleMem calibration；不得顺带启动
  其余八家、改写旧 artifact、把旧 embedding build 重标为新 controlled identity，或用 lineage
  伪造 metric 资格。
- **当前动作**：LightMem 最终五格累计 8,620,622 个 SDK `api_usage` tokens，conversation/question
  零失败；LoCoMo/LME/BEAM/HaluMem 停在 p25/p50/p75，MemBench 因四 lane 异质性补齐五点，详见
  [最终收据](branches/lightmem-mimo-calibration/notes/second-batch-receipt.md)。SimpleMem 逐字复用
  paired cohort：先做 Mimo streaming exact-usage 探针，再优先启动 HaluMem；任何成功 API LLM
  observation 若不是 `api_usage`，立即把 token receipt 标 incomplete，不能用估算补账。
  M11 前的 method state 不 resume；作者校准、Mimo calibration
  与主 controlled run 分开。

## 目标

在 ws02 smoke 矩阵完成后，组装与导师讨论全量实验的完整申请材料，并在预算
获批前完成全量运行的兜底工程验证。完成判据：申请材料（成本估算表 + 现有
结果汇总 + 实验方案）可直接用于导师讨论；兜底验证清单全绿后才允许启动全量。

## 当前断点

运行账：
[`ox 完整 isolation pilot 矩阵账`](notes/2026-08-21-ox-complete-isolation-pilot-ledger.md)。

- 2026-08-27：LightMem Mimo calibration 在自适应停表点完成。四个普通 benchmark 各三个完整
  isolation；MemBench 基于 lane 内 1.6×–5.2× 的三点差异条件补齐四 lane 五点；最终五格累计
  8,620,622 个真实 SDK `api_usage` tokens。下一家 SimpleMem 使用同一 paired cohort，HaluMem
  先启动；目标模型经费优先覆盖 LightMem/SimpleMem 等效率候选，其余方法允许低价 token 外推，
  但不得外推分数或速度。
- 2026-08-26：用户最终确认 QA v3：固定题池逐题一票，不再五 benchmark 等权；update、HaluMem
  错误前提、BEAM 历史内部矛盾拆分；personalization/instruction 分开；lowlevel_rec 归事实回顾，
  noisy 与 LoCoMo category 5 排除；abstention M0 只看 fixed answer LLM；BEAM 十类均可进入聚合，
  普通题与 event ordering 使用标准化三档 credit，后者由有序整题 rubric judge 同时检查内容和
  顺序，native F1/tau/rubric 继续并列报告。入口见
  [aggregation.md](../../survey/qa-task-types/aggregation.md)。
- 2026-08-26：用户纠正了 M0-R1 的两个越权收口：① boundary 若评测 memory module，检索出
  无关记忆即失败，不能只靠 reader 最终拒答；②交付物应为五份独立 benchmark task 文档 + 一份
  聚合讨论稿，先审阅讨论、再定正式合同。current artifact 又把 `items=None` 与 `items=()` 都写成
  `[]`，retrieval-boundary metric 在修可观测性前不可可靠复算。入口见
  [`qa-task-types/README.md`](../../survey/qa-task-types/README.md)。
- 2026-08-25：用户提出成本校准应先按 public input shape 选择有代表性的完整 isolation，以每次
  一个未完成 isolation 的预算运行，并在同一 run 上 resume，兼顾成本外推与真实续跑验收；实际
  provider/model 在 API 前另行指定。架构核对确认内部字段仍为 `max_new_conversations`，当前正式
  CLI 名为 `--conversation-budget`；它只按数据顺序取下一个未完成 isolation，不会自动选中位样本。
  `predict pilot` 又在 dataset prepare 阶段只保留第一 isolation，无法继续到余量。因此下一步先
  裁定代表样本的无 gold 选择规则及可续跑 calibration scope，不复用旧 run、不调用 API。
- 2026-08-25：分批语义进一步对齐为 `1 + 2 (+ 2)`：十家×五格先各推进 1 个完整
  isolation，全部通过后对同一 run `--resume --conversation-budget 2`，即再推进 2 个、累计 3 个；
  若实测方差仍大，再增量 2 个到累计 5 个，不在开跑前盲目扩全矩阵。
  `max_workers` 是 manifest/resume identity，因此任一 run 必须首批就锁定后续实际使用的 worker
  数，resume 不得改。W2 只是最小并发哨兵，不是 method 能力上限；样本候选集须在首批前由
  公开输入形状一次锁定，
  不用 gold/答案/method 输出选样；这样后续增量才不改变实验人群或 resume identity。
- 2026-08-26：用户裁定不在开跑前重构 `max_workers` 与 `worker_N` 状态所有权；该工程债不影响
  固定 worker identity 的当前实验。框架复用既有 `PredictionRunPolicy.conversation_ids`，新增 formal-only
  可重复 `--isolation-id`，把代表 cohort 的选择从隐式 dataset 顺序升级为显式、可审计、严格 resume
  identity；`--conversation-budget` 仍是可变的单次推进预算。本批零 API，不改变 runner、provider 或
  method 算法。
- 2026-08-26：用户选择本轮 LightMem 五格使用 `.env` 第三槽 `mimo-v2.5`、禁用 thinking、
  `workers=10`。新增独立 `calibration` runtime/execution profile，不改 `smoke` ox 或
  `official_full` GPT-4o-mini；method `[method]` 与 benchmark answer resolver 原样复用。cohort 在首轮
  manifest 即锁 5 个代表 isolation（MemBench 每 lane 5 个、轮次交错），首批实际推进 1 或 4，保留
  `1+2(+2)` / `4+8(+8)` resume 能力。首批 prediction 已于 2026-08-26 完成；该运行身份只用于
  calibration，不与 `official_full` 分数混用。
- W1/W2/W10 只是单个 run 的 isolation worker 数示例，不是 method 内部算法并行。HaluMem 已改为
  UUID 级 worker lane，UUID 内 session 顺序不变；Letta 与 MemOS 也使用每 worker 独立 runtime，
  不再需要另造“W1 child run + artifact 合并”旁路。execution profile 的 W1/W10 是默认值，
  显式 `--workers` 没有伪造的 2/10 method 上限；正式大规模前仍需全局 API/本地资源 admission
  control，不能因参数可填任意正整数就同时盲放 50 格。

- 2026-08-21：用户明确恢复 ws05，并授权用 `.env` 第四槽限时免费
  `opencodego/ox-alpha-free` 做真实兼容性、效率观测和受控扩大范围测试。直接 OpenAI SDK
  探针已经证明：禁用 thinking（含错误尝试的 low thinking body）返回 HTTP 400；改用顶层
  `reasoning_effort="low"` 后普通 answer、JSON judge、LongMemEval yes/no 三种生产形状均
  HTTP 200 且携带精确 usage。并发阶梯 4/4、8/8 传输成功，因此只证明当前端点的安全
  **下界 ≥8**，没有 rate-limit header，不能宣称已知最大并发。首批矩阵 pilot 采用全局 API
  semaphore=4 留余量；先完成十家真实调用面的 model-aware transport 与一条 framework
  efficiency artifact 门，再分批运行，不同时放飞 50 格。该模型只用于流通/调用拓扑/成本
  observation，不与正式分数对比；`official_full` 仍为 `primary/gpt-4o-mini`。
- 2026-08-24：用户在扩大 pilot 前重开配置与观测审计，真实 pilot 再次暂停。当前支线为
  [runtime config/observability](branches/runtime-config-and-observability/README.md)：主比较统一
  MiniLM-384 仅覆盖真实消费 embedding 的兼容方法；Letta official SDK 的“省略 embedding”与
  framework 显式 `None` 已拆开记账；效率失败成本与四家 HaluMem extraction 候选进入 M2/M3。
- 2026-08-24：上述支线完成后，用户追加“参数值与作者 prompt provenance”门。现有十家主
  TOML 已完成所有权单源化，但不等于每个开关/高影响数值都已证明符合完整算法；
  `prompts/author/` 目前只有三家代码资产，也不等于其余七家没有官方评测 prompt。ws05.1 将
  逐家复用已有 integration/note 后补 current-source 一手证据，避免重复调查；真实 pilot 继续
  暂停。
- 2026-08-25：ws05.1 M11 已关闭。九家 embedding consumer 使用内容锁定的项目本地 MiniLM，
  Letta 为 N/A；十家 registered source 改用分组件 closure v2；dead/hidden config 已按 final
  consumer 修正，零 author profile 通过完整就绪门。新 identity 与旧 artifact 严格失配，下一轮
  pilot 全部 fresh-state。实施收据见
  [`M11 implementation`](../ws05.1-method-profile-provenance/notes/m11-effective-config-source-embedding-implementation.md)。

### M11 后重建矩阵

| 范围 | 下一轮 pilot | 历史 artifact |
|---|---|---|
| LightMem、A-Mem、Mem0、MemoryOS、MemOS、SimpleMem、LangMem、EverOS、Graphiti | embedding artifact v2 + source closure v2，全部 fresh-state | 只按原 manifest 回读，不重标、不 resume |
| Letta | source closure v2，fresh-state；embedding 继续 N/A | 只读，不补 MiniLM 身份 |
| EverOS 特别项 | v8 effective strategy 与 controlled MiniLM 必须用新 run-id 实跑 | 旧 v6/v7 只证明当时 profile |
| author calibration | 当前不运行；逐格 source/data/builder/decode/parser 全闭合后另批批准 | 不拿历史主表 run 冒充 author parity |
- 2026-08-21：新增 `RunScope.PILOT`。它复用 TOML `[smoke]` 的 method 参数与 ox runtime，
  但保留一个完整 isolation 及全部问题、写独立 `pilot/` 目录并进入 manifest identity。
  LoCoMo/LME/BEAM/HaluMem 各取第一完整 conversation/instance/conversation/UUID；MemBench
  在一个 run 中从四条默认 source lane 各取第一完整 tid。它解决“smoke 会裁剪、formal 会换回
  primary”的身份矛盾，不新增第三套算法参数。
- 2026-08-14：用户明确暂缓“每个 benchmark 跑隔离空间再外推”的成本 pilot，先执行
  ws03 maintainability M1。该暂停已由上条用户授权取代；旧 smoke/artifact 仍不得改写或
  静默 resume，所有 ox pilot 使用新 run identity。
- 2026-07-05：依赖 ws02 矩阵产出，暂不开工。本 workstream 从旧
  "experiment-reporting" 口径重构而来：成本估算不再是一次性报告任务，而是
  ws02 每个格子的标准产出；本 ws 负责"组装申请材料 + 全量前置工程"。

## 任务清单

### 开跑前 QA 聚合合同

- [x] QA task taxonomy/score/weight v3 已获用户确认并落稳定合同。
- [x] M0-R2 把旧 benchmark-equal `v2-draft` 内核升级为题目级 pooled-micro 可执行合同。
- [x] M1 实现显式 cohort identity receipt 与 JSON/Markdown report 写出面。
- [ ] 首批 formal 后生成真正 10×5 receipt；再做 isolation-level paired bootstrap 与完整报告面。

### 申请材料（依赖 ws02）

- [ ] 全矩阵成本估算表：基于各格子 smoke/pilot 的 token/latency observation，
  按 ohmygpt 实价离线计算（`memory_benchmark.analysis`；严格区分
  api_usage / method_native / tokenizer_estimate）；给出分 benchmark、
  分 method 的全量费用与时间预估区间。
- [ ] 目标模型经费分层：低价 calibration 必须保存逐 method/benchmark/stage 的真实
  `api_usage` 与失败尝试；按运行时点目标模型价格离线外推。GPT-4o-mini 经费优先用于
  LightMem、SimpleMem 及后续由 observation 证明效率较高的方法；A-Mem 等高调用方法允许只给
  低价模型 token 外推，但报告必须标明“非目标模型实测”，不能外推分数或速度。
- [ ] 自适应样本门：方法间复用同一 public-shape paired cohort；LoCoMo/LME 等先以
  p25/p50/p75 三个完整 isolation 形成首轮外推，MemBench 至少四 lane×三条。只有 shape/token/
  runtime 敏感性足以影响预算决策时才补 p10/p90，不机械要求每个 benchmark 同样 n。
- [ ] API token 完整性门：计费表只纳入 SDK response 的 `api_usage`；任何成功 API LLM call
  缺 usage 都标 incomplete，不用 tokenizer estimate 回填。本地 embedding estimate 单独报告。
- [ ] `ox-alpha-free` transport/efficiency 资格门：十家 build LLM + framework answer/judge
  均使用 model-aware 请求参数；最小真实 run 的 prediction efficiency artifact 含非空
  API usage、model identity 与 latency；旧 Mimo artifact 精确回读不退化。
- [ ] 现有结果汇总：LoCoMo 4-method full（历史口径，注明将重跑）、
  LongMemEval 1-conv pilot judge 结果；区分历史 run 与新架构 run。
- [ ] 全量实验方案：规模选项（如 LongMemEval 5/10/500 conv 梯度）、
  分批 resume 策略、run_id 规划，供导师选择。

### 全量前置兜底工程（预算获批前完成验证）

- [ ] 失败恢复演练：模拟中断后同 run_id resume，不从零开始、不重复计费。
- [ ] 防 API 空烧复验：连续失败熔断（max_consecutive_failures）、
  failed conversation 默认隔离、`--retry-failed` clean state 在真实网络
  故障场景下的行为验证。
- [ ] 断网/限流韧性测试（timeout/retry 兜底已实现，未做真实故障注入）。

### 5×10 容量与共享资源治理（正式并发前；当前只登记，不开工）

目标不是先造“全局单例容器”，而是先找出实际 RSS、CPU/GPU、I/O 与外部服务瓶颈，再只共享
被证明 immutable、同 identity 且并发安全的资源。OmniMemEval 等第三方框架可作工程比较样本，
不能替代本项目的算法身份、隔离与 artifact 判据。

- [ ] **基线剖析**：对单 run、同 benchmark 多 method、跨 benchmark 并发分别记录 process tree、
  RSS/PSS、page cache、dataset decode 次数、本地 model 实例数、GPU/CPU utilization、DB/HTTP
  connection 数、queue depth 与吞吐；没有测量前不宣称“重复加载”是主瓶颈。
- [ ] **dataset 共享边界**：区分 OS page cache、mmap/Arrow 只读页、Python materialized object 与
  每题 private labels；候选共享仅限不可变 source/index，conversation crop、gold/private view 和
  iterator cursor 必须 run-local。优先消除重复 decode/copy，而不是为省一份小对象引入跨 run
  可变状态。
- [ ] **embedding/model 服务边界**：只有 model/provider/revision/dimension/normalization/
  instruction/device 完全同 identity，且 tokenizer/model backend 已证明 thread/process safe 时，
  才允许同进程复用或建立带 batching/backpressure 的本地服务。十家 method 并不天然使用同一
  embedding；统一模型本身是研究配置裁决，不能由性能层暗改。
- [ ] **禁止盲目 singleton 的对象**：method memory/state、conversation namespace、mutable vector/
  graph store、transaction、scheduler/lifecycle、非线程安全 tokenizer/client 均保持隔离；连接池
  可以共享 transport，不等于共享业务状态。Spring Bean 的复用思想只适用于明确 stateless 或
  受控生命周期对象，不能照搬成“一类只建一个实例”。
- [ ] **资源调度器**：按 local embedding、GPU model、Docker/DB、API-only、isolated-runtime 等资源类给
  run 建 semaphore/配额与 admission control；5×10 是实验矩阵，不代表同时放行 50 个进程。
  支持 bounded queue、背压、优雅取消、per-run timeout 与失败隔离。
- [ ] **验收指标**：相同 run identity 下 payload/artifact/score 字节或语义守恒；峰值 RSS、模型
  副本数、重复 decode、吞吐与故障影响面有前后对照；优化失败可回退，不把缓存命中变成新的
  correctness 前提。

### 每周导师汇报支持（常态）

- [ ] 每周从 roadmap/workstream 状态生成进度简报素材（放 `reports/`）。

## 决策记录

- 2026-07-05 用户：先 smoke 矩阵攒成本表 → 导师批预算 → 才跑全量；
  全量前兜底机制必须做好，不能中途失败从零开始或 API 空烧。
- 2026-08-26 用户：目标模型预算可能不足以覆盖十家 full；先用低价模型精确记录 token，
  正式经费优先覆盖效率较高的方法，其余只做带假设与身份披露的成本外推。
- 2026-08-27 用户：预算样本量不再一刀切；低异质 benchmark 先跑三个代表 isolation，分布不均或
  多 source 的 benchmark 分层追加。多 method 调度先启动 HaluMem 等最长关键路径，再并行填短 run；
  API token 只接受 OpenAI-compatible SDK 返回的真实 usage。
- 既定：真实费用按 ohmygpt 实价离线算，不用 OpenAI 官方价做结论。
