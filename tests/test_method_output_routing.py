"""测试 in-process method 的窄 stdout/stderr 诊断路由。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from memory_benchmark.methods.amem_adapter import AMem
from memory_benchmark.methods.lightmem_adapter import LightMem
from memory_benchmark.methods.memoryos_adapter import MemoryOS


pytestmark = pytest.mark.unit


def _noisy_call() -> str:
    """模拟同时向 stdout/stderr 输出 secret 的第三方调用。"""

    print("stdout sk-private")
    print("stderr https://private.example/v1", file=sys.stderr)
    return "ok"


def _assert_redacted_output(log_path: Path) -> None:
    """断言完整输出已落盘且受保护值没有泄露。"""

    content = log_path.read_text(encoding="utf-8")
    assert "stdout <redacted>" in content
    assert "stderr <redacted>" in content
    assert "sk-private" not in content
    assert "https://private.example/v1" not in content


def test_lightmem_suppressed_output_is_redacted_and_persisted(tmp_path: Path) -> None:
    """LightMem 原有窄调用边界不再静默丢弃第三方输出。"""

    provider = object.__new__(LightMem)
    provider.config = SimpleNamespace(suppress_official_stdout=True)
    provider._openai_settings = SimpleNamespace(
        api_key="sk-private",
        base_url="https://private.example/v1",
    )
    provider._diagnostic_log_path = tmp_path / "lightmem.log"

    assert provider._suppress_stdout_if_needed(_noisy_call) == "ok"

    _assert_redacted_output(provider._diagnostic_log_path)


def test_amem_suppressed_output_is_redacted_and_persisted(tmp_path: Path) -> None:
    """A-Mem 的 key/base URL 只用于脱敏，不得写入诊断日志。"""

    provider = object.__new__(AMem)
    provider.config = SimpleNamespace(suppress_official_stdout=True)
    provider._openai_api_key = "sk-private"
    provider._openai_base_url = "https://private.example/v1"
    provider._diagnostic_log_path = tmp_path / "amem.log"

    assert provider._suppress_stdout_if_needed(_noisy_call) == "ok"

    _assert_redacted_output(provider._diagnostic_log_path)


def test_memoryos_context_output_is_redacted_and_persisted(tmp_path: Path) -> None:
    """MemoryOS contextmanager 路径应覆盖真实 backend 调用形状。"""

    provider = object.__new__(MemoryOS)
    provider.config = SimpleNamespace(suppress_official_stdout=True)
    provider.openai_api_key = "sk-private"
    provider.openai_base_url = "https://private.example/v1"
    provider._diagnostic_log_path = tmp_path / "memoryos.log"

    with provider._suppress_stdout_if_needed():
        assert _noisy_call() == "ok"

    _assert_redacted_output(provider._diagnostic_log_path)
