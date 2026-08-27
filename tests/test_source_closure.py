"""method 新 run 的确定性源码闭包、组件边界与反例。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.config import load_path_settings
from memory_benchmark.core import ConfigurationError
import memory_benchmark.methods.source_closure as source_closure
from memory_benchmark.methods.source_closure import (
    MethodSourceRecipe,
    SOURCE_CLOSURE_SCHEMA_VERSION,
    SourceComponentRecipe,
    build_registered_method_source_identity,
)


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]
METHODS = (
    "lightmem",
    "amem",
    "mem0",
    "memoryos",
    "memos",
    "simplemem",
    "letta",
    "langmem",
    "everos",
    "graphiti",
)
EXPECTED_COMPONENT_COUNTS = {
    "lightmem": {
        "product_algorithm": 63,
        "package_metadata": 1,
        "framework_runtime": 1,
        "author_eval": 6,
    },
    "amem": {
        "product_algorithm": 4,
        "package_metadata": 1,
        "runtime_lock": 1,
        "framework_runtime": 1,
    },
    "mem0": {
        "product_algorithm": 142,
        "package_metadata": 1,
        "runtime_lock": 1,
        "framework_runtime": 1,
        "author_eval": 4,
    },
    "memoryos": {
        "product_algorithm": 9,
        "runtime_lock": 1,
        "framework_runtime": 1,
        "author_eval": 1,
    },
    "memos": {
        "product_algorithm": 380,
        "package_metadata": 1,
        "runtime_lock": 1,
        "framework_runtime": 3,
    },
    "simplemem": {
        "product_algorithm": 16,
        "package_metadata": 1,
        "runtime_lock": 1,
        "framework_runtime": 2,
    },
    "letta": {
        "product_algorithm": 536,
        "runtime_asset": 1,
        "package_metadata": 1,
        "runtime_lock": 1,
        "framework_runtime": 4,
    },
    "langmem": {
        "product_algorithm": 24,
        "package_metadata": 1,
        "runtime_lock": 1,
        "framework_runtime": 5,
    },
    "everos": {
        "product_algorithm": 283,
        "runtime_asset": 4,
        "package_metadata": 1,
        "runtime_lock": 1,
        "framework_runtime": 7,
    },
    "graphiti": {
        "product_algorithm": 159,
        "package_metadata": 1,
        "runtime_lock": 1,
        "framework_runtime": 4,
    },
}


def test_current_method_source_closures_are_componentized_and_portable() -> None:
    """十家新 run 都应锁 product/framework/必要资产且不泄漏绝对路径。"""

    settings = load_path_settings(project_root=PROJECT_ROOT)
    identities = {
        name: build_registered_method_source_identity(name, settings)
        for name in METHODS
    }

    for name, identity in identities.items():
        assert identity["closure_schema_version"] == SOURCE_CLOSURE_SCHEMA_VERSION
        assert identity["source_mode"] == "deterministic-component-closure"
        assert identity["file_count"] == len(identity["files"])
        assert len(identity["source_sha256"]) == 64
        assert "product_algorithm" in identity["components"], name
        assert "framework_runtime" in identity["components"], name
        assert all(not Path(path).is_absolute() for path in identity["files"])
        assert all("__pycache__" not in path for path in identity["files"])
        assert all(not path.lower().endswith(".pdf") for path in identity["files"])
        assert {
            component: payload["file_count"]
            for component, payload in identity["components"].items()
        } == EXPECTED_COMPONENT_COUNTS[name]

    assert not any(
        path.endswith("memoryos-pypi/test.py")
        for path in identities["memoryos"]["files"]
    )
    assert not any(
        "tests/evals" in path for path in identities["graphiti"]["files"]
    )
    assert identities["letta"]["external_dependencies"] == {
        "ai-memory-sdk": (
            "v0.2.0@4494e00410469082bf298b8b03b7c9f93e244f14:source-unavailable"
        )
    }
    assert "author_eval" in identities["mem0"]["components"]
    assert "author_eval" in identities["lightmem"]["components"]


def test_source_closure_digest_changes_only_after_declared_file_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """声明文件的 bytes 变化必须改变组件与总 identity。"""

    (tmp_path / "pkg").mkdir()
    product = tmp_path / "pkg" / "algorithm.py"
    wrapper = tmp_path / "wrapper.py"
    product.write_text("VALUE = 1\n", encoding="utf-8")
    wrapper.write_text("def wrap():\n    return 1\n", encoding="utf-8")
    monkeypatch.setitem(
        source_closure._RECIPES,
        "probe",
        MethodSourceRecipe(
            recipe_id="probe-v1",
            components=(
                SourceComponentRecipe("product_algorithm", ("pkg/**/*.py",)),
                SourceComponentRecipe("framework_runtime", ("wrapper.py",)),
            ),
        ),
    )
    settings = load_path_settings(project_root=tmp_path)
    before = build_registered_method_source_identity("probe", settings)
    product.write_text("VALUE = 2\n", encoding="utf-8")
    after = build_registered_method_source_identity("probe", settings)

    assert before["source_sha256"] != after["source_sha256"]
    assert (
        before["components"]["product_algorithm"]["sha256"]
        != after["components"]["product_algorithm"]["sha256"]
    )
    assert (
        before["components"]["framework_runtime"]["sha256"]
        == after["components"]["framework_runtime"]["sha256"]
    )


def test_source_closure_rejects_symlink_missing_and_overlapping_patterns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """symlink、空 pattern 与一个文件跨组件都不得静默进入身份。"""

    (tmp_path / "pkg").mkdir()
    real = tmp_path / "real.py"
    real.write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pkg" / "alias.py").symlink_to(real)
    settings = load_path_settings(project_root=tmp_path)

    monkeypatch.setitem(
        source_closure._RECIPES,
        "probe",
        MethodSourceRecipe(
            recipe_id="probe-v1",
            components=(
                SourceComponentRecipe("product_algorithm", ("pkg/*.py",)),
            ),
        ),
    )
    with pytest.raises(ConfigurationError, match="symlink"):
        build_registered_method_source_identity("probe", settings)

    monkeypatch.setitem(
        source_closure._RECIPES,
        "probe",
        MethodSourceRecipe(
            recipe_id="probe-v1",
            components=(
                SourceComponentRecipe("product_algorithm", ("missing/*.py",)),
            ),
        ),
    )
    with pytest.raises(ConfigurationError, match="matched no files"):
        build_registered_method_source_identity("probe", settings)

    monkeypatch.setitem(
        source_closure._RECIPES,
        "probe",
        MethodSourceRecipe(
            recipe_id="probe-v1",
            components=(
                SourceComponentRecipe("product_algorithm", ("real.py",)),
                SourceComponentRecipe("framework_runtime", ("real.py",)),
            ),
        ),
    )
    with pytest.raises(ConfigurationError, match="multiple components"):
        build_registered_method_source_identity("probe", settings)
