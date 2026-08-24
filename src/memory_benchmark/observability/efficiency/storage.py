"""效率模型清单和 observation 的标准 artifact 存储。

本模块负责强类型 JSON/JSONL round-trip、确定性排序和 observation id 冲突检测。
它不负责创建 observation，也不计算聚合指标或费用。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Sequence

from memory_benchmark.core import ConfigurationError
from memory_benchmark.observability.efficiency.entities import (
    ConversationEfficiencyObservation,
    EfficiencyObservation,
    EfficiencyStage,
    EmbeddingCallObservation,
    FailedEfficiencyAttempt,
    LLMCallObservation,
    MeasurementSource,
    ModelDescriptor,
    QuestionEfficiencyObservation,
)
from memory_benchmark.storage.atomic import atomic_write_json, atomic_write_jsonl
from memory_benchmark.storage.experiment_paths import ExperimentPaths
from memory_benchmark.storage.jsonl import JsonlWriter, read_jsonl


@dataclass(frozen=True)
class EfficiencyArtifactStore:
    """一组 prediction 或 evaluator efficiency artifact 路径。"""

    model_inventory_path: Path
    observations_path: Path
    failed_attempts_path: Path
    _failed_attempt_lock: Lock = field(
        default_factory=Lock,
        compare=False,
        repr=False,
    )

    @classmethod
    def for_prediction(
        cls,
        paths: ExperimentPaths,
    ) -> "EfficiencyArtifactStore":
        """创建 prediction 阶段 artifact store。"""

        return cls(
            model_inventory_path=paths.prediction_model_inventory_path,
            observations_path=paths.prediction_efficiency_observations_path,
            failed_attempts_path=paths.prediction_failed_efficiency_attempts_path,
        )

    @classmethod
    def for_evaluator(
        cls,
        paths: ExperimentPaths,
        metric_name: str,
    ) -> "EfficiencyArtifactStore":
        """创建指定 evaluator 的独立 artifact store。"""

        return cls(
            model_inventory_path=paths.evaluator_model_inventory_path(metric_name),
            observations_path=paths.evaluator_efficiency_observations_path(
                metric_name
            ),
            failed_attempts_path=(
                paths.evaluator_failed_efficiency_attempts_path(metric_name)
            ),
        )

    def append_failed_attempt(self, attempt: FailedEfficiencyAttempt) -> None:
        """追加一次失败 scope 的成本事实，不与成功 artifact 一起回滚。

        失败很少发生，因此每次追加前读取现存 id 以拒绝重复或冲突；文件使用
        append-only JSONL，不会因后续 retry 改写先前尝试。
        """

        if not isinstance(attempt, FailedEfficiencyAttempt):
            raise ConfigurationError(
                "failed efficiency attempt must be FailedEfficiencyAttempt"
            )
        payload = attempt.to_dict()
        with self._failed_attempt_lock:
            existing = self.read_failed_attempts()
            if any(record.get("attempt_id") == attempt.attempt_id for record in existing):
                raise ConfigurationError(
                    "Efficiency attempt ledger has duplicate attempt_id: "
                    f"{attempt.attempt_id}"
                )
            JsonlWriter(self.failed_attempts_path).append(payload)

    def read_failed_attempts(self) -> list[dict[str, Any]]:
        """严格读取失败尝试账，并校验 schema、唯一 id 与固定完成度声明。"""

        try:
            records = read_jsonl(self.failed_attempts_path)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise ConfigurationError(
                f"Efficiency attempt JSONL is invalid: {self.failed_attempts_path}"
            ) from exc
        seen_ids: set[str] = set()
        for record in records:
            expected = {
                "schema_version",
                "attempt_id",
                "collector_session_id",
                "attempt_index",
                "outcome",
                "scope_type",
                "conversation_id",
                "question_id",
                "scope_discriminator",
                "error_type",
                "capture_completeness",
                "calls",
            }
            if set(record) != expected:
                raise ConfigurationError(
                    "Efficiency attempt fields do not match schema"
                )
            if record.get("schema_version") != 1 or record.get("outcome") != "failed":
                raise ConfigurationError(
                    "Efficiency attempt schema or outcome is invalid"
                )
            attempt_id = record.get("attempt_id")
            if not isinstance(attempt_id, str) or not attempt_id.strip():
                raise ConfigurationError("Efficiency attempt_id is invalid")
            if attempt_id in seen_ids:
                raise ConfigurationError(
                    f"Efficiency attempt ledger has duplicate attempt_id: {attempt_id}"
                )
            seen_ids.add(attempt_id)
            if record.get("capture_completeness") != (
                "caught_scope_exception_completed_model_calls_only"
            ):
                raise ConfigurationError(
                    "Efficiency attempt capture_completeness is invalid"
                )
            calls = record.get("calls")
            if not isinstance(calls, list):
                raise ConfigurationError("Efficiency attempt calls must be a list")
            for call in calls:
                if not isinstance(call, dict):
                    raise ConfigurationError(
                        "Efficiency attempt call must be an object"
                    )
                observation = _observation_from_record(call)
                if not isinstance(observation, (LLMCallObservation, EmbeddingCallObservation)):
                    raise ConfigurationError(
                        "Efficiency attempt calls must be model-call observations"
                    )
        return records

    def write_model_inventory(
        self,
        descriptors: Sequence[ModelDescriptor],
    ) -> None:
        """原子写入稳定排序的模型清单，并拒绝同 id 歧义。"""

        by_id: dict[str, ModelDescriptor] = {}
        for descriptor in descriptors:
            if descriptor.model_id in by_id:
                raise ConfigurationError(
                    f"Efficiency model inventory has duplicate model_id: "
                    f"{descriptor.model_id}"
                )
            by_id[descriptor.model_id] = descriptor
        payload = {
            "schema_version": 1,
            "models": [
                by_id[model_id].to_dict()
                for model_id in sorted(by_id)
            ],
        }
        if self.model_inventory_path.exists():
            existing = _read_json_object(self.model_inventory_path)
            if existing != payload:
                raise ConfigurationError(
                    "Efficiency model inventory conflicts with existing artifact"
                )
            return
        atomic_write_json(self.model_inventory_path, payload)

    def merge_observations(
        self,
        observations: Sequence[EfficiencyObservation],
    ) -> None:
        """按 observation_id 幂等合并，并拒绝同 id 不同内容。"""

        by_id = {
            observation.observation_id: observation
            for observation in self.read_observations()
        }
        for observation in observations:
            existing = by_id.get(observation.observation_id)
            if existing is not None:
                if existing.to_dict() != observation.to_dict():
                    raise ConfigurationError(
                        "Efficiency artifact has conflicting observation_id: "
                        f"{observation.observation_id}"
                    )
                continue
            by_id[observation.observation_id] = observation
        atomic_write_jsonl(
            self.observations_path,
            [
                by_id[observation_id].to_dict()
                for observation_id in sorted(by_id)
            ],
        )

    def read_observations(self) -> list[EfficiencyObservation]:
        """读取 JSONL 并重建强类型 observation。"""

        try:
            records = read_jsonl(self.observations_path)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            raise ConfigurationError(
                f"Efficiency observation JSONL is invalid: {self.observations_path}"
            ) from exc
        observations: list[EfficiencyObservation] = []
        seen_ids: set[str] = set()
        for record in records:
            observation = _observation_from_record(record)
            if observation.observation_id in seen_ids:
                raise ConfigurationError(
                    "Efficiency artifact has duplicate observation_id: "
                    f"{observation.observation_id}"
                )
            seen_ids.add(observation.observation_id)
            observations.append(observation)
        return observations


def _observation_from_record(
    record: dict[str, Any],
) -> EfficiencyObservation:
    """根据 observation_type 严格重建对应 dataclass。"""

    observation_type = record.get("observation_type")
    constructors = {
        "conversation_efficiency": _conversation_from_record,
        "question_efficiency": _question_from_record,
        "llm_call": _llm_from_record,
        "embedding_call": _embedding_from_record,
    }
    constructor = constructors.get(observation_type)
    if constructor is None:
        raise ConfigurationError(
            f"Unsupported efficiency observation_type: {observation_type!r}"
        )
    return constructor(record)


def _conversation_from_record(
    record: dict[str, Any],
) -> ConversationEfficiencyObservation:
    """重建 conversation 级 observation。"""

    payload = _payload_without_type(
        record,
        expected_keys={
            "observation_id",
            "conversation_id",
            "memory_build_total_latency_ms",
        },
    )
    return ConversationEfficiencyObservation(**payload)


def _question_from_record(
    record: dict[str, Any],
) -> QuestionEfficiencyObservation:
    """重建 question 级 observation。"""

    payload = _payload_without_type(
        record,
        expected_keys={
            "observation_id",
            "conversation_id",
            "question_id",
            "retrieval_latency_ms",
            "unsupported_reason",
            "injected_memory_context_tokens",
            "answer_generation_latency_ms",
        },
    )
    return QuestionEfficiencyObservation(**payload)


def _llm_from_record(record: dict[str, Any]) -> LLMCallObservation:
    """重建 LLM 调用 observation。"""

    payload = _payload_without_type(
        record,
        expected_keys={
            "observation_id",
            "stage",
            "model_id",
            "input_tokens",
            "output_tokens",
            "token_measurement_source",
            "conversation_id",
            "question_id",
        },
    )
    payload["stage"] = _parse_enum(
        EfficiencyStage,
        payload["stage"],
        "stage",
    )
    payload["token_measurement_source"] = _parse_enum(
        MeasurementSource,
        payload["token_measurement_source"],
        "token_measurement_source",
    )
    return LLMCallObservation(**payload)


def _embedding_from_record(
    record: dict[str, Any],
) -> EmbeddingCallObservation:
    """重建 embedding 调用 observation。"""

    payload = _payload_without_type(
        record,
        expected_keys={
            "observation_id",
            "stage",
            "model_id",
            "input_tokens",
            "latency_ms",
            "token_measurement_source",
            "latency_measurement_source",
            "conversation_id",
            "question_id",
        },
    )
    payload["stage"] = _parse_enum(
        EfficiencyStage,
        payload["stage"],
        "stage",
    )
    payload["token_measurement_source"] = _parse_enum(
        MeasurementSource,
        payload["token_measurement_source"],
        "token_measurement_source",
    )
    payload["latency_measurement_source"] = _parse_enum(
        MeasurementSource,
        payload["latency_measurement_source"],
        "latency_measurement_source",
    )
    return EmbeddingCallObservation(**payload)


def _payload_without_type(
    record: dict[str, Any],
    *,
    expected_keys: set[str],
) -> dict[str, Any]:
    """校验 JSONL 字段集合并移除 discriminator。"""

    actual_keys = set(record) - {"observation_type"}
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise ConfigurationError(
            "Efficiency observation fields do not match schema: "
            f"missing={missing}, extra={extra}"
        )
    return {
        key: value
        for key, value in record.items()
        if key != "observation_type"
    }


def _parse_enum(
    enum_type: type[EfficiencyStage] | type[MeasurementSource],
    value: Any,
    field_name: str,
) -> EfficiencyStage | MeasurementSource:
    """把 JSON 字符串转换为强类型枚举并包装错误。"""

    try:
        return enum_type(value)
    except (TypeError, ValueError):
        raise ConfigurationError(
            f"Efficiency observation {field_name} is invalid: {value!r}"
        ) from None


def _read_json_object(path: Path) -> dict[str, Any]:
    """读取模型清单 JSON 对象。"""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(
            f"Efficiency model inventory is invalid: {path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ConfigurationError(
            f"Efficiency model inventory must be a JSON object: {path}"
        )
    return payload


__all__ = ["EfficiencyArtifactStore"]
