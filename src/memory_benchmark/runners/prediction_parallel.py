"""Prediction runner 的 isolated worker 并行协调与故障隔离。

本模块只负责稳定分片、worker 生命周期、局部失败隔离及协调线程提交；实际 ingest、
retrieve/answer 与 manifest 规则由对应叶模块拥有。
"""

from __future__ import annotations

import traceback
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from threading import Event
from time import perf_counter_ns
from typing import Any, Callable

from memory_benchmark.core import (
    AnswerPromptResult,
    AnswerResult,
    Conversation,
    Question,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemoryProvider, BaseMemorySystem
from memory_benchmark.core.provider_protocol import MemoryProvider, RetrievalResult
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.methods.registry import MethodBuildContext
from memory_benchmark.observability import ProgressReporter, RunContext
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    EfficiencyObservation,
    RetrievalObservationContract,
)
from memory_benchmark.readers.answer import FrameworkAnswerReader
from memory_benchmark.runners.conversation_qa import (
    _make_public_conversation,
    _make_public_question,
)
from memory_benchmark.runners.prediction_answer import (
    _ConversationAnswerBatch,
    _answer_question_retrieve_first_or_reuse,
    _persist_answer_prompt_records,
    _transform_prediction_if_needed,
    _validate_prediction,
)
from memory_benchmark.runners.prediction_ingest import (
    _add_public_conversation_coarse,
    _merge_session_report_records,
    _persist_session_memory_reports,
)
from memory_benchmark.runners.prediction_observability import _elapsed_ms
from memory_benchmark.runners.prediction_planning import (
    PredictionRunPolicy,
    _ConversationWorkItem,
    _PredictionWorkPlan,
    _STATUS_COMPLETED,
    _STATUS_FAILED_ANSWER,
    _STATUS_FAILED_INGEST,
)
from memory_benchmark.runners.prediction_preflight import (
    _cleanup_memory_provider,
    _is_memory_provider,
    _normalize_memory_system,
    _prepare_memory_provider,
    _validate_consume_granularity,
    _validate_protocol_version,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    read_jsonl,
)
from memory_benchmark.utils.run_logger import RunLogger


_PredictionSystem = BaseMemorySystem | BaseMemoryProvider | MemoryProvider


@dataclass(frozen=True)
class _ConversationFailureBatch:
    """单个 isolated worker 捕获的 conversation 局部失败。

    字段:
        conversation_id: 失败 conversation id。
        stage: 失败阶段，例如 `isolated_worker`。
        error_type: 原始异常类型名。
        error: 原始异常消息。
        traceback_text: 完整 traceback，写入事件和 checkpoint 方便定位。
        observations: 失败前已采集的效率观测。
        predictions: 失败前已生成并校验通过的问题回答。
        retrievals: 失败前已生成并校验通过的 answer prompt 记录。
        ingested: 当前 conversation 的 memory state 是否已经写入完成。
    """

    conversation_id: str
    stage: str
    error_type: str
    error: str
    traceback_text: str
    observations: tuple[EfficiencyObservation, ...] = ()
    predictions: tuple[dict[str, Any], ...] = ()
    retrievals: tuple[dict[str, Any], ...] = ()
    session_reports: tuple[dict[str, Any], ...] = ()
    ingested: bool = False


class _ConversationWorkItemError(RuntimeError):
    """isolated worker 内某个 conversation 失败时携带定位信息。

    字段:
        conversation_id: 失败 conversation，用于写入 quarantine checkpoint。
        stage: 失败发生的 runner 阶段。
        original_error: 第三方 method 或 runner 抛出的原始异常。
    """

    def __init__(
        self,
        *,
        conversation_id: str,
        stage: str,
        original_error: Exception,
    ) -> None:
        """保存失败定位信息，同时保留原始异常消息方便外层匹配。"""

        super().__init__(str(original_error))
        self.conversation_id = conversation_id
        self.stage = stage
        self.original_error = original_error


def _split_into_chunks(
    items: list[Any],
    num_chunks: int,
) -> list[list[Any]]:
    """把 conversation 列表均匀分布到 num_chunks 个 chunk。

    最后剩余不足 num_chunks 的归入最后一个非满 chunk。
    """

    if num_chunks < 1:
        raise ConfigurationError("num_chunks must be at least 1")
    if num_chunks > len(items):
        num_chunks = len(items)
    chunks: list[list[Any]] = [[] for _ in range(num_chunks)]
    for idx, item in enumerate(items):
        chunks[idx % num_chunks].append(item)
    return chunks


def _split_work_items_by_stable_conversation_order(
    *,
    items: tuple[_ConversationWorkItem, ...],
    conversation_order: tuple[str, ...],
    num_workers: int,
) -> tuple[tuple[int, tuple[_ConversationWorkItem, ...]], ...]:
    """按完整 conversation 顺序稳定分配 isolated worker 工作项。

    `items` 只包含本次命令仍需推进的 conversation；resume 后它可能只剩一个
    conversation。如果直接对 `items` 重新分块，同一个 conversation 的 worker state
    目录会从 `worker_5` 变成 `worker_0`。因此 worker index 必须基于完整
    `conversation_order` 计算，保证同一 `run_id + max_workers + dataset` 下 state root
    稳定。
    """

    if num_workers < 1:
        raise ConfigurationError("num_workers must be at least 1")
    if not conversation_order:
        raise ConfigurationError("conversation_order cannot be empty")
    worker_count = min(num_workers, len(conversation_order))
    index_by_conversation = {
        conversation_id: index
        for index, conversation_id in enumerate(conversation_order)
    }
    chunks: dict[int, list[_ConversationWorkItem]] = {
        worker_idx: [] for worker_idx in range(worker_count)
    }
    for item in items:
        try:
            conversation_index = index_by_conversation[item.conversation.conversation_id]
        except KeyError as exc:
            raise ConfigurationError(
                "Work item conversation is missing from stable conversation order: "
                f"{item.conversation.conversation_id}"
            ) from exc
        worker_idx = conversation_index % worker_count
        chunks[worker_idx].append(item)
    return tuple(
        (worker_idx, tuple(chunk))
        for worker_idx, chunk in chunks.items()
        if chunk
    )


def _run_isolated_worker_pipeline(
    *,
    work_plan: _PredictionWorkPlan,
    system_factory: Callable[
        [MethodBuildContext],
        _PredictionSystem,
    ],
    build_context_template: MethodBuildContext,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    paths: ExperimentPaths,
    progress: ProgressReporter,
    logger: RunLogger,
    efficiency_collector: EfficiencyCollector | None,
    efficiency_store: EfficiencyArtifactStore | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
    prediction_records: dict[str, dict[str, Any]],
    conversation_status: dict[str, Any],
    question_status: dict[str, Any],
    question_order: list[str],
    run_id: str = "prediction-run",
    answer_reader: FrameworkAnswerReader | None = None,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ) = None,
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None = None,
    protocol_version: str = "",
    consume_granularity: str | None = None,
) -> None:
    """使用独立 method instance 并行处理 conversation 的 ingest 与 answer。

    每个 worker 创建自己的 method instance（storage 隔离到 worker_{idx}/），
    在内部串行 ingest + answer 分配给它的 conversation 子集。
    协调线程串行写入 artifact，避免竞态。
    """

    progress.set_stage("Ingest + answer", step_index=1, step_count=2)
    if any(paths.ingest_turn_checkpoints_dir.glob("*.json")):
        raise ConfigurationError(
            "Isolated worker prediction cannot resume turn-level ingest checkpoints"
        )
    _conv_progress_total = (
        len(work_plan.ingested_conversation_ids) + len(work_plan.items)
    )
    _question_progress_total = (
        len(work_plan.completed_question_ids)
        + sum(len(item.pending_questions) for item in work_plan.items)
    )
    if not work_plan.items:
        progress.update_conversations(
            completed=len(work_plan.ingested_conversation_ids),
            total=_conv_progress_total,
            current_conversation_id=None,
        )
        progress.update_questions(
            completed=len(work_plan.completed_question_ids),
            total=_question_progress_total,
            current_conversation_id=None,
            current_question_id=None,
        )
        return

    chunks = _split_work_items_by_stable_conversation_order(
        items=work_plan.items,
        conversation_order=work_plan.conversation_order,
        num_workers=policy.max_workers,
    )
    conversation_ingested: int = len(work_plan.ingested_conversation_ids)
    question_answered: int = len(work_plan.completed_question_ids)
    cancellation_event = Event()
    answer_prompt_records = {
        record["question_id"]: record
        for record in read_jsonl(
            paths.answer_prompts_path,
            recover_torn_tail=policy.resume,
        )
    }
    session_report_records = read_jsonl(paths.session_memory_reports_path)

    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        future_to_chunk: dict[
            Future[
                tuple[_ConversationAnswerBatch | _ConversationFailureBatch, ...]
            ],
            int,
        ] = {}
        for worker_idx, chunk in chunks:
            worker_storage = (
                build_context_template.storage_root / f"worker_{worker_idx}"
            )
            completed_for_chunk = tuple(
                _make_public_conversation(item.conversation)
                for item in chunk
                if not item.needs_ingest
            )
            worker_context = MethodBuildContext(
                config=build_context_template.config,
                openai_settings=build_context_template.openai_settings,
                path_settings=build_context_template.path_settings,
                storage_root=worker_storage,
                benchmark_name=build_context_template.benchmark_name,
                completed_conversations=completed_for_chunk,
                efficiency_collector=build_context_template.efficiency_collector,
            )
            future = executor.submit(
                _isolated_worker,
                worker_context,
                run_context,
                system_factory,
                tuple(chunk),
                run_id,
                efficiency_collector,
                retrieval_observation_contract,
                answer_reader,
                unified_prompt_builder,
                prediction_transform,
                answer_prompt_records,
                cancellation_event,
                policy.max_consecutive_failures,
                protocol_version=protocol_version,
                consume_granularity=consume_granularity,
            )
            future_to_chunk[future] = worker_idx

        for future in as_completed(future_to_chunk):
            try:
                batches = future.result()
            except Exception as exc:
                cancellation_event.set()
                for pending_future in future_to_chunk:
                    if pending_future is not future:
                        pending_future.cancel()
                if isinstance(exc, _ConversationWorkItemError):
                    logged_error = exc.original_error
                    failed_conversation_id = exc.conversation_id
                    conversation_status[exc.conversation_id] = {
                        "status": _STATUS_FAILED_INGEST,
                        "stage": exc.stage,
                        "error_type": type(logged_error).__name__,
                        "error": str(logged_error),
                        "ingested": False,
                        "worker_idx": future_to_chunk[future],
                    }
                    atomic_write_json(
                        paths.conversation_status_path,
                        conversation_status,
                    )
                else:
                    logged_error = exc
                    failed_conversation_id = None
                logger.log_event(
                    "isolated_worker_failed",
                    {
                        "worker_idx": future_to_chunk[future],
                        "conversation_id": failed_conversation_id,
                        "error_type": type(logged_error).__name__,
                        "error": str(logged_error),
                        "traceback": "".join(
                            traceback.format_exception(
                                type(exc),
                                exc,
                                exc.__traceback__,
                            )
                        ),
                    },
                )
                if isinstance(exc, _ConversationWorkItemError):
                    raise exc.original_error from exc
                raise
            if efficiency_store is not None:
                for batch in batches:
                    efficiency_store.merge_observations(batch.observations)
            for batch in batches:
                if batch.session_reports:
                    session_report_records = _merge_session_report_records(
                        existing=session_report_records,
                        conversation_id=batch.conversation_id,
                        new_reports=batch.session_reports,
                    )
                for answer_prompt_record in batch.retrievals:
                    answer_prompt_records[answer_prompt_record["question_id"]] = (
                        answer_prompt_record
                    )
                if isinstance(batch, _ConversationFailureBatch):
                    for record in batch.predictions:
                        prediction_records[record["question_id"]] = record
                        question_status[record["question_id"]] = {
                            "question_id": record["question_id"],
                            "conversation_id": record["conversation_id"],
                            "status": "completed",
                        }
                        question_answered += 1
                    conversation_status[batch.conversation_id] = {
                        "status": (
                            _STATUS_FAILED_ANSWER
                            if batch.ingested
                            else _STATUS_FAILED_INGEST
                        ),
                        "stage": batch.stage,
                        "error_type": batch.error_type,
                        "error": batch.error,
                        "traceback": batch.traceback_text,
                        "ingested": batch.ingested,
                        "worker_idx": future_to_chunk[future],
                    }
                    progress.update_conversations(
                        completed=conversation_ingested,
                        total=_conv_progress_total,
                        current_conversation_id=batch.conversation_id,
                    )
                    progress.update_questions(
                        completed=question_answered,
                        total=_question_progress_total,
                        current_conversation_id=batch.conversation_id,
                        current_question_id=None,
                    )
                    logger.log_event(
                        "conversation_failed_isolated",
                        {
                            "worker_idx": future_to_chunk[future],
                            "conversation_id": batch.conversation_id,
                            "stage": batch.stage,
                            "error_type": batch.error_type,
                            "error": batch.error,
                            "traceback": batch.traceback_text,
                            "ingested": batch.ingested,
                        },
                    )
                    continue
                for record in batch.predictions:
                    prediction_records[record["question_id"]] = record
                    question_status[record["question_id"]] = {
                        "question_id": record["question_id"],
                        "conversation_id": record["conversation_id"],
                        "status": "completed",
                    }
                    question_answered += 1
                if batch.ingested:
                    conversation_ingested += 1
                    conversation_status[batch.conversation_id] = {
                        "status": _STATUS_COMPLETED,
                        "ingested": True,
                    }
                progress.update_conversations(
                    completed=conversation_ingested,
                    total=_conv_progress_total,
                    current_conversation_id=batch.conversation_id,
                )
                progress.update_questions(
                    completed=question_answered,
                    total=_question_progress_total,
                    current_conversation_id=batch.conversation_id,
                    current_question_id=None,
                )
                logger.log_event(
                    "conversation_completed_isolated",
                    {"conversation_id": batch.conversation_id},
                )
            atomic_write_jsonl(
                paths.method_predictions_path,
                [
                    prediction_records[qid]
                    for qid in question_order
                    if qid in prediction_records
                ],
            )
            atomic_write_jsonl(
                paths.question_status_path,
                [
                    question_status[qid]
                    for qid in question_order
                    if qid in question_status
                ],
            )
            _persist_answer_prompt_records(
                paths=paths,
                answer_prompt_records=answer_prompt_records,
                question_order=question_order,
            )
            _persist_session_memory_reports(
                paths=paths,
                session_report_records=session_report_records,
            )
            atomic_write_json(paths.conversation_status_path, conversation_status)

    progress.set_stage("Completed", step_index=2, step_count=2)


def _isolated_worker(
    build_context: MethodBuildContext,
    run_context: RunContext,
    system_factory: Callable[
        [MethodBuildContext],
        _PredictionSystem,
    ],
    work_items: tuple[_ConversationWorkItem, ...],
    run_id: str,
    efficiency_collector: EfficiencyCollector | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
    answer_reader: FrameworkAnswerReader | None,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ),
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None,
    existing_retrieval_records: dict[str, dict[str, Any]],
    cancellation_event: Event | None = None,
    max_consecutive_failures: int | None = 3,
    *,
    protocol_version: str = "",
    consume_granularity: str | None = None,
) -> tuple[_ConversationAnswerBatch | _ConversationFailureBatch, ...]:
    """单个独立 worker：创建 method instance，串行处理分配到的 conversation。

    每个 worker 内按 conversation 顺序执行 add → get_answer，
    conversation 间无共享状态。
    """

    system = _normalize_memory_system(system_factory(build_context))
    try:
        _validate_protocol_version(protocol_version, system)
        _validate_consume_granularity(consume_granularity, system)
        if work_items:
            _prepare_memory_provider(system, run_context)
        results: list[_ConversationAnswerBatch | _ConversationFailureBatch] = []
        consecutive_failures = 0
        for work_item in work_items:
            if cancellation_event is not None and cancellation_event.is_set():
                break
            conversation = work_item.conversation
            conv_predictions: list[dict[str, Any]] = []
            conv_retrievals: list[dict[str, Any]] = []
            conv_session_reports: list[dict[str, Any]] = []
            conv_observations: list[EfficiencyObservation] = []
            ingested = not work_item.needs_ingest
            try:
                public_conversation = _make_public_conversation(conversation)
                if work_item.needs_ingest:
                    if (
                        efficiency_collector is not None
                        and efficiency_collector.enabled
                    ):
                        started_ns = perf_counter_ns()
                        with efficiency_collector.conversation_scope(
                            conversation.conversation_id,
                        ) as conv_scope:
                            conv_session_reports.extend(
                                _add_public_conversation_coarse(
                                    system=system,
                                    run_id=run_id,
                                    public_conversation=public_conversation,
                                )
                            )
                            efficiency_collector.record_memory_build_total_latency(
                                latency_ms=_elapsed_ms(started_ns),
                            )
                        conv_observations.extend(conv_scope.records)
                    else:
                        conv_session_reports.extend(
                            _add_public_conversation_coarse(
                                system=system,
                                run_id=run_id,
                                public_conversation=public_conversation,
                            )
                        )
                    ingested = True
                for source_question in work_item.pending_questions:
                    question = _make_public_question(source_question)
                    validate_no_private_keys(question.to_dict())
                    if (
                        efficiency_collector is not None
                        and efficiency_collector.enabled
                    ):
                        with efficiency_collector.question_scope(
                            conversation.conversation_id,
                            question.question_id,
                        ) as scope:
                            if _is_memory_provider(system):
                                prediction, retrieval_record = (
                                    _answer_question_retrieve_first_or_reuse(
                                        provider=system,
                                        question=question,
                                        run_id=run_id,
                                        answer_reader=answer_reader,
                                        efficiency_collector=efficiency_collector,
                                        unified_prompt_builder=unified_prompt_builder,
                                        existing_retrieval_records=existing_retrieval_records,
                                    )
                                )
                                if retrieval_record is not None:
                                    conv_retrievals.append(retrieval_record)
                            else:
                                if not isinstance(
                                    retrieval_observation_contract,
                                    RetrievalObservationContract,
                                ):
                                    raise ConfigurationError(
                                        "Enabled efficiency observability requires an "
                                        "explicit retrieval observation contract"
                                    )
                                prediction = system.get_answer(question)
                                if (
                                    not retrieval_observation_contract.supported_by_method
                                ):
                                    efficiency_collector.record_retrieval_unsupported_if_missing(
                                        retrieval_observation_contract.unsupported_reason
                                        or ""
                                    )
                        conv_observations.extend(scope.records)
                    else:
                        if _is_memory_provider(system):
                            prediction, retrieval_record = (
                                _answer_question_retrieve_first_or_reuse(
                                    provider=system,
                                    question=question,
                                    run_id=run_id,
                                    answer_reader=answer_reader,
                                    efficiency_collector=None,
                                    unified_prompt_builder=unified_prompt_builder,
                                    existing_retrieval_records=existing_retrieval_records,
                                )
                            )
                            if retrieval_record is not None:
                                conv_retrievals.append(retrieval_record)
                        else:
                            prediction = system.get_answer(question)
                    prediction = _transform_prediction_if_needed(
                        prediction,
                        prediction_transform,
                    )
                    _validate_prediction(prediction, question)
                    validate_no_private_keys(prediction.metadata)
                    conv_predictions.append(
                        {
                            "question_id": question.question_id,
                            "conversation_id": conversation.conversation_id,
                            "question_text": question.text,
                            "answer": prediction.answer,
                            "metadata": prediction.metadata,
                        }
                    )
            except Exception as exc:
                results.append(
                    _ConversationFailureBatch(
                        conversation_id=conversation.conversation_id,
                        stage="isolated_worker",
                        error_type=type(exc).__name__,
                        error=str(exc),
                        traceback_text="".join(
                            traceback.format_exception(type(exc), exc, exc.__traceback__)
                        ),
                        observations=tuple(conv_observations),
                        predictions=tuple(conv_predictions),
                        retrievals=tuple(
                            conv_retrievals
                            + list(getattr(exc, "retrievals", ()))
                        ),
                        session_reports=tuple(conv_session_reports),
                        ingested=ingested,
                    )
                )
                consecutive_failures += 1
                if (
                    max_consecutive_failures is not None
                    and consecutive_failures >= max_consecutive_failures
                ):
                    if cancellation_event is not None:
                        cancellation_event.set()
                    break
                continue
            results.append(
                _ConversationAnswerBatch(
                    conversation_id=conversation.conversation_id,
                    predictions=tuple(conv_predictions),
                    retrievals=tuple(conv_retrievals),
                    session_reports=tuple(conv_session_reports),
                    observations=tuple(conv_observations),
                    ingested=work_item.needs_ingest,
                )
            )
            consecutive_failures = 0
        return tuple(results)
    finally:
        # worker 自建的 v3 provider 生命周期归 worker 所有：成功 batch 交回协调
        # 线程之前、以及异常退出之前，都必须收敛恰好一次，避免后台线程随进程
        # 池复用而泄漏。
        _cleanup_memory_provider(system)
