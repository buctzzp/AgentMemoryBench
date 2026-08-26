"""artifact-only retrieval evaluator 的公共装载与身份校验。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memory_benchmark.core import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl

from ..gold_evidence_groups import require_manifest_gold_evidence_contract_v1
from ..retrieval_evidence import require_manifest_retrieval_evidence_contract_v1


@dataclass(frozen=True)
class RetrievalArtifacts:
    """一次 retrieval 评测所需的三类对齐 artifact。"""

    answer_records: list[dict[str, Any]]
    private_records: list[dict[str, Any]]
    public_records: list[dict[str, Any]]
    private_by_id: dict[Any, dict[str, Any]]
    category_by_id: dict[Any, Any]


def load_retrieval_artifacts(
    *,
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    mismatch_error: str,
) -> RetrievalArtifacts:
    """先过两道版本门，再装载并严格对齐三类 question artifact。"""

    require_manifest_gold_evidence_contract_v1(manifest)
    require_manifest_retrieval_evidence_contract_v1(manifest)
    answers = read_jsonl(paths.answer_prompts_path)
    private = read_jsonl(paths.evaluator_private_labels_path)
    public = read_jsonl(paths.public_questions_path)
    private, public = _align_completed_question_records(
        answer_records=answers,
        private_records=private,
        public_records=public,
        mismatch_error=mismatch_error,
    )
    return RetrievalArtifacts(
        answer_records=answers,
        private_records=private,
        public_records=public,
        private_by_id={record["question_id"]: record for record in private},
        category_by_id={
            record["question_id"]: record.get("category") for record in public
        },
    )


def _align_completed_question_records(
    *,
    answer_records: list[dict[str, Any]],
    private_records: list[dict[str, Any]],
    public_records: list[dict[str, Any]],
    mismatch_error: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """校验完整 cohort 标签，并投影到本批已完成 question。

    formal run 会先写出所选 cohort 的完整 public/private 标签，再由
    `conversation_budget` 分批追加 answer artifact。因此 private/public 必须彼此
    完全一致，但允许它们包含尚未回答的未来 question；每条已完成 answer 仍必须在
    两份标签中唯一存在。
    """

    answer_ids = [record.get("question_id") for record in answer_records]
    private_ids = [record.get("question_id") for record in private_records]
    public_ids = [record.get("question_id") for record in public_records]
    if (
        any(
            not isinstance(question_id, str) or not question_id.strip()
            for question_id in (*answer_ids, *private_ids, *public_ids)
        )
        or len(answer_ids) != len(set(answer_ids))
        or len(private_ids) != len(set(private_ids))
        or len(public_ids) != len(set(public_ids))
        or set(private_ids) != set(public_ids)
        or not set(answer_ids).issubset(set(private_ids))
    ):
        raise ConfigurationError(mismatch_error)
    private_by_id = {
        record["question_id"]: record for record in private_records
    }
    public_by_id = {
        record["question_id"]: record for record in public_records
    }
    return (
        [private_by_id[question_id] for question_id in answer_ids],
        [public_by_id[question_id] for question_id in answer_ids],
    )


__all__ = ["RetrievalArtifacts", "load_retrieval_artifacts"]
