# Custom Method Onboarding（provider v3）

本页只讲 `--method-class` 的轻量接入。项目维护的十家内置 method 还要进入 TOML、
source identity、效率观测和 registry；普通用户验证自己的 memory method，不必先完成这些
白盒工程。

## 1. 最小契约

自定义类必须：

1. 继承 `MemoryProvider`；
2. 可无参数构造；
3. 声明 `consume_granularity`；
4. 实现 `ingest()` 与 `retrieve()`；
5. 用框架发放的 `isolation_key` 隔离不同 conversation。

```python
from memory_benchmark.core import PromptMessage
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    TurnEvent,
)


class MyMemory(MemoryProvider):
    """最小 turn 粒度自定义 provider。"""

    consume_granularity = "turn"
    provenance_granularity = "none"

    def __init__(self) -> None:
        """初始化按 isolation key 隔离的内存。"""

        self._memory: dict[str, list[str]] = {}

    def ingest(self, unit: TurnEvent) -> IngestResult:
        """写入框架已经规范化的一个 turn。"""

        self._memory.setdefault(unit.isolation_key, []).append(
            f"{unit.speaker_name or unit.role}: {unit.content}"
        )
        return IngestResult()

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """只检索并格式化记忆，不在这里回答问题。"""

        memory = "\n".join(self._memory.get(query.isolation_key, ()))
        return RetrievalResult(
            formatted_memory=memory or "No memory retrieved.",
            # 主 smoke/formal 使用 benchmark builder；本字段仅为可选 native 资产。
            prompt_messages=(
                PromptMessage(role="user", content=memory),
            ) if memory else (),
        )
```

`consume_granularity` 与 `ingest()` 的入参一一对应：

| 声明 | 入参 |
| --- | --- |
| `turn` | `TurnEvent` |
| `pair` | `TurnPair`（允许 orphan/dangling 单边） |
| `session` | `SessionBatch` |
| `conversation` | `ConversationBatch` |

框架拥有数据迭代、事件顺序、聚合和 session/conversation 边界；method 不应自行读取
benchmark 文件。需要 flush 或完成屏障时覆写 `end_session()` / `end_conversation()`；需要
连接数据库或关闭后台资源时覆写 `prepare()` / `cleanup()`。这些钩子默认都是 no-op。

## 2. Retrieve 输出

`retrieve(query)` 返回 `RetrievalResult`：

- `formatted_memory`：必填，主 benchmark answer builder 的唯一 method 输入；
- `prompt_messages`：可选，仅供有证据的作者校准 builder/native readout；
- `items`：可选结构化命中项；只有当前 memory 的 provenance 与 ranking 真实有效时才填；
- `evidence`：逐题声明 valid/N/A/pending，不能为了算 Recall 伪造；
- `metadata`：公开诊断字段，不能含 gold/evidence label/API secret。

`RetrievalQuery` 已带 `query_text`、`question_time`、`top_k`、`purpose`、
`isolation_key` 和可选公开 `source_question`。不要从全局变量猜 conversation，也不要让
gold answer、gold turn id 或 judge label 进入 method。

## 3. 运行

```bash
uv run memory-benchmark predict smoke \
  --root . \
  --method-class my_project.my_adapter:MyMemory \
  --benchmark locomo \
  --run-id my-memory-locomo-smoke \
  --allow-api \
  --conversations 1 \
  --rounds 3 \
  --questions-per-conversation 1 \
  --workers 1
```

该入口固定使用 benchmark 注册的统一 answer builder，不接受旧
`BaseMemoryProvider.add/retrieve` 或 `BaseMemorySystem.get_answer`。类只在校验阶段加载，
不会为了“探测接口”提前构造一份可能启动数据库/模型的实例；真实实例在 runner 生命周期
内构造并 cleanup。

## 4. 并行、resume 与观测边界

默认 `workers=1`。只有用户显式传
`--workers N --allow-unsafe-custom-parallel` 才会为每个 worker 构造独立实例；这表示用户
自行保证外部数据库、collection、文件和 namespace 并发安全，不是框架替黑盒后端背书。

- `failed_answer`：记忆已经完成，可在 formal run 中只补未答问题；
- `failed_ingest`：可能半写，custom path 没有可证明的 clean hook，默认 fail closed；
- smoke 不支持 resume；
- 框架记录公开输入、retrieval artifact、answer、framework answer LLM 与可见 latency；
- 黑盒 method 内部的 LLM/embedding/database 调用不会被自动猜测或伪造 observation。

正式纳入项目对比表时，不再使用轻量 custom path；按
[method 接入清单](method-integration-checklist.md) 完成官方源码、产品接口、五格输入、
算法资格、TOML、source identity、失败清理、效率观测和 B11 证据。
