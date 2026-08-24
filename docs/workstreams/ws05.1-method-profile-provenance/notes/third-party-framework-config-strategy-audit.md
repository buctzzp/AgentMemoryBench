# 第三方多方法框架配置策略审计

> 审计日期：2026-08-24。用途仅是回答“已有框架怎样组织跨 benchmark 配置”，不为本项目的
> `author_<benchmark>` 提供作者身份背书。所有结论都追到声明、覆盖和最终消费点；只看到 YAML、
> `.env` 或 README 不算闭合。

## 1. 判词

没有一个受审框架同时满足“同一 method 跨 benchmark 真正固定算法参数、配置职责分层、严格类型
校验、最终 effective config 可审计、并进入 resume/rebuild identity”。它们提供了三个有用样本：

1. **MemoryData**：method YAML 与 dataset YAML 物理分离，一份 method preset 被不同 benchmark
   复用；这是最接近 `TRUE_GLOBAL` 的外观，但 adapter 仍读取 `dataset_config/sub_dataset` 改变
   collection、prompt 和部分 fallback，且 method YAML 混有 answer/runtime/output 参数。
2. **EverCore evaluation**：system YAML 与 dataset YAML 分离，却公开支持
   `dataset_overrides` 深合并；这是明确的 `PER_BENCHMARK`，不是统一配置。
3. **MemEval**：不用 YAML 也能统一 answer LLM/embedding；但算法参数散落在各 system Python
   wrapper 的常量和构造器里，属于 `HYBRID_OR_HIDDEN`。它证明公平控制来自有效调用链，不来自
   文件后缀。

因此本项目维持 TOML，不迁移到 YAML。原因不是 TOML 天生更“先进”，而是现有 method 配置主要是
浅层、静态、强类型 section；TOML 配合严格 loader、unknown-key fail-fast、manifest/resume identity，
比换格式更符合当前目标。若未来需要大规模矩阵生成，应增加显式 planner/composition schema，而不是
让 YAML merge 隐式改写 method 主算法参数。

## 2. 审计范围与分类

| 框架 | source identity | 多 method × 多 benchmark | 主分类 | 深读结论 |
| --- | --- | --- | --- | --- |
| OmniMemEval | `MemTensor/OmniMemEval@0b1ea8d` | 是 | `HYBRID_OR_HIDDEN` | 每产品一份 `.env`，共享 answer/judge/top-k；产品参数不同，benchmark 脚本还会改产品行为 |
| MemoryData | `OpenDataBox/MemoryData@e7ecdbe` | 是 | `HYBRID_OR_HIDDEN`（声明层接近 `TRUE_GLOBAL`） | method/dataset 两份扁平 YAML；method preset 可复用，但最终 adapter 同时消费 dataset identity |
| EverCore evaluation | 本地快照目录名含 `29d555c…`，无 nested Git identity | 是 | `PER_BENCHMARK` | `dataset_overrides` 被递归深合并后再传 adapter；不同 dataset 可改变 system 参数 |
| MemEval | `ProsusAI/MemEval@807ae6d` | 是 | `HYBRID_OR_HIDDEN` | CLI 统一 LLM，embedding 多处硬编码统一；method 算法参数仍分散在 Python wrapper |
| agent-memory-benchmark | `vectorize-io/agent-memory-benchmark@aa9273a` | 是 | `REPO_DEFAULT` / `HYBRID_OR_HIDDEN` | CLI 只选 provider；不同 provider 在类内各用 env、常量和产品默认，无统一算法 schema |
| memorybench | `supermemoryai/memorybench@118209a` | 是 | `REPO_DEFAULT` / `HYBRID_OR_HIDDEN` | config 只管理 key/base URL；各 provider 在源码中使用不同 limit、embedding 与 prompt |

EverCore 快照不是独立 Git checkout；父仓 `git rev-parse` 不能证明它的 upstream commit。因此这里仅按
目录快照审计，不能把 `29d555c…` 升级成作者 source lock。

## 3. OmniMemEval

### 3.1 配置链

1. `env_examples/.env.<client>` 同时放产品参数、`TOPK`、answer/eval model 和 runtime retry/timeout；
   `env_examples/PARAMETERS.md` 明确 `--top-k` 覆盖 `TOPK`，而 product-specific template 是各产品
   的公共设置入口。
2. benchmark runner 用 `--env` 加载一份产品 `.env`，search 函数把 CLI/env 的 `top_k` 交给
   `client.search(...)`。
3. `scripts/client_factory/<product>_client.py` 在构造器读取产品 env，并在 add/search 最终 payload
   中消费。例如：
   - Mem0 把 `MEM0_SEARCH_THRESHOLD`、`MEM0_SEARCH_RERANK` 写进 search payload；
   - MemOS 分 cloud/local 两套 payload，并读取 preference、relativity、context format、search mode、
     dedup、rerank；
   - EverOS 读取 group/personal、search method、memory types、flush policy、async、profile；
   - Letta 的 ingest/eval/search backend、model、embedding、sleeptime 与 agent settings 都来自 env；
   - Graphiti 只有 sync add、batch、timeout 等较窄设置，产品内部模型由 server 侧决定。

这条链证明它不是“全部沿 repo default”：大量产品参数由框架显式选择。但它也不是跨产品统一算法
配置；只有 answer/judge/top-k 等评测层字段被统一。

### 3.2 benchmark 隐式覆盖

- `scripts/utils/streaming.py:24-27` 在单用户 streaming 且 frame=EverOS 时直接写
  `EVEROS_USE_GROUP=false`。
- `.env.everos` 自己列出 LongMemEval local preset，并包含 `EVEROS_LME_FLUSH_ONCE` 这种
  benchmark-specific knob。
- 同一模板对 LoCoMo 推荐 group/agentic，而 LongMemEval 注释推荐 personal/hybrid/flush-once。

因此“一份 `.env.everos` 被五条命令复用”不等于同一 effective config。主分类为
`HYBRID_OR_HIDDEN`。

### 3.3 可借鉴与风险

- 可借鉴：公共 answer/judge/runtime 字段有独立命名空间；产品 client 负责把配置追到最终 payload；
  top-k 有清楚的 env→CLI 覆盖顺序。
- 不照搬：credential、runtime、evaluation 与算法字段共居 `.env`；benchmark 脚本可以修改产品
  env；没有看到与本项目同等级的 typed manifest/resume identity 来锁最终有效配置。

## 4. MemoryData

### 4.1 配置链

1. CLI 接受 `--agent_config` 与 `--dataset_config` 两个独立 YAML。
2. `utils/initialization.py:39-70` 分别 `yaml.safe_load`，不做通用深合并；只有显式 ablation 会修改
   agent/dataset 字典。
3. `AgentWrapper(agent_config, dataset_config, ...)` 同时持有两份字典，并按 `agent_name` 分派产品
   initializer。方法参数主要来自 agent YAML，answer `max_tokens` 来自 dataset
   `generation_max_length`，collection/table/namespace、chunk fallback 和 benchmark prompt 又会读取
   `sub_dataset` 或 dataset config。
4. LightMem initializer 直接把 `messages_use/metadata_generate/text_summary/pre_compress/topic_segment/
   index_strategy/retrieve_strategy/update` 从 agent config 传入产品；缺值就使用 wrapper 自己写的
   fallback，而不是统一回到 upstream schema。

### 4.2 有效策略

一份 `hybrid_lightmem.yaml`、`sequential_mem0.yaml` 等确实能和多个 dataset YAML 组合，声明层接近
`TRUE_GLOBAL`。但以下事实使最终行为只能判 `HYBRID_OR_HIDDEN`：

- dataset 的 `generation_max_length` 改变 answer decode；
- `sub_dataset` 参与 prompt template、collection/table/namespace 和若干 runtime 选择；
- CLI `--chunk-size-ablation` 会同时覆盖 method `agent_chunk_size` 与 dataset `chunk_size`；
- agent YAML 把 method 算法、answer model/temperature、embedding endpoint、runtime 并发、artifact
  output 混在一份扁平 dict 中；
- loader 没有发现 unknown-key/type schema，initializer 广泛使用 `.get(default)`，拼错字段可能退回
  wrapper default。

### 4.3 对本项目的启发

物理分开 method 与 dataset 配置是正确方向；但“两个文件”不足以形成职责边界。本项目应继续让
benchmark evaluation、API runtime、execution 与 method algorithm 分属强类型 schema，并把最终
composition 写进 manifest。MemoryData 的扁平 preset 可作参数盘点线索，不能作 author provenance。

## 5. EverCore evaluation

### 5.1 配置链

1. `config/datasets/<dataset>.yaml` 保存 data/evaluator/judge；
   `config/systems/<system>.yaml` 保存产品、answer LLM、search 和 runtime。
2. `evaluation/cli.py:42-61` 定义递归 `deep_merge_config`；`:155-174` 若 system config 存在
   `dataset_overrides[dataset]`，就在创建 adapter 前覆盖 system config。
3. 合并后的 dict 在 `:228-255` 增加 `dataset_name`/clean flag，传给 adapter，并直接构造 answer
   `LLMProvider`。judge 则由 dataset config 构造。

`memos.yaml` 的 `dataset_overrides.longmemeval.batch_size=6` 是确定反例：默认 batch=10，LME 最终为
6。因此这个框架明确是 `PER_BENCHMARK`。

### 5.2 其他方法学差异

- README 一方面说所有系统 answer LLM 统一为 GPT-4.1-mini，另一方面又明确“每个 memory system
  使用自己的 official answer prompt”。这相当于统一 model、不统一 builder。
- system YAML 把 batch/retry/worker/wait 等 runtime 与 search/算法/answer 配置混在一起。
- YAML 的嵌套结构让 dataset override 很方便，但也让同名 system 的 identity 依赖运行时 merge；
  若 artifact 不保存展开后的 effective config，就无法只凭文件名复现。

可借鉴的是 dataset/system/evaluator 分层和显式深合并函数；本项目不采用其 benchmark 自动覆盖
method 参数的政策。

## 6. MemEval

MemEval README 声明同 LLM、同 embedding、同 scoring；runner 的 `--llm-model` 确实向全部 system
函数传同一个模型，LoCoMo/LongMemEval 共享 registry。多个 wrapper 又明确把
`text-embedding-3-small` 写入 Mem0、Graphiti、SimpleMem、MemU、OpenClaw 等产品路径。

但它没有独立 method config schema：

- top-k、embedding model、constructor kwargs 与 monkey patch 分散在
  `src/agents_memory/systems/*.py`；
- SimpleMem 通过 monkey patch 换 embedding；
- Hindsight、Memory-R1 等保留各自运行拓扑和模型约束；
- 输出的 `config` 只记录 architecture/infrastructure/LLM/judge，没有完整展开每家算法参数。

所以它是“**控制变量做得明确，但参数 provenance/identity 不完整**”的样本，分类
`HYBRID_OR_HIDDEN`。它也证明 YAML 不是统一配置的必要条件。

## 7. 两个只作负面样本的框架

### 7.1 agent-memory-benchmark

CLI 只选择 dataset、memory provider、mode 与 answer LLM；`get_memory_provider(name)` 构造各自类。
不同 provider 自行读取 env、使用 class constant 或产品默认，例如 Cognee 固定 BGE-small-384、
Hindsight embedded 固定 Gemini extraction、部分 provider 自己决定 top-k。没有发现覆盖所有 provider
的 method algorithm schema，也没有一条统一 embedding 政策。结论：`REPO_DEFAULT` 与
`HYBRID_OR_HIDDEN` 混合，不进入本项目 author 证据。

### 7.2 memorybench

`src/utils/config.ts` 只解析 API key/base URL；`createProvider` 无参数构造 provider 后只传 credential。
最终 limit 在 provider 源码中不同：Supermemory/Mem0 常用 30，Zep 分 node/edge，RAG/Filesystem
常用 10；RAG embedding 固定 `text-embedding-3-small`。它适合产品 smoke/横向体验，不适合作为
“十家跨 benchmark 统一算法配置”的参考实现，分类 `REPO_DEFAULT/HYBRID_OR_HIDDEN`。

## 8. YAML 与 TOML 裁决

### 8.1 为什么 ML 框架常用 YAML

本次源码给出的实际原因是：YAML 很适合深层 dict/list、dataset/system 两棵配置树、环境变量占位、
多行 prompt，以及 Hydra/OmegaConf 风格的组合与 override。EverCore 的
`dataset_overrides → deep_merge_config` 就是最直接例子。

### 8.2 为什么本项目当前不迁移

1. Phase 1 method 参数是有限、静态、浅层的强类型字段；`[method]` 与稀疏
   `[author_<benchmark>]` 用 TOML 已足够清楚。
2. 本项目真正需要的是 owner 分离、unknown-key/type fail-fast、effective identity、fresh-state
   rebuild 与 manifest/resume 锁；换 YAML 不会自动提供任何一项。
3. YAML 的自由嵌套和 merge 对本项目反而增加“benchmark 暗中改 method”的风险；EverCore 已提供
   一手判例。
4. 迁移会制造没有科研收益的格式 churn，并增加旧配置、文档、测试和 artifact 兼容成本。

### 8.3 将来何时重新评估

只有在出现下列真实需求时再讨论 YAML 或独立 planner DSL：大规模实验矩阵生成、可复用继承树、
需要声明式组合多 backend、或 TOML 无法清楚表达的嵌套对象。即使届时采用 YAML，也必须先解析为
同一强类型 effective config，拒绝 duplicate/unknown key，并把展开后的 identity 写入 manifest；
不能让 merge 规则本身成为隐藏算法。

## 9. 对 ws05.1 的直接约束

- 主 `[method]` 继续跨五 benchmark 固定；benchmark 只能改变输入合同和 evaluation，不能静默覆盖
  method 算法参数。
- author profile 允许 benchmark-specific，但必须显式选择、只为作者真实跑过的格子存在，并把最终
  builder/参数/topology 写入 identity。
- 统一 embedding、answer/judge/runtime 都必须追到最终调用对象；“所有配置文件都写了同一名字”
  不是证据。
- 每家 method 先完成论文/技术报告算法阶段图，再解释哪些参数必须显式开启；第三方 framework
  preset 只能作为差异线索，不能替代一手来源。
