---
id: ws02.7
parent: ws02
status: in-progress（首批 6 method frozen；Letta 离线门完成，LangMem M2 在建）
created: 2026-07-12
---
# ws02.7 Method Track M0

本 workstream 在五个 benchmark frozen-v1 的稳定层上，按
[`method-integration-checklist.md`](../../reference/method-integration-checklist.md)
B1-B11 逐家接入 10 个 method。活跃支线统一从
[`branches/README.md`](branches/README.md) 进入；不要从历史文件名猜当前动作。

完整历史账已归档到
[`2026-07-23-ws02.7-method-track-full-ledger.md`](../../archive/status/2026-07-23-ws02.7-method-track-full-ledger.md)。
该档只供定点追溯，不参与日常恢复。

## Codex 恢复胶囊（热层）

压缩后只执行：

1. `git status --short`
2. `git log -5 --oneline`
3. 读取本节
4. 读取“当前动作”链接的一份 ruling/note

禁止为恢复全局而全文读取历史账、全部 workstream 或两本经验手册。若本节与 Git
冲突，以 Git 和最新 ruling 为准。

- **稳定基线（2026-07-29）**：5 benchmark × 首批 6 method 的真实 smoke 与
  B1-B11 已关闭；ws03
  [结构归一 M0](../ws03-architecture-slimming/notes/2026-07-23-structural-normalization-m0-ruling.md)
  已通过守恒门。无 API 全量：
  `1685 passed, 3 deselected, 1 warning, 29 subtests passed in 128.11s`；
  compileall exit 0。唯一 warning 是既有 vendored LightMem Pydantic deprecation。
- **当前动作**：**MemOS 已冻结，机器化 smoke plan/preflight 与新 method ledger v1
  强制门均已关闭；Letta/MemGPT
  [source/product identity M1](branches/method-recertification/letta/notes/letta-current-product-identity-m1-ruling.md)
  与
  [sleeptime-memory product adapter M2](branches/method-recertification/letta/notes/letta-m2-adapter-checkpoint.md)
  均已验收，当前位于 **B11 真实 smoke 预算批准门**。Letta ledger 已转
  `ready_for_smoke`，11 个 concrete variant 的原始 planner JSON、五格 dossier、零 API
  PostgreSQL/`SyncServer` product chain、扩展定向与主树全量均已闭合；未经用户新批准，不得执行
  build/answer/judge API。Letta 主轨锁为 legacy V1
  `0.16.8` 内核 + official `ai-memory-sdk v0.2.0` 产品契约，五格均为 framework extension；
  active Letta Code 属算法变体，direct archival 属机制绕行。MemOS source lock 为官方稳定版
  `v2.0.25@e820406`。架构师
  [最终裁定](branches/method-recertification/memos/notes/memos-v2.0.25-m1-final-ruling.md)
  锁定的 `tree_text + MultiModalStruct + typed handlers +
  async/fast→MEM_READ` 主 profile 不变。R2 首轮 `d1a0178` 的缺口已由 follow-up
  `2830c32` 关闭，并通过
  [架构师最终验收](branches/method-recertification/memos/notes/memos-v2.0.25-async-lifecycle-r2-architect-acceptance.md)：
  product reader/storage failure 可达精确 terminal、local tracker 拒绝终态污染、
  full async product chain 与 patch identity 均已实证；架构师另补 Factory 作用域隔离与
  两条最低叶子强反例。MemOS product v3 adapter M4 首轮 `a87353a` 已完成 typed handler、
  MiniLM config、search 失败可见、namespace-safe clean retry 与五格实现，但架构师强反例
  证实 cleanup 在 pending refusal 前先丢失 provider/owner runtime 引用，重试会 no-op；
  generic runner 的 cleanup 保护区也尚未覆盖 clean hook/preflight。M4-R1 `de29c4c` 已关闭
  上述两处及环境恢复/typed-handler 共用 dependencies 漏测；其 `_stop_attempted` 遗留取舍
  又由 follow-up `f6e725e` 收敛为 stop failure 永久 fail-closed。三段现已线性合入
  `dff8185`、`02ffc9d`、`3e1d621`，并通过
  [M4 架构师最终验收](branches/method-recertification/memos/notes/memos-v2.0.25-product-adapter-m4-architect-acceptance.md)：
  主树 `1863 passed, 3 deselected, 11 warnings, 29 subtests passed`，compileall 与 patch
  reverse-check 均通过。2026-07-27 又按用户裁决完成
  [API runtime smoke 支线](branches/api-runtime-smoke/README.md)：新 smoke 锁为
  `opencodego/deepseek-v4-flash + Chat Completions`，Responses 不可用与 JSON mode 可用均
  已最小真调用证实；manifest/resume/evaluate 身份与离线 metric 免 secret 读取已锁强反例，
  无 API 全量为
  `1879 passed, 3 deselected, 11 warnings, 29 subtests passed in 132.87s`，compileall
  exit 0。M5 官方 harness 复核随后推翻了 M4 的 LoCoMo 单视角局部口径：
  [M5 harness 裁决](branches/method-recertification/memos/notes/memos-v2.0.25-official-harness-parity-m5-ruling.md)
  锁定主轨双 namespace、正/反 role、每视角 batch=2 与双路检索合并；
  LongMemEval 主轨仍是完整 session，官方 pair/truncate wrapper 留在 author 校准。
  current adapter 已升 `product-v4`，完成 product-v3 五格真实服务 smoke，并以
  LoCoMo/HaluMem 两条 v4 真实哨兵补齐 async build LLM `api_usage` 与本地 embedding
  tokenizer observation；见
  [frozen-v1](branches/method-recertification/memos/notes/memos-frozen-v1.md)。
  framework W2 的两个 provider 仍共享进程级 runtime/embedder，LongMemEval 实测
  `RuntimeError: Already borrowed`，故并行资格明确为 N/A：两主 profile 固定 W1、
  CLI 在 API/runtime 前拒绝 override。最终无 API 全量：
  `1902 passed, 3 deselected, 13 warnings, 29 subtests passed in 129.84s`，
  compileall 与 patch reverse-check 均为 exit 0。当前动作转为
  机器化 smoke plan/preflight 已由
  [M0 裁决与验收](notes/smoke-plan-preflight-m0.md)关闭：HaluMem fixed shape、
  operation-level W1、multi-variant child run-id、method worker 资格与 evaluator 集合
  均从 registry/TOML 生成，B11 禁止继续手写命令。最新无 API 全量：
  `1917 passed, 3 deselected, 13 warnings, 29 subtests passed in 160.69s`，
  compileall exit 0。ledger v1 随后以
  [`method-integration-ledger-v1`](notes/method-integration-ledger-v1.md)
  落地：33 个受保护检查点、五格独立记录、状态跃迁与证据入口均有机器门；首份
  [Letta ledger](branches/method-recertification/letta/notes/letta-integration-ledger.md)
  已在 adapter 前创建并经 M1/M2 更新到 `ready_for_smoke`；复用五个 benchmark 稳定事实，
  不重开 raw census，也不把 source lineage、rank、HaluMem extraction 等 N/A 能力伪造成 valid。
  ledger 门无 API 全量为
  `1923 passed, 3 deselected, 13 warnings, 29 subtests passed in 144.84s`，compileall exit 0。
- **不可顺手重开**：benchmark raw/canonical/gold 调查、已冻结 25 格、旧
  `config_track` 兼容、legacy bridge/resume、BLEU/ROUGE/Precision 新公式。Letta 真实
  B11 继续等待用户新批准；当前不烧 API 的施工动作已转入
  [LangMem ledger](branches/method-recertification/langmem/notes/langmem-integration-ledger.md)：
  M1 已锁 current source/product/harness，当前进入 M2 adapter 离线施工。
- **恢复当前结构任务只读**：上方 M0 ruling；需要追溯某家 method 才读下表对应 frozen note。
- **派工边界**：actor 卡由架构师写成自包含 prompt，用户选择跨模型 actor；除非用户明确
  要求，不自动启动 Codex subagent。

## 当前里程碑

| Method | 状态 | 权威冻结记录 | 关键资格边界 |
| --- | --- | --- | --- |
| LightMem | `method-frozen-v3` | [frozen-v3](branches/method-recertification/lightmem/notes/lightmem-frozen-v3.md) | online-soft；pair lineage 资格按 benchmark；forced flush 已修 |
| Mem0 | `method-frozen-v2` | [frozen-v2](branches/method-recertification/mem0/notes/mem0-frozen-v2.md) | V3 singleton 合法；LoCoMo speaker 映射；turn/session provenance 分格 |
| MemoryOS | `method-frozen-v1` | [frozen-v1](branches/method-recertification/memoryos/notes/memoryos-frozen-v1.md) | STM + ranked MTM Recall；HaluMem extraction N/A |
| A-Mem | `method-frozen-v1` | [frozen-v1](branches/method-recertification/amem/notes/amem-frozen-v1.md) | evolution 后 current memory；Recall/Precision/NDCG N/A |
| SimpleMem | `method-frozen-v1` | [frozen-v1](branches/method-recertification/simplemem/notes/simplemem-frozen-v1.md) | 合成 MemoryEntry；provenance N/A；build 串行 |
| MemOS | `method-frozen-v1` | [frozen-v1](branches/method-recertification/memos/notes/memos-frozen-v1.md) | typed product handlers；LoCoMo 双视角；framework W2 N/A |

未接入：Letta/MemGPT、EverOS、LangMem、Supermemory。EverOS 仍排最后。

## 现行长期裁决

### 数据与输入

- benchmark 稳定事实从 `docs/survey/` 与五家 benchmark frozen note 复用；只有 source lock/
  official asset 变化或新一手反证才重开 census。
- role/content/time/place/image 必须沿 canonical event → method ingest → backend
  payload 一手验证；不从 prompt 文案反推接口硬约束。
- placeholder 只有 method 的真实结构约束需要时才允许；不得制造非空假回复。
- typed timestamp 用 `turn → session → None` 的已声明回落；question time、兄弟 turn、
  wall clock 不得补进 source time。

### Method 与配置

- 主路径是 v3 `ingest + retrieve → framework reader`；新 method 不扩展 legacy API。
- 每个 method 一个 TOML；`smoke`/`official_full` 是跨五 benchmark 固定主 section；
  有一手证据时才增加稀疏 `author_<benchmark>`。
- 主 answer builder 归 benchmark；作者 builder 是完整 `PromptMessage[]` 构造，
  不是模板文件名。旧 `unified/native` 只作历史产物兼容。
- method × benchmark × metric 独立判 `valid/N/A/pending`。变换输入 lineage
  不等于当前 memory 的 semantic provenance。

### Metric 与 artifact

- Gold Evidence Group、RetrievalEvidence、N/A/null 与 stable-ranking 资格均已进入
  artifact；不得回退 run 级静态猜测。
- Recall 公式内核通用，benchmark 壳保留 gold view、empty/no-target/abstention 和
  official parity。当前结构归一只迁职责，不改公式、分母或启用面。
- 新答案/检索指标属于 metric-pack；已有 artifact 字段足够时离线复算，不反向重烧
  method build。LLM judge 仍需单独预算批准。

## 当前动作与关闭门

1. [x] **ws03 M0-A**：本 README 与经验手册热/冷分层；
2. [x] **ws03 M0-B**：pure metric 归位、retrieval evaluator 共壳；
3. [x] **ws03 M0-C**：benchmark/author prompt ownership；
4. [x] 定向测试、文档门、compileall、无 API 全量 pytest；
5. [x] 按新结构接入 MemOS；
6. [x] 机器化 smoke 规划/预检；
7. [ ] 新 method 强制接入 ledger；
8. [ ] 接入 Letta/MemGPT。

M0 红线：零真实 API、零 third-party 算法改动、零 metric/prompt/artifact 语义变化；
旧 import path 在迁移期保留薄兼容层。

## 稳定入口

- [活跃支线索引](branches/README.md)
- [method 重认证总入口](branches/method-recertification/README.md)
- [Method TOML 与 answer builder 政策](../../reference/method-toml-and-answer-builder-policy.md)
- [Method 接入清单 B1-B11](../../reference/method-integration-checklist.md)
- [指标扩展计划](../../reference/metric-extension-plan.md)
- [结构归一 M0 裁决](../ws03-architecture-slimming/notes/2026-07-23-structural-normalization-m0-ruling.md)
- [截至 2026-07-23 的完整历史账](../../archive/status/2026-07-23-ws02.7-method-track-full-ledger.md)

## 里程碑

- [x] 五个 benchmark frozen-v1
- [x] 首批 5 method × 5 benchmark 真实 smoke 与 B1-B11
- [x] 结构归一 M0
- [x] MemOS
- [ ] Letta/MemGPT
- [ ] LangMem
- [ ] Supermemory
- [ ] EverOS（最后）
