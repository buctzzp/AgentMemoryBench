"""Prediction runner 的 manifest、resume 与 provider 生命周期预检。

本模块只处理运行前的公开身份、恢复兼容和 provider 协议边界，不执行记忆写入、
问题回答或并行调度。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core import Conversation, Dataset, Question
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider, BaseMemorySystem
from memory_benchmark.core.provider_bridge import LegacyProviderBridge
from memory_benchmark.core.provider_protocol import MemoryProvider
from memory_benchmark.core.validators import validate_dataset, validate_no_private_keys
from memory_benchmark.observability import RunContext
from memory_benchmark.observability.efficiency import (
    EfficiencyCollector,
    ModelDescriptor,
    RetrievalObservationContract,
)
from memory_benchmark.runners.conversation_qa import (
    _make_public_conversation,
    _make_public_question,
)
from memory_benchmark.runners.prediction_planning import (
    PredictionRunPolicy,
    _STATUS_FAILED_INGEST,
    _STATUS_PENDING,
    _conversation_state_status,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    build_dataset_fingerprint,
    evaluator_private_label_record,
    public_question_record,
)
from memory_benchmark.utils.run_logger import RunLogger


_PredictionSystem = BaseMemorySystem | BaseMemoryProvider | MemoryProvider


def _prepare_clean_failed_ingest_retries(
    *,
    conversations: list[Conversation],
    conversation_status: dict[str, Any],
    policy: PredictionRunPolicy,
    clean_failed_ingest_conversation: (
        Callable[[Conversation, dict[str, Any]], None] | None
    ),
    paths: ExperimentPaths,
    logger: RunLogger,
) -> tuple[str, ...]:
    """在生成 work plan 前清理可安全重试的 failed_ingest conversation。

    输入:
        conversations: 本次 run 选择的原始 conversation；调用 clean hook 前会转换为
            public conversation，避免泄露 gold/evidence。
        conversation_status: 持久化 conversation 状态，会被原地更新。
        policy: 当前 resume/retry 策略。
        clean_failed_ingest_conversation: method 侧证明安全的清理 hook。
        paths: 当前 run 标准路径，用于清理后立即持久化 checkpoint。
        logger: 结构化事件日志。

    输出:
        tuple[str, ...]: 本次已清理的 conversation id。无 clean hook 时不改变状态，
        后续 work plan 仍会 fail closed。
    """

    if not policy.retry_failed_conversations:
        return ()
    if clean_failed_ingest_conversation is None:
        return ()

    cleaned_conversation_ids: list[str] = []
    for conversation in conversations:
        conversation_id = conversation.conversation_id
        state = conversation_status.get(conversation_id, {})
        if _conversation_state_status(state) != _STATUS_FAILED_INGEST:
            continue

        clean_failed_ingest_conversation(
            _make_public_conversation(conversation),
            dict(state),
        )
        conversation_status[conversation_id] = {
            "status": _STATUS_PENDING,
            "ingested": False,
            "retry_cleaned": True,
            "previous_status": state,
        }
        cleaned_conversation_ids.append(conversation_id)
        logger.log_event(
            "failed_ingest_cleaned_for_retry",
            {"conversation_id": conversation_id},
        )

    if cleaned_conversation_ids:
        atomic_write_json(paths.conversation_status_path, conversation_status)

    return tuple(cleaned_conversation_ids)


def _build_manifest(
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_policy: dict[str, object] | None,
    benchmark_variant: str,
    run_scope: RunScope,
    dataset_fingerprint: dict[str, Any],
    efficiency_observability: dict[str, object] | None = None,
) -> dict[str, Any]:
    """构造用于 resume 兼容检查的公开 manifest。"""

    policy_payload = {
        "max_workers": policy.max_workers,
        "conversation_ids": (
            list(policy.conversation_ids)
            if policy.conversation_ids is not None
            else None
        ),
    }
    manifest = {
        "schema_version": 2,
        "runner": "generic_conversation_qa_prediction",
        "run_id": run_context.run_id,
        "benchmark_name": run_context.benchmark_name,
        "method_name": run_context.method_name,
        "model_name": run_context.model_name,
        "dataset_sha256": dataset_fingerprint["dataset_sha256"],
        "source_fingerprint_sha256": dataset_fingerprint[
            "source_fingerprint_sha256"
        ],
        "benchmark_variant": benchmark_variant,
        "run_scope": run_scope.value,
        "policy": policy_payload,
        "method": method_manifest,
    }
    if efficiency_observability is not None:
        manifest["efficiency_observability"] = efficiency_observability
    if benchmark_policy is not None:
        manifest["benchmark_policy"] = benchmark_policy
    return manifest


def validate_gold_evidence_contract_alignment(
    *,
    dataset: Dataset,
    benchmark_policy: dict[str, object] | None,
) -> None:
    """交叉校验 benchmark policy 声明与 dataset gold label 的 contract 版本。

    输入:
        dataset: 本次运行的完整统一数据集（含私有 gold_answers）。
        benchmark_policy: 已注册 benchmark 的 policy manifest；未注册（legacy/
            测试自定义路径）为 None 时，只允许全部 gold label 都未声明契约版本。

    输出:
        None。任何一侧声明 v1 而另一侧缺失、或版本非法时抛 ConfigurationError；
        本函数必须在创建目录、构造 method factory 或调用真实 API 之前执行。
    """

    if benchmark_policy is not None and not isinstance(benchmark_policy, dict):
        raise ConfigurationError("benchmark_policy must be a dict or None")
    declared_version = (
        None
        if benchmark_policy is None
        else benchmark_policy.get("gold_evidence_contract_version")
    )
    if declared_version not in (None, "v1"):
        raise ConfigurationError(
            "benchmark_policy gold_evidence_contract_version must be None or "
            f"'v1', got {declared_version!r}"
        )
    for conversation in dataset.conversations:
        for question in conversation.questions:
            gold = conversation.gold_answers.get(question.question_id)
            label_version = (
                None
                if gold is None
                else getattr(gold, "gold_evidence_contract_version", None)
            )
            if benchmark_policy is None:
                if label_version is not None:
                    raise ConfigurationError(
                        f"{question.question_id}: gold label declares gold evidence "
                        f"contract {label_version!r} but benchmark_policy is absent; "
                        "refuse to run with mixed versions"
                    )
                continue
            if declared_version == "v1":
                if gold is None:
                    raise ConfigurationError(
                        f"{question.question_id}: benchmark declares gold evidence "
                        "contract v1 but the public question has no gold label"
                    )
                if label_version != "v1":
                    raise ConfigurationError(
                        f"{question.question_id}: benchmark declares gold evidence "
                        "contract v1 but the gold label declares "
                        f"{label_version!r}; refuse to run with mixed versions"
                    )
            elif label_version is not None:
                raise ConfigurationError(
                    f"{question.question_id}: gold label declares gold evidence "
                    "contract v1 but the benchmark policy does not; refuse to run "
                    "with mixed versions"
                )


def _build_prediction_resume_artifacts(
    *,
    dataset: Dataset,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    benchmark_policy: dict[str, object] | None = None,
    source_paths: tuple[str | Path, ...] = (),
    efficiency_collector: EfficiencyCollector | None = None,
    model_inventory: tuple[ModelDescriptor, ...] = (),
    instrumentation_identity: dict[str, object] | None = None,
    retrieval_observation_contract: RetrievalObservationContract | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """构造 resume 校验所需的数据集指纹与公开 manifest。"""

    validate_dataset(dataset)
    validate_gold_evidence_contract_alignment(
        dataset=dataset,
        benchmark_policy=benchmark_policy,
    )
    _validate_public_manifest(method_manifest)
    validated_variant = _validate_concrete_benchmark_variant(benchmark_variant)
    validated_run_scope = _validate_run_scope(run_scope)
    dataset_fingerprint = build_dataset_fingerprint(
        dataset=dataset,
        source_paths=[Path(path) for path in source_paths],
    )
    efficiency_observability = _build_efficiency_observability_manifest(
        run_context=run_context,
        efficiency_collector=efficiency_collector,
        model_inventory=model_inventory,
        instrumentation_identity=instrumentation_identity,
        retrieval_observation_contract=retrieval_observation_contract,
    )
    manifest = _build_manifest(
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
        benchmark_policy=benchmark_policy,
        benchmark_variant=validated_variant,
        run_scope=validated_run_scope,
        dataset_fingerprint=dataset_fingerprint,
        efficiency_observability=efficiency_observability,
    )
    return dataset_fingerprint, manifest


def _preflight_prediction_run(
    *,
    dataset: Dataset,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    benchmark_policy: dict[str, object] | None = None,
    source_paths: tuple[str | Path, ...] = (),
    efficiency_collector: EfficiencyCollector | None = None,
    model_inventory: tuple[ModelDescriptor, ...] = (),
    instrumentation_identity: dict[str, object] | None = None,
    retrieval_observation_contract: RetrievalObservationContract | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """只读预检 run manifest 与 resume 身份，不创建目录也不写文件。"""

    dataset_fingerprint, manifest = _build_prediction_resume_artifacts(
        dataset=dataset,
        run_context=run_context,
        policy=policy,
        method_manifest=method_manifest,
        benchmark_policy=benchmark_policy,
        benchmark_variant=benchmark_variant,
        run_scope=run_scope,
        source_paths=source_paths,
        efficiency_collector=efficiency_collector,
        model_inventory=model_inventory,
        instrumentation_identity=instrumentation_identity,
        retrieval_observation_contract=retrieval_observation_contract,
    )
    _validate_run_manifest_state(
        paths=ExperimentPaths(run_dir=run_context.run_dir.resolve()),
        manifest=manifest,
        resume=policy.resume,
    )
    return dataset_fingerprint, manifest


def _prepare_run(
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    resume: bool,
) -> None:
    """创建新 manifest，或在 resume 时验证关键配置完全一致。"""

    manifest_exists = paths.manifest_path.exists()
    _validate_run_manifest_state(paths=paths, manifest=manifest, resume=resume)
    if manifest_exists:
        return
    atomic_write_json(paths.manifest_path, manifest)
    redacted_config = {
        "runner": manifest["runner"],
        "policy": manifest["policy"],
        "method": manifest["method"],
    }
    if "efficiency_observability" in manifest:
        redacted_config["efficiency_observability"] = manifest[
            "efficiency_observability"
        ]
    atomic_write_json(paths.redacted_config_path, redacted_config)


def _build_efficiency_observability_manifest(
    *,
    run_context: RunContext,
    efficiency_collector: EfficiencyCollector | None,
    model_inventory: tuple[ModelDescriptor, ...],
    instrumentation_identity: dict[str, object] | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
) -> dict[str, object] | None:
    """构造启用观测时的不可变身份；关闭时保持旧 manifest 不变。"""

    enabled = efficiency_collector is not None and efficiency_collector.enabled
    if not enabled:
        if (
            model_inventory
            or instrumentation_identity is not None
            or retrieval_observation_contract is not None
        ):
            raise ConfigurationError(
                "Efficiency identity requires an enabled collector"
            )
        return None
    if efficiency_collector.run_id != run_context.run_id:
        raise ConfigurationError(
            "EfficiencyCollector run_id must match RunContext run_id"
        )
    if not model_inventory:
        raise ConfigurationError(
            "Enabled efficiency observability requires a model inventory"
        )
    model_ids = [descriptor.model_id for descriptor in model_inventory]
    if len(model_ids) != len(set(model_ids)):
        raise ConfigurationError(
            "Efficiency model inventory contains duplicate model_id"
        )
    if not isinstance(instrumentation_identity, dict) or not instrumentation_identity:
        raise ConfigurationError(
            "Enabled efficiency observability requires instrumentation identity"
        )
    _validate_public_manifest(instrumentation_identity)
    if not isinstance(
        retrieval_observation_contract,
        RetrievalObservationContract,
    ):
        raise ConfigurationError(
            "Enabled efficiency observability requires an explicit retrieval "
            "observation contract"
        )
    return {
        "enabled": True,
        "model_inventory": [
            descriptor.to_dict()
            for descriptor in sorted(
                model_inventory,
                key=lambda descriptor: descriptor.model_id,
            )
        ],
        "instrumentation_identity": instrumentation_identity,
        "retrieval_observation_contract": (
            retrieval_observation_contract.to_dict()
        ),
    }


def _validate_run_manifest_state(
    *,
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    resume: bool,
) -> None:
    """校验 run 目录的 manifest 是否允许本次新建或 resume。"""

    if paths.manifest_path.exists():
        existing = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
        if not resume:
            raise ConfigurationError(
                f"Run directory already has a manifest; use resume or a new run_id: "
                f"{paths.run_dir}"
            )
        if existing.get("schema_version") == 1:
            raise ConfigurationError(
                "Generic prediction manifest schema v1 artifacts remain usable for "
                "artifact-only evaluation, but cannot resume through the v2 "
                "registered prediction service; use a new run_id or a "
                "legacy-compatible entry."
            )
        if existing.get("source_fingerprint_sha256") != manifest.get(
            "source_fingerprint_sha256"
        ):
            raise ConfigurationError(
                "Resume source fingerprint mismatch: source file contents "
                "changed or are missing, or the existing manifest predates the "
                "content-only source fingerprint (ws02.6; older manifests "
                "hashed absolute paths into identity) — use a new run_id"
            )
        if not _manifests_match_for_resume(existing, manifest):
            raise ConfigurationError(
                "Resume manifest mismatch: dataset, method or run policy changed"
            )
        return
    if resume:
        raise ConfigurationError(
            f"Cannot resume because manifest is missing: {paths.manifest_path}"
        )


def _normalize_manifest_for_resume_compare(
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """去掉允许随命令变化的运行预算字段后再比较 manifest。

    `question_limit_per_conversation` 是本次命令预算，不属于实验身份。旧 manifest
    可能仍在 `policy` 中包含该字段，因此 resume 比较时需要忽略它。
    """

    normalized = json.loads(json.dumps(manifest))
    policy = normalized.get("policy")
    if isinstance(policy, dict):
        policy.pop("question_limit_per_conversation", None)
    return normalized


def _manifests_match_for_resume(
    existing: dict[str, Any],
    manifest: dict[str, Any],
) -> bool:
    """比较 resume manifest，并兼容 T3 前缺省的协议字段。"""

    existing_normalized = _normalize_manifest_for_resume_compare(existing)
    current_normalized = _normalize_manifest_for_resume_compare(manifest)
    existing_method = existing_normalized.get("method")
    current_method = current_normalized.get("method")
    if isinstance(existing_method, dict) and isinstance(current_method, dict):
        for key in (
            "protocol_version",
            "prompt_track",
            "profile",
            "provenance_granularity",
        ):
            if key not in existing_method or key not in current_method:
                existing_method.pop(key, None)
                current_method.pop(key, None)
    return existing_normalized == current_normalized


def _validate_concrete_benchmark_variant(benchmark_variant: str) -> str:
    """校验 concrete benchmark variant 已在命令层解析完成。"""

    if not isinstance(benchmark_variant, str):
        raise ConfigurationError("benchmark_variant must be a non-empty concrete value")
    normalized_variant = benchmark_variant.strip()
    if not normalized_variant or normalized_variant == "all":
        raise ConfigurationError("benchmark_variant must be a non-empty concrete value")
    return normalized_variant


def _validate_run_scope(run_scope: RunScope) -> RunScope:
    """校验 run_scope 使用强类型枚举，而不是宽松字符串。"""

    if not isinstance(run_scope, RunScope):
        raise ConfigurationError("run_scope must be a RunScope")
    return run_scope


def _cleanup_memory_provider(system: BaseMemorySystem | MemoryProvider) -> None:
    """对 v3 provider 调用一次 `cleanup()`，legacy system 保持原有语义不变。

    只有 `MemoryProvider` 声明了 `cleanup()` 钩子；旧 `BaseMemorySystem`
    （含 `_UnusedRootSystem`）没有该协议，必须原样跳过。调用点自身保证"恰好一次"，
    因此这里不吞异常：cleanup 失败必须可见，不能让 run 被写成成功。

    输入:
        system: 已规范化的被测系统。
    """

    if isinstance(system, MemoryProvider):
        system.cleanup()


def _prepare_memory_provider(
    system: BaseMemorySystem | MemoryProvider,
    run_context: Any,
) -> None:
    """对 v3 provider 调用一次 prepare；legacy system 保持原有语义。"""

    if isinstance(system, MemoryProvider):
        system.prepare(run_context)


def _normalize_memory_system(system: _PredictionSystem) -> BaseMemorySystem | MemoryProvider:
    """把旧 retrieve-first provider 规范化为 v3 MemoryProvider。"""

    if isinstance(system, MemoryProvider):
        return system
    if isinstance(system, BaseMemoryProvider):
        return LegacyProviderBridge(system)
    return system


def _method_manifest_with_protocol(
    *,
    method_manifest: dict[str, object],
    protocol_version: str = "",
    prompt_track: str = "native",
    system: BaseMemorySystem | MemoryProvider | None = None,
    provenance_granularity: str | None = None,
    retrieval_evidence_contract_version: str | None = None,
    consume_granularity: str | None = None,
) -> dict[str, object]:
    """按注册声明协议版本补充 manifest 协议身份字段。

    首选路径：显式 protocol_version（来自 MethodRegistration.protocol_version），
    保证 workers>1 路径中不需要真实 method 实例也能正确盖章。
    provenance_granularity 同样优先使用注册级静态声明；未声明时才读取实例。
    retrieval_evidence_contract_version 只由注册级静态声明提供（无实例回退），非空时
    写入 method manifest 作为 resume 身份，同样不依赖真实 method 实例。
    consume_granularity 优先使用与 factory 同源的注册级 resolver；未注册的真实 v3
    provider 可从实例补出。声明与实例同时存在时必须严格一致。
    回退路径：当 protocol_version 为空且 system 可用时，沿用旧 isinstance 推断，
    用于未通过注册表的测试/自定义路径向后兼容。
    """

    if not protocol_version:
        if system is not None and isinstance(system, MemoryProvider):
            protocol_version = (
                "v2-bridged"
                if isinstance(system, LegacyProviderBridge)
                else "v3"
            )
        else:
            return method_manifest
    normalized = dict(method_manifest)
    normalized.setdefault("protocol_version", protocol_version)
    normalized.setdefault("prompt_track", prompt_track)
    if "run_identity" not in normalized:
        normalized.setdefault("profile", {})
    if provenance_granularity is None and isinstance(system, MemoryProvider):
        provenance_granularity = system.provenance_granularity
    if provenance_granularity is not None:
        if provenance_granularity not in ("none", "session", "turn"):
            raise ConfigurationError(
                f"Provider declares unknown provenance_granularity="
                f"{provenance_granularity!r} (expected 'none', 'session' or "
                "'turn')."
            )
        normalized.setdefault("provenance_granularity", provenance_granularity)
    if retrieval_evidence_contract_version is not None:
        normalized.setdefault(
            "retrieval_evidence_contract_version",
            retrieval_evidence_contract_version,
        )
    manifest_consume_granularity = normalized.get("consume_granularity")
    if consume_granularity is None and isinstance(
        manifest_consume_granularity,
        str,
    ):
        consume_granularity = manifest_consume_granularity
    if (
        consume_granularity is None
        and isinstance(system, MemoryProvider)
        and not isinstance(system, LegacyProviderBridge)
    ):
        consume_granularity = system.consume_granularity
    if consume_granularity is not None:
        _validate_consume_granularity_value(consume_granularity)
        normalized.setdefault("consume_granularity", consume_granularity)
    if isinstance(system, MemoryProvider) and not isinstance(
        system,
        LegacyProviderBridge,
    ):
        _validate_consume_granularity(
            _manifest_consume_granularity(normalized),
            system,
        )
    return normalized


def _validate_consume_granularity_value(consume_granularity: str) -> None:
    """校验 manifest/provider 消费粒度是协议允许的 concrete 值。"""

    if consume_granularity not in {"turn", "pair", "session", "conversation"}:
        raise ConfigurationError(
            "consume_granularity must be turn, pair, session or conversation; "
            f"got {consume_granularity!r}"
        )


def _manifest_consume_granularity(
    method_manifest: dict[str, object],
) -> str | None:
    """严格读取 method manifest 的可选消费粒度。"""

    value = method_manifest.get("consume_granularity")
    if value is None:
        return None
    if not isinstance(value, str):
        raise ConfigurationError("method.consume_granularity must be a string")
    _validate_consume_granularity_value(value)
    return value


def _validate_consume_granularity(
    declared: str | None,
    system: BaseMemorySystem | MemoryProvider,
) -> None:
    """交叉校验 manifest 声明与真实 v3 provider 实例的消费粒度。"""

    if declared is None or not isinstance(system, MemoryProvider):
        return
    if isinstance(system, LegacyProviderBridge):
        return
    actual = system.consume_granularity
    _validate_consume_granularity_value(actual)
    if actual != declared:
        raise ConfigurationError(
            "Provider consume_granularity does not match method manifest: "
            f"declared={declared!r}, actual={actual!r}"
        )


def _validate_protocol_version(
    protocol_version: str,
    system: BaseMemorySystem | MemoryProvider,
) -> None:
    """交叉校验 method 声明的协议版本与实际实例类型一致，不符则 fail-fast。

    这保证注册声明的 protocol_version 不会因 factory 实现错误而产生不可复现的
    manifest，尤其在 isolated worker 路径中需要独立校验。

    当 protocol_version 为空字符串时跳过校验——这用于未通过注册表的测试/自定义路径。
    """

    if not protocol_version:
        return
    if protocol_version == "v3":
        if not isinstance(system, MemoryProvider):
            raise ConfigurationError(
                f"Method declares protocol_version='v3' but factory produced "
                f"{type(system).__name__} (expected MemoryProvider). "
                "Update the method adapter to implement MemoryProvider or fix "
                "the registration's protocol_version."
            )
        if isinstance(system, LegacyProviderBridge):
            raise ConfigurationError(
                "Method declares protocol_version='v3' but factory produced a "
                "LegacyProviderBridge (v2-bridged). If this method uses "
                "BaseMemoryProvider, set protocol_version='v2-bridged' in its "
                "registration."
            )
    elif protocol_version == "v2-bridged":
        if not isinstance(system, LegacyProviderBridge):
            raise ConfigurationError(
                f"Method declares protocol_version='v2-bridged' but factory "
                f"produced {type(system).__name__} (expected "
                "LegacyProviderBridge wrapping a BaseMemoryProvider)."
            )
    else:
        raise ConfigurationError(
            f"Unknown protocol_version: {protocol_version!r} (expected 'v3' or "
            "'v2-bridged'). Fix the method registration to avoid stamping an "
            "unreproducible protocol identity into the manifest."
        )


def _is_memory_provider(system: BaseMemorySystem | MemoryProvider) -> bool:
    """判断系统是否已经进入 v3 provider 路径。"""

    return isinstance(system, MemoryProvider)


def _write_input_artifacts(
    paths: ExperimentPaths,
    conversations: list[Conversation],
    selected_questions: dict[str, list[Question]],
) -> None:
    """原子写入公开问题与 evaluator-only 私有标签。"""

    public_records: list[dict[str, Any]] = []
    private_records: list[dict[str, Any]] = []
    for conversation in conversations:
        for source_question in selected_questions[conversation.conversation_id]:
            question = _make_public_question(source_question)
            public_records.append(public_question_record(question))
            private_records.append(
                evaluator_private_label_record(
                    conversation.gold_answers[question.question_id],
                    question.category,
                )
            )
    atomic_write_jsonl(paths.public_questions_path, public_records)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_records)


def _validate_public_manifest(payload: dict[str, object]) -> None:
    """拒绝 method manifest 中的 secret 和私有评测字段。"""

    validate_no_private_keys(payload)
    forbidden_fragments = ("api_key", "secret", "password")
    forbidden_token_keys = frozenset(
        {
            "token",
            "api_token",
            "access_token",
            "auth_token",
            "bearer_token",
            "id_token",
            "refresh_token",
        }
    )

    def walk(value: Any, path: str) -> None:
        """递归检查嵌套 manifest 的字段名称。"""

        if isinstance(value, dict):
            for key, child in value.items():
                normalized = str(key).lower()
                if any(fragment in normalized for fragment in forbidden_fragments) or (
                    normalized in forbidden_token_keys
                    or normalized.endswith("_token")
                    or normalized.endswith("-token")
                ):
                    raise ConfigurationError(
                        f"Method manifest contains a secret-like field: {path}.{key}"
                    )
                walk(child, f"{path}.{key}")
        elif isinstance(value, list | tuple):
            for index, child in enumerate(value):
                walk(child, f"{path}[{index}]")

    walk(payload, "$")


def _read_json_object(path: Path) -> dict[str, Any]:
    """读取 JSON 对象；文件不存在时返回空字典。"""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigurationError(f"Expected JSON object checkpoint: {path}")
    return payload
