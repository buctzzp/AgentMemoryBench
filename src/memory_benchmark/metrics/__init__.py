"""纯指标内核层。

这里只放不读取 benchmark、method、artifact 或配置的确定性公式。资格、gold view、
空值政策与报告结构留在 evaluator 层。
"""

from .beam_question_credit import (
    BEAM_ORDINARY_QUESTION_CREDIT_PROFILE,
    BEAM_QUESTION_CREDIT_CONTRACT_VERSION,
    BEAM_QUESTION_CREDIT_VALUES,
    ordinary_beam_question_credit,
    require_beam_question_credit,
)
from .ranking import (
    discounted_cumulative_gain,
    group_first_hit_rank,
    group_rank_metrics_at_k,
    ranked_source_ids,
)
from .retrieval import (
    RecallAtKResult,
    group_is_hit,
    group_recall_score,
    recall_at_k,
    selected_retrieval_items,
    top_k_source_ids,
)
from .text import (
    ANSWER_TEXT_PACK_VERSION,
    is_contiguous_token_subsequence,
    normalize_answer,
    normalized_tokens,
)

__all__ = [
    "ANSWER_TEXT_PACK_VERSION",
    "BEAM_ORDINARY_QUESTION_CREDIT_PROFILE",
    "BEAM_QUESTION_CREDIT_CONTRACT_VERSION",
    "BEAM_QUESTION_CREDIT_VALUES",
    "RecallAtKResult",
    "discounted_cumulative_gain",
    "group_first_hit_rank",
    "group_is_hit",
    "group_rank_metrics_at_k",
    "group_recall_score",
    "is_contiguous_token_subsequence",
    "normalize_answer",
    "normalized_tokens",
    "ordinary_beam_question_credit",
    "ranked_source_ids",
    "recall_at_k",
    "require_beam_question_credit",
    "selected_retrieval_items",
    "top_k_source_ids",
]
