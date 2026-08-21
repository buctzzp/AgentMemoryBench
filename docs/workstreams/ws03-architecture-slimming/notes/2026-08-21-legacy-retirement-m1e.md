# M1-E legacy 退役、custom v3 与 registry 责任审计

日期：2026-08-21
范围：无 API、无 method 算法/metric/prompt/third-party/data/models/outputs 改动。

## 1. 为什么本批不是“见到 legacy 就删”

用户要求项目干净、规整，但同时提醒不要过度追求架构。M1-E 因此采用生产可达性退出门：

1. 搜索 import、CLI、factory、test 与文档消费者；
2. 区分“新 run 生产路径”“旧 artifact 只读兼容”“测试 parity 面”；
3. 只有消费者清零或已迁移才删；
4. 给仍有消费者的旧接口列出边界和退出条件；
5. 用架构强反例防止旧入口复活，再跑无 API 全量。

删除量不是 KPI。目标是只保留一套可创建新实验的 v3 协议，同时不牺牲历史 artifact 审计与
仍有价值的迁移等价性证据。

## 2. 已退役的生产闭环

### 2.1 MemoryOS 专用 runner

引用扫描确认 `runners/memoryos_locomo_full.py` 与
`runners/memoryos_locomo_smoke.py` 没有生产/CLI 消费者，只被两份同名测试自证。十家 method
已经通过通用 registered prediction 完成五格 smoke，继续保留专用入口会形成第二套
manifest/resume/answer/observability 语义。

本批删除两份 runner 与两份专用测试；架构门锁定文件和 import 均不得返回。受保护的历史
`outputs/memoryos-locomo-full-20260603/` 未触碰，旧 artifact 仍可离线审计。

### 2.2 provider v2 bridge

删除前唯一生产消费者是 `--method-class` custom 组合根；十家 registry factory 已全部返回
v3。custom path 现改为：

- 只加载并校验 `MemoryProvider` class，不在 preflight 提前构造可能启动模型/DB 的 probe；
- 无参构造、consume/provenance/session-report 声明运行期 fail-fast；
- 真实实例由 runner 生命周期创建和 cleanup；
- 固定使用 benchmark 注册的统一 answer builder；
- manifest 盖 `method_protocol=MemoryProvider`、`protocol_version=v3` 与具体消费粒度；
- 旧 `BaseMemoryProvider`、`v2-bridged` 与未知协议均拒绝。

迁移后删除 `core/provider_bridge.py`、bridge sentinel、bridge 专用测试和 summary sentinel 计数。
架构门扫描整个生产 package，禁止文件/import/class/`v2-bridged` 身份复活。

### 2.3 零消费者 ABC

`BaseMemoryRetriever` 没有生产或测试消费者，已从 `interfaces.py` 和 core export 删除。

## 3. 为什么没有把 interfaces.py 全删

当前仍有两类真实消费者：

| legacy 面 | current 消费者 | 当前边界 | 退出条件 |
| --- | --- | --- | --- |
| `BaseMemoryProvider` | Mem0/LightMem/A-Mem/MemoryOS 的旧 add/retrieve parity 测试 | generic/custom prediction 均拒绝；架构门限制消费者只能是这四家 adapter | parity 断言迁成纯 v3 产品调用证据后，移除四家继承与 ABC/export |
| `BaseMemorySystem` / resumable | Mock/旧 full-answer fake、Mem0 turn checkpoint 与 runner compatibility branch | registry factory 不得返回，不能成为新 adapter 教程 | 先把 fake 与 turn-resume 消费者迁到 v3 lifecycle/checkpoint 契约，再原子删除分支 |

因此“兼容桥”本批已经删除；剩余 ABC 不是可选择的第二条生产主线。为了避免债务扩大，稳定
文档只教授 v3，架构门锁住 `BaseMemoryProvider` 的精确四个生产标记位置。

## 4. Registry 责任审计

`methods/registry.py` 的 2422 行由三类同一组合根责任构成：

1. `MethodBuildContext / ResolvedMethodProfile / MethodRegistration`；
2. 十家 method 的 factory、source/build/embedding/efficiency/clean-retry 声明；
3. registration map 与纯查询/profile resolver。

本批修正了实质边界：所有 builder/factory/resolver 类型从 legacy system 收敛为
`MemoryProvider`，registry 源码不再出现 `BaseMemorySystem/BaseMemoryProvider`。它不持有实例、
不读 benchmark、无 metric/runner 副作用。

裁决：**本批不按 2422 行强拆。**按 method 拆十份 registration 文件会增加新增 method 的
导航与跨文件编辑点，而没有消除第二种变化原因；当前也没有重复运行时状态或 import cycle。
若后续出现独立 registry backend、持续 merge 冲突，或某一 method 的 composition 需要脱离
主 package 单独发布，再依据真实变化原因拆分。此裁决不是“永不拆”，而是避免用文件搬家冒充
减耦。

## 5. 文档 freshness

重写 `custom-method-onboarding.md`、`architecture-execution-flow.md` 与 core README；同步根
README、AGENTS、CLAUDE、architect onboarding、v3 spec current 注记与 survey 路由。历史
plan/note 保留原判词，只在仍会被当成 current 状态的 README 上补 superseded 链。

## 6. 验收

- 迁移承重定向集：`527 passed, 1 warning in 14.37s`；
- architecture/docs：`19 passed in 5.41s`；
- compileall：exit 0；
- 无 API 全量：`2196 passed, 3 deselected, 25 warnings, 29 subtests passed in 226.48s`。

前一基线为 2243 passed，本批净少 47。测试 diff 逐项复核为：删除 bridge 专用测试 6 个、
MemoryOS full 专用 runner 测试 38 个、MemoryOS smoke 专用 runner 测试 4 个，共 48 个死入口
测试；本批测试变更按 test function 计新增 9、移除 56，净差正好为 -47。差异由有意退役和
强反例替换完全解释，不是 pytest 漏收集。

唯一 warning 是 vendored LightMem 的既有 Pydantic v2 deprecation，不由本批引入。

## 7. 停手线

本批关闭后不顺手做以下工作：彻底删除 BaseMemorySystem/turn resume、重组全部 tests、重写
历史 survey 单卡、拆十份 registry、改变 artifact schema。它们必须各自证明消费者、迁移收益
与守恒门；否则会从“清理”滑向无限重构。
