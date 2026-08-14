"""EverOS v1.2.3 typed product service 的 provider v3 adapter。

主进程只负责 benchmark 公共字段、物理隔离、sidecar、效率观测回放与
``formatted_memory``。EverOS 及其 Python 3.12 依赖始终运行在独立 worker；worker
进入官方 ``create_app()`` lifespan 后直接调用 typed memorize/search/get service，
不启动 HTTP host，也不绕过产品算法。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import selectors
import shutil
import subprocess
import tempfile
import threading
from time import perf_counter_ns
from typing import Any, Protocol

from memory_benchmark.config import OpenAISettings, PathSettings, load_path_settings
from memory_benchmark.core import ConfigurationError, ImageRef, Turn
from memory_benchmark.core.provider_protocol import (
    EvidenceAssertion,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    RetrievalEvidence,
    RetrievalQuery,
    RetrievalResult,
    RetrievedItem,
    SessionBatch,
    SessionMemoryReport,
    SessionRef,
)
from memory_benchmark.methods.image_text import turn_text_with_images
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
)


EVEROS_ADAPTER_VERSION = "everos-product-chat-v6"
EVEROS_WORKER_SCHEMA_VERSION = "everos-worker-protocol-v2"
EVEROS_METHOD_DIRECTORY = "EverOS"
EVEROS_UPSTREAM_URL = "https://github.com/EverMind-AI/EverOS.git"
EVEROS_COMMIT = "48fc9084888bc17100053227284f939a5aca5e91"
EVEROS_PACKAGE_VERSION = "1.2.3"
EVEROS_PRODUCT_SURFACE = "create_app-lifespan+typed-memorize-search-get"
EVEROS_IMPLEMENTATION_IDENTITY = "product-chat-session-isolated"
EVEROS_LLM_MODEL_ID = "everos-build-llm"
EVEROS_EMBEDDING_MODEL_ID = "everos-embedding"
EVEROS_RERANKER_MODEL_ID = "everos-reranker"
EVEROS_EMPTY_MEMORY_SENTINEL = "(No EverOS episodes retrieved)"
EVEROS_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/everos_adapter.py"
EVEROS_WORKER_LOGICAL_PATH = "src/memory_benchmark/methods/everos_worker.py"
EVEROS_BOOTSTRAP_LOGICAL_PATH = "scripts/bootstrap_everos_runtime.sh"
EVEROS_PATCH_LOGICAL_PATH = "scripts/patches/everos-product-runtime-observability.patch"
EVEROS_STATE_SCHEMA_VERSION = "everos-conversation-sidecar-v2"
EVEROS_ROOT_MARKER = ".memory-benchmark-everos-root.json"
EVEROS_SOURCE_MODE = "vendored-v1.2.3-plus-observability-patch"
EVEROS_SOURCE_FILES = (
    "LICENSE",
    "pyproject.toml",
    "uv.lock",
    "benchmarks/run.py",
    "src/everos/entrypoints/api/app.py",
    "src/everos/entrypoints/api/routes/memorize.py",
    "src/everos/service/memorize.py",
    "src/everos/service/search.py",
    "src/everos/service/get.py",
    "src/everos/memory/search/dto.py",
    "src/everos/memory/get/dto.py",
    "src/everos/config/default.toml",
    "src/everos/config/default_ome.toml",
    "src/everos/core/lifespan/factory.py",
)
# ``everos.toml`` is deliberately absent.  EverOS already loads its shipped
# ``default.toml`` from the vendored package and applies ``EVEROS_*``
# environment variables above it.  Copying the shipped template into an
# experiment root would persist provider endpoints under ``outputs/`` and
# violate the framework secret/base-URL boundary.  OME, by contrast, watches
# a root-local ``ome.toml`` at runtime, so that one template remains required.
_PRODUCT_ROOT_TEMPLATES = {
    "ome.toml": "src/everos/config/default_ome.toml",
}
_ALLOWED_ROLES = frozenset({"user", "assistant"})
_PATH_SAFE_ID_RE = re.compile(r"^[a-zA-Z0-9_.@+-]+$")
_WORKER_PASSTHROUGH_ENV_NAMES = frozenset(
    {
        "CURL_CA_BUNDLE",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "LANG",
        "LC_ALL",
        "NO_PROXY",
        "PATH",
        "REQUESTS_CA_BUNDLE",
        "SSL_CERT_FILE",
        "TMPDIR",
        "TZ",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    }
)


@dataclass(frozen=True)
class EverOSConfig:
    """EverOS product-chat 主 profile 的强类型配置。"""

    llm_model: str
    memory_mode: str
    search_method: str
    add_batch_size: int
    embedding_model: str
    embedding_dimension: int
    embedding_provider: str
    embedding_credential_env: str
    rerank_provider: str
    rerank_model: str
    rerank_credential_env: str
    rerank_capability_mode: str
    app_id: str
    project_id: str
    worker_request_timeout_seconds: float
    drain_timeout_seconds: float
    max_workers: int
    profile_name: str = "product-chat-v1"

    def __post_init__(self) -> None:
        """拒绝偏离 M1/M2 已裁主产品边界的配置。"""

        text_fields = (
            "llm_model",
            "memory_mode",
            "search_method",
            "embedding_model",
            "embedding_provider",
            "embedding_credential_env",
            "rerank_provider",
            "rerank_model",
            "rerank_credential_env",
            "rerank_capability_mode",
            "app_id",
            "project_id",
            "profile_name",
        )
        for field_name in text_fields:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"EverOS {field_name} is required")
        for field_name in ("add_batch_size", "embedding_dimension", "max_workers"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 1:
                raise ConfigurationError(
                    f"EverOS {field_name} must be a positive integer"
                )
        for field_name in (
            "worker_request_timeout_seconds",
            "drain_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(float(value))
                or float(value) <= 0
            ):
                raise ConfigurationError(
                    f"EverOS {field_name} must be positive and finite"
                )
        if self.memory_mode != "chat":
            raise ConfigurationError("EverOS main profile requires memory_mode='chat'")
        if self.search_method != "hybrid":
            raise ConfigurationError(
                "EverOS main profile requires public search_method='hybrid'"
            )
        if self.add_batch_size != 25:
            raise ConfigurationError(
                "EverOS main profile preserves official add_batch_size=25"
            )
        if self.embedding_model != "Qwen/Qwen3-Embedding-4B":
            raise ConfigurationError(
                "EverOS main profile preserves Qwen/Qwen3-Embedding-4B"
            )
        if self.embedding_dimension != 1024:
            raise ConfigurationError(
                "EverOS LanceDB schema requires embedding_dimension=1024"
            )
        if self.embedding_provider not in {
            "deepinfra-openai-compatible",
            "openrouter-openai-compatible",
        }:
            raise ConfigurationError(
                "EverOS embedding_provider must name an approved "
                "OpenAI-compatible Qwen transport"
            )
        expected_credential_env = {
            "deepinfra-openai-compatible": "EVEROS_DEEPINFRA_API_KEY",
            "openrouter-openai-compatible": "openrouter_key",
        }[self.embedding_provider]
        if self.embedding_credential_env != expected_credential_env:
            raise ConfigurationError(
                "EverOS embedding credential environment does not match "
                f"{self.embedding_provider}"
            )
        if self.rerank_provider != "deepinfra":
            raise ConfigurationError(
                "EverOS current product rerank provider must be deepinfra"
            )
        if self.rerank_model != "Qwen/Qwen3-Reranker-4B":
            raise ConfigurationError(
                "EverOS current product rerank model identity drifted"
            )
        if self.rerank_capability_mode not in {
            "configured",
            "disabled-zero-call",
        }:
            raise ConfigurationError(
                "EverOS rerank_capability_mode must be configured or "
                "disabled-zero-call"
            )
        for field_name in ("app_id", "project_id"):
            value = getattr(self, field_name)
            if value in {".", ".."} or _PATH_SAFE_ID_RE.fullmatch(value) is None:
                raise ConfigurationError(
                    f"EverOS {field_name} must satisfy product PathSafeId"
                )

    def to_manifest(self) -> dict[str, Any]:
        """返回不含 secret/base URL/机器绝对路径的运行身份。"""

        return {
            **asdict(self),
            "adapter_version": EVEROS_ADAPTER_VERSION,
            "worker_schema_version": EVEROS_WORKER_SCHEMA_VERSION,
            "implementation_identity": EVEROS_IMPLEMENTATION_IDENTITY,
            "product_surface": EVEROS_PRODUCT_SURFACE,
            "consume_granularity": "session",
            "embedding_distance": "lancedb-l2",
            "missing_timestamp_policy": "require-source-time-v1",
            "timestamp_derivation_policy": "locomo-official-30s-only-v1",
            "locomo_role_policy": "all-user-real-speaker-owner",
            "owner_merge_policy": "score-desc-owner-order-product-rank-v1",
            "input_content_time_prefix": False,
            "product_episode_time_policy": "source-derived-only-v1",
        }


class EverOSRuntimeProtocol(Protocol):
    """adapter 所需的最窄独立 worker runtime 协议。"""

    def ingest_session(
        self,
        *,
        isolation_key: str,
        operation_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        owner_ids: list[str],
    ) -> dict[str, Any]:
        """执行一次 session add+flush+exact drain。"""

    def retrieve(
        self,
        *,
        isolation_key: str,
        owner_ids: list[str],
        query: str,
        top_k: int,
    ) -> dict[str, Any]:
        """执行多 owner public search 与全局稳定合并。"""

    def get_session_memories(
        self,
        *,
        isolation_key: str,
        owner_ids: list[str],
        session_id: str,
    ) -> dict[str, Any]:
        """经 public get 读取一个 product session 的 Episodes。"""

    def delete_conversation(self, *, isolation_key: str) -> dict[str, Any]:
        """安全删除一个 conversation 的物理 product root。"""

    def close(self) -> None:
        """关闭当前 worker；失败必须可见。"""


RuntimeFactory = Callable[..., EverOSRuntimeProtocol]


class EverOSRuntime:
    """一个 provider 独占、按 conversation 切换物理 root 的 worker 控制器。"""

    def __init__(
        self,
        *,
        config: EverOSConfig,
        openai_settings: OpenAISettings,
        path_settings: PathSettings,
        storage_root: Path,
    ) -> None:
        """保存配置；第三方 import、lifespan 与 API client 均推迟到首个 conversation。"""

        self.config = config
        self.openai_settings = openai_settings
        self.path_settings = path_settings
        self.storage_root = storage_root
        self._worker: subprocess.Popen[str] | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr_tail: deque[str] = deque(maxlen=80)
        self._request_lock = threading.Lock()
        self._request_sequence = 0
        self._active_isolation_key: str | None = None
        self._active_root: Path | None = None
        self._closed = False
        self._close_error: BaseException | None = None

    def _everos_root(self) -> Path:
        """返回 source-locked vendored EverOS 根目录。"""

        return self.path_settings.resolve_third_party_method_path(
            EVEROS_METHOD_DIRECTORY
        )

    def _worker_python(self) -> Path:
        """返回独立 Python 3.12 runtime，禁止回落主框架解释器。"""

        python = self._everos_root() / ".venv" / "bin" / "python"
        if not python.is_file():
            raise ConfigurationError(
                "EverOS isolated runtime is missing. Run "
                "scripts/bootstrap_everos_runtime.sh first."
            )
        return python

    def _conversation_root(self, isolation_key: str) -> Path:
        """把公开 isolation key 映射到 storage_root 内固定物理目录。"""

        digest = _namespace_id(isolation_key)
        roots = (self.storage_root / "everos_roots").resolve(strict=False)
        candidate = (roots / digest).resolve(strict=False)
        try:
            candidate.relative_to(roots)
        except ValueError as exc:
            raise ConfigurationError("EverOS conversation root escaped storage root") from exc
        return candidate

    def _worker_environment(self, product_root: Path) -> dict[str, str]:
        """构造最小 worker 环境，secret 仅由环境变量进入子进程。"""

        embedding_key = os.environ.get(self.config.embedding_credential_env)
        if not isinstance(embedding_key, str) or not embedding_key.strip():
            raise ConfigurationError(
                "EverOS embedding credential is missing: set environment variable "
                f"{self.config.embedding_credential_env} before running"
            )
        environment = {
            name: value
            for name, value in os.environ.items()
            if name in _WORKER_PASSTHROUGH_ENV_NAMES
        }
        environment.update(
            {
                "EVEROS_ROOT": str(product_root),
                "EVEROS_MEMORY__TIMEZONE": "UTC",
                "EVEROS_MEMORIZE__MODE": self.config.memory_mode,
                "EVEROS_LLM__MODEL": self.config.llm_model,
                "EVEROS_LLM__API_KEY": self.openai_settings.api_key,
                "EVEROS_LLM__BASE_URL": self.openai_settings.base_url,
                "EVEROS_EMBEDDING__MODEL": self.config.embedding_model,
                "EVEROS_EMBEDDING__API_KEY": embedding_key,
                "EVEROS_EMBEDDING__DIMENSIONS": str(
                    self.config.embedding_dimension
                ),
                "EVEROS_RERANK__PROVIDER": self.config.rerank_provider,
                "EVEROS_RERANK__MODEL": self.config.rerank_model,
                "EVEROS_OBSERVABILITY__ENABLED": "false",
                "PYTHONUNBUFFERED": "1",
            }
        )
        if self.config.embedding_provider == "openrouter-openai-compatible":
            embedding_base_url = os.environ.get(
                "openrouter_base_url"
            ) or os.environ.get("OPENROUTER_BASE_URL")
            if (
                not isinstance(embedding_base_url, str)
                or not embedding_base_url.strip()
            ):
                raise ConfigurationError(
                    "EverOS OpenRouter embedding endpoint is missing: set "
                    "openrouter_base_url or OPENROUTER_BASE_URL before running"
                )
            environment["EVEROS_EMBEDDING__BASE_URL"] = embedding_base_url
        rerank_key = os.environ.get(self.config.rerank_credential_env)
        if self.config.rerank_capability_mode == "configured":
            if not isinstance(rerank_key, str) or not rerank_key.strip():
                raise ConfigurationError(
                    "EverOS configured rerank capability is missing credential: "
                    f"set {self.config.rerank_credential_env} before running"
                )
            environment["EVEROS_RERANK__API_KEY"] = rerank_key
        return environment

    def _activate(self, isolation_key: str) -> None:
        """确保当前子进程唯一绑定请求 conversation 的物理 root。"""

        if self._closed:
            raise ConfigurationError("EverOS runtime is already closed")
        if self._close_error is not None:
            raise ConfigurationError(
                "EverOS runtime is permanently unusable after a cleanup failure"
            ) from self._close_error
        if self._active_isolation_key == isolation_key and self._worker is not None:
            if self._worker.poll() is None:
                return
            raise ConfigurationError(self._worker_failure_text("exited"))
        if self._worker is not None:
            self._shutdown_active()
        product_root, root_marker = self._prepare_product_root(isolation_key)
        worker_path = self.path_settings.project_root / EVEROS_WORKER_LOGICAL_PATH
        if not worker_path.is_file():
            raise ConfigurationError(f"EverOS worker file missing: {worker_path}")
        self._worker = subprocess.Popen(
            [str(self._worker_python()), str(worker_path)],
            cwd=self._everos_root(),
            env=self._worker_environment(product_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._active_isolation_key = isolation_key
        self._active_root = product_root
        self._stderr_thread = threading.Thread(
            target=self._drain_worker_stderr,
            name=f"everos-worker-{id(self)}-stderr",
            daemon=True,
        )
        self._stderr_thread.start()
        try:
            result = self._request(
                "initialize",
                {
                    "adapter_version": EVEROS_ADAPTER_VERSION,
                    "app_id": self.config.app_id,
                    "project_id": self.config.project_id,
                    "add_batch_size": self.config.add_batch_size,
                    "search_method": self.config.search_method,
                    "drain_timeout_seconds": self.config.drain_timeout_seconds,
                    "root_marker": root_marker,
                },
            )
        except BaseException:
            self._terminate_worker()
            self._active_isolation_key = None
            self._active_root = None
            raise
        if (
            result.get("status") != "ready"
            or result.get("adapter_version") != EVEROS_ADAPTER_VERSION
            or result.get("worker_schema_version") != EVEROS_WORKER_SCHEMA_VERSION
            or result.get("product_surface") != EVEROS_PRODUCT_SURFACE
        ):
            self._terminate_worker()
            self._active_isolation_key = None
            self._active_root = None
            raise ConfigurationError("EverOS worker initialize identity mismatch")

    def _prepare_product_root(
        self,
        isolation_key: str,
    ) -> tuple[Path, dict[str, str]]:
        """物化不含 endpoint/credential 的 conversation 产品根目录。"""

        product_root = self._conversation_root(isolation_key)
        product_root.mkdir(parents=True, exist_ok=True)
        root_marker = {
            "adapter_version": EVEROS_ADAPTER_VERSION,
            "everos_commit": EVEROS_COMMIT,
            "isolation_hash": _namespace_id(isolation_key),
            "schema_version": EVEROS_STATE_SCHEMA_VERSION,
        }
        marker_path = product_root / EVEROS_ROOT_MARKER
        if marker_path.is_file():
            try:
                existing_marker = json.loads(marker_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigurationError("EverOS product root marker is invalid") from exc
            if existing_marker != root_marker:
                raise ConfigurationError("EverOS product root marker identity mismatch")
        else:
            if any(product_root.iterdir()):
                raise ConfigurationError(
                    "EverOS refused to initialize a non-empty unmarked product root"
                )
            for target_name, source_relative in _PRODUCT_ROOT_TEMPLATES.items():
                source = self._everos_root() / source_relative
                if not source.is_file():
                    raise ConfigurationError(
                        f"EverOS product root template is missing: {source_relative}"
                    )
                _atomic_write_bytes(product_root / target_name, source.read_bytes())
            _atomic_write_json(marker_path, root_marker)
        for target_name, source_relative in _PRODUCT_ROOT_TEMPLATES.items():
            target = product_root / target_name
            source = self._everos_root() / source_relative
            if not target.is_file() or target.read_bytes() != source.read_bytes():
                raise ConfigurationError(
                    f"EverOS product root config drifted: {target_name}"
                )
        return product_root, root_marker

    def _drain_worker_stderr(self) -> None:
        """持续排空并脱敏保存 worker stderr 尾部。"""

        worker = self._worker
        if worker is None or worker.stderr is None:
            return
        secrets = [self.openai_settings.api_key]
        for env_name in (
            self.config.embedding_credential_env,
            self.config.rerank_credential_env,
        ):
            value = os.environ.get(env_name)
            if value:
                secrets.append(value)
        for line in worker.stderr:
            redacted = line.rstrip()
            for secret in secrets:
                redacted = redacted.replace(secret, "<redacted>")
            self._stderr_tail.append(redacted)

    def _request(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送一条串行 JSON-lines 请求并严格核对响应身份。"""

        worker = self._worker
        if worker is None or worker.stdin is None or worker.stdout is None:
            raise ConfigurationError("EverOS worker is not running")
        with self._request_lock:
            if worker.poll() is not None:
                raise ConfigurationError(self._worker_failure_text("exited"))
            self._request_sequence += 1
            request_id = self._request_sequence
            worker.stdin.write(
                json.dumps(
                    {
                        "request_id": request_id,
                        "command": command,
                        "payload": payload,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                + "\n"
            )
            worker.stdin.flush()
            selector = selectors.DefaultSelector()
            selector.register(worker.stdout, selectors.EVENT_READ)
            try:
                ready = selector.select(self.config.worker_request_timeout_seconds)
            finally:
                selector.close()
            if not ready:
                self._terminate_worker()
                raise ConfigurationError(
                    f"EverOS worker command timed out: {command}; "
                    "the conversation root must be cleaned before retry"
                )
            raw = worker.stdout.readline()
            if not raw:
                raise ConfigurationError(self._worker_failure_text("closed stdout"))
            try:
                response = json.loads(raw)
            except json.JSONDecodeError as exc:
                self._terminate_worker()
                raise ConfigurationError(
                    f"EverOS worker protocol was polluted: {raw[:200]!r}"
                ) from exc
            if not isinstance(response, dict) or response.get("request_id") != request_id:
                self._terminate_worker()
                raise ConfigurationError("EverOS worker response identity mismatch")
            if response.get("ok") is not True:
                raise ConfigurationError(
                    f"EverOS worker {command} failed "
                    f"[{response.get('error_type')}]: {response.get('error')}"
                )
            result = response.get("result")
            if not isinstance(result, dict):
                raise ConfigurationError("EverOS worker result must be an object")
            return result

    def _worker_failure_text(self, state: str) -> str:
        """构造不含 secret 的 worker 失败摘要。"""

        tail = "\n".join(self._stderr_tail)[-3000:]
        return f"EverOS worker {state}; stderr tail: {tail}"

    def ingest_session(
        self,
        *,
        isolation_key: str,
        operation_id: str,
        session_id: str,
        messages: list[dict[str, Any]],
        owner_ids: list[str],
    ) -> dict[str, Any]:
        """经 worker 执行 session add、flush、exact drain 与 public get。"""

        self._activate(isolation_key)
        return self._request(
            "ingest_session",
            {
                "operation_id": operation_id,
                "session_id": session_id,
                "messages": messages,
                "owner_ids": owner_ids,
            },
        )

    def retrieve(
        self,
        *,
        isolation_key: str,
        owner_ids: list[str],
        query: str,
        top_k: int,
    ) -> dict[str, Any]:
        """经 worker 调用 public HYBRID search 并合并 owner 结果。"""

        self._activate(isolation_key)
        return self._request(
            "retrieve",
            {"owner_ids": owner_ids, "query": query, "top_k": top_k},
        )

    def get_session_memories(
        self,
        *,
        isolation_key: str,
        owner_ids: list[str],
        session_id: str,
    ) -> dict[str, Any]:
        """经 worker 的 public get 读取 session-local Episode。"""

        self._activate(isolation_key)
        return self._request(
            "get_session_memories",
            {"owner_ids": owner_ids, "session_id": session_id},
        )

    def delete_conversation(self, *, isolation_key: str) -> dict[str, Any]:
        """先关闭同 root worker，再以 marker+containment 删除唯一物理目录。"""

        if self._active_isolation_key == isolation_key and self._worker is not None:
            self._shutdown_active()
        root = self._conversation_root(isolation_key)
        expected = {
            "adapter_version": EVEROS_ADAPTER_VERSION,
            "everos_commit": EVEROS_COMMIT,
            "isolation_hash": _namespace_id(isolation_key),
            "schema_version": EVEROS_STATE_SCHEMA_VERSION,
        }
        tombstone = root.with_name(f".{root.name}.cleanup")
        cleanup_marker = root.with_name(f".{root.name}.cleanup.json")
        if root.exists() and tombstone.exists():
            raise ConfigurationError(
                "EverOS clean retry found both live root and cleanup tombstone"
            )
        if cleanup_marker.exists():
            try:
                cleanup_identity = json.loads(
                    cleanup_marker.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigurationError(
                    "EverOS cleanup marker is invalid"
                ) from exc
            if cleanup_identity != expected:
                raise ConfigurationError(
                    "EverOS cleanup marker does not match isolation identity"
                )
        if root.exists():
            try:
                raw_marker = json.loads(
                    (root / EVEROS_ROOT_MARKER).read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigurationError(
                    "EverOS clean retry refused an unmarked conversation root"
                ) from exc
            if raw_marker != expected:
                raise ConfigurationError(
                    "EverOS clean retry root marker does not match isolation identity"
                )
        elif tombstone.exists() and not cleanup_marker.exists():
            try:
                raw_marker = json.loads(
                    (tombstone / EVEROS_ROOT_MARKER).read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError) as exc:
                raise ConfigurationError(
                    "EverOS clean retry refused an unmarked cleanup tombstone"
                ) from exc
            if raw_marker != expected:
                raise ConfigurationError(
                    "EverOS cleanup tombstone does not match isolation identity"
                )
        if not cleanup_marker.exists() and (root.exists() or tombstone.exists()):
            _atomic_write_json(cleanup_marker, expected)
        elif (
            not root.exists()
            and not tombstone.exists()
            and not cleanup_marker.exists()
        ):
            return {"deleted": True, "already_absent": True}
        if root.exists():
            root.rename(tombstone)
        if not tombstone.exists():
            cleanup_marker.unlink(missing_ok=True)
            if cleanup_marker.exists():
                raise ConfigurationError("EverOS cleanup marker remains after cleanup")
            return {"deleted": True, "already_absent": False}
        shutil.rmtree(tombstone)
        if root.exists() or tombstone.exists():
            raise ConfigurationError("EverOS conversation root remains after cleanup")
        cleanup_marker.unlink(missing_ok=True)
        if cleanup_marker.exists():
            raise ConfigurationError("EverOS cleanup marker remains after cleanup")
        return {"deleted": True, "already_absent": False}

    def close(self) -> None:
        """关闭最后一个 worker；shutdown 失败后永久 fail-closed。"""

        if self._closed:
            return
        if self._close_error is not None:
            raise ConfigurationError(
                "EverOS runtime cleanup previously failed and cannot be retried safely"
            ) from self._close_error
        try:
            if self._worker is not None:
                self._shutdown_active()
        except BaseException as exc:
            self._close_error = exc
            raise
        self._closed = True

    def _shutdown_active(self) -> None:
        """要求 worker 经 patched lifespan 完整退出，不把 terminate 冒充成功。"""

        worker = self._worker
        if worker is None:
            return
        if worker.poll() is None:
            try:
                result = self._request("shutdown", {})
                if result.get("status") != "closed":
                    raise ConfigurationError(
                        "EverOS worker did not confirm patched lifespan shutdown"
                    )
                worker.wait(timeout=15)
            except BaseException:
                self._terminate_worker()
                raise
        self._terminate_worker()
        self._active_isolation_key = None
        self._active_root = None

    def _terminate_worker(self) -> None:
        """尽力终止子进程并关闭 pipe；只用于资源回收，不提交业务成功。"""

        worker = self._worker
        if worker is None:
            return
        if worker.poll() is None:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
        for stream in (worker.stdin, worker.stdout, worker.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        self._worker = None


class EverOS(MemoryProvider):
    """EverOS product-chat 的 session 粒度 provider。"""

    consume_granularity = "session"
    provenance_granularity = "none"

    def __init__(
        self,
        *,
        config: EverOSConfig,
        path_settings: PathSettings,
        storage_root: Path,
        openai_settings: OpenAISettings,
        efficiency_collector: EfficiencyCollector | None = None,
        benchmark_name: str | None = None,
        session_memory_report: bool = False,
        completed_conversation_ids: set[str] | None = None,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        """保存构造依赖；真实 product runtime 保持 lazy。"""

        if config.llm_model != openai_settings.model:
            raise ConfigurationError(
                "EverOS config llm_model must match selected API runtime model"
            )
        self.config = config
        self.path_settings = path_settings
        self.storage_root = storage_root
        self.openai_settings = openai_settings
        self.efficiency_collector = efficiency_collector
        self.benchmark_name = benchmark_name
        self.session_memory_report = session_memory_report
        self._runtime_factory = runtime_factory or EverOSRuntime
        self._runtime: EverOSRuntimeProtocol | None = None
        self._cleaned = False
        self._observed_operation_ids: set[str] = set()
        self._session_reports: dict[tuple[str, str | None], list[str]] = {}
        self._completed_conversation_ids = set(completed_conversation_ids or ())

    def prepare(self, run_context: Any) -> None:
        """只核 source/runtime 文件；conversation root 在首个 ingest/retrieve 激活。"""

        del run_context
        everos_root = self.path_settings.resolve_third_party_method_path(
            EVEROS_METHOD_DIRECTORY
        )
        if not (everos_root / "pyproject.toml").is_file():
            raise ConfigurationError("EverOS vendored source is missing")
        if self._runtime_factory is EverOSRuntime:
            python = everos_root / ".venv" / "bin" / "python"
            if not python.is_file():
                raise ConfigurationError(
                    "EverOS isolated runtime is missing. Run "
                    "scripts/bootstrap_everos_runtime.sh first."
                )

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """把一个 canonical session 无损转换成 typed product messages。"""

        if not isinstance(unit, SessionBatch):
            raise ConfigurationError("EverOS provider only accepts SessionBatch")
        if not unit.events:
            return IngestResult(
                unit_ref=unit.ref,
                session_memories=[] if self.session_memory_report else None,
                metadata={"method": "everos", "source_message_count": 0},
            )
        messages, owners, audit = self._build_messages(unit)
        product_session_id = _product_session_id(
            unit.isolation_key,
            unit.session_id,
        )
        operation_id = _operation_id(
            isolation_key=unit.isolation_key,
            source_session_id=unit.session_id,
            product_session_id=product_session_id,
            messages=messages,
            owner_ids=owners,
        )
        sidecar = self._load_sidecar(unit.isolation_key)
        completed = sidecar["completed_operations"].get(operation_id)
        input_digest = _input_digest(
            product_session_id=product_session_id,
            messages=messages,
            owner_ids=owners,
        )
        if completed is not None:
            if completed.get("input_digest") != input_digest:
                raise ConfigurationError(
                    "EverOS operation id was reused with a different input"
                )
            session_memories = _required_text_list(
                completed.get("session_memories"),
                "completed.session_memories",
                allow_empty=True,
            )
            self._session_reports[(unit.isolation_key, unit.session_id)] = list(
                session_memories
            )
            return IngestResult(
                unit_ref=unit.ref,
                session_memories=(
                    list(session_memories) if self.session_memory_report else None
                ),
                metadata={
                    "method": "everos",
                    "operation_id": operation_id,
                    "operation_reused": True,
                    "source_message_count": len(unit.events),
                    "product_message_count": len(messages),
                    "product_owner_count": len(owners),
                    "synthetic_owner_anchor_count": audit[
                        "synthetic_owner_anchor_count"
                    ],
                    "derived_timestamp_count": audit[
                        "derived_timestamp_count"
                    ],
                },
            )
        result = self._require_runtime().ingest_session(
            isolation_key=unit.isolation_key,
            operation_id=operation_id,
            session_id=product_session_id,
            messages=messages,
            owner_ids=owners,
        )
        self._record_observations(operation_id, result, stage=EfficiencyStage.MEMORY_BUILD)
        session_items = _required_object_list(result.get("session_items"), "session_items")
        session_memories = [_episode_content(item) for item in session_items]
        next_sidecar = _sidecar_after_operation(
            sidecar,
            isolation_key=unit.isolation_key,
            source_session_id=unit.session_id,
            product_session_id=product_session_id,
            operation_id=operation_id,
            input_digest=input_digest,
            owner_ids=owners,
            source_audit=audit,
            session_memories=session_memories,
        )
        self._write_sidecar(unit.isolation_key, next_sidecar)
        self._session_reports[(unit.isolation_key, unit.session_id)] = list(
            session_memories
        )
        return IngestResult(
            unit_ref=unit.ref,
            session_memories=(
                list(session_memories) if self.session_memory_report else None
            ),
            metadata={
                "method": "everos",
                "operation_id": operation_id,
                "operation_reused": False,
                "source_message_count": len(unit.events),
                "product_message_count": len(messages),
                "product_owner_count": len(owners),
                "session_memory_count": len(session_memories),
                "synthetic_owner_anchor_count": audit[
                    "synthetic_owner_anchor_count"
                ],
                "derived_timestamp_count": audit[
                    "derived_timestamp_count"
                ],
                "exact_drain": _required_bool(result.get("exact_drain"), "exact_drain"),
            },
        )

    def _build_messages(
        self,
        unit: SessionBatch,
    ) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
        """构造产品消息及不进入算法的 source-time/lineage 审计事实。"""

        locomo = self.benchmark_name == "locomo"
        conversation_owner = _product_owner_id(unit.isolation_key, "user")
        assistant_sender = _product_owner_id(unit.isolation_key, "assistant")
        timestamp_rows = _product_timestamps(
            unit.events,
            session_time=unit.session_time,
            locomo_official_sequence=locomo,
        )
        owners: list[str] = []
        messages: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        has_user = False
        for event, timestamp_row in zip(unit.events, timestamp_rows, strict=True):
            if locomo:
                speaker = event.speaker_name or event.role
                if not speaker.strip():
                    raise ConfigurationError("EverOS LoCoMo speaker name is missing")
                role = "user"
                sender_id = _product_owner_id(unit.isolation_key, f"speaker:{speaker}")
                sender_name = speaker
                if sender_id not in owners:
                    owners.append(sender_id)
                has_user = True
            else:
                role = event.role
                if role not in _ALLOWED_ROLES:
                    raise ConfigurationError(
                        "EverOS chat profile only accepts canonical user/assistant roles: "
                        f"{role!r}"
                    )
                has_user = has_user or role == "user"
                sender_id = conversation_owner if role == "user" else assistant_sender
                sender_name = event.speaker_name or role
                if role == "user" and conversation_owner not in owners:
                    owners.append(conversation_owner)
            content = _event_content(event)
            if not content.strip():
                raise ConfigurationError(
                    f"EverOS canonical turn has no visible content: {event.turn_id}"
                )
            messages.append(
                {
                    "sender_id": sender_id,
                    "sender_name": sender_name,
                    "role": role,
                    "timestamp": timestamp_row["product_timestamp_ms"],
                    "content": content,
                }
            )
            source_rows.append(
                {
                    "turn_id": event.turn_id,
                    "source_timestamp": timestamp_row["source_timestamp"],
                    "product_timestamp_ms": timestamp_row[
                        "product_timestamp_ms"
                    ],
                    "timestamp_kind": timestamp_row["timestamp_kind"],
                    "synthetic_anchor": False,
                }
            )
        synthetic_anchor_count = 0
        if not has_user:
            anchor_ts = max(1, messages[0]["timestamp"] - 1)
            messages.insert(
                0,
                {
                    "sender_id": conversation_owner,
                    "sender_name": None,
                    "role": "user",
                    "timestamp": anchor_ts,
                    "content": "",
                },
            )
            source_rows.insert(
                0,
                {
                    "turn_id": None,
                    "source_timestamp": None,
                    "product_timestamp_ms": anchor_ts,
                    "timestamp_kind": "structural-owner-anchor",
                    "synthetic_anchor": True,
                },
            )
            owners.append(conversation_owner)
            synthetic_anchor_count = 1
        return (
            messages,
            owners,
            {
                "source_rows": source_rows,
                "synthetic_owner_anchor_count": synthetic_anchor_count,
                "derived_timestamp_count": sum(
                    row["timestamp_kind"] != "source-exact" for row in source_rows
                ),
            },
        )
    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """HaluMem 只返回当前 session 经 public get 可见的 Episode。"""

        if not self.session_memory_report:
            return None
        key = (ref.isolation_key, ref.session_id)
        memories = self._session_reports.get(key)
        if memories is None:
            sidecar = self._load_sidecar(ref.isolation_key)
            session_record = sidecar["sessions"].get(_sidecar_session_key(ref.session_id))
            if not isinstance(session_record, dict):
                raise ConfigurationError(
                    "EverOS session report requested before successful session ingest"
                )
            product_session_id = _required_text(
                session_record.get("product_session_id"),
                "session.product_session_id",
            )
            owners = _required_text_list(
                sidecar.get("owner_ids"), "sidecar.owner_ids", allow_empty=False
            )
            result = self._require_runtime().get_session_memories(
                isolation_key=ref.isolation_key,
                owner_ids=owners,
                session_id=product_session_id,
            )
            memories = [
                _episode_content(item)
                for item in _required_object_list(
                    result.get("session_items"), "session_items"
                )
            ]
            self._session_reports[key] = memories
        return SessionMemoryReport(
            session_ref=ref,
            memories=list(memories),
            metadata={
                "method": "everos",
                "scope": "session-local-public-get",
                "memory_unit": "episode",
            },
        )

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """调用 public HYBRID search，保留 product rank/score 与零命中。"""

        sidecar = self._load_sidecar(query.isolation_key)
        owners = _required_text_list(
            sidecar.get("owner_ids"), "sidecar.owner_ids", allow_empty=False
        )
        started_ns = perf_counter_ns()
        result = self._require_runtime().retrieve(
            isolation_key=query.isolation_key,
            owner_ids=owners,
            query=query.query_text,
            top_k=query.top_k,
        )
        latency_ms = max(0.0, (perf_counter_ns() - started_ns) / 1_000_000)
        self._record_retrieval_observations(result)
        raw_items = _required_object_list(result.get("items"), "items")
        session_semantics = {
            record.get("product_session_id"): record
            for record in sidecar["sessions"].values()
            if isinstance(record, dict)
        }
        items = tuple(
            _retrieved_item(index, raw, session_semantics)
            for index, raw in enumerate(raw_items, start=1)
        )
        formatted = _format_everos_items(items)
        if self.efficiency_collector is not None:
            self.efficiency_collector.record_retrieval_result_if_question_scope(
                latency_ms=latency_ms,
                injected_memory_context_tokens=None,
            )
        return RetrievalResult(
            formatted_memory=formatted or EVEROS_EMPTY_MEMORY_SENTINEL,
            items=items,
            metadata={
                "method": "everos",
                "prompt_track": "unified",
                "product_surface": EVEROS_PRODUCT_SURFACE,
                "search_method": self.config.search_method,
                "owner_count": len(owners),
                "owner_merge_policy": "score-desc-owner-order-product-rank-v1",
                "query_consumed_by_method": True,
                "stable_product_ranking": True,
                "provenance_granularity": "none",
                "worker_search_latency_ms": _required_non_negative_number(
                    result.get("latency_ms"), "latency_ms"
                ),
            },
            evidence=_everos_retrieval_evidence(),
        )

    def _record_observations(
        self,
        operation_id: str,
        result: dict[str, Any],
        *,
        stage: EfficiencyStage,
    ) -> None:
        """把 worker 捕获的 exact API usage 按成功 operation 回放一次。"""

        llm = _required_object_list(result.get("llm_observations"), "llm_observations")
        embedding = _required_object_list(
            result.get("embedding_observations"), "embedding_observations"
        )
        self._assert_no_rerank_observations(result, stage="memory build")
        if operation_id in self._observed_operation_ids:
            return
        collector = self.efficiency_collector
        if collector is not None:
            with collector.operation_stage(stage):
                for observation in llm:
                    collector.record_llm_call(
                        model_id=EVEROS_LLM_MODEL_ID,
                        input_tokens=_required_non_negative_int(
                            observation.get("input_tokens"), "input_tokens"
                        ),
                        output_tokens=_required_non_negative_int(
                            observation.get("output_tokens"), "output_tokens"
                        ),
                        token_measurement_source=MeasurementSource.API_USAGE,
                    )
                for observation in embedding:
                    collector.record_embedding_call(
                        model_id=EVEROS_EMBEDDING_MODEL_ID,
                        input_tokens=_required_non_negative_int(
                            observation.get("input_tokens"), "input_tokens"
                        ),
                        latency_ms=_required_non_negative_number(
                            observation.get("latency_ms"), "latency_ms"
                        ),
                        token_measurement_source=MeasurementSource.API_USAGE,
                        latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
                    )
        self._observed_operation_ids.add(operation_id)

    def _record_retrieval_observations(self, result: dict[str, Any]) -> None:
        """回放一次检索 embedding；HYBRID 主轨不得暗中调用 LLM/rerank。"""

        llm = _required_object_list(result.get("llm_observations"), "llm_observations")
        if llm:
            raise ConfigurationError("EverOS HYBRID retrieval unexpectedly called an LLM")
        self._assert_no_rerank_observations(result, stage="retrieval")
        embedding = _required_object_list(
            result.get("embedding_observations"), "embedding_observations"
        )
        collector = self.efficiency_collector
        if collector is None:
            return
        with collector.operation_stage(EfficiencyStage.RETRIEVAL):
            for observation in embedding:
                collector.record_embedding_call(
                    model_id=EVEROS_EMBEDDING_MODEL_ID,
                    input_tokens=_required_non_negative_int(
                        observation.get("input_tokens"), "input_tokens"
                    ),
                    latency_ms=_required_non_negative_number(
                        observation.get("latency_ms"), "latency_ms"
                    ),
                    token_measurement_source=MeasurementSource.API_USAGE,
                    latency_measurement_source=MeasurementSource.FRAMEWORK_TIMER,
                )

    @staticmethod
    def _assert_no_rerank_observations(
        result: dict[str, Any],
        *,
        stage: str,
    ) -> None:
        """锁定 chat/Episode 主轨为 rerank 零调用；未知 shape 同样拒绝。"""

        observations = _required_object_list(
            result.get("rerank_observations"), "rerank_observations"
        )
        for observation in observations:
            _required_positive_int(
                observation.get("document_count"), "document_count"
            )
            _required_non_negative_number(
                observation.get("latency_ms"), "latency_ms"
            )
            if set(observation) != {"document_count", "latency_ms"}:
                raise ConfigurationError(
                    "EverOS rerank observation has invalid shape"
                )
        if observations:
            raise ConfigurationError(
                f"EverOS {stage} unexpectedly called the product reranker"
            )

    def cleanup(self) -> None:
        """关闭独占 runtime；成功后才提交 provider cleaned 状态。"""

        if self._cleaned:
            return
        runtime = self._runtime
        if runtime is not None:
            runtime.close()
        self._runtime = None
        self._cleaned = True

    def _require_runtime(self) -> EverOSRuntimeProtocol:
        """懒构造并复用 provider 唯一 runtime 控制器。"""

        if self._cleaned:
            raise ConfigurationError("EverOS provider is already cleaned")
        if self._runtime is None:
            self._runtime = self._runtime_factory(
                config=self.config,
                openai_settings=self.openai_settings,
                path_settings=self.path_settings,
                storage_root=self.storage_root,
            )
        return self._runtime

    def _sidecar_path(self, isolation_key: str) -> Path:
        """返回 conversation sidecar 路径。"""

        return self.storage_root / "everos_sidecars" / f"{_namespace_id(isolation_key)}.json"

    def _load_sidecar(self, isolation_key: str) -> dict[str, Any]:
        """读取并严格校验 sidecar；不存在时返回未提交空状态。"""

        path = self._sidecar_path(isolation_key)
        if not path.is_file():
            return _empty_sidecar(isolation_key)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"invalid EverOS sidecar: {path}") from exc
        return _validate_sidecar(raw, isolation_key=isolation_key)

    def _write_sidecar(self, isolation_key: str, sidecar: dict[str, Any]) -> None:
        """强校验后原子写 sidecar，避免半截 JSON 冒充 resume 权威。"""

        normalized = _validate_sidecar(sidecar, isolation_key=isolation_key)
        _atomic_write_json(self._sidecar_path(isolation_key), normalized)


def validate_everos_variant(benchmark_name: str, variant: str) -> None:
    """在 output/runtime/API 前拒绝无法诚实表达的 MemBench 100K。"""

    if benchmark_name == "membench" and variant == "100k":
        raise ConfigurationError(
            "EverOS does not support MemBench variant '100k': official noise "
            "turns may lack source timestamps, while the typed product API "
            "requires milliseconds and its Episode prompt renders them into "
            "answer-visible memory; timestamp fabrication is forbidden"
        )


def clean_everos_conversation_state(
    *,
    provider: EverOS,
    isolation_key: str,
) -> None:
    """清理 failed-ingest 的 product root 与 framework sidecar。"""

    result = provider._require_runtime().delete_conversation(
        isolation_key=isolation_key
    )
    if result.get("deleted") is not True:
        raise ConfigurationError("EverOS runtime did not confirm root deletion")
    sidecar = provider._sidecar_path(isolation_key)
    sidecar.unlink(missing_ok=True)
    if sidecar.exists():
        raise ConfigurationError("EverOS sidecar remains after clean retry")


def _namespace_id(isolation_key: str) -> str:
    """生成固定长度、路径安全的 conversation 物理 namespace。"""

    if not isinstance(isolation_key, str) or not isolation_key.strip():
        raise ConfigurationError("EverOS isolation_key is required")
    return hashlib.sha256(
        f"{EVEROS_ADAPTER_VERSION}|{isolation_key}".encode("utf-8")
    ).hexdigest()[:32]


def _product_owner_id(isolation_key: str, owner_label: str) -> str:
    """生成产品 PathSafeId owner，不把 benchmark 原始名字用于路径。"""

    digest = hashlib.sha256(
        f"{EVEROS_ADAPTER_VERSION}|{isolation_key}|owner|{owner_label}".encode(
            "utf-8"
        )
    ).hexdigest()[:32]
    return f"u-{digest}"


def _product_session_id(isolation_key: str, session_id: str | None) -> str:
    """生成稳定、长度有界的 product session id。"""

    label = "<none>" if session_id is None else session_id
    digest = hashlib.sha256(
        f"{EVEROS_ADAPTER_VERSION}|{isolation_key}|session|{label}".encode("utf-8")
    ).hexdigest()[:32]
    return f"s-{digest}"


def _operation_id(
    *,
    isolation_key: str,
    source_session_id: str | None,
    product_session_id: str,
    messages: list[dict[str, Any]],
    owner_ids: list[str],
) -> str:
    """生成同输入重试稳定、任一 payload 漂移即变化的 operation id。"""

    payload = {
        "adapter_version": EVEROS_ADAPTER_VERSION,
        "isolation_key": isolation_key,
        "source_session_id": source_session_id,
        "product_session_id": product_session_id,
        "messages": messages,
        "owner_ids": owner_ids,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _input_digest(
    *,
    product_session_id: str,
    messages: list[dict[str, Any]],
    owner_ids: list[str],
) -> str:
    """计算 sidecar operation journal 的稳定公开输入摘要。"""

    return hashlib.sha256(
        json.dumps(
            {
                "product_session_id": product_session_id,
                "messages": messages,
                "owner_ids": owner_ids,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _event_content(event: Any) -> str:
    """从 original content + image sidecar 重建共享 caption 文本。"""

    original = event.metadata.get("original_content")
    content = original if isinstance(original, str) else event.content
    turn_metadata = event.metadata.get("turn_metadata")
    if not isinstance(turn_metadata, dict):
        turn_metadata = {}
    turn = Turn(
        turn_id=event.turn_id,
        speaker=event.speaker_name or event.role,
        normalized_role=event.role if event.role in _ALLOWED_ROLES else None,
        content=content,
        turn_time=(
            event.metadata.get("original_turn_time")
            if isinstance(event.metadata.get("original_turn_time"), str)
            else None
        ),
        metadata=dict(turn_metadata),
        images=_images_from_event(event),
    )
    return turn_text_with_images(turn)


def _images_from_event(event: Any) -> list[ImageRef]:
    """恢复 caption；path/query 等 locator 不进入算法 content。"""

    raw_images = event.metadata.get("turn_images")
    if not isinstance(raw_images, list):
        return []
    return [
        ImageRef(
            image_id=raw.get("image_id"),
            path=raw.get("path"),
            caption=raw.get("caption"),
            metadata=dict(raw.get("metadata") or {}),
        )
        for raw in raw_images
        if isinstance(raw, dict)
    ]


def _product_timestamps(
    events: tuple[Any, ...],
    *,
    session_time: str | None,
    locomo_official_sequence: bool,
) -> list[dict[str, Any]]:
    """把 source time 转为 Unix ms；缺失 source time 时拒绝产品调用。

    LoCoMo current official harness 在 session source time 上按 utterance 加 30 秒；
    主轨沿用这个产品输入姿势，但 sidecar 仍把每条 source time 记为原 session time，
    不把派生秒数宣称成数据集事实。除此之外不制造时间：EverOS v1.2.3 的 typed
    API 虽然只要求正毫秒值，但 bundled Episode prompt 会把每条消息时间强制写入
    生成记忆；transport sentinel 因此会变成 answer-visible 的伪事实。
    """

    source_values: list[str | None] = []
    parsed: list[int | None] = []
    for event in events:
        raw_turn = event.metadata.get("original_turn_time")
        raw_session = event.metadata.get("original_session_time")
        source = (
            raw_turn.strip()
            if isinstance(raw_turn, str) and raw_turn.strip()
            else (
                raw_session.strip()
                if isinstance(raw_session, str) and raw_session.strip()
                else (
                    session_time.strip()
                    if isinstance(session_time, str) and session_time.strip()
                    else None
                )
            )
        )
        source_values.append(source)
        parsed.append(_parse_timestamp_ms(source))
    if locomo_official_sequence and parsed and parsed[0] is not None:
        base = parsed[0]
        return [
            {
                "source_timestamp": source_values[index],
                "product_timestamp_ms": base + index * 30_000,
                "timestamp_kind": (
                    "source-exact" if index == 0 else "locomo-official-30s-order"
                ),
            }
            for index in range(len(events))
        ]
    missing_turn_ids = [
        str(event.turn_id)
        for event, current in zip(events, parsed, strict=True)
        if current is None
    ]
    if missing_turn_ids:
        preview = ", ".join(missing_turn_ids[:3])
        suffix = "" if len(missing_turn_ids) <= 3 else ", ..."
        raise ConfigurationError(
            "EverOS requires source time for every non-LoCoMo turn because its "
            "Episode prompt renders message timestamps into memory; refusing to "
            f"fabricate time for turn(s): {preview}{suffix}"
        )
    return [
        {
            "source_timestamp": source_values[index],
            "product_timestamp_ms": current,
            "timestamp_kind": "source-exact",
        }
        for index, current in enumerate(parsed)
        if current is not None
    ]


def _parse_timestamp_ms(value: str | None) -> int | None:
    """解析五 benchmark 已知公开时间格式为 UTC Unix 毫秒。"""

    if value is None or not value.strip():
        return None
    text = value.strip()
    candidates: list[datetime] = []
    try:
        candidates.append(datetime.fromisoformat(text.replace("Z", "+00:00")))
    except ValueError:
        pass
    for timestamp_format in (
        "%Y/%m/%d (%a) %H:%M",
        "%Y-%m-%d %H:%M",
        "%B-%d-%Y",
        "%b %d, %Y, %H:%M:%S",
        "%I:%M %p on %d %B, %Y",
    ):
        try:
            candidates.append(datetime.strptime(text, timestamp_format))
            break
        except ValueError:
            continue
    if not candidates:
        return None
    parsed = candidates[0]
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    milliseconds = int(parsed.timestamp() * 1000)
    return milliseconds if milliseconds > 0 else None


def _episode_content(raw: dict[str, Any]) -> str:
    """把完整 Episode answer-visible 字段无损渲染为单条 memory。"""

    summary = _required_text(raw.get("summary"), "episode.summary")
    subject = _required_text(raw.get("subject"), "episode.subject")
    episode = _required_text(raw.get("episode"), "episode.episode")
    atomic_facts = raw.get("atomic_facts", [])
    if not isinstance(atomic_facts, list):
        raise ConfigurationError("EverOS episode.atomic_facts must be a list")
    fact_texts: list[str] = []
    for fact in atomic_facts:
        if not isinstance(fact, dict):
            raise ConfigurationError("EverOS atomic fact must be an object")
        content = fact.get("content")
        if isinstance(content, str) and content.strip():
            fact_texts.append(content.strip())
    parts = [f"Subject: {subject}", f"Summary: {summary}", f"Episode: {episode}"]
    if fact_texts:
        parts.append("Atomic facts:\n- " + "\n- ".join(fact_texts))
    return "\n".join(parts)


def _retrieved_item(
    rank: int,
    raw: dict[str, Any],
    session_semantics: dict[Any, dict[str, Any]],
) -> RetrievedItem:
    """把 public search Episode 转成协议条目，不伪造 source lineage。"""

    item_id = _required_text(raw.get("id"), "item.id")
    score = _required_finite_number(raw.get("score"), "item.score")
    product_session_id = raw.get("session_id")
    if product_session_id is not None and not isinstance(product_session_id, str):
        raise ConfigurationError("EverOS item.session_id must be text or null")
    timestamp = raw.get("timestamp")
    if timestamp is not None and not isinstance(timestamp, str):
        raise ConfigurationError("EverOS item.timestamp must be text or null")
    session_record = session_semantics.get(product_session_id)
    source_time_exact = bool(
        isinstance(session_record, dict)
        and session_record.get("derived_timestamp_count") == 0
    )
    sender_ids = raw.get("sender_ids", [])
    if not isinstance(sender_ids, list) or not all(
        isinstance(sender_id, str) and sender_id.strip()
        for sender_id in sender_ids
    ):
        raise ConfigurationError("EverOS item.sender_ids must be a text list")
    return RetrievedItem(
        item_id=item_id,
        content=_episode_content(raw),
        score=score,
        timestamp=timestamp if source_time_exact else None,
        source_turn_ids=(),
        metadata={
            "product_rank": rank,
            "product_session_id": product_session_id,
            "product_timestamp": timestamp,
            "timestamp_semantics": (
                "source-derived-product-time"
                if source_time_exact
                else "method-operational-or-unmapped-not-source-exact"
            ),
            "sender_ids": list(sender_ids),
            "memory_type": raw.get("type"),
        },
    )


def _format_everos_items(items: tuple[RetrievedItem, ...]) -> str:
    """按产品全局 rank 生成 benchmark unified builder 的 memory 文本。"""

    chunks: list[str] = []
    for rank, item in enumerate(items, start=1):
        attributes = [
            f'rank="{rank}"',
            f'id="{html.escape(item.item_id, quote=True)}"',
        ]
        if item.score is not None:
            attributes.append(f'score="{item.score:.12g}"')
        product_time = item.timestamp
        if isinstance(product_time, str) and product_time.strip():
            attributes.append(
                f'product_time="{html.escape(product_time, quote=True)}"'
            )
        chunks.append(
            f"<episode {' '.join(attributes)}>{html.escape(item.content)}</episode>"
        )
    return "\n\n".join(chunks)


def _everos_retrieval_evidence() -> RetrievalEvidence:
    """声明 synthesized Episode provenance N/A 与稳定 product rank。"""

    return RetrievalEvidence(
        semantic_provenance=EvidenceAssertion(
            status="n_a",
            reason_code="everos_episode_is_synthesized_not_source_exact",
            reason=(
                "EverOS retrieves synthesized Episodes and optional atomic facts; "
                "public search results do not expose a lossless semantic mapping "
                "from each current memory to benchmark source evidence units."
            ),
        ),
        provenance_granularity="none",
        stable_ranking=EvidenceAssertion(status="valid"),
    )


def _empty_sidecar(isolation_key: str) -> dict[str, Any]:
    """构造尚未提交 operation 的 conversation sidecar。"""

    return {
        "adapter_version": EVEROS_ADAPTER_VERSION,
        "completed_operations": {},
        "isolation_hash": _namespace_id(isolation_key),
        "owner_ids": [],
        "schema_version": EVEROS_STATE_SCHEMA_VERSION,
        "sessions": {},
    }


def _validate_sidecar(value: Any, *, isolation_key: str) -> dict[str, Any]:
    """严格校验 sidecar，不接受旧 schema 或宽松缺键。"""

    expected = {
        "adapter_version",
        "completed_operations",
        "isolation_hash",
        "owner_ids",
        "schema_version",
        "sessions",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ConfigurationError("EverOS sidecar has an invalid top-level shape")
    if value.get("adapter_version") != EVEROS_ADAPTER_VERSION:
        raise ConfigurationError("EverOS sidecar adapter version mismatch")
    if value.get("schema_version") != EVEROS_STATE_SCHEMA_VERSION:
        raise ConfigurationError("EverOS sidecar schema version mismatch")
    if value.get("isolation_hash") != _namespace_id(isolation_key):
        raise ConfigurationError("EverOS sidecar isolation identity mismatch")
    owners = _required_text_list(
        value.get("owner_ids"), "sidecar.owner_ids", allow_empty=True
    )
    if len(owners) != len(set(owners)):
        raise ConfigurationError("EverOS sidecar owner_ids contain duplicates")
    operations = value.get("completed_operations")
    sessions = value.get("sessions")
    if not isinstance(operations, dict) or not isinstance(sessions, dict):
        raise ConfigurationError("EverOS sidecar operations/sessions must be objects")
    normalized_operations: dict[str, dict[str, Any]] = {}
    for operation_id, operation in operations.items():
        operation_key = _required_text(operation_id, "operation_id")
        if not isinstance(operation, dict) or set(operation) != {
            "input_digest",
            "product_session_id",
            "session_memories",
        }:
            raise ConfigurationError("EverOS completed operation has invalid shape")
        normalized_operations[operation_key] = {
            "input_digest": _required_text(
                operation.get("input_digest"), "operation.input_digest"
            ),
            "product_session_id": _required_text(
                operation.get("product_session_id"),
                "operation.product_session_id",
            ),
            "session_memories": _required_text_list(
                operation.get("session_memories"),
                "operation.session_memories",
                allow_empty=True,
            ),
        }
    normalized_sessions: dict[str, dict[str, Any]] = {}
    for key, session in sessions.items():
        session_key = _required_text(key, "session key")
        if not isinstance(session, dict) or set(session) != {
            "derived_timestamp_count",
            "owner_ids",
            "product_session_id",
            "source_rows",
            "source_session_id",
            "synthetic_owner_anchor_count",
        }:
            raise ConfigurationError("EverOS sidecar session has invalid shape")
        raw_source_rows = session.get("source_rows")
        if not isinstance(raw_source_rows, list):
            raise ConfigurationError("EverOS sidecar source_rows must be object list")
        source_rows = [
            _validate_source_row(row, index=index)
            for index, row in enumerate(raw_source_rows)
        ]
        source_session_id = session.get("source_session_id")
        if source_session_id is not None and not isinstance(source_session_id, str):
            raise ConfigurationError(
                "EverOS sidecar source_session_id must be text or null"
            )
        session_owners = _required_text_list(
            session.get("owner_ids"), "session.owner_ids", allow_empty=False
        )
        if len(session_owners) != len(set(session_owners)):
            raise ConfigurationError(
                "EverOS sidecar session.owner_ids contain duplicates"
            )
        derived_timestamp_count = _required_non_negative_int(
            session.get("derived_timestamp_count"),
            "session.derived_timestamp_count",
        )
        if derived_timestamp_count != sum(
            row["timestamp_kind"] != "source-exact" for row in source_rows
        ):
            raise ConfigurationError(
                "EverOS sidecar derived timestamp count is inconsistent"
            )
        synthetic_owner_anchor_count = _required_non_negative_int(
            session.get("synthetic_owner_anchor_count"),
            "session.synthetic_owner_anchor_count",
        )
        if synthetic_owner_anchor_count != sum(
            row["synthetic_anchor"] for row in source_rows
        ):
            raise ConfigurationError(
                "EverOS sidecar synthetic owner anchor count is inconsistent"
            )
        normalized_sessions[session_key] = {
            "derived_timestamp_count": derived_timestamp_count,
            "owner_ids": session_owners,
            "product_session_id": _required_text(
                session.get("product_session_id"),
                "session.product_session_id",
            ),
            "source_rows": source_rows,
            "source_session_id": source_session_id,
            "synthetic_owner_anchor_count": synthetic_owner_anchor_count,
        }
    return {
        "adapter_version": EVEROS_ADAPTER_VERSION,
        "completed_operations": normalized_operations,
        "isolation_hash": _namespace_id(isolation_key),
        "owner_ids": owners,
        "schema_version": EVEROS_STATE_SCHEMA_VERSION,
        "sessions": normalized_sessions,
    }


def _validate_source_row(value: Any, *, index: int) -> dict[str, Any]:
    """校验一条只用于审计、绝不进入算法的 source lineage/time row。"""

    expected = {
        "product_timestamp_ms",
        "source_timestamp",
        "synthetic_anchor",
        "timestamp_kind",
        "turn_id",
    }
    if not isinstance(value, dict) or set(value) != expected:
        raise ConfigurationError(
            f"EverOS sidecar source_rows[{index}] has invalid shape"
        )
    turn_id = value.get("turn_id")
    source_timestamp = value.get("source_timestamp")
    synthetic_anchor = value.get("synthetic_anchor")
    timestamp_kind = value.get("timestamp_kind")
    if turn_id is not None and (
        not isinstance(turn_id, str) or not turn_id.strip()
    ):
        raise ConfigurationError(
            f"EverOS sidecar source_rows[{index}].turn_id is invalid"
        )
    if source_timestamp is not None and (
        not isinstance(source_timestamp, str) or not source_timestamp.strip()
    ):
        raise ConfigurationError(
            f"EverOS sidecar source_rows[{index}].source_timestamp is invalid"
        )
    if type(synthetic_anchor) is not bool:
        raise ConfigurationError(
            f"EverOS sidecar source_rows[{index}].synthetic_anchor must be boolean"
        )
    allowed_kinds = {
        "source-exact",
        "locomo-official-30s-order",
        "structural-owner-anchor",
    }
    if timestamp_kind not in allowed_kinds:
        raise ConfigurationError(
            f"EverOS sidecar source_rows[{index}].timestamp_kind is invalid"
        )
    if synthetic_anchor:
        if (
            timestamp_kind != "structural-owner-anchor"
            or turn_id is not None
            or source_timestamp is not None
        ):
            raise ConfigurationError(
                "EverOS structural owner anchor carries source identity"
            )
    else:
        if turn_id is None or timestamp_kind == "structural-owner-anchor":
            raise ConfigurationError("EverOS source row lost its public turn identity")
        if source_timestamp is None:
            raise ConfigurationError(
                "EverOS source-derived row is missing its source timestamp"
            )
    return {
        "product_timestamp_ms": _required_positive_int(
            value.get("product_timestamp_ms"),
            f"source_rows[{index}].product_timestamp_ms",
        ),
        "source_timestamp": source_timestamp,
        "synthetic_anchor": synthetic_anchor,
        "timestamp_kind": timestamp_kind,
        "turn_id": turn_id,
    }


def _sidecar_after_operation(
    sidecar: dict[str, Any],
    *,
    isolation_key: str,
    source_session_id: str | None,
    product_session_id: str,
    operation_id: str,
    input_digest: str,
    owner_ids: list[str],
    source_audit: dict[str, Any],
    session_memories: list[str],
) -> dict[str, Any]:
    """生成完成 operation 后的新 sidecar，保持 owner 首见顺序。"""

    normalized = _validate_sidecar(sidecar, isolation_key=isolation_key)
    merged_owners = list(normalized["owner_ids"])
    for owner in owner_ids:
        if owner not in merged_owners:
            merged_owners.append(owner)
    return {
        **normalized,
        "owner_ids": merged_owners,
        "completed_operations": {
            **normalized["completed_operations"],
            operation_id: {
                "input_digest": input_digest,
                "product_session_id": product_session_id,
                "session_memories": list(session_memories),
            },
        },
        "sessions": {
            **normalized["sessions"],
            _sidecar_session_key(source_session_id): {
                "derived_timestamp_count": _required_non_negative_int(
                    source_audit.get("derived_timestamp_count"),
                    "derived_timestamp_count",
                ),
                "owner_ids": list(owner_ids),
                "product_session_id": product_session_id,
                "source_rows": list(source_audit.get("source_rows") or []),
                "source_session_id": source_session_id,
                "synthetic_owner_anchor_count": _required_non_negative_int(
                    source_audit.get("synthetic_owner_anchor_count"),
                    "synthetic_owner_anchor_count",
                ),
            },
        },
    }


def _sidecar_session_key(session_id: str | None) -> str:
    """把可空 source session id 转成无碰撞 sidecar key。"""

    payload = "<none>" if session_id is None else f"text:{session_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _atomic_write_json(path: Path, payload: Any) -> None:
    """同目录 fsync 后原子替换 JSON。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(
                payload,
                stream,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    """同目录 fsync 后原子写产品配置模板。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _required_text(value: Any, label: str) -> str:
    """读取非空字符串。"""

    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"EverOS {label} must be non-blank text")
    return value


def _required_text_list(
    value: Any,
    label: str,
    *,
    allow_empty: bool,
) -> list[str]:
    """读取元素非空的文本列表，可选择是否允许空列表。"""

    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ConfigurationError(f"EverOS {label} must be a text list")
    if not allow_empty and not value:
        raise ConfigurationError(f"EverOS {label} must not be empty")
    return list(value)


def _required_object_list(value: Any, label: str) -> list[dict[str, Any]]:
    """读取对象列表。"""

    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ConfigurationError(f"EverOS {label} must be an object list")
    return list(value)


def _required_non_negative_int(value: Any, label: str) -> int:
    """读取非负整数，拒绝 bool。"""

    if type(value) is not int or value < 0:
        raise ConfigurationError(f"EverOS {label} must be a non-negative integer")
    return value


def _required_positive_int(value: Any, label: str) -> int:
    """读取正整数，拒绝 bool。"""

    if type(value) is not int or value < 1:
        raise ConfigurationError(f"EverOS {label} must be a positive integer")
    return value


def _required_bool(value: Any, label: str) -> bool:
    """读取严格布尔。"""

    if type(value) is not bool:
        raise ConfigurationError(f"EverOS {label} must be boolean")
    return value


def _required_finite_number(value: Any, label: str) -> float:
    """读取有限数值。"""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigurationError(f"EverOS {label} must be numeric")
    resolved = float(value)
    if not math.isfinite(resolved):
        raise ConfigurationError(f"EverOS {label} must be finite")
    return resolved


def _required_non_negative_number(value: Any, label: str) -> float:
    """读取非负有限数值。"""

    resolved = _required_finite_number(value, label)
    if resolved < 0:
        raise ConfigurationError(f"EverOS {label} must be non-negative")
    return resolved


def build_everos_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored source lock、runtime lock、patch 与 wrapper 的组合身份。"""

    settings = path_settings or load_path_settings()
    everos_root = settings.resolve_third_party_method_path(EVEROS_METHOD_DIRECTORY)
    source_files = [everos_root / relative for relative in EVEROS_SOURCE_FILES]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        raise ConfigurationError(
            "EverOS source files missing: " + ", ".join(str(path) for path in missing)
        )
    source_hash, relative_paths = _hash_relative_files(everos_root, source_files)
    wrapper_paths = [
        settings.project_root / EVEROS_WRAPPER_LOGICAL_PATH,
        settings.project_root / EVEROS_WORKER_LOGICAL_PATH,
        settings.project_root / EVEROS_BOOTSTRAP_LOGICAL_PATH,
        settings.project_root / EVEROS_PATCH_LOGICAL_PATH,
    ]
    missing_wrappers = [path for path in wrapper_paths if not path.is_file()]
    if missing_wrappers:
        raise ConfigurationError(
            "EverOS wrapper files missing: "
            + ", ".join(str(path) for path in missing_wrappers)
        )
    wrapper_hashes = {
        path.relative_to(settings.project_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in wrapper_paths
    }
    identity = {
        "upstream_url": EVEROS_UPSTREAM_URL,
        "commit": EVEROS_COMMIT,
        "package_version": EVEROS_PACKAGE_VERSION,
        "implementation_identity": EVEROS_IMPLEMENTATION_IDENTITY,
        "product_surface": EVEROS_PRODUCT_SURFACE,
        "source_mode": EVEROS_SOURCE_MODE,
        "vendored_source_sha256": source_hash,
        "runtime_lock_sha256": hashlib.sha256(
            (everos_root / "uv.lock").read_bytes()
        ).hexdigest(),
        "wrapper_hashes": wrapper_hashes,
    }
    return {
        "source_sha256": hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        **identity,
        "file_count": len(relative_paths),
        "files": relative_paths,
    }


def _hash_relative_files(root: Path, paths: list[Path]) -> tuple[str, list[str]]:
    """按相对路径与内容 bytes 计算 selected-source hash。"""

    digest = hashlib.sha256()
    relatives: list[str] = []
    for path in paths:
        relative = path.relative_to(root).as_posix()
        relatives.append(relative)
        name = relative.encode("utf-8")
        content = path.read_bytes()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest(), relatives


__all__ = [
    "EVEROS_ADAPTER_VERSION",
    "EVEROS_EMBEDDING_MODEL_ID",
    "EVEROS_EMPTY_MEMORY_SENTINEL",
    "EVEROS_IMPLEMENTATION_IDENTITY",
    "EVEROS_LLM_MODEL_ID",
    "EVEROS_PRODUCT_SURFACE",
    "EVEROS_RERANKER_MODEL_ID",
    "EverOS",
    "EverOSConfig",
    "EverOSRuntime",
    "build_everos_source_identity",
    "clean_everos_conversation_state",
    "validate_everos_variant",
]
