"""从注册契约生成可执行 smoke 命令。

本模块只读取 benchmark/method/evaluator 的公开注册信息与 method TOML，不读取
``.env``、不构造 method runtime、也不调用 API。命令行 smoke 必须先经这里规划，
避免靠操作者记忆 HaluMem 固定 shape、多 variant child run-id 或 worker 资格。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shlex

from memory_benchmark.benchmark_adapters import get_benchmark_registration
from memory_benchmark.core import ConfigurationError, validate_compatibility
from memory_benchmark.evaluators import (
    get_evaluator_registration,
    list_metrics,
    order_metrics_for_evaluation,
)
from memory_benchmark.methods import (
    get_method_registration,
    load_method_profile,
)

from .run_prediction import resolve_explicit_prediction_run_id


SMOKE_PLAN_CONTRACT_VERSION = "smoke-plan-v1"


@dataclass(frozen=True)
class SmokeShapePlan:
    """一个 benchmark 的已解析 smoke 形状。"""

    mode: str
    history_axis: str
    history_limit: int
    isolation_limit: int
    question_limit: int

    def to_dict(self) -> dict[str, object]:
        """返回不含运行时状态的公开字典。"""

        return {
            "mode": self.mode,
            "history_axis": self.history_axis,
            "history_limit": self.history_limit,
            "isolation_limit": self.isolation_limit,
            "question_limit": self.question_limit,
        }


@dataclass(frozen=True)
class SmokeWorkerPlan:
    """method 配置与 benchmark 执行面共同裁出的 worker 计划。"""

    configured: int
    selected: int
    override_allowed: bool
    cli_override_emitted: bool

    def to_dict(self) -> dict[str, object]:
        """返回 worker 资格与最终选择。"""

        return {
            "configured": self.configured,
            "selected": self.selected,
            "override_allowed": self.override_allowed,
            "cli_override_emitted": self.cli_override_emitted,
        }


@dataclass(frozen=True)
class SmokeMetricPlan:
    """一个适用于当前 benchmark 的 evaluator 计划。"""

    name: str
    requires_api: bool

    def to_dict(self) -> dict[str, object]:
        """返回 metric 的 CLI 名与 API 资格。"""

        return {
            "name": self.name,
            "requires_api": self.requires_api,
        }


@dataclass(frozen=True)
class SmokeExecutionPlan:
    """一次 method × benchmark × variant smoke 的完整可执行计划。"""

    method: str
    benchmark: str
    variant: str
    base_run_id: str
    prediction_run_id: str
    shape: SmokeShapePlan
    workers: SmokeWorkerPlan
    metrics: tuple[SmokeMetricPlan, ...]
    predict_argv: tuple[str, ...]
    evaluate_argv: tuple[str, ...]

    @property
    def contract_version(self) -> str:
        """返回 planner 的稳定契约版本。"""

        return SMOKE_PLAN_CONTRACT_VERSION

    @property
    def predict_command(self) -> str:
        """返回可复制执行的 shell-safe predict 命令。"""

        return shlex.join(self.predict_argv)

    @property
    def evaluate_command(self) -> str:
        """返回可复制执行的 shell-safe evaluate 命令。"""

        return shlex.join(self.evaluate_argv)

    def to_dict(self) -> dict[str, object]:
        """转换为稳定 JSON 结构；argv 是执行事实源，command 只供人阅读。"""

        return {
            "contract_version": self.contract_version,
            "method": self.method,
            "benchmark": self.benchmark,
            "variant": self.variant,
            "base_run_id": self.base_run_id,
            "prediction_run_id": self.prediction_run_id,
            "shape": self.shape.to_dict(),
            "workers": self.workers.to_dict(),
            "metrics": [metric.to_dict() for metric in self.metrics],
            "predict_argv": list(self.predict_argv),
            "predict_command": self.predict_command,
            "evaluate_argv": list(self.evaluate_argv),
            "evaluate_command": self.evaluate_command,
        }


def build_smoke_execution_plan(
    *,
    project_root: str | Path,
    method_name: str,
    benchmark_name: str,
    run_id: str,
    variant: str | None = None,
    history_limit: int | None = None,
    isolation_limit: int | None = None,
    question_limit: int | None = None,
    workers: int | None = None,
) -> SmokeExecutionPlan:
    """只读注册契约并生成 predict + evaluate 的精确 argv。

    固定 shape benchmark 拒绝所有裁剪覆盖。operation-level benchmark 当前由统一
    runner 强制 W1；规划器会在 runtime/API 前把该约束与 method worker 配置合并。
    """

    root = Path(project_root).expanduser().resolve()
    method_registration = get_method_registration(method_name)
    benchmark_registration = get_benchmark_registration(benchmark_name)
    if not benchmark_registration.prediction_enabled:
        raise ConfigurationError(
            f"Benchmark '{benchmark_name}' prediction is not enabled"
        )
    validate_compatibility(
        benchmark_task_family=benchmark_registration.task_family,
        required_capabilities=benchmark_registration.required_capabilities,
        method_task_families=method_registration.task_families,
        provided_capabilities=method_registration.provided_capabilities,
    )

    selected_variant = (
        benchmark_registration.default_variant
        if variant is None
        else variant.strip()
    )
    if not selected_variant:
        raise ConfigurationError("smoke plan variant must not be blank")
    if selected_variant == "all":
        raise ConfigurationError(
            "plan-smoke requires one concrete variant; generate one plan per variant"
        )
    benchmark_registration.variant_spec(selected_variant)
    method_registration.validate_variant(benchmark_name, selected_variant)

    smoke_policy = benchmark_registration.smoke_policy
    if smoke_policy is None:
        raise ConfigurationError(
            f"{benchmark_name} does not declare a smoke policy"
        )
    shape = _resolve_smoke_shape(
        benchmark_name=benchmark_name,
        shape_mode=smoke_policy.shape_mode,
        history_axis=smoke_policy.history_axis,
        default_history_limit=smoke_policy.default_history_limit,
        default_isolation_limit=smoke_policy.default_isolation_limit,
        default_question_limit=smoke_policy.default_question_limit,
        history_limit=history_limit,
        isolation_limit=isolation_limit,
        question_limit=question_limit,
    )

    config = load_method_profile(
        method_name=method_name,
        profile_name="smoke",
        project_root=root,
    )
    configured_workers = method_registration.max_workers_getter(config)
    worker_plan = _resolve_worker_plan(
        method_display_name=method_registration.display_name,
        benchmark_name=benchmark_name,
        operation_level=benchmark_registration.operation_level,
        configured_workers=configured_workers,
        requested_workers=workers,
        override_allowed=method_registration.allow_smoke_worker_override,
    )

    normalized_run_id = run_id.strip()
    prediction_run_id = resolve_explicit_prediction_run_id(
        base_run_id=normalized_run_id,
        variant=selected_variant,
        registration=benchmark_registration,
    )
    metrics_by_name: dict[str, SmokeMetricPlan] = {}
    for metric_name in list_metrics():
        evaluator_registration = get_evaluator_registration(metric_name)
        if benchmark_name not in evaluator_registration.supported_benchmarks:
            continue
        metrics_by_name[metric_name] = (
            SmokeMetricPlan(
                name=metric_name,
                requires_api=evaluator_registration.requires_api,
            )
        )
    metric_plan = tuple(
        metrics_by_name[metric_name]
        for metric_name in order_metrics_for_evaluation(list(metrics_by_name))
    )
    if not metric_plan:
        raise ConfigurationError(
            f"{benchmark_name} does not have any registered evaluators"
        )

    predict_argv = _build_predict_argv(
        project_root=root,
        method_name=method_name,
        benchmark_name=benchmark_name,
        variant=selected_variant,
        base_run_id=normalized_run_id,
        shape=shape,
        workers=worker_plan,
    )
    evaluate_argv = _build_evaluate_argv(
        project_root=root,
        prediction_run_id=prediction_run_id,
        metrics=metric_plan,
    )
    return SmokeExecutionPlan(
        method=method_name,
        benchmark=benchmark_name,
        variant=selected_variant,
        base_run_id=normalized_run_id,
        prediction_run_id=prediction_run_id,
        shape=shape,
        workers=worker_plan,
        metrics=metric_plan,
        predict_argv=predict_argv,
        evaluate_argv=evaluate_argv,
    )


def _resolve_smoke_shape(
    *,
    benchmark_name: str,
    shape_mode: str,
    history_axis: str,
    default_history_limit: int,
    default_isolation_limit: int,
    default_question_limit: int,
    history_limit: int | None,
    isolation_limit: int | None,
    question_limit: int | None,
) -> SmokeShapePlan:
    """合并 smoke policy 默认值与可选覆盖。"""

    if shape_mode == "fixed" and any(
        value is not None
        for value in (history_limit, isolation_limit, question_limit)
    ):
        raise ConfigurationError(
            f"{benchmark_name} smoke has a fixed shape and does not accept "
            "history/isolation/question overrides"
        )
    return SmokeShapePlan(
        mode=shape_mode,
        history_axis=history_axis,
        history_limit=_positive_or_default(
            history_limit,
            default=default_history_limit,
            field_name="history limit",
        ),
        isolation_limit=_positive_or_default(
            isolation_limit,
            default=default_isolation_limit,
            field_name="isolation limit",
        ),
        question_limit=_positive_or_default(
            question_limit,
            default=default_question_limit,
            field_name="question limit",
        ),
    )


def _resolve_worker_plan(
    *,
    method_display_name: str,
    benchmark_name: str,
    operation_level: bool,
    configured_workers: int,
    requested_workers: int | None,
    override_allowed: bool,
) -> SmokeWorkerPlan:
    """在 method 配置、覆盖资格和 operation-level W1 门之间裁出 worker。"""

    configured = _positive_or_default(
        configured_workers,
        default=1,
        field_name="configured workers",
    )
    requested = (
        None
        if requested_workers is None
        else _positive_or_default(
            requested_workers,
            default=configured,
            field_name="workers",
        )
    )
    if operation_level:
        if requested not in {None, 1}:
            raise ConfigurationError(
                f"{benchmark_name} operation-level smoke requires workers=1"
            )
        selected = 1
    else:
        selected = configured if requested is None else requested

    emits_override = selected != configured
    if emits_override and not override_allowed:
        raise ConfigurationError(
            f"{method_display_name} does not support smoke worker override "
            f"from configured {configured} to {selected}"
        )
    return SmokeWorkerPlan(
        configured=configured,
        selected=selected,
        override_allowed=override_allowed,
        cli_override_emitted=emits_override,
    )


def _build_predict_argv(
    *,
    project_root: Path,
    method_name: str,
    benchmark_name: str,
    variant: str,
    base_run_id: str,
    shape: SmokeShapePlan,
    workers: SmokeWorkerPlan,
) -> tuple[str, ...]:
    """生成真实 CLI 可直接执行的 predict argv。"""

    argv = [
        "uv",
        "run",
        "memory-benchmark",
        "predict",
        "smoke",
        "--root",
        str(project_root),
        "--method",
        method_name,
        "--benchmark",
        benchmark_name,
        "--variant",
        variant,
        "--config-track",
        "unified",
        "--run-id",
        base_run_id,
        "--allow-api",
    ]
    if shape.mode != "fixed":
        argv.extend(
            [
                f"--{shape.history_axis}",
                str(shape.history_limit),
                "--conversations",
                str(shape.isolation_limit),
                "--questions-per-conversation",
                str(shape.question_limit),
            ]
        )
    if workers.cli_override_emitted:
        argv.extend(["--workers", str(workers.selected)])
    return tuple(argv)


def _build_evaluate_argv(
    *,
    project_root: Path,
    prediction_run_id: str,
    metrics: tuple[SmokeMetricPlan, ...],
) -> tuple[str, ...]:
    """生成覆盖当前 benchmark 全部已注册 evaluator 的 evaluate argv。"""

    argv = [
        "uv",
        "run",
        "memory-benchmark",
        "evaluate",
        "--root",
        str(project_root),
        "--run-id",
        prediction_run_id,
    ]
    for metric in metrics:
        argv.extend(["--metric", metric.name])
    if any(metric.requires_api for metric in metrics):
        argv.append("--allow-api")
    return tuple(argv)


def _positive_or_default(
    value: int | None,
    *,
    default: int,
    field_name: str,
) -> int:
    """返回正整数值，未提供时使用已注册默认值。"""

    normalized = default if value is None else value
    if isinstance(normalized, bool) or not isinstance(normalized, int):
        raise ConfigurationError(f"{field_name} must be an integer")
    if normalized < 1:
        raise ConfigurationError(f"{field_name} must be at least 1")
    return normalized


__all__ = [
    "SMOKE_PLAN_CONTRACT_VERSION",
    "SmokeExecutionPlan",
    "SmokeMetricPlan",
    "SmokeShapePlan",
    "SmokeWorkerPlan",
    "build_smoke_execution_plan",
]
