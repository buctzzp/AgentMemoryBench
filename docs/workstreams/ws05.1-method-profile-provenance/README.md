---
id: ws05.1
parent: ws05
status: in-progress
created: 2026-08-24
---
# ws05.1 十家 method prompt 与参数 provenance

## 恢复胶囊

- **目标**：在扩大 pilot 前，逐家确认主 method 配置保留完整算法机制，并为作者实际跑过的
  benchmark 找到可复现的完整 answer builder、effective 参数与明确 source identity。
- **当前批次**：M0 资产模板与 M0.5 第三方框架配置对照已完成，结论是配置格式不等于
  effective config 公平性，本项目继续使用强类型 TOML。当前进入 M1 LightMem：先读匹配版本
  paper 并画算法阶段图，再核 LoCoMo/LongMemEval harness、current source 与最终参数调用链。
- **当前判据**：[`spec.md`](spec.md)。参数是否承重只由有效调用语义判定，不按 bool/number
  分类；paper identity、author-reported identity、current product default 与 framework main
  identity 必须分栏，不得揉成一个“官方默认”。
- **禁止事项**：本任务零真实 API、零参数 sweep、零效果调优；不得因为找到模板就宣称完整
  prompt parity，不得把 method 官方 judge 暗换进 benchmark 主表，也不得以非官方 fork 冒充
  author source。
- **当前动作**：完成 LightMem 的一手参数/prompt 矩阵并回填稳定 integration 页；M1 未经验收前
  不开始 A-Mem，不修改其余九家 TOML，也不恢复真实 pilot。

## 为什么单独立项

2026-08-24 的配置所有权迁移已经把 method 算法参数、API runtime、benchmark evaluation 与
execution 分开，但它没有逐项证明“当前值为什么是这个值”。同时
`src/memory_benchmark/prompts/author/` 只有 LightMem、Mem0、MemoryOS 三家资产，A-Mem 等方法
在独立评测仓库中存在官方 prompt 的可能性尚未系统闭合。若直接扩大 pilot，可能用关闭核心
阶段的产品默认或不完整 builder 生成一批身份错误的结果。

本任务只关闭这道研究身份门，不重做十家 B1-B11，不重跑已经冻结的 smoke，也不借机优化分数。

## 稳定输出与长期读取入口

- 永久政策：[`method-toml-and-answer-builder-policy.md`](../../reference/method-toml-and-answer-builder-policy.md)
- 每家稳定结论：`docs/reference/integration/<method>.md`
- 当前进度与断点：本 README + 父 [`ws05 README`](../ws05-experiment-reporting/README.md)
- 一手长证据：本目录 `notes/<method>-profile-provenance.md`
- 十家对表：[`method-profile-provenance-matrix.md`](notes/method-profile-provenance-matrix.md)；每完成一家立即更新，
  不等十家结束后凭记忆补写。
- 每家统一记录格式：[`method-profile-provenance-note-template.md`](notes/method-profile-provenance-note-template.md)，
  先画算法阶段图再填参数表。
- 第三方框架配置比较：[`third-party-framework-config-strategy-audit.md`](notes/third-party-framework-config-strategy-audit.md)；只深读
  真正同时覆盖多 method/多 benchmark 且暴露有效配置链的框架，避免把整个参考目录机械倾倒。
- 新取得的官方仓库：先核 owner/license/commit，再登记
  `third_party/methods/MANIFEST.md` 与可重放 fetch 入口；孤立 clone 不算项目资产。

## 完成判据

1. 十家各有 current source identity 与官方 benchmark 覆盖清单；找不到也记录搜索边界和
   `SOURCE_UNAVAILABLE`，不虚构。
2. 每个官方 benchmark 的最终 answer messages、变量来源、decode 参数与读取/解析链已闭合，
   或诚实标 pending/unavailable；只找到模板不算完成。
3. method harness 中出现的 judge prompt 已盘点，但是否进入框架由独立 metric tier 裁决；
   benchmark 主 judge 不被暗换。
4. 全部 method-owned 开关/枚举与高影响数值都有 upstream default、paper role、official
   effective value、current main value、调用点、重建影响和裁决。
   每家在参数表之前先完成论文/技术报告算法阶段图与 current source 对应关系；无正式论文时明确
   官方替代材料和证据等级。
5. 主配置跨五 benchmark 固定；作者值只进入显式、稀疏、可运行且可审计的
   `author_<benchmark>`。若 harness 改变双写/namespace/算法拓扑，不能伪装成普通 TOML 覆盖。
6. 配置或 builder 修改通过零 API 定向门、manifest/resume identity 门和最终无 API全量门；
   用户重新批准预算、规模、run_id 前不恢复真实 pilot。

## 决策记录

- 2026-08-24 用户：论文算法图、README 与 method 官方 benchmark 代码是必要证据；缺失的专门
  评测仓库应主动寻找，实在不可得才诚实停在 unavailable。
- 2026-08-24 架构裁决：参数类型不是语义；论文完整算法、作者实际实验与 current product
  默认回答三个不同问题。作者复现用来验证框架 fidelity，跨五格固定主配置用来保证主表公平。
- 2026-08-24 用户：`第三方框架参考/` 如何选择同一 method 的跨 benchmark 配置，是本项目主
  配置设计的重要比较输入，必须列入计划。架构裁决：这些框架可证明一种工程策略如何落地，
  但除非它本身就是 method 官方评测入口，否则不能升级为 author-reported 参数证据。
- 2026-08-24 用户：参数裁决前必须先理解每家 method 的算法机制；优先读匹配版本论文，没有论文
  再查官方技术报告/架构文档。架构裁决：每家 note 先画算法阶段图并追到 current source，再讨论
  开关和数值，不能从 README 参数表或 constructor default 反推完整算法。
- 2026-08-24 架构裁决：YAML 常因嵌套结构、深合并和生态工具被采用，但这不等于配置更公平；
  第三方框架已出现 benchmark override 与隐藏 fallback。当前强类型、浅层 method schema 继续用
  TOML，只有出现真实深层组合需求时才重新评估格式。
