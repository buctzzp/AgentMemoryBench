# Method TOML 配置与 answer prompt 构造政策

> **现行长期政策（2026-07-17 建立，2026-08-24 配置所有权与参数 provenance 修订）。**本文取代
> `dual-track-config-policy.md` 作为 method 参数选择与 answer prompt 构造的事实源。
> 旧 `config_track=unified/native` 实现和既有产物继续如实保留历史身份，但不再代表目标
> 配置模型。

## 0. 一句话裁决

每个 method 只维护一个 TOML 文件；method 主算法参数跨五个 benchmark 固定，作者实际跑过的
benchmark 可以增加少量 `author_<benchmark>` section。API runtime、benchmark answer/judge 与
execution 参数由各自配置层组合，不再复制进十家 method 参数。CLI 只选择明确 profile，不逐项
携带算法值，也不根据 benchmark 暗中自动切换。answer 配置选择的是**完整 prompt builder**，
不是一份尚未填变量的模板文件。

## 1. TOML 结构

目标结构如下；具体字段由各 method 的强类型 config 决定。迁移期旧
`smoke/official_full` section 保持严格只读兼容，但新 run 最终只组合一份主 method 参数：

```toml
[method]
# 跨五格固定的主 method 算法参数。只包含 upstream 公开的算法/产品旋钮。
answer_builder = "benchmark"

[author_locomo]
# 只有作者确实在 LoCoMo 跑过且参数有一手证据时才存在。
answer_builder = "<method>_locomo_official"

[author_longmemeval]
# 只有作者确实在 LongMemEval 跑过且参数有一手证据时才存在。
answer_builder = "<method>_longmemeval_official"
```

规则：

1. “跨五个 benchmark 固定”指**同一 method** 的主配置固定，不要求十个 method 使用
   相同的内部数值。
2. `smoke`/`pilot`/`official_full` 首先是 runtime 与 execution scope，不是三套 method 算法。
   smoke 不为省钱篡改 embedding、检索、update、summary、storage 等 method 算法参数；成本
   优先靠数据、conversation/question/turn 范围和并发缩小。低预算 runtime 使用
   `opencodego/ox-alpha-free`，正式 `official_full` 保持
   `primary/gpt-4o-mini`。这是流通验证而非效果对比，provider/model/transport 与必要的
   reasoning completion floor 必须进入 manifest/resume；细则见
   [`api-runtime-profiles.md`](api-runtime-profiles.md)。
3. `author_<benchmark>` 是稀疏的作者复现配置，不是主表默认，也不因为当前 benchmark
   同名就自动启用。作者没有跑过的格子不编造 section、不代替作者调参。
4. `author_<benchmark>` 写完整可审计的覆盖；主参数不使用隐式 benchmark merge。runtime 与
   execution 的组合由强类型 composition root 完成，并完整进入 manifest，不靠 TOML 复制。
5. embedding model、dimension、normalization、retrieval depth、chunk、update、summary 等若为
   upstream 公开算法旋钮，属于 method 配置。Phase 1 主比较对所有实际消费 embedding 且接口
   兼容的方法统一 `all-MiniLM-L6-v2`/384；完整 identity 与重建门必填。不消费 embedding 的
   profile 记 N/A，product default/author 配置只作显式补充校准。
6. 通用 `api_timeout_seconds`、`api_max_retries`、credential/base URL 与 runner `max_workers`
   不属于 method 算法参数。作者未暴露的内部 LLM temperature/max-token 常量也不为对称性强行
   变成配置；作者明确暴露且影响算法时才保留，默认锁 upstream 值。

### 1.1 参数值不是由“类型”裁定

不能用“布尔开关重点审、数值参数沿用默认”替代参数语义审计。凡会改变下列任一事实的参数，
无论类型是 bool、enum、number 还是 string，都属于 method identity，必须显式冻结并进入
manifest/resume：

- 是否执行抽取、压缩、分段、总结、更新、删除、反思或 rerank 阶段；
- 写入 memory 的内容、数量、粒度、lineage 或生命周期；
- retrieval candidate、排序、返回深度或 metric 资格；
- 修改后是否必须重建 method state。

参数值按三个不同问题取证，不能拿一种“默认值”同时回答：

1. **完整算法是什么**：读与当前代码版本相符的论文正文、附录、伪代码和消融实验，并追到
   current source 的有效调用分支。论文主流程中的组件若只在代码里作为开关暴露，不能仅因
   constructor 默认关闭就把它从完整算法中删掉。
2. **作者报告结果实际用了什么**：读匹配 commit/tag 的官方 benchmark harness、最终配置、
   启动命令、环境覆盖与公开日志/artifact；最终 effective value 高于配置类的声明默认。值只
   进入对应稀疏 `author_<benchmark>`，不得按 benchmark 暗换主配置。
3. **当前通用产品默认是什么**：读 README、config schema、constructor/factory 默认和最终
   product object/payload。只有没有更强官方覆盖、确认不是 demo/成本保护/兼容默认，且不会
   关闭命名算法阶段时，才可把 repo default 作为主配置候选。

README/example、release note/model card、官方 issue/PR/作者回复可用于消解矛盾；第三方复现只能
作为明确标注的辅助证据。关键开关或高影响数值还应做零 API mutation：翻转值后观察实际调用
阶段、payload/state 或 identity 是否变化，防止把 dead config 当算法能力。即便选定值等于
upstream 默认，也要在 TOML 与 manifest 中显式记录，避免依赖升级后静默漂移。

多方法第三方框架的配置可用来比较工程策略：它们可能选择真正的跨 benchmark 全局值、完全
沿用 repo default、逐 benchmark 调参，或通过 env/CLI 形成不可见混合。比较时必须追到最终
effective payload；这类证据能帮助设计 framework main profile，却不能替代 method 官方 harness
为 `author_<benchmark>` 提供 provenance。

LightMem `pre_compress` 是现行判例：通用 schema 默认 `False`，但论文完整流程包含预压缩，
官方 LoCoMo/LongMemEval 脚本与 README runnable example 均显式设为 `True`，current adapter
也能追到真实预压缩分支。因此主 profile 显式锁 `True`；不能用库的易用性默认覆盖实验身份。
十家逐项取证与进度入口见
[`ws05.1 method profile provenance`](../workstreams/ws05.1-method-profile-provenance/README.md)。

### 1.2 配置格式不是公平性合同

YAML、TOML、`.env` 或 Python 常量都只是声明载体；真正决定实验身份的是配置经过 merge、环境变量、
CLI、adapter fallback 和 product factory 后形成的 **effective config**。审计配置时必须追完：

```text
声明值 → merge/override → typed config → adapter/factory → 最终 product object/payload
```

2026-08-24 对 OmniMemEval、MemoryData、EverCore evaluation、MemEval、
agent-memory-benchmark 与 memorybench 的源码对照显示：YAML 常被选择是因为它便于表达嵌套
dict/list、多行 prompt、环境变量占位和深合并；但深合并也很容易让 benchmark 在运行时静默修改
method 参数。单一 YAML 或 `.env` 被多条命令复用，同样不能证明跨 benchmark 的 effective config
固定。完整证据见
[`third-party-framework-config-strategy-audit.md`](../workstreams/ws05.1-method-profile-provenance/notes/third-party-framework-config-strategy-audit.md)。

本项目当前继续使用 TOML：十家 method 的主算法配置是浅层、静态、有限的强类型字段，
`[method]` 与稀疏 `[author_<benchmark>]` 已能清楚表达；迁移文件格式只会增加兼容成本，不会自动
获得类型校验、职责分层、provenance 或公平性。若未来出现大规模矩阵、继承树或深层 backend
组合的真实需求，可以重新评估 YAML 或独立 planner DSL，但仍须先展开为同一强类型 effective
config，拒绝 unknown/duplicate key，并把最终身份写入 manifest/resume。

## 2. 运行选择

- 超参数值只写在 TOML；CLI 不提供几十个逐项覆盖参数。
- CLI 保留一个必要选择器，例如 `--profile official-full` 或
  `--profile author-locomo`。它只选择 TOML section，不携带配置值。
- 禁止看到 `benchmark=locomo` 就自动切到 `author_locomo`；主表在 LoCoMo 上仍使用
  `official_full`，只有显式作者校准 run 才选择 `author_locomo`。
- 禁止运行前手改同一个 section 再复用旧 run_id。manifest 必须记录 section 名、解析后的
  完整公开配置与足以阻断错误 resume 的身份。

## 3. answer prompt：选择 builder，不是选择模板

静态 prompt template 只是 builder 的一个素材。真正的实验资产是完整构造过程：

```text
TOML 选择 answer_builder
  → builder 读取公开 Question + RetrievalResult
  → 取得并校验官方要求的全部变量
  → 完成格式化、角色与消息顺序
  → 产出可直接交给 answer LLM 的 AnswerPromptResult.prompt_messages
```

### 3.1 主配置

`answer_builder = "benchmark"` 表示使用当前 benchmark 注册的统一 builder。同一 benchmark
下所有 method 共用该 builder。它可以填入 `formatted_memory`、question、question time、
category、choices 等公开变量，但不得读取 method 私有实现或 gold。

### 3.2 作者配置

`answer_builder = "<method>_<benchmark>_official"` 表示复现 method 官方 harness 的完整
answer 构造。官方模板若需要 speaker 分组、日期、检索条目、摘要、system/user 多消息或其他
变量，builder 必须逐项从正确的公开来源取得并填好；不能把模板文件本身冒充“prompt parity”。

作者 builder 必须同时满足：

1. **变量来源正确**：每个占位变量有公开字段或 method 检索输出锚，不拿 question time
   替 source time，也不拿任意 metadata 猜值。
2. **缺失 fail-fast**：必需变量缺失、类型错误或空白时在 answer API 前失败；不补空串、
   synthetic value 或静默省略。
3. **最终消息 parity**：验收最终 `PromptMessage[]` 的条数、role、顺序、内容、格式和必要的
   decoding 参数，而不只比较模板文本。
4. **隐私边界**：builder 只能消费公开 question、时间、选择项、method 检索结果及公开
   metadata；gold answer、gold evidence、judge label 永不可达。
5. **可审计 artifact**：最终构造好的 messages 与 builder 身份进入公开 answer artifact/
   manifest；不能只记录一个模板文件名。

`answer_builder` **不选择 judge**。主配置与作者校准都继续使用当前 benchmark 注册的统一
evaluator/judge LLM、prompt 与计分语义；不能因选了 method 官方 answer builder 就暗换 judge。
若未来确需复现 method harness 的专属 judge，只能另立带身份与指标 tier 的补充研究卡，经用户
拍板后实施，不能借 `author_<benchmark>` 默默带入。

现有代码中，benchmark unified builder 已直接返回 `AnswerPromptResult`；部分 method 官方路径
则由 adapter 在 retrieve 阶段提前构造 `prompt_messages`，后层 builder 只做验证/透传。后者
验收时必须沿调用链检查“变量产生 → 格式化 → 最终 messages”，不能只审最后一个函数。

### 3.3 Prompt 资产的代码所有权

prompt 目录按“谁定义实验口径”分层，而不是按“当前由哪个 adapter/evaluator 调用”分层：

- `src/memory_benchmark/prompts/benchmarks/`：五家主表 answer builder、
  benchmark judge prompt 与官方来源；不得 import `methods/` 或 `prompts/author/`；
- `src/memory_benchmark/prompts/author/`：LightMem、Mem0、MemoryOS 等作者校准
  builder/prompt；只服务显式 author profile；
- method 产品内部的 extraction/update/build prompt 仍归 method/vendored 实现，
  不复制进 framework prompt 包。

旧 `benchmark_adapters/*_prompt.py` 与 `evaluators/halumem_prompts.py` 仍是薄 re-export
shim，保证现有扩展可导入；新代码必须引用 canonical prompt package。三份仅供仓库内部
使用的 `methods/{lightmem,mem0,memoryos}_native_prompts.py` 已在 2026-08-14 M1-B 完成
内部 import 清零和 parity 门后删除。兼容层逐项按消费者与退出门处置，不能因为同属 shim
就成批删除，也不能继续承载新内容。

## 4. TOML 的边界

TOML 负责**保存数值与选择实现**；代码只负责两类不可避免的工作：

1. 把第三方库通过公开 seam 暴露、且确属算法配置的参数交给强类型 config；
2. 实现并注册需要逻辑构造的 answer builder。

API provider/model/base URL/credential/timeout/retry 归 runtime；workers/crop/queue 归 execution；
answer/judge decode 与 prompt 归 benchmark evaluation。把字段移出 method TOML 不等于把值隐藏到
代码里：组合后的公开配置仍须完整进入 manifest/resume identity。

如果两个官方目录改变了 update/retrieval/storage 等算法流程，它们是不同 implementation，
不能靠 TOML section 或旧 `native` 名称伪装成同一个 method 的参数差。

## 5. 与旧 `config_track` 的关系

- **2026-08-14 起的新 run 已完成迁移**：由公开 TOML profile 名、实际 section、
  `answer_builder` 和当前 build/embedding 组成 `MethodRunIdentity v1`；这些字段与解析后的
  method config、API runtime 一同严格参与 resume。
- 分层输出路径现在是 `.../{smoke|formal}/{profile}/{run_id}`。旧目录中的
  `unified/native` segment 不移动、不重命名，新 run 也不会探测或复用旧路径。
- CLI `--config-track native` 不再能创建新 run；显式 `--config-track unified` 只发弃用警告且
  不改变行为。旧 `predict --profile ...` 写法仍分阶段弃用，正式入口为
  `predict smoke` 或 `predict formal --profile <name>`。
- `TrackIdentity v1` parser、旧 native bundle 和 evaluate/cost artifact 回读长期保留；旧产物
  不改写、不假装来自新政策。新 run 不能同时写 `run_identity` 与旧
  `config_track/track_identity/contract_version` 字段。
- 新运行模型不再强铺两条流水线：5×10 主 smoke 使用 `smoke`；正式主表默认
  `official-full`；作者配置只在确有复现价值、预算和一手参数时显式选择。

## 6. 实施日程

1. **现在已完成**：政策落盘；不改既有实验史，不触发真实 API。
2. **2026-08-14 状态**：MemBench canonical split、RetrievalEvidence 与 5×10 主 smoke
   均已关闭。旧“当前主线”只属历史，不再作为恢复动作。
3. **2026-08-14 ws03 M1-B 已完成（迁移基线）**：十家 `smoke/official_full` section 均显式声明
   `answer_builder="benchmark"`；新 loader/registry 把 framework envelope 与 method dataclass
   严格分离；新 manifest/resume/output identity 已切换至 `MethodRunIdentity v1`；旧 artifact
   只读回读保持。当前只注册 `benchmark` builder，不凭已有 prompt 文件虚构任何作者 profile。
4. **2026-08-24 ws05 再迁移**：开始把上述两份重复 section 收敛为一份 method 主参数，
   runtime/execution 独立组合；旧 section 与 artifact 只读兼容，完成前不得删旧 parser。
5. **逐 method 到性能阶段时**：作者跑过的 benchmark 才补
   对应 author section。Phase 1 不做五个 benchmark 各自 sweep，也不追求 smoke 分数最优。
   新 `author_<benchmark>` section 必须同时注册经过最终消息 parity 验收的完整 builder；名字
   未注册或变量链未闭合时在 API/runtime 前 fail-fast。
6. **2026-08-24 参数 provenance 门**：扩大 pilot 前由 ws05.1 逐家核对完整算法阶段、官方
   benchmark effective config、完整 answer builder 与 method harness judge 资产。该任务是
   语义冻结，不做参数 sweep、不调用真实 API；未闭合的作者配置不得用现有 prompt 文件名冒充
   可运行 profile。
