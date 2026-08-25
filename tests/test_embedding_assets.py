"""受控本地 embedding 资产闭包、路径与 digest 的强反例。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods import embedding_assets
from memory_benchmark.methods.embedding_assets import (
    LOCAL_MINILM_CLOSURE_FILES,
    _canonical_files_digest,
    build_local_minilm_asset_receipt,
    resolve_embedding_runtime_model_reference,
    resolve_project_local_embedding_path,
)


pytestmark = pytest.mark.unit
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_local_minilm_receipt_locks_current_bytes_tokenizer_and_runtime() -> None:
    """当前受控 MiniLM 的 bytes、tokenizer、pipeline 与 loader 必须逐轴锁定。"""

    receipt = build_local_minilm_asset_receipt(project_root=PROJECT_ROOT)

    assert receipt.logical_path == "models/all-MiniLM-L6-v2"
    assert receipt.local_content_sha256 == (
        "9c93593d1d7501d102d755cefc98dd8f7b02d088a606b9a3d328502f90372fce"
    )
    assert receipt.tokenizer_sha256 == (
        "517a76b5b3e9fb42ab62649a9d9642dd7cbe4b6ec1e4d04d8e029fd224ffab0a"
    )
    assert receipt.tokenizer_name == "BertTokenizer"
    assert receipt.tokenizer_max_length == 256
    assert receipt.tokenizer_lowercase is True
    assert receipt.dimension == 384
    assert receipt.model_pipeline == (
        "sentence_transformers.models.Transformer",
        "sentence_transformers.models.Pooling",
        "sentence_transformers.models.Normalize",
    )
    assert receipt.sentence_transformers_version == "5.5.1"
    assert receipt.transformers_version == "5.9.0"


def test_runtime_reference_keeps_manifest_logical_but_product_gets_absolute() -> None:
    """本地逻辑路径只在产品边界转绝对，Hub id 不得被偷偷改写。"""

    resolved = resolve_embedding_runtime_model_reference(
        "models/all-MiniLM-L6-v2",
        PROJECT_ROOT,
    )

    assert resolved == str((PROJECT_ROOT / "models/all-MiniLM-L6-v2").resolve())
    assert resolve_embedding_runtime_model_reference(
        "sentence-transformers/all-MiniLM-L6-v2",
        PROJECT_ROOT,
    ) == "sentence-transformers/all-MiniLM-L6-v2"


@pytest.mark.parametrize(
    "reference",
    (
        "/tmp/all-MiniLM-L6-v2",
        "models/../outside",
        "third_party/all-MiniLM-L6-v2",
        "models/missing-model",
    ),
)
def test_local_embedding_path_rejects_absolute_escape_wrong_root_and_missing(
    reference: str,
) -> None:
    """本地模型不能通过绝对路径、父目录、错误根或缺失目录进入身份。"""

    with pytest.raises(ConfigurationError):
        resolve_project_local_embedding_path(reference, PROJECT_ROOT)


def test_local_embedding_path_rejects_component_or_final_directory_symlink(
    tmp_path: Path,
) -> None:
    """即便最终 resolve 仍在 models 内，目录链中的 symlink 也必须 fail-fast。"""

    real = tmp_path / "models" / "real"
    real.mkdir(parents=True)
    (tmp_path / "models" / "alias").symlink_to(real, target_is_directory=True)

    with pytest.raises(ConfigurationError, match="symlink"):
        resolve_project_local_embedding_path("models/alias", tmp_path)


def test_local_embedding_path_wraps_nul_as_configuration_error() -> None:
    """非法 NUL 路径不能把底层 ``ValueError`` 泄漏到 CLI。"""

    with pytest.raises(ConfigurationError, match="NUL"):
        resolve_project_local_embedding_path(
            "models/all-MiniLM-L6-v2\x00",
            PROJECT_ROOT,
        )


def test_canonical_digest_is_path_bound_and_rejects_symlinked_file(
    tmp_path: Path,
) -> None:
    """相同 bytes 的不同路径应得不同 digest，symlink 文件不能混入 closure。"""

    (tmp_path / "a.bin").write_bytes(b"same")
    (tmp_path / "b.bin").write_bytes(b"same")
    first = _canonical_files_digest(tmp_path, ("a.bin",))
    second = _canonical_files_digest(tmp_path, ("b.bin",))
    assert first != second

    (tmp_path / "alias.bin").symlink_to(tmp_path / "a.bin")
    with pytest.raises(ConfigurationError, match="symlink"):
        _canonical_files_digest(tmp_path, ("alias.bin",))


def test_canonical_digest_rejects_lexical_alias_and_nul(tmp_path: Path) -> None:
    """``x``/``./x`` 是同一 portable 路径，NUL 也必须走领域异常。"""

    (tmp_path / "x").write_bytes(b"x")
    with pytest.raises(ConfigurationError, match="unique"):
        _canonical_files_digest(tmp_path, ("x", "./x"))
    with pytest.raises(ConfigurationError, match="NUL"):
        _canonical_files_digest(tmp_path, ("x\x00",))


def test_sentence_transformers_loader_config_is_inside_content_closure(
    tmp_path: Path,
) -> None:
    """SentenceTransformers 实际读取的顶层 loader config 必须改变内容 digest。"""

    for relative in LOCAL_MINILM_CLOSURE_FILES:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"fixture:{relative}".encode())
    before = _canonical_files_digest(tmp_path, LOCAL_MINILM_CLOSURE_FILES)
    loader_config = tmp_path / "config_sentence_transformers.json"
    loader_config.write_bytes(b'{"__version__":{"sentence_transformers":"changed"}}')

    assert "config_sentence_transformers.json" in LOCAL_MINILM_CLOSURE_FILES
    assert _canonical_files_digest(tmp_path, LOCAL_MINILM_CLOSURE_FILES) != before


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("pooling_mode_cls_token", True),
        ("pooling_mode_max_tokens", True),
        ("pooling_mode_mean_sqrt_len_tokens", True),
        ("include_prompt", False),
    ),
)
def test_local_minilm_rejects_noncanonical_pooling_modes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: bool,
) -> None:
    """受控 MiniLM 必须是 mean-only；额外 pooling 会改变真实输出维度或语义。"""

    source = PROJECT_ROOT / "models/all-MiniLM-L6-v2"
    model_root = tmp_path / "models/all-MiniLM-L6-v2"
    for relative in (
        "config.json",
        "modules.json",
        "sentence_bert_config.json",
        "tokenizer_config.json",
        "1_Pooling/config.json",
    ):
        target = model_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / relative).read_bytes())
    pooling_path = model_root / "1_Pooling/config.json"
    pooling = json.loads(pooling_path.read_text(encoding="utf-8"))
    pooling[field] = value
    pooling_path.write_text(json.dumps(pooling), encoding="utf-8")
    monkeypatch.setattr(
        embedding_assets,
        "_canonical_files_digest",
        lambda _root, _paths: "0" * 64,
    )

    with pytest.raises(ConfigurationError, match="runtime shape mismatch"):
        build_local_minilm_asset_receipt(project_root=tmp_path)
