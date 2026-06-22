# AgentMemoryBench 项目阶段汇报草稿

本文档用于向老师汇报 AgentMemoryBench 当前建设进度、工程架构、实验可复现机制和后续风险。
它是可编辑 Markdown 草稿，不是论文终稿。

## 1. 项目定位

AgentMemoryBench 目标是建设一个可复现、可扩展、可审计的 Agent Memory Benchmark
集成框架。当前阶段聚焦 conversation + QA 类型任务：

```text
conversation history -> method 写入记忆 -> question -> method 输出 answer -> answer-level metric
```

当前第一类用户是实验使用者：直接运行已接入 method 的 benchmark。第二类用户是新 memory
method 研究者：只要实现统一 adapter，就能在相同 benchmark、相同 artifact 和相同 metric
下评测。

当前主线 benchmark 是 LoCoMo 和 LongMemEval；HaluMem、MemBench、Mem-Gallery 暂缓；
PrefEval 已移除。

## 2. 总体架构

核心流程：

```text
原始 benchmark 数据
  -> Benchmark Adapter
  -> 统一 Dataset / Conversation / Session / Turn / Question
  -> Method Adapter
  -> Prediction Runner
  -> 标准 prediction artifacts
  -> Evaluation Runner
  -> F1 / LLM Judge / category summary
  -> efficiency observations / logs / checkpoints
```

主要代码层次：

| 层 | 作用 |
| --- | --- |
| `core/` | 统一实体、接口、校验和领域异常 |
| `benchmark_adapters/` | 把原始 benchmark 数据转成统一 conversation-QA 格式 |
| `methods/` | 包装 Mem0、MemoryOS、A-Mem、LightMem 等第三方 method |
| `runners/` | 串联 predict、evaluate、resume、parallel 和 artifact 写入 |
| `evaluators/` | 只读取 artifact 计算 answer-level metric，不重新调用 method |
| `observability/` | Rich 进度、事件日志、token/latency observation |
| `storage/` | 标准输出目录、JSONL、manifest、fingerprint |

## 3. 数据与隐私边界

统一数据层级：

```text
Dataset
└── Conversation
    ├── Session
    │   └── Turn
    ├── Question
    └── GoldAnswerInfo
```

关键约束：

- 通过 `conversation_id` 隔离记忆，不设计 reset 接口。
- `Turn` 是一次单 speaker 发言；user+assistant round 会拆成两个 turn。
- `Question` 是 method 可见公开输入，可带 `question_time`、`category` 等公开字段。
- `GoldAnswerInfo` 只给 evaluator，不能传给 method。
- gold answer、evidence、judge label、LongMemEval `answer_session_ids` 等私有字段不能进入
  method public input。

## 4. Method Adapter 机制

统一 method 接口：

```python
add(conversations: list[Conversation]) -> AddResult
get_answer(question: Question) -> AnswerResult
retrieve(question: Question) -> RetrievalResult  # 可选
```

第三方 method 可以没有同名 `get_answer()`。如果官方仓库只提供检索接口，adapter 必须按论文
或官方实验脚本的 `retrieval/search + prompt + LLM` 路径包装成统一 `get_answer()`。

当前 method 状态：

| Method | 当前状态 |
| --- | --- |
| Mem0 | 使用 OSS Mem0 源码；LoCoMo/LongMemEval reader prompt 来自 Mem0 memory-benchmarks；已改为 isolated conversation 并发和 conversation-level resume |
| MemoryOS | LoCoMo 路径已跑过历史正式实验；LongMemEval adapter 仍需单独设计 |
| A-Mem | 已补齐 LoCoMo query keyword generation、category k、session time 和 conversation-level state 持久化 |
| LightMem | LoCoMo 已专门化为官方 `search_locomo.py` 风格并在 `add()` 后执行 offline update；LongMemEval 当前保持 online retrieve 路径 |

## 5. Prediction 运行逻辑

`predict` 只生成 method answer，不计算指标。

主要步骤：

1. 读取 method、benchmark、profile 和 variant。
2. benchmark adapter 构建统一 Dataset。
3. 生成 dataset fingerprint、method manifest 和 source identity。
4. 基于 manifest、checkpoint、`max_new_conversations` 和已完成 question 生成 work plan。
5. 对需要推进的 conversation 调 `method.add([conversation])`。
6. 对未完成 question 调 `method.get_answer(question)`。
7. 写出标准 artifacts、checkpoint、日志和 efficiency observations。

标准输出：

```text
outputs/<run_id>/
  artifacts/
    public_questions.jsonl
    evaluator_private_labels.jsonl
    method_predictions.jsonl
    conversation_prompts.jsonl
    efficiency_observations.prediction.jsonl
  checkpoints/
    progress.json
    conversation_status.json
    question_status.jsonl
  logs/
    run.log
    events.jsonl
  method_state/
  summaries/
  manifest.json
  config.redacted.json
```

## 6. Evaluation 运行逻辑

`evaluate` 只基于已有 artifacts 计算指标，不重新调用 method。

当前支持：

- LoCoMo F1。
- LoCoMo LLM judge。
- LongMemEval LLM judge。
- 通用 category breakdown：只要 question 带 `category`，answer-level metric 都应输出 overall
  和 by-category summary。

LLM judge 已支持 `--max-eval-workers` 并行评测。

## 7. 并行、分批和 Resume

当前已支持：

- 单 run 内 conversation-level 并行。
- isolated worker：不适合共享实例并发的 method 每个 worker 创建独立 method instance。
- question-level resume：已完成 question 不重复 answer。
- conversation-level resume：已完成 conversation 不重复 add。
- `max_new_conversations`：本次命令预算，不进入实验 identity，可用同一个 `run_id` 分批推进。
- `question_limit_per_conversation`：本次命令每个 conversation 的问题预算，也不进入 resume identity，
  后续可增加题数继续跑。

已修复的问题：

- isolated worker 失败时会记录 `error_type/error/traceback`。
- 一个 worker 失败后会设置协作取消信号，其他 worker 不再继续处理后续 conversation。
- registered isolated path 不再提前构造根 method instance，避免顶层 `method_state/qdrant`
  或 `history.db` 这类副作用。

仍需复核：

- 用 Mem0 真实 API 极小 smoke 验证上述失败治理和进度显示，再恢复 full。
- isolated worker 的中间进度还可以更细，避免单个长 conversation 时终端看似卡住。

## 8. 成本与效率观测

prediction 默认开启 efficiency observation；临时调试才显式传
`--disable-efficiency-observability`。

当前记录：

- `memory_build_total_latency_ms`
- `retrieval_latency_ms`
- `injected_memory_context_tokens`
- `answer_generation_latency_ms`
- LLM input/output tokens
- embedding input tokens 和 latency
- model identity 和本地/API 执行方式
- `measurement_source`

`measurement_source` 语义：

- `api_usage`：直接读取 OpenAI-compatible response usage。
- `tokenizer_estimate`：无法拿到 response usage 时用匹配 tokenizer 估算，不等同真实账单。

当前 Mem0/MemoryOS 能记录较精确 API usage。A-Mem query/answer 和 LightMem reader 已优先读取
API usage；二者第三方内部 memory build LLM 调用仍需进一步审计或 observer 插桩。

## 9. 灵活实验裁剪

当前支持：

- `--smoke-turn-limit N`：smoke profile 每个 conversation/instance 最多写入的历史 turn 或
  完整 round。
- `--smoke-conversation-limit N`：smoke profile 最多加载的 conversation/instance 数。
- `--question-limit-per-conversation N`：本次命令每个 conversation 最多回答的问题数；不进入
  resume identity。
- `--max-new-conversations N`：本次命令最多推进多少个未完成 conversation；适合 full 分批运行。

原则：

- smoke 可以裁剪历史规模，用于成本估算和链路调试。
- official-full 不随意截断历史 turn，保持官方实验语义。
- 分批预算不进入 manifest identity，避免下次 resume 被拒绝。

## 10. 新 Method 接入步骤

推荐流程：

1. 固定第三方源码版本，放入 `third_party/methods/`。
2. 阅读论文、README 和官方实验脚本。
3. 在 `docs/method-interface-inventory.md` 记录原生接口：
   写入、检索、回答、离线更新、配置注入、prompt 来源、模型、API key/base URL、状态持久化。
4. 编写强类型 config/profile。
5. 编写 adapter，实现 `add()` 和 `get_answer()`。
6. 注册 task family、capability、factory、source identity、model inventory。
7. 写 contract tests：
   基本 add/get_answer、private 字段隔离、conversation 隔离、resume、并行和 efficiency observation。
8. 先 fake/offline smoke，再真实极小 API smoke。
9. 通过后逐步扩大到 partial run 和 full run。

后续可以沉淀成 “method 接入 skill”：研究者提供 method 源码和说明，agent 按固定 checklist
自动生成 adapter、测试和接入报告。

## 11. 当前实验状态

| 实验 | 状态 |
| --- | --- |
| MemoryOS-LoCoMo 历史正式实验 | 已完成，有受保护输出目录 |
| LightMem-LoCoMo full | 已完成 prediction、F1/Judge summary |
| A-Mem-LoCoMo full-v2 | 已完成 prediction、F1/Judge summary；旧 run 因 session time bug 作废 |
| Mem0-LoCoMo full-v2 | 暴露并发失败问题；框架侧已修失败治理，需新 run_id 极小 smoke 复核 |
| LongMemEval-S smoke | Mem0/A-Mem/LightMem 极小 smoke 已完成；MemoryOS 暂未接入 |

## 12. 下一步优先级

1. 用 Mem0 新 run_id 做极小 API smoke，复核 isolated worker 失败治理、进度显示和 artifact。
2. 审计 A-Mem/LightMem 内部 memory build LLM 调用，尽量提升到 `api_usage` 级观测。
3. 修 Rich/third-party warning/tqdm 终端污染问题。
4. 完善 prediction artifact 瘦身的长期兼容策略。
5. 讨论 MemoryOS LongMemEval adapter 方案。
6. 整理 method 接入文档和未来接入 skill。
