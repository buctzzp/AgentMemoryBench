"""测试注册表驱动的 smoke 命令规划器。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from memory_benchmark.cli import main as main_cli
from memory_benchmark.cli.smoke_plan import build_smoke_execution_plan
from memory_benchmark.core import ConfigurationError


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CROP_FLAGS = frozenset(
    {
        "--rounds",
        "--turns",
        "--sessions",
        "--sources",
        "--conversations",
        "--questions-per-conversation",
    }
)


def test_halumem_plan_omits_every_crop_flag_and_uses_child_run_id() -> None:
    """HaluMem 固定 shape 命令不得再靠人工删除裁剪参数。"""

    plan = build_smoke_execution_plan(
        project_root=PROJECT_ROOT,
        method_name="mem0",
        benchmark_name="halumem",
        variant="medium",
        run_id="mem0-halumem-plan",
    )

    assert plan.shape.mode == "fixed"
    assert plan.shape.history_axis == "sessions"
    assert plan.prediction_run_id == "mem0-halumem-plan-medium"
    assert _CROP_FLAGS.isdisjoint(plan.predict_argv)
    assert "--workers" not in plan.predict_argv
    assert plan.evaluate_argv[
        plan.evaluate_argv.index("--run-id") + 1
    ] == "mem0-halumem-plan-medium"
    assert {
        metric.name for metric in plan.metrics
    } >= {
        "halumem-extraction",
        "halumem-memory-type",
        "halumem-update",
        "halumem-qa",
    }
    metric_names = [metric.name for metric in plan.metrics]
    assert metric_names.index("halumem-extraction") < metric_names.index(
        "halumem-memory-type"
    )
    assert metric_names.index("halumem-update") < metric_names.index(
        "halumem-memory-type"
    )
    evaluate_metrics = [
        plan.evaluate_argv[index + 1]
        for index, argument in enumerate(plan.evaluate_argv)
        if argument == "--metric"
    ]
    assert evaluate_metrics == metric_names


def test_halumem_plan_rejects_crop_override_before_runtime() -> None:
    """固定 shape 的任一通用裁剪覆盖都必须在规划阶段失败。"""

    with pytest.raises(ConfigurationError, match="fixed shape"):
        build_smoke_execution_plan(
            project_root=PROJECT_ROOT,
            method_name="mem0",
            benchmark_name="halumem",
            run_id="mem0-halumem-plan",
            history_limit=2,
        )


def test_locomo_plan_emits_registered_default_shape() -> None:
    """LoCoMo 规划器应从 policy 生成 1 round/1 conversation/1 question。"""

    plan = build_smoke_execution_plan(
        project_root=PROJECT_ROOT,
        method_name="mem0",
        benchmark_name="locomo",
        run_id="mem0-locomo-plan",
    )

    assert plan.shape.to_dict() == {
        "mode": "croppable",
        "history_axis": "rounds",
        "history_limit": 1,
        "isolation_limit": 1,
        "question_limit": 1,
    }
    assert plan.prediction_run_id == "mem0-locomo-plan"
    assert _flag_value(plan.predict_argv, "--rounds") == "1"
    assert _flag_value(plan.predict_argv, "--conversations") == "1"
    assert _flag_value(plan.predict_argv, "--questions-per-conversation") == "1"


def test_memos_plan_rejects_unqualified_worker_override_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MemOS W2 必须只靠 registry/TOML 被拒绝，不得读取 API secret。"""

    monkeypatch.delenv("OPENCODEGO_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="does not support smoke worker override"):
        build_smoke_execution_plan(
            project_root=PROJECT_ROOT,
            method_name="memos",
            benchmark_name="locomo",
            run_id="memos-locomo-plan",
            workers=2,
        )


def test_mem0_plan_emits_allowed_worker_override() -> None:
    """允许覆盖的 method 应把 W2 精确写入生成的 predict argv。"""

    plan = build_smoke_execution_plan(
        project_root=PROJECT_ROOT,
        method_name="mem0",
        benchmark_name="locomo",
        run_id="mem0-locomo-w2-plan",
        workers=2,
    )

    assert plan.workers.configured == 1
    assert plan.workers.selected == 2
    assert plan.workers.cli_override_emitted is True
    assert _flag_value(plan.predict_argv, "--workers") == "2"


def test_graphiti_variant_gate_rejects_membench_100k_but_plans_0_10k(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graphiti 缺时 variant 应在 secret/runtime 前失败，其余 MemBench 可规划。"""

    monkeypatch.delenv("OPENCODEGO_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(
        ConfigurationError,
        match="does not support MemBench variant '100k'",
    ):
        build_smoke_execution_plan(
            project_root=PROJECT_ROOT,
            method_name="graphiti",
            benchmark_name="membench",
            variant="100k",
            run_id="graphiti-membench-100k-rejected",
        )

    plan = build_smoke_execution_plan(
        project_root=PROJECT_ROOT,
        method_name="graphiti",
        benchmark_name="membench",
        variant="0_10k",
        run_id="graphiti-membench-0-10k-ready",
    )
    assert plan.prediction_run_id == "graphiti-membench-0-10k-ready-0-10k"
    assert plan.method == "graphiti"


def test_operation_level_plan_rejects_parallel_request() -> None:
    """HaluMem operation-level runner 的 W1 门也应在 planner 前置。"""

    with pytest.raises(ConfigurationError, match="requires workers=1"):
        build_smoke_execution_plan(
            project_root=PROJECT_ROOT,
            method_name="mem0",
            benchmark_name="halumem",
            run_id="mem0-halumem-w2-plan",
            workers=2,
        )


def test_multivariant_plan_evaluates_exact_child_run_id() -> None:
    """LongMemEval evaluate 命令必须消费追加 variant suffix 的 child run。"""

    plan = build_smoke_execution_plan(
        project_root=PROJECT_ROOT,
        method_name="mem0",
        benchmark_name="longmemeval",
        variant="s_cleaned",
        run_id="mem0-lme-plan",
    )

    assert plan.prediction_run_id == "mem0-lme-plan-s-cleaned"
    assert _flag_value(plan.evaluate_argv, "--run-id") == (
        "mem0-lme-plan-s-cleaned"
    )


def test_main_plan_smoke_prints_json_without_api_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """统一 CLI 应只读生成 JSON，缺少 API key 也能成功。"""

    monkeypatch.delenv("OPENCODEGO_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    exit_code = main_cli.main(
        [
            "plan-smoke",
            "--root",
            str(PROJECT_ROOT),
            "--method",
            "mem0",
            "--benchmark",
            "halumem",
            "--variant",
            "medium",
            "--run-id",
            "mem0-halumem-cli-plan",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["contract_version"] == "smoke-plan-v1"
    assert payload["shape"]["mode"] == "fixed"
    assert _CROP_FLAGS.isdisjoint(payload["predict_argv"])


@pytest.mark.parametrize(
    ("benchmark_name", "variant"),
    [
        ("locomo", "locomo10"),
        ("longmemeval", "s_cleaned"),
        ("membench", "0_10k"),
        ("beam", "100k"),
        ("halumem", "medium"),
    ],
)
def test_planned_predict_argv_roundtrips_through_main_cli(
    monkeypatch: pytest.MonkeyPatch,
    benchmark_name: str,
    variant: str,
) -> None:
    """五家 planner 生成的 argv 必须被真实 argparse/normalizer 原样接受。"""

    plan = build_smoke_execution_plan(
        project_root=PROJECT_ROOT,
        method_name="mem0",
        benchmark_name=benchmark_name,
        variant=variant,
        run_id=f"mem0-{benchmark_name}-roundtrip",
    )
    received: list[object] = []
    monkeypatch.setattr(
        main_cli,
        "execute_predict",
        lambda command: received.append(command)
        or SimpleNamespace(run_id=plan.prediction_run_id),
    )

    exit_code = main_cli.main(list(plan.predict_argv[3:]))

    assert exit_code == 0
    assert len(received) == 1


def _flag_value(argv: tuple[str, ...], flag: str) -> str:
    """返回 argv 中一个单值 flag 的值。"""

    return argv[argv.index(flag) + 1]
