"""检验分批 formal run 的 retrieval artifact 对齐合同。"""

from __future__ import annotations

import pytest

from memory_benchmark.core import ConfigurationError
from memory_benchmark.evaluators.common.artifact import (
    _align_completed_question_records,
)


def _record(question_id: str) -> dict[str, str]:
    """构造最小 question artifact 记录。"""

    return {"question_id": question_id}


def test_completed_answers_may_be_subset_of_full_selected_cohort() -> None:
    """conversation budget 首批只完成部分题时应按 answer 顺序投影标签。"""

    private, public = _align_completed_question_records(
        answer_records=[_record("q2"), _record("q1")],
        private_records=[_record("q1"), _record("q2"), _record("q3")],
        public_records=[_record("q3"), _record("q2"), _record("q1")],
        mismatch_error="mismatch",
    )

    assert [record["question_id"] for record in private] == ["q2", "q1"]
    assert [record["question_id"] for record in public] == ["q2", "q1"]


@pytest.mark.parametrize(
    ("answers", "private", "public"),
    [
        (["q1", "q1"], ["q1"], ["q1"]),
        (["q2"], ["q1"], ["q1"]),
        (["q1"], ["q1", "q2"], ["q1"]),
        ([""], [""], [""]),
    ],
)
def test_artifact_alignment_rejects_duplicate_missing_or_invalid_ids(
    answers: list[str],
    private: list[str],
    public: list[str],
) -> None:
    """重复、缺标签、cohort 漂移与空 ID 均应 fail-fast。"""

    with pytest.raises(ConfigurationError, match="mismatch"):
        _align_completed_question_records(
            answer_records=[_record(question_id) for question_id in answers],
            private_records=[_record(question_id) for question_id in private],
            public_records=[_record(question_id) for question_id in public],
            mismatch_error="mismatch",
        )
