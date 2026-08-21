"""测试 M1-A 锁定的依赖方向与兼容入口边界。"""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "memory_benchmark"


def _resolved_imports(path: Path) -> tuple[tuple[int, str], ...]:
    """返回一个 Python 文件中解析为绝对名称的 import 模块及行号。"""

    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: list[tuple[int, str]] = []
    package_parts = path.relative_to(ROOT / "src").parent.parts
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                if node.module:
                    imports.append((node.lineno, node.module))
                continue
            keep = len(package_parts) - node.level + 1
            if keep < 0:
                continue
            resolved = (*package_parts[:keep], *(node.module or "").split("."))
            module = ".".join(part for part in resolved if part)
            if module:
                imports.append((node.lineno, module))
    return tuple(imports)


def _forbidden_imports(root: Path, prefix: str) -> list[str]:
    """扫描目录并返回命中禁止前缀的稳定诊断。"""

    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        for lineno, module in _resolved_imports(path):
            if module == prefix or module.startswith(f"{prefix}."):
                relative = path.relative_to(ROOT)
                violations.append(f"{relative}:{lineno}: {module}")
    return violations


def test_runners_do_not_depend_on_cli() -> None:
    """runner/application service 不得反向 import 最外层 CLI。"""

    assert _forbidden_imports(PACKAGE / "runners", "memory_benchmark.cli") == []


def test_prompt_assets_do_not_depend_on_evaluators() -> None:
    """prompt 资产只声明稳定 key，不得保存 evaluator 执行 class。"""

    assert _forbidden_imports(
        PACKAGE / "prompts", "memory_benchmark.evaluators"
    ) == []


def test_new_run_composition_root_does_not_depend_on_legacy_config_track() -> None:
    """新 prediction 组合根不得重新引入 unified/native 双轨 resolver。"""

    path = PACKAGE / "runners" / "registered_prediction.py"
    imported = {module for _, module in _resolved_imports(path)}
    assert "memory_benchmark.methods.config_track" not in imported


def test_author_prompt_assets_have_no_internal_method_shims() -> None:
    """作者 prompt 资产的旧 methods re-export 已退出且不得复活。"""

    for stem in (
        "lightmem_native_prompts",
        "mem0_native_prompts",
        "memoryos_native_prompts",
    ):
        assert not (PACKAGE / "methods" / f"{stem}.py").exists()
        assert _forbidden_imports(
            PACKAGE,
            f"memory_benchmark.methods.{stem}",
        ) == []


def test_memoryos_dedicated_prediction_runners_do_not_return() -> None:
    """MemoryOS 新旧实验都必须走通用 prediction 入口，不得复活专用 runner。"""

    for stem in ("memoryos_locomo_full", "memoryos_locomo_smoke"):
        assert not (PACKAGE / "runners" / f"{stem}.py").exists()
        assert _forbidden_imports(
            PACKAGE,
            f"memory_benchmark.runners.{stem}",
        ) == []


def test_provider_v2_bridge_does_not_return() -> None:
    """custom 与 registered prediction 都只接受 v3，不得复活 v2 bridge。"""

    assert not (PACKAGE / "core" / "provider_bridge.py").exists()
    assert _forbidden_imports(
        PACKAGE,
        "memory_benchmark.core.provider_bridge",
    ) == []
    production_sources = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted(PACKAGE.rglob("*.py"))
    )
    assert "LegacyProviderBridge" not in production_sources
    assert "v2-bridged" not in production_sources


def test_legacy_provider_marker_stays_on_explicit_parity_surfaces() -> None:
    """退出预算内的 v2 ABC 只能标记四家已知 parity adapter。"""

    consumers: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name == "interfaces.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        if any(
            isinstance(node, ast.ImportFrom)
            and any(alias.name == "BaseMemoryProvider" for alias in node.names)
            for node in ast.walk(tree)
        ):
            consumers.append(path.relative_to(PACKAGE).as_posix())
    assert consumers == [
        "methods/amem_adapter.py",
        "methods/lightmem_adapter.py",
        "methods/mem0_adapter.py",
        "methods/memoryos_adapter.py",
    ]


def test_method_registry_factories_expose_only_v3_provider() -> None:
    """registry 作为组合根不得重新声明 legacy system/provider factory。"""

    source = (PACKAGE / "methods" / "registry.py").read_text(encoding="utf-8")
    assert "BaseMemoryProvider" not in source
    assert "BaseMemorySystem" not in source


def test_legacy_cli_prediction_module_is_canonical_module_alias() -> None:
    """旧 import 在兼容期必须返回 canonical module 本身，避免双份状态。"""

    from memory_benchmark.cli import run_prediction as legacy
    from memory_benchmark.runners import registered_prediction as canonical

    assert legacy is canonical
    assert (
        legacy.run_registered_conversation_qa_prediction
        is canonical.run_registered_conversation_qa_prediction
    )


def test_isolated_adapters_delegate_main_process_transport() -> None:
    """四家 adapter 不得重新复制 Popen/selector/stderr-thread transport。"""

    for stem in (
        "everos_adapter",
        "graphiti_adapter",
        "langmem_adapter",
        "letta_adapter",
    ):
        path = PACKAGE / "methods" / f"{stem}.py"
        source = path.read_text(encoding="utf-8")
        imports = {module for _, module in _resolved_imports(path)}
        assert "memory_benchmark.methods.worker_transport" in imports
        assert "selectors" not in imports
        assert "threading" not in imports
        assert "subprocess.Popen" not in source
        assert "threading.Thread" not in source


def test_prediction_leaf_modules_follow_one_way_dependency_order() -> None:
    """Prediction 叶模块只能依赖同层以下责任，不得反向引用 façade 或上层。"""

    module_prefix = "memory_benchmark.runners."
    allowed: dict[str, frozenset[str]] = {
        "prediction_planning": frozenset(),
        "prediction_observability": frozenset(),
        "prediction_preflight": frozenset({"prediction_planning"}),
        "prediction_ingest": frozenset(
            {"prediction_planning", "prediction_observability"}
        ),
        "prediction_answer": frozenset(
            {
                "prediction_planning",
                "prediction_preflight",
                "prediction_observability",
            }
        ),
        "prediction_parallel": frozenset(
            {
                "prediction_planning",
                "prediction_preflight",
                "prediction_ingest",
                "prediction_answer",
                "prediction_observability",
            }
        ),
    }
    for stem, expected in allowed.items():
        path = PACKAGE / "runners" / f"{stem}.py"
        actual = {
            module.removeprefix(module_prefix)
            for _, module in _resolved_imports(path)
            if module.startswith(f"{module_prefix}prediction")
        }
        assert actual == expected, stem


def test_prediction_facade_owns_only_summary_and_orchestration() -> None:
    """兼容 façade 不得重新吸回叶模块的业务实现。"""

    path = PACKAGE / "runners" / "prediction.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    definitions = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    assert definitions == {"PredictionRunSummary", "run_predictions"}


def test_prediction_facade_preserves_representative_import_identities() -> None:
    """历史 private import 在迁移期仍须指向唯一叶实现，而非复制 wrapper。"""

    from memory_benchmark.runners import prediction as facade
    from memory_benchmark.runners import prediction_answer
    from memory_benchmark.runners import prediction_ingest
    from memory_benchmark.runners import prediction_parallel
    from memory_benchmark.runners import prediction_planning
    from memory_benchmark.runners import prediction_preflight

    assert (
        facade._build_prediction_work_plan
        is prediction_planning._build_prediction_work_plan
    )
    assert (
        facade._build_prediction_resume_artifacts
        is prediction_preflight._build_prediction_resume_artifacts
    )
    assert facade._ingest_one is prediction_ingest._ingest_one
    assert (
        facade._answer_question_retrieve_first
        is prediction_answer._answer_question_retrieve_first
    )
    assert facade._isolated_worker is prediction_parallel._isolated_worker
