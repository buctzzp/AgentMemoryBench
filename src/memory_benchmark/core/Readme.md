# core 层说明

`memory_benchmark/core/` 是框架的稳定公共语言层：定义统一实体、provider v3 协议、
校验和领域异常。它不读取原始 dataset、不调用模型、不访问 method 数据库，也不计算 metric。

## 文件职责

- `entities.py`：`Dataset / Conversation / Session / Turn / Question / GoldAnswerInfo` 等领域实体；
- `provider_protocol.py`：唯一的新接入协议 `MemoryProvider` 及事件、检索、provenance 实体；
- `interfaces.py`：退出预算内的 legacy full-answer/resume/parity ABC，新代码不得依赖；
- `validators.py`：统一数据校验与公开 payload 私有字段扫描；
- `exceptions.py`：稳定领域异常；
- `results.py`：框架级摘要；
- `__init__.py`：经审查的稳定导出面。

## 领域层级与隐私边界

```text
Dataset
└── Conversation              # 一个 isolation unit
    ├── Session               # 有顺序与边界，可带 session time
    │   └── Turn              # 单 speaker 发言，可带 turn time / images
    ├── Question              # method 可见
    └── GoldAnswerInfo        # evaluator 私有，绝不进入 method
```

runner 在调用 method 前重建公开 conversation/question，并用
`validate_no_private_keys()` 递归检查。gold answer、gold evidence、judge label 与 scorer-only
metadata 只能写入 evaluator-private artifact。

## 唯一新接入协议：MemoryProvider v3

```python
class MemoryProvider(ABC):
    consume_granularity = "turn"  # turn | pair | session | conversation
    session_memory_report = False
    provenance_granularity = "none"  # none | session | turn

    def prepare(self, run_context): ...
    def ingest(self, unit: IngestUnit) -> IngestResult: ...
    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None: ...
    def end_conversation(self, ref: UnitRef) -> None: ...
    def retrieve(self, query: RetrievalQuery) -> RetrievalResult: ...
    def cleanup(self) -> None: ...
```

只有 `ingest()` 和 `retrieve()` 是必选算法面；其余钩子默认 no-op。框架先把
`Conversation` 规范成 `TurnEvent` 流，再按实例声明投递：

| consume granularity | ingest unit |
| --- | --- |
| turn | `TurnEvent` |
| pair | `TurnPair` |
| session | `SessionBatch` |
| conversation | `ConversationBatch` |

method 必须使用 `isolation_key` 隔离状态，不能自行遍历 benchmark 文件或读取私有 gold。
`end_conversation()` 返回即代表当前 isolation unit 的 memory 可检索；异步产品必须在这里
等待真实 terminal state，不能只提交后台任务。

`RetrievalResult` 的承重字段：

- `formatted_memory`：主 benchmark answer builder 使用的规范记忆；
- `prompt_messages`：可选作者校准/native readout；
- `items`：可选结构化检索项；
- `evidence`：逐题 valid/N/A/pending 事实，不能从 method 名静态猜；
- `metadata`：公开诊断信息。

主 prediction 不再接受 `BaseMemoryProvider`，`--method-class` 也必须直接实现 v3；迁移期
`provider_bridge.py` 已于 ws03 M1-E 删除。

## Legacy 退出边界

`interfaces.py` 暂留两类有明确消费者的旧接口：

- `BaseMemorySystem / BaseResumableMemorySystem`：旧 full-answer fake、Mem0 turn checkpoint
  和迁移期 runner 分支仍在使用；
- `BaseMemoryProvider`：只标记 Mem0/LightMem/A-Mem/MemoryOS 的旧 add/retrieve parity 面，
  供迁移等价性测试使用；generic prediction 与 custom loader 均拒绝它。

这不是第二套可选主协议。新 adapter、registry factory 和用户文档只能使用
`MemoryProvider`。删除剩余 ABC 前必须先替代上述真实消费者并跑全量门；不能按名字或文件
年龄猜测，也不能让新代码继续扩大消费者。

完整协议与粒度裁决见
[`spec-protocol-v3.md`](../../../docs/workstreams/ws02-phase1-matrix/spec-protocol-v3.md)。
