"""HaluMem operation-level prediction runner。

本模块实现 benchmark 级 operation-level 驱动顺序：每个 user 内按 session
逐段 ingest，在 session 边界就地触发 extraction、update probe 和 QA。它只
使用协议 v3 provider，不调用真实 API；answer 由调用方注入的 framework reader
负责。
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from queue import Empty, Queue
from threading import Event
from time import perf_counter, perf_counter_ns
from typing import Any, Callable

from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core import AnswerPromptResult, AnswerResult, Conversation, Dataset, Question, Session
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.provider_protocol import (
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
    SessionMemoryReport,
    SessionRef,
    UnitRef,
)
from memory_benchmark.core.validators import validate_dataset, validate_no_private_keys
from memory_benchmark.observability import RunContext, method_log_scope
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    EfficiencyObservation,
    EfficiencyStage,
    ModelDescriptor,
    RetrievalObservationContract,
)
from memory_benchmark.readers.answer import FrameworkAnswerReader
from memory_benchmark.methods.registry import MethodBuildContext
from memory_benchmark.runners.conversation_qa import _make_public_question
from memory_benchmark.runners.event_stream import (
    GranularityAggregator,
    build_turn_events,
    default_isolation_key,
)
from memory_benchmark.runners.prediction import (
    _STATUS_FAILED_INGEST,
    _STATUS_COMPLETED,
    PredictionRunPolicy,
    PredictionRunSummary,
    _conversation_state_status,
    _build_efficiency_observability_manifest,
    _count_answer_context_tokens,
    _elapsed_ms,
    _manifests_match_for_resume,
    _method_manifest_with_protocol,
    _prepare_clean_failed_ingest_retries,
    _record_framework_answer_llm_call,
    _validate_consume_granularity,
    _validate_protocol_version,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    build_dataset_fingerprint,
    evaluator_private_label_record,
    public_question_record,
    read_jsonl,
)
from memory_benchmark.utils.run_logger import RunLogger


@dataclass(frozen=True)
class _OperationConversationBatch:
    """一个 UUID 完整成功后交给 coordinator 的公开结果。"""

    worker_idx: int
    conversation_id: str
    session_reports: tuple[dict[str, Any], ...]
    update_probes: tuple[dict[str, Any], ...]
    predictions: tuple[dict[str, Any], ...]
    answer_prompts: tuple[dict[str, Any], ...]
    observations: tuple[EfficiencyObservation, ...]


@dataclass(frozen=True)
class _OperationConversationFailure:
    """worker 对一个 UUID 的精确失败定位，不携带任何私有 label。"""

    worker_idx: int
    conversation_id: str
    failure_context: dict[str, str]
    error: BaseException


@dataclass(frozen=True)
class _OperationWorkerFailure:
    """business batches 已提交后发生的 lane 级生命周期失败。"""

    worker_idx: int
    stage: str
    error: BaseException


def run_operation_level_predictions(
    *,
    dataset: Dataset,
    provider: MemoryProvider | None,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    answer_reader: FrameworkAnswerReader,
    unified_prompt_builder: Callable[[Question, RetrievalResult], AnswerPromptResult],
    source_paths: tuple[str | Path, ...] = (),
    efficiency_collector: EfficiencyCollector | None = None,
    model_inventory: tuple[ModelDescriptor, ...] = (),
    instrumentation_identity: dict[str, object] | None = None,
    retrieval_observation_contract: RetrievalObservationContract | None = None,
    protocol_version: str = "",
    provenance_granularity: str | None = None,
    retrieval_evidence_contract_version: str | None = None,
    clean_failed_ingest_conversation: (
        Callable[[Conversation, dict[str, Any]], None] | None
    ) = None,
    provider_factory: Callable[[MethodBuildContext], MemoryProvider] | None = None,
    build_context_template: MethodBuildContext | None = None,
    consume_granularity: str | None = None,
) -> PredictionRunSummary:
    """运行 HaluMem operation-level prediction。

    输入:
        dataset: HaluMem adapter 生成的数据集。
        provider: 协议 v3 MemoryProvider。
        run_context: 标准输出目录上下文。
        policy: conversation 级范围、并发与 resume 策略。
        method_manifest: method 公开 manifest。
        benchmark_variant: concrete variant 名。
        run_scope: smoke/full。
        answer_reader: framework-owned answer reader。
        unified_prompt_builder: benchmark 官方 prompt builder。
        source_paths: 可选原始源文件路径，用于数据指纹。
        protocol_version: method 注册级 provider 协议版本声明。
        provenance_granularity: method 注册级 provenance 粒度声明。
        retrieval_evidence_contract_version: method 注册级逐题 retrieval evidence
            契约版本声明；非空时写入 manifest 作为 resume 身份。
        retrieval_observation_contract: retrieval 效率观测能力契约；启用效率
            collector 时与模型清单、插桩身份一同写入不可变 manifest。
        clean_failed_ingest_conversation: 可选 conversation 级 clean retry hook，
            与标准 runner 同型；只有内置 method 能证明可安全清理半写入状态时才应
            传入。任一 session 的 ingest/extraction/update/QA/end_conversation 抛错
            都会把该 conversation 标记为 `failed_ingest`；显式 retry 且无该 hook 时
            fail-closed，不直接从 session 1 重放。
        provider_factory: registered 路径为每个稳定 worker lane 构造独立 provider。
        build_context_template: registered 路径构造 `worker_<idx>` context 的模板。
        consume_granularity: 注册级 concrete 消费粒度；根进程不构造 provider
            时仍用于 manifest 与 worker 交叉校验。

    输出:
        PredictionRunSummary: 标准 prediction 摘要。
    """

    uses_factory_workers = provider is None
    if uses_factory_workers and (
        provider_factory is None or build_context_template is None
    ):
        raise ConfigurationError(
            "isolated operation-level prediction requires provider_factory "
            "and build_context_template"
        )
    if not uses_factory_workers and policy.max_workers > 1:
        raise ConfigurationError(
            "multi-worker operation-level prediction must not share one provider"
        )
    validate_dataset(dataset)
    paths = ExperimentPaths.create(run_context.run_dir)
    with method_log_scope(paths.logs_dir):
        selected_conversations = _select_conversations(dataset, policy)
        method_manifest = _method_manifest_with_protocol(
            method_manifest=method_manifest,
            protocol_version=protocol_version,
            prompt_track="unified",
            system=provider,
            provenance_granularity=provenance_granularity,
            retrieval_evidence_contract_version=(
                retrieval_evidence_contract_version
            ),
            consume_granularity=consume_granularity,
        )
        manifest = _build_operation_manifest(
            dataset=dataset,
            run_context=run_context,
            policy=policy,
            method_manifest=method_manifest,
            benchmark_variant=benchmark_variant,
            run_scope=run_scope,
            source_paths=tuple(Path(path) for path in source_paths),
            efficiency_observability=_build_efficiency_observability_manifest(
                run_context=run_context,
                efficiency_collector=efficiency_collector,
                model_inventory=model_inventory,
                instrumentation_identity=instrumentation_identity,
                retrieval_observation_contract=retrieval_observation_contract,
            ),
        )
        _prepare_operation_run(paths=paths, manifest=manifest, resume=policy.resume)
        _write_operation_input_artifacts(paths, selected_conversations)

        efficiency_store: EfficiencyArtifactStore | None = None
        if efficiency_collector is not None and efficiency_collector.enabled:
            if efficiency_collector.run_id != run_context.run_id:
                raise ConfigurationError(
                    "EfficiencyCollector run_id must match RunContext run_id"
                )
            efficiency_store = EfficiencyArtifactStore.for_prediction(paths)
            efficiency_store.write_model_inventory(model_inventory)
            efficiency_collector.bind_failed_attempt_sink(
                efficiency_store.append_failed_attempt
            )

        conversation_status = _read_json_object(paths.conversation_status_path)
        prediction_records = {
            record["question_id"]: record
            for record in read_jsonl(
                paths.method_predictions_path,
                recover_torn_tail=policy.resume,
            )
        }
        session_report_records = read_jsonl(
            paths.session_memory_reports_path,
            recover_torn_tail=policy.resume,
        )
        update_probe_records = read_jsonl(
            _update_probe_results_path(paths),
            recover_torn_tail=policy.resume,
        )
        answer_prompt_records = read_jsonl(
            paths.answer_prompts_path,
            recover_torn_tail=policy.resume,
        )
        logger = RunLogger(paths.logs_dir)
        _prepare_clean_failed_ingest_retries(
            conversations=selected_conversations,
            conversation_status=conversation_status,
            policy=policy,
            clean_failed_ingest_conversation=clean_failed_ingest_conversation,
            paths=paths,
            logger=logger,
        )

        pending_conversations = _pending_operation_conversations(
            selected_conversations=selected_conversations,
            conversation_status=conversation_status,
            policy=policy,
        )
        needs_provider = bool(pending_conversations)
        if uses_factory_workers:
            _run_parallel_operation_conversations(
                pending_conversations=pending_conversations,
                selected_conversations=selected_conversations,
                conversation_status=conversation_status,
                prediction_records=prediction_records,
                session_report_records=session_report_records,
                update_probe_records=update_probe_records,
                answer_prompt_records=answer_prompt_records,
                provider_factory=provider_factory,
                build_context_template=build_context_template,
                run_context=run_context,
                policy=policy,
                answer_reader=answer_reader,
                unified_prompt_builder=unified_prompt_builder,
                efficiency_collector=efficiency_collector,
                efficiency_store=efficiency_store,
                protocol_version=protocol_version,
                consume_granularity=consume_granularity,
                paths=paths,
                logger=logger,
            )
        elif needs_provider:
            assert provider is not None
            try:
                provider.prepare(run_context)
            except Exception:
                provider.cleanup()
                raise

        if not uses_factory_workers:
            assert provider is not None
            for conversation in pending_conversations:
                try:
                    failure_context: dict[str, str] = {
                        "stage": "operation_conversation",
                    }
                    conversation_observations = _run_operation_conversation(
                        conversation=conversation,
                        provider=provider,
                        run_id=run_context.run_id,
                        answer_reader=answer_reader,
                        unified_prompt_builder=unified_prompt_builder,
                        supports_extraction=provider.session_memory_report,
                        session_report_records=session_report_records,
                        update_probe_records=update_probe_records,
                        prediction_records=prediction_records,
                        answer_prompt_records=answer_prompt_records,
                        efficiency_collector=efficiency_collector,
                        failure_context=failure_context,
                    )
                except Exception as exc:
                    conversation_status[conversation.conversation_id] = {
                        "status": _STATUS_FAILED_INGEST,
                        **failure_context,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "ingested": False,
                    }
                    atomic_write_json(paths.conversation_status_path, conversation_status)
                    logger.log_event(
                        "conversation_failed",
                        {
                            "conversation_id": conversation.conversation_id,
                            **failure_context,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        },
                    )
                    if failure_context.get("stage") != "provider_cleanup":
                        try:
                            provider.cleanup()
                        except Exception as cleanup_exc:
                            raise cleanup_exc from exc
                    raise
                if efficiency_store is not None:
                    efficiency_store.merge_observations(conversation_observations)
                conversation_status[conversation.conversation_id] = {
                    "status": _STATUS_COMPLETED,
                    "ingested": True,
                }
                atomic_write_json(paths.conversation_status_path, conversation_status)
                _write_operation_output_artifacts(
                    paths=paths,
                    session_report_records=session_report_records,
                    update_probe_records=update_probe_records,
                    prediction_records=prediction_records,
                    answer_prompt_records=answer_prompt_records,
                    selected_conversations=selected_conversations,
                )

        completed_conversations = sum(
            1
            for conversation in selected_conversations
            if conversation_status.get(conversation.conversation_id, {}).get("status")
            == "completed"
        )
        selected_question_ids = _selected_operation_question_ids(selected_conversations)
        summary = PredictionRunSummary(
            run_id=run_context.run_id,
            dataset_name=dataset.dataset_name,
            total_conversations=len(selected_conversations),
            completed_conversations=completed_conversations,
            total_questions=len(selected_question_ids),
            completed_questions=sum(
                1 for question_id in selected_question_ids if question_id in prediction_records
            ),
            prediction_path=str(paths.method_predictions_path),
            private_label_path=str(paths.evaluator_private_labels_path),
            summary_path=str(paths.summary_path),
            metadata={"runner": "operation_level_prediction"},
            failed_conversations=sum(
                1
                for conversation in selected_conversations
                if str(
                    conversation_status.get(
                        conversation.conversation_id,
                        {},
                    ).get("status", "")
                ).startswith("failed")
            ),
        )
        atomic_write_json(paths.summary_path, summary.to_dict())
        return summary


def _pending_operation_conversations(
    *,
    selected_conversations: list[Conversation],
    conversation_status: dict[str, Any],
    policy: PredictionRunPolicy,
) -> list[Conversation]:
    """按 resume/failure/budget 语义选择本次真正推进的 UUID。"""

    pending: list[Conversation] = []
    for conversation in selected_conversations:
        status = _conversation_state_status(
            conversation_status.get(conversation.conversation_id, {})
        )
        if status == _STATUS_COMPLETED:
            continue
        if status == _STATUS_FAILED_INGEST:
            if policy.retry_failed_conversations:
                raise ConfigurationError(
                    f"Cannot retry conversation '{conversation.conversation_id}' "
                    "after failed ingest without clean retry support"
                )
            continue
        if (
            policy.max_new_conversations is not None
            and len(pending) >= policy.max_new_conversations
        ):
            break
        pending.append(conversation)
    return pending


def _stable_operation_worker_chunks(
    *,
    pending_conversations: list[Conversation],
    selected_conversations: list[Conversation],
    max_workers: int,
) -> tuple[tuple[int, tuple[Conversation, ...]], ...]:
    """按完整 UUID 顺序稳定映射 worker，保证 resume 不换 state root。"""

    if max_workers < 1:
        raise ConfigurationError("operation-level max_workers must be positive")
    if not pending_conversations:
        return ()
    worker_count = min(max_workers, len(selected_conversations))
    order = {
        conversation.conversation_id: index
        for index, conversation in enumerate(selected_conversations)
    }
    chunks: dict[int, list[Conversation]] = {
        worker_idx: [] for worker_idx in range(worker_count)
    }
    for conversation in pending_conversations:
        worker_idx = order[conversation.conversation_id] % worker_count
        chunks[worker_idx].append(conversation)
    return tuple(
        (worker_idx, tuple(conversations))
        for worker_idx, conversations in chunks.items()
        if conversations
    )


def _operation_worker_lane(
    *,
    worker_idx: int,
    conversations: tuple[Conversation, ...],
    provider_factory: Callable[[MethodBuildContext], MemoryProvider],
    build_context_template: MethodBuildContext,
    run_context: RunContext,
    answer_reader: FrameworkAnswerReader,
    unified_prompt_builder: Callable[[Question, RetrievalResult], AnswerPromptResult],
    efficiency_collector: EfficiencyCollector | None,
    protocol_version: str,
    consume_granularity: str | None,
    result_queue: Queue[
        _OperationConversationBatch
        | _OperationConversationFailure
        | _OperationWorkerFailure
    ],
    cancellation_event: Event,
) -> None:
    """一个 worker 独占一份 runtime，并在 lane 内串行处理 UUID。"""

    worker_context = MethodBuildContext(
        config=build_context_template.config,
        openai_settings=build_context_template.openai_settings,
        path_settings=build_context_template.path_settings,
        storage_root=build_context_template.storage_root / f"worker_{worker_idx}",
        benchmark_name=build_context_template.benchmark_name,
        completed_conversations=(),
        efficiency_collector=build_context_template.efficiency_collector,
        diagnostic_log_path=build_context_template.diagnostic_log_path,
    )
    if cancellation_event.is_set():
        return
    provider: MemoryProvider | None = None
    failure_context: dict[str, str] = {"stage": "provider_factory"}
    failure_conversation_id = conversations[0].conversation_id
    try:
        provider = provider_factory(worker_context)
        if not isinstance(provider, MemoryProvider):
            raise ConfigurationError(
                "operation-level provider_factory must return MemoryProvider"
            )
        _validate_protocol_version(protocol_version, provider)
        if consume_granularity is not None:
            _validate_consume_granularity(consume_granularity, provider)
        failure_context["stage"] = "provider_prepare"
        provider.prepare(run_context)
        for conversation in conversations:
            if cancellation_event.is_set():
                break
            failure_conversation_id = conversation.conversation_id
            local_session_reports: list[dict[str, Any]] = []
            local_update_probes: list[dict[str, Any]] = []
            local_predictions: dict[str, dict[str, Any]] = {}
            local_answer_prompts: list[dict[str, Any]] = []
            observations = _run_operation_conversation(
                conversation=conversation,
                provider=provider,
                run_id=run_context.run_id,
                answer_reader=answer_reader,
                unified_prompt_builder=unified_prompt_builder,
                supports_extraction=provider.session_memory_report,
                session_report_records=local_session_reports,
                update_probe_records=local_update_probes,
                prediction_records=local_predictions,
                answer_prompt_records=local_answer_prompts,
                efficiency_collector=efficiency_collector,
                failure_context=failure_context,
                cleanup_provider=False,
            )
            result_queue.put(
                _OperationConversationBatch(
                    worker_idx=worker_idx,
                    conversation_id=conversation.conversation_id,
                    session_reports=tuple(local_session_reports),
                    update_probes=tuple(local_update_probes),
                    predictions=tuple(local_predictions.values()),
                    answer_prompts=tuple(local_answer_prompts),
                    observations=tuple(observations),
                )
            )
    except BaseException as exc:
        if provider is not None and failure_context.get("stage") != "provider_cleanup":
            try:
                provider.cleanup()
            except BaseException as cleanup_exc:
                failure_context = {"stage": "provider_cleanup"}
                exc = cleanup_exc
        result_queue.put(
            _OperationConversationFailure(
                worker_idx=worker_idx,
                conversation_id=failure_conversation_id,
                failure_context=dict(failure_context),
                error=exc,
            )
        )
        cancellation_event.set()
        return
    try:
        provider.cleanup()
    except BaseException as exc:
        result_queue.put(
            _OperationWorkerFailure(
                worker_idx=worker_idx,
                stage="provider_cleanup",
                error=exc,
            )
        )
        cancellation_event.set()


def _run_parallel_operation_conversations(
    *,
    pending_conversations: list[Conversation],
    selected_conversations: list[Conversation],
    conversation_status: dict[str, Any],
    prediction_records: dict[str, dict[str, Any]],
    session_report_records: list[dict[str, Any]],
    update_probe_records: list[dict[str, Any]],
    answer_prompt_records: list[dict[str, Any]],
    provider_factory: Callable[[MethodBuildContext], MemoryProvider] | None,
    build_context_template: MethodBuildContext | None,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    answer_reader: FrameworkAnswerReader,
    unified_prompt_builder: Callable[[Question, RetrievalResult], AnswerPromptResult],
    efficiency_collector: EfficiencyCollector | None,
    efficiency_store: EfficiencyArtifactStore | None,
    protocol_version: str,
    consume_granularity: str | None,
    paths: ExperimentPaths,
    logger: RunLogger,
) -> None:
    """并行调度 UUID；worker 不写 artifact，coordinator 稳定合并。"""

    if not pending_conversations:
        return
    if provider_factory is None or build_context_template is None:
        raise ConfigurationError("parallel operation-level dependencies are missing")
    chunks = _stable_operation_worker_chunks(
        pending_conversations=pending_conversations,
        selected_conversations=selected_conversations,
        max_workers=policy.max_workers,
    )
    result_queue: Queue[
        _OperationConversationBatch
        | _OperationConversationFailure
        | _OperationWorkerFailure
    ] = Queue()
    cancellation_event = Event()
    first_error: BaseException | None = None

    def persist_result(
        result: (
            _OperationConversationBatch
            | _OperationConversationFailure
            | _OperationWorkerFailure
        ),
    ) -> None:
        """在 coordinator 线程内提交一条 UUID 结果。"""

        nonlocal first_error
        if isinstance(result, _OperationWorkerFailure):
            if first_error is None:
                first_error = result.error
            logger.log_event(
                "operation_worker_failed",
                {
                    "worker_idx": result.worker_idx,
                    "stage": result.stage,
                    "error_type": type(result.error).__name__,
                    "error": str(result.error),
                },
            )
            return
        if isinstance(result, _OperationConversationFailure):
            if first_error is None:
                first_error = result.error
            conversation_status[result.conversation_id] = {
                "status": _STATUS_FAILED_INGEST,
                **result.failure_context,
                "error_type": type(result.error).__name__,
                "error": str(result.error),
                "ingested": False,
                "worker_idx": result.worker_idx,
            }
            atomic_write_json(paths.conversation_status_path, conversation_status)
            logger.log_event(
                "conversation_failed",
                {
                    "worker_idx": result.worker_idx,
                    "conversation_id": result.conversation_id,
                    **result.failure_context,
                    "error_type": type(result.error).__name__,
                    "error": str(result.error),
                },
            )
            return
        session_report_records.extend(result.session_reports)
        update_probe_records.extend(result.update_probes)
        for record in result.predictions:
            prediction_records[record["question_id"]] = record
        answer_prompt_records.extend(result.answer_prompts)
        if efficiency_store is not None:
            efficiency_store.merge_observations(result.observations)
        conversation_status[result.conversation_id] = {
            "status": _STATUS_COMPLETED,
            "ingested": True,
            "worker_idx": result.worker_idx,
        }
        atomic_write_json(paths.conversation_status_path, conversation_status)
        _stable_sort_operation_records(
            records=session_report_records,
            selected_conversations=selected_conversations,
            run_id=run_context.run_id,
        )
        _stable_sort_operation_records(
            records=update_probe_records,
            selected_conversations=selected_conversations,
            run_id=run_context.run_id,
        )
        _write_operation_output_artifacts(
            paths=paths,
            session_report_records=session_report_records,
            update_probe_records=update_probe_records,
            prediction_records=prediction_records,
            answer_prompt_records=answer_prompt_records,
            selected_conversations=selected_conversations,
        )
        logger.log_event(
            "conversation_completed_isolated",
            {
                "worker_idx": result.worker_idx,
                "conversation_id": result.conversation_id,
            },
        )

    with ThreadPoolExecutor(max_workers=len(chunks)) as executor:
        futures: set[Future[None]] = {
            executor.submit(
                _operation_worker_lane,
                worker_idx=worker_idx,
                conversations=conversations,
                provider_factory=provider_factory,
                build_context_template=build_context_template,
                run_context=run_context,
                answer_reader=answer_reader,
                unified_prompt_builder=unified_prompt_builder,
                efficiency_collector=efficiency_collector,
                protocol_version=protocol_version,
                consume_granularity=consume_granularity,
                result_queue=result_queue,
                cancellation_event=cancellation_event,
            )
            for worker_idx, conversations in chunks
        }
        pending = set(futures)
        while pending:
            _, pending = wait(pending, timeout=0.1)
            while True:
                try:
                    persist_result(result_queue.get_nowait())
                except Empty:
                    break
        while True:
            try:
                persist_result(result_queue.get_nowait())
            except Empty:
                break
        for future in futures:
            future.result()
    if first_error is not None:
        raise first_error


def _stable_sort_operation_records(
    *,
    records: list[dict[str, Any]],
    selected_conversations: list[Conversation],
    run_id: str,
) -> None:
    """按 dataset UUID/session/gold-index 重排并发产生的 session 型记录。"""

    conversation_order = {
        default_isolation_key(run_id, conversation.conversation_id): index
        for index, conversation in enumerate(selected_conversations)
    }
    session_order = {
        (
            default_isolation_key(run_id, conversation.conversation_id),
            session.session_id,
        ): session_index
        for conversation in selected_conversations
        for session_index, session in enumerate(conversation.sessions)
    }

    def sort_key(record: dict[str, Any]) -> tuple[int, int, str]:
        """返回公开 dataset 顺序对应的稳定记录排序键。"""

        session_ref = record.get("session_ref")
        if not isinstance(session_ref, dict):
            raise ConfigurationError("operation-level record is missing session_ref")
        isolation_key = session_ref.get("isolation_key")
        session_id = session_ref.get("session_id")
        if not isinstance(isolation_key, str):
            raise ConfigurationError("operation-level session_ref isolation_key is invalid")
        return (
            conversation_order.get(isolation_key, len(conversation_order)),
            session_order.get((isolation_key, session_id), 10**9),
            str(record.get("gold_memory_index", "")),
        )

    records.sort(key=sort_key)


def _run_operation_conversation(
    *,
    conversation: Conversation,
    provider: MemoryProvider,
    run_id: str,
    answer_reader: FrameworkAnswerReader,
    unified_prompt_builder: Callable[[Question, RetrievalResult], AnswerPromptResult],
    supports_extraction: bool,
    session_report_records: list[dict[str, Any]],
    update_probe_records: list[dict[str, Any]],
    prediction_records: dict[str, dict[str, Any]],
    answer_prompt_records: list[dict[str, Any]],
    efficiency_collector: EfficiencyCollector | None = None,
    failure_context: dict[str, str],
    cleanup_provider: bool = True,
) -> list[EfficiencyObservation]:
    """按 spec S4.2 驱动单个 HaluMem user，并采集效率 observation。

    效率 scope 贴合官方 eval 的 per-session 交错语义（ingest→extraction→
    update-probe→该 session 的 QA），**不改变** ingest/QA 顺序：每个 session 的记忆
    构建包一层 conversation_scope（scope_discriminator=session_id 保证同一 conversation
    多 session 的 observation id 唯一），每个问题包一层 question_scope。返回本
    conversation 采集到的全部 observation，由调用方合并进 EfficiencyArtifactStore。
    """

    observations: list[EfficiencyObservation] = []
    enabled = efficiency_collector is not None and efficiency_collector.enabled
    isolation_key = default_isolation_key(run_id, conversation.conversation_id)
    questions_by_session = _questions_by_session(conversation)
    aggregator = GranularityAggregator(provider.consume_granularity)
    for session in conversation.sessions:
        if enabled:
            with efficiency_collector.conversation_scope(
                conversation.conversation_id,
                scope_discriminator=session.session_id,
            ) as memory_scope:
                generated = _ingest_and_probe_session(
                    session=session,
                    conversation=conversation,
                    isolation_key=isolation_key,
                    aggregator=aggregator,
                    provider=provider,
                    supports_extraction=supports_extraction,
                    session_report_records=session_report_records,
                    update_probe_records=update_probe_records,
                    failure_context=failure_context,
                    efficiency_collector=efficiency_collector,
                )
            observations.extend(memory_scope.records)
        else:
            generated = _ingest_and_probe_session(
                session=session,
                conversation=conversation,
                isolation_key=isolation_key,
                aggregator=aggregator,
                provider=provider,
                supports_extraction=supports_extraction,
                session_report_records=session_report_records,
                update_probe_records=update_probe_records,
                failure_context=failure_context,
                efficiency_collector=None,
            )
        if generated:
            continue

        for source_question in questions_by_session.get(session.session_id, []):
            question = _make_public_question(source_question)
            validate_no_private_keys(question.to_dict())
            _set_operation_failure_context(
                failure_context,
                stage="question_answer",
                session_id=session.session_id,
                question_id=question.question_id,
            )
            if enabled:
                with efficiency_collector.question_scope(
                    conversation.conversation_id,
                    question.question_id,
                ) as question_scope:
                    _answer_operation_question(
                        question=question,
                        isolation_key=isolation_key,
                        provider=provider,
                        answer_reader=answer_reader,
                        unified_prompt_builder=unified_prompt_builder,
                        efficiency_collector=efficiency_collector,
                        prediction_records=prediction_records,
                        answer_prompt_records=answer_prompt_records,
                    )
                observations.extend(question_scope.records)
            else:
                _answer_operation_question(
                    question=question,
                    isolation_key=isolation_key,
                    provider=provider,
                    answer_reader=answer_reader,
                    unified_prompt_builder=unified_prompt_builder,
                    efficiency_collector=None,
                    prediction_records=prediction_records,
                    answer_prompt_records=answer_prompt_records,
                )

    _set_operation_failure_context(
        failure_context,
        stage="end_conversation",
    )
    if enabled:
        with efficiency_collector.conversation_scope(
            conversation.conversation_id,
            scope_discriminator="__end_conversation__",
        ) as end_scope:
            started_ns = perf_counter_ns()
            provider.end_conversation(UnitRef(isolation_key=isolation_key))
            efficiency_collector.record_memory_build_total_latency(
                latency_ms=_elapsed_ms(started_ns)
            )
        observations.extend(end_scope.records)
    else:
        provider.end_conversation(UnitRef(isolation_key=isolation_key))
    if cleanup_provider:
        _set_operation_failure_context(
            failure_context,
            stage="provider_cleanup",
        )
        provider.cleanup()
    return observations


def _ingest_and_probe_session(
    *,
    session: Session,
    conversation: Conversation,
    isolation_key: str,
    aggregator: GranularityAggregator,
    provider: MemoryProvider,
    supports_extraction: bool,
    session_report_records: list[dict[str, Any]],
    update_probe_records: list[dict[str, Any]],
    failure_context: dict[str, str],
    efficiency_collector: EfficiencyCollector | None,
) -> bool:
    """ingest 单个 session + extraction + update probe，返回是否为 generated QA session。

    generated session 只 ingest + end_session（不记 session report、不跑 update
    probe、不 QA），与官方 eval 一致。全部 provider 调用发生在调用方开启的
    conversation scope 内；ingest/end_session 归 memory_build，update probe retrieve
    显式切到 retrieval，避免 SimpleMem planning/reflection 被误记为构建调用。
    """

    build_started_ns = perf_counter_ns()
    events = [
        event
        for event in build_turn_events(conversation, isolation_key)
        if event.session_id == session.session_id
    ]
    for signal in aggregator.aggregate(events, isolation_key=isolation_key):
        if isinstance(signal, UnitRef):
            continue
        if isinstance(signal, SessionRef):
            continue
        _set_operation_failure_context(
            failure_context,
            stage="session_ingest",
            session_id=session.session_id,
        )
        provider.ingest(signal)

    session_ref = SessionRef(
        isolation_key=isolation_key,
        session_id=session.session_id,
    )
    report = None
    if supports_extraction:
        _set_operation_failure_context(
            failure_context,
            stage="session_extraction",
            session_id=session.session_id,
        )
        report = provider.end_session(session_ref)
    if efficiency_collector is not None and efficiency_collector.enabled:
        efficiency_collector.record_memory_build_total_latency(
            latency_ms=_elapsed_ms(build_started_ns)
        )
    generated = bool(session.private_metadata.get("is_generated_qa_session"))
    if generated:
        return True
    session_report_records.append(
        _session_report_record(
            session_ref=session_ref,
            report=report,
            supports_extraction=supports_extraction,
        )
    )
    for memory_point in _update_memory_points(session.private_metadata):
        _set_operation_failure_context(
            failure_context,
            stage="memory_update_probe",
            session_id=session.session_id,
        )
        started = perf_counter()
        query = RetrievalQuery(
            query_text=str(memory_point["memory_content"]),
            isolation_key=isolation_key,
            question_time=None,
            top_k=10,
            purpose="memory_update_probe",
        )
        if efficiency_collector is not None and efficiency_collector.enabled:
            with efficiency_collector.operation_stage(EfficiencyStage.RETRIEVAL):
                retrieval = provider.retrieve(query)
        else:
            retrieval = provider.retrieve(query)
        update_probe_records.append(
            _update_probe_record(
                session_ref=session_ref,
                memory_point=memory_point,
                retrieval=retrieval,
                duration_ms=(perf_counter() - started) * 1000,
            )
        )
    return False


def _set_operation_failure_context(
    failure_context: dict[str, str],
    *,
    stage: str,
    session_id: str | None = None,
    question_id: str | None = None,
) -> None:
    """就地更新当前 operation 调用的公开失败定位信息。"""

    failure_context.clear()
    failure_context["stage"] = stage
    if session_id is not None:
        failure_context["session_id"] = session_id
    if question_id is not None:
        failure_context["question_id"] = question_id


def _answer_operation_question(
    *,
    question: Question,
    isolation_key: str,
    provider: MemoryProvider,
    answer_reader: FrameworkAnswerReader,
    unified_prompt_builder: Callable[[Question, RetrievalResult], AnswerPromptResult],
    efficiency_collector: EfficiencyCollector | None,
    prediction_records: dict[str, dict[str, Any]],
    answer_prompt_records: list[dict[str, Any]],
) -> None:
    """检索 + 回答单个 QA 问题，并在启用时采集 retrieval/answer 效率 observation。

    效率口径与标准 runner 的 `_answer_question_retrieve_first` 完全对齐：retrieve
    包 RETRIEVAL 阶段并记 injected_memory_context_tokens；answer LLM 调用优先取
    api_usage token（`_record_framework_answer_llm_call`），再记 answer 生成延迟。
    """

    enabled = efficiency_collector is not None and efficiency_collector.enabled
    started_ns = perf_counter_ns()
    query = RetrievalQuery(
        query_text=question.text,
        isolation_key=isolation_key,
        question_time=question.question_time,
        top_k=20,
        purpose="qa",
        source_question=question,
    )
    if enabled:
        with efficiency_collector.operation_stage(EfficiencyStage.RETRIEVAL):
            retrieval_result = provider.retrieve(query)
    else:
        retrieval_result = provider.retrieve(query)
    retrieval = unified_prompt_builder(question, retrieval_result)
    if enabled:
        efficiency_collector.record_retrieval_result_if_missing(
            latency_ms=_elapsed_ms(started_ns),
            injected_memory_context_tokens=_count_answer_context_tokens(
                retrieval.metadata,
                answer_reader.client.model_name,
            ),
        )

    answer_started_ns = perf_counter_ns()
    prediction, answer_prompt, answer_response = (
        answer_reader.generate_answer_with_trace(
            question=question,
            retrieval=retrieval,
        )
    )
    if enabled:
        with efficiency_collector.operation_stage(EfficiencyStage.ANSWER):
            _record_framework_answer_llm_call(
                efficiency_collector=efficiency_collector,
                model_id=answer_reader.client.model_name,
                model_name=answer_reader.client.model_name,
                prompt_text=answer_prompt,
                answer_text=prediction.answer,
                response=answer_response,
            )
        efficiency_collector.record_answer_generation(
            latency_ms=_elapsed_ms(answer_started_ns)
        )

    _validate_prediction(prediction, question)
    answer_prompt_records.append(
        _answer_prompt_record(
            retrieval=retrieval,
            retrieval_result=retrieval_result,
            retrieval_query_top_k=query.top_k,
        )
    )
    prediction_records[question.question_id] = {
        "question_id": question.question_id,
        "conversation_id": question.conversation_id,
        "question_text": question.text,
        "answer": prediction.answer,
        "metadata": {
            **prediction.metadata,
            "operation_level_duration_ms": _elapsed_ms(started_ns),
        },
    }


def _select_conversations(
    dataset: Dataset,
    policy: PredictionRunPolicy,
) -> list[Conversation]:
    """按 policy 选择 conversation。"""

    if policy.conversation_ids is None:
        return list(dataset.conversations)
    by_id = {conversation.conversation_id: conversation for conversation in dataset.conversations}
    missing = [item for item in policy.conversation_ids if item not in by_id]
    if missing:
        raise ConfigurationError(
            f"Unknown conversation_ids in operation-level policy: {', '.join(missing)}"
        )
    return [by_id[item] for item in policy.conversation_ids]


def _questions_by_session(conversation: Conversation) -> dict[str | None, list[Question]]:
    """按 gold metadata 或 question_id 把问题归到 session。"""

    grouped: dict[str | None, list[Question]] = {}
    for question in conversation.questions:
        gold = conversation.gold_answers.get(question.question_id)
        session_id = None
        if gold is not None:
            metadata_session_id = gold.metadata.get("session_id")
            if isinstance(metadata_session_id, str):
                session_id = metadata_session_id
        if session_id is None:
            session_id = _question_session_id(question.question_id)
        grouped.setdefault(session_id, []).append(question)
    return grouped


def _question_session_id(question_id: str) -> str | None:
    """从 HaluMem question id 中解析 session id。"""

    parts = question_id.split(":")
    if len(parts) < 3:
        return None
    return parts[-2]


def _update_memory_points(private_metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """筛选官方 update probe 需要的 memory points。"""

    memory_points = private_metadata.get("memory_points")
    if not isinstance(memory_points, list):
        return []
    selected: list[dict[str, Any]] = []
    for memory_point in memory_points:
        if not isinstance(memory_point, dict):
            continue
        if memory_point.get("is_update") == "False":
            continue
        original_memories = memory_point.get("original_memories")
        if not original_memories:
            continue
        if not isinstance(memory_point.get("memory_content"), str):
            continue
        selected.append(memory_point)
    return selected


def _session_report_record(
    *,
    session_ref: SessionRef,
    report: SessionMemoryReport | None,
    supports_extraction: bool,
) -> dict[str, Any]:
    """构造 session memory report artifact 记录。"""

    if report is None:
        return {
            "session_ref": asdict(session_ref),
            "memories": [],
            "metadata": {},
            "status": "n/a" if not supports_extraction else "empty",
        }
    return {
        "session_ref": asdict(report.session_ref),
        "memories": list(report.memories),
        "metadata": dict(report.metadata),
        "status": "ok",
    }


def _update_probe_record(
    *,
    session_ref: SessionRef,
    memory_point: dict[str, Any],
    retrieval: RetrievalResult,
    duration_ms: float,
) -> dict[str, Any]:
    """构造 update probe artifact 记录。"""

    return {
        "session_ref": asdict(session_ref),
        "gold_memory_index": memory_point.get("index"),
        "query_text": memory_point["memory_content"],
        "formatted_memory": retrieval.formatted_memory,
        "memories_from_system": _memories_from_retrieval(retrieval),
        "duration_ms": duration_ms,
    }


def _memories_from_retrieval(retrieval: RetrievalResult) -> list[str]:
    """把 RetrievalResult 转成 HaluMem update scorer 需要的 memory 列表。"""

    if retrieval.items is not None:
        return [item.content for item in retrieval.items]
    return [line for line in retrieval.formatted_memory.splitlines() if line.strip()]


def _answer_prompt_record(
    *,
    retrieval: AnswerPromptResult,
    retrieval_result: RetrievalResult,
    retrieval_query_top_k: int,
) -> dict[str, Any]:
    """构造 QA answer prompt artifact 记录，并保留实际请求的 top-k。"""

    record = {
        "question_id": retrieval.question_id,
        "conversation_id": retrieval.conversation_id,
        "answer_prompt": retrieval.answer_prompt,
        "prompt_messages": [message.to_dict() for message in retrieval.prompt_messages],
        "metadata": retrieval.metadata,
        "formatted_memory": retrieval_result.formatted_memory,
        "retrieved_items": [
            asdict(item) for item in retrieval_result.items or ()
        ],
        "retrieval_query_top_k": retrieval_query_top_k,
        "retrieval_evidence": (
            asdict(retrieval_result.evidence)
            if retrieval_result.evidence is not None
            else None
        ),
    }
    validate_no_private_keys(record)
    return record


def _validate_prediction(prediction: AnswerResult, question: Question) -> None:
    """校验 framework reader 返回结果与公开 question 对齐。"""

    if prediction.question_id != question.question_id:
        raise ConfigurationError("operation-level prediction question_id mismatch")
    if prediction.conversation_id != question.conversation_id:
        raise ConfigurationError("operation-level prediction conversation_id mismatch")
    if not prediction.answer.strip():
        raise ConfigurationError("operation-level prediction answer is empty")
    validate_no_private_keys(prediction.metadata)


def _write_operation_input_artifacts(
    paths: ExperimentPaths,
    conversations: list[Conversation],
) -> None:
    """写入公开 question 与 evaluator-only 私有标签。"""

    public_questions: list[dict[str, Any]] = []
    private_labels: list[dict[str, Any]] = []
    private_session_labels: list[dict[str, Any]] = []
    for conversation in conversations:
        for session in conversation.sessions:
            if session.private_metadata.get("is_generated_qa_session") is True:
                continue
            private_session_labels.append(
                _evaluator_private_session_label_record(
                    conversation_id=conversation.conversation_id,
                    session=session,
                )
            )
        for question in conversation.questions:
            public_question = _make_public_question(question)
            public_questions.append(public_question_record(public_question))
            gold = conversation.gold_answers.get(question.question_id)
            if gold is not None:
                private_labels.append(
                    evaluator_private_label_record(gold, question.category)
                )
    atomic_write_jsonl(paths.public_questions_path, public_questions)
    atomic_write_jsonl(paths.evaluator_private_labels_path, private_labels)
    atomic_write_jsonl(
        paths.evaluator_private_session_labels_path,
        private_session_labels,
    )


def _evaluator_private_session_label_record(
    *,
    conversation_id: str,
    session: Session,
) -> dict[str, Any]:
    """构造 HaluMem session 级 evaluator-only gold 记录。"""

    memory_points = session.private_metadata.get("memory_points")
    if not isinstance(memory_points, list):
        memory_points = []
    return {
        "conversation_id": conversation_id,
        "session_id": session.session_id,
        "memory_points": list(memory_points),
        "dialogue": [turn.to_dict() for turn in session.turns],
    }


def _write_operation_output_artifacts(
    *,
    paths: ExperimentPaths,
    session_report_records: list[dict[str, Any]],
    update_probe_records: list[dict[str, Any]],
    prediction_records: dict[str, dict[str, Any]],
    answer_prompt_records: list[dict[str, Any]],
    selected_conversations: list[Conversation],
) -> None:
    """稳定写入 operation-level 输出 artifact。"""

    atomic_write_jsonl(paths.session_memory_reports_path, session_report_records)
    atomic_write_jsonl(_update_probe_results_path(paths), update_probe_records)
    question_order = _selected_operation_question_ids(selected_conversations)
    atomic_write_jsonl(
        paths.method_predictions_path,
        [
            prediction_records[question_id]
            for question_id in question_order
            if question_id in prediction_records
        ],
    )
    answer_prompts_by_question = {
        record["question_id"]: record for record in answer_prompt_records
    }
    atomic_write_jsonl(
        paths.answer_prompts_path,
        [
            answer_prompts_by_question[question_id]
            for question_id in question_order
            if question_id in answer_prompts_by_question
        ],
    )


def _selected_operation_question_ids(conversations: list[Conversation]) -> list[str]:
    """返回非 generated session 的 question id 顺序。"""

    question_ids: list[str] = []
    for conversation in conversations:
        generated_session_ids = {
            session.session_id
            for session in conversation.sessions
            if session.private_metadata.get("is_generated_qa_session") is True
        }
        for question in conversation.questions:
            if _question_session_id(question.question_id) in generated_session_ids:
                continue
            question_ids.append(question.question_id)
    return question_ids


def _build_operation_manifest(
    *,
    dataset: Dataset,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    source_paths: tuple[Path, ...],
    efficiency_observability: dict[str, object] | None = None,
) -> dict[str, Any]:
    """构造 operation-level runner manifest。"""

    dataset_fingerprint = build_dataset_fingerprint(dataset, list(source_paths))
    manifest: dict[str, Any] = {
        "schema_version": 2,
        "runner": "operation_level_prediction",
        "run_id": run_context.run_id,
        "benchmark_name": run_context.benchmark_name,
        "method_name": run_context.method_name,
        "model_name": run_context.model_name,
        "benchmark_variant": benchmark_variant,
        "run_scope": run_scope.value,
        "dataset_sha256": dataset_fingerprint["dataset_sha256"],
        "source_fingerprint_sha256": dataset_fingerprint["source_fingerprint_sha256"],
        "policy": {
            "max_workers": policy.max_workers,
            "conversation_ids": (
                list(policy.conversation_ids)
                if policy.conversation_ids is not None
                else None
            ),
        },
        "method": method_manifest,
    }
    if efficiency_observability is not None:
        manifest["efficiency_observability"] = efficiency_observability
    return manifest


def _prepare_operation_run(
    *,
    paths: ExperimentPaths,
    manifest: dict[str, Any],
    resume: bool,
) -> None:
    """写入或校验 operation-level manifest。"""

    if paths.manifest_path.exists():
        existing = json.loads(paths.manifest_path.read_text(encoding="utf-8"))
        if not resume:
            raise ConfigurationError(
                f"Run directory already has a manifest; use resume or a new run_id: {paths.run_dir}"
            )
        if not _manifests_match_for_resume(existing, manifest):
            raise ConfigurationError("Operation-level resume manifest mismatch")
        return
    if resume:
        raise ConfigurationError(
            f"Cannot resume because manifest is missing: {paths.manifest_path}"
        )
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


def _read_json_object(path: Path) -> dict[str, Any]:
    """读取 JSON object；缺失时返回空 dict。"""

    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ConfigurationError(f"Expected JSON object checkpoint: {path}")
    return payload


def _update_probe_results_path(paths: ExperimentPaths) -> Path:
    """返回 HaluMem update probe artifact 路径。"""

    return paths.artifacts_dir / "update_probe_results.jsonl"


__all__ = ["run_operation_level_predictions"]
