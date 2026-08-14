"""新 TOML profile run identity 的严格序列化与强反例。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.run_identity import (
    BuildIdentityDeclaration,
    EmbeddingIdentity,
    MethodRunIdentity,
    build_method_run_identity,
)


def _build_identity() -> BuildIdentityDeclaration:
    """返回 hermetic 的 declared MiniLM build 身份。"""

    return BuildIdentityDeclaration(
        implementation_variant="product",
        embedding_profile="controlled_embedding_v1",
        historical_controlled_build_equivalent_to_current_main=False,
        embedding=EmbeddingIdentity(
            provider="huggingface",
            model="sentence-transformers/all-MiniLM-L6-v2",
            dimension=384,
            revision=None,
            revision_status="local_unpinned",
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
    )

    raw = identity.to_manifest_dict()
    assert MethodRunIdentity.from_manifest_dict(raw) == identity
    assert raw["profile"] == {
        "name": "official-full",
        "section": "official_full",
    }
    assert raw["answer_builder"] == "benchmark"


@pytest.mark.parametrize(
    ("path", "value", "message"),
    (
        (("contract_version",), "v2", "contract_version"),
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
    ).to_manifest_dict()
    missing = deepcopy(raw)
    missing.pop("answer_builder")
    extra = deepcopy(raw)
    extra["readout_track"] = "unified"

    with pytest.raises(ConfigurationError, match="keys mismatch"):
        MethodRunIdentity.from_manifest_dict(missing)
    with pytest.raises(ConfigurationError, match="keys mismatch"):
        MethodRunIdentity.from_manifest_dict(extra)
