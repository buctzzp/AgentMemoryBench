"""测试成本校准 smoke 的外层并行调度。

这些测试全部使用 fake prediction runner，不调用真实 API。它们验证的是调度层是否
正确生成 method × benchmark child run、是否强制开启效率观测、是否限制外层并发，
以及单个 child 失败后其他 child 是否仍能完成。
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.cli.run_prediction import (
    PredictionBatchResult,
    PredictionVariantResult,
)
from memory_benchmark.core import ConfigurationError
from memory_benchmark.runners.cost_calibration import (
    CalibrationSmokeCommand,
    run_cost_calibration_smoke,
)


pytestmark = pytest.mark.unit


def _fake_batch(method: str, benchmark: str, run_id: str) -> PredictionBatchResult:
    """构造一个最小 prediction batch，模拟 registered prediction 成功返回。"""

    return PredictionBatchResult(
        benchmark=benchmark,
        selector="default",
        runs=(
            PredictionVariantResult(
                variant="default",
                run_id=run_id,
                summary=SimpleNamespace(
                    run_id=run_id,
                    method=method,
                    benchmark=benchmark,
                ),
            ),
        ),
    )


def test_calibration_runs_every_method_benchmark_pair_with_efficiency_enabled(
    tmp_path: Path,
) -> None:
    """每个 method × benchmark 都应生成独立 child run，并强制开启效率观测。"""

    calls: list[dict[str, object]] = []

    def fake_runner(**kwargs):
        """记录调度参数，并返回一个成功的 fake prediction batch。"""

        calls.append(kwargs)
        return _fake_batch(
            method=str(kwargs["method_name"]),
            benchmark=str(kwargs["benchmark_name"]),
            run_id=str(kwargs["run_id"]),
        )

    summary = run_cost_calibration_smoke(
        CalibrationSmokeCommand(
            project_root=tmp_path,
            methods=("mem0", "memoryos"),
            benchmarks=("locomo", "longmemeval"),
            run_prefix="ohmygpt-calib",
            confirm_api=True,
            max_parallel_runs=2,
        ),
        prediction_runner=fake_runner,
    )

    assert summary.total_tasks == 4
    assert summary.completed_count == 4
    assert summary.failed_count == 0
    assert {call["run_id"] for call in calls} == {
        "ohmygpt-calib-mem0-locomo",
        "ohmygpt-calib-mem0-longmemeval",
        "ohmygpt-calib-memoryos-locomo",
        "ohmygpt-calib-memoryos-longmemeval",
    }
    assert all(call["profile_name"] == "smoke" for call in calls)
    assert all(call["resume"] is True for call in calls)
    assert all(call["confirm_api"] is True for call in calls)
    assert all(call["smoke_conversation_limit"] == 1 for call in calls)
    assert all(call["enable_efficiency_observability"] is True for call in calls)


def test_calibration_limits_outer_parallelism_to_two(tmp_path: Path) -> None:
    """外层 child run 并发数必须受 max_parallel_runs 控制，避免 API 网关过载。"""

    running = 0
    max_seen = 0
    lock = threading.Lock()
    two_workers_started = threading.Event()

    def fake_runner(**kwargs):
        """模拟较慢的 child run，用于观察最大并发数。"""

        nonlocal running, max_seen
        with lock:
            running += 1
            max_seen = max(max_seen, running)
            if max_seen == 2:
                two_workers_started.set()
        two_workers_started.wait(timeout=1.0)
        time.sleep(0.01)
        with lock:
            running -= 1
        return _fake_batch(
            method=str(kwargs["method_name"]),
            benchmark=str(kwargs["benchmark_name"]),
            run_id=str(kwargs["run_id"]),
        )

    summary = run_cost_calibration_smoke(
        CalibrationSmokeCommand(
            project_root=tmp_path,
            methods=("mem0", "memoryos"),
            benchmarks=("locomo", "longmemeval"),
            run_prefix="parallel-check",
            confirm_api=True,
            max_parallel_runs=2,
        ),
        prediction_runner=fake_runner,
    )

    assert summary.completed_count == 4
    assert max_seen == 2


def test_calibration_keeps_running_when_one_child_fails(tmp_path: Path) -> None:
    """单个 child run 失败时应写入失败结果，但不能阻止其他组合完成。"""

    def fake_runner(**kwargs):
        """让 A-Mem child run 失败，其余 child run 正常返回。"""

        if kwargs["method_name"] == "amem":
            raise RuntimeError("temporary gateway failure")
        return _fake_batch(
            method=str(kwargs["method_name"]),
            benchmark=str(kwargs["benchmark_name"]),
            run_id=str(kwargs["run_id"]),
        )

    summary = run_cost_calibration_smoke(
        CalibrationSmokeCommand(
            project_root=tmp_path,
            methods=("mem0", "amem"),
            benchmarks=("locomo",),
            run_prefix="failure-check",
            confirm_api=True,
            max_parallel_runs=2,
        ),
        prediction_runner=fake_runner,
    )

    assert summary.completed_count == 1
    assert summary.failed_count == 1
    failed = [run for run in summary.runs if run.status == "failed"][0]
    assert failed.method == "amem"
    assert failed.run_id == "failure-check-amem-locomo"
    assert failed.error_type == "RuntimeError"
    assert "gateway" in str(failed.error)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("methods", (), "methods"),
        ("benchmarks", (), "benchmarks"),
        ("run_prefix", "../bad", "path separators"),
        ("profile", "official-full", "smoke profile"),
        ("smoke_conversation_limit", 2, "exactly 1"),
        ("max_parallel_runs", 3, "1 or 2"),
    ],
)
def test_calibration_command_rejects_unsafe_scope(
    tmp_path: Path,
    field: str,
    value,
    message: str,
) -> None:
    """校准入口必须拒绝可能误跑全量或污染输出目录的参数。"""

    values = {
        "project_root": tmp_path,
        "methods": ("mem0",),
        "benchmarks": ("locomo",),
        "run_prefix": "safe-prefix",
        "profile": "smoke",
        "smoke_conversation_limit": 1,
        "max_parallel_runs": 2,
    }
    values[field] = value

    with pytest.raises(ConfigurationError, match=message):
        CalibrationSmokeCommand(**values)
