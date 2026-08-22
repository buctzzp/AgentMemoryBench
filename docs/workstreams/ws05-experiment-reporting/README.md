---
id: ws05
parent: null
status: in-progress
created: 2026-07-05
---
# ws05 全量实验申请材料与前置工程

## Codex 恢复胶囊（2026-08-21）

- **当前目标**：用限时免费的 `opencodego/ox-alpha-free` 完成 ws05 transport、效率
  observation 与受控矩阵 pilot；它不进入正式效果主表。
- **当前批次**：先压绿十家 model-aware transport、manifest/resume 与无 API 回归；随后按
  全局 API 并发上限 4 分批运行一 isolation pilot，不同时放飞 50 格。
- **当前判据**：[API runtime profile](../../reference/api-runtime-profiles.md)；顶层
  `reasoning_effort="low"` 是 ox 的唯一已验证请求形状，旧模型 slot 只供历史 artifact 精确回读。
- **现场证据**：直接 SDK 普通 answer、JSON judge、LongMemEval yes/no 与 streaming usage
  均通过；4/4 与 8/8 并发传输成功只证明安全下界 ≥8。Mem0、A-Mem、SimpleMem 的极小
  真实 run 已分别闭合 build/answer/judge 或 streaming exact-usage；无 API 全量门为
  `2238 passed, 3 deselected, 25 warnings, 29 subtests passed`。
- **禁止事项**：不得把 ox 分数与 `official_full` 比较；不得复用旧 smoke run_id 或对 smoke
  做 resume；不得把 key/base URL 写入 artifact；未过回归门前不得扩大矩阵。
- **当前动作**：公开 `predict pilot` 已实现并锁定五家完整 isolation 形状；EverOS × BEAM
  资格格的 prediction、两项 evaluator、exact usage 与 secret/base-URL 负空间门已全部通过。
  当前以 Mem0 + MemoryOS 两格并行进入第一扩大波；全局 API 并发上限仍为 4，重型 runtime
  进一步降并发。

## 目标

在 ws02 smoke 矩阵完成后，组装与导师讨论全量实验的完整申请材料，并在预算
获批前完成全量运行的兜底工程验证。完成判据：申请材料（成本估算表 + 现有
结果汇总 + 实验方案）可直接用于导师讨论；兜底验证清单全绿后才允许启动全量。

## 当前断点

运行账：
[`ox 完整 isolation pilot 矩阵账`](notes/2026-08-21-ox-complete-isolation-pilot-ledger.md)。

- 2026-08-21：用户明确恢复 ws05，并授权用 `.env` 第四槽限时免费
  `opencodego/ox-alpha-free` 做真实兼容性、效率观测和受控扩大范围测试。直接 OpenAI SDK
  探针已经证明：禁用 thinking（含错误尝试的 low thinking body）返回 HTTP 400；改用顶层
  `reasoning_effort="low"` 后普通 answer、JSON judge、LongMemEval yes/no 三种生产形状均
  HTTP 200 且携带精确 usage。并发阶梯 4/4、8/8 传输成功，因此只证明当前端点的安全
  **下界 ≥8**，没有 rate-limit header，不能宣称已知最大并发。首批矩阵 pilot 采用全局 API
  semaphore=4 留余量；先完成十家真实调用面的 model-aware transport 与一条 framework
  efficiency artifact 门，再分批运行，不同时放飞 50 格。该模型只用于流通/调用拓扑/成本
  observation，不与正式分数对比；`official_full` 仍为 `primary/gpt-4o-mini`。
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

### 申请材料（依赖 ws02）

- [ ] 全矩阵成本估算表：基于各格子 smoke/pilot 的 token/latency observation，
  按 ohmygpt 实价离线计算（`memory_benchmark.analysis`；严格区分
  api_usage / method_native / tokenizer_estimate）；给出分 benchmark、
  分 method 的全量费用与时间预估区间。
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
- [ ] **资源调度器**：按 local embedding、GPU model、Docker/DB、API-only、W1-only 等资源类给
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
- 既定：真实费用按 ohmygpt 实价离线算，不用 OpenAI 官方价做结论。
