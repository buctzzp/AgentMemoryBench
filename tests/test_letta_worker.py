"""测试 Letta 独立 worker 的 transport 与精确 usage 契约。"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from memory_benchmark.methods.letta_worker import _WorkerEngine


pytestmark = pytest.mark.unit


def test_letta_worker_opencodego_transport_disables_thinking_without_mutation() -> None:
    """opencodego 只追加 transport override，不原地修改上游请求。"""

    engine = _WorkerEngine()
    engine.config = {"provider": "opencodego"}
    request: dict[str, Any] = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "hello"}],
        "extra_body": {"existing": "kept"},
    }

    transported = engine._transport_request(request)

    assert transported == {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "hello"}],
        "extra_body": {
            "existing": "kept",
            "thinking": {"type": "disabled"},
        },
    }
    assert request["extra_body"] == {"existing": "kept"}


def test_letta_worker_primary_transport_is_semantics_preserving() -> None:
    """primary profile 不追加 provider 私有字段，也不返回同一顶层对象。"""

    engine = _WorkerEngine()
    engine.config = {"provider": "primary"}
    request: dict[str, Any] = {
        "model": "gpt-4o-mini",
        "messages": [],
    }

    transported = engine._transport_request(request)

    assert transported == request
    assert transported is not request


def test_letta_worker_captures_chat_and_responses_usage_exactly() -> None:
    """两种 OpenAI-compatible usage 键均逐调用保真进入同一 ingest 缓冲。"""

    engine = _WorkerEngine()
    engine._begin_usage()
    engine._capture_usage(
        {"usage": {"prompt_tokens": 11, "completion_tokens": 3}}
    )
    engine._capture_usage({"usage": {"input_tokens": 7, "output_tokens": 2}})

    assert engine._finish_usage() == [
        {"input_tokens": 11, "output_tokens": 3},
        {"input_tokens": 7, "output_tokens": 2},
    ]


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"usage": None},
        {"usage": {"prompt_tokens": True, "completion_tokens": 1}},
        {"usage": {"prompt_tokens": 1, "completion_tokens": -1}},
    ],
)
def test_letta_worker_rejects_missing_or_inexact_usage(response: dict[str, Any]) -> None:
    """缺失、布尔或负数 usage 不得伪装成精确 API 观测。"""

    engine = _WorkerEngine()
    engine._begin_usage()

    with pytest.raises((RuntimeError, ValueError)):
        engine._capture_usage(response)

    engine._discard_usage()
    assert engine._usage_buffer is None


def test_letta_worker_rejects_persisted_llm_config_drift() -> None:
    """同 tag agent 的完整 LLM config 漂移时不得只比 model 后继续复用。"""

    engine, agent = _subject_validation_engine()
    agent.llm_config.context_window = 64_000

    with pytest.raises(RuntimeError, match="LLM config conflicts"):
        asyncio.run(engine._validate_and_initialize_subject("subject-1", agent))


def test_letta_worker_rejects_extra_sdk_tagged_passage() -> None:
    """skip-vector-storage profile 中 SDK tag 下只能存在唯一 initializer。"""

    engine, agent = _subject_validation_engine(extra_passage=True)

    with pytest.raises(RuntimeError, match="unexpected SDK-tagged passages"):
        asyncio.run(engine._validate_and_initialize_subject("subject-1", agent))


def _subject_validation_engine(
    *,
    extra_passage: bool = False,
) -> tuple[_WorkerEngine, SimpleNamespace]:
    """构造不导入 Letta runtime 的 subject identity manager 替身。"""

    engine = _WorkerEngine()
    engine.config = {
        "llm_model": "gpt-4o-mini",
        "model_endpoint": "https://example.invalid/v1",
        "provider": "primary",
        "context_window": 128_000,
        "max_tokens": 4_096,
        "temperature": 0.0,
        "max_steps": 50,
        "timeout_seconds": 30.0,
        "max_retries": 2,
        "human_block_limit": 10_000,
        "summary_block_limit": 1_000,
        "runtime_tag": "mb-runtime:test",
    }
    llm_config = SimpleNamespace(
        model="gpt-4o-mini",
        model_endpoint_type="openai",
        model_endpoint="https://example.invalid/v1",
        provider_name="openai",
        context_window=128_000,
        max_tokens=4_096,
        temperature=0.0,
        enable_reasoner=False,
        put_inner_thoughts_in_kwargs=False,
        parallel_tool_calls=False,
        handle="openai/gpt-4o-mini",
    )
    agent = SimpleNamespace(
        id="agent-1",
        agent_type=SimpleNamespace(value="sleeptime_agent"),
        enable_sleeptime=None,
        embedding_config=None,
        llm_config=llm_config,
        tags=engine._subject_tags("subject-1"),
        tools=[SimpleNamespace(name=name) for name in sorted(
            {
                "memory_finish_edits",
                "memory_insert",
                "memory_replace",
                "memory_rethink",
            }
        )],
    )
    blocks = [
        SimpleNamespace(
            id="block-human",
            label="human",
            description="Details about the human user you are speaking to.",
            limit=10_000,
        ),
        SimpleNamespace(
            id="block-summary",
            label="summary",
            description="A short (1-2 sentences) running summary of the conversation.",
            limit=1_000,
        ),
    ]
    initializer = SimpleNamespace(
        text="Initialized memory for subject subject-1",
        embedding=None,
    )
    passage_rows = [(initializer, None, None)]
    if extra_passage:
        passage_rows.append(
            (SimpleNamespace(text="raw turn", embedding=None), None, None)
        )

    class _BlockManager:
        """提供固定 block 集合的最小 manager。"""

        async def get_blocks_by_agent_async(self, **_kwargs: Any) -> list[Any]:
            """返回固定两块。"""

            return blocks

    class _ArchiveManager:
        """提供唯一 default archive 的最小 manager。"""

        async def get_or_create_default_archive_for_agent_async(
            self,
            **_kwargs: Any,
        ) -> Any:
            """返回唯一 archive。"""

            return SimpleNamespace(id="archive-1")

    class _AgentManager:
        """提供 archive 关系与 passage 查询的最小 manager。"""

        async def get_agent_archive_ids_async(self, **_kwargs: Any) -> list[str]:
            """返回唯一 archive id。"""

            return ["archive-1"]

        async def query_agent_passages_async(self, **_kwargs: Any) -> list[Any]:
            """返回 SDK tag 下的 passage。"""

            return passage_rows

    engine.server = SimpleNamespace(
        block_manager=_BlockManager(),
        archive_manager=_ArchiveManager(),
        agent_manager=_AgentManager(),
    )
    engine.actor = SimpleNamespace(id="actor-1")
    return engine, agent
