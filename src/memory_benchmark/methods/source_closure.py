"""十家 method 新 run 使用的确定性源码闭包与组件身份。"""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from hashlib import sha256
import json
from pathlib import Path
import stat
from typing import Any
import unicodedata

from memory_benchmark.config import PathSettings
from memory_benchmark.core import ConfigurationError


SOURCE_CLOSURE_SCHEMA_VERSION = "method-source-closure-v2"


@dataclass(frozen=True)
class SourceComponentRecipe:
    """一个源码组件的 include/exclude 选择规则。"""

    name: str
    include_globs: tuple[str, ...]
    exclude_globs: tuple[str, ...] = ()


@dataclass(frozen=True)
class MethodSourceRecipe:
    """一个 method 的 product/framework/lock/author 组件配方。"""

    recipe_id: str
    components: tuple[SourceComponentRecipe, ...]
    external_dependencies: tuple[tuple[str, str], ...] = ()


def _component(
    name: str,
    *patterns: str,
    exclude: tuple[str, ...] = (),
) -> SourceComponentRecipe:
    """用紧凑语法构造组件配方。"""

    return SourceComponentRecipe(
        name=name,
        include_globs=tuple(patterns),
        exclude_globs=exclude,
    )


_RECIPES: dict[str, MethodSourceRecipe] = {
    "lightmem": MethodSourceRecipe(
        recipe_id="lightmem-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/LightMem/src/lightmem/__init__.py",
                "third_party/methods/LightMem/src/lightmem/configs/**/*.py",
                "third_party/methods/LightMem/src/lightmem/factory/**/*.py",
                "third_party/methods/LightMem/src/lightmem/memory/**/*.py",
            ),
            _component(
                "package_metadata",
                "third_party/methods/LightMem/pyproject.toml",
            ),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/lightmem_adapter.py",
            ),
            _component(
                "author_eval",
                "third_party/methods/LightMem/experiments/locomo/add_locomo.py",
                "third_party/methods/LightMem/experiments/locomo/search_locomo.py",
                "third_party/methods/LightMem/experiments/locomo/prompts.py",
                "third_party/methods/LightMem/experiments/longmemeval/run_lightmem_gpt.py",
                "src/memory_benchmark/prompts/author/lightmem.py",
            ),
        ),
    ),
    "amem": MethodSourceRecipe(
        recipe_id="amem-product-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/A-mem-product/agentic_memory/**/*.py",
            ),
            _component(
                "package_metadata",
                "third_party/methods/A-mem-product/pyproject.toml",
            ),
            _component(
                "runtime_lock",
                "third_party/methods/A-mem-product/requirements.txt",
            ),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/amem_adapter.py",
            ),
        ),
    ),
    "mem0": MethodSourceRecipe(
        recipe_id="mem0-product-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/mem0-main/mem0/**/*.py",
            ),
            _component(
                "package_metadata",
                "third_party/methods/mem0-main/pyproject.toml",
            ),
            _component(
                "runtime_lock",
                "third_party/methods/mem0-main/poetry.lock",
            ),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/mem0_adapter.py",
            ),
            _component(
                "author_eval",
                "third_party/methods/mem0-main/memory-benchmarks/benchmarks/locomo/prompts.py",
                "third_party/methods/mem0-main/memory-benchmarks/benchmarks/longmemeval/prompts.py",
                "third_party/methods/mem0-main/memory-benchmarks/benchmarks/beam/prompts.py",
                "src/memory_benchmark/prompts/author/mem0.py",
            ),
        ),
    ),
    "memoryos": MethodSourceRecipe(
        recipe_id="memoryos-pypi-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/MemoryOS-main/memoryos-pypi/*.py",
                exclude=(
                    "third_party/methods/MemoryOS-main/memoryos-pypi/test.py",
                ),
            ),
            _component(
                "runtime_lock",
                "third_party/methods/MemoryOS-main/memoryos-pypi/requirements.txt",
            ),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/memoryos_adapter.py",
            ),
            _component(
                "author_eval",
                "src/memory_benchmark/prompts/author/memoryos.py",
            ),
        ),
    ),
    "memos": MethodSourceRecipe(
        recipe_id="memos-product-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/MemOS/src/memos/**/*.py",
            ),
            _component(
                "package_metadata",
                "third_party/methods/MemOS/pyproject.toml",
            ),
            _component("runtime_lock", "third_party/methods/MemOS/uv.lock"),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/memos_adapter.py",
                "src/memory_benchmark/methods/memos_lifecycle.py",
                "scripts/patches/memos-product-runtime-observability.patch",
            ),
        ),
    ),
    "simplemem": MethodSourceRecipe(
        recipe_id="simplemem-text-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/SimpleMem/main.py",
                "third_party/methods/SimpleMem/simplemem/__init__.py",
                "third_party/methods/SimpleMem/simplemem/router.py",
                "third_party/methods/SimpleMem/simplemem/config.py",
                "third_party/methods/SimpleMem/simplemem/core/**/*.py",
                exclude=(
                    "third_party/methods/SimpleMem/simplemem/core/config_default.py",
                ),
            ),
            _component(
                "package_metadata",
                "third_party/methods/SimpleMem/setup.py",
            ),
            _component(
                "runtime_lock",
                "third_party/methods/SimpleMem/requirements.txt",
            ),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/simplemem_adapter.py",
                "scripts/patches/simplemem-product-compat.patch",
            ),
        ),
    ),
    "letta": MethodSourceRecipe(
        recipe_id="letta-sleeptime-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/letta/letta/**/*.py",
            ),
            _component(
                "runtime_asset",
                "third_party/methods/letta/letta/model_specs/model_prices_and_context_window.json",
            ),
            _component(
                "package_metadata",
                "third_party/methods/letta/pyproject.toml",
            ),
            _component("runtime_lock", "third_party/methods/letta/uv.lock"),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/letta_adapter.py",
                "src/memory_benchmark/methods/letta_worker.py",
                "src/memory_benchmark/methods/worker_transport.py",
                "scripts/bootstrap_letta_runtime.sh",
            ),
        ),
        external_dependencies=(
            ("ai-memory-sdk", "v0.2.0@4494e00410469082bf298b8b03b7c9f93e244f14:source-unavailable"),
        ),
    ),
    "langmem": MethodSourceRecipe(
        recipe_id="langmem-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/langmem/src/langmem/**/*.py",
            ),
            _component(
                "package_metadata",
                "third_party/methods/langmem/pyproject.toml",
            ),
            _component("runtime_lock", "third_party/methods/langmem/uv.lock"),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/langmem_adapter.py",
                "src/memory_benchmark/methods/langmem_worker.py",
                "src/memory_benchmark/methods/worker_transport.py",
                "scripts/bootstrap_langmem_runtime.sh",
                "scripts/requirements/langmem-runtime.txt",
            ),
        ),
    ),
    "everos": MethodSourceRecipe(
        recipe_id="everos-api-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/EverOS/src/everos/__init__.py",
                "third_party/methods/EverOS/src/everos/component/**/*.py",
                "third_party/methods/EverOS/src/everos/config/**/*.py",
                "third_party/methods/EverOS/src/everos/core/**/*.py",
                "third_party/methods/EverOS/src/everos/entrypoints/api/**/*.py",
                "third_party/methods/EverOS/src/everos/infra/**/*.py",
                "third_party/methods/EverOS/src/everos/memory/**/*.py",
                "third_party/methods/EverOS/src/everos/service/**/*.py",
            ),
            _component(
                "runtime_asset",
                "third_party/methods/EverOS/src/everos/config/default.toml",
                "third_party/methods/EverOS/src/everos/config/default_ome.toml",
                "third_party/methods/EverOS/src/everos/config/prompt_slots/*.yaml",
            ),
            _component(
                "package_metadata",
                "third_party/methods/EverOS/pyproject.toml",
            ),
            _component("runtime_lock", "third_party/methods/EverOS/uv.lock"),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/everos_adapter.py",
                "src/memory_benchmark/methods/everos_worker.py",
                "src/memory_benchmark/methods/worker_transport.py",
                "scripts/bootstrap_everos_runtime.sh",
                "scripts/patches/everos-configured-embedding-dimension.patch",
                "scripts/patches/everos-product-runtime-observability.patch",
                "scripts/requirements/everos-controlled-embedding.txt",
            ),
        ),
    ),
    "graphiti": MethodSourceRecipe(
        recipe_id="graphiti-oss-main-v2",
        components=(
            _component(
                "product_algorithm",
                "third_party/methods/graphiti/graphiti_core/**/*.py",
                "third_party/methods/graphiti/graphiti_core/py.typed",
            ),
            _component(
                "package_metadata",
                "third_party/methods/graphiti/pyproject.toml",
            ),
            _component("runtime_lock", "third_party/methods/graphiti/uv.lock"),
            _component(
                "framework_runtime",
                "src/memory_benchmark/methods/graphiti_adapter.py",
                "src/memory_benchmark/methods/graphiti_worker.py",
                "src/memory_benchmark/methods/worker_transport.py",
                "scripts/bootstrap_graphiti_runtime.sh",
            ),
        ),
    ),
}


def _assert_no_symlink_components(root: Path, relative: Path) -> None:
    """拒绝闭包路径任何一层 symlink。"""

    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ConfigurationError(
                f"method source closure path contains symlink: {relative.as_posix()}"
            )


def _read_stable_regular_file(root: Path, relative: Path) -> bytes:
    """读取项目内稳定普通文件并执行 TOCTOU 守门。"""

    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError(
            f"method source closure path must be project-relative: {relative}"
        )
    _assert_no_symlink_components(root, relative)
    path = root / relative
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ConfigurationError(
            f"method source closure path escaped project root: {relative}"
        ) from exc
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        raise ConfigurationError(
            f"method source closure requires a regular file: {relative}"
        )
    payload = path.read_bytes()
    after = path.stat()
    if (
        before.st_dev != after.st_dev
        or before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(payload) != after.st_size
    ):
        raise ConfigurationError(
            f"method source closure file changed while hashing: {relative}"
        )
    return payload


def _digest_files(root: Path, relatives: tuple[Path, ...]) -> str:
    """按项目相对 POSIX 路径与原始 bytes 生成确定性 digest。"""

    digest = sha256()
    for relative in relatives:
        path_bytes = relative.as_posix().encode("utf-8")
        payload = _read_stable_regular_file(root, relative)
        digest.update(len(path_bytes).to_bytes(8, "big"))
        digest.update(path_bytes)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _select_component_files(
    root: Path,
    component: SourceComponentRecipe,
) -> tuple[Path, ...]:
    """展开单个组件的 glob，拒绝空 pattern、重复与可移植路径碰撞。"""

    selected: list[Path] = []
    for pattern in component.include_globs:
        if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ConfigurationError(
                f"invalid source closure include pattern: {pattern}"
            )
        matches = [
            path
            for path in root.glob(pattern)
            if path.is_file()
            and not any(
                fnmatch(path.relative_to(root).as_posix(), excluded)
                for excluded in component.exclude_globs
            )
        ]
        if not matches:
            raise ConfigurationError(
                "method source closure include pattern matched no files: "
                f"{component.name}:{pattern}"
            )
        selected.extend(path.relative_to(root) for path in matches)
    ordered = tuple(sorted(selected, key=lambda path: path.as_posix().encode("utf-8")))
    if len(ordered) != len(set(ordered)):
        raise ConfigurationError(
            f"method source closure component has overlapping patterns: {component.name}"
        )
    portable = tuple(
        unicodedata.normalize("NFC", path.as_posix()).casefold()
        for path in ordered
    )
    if len(portable) != len(set(portable)):
        raise ConfigurationError(
            f"method source closure component has portable path collisions: {component.name}"
        )
    return ordered


def build_registered_method_source_identity(
    method_name: str,
    path_settings: PathSettings,
) -> dict[str, Any]:
    """生成新 run 使用的完整、分组件、无绝对路径 source identity。"""

    try:
        recipe = _RECIPES[method_name]
    except KeyError as exc:
        raise ConfigurationError(
            f"no deterministic source closure recipe registered for {method_name!r}"
        ) from exc
    declared_root = path_settings.project_root.expanduser().absolute()
    if declared_root.is_symlink() or not declared_root.is_dir():
        raise ConfigurationError("method source closure project root is invalid")
    root = declared_root.resolve()
    components: dict[str, dict[str, Any]] = {}
    all_files: list[Path] = []
    for component in recipe.components:
        if component.name in components:
            raise ConfigurationError(
                f"duplicate method source component name: {component.name}"
            )
        files = _select_component_files(root, component)
        overlap = sorted(set(files).intersection(all_files), key=lambda p: p.as_posix())
        if overlap:
            raise ConfigurationError(
                "method source closure file belongs to multiple components: "
                f"{[path.as_posix() for path in overlap]}"
            )
        all_files.extend(files)
        components[component.name] = {
            "file_count": len(files),
            "sha256": _digest_files(root, files),
            "files": [path.as_posix() for path in files],
        }
    if not all_files:
        raise ConfigurationError("method source closure cannot be empty")
    all_ordered = tuple(
        sorted(all_files, key=lambda path: path.as_posix().encode("utf-8"))
    )
    external = {name: identity for name, identity in recipe.external_dependencies}
    aggregate_payload = {
        "closure_schema_version": SOURCE_CLOSURE_SCHEMA_VERSION,
        "recipe_id": recipe.recipe_id,
        "components": {
            name: {
                "file_count": payload["file_count"],
                "sha256": payload["sha256"],
            }
            for name, payload in sorted(components.items())
        },
        "external_dependencies": external,
    }
    source_sha256 = sha256(
        json.dumps(
            aggregate_payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()
    return {
        "source_mode": "deterministic-component-closure",
        "closure_schema_version": SOURCE_CLOSURE_SCHEMA_VERSION,
        "recipe_id": recipe.recipe_id,
        "source_sha256": source_sha256,
        "file_count": len(all_ordered),
        "files": [path.as_posix() for path in all_ordered],
        "components": components,
        "external_dependencies": external,
    }


__all__ = [
    "MethodSourceRecipe",
    "SOURCE_CLOSURE_SCHEMA_VERSION",
    "SourceComponentRecipe",
    "build_registered_method_source_identity",
]
