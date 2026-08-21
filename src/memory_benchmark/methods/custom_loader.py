"""用户自定义 provider v3 的轻量加载工具。

该模块只服务普通用户接入路径：通过 ``module:ClassName`` import 一个无参构造的
``MemoryProvider`` 子类。内置 method 仍走 registry/TOML 深度集成路径。
"""

from __future__ import annotations

from importlib import import_module
from inspect import isabstract, signature
from typing import Any

from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import MemoryProvider


def load_custom_memory_provider_class(class_path: str) -> type[MemoryProvider]:
    """加载并校验用户自定义 ``MemoryProvider`` class。

    输入:
        class_path: `module:ClassName` 格式，例如 `my_pkg.my_adapter:MyMemory`。

    输出:
        type[MemoryProvider]: 已验证协议、构造器和消费粒度的 provider class。

    说明:
        这里只加载 class，不创建一次性“探针实例”。真实实例只由 prediction 的
        composition root 按 run/worker 生命周期构造，避免校验阶段提前连接数据库或
        分配模型资源。
    """

    module_name, class_name = _split_class_path(class_path)
    try:
        module = import_module(module_name)
    except Exception as exc:
        raise ConfigurationError(
            f"Cannot import custom method module '{module_name}': {exc}"
        ) from exc
    try:
        cls = getattr(module, class_name)
    except AttributeError as exc:
        raise ConfigurationError(
            f"Custom method class '{class_name}' was not found in '{module_name}'"
        ) from exc
    if not isinstance(cls, type) or not issubclass(cls, MemoryProvider):
        raise ConfigurationError(
            f"Custom method '{class_path}' must inherit MemoryProvider"
        )
    if isabstract(cls):
        raise ConfigurationError(
            f"Custom method '{class_path}' must implement ingest() and retrieve()"
        )
    try:
        signature(cls).bind()
    except TypeError as exc:
        raise ConfigurationError(
            f"Custom method '{class_path}' must provide a no-argument constructor"
        ) from exc
    consume_granularity: Any = getattr(cls, "consume_granularity", None)
    if consume_granularity not in {"turn", "pair", "session", "conversation"}:
        raise ConfigurationError(
            f"Custom method '{class_path}' must declare consume_granularity as "
            "turn, pair, session or conversation"
        )
    provenance_granularity: Any = getattr(cls, "provenance_granularity", "none")
    if provenance_granularity not in {"none", "session", "turn"}:
        raise ConfigurationError(
            f"Custom method '{class_path}' must declare provenance_granularity as "
            "none, session or turn"
        )
    return cls


def _split_class_path(class_path: str) -> tuple[str, str]:
    """解析 `module:ClassName`，并给出明确错误信息。

    输入:
        class_path: 用户传入的 class path。

    输出:
        tuple[str, str]: module 名称和 class 名称。
    """

    if ":" not in class_path:
        raise ConfigurationError(
            "Custom method class must use 'module:ClassName' format"
        )
    module_name, class_name = class_path.split(":", 1)
    if not module_name.strip() or not class_name.strip():
        raise ConfigurationError(
            "Custom method class must use 'module:ClassName' format"
        )
    return module_name.strip(), class_name.strip()


__all__ = ["load_custom_memory_provider_class"]
