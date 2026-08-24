"""运行时与执行层 profile 的强类型组合。

本模块只读取公开配置，不读取 secret，也不构造任何第三方 client。method 算法参数由
``configs/methods`` 独立加载；这里负责把 API provider/model 与框架 conversation 并发
组合成一次新 run 的公开身份。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from memory_benchmark.config.profiles import load_typed_profile
from memory_benchmark.config.settings import (
    SUPPORTED_API_PROVIDERS,
    build_api_runtime_manifest,
)
from memory_benchmark.core import ConfigurationError


RUNTIME_PROFILE_PATH = Path("configs/runtime/api.toml")
EXECUTION_PROFILE_PATH = Path("configs/execution/prediction.toml")


@dataclass(frozen=True)
class ApiRuntimeProfile:
    """一次 run 使用的公开 API provider/model 选择。"""

    profile_name: str
    provider: str
    model: str
    timeout_seconds: float = 60.0
    max_retries: int = 8
    retry_wait_seconds: float = 5.0
    retry_backoff_multiplier: float = 2.0
    retry_max_wait_seconds: float = 60.0
    structured_output_mode: str = "json_schema"

    def __post_init__(self) -> None:
        """拒绝空白值、未知 provider 与配置/transport 自相矛盾。"""

        if not self.profile_name.strip() or self.profile_name != self.profile_name.strip():
            raise ConfigurationError("API runtime profile_name must be a trimmed string")
        if self.provider not in SUPPORTED_API_PROVIDERS:
            raise ConfigurationError(
                f"Unsupported API runtime provider: {self.provider!r}"
            )
        if not self.model.strip() or self.model != self.model.strip():
            raise ConfigurationError("API runtime model must be a trimmed string")
        for field_name in (
            "timeout_seconds",
            "retry_wait_seconds",
            "retry_backoff_multiplier",
            "retry_max_wait_seconds",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or float(value) <= 0
            ):
                raise ConfigurationError(
                    f"API runtime {field_name} must be positive"
                )
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ConfigurationError("API runtime max_retries must be non-negative")
        if self.structured_output_mode not in {"json_object", "json_schema"}:
            raise ConfigurationError(
                "API runtime structured_output_mode must be json_object or json_schema"
            )
        # 复用 settings 的公开 identity 校验，避免配置层再维护一份 transport 表。
        build_api_runtime_manifest(provider=self.provider, model=self.model)

    def to_manifest_dict(self) -> dict[str, object]:
        """返回参与 manifest/resume 的公开 runtime 身份。"""

        return build_api_runtime_manifest(provider=self.provider, model=self.model)


@dataclass(frozen=True)
class ExecutionProfile:
    """一次 run 的框架 execution 默认值。"""

    profile_name: str
    default_max_workers: int
    worker_request_timeout_seconds: float = 900.0
    drain_timeout_seconds: float = 600.0
    task_timeout_seconds: float = 600.0
    service_startup_timeout_seconds: float = 60.0
    suppress_method_stdout: bool = True

    def __post_init__(self) -> None:
        """拒绝非正并发。"""

        if not self.profile_name.strip() or self.profile_name != self.profile_name.strip():
            raise ConfigurationError("Execution profile_name must be a trimmed string")
        if type(self.default_max_workers) is not int or self.default_max_workers < 1:
            raise ConfigurationError("Execution default_max_workers must be a positive integer")
        for field_name in (
            "worker_request_timeout_seconds",
            "drain_timeout_seconds",
            "task_timeout_seconds",
            "service_startup_timeout_seconds",
        ):
            value = getattr(self, field_name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or float(value) <= 0
            ):
                raise ConfigurationError(
                    f"Execution {field_name} must be positive"
                )
        if type(self.suppress_method_stdout) is not bool:
            raise ConfigurationError(
                "Execution suppress_method_stdout must be a boolean"
            )

    def resolve_for_method(self, *, method_max_workers_cap: int) -> int:
        """按 method 的执行能力上限解析实际默认 conversation 并发。"""

        if type(method_max_workers_cap) is not int or method_max_workers_cap < 1:
            raise ConfigurationError("method_max_workers_cap must be a positive integer")
        return min(self.default_max_workers, method_max_workers_cap)


@dataclass(frozen=True)
class RunComposition:
    """method 算法配置之外的一次 run 组合结果。"""

    runtime: ApiRuntimeProfile
    execution: ExecutionProfile
    resolved_max_workers: int

    def __post_init__(self) -> None:
        """校验组合对象与已解析并发。"""

        if not isinstance(self.runtime, ApiRuntimeProfile):
            raise ConfigurationError("RunComposition.runtime must be ApiRuntimeProfile")
        if not isinstance(self.execution, ExecutionProfile):
            raise ConfigurationError("RunComposition.execution must be ExecutionProfile")
        if type(self.resolved_max_workers) is not int or self.resolved_max_workers < 1:
            raise ConfigurationError("resolved_max_workers must be a positive integer")
        if self.resolved_max_workers > self.execution.default_max_workers:
            raise ConfigurationError(
                "resolved_max_workers cannot exceed execution default_max_workers"
            )

    def to_manifest_dict(self) -> dict[str, object]:
        """返回不含 secret、参与新 run resume 的完整组合身份。"""

        return {
            "contract_version": "v1",
            "runtime": {
                "profile_name": self.runtime.profile_name,
                **self.runtime.to_manifest_dict(),
                "request_policy": {
                    "timeout_seconds": self.runtime.timeout_seconds,
                    "max_retries": self.runtime.max_retries,
                    "retry_wait_seconds": self.runtime.retry_wait_seconds,
                    "retry_backoff_multiplier": (
                        self.runtime.retry_backoff_multiplier
                    ),
                    "retry_max_wait_seconds": self.runtime.retry_max_wait_seconds,
                },
                "structured_output_mode": self.runtime.structured_output_mode,
            },
            "execution": {
                "profile_name": self.execution.profile_name,
                "default_max_workers": self.execution.default_max_workers,
                "resolved_max_workers": self.resolved_max_workers,
                "worker_request_timeout_seconds": (
                    self.execution.worker_request_timeout_seconds
                ),
                "drain_timeout_seconds": self.execution.drain_timeout_seconds,
                "task_timeout_seconds": self.execution.task_timeout_seconds,
                "service_startup_timeout_seconds": (
                    self.execution.service_startup_timeout_seconds
                ),
                "suppress_method_stdout": self.execution.suppress_method_stdout,
            },
        }


def _profile_section_name(profile_name: str) -> str:
    """把公开 run profile 映射到 runtime/execution TOML section。"""

    normalized = profile_name.strip().lower()
    if normalized in {"smoke", "pilot"}:
        return normalized
    if normalized in {"official-full", "official_full"}:
        return "official_full"
    if normalized.startswith("author-") or normalized.startswith("author_"):
        return "official_full"
    raise ConfigurationError(f"Unsupported run profile: {profile_name!r}")


def load_run_composition(
    *,
    project_root: str | Path,
    profile_name: str,
    method_max_workers_cap: int,
) -> RunComposition:
    """从独立 TOML 组合 API runtime 与 execution profile。

    输入:
        project_root: 项目根目录。
        profile_name: CLI 公开 run profile。
        method_max_workers_cap: registry 声明的产品执行能力上限。

    输出:
        RunComposition: 不含 secret 与 method 算法参数的组合结果。
    """

    root = Path(project_root).expanduser().resolve()
    section_name = _profile_section_name(profile_name)
    runtime = load_typed_profile(
        root / RUNTIME_PROFILE_PATH,
        section_name,
        ApiRuntimeProfile,
    )
    execution = load_typed_profile(
        root / EXECUTION_PROFILE_PATH,
        section_name,
        ExecutionProfile,
    )
    return RunComposition(
        runtime=runtime,
        execution=execution,
        resolved_max_workers=execution.resolve_for_method(
            method_max_workers_cap=method_max_workers_cap,
        ),
    )


__all__ = [
    "ApiRuntimeProfile",
    "EXECUTION_PROFILE_PATH",
    "ExecutionProfile",
    "RUNTIME_PROFILE_PATH",
    "RunComposition",
    "load_run_composition",
]
