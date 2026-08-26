# 项目路线图

更新日期：2026-08-26。本文件是唯一方向文档：Phase 1 目标、workstream 索引与
全局约束。逐任务状态见各 workstream README；2026-06 的历史阶段记录（Phase E-S）
已归档到 `archive/status/2026-07-04-current-roadmap.md` 与
`archive/status/2026-07-04-task-ledger.md`。

## Phase 1 目标（2026-07-04 锁定范围；里程碑 2026-07-20）

- **Benchmark（5）**：LoCoMo、LongMemEval、HaluMem、BEAM、MemBench。
- **Method（10）**：学术型 A-Mem、MemoryOS、MemOS、LightMem、SimpleMem；
  工程型 Mem0、Letta/MemGPT、EverOS、LangMem、Graphiti OSS。（2026-07-11 用户拍板
  去 Cognee 换 EverOS；2026-08-09 又因 Supermemory stable self-host runtime 只有 binary、
  公开 tree 缺运行时核心源码，改由 Apache-2.0 Graphiti 接替。Graphiti 不等于 Zep hosted
  product，结果也不宣称 Zep parity。）

**Phase 1 的完成判据不是全量实验，而是 5×10 smoke 矩阵**（2026-07-05 与用户
重新对齐）：每个可行组合跑通极小规模真实测试并写出成本 observation；汇总为
全矩阵成本估算表（ohmygpt 实价），作为与导师讨论全量预算的申请材料；不可行
组合记录 gap 与原因，不强行接入。全量实验在预算获批后另启，前置条件是失败
恢复/防 API 空烧兜底工程通过验证；已有 LoCoMo full 结果届时在完成后的 5×10
架构下用新 run_id 重跑。

当前基线（2026-08-14）：5 个 benchmark adapter 全部 frozen-v1；Phase 1 十家 method
（Mem0、MemoryOS、A-Mem、LightMem、SimpleMem、MemOS、Graphiti、Letta/MemGPT、LangMem、
EverOS）均已完成全部可行格的真实 smoke 与 B1-B11；5×10 smoke 矩阵关闭，不可行组合以 N/A/
unsupported 留痕，不为填格伪造能力。
LightMem=`method-frozen-v3`，Mem0=`method-frozen-v2`，MemoryOS/A-Mem/SimpleMem=
`method-frozen-v1`。A-Mem 与 SimpleMem 各完成 11 个正式真实 run；前者检索 evolution 后
current memory，后者检索合成 MemoryEntry，turn-evidence retrieval metric 的研究裁决均为 N/A。
2026-08-21 冻结后轻量差量审计发现 A-Mem adapter/test/旧 artifact 的 runtime capability
stamp 实际为 `valid/turn`，与该 N/A 裁决矛盾；current runtime/registry/manifest 已修为
N/A/none，并独立保留 stable ranking=valid，B5/GRID 精确重开关闭。该零 API 小修不撤销其
product build、既有 smoke 或 5×10 矩阵，也不改写旧 artifact。
current closure 的无 API 全量为
`2200 passed, 3 deselected, 25 warnings, 29 subtests passed in 200.86s`，compileall exit 0。
逐题 RetrievalEvidence 与 Gold Evidence Group 已让 LoCoMo/MemBench/LME 的有效 Recall 和
BEAM/HaluMem 的 N/A、stable ranking 的 pending 进入 artifact，不为填矩阵硬算。

旧协议 V2 的 LoCoMo full 仍不计入 v3 矩阵。旧 `unified/native` 双轨硬编码已由
`docs/reference/method-toml-and-answer-builder-policy.md` 取代：每家一个 TOML，主 smoke/full
section 跨五格固定，作者确有一手配置时才加稀疏 `author_<benchmark>`；embedding 也是普通
TOML 字段，效果实验前再裁共同模型或产品默认，当前 smoke 沿用已验收 MiniLM。旧 TrackIdentity
仅作产物兼容，eval fork 不得藏进配置名字。Mem0/LightMem/MemoryOS 的 product default、
generic/eval/build-axis 与 MemoryOS PyPI/ChromaDB 关系已完成审计和架构裁决；truthful track
identity M0 已经 R1/R2、严格 resume/evaluate 和全量回归关闭。LightMem → Mem0 → MemoryOS →
A-Mem → SimpleMem → MemOS → Letta/MemGPT → LangMem → EverOS 已逐家重认证 B1-B11，
不靠历史 frozen 惯性，也不盲目重烧未变资产。

MemOS=`method-frozen-v1`：官方 `v2.0.25` typed product handler、LoCoMo 双 namespace、
async exact terminal 与真实 API usage 观测已闭合。历史 W2 的 `Already borrowed` 证明共享
进程级 runtime/embedder 不安全；2026-08-25 的 v6 改为每 framework worker 独立 runtime/
embedder/scheduler，W2 ownership 零 API门已闭合，不再把 W1/W2/W10 写成 method 能力上限；
真实多 isolation sentinel 仍待用户批准。

Graphiti OSS 已锁 `v0.29.3@021d3a5`，并以 direct-core/FalkorDB Lite product adapter 完成
18 份真实 v2 run、35 question、88 product episodes、全部适用 W1/W2 与 artifact/payload
机器门，冻结为 `method-frozen-v1`。MemBench 100k 因 product mandatory source time 诚实
N/A；Graphiti 不是 Zep hosted。Supermemory 旧 blocked 记录只保留为 source-gate 历史。
Letta/MemGPT 以 legacy V1 0.16.8 + official ai-memory-sdk v0.2.0 产品链完成 11 份 current
真实 run、17 question 与 artifact/效率/隐私/volume 机器门，冻结为 `method-frozen-v1`。
LangMem 以 async background manager 产品链完成 20 份真实 run、47 question、全部 croppable
W1/W2 与 artifact/效率/隐私/state 机器门，冻结为 `method-frozen-v1`。EverOS 以 v1.2.3
official lifespan typed-product 链完成 18 份 fresh v6 run、35 question、全部可行 variant 的
W1/W2 与 artifact/效率/隐私/state 门，冻结为 `method-frozen-v1`；MemBench 100k 因 source time
缺失且产品会把 timestamp 写入 Episode，诚实 unsupported。2026-08-24 EverOS 主 build identity
升级为 v7 controlled MiniLM-384；旧 v6 证据保留为历史冻结资产，v7 已过 patch 重放、本地模型、
schema 与 official lifespan 零 API门，但须在 ws05 M5 后用新 run-id 重建，不能借旧 smoke
续跑或重标。旧
Letta/Graphiti 403 run 只保留作失败阶段证据，不冒充可 resume smoke。
效果参数、作者 builder、真实 resume 与 full 成本 pilot 仍待后续。真实 API
一律继续由用户确认预算、规模与 run_id。首批 25 格完成后已做一次有边界的
[架构减重审计](workstreams/ws03-architecture-slimming/notes/2026-07-23-first-25-cell-consolidation-audit.md)：
先清临时事实源、盘点活跃 legacy。用户随后明确“整治不只是删除”，
[结构归一 M0](workstreams/ws03-architecture-slimming/notes/2026-07-23-structural-normalization-m0-ruling.md)
已完成 evaluator/prompt/文档的零语义迁移与全量守恒门；MemOS 随后已冻结，
registry-backed `plan-smoke` preflight 与新 method ledger v1 强制门也已关闭；Graphiti、Letta 与
LangMem、EverOS 均已完成真实 B11 与冻结对表。ws02.7 原于此关闭；2026-08-21 因 A-Mem
B5 runtime evidence stamp 的精确反例临时重开并以零 API 小修关闭，范围不含真实 smoke。
2026-08-14 用户
2026-08-21 用户已恢复 ws05：先用限时免费 `opencodego/ox-alpha-free` 完成 model-aware
transport、efficiency artifact 与受控并发门，再以全局 API semaphore=4 分批运行隔离 pilot；
这不是正式效果分数轨，`official_full` 仍保持 `primary/gpt-4o-mini`。此前成本 pilot 暂缓期间
已完成 ws03 maintainability M1；live 文档/依赖方向、
TOML profile、共享 worker transport、prediction 编排与 legacy 退役五批均已关闭；新实验只保留
provider v3 + 通用 prediction，registry 已完成责任审计。M1 全程零真实 API，ws03 已完成。
2026-08-21 用户选择并完成 ws04：纠正 7 月已落地 `method.log`
但状态页未回填的文档漂移，补齐 isolated heartbeat、factory handler 恢复、in-process
stdout/stderr 与 JSON-lines worker stderr 脱敏落盘；该批当时的无 API 全量为 2243 passed，
后续 legacy 退役、profile provenance 与并行门增删后的 current baseline 为
`2304 passed, 3 deselected, 25 warnings, 29 subtests passed`。

2026-08-24 用户在扩大 ws05 pilot 前再次暂停真实 API，先治理配置所有权、controlled embedding、
模型调用/失败成本观测与 HaluMem session extraction 资格。当前施工入口为
[ws05 runtime 配置与观测支线](workstreams/ws05-experiment-reporting/branches/runtime-config-and-observability/README.md)；
旧“Mem0 + MemoryOS 第一扩大波”不再是恢复动作。
该支线 M0-M5 无 API门关闭后，用户进一步要求在 pilot 前逐家核实参数**值**与作者 prompt
provenance：论文完整算法、官方 benchmark effective config、current product default 与主表固定
配置不得混为一谈；缺失的独立官方评测仓库要主动定位，实在不可得才标 unavailable。
[ws05.1 method profile provenance](workstreams/ws05.1-method-profile-provenance/README.md) 已关闭：
`第三方框架参考/` 的 repo-default/跨 benchmark 固定/逐格调参策略，以及逐家官方论文/仓库裁决
均已沉淀。当前执行入口回到 [ws05](workstreams/ws05-experiment-reporting/README.md) 的开跑前
isolation 并行门；真实 pilot 继续暂停，下一步是
Letta/MemOS/HaluMem 的新 run 多 isolation sentinel 与 staged calibration 命令身份。

## Workstream 索引

| ID | 名称 | 状态 | 优先级 | 说明 |
| --- | --- | --- | --- | --- |
| [ws01](workstreams/ws01-docs-governance/README.md) | docs-governance | done | P0 | 文档治理与任务树重构（2026-07-05 终验通过） |
| [ws02](workstreams/ws02-phase1-matrix/README.md) | phase1-matrix | paused | P1 | 5×10 smoke 已关闭；只剩成本估算/申请材料，按用户裁定随 ws05 暂缓 |
| [ws02.1](workstreams/ws02.1-membench/README.md) | membench-adapter | accepted | P0 | MemBench frozen-v1；method 矩阵的 0-10k/100k smoke 证据统一在 ws02.7 |
| [ws02.2](workstreams/ws02.2-halumem/README.md) | halumem-adapter | accepted | P0 | HaluMem frozen-v1；method extraction/update/QA/type 真实 smoke 由 ws02.7 逐家验收 |
| [ws02.3](workstreams/ws02.3-beam/README.md) | beam-adapter | accepted | P0 | BEAM frozen-v1；method variant/rubric 真实 smoke 由 ws02.7 逐家验收 |
| [ws02.4](workstreams/ws02.4-simplemem/README.md) | simplemem-adapter | accepted | P0 | 历史 T1-T6 已关闭；current text product 的五格重认证与 frozen-v1 见 ws02.7 |
| [ws02.5](workstreams/ws02.5-method-interface-audit/README.md) | method-interface-audit | done | P0 | 2026-07-09 关闭：5 method 接口审计 + MemoryOS 迁移 + 当时配置归一化；shared embedder 资产保留为 controlled，ws02.7 现审计 product-default 精确身份与迁移/复证面 |
| [ws02.6](workstreams/ws02.6-first-smoke-hardening/README.md) | first-smoke-hardening | done | P0 | 五 benchmark 全部 frozen-v1 + B6 横向总验收完成（2026-07-12）；method 侧已转 ws02.7 |
| [ws02.7](workstreams/ws02.7-method-track/README.md) | method-track-m0 | done | P0 | 5×10 smoke matrix 与 A-Mem B5/GRID 精确 closure 均关闭；无在途施工 |
| [ws03](workstreams/ws03-architecture-slimming/README.md) | architecture-slimming | done | P0 | M1-A→E 已关闭：依赖方向、TOML profile、worker transport、prediction 拆责与 legacy 退役 |
| [ws04](workstreams/ws04-terminal-observability/README.md) | terminal-observability | done | P0 | isolated heartbeat 与第三方输出治理已关闭；完整诊断进 method.log |
| [ws05](workstreams/ws05-experiment-reporting/README.md) | experiment-reporting | in-progress | P0 | profile provenance、isolation 并行门与 QA aggregation M0 已闭合；当前补 cohort receipt/bootstrap 报告面，再恢复 staged calibration；真实 pilot 暂停 |
| [ws05.1](workstreams/ws05.1-method-profile-provenance/README.md) | method-profile-provenance | done | P1 | 十家纵向机制卡 + M11 source/embedding/run identity v2 已闭合；零 author profile，真实 pilot 待用户批准 |
| [ws06](workstreams/ws06-tests-restructure/README.md) | tests-restructure | open | P2 | tests 分组重组、大文件拆分、过时断言排查 |

新 workstream 的建立与命名规则见 `AGENTS.md` "文档规则"。

## 全局约束（长期有效，硬规则全文见 AGENTS.md）

- **预算强约束**：全量实验必须先有成本估算表并经导师/用户批准；当前阶段一切
  真实 run 均为极小规模。任何真实 run 需用户确认预算、规模与 run_id。
- smoke 使用同一 method 主参数；成本控制只通过数据规模裁剪，不降 `top_k` 等算法参数。
  超参数采用作者公开产品接口的固定主配置，跨全部 benchmark 同一套、不 per-benchmark 调优；
  作者确有一手 benchmark 配置时才另建稀疏校准。embedding 的 Phase 1 主比较自 2026-08-24
  改为：所有实际消费 embedding 且公开接口兼容的方法统一 MiniLM-384 controlled identity，
  完整锁 provider/model/revision/dimension/normalization/instruction/distance；不消费 embedding
  的 profile 记 N/A，不能为“十家同名”伪造配置。product default 保留为补充校准；
  **paper 声明 ≠ repo 默认时仍须显式记录差异**（政策全文与理由见
  `workstreams/ws02.5-method-interface-audit/README.md` "超参数政策"）。
- 不合并不同 dataset variant 的 run；不创建 method × benchmark 专用 runner。
- 真实费用按实际 API 服务商（ohmygpt）价格离线计算，不绑定 OpenAI 官方价。
- `outputs/memoryos-locomo-full-20260603/` 是受保护实验资产。

## 恢复流程（冷启动与 compaction 分开）

1. **同一架构师 compaction/resume**：由受信任的 Codex hook 自举；只看
   `git status --short`、`git log -5 --oneline`、本表唯一 `in-progress + P0` 行所指
   README 顶部恢复胶囊，以及当前动作的一份判据。不要重读全仓文档。
2. **全新架构师冷启动**：读 `AGENTS.md` → `architect-onboarding.md` 的首次上岗读序；
   不把冷启动读序套到每次压缩。
3. 涉及真实实验时，先查 `outputs/<run_id>/checkpoints/progress.json`、
   `conversation_status.json` 和 `summaries/summary.json`。
4. 不要依据 archive 内旧文档的"待办"直接开工，先核对 workstream 状态页。
