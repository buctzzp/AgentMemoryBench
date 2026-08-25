# M11 横向配置真值、源码闭包与 embedding 资产身份实施记录

日期：2026-08-25
状态：已验收
范围：M11-A / M11-B / M11-C；不恢复真实 pilot，不调用真实 API

## 1. 结论先行

本批把 M1-M10 的十家纵向证据转换成了新 run 可执行的横向合同：

1. 已证实的 dead/假控制面退出，而不是继续写进 TOML 假装可调；
2. EverOS 当前主轨的 hidden effective strategy 被显式注入并在最终产品对象验真；
3. 九家实际消费 embedding 的主配置统一指向同一份项目本地
   `models/all-MiniLM-L6-v2`，并锁内容、tokenizer、pipeline、维度和 loader runtime；
4. Letta 当前主轨明确为 embedding N/A，不为凑齐十家而伪造模型身份；
5. 十家新 run 改用分组件、确定性的 source closure v2，替代容易漏消费者的手写少文件 hash；
6. 旧 run identity v1 只读兼容，新 run identity v2 与 v1 严格 resume mismatch；
7. M1-M10 没有一家同时闭合完整 author source/data/final messages/decode/parser，因此本批不注册
   空壳 `author_<benchmark>`，也不把 method 官方 judge 暗换进主 evaluator。

这里的目标不是“参数越统一越公平”。第一性原则是：只有 upstream 公开 seam 能在不改变算法
topology 的前提下替换 embedding，才进入 controlled comparison；不消费 embedding 的 Letta 记 N/A。
作者复现、current product default 与 framework controlled main 继续是三种不同实验身份。

## 2. M11-A：配置真值

### 2.1 退出的 dead / 假控制面

| method | 退出字段 | 一手原因 |
|---|---|---|
| LightMem | `extract_threshold` | current online-soft 主轨没有 final consumer；保留会制造“可调但无效”的 manifest 身份 |
| A-Mem | `use_product_layer` | current adapter 只支持 product layer，布尔 selector 没有第二条合法实现 |
| Mem0 | 全局 `ingestion_chunk_size` | 真正 add topology 由 operation/event 聚合路径决定，该字段不控制产品调用 |
| MemoryOS | `longmemeval_prompt_profile` | retrieve-first 主轨不消费该字段；旧名还把产品 readout 与 answer prompt 混成一层 |

MemoryOS 强类型类从历史误导名 `MemoryOSPaperConfig` 收敛为 `MemoryOSConfig`；这是类型/所有权修正，
不是把 current PyPI product 冒充 paper reproduction。

### 2.2 EverOS hidden effective profile

EverOS adapter/worker 升到 v8/v4，通过官方 config seam 显式形成当前 controlled OME strategy：

- atomic facts：开；
- foresight：关；
- user-profile extraction：关；
- reflection：关；
- profile clustering：开。

产品 config reloader 运行后再读取最终 `StrategyMeta` 验真，避免“overlay 写了但最终对象被默认值覆盖”。
该 profile 是 current product 可执行的 controlled variant，不宣称 paper-complete；agentic recollection
仍是另一个 estimand，不夹带进本批。

## 3. M11-B：本地 embedding 资产合同

### 3.1 逻辑路径与产品路径分离

manifest/config 只保存项目相对逻辑路径：

```text
models/all-MiniLM-L6-v2
```

只有在第三方产品构造边界，才解析成当前项目根下的绝对路径。这样 artifact 不泄漏机器路径，
产品又不会受 worker cwd 影响。绝对路径、`..` 逃逸、错误根、缺失目录和 symlink 组件均 fail-fast。
Hub id/product-default profile 不被这个 resolver 偷偷改写。

### 3.2 当前可重放收据

内容闭包算法：按排序后的 POSIX 相对路径，对“路径长度 + 路径 bytes + 内容长度 + 内容 bytes”做
uint64 big-endian length prefix 后 SHA-256。当前 closure 包含 Torch/ST 真正消费的：

- Transformer/Pooling/Normalize 模块配置；
- `model.safetensors`；
- BERT config 与 SentenceTransformers loader config；
- tokenizer config/json/vocab/special token 资产。

当前收据：

| 轴 | 值 |
|---|---|
| closure schema | `length-prefixed-files-v1` |
| local content SHA-256 | `9c93593d1d7501d102d755cefc98dd8f7b02d088a606b9a3d328502f90372fce` |
| tokenizer SHA-256 | `517a76b5b3e9fb42ab62649a9d9642dd7cbe4b6ec1e4d04d8e029fd224ffab0a` |
| tokenizer | `BertTokenizer`，lowercase=true，max length=256 |
| pipeline | `Transformer → Pooling → Normalize` |
| pooling | mean-only，其他 pooling 关闭，effective `include_prompt=true` |
| dimension | 384；真实本地 `encode()` 探针输出 `(1, 384)` |
| runtime | sentence-transformers 5.5.1 / transformers 5.9.0 |

`config_sentence_transformers.json` 是 SentenceTransformers 5.5.1 的实际 loader 输入；初版闭包漏掉
它，Luna/max 红队指出后由架构师复核 runtime source 并补入，因此 content digest 从旧候选值
`a5c4…` 正确变为上述 `9c93…`。同一红队还发现只锁 `mean=true` 不足以排除 `cls/max/mean_sqrt`
同时开启；现已逐 flag fail-fast，否则产品输出可从 384 拼接成 768。

### 3.3 九家 controlled 与 Letta N/A

实际消费 controlled MiniLM 的九家为 LightMem、A-Mem、Mem0、MemoryOS、MemOS、SimpleMem、
LangMem、EverOS、Graphiti。每家仍分别声明最终 distance/normalization；“同一模型 bytes”不等于
“检索空间实现相同”。例如 A-Mem 的 Chroma 1.5.9 因安装了
`SentenceTransformerEmbeddingFunction`，最终 space 是 cosine；不能拿无 embedding function 的
fallback L2 探针替代真实构造。

Letta current main 的最终 `AgentState/Archive/initializer passage` 均为 embedding None，retrieve
只读 core blocks；其 embedding artifact 严格为 N/A。若未来启用 archival/vector search，必须新建
算法 variant、重开 metric/observability 并全量重建，不能在当前 profile 上补一个 MiniLM 名字。

## 4. run identity v2 与旧 artifact 边界

新 `MethodRunIdentity` 使用 v2，并新增 `EmbeddingArtifactIdentity`：

- `local_locked`：九家 controlled 本地资产，全部具体字段必填；
- `not_applicable`：Letta，全部具体字段必须为 null；
- `pending` / `provider_managed_unpinned`：同样强制负空间，不能夹带半份本地收据。

`controlled_embedding_v1` 与 `product_canonical_required_config_v1` 必须对齐 `local_locked`；v1 parser
显式拒绝 v2-only 的 `local_content_locked`，防止旧 shape 伪称已经锁 bytes。

兼容政策分两层：

1. `from_manifest_dict()` 负责历史 artifact 的严格结构读取；v1 重新序列化必须逐字 shape 等价；
2. 新 build/resume 会从当前 `project_root` 重新读取模型 bytes 生成 v2 identity，并与旧 manifest 严格
   比较。parser 单独看到格式合法的 64 位 digest 时不会声称它对应当前磁盘资产；这是历史可读性
   边界，不是 resume 绕过。

因此 v1 与 v2 永不 resume 匹配；旧 artifact 不改写、不升级标签，也不被重新解释成新 controlled
run。

## 5. 十家 source closure v2

### 5.1 设计

新 run 的 source identity 使用 `method-source-closure-v2`，每家按实际产品边界分成：

- `product_algorithm`；
- 必要时的 `runtime_asset`；
- `package_metadata` / `runtime_lock`；
- `framework_runtime`（adapter、worker、patch/bootstrap 等真实接线）；
- 当前 source factory 尚未 profile-aware 时，少数 method 的 `author_eval` 作为单独可见组件。

每个 include pattern 必须命中文件；任一文件跨组件、symlink、非普通文件、路径逃逸、Unicode/case
碰撞或读取中变化都会 fail-fast。manifest 存项目相对完整文件清单、分组件 count/hash 和总 hash，
不存绝对路径。recipe 变化或文件 bytes 变化都会改变 resume identity。

`author_eval` 是有意的保守 superset：当前主 run 不消费它，但 factory 还没有 answer-builder 上下文；
把它单独列出可避免未来作者 builder 上线后代码静默漂移，代价是作者资产变化也会保守地使主 run
失配。当前每份 identity 只有数十 KB，尚无证据支持为减少这点体积引入 profile-aware 双工厂；若
实测 artifact 膨胀或无关重建成为瓶颈，再拆为独立 answer-builder source identity。

adapter 内原有 `build_<method>_source_identity()` 暂未机械删除：A-Mem 等 method-state schema 仍直接
消费其中部分函数。新 registered run manifest 的唯一 source factory 已切到中央 v2；旧 helper 属
state-local/legacy identity，待其消费者迁移清零后再退出，不能因名字相似贸然删除。

### 5.2 当前 closure 收据

| method | recipe | files | aggregate SHA-256 |
|---|---|---:|---|
| LightMem | `lightmem-main-v2` | 70 | `860fc055a557f1bc251ded269040c96f3cde10ef134e2b48b1b421edb8210692` |
| A-Mem | `amem-product-main-v2` | 7 | `90fb5fc0ecb01510603c2b6dde6b7d34409d6493a3e09ab0283c682947845be8` |
| Mem0 | `mem0-product-main-v2` | 149 | `b3b4c14f1991683af0dd2fc3af581fdeb6ccf182e8d7196f574be01767e15123` |
| MemoryOS | `memoryos-pypi-main-v2` | 12 | `0ac22450c5b825870b10c55359b7349cec8310db051be53d66cc84f69f0f8fbd` |
| MemOS | `memos-product-main-v2` | 385 | `873e271793450661491846ac8e4549b0efa2f38cbe407861b869c57a6b105c6d` |
| SimpleMem | `simplemem-text-main-v2` | 20 | `1e0d6407687938930505bddc1b6a47df9972f9ca6b3292857d251f3d4dbb1304` |
| Letta | `letta-sleeptime-main-v2` | 543 | `1c03e8adcba76b5ab17b6e9b1b602dc394b01e59a8f4c6fcf08e559149b8689a` |
| LangMem | `langmem-main-v2` | 31 | `c04f8a319af2daca732bd09a8d5cdbb2dc633c89f42c7771a099c6e2e01139c0` |
| EverOS | `everos-api-main-v2` | 296 | `c4e53e7e11ed536f7251bcc9b5f8f3e725f0a686d894c7e32073c46b84daebe4` |
| Graphiti | `graphiti-oss-main-v2` | 165 | `3103ce708dbf664ee79d626280f9c4462135339118ede022512d1eaee387d07f` |

Letta 的 `ai-memory-sdk` 源码没有 vendored；identity 明示
`v0.2.0@4494e00410469082bf298b8b03b7c9f93e244f14:source-unavailable`，不能用版本字符串冒充
本地内容 hash。

上述 hash 是实施时 current dirty tree 的验收收据；之后任何被闭包覆盖的真实代码变更都应自然
改变 hash。稳定合同是 recipe、文件选择规则和 manifest 重算，不是要求未来源码永远保持此值。

## 6. M11-C：作者配置与 judge 裁决

十份机制卡虽发现了 LightMem/Mem0/MemoryOS/A-Mem/EverOS 等作者 prompt 或 harness 资产，但没有
一家同时闭合“exact source + dataset revision + 全部 builder 变量 + final messages + decode + parser”
且可无歧义映射到当前 product identity。故：

- 当前新 run 仍只开放 `answer_builder="benchmark"`；
- 不创建 `author_<benchmark>` skeleton；
- official method judge 只留候选清单，不进入主 evaluator registry；
- paper/current product/historical harness 若算法不同，分类为 implementation variant，而不是用 TOML
  把它们揉成一个默认。

这是 `AUTHOR_NOT_READY` 的诚实完成，不是 M11 遗漏。后续真正做作者数字复现时，逐格新开校准批次。

## 7. 重建与 resume 矩阵

| 范围 | 新 run 处理 | 旧 artifact |
|---|---|---|
| 九家 controlled embedding consumer | fresh memory；v2 本地 bytes identity | 原样只读；不得标成 `local_locked` |
| Letta | source closure v2 变化，fresh run；embedding 仍 N/A | 原样只读 |
| 十家 method source | 新 `deterministic-component-closure` 与旧 shape 严格失配 | 不重写 source manifest |
| EverOS | v8 effective strategy profile + 新 source/embedding identity，必须 fresh | 旧 v7 只证明旧 profile |
| A-Mem / Mem0 / MemoryOS | Hub-style 名称切为项目本地 logical path，即使权重可能同源也不宣称历史等价 | 历史 run 不 resume |

这意味着下一轮 pilot 不能复用 M11 前的 method state。用户重新批准预算、规模和 run-id 前仍禁止
真实 API。

## 8. 调查型 subagent 收据验收

本批使用 `gpt-5.6-luna` / `reasoning_effort=max` 做只读、零 API 的 source closure、run identity、
embedding 资产与 Letta paper/product 调查。架构师没有把回报直接当裁决：

| 候选发现 | 风险 | 架构师复核与处置 |
|---|---:|---|
| v1 可伪称 `local_content_locked` | 高 | 本地构造反例复现；v1 parser 增显式拒绝 |
| controlled profile 可配 provider-managed artifact | 高 | 沿 profile→revision→artifact 验证；补强对齐规则 |
| Pooling 只验 mean=true | 高 | 读取 ST 5.5.1 Pooling 实现并做临时配置 mutation；补齐四组强反例 |
| loader config 漏闭包 | 高 | 核 runtime loader source；补文件并确认 digest 变化 |
| A-Mem distance 可能是 L2 | 高、且最终被推翻 | 复现真实 embedding function 构造，确认 `default_space()=cosine`；保留 cosine |
| direct adapter 自有路径 helper 较宽 | 中 | registered path 在 factory 前已统一校验；不把 general/author seam 强收窄，记录边界 |
| parser 不重算任意历史 digest | 中 | 定为“结构读取 vs current build/resume bytes 验证”边界，文档明确 |
| 极窄恶意 TOCTOU | 条件性 | 本地模型目录视为受信工作站资产；保留 stat-read-stat，不扩大安全工程 |

这体现长期验收原则：低风险 locator 可抽锚，高风险 identity/provenance/metric 结论必须由架构师
读取 final consumer 或运行最小反例；reviewer 的沉默不是完成标准。

## 9. 验收记录

已完成的零 API 门：

```text
tests/test_embedding_assets.py + tests/test_run_identity.py
37 passed in 2.45s

tests/test_source_closure.py + tests/test_method_registry.py
106 passed in 2.00s

SentenceTransformer(local_files_only=True) 实际加载
shape=(1, 384), max_seq_length=256, modules=Transformer/Pooling/Normalize
```

最终门：

```text
承重定向门：469 passed in 12.81s
文档标准门：7 passed in 3.29s
全量零 API：2297 passed, 3 deselected, 25 warnings, 29 subtests passed in 269.11s
git diff --check：clean
```

warnings 是既有 LightMem Pydantic、CLI deprecation 与 MemOS datetime/Pydantic serializer 画像；
没有真实 API、模型下载或新实验 artifact。上述结果关闭 M11-D，但不等于真实 pilot/效果已经运行。

## 10. 重读触发器

以后回答参数/算法问题优先读各家 integration 机制卡与 M1-M10 note；只有以下情况才重读论文或
全仓调查：

- upstream/paper/version/source pin 变化；
- 现有 locator 失效或出现反证；
- 新问题涉及机制卡未覆盖分支；
- 作者校准要真正注册；
- controlled embedding、产品 search recipe 或算法 topology 要改变。

不要在无新信息时从头重复调查，也不能把这份 2026-08-25 收据冒充未来 checkout 的 current truth。
