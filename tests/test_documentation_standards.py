"""测试项目文档和中文代码说明是否达标。

这些测试不是业务逻辑测试，而是防止框架在快速迭代中退化成难以阅读、
难以 debug 的脚本集合。
"""

import ast
import re
import unittest
from pathlib import Path
from urllib.parse import unquote

import pytest


ROOT = Path(__file__).resolve().parents[1]
FIRST_PARTY_SOURCE = ROOT / "src" / "memory_benchmark"
TESTS_ROOT = ROOT / "tests"
LIVE_DOCUMENTS = (
    ROOT / "AGENTS.md",
    ROOT / "README.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "roadmap.md",
    ROOT / "docs" / "reference" / "architect-onboarding.md",
    ROOT / "docs" / "reference" / "architect-playbook.md",
    ROOT / "docs" / "reference" / "code-structure-principles.md",
    ROOT / "docs" / "workstreams" / "ws03-architecture-slimming" / "README.md",
    ROOT / "docs" / "workstreams" / "ws04-terminal-observability" / "README.md",
)
METHOD_INTEGRATION_DOCUMENTS = tuple(
    ROOT / "docs" / "reference" / "integration" / f"{method}.md"
    for method in (
        "amem",
        "memoryos",
        "memos",
        "lightmem",
        "simplemem",
        "mem0",
        "letta",
        "everos",
        "langmem",
        "graphiti",
    )
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


pytestmark = pytest.mark.unit


def contains_chinese(text: str | None) -> bool:
    """判断一段文本是否包含中文字符。

    参数:
        text: 待检查的字符串，允许为空。

    返回:
        bool: 只要包含一个 CJK 中文字符就返回 True。
    """

    return bool(text) and any("\u4e00" <= char <= "\u9fff" for char in text)


def python_files_requiring_docs() -> list[Path]:
    """返回需要中文说明的 Python 文件列表。

    输入:
        无。

    返回:
        list[Path]: `src/memory_benchmark/` 和 `tests/` 下的本项目 `.py` 文件。
        `third_party/` 等第三方源码不属于本项目源码规范检查范围。
    """

    files = []
    for folder in (FIRST_PARTY_SOURCE, TESTS_ROOT):
        for path in sorted(folder.rglob("*.py")):
            files.append(path)
    return files


class DocumentationStandardsTests(unittest.TestCase):
    """验证项目文档、日志结构和 Python 中文注释约定。"""

    def test_root_readme_explains_structure_and_runtime_flow(self):
        """测试根目录 README 是否解释项目层次和运转逻辑。"""

        readme = ROOT / "README.md"
        self.assertTrue(readme.exists(), "根目录必须有 README.md")
        content = readme.read_text(encoding="utf-8")

        for required_text in ("项目层次", "运转逻辑", "日志结构", "验证命令"):
            self.assertIn(required_text, content)

    def test_documentation_scanner_targets_src_and_tests_only(self):
        """测试文档规范扫描器只检查 `src/memory_benchmark` 与 `tests`。"""

        files = python_files_requiring_docs()

        self.assertTrue(FIRST_PARTY_SOURCE.is_dir(), "src/memory_benchmark 必须存在")
        self.assertTrue(TESTS_ROOT.is_dir(), "tests 目录必须存在")
        self.assertGreater(len(files), 0)
        self.assertTrue(all(path.is_relative_to(FIRST_PARTY_SOURCE) or path.is_relative_to(TESTS_ROOT) for path in files))

    def test_archived_log_readme_keeps_naming_convention(self):
        """测试归档日志说明是否保留位置说明和命名规范。"""

        log_readme = ROOT / "docs" / "archive" / "logs" / "README.md"
        self.assertTrue(log_readme.exists(), "日志规范必须保留在 docs/archive/logs/README.md")
        content = log_readme.read_text(encoding="utf-8")

        self.assertIn("YYYY-MM-DD", content)
        self.assertIn("phase", content)
        self.assertIn("project-log", content)

    def test_live_document_relative_links_resolve(self):
        """热入口的本地相对链接必须存在，archive 不纳入本批无边界扫描。"""

        missing: list[str] = []
        for document in LIVE_DOCUMENTS:
            self.assertTrue(document.is_file(), f"live document missing: {document}")
            text = document.read_text(encoding="utf-8")
            for raw_target in MARKDOWN_LINK.findall(text):
                target = raw_target.strip().strip("<>")
                if target.startswith(("http://", "https://", "mailto:", "#")):
                    continue
                relative = unquote(target.split("#", 1)[0])
                if not relative:
                    continue
                resolved = (document.parent / relative).resolve()
                if not resolved.exists():
                    missing.append(
                        f"{document.relative_to(ROOT)} -> {target}"
                    )
        self.assertEqual(missing, [])

    def test_every_method_integration_page_documents_product_call_contract(self):
        """十家稳定页都必须记录产品参数、返回与 batch 语义并链接接口总账。"""

        inventory = ROOT / "docs" / "reference" / "method-interface-inventory.md"
        self.assertTrue(inventory.is_file())
        inventory_text = inventory.read_text(encoding="utf-8")

        for document in METHOD_INTEGRATION_DOCUMENTS:
            self.assertTrue(document.is_file(), f"method integration missing: {document}")
            content = document.read_text(encoding="utf-8")
            self.assertIn("## 产品接口契约（参数、返回与批次）", content)
            self.assertIn("../method-interface-inventory.md", content)
            self.assertIn(f"integration/{document.name}", inventory_text)

    def test_every_python_module_has_chinese_module_docstring(self):
        """测试每个 Python 文件顶端是否有中文模块说明。"""

        missing = []
        for path in python_files_requiring_docs():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if not contains_chinese(ast.get_docstring(tree)):
                missing.append(str(path.relative_to(ROOT)))

        self.assertEqual(missing, [])

    def test_every_class_and_function_has_chinese_docstring(self):
        """测试每个类、函数和测试函数是否有中文说明。"""

        missing = []
        for path in python_files_requiring_docs():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not contains_chinese(ast.get_docstring(node)):
                        location = f"{path.relative_to(ROOT)}::{node.name}"
                        missing.append(location)

        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
