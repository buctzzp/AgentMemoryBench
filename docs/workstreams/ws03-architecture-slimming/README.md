---
id: ws03
parent: null
status: in-progress
created: 2026-07-05
---
# ws03 架构减重（registry / legacy 接口 / CLI / LLM 配置）

## Codex 恢复胶囊（2026-08-14）

- **当前目标**：十家 method/5×10 smoke 已闭合，暂停 ws05 成本 pilot；执行有停手线的
  maintainability M1，不调用真实 API。
- **当前批次**：M1-A freshness 与依赖方向——先切断 `runners → cli`、
  `prompts → evaluators`，补最小 architecture/live-link gate，再盘点兼容层退出。
- **当前判据**：只读
  [十家 method 后的可维护性审计与 M1 裁决](notes/2026-08-14-maintainability-audit-and-m1-ruling.md)；
  结构灰区查 [`code-structure-principles.md`](../../reference/code-structure-principles.md)。
- **禁止事项**：不跑成本/official-full/API，不改 metric/prompt/method 算法，不按文件行数
  大搬家，不碰 data/models/outputs/third-party 或用户未跟踪资产。
- **完成门**：每批定向守恒 + compileall + 无 API 全量回归；M1-A→B→C→D 顺序推进，
  达到 note §7 后停止 ws03，不无限重构。

## 目标

retrieve-first 主路径稳定后，清除迁移期留下的重复机制：capability 推理、
legacy 基类、legacy CLI、分散的 LLM 配置。完成判据：新 method 兼容性由
`BaseMemoryProvider` 继承关系表达；legacy 负担删除或明确降级；
统一 `LLMRuntimeConfig` 落地且 manifest/model inventory 不回退。

## 当前断点

- 2026-08-14：用户裁定成本估算实验暂缓，先做项目“瘦身/规范化”。架构师完成 current-main
  只读审计并发布
  [M1 裁决](notes/2026-08-14-maintainability-audit-and-m1-ruling.md)：
  `metrics/evaluators` 分层和 method-specific worker/lifecycle 属合理结构；真实优先债是两条
  反向依赖、活跃 `config_track` 选择器、四份 worker transport 重复及 prediction 巨型编排。
  docs/roadmap/ws02/ws05 的 live 状态同步修正；文档门 `5 passed in 1.26s`，M1-A 的依赖
  环修复与自动边界门为下一动作。
- 2026-07-23：**结构归一 M0 已关闭**。架构师在
  `codex/ws03-structural-normalization-m0` 按 A→B→C 串行完成：
  文档热/冷分层与任务路由经验检索、pure metric + retrieval evaluator 共壳、
  benchmark/author prompt ownership 归位。兼容 import 保留薄 shim；
  runner/registry/legacy protocol、metric 公式、prompt 字节与 artifact schema 均未改变。
  compileall exit 0；无 API 全量门
  `1685 passed, 3 deselected, 1 warning, 29 subtests passed in 128.11s`。
  详细 commit、边界与行数见
  [结构归一 M0 裁决/施工记录](notes/2026-07-23-structural-normalization-m0-ruling.md)。
- “下一主线回 ws02.7 接 MemOS”已于 2026-08-14 被本轮 M1 裁决 supersede；MemOS 与后续
  十家 method 均已冻结，旧句不得再作为恢复动作。
- 先前的
  [里程碑收口与架构减重审计](notes/2026-07-23-first-25-cell-consolidation-audit.md)
  中体积盘点、scratch 吸收和 legacy 分类继续有效，只有“立即 MemOS”的顺序被改判。
  `BaseMemoryRetriever` 是第一项确认 legacy 候选，但
  `BaseResumableMemorySystem/add_from_turn`、`LegacyProviderBridge`、
  `ingest_resume.py` 与 `config_track.py` 均仍有生产可达调用，禁止按名字删除。

## 设计文档

- [十家 method 后的可维护性审计与 M1 裁决](notes/2026-08-14-maintainability-audit-and-m1-ruling.md)
- [稳定代码结构判据](../../reference/code-structure-principles.md)
- [2026-06-21-registry-capability-simplification-design.md](2026-06-21-registry-capability-simplification-design.md)
- [2026-06-21-llm-provider-config-design.md](2026-06-21-llm-provider-config-design.md)
- [首批 25 格里程碑收口与架构减重审计](notes/2026-07-23-first-25-cell-consolidation-audit.md)
- [结构归一 M0 裁决：metric / evaluator / prompt / 文档](notes/2026-07-23-structural-normalization-m0-ruling.md)

## 任务清单

- [ ] **M1-A freshness / dependency direction**：修 live 状态与链接；切断
  `runners → cli`、`prompts → evaluators`；补最小 AST/import gate；完成 shim/legacy
  消费者和退出门清单。
- [ ] **M1-B TOML profile migration**：新 run 由 TOML section + 完整 answer builder
  选择；active identity 与 legacy `TrackIdentity v1` readback 分离；旧 artifact 不改写。
- [ ] **M1-C isolated worker transport**：抽四家 adapter 主进程侧 JSON-lines transport；
  产品 worker、环境、Docker/DB 与 cleanup 差异继续显式。
- [ ] **M1-D prediction decomposition**：leaf-first 拆 planning/preflight、ingest、answer、
  parallel；原 import 保留 façade，每批行为守恒。达到停手线后返回用户选择，不自动扩 M1-E。

- [ ] 弱化 `MethodCapability` 推理，conversation-QA 兼容性收敛到
  `BaseMemoryProvider` 继承关系；保留轻量 registry（名称 → factory/config/
  source identity 映射），不回退分散 `if/else`。
- [ ] 清理或降级 `BaseResumableMemorySystem`、`BaseMemoryRetriever`、
  `add_from_turn()` 与历史 turn-level resume 文档/测试；`BaseMemorySystem`
  暂保留为后备兼容接口。删除前必须证明四个内置 method、fake/offline 测试和
  artifact-only evaluation 不依赖旧主路径。
- [ ] Legacy CLI 分阶段清理（节奏已定）：四 method 的 LoCoMo/LongMemEval v2
  smoke 稳定后加 deprecated warning → 至少一次 v2 formal 小规模 run 后从 README
  示例移除旧写法 → 对外发布前决定是否彻底删除旧参数。
- [ ] `OpenAISettings` 迁移到统一 `LLMRuntimeConfig` / `LLMResponse`；
  第一版仍只实现 OpenAI-compatible provider。
- [ ] 减重 evaluator registry：F1 / LLM judge 统一为 metric profile +
  prompt profile，不为每个 benchmark 复制 evaluator 类。
- [ ] prediction artifact 瘦身长期兼容：旧 artifact 回读策略、更多
  conversation-level metadata key、evaluator 是否引用 `conversation_prompts.jsonl`。
- [ ] evaluator category 汇总里 `correct_count` 是否更名
  `perfect_match_count`（防止 F1 连续指标被误读为 accuracy）。
- [ ] 评估可选 `--method-file` 单文件快速测试入口（method 接入轻量化遗留项）。

## 项目结构整治优化（2026-07-11 用户立项扩充；前置条件 = ws02.6 B6 五
benchmark 全部 frozen 后，行为被全量测试锁死才允许动结构）

- [ ] **evaluator 通用化**：retrieval recall 的 artifact/preflight/资格/summary
  共壳已在 M0 完成；LLM judge 共壳与 benchmark policy package 仍待后续。红线不变：
  recall 类抽公共骨架（公开 id 空间匹配、
  any-match、unmatched/歧义计数），llm judge 抽公共调用壳（模型/重试/
  解析）；**红线：各 benchmark 的 gold 形态差异与官方 parity 规则必须
  保持显式声明**（longmemeval 双粒度/membench +1 平移/beam 三形态打平/
  halumem 无 turn id——B 线教训：个性被通用代码吞掉 = bug 温床），
  通用骨架 + benchmark 声明差异，行为以现有全量测试逐一守恒验证。
- [ ] **拆开 answer depth 与 evaluation ranking depth**（2026-07-15 LightMem
  审计）：当前 `RetrievalQuery.top_k=10` 全局硬编码，同时被当成 evaluator 可算的
  最大 k；LongMemEval 官方 k=30/50 因而在真实通用 run 必然跳过，即便某 method 已
  保存 60 项。设计 benchmark-required ranking depth 与 method-native answer context
  depth 两个字段/视图，保证扩深排名观测不偷偷改变 answer prompt。
- [ ] **Recall@k 粒度诊断与公平伴随指标**：保留 method-native item recall，但统一
  报 top-k unique source 数、`source ids/item` 与 payload token；研究 source-budget/
  token-budget recall。未完成前禁止用单一 item Recall@k 作跨 method headline 排名。
- [ ] **method × benchmark × metric 资格声明**（2026-07-15 LightMem 二次裁决）：
  将当前 registry 静态 `provenance_granularity` 拆为可按 benchmark/metric 表达的
  valid/N/A/pending capability，并带机器可读 reason。区分 semantic evidence
  provenance 与 transformation-input lineage；NDCG 另校验稳定顺序和 evaluation
  depth。先做 docs-only 契约审计，不在单个 adapter 里打 LoCoMo 特判。
- [ ] **目录分层**：M0 已完成 pure metrics、evaluator common shell 与
  benchmark/author prompt ownership；benchmark 专属 evaluator 暂留原路径，避免同批再做
  第二次 import churn。后续等 policy 接口稳定后再归
  `evaluators/benchmarks/`，不以搬目录冒充抽象完成。
- [ ] **历史遗留盘点**（先盘点分类再动手，每项以"引用扫描 + 测试通过"
  为证据，不凭印象）：已确认遗留 = `BaseMemoryRetriever`（本 ws 既有）、
  `--profile` 残留；**待核** = `runners/ingest_resume.py`（用户 2026-07-11
  点名疑似遗留，但 CLAUDE.md 载明其为 resume 系统活跃组件
  ——TurnIngestCheckpointStore——须引用扫描裁定，不得凭印象删）；
  盘点产出三列清单：活跃/疑似/确认遗留。
- [x] **首批 25 格收口盘点**（2026-07-23）：完成工作目录/Git 体积拆分、四份根目录
  scratch 吸收账、活跃/兼容活跃/确认遗留三分类；确认 `BaseMemoryRetriever`
  为第一项 removal 候选，其余 resume/bridge/config-track 当前不可直接删。
- [x] **结构归一 M0**（2026-07-23 关闭）：A 文档热/冷层；B pure metric +
  retrieval evaluator 共壳；C benchmark/author prompt ownership。M0 零 API、零
  公式/prompt/artifact 语义变化；全量守恒门通过，下一家接 MemOS。
- [ ] **可执行架构边界**：继续把“高内聚、低耦合”变成 AST/import 回归门，而不是
  口号。已锁 `metrics/` 不反向依赖 evaluator/adapter/method/storage、
  `prompts/benchmarks/` 不依赖 method/author；后续只为真实漂移风险增加边界，
  不堆形式化测试。
- [ ] **兼容层退出预算**：每个 shim/deprecated 入口记录消费者、最后新增日期与退出门；
  新代码不得 import shim。删除以引用扫描 + artifact 回读 + 全量门为证据，不按年龄猜。
- [ ] **文档/经验可检索性**：热规则常驻，按任务标签检索一到两条 case；未来案例写
  `playbooks/architect/cases/` 并登记 trigger/supersedes/退出证据。定期检查孤立 note
  和失效链接，但不恢复“每次全文读取”。
- [ ] **长期健壮性排查**（第一性原理：项目连续运行 3-12 个月不腐坏）：
  ① **wall-clock 泄漏扫描**——`datetime.now()/today()` 是否参与任何
  评测语义（question time、相对时间换算、resume 判定），只允许出现在
  观测性时间戳；② **judge/answer 模型指纹**——manifest 是否钉死模型名
  +版本，模型漂移（gpt-4o-mini 升级/退役）是评测框架最大外部风险，
  结果必须可追溯到模型指纹；③ 依赖锁完整性（uv.lock + vendored
  third_party）；④ 绝对路径/主机名假设（原则 #12 身份=内容已治理
  一处，扫残余）。

## 决策记录

- 2026-06-21 用户：保留轻量 registry；capability 枚举与 legacy 基类属迁移期负担。
- 2026-06-22 用户：`retrieve()` 主输出为 `AnswerPromptResult.prompt_messages`；
  `answer_prompt` 仅兼容视图。
- 2026-06-24 用户：普通用户接入只要求 `add + retrieve`；TOML/source identity/
  深度插桩属框架开发者白盒路径（已实现，本 ws 不重复）。
- 2026-07-23 用户：结构治理服务长期可维护性，不以删除量为目标；采用稳定内核、
  显式 policy、边界层、兼容层退出预算与任务路由经验检索。M0 守恒迁移已通过全量门。
