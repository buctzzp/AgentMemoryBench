# 文档地图

| 位置 | 内容 | 性质 |
| --- | --- | --- |
| `AGENTS.md`（仓库根） | 定位、硬规则、协作模式、导航 | 静态入口 |
| `docs/roadmap.md` | Phase 1 目标、workstream 索引、全局约束 | 方向文档 |
| `docs/workstreams/` | 每条任务线：README（状态页）+ spec + plan + notes/ | 活跃过程文档 |
| `docs/reference/` | 架构、数据模型、method 接口清单、接入指南 | 长期参考 |
| `docs/survey/` | [调查事实索引](survey/README.md) + benchmarks/ 总览、datasets/ 数据结构、workflows/ 官方评测流程 | 稳定调研资料 |
| `docs/archive/` | 已完成/被覆盖的 spec、plan、handoff、旧状态文档 | 只读历史 |
| `docs/调研资料/` | 用户个人 Obsidian 调研笔记（含 benchmark 总表） | 用户维护 |
| `opencode/` | OpenCode 通道任务与结果索引（archive/ 为历史） | 后备通道（待命） |
| `reports/` | 对外汇报材料（assets/ 存图片） | 汇报 |

## 本地目录说明（已 gitignore，不入库）

| 目录 | 性质 |
| --- | --- |
| `data/`、`models/` | 运行时数据集与本地模型权重（HF repo `BuptZZP/agentmemorybench-data`） |
| `outputs/` | 实验产物；`memoryos-locomo-full-20260603/` 受保护 |
| `third_party/benchmarks/` | 官方 benchmark 仓库副本（事实核查用） |
| `third_party/methods/` 中多个重仓库 | 见 `third_party/methods/MANIFEST.md` + fetch 脚本 |
| `old/` | 2026-06 之前的遗留草稿 |
| `tmp/` | 临时抓取与中间产物 |
| `paper-make/` | 论文 LaTeX 工作区 |
| `第三方框架参考/` | 第三方框架调研参考资料 |

## 查找路径

- 想知道"现在做到哪了"：`roadmap.md` → 对应 workstream README 的"当前断点"。
- 想知道"某个决定为什么这样定"：先查 workstream README 的"决策记录"，再查 `archive/`。
- 想找"某 benchmark/method 以前是否调查过"：先看 `survey/README.md`；benchmark 走三联
  survey，method 走 `reference/integration/<method>.md`，再顺链接读承重 evidence note。
- 想知道十家 method 的产品调用签名、参数/返回类型、框架注入粒度，以及 API 中
  `list[...]` 到底是 session、pair 还是内部 batch：先看
  `reference/method-interface-inventory.md`，再进入对应 integration 页的“产品接口契约”。
- 想知道 method 超参数、作者配置与 answer prompt 如何选择：
  `reference/method-toml-and-answer-builder-policy.md`；十家逐项参数/prompt 取证的当前进度看
  `workstreams/ws05.1-method-profile-provenance/README.md`。
- 想知道 smoke/official 使用哪个 API provider、model、transport，以及如何进入
  manifest/resume：`reference/api-runtime-profiles.md`。
- 想生成不会误带 HaluMem 裁剪轴、错误 worker 或 variant run-id 的 smoke 命令：
  先运行 `uv run memory-benchmark plan-smoke --help`；强制门见
  `reference/method-integration-checklist.md` B11。
- 想接入一家新 method：先复制
  `reference/templates/method-integration-ledger.md`，再按
  `reference/method-onboarding-assembly-line.md` 推进；运行
  `uv run python scripts/validate_method_integration_ledgers.py --root .` 检查漏格与状态越级。
- 想跑命令、查代码结构：`CLAUDE.md`。
- 想比较 actor 的真实交付：`reference/actor-performance-ledger.md`（任务级样本，不是
  脱离卡难度的模型神榜）。
- 想复用架构经验：先读 `reference/architect-playbook.md` 热入口，再按
  `reference/playbooks/architect/README.md` 的任务标签定点检索案例；禁止默认全文灌入
  冷层 casebook。
- 想在硬规则未覆盖的灰区做结构/设计裁决：`reference/code-structure-principles.md`
  （架构师参考：代码结构 7 条 + 项目设计 8 条 + 四问判断流程 + 本仓库真实判例与
  可复现核查命令。只提供判据，实际结构改动仍归 `ws03`）。
