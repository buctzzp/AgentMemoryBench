"""通用 conversation-QA prediction 的兼容 façade 与顶层编排。

具体 planning、preflight、ingest、answer、parallel 和 observability 责任由同名前缀
叶模块拥有；本模块保留历史 import 身份，并只编排一次完整运行。
"""

from __future__ import annotations

import contextlib
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from memory_benchmark.benchmark_adapters.contracts import RunScope
from memory_benchmark.core import (
    AnswerResult,
    Conversation,
    Dataset,
    Question,
    AnswerPromptResult,
)
from memory_benchmark.core.interfaces import BaseMemorySystem
from memory_benchmark.core.provider_protocol import (
    MemoryProvider,
    RetrievalResult,
)
from memory_benchmark.methods.registry import (
    MethodBuildContext,
    resolve_registered_factory_consume_granularity,
    resolve_registered_factory_provenance_granularity,
    resolve_registered_factory_retrieval_evidence_contract_version,
)
from memory_benchmark.observability import (
    ProgressReporter,
    RunContext,
    method_log_scope,
)
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    ModelDescriptor,
    RetrievalObservationContract,
)
from memory_benchmark.readers.answer import FrameworkAnswerReader
from memory_benchmark.runners.ingest_resume import TurnIngestCheckpointStore
from memory_benchmark.runners.prediction_planning import (
    PredictionRunPolicy,
    _ConversationWorkItem,
    _PredictionWorkPlan,
    _STATUS_COMPLETED,
    _STATUS_FAILED_ANSWER,
    _STATUS_FAILED_INGEST,
    _STATUS_PENDING,
    _build_prediction_work_plan,
    _conversation_state_status,
    _select_conversations,
    _selected_questions,
)
from memory_benchmark.runners.prediction_parallel import (
    _ConversationFailureBatch,
    _ConversationWorkItemError,
    _isolated_worker,
    _run_isolated_worker_pipeline,
    _split_into_chunks,
    _split_work_items_by_stable_conversation_order,
)
from memory_benchmark.runners.prediction_observability import (
    _elapsed_ms,
    _write_prediction_efficiency_summaries,
)
from memory_benchmark.runners.prediction_ingest import (
    _ConversationIngestBatch,
    _add_public_conversation,
    _add_public_conversation_coarse,
    _conversation_turn_count,
    _ingest_memory_provider_conversation,
    _ingest_one,
    _ingest_pending_conversations,
    _is_ingest_unit,
    _merge_session_report_records,
    _persist_session_memory_reports,
    _preflight_ingest_checkpoints,
    _session_memory_report_payload,
    _session_ref_from_ingest_result,
    _session_reports_from_ingest_result,
    _uses_turn_resume,
)
from memory_benchmark.runners.prediction_answer import (
    _CONVERSATION_LEVEL_METADATA_KEYS,
    _ConversationAnswerBatch,
    _OpenAICompatibleTokenCounter,
    _RetrieveFirstAnswerError,
    _answer_conversation_questions,
    _answer_pending_questions,
    _answer_prompt_from_retrieval_result,
    _answer_question_retrieve_first,
    _answer_question_retrieve_first_or_reuse,
    _build_conversation_prompts,
    _count_answer_context_tokens,
    _count_openai_compatible_tokens,
    _persist_answer_prompt_records,
    _record_framework_answer_llm_call,
    _retrieval_evidence_payload,
    _retrieval_from_record,
    _retrieval_query_from_question,
    _retrieved_items_payload,
    _strip_conversation_metadata,
    _transform_prediction_if_needed,
    _validate_prediction,
    _validate_retrieval,
)
from memory_benchmark.runners.prediction_preflight import (
    _build_efficiency_observability_manifest,
    _build_manifest,
    _build_prediction_resume_artifacts,
    _cleanup_memory_provider,
    _is_memory_provider,
    _manifest_consume_granularity,
    _manifests_match_for_resume,
    _method_manifest_with_protocol,
    _normalize_manifest_for_resume_compare,
    _require_prediction_system,
    _preflight_prediction_run,
    _prepare_clean_failed_ingest_retries,
    _prepare_memory_provider,
    _prepare_run,
    _read_json_object,
    _validate_concrete_benchmark_variant,
    _validate_consume_granularity,
    _validate_consume_granularity_value,
    _validate_protocol_version,
    _validate_public_manifest,
    _validate_run_manifest_state,
    _validate_run_scope,
    _write_input_artifacts,
    validate_gold_evidence_contract_alignment,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    read_jsonl,
)
from memory_benchmark.utils.run_logger import RunLogger


@dataclass(frozen=True)
class PredictionRunSummary:
    """一次回复生成运行的机器可读摘要。"""

    run_id: str
    dataset_name: str
    total_conversations: int
    completed_conversations: int
    total_questions: int
    completed_questions: int
    prediction_path: str
    private_label_path: str
    summary_path: str
    metadata: dict[str, Any] = field(default_factory=dict)
    failed_conversations: int = 0

    def to_dict(self) -> dict[str, Any]:
        """返回 JSON 可序列化摘要。"""

        return asdict(self)

    @property
    def failed_count(self) -> int:
        """返回 shell/上层 command 可消费的失败 conversation 数。"""

        return self.failed_conversations


_PredictionSystem = BaseMemorySystem | MemoryProvider


def run_predictions(
    dataset: Dataset,
    system: _PredictionSystem,
    run_context: RunContext,
    policy: PredictionRunPolicy,
    method_manifest: dict[str, object],
    benchmark_variant: str,
    run_scope: RunScope,
    source_paths: tuple[str | Path, ...] = (),
    efficiency_collector: EfficiencyCollector | None = None,
    model_inventory: tuple[ModelDescriptor, ...] = (),
    instrumentation_identity: dict[str, object] | None = None,
    retrieval_observation_contract: RetrievalObservationContract | None = None,
    answer_reader: FrameworkAnswerReader | None = None,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ) = None,
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None = None,
    protocol_version: str = "",
    benchmark_policy: dict[str, object] | None = None,
    *,
    system_factory: Callable[
        [MethodBuildContext], _PredictionSystem
    ] | None = None,
    build_context_template: MethodBuildContext | None = None,
    supports_shared_instance_parallelism: bool = False,
    clean_failed_ingest_conversation: (
        Callable[[Conversation, dict[str, Any]], None] | None
    ) = None,
) -> PredictionRunSummary:
    """运行不含 metric 的通用 conversation-QA 回复生成。

    输入:
        dataset: benchmark adapter 生成的完整统一数据集。
        system: 实现 provider v3 ``MemoryProvider``，或仍在退出预算内的完整
            ``BaseMemorySystem`` 的被测记忆系统。
        run_context: 本次运行的标准目录和公开身份。
        policy: conversation/question 范围、并发和 resume 策略。
        answer_reader: retrieve-first provider 路径使用的 framework answer reader。
        method_manifest: method 公开配置和源码身份，不能包含 secret。
        benchmark_variant: 当前 benchmark 的 concrete variant，不能为 `all`。
        run_scope: 本次运行范围，必须是 `RunScope`。
        source_paths: 可选原始数据文件，用于数据指纹审计。
        unified_prompt_builder: 可选 benchmark 级 prompt 构造器；为空时沿用
            method native prompt_messages。
        prediction_transform: 可选 benchmark 级 answer 规整器，用于选择题等固定输出。
        system_factory: 独立 instance 模式下 worker 创建 system 的工厂函数。
        build_context_template: 独立 instance 模式下 worker 构造 context 的模板。
        supports_shared_instance_parallelism: method 是否支持共享实例线程并行。
        clean_failed_ingest_conversation: 可选 conversation 级 clean retry hook；
            只有内置 method 能证明可安全清理半写入状态时才应传入。

    输出:
        PredictionRunSummary: 回复数量和标准 artifact 路径。
    """

    system = _require_prediction_system(system)
    prompt_track = "unified" if unified_prompt_builder is not None else "native"
    declared_provenance_granularity = (
        resolve_registered_factory_provenance_granularity(system_factory)
        if system_factory is not None
        else None
    )
    declared_retrieval_evidence_contract_version = (
        resolve_registered_factory_retrieval_evidence_contract_version(system_factory)
        if system_factory is not None
        else None
    )
    declared_consume_granularity = (
        resolve_registered_factory_consume_granularity(
            system_factory,
            None
            if build_context_template is None
            else build_context_template.benchmark_name,
        )
        if system_factory is not None
        else None
    )
    method_manifest = _method_manifest_with_protocol(
        method_manifest=method_manifest,
        protocol_version=protocol_version,
        prompt_track=prompt_track,
        system=system,
        provenance_granularity=declared_provenance_granularity,
        retrieval_evidence_contract_version=(
            declared_retrieval_evidence_contract_version
        ),
        consume_granularity=declared_consume_granularity,
    )
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
    selected_conversations = _select_conversations(dataset, policy)
    selected_questions = _selected_questions(selected_conversations, policy)
    paths = ExperimentPaths.create(run_context.run_dir)
    _prepare_run(paths=paths, manifest=manifest, resume=policy.resume)
    efficiency_store: EfficiencyArtifactStore | None = None
    if efficiency_collector is not None and efficiency_collector.enabled:
        efficiency_store = EfficiencyArtifactStore.for_prediction(paths)
        efficiency_store.write_model_inventory(model_inventory)
        efficiency_collector.bind_failed_attempt_sink(
            efficiency_store.append_failed_attempt
        )
    with method_log_scope(paths.logs_dir):
        logger = RunLogger(paths.logs_dir)
        atomic_write_json(paths.dataset_fingerprint_path, dataset_fingerprint)
        _write_input_artifacts(
            paths=paths,
            conversations=selected_conversations,
            selected_questions=selected_questions,
        )

        prediction_records = {
            record["question_id"]: record
            for record in read_jsonl(
                paths.method_predictions_path,
                recover_torn_tail=policy.resume,
            )
        }
        conversation_status = _read_json_object(paths.conversation_status_path)
        question_status = {
            record["question_id"]: record
            for record in read_jsonl(
                paths.question_status_path,
                recover_torn_tail=policy.resume,
            )
        }
        question_order = [
            question.question_id
            for conversation in selected_conversations
            for question in selected_questions[conversation.conversation_id]
        ]
        use_isolated = (
            system_factory is not None
            and build_context_template is not None
            and policy.max_workers > 1
            and not supports_shared_instance_parallelism
        )
        # shared/non-isolated v3 provider 的生命周期归本 runner 所有，且保护区必须
        # 从 failed-ingest clean retry **之前**开始：MemOS 这类 provider 的 clean
        # hook 会先 lazy 建好共享 runtime，因此 clean hook、checkpoint preflight 与
        # work-plan 阶段任一失败都可能泄漏后台线程。正常路径仍在写 Completed
        # stage/summary/run_completed 之前显式 close，close() 会弹出回调，
        # 因此 context 退出时不会重复执行。isolated 路径的 provider 由各 worker
        # 自行创建与清理，根 system 不参与。
        with contextlib.ExitStack() as lifecycle_stack:
            if not use_isolated:
                lifecycle_stack.callback(_cleanup_memory_provider, system)
            cleaned_failed_ingest_conversation_ids = _prepare_clean_failed_ingest_retries(
                conversations=selected_conversations,
                conversation_status=conversation_status,
                policy=policy,
                clean_failed_ingest_conversation=clean_failed_ingest_conversation,
                paths=paths,
                logger=logger,
            )
            if not use_isolated:
                checkpoint_store = TurnIngestCheckpointStore(
                    paths.ingest_turn_checkpoints_dir
                )
                _preflight_ingest_checkpoints(
                    conversations=selected_conversations,
                    system=system,
                    policy=policy,
                    conversation_status=conversation_status,
                    checkpoint_store=checkpoint_store,
                )
                atomic_write_json(paths.conversation_status_path, conversation_status)
            work_plan = _build_prediction_work_plan(
                conversations=selected_conversations,
                selected_questions=selected_questions,
                conversation_status=conversation_status,
                prediction_records=prediction_records,
                policy=policy,
            )
            run_control_metadata = {
                "max_new_conversations": policy.max_new_conversations,
                "retry_failed_conversations": policy.retry_failed_conversations,
                "skipped_failed_conversations": list(
                    work_plan.skipped_failed_conversation_ids
                ),
                "budget_exhausted": work_plan.budget_exhausted,
            }
            if cleaned_failed_ingest_conversation_ids:
                run_control_metadata["cleaned_failed_ingest_conversations"] = list(
                    cleaned_failed_ingest_conversation_ids
                )

            _conversation_progress_total = (
                len(work_plan.ingested_conversation_ids) + len(work_plan.items)
            )
            _question_progress_total = (
                len(work_plan.completed_question_ids)
                + sum(len(item.pending_questions) for item in work_plan.items)
            )

            logger.info(
                "[bold]Prediction run[/bold] "
                f"benchmark={dataset.dataset_name} method={run_context.method_name} "
                f"conversations={_conversation_progress_total} questions={_question_progress_total}"
            )
            logger.log_event(
                "run_started",
                {
                    "run_id": run_context.run_id,
                    "benchmark": dataset.dataset_name,
                    "method": run_context.method_name,
                    "resume": policy.resume,
                    "run_control": run_control_metadata,
                },
            )

            with ProgressReporter(
                paths.progress_path,
                enabled=policy.progress_enabled,
            ) as progress:
                progress.start_conversations(_conversation_progress_total)
                progress.start_questions(_question_progress_total)
                if use_isolated:
                    _run_isolated_worker_pipeline(
                        work_plan=work_plan,
                        system_factory=system_factory,
                        build_context_template=build_context_template,
                        run_context=run_context,
                        run_id=run_context.run_id,
                        policy=policy,
                        paths=paths,
                        progress=progress,
                        logger=logger,
                        efficiency_collector=efficiency_collector,
                        efficiency_store=efficiency_store,
                        retrieval_observation_contract=retrieval_observation_contract,
                        prediction_records=prediction_records,
                        conversation_status=conversation_status,
                        question_status=question_status,
                        question_order=question_order,
                        answer_reader=answer_reader,
                        unified_prompt_builder=unified_prompt_builder,
                        prediction_transform=prediction_transform,
                        protocol_version=protocol_version,
                        consume_granularity=_manifest_consume_granularity(
                            method_manifest
                        ),
                    )
                else:
                    _validate_protocol_version(protocol_version, system)
                    _validate_consume_granularity(
                        _manifest_consume_granularity(method_manifest),
                        system,
                    )
                    if work_plan.items:
                        _prepare_memory_provider(system, run_context)
                    ingest_conversations = [
                        item.conversation
                        for item in work_plan.items
                        if item.needs_ingest
                    ]
                    answer_conversations = [
                        item.conversation
                        for item in work_plan.items
                        if item.pending_questions
                    ]
                    pending_selected_questions = {
                        item.conversation.conversation_id: list(item.pending_questions)
                        for item in work_plan.items
                        if item.pending_questions
                    }
                    _ingest_pending_conversations(
                        conversations=ingest_conversations,
                        system=system,
                        run_id=run_context.run_id,
                        policy=policy,
                        conversation_status=conversation_status,
                        paths=paths,
                        progress=progress,
                        logger=logger,
                        efficiency_collector=efficiency_collector,
                        efficiency_store=efficiency_store,
                    )
                    _answer_pending_questions(
                        conversations=answer_conversations,
                        selected_questions=pending_selected_questions,
                        system=system,
                        run_id=run_context.run_id,
                        policy=policy,
                        prediction_records=prediction_records,
                        question_status=question_status,
                        question_order=question_order,
                        paths=paths,
                        progress=progress,
                        logger=logger,
                        efficiency_collector=efficiency_collector,
                        efficiency_store=efficiency_store,
                        retrieval_observation_contract=(
                            retrieval_observation_contract
                        ),
                        answer_reader=answer_reader,
                        unified_prompt_builder=unified_prompt_builder,
                        prediction_transform=prediction_transform,
                    )
                # 正常路径：在既有完成点收敛，早于 Completed/summary/run_completed。
                lifecycle_stack.close()
                progress.set_stage("Completed", step_index=3, step_count=3)
                completed_conversation_count = sum(
                    1
                    for conversation in selected_conversations
                    if conversation_status.get(conversation.conversation_id, {}).get("status")
                    == "completed"
                )
                progress.update_conversations(
                    completed=completed_conversation_count,
                    total=_conversation_progress_total,
                    current_conversation_id=None,
                )
                progress.update_questions(
                    completed=len(prediction_records),
                    total=_question_progress_total,
                    current_conversation_id=None,
                    current_question_id=None,
                )
                progress.flush()

            conversation_prompts = _build_conversation_prompts(prediction_records)
            if conversation_prompts:
                atomic_write_jsonl(
                    paths.conversation_prompts_path,
                    [
                        {"conversation_id": conv_id, **prompts}
                        for conv_id, prompts in conversation_prompts.items()
                    ],
                )
                _strip_conversation_metadata(prediction_records)
                atomic_write_jsonl(
                    paths.method_predictions_path,
                    [
                        prediction_records[qid]
                        for qid in question_order
                        if qid in prediction_records
                    ],
                )

            if efficiency_store is not None:
                _write_prediction_efficiency_summaries(
                    paths=paths,
                    efficiency_store=efficiency_store,
                )

            summary = PredictionRunSummary(
                run_id=run_context.run_id,
                dataset_name=dataset.dataset_name,
                total_conversations=len(selected_conversations),
                completed_conversations=sum(
                    1
                    for conversation in selected_conversations
                    if conversation_status.get(conversation.conversation_id, {}).get("status")
                    == "completed"
                ),
                total_questions=len(question_order),
                completed_questions=sum(
                    1 for question_id in question_order if question_id in prediction_records
                ),
                prediction_path=str(paths.method_predictions_path),
                private_label_path=str(paths.evaluator_private_labels_path),
                summary_path=str(paths.summary_path),
                metadata={"run_control": run_control_metadata},
                failed_conversations=sum(
                    1
                    for conversation in selected_conversations
                    if _conversation_state_status(
                        conversation_status.get(
                            conversation.conversation_id,
                            {},
                        )
                    )
                    in {_STATUS_FAILED_INGEST, _STATUS_FAILED_ANSWER}
                ),
            )
            atomic_write_json(paths.summary_path, summary.to_dict())
            logger.log_event("run_completed", summary.to_dict())
            logger.info(
                "[green]Prediction run completed[/green] "
                f"answers={summary.completed_questions}/{summary.total_questions}"
            )
            return summary


__all__ = [
    "PredictionRunPolicy",
    "PredictionRunSummary",
    "run_predictions",
]
