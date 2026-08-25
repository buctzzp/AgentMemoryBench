"""新 TOML profile run identity 的严格序列化与强反例。"""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, cast

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.run_identity import (
    BuildIdentityDeclaration,
    EmbeddingArtifactIdentity,
    EmbeddingIdentity,
    MethodRunIdentity,
    build_method_run_identity,
)
from memory_benchmark.methods.registry import (
    get_method_registration,
    load_method_profile,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "method_name",
    (
        "lightmem",
        "amem",
        "mem0",
        "memoryos",
        "memos",
        "simplemem",
        "langmem",
        "everos",
        "graphiti",
    ),
)
def test_current_embedding_consumers_share_one_content_locked_minilm(
    method_name: str,
) -> None:
    """九个实际消费 embedding 的主 profile 必须锁同一组本地 bytes。"""

    registration = get_method_registration(method_name)
    config = load_method_profile(method_name, "smoke", project_root=PROJECT_ROOT)
    build = registration.build_identity_resolver(config.to_manifest())
    identity = build_method_run_identity(
        profile_name="smoke",
        profile_section="method",
        answer_builder="benchmark",
        build_identity=build,
        project_root=PROJECT_ROOT,
    )

    assert build.embedding.model == "models/all-MiniLM-L6-v2"
    assert build.embedding.revision_status == "local_content_locked"
    assert identity.embedding_artifact is not None
    assert identity.embedding_artifact.status == "local_locked"
    assert identity.embedding_artifact.local_content_sha256 == (
        "9c93593d1d7501d102d755cefc98dd8f7b02d088a606b9a3d328502f90372fce"
    )


def test_letta_embedding_identity_is_truthfully_not_applicable() -> None:
    """Letta 主 profile 不消费 embedding，不能为十家齐表伪造本地模型。"""

    registration = get_method_registration("letta")
    config = load_method_profile("letta", "smoke", project_root=PROJECT_ROOT)
    build = registration.build_identity_resolver(config.to_manifest())
    identity = build_method_run_identity(
        profile_name="smoke",
        profile_section="method",
        answer_builder="benchmark",
        build_identity=build,
        project_root=PROJECT_ROOT,
    )

    assert build.embedding_profile == "not_applicable_v1"
    assert identity.embedding_artifact is not None
    assert identity.embedding_artifact.status == "not_applicable"


def _build_identity() -> BuildIdentityDeclaration:
    """返回 hermetic 的 declared MiniLM build 身份。"""

    return BuildIdentityDeclaration(
        implementation_variant="product",
        embedding_profile="controlled_embedding_v1",
        historical_controlled_build_equivalent_to_current_main=False,
        embedding=EmbeddingIdentity(
            provider="huggingface",
            model="models/all-MiniLM-L6-v2",
            dimension=384,
            revision=None,
            revision_status="local_content_locked",
            normalization="l2",
            instruction=None,
            distance="cosine",
            identity_status="declared",
        ),
    )


def test_method_run_identity_round_trip_is_strict_and_lossless() -> None:
    """新身份应完整锁住公开 profile、section、builder 与 build。"""

    identity = build_method_run_identity(
        profile_name="official-full",
        profile_section="official_full",
        answer_builder="benchmark",
        build_identity=_build_identity(),
        project_root=PROJECT_ROOT,
    )

    raw = identity.to_manifest_dict()
    assert MethodRunIdentity.from_manifest_dict(raw) == identity
    assert raw["profile"] == {
        "name": "official-full",
        "section": "official_full",
    }
    assert raw["answer_builder"] == "benchmark"
    artifact = raw["build"]["embedding_artifact"]
    assert artifact["status"] == "local_locked"
    assert artifact["local_content_sha256"] == (
        "9c93593d1d7501d102d755cefc98dd8f7b02d088a606b9a3d328502f90372fce"
    )


@pytest.mark.parametrize(
    ("path", "value", "message"),
    (
        (("contract_version",), "v3", "contract_version"),
        (("profile", "name"), "Official Full", "profile_name"),
        (("profile", "section"), "../smoke", "profile_section"),
        (("answer_builder",), " benchmark ", "answer_builder"),
        (("build", "embedding", "dimension"), True, "dimension"),
    ),
)
def test_method_run_identity_rejects_illegal_runtime_values(
    path: tuple[str, ...],
    value: Any,
    message: str,
) -> None:
    """路径字符、宽松枚举和 bool-as-int 都不得进入新 manifest。"""

    raw = build_method_run_identity(
        profile_name="smoke",
        profile_section="smoke",
        answer_builder="benchmark",
        build_identity=_build_identity(),
        project_root=PROJECT_ROOT,
    ).to_manifest_dict()
    cursor = raw
    for key in path[:-1]:
        cursor = cast(dict[str, Any], cursor[key])
    cursor[path[-1]] = value

    with pytest.raises(ConfigurationError, match=message):
        MethodRunIdentity.from_manifest_dict(raw)


def test_method_run_identity_rejects_missing_extra_and_mixed_shape() -> None:
    """新身份 parser 不接受缺键、多余键或 legacy track 字段。"""

    raw = build_method_run_identity(
        profile_name="smoke",
        profile_section="smoke",
        answer_builder="benchmark",
        build_identity=_build_identity(),
        project_root=PROJECT_ROOT,
    ).to_manifest_dict()
    missing = deepcopy(raw)
    missing.pop("answer_builder")
    extra = deepcopy(raw)
    extra["readout_track"] = "unified"

    with pytest.raises(ConfigurationError, match="keys mismatch"):
        MethodRunIdentity.from_manifest_dict(missing)
    with pytest.raises(ConfigurationError, match="keys mismatch"):
        MethodRunIdentity.from_manifest_dict(extra)


def test_v1_run_identity_remains_read_only_parseable_without_v2_artifact() -> None:
    """旧 v1 shape 应能原样回读，但绝不能被偷偷补成当前 v2。"""

    current = build_method_run_identity(
        profile_name="smoke",
        profile_section="smoke",
        answer_builder="benchmark",
        build_identity=_build_identity(),
        project_root=PROJECT_ROOT,
    ).to_manifest_dict()
    legacy = deepcopy(current)
    legacy["contract_version"] = "v1"
    legacy["build"].pop("embedding_artifact")
    legacy["build"]["embedding"]["revision_status"] = "local_unpinned"

    parsed = MethodRunIdentity.from_manifest_dict(legacy)

    assert parsed.contract_version == "v1"
    assert parsed.embedding_artifact is None
    assert parsed.to_manifest_dict() == legacy


def test_v1_run_identity_rejects_v2_only_local_content_lock_claim() -> None:
    """旧 shape 不得冒充已经锁住本地模型 bytes 的 v2 identity。"""

    raw = build_method_run_identity(
        profile_name="smoke",
        profile_section="smoke",
        answer_builder="benchmark",
        build_identity=_build_identity(),
        project_root=PROJECT_ROOT,
    ).to_manifest_dict()
    raw["contract_version"] = "v1"
    raw["build"].pop("embedding_artifact")

    with pytest.raises(ConfigurationError, match="v2 local_content_locked"):
        MethodRunIdentity.from_manifest_dict(raw)


def test_v2_run_identity_rejects_missing_tampered_or_misaligned_artifact() -> None:
    """新 v2 不允许丢资产锁、伪造 digest 或把逻辑路径换成别的模型。"""

    raw = build_method_run_identity(
        profile_name="smoke",
        profile_section="smoke",
        answer_builder="benchmark",
        build_identity=_build_identity(),
        project_root=PROJECT_ROOT,
    ).to_manifest_dict()
    missing = deepcopy(raw)
    missing["build"].pop("embedding_artifact")
    bad_digest = deepcopy(raw)
    bad_digest["build"]["embedding_artifact"]["local_content_sha256"] = "ABC"
    wrong_path = deepcopy(raw)
    wrong_path["build"]["embedding_artifact"]["logical_path"] = (
        "models/another-model"
    )

    with pytest.raises(ConfigurationError, match="keys mismatch"):
        MethodRunIdentity.from_manifest_dict(missing)
    with pytest.raises(ConfigurationError, match="lowercase SHA-256"):
        MethodRunIdentity.from_manifest_dict(bad_digest)
    with pytest.raises(ConfigurationError, match="logical_path"):
        MethodRunIdentity.from_manifest_dict(wrong_path)


def test_v2_controlled_profile_rejects_provider_managed_embedding_artifact() -> None:
    """controlled/canonical profile 不能只写一个未锁 bytes 的 provider model id。"""

    build = BuildIdentityDeclaration(
        implementation_variant="product",
        embedding_profile="controlled_embedding_v1",
        historical_controlled_build_equivalent_to_current_main=False,
        embedding=EmbeddingIdentity(
            provider="huggingface",
            model="sentence-transformers/all-MiniLM-L6-v2",
            dimension=384,
            revision=None,
            revision_status="local_unpinned",
            normalization="model_pipeline_l2",
            instruction=None,
            distance="cosine",
            identity_status="declared",
        ),
    )
    artifact = EmbeddingArtifactIdentity(
        status="provider_managed_unpinned",
        closure_schema_version=None,
        logical_path=None,
        local_content_sha256=None,
        tokenizer_sha256=None,
        tokenizer_name=None,
        tokenizer_max_length=None,
        tokenizer_lowercase=None,
        sentence_transformers_version=None,
        transformers_version=None,
    )

    with pytest.raises(ConfigurationError, match="requires a local_locked"):
        MethodRunIdentity(
            contract_version="v2",
            profile_name="smoke",
            profile_section="smoke",
            answer_builder="benchmark",
            build=build,
            embedding_artifact=artifact,
        )


def test_embedding_not_applicable_requires_all_concrete_fields_null() -> None:
    """不消费 embedding 的 profile 必须显式 N/A，不能夹带假模型。"""

    identity = BuildIdentityDeclaration(
        implementation_variant="product",
        embedding_profile="not_applicable_v1",
        historical_controlled_build_equivalent_to_current_main=False,
        embedding=EmbeddingIdentity(
            provider=None,
            model=None,
            dimension=None,
            revision=None,
            revision_status="not_applicable",
            normalization=None,
            instruction=None,
            distance=None,
            identity_status="not_applicable",
        ),
    )
    assert identity.embedding.to_manifest_dict()["identity_status"] == "not_applicable"

    with pytest.raises(ConfigurationError, match="all concrete fields null"):
        EmbeddingIdentity(
            provider="sentence-transformers",
            model=None,
            dimension=None,
            revision=None,
            revision_status="not_applicable",
            normalization=None,
            instruction=None,
            distance=None,
            identity_status="not_applicable",
        )
