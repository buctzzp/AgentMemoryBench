"""受控本地 embedding 模型的路径、内容闭包与 tokenizer 身份。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
from typing import Any, Iterable
import unicodedata

from memory_benchmark.core import ConfigurationError


LOCAL_MINILM_LOGICAL_PATH = "models/all-MiniLM-L6-v2"
LOCAL_EMBEDDING_CLOSURE_SCHEMA_VERSION = "length-prefixed-files-v1"
LOCAL_MINILM_CLOSURE_FILES = (
    "1_Pooling/config.json",
    "config.json",
    "config_sentence_transformers.json",
    "model.safetensors",
    "modules.json",
    "sentence_bert_config.json",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)
LOCAL_MINILM_TOKENIZER_FILES = (
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.txt",
)


@dataclass(frozen=True)
class LocalEmbeddingAssetReceipt:
    """一次本地 SentenceTransformer 资产闭包的可公开收据。"""

    logical_path: str
    local_content_sha256: str
    tokenizer_sha256: str
    tokenizer_name: str
    tokenizer_max_length: int
    tokenizer_lowercase: bool
    dimension: int
    model_pipeline: tuple[str, ...]
    sentence_transformers_version: str
    transformers_version: str


def resolve_project_local_embedding_path(
    reference: str,
    project_root: Path,
) -> Path:
    """解析 `models/...` 逻辑路径并拒绝绝对路径、逃逸与 symlink。"""

    if type(reference) is not str or not reference.strip():
        raise ConfigurationError("local embedding model reference is required")
    if "\x00" in reference:
        raise ConfigurationError(
            "local embedding model reference must not contain NUL bytes"
        )
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        raise ConfigurationError(
            "local embedding model reference must be a project-relative models/... path"
        )
    normalized = relative.as_posix()
    if not normalized.startswith("models/"):
        raise ConfigurationError(
            "local embedding model reference must start with 'models/'"
        )
    root = project_root.expanduser().absolute()
    if root.is_symlink() or not root.is_dir():
        raise ConfigurationError(
            "project root for local embedding must be a real directory"
        )
    models_root = root / "models"
    model_path = root / relative
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ConfigurationError(
                "local embedding path must not contain symlink components"
            )
    resolved_models_root = models_root.resolve()
    resolved = model_path.resolve()
    try:
        resolved.relative_to(resolved_models_root)
    except ValueError as exc:
        raise ConfigurationError("local embedding model escaped models_root") from exc
    if not resolved.is_dir():
        raise ConfigurationError(f"local embedding model directory missing: {reference}")
    return resolved


def resolve_embedding_runtime_model_reference(
    reference: str,
    project_root: Path,
) -> str:
    """把受控 ``models/...`` 逻辑路径转成产品可消费的绝对路径。

    非项目本地引用（例如作者 profile 的 Hub model id）保持原字节值；因此 manifest
    继续保存逻辑身份，只有第三方产品构造边界看到绝对路径。
    """

    if type(reference) is not str or not reference.strip():
        raise ConfigurationError("embedding model reference is required")
    if reference.startswith("models/"):
        return str(resolve_project_local_embedding_path(reference, project_root))
    return reference


def _canonical_files_digest(root: Path, relative_paths: Iterable[str]) -> str:
    """按 POSIX 路径与原始 bytes 的 uint64 大端长度前缀计算 SHA-256。"""

    raw_paths = tuple(relative_paths)
    if not raw_paths:
        raise ConfigurationError("embedding closure file list must be non-empty")
    canonical_paths: list[str] = []
    for relative_text in raw_paths:
        if type(relative_text) is not str or not relative_text.strip():
            raise ConfigurationError(
                "embedding closure paths must be non-blank strings"
            )
        if "\x00" in relative_text:
            raise ConfigurationError(
                "embedding closure paths must not contain NUL bytes"
            )
        relative = Path(relative_text)
        if relative.is_absolute() or ".." in relative.parts:
            raise ConfigurationError(
                f"embedding closure path must be relative: {relative_text}"
            )
        canonical = relative.as_posix()
        if canonical in {"", "."}:
            raise ConfigurationError(
                f"embedding closure path must name a file: {relative_text}"
            )
        canonical_paths.append(canonical)
    paths = tuple(sorted(canonical_paths))
    if len(paths) != len(set(paths)):
        raise ConfigurationError("embedding closure file list must be non-empty and unique")
    portable_keys = tuple(
        unicodedata.normalize("NFC", path).casefold() for path in paths
    )
    if len(portable_keys) != len(set(portable_keys)):
        raise ConfigurationError(
            "embedding closure paths collide after Unicode/case normalization"
        )
    digest = sha256()
    for relative_text in paths:
        relative = Path(relative_text)
        path = root / relative
        current = root
        if root.is_symlink():
            raise ConfigurationError("embedding closure root must not be a symlink")
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise ConfigurationError(
                    f"embedding closure path contains a symlink: {relative_text}"
                )
        if not path.is_file():
            raise ConfigurationError(
                f"embedding closure requires a regular non-symlink file: {relative_text}"
            )
        before = path.stat()
        payload = path.read_bytes()
        after = path.stat()
        if (
            before.st_ino != after.st_ino
            or before.st_size != after.st_size
            or before.st_mtime_ns != after.st_mtime_ns
            or len(payload) != after.st_size
        ):
            raise ConfigurationError(
                f"embedding closure file changed while hashing: {relative_text}"
            )
        encoded = relative.as_posix().encode("utf-8")
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    """读取 JSON object，拒绝缺失、非法编码和非 object 根。"""

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"invalid local embedding {label}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"local embedding {label} must be an object")
    return raw


def _installed_version(distribution: str) -> str:
    """读取 loader 版本；未安装时不能生成可重放 identity。"""

    try:
        value = version(distribution)
    except PackageNotFoundError as exc:
        raise ConfigurationError(
            f"required embedding runtime distribution missing: {distribution}"
        ) from exc
    if not value.strip():
        raise ConfigurationError(
            f"embedding runtime distribution has blank version: {distribution}"
        )
    return value


def build_local_minilm_asset_receipt(
    *,
    project_root: Path,
    logical_path: str = LOCAL_MINILM_LOGICAL_PATH,
) -> LocalEmbeddingAssetReceipt:
    """从当前实际消费的 MiniLM Torch/ST 资产生成严格本地身份。"""

    root = resolve_project_local_embedding_path(logical_path, project_root)
    config = _read_json_object(root / "config.json", "config.json")
    pooling = _read_json_object(
        root / "1_Pooling/config.json", "1_Pooling/config.json"
    )
    sentence = _read_json_object(
        root / "sentence_bert_config.json", "sentence_bert_config.json"
    )
    tokenizer = _read_json_object(
        root / "tokenizer_config.json", "tokenizer_config.json"
    )
    try:
        modules_raw = json.loads((root / "modules.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError("invalid local embedding modules.json") from exc
    if not isinstance(modules_raw, list) or not all(
        isinstance(item, dict) and type(item.get("type")) is str
        for item in modules_raw
    ):
        raise ConfigurationError("local embedding modules.json has invalid shape")
    module_types = tuple(str(item["type"]) for item in modules_raw)
    expected_pipeline = (
        "sentence_transformers.models.Transformer",
        "sentence_transformers.models.Pooling",
        "sentence_transformers.models.Normalize",
    )
    if module_types != expected_pipeline:
        raise ConfigurationError(
            f"local MiniLM pipeline mismatch: {module_types!r}"
        )
    if (
        config.get("hidden_size") != 384
        or config.get("model_type") != "bert"
        or pooling.get("word_embedding_dimension") != 384
        or pooling.get("pooling_mode_cls_token") is not False
        or pooling.get("pooling_mode_mean_tokens") is not True
        or pooling.get("pooling_mode_max_tokens") is not False
        or pooling.get("pooling_mode_mean_sqrt_len_tokens") is not False
        or pooling.get("include_prompt", True) is not True
        or sentence.get("max_seq_length") != 256
        or tokenizer.get("tokenizer_class") != "BertTokenizer"
        or tokenizer.get("do_lower_case") is not True
    ):
        raise ConfigurationError("local MiniLM declared runtime shape mismatch")
    return LocalEmbeddingAssetReceipt(
        logical_path=Path(logical_path).as_posix(),
        local_content_sha256=_canonical_files_digest(
            root, LOCAL_MINILM_CLOSURE_FILES
        ),
        tokenizer_sha256=_canonical_files_digest(
            root, LOCAL_MINILM_TOKENIZER_FILES
        ),
        tokenizer_name="BertTokenizer",
        tokenizer_max_length=256,
        tokenizer_lowercase=True,
        dimension=384,
        model_pipeline=module_types,
        sentence_transformers_version=_installed_version("sentence-transformers"),
        transformers_version=_installed_version("transformers"),
    )


__all__ = [
    "LOCAL_EMBEDDING_CLOSURE_SCHEMA_VERSION",
    "LOCAL_MINILM_CLOSURE_FILES",
    "LOCAL_MINILM_LOGICAL_PATH",
    "LOCAL_MINILM_TOKENIZER_FILES",
    "LocalEmbeddingAssetReceipt",
    "build_local_minilm_asset_receipt",
    "resolve_embedding_runtime_model_reference",
    "resolve_project_local_embedding_path",
]
