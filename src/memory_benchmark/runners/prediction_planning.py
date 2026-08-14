"""Prediction 的范围选择、checkpoint 状态解释与工作计划。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memory_benchmark.core import Conversation, Dataset, Question
from memory_benchmark.core.exceptions import ConfigurationError


@dataclass(frozen=True)
class PredictionRunPolicy:
    """控制一次通用回复生成运行的公开策略。

    字段:
        max_workers: conversation 级最大并发数。
        conversation_ids: 可选 conversation 白名单；为空时选择全部。
        question_limit_per_conversation: 每个 conversation 最多回答的问题数。
        max_new_conversations: 本次命令最多推进多少个未完成 conversation；不属于
            实验 identity，可在 resume 命令之间变化。
        retry_failed_conversations: 是否把上次已标记 failed 的 conversation 重新纳入
            本次工作计划；默认 False，避免失败 conversation 在 resume 时反复空烧 API。
        max_consecutive_failures: 单个 worker 连续 conversation 失败熔断阈值；达到后
            停止该 worker 后续 conversation，避免配置或网络系统性异常时批量空烧。
        resume: 是否允许复用当前 run_id 的兼容 checkpoint。
        progress_enabled: 是否在终端渲染 Rich 进度条。
    """

    max_workers: int = 1
    conversation_ids: tuple[str, ...] | None = None
    question_limit_per_conversation: int | None = None
    max_new_conversations: int | None = None
    retry_failed_conversations: bool = False
    max_consecutive_failures: int | None = 3
    resume: bool = False
    progress_enabled: bool = True

    def __post_init__(self) -> None:
        """校验调度参数，避免无效配置进入长实验。"""

        if self.max_workers < 1:
            raise ConfigurationError("Prediction max_workers must be at least 1")
        if (
            self.question_limit_per_conversation is not None
            and self.question_limit_per_conversation < 1
        ):
            raise ConfigurationError(
                "question_limit_per_conversation must be at least 1"
            )
        if self.max_new_conversations is not None and self.max_new_conversations < 1:
            raise ConfigurationError("max_new_conversations must be at least 1")
        if (
            self.max_consecutive_failures is not None
            and self.max_consecutive_failures < 1
        ):
            raise ConfigurationError("max_consecutive_failures must be at least 1")


@dataclass(frozen=True)
class _ConversationWorkItem:
    """本次命令要处理的单个 conversation 工作项。"""

    conversation: Conversation
    needs_ingest: bool
    pending_questions: tuple[Question, ...]


@dataclass(frozen=True)
class _PredictionWorkPlan:
    """本次命令裁剪后的 prediction 工作计划。"""

    items: tuple[_ConversationWorkItem, ...]
    conversation_order: tuple[str, ...]
    selected_questions: dict[str, list[Question]]
    question_order: tuple[str, ...]
    completed_question_ids: frozenset[str]
    ingested_conversation_ids: frozenset[str]
    skipped_failed_conversation_ids: tuple[str, ...]
    dataset_conversation_count: int
    budget_exhausted: bool


_STATUS_PENDING = "pending"
_STATUS_INGESTED = "ingested"
_STATUS_COMPLETED = "completed"
_STATUS_FAILED_INGEST = "failed_ingest"
_STATUS_FAILED_ANSWER = "failed_answer"


def _conversation_state_status(state: dict[str, Any]) -> str:
    """读取 conversation 状态，并兼容旧 `failed + ingested` checkpoint。"""

    status = str(state.get("status", _STATUS_PENDING))
    if status == "failed":
        if state.get("ingested") is True:
            return _STATUS_FAILED_ANSWER
        return _STATUS_FAILED_INGEST
    return status


def _conversation_is_ingested(state: dict[str, Any]) -> bool:
    """判断 conversation 是否已完成 add，可直接进入 answer 阶段。"""

    status = _conversation_state_status(state)
    return (
        status
        in {
            _STATUS_INGESTED,
            _STATUS_COMPLETED,
            _STATUS_FAILED_ANSWER,
        }
        or state.get("ingested") is True
    )


def _select_conversations(
    dataset: Dataset,
    policy: PredictionRunPolicy,
) -> list[Conversation]:
    """按 policy 选择 conversation，并拒绝不存在的显式 id。"""

    by_id = {
        conversation.conversation_id: conversation
        for conversation in dataset.conversations
    }
    if policy.conversation_ids is None:
        return list(dataset.conversations)

    missing = [
        conversation_id
        for conversation_id in policy.conversation_ids
        if conversation_id not in by_id
    ]
    if missing:
        raise ConfigurationError(
            f"Unknown conversation_ids in prediction policy: {', '.join(missing)}"
        )
    return [by_id[conversation_id] for conversation_id in policy.conversation_ids]


def _selected_questions(
    conversations: list[Conversation],
    policy: PredictionRunPolicy,
) -> dict[str, list[Question]]:
    """返回每个 conversation 本次需要回答的原始公开问题范围。"""

    return {
        conversation.conversation_id: list(
            conversation.questions[: policy.question_limit_per_conversation]
            if policy.question_limit_per_conversation is not None
            else conversation.questions
        )
        for conversation in conversations
    }


def _build_prediction_work_plan(
    *,
    conversations: list[Conversation],
    selected_questions: dict[str, list[Question]],
    conversation_status: dict[str, Any],
    prediction_records: dict[str, dict[str, Any]],
    policy: PredictionRunPolicy,
) -> _PredictionWorkPlan:
    """根据持久化状态和本次预算生成实际要执行的工作计划。

    `max_new_conversations` 只限制本次命令推进多少个未完成 conversation，不改变
    manifest identity。已完成 conversation 不占预算；已完成 add 但仍有未答问题的
    conversation 会占预算并只进入 answer 阶段。
    """

    selected_question_ids = {
        question.question_id
        for conversation in conversations
        for question in selected_questions[conversation.conversation_id]
    }
    completed_question_ids = frozenset(
        question_id
        for question_id in prediction_records
        if question_id in selected_question_ids
    )
    ingested_conversation_ids = frozenset(
        conversation.conversation_id
        for conversation in conversations
        if _conversation_is_ingested(
            conversation_status.get(conversation.conversation_id, {})
        )
    )
    question_order = tuple(
        question.question_id
        for conversation in conversations
        for question in selected_questions[conversation.conversation_id]
    )
    conversation_order = tuple(
        conversation.conversation_id for conversation in conversations
    )

    items: list[_ConversationWorkItem] = []
    skipped_failed_conversation_ids: list[str] = []
    unfinished_seen = 0
    budget_exhausted = False
    for conversation in conversations:
        conversation_id = conversation.conversation_id
        conversation_state = conversation_status.get(conversation_id, {})
        status = _conversation_state_status(conversation_state)
        if status == _STATUS_FAILED_INGEST:
            if policy.retry_failed_conversations:
                raise ConfigurationError(
                    f"Cannot retry conversation '{conversation_id}' after "
                    "failed ingest without clean retry support"
                )
            skipped_failed_conversation_ids.append(conversation_id)
            continue
        if status == _STATUS_FAILED_ANSWER and not policy.retry_failed_conversations:
            skipped_failed_conversation_ids.append(conversation_id)
            continue
        pending_questions = tuple(
            question
            for question in selected_questions[conversation_id]
            if question.question_id not in completed_question_ids
        )
        needs_ingest = conversation_id not in ingested_conversation_ids
        if not needs_ingest and not pending_questions:
            continue
        if (
            policy.max_new_conversations is not None
            and unfinished_seen >= policy.max_new_conversations
        ):
            budget_exhausted = True
            continue
        unfinished_seen += 1
        items.append(
            _ConversationWorkItem(
                conversation=conversation,
                needs_ingest=needs_ingest,
                pending_questions=pending_questions,
            )
        )

    return _PredictionWorkPlan(
        items=tuple(items),
        conversation_order=conversation_order,
        selected_questions=selected_questions,
        question_order=question_order,
        completed_question_ids=completed_question_ids,
        ingested_conversation_ids=ingested_conversation_ids,
        skipped_failed_conversation_ids=tuple(skipped_failed_conversation_ids),
        dataset_conversation_count=len(conversations),
        budget_exhausted=budget_exhausted,
    )


__all__ = ["PredictionRunPolicy"]
