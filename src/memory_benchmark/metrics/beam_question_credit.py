"""BEAM 逐题三档聚合 credit 的纯确定性内核。"""

from __future__ import annotations

import math
from typing import Iterable

from memory_benchmark.core import ConfigurationError


BEAM_QUESTION_CREDIT_CONTRACT_VERSION = "beam-question-credit-v1"
BEAM_QUESTION_CREDIT_VALUES = frozenset({0.0, 0.5, 1.0})
BEAM_ORDINARY_QUESTION_CREDIT_PROFILE = (
    "deterministic_rubric_items_all_mixed_none_v1"
)


def require_beam_question_credit(value: object, *, label: str) -> float:
    """校验 BEAM 聚合 credit 必须精确属于 ``{0, 0.5, 1}``。"""

    if isinstance(value, bool) or type(value) not in (int, float):
        raise ConfigurationError(f"{label} must be numeric 0, 0.5, or 1")
    score = float(value)
    if not math.isfinite(score) or score not in BEAM_QUESTION_CREDIT_VALUES:
        raise ConfigurationError(f"{label} must be exactly 0, 0.5, or 1")
    return score


def ordinary_beam_question_credit(item_scores: Iterable[object]) -> float:
    """把普通 BEAM 题的 rubric-item 分数规约为整题 ``0/0.5/1``。

    全部 item 完全满足才记 1，全部不满足记 0，其余任何混合或局部满足均记 0.5。
    """

    scores = tuple(
        require_beam_question_credit(value, label="BEAM rubric item score")
        for value in item_scores
    )
    if not scores:
        raise ConfigurationError("BEAM question credit requires non-empty rubric items")
    if all(score == 1.0 for score in scores):
        return 1.0
    if all(score == 0.0 for score in scores):
        return 0.0
    return 0.5


__all__ = [
    "BEAM_QUESTION_CREDIT_CONTRACT_VERSION",
    "BEAM_QUESTION_CREDIT_VALUES",
    "BEAM_ORDINARY_QUESTION_CREDIT_PROFILE",
    "ordinary_beam_question_credit",
    "require_beam_question_credit",
]
