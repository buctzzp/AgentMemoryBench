"""新运行使用的 method profile、build 与 embedding 身份契约。

本模块不选择旧 ``unified/native`` readout。它只描述一次新 run 实际选择的
TOML profile、完整 answer builder，以及由当前强类型 method 配置解析出的 build
事实。历史 ``TrackIdentity v1`` 仍由 ``config_track`` 只读解析。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, TypeAlias, cast, get_args

from memory_benchmark.core import ConfigurationError
from memory_benchmark.methods.embedding_assets import (
    LOCAL_EMBEDDING_CLOSURE_SCHEMA_VERSION,
    build_local_minilm_asset_receipt,
)


RunIdentityContractVersion = Literal["v1", "v2"]
ImplementationVariant = Literal["product", "reproduction:memoryos-chromadb"]
EmbeddingProfile = Literal[
    "controlled_embedding_v1",
    "product_canonical_required_config_v1",
    "product_default_v1",
    "not_applicable_v1",
    "unclassified_pending",
]
EmbeddingRevisionStatus = Literal[
    "local_content_locked",
    "local_unpinned",
    "provider_managed_unpinned",
    "not_applicable",
    "pending",
]
EmbeddingIdentityStatus = Literal["declared", "not_applicable", "pending"]
EmbeddingArtifactStatus = Literal[
    "local_locked",
    "provider_managed_unpinned",
    "not_applicable",
    "pending",
]

LiteralAlias: TypeAlias = Any
RUN_IDENTITY_CONTRACT_VERSION: RunIdentityContractVersion = "v2"


def _literal_values(alias: LiteralAlias) -> frozenset[Any]:
    """从 Literal 注解单源派生运行时允许集合。"""

    return frozenset(get_args(alias))


def _require_literal(value: Any, alias: LiteralAlias, label: str) -> Any:
    """校验值属于指定 Literal，并把非法运行时输入统一为领域异常。"""

    allowed = _literal_values(alias)
    if type(value) is not str or value not in allowed:
        raise ConfigurationError(
            f"method run identity {label}={value!r} not in {sorted(allowed)}"
        )
    return value


def _require_exact_keys(
    raw: Mapping[str, Any],
    expected: frozenset[str],
    label: str,
) -> None:
    """拒绝 manifest 对象缺键、携带未知键或使用非文本键。"""

    non_text_keys = [repr(key) for key in raw if type(key) is not str]
    if non_text_keys:
        raise ConfigurationError(
            f"{label} keys must be strings, got {sorted(non_text_keys)}"
        )
    actual = frozenset(raw)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing or extra:
        raise ConfigurationError(
            f"{label} keys mismatch: missing={missing}, extra={extra}"
        )


def _optional_manifest_text(value: Any, label: str) -> str | None:
    """解析可空文本；非字符串和空白字符串均 fail-fast。"""

    if value is None:
        return None
    if type(value) is not str or not value.strip():
        raise ConfigurationError(f"{label} must be null or a non-blank string")
    return value


def _identity_token(value: Any, label: str) -> str:
    """校验 profile/builder 的稳定 token，阻止路径字符和隐式正规化。"""

    if type(value) is not str or not value:
        raise ConfigurationError(f"{label} must be a non-blank identity token")
    allowed = frozenset(
        "abcdefghijklmnopqrstuvwxyz0123456789_-"
    )
    if value[0] not in frozenset("abcdefghijklmnopqrstuvwxyz0123456789") or any(
        character not in allowed for character in value
    ):
        raise ConfigurationError(
            f"{label} must match [a-z0-9][a-z0-9_-]*, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class EmbeddingIdentity:
    """method 当前 build 的 concrete embedding 身份。"""

    provider: str | None
    model: str | None
    dimension: int | None
    revision: str | None
    revision_status: EmbeddingRevisionStatus
    normalization: str | None
    instruction: str | None
    distance: str | None
    identity_status: EmbeddingIdentityStatus

    def __post_init__(self) -> None:
        """构造时立即拒绝非法或自相矛盾的 embedding 身份。"""

        validate_embedding_identity(self)

    def to_manifest_dict(self) -> dict[str, Any]:
        """返回可公开写入 manifest 的稳定字典。"""

        return {
            "provider": self.provider,
            "model": self.model,
            "dimension": self.dimension,
            "revision": self.revision,
            "revision_status": self.revision_status,
            "normalization": self.normalization,
            "instruction": self.instruction,
            "distance": self.distance,
            "identity_status": self.identity_status,
        }

    @classmethod
    def from_manifest_dict(cls, raw: Mapping[str, Any]) -> "EmbeddingIdentity":
        """严格解析 manifest embedding，不做宽松类型转换。"""

        if not isinstance(raw, Mapping):
            raise ConfigurationError("method run identity embedding must be an object")
        _require_exact_keys(
            raw,
            frozenset(
                {
                    "provider",
                    "model",
                    "dimension",
                    "revision",
                    "revision_status",
                    "normalization",
                    "instruction",
                    "distance",
                    "identity_status",
                }
            ),
            "method run identity embedding",
        )
        dimension = raw["dimension"]
        if dimension is not None and type(dimension) is not int:
            raise ConfigurationError("embedding dimension must be null or an integer")
        return cls(
            provider=_optional_manifest_text(raw["provider"], "embedding provider"),
            model=_optional_manifest_text(raw["model"], "embedding model"),
            dimension=dimension,
            revision=_optional_manifest_text(raw["revision"], "embedding revision"),
            revision_status=cast(
                EmbeddingRevisionStatus,
                _require_literal(
                    raw["revision_status"],
                    EmbeddingRevisionStatus,
                    "embedding.revision_status",
                ),
            ),
            normalization=_optional_manifest_text(
                raw["normalization"], "embedding normalization"
            ),
            instruction=_optional_manifest_text(
                raw["instruction"], "embedding instruction"
            ),
            distance=_optional_manifest_text(raw["distance"], "embedding distance"),
            identity_status=cast(
                EmbeddingIdentityStatus,
                _require_literal(
                    raw["identity_status"],
                    EmbeddingIdentityStatus,
                    "embedding.identity_status",
                ),
            ),
        )


@dataclass(frozen=True)
class EmbeddingArtifactIdentity:
    """embedding 模型 bytes、tokenizer 与 loader runtime 的 v2 身份。"""

    status: EmbeddingArtifactStatus
    closure_schema_version: str | None
    logical_path: str | None
    local_content_sha256: str | None
    tokenizer_sha256: str | None
    tokenizer_name: str | None
    tokenizer_max_length: int | None
    tokenizer_lowercase: bool | None
    sentence_transformers_version: str | None
    transformers_version: str | None

    def __post_init__(self) -> None:
        """构造时拒绝半锁定、假 N/A 或宽松 token。"""

        validate_embedding_artifact_identity(self)

    def to_manifest_dict(self) -> dict[str, Any]:
        """返回 v2 manifest 的固定 shape。"""

        return {
            "status": self.status,
            "closure_schema_version": self.closure_schema_version,
            "logical_path": self.logical_path,
            "local_content_sha256": self.local_content_sha256,
            "tokenizer_sha256": self.tokenizer_sha256,
            "tokenizer_name": self.tokenizer_name,
            "tokenizer_max_length": self.tokenizer_max_length,
            "tokenizer_lowercase": self.tokenizer_lowercase,
            "sentence_transformers_version": self.sentence_transformers_version,
            "transformers_version": self.transformers_version,
        }

    @classmethod
    def from_manifest_dict(
        cls, raw: Mapping[str, Any]
    ) -> "EmbeddingArtifactIdentity":
        """严格解析 v2 embedding artifact。"""

        if not isinstance(raw, Mapping):
            raise ConfigurationError(
                "method run identity embedding_artifact must be an object"
            )
        expected = frozenset(
            {
                "status",
                "closure_schema_version",
                "logical_path",
                "local_content_sha256",
                "tokenizer_sha256",
                "tokenizer_name",
                "tokenizer_max_length",
                "tokenizer_lowercase",
                "sentence_transformers_version",
                "transformers_version",
            }
        )
        _require_exact_keys(raw, expected, "method run identity embedding_artifact")
        tokenizer_max_length = raw["tokenizer_max_length"]
        if tokenizer_max_length is not None and type(tokenizer_max_length) is not int:
            raise ConfigurationError(
                "embedding artifact tokenizer_max_length must be null or integer"
            )
        tokenizer_lowercase = raw["tokenizer_lowercase"]
        if tokenizer_lowercase is not None and type(tokenizer_lowercase) is not bool:
            raise ConfigurationError(
                "embedding artifact tokenizer_lowercase must be null or bool"
            )
        return cls(
            status=cast(
                EmbeddingArtifactStatus,
                _require_literal(
                    raw["status"],
                    EmbeddingArtifactStatus,
                    "embedding_artifact.status",
                ),
            ),
            closure_schema_version=_optional_manifest_text(
                raw["closure_schema_version"],
                "embedding artifact closure_schema_version",
            ),
            logical_path=_optional_manifest_text(
                raw["logical_path"], "embedding artifact logical_path"
            ),
            local_content_sha256=_optional_manifest_text(
                raw["local_content_sha256"],
                "embedding artifact local_content_sha256",
            ),
            tokenizer_sha256=_optional_manifest_text(
                raw["tokenizer_sha256"], "embedding artifact tokenizer_sha256"
            ),
            tokenizer_name=_optional_manifest_text(
                raw["tokenizer_name"], "embedding artifact tokenizer_name"
            ),
            tokenizer_max_length=tokenizer_max_length,
            tokenizer_lowercase=tokenizer_lowercase,
            sentence_transformers_version=_optional_manifest_text(
                raw["sentence_transformers_version"],
                "embedding artifact sentence_transformers_version",
            ),
            transformers_version=_optional_manifest_text(
                raw["transformers_version"],
                "embedding artifact transformers_version",
            ),
        )


@dataclass(frozen=True)
class BuildIdentityDeclaration:
    """注册表从当前 method config 解析出的单一 build 身份事实源。"""

    implementation_variant: ImplementationVariant
    embedding_profile: EmbeddingProfile
    historical_controlled_build_equivalent_to_current_main: bool
    embedding: EmbeddingIdentity

    def __post_init__(self) -> None:
        """校验注册声明的枚举、布尔类型与 pending 对齐关系。"""

        validate_build_identity(self)

    def to_manifest_dict(self) -> dict[str, Any]:
        """返回新 run identity 使用的稳定嵌套字典。"""

        return {
            "implementation_variant": self.implementation_variant,
            "embedding_profile": self.embedding_profile,
            "historical_controlled_build_equivalent_to_current_main": (
                self.historical_controlled_build_equivalent_to_current_main
            ),
            "embedding": self.embedding.to_manifest_dict(),
        }

    @classmethod
    def from_manifest_dict(cls, raw: Mapping[str, Any]) -> "BuildIdentityDeclaration":
        """严格解析新 run manifest 的 build 对象。"""

        if not isinstance(raw, Mapping):
            raise ConfigurationError("method run identity build must be an object")
        _require_exact_keys(
            raw,
            frozenset(
                {
                    "implementation_variant",
                    "embedding_profile",
                    "historical_controlled_build_equivalent_to_current_main",
                    "embedding",
                }
            ),
            "method run identity build",
        )
        historical_equivalent = raw[
            "historical_controlled_build_equivalent_to_current_main"
        ]
        if type(historical_equivalent) is not bool:
            raise ConfigurationError(
                "historical_controlled_build_equivalent_to_current_main must be bool"
            )
        embedding = raw["embedding"]
        if not isinstance(embedding, Mapping):
            raise ConfigurationError("method run identity build.embedding must be an object")
        return cls(
            implementation_variant=cast(
                ImplementationVariant,
                _require_literal(
                    raw["implementation_variant"],
                    ImplementationVariant,
                    "build.implementation_variant",
                ),
            ),
            embedding_profile=cast(
                EmbeddingProfile,
                _require_literal(
                    raw["embedding_profile"],
                    EmbeddingProfile,
                    "build.embedding_profile",
                ),
            ),
            historical_controlled_build_equivalent_to_current_main=(
                historical_equivalent
            ),
            embedding=EmbeddingIdentity.from_manifest_dict(embedding),
        )


@dataclass(frozen=True)
class MethodRunIdentity:
    """新 run 的 profile、answer builder 与 build 身份契约。"""

    contract_version: RunIdentityContractVersion
    profile_name: str
    profile_section: str
    answer_builder: str
    build: BuildIdentityDeclaration
    embedding_artifact: EmbeddingArtifactIdentity | None = None

    def __post_init__(self) -> None:
        """构造时执行完整运行身份校验。"""

        _require_literal(
            self.contract_version,
            RunIdentityContractVersion,
            "contract_version",
        )
        _identity_token(self.profile_name, "method run identity profile_name")
        _identity_token(self.profile_section, "method run identity profile_section")
        _identity_token(self.answer_builder, "method run identity answer_builder")
        if not isinstance(self.build, BuildIdentityDeclaration):
            raise ConfigurationError(
                "method run identity build must be BuildIdentityDeclaration"
            )
        if self.contract_version == "v1":
            if self.embedding_artifact is not None:
                raise ConfigurationError(
                    "v1 method run identity cannot contain embedding_artifact"
                )
        elif not isinstance(self.embedding_artifact, EmbeddingArtifactIdentity):
            raise ConfigurationError(
                "v2 method run identity requires EmbeddingArtifactIdentity"
            )
        else:
            validate_method_embedding_artifact_alignment(
                self.build,
                self.embedding_artifact,
            )

    def to_manifest_dict(self) -> dict[str, Any]:
        """返回可公开写入 method manifest 的稳定字典。"""

        build = self.build.to_manifest_dict()
        if self.contract_version == "v2":
            if self.embedding_artifact is None:  # defensive; __post_init__ rejects
                raise ConfigurationError("v2 run identity embedding artifact missing")
            build["embedding_artifact"] = self.embedding_artifact.to_manifest_dict()
        return {
            "contract_version": self.contract_version,
            "profile": {
                "name": self.profile_name,
                "section": self.profile_section,
            },
            "answer_builder": self.answer_builder,
            "build": build,
        }

    @classmethod
    def from_manifest_dict(cls, raw: Mapping[str, Any]) -> "MethodRunIdentity":
        """严格解析 v1 新运行身份，拒绝和旧 track schema 混读。"""

        if not isinstance(raw, Mapping):
            raise ConfigurationError("method.run_identity must be an object")
        _require_exact_keys(
            raw,
            frozenset(
                {
                    "contract_version",
                    "profile",
                    "answer_builder",
                    "build",
                }
            ),
            "method.run_identity",
        )
        profile = raw["profile"]
        if not isinstance(profile, Mapping):
            raise ConfigurationError("method.run_identity.profile must be an object")
        _require_exact_keys(
            profile,
            frozenset({"name", "section"}),
            "method.run_identity.profile",
        )
        build_raw = raw["build"]
        if not isinstance(build_raw, Mapping):
            raise ConfigurationError("method.run_identity.build must be an object")
        contract_version = cast(
            RunIdentityContractVersion,
            _require_literal(
                raw["contract_version"],
                RunIdentityContractVersion,
                "contract_version",
            ),
        )
        embedding_artifact: EmbeddingArtifactIdentity | None = None
        if contract_version == "v1":
            build = build_raw
        else:
            _require_exact_keys(
                build_raw,
                frozenset(
                    {
                        "implementation_variant",
                        "embedding_profile",
                        "historical_controlled_build_equivalent_to_current_main",
                        "embedding",
                        "embedding_artifact",
                    }
                ),
                "method run identity build",
            )
            artifact_raw = build_raw["embedding_artifact"]
            if not isinstance(artifact_raw, Mapping):
                raise ConfigurationError(
                    "method.run_identity.build.embedding_artifact must be an object"
                )
            embedding_artifact = EmbeddingArtifactIdentity.from_manifest_dict(
                artifact_raw
            )
            build = {
                key: value
                for key, value in build_raw.items()
                if key != "embedding_artifact"
            }
        parsed_build = BuildIdentityDeclaration.from_manifest_dict(build)
        if (
            contract_version == "v1"
            and parsed_build.embedding.revision_status == "local_content_locked"
        ):
            raise ConfigurationError(
                "v1 method run identity cannot claim v2 local_content_locked assets"
            )
        return cls(
            contract_version=contract_version,
            profile_name=_identity_token(
                profile["name"], "method run identity profile_name"
            ),
            profile_section=_identity_token(
                profile["section"], "method run identity profile_section"
            ),
            answer_builder=_identity_token(
                raw["answer_builder"], "method run identity answer_builder"
            ),
            build=parsed_build,
            embedding_artifact=embedding_artifact,
        )


def validate_embedding_identity(embedding: EmbeddingIdentity) -> None:
    """强校验 embedding 字段及 declared/pending 互斥语义。"""

    _require_literal(
        embedding.revision_status,
        EmbeddingRevisionStatus,
        "embedding.revision_status",
    )
    _require_literal(
        embedding.identity_status,
        EmbeddingIdentityStatus,
        "embedding.identity_status",
    )
    for label, value in (
        ("provider", embedding.provider),
        ("model", embedding.model),
        ("revision", embedding.revision),
        ("normalization", embedding.normalization),
        ("instruction", embedding.instruction),
        ("distance", embedding.distance),
    ):
        _optional_manifest_text(value, f"embedding {label}")
        if isinstance(value, str) and value.strip().lower() == "unknown":
            raise ConfigurationError(
                f"embedding {label} must use null instead of the string 'unknown'"
            )
    if embedding.dimension is not None and (
        type(embedding.dimension) is not int or embedding.dimension <= 0
    ):
        raise ConfigurationError(
            f"embedding dimension must be a positive int or null, got {embedding.dimension!r}"
        )
    if embedding.identity_status == "declared":
        if embedding.provider is None or embedding.model is None:
            raise ConfigurationError(
                "declared embedding identity requires non-blank provider and model"
            )
        if embedding.dimension is None:
            raise ConfigurationError(
                "declared embedding identity requires a positive dimension"
            )
        if embedding.revision_status == "pending":
            raise ConfigurationError(
                "declared embedding identity cannot use pending revision_status"
            )
        if embedding.distance is None:
            raise ConfigurationError(
                "declared embedding identity requires a known distance"
            )
    elif embedding.identity_status == "pending":
        if embedding.revision_status != "pending":
            raise ConfigurationError(
                "pending embedding identity requires revision_status='pending'"
            )
        if embedding.revision is not None:
            raise ConfigurationError(
                "pending embedding identity cannot claim a concrete revision"
            )
    else:
        if embedding.revision_status != "not_applicable":
            raise ConfigurationError(
                "not_applicable embedding identity requires "
                "revision_status='not_applicable'"
            )
        non_null = {
            label: value
            for label, value in (
                ("provider", embedding.provider),
                ("model", embedding.model),
                ("dimension", embedding.dimension),
                ("revision", embedding.revision),
                ("normalization", embedding.normalization),
                ("instruction", embedding.instruction),
                ("distance", embedding.distance),
            )
            if value is not None
        }
        if non_null:
            raise ConfigurationError(
                "not_applicable embedding identity requires all concrete fields null: "
                f"{sorted(non_null)}"
            )


def validate_build_identity(identity: BuildIdentityDeclaration) -> None:
    """校验 build identity 的枚举、布尔与 embedding 分类一致性。"""

    _require_literal(
        identity.implementation_variant,
        ImplementationVariant,
        "build.implementation_variant",
    )
    _require_literal(
        identity.embedding_profile,
        EmbeddingProfile,
        "build.embedding_profile",
    )
    if type(identity.historical_controlled_build_equivalent_to_current_main) is not bool:
        raise ConfigurationError(
            "historical_controlled_build_equivalent_to_current_main must be bool"
        )
    if (
        identity.embedding_profile == "unclassified_pending"
        and identity.embedding.identity_status != "pending"
    ):
        raise ConfigurationError(
            "unclassified_pending profile requires pending embedding identity"
        )
    if identity.embedding_profile == "not_applicable_v1":
        if identity.embedding.identity_status != "not_applicable":
            raise ConfigurationError(
                "not_applicable_v1 profile requires not_applicable embedding identity"
            )
    elif (
        identity.embedding_profile != "unclassified_pending"
        and identity.embedding.identity_status != "declared"
    ):
        raise ConfigurationError(
            "classified embedding profile requires declared embedding identity"
        )


def validate_embedding_artifact_identity(
    artifact: EmbeddingArtifactIdentity,
) -> None:
    """校验 v2 模型资产锁的完整性与 N/A/pending 负空间。"""

    _require_literal(
        artifact.status,
        EmbeddingArtifactStatus,
        "embedding_artifact.status",
    )
    text_fields = (
        ("closure_schema_version", artifact.closure_schema_version),
        ("logical_path", artifact.logical_path),
        ("local_content_sha256", artifact.local_content_sha256),
        ("tokenizer_sha256", artifact.tokenizer_sha256),
        ("tokenizer_name", artifact.tokenizer_name),
        ("sentence_transformers_version", artifact.sentence_transformers_version),
        ("transformers_version", artifact.transformers_version),
    )
    for label, value in text_fields:
        _optional_manifest_text(value, f"embedding artifact {label}")
    if artifact.tokenizer_max_length is not None and (
        type(artifact.tokenizer_max_length) is not int
        or artifact.tokenizer_max_length <= 0
    ):
        raise ConfigurationError(
            "embedding artifact tokenizer_max_length must be positive int or null"
        )
    if artifact.tokenizer_lowercase is not None and (
        type(artifact.tokenizer_lowercase) is not bool
    ):
        raise ConfigurationError(
            "embedding artifact tokenizer_lowercase must be bool or null"
        )
    concrete = {
        label: value
        for label, value in (
            *text_fields,
            ("tokenizer_max_length", artifact.tokenizer_max_length),
            ("tokenizer_lowercase", artifact.tokenizer_lowercase),
        )
        if value is not None
    }
    if artifact.status == "local_locked":
        required = {
            "closure_schema_version",
            "logical_path",
            "local_content_sha256",
            "tokenizer_sha256",
            "tokenizer_name",
            "sentence_transformers_version",
            "transformers_version",
            "tokenizer_max_length",
            "tokenizer_lowercase",
        }
        missing = sorted(required - concrete.keys())
        if missing:
            raise ConfigurationError(
                f"local_locked embedding artifact missing fields: {missing}"
            )
        for label in ("local_content_sha256", "tokenizer_sha256"):
            digest = concrete[label]
            if (
                type(digest) is not str
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise ConfigurationError(
                    f"embedding artifact {label} must be lowercase SHA-256"
                )
    elif concrete:
        raise ConfigurationError(
            f"{artifact.status} embedding artifact requires all concrete fields null: "
            f"{sorted(concrete)}"
        )


def validate_method_embedding_artifact_alignment(
    build: BuildIdentityDeclaration,
    artifact: EmbeddingArtifactIdentity,
) -> None:
    """把 v2 artifact 与 build profile、embedding、路径和维度绑定。"""

    embedding = build.embedding

    if embedding.identity_status == "not_applicable":
        expected_status = "not_applicable"
    elif embedding.identity_status == "pending":
        expected_status = "pending"
    elif embedding.revision_status == "local_content_locked":
        expected_status = "local_locked"
    else:
        expected_status = "provider_managed_unpinned"
    if artifact.status != expected_status:
        raise ConfigurationError(
            "embedding artifact status does not match build embedding identity: "
            f"expected {expected_status!r}, got {artifact.status!r}"
        )
    if build.embedding_profile in {
        "controlled_embedding_v1",
        "product_canonical_required_config_v1",
    } and artifact.status != "local_locked":
        raise ConfigurationError(
            f"{build.embedding_profile} requires a local_locked embedding artifact"
        )
    if artifact.status == "local_locked":
        if artifact.logical_path != embedding.model:
            raise ConfigurationError(
                "local embedding artifact logical_path must equal embedding model"
            )
        if embedding.dimension != 384:
            raise ConfigurationError(
                "current local MiniLM artifact requires embedding dimension 384"
            )


def _empty_embedding_artifact(status: EmbeddingArtifactStatus) -> EmbeddingArtifactIdentity:
    """构造 provider-managed、N/A 或 pending 的严格空 artifact。"""

    return EmbeddingArtifactIdentity(
        status=status,
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


def build_embedding_artifact_identity(
    *,
    embedding: EmbeddingIdentity,
    project_root: Path,
) -> EmbeddingArtifactIdentity:
    """按最终 embedding 分类生成本地锁、provider-managed、N/A 或 pending。"""

    if embedding.identity_status == "not_applicable":
        return _empty_embedding_artifact("not_applicable")
    if embedding.identity_status == "pending":
        return _empty_embedding_artifact("pending")
    if embedding.revision_status != "local_content_locked":
        return _empty_embedding_artifact("provider_managed_unpinned")
    if embedding.model is None:
        raise ConfigurationError("local embedding identity requires a model path")
    receipt = build_local_minilm_asset_receipt(
        project_root=project_root,
        logical_path=embedding.model,
    )
    if embedding.dimension != receipt.dimension:
        raise ConfigurationError(
            "local embedding model dimension does not match build declaration"
        )
    return EmbeddingArtifactIdentity(
        status="local_locked",
        closure_schema_version=LOCAL_EMBEDDING_CLOSURE_SCHEMA_VERSION,
        logical_path=receipt.logical_path,
        local_content_sha256=receipt.local_content_sha256,
        tokenizer_sha256=receipt.tokenizer_sha256,
        tokenizer_name=receipt.tokenizer_name,
        tokenizer_max_length=receipt.tokenizer_max_length,
        tokenizer_lowercase=receipt.tokenizer_lowercase,
        sentence_transformers_version=receipt.sentence_transformers_version,
        transformers_version=receipt.transformers_version,
    )


def build_method_run_identity(
    *,
    profile_name: str,
    profile_section: str,
    answer_builder: str,
    build_identity: BuildIdentityDeclaration,
    project_root: Path,
) -> MethodRunIdentity:
    """把当前 profile 选择与注册表 build 声明组合成新 run 身份。"""

    return MethodRunIdentity(
        contract_version=RUN_IDENTITY_CONTRACT_VERSION,
        profile_name=profile_name,
        profile_section=profile_section,
        answer_builder=answer_builder,
        build=build_identity,
        embedding_artifact=build_embedding_artifact_identity(
            embedding=build_identity.embedding,
            project_root=project_root,
        ),
    )


__all__ = [
    "BuildIdentityDeclaration",
    "EmbeddingArtifactIdentity",
    "EmbeddingArtifactStatus",
    "EmbeddingIdentity",
    "EmbeddingProfile",
    "ImplementationVariant",
    "MethodRunIdentity",
    "RUN_IDENTITY_CONTRACT_VERSION",
    "RunIdentityContractVersion",
    "build_method_run_identity",
    "build_embedding_artifact_identity",
    "validate_build_identity",
    "validate_embedding_artifact_identity",
    "validate_embedding_identity",
    "validate_method_embedding_artifact_alignment",
]
