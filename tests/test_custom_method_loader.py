"""测试用户自定义 method 的轻量加载入口。

本模块只验证 `--method-class module:ClassName` 底层 loader，不触碰内置 method
registry、TOML 或真实 API。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import MemoryProvider
from memory_benchmark.methods.custom_loader import load_custom_memory_provider_class


pytestmark = pytest.mark.unit


def _write_module(tmp_path: Path, source: str) -> str:
    """写入一个临时 Python module，并返回 importable module 名。

    输入:
        tmp_path: pytest 提供的临时目录。
        source: 要写入临时 module 的 Python 源码。

    输出:
        str: 可被 import 的 module 名称。
    """

    module_path = tmp_path / "custom_adapter.py"
    module_path.write_text(source, encoding="utf-8")
    sys.modules.pop("custom_adapter", None)
    sys.path.insert(0, str(tmp_path))
    return "custom_adapter"


def test_load_custom_memory_provider_class_accepts_v3_no_arg_class(
    tmp_path: Path,
) -> None:
    """合法用户 adapter 须无参构造、继承 MemoryProvider 并声明粒度。"""

    module_name = _write_module(
        tmp_path,
        '''
from memory_benchmark.core.provider_protocol import (
    IngestResult,
    MemoryProvider,
    RetrievalResult,
)


class MyMemory(MemoryProvider):
    consume_granularity = "turn"

    def ingest(self, unit):
        return IngestResult()

    def retrieve(self, query):
        return RetrievalResult(formatted_memory="memory")
''',
    )

    provider_class = load_custom_memory_provider_class(f"{module_name}:MyMemory")

    assert issubclass(provider_class, MemoryProvider)
    assert provider_class.consume_granularity == "turn"


def test_load_custom_memory_provider_rejects_missing_colon() -> None:
    """class path 必须是 module:ClassName，避免用户传入含糊路径。"""

    with pytest.raises(ConfigurationError, match="module:ClassName"):
        load_custom_memory_provider_class("custom_adapter.MyMemory")


def test_load_custom_memory_provider_rejects_constructor_args(
    tmp_path: Path,
) -> None:
    """第一版用户 adapter 必须能无参数构造。"""

    module_name = _write_module(
        tmp_path,
        '''
from memory_benchmark.core.provider_protocol import MemoryProvider


class NeedsArgs(MemoryProvider):
    consume_granularity = "turn"

    def __init__(self, path):
        self.path = path

    def ingest(self, unit):
        raise NotImplementedError

    def retrieve(self, query):
        raise NotImplementedError
''',
    )

    with pytest.raises(ConfigurationError, match="no-argument constructor"):
        load_custom_memory_provider_class(f"{module_name}:NeedsArgs")


def test_load_custom_memory_provider_rejects_wrong_base_class(
    tmp_path: Path,
) -> None:
    """用户传入的类必须实现 provider v3 MemoryProvider。"""

    module_name = _write_module(
        tmp_path,
        '''
class NotMemory:
    pass
''',
    )

    with pytest.raises(ConfigurationError, match="MemoryProvider"):
        load_custom_memory_provider_class(f"{module_name}:NotMemory")


def test_load_custom_memory_provider_class_rejects_missing_granularity(
    tmp_path: Path,
) -> None:
    """v3 custom provider 必须显式声明事件流消费粒度。"""

    module_name = _write_module(
        tmp_path,
        '''
from memory_benchmark.core.provider_protocol import MemoryProvider


class MissingGranularity(MemoryProvider):
    def ingest(self, unit):
        raise NotImplementedError

    def retrieve(self, query):
        raise NotImplementedError
''',
    )

    with pytest.raises(ConfigurationError, match="consume_granularity"):
        load_custom_memory_provider_class(f"{module_name}:MissingGranularity")
