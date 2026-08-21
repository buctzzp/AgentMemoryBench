"""测试 provider v3 核心协议，不调用外部模型。"""

from __future__ import annotations

from memory_benchmark.core import MethodCapability
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    TurnEvent,
)


class TinyProvider(MemoryProvider):
    """最小 turn 粒度 provider，用于验证 v3 接口可实例化。"""

    consume_granularity = "turn"

    def __init__(self) -> None:
        """初始化测试用隔离状态。"""

        self.added: list[str] = []

    def ingest(self, unit: TurnEvent) -> IngestResult:
        """写入单个规范 turn event。"""

        self.added.append(unit.turn_id)
        return IngestResult()

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """返回 framework answer builder 可消费的格式化记忆。"""

        return RetrievalResult(
            formatted_memory="Alice likes tea.",
            metadata={"strategy": "tiny", "query": query.query_text},
        )


def test_memory_provider_ingests_declared_unit_and_returns_retrieval_result() -> None:
    """v3 主接口应接收声明粒度载荷并返回非空 formatted_memory。"""

    provider = TinyProvider()
    event = TurnEvent(
        role="user",
        speaker_name="Alice",
        content="I like tea.",
        timestamp=None,
        isolation_key="run_conv-1",
        session_id="s1",
        turn_id="t1",
    )
    query = RetrievalQuery(
        query_text="What does Alice like?",
        isolation_key="run_conv-1",
        question_time=None,
        top_k=10,
        purpose="qa",
    )

    ingest_result = provider.ingest(event)
    retrieval = provider.retrieve(query)

    assert ingest_result is not None
    assert provider.added == ["t1"]
    assert retrieval.formatted_memory == "Alice likes tea."
    assert retrieval.metadata == {
        "strategy": "tiny",
        "query": "What does Alice like?",
    }


def test_memory_retrieval_capability_is_public_contract() -> None:
    """capability 层保留 memory_retrieval，供 registry 做兼容性声明。"""

    assert MethodCapability.MEMORY_RETRIEVAL.value == "memory_retrieval"
