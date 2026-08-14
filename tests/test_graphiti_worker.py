"""测试 Graphiti worker 的状态、API 观测与 embedded close 契约。"""

from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from types import SimpleNamespace
from typing import Any

import pytest

from memory_benchmark.config import OpenAISettings, load_path_settings
from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.graphiti_adapter import GraphitiConfig, GraphitiRuntime
from memory_benchmark.methods import graphiti_worker as graphiti_worker_module
from memory_benchmark.methods.graphiti_worker import (
    GRAPHITI_STATE_SCHEMA_VERSION,
    _ObservedCompletions,
    _WorkerEngine,
    _embedding_token_count,
    _empty_state,
    _validate_state,
)


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _FakeCompletions:
    """返回可控 usage 的 async endpoint。"""

    def __init__(self, response: Any) -> None:
        """保存响应并初始化调用账。"""

        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        """记录实际 request。"""

        self.calls.append(dict(kwargs))
        return self.response


def _response(input_tokens: Any = 5, output_tokens: Any = 2) -> Any:
    """构造 OpenAI SDK usage 形状替身。"""

    return SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
        )
    )


def test_graphiti_state_validator_roundtrips_and_rejects_drift() -> None:
    """sidecar 只接受 exact schema、isolation 与无重复 session 序列。"""

    state = _empty_state("run_conv")
    assert _validate_state(state, "run_conv") == state
    assert state["contract_version"] == GRAPHITI_STATE_SCHEMA_VERSION

    drift = dict(state)
    drift["extra"] = True
    with pytest.raises(ValueError, match="top-level shape"):
        _validate_state(drift, "run_conv")

    mismatch = _empty_state("other")
    with pytest.raises(ValueError, match="isolation_key mismatch"):
        _validate_state(mismatch, "run_conv")

    duplicate = _empty_state("run_conv")
    duplicate["sessions"] = {
        "s1": {"edge_uuids": ["e1", "e1"], "episode_uuids": []}
    }
    with pytest.raises(ValueError, match="must not contain duplicates"):
        _validate_state(duplicate, "run_conv")


def test_observed_completions_preserves_request_and_adds_opencodego_control() -> None:
    """endpoint wrapper 只追加 thinking disabled，并记录精确成功 usage。"""

    engine = _WorkerEngine()
    engine.config = {"api_provider": "opencodego"}
    real = _FakeCompletions(_response(11, 3))
    wrapper = _ObservedCompletions(engine, real)

    result = asyncio.run(
        wrapper.create(
            model="deepseek-v4-flash",
            messages=[{"role": "user", "content": "x"}],
            response_format={"type": "json_object"},
        )
    )

    assert result is real.response
    assert real.calls[0]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert engine.llm_observations == [
        {"input_tokens": 11, "output_tokens": 3}
    ]


@pytest.mark.parametrize(
    ("input_tokens", "output_tokens", "message"),
    [
        (None, 2, "prompt token usage"),
        (5, None, "completion token usage"),
        (True, 2, "prompt token usage"),
        (5, -1, "completion token usage"),
    ],
)
def test_observed_completions_rejects_missing_or_invalid_usage(
    input_tokens: Any,
    output_tokens: Any,
    message: str,
) -> None:
    """API usage 不可用估算或零值替身掩盖。"""

    engine = _WorkerEngine()
    engine.config = {"api_provider": "primary"}
    wrapper = _ObservedCompletions(
        engine,
        _FakeCompletions(_response(input_tokens, output_tokens)),
    )
    with pytest.raises(RuntimeError, match=message):
        asyncio.run(wrapper.create(model="gpt-4o-mini", messages=[]))


def test_embedding_token_count_uses_attention_mask_and_truncation() -> None:
    """本地 embedding token 只从实际 tokenizer attention mask 计数。"""

    calls: list[dict[str, Any]] = []

    class _Tokenizer:
        """返回固定 attention mask 的 tokenizer 替身。"""

        def __call__(self, texts: list[str], **kwargs: Any) -> dict[str, Any]:
            """记录参数并返回固定 token mask。"""

            calls.append({"texts": texts, **kwargs})
            return {"attention_mask": [[1, 1, 1], [1, 1]]}

    model = SimpleNamespace(tokenizer=_Tokenizer(), max_seq_length=256)
    assert _embedding_token_count(model, ["a", "b"]) == 5
    assert calls == [
        {
            "texts": ["a", "b"],
            "add_special_tokens": True,
            "max_length": 256,
            "truncation": True,
            "return_attention_mask": True,
        }
    ]


def test_falkordblite_close_runs_exact_sync_cleanup_and_verifies_stopped() -> None:
    """upstream async close 后必须补齐 0.10.0 sync cleanup。"""

    trace: list[str] = []

    class _SyncClient:
        """模拟 FalkorDB Lite 底层同步 client。"""

        _async_managed = True

        def _cleanup(self) -> None:
            """记录并完成 embedded 进程清理。"""

            trace.append("sync_cleanup")
            self.running = False

        def _is_redis_running(self) -> bool:
            """返回 embedded 进程是否仍运行。"""

            return getattr(self, "running", True)

    sync = _SyncClient()
    sync.running = True
    async_client = SimpleNamespace(_sync_client=sync, _async_managed=False)

    class _Graphiti:
        """只记录产品 close 的 Graphiti 替身。"""

        async def close(self) -> None:
            """记录 Graphiti close 顺序。"""

            trace.append("graphiti_close")

    engine = _WorkerEngine()
    engine.graphiti = _Graphiti()
    engine.lite = SimpleNamespace(client=async_client)
    engine.active_isolation_key = "run_conv"
    asyncio.run(engine._close_active())

    assert trace == ["graphiti_close", "sync_cleanup"]
    assert sync._async_managed is False
    assert async_client._async_managed is True
    assert engine.graphiti is None


def test_graphiti_activation_failure_closes_partially_constructed_lite(
    tmp_path: Path,
) -> None:
    """Graphiti 构造中途失败也必须关闭 driver 与 embedded Redis。"""

    trace: list[str] = []

    class _SyncClient:
        """模拟构造失败场景的同步 client。"""

        _async_managed = True
        running = True

        def _cleanup(self) -> None:
            """记录 embedded cleanup。"""

            trace.append("sync_cleanup")
            self.running = False

        def _is_redis_running(self) -> bool:
            """返回 fake 进程状态。"""

            return self.running

    sync = _SyncClient()
    lite = SimpleNamespace(
        client=SimpleNamespace(_sync_client=sync, _async_managed=False)
    )

    class _Driver:
        """模拟部分构造成功的 Graphiti driver。"""

        async def close(self) -> None:
            """记录 driver close。"""

            trace.append("driver_close")

    class _ExplodingGraphiti:
        """在构造阶段抛错的产品替身。"""

        def __init__(self, **kwargs: Any) -> None:
            """抛出确定性构造错误。"""

            del kwargs
            raise RuntimeError("graphiti constructor exploded")

    engine = _WorkerEngine()
    engine.state_root = tmp_path
    engine.config = {"max_coroutines": 1}
    engine.embedder = object()
    engine.async_falkor_class = lambda **_kwargs: lite
    engine.falkor_driver_class = lambda **_kwargs: _Driver()
    engine.graphiti_class = _ExplodingGraphiti
    engine._build_llm_client = lambda: object()  # type: ignore[method-assign]
    engine._build_unused_cross_encoder = lambda: object()  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="constructor exploded"):
        asyncio.run(engine._activate("run_conv"))

    assert trace == ["driver_close", "sync_cleanup"]
    assert sync._async_managed is False
    assert lite.client._async_managed is True
    assert engine.active_isolation_key is None
    assert engine.driver is None
    assert engine.lite is None


def test_graphiti_physical_cleanup_resumes_from_external_tombstone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """rmtree 中断后须靠 root 外 marker 续删，且禁止提前重建 live root。"""

    engine = _WorkerEngine()
    engine.state_root = tmp_path
    isolation_key = "run_conv"
    root, cleanup_marker, tombstone = engine._cleanup_paths(isolation_key)
    root.mkdir()
    (root / "conversation_id.txt").write_text(
        isolation_key + "\n",
        encoding="utf-8",
    )
    (root / "partial.bin").write_bytes(b"state")
    real_rmtree = graphiti_worker_module.shutil.rmtree

    def _interrupted_rmtree(path: Path) -> None:
        """模拟 tombstone 已部分删除后进程失败。"""

        (path / "partial.bin").unlink()
        raise OSError("simulated recursive delete interruption")

    monkeypatch.setattr(graphiti_worker_module.shutil, "rmtree", _interrupted_rmtree)
    with pytest.raises(OSError, match="delete interruption"):
        asyncio.run(
            engine.delete_conversation({"isolation_key": isolation_key})
        )

    assert not root.exists()
    assert tombstone.exists()
    assert cleanup_marker.is_file()
    with pytest.raises(RuntimeError, match="incomplete physical cleanup"):
        asyncio.run(engine._activate(isolation_key))

    monkeypatch.setattr(graphiti_worker_module.shutil, "rmtree", real_rmtree)
    assert asyncio.run(
        engine.delete_conversation({"isolation_key": isolation_key})
    ) == {"deleted": True}
    assert not root.exists()
    assert not tombstone.exists()
    assert not cleanup_marker.exists()
    assert asyncio.run(
        engine.delete_conversation({"isolation_key": isolation_key})
    ) == {"deleted": True}


def test_real_graphiti_worker_initialize_and_shutdown_are_zero_api(tmp_path: Path) -> None:
    """隔离 runtime 能加载 Graphiti/FalkorDB/MiniLM，握手与关闭不调用 API。"""

    paths = load_path_settings(project_root=PROJECT_ROOT)
    runtime = GraphitiRuntime(
        config=GraphitiConfig(
            llm_model="deepseek-v4-flash",
            structured_output_mode="json_object",
            llm_temperature=1.0,
            llm_max_tokens=16384,
            embedding_model_path="models/all-MiniLM-L6-v2",
            embedding_dimension=384,
            embedding_normalize=True,
            query_limit=20,
            max_coroutines=10,
            worker_request_timeout_seconds=120.0,
            max_workers=1,
        ),
        openai_settings=OpenAISettings(
            api_key="dummy-never-called",
            base_url="http://127.0.0.1:9/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
            timeout_seconds=1.0,
            max_retries=0,
        ),
        path_settings=paths,
        storage_root=tmp_path / "method_state",
    )
    runtime.ensure_started()
    runtime.close()
    runtime.close()


def test_graphiti_runtime_shutdown_failure_is_permanently_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一次未确认 shutdown 后不得重试成 closed 或复用同一 runtime。"""

    paths = load_path_settings(project_root=PROJECT_ROOT)
    runtime = GraphitiRuntime(
        config=GraphitiConfig(
            llm_model="deepseek-v4-flash",
            structured_output_mode="json_object",
            llm_temperature=1.0,
            llm_max_tokens=16384,
            embedding_model_path="models/all-MiniLM-L6-v2",
            embedding_dimension=384,
            embedding_normalize=True,
            query_limit=20,
            max_coroutines=10,
            worker_request_timeout_seconds=120.0,
            max_workers=1,
        ),
        openai_settings=OpenAISettings(
            api_key="dummy-never-called",
            base_url="http://127.0.0.1:9/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
            timeout_seconds=1.0,
            max_retries=0,
        ),
        path_settings=paths,
        storage_root=tmp_path / "method_state",
    )
    runtime._transport._process = SimpleNamespace(  # type: ignore[assignment]
        poll=lambda: None
    )
    terminate_calls: list[str] = []

    def _failed_shutdown(command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """模拟产品 shutdown 未确认。"""

        del command, payload
        raise RuntimeError("shutdown exploded")

    monkeypatch.setattr(runtime, "_request", _failed_shutdown)
    monkeypatch.setattr(
        runtime,
        "_terminate_worker",
        lambda: terminate_calls.append("terminate"),
    )

    with pytest.raises(RuntimeError, match="shutdown exploded"):
        runtime.close()
    assert runtime._closed is False
    assert runtime._close_failed is True
    assert terminate_calls == ["terminate"]

    with pytest.raises(ConfigurationError, match="permanently unusable"):
        runtime.close()
    assert runtime._closed is False
    assert terminate_calls == ["terminate"]


def test_real_graphiti_product_edge_chain_uses_only_local_fake_endpoint(
    tmp_path: Path,
) -> None:
    """真实 add/search/lineage/session 链须经本地假 endpoint 与 MiniLM 跑通。"""

    requests: list[dict[str, Any]] = []

    class _Handler(BaseHTTPRequestHandler):
        """返回可形成一个 Graphiti fact edge 的 Chat Completions 响应。"""

        def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
            """按请求中的 response schema 返回确定性结构化结果。"""

            length = int(self.headers.get("content-length", "0"))
            request = json.loads(self.rfile.read(length))
            requests.append(request)
            serialized = json.dumps(request, ensure_ascii=False)
            if "extracted_entities" in serialized:
                result: dict[str, Any] = {
                    "extracted_entities": [
                        {
                            "name": "Alice",
                            "entity_type_id": 0,
                            "episode_indices": [0],
                        },
                        {
                            "name": "Seattle",
                            "entity_type_id": 0,
                            "episode_indices": [0],
                        },
                    ]
                }
            elif "source_entity_name" in serialized and "relation_type" in serialized:
                result = {
                    "edges": [
                        {
                            "source_entity_name": "Alice",
                            "target_entity_name": "Seattle",
                            "relation_type": "MOVED_TO",
                            "fact": "Alice moved to Seattle.",
                            "valid_at": "2024-10-01T08:00:00Z",
                            "invalid_at": None,
                            "episode_indices": [0],
                        }
                    ]
                }
            else:
                raise AssertionError("unexpected Graphiti LLM request schema")
            payload = {
                "id": "local-fake",
                "object": "chat.completion",
                "created": 1,
                "model": "deepseek-v4-flash",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(result),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 11,
                    "completion_tokens": 5,
                    "total_tokens": 16,
                },
            }
            raw = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, format: str, *args: Any) -> None:
            """禁止本地 fake endpoint 污染测试输出。"""

            del format, args

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    paths = load_path_settings(project_root=PROJECT_ROOT)
    runtime = GraphitiRuntime(
        config=GraphitiConfig(
            llm_model="deepseek-v4-flash",
            structured_output_mode="json_object",
            llm_temperature=1.0,
            llm_max_tokens=16384,
            embedding_model_path="models/all-MiniLM-L6-v2",
            embedding_dimension=384,
            embedding_normalize=True,
            query_limit=20,
            max_coroutines=10,
            worker_request_timeout_seconds=120.0,
            max_workers=1,
        ),
        openai_settings=OpenAISettings(
            api_key="local-fake-key",
            base_url=f"http://127.0.0.1:{server.server_port}/v1",
            model="deepseek-v4-flash",
            provider="opencodego",
            judge_transport="chat_completions",
            timeout_seconds=30.0,
            max_retries=0,
        ),
        path_settings=paths,
        storage_root=tmp_path / "method_state",
    )
    try:
        added = runtime.ingest(
            isolation_key="edge_conv",
            operation_id="c" * 64,
            input_digest="d" * 64,
            turn_id="t1",
            session_id="s1",
            episode_body="user: Alice moved to Seattle.",
            reference_time="2024-10-01T08:00:00+00:00",
        )
        report_before = runtime.session_memories(
            isolation_key="edge_conv",
            session_id="s1",
        )
        sidecar_root = (
            tmp_path
            / "method_state"
            / "graphiti_state"
            / "conversation_"
        )
        sidecars = list(sidecar_root.parent.glob("conversation_*/state.json"))
        assert len(sidecars) == 1
        sidecar_before = sidecars[0].read_bytes()
        found = runtime.retrieve(
            isolation_key="edge_conv",
            query="Where did Alice move?",
            limit=10,
        )
        report_after = runtime.session_memories(
            isolation_key="edge_conv",
            session_id="s1",
        )
        sidecar_after = sidecars[0].read_bytes()
    finally:
        runtime.close()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert len(added["episode_uuid"]) == 36
    assert len(added["llm_observations"]) == 2
    assert len(added["embedding_observations"]) >= 1
    assert len(found["embedding_observations"]) == 1
    assert [item["fact"] for item in found["items"]] == [
        "Alice moved to Seattle."
    ]
    assert found["items"][0]["source_turn_ids"] == ["t1"]
    assert report_before == report_after
    assert report_after["memories"] == ["Alice moved to Seattle."]
    assert sidecar_before == sidecar_after
    assert len(requests) == 2
    assert all(
        request.get("thinking") == {"type": "disabled"}
        for request in requests
    )
