# ws05.1 规格：method profile provenance contract

## 1. 范围

覆盖 Phase 1 十家 method：LightMem、A-Mem、Mem0、MemoryOS、MemOS、SimpleMem、Letta/MemGPT、
LangMem、EverOS、Graphiti OSS。每家同时审查两条轴：

1. **prompt 轴**：作者在哪些 benchmark 上公开测评；最终 answer builder、消息 role/顺序、全部
   变量来源、decode 参数、parser 和 method harness judge 资产是什么；
2. **parameter 轴**：完整算法包含哪些阶段；upstream 公开参数的默认、官方实验 effective value、
   current main value及其真实调用语义是什么。

不在范围：参数 sweep、为未跑过的 benchmark 调优、真实 API、正式效果复现、统一替换 benchmark
主 judge、重新审计 frozen benchmark 数据。

## 2. 四种身份必须分开

| 身份 | 回答的问题 | 允许来源 | 配置落点 |
| --- | --- | --- | --- |
| paper identity | 论文声称的完整算法是什么 | 匹配版本的正文、附录、伪代码、消融 + source call path | provenance 记录；必要时约束主/作者 profile |
| author-reported identity | 某篇结果真正怎样运行 | 官方 benchmark repo/harness、最终配置、命令、公开日志/artifact | 稀疏 `author_<benchmark>` |
| current product identity | 当前公开产品默认怎样运行 | tagged current source、schema、factory、最终 object/payload | 主配置候选或 product-default 补充身份 |
| framework main identity | 五 benchmark 主表采用什么 | 完整算法约束 + 跨 benchmark 公平裁决 + controlled embedding 政策 | `[method]`，跨五格固定 |

四列数值可以相同，但证据与含义不能合并。paper 与 current repo 不对应时必须锁版本并声明
不可直接复现；不能用最新版默认倒推旧论文结果。

## 3. 证据取得顺序

### 3.1 已有本地资产优先

1. `third_party/methods/MANIFEST.md` 锁定的官方产品/论文/评测仓库；
2. method integration 页与已验收 evidence note，用于避免重复调查；
3. 与 source lock 对应的论文正文、附录、消融、README、examples、eval/benchmark scripts；
4. current source 的 config schema、constructor/factory、调用点和最终 payload。

已有 note 是检索入口，不替代 current source 复核。测试只作行为证据，不可单独覆盖论文、源码或
官方 harness。

### 3.2 本地缺失时

按官方论文链接、官方 GitHub owner/org、README citation 与 release/tag 搜索专用评测仓库；再看
官方 model card、release note、公开 artifact/log、issue/PR 和作者回复。只有身份、license、commit
或可重放版本闭合后，才登记进 MANIFEST/fetch 流程。随机 fork、博客和第三方复现只能标
`SECONDARY`，不得生成 `author_*` 身份。穷尽可定位的一手入口仍无源码时，记录检索日期、查询面
与 `SOURCE_UNAVAILABLE`，不得根据论文描述臆造 prompt。

### 3.3 第三方多方法框架只作比较证据

`第三方框架参考/` 用来回答“现有框架怎样组织跨 benchmark 配置”，不直接回答“method 作者
当年用了什么”。先筛出同时覆盖至少两个 method、两个 benchmark，且能追到有效配置 merge 与
最终 product payload 的框架，再逐项记录：

- 一个 method 是否只有一份全局配置，还是 method × benchmark 分叉；
- 值来自 upstream default、框架硬编码、作者 harness、论文表格，还是没有 provenance；
- CLI/env/YAML/代码的覆盖顺序，最终 effective config 是否可追；
- embedding、build LLM、answer/judge、top-k 与算法开关是统一、沿默认还是逐格不同；
- framework 是否把 runtime 参数与 method 算法参数混写；
- source version、manifest、resume/rebuild identity 是否足以阻止静默漂移。

结论按 `TRUE_GLOBAL`、`PER_BENCHMARK`、`REPO_DEFAULT`、`HYBRID_OR_HIDDEN`、
`INSUFFICIENT_EVIDENCE` 分类。可以借鉴其配置结构和失败判例，但不能用第三方框架的选择为本项目
`author_<benchmark>` 盖章；若其 vendored 文件恰来自可验证的 method 官方仓库，仍须回到官方
source identity 独立核实。

## 4. Prompt 闭合合同

每个 method × official benchmark 至少记录：

- source repo/commit/path 与 benchmark/data version；
- build/ingest 与 retrieve 的官方调用拓扑；
- answer template 及其所有占位变量来自哪个公开字段；
- 最终 `PromptMessage[]` 的数量、role、顺序和逐段内容；
- model、temperature、max_tokens、top_p、response format、reasoning/thinking 参数；
- output parser、abstention/choice/日期等特殊路由；
- method harness 是否另带 judge，以及它与 benchmark 官方 judge 的关系。

只复制模板、不填全变量，或只比较模板文本而不比较最终 messages，都记 `INCOMPLETE`。
`answer_builder` 不自动选择 judge；method 官方 judge 只登记，若将来纳入必须另立 metric identity、
tier 与用户裁决。

## 5. Parameter 闭合合同

每个 method-owned 开关/枚举与高影响数值填写：

| 字段 | 说明 |
| --- | --- |
| parameter path/type | TOML 字段及最终 upstream 参数 |
| upstream default | schema/constructor 的 current 默认 |
| paper role | 是否出现在主流程、伪代码或消融 |
| official effective values | 逐个作者跑过的 benchmark 记录最终值 |
| current main value | 当前 `[method]` 解析值 |
| effective call site | 控制的分支、公式、payload 与 backend 限定 |
| classification | core stage / high-impact hyperparameter / compatibility extension / runtime / dormant |
| state impact | 是否改变 memory 内容、索引、ranking、metric 资格，是否要求重建 |
| ruling | main 固定值、author override、N/A、pending 或 source unavailable |

关键值做零 API mutation；若翻转后生产调用/state/identity 都不变，先调查 dead/overridden config，
不能继续把它当有效算法旋钮。数值默认只有在没有更强官方覆盖、不是 demo/成本保护默认、且不关闭
完整算法阶段时才可直接采用。

## 6. 配置与实现边界

- 主 `[method]` 跨五 benchmark 固定，不按 benchmark 自动调参；
- `author_<benchmark>` 只为作者实际跑过且一手值闭合的格子建立；
- author harness 若改变双写、namespace、batching、storage/update/retrieval 拓扑，先判
  implementation variant，不能只靠 TOML 名称伪装；
- upstream 未公开的内部温度/阈值不为“配置齐全”强行暴露；但必须记录其 source-locked 常量；
- 改变 build identity 的任何字段必须进入 manifest/resume，并用 fresh state 重建；
- framework runtime、credential、timeout/retry、workers、crop 不回流 method TOML。

## 7. 停工条件

- 论文与仓库版本无法对应，且差异会改变算法拓扑；
- 官方 prompt/参数依赖私有仓库、托管服务或不可定位 artifact；
- source/license/owner 身份不清；
- 官方 harness 要求把 gold/private label 暴露给 method；
- 复现需要修改第三方算法核心，而非公开 seam/config；
- 参数证据矛盾无法由 current call path、最终 effective config 或作者一手回复消解。

命中时保留证据并交回架构裁决，不用“最合理猜测”补齐 author profile。
