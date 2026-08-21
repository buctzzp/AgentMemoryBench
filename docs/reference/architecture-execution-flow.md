# AgentMemoryBenchmark 当前架构与执行流程

本页描述 current main 的稳定结构，不记录每日施工状态。当前任务看
[`docs/roadmap.md`](../roadmap.md) 和唯一活跃 workstream README；协议细节看
[`spec-protocol-v3.md`](../workstreams/ws02-phase1-matrix/spec-protocol-v3.md)。

## 1. 设计目标与边界

框架比较的是 memory method 在统一 benchmark 输入、answer builder 与 evaluator 下的行为：

```text
raw benchmark
  → BenchmarkAdapter（规范化 + 私有 gold 分离）
  → event stream + provider v3（写入、边界完成、检索）
  → benchmark answer builder + framework answer LLM
  → public artifacts / private labels
  → artifact-only evaluator → metric
```

结构优先级依次是：科研有效性、隐私与失败可见性、可复现、可维护；不是目录对称或文件最少。
具体判据见 [`code-structure-principles.md`](code-structure-principles.md)。

## 2. 稳定分层与依赖方向

```text
CLI
 └─ registered application service
     ├─ benchmark registry / adapter
     ├─ method registry / adapter
     ├─ prediction runner leaves
     └─ core contracts

artifact evaluation
 ├─ evaluator policy / eligibility
 ├─ pure metrics
 └─ prompt assets / judge client
```

- `core/`：实体、v3 协议、校验、异常；无 I/O；
- `benchmark_adapters/`：raw source → canonical dataset + evaluator-private gold；
- `methods/`：v3 ↔ 产品接口翻译、产品生命周期与 source identity；
- `runners/`：规划、preflight、ingest、answer、parallel、operation-level 编排；
- `metrics/`：不读 artifact/benchmark/method 的纯公式；
- `evaluators/`：artifact、gold view、官方排除、资格、汇总与 judge；
- `prompts/`：benchmark builder 与作者校准资产；
- `observability/`、`storage/`：效率事实、日志、原子 artifact 与指纹；
- `cli/`：解析和用户交互，不被 runner 反向依赖。

AST 架构门锁住 `runners → cli`、`prompts → evaluators`、prediction 叶模块顺序、共享 worker
transport、provider bridge 退役等边界。

## 3. Canonical 数据与隐私

```text
Dataset
└── Conversation / isolation unit
    ├── Session
    │   └── Turn
    ├── public Question
    └── private GoldAnswerInfo
```

benchmark adapter 保留 raw 顺序、role/speaker、原文、时间、图片 caption 与稳定 source id；
只有证据支持的确定性规范化才能改变表示。runner 重建 public object 并递归扫描私有 key。
gold answer、target/evidence、judge label 与 scorer-only metadata 不可到达 method、公开 manifest
或 answer prompt。

## 4. 唯一新接入协议：MemoryProvider v3

provider 声明实例级 `consume_granularity`，框架把 canonical turn stream 聚合为：

```text
turn         → TurnEvent
pair         → TurnPair
session      → SessionBatch
conversation → ConversationBatch
```

框架调用顺序：

```text
prepare(run_context)
  → ingest(unit)*
  → end_session(ref)*
  → end_conversation(ref)   # 返回 = 当前 memory 已可检索
  → retrieve(query)*
cleanup()
```

`retrieve()` 只做 method-native query/retrieval/rerank/format，不生成最终答案。它返回：

- `formatted_memory`：主 benchmark builder 的 method 输入；
- 可选 `prompt_messages`：作者校准/native readout；
- 可选 `RetrievedItem[]`：真实结构化命中；
- `RetrievalEvidence`：逐题 valid/N/A/pending；
- 公开 metadata。

所有 registry factory 与 `--method-class` 都产出 `MemoryProvider`。旧 v2 bridge 与
MemoryOS 专用 prediction runner 已退役；Phase 1 旧 artifact 仍可 artifact-only evaluate，
但不能借旧入口创建新 run。

## 5. 三注册表不是全局 service locator

### Benchmark registration

声明 task family、variant、smoke policy、canonical loader、benchmark answer builder、
evaluator-private gold contract 与 prediction eligibility。

### Method registration

它是内置 method 的组合根：名称、TOML profile、source/build identity、v3 factory、实例级
consume granularity、worker/lifecycle policy、效率 observation 与 clean retry。它不持有运行时
method instance，不读数据集，不计算 metric，也不变成任意依赖注入容器。

`methods/registry.py` 虽然长，但当前内容因“新增或变更 method composition”同因变化；按 method
拆成十个 registration 文件只会增加跨文件编辑点。只有出现第二种独立变化原因或真实 merge
冲突，才继续拆分，而不拿行数当架构指标。

### Evaluator registration

声明 metric 名、适用 benchmark、API/依赖顺序与 factory。公式属于 `metrics/`；gold view 与
官方 policy 属于 evaluator，不能为了文件少把五家差异吞成一个万能 scorer。

## 6. Prediction 两条执行面

### 6.1 Conversation-QA

`runners/registered_prediction.py` 完成配置与依赖装配，`runners/prediction.py` 只保留
`run_predictions()` 和 summary façade；叶模块拥有：

1. `prediction_planning.py`：selection、resume work plan、状态；
2. `prediction_preflight.py`：manifest、协议/粒度/隐私强校验；
3. `prediction_ingest.py`：事件投递、边界、session report；
4. `prediction_answer.py`：retrieve → builder → framework reader → artifacts；
5. `prediction_parallel.py`：stable shard、isolated instance、heartbeat 与失败隔离；
6. `prediction_observability.py`：共享观测 helper。

单 worker/shared-safe method 可复用一个实例；依赖冲突或产品不支持共享线程的 method 使用
isolated worker，每个 worker 独立 state root。协调线程只合并公开 artifact，不共享 method
对象。并行必须与串行语义等价。

### 6.2 HaluMem operation-level

`runners/operation_level.py` 边写边测 extraction/update/QA/memory-type。它与普通 QA 的 gold
单位、调用顺序和 session-local memory report 不同，因此保留独立 runner；共享协议、manifest、
cleanup、效率与隐私契约，但不强迫共用一套编排。

## 7. Answer 与配置

新 run 由 method TOML section 选择完整 profile：

- `smoke`：低预算流通验证；
- `official_full`：正式主配置；
- 稀疏 `author_<benchmark>`：只有 method 官方确实跑过且一手 builder/参数闭合时才存在。

主 profile 使用 benchmark 注册的完整 answer builder；builder 收到 `formatted_memory`、question、
question time/options 等变量，产出最终 `PromptMessage[]`。旧 `unified/native config_track` 不再
选择新 run，只为历史 artifact 回读保留身份兼容。

API runtime profile、provider、model、transport、prompt/builder、method build 与 embedding
identity 都进入 manifest。secret/base URL 只从 `.env` 读取，不落 artifact。

## 8. Artifact、resume 与失败语义

新 run 先做只读 preflight，再创建目录。manifest 锁 dataset/source、variant、scope、method
profile/build、协议/粒度、answer/runtime、worker policy 与 observation contract。

- smoke 是 fresh sentinel，不 resume；
- formal 可按 manifest identity resume；
- `failed_answer` 且 ingest 完成时可只补未答 question；
- `failed_ingest` 只有 method 提供可证明的 namespace-local clean hook 才重试；
- cleanup/terminal state/worker failure 必须可见，不能写成成功；
- 旧 artifact 可以只读 evaluate，不等于允许旧代码继续生成新实验。

所有 JSON/JSONL 状态使用原子写；torn-tail 恢复只处理最后一条未完成 JSONL，不掩盖中间损坏。

## 9. 扩展与停手线

新增 benchmark 先锁 raw source、canonical role/time/id、异常账、gold group 与官方 evaluator；
新增 method 按 [`method-integration-checklist.md`](method-integration-checklist.md) 核对产品源码、
官方 benchmark harness、五格输入、生命周期、检索/lineage 资格、失败清理、效率、TOML 与 B11。

不要创建 method × benchmark 专用 runner；benchmark-specific 差异应进入 adapter/builder/policy，
method-specific 差异进入 adapter/lifecycle。也不要为“整齐”给每家造空 worker/lifecycle，或在
没有三个语义相同消费者前提前抽万能 helper。
