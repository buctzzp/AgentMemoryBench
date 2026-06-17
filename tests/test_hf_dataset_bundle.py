"""测试 Hugging Face 数据包准备脚本。

这些测试用临时小数据模拟 `data/`，验证脚本不会依赖真实大数据集，
也不会在测试中触发网络上传。
"""

import hashlib
import json
from pathlib import Path

import pytest

from scripts.prepare_hf_dataset_bundle import build_hf_dataset_bundle


pytestmark = pytest.mark.unit


def test_build_hf_dataset_bundle_writes_docs_manifest_and_checksums(tmp_path: Path) -> None:
    """测试脚本能生成 README、manifest、checksum，并排除系统噪声文件。

    参数:
        tmp_path: pytest 提供的临时目录，用来构造小型源数据和输出目录。

    输出:
        无直接返回；通过断言确认 bundle 文件结构和校验内容正确。
    """

    source_dir = tmp_path / "data"
    locomo_dir = source_dir / "locomo"
    locomo_dir.mkdir(parents=True)
    dataset_file = locomo_dir / "locomo10.json"
    dataset_file.write_text('{"conversation": []}\n', encoding="utf-8")
    (locomo_dir / ".DS_Store").write_bytes(b"noise")

    output_dir = tmp_path / "hf_bundle"

    manifest = build_hf_dataset_bundle(
        source_dir=source_dir,
        output_dir=output_dir,
        repo_id="BuptZZP/agentmemorybench-data",
        link_mode="copy",
    )

    copied_file = output_dir / "locomo" / "locomo10.json"
    skipped_file = output_dir / "locomo" / ".DS_Store"
    checksum = hashlib.sha256(copied_file.read_bytes()).hexdigest()

    assert copied_file.exists()
    assert not skipped_file.exists()
    assert (output_dir / "README.md").exists()
    assert (output_dir / "locomo" / "README.md").exists()
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "checksums.sha256").exists()

    manifest_payload = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["repo_id"] == "BuptZZP/agentmemorybench-data"
    assert manifest_payload["total_files"] == 1
    assert manifest_payload["datasets"]["locomo"]["file_count"] == 1
    assert manifest_payload["files"][0]["sha256"] == checksum
    assert manifest.total_files == 1

    checksum_lines = (output_dir / "checksums.sha256").read_text(encoding="utf-8").splitlines()
    assert checksum_lines == [f"{checksum}  locomo/locomo10.json"]


def test_build_hf_dataset_bundle_rejects_output_inside_source(tmp_path: Path) -> None:
    """测试输出目录不能放在源数据目录内部。

    参数:
        tmp_path: pytest 提供的临时目录，用来构造源数据目录。

    输出:
        无直接返回；通过断言确认危险路径会被拒绝。
    """

    source_dir = tmp_path / "data"
    source_dir.mkdir()

    with pytest.raises(ValueError, match="输出目录不能位于源数据目录内部"):
        build_hf_dataset_bundle(
            source_dir=source_dir,
            output_dir=source_dir / "hf_bundle",
            repo_id="BuptZZP/agentmemorybench-data",
        )
