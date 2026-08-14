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


def test_legacy_cli_prediction_module_is_canonical_module_alias() -> None:
    """旧 import 在兼容期必须返回 canonical module 本身，避免双份状态。"""

    from memory_benchmark.cli import run_prediction as legacy
    from memory_benchmark.runners import registered_prediction as canonical

    assert legacy is canonical
    assert (
        legacy.run_registered_conversation_qa_prediction
        is canonical.run_registered_conversation_qa_prediction
    )
