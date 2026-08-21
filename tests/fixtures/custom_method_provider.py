"""pytest 用的用户自定义 provider v3 fixture。"""

from __future__ import annotations

from memory_benchmark.core.provider_protocol import (
    IngestResult,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    TurnEvent,
)


class FixtureCustomMemory(MemoryProvider):
    """最小用户 provider：把 turn event 文本存在隔离空间内。"""

    consume_granularity = "turn"

    def __init__(self) -> None:
        """无参数构造，符合用户轻量接入契约。"""

        self._memory_by_isolation: dict[str, list[str]] = {}

    def ingest(self, unit: TurnEvent) -> IngestResult:
        """逐 turn 写入公开历史。"""

        self._memory_by_isolation.setdefault(unit.isolation_key, []).append(
            f"{unit.speaker_name or unit.role}: {unit.content}"
        )
        return IngestResult()

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回 framework answer builder 可消费的格式化记忆。"""

        memory = "\n".join(self._memory_by_isolation.get(query.isolation_key, []))
        return RetrievalResult(
            formatted_memory=memory or "No memory retrieved.",
            metadata={"answer_context": memory or "No memory retrieved."},
        )
