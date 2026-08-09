"""Letta 独立运行时的 JSON-lines worker。

本模块由 vendored Letta 的 Python 3.12 虚拟环境直接执行。它不导入主框架，
只在独立进程内初始化 PostgreSQL-backed ``SyncServer``，并把 official
``ai-memory-sdk`` 的 sleeptime-memory 产品调用面暴露成窄协议。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import traceback
from typing import Any


_SDK_TAG = "ai-memory-sdk"
_OWNER_TAG = "memory-benchmark-letta"
_EXPECTED_TOOLS = frozenset(
    {
        "memory_finish_edits",
        "memory_insert",
        "memory_replace",
        "memory_rethink",
    }
)
_SUCCESS_STOP_REASONS = frozenset({"end_turn", "tool_rule"})


def _required_text(value: Any, label: str) -> str:
    """读取非空字符串，拒绝协议层宽松转换。"""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-blank string")
    return value


def _required_int(value: Any, label: str, *, minimum: int = 0) -> int:
    """读取不小于下界的整数，布尔值不得冒充整数。"""

    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _optional_text(value: Any, label: str) -> str | None:
    """读取可空字符串；空白字符串仍视为非法配置。"""

    if value is None:
        return None
    return _required_text(value, label)


def _plain_id(value: Any) -> str:
    """把 Letta 的强类型 id 转成协议字符串。"""

    text = str(value)
    if not text.strip():
        raise RuntimeError("Letta returned an empty identifier")
    return text


class _WorkerEngine:
    """在单一 event loop 内持有 Letta server、actor 与观测补丁。"""

    def __init__(self) -> None:
        """创建尚未初始化的 worker 状态。"""

        self.server: Any = None
        self.actor: Any = None
        self.config: dict[str, Any] = {}
        self._usage_buffer: list[dict[str, int]] | None = None
        self._closed = False

    async def dispatch(self, request: dict[str, Any]) -> dict[str, Any]:
        """路由一条已解析的 worker 请求。"""

        command = _required_text(request.get("command"), "command")
        payload = request.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        if command == "initialize":
            return await self.initialize(payload)
        self._require_ready()
        if command == "ping":
            return {"status": "ready"}
        if command == "ensure_subject":
            return await self.ensure_subject(payload)
        if command == "ingest":
            return await self.ingest(payload)
        if command == "read_blocks":
            return await self.read_blocks(payload)
        if command == "delete_subject":
            return await self.delete_subject(payload)
        if command == "shutdown":
            return await self.shutdown()
        raise ValueError(f"unknown command: {command}")

    async def initialize(self, payload: dict[str, Any]) -> dict[str, Any]:
        """初始化真实 ``SyncServer``，但不做 provider model 网络同步。"""

        if self.server is not None:
            raise RuntimeError("Letta worker was already initialized")
        config = payload.get("config")
        if not isinstance(config, dict):
            raise ValueError("initialize.config must be an object")
        self.config = self._validate_config(config)

        from letta.server.server import SyncServer

        self.server = SyncServer(init_with_default_org_and_user=False)
        await self.server.organization_manager.create_default_organization_async()
        self.actor = await self.server.user_manager.create_default_actor_async()
        await self.server.tool_manager.upsert_base_tools_async(actor=self.actor)
        self._install_openai_runtime_patch()
        return {"status": "ready", "actor_id": _plain_id(self.actor.id)}

    @staticmethod
    def _validate_config(raw: dict[str, Any]) -> dict[str, Any]:
        """强校验 worker 真正消费的非 secret 配置。"""

        temperature = raw.get("temperature")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            raise ValueError("temperature must be numeric")
        config = {
            "llm_model": _required_text(raw.get("llm_model"), "llm_model"),
            "model_endpoint": _optional_text(raw.get("model_endpoint"), "model_endpoint"),
            "provider": _required_text(raw.get("provider"), "provider"),
            "context_window": _required_int(raw.get("context_window"), "context_window", minimum=1),
            "max_tokens": _required_int(raw.get("max_tokens"), "max_tokens", minimum=1),
            "temperature": float(temperature),
            "max_steps": _required_int(raw.get("max_steps"), "max_steps", minimum=1),
            "timeout_seconds": float(raw.get("timeout_seconds")),
            "max_retries": _required_int(raw.get("max_retries"), "max_retries"),
            "human_block_limit": _required_int(raw.get("human_block_limit"), "human_block_limit", minimum=1),
            "summary_block_limit": _required_int(raw.get("summary_block_limit"), "summary_block_limit", minimum=1),
            "runtime_tag": _required_text(raw.get("runtime_tag"), "runtime_tag"),
        }
        if config["timeout_seconds"] <= 0:
            raise ValueError("timeout_seconds must be positive")
        if config["provider"] not in {"primary", "opencodego"}:
            raise ValueError("provider must be primary or opencodego")
        return config

    def _require_ready(self) -> None:
        """拒绝初始化前或关闭后的业务命令。"""

        if self.server is None or self.actor is None:
            raise RuntimeError("Letta worker is not initialized")
        if self._closed:
            raise RuntimeError("Letta worker is closed")

    def _install_openai_runtime_patch(self) -> None:
        """安装 transport/usage 纯观测补丁，不改变 agent 算法路径。"""

        from letta.llm_api.openai_client import OpenAIClient

        engine = self
        original_prepare = OpenAIClient._prepare_client_kwargs
        original_prepare_async = OpenAIClient._prepare_client_kwargs_async
        original_request = OpenAIClient.request
        original_request_async = OpenAIClient.request_async

        def prepare(client: Any, llm_config: Any) -> dict[str, Any]:
            """给同步 OpenAI client 补框架 timeout/retry。"""

            kwargs = dict(original_prepare(client, llm_config))
            kwargs["timeout"] = engine.config["timeout_seconds"]
            kwargs["max_retries"] = engine.config["max_retries"]
            return kwargs

        async def prepare_async(client: Any, llm_config: Any) -> dict[str, Any]:
            """给异步 OpenAI client 补框架 timeout/retry。"""

            kwargs = dict(await original_prepare_async(client, llm_config))
            kwargs["timeout"] = engine.config["timeout_seconds"]
            kwargs["max_retries"] = engine.config["max_retries"]
            return kwargs

        def request(client: Any, request_data: dict[str, Any], llm_config: Any) -> dict[str, Any]:
            """执行同步请求并记录真实 provider usage。"""

            result = original_request(
                client,
                engine._transport_request(request_data),
                llm_config,
            )
            engine._capture_usage(result)
            return result

        async def request_async(
            client: Any,
            request_data: dict[str, Any],
            llm_config: Any,
        ) -> dict[str, Any]:
            """执行异步请求并记录真实 provider usage。"""

            result = await original_request_async(
                client,
                engine._transport_request(request_data),
                llm_config,
            )
            engine._capture_usage(result)
            return result

        OpenAIClient._prepare_client_kwargs = prepare
        OpenAIClient._prepare_client_kwargs_async = prepare_async
        OpenAIClient.request = request
        OpenAIClient.request_async = request_async

    def _transport_request(self, request_data: dict[str, Any]) -> dict[str, Any]:
        """复制请求并追加 provider 所需的非算法 transport override。"""

        copied = dict(request_data)
        if self.config["provider"] == "opencodego":
            extra_body = dict(copied.get("extra_body") or {})
            extra_body["thinking"] = {"type": "disabled"}
            copied["extra_body"] = extra_body
        return copied

    def _capture_usage(self, response: dict[str, Any]) -> None:
        """从一次成功响应提取精确 token usage；缺失时立即失败。"""

        if self._usage_buffer is None:
            return
        usage = response.get("usage") if isinstance(response, dict) else None
        if not isinstance(usage, dict):
            raise RuntimeError("Letta build LLM response has no exact usage object")
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        self._usage_buffer.append(
            {
                "input_tokens": _required_int(input_tokens, "usage.input_tokens"),
                "output_tokens": _required_int(output_tokens, "usage.output_tokens"),
            }
        )

    def _begin_usage(self) -> None:
        """为一个 ingest command 建立独占 usage 缓冲。"""

        if self._usage_buffer is not None:
            raise RuntimeError("nested Letta usage capture is forbidden")
        self._usage_buffer = []

    def _finish_usage(self) -> list[dict[str, int]]:
        """冻结当前 usage 缓冲并恢复空闲状态。"""

        if self._usage_buffer is None:
            raise RuntimeError("Letta usage capture was not started")
        captured = self._usage_buffer
        self._usage_buffer = None
        return captured

    def _discard_usage(self) -> None:
        """异常路径丢弃未完成 observation，禁止写半条记录。"""

        self._usage_buffer = None

    def _subject_tags(self, subject_id: str) -> list[str]:
        """返回 official SDK tag 加框架 runtime/subject 隔离 tag。"""

        return [
            _SDK_TAG,
            _OWNER_TAG,
            self.config["runtime_tag"],
            f"subj:{subject_id}",
            subject_id,
        ]

    async def _find_subject_agent(self, subject_id: str) -> Any | None:
        """按 runtime 与 subject 双 tag 查找唯一 agent。"""

        matches = await self.server.agent_manager.list_agents_async(
            actor=self.actor,
            tags=[self.config["runtime_tag"], f"subj:{subject_id}"],
            match_all_tags=True,
            limit=2,
            include_relationships=[
                "memory",
                "multi_agent_group",
                "sources",
                "tool_exec_environment_variables",
                "tools",
                "tags",
            ],
        )
        if len(matches) > 1:
            raise RuntimeError(f"multiple Letta agents found for subject {subject_id}")
        return matches[0] if matches else None

    def _llm_config(self) -> Any:
        """构造不经 provider registry/network 解析的显式 LLMConfig。"""

        from letta.schemas.llm_config import LLMConfig

        return LLMConfig(
            model=self.config["llm_model"],
            model_endpoint_type="openai",
            model_endpoint=self.config["model_endpoint"],
            provider_name="openai",
            context_window=self.config["context_window"],
            max_tokens=self.config["max_tokens"],
            temperature=self.config["temperature"],
            enable_reasoner=False,
            put_inner_thoughts_in_kwargs=False,
            parallel_tool_calls=False,
            handle=f"openai/{self.config['llm_model']}",
        )

    async def ensure_subject(self, payload: dict[str, Any]) -> dict[str, Any]:
        """创建或严格验证一个 official sleeptime-memory subject。"""

        subject_id = _required_text(payload.get("subject_id"), "subject_id")
        agent = await self._find_subject_agent(subject_id)
        if agent is None:
            from letta.schemas.agent import CreateAgent
            from letta.schemas.block import CreateBlock
            from letta.schemas.enums import AgentType

            request = CreateAgent(
                name=f"mb_letta_{subject_id[:32]}",
                agent_type=AgentType.sleeptime_agent,
                llm_config=self._llm_config(),
                embedding_config=None,
                memory_blocks=[
                    CreateBlock(
                        label="human",
                        description="Details about the human user you are speaking to.",
                        limit=self.config["human_block_limit"],
                        value="",
                    ),
                    CreateBlock(
                        label="summary",
                        description="A short (1-2 sentences) running summary of the conversation.",
                        limit=self.config["summary_block_limit"],
                        value="",
                    ),
                ],
                initial_message_sequence=[],
                include_base_tools=True,
                enable_sleeptime=None,
                tags=self._subject_tags(subject_id),
            )
            agent = await self.server.create_agent_async(request=request, actor=self.actor)
            agent = await self.server.agent_manager.get_agent_by_id_async(
                agent_id=agent.id,
                actor=self.actor,
                include_relationships=[
                    "memory",
                    "multi_agent_group",
                    "sources",
                    "tool_exec_environment_variables",
                    "tools",
                    "tags",
                ],
            )
        return await self._validate_and_initialize_subject(subject_id, agent)

    async def _validate_and_initialize_subject(
        self,
        subject_id: str,
        agent: Any,
    ) -> dict[str, Any]:
        """校验 agent、blocks、tools，并补齐唯一 official initializer passage。"""

        agent_type = getattr(agent.agent_type, "value", agent.agent_type)
        if agent_type != "sleeptime_agent" or bool(agent.enable_sleeptime):
            raise RuntimeError("Letta subject agent is not the standalone sleeptime profile")
        if agent.embedding_config is not None:
            raise RuntimeError("Letta product profile must keep embedding_config=None")
        expected_llm_config = {
            "model": self.config["llm_model"],
            "model_endpoint_type": "openai",
            "model_endpoint": self.config["model_endpoint"],
            "provider_name": "openai",
            "context_window": self.config["context_window"],
            "max_tokens": self.config["max_tokens"],
            "temperature": self.config["temperature"],
            "enable_reasoner": False,
            "put_inner_thoughts_in_kwargs": False,
            "parallel_tool_calls": False,
            "handle": f"openai/{self.config['llm_model']}",
        }
        actual_llm_config = {
            key: getattr(agent.llm_config, key)
            for key in expected_llm_config
        }
        if actual_llm_config != expected_llm_config:
            raise RuntimeError("Letta subject LLM config conflicts with runtime config")
        if set(agent.tags or []) != set(self._subject_tags(subject_id)):
            raise RuntimeError("Letta subject tags conflict with runtime identity")

        tools = frozenset(tool.name for tool in (agent.tools or []))
        if tools != _EXPECTED_TOOLS:
            raise RuntimeError(
                "Letta sleeptime tool set mismatch: " + ",".join(sorted(tools))
            )
        blocks = await self.server.block_manager.get_blocks_by_agent_async(
            agent_id=agent.id,
            actor=self.actor,
        )
        by_label = {block.label: block for block in blocks}
        if set(by_label) != {"human", "summary"} or len(by_label) != len(blocks):
            raise RuntimeError("Letta subject must have exactly human and summary blocks")
        expected_limits = {
            "human": self.config["human_block_limit"],
            "summary": self.config["summary_block_limit"],
        }
        expected_descriptions = {
            "human": "Details about the human user you are speaking to.",
            "summary": "A short (1-2 sentences) running summary of the conversation.",
        }
        for label, block in by_label.items():
            if block.limit != expected_limits[label]:
                raise RuntimeError(f"Letta {label} block limit conflicts with config")
            if block.description != expected_descriptions[label]:
                raise RuntimeError(
                    f"Letta {label} block description conflicts with product contract"
                )

        archive = await self.server.archive_manager.get_or_create_default_archive_for_agent_async(
            agent_state=agent,
            actor=self.actor,
        )
        archive_ids = await self.server.agent_manager.get_agent_archive_ids_async(
            agent_id=agent.id,
            actor=self.actor,
        )
        if len(archive_ids) != 1 or _plain_id(archive_ids[0]) != _plain_id(archive.id):
            raise RuntimeError("Letta subject must own exactly one default archive")
        initializer = f"Initialized memory for subject {subject_id}"
        passage_rows = await self.server.agent_manager.query_agent_passages_async(
            actor=self.actor,
            agent_id=agent.id,
            limit=10,
            query_text=None,
            embed_query=False,
            tags=[_SDK_TAG],
        )
        matches = [passage for passage, _, _ in passage_rows if passage.text == initializer]
        if len(passage_rows) > 1 or len(matches) > 1:
            raise RuntimeError("Letta subject has unexpected SDK-tagged passages")
        if matches and matches[0].embedding is not None:
            raise RuntimeError("Letta initializer passage must not have an embedding")
        if not matches:
            inserted = await self.server.passage_manager.insert_passage(
                agent_state=agent,
                text=initializer,
                actor=self.actor,
                tags=[_SDK_TAG],
            )
            if len(inserted) != 1 or inserted[0].embedding is not None:
                raise RuntimeError("Letta initializer passage violated no-embedding contract")

        return {
            "subject_id": subject_id,
            "agent_id": _plain_id(agent.id),
            "block_ids": [_plain_id(by_label[label].id) for label in sorted(by_label)],
            "archive_id": _plain_id(archive.id),
        }

    async def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        """把一个已格式化 SDK batch 交给真实 ``AgentLoop.step``。"""

        subject_id = _required_text(payload.get("subject_id"), "subject_id")
        operation_id = _required_text(payload.get("operation_id"), "operation_id")
        content = _required_text(payload.get("content"), "content")
        state = await self.ensure_subject({"subject_id": subject_id})
        agent = await self.server.agent_manager.get_agent_by_id_async(
            agent_id=state["agent_id"],
            actor=self.actor,
            include_relationships=[
                "memory",
                "multi_agent_group",
                "sources",
                "tool_exec_environment_variables",
                "tools",
                "tags",
            ],
        )

        from letta.agents.agent_loop import AgentLoop
        from letta.schemas.enums import RunStatus
        from letta.schemas.job import LettaRequestConfig
        from letta.schemas.message import MessageCreate
        from letta.schemas.run import Run as PydanticRun
        from letta.schemas.run import RunUpdate

        api_key_name = "MEMORY_BENCHMARK_LETTA_BUILD_API_KEY"
        api_key = _required_text(os.environ.get(api_key_name), api_key_name)
        previous = os.environ.get("OPENAI_API_KEY")
        run = await self.server.run_manager.create_run(
            pydantic_run=PydanticRun(
                agent_id=state["agent_id"],
                background=False,
                metadata={"run_type": "send_message"},
                request_config=LettaRequestConfig(),
            ),
            actor=self.actor,
        )
        response = None
        run_status = RunStatus.failed
        run_update_metadata = None
        stop_reason_object = None
        self._begin_usage()
        try:
            os.environ["OPENAI_API_KEY"] = api_key
            response = await AgentLoop.load(agent_state=agent, actor=self.actor).step(
                [MessageCreate(role="user", content=content, otid=operation_id)],
                max_steps=self.config["max_steps"],
                run_id=run.id,
            )
            stop_reason_object = response.stop_reason.stop_reason
            stop_reason = getattr(stop_reason_object, "value", stop_reason_object)
            if stop_reason not in _SUCCESS_STOP_REASONS:
                raise RuntimeError(f"Letta agent stopped non-terminally: {stop_reason}")
            usage = self._finish_usage()
            if response.usage.step_count != len(usage):
                raise RuntimeError(
                    "Letta per-call usage count does not match response step_count: "
                    f"calls={len(usage)}, step_count={response.usage.step_count}"
                )
            run_status = stop_reason_object.run_status
        except BaseException as exc:
            self._discard_usage()
            run_update_metadata = {"error_type": type(exc).__name__}
            raise
        finally:
            if previous is None:
                os.environ.pop("OPENAI_API_KEY", None)
            else:
                os.environ["OPENAI_API_KEY"] = previous
            await self.server.run_manager.update_run_by_id_async(
                run_id=run.id,
                update=RunUpdate(
                    status=run_status,
                    metadata=run_update_metadata,
                    stop_reason=stop_reason_object,
                ),
                actor=self.actor,
            )
        return {
            **state,
            "stop_reason": str(stop_reason),
            "usage": usage,
            "step_count": response.usage.step_count,
        }

    async def read_blocks(self, payload: dict[str, Any]) -> dict[str, Any]:
        """读取 subject 的全部 attached core blocks，不调用 query/LLM/embedding。"""

        subject_id = _required_text(payload.get("subject_id"), "subject_id")
        expected_agent_id = _optional_text(payload.get("agent_id"), "agent_id")
        agent = await self._find_subject_agent(subject_id)
        if agent is None:
            raise RuntimeError(f"Letta subject does not exist: {subject_id}")
        if expected_agent_id is not None and _plain_id(agent.id) != expected_agent_id:
            raise RuntimeError("Letta subject sidecar points to a different agent")
        blocks = await self.server.block_manager.get_blocks_by_agent_async(
            agent_id=agent.id,
            actor=self.actor,
        )
        ordered = sorted(blocks, key=lambda block: (block.label, _plain_id(block.id)))
        return {
            "agent_id": _plain_id(agent.id),
            "blocks": [
                {
                    "id": _plain_id(block.id),
                    "label": block.label,
                    "description": block.description,
                    "value": block.value,
                }
                for block in ordered
            ],
        }

    async def delete_subject(self, payload: dict[str, Any]) -> dict[str, Any]:
        """按 subject namespace 幂等删除 agent、archive 与独占 orphan blocks。"""

        subject_id = _required_text(payload.get("subject_id"), "subject_id")
        expected = payload.get("state")
        if expected is not None and not isinstance(expected, dict):
            raise ValueError("delete_subject.state must be null or an object")
        agent = await self._find_subject_agent(subject_id)
        agent_id = _optional_text((expected or {}).get("agent_id"), "state.agent_id")
        block_ids = (expected or {}).get("block_ids") or []
        archive_id = _optional_text((expected or {}).get("archive_id"), "state.archive_id")
        if not isinstance(block_ids, list) or not all(
            isinstance(value, str) and value.strip() for value in block_ids
        ):
            raise ValueError("state.block_ids must be a list of non-blank strings")

        if agent is not None:
            discovered_id = _plain_id(agent.id)
            if agent_id is not None and discovered_id != agent_id:
                raise RuntimeError("Letta cleanup sidecar agent conflicts with discovered subject")
            agent_id = discovered_id
            blocks = await self.server.block_manager.get_blocks_by_agent_async(
                agent_id=agent.id,
                actor=self.actor,
            )
            discovered_blocks = [_plain_id(block.id) for block in blocks]
            if block_ids and set(block_ids) != set(discovered_blocks):
                raise RuntimeError("Letta cleanup sidecar block set conflicts with subject")
            block_ids = discovered_blocks
            archive_ids = await self.server.agent_manager.get_agent_archive_ids_async(
                agent_id=agent.id,
                actor=self.actor,
            )
            if len(archive_ids) > 1:
                raise RuntimeError("Letta subject unexpectedly owns multiple archives")
            discovered_archive = _plain_id(archive_ids[0]) if archive_ids else None
            if archive_id is not None and discovered_archive != archive_id:
                raise RuntimeError("Letta cleanup sidecar archive conflicts with subject")
            archive_id = discovered_archive

        for block_id in block_ids:
            owners = await self.server.block_manager.get_agents_for_block_async(
                block_id=block_id,
                actor=self.actor,
            )
            foreign = [owner for owner in owners if _plain_id(owner.id) != agent_id]
            if foreign:
                raise RuntimeError("Letta cleanup refuses to delete a shared block")
        if archive_id is not None:
            owners = await self.server.archive_manager.get_agents_for_archive_async(
                archive_id=archive_id,
                actor=self.actor,
            )
            foreign = [owner for owner in owners if _plain_id(owner.id) != agent_id]
            if foreign:
                raise RuntimeError("Letta cleanup refuses to delete a shared archive")

        if agent is not None:
            await self.server.agent_manager.delete_agent_async(
                agent_id=_plain_id(agent.id),
                actor=self.actor,
            )
        if archive_id is not None:
            try:
                await self.server.archive_manager.get_archive_by_id_async(
                    archive_id=archive_id,
                    actor=self.actor,
                )
            except Exception as exc:
                if exc.__class__.__name__ != "NoResultFound":
                    raise
            else:
                await self.server.archive_manager.delete_archive_async(
                    archive_id=archive_id,
                    actor=self.actor,
                )
        for block_id in block_ids:
            block = await self.server.block_manager.get_block_by_id_async(
                block_id=block_id,
                actor=self.actor,
            )
            if block is None:
                continue
            owners = await self.server.block_manager.get_agents_for_block_async(
                block_id=block_id,
                actor=self.actor,
            )
            if owners:
                raise RuntimeError("Letta block still has owners after subject deletion")
            await self.server.block_manager.delete_block_async(
                block_id=block_id,
                actor=self.actor,
            )
        if await self._find_subject_agent(subject_id) is not None:
            raise RuntimeError("Letta subject still exists after cleanup")
        return {"deleted": True}

    async def shutdown(self) -> dict[str, Any]:
        """关闭进程级数据库 engine；重复调用保持幂等。"""

        if self._closed:
            return {"status": "closed"}
        from letta.server.db import close_db

        await close_db()
        self._closed = True
        return {"status": "closed"}


def _sanitize_error(message: str) -> str:
    """从错误文本移除 worker 私有 API key。"""

    secret = os.environ.get("MEMORY_BENCHMARK_LETTA_BUILD_API_KEY")
    return message.replace(secret, "<redacted>") if secret else message


def _prepare_protocol_stream() -> Any:
    """保留原 stdout 供协议使用，并把第三方普通输出改送 stderr。"""

    protocol = os.fdopen(os.dup(sys.stdout.fileno()), "w", encoding="utf-8", buffering=1)
    os.dup2(sys.stderr.fileno(), sys.stdout.fileno())
    return protocol


def main() -> int:
    """运行长驻 JSON-lines 命令循环。"""

    protocol = _prepare_protocol_stream()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    engine = _WorkerEngine()
    try:
        for raw_line in sys.stdin:
            request_id: Any = None
            should_stop = False
            try:
                request = json.loads(raw_line)
                if not isinstance(request, dict):
                    raise ValueError("request must be an object")
                request_id = request.get("request_id")
                result = loop.run_until_complete(engine.dispatch(request))
                response = {"request_id": request_id, "ok": True, "result": result}
                should_stop = request.get("command") == "shutdown"
            except BaseException as exc:
                traceback.print_exc(file=sys.stderr)
                response = {
                    "request_id": request_id,
                    "ok": False,
                    "error_type": exc.__class__.__name__,
                    "error": _sanitize_error(str(exc)),
                }
            protocol.write(json.dumps(response, ensure_ascii=False, sort_keys=True) + "\n")
            protocol.flush()
            if should_stop:
                break
    finally:
        if engine.server is not None and not engine._closed:
            try:
                loop.run_until_complete(engine.shutdown())
            except BaseException:
                traceback.print_exc(file=sys.stderr)
        loop.close()
        protocol.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
