# 代码结构与长期可维护性判据

> 本页回答“什么样的结构值得改、什么样的不对称应保留”。它是稳定判据，不记录
> 当前施工状态；当前批次与证据看 `docs/workstreams/ws03-architecture-slimming/`。

## 1. 一句话原则

本项目追求的不是文件最少、目录最整齐或抽象最多，而是：**一次需求变化只触及它真正
负责的少数模块，错误能在边界处暴露，旧实验仍可审计，下一位架构师能从短入口恢复。**

“高内聚、低耦合、可复用”可以拆成下面八条可检验规则。

## 2. 八条结构规则

### 2.1 一个模块只有一个主要变化原因

同一模块里的代码应因同一种原因一起变化。例如纯 Recall 公式因数学定义变化，benchmark
evaluator 因 gold/排除口径变化，method adapter 因产品接口变化。它们不应绑在一个文件里。

反过来，两个函数长得像，不等于它们应该合并。只有当语义、依赖和失败策略都相同，抽取
公共实现才会降低维护成本。

### 2.2 依赖只能朝稳定内核流动

本仓库的目标方向是：

```text
CLI → application service / runner → benchmark policy + method adapter
                                      ↓
                                core contracts

evaluator → pure metrics
prompt registry / evaluator registry → prompt assets
method adapter → product runtime boundary
```

禁止反向依赖，例如 runner import CLI、prompt asset import evaluator class。出现双向边时，
通常说明共享契约放错层，而不是需要再加一个全局 helper。

### 2.3 纯计算、政策和副作用分层

- `metrics/`：纯确定性公式，不读 artifact、benchmark、method、配置或网络；
- `evaluators/`：读取 artifact，选择 gold view，判 valid/N/A/pending，执行官方排除政策，
  必要时调用 judge；
- `prompts/`：拥有 prompt/builder 资产，不拥有 evaluator 的执行生命周期；
- `methods/`：把统一协议翻译成产品接口，隔离第三方依赖与生命周期；
- `runners/`：编排，不重新实现上述各层规则。

因此 `metrics/` 与 `evaluators/` 名字都与“指标”有关，但职责不同，不应合并。

### 2.4 接口统一，不强求文件形状统一

所有 method 对框架提供相同 provider contract；内部结构按产品约束组合：

- 单进程、依赖兼容的产品可以只有 `<method>_adapter.py`；
- 需要独立 Python/依赖环境的产品可增加 `<method>_worker.py`；
- 有真实异步后台状态机的产品可增加 `<method>_lifecycle.py`；
- Docker、数据库、队列等边界只在确有产品约束时存在。

为了目录对称而给所有 method 制造空 worker/lifecycle，或把必要边界塞回 adapter，都会让
代码更难理解。规范应约束“何时允许出现”，不是要求每家文件数一致。

### 2.5 先保语义，再消重复

遵守 Rule of Three：至少三处实现已经证明语义相同，再抽公共模块。抽取前后必须锁住：

- 输入/输出字节和顺序；
- manifest、artifact 与 resume identity；
- timeout、cleanup、异常传播和并发行为；
- 隐私与 namespace 边界。

小型字段校验即使重复，也可能承载不同产品的失败语义；不要为了 DRY 制造一只万能工具箱。
抽出的公共执行文件必须进入每个消费者的 source/resume identity；否则公共代码已经改变，
旧 manifest 却仍可能声称同一 method build。共用 transport 只统一 request/response/pipe
机械层，timeout 后是否终止、是否忘记进程对象、错误提示和最终 cleanup 归属继续用窄 policy
显式声明，不能用一套默认值吞掉产品状态机。

### 2.6 生命周期与所有权必须显式

每个外部资源都要回答：谁创建、谁独占或共享、何时完成、失败后是否可重试、谁关闭。
worker transport、MemOS scheduler waiter、Letta Docker 生命周期之所以可以独立成文件，正是
因为它们有独立的资源所有权与失败状态机。

### 2.7 兼容层是一笔有退出条件的债

兼容 shim 可以短期保留旧 import/旧 artifact，但必须满足：

1. 新代码不再引用；
2. 记录消费者、历史用途和退出门；
3. 旧 artifact 读兼容与旧命令继续生成新 run 分开裁决；
4. 到门后删除，不把 shim 变成第二份实现。

本项目是 `0.1.0`、尚无已声明的稳定 Python 公共 API。默认政策是：内部 import 在迁移完成后
可删除；Phase 1 已有 artifact 的只读兼容长期保留；公开 CLI 的破坏性变更仍需显式迁移说明。

### 2.8 简单优先，但不把复杂事实藏起来

采用 KISS/YAGNI：没有当前需求和失败判例支撑的扩展点不提前造；同时，benchmark gold
差异、method 产品生命周期、N/A 资格等真实复杂性必须显式表达，不能用一个巨大
`if benchmark == ...` 或“通用”名字掩盖。

## 3. 文档也是架构：分层而不是全文记忆

项目文档按访问频率形成五层，而不是把聊天原文全部写入一个大文件：

| 层 | 内容 | 读取时机 |
| --- | --- | --- |
| L0 | 当前代码、测试、artifact、`git status/log` | 每次验收，以此裁决现实 |
| L1 | `roadmap.md` + 唯一活跃 workstream README 恢复胶囊 | compaction 后只读这一层 |
| L2 | `reference/`、`survey/`、integration 稳定页 | 对应任务开始时按索引定点读 |
| L3 | workstream notes/cards | 需要一手证据、历史改判或施工细节时读 |
| L4 | `archive/` | 仅追溯历史；不得从旧待办直接开工 |

新结论先落 L3，架构师验收后把承重摘要回填 L2；状态只更新 L1。L1 不复制 L3 的完整
证据，L2 不保存每日施工进度。这样既避免“失忆”，也避免恢复过程再次挤爆上下文。

Codex 会话另有一条外层恢复链：active context 是易失 working set；
`SessionStart(source=compact)` 只注入有界 Git 快照、L1 胶囊和会话定位器；项目文档保存
经裁决的语义记忆；本地 transcript 是按需回放的逐字证据档案。旧对话中的用户、actor 或
架构师主张都可能已过时，优先级始终低于 current code/data 与最新裁决。经验只有同时具备
“稳定落点 + 索引入口 + 任务触发器 + supersede 路径”才算可复用资产，不能只写不读。

## 4. 本仓库的具体判法

| 现象 | 裁决方法 |
| --- | --- |
| `metrics/` 与 `evaluators/` 都涉及指标 | 保留两层；前者是公式，后者是 artifact + policy + eligibility |
| 部分 method 有 `_worker.py` | 若用于依赖/进程隔离则保留；只抽共享 transport，不合并产品 worker |
| MemOS 有 `memos_lifecycle.py` | 保留；它承载 async task 的精确完成与失败传播，不是普通 helper |
| `methods/*_native_prompts.py` 很薄 | 它们是旧 import shim；canonical owner 已在 `prompts/author/`，按兼容预算退出 |
| `prediction.py`、`registry.py` 很大 | `prediction` 已按 planning/preflight/ingest/answer/parallel 拆成单向 leaf，原入口只保留 façade/orchestration；`registry` 仍须另批按 registration 变化原因裁定，不能因相邻债顺手开拆 |
| 多个 adapter 都有 `_request/_terminate_worker` | 共用 `methods/worker_transport.py`；产品 timeout/terminate policy 与 lifecycle 留在 adapter |
| benchmark 各有 recall evaluator | 纯 Recall 单源；gold view、排除政策与诊断保持薄 policy，不追求零 benchmark 文件 |
| 旧 `unified/native` 仍在代码里 | 分离“新 run 配置选择”与“旧 artifact 身份回读”；前者迁 TOML profile，后者保留兼容 |

## 5. 每次结构改动前的四问

1. **变化原因相同吗？** 两段代码未来会因同一需求一起改变吗？
2. **依赖方向正确吗？** 抽取后是否让稳定层依赖更不稳定的 CLI、产品或 benchmark？
3. **生命周期相同吗？** timeout、重试、cleanup、并发和错误传播是否真的一致？
4. **如何证明守恒？** 哪些输出、artifact、identity、隐私和真实副作用必须逐字或逐状态相同？

四问不能闭合时先盘点，不重构。

## 6. “瘦身完成”的判据

不以删除文件数或总代码行数作为 KPI。一个批次只有同时满足以下条件才算完成：

- 目标依赖倒置或重复责任已消失，并有自动边界测试；
- 生产行为、metric/prompt 字节、artifact/resume 语义没有暗变；
- 兼容层有明确消费者与退出门，没有新增调用方；
- 活跃 README、roadmap 与稳定参考同步更新，旧判词有 superseded/归档路径；
- 定向门和无 API 全量回归通过；
- 下一项没有因为“顺手”而被无限纳入当前批次。
