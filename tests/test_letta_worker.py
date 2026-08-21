"""测试 Letta 独立 worker 的 transport 与精确 usage 契约。"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from types import ModuleType
from types import SimpleNamespace
from typing import Any

import pytest

from memory_benchmark.methods.letta_worker import (
    _RuntimeSecretRedactionFilter,
    _WorkerEngine,
)


pytestmark = pytest.mark.unit


def test_letta_worker_runtime_filter_redacts_endpoint_and_key_with_format_args() -> None:
    """第三方 `%s` 日志必须在 handler 写文件前同时清除 endpoint 与 key。"""

    endpoint = "https://private-runtime.example/v1"
    api_key = "secret-runtime-key"
    record = logging.LogRecord(
        name="httpx",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="HTTP Request: POST %s key=%s",
        args=(endpoint, api_key),
        exc_info=None,
    )

    assert _RuntimeSecretRedactionFilter(endpoint, api_key).filter(record) is True
    message = record.getMessage()
    assert endpoint not in message
    assert api_key not in message
    assert message.count("<redacted-runtime-value>") == 2


def test_letta_worker_installs_log_redaction_before_server_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """import 完成后必须先装脱敏，再构造可能发起产品请求的 SyncServer。"""

    order: list[str] = []

    class _AsyncManager:
        """模拟 SyncServer 暴露的最小异步管理器。"""

        async def create_default_organization_async(self) -> None:
            """模拟默认组织初始化。"""

        async def create_default_actor_async(self) -> SimpleNamespace:
            """返回最小 actor。"""

            return SimpleNamespace(id="actor-1")

        async def upsert_base_tools_async(self, *, actor: Any) -> None:
            """模拟工具初始化。"""

            assert actor.id == "actor-1"

    class _SyncServer:
        """模拟会在构造阶段触发产品日志的同步服务。"""

        def __init__(self, *, init_with_default_org_and_user: bool) -> None:
            """记录构造顺序并暴露三个异步 manager。"""

            assert init_with_default_org_and_user is False
            order.append("server")
            manager = _AsyncManager()
            self.organization_manager = manager
            self.user_manager = manager
            self.tool_manager = manager

    letta_module = ModuleType("letta")
    server_package = ModuleType("letta.server")
    server_module = ModuleType("letta.server.server")
    server_module.SyncServer = _SyncServer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "letta", letta_module)
    monkeypatch.setitem(sys.modules, "letta.server", server_package)
    monkeypatch.setitem(sys.modules, "letta.server.server", server_module)

    engine = _WorkerEngine()
    monkeypatch.setattr(
        engine,
        "_install_runtime_log_redaction",
        lambda: order.append("redaction"),
    )
    monkeypatch.setattr(engine, "_install_openai_runtime_patch", lambda: None)
    payload = {
        "config": {
            "llm_model": "mimo-v2.5",
            "model_endpoint": "https://private-runtime.example/v1",
            "provider": "opencodego",
            "context_window": 128000,
            "max_tokens": 4096,
            "temperature": 0.0,
            "max_steps": 50,
            "timeout_seconds": 60.0,
            "max_retries": 2,
            "human_block_limit": 10000,
            "summary_block_limit": 1000,
            "runtime_tag": "mb-runtime:test",
        }
    }

    result = asyncio.run(engine.initialize(payload))

    assert result == {"status": "ready", "actor_id": "actor-1"}
    assert order == ["redaction", "server"]


def test_letta_worker_opencodego_transport_disables_thinking_without_mutation() -> None:
    """opencodego 只追加 transport override，不原地修改上游请求。"""

    engine = _WorkerEngine()
    engine.config = {"provider": "opencodego"}
    request: dict[str, Any] = {
        "model": "mimo-v2.5",
        "messages": [{"role": "user", "content": "hello"}],
        "extra_body": {"existing": "kept"},
    }

    transported = engine._transport_request(request)

    assert transported == {
        "model": "mimo-v2.5",
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


def test_letta_worker_creates_and_finishes_official_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 agent step 必须携带先创建的 run id，并在成功后提交终态。"""

    engine, records = _tracked_ingest_engine(monkeypatch)

    result = asyncio.run(
        engine.ingest(
            {
                "subject_id": "subject-1",
                "operation_id": "operation-1",
                "content": "user: hello",
            }
        )
    )

    assert records["events"] == [
        "create_run",
        "step:run-1",
        "update_run:run-1:completed",
    ]
    assert records["created"].agent_id == "agent-1"
    assert records["created"].metadata == {"run_type": "send_message"}
    assert records["updated"].stop_reason.value == "tool_rule"
    assert records["updated"].metadata is None
    assert result["usage"] == [{"input_tokens": 11, "output_tokens": 3}]
    assert result["step_count"] == 1


def test_letta_worker_marks_tracked_run_failed_when_step_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """agent step 失败必须传播，同时把已创建 run 精确落为 failed。"""

    engine, records = _tracked_ingest_engine(monkeypatch, step_failure=True)

    with pytest.raises(RuntimeError, match="step exploded"):
        asyncio.run(
            engine.ingest(
                {
                    "subject_id": "subject-1",
                    "operation_id": "operation-1",
                    "content": "user: hello",
                }
            )
        )

    assert records["events"] == [
        "create_run",
        "step:run-1",
        "update_run:run-1:failed",
    ]
    assert records["updated"].stop_reason is None
    assert records["updated"].metadata == {"error_type": "RuntimeError"}
    assert engine._usage_buffer is None


def _tracked_ingest_engine(
    monkeypatch: pytest.MonkeyPatch,
    *,
    step_failure: bool = False,
) -> tuple[_WorkerEngine, dict[str, Any]]:
    """构造可锁定 official run 生命周期的 hermetic worker。"""

    records: dict[str, Any] = {"events": []}
    engine = _WorkerEngine()
    engine.config = {"max_steps": 3}
    engine.actor = SimpleNamespace(id="actor-1")

    async def _ensure_subject(_payload: dict[str, Any]) -> dict[str, Any]:
        """返回已存在的 subject，隔离本测试于 subject 建表细节。"""

        return {
            "subject_id": "subject-1",
            "agent_id": "agent-1",
            "block_ids": ["block-human", "block-summary"],
            "archive_id": "archive-1",
        }

    engine.ensure_subject = _ensure_subject

    class _RunManager:
        """记录 run create/update 的最小 product manager。"""

        async def create_run(self, *, pydantic_run: Any, actor: Any) -> Any:
            """创建稳定 run id。"""

            assert actor is engine.actor
            records["events"].append("create_run")
            records["created"] = pydantic_run
            return SimpleNamespace(id="run-1")

        async def update_run_by_id_async(
            self, *, run_id: str, update: Any, actor: Any
        ) -> Any:
            """记录 terminal update。"""

            assert actor is engine.actor
            records["events"].append(f"update_run:{run_id}:{update.status}")
            records["updated"] = update
            return SimpleNamespace(id=run_id)

    class _AgentManager:
        """返回固定 agent。"""

        async def get_agent_by_id_async(self, **_kwargs: Any) -> Any:
            """返回固定 agent identity。"""

            return SimpleNamespace(id="agent-1")

    engine.server = SimpleNamespace(
        run_manager=_RunManager(),
        agent_manager=_AgentManager(),
    )

    class _RunStatus:
        """最小 run status 常量。"""

        failed = "failed"

    class _Run:
        """保存 create_run 构造参数。"""

        def __init__(self, **kwargs: Any) -> None:
            """复制字段供断言。"""

            vars(self).update(kwargs)

    class _RunUpdate(_Run):
        """保存 terminal update 字段。"""

    class _RequestConfig:
        """代表官方默认 request config。"""

    class _MessageCreate(_Run):
        """保存 official message 字段。"""

    stop_reason = SimpleNamespace(value="tool_rule", run_status="completed")

    class _AgentLoopInstance:
        """记录 agent step 的 run id，并模拟 usage。"""

        async def step(self, _messages: list[Any], **kwargs: Any) -> Any:
            """执行成功或注入失败。"""

            records["events"].append(f"step:{kwargs.get('run_id')}")
            if step_failure:
                raise RuntimeError("step exploded")
            engine._capture_usage(
                {"usage": {"prompt_tokens": 11, "completion_tokens": 3}}
            )
            return SimpleNamespace(
                stop_reason=SimpleNamespace(stop_reason=stop_reason),
                usage=SimpleNamespace(step_count=1),
            )

    class _AgentLoop:
        """返回固定 agent loop。"""

        @staticmethod
        def load(**_kwargs: Any) -> _AgentLoopInstance:
            """返回固定 loop。"""

            return _AgentLoopInstance()

    modules = {
        "letta": ModuleType("letta"),
        "letta.agents": ModuleType("letta.agents"),
        "letta.agents.agent_loop": ModuleType("letta.agents.agent_loop"),
        "letta.schemas": ModuleType("letta.schemas"),
        "letta.schemas.enums": ModuleType("letta.schemas.enums"),
        "letta.schemas.job": ModuleType("letta.schemas.job"),
        "letta.schemas.message": ModuleType("letta.schemas.message"),
        "letta.schemas.run": ModuleType("letta.schemas.run"),
    }
    modules["letta.agents.agent_loop"].AgentLoop = _AgentLoop
    modules["letta.schemas.enums"].RunStatus = _RunStatus
    modules["letta.schemas.job"].LettaRequestConfig = _RequestConfig
    modules["letta.schemas.message"].MessageCreate = _MessageCreate
    modules["letta.schemas.run"].Run = _Run
    modules["letta.schemas.run"].RunUpdate = _RunUpdate
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setenv("MEMORY_BENCHMARK_LETTA_BUILD_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    records["original_openai_key"] = os.environ.get("OPENAI_API_KEY")
    return engine, records


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
