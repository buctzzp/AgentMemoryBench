"""API runtime 与 execution composition root 的无网络测试。"""

from __future__ import annotations

from pathlib import Path
import tomllib

import pytest

from memory_benchmark.config.run_profiles import load_run_composition
from memory_benchmark.core import ConfigurationError


pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_current_method_tomls_have_one_main_section_and_no_framework_keys() -> None:
    """十家主参数必须单源，稀疏 author section 之外不得恢复旧双轨。"""

    forbidden = {
        "answer_builder",
        "api_max_retries",
        "api_retry_backoff_multiplier",
        "api_retry_max_wait_seconds",
        "api_retry_wait_seconds",
        "api_timeout_seconds",
        "drain_timeout_seconds",
        "extraction_model",
        "llm_model",
        "max_workers",
        "postgres_startup_timeout_seconds",
        "reader_model",
        "service_startup_timeout_seconds",
        "structured_output_mode",
        "suppress_official_stdout",
        "task_timeout_seconds",
        "worker_request_timeout_seconds",
    }
    for profile_path in sorted((PROJECT_ROOT / "configs/methods").glob("*.toml")):
        payload = tomllib.loads(profile_path.read_text(encoding="utf-8"))
        assert "method" in payload, profile_path
        unexpected = {
            section
            for section in payload
            if section != "method" and not section.startswith("author_")
        }
        assert not unexpected, (profile_path, sorted(unexpected))
        overlap = forbidden.intersection(payload["method"])
        assert not overlap, (profile_path, sorted(overlap))


def test_current_profiles_resolve_without_method_algorithm_config() -> None:
    """runtime/execution 应独立于 method TOML，并按可选产品硬上限组合。"""

    smoke = load_run_composition(
        project_root=PROJECT_ROOT,
        profile_name="smoke",
        method_max_workers_cap=10,
    )
    pilot = load_run_composition(
        project_root=PROJECT_ROOT,
        profile_name="pilot",
        method_max_workers_cap=10,
    )
    calibration = load_run_composition(
        project_root=PROJECT_ROOT,
        profile_name="calibration",
        method_max_workers_cap=None,
    )
    official = load_run_composition(
        project_root=PROJECT_ROOT,
        profile_name="official-full",
        method_max_workers_cap=1,
    )

    assert smoke.runtime.to_manifest_dict() == {
        "contract_version": "v2",
        "provider": "opencodego",
        "model": "ox-alpha-free",
        "answer_transport": "chat_completions",
        "judge_transport": "chat_completions",
        "thinking_mode": "reasoning_effort_low",
    }
    assert smoke.resolved_max_workers == 1
    assert smoke.to_manifest_dict() == {
        "contract_version": "v1",
        "runtime": {
            "profile_name": "smoke",
            "contract_version": "v2",
            "provider": "opencodego",
            "model": "ox-alpha-free",
            "answer_transport": "chat_completions",
            "judge_transport": "chat_completions",
            "thinking_mode": "reasoning_effort_low",
            "request_policy": {
                "timeout_seconds": 60.0,
                "max_retries": 8,
                "retry_wait_seconds": 5.0,
                "retry_backoff_multiplier": 2.0,
                "retry_max_wait_seconds": 60.0,
            },
            "structured_output_mode": "json_object",
        },
        "execution": {
            "profile_name": "smoke",
            "default_max_workers": 1,
            "resolved_max_workers": 1,
            "worker_request_timeout_seconds": 900.0,
            "drain_timeout_seconds": 600.0,
            "task_timeout_seconds": 600.0,
            "service_startup_timeout_seconds": 60.0,
            "suppress_method_stdout": True,
        },
    }
    assert pilot.runtime == smoke.runtime.__class__(
        profile_name="pilot",
        provider="opencodego",
        model="ox-alpha-free",
        structured_output_mode="json_object",
    )
    assert calibration.runtime == smoke.runtime.__class__(
        profile_name="calibration",
        provider="opencodego",
        model="mimo-v2.5",
        structured_output_mode="json_object",
    )
    assert calibration.runtime.to_manifest_dict()["thinking_mode"] == "disabled"
    assert calibration.execution.default_max_workers == 10
    assert calibration.resolved_max_workers == 10
    assert official.runtime.provider == "primary"
    assert official.runtime.model == "gpt-4o-mini"
    assert official.execution.default_max_workers == 10
    assert official.resolved_max_workers == 1


def test_author_profile_uses_explicit_apilio_runtime_and_full_execution() -> None:
    """作者校准应锁独立 GPT runtime 与 full-size execution，不隐式降 smoke。"""

    composition = load_run_composition(
        project_root=PROJECT_ROOT,
        profile_name="author_locomo",
        method_max_workers_cap=10,
    )

    assert composition.runtime.profile_name == "author_locomo"
    assert composition.runtime.provider == "apilio"
    assert composition.runtime.model == "gpt-4o-mini"
    assert composition.runtime.to_manifest_dict()["judge_transport"] == (
        "chat_completions"
    )
    assert composition.resolved_max_workers == 10


def test_execution_default_is_not_a_parallel_cap() -> None:
    """execution default 可被显式资源选择覆盖，method 无硬上限时不截断。"""

    from dataclasses import replace

    composition = load_run_composition(
        project_root=PROJECT_ROOT,
        profile_name="smoke",
        method_max_workers_cap=None,
    )

    selected = replace(composition, resolved_max_workers=37)
    assert composition.resolved_max_workers == 1
    assert selected.resolved_max_workers == 37
    assert selected.to_manifest_dict()["execution"]["resolved_max_workers"] == 37


def test_composition_rejects_missing_or_malformed_public_config(tmp_path: Path) -> None:
    """配置文件缺失和非正 execution 并发都必须 fail-fast。"""

    with pytest.raises(ConfigurationError, match="Profile TOML file missing"):
        load_run_composition(
            project_root=tmp_path,
            profile_name="smoke",
            method_max_workers_cap=10,
        )

    runtime_path = tmp_path / "configs/runtime/api.toml"
    execution_path = tmp_path / "configs/execution/prediction.toml"
    runtime_path.parent.mkdir(parents=True)
    execution_path.parent.mkdir(parents=True)
    runtime_path.write_text(
        '[smoke]\nprovider = "opencodego"\nmodel = "ox-alpha-free"\n',
        encoding="utf-8",
    )
    execution_path.write_text(
        "[smoke]\ndefault_max_workers = 0\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="positive integer"):
        load_run_composition(
            project_root=tmp_path,
            profile_name="smoke",
            method_max_workers_cap=10,
        )
