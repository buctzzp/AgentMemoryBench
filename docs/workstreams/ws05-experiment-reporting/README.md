---
id: ws05
parent: null
status: paused
created: 2026-07-05
---
# ws05 全量实验申请材料与前置工程

## 目标

在 ws02 smoke 矩阵完成后，组装与导师讨论全量实验的完整申请材料，并在预算
获批前完成全量运行的兜底工程验证。完成判据：申请材料（成本估算表 + 现有
结果汇总 + 实验方案）可直接用于导师讨论；兜底验证清单全绿后才允许启动全量。

## 当前断点

- 2026-08-14：用户明确暂缓“每个 benchmark 跑隔离空间再外推”的成本 pilot，先执行
  ws03 maintainability M1。本页任务未取消；恢复前必须由用户重新确认预算、规模与 run_id，
  不得从旧 smoke/artifact 或底层 resume 能力自动续跑。
- 2026-07-05：依赖 ws02 矩阵产出，暂不开工。本 workstream 从旧
  "experiment-reporting" 口径重构而来：成本估算不再是一次性报告任务，而是
  ws02 每个格子的标准产出；本 ws 负责"组装申请材料 + 全量前置工程"。

## 任务清单

### 申请材料（依赖 ws02）

- [ ] 全矩阵成本估算表：基于各格子 smoke/pilot 的 token/latency observation，
  按 ohmygpt 实价离线计算（`memory_benchmark.analysis`；严格区分
  api_usage / method_native / tokenizer_estimate）；给出分 benchmark、
  分 method 的全量费用与时间预估区间。
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
