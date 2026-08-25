"""Letta 0.16.8 + official ai-memory-sdk sleeptime-memory 的 provider v3 adapter。

主框架不启动 Letta HTTP host，也不把 raw turn 直接写入 archival vector store。
adapter 管理一个独立 PostgreSQL 容器和 Python 3.12 worker；worker 内直接调用
``SyncServer``、``AgentLoop`` 与 core-block manager，复现 official SDK 的
message wrapper、逐 subject sleeptime agent、terminal wait 与 core-block readout。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import subprocess
from time import monotonic, perf_counter_ns, sleep
from typing import Any, Protocol
import uuid

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
    SessionBatch,
    SessionMemoryReport,
    SessionRef,
)
from memory_benchmark.methods.image_text import turn_text_with_images
from memory_benchmark.methods.worker_transport import (
    JsonLinesWorkerTransport,
    WORKER_TRANSPORT_LOGICAL_PATH,
    WorkerCommandError,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    EfficiencyStage,
    MeasurementSource,
)
from memory_benchmark.storage import atomic_write_json


LETTA_ADAPTER_VERSION = "letta-sleeptime-product-v3"
LETTA_METHOD_DIRECTORY = "letta"
LETTA_UPSTREAM_URL = "https://github.com/letta-ai/letta.git"
LETTA_RELEASE_TAG = "0.16.8"
LETTA_RELEASE_COMMIT = "1131535716e8a31c9a437f8695e25ac98f203a24"
LETTA_COMMIT = "b76da9092518cbaa2d09042e52fdcbde69243e18"
LETTA_SDK_URL = "https://github.com/letta-ai/ai-memory-sdk.git"
LETTA_SDK_RELEASE_TAG = "v0.2.0"
LETTA_SDK_COMMIT = "4494e00410469082bf298b8b03b7c9f93e244f14"
LETTA_IMPLEMENTATION_IDENTITY = "sleeptime-core-block-product"
LETTA_SOURCE_MODE = "vendored-letta-plus-official-sdk-contract-plus-wrapper"
LETTA_LLM_MODEL_ID = "letta-build-llm"
LETTA_BUILD_LLM_RESPONSE_CONTRACT = (
    "provider-aware-v2:"
    "opencodego=chat_completions+model_aware_reasoning;"
    "primary=chat_completions+provider_default"
)
LETTA_EMPTY_MEMORY_SENTINEL = "(No Letta core memory available)"
LETTA_WRAPPER_LOGICAL_PATH = "src/memory_benchmark/methods/letta_adapter.py"
LETTA_WORKER_LOGICAL_PATH = "src/memory_benchmark/methods/letta_worker.py"
LETTA_BOOTSTRAP_LOGICAL_PATH = "scripts/bootstrap_letta_runtime.sh"
LETTA_SIDECAR_SCHEMA_VERSION = "v2"
LETTA_NAMESPACE_ALGORITHM = "sha256(storage_root_relative|isolation_key)[:32]"
LETTA_POSTGRES_USER = "letta"
LETTA_POSTGRES_DATABASE = "letta"
_ALLOWED_ROLES = frozenset({"user", "assistant"})
_SECRET_ENV_NAMES = frozenset(
    {
        "OPENAI_API_KEY",
        "OPENCODEGO_API_KEY",
        "ANTHROPIC_API_KEY",
        "LETTA_API_KEY",
    }
)
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
LETTA_SOURCE_FILES = (
    "pyproject.toml",
    "uv.lock",
    "letta/agents/agent_loop.py",
    "letta/agents/letta_agent_v3.py",
    "letta/constants.py",
    "letta/functions/function_sets/base.py",
    "letta/llm_api/openai_client.py",
    "letta/schemas/agent.py",
    "letta/schemas/block.py",
    "letta/schemas/letta_response.py",
    "letta/schemas/letta_stop_reason.py",
    "letta/schemas/llm_config.py",
    "letta/schemas/message.py",
    "letta/server/db.py",
    "letta/server/server.py",
    "letta/services/agent_manager.py",
    "letta/services/archive_manager.py",
    "letta/services/block_manager.py",
    "letta/services/passage_manager.py",
    "letta/services/tool_manager.py",
)


@dataclass(frozen=True)
class LettaConfig:
    """Letta sleeptime-memory 主 profile 的强类型配置。"""

    llm_model: str
    context_window: int
    max_tokens: int
    temperature: float
    max_steps: int
    max_messages_per_batch: int
    human_block_limit: int
    summary_block_limit: int
    postgres_image: str
    postgres_startup_timeout_seconds: float
    worker_request_timeout_seconds: float
    max_workers: int
    profile_name: str = "smoke"

    def __post_init__(self) -> None:
        """拒绝偏离 official product contract 的配置。"""

        for field_name in ("llm_model", "postgres_image"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ConfigurationError(f"Letta {field_name} is required")
        for field_name in (
            "context_window",
            "max_tokens",
            "max_steps",
            "max_messages_per_batch",
            "human_block_limit",
            "summary_block_limit",
            "max_workers",
        ):
            value = getattr(self, field_name)
            if type(value) is not int or value < 1:
                raise ConfigurationError(f"Letta {field_name} must be a positive integer")
        if self.max_messages_per_batch > 10:
            raise ConfigurationError(
                "Letta official SDK recommends 5-10 messages per build call; "
                "max_messages_per_batch must not exceed 10"
            )
        if self.human_block_limit != 10_000 or self.summary_block_limit != 1_000:
            raise ConfigurationError(
                "Letta product profile locks human=10000 and summary=1000 chars"
            )
        if isinstance(self.temperature, bool) or not isinstance(
            self.temperature,
            (int, float),
        ):
            raise ConfigurationError("Letta temperature must be numeric")
        if self.postgres_startup_timeout_seconds <= 0:
            raise ConfigurationError(
                "Letta postgres_startup_timeout_seconds must be positive"
            )
        if self.worker_request_timeout_seconds <= 0:
            raise ConfigurationError(
                "Letta worker_request_timeout_seconds must be positive"
            )

    def to_manifest(self) -> dict[str, Any]:
        """返回无 secret、无绝对路径的公开配置身份。"""

        return {
            **asdict(self),
            "adapter_version": LETTA_ADAPTER_VERSION,
            "implementation_identity": LETTA_IMPLEMENTATION_IDENTITY,
            "product_contract": "ai-memory-sdk-v0.2.0",
            "agent_type": "sleeptime_agent",
            "consume_granularity": "session",
            "message_wrapper": "official-ai-memory-sdk",
            "build_llm_response_contract": LETTA_BUILD_LLM_RESPONSE_CONTRACT,
            "skip_vector_storage": True,
            "embedding_provider": None,
            "readout": "all-attached-core-blocks-query-independent",
            "namespace_algorithm": LETTA_NAMESPACE_ALGORITHM,
        }


class LettaRuntimeProtocol(Protocol):
    """adapter 依赖的最窄 runtime 协议，供生产实现与 hermetic fake 共用。"""

    def ensure_started(self) -> None:
        """确保本地数据库和 worker 已就绪。"""

    def ensure_subject(self, subject_id: str) -> dict[str, Any]:
        """创建或验证一个 subject。"""

    def ingest(self, *, subject_id: str, operation_id: str, content: str) -> dict[str, Any]:
        """执行一次 official wrapper build。"""

    def read_blocks(self, *, subject_id: str, agent_id: str | None) -> dict[str, Any]:
        """读取全部 attached core blocks。"""

    def delete_subject(
        self,
        *,
        subject_id: str,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """幂等删除一个 subject namespace。"""

    def close(self) -> None:
        """关闭 worker 与本 runtime 拥有的容器。"""


RuntimeFactory = Callable[..., LettaRuntimeProtocol]


class LettaRuntime:
    """一个 run/worker storage root 独占的 PostgreSQL + worker runtime。"""

    def __init__(
        self,
        *,
        config: LettaConfig,
        openai_settings: OpenAISettings,
        path_settings: PathSettings,
        storage_root: Path,
        diagnostic_log_path: Path | None = None,
    ) -> None:
        """保存依赖；真正启动推迟到 ``ensure_started``。"""

        self.config = config
        self.openai_settings = openai_settings
        self.path_settings = path_settings
        self.storage_root = storage_root
        self._identity = _runtime_identity(
            config=config,
            openai_settings=openai_settings,
            path_settings=path_settings,
            storage_root=storage_root,
        )
        short = self._identity[:20]
        self._container_name = f"mb-letta-{short}-pg"
        self._volume_name = f"mb-letta-{short}-pgdata"
        self._label_value = self._identity
        self._transport = JsonLinesWorkerTransport(
            product_label="Letta",
            request_timeout_seconds=config.worker_request_timeout_seconds,
            timeout_detail=None,
            stderr_tail_char_limit=2000,
            terminate_on_timeout=False,
            terminate_on_protocol_error=False,
            forget_process_on_terminate=False,
            diagnostic_log_path=diagnostic_log_path,
        )
        self._started = False
        self._closed = False
        self._close_error: BaseException | None = None

    @property
    def runtime_tag(self) -> str:
        """返回不含机器绝对路径的 agent runtime tag。"""

        return f"mb-runtime:{self._identity[:32]}"

    def ensure_started(self) -> None:
        """启动受控 Postgres、执行 migration 并握手 worker。"""

        if self._closed:
            raise ConfigurationError("Letta runtime is already closed")
        if self._close_error is not None:
            raise ConfigurationError(
                "Letta runtime is permanently unusable after cleanup failure"
            ) from self._close_error
        if self._started:
            return
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self._require_bootstrapped_runtime()
        self._ensure_owned_volume()
        self._ensure_owned_container()
        try:
            port = self._wait_for_postgres()
            self._ensure_pgvector_extension()
            self._run_migration(port)
            self._start_worker(port)
            self._request(
                "initialize",
                {
                    "config": {
                        "llm_model": self.config.llm_model,
                        "model_endpoint": self.openai_settings.base_url,
                        "provider": self.openai_settings.provider,
                        "context_window": self.config.context_window,
                        "max_tokens": self.config.max_tokens,
                        "temperature": self.config.temperature,
                        "max_steps": self.config.max_steps,
                        "timeout_seconds": self.openai_settings.timeout_seconds,
                        "max_retries": self.openai_settings.max_retries,
                        "human_block_limit": self.config.human_block_limit,
                        "summary_block_limit": self.config.summary_block_limit,
                        "runtime_tag": self.runtime_tag,
                    }
                },
            )
        except BaseException:
            self._terminate_worker()
            self._remove_owned_container()
            raise
        self._started = True

    def _require_bootstrapped_runtime(self) -> None:
        """校验独立 venv 与三个 PostgreSQL 补充依赖已准备。"""

        python = self._worker_python()
        if not python.is_file():
            raise ConfigurationError(
                "Letta isolated runtime is missing. Run: "
                f"{self.path_settings.project_root / LETTA_BOOTSTRAP_LOGICAL_PATH}"
            )
        result = subprocess.run(
            [
                str(python),
                "-c",
                "import asyncpg, pg8000, pgvector, letta",
            ],
            cwd=self._letta_root(),
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ConfigurationError(
                "Letta isolated runtime dependencies are incomplete. Run: "
                f"{self.path_settings.project_root / LETTA_BOOTSTRAP_LOGICAL_PATH}"
            )

    def _letta_root(self) -> Path:
        """返回 source-locked vendored Letta 根目录。"""

        return self.path_settings.resolve_third_party_method_path(
            LETTA_METHOD_DIRECTORY
        )

    def _worker_python(self) -> Path:
        """返回 vendored lock 对应的独立 Python。"""

        return self._letta_root() / ".venv" / "bin" / "python"

    def _docker(self, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
        """运行 docker 命令并把失败转为不泄露 secret 的配置错误。"""

        if shutil.which("docker") is None:
            raise ConfigurationError("Letta product runtime requires Docker")
        result = subprocess.run(
            ["docker", *args],
            text=True,
            capture_output=True,
            check=False,
        )
        if check and result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ConfigurationError(
                f"Letta Docker command failed ({' '.join(args[:2])}): {detail}"
            )
        return result

    def _inspect(self, object_name: str, *, volume: bool = False) -> dict[str, Any] | None:
        """读取容器或 volume inspect；不存在返回 None，其他失败照常报错。"""

        args = ["volume", "inspect", object_name] if volume else ["inspect", object_name]
        result = self._docker(args, check=False)
        if result.returncode != 0:
            missing_text = (result.stderr or "").lower()
            if "no such" in missing_text:
                return None
            raise ConfigurationError(
                f"Letta cannot inspect owned Docker object {object_name}: "
                f"{(result.stderr or result.stdout).strip()}"
            )
        payload = json.loads(result.stdout)
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise ConfigurationError(f"Invalid Docker inspect payload for {object_name}")
        return payload[0]

    def _ensure_owned_volume(self) -> None:
        """创建或验证仅属于当前 runtime identity 的 Postgres volume。"""

        inspected = self._inspect(self._volume_name, volume=True)
        if inspected is None:
            self._docker(
                [
                    "volume",
                    "create",
                    "--label",
                    "memory-benchmark.owner=letta",
                    "--label",
                    f"memory-benchmark.runtime={self._label_value}",
                    self._volume_name,
                ]
            )
            return
        labels = inspected.get("Labels") or {}
        if labels.get("memory-benchmark.owner") != "letta" or labels.get(
            "memory-benchmark.runtime"
        ) != self._label_value:
            raise ConfigurationError(
                f"Docker volume name is occupied by an unowned object: {self._volume_name}"
            )

    def _ensure_owned_container(self) -> None:
        """创建、启动或验证当前 runtime 独占的 Postgres 容器。"""

        inspected = self._inspect(self._container_name)
        if inspected is None:
            self._docker(
                [
                    "run",
                    "-d",
                    "--name",
                    self._container_name,
                    "--label",
                    "memory-benchmark.owner=letta",
                    "--label",
                    f"memory-benchmark.runtime={self._label_value}",
                    "-e",
                    f"POSTGRES_USER={LETTA_POSTGRES_USER}",
                    "-e",
                    f"POSTGRES_DB={LETTA_POSTGRES_DATABASE}",
                    "-e",
                    "POSTGRES_HOST_AUTH_METHOD=trust",
                    "-p",
                    "127.0.0.1::5432",
                    "-v",
                    f"{self._volume_name}:/var/lib/postgresql/data",
                    self.config.postgres_image,
                ]
            )
            return
        labels = (inspected.get("Config") or {}).get("Labels") or {}
        if labels.get("memory-benchmark.owner") != "letta" or labels.get(
            "memory-benchmark.runtime"
        ) != self._label_value:
            raise ConfigurationError(
                f"Docker container name is occupied by an unowned object: {self._container_name}"
            )
        if not (inspected.get("State") or {}).get("Running"):
            self._docker(["start", self._container_name])

    def _wait_for_postgres(self) -> int:
        """等待最终 PostgreSQL TCP server 可执行 SQL，再返回映射端口。

        官方 Postgres image 初始化时会短暂启动一个只监听 Unix socket 的临时
        server；单独依赖 ``pg_isready`` 会把这个阶段误判为 product-ready，随后
        ``psql`` 恰逢临时 server 关闭便产生竞态。这里改用容器内 TCP + ``SELECT
        1``，只接受最终 server 的真实查询成功。
        """

        deadline = monotonic() + self.config.postgres_startup_timeout_seconds
        while monotonic() < deadline:
            ready = self._docker(
                [
                    "exec",
                    self._container_name,
                    "psql",
                    "-h",
                    "127.0.0.1",
                    "-Atqc",
                    "SELECT 1",
                    "-U",
                    LETTA_POSTGRES_USER,
                    "-d",
                    LETTA_POSTGRES_DATABASE,
                ],
                check=False,
            )
            if ready.returncode == 0:
                break
            sleep(0.25)
        else:
            raise ConfigurationError("Letta PostgreSQL did not become ready in time")
        port_result = self._docker(["port", self._container_name, "5432/tcp"])
        line = port_result.stdout.strip().splitlines()[0]
        try:
            port = int(line.rsplit(":", 1)[1])
        except (IndexError, ValueError) as exc:
            raise ConfigurationError(
                f"Cannot parse Letta PostgreSQL port mapping: {line!r}"
            ) from exc
        return port

    def _run_migration(self, port: int) -> None:
        """用 pg8000 同步 URI执行 vendored Alembic migration。"""

        alembic = self._letta_root() / ".venv" / "bin" / "alembic"
        if not alembic.is_file():
            raise ConfigurationError("Letta runtime is missing the alembic executable")
        env = self._worker_environment(port, include_build_key=False)
        env["LETTA_PG_URI"] = (
            f"postgresql://{LETTA_POSTGRES_USER}@127.0.0.1:{port}/"
            f"{LETTA_POSTGRES_DATABASE}"
        )
        result = subprocess.run(
            [str(alembic), "upgrade", "head"],
            cwd=self._letta_root(),
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise ConfigurationError(
                "Letta schema migration failed: "
                f"{(result.stderr or result.stdout).strip()}"
            )

    def _ensure_pgvector_extension(self) -> None:
        """在 Alembic 建 VECTOR 列前幂等启用镜像内置的 pgvector 扩展。"""

        self._docker(
            [
                "exec",
                self._container_name,
                "psql",
                "-v",
                "ON_ERROR_STOP=1",
                "-U",
                LETTA_POSTGRES_USER,
                "-d",
                LETTA_POSTGRES_DATABASE,
                "-c",
                "CREATE EXTENSION IF NOT EXISTS vector",
            ]
        )

    def _worker_environment(self, port: int, *, include_build_key: bool) -> dict[str, str]:
        """构造 import 前生效的隔离环境；API key 只使用私有 env 名。"""

        env = {
            name: os.environ[name]
            for name in _WORKER_PASSTHROUGH_ENV_NAMES
            if name in os.environ
        }
        if set(env).intersection(_SECRET_ENV_NAMES):
            raise ConfigurationError("Letta worker environment allowlist contains a secret")
        runtime_dir = self.storage_root / "runtime"
        home_dir = runtime_dir / "home"
        letta_dir = runtime_dir / "letta"
        home_dir.mkdir(parents=True, exist_ok=True)
        letta_dir.mkdir(parents=True, exist_ok=True)
        env.update(
            {
                "HOME": str(home_dir),
                "LETTA_DIR": str(letta_dir),
                "MEMGPT_CONFIG_PATH": str(letta_dir / "config"),
                "LETTA_PG_URI": (
                    f"postgresql://{LETTA_POSTGRES_USER}@127.0.0.1:{port}/"
                    f"{LETTA_POSTGRES_DATABASE}?sslmode=disable"
                ),
                "LETTA_DISABLE_SQLALCHEMY_POOLING": "true",
                "LETTA_ENABLE_BATCH_JOB_POLLING": "false",
            }
        )
        if include_build_key:
            env["MEMORY_BENCHMARK_LETTA_BUILD_API_KEY"] = self.openai_settings.api_key
        return env

    def _start_worker(self, port: int) -> None:
        """启动 stdio worker 并持续排空 stderr，防止第三方日志堵塞 pipe。"""

        worker_path = self.path_settings.project_root / LETTA_WORKER_LOGICAL_PATH
        self._transport.start(
            argv=[str(self._worker_python()), str(worker_path)],
            cwd=self._letta_root(),
            env=self._worker_environment(port, include_build_key=True),
            stderr_thread_name=f"{self._container_name}-stderr",
            stderr_redactor=self._worker_stderr_redactor(),
        )

    def _worker_stderr_redactor(self) -> Callable[[str], str]:
        """冻结 build endpoint/secret 并返回逐行脱敏器。"""

        api_key = self.openai_settings.api_key
        base_url = self.openai_settings.base_url

        def redact(line: str) -> str:
            """脱敏 Letta worker 可见的 endpoint 与 credential。"""

            redacted = line.replace(
                api_key,
                "<redacted-api-key>",
            )
            if base_url:
                redacted = redacted.replace(
                    base_url,
                    "<redacted-api-base-url>",
                )
            return redacted

        return redact

    def _request(self, command: str, payload: dict[str, Any]) -> dict[str, Any]:
        """经共享 transport 发送请求；Letta payload 保持本地显式。"""

        return self._transport.request(command, payload)

    def _worker_failure_text(self, state: str) -> str:
        """构造不含 secret 的 worker 失败摘要。"""

        return self._transport.failure_text(state)

    def ensure_subject(self, subject_id: str) -> dict[str, Any]:
        """经 worker 创建或验证 subject。"""

        self.ensure_started()
        return self._request("ensure_subject", {"subject_id": subject_id})

    def ingest(self, *, subject_id: str, operation_id: str, content: str) -> dict[str, Any]:
        """经 worker 执行一次 official message wrapper build。"""

        self.ensure_started()
        return self._request(
            "ingest",
            {
                "subject_id": subject_id,
                "operation_id": operation_id,
                "content": content,
            },
        )

    def read_blocks(self, *, subject_id: str, agent_id: str | None) -> dict[str, Any]:
        """经 worker 读取 attached core blocks。"""

        self.ensure_started()
        return self._request(
            "read_blocks",
            {"subject_id": subject_id, "agent_id": agent_id},
        )

    def delete_subject(
        self,
        *,
        subject_id: str,
        state: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """经 worker 执行 namespace-scoped clean retry。"""

        self.ensure_started()
        return self._request(
            "delete_subject",
            {"subject_id": subject_id, "state": state},
        )

    def close(self) -> None:
        """关闭 worker 和 owned container，保留 volume 供 resume。"""

        if self._closed:
            return
        if self._close_error is not None:
            raise ConfigurationError(
                "Letta runtime cleanup previously failed and is permanently fail-closed"
            ) from self._close_error
        try:
            if self._transport.is_running:
                self._request("shutdown", {})
                self._transport.wait(timeout=10)
            self._terminate_worker()
        except BaseException as exc:
            self._close_error = exc
            self._terminate_worker()
            self._remove_owned_container()
            raise
        self._remove_owned_container()
        self._closed = True

    def _terminate_worker(self) -> None:
        """尽力终止 worker，不把该 helper 当作业务成功证明。"""

        self._transport.terminate()

    def _remove_owned_container(self) -> None:
        """只删除带当前 identity label 的容器，绝不触碰 volume。"""

        inspected = self._inspect(self._container_name)
        if inspected is None:
            return
        labels = (inspected.get("Config") or {}).get("Labels") or {}
        if labels.get("memory-benchmark.owner") != "letta" or labels.get(
            "memory-benchmark.runtime"
        ) != self._label_value:
            raise ConfigurationError(
                f"Refusing to remove unowned Docker container: {self._container_name}"
            )
        self._docker(["rm", "-f", self._container_name])


class Letta(MemoryProvider):
    """official sleeptime-memory product surface 的 session 粒度 provider。"""

    consume_granularity = "session"
    session_memory_report = False
    provenance_granularity = "none"

    def __init__(
        self,
        *,
        config: LettaConfig,
        path_settings: PathSettings,
        storage_root: Path,
        openai_settings: OpenAISettings,
        efficiency_collector: EfficiencyCollector | None = None,
        session_memory_report: bool = False,
        benchmark_name: str | None = None,
        diagnostic_log_path: Path | None = None,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        """保存构造依赖，runtime 仍延迟到 prepare/首次操作。"""

        if config.llm_model != openai_settings.model:
            raise ConfigurationError(
                "Letta config llm_model must match the selected API runtime model"
            )
        self.config = config
        self.path_settings = path_settings
        self.storage_root = storage_root
        self.openai_settings = openai_settings
        self.efficiency_collector = efficiency_collector
        if not isinstance(session_memory_report, bool):
            raise ConfigurationError("Letta session_memory_report must be bool")
        self.session_memory_report = session_memory_report
        self.benchmark_name = benchmark_name
        self.diagnostic_log_path = diagnostic_log_path
        self._runtime_factory = runtime_factory or LettaRuntime
        self._runtime: LettaRuntimeProtocol | None = None
        self._session_report_memories: dict[tuple[str, str | None], list[str]] = {}
        self._cleaned = False

    def prepare(self, run_context: Any) -> None:
        """在 ingest 前启动本地产品 runtime；此阶段不调用外部 LLM。"""

        del run_context
        self._require_runtime().ensure_started()

    def ingest(self, unit: IngestUnit) -> IngestResult | None:
        """按 session 顺序，把至多 10 条原始 message 包成一次 SDK 调用。"""

        if not isinstance(unit, SessionBatch):
            raise ConfigurationError("Letta provider only accepts SessionBatch")
        if not unit.events:
            if self.session_memory_report:
                self._session_report_memories[
                    (unit.isolation_key, unit.session_id)
                ] = []
            return IngestResult(
                unit_ref=unit.ref,
                metadata={"method": "letta", "source_message_count": 0, "build_call_count": 0},
            )
        subject_id = self._subject_id(unit.isolation_key)
        runtime = self._require_runtime()
        state = runtime.ensure_subject(subject_id)
        self._persist_subject_state(unit.isolation_key, subject_id, state)
        messages = self._build_messages(unit)
        report_record = None
        if self.session_memory_report:
            report_record = self._prepare_session_report(
                unit=unit,
                subject_id=subject_id,
                messages=messages,
                runtime=runtime,
            )
        batches = _message_chunks(messages, self.config.max_messages_per_batch)
        step_count = 0
        llm_call_count = 0
        reused_build_call_count = 0
        for batch_index, batch in enumerate(batches):
            wrapper = _official_message_wrapper(batch)
            operation_id = str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "|".join(
                        (
                            LETTA_ADAPTER_VERSION,
                            subject_id,
                            unit.session_id or "none",
                            str(batch_index),
                            hashlib.sha256(wrapper.encode("utf-8")).hexdigest(),
                        )
                    ),
                )
            )
            if not self._begin_operation(unit.isolation_key, operation_id):
                reused_build_call_count += 1
                continue
            try:
                result = runtime.ingest(
                    subject_id=subject_id,
                    operation_id=operation_id,
                    content=wrapper,
                )
            except WorkerCommandError as exc:
                self._record_failed_worker_usage(exc.details)
                raise
            persisted_state = self._load_subject_state(
                unit.isolation_key,
                required=True,
            )
            assert persisted_state is not None
            _validate_runtime_subject_identity(
                result,
                expected_subject_id=subject_id,
                expected_state=persisted_state,
                source="ingest",
            )
            usage = result.get("usage")
            if not isinstance(usage, list):
                raise ConfigurationError("Letta worker ingest result has no usage list")
            for call in usage:
                if not isinstance(call, dict):
                    raise ConfigurationError("Letta worker usage entry must be an object")
                self._record_llm_usage(call)
            current_steps = result.get("step_count")
            if type(current_steps) is not int or current_steps < 1:
                raise ConfigurationError("Letta worker returned invalid step_count")
            step_count += current_steps
            llm_call_count += len(usage)
            self._complete_operation(unit.isolation_key, operation_id)
        if report_record is not None:
            memories = self._complete_session_report(
                unit=unit,
                subject_id=subject_id,
                runtime=runtime,
                report_record=report_record,
            )
            self._session_report_memories[
                (unit.isolation_key, unit.session_id)
            ] = memories
        return IngestResult(
            unit_ref=SessionRef(
                isolation_key=unit.isolation_key,
                session_id=unit.session_id,
            ),
            metadata={
                "method": "letta",
                "subject_id": subject_id,
                "source_message_count": len(messages),
                "build_call_count": len(batches) - reused_build_call_count,
                "reused_build_call_count": reused_build_call_count,
                "llm_call_count": llm_call_count,
                "agent_step_count": step_count,
                "message_wrapper": "official-ai-memory-sdk",
                "skip_vector_storage": True,
            },
        )

    def end_session(self, ref: SessionRef) -> SessionMemoryReport | None:
        """报告该 session 对 attached core blocks 造成的稳定 ID before/after delta。"""

        if not self.session_memory_report:
            return None
        memories = self._session_report_memories.pop(
            (ref.isolation_key, ref.session_id),
            [],
        )
        return SessionMemoryReport(
            session_ref=ref,
            memories=memories,
            metadata={
                "method": "letta",
                "memory_unit": "changed_attached_core_block",
                "changed_block_count": len(memories),
            },
        )

    def _prepare_session_report(
        self,
        *,
        unit: SessionBatch,
        subject_id: str,
        messages: list[dict[str, str]],
        runtime: LettaRuntimeProtocol,
    ) -> dict[str, Any]:
        """在任何 session build 前持久化 core-block baseline，保证 crash 后可重放。"""

        session_key = _required_session_report_key(unit.session_id)
        digest = _session_input_digest(messages)
        state = self._load_subject_state(unit.isolation_key, required=True)
        assert state is not None
        existing = state["session_reports"].get(session_key)
        if existing is not None:
            if existing["input_digest"] != digest:
                raise ConfigurationError(
                    "Letta session report key was reused with different input"
                )
            return existing
        before_blocks = self._read_core_blocks(
            runtime=runtime,
            subject_id=subject_id,
            state=state,
        )
        record = {
            "input_digest": digest,
            "before_blocks": before_blocks,
            "memories": None,
        }
        atomic_write_json(
            self._sidecar_path(unit.isolation_key),
            {
                **state,
                "session_reports": {**state["session_reports"], session_key: record},
            },
        )
        return record

    def _complete_session_report(
        self,
        *,
        unit: SessionBatch,
        subject_id: str,
        runtime: LettaRuntimeProtocol,
        report_record: dict[str, Any],
    ) -> list[str]:
        """完成或重放 session block delta，并把结果与 operation journal 一起持久化。"""

        persisted_memories = report_record.get("memories")
        if persisted_memories is not None:
            return list(persisted_memories)
        state = self._load_subject_state(unit.isolation_key, required=True)
        assert state is not None
        after_blocks = self._read_core_blocks(
            runtime=runtime,
            subject_id=subject_id,
            state=state,
        )
        memories = _changed_block_values(
            before=report_record["before_blocks"],
            after=after_blocks,
        )
        session_key = _required_session_report_key(unit.session_id)
        completed_record = {**report_record, "memories": memories}
        atomic_write_json(
            self._sidecar_path(unit.isolation_key),
            {
                **state,
                "session_reports": {
                    **state["session_reports"],
                    session_key: completed_record,
                },
            },
        )
        return memories

    @staticmethod
    def _read_core_blocks(
        *,
        runtime: LettaRuntimeProtocol,
        subject_id: str,
        state: dict[str, Any],
    ) -> list[dict[str, str | None]]:
        """读取、验明身份并规范化全部 attached core blocks。"""

        result = runtime.read_blocks(
            subject_id=subject_id,
            agent_id=state["agent_id"],
        )
        blocks = result.get("blocks")
        if not isinstance(blocks, list):
            raise ConfigurationError("Letta worker read_blocks result is malformed")
        if result.get("agent_id") != state["agent_id"]:
            raise ConfigurationError(
                "Letta worker read_blocks returned a different agent identity"
            )
        _validate_readout_block_identity(blocks, state=state)
        return _normalize_blocks(blocks)

    def _record_llm_usage(self, call: dict[str, Any]) -> None:
        """把 worker 的真实逐调用 usage 写入当前 conversation scope。"""

        input_tokens = call.get("input_tokens")
        output_tokens = call.get("output_tokens")
        if type(input_tokens) is not int or input_tokens < 0:
            raise ConfigurationError("Letta usage input_tokens must be non-negative int")
        if type(output_tokens) is not int or output_tokens < 0:
            raise ConfigurationError("Letta usage output_tokens must be non-negative int")
        if self.efficiency_collector is None:
            return
        self.efficiency_collector.record_llm_call(
            model_id=LETTA_LLM_MODEL_ID,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            token_measurement_source=MeasurementSource.API_USAGE,
        )

    def _record_failed_worker_usage(
        self,
        details: dict[str, Any] | None,
    ) -> None:
        """把失败 Letta step 前已完成的 exact usage 写入当前失败 scope。"""

        if details is None or self.efficiency_collector is None:
            return
        if set(details) != {"llm_observations"}:
            raise ConfigurationError(
                "Letta worker failure observation fields are malformed"
            )
        usage = details.get("llm_observations")
        if not isinstance(usage, list):
            raise ConfigurationError(
                "Letta worker failure llm_observations must be a list"
            )
        with self.efficiency_collector.operation_stage(
            EfficiencyStage.MEMORY_BUILD
        ):
            for call in usage:
                if not isinstance(call, dict):
                    raise ConfigurationError(
                        "Letta worker failure usage entry must be an object"
                    )
                self._record_llm_usage(call)

    def _build_messages(self, unit: SessionBatch) -> list[dict[str, str]]:
        """无损构造 official formatter 的 role/content 输入，不补 placeholder。"""

        locomo_roles = (
            self._locomo_speaker_roles(unit)
            if self.benchmark_name == "locomo"
            else None
        )
        messages: list[dict[str, str]] = []
        for event in unit.events:
            if locomo_roles is None:
                role = event.role
                if role not in _ALLOWED_ROLES:
                    raise ConfigurationError(
                        f"Letta only accepts canonical user/assistant roles: {role!r}"
                    )
            else:
                speaker = event.speaker_name or event.role
                role = locomo_roles.get(speaker)
                if role is None:
                    raise ConfigurationError(
                        f"Letta LoCoMo speaker is not declared: {speaker!r}"
                    )
            rendered = self._render_event_content(event, unit.session_time)
            if locomo_roles is not None:
                time_prefix, source_content = _split_source_time_prefix(rendered)
                rendered = (
                    f"{time_prefix}{event.speaker_name or event.role}: "
                    f"{source_content}"
                )
            if not rendered.strip():
                raise ConfigurationError(f"Letta turn has no content: {event.turn_id}")
            messages.append({"role": role, "content": rendered})
        return messages

    @staticmethod
    def _locomo_speaker_roles(unit: SessionBatch) -> dict[str, str]:
        """按公开 conversation metadata 稳定映射 speaker_a/user、speaker_b/assistant。"""

        metadata: dict[str, Any] = {}
        for event in unit.events:
            candidate = event.metadata.get("conversation_metadata")
            if isinstance(candidate, dict):
                metadata = candidate
                break
        speaker_a = metadata.get("speaker_a")
        speaker_b = metadata.get("speaker_b")
        if not isinstance(speaker_a, str) or not speaker_a.strip():
            raise ConfigurationError("Letta LoCoMo metadata is missing speaker_a")
        if not isinstance(speaker_b, str) or not speaker_b.strip():
            raise ConfigurationError("Letta LoCoMo metadata is missing speaker_b")
        if speaker_a == speaker_b:
            raise ConfigurationError("Letta LoCoMo speakers must be distinct")
        return {speaker_a: "user", speaker_b: "assistant"}

    @staticmethod
    def _render_event_content(event: Any, session_time: str | None) -> str:
        """重建共享 image caption，并按 turn→session→None 唯一渲染时间。"""

        turn_metadata = event.metadata.get("turn_metadata")
        if not isinstance(turn_metadata, dict):
            turn_metadata = {}
        original = event.metadata.get("original_content")
        content = original if isinstance(original, str) else event.content
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
        rendered = turn_text_with_images(turn)
        prefix = _effective_time_prefix(
            turn_time=turn.turn_time,
            session_time=session_time,
            source_timestamp_embedded=turn_metadata.get(
                "source_timestamp_embedded_in_content"
            ),
        )
        return f"{prefix}{rendered}"

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """忽略 query 语义，只读该 subject 演化后的全部 attached core blocks。"""

        subject_id = self._subject_id(query.isolation_key)
        state = self._load_subject_state(query.isolation_key, required=True)
        started_ns = perf_counter_ns()
        result = self._require_runtime().read_blocks(
            subject_id=subject_id,
            agent_id=state["agent_id"],
        )
        blocks = result.get("blocks")
        if not isinstance(blocks, list):
            raise ConfigurationError("Letta worker read_blocks result is malformed")
        if result.get("agent_id") != state["agent_id"]:
            raise ConfigurationError(
                "Letta worker read_blocks returned a different agent identity"
            )
        _validate_readout_block_identity(blocks, state=state)
        formatted_memory = _format_blocks(blocks)
        if self.efficiency_collector is not None:
            self.efficiency_collector.record_retrieval_result_if_question_scope(
                latency_ms=max(0.0, (perf_counter_ns() - started_ns) / 1_000_000),
                injected_memory_context_tokens=None,
            )
        return RetrievalResult(
            formatted_memory=formatted_memory or LETTA_EMPTY_MEMORY_SENTINEL,
            items=None,
            metadata={
                "method": "letta",
                "prompt_track": "unified",
                "subject_id": subject_id,
                "readout": "all-attached-core-blocks-query-independent",
                "query_consumed_by_method": False,
                "provenance_granularity": "none",
            },
            evidence=_letta_retrieval_evidence(),
        )

    def cleanup(self) -> None:
        """关闭 runtime；只有 close 成功后才提交 adapter 清理状态。"""

        if self._cleaned:
            return
        runtime = self._runtime
        if runtime is None:
            self._cleaned = True
            return
        runtime.close()
        self._runtime = None
        self._cleaned = True

    def _require_runtime(self) -> LettaRuntimeProtocol:
        """懒构造且复用当前 provider 的唯一 runtime。"""

        if self._cleaned:
            raise ConfigurationError("Letta provider is already cleaned")
        if self._runtime is None:
            runtime_kwargs: dict[str, Any] = dict(
                config=self.config,
                openai_settings=self.openai_settings,
                path_settings=self.path_settings,
                storage_root=self.storage_root,
            )
            if self.diagnostic_log_path is not None:
                runtime_kwargs["diagnostic_log_path"] = self.diagnostic_log_path
            self._runtime = self._runtime_factory(**runtime_kwargs)
        return self._runtime

    def _subject_id(self, isolation_key: str) -> str:
        """按 run storage identity + isolation key 生成确定性 opaque subject。"""

        if not isolation_key.strip():
            raise ConfigurationError("Letta isolation_key is required")
        relative = _storage_root_relative(
            storage_root=self.storage_root,
            outputs_root=self.path_settings.outputs_root,
        )
        return hashlib.sha256(f"{relative}|{isolation_key}".encode("utf-8")).hexdigest()[:32]

    def _sidecar_path(self, isolation_key: str) -> Path:
        """返回 conversation subject sidecar 的确定性路径。"""

        digest = hashlib.sha256(isolation_key.encode("utf-8")).hexdigest()
        return self.storage_root / "subjects" / f"{digest}.json"

    def _persist_subject_state(
        self,
        isolation_key: str,
        subject_id: str,
        state: dict[str, Any],
    ) -> None:
        """原子写入或验证 subject/agent/block/archive identity。"""

        _validate_runtime_subject_identity(
            state,
            expected_subject_id=subject_id,
            expected_state=None,
            source="ensure_subject",
        )

        payload = {
            "schema_version": LETTA_SIDECAR_SCHEMA_VERSION,
            "adapter_version": LETTA_ADAPTER_VERSION,
            "isolation_key": isolation_key,
            "subject_id": subject_id,
            "agent_id": state.get("agent_id"),
            "block_ids": state.get("block_ids"),
            "archive_id": state.get("archive_id"),
            "cleanup_phase": "active",
            "pending_operation_id": None,
            "completed_operation_ids": [],
            "session_reports": {},
        }
        _validate_sidecar(payload)
        path = self._sidecar_path(isolation_key)
        if path.is_file():
            existing = self._read_sidecar(path)
            stable_keys = (
                "schema_version",
                "adapter_version",
                "isolation_key",
                "subject_id",
                "agent_id",
                "block_ids",
                "archive_id",
            )
            if any(existing[key] != payload[key] for key in stable_keys):
                raise ConfigurationError(
                    "Letta subject state conflicts with persisted sidecar: "
                    f"{isolation_key}"
                )
            return
        atomic_write_json(path, payload)

    def _begin_operation(self, isolation_key: str, operation_id: str) -> bool:
        """两阶段登记一次 build；已完成返回 False，悬空状态拒绝重放。"""

        state = self._load_subject_state(isolation_key, required=True)
        assert state is not None
        if state["cleanup_phase"] != "active":
            raise ConfigurationError(
                "Letta subject is pending cleanup and cannot accept ingest"
            )
        completed = state["completed_operation_ids"]
        if operation_id in completed:
            return False
        pending = state["pending_operation_id"]
        if pending is not None:
            raise ConfigurationError(
                "Letta has an ambiguous pending build operation; run the existing "
                "failed-ingest clean retry before replay"
            )
        atomic_write_json(
            self._sidecar_path(isolation_key),
            {**state, "pending_operation_id": operation_id},
        )
        return True

    def _complete_operation(self, isolation_key: str, operation_id: str) -> None:
        """只在 terminal、usage 与 step 均验收后提交 completed operation。"""

        state = self._load_subject_state(isolation_key, required=True)
        assert state is not None
        if state["cleanup_phase"] != "active":
            raise ConfigurationError("Letta subject entered cleanup during ingest")
        if state["pending_operation_id"] != operation_id:
            raise ConfigurationError("Letta pending build operation identity mismatch")
        completed = [*state["completed_operation_ids"], operation_id]
        atomic_write_json(
            self._sidecar_path(isolation_key),
            {
                **state,
                "pending_operation_id": None,
                "completed_operation_ids": completed,
            },
        )

    def _load_subject_state(
        self,
        isolation_key: str,
        *,
        required: bool,
    ) -> dict[str, Any] | None:
        """读取严格 sidecar；retrieve 缺失时不得猜测 subject identity。"""

        path = self._sidecar_path(isolation_key)
        if not path.is_file():
            if required:
                raise ConfigurationError(
                    f"Letta subject sidecar is missing: {isolation_key}"
                )
            return None
        payload = self._read_sidecar(path)
        expected_subject = self._subject_id(isolation_key)
        if payload["isolation_key"] != isolation_key or payload["subject_id"] != expected_subject:
            raise ConfigurationError("Letta subject sidecar identity mismatch")
        return payload

    @staticmethod
    def _read_sidecar(path: Path) -> dict[str, Any]:
        """解析一个 subject sidecar 并运行完整 schema 校验。"""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigurationError(f"Invalid Letta subject sidecar: {path}") from exc
        _validate_sidecar(payload)
        return payload


def clean_letta_conversation_state(*, provider: Letta, isolation_key: str) -> None:
    """清理一个 failed-ingest conversation 的独占 subject，支持中断后重试。"""

    subject_id = provider._subject_id(isolation_key)
    state = provider._load_subject_state(isolation_key, required=False)
    path = provider._sidecar_path(isolation_key)
    if state is not None:
        pending = {**state, "cleanup_phase": "pending"}
        atomic_write_json(path, pending)
        state = pending
    result = provider._require_runtime().delete_subject(
        subject_id=subject_id,
        state=state,
    )
    if result.get("deleted") is not True:
        raise ConfigurationError("Letta worker did not confirm subject deletion")
    path.unlink(missing_ok=True)


def _runtime_identity(
    *,
    config: LettaConfig,
    openai_settings: OpenAISettings,
    path_settings: PathSettings,
    storage_root: Path,
) -> str:
    """生成 runtime/container/volume 共用的稳定 identity，不包含 API key。"""

    relative = _storage_root_relative(
        storage_root=storage_root,
        outputs_root=path_settings.outputs_root,
    )
    payload = {
        "storage_root_relative": relative,
        "config": config.to_manifest(),
        "api_provider": openai_settings.provider,
        "api_model": openai_settings.model,
        "api_base_url": openai_settings.base_url,
        "api_timeout_seconds": openai_settings.timeout_seconds,
        "api_max_retries": openai_settings.max_retries,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_runtime_subject_identity(
    payload: dict[str, Any],
    *,
    expected_subject_id: str,
    expected_state: dict[str, Any] | None,
    source: str,
) -> None:
    """交叉验证 worker 的 subject 资源身份，拒绝跨 namespace 协议污染。"""

    if payload.get("subject_id") != expected_subject_id:
        raise ConfigurationError(
            f"Letta worker {source} returned a different subject identity"
        )
    for key in ("agent_id", "archive_id"):
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigurationError(f"Letta worker {source} returned invalid {key}")
        if expected_state is not None and value != expected_state[key]:
            raise ConfigurationError(
                f"Letta worker {source} returned a different {key}"
            )
    block_ids = payload.get("block_ids")
    if (
        not isinstance(block_ids, list)
        or len(block_ids) != 2
        or not all(isinstance(value, str) and value.strip() for value in block_ids)
        or len(set(block_ids)) != 2
    ):
        raise ConfigurationError(
            f"Letta worker {source} returned invalid block_ids"
        )
    if expected_state is not None and set(block_ids) != set(
        expected_state["block_ids"]
    ):
        raise ConfigurationError(
            f"Letta worker {source} returned a different block set"
        )


def _validate_readout_block_identity(
    blocks: list[Any],
    *,
    state: dict[str, Any],
) -> None:
    """确保 readout 仍是 sidecar 锁定的 human/summary 两块产品记忆。"""

    if len(blocks) != 2 or not all(isinstance(block, dict) for block in blocks):
        raise ConfigurationError(
            "Letta readout must contain exactly two core memory blocks"
        )
    block_ids = [block.get("id") for block in blocks]
    if (
        not all(isinstance(value, str) and value.strip() for value in block_ids)
        or len(set(block_ids)) != 2
        or set(block_ids) != set(state["block_ids"])
    ):
        raise ConfigurationError("Letta readout block identity conflicts with sidecar")
    labels = [block.get("label") for block in blocks]
    if set(labels) != {"human", "summary"} or len(set(labels)) != 2:
        raise ConfigurationError(
            "Letta readout must contain the human and summary blocks"
        )


def _storage_root_relative(*, storage_root: Path, outputs_root: Path) -> str:
    """把 method state 约束成配置 outputs 根内的机器无关相对路径。"""

    try:
        relative = storage_root.resolve().relative_to(outputs_root.resolve()).as_posix()
    except ValueError as exc:
        raise ConfigurationError(
            "Letta storage_root must live inside the configured outputs root"
        ) from exc
    if not relative.strip():
        raise ConfigurationError("Letta storage_root relative identity is empty")
    return relative


def _message_chunks(
    messages: list[dict[str, str]],
    size: int,
) -> tuple[list[dict[str, str]], ...]:
    """按原顺序切 SDK batch，不跨 session、不制造 placeholder。"""

    if size < 1:
        raise ConfigurationError("Letta message batch size must be positive")
    return tuple(messages[index : index + size] for index in range(0, len(messages), size))


def _official_message_wrapper(messages: list[dict[str, str]]) -> str:
    """字节级复现 ai-memory-sdk v0.2.0 的 role/content formatter。"""

    if not messages:
        raise ConfigurationError("Letta official wrapper requires at least one message")
    history = "\n".join(f"{message['role']}: {message['content']}" for message in messages)
    return (
        "<messages>The following message interactions have occured:\n"
        f"{history}</messages>"
    )


def _effective_time_prefix(
    *,
    turn_time: str | None,
    session_time: str | None,
    source_timestamp_embedded: object,
) -> str:
    """按 turn→session→None 唯一前置时间；严格 True marker 才去重。"""

    if isinstance(turn_time, str) and turn_time.strip():
        if source_timestamp_embedded is True:
            return ""
        return f"[Turn time: {turn_time.strip()}] "
    if isinstance(session_time, str) and session_time.strip():
        return f"[Session time: {session_time.strip()}] "
    return ""


def _split_source_time_prefix(content: str) -> tuple[str, str]:
    """拆出框架生成的 source-time 前缀，供 speaker 标签按统一顺序渲染。"""

    if not content.startswith("["):
        return "", content
    marker_end = content.find("] ")
    if marker_end < 0:
        return "", content
    prefix = content[: marker_end + 2]
    if not prefix.startswith(("[Turn time: ", "[Session time: ")):
        return "", content
    return prefix, content[marker_end + 2 :]


def _images_from_event(event: Any) -> list[ImageRef]:
    """从公开 event metadata 恢复 image caption，忽略 locator/query。"""

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


def _format_blocks(blocks: list[Any]) -> str:
    """按 ``(label,id)`` 稳定排序并生成可直接注入 answer builder 的文本。"""

    normalized = _normalize_blocks(blocks)
    return "\n\n".join(
        (
            f'<memory_block label="{html.escape(str(block["label"]), quote=True)}" '
            f'description="{html.escape(str(block["description"] or ""), quote=True)}">'
            f'{block["value"]}</memory_block>'
        )
        for block in normalized
    )


def _normalize_blocks(blocks: list[Any]) -> list[dict[str, str | None]]:
    """强校验并稳定排序 Letta core-block product units。"""

    normalized: list[dict[str, str | None]] = []
    for block in blocks:
        if not isinstance(block, dict):
            raise ConfigurationError("Letta block must be an object")
        block_id = block.get("id")
        label = block.get("label")
        value = block.get("value")
        description = block.get("description")
        if not isinstance(block_id, str) or not block_id.strip():
            raise ConfigurationError("Letta block id is missing")
        if not isinstance(label, str) or not label.strip():
            raise ConfigurationError("Letta block label is missing")
        if not isinstance(value, str):
            raise ConfigurationError(f"Letta block {block_id} value must be text")
        if description is not None and not isinstance(description, str):
            raise ConfigurationError(
                f"Letta block {block_id} description must be text or null"
            )
        normalized.append(
            {
                "id": block_id,
                "label": label,
                "value": value,
                "description": description,
            }
        )
    normalized.sort(key=lambda block: (str(block["label"]), str(block["id"])))
    return normalized


def _required_session_report_key(session_id: str | None) -> str:
    """返回可持久化的真实 session id；HaluMem extraction 不允许匿名 session。"""

    if not isinstance(session_id, str) or not session_id.strip():
        raise ConfigurationError(
            "Letta session memory reporting requires a non-blank session_id"
        )
    return session_id


def _session_input_digest(messages: list[dict[str, str]]) -> str:
    """计算 session report journal 的稳定公开输入摘要。"""

    payload = json.dumps(
        messages,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _changed_block_values(
    *,
    before: list[dict[str, str | None]],
    after: list[dict[str, str | None]],
) -> list[str]:
    """按稳定 block ID 返回 session 后新建或变化的非空 product values。"""

    before_by_id = {str(block["id"]): block for block in before}
    changed: list[str] = []
    for block in after:
        value = block["value"]
        if before_by_id.get(str(block["id"])) == block:
            continue
        if isinstance(value, str) and value.strip():
            changed.append(value)
    return changed


def _validate_sidecar(payload: Any) -> None:
    """强校验公开 subject sidecar，拒绝半写或宽松字段。"""

    if not isinstance(payload, dict):
        raise ConfigurationError("Letta subject sidecar must be an object")
    expected_keys = {
        "schema_version",
        "adapter_version",
        "isolation_key",
        "subject_id",
        "agent_id",
        "block_ids",
        "archive_id",
        "cleanup_phase",
        "pending_operation_id",
        "completed_operation_ids",
        "session_reports",
    }
    if set(payload) != expected_keys:
        raise ConfigurationError("Letta subject sidecar keys mismatch")
    if payload.get("schema_version") != LETTA_SIDECAR_SCHEMA_VERSION:
        raise ConfigurationError("Letta subject sidecar schema version mismatch")
    if payload.get("adapter_version") != LETTA_ADAPTER_VERSION:
        raise ConfigurationError("Letta subject sidecar adapter version mismatch")
    for key in ("isolation_key", "subject_id", "agent_id", "archive_id"):
        if not isinstance(payload.get(key), str) or not payload[key].strip():
            raise ConfigurationError(f"Letta subject sidecar {key} is invalid")
    block_ids = payload.get("block_ids")
    if (
        not isinstance(block_ids, list)
        or len(block_ids) != 2
        or not all(isinstance(value, str) and value.strip() for value in block_ids)
        or len(set(block_ids)) != len(block_ids)
    ):
        raise ConfigurationError("Letta subject sidecar block_ids is invalid")
    if payload.get("cleanup_phase") not in {"active", "pending"}:
        raise ConfigurationError("Letta subject sidecar cleanup_phase is invalid")
    pending_operation_id = payload.get("pending_operation_id")
    if pending_operation_id is not None and (
        not isinstance(pending_operation_id, str)
        or not pending_operation_id.strip()
    ):
        raise ConfigurationError(
            "Letta subject sidecar pending_operation_id is invalid"
        )
    completed_operation_ids = payload.get("completed_operation_ids")
    if (
        not isinstance(completed_operation_ids, list)
        or not all(
            isinstance(value, str) and value.strip()
            for value in completed_operation_ids
        )
        or len(set(completed_operation_ids)) != len(completed_operation_ids)
    ):
        raise ConfigurationError(
            "Letta subject sidecar completed_operation_ids is invalid"
        )
    if pending_operation_id in completed_operation_ids:
        raise ConfigurationError(
            "Letta pending operation cannot already be completed"
        )
    _validate_session_reports(payload.get("session_reports"))


def _validate_session_reports(value: Any) -> None:
    """校验 crash-safe session baseline/result journal。"""

    if not isinstance(value, dict):
        raise ConfigurationError("Letta session_reports must be an object")
    for session_id, record in value.items():
        if not isinstance(session_id, str) or not session_id.strip():
            raise ConfigurationError("Letta session_reports key is invalid")
        if not isinstance(record, dict) or set(record) != {
            "input_digest",
            "before_blocks",
            "memories",
        }:
            raise ConfigurationError("Letta session report record keys mismatch")
        digest = record.get("input_digest")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ConfigurationError("Letta session report input_digest is invalid")
        before_blocks = record.get("before_blocks")
        if not isinstance(before_blocks, list):
            raise ConfigurationError("Letta session report before_blocks must be a list")
        normalized = _normalize_blocks(before_blocks)
        if normalized != before_blocks:
            raise ConfigurationError(
                "Letta session report before_blocks must be normalized"
            )
        memories = record.get("memories")
        if memories is not None and (
            not isinstance(memories, list)
            or not all(isinstance(item, str) and item.strip() for item in memories)
        ):
            raise ConfigurationError(
                "Letta session report memories must be null or non-blank text list"
            )


def _letta_retrieval_evidence() -> RetrievalEvidence:
    """声明 query-independent evolved core blocks 不具备 retrieval metric 资格。"""

    return RetrievalEvidence(
        semantic_provenance=EvidenceAssertion(
            status="n_a",
            reason_code="letta_core_blocks_are_evolved_query_independent_memory",
            reason=(
                "Letta sleeptime tools continuously rewrite query-independent core "
                "blocks; current block text cannot be mapped losslessly to source "
                "benchmark evidence units."
            ),
        ),
        provenance_granularity="none",
        stable_ranking=EvidenceAssertion(
            status="n_a",
            reason_code="letta_core_blocks_are_not_query_ranked_retrieval_items",
            reason=(
                "The product readout returns all attached core blocks and does not "
                "perform a query-ranked retrieval operation."
            ),
        ),
    )


def build_letta_source_identity(
    path_settings: PathSettings | None = None,
) -> dict[str, Any]:
    """计算 vendored Letta、official SDK contract 与 wrapper 的稳定身份。"""

    settings = path_settings or load_path_settings()
    letta_root = settings.resolve_third_party_method_path(LETTA_METHOD_DIRECTORY)
    source_files = [letta_root / relative for relative in LETTA_SOURCE_FILES]
    missing = [path for path in source_files if not path.is_file()]
    if missing:
        raise ConfigurationError(
            "Letta source files missing: " + ", ".join(str(path) for path in missing)
        )
    vendored_sha256, relative_paths = _hash_relative_source_files(
        root=letta_root,
        source_files=source_files,
    )
    wrapper_files = [
        settings.project_root / LETTA_WRAPPER_LOGICAL_PATH,
        settings.project_root / LETTA_WORKER_LOGICAL_PATH,
        settings.project_root / WORKER_TRANSPORT_LOGICAL_PATH,
        settings.project_root / LETTA_BOOTSTRAP_LOGICAL_PATH,
    ]
    missing_wrappers = [path for path in wrapper_files if not path.is_file()]
    if missing_wrappers:
        raise ConfigurationError(
            "Letta wrapper files missing: "
            + ", ".join(str(path) for path in missing_wrappers)
        )
    wrapper_hashes = {
        path.relative_to(settings.project_root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in wrapper_files
    }
    identity = {
        "upstream_url": LETTA_UPSTREAM_URL,
        "release_tag": LETTA_RELEASE_TAG,
        "release_commit": LETTA_RELEASE_COMMIT,
        "commit": LETTA_COMMIT,
        "vendored_source_sha256": vendored_sha256,
        "sdk_upstream_url": LETTA_SDK_URL,
        "sdk_release_tag": LETTA_SDK_RELEASE_TAG,
        "sdk_commit": LETTA_SDK_COMMIT,
        "implementation_identity": LETTA_IMPLEMENTATION_IDENTITY,
        "source_mode": LETTA_SOURCE_MODE,
        "wrapper_hashes": wrapper_hashes,
    }
    source_sha256 = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "source_sha256": source_sha256,
        **identity,
        "file_count": len(relative_paths),
        "files": list(relative_paths),
    }


def _hash_relative_source_files(
    *,
    root: Path,
    source_files: list[Path],
) -> tuple[str, list[str]]:
    """按相对路径与 bytes 计算 vendored source 集合哈希。"""

    digest = hashlib.sha256()
    relative_paths: list[str] = []
    for source_file in source_files:
        relative = source_file.relative_to(root).as_posix()
        relative_paths.append(relative)
        path_bytes = relative.encode("utf-8")
        content = source_file.read_bytes()
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest(), relative_paths


__all__ = [
    "LETTA_ADAPTER_VERSION",
    "LETTA_EMPTY_MEMORY_SENTINEL",
    "LETTA_IMPLEMENTATION_IDENTITY",
    "LETTA_BUILD_LLM_RESPONSE_CONTRACT",
    "LETTA_LLM_MODEL_ID",
    "Letta",
    "LettaConfig",
    "LettaRuntime",
    "build_letta_source_identity",
    "clean_letta_conversation_state",
]
