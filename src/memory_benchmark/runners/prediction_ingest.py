"""Prediction runner 的公开记忆写入与 ingest checkpoint 流程。

本模块拥有事件流聚合、记忆写入、session report 和 turn-resume 状态；它不负责
manifest 构造、问题回答或 isolated worker 调度。
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from time import perf_counter_ns
from typing import Any

from memory_benchmark.core import Conversation
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemorySystem, BaseResumableMemorySystem
from memory_benchmark.core.provider_protocol import (
    ConversationBatch,
    IngestResult,
    IngestUnit,
    MemoryProvider,
    SessionBatch,
    SessionMemoryReport,
    SessionRef,
    TurnEvent,
    TurnPair,
    UnitRef,
)
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.observability import ProgressReporter
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    EfficiencyObservation,
)
from memory_benchmark.runners.conversation_qa import _make_public_conversation
from memory_benchmark.runners.event_stream import (
    GranularityAggregator,
    build_turn_events,
    default_isolation_key,
)
from memory_benchmark.runners.ingest_resume import (
    TurnIngestCheckpoint,
    TurnIngestCheckpointStore,
)
from memory_benchmark.runners.prediction_observability import _elapsed_ms
from memory_benchmark.runners.prediction_planning import (
    PredictionRunPolicy,
    _STATUS_COMPLETED,
    _STATUS_FAILED_INGEST,
)
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
    read_jsonl,
)
from memory_benchmark.utils.run_logger import RunLogger


@dataclass(frozen=True)
class _ConversationIngestBatch:
    """单个 worker 返回的不可变记忆构建批次。"""

    conversation_id: str
    session_reports: tuple[dict[str, Any], ...] = ()
    observations: tuple[EfficiencyObservation, ...] = ()


def _add_public_conversation_coarse(
    *,
    system: BaseMemorySystem | MemoryProvider,
    run_id: str,
    public_conversation: Conversation,
) -> tuple[dict[str, Any], ...]:
    """isolated worker 使用的 conversation 级写入，不处理逐 turn checkpoint。"""

    if isinstance(system, MemoryProvider):
        return _ingest_memory_provider_conversation(
            provider=system,
            public_conversation=public_conversation,
            run_id=run_id,
        )
    result = system.add([public_conversation])
    if result is None:
        return ()
    if public_conversation.conversation_id not in result.conversation_ids:
        raise ConfigurationError(
            "Method add result did not include expected conversation_id: "
            f"{public_conversation.conversation_id}"
        )
    return ()


def _ingest_pending_conversations(
    conversations: list[Conversation],
    system: BaseMemorySystem | MemoryProvider,
    run_id: str,
    policy: PredictionRunPolicy,
    conversation_status: dict[str, Any],
    paths: ExperimentPaths,
    progress: ProgressReporter,
    logger: RunLogger,
    efficiency_collector: EfficiencyCollector | None,
    efficiency_store: EfficiencyArtifactStore | None,
) -> None:
    """并发写入尚未完成的 conversation，并由协调线程持久化状态。"""

    progress.set_stage("Ingest conversations", step_index=1, step_count=3)
    checkpoint_store = TurnIngestCheckpointStore(
        paths.ingest_turn_checkpoints_dir
    )
    resume_checkpoints = _preflight_ingest_checkpoints(
        conversations=conversations,
        system=system,
        policy=policy,
        conversation_status=conversation_status,
        checkpoint_store=checkpoint_store,
    )
    if any(
        conversation_status.get(conversation.conversation_id, {}).get("status")
        == "completed"
        and resume_checkpoints.get(conversation.conversation_id) is not None
        for conversation in conversations
    ):
        atomic_write_json(paths.conversation_status_path, conversation_status)

    completed = sum(
        1
        for conversation in conversations
        if conversation_status.get(conversation.conversation_id, {}).get("status")
        == "completed"
    )
    pending = [
        conversation
        for conversation in conversations
        if conversation_status.get(conversation.conversation_id, {}).get("status")
        != "completed"
    ]
    if not pending:
        progress.update_conversations(completed, len(conversations), None)
        return

    session_report_records = read_jsonl(paths.session_memory_reports_path)
    with ThreadPoolExecutor(max_workers=policy.max_workers) as executor:
        futures: dict[Future[_ConversationIngestBatch], str] = {
            executor.submit(
                _ingest_one,
                system,
                conversation,
                run_id,
                checkpoint_store,
                resume_checkpoints.get(conversation.conversation_id),
                efficiency_collector,
            ): conversation.conversation_id
            for conversation in pending
        }
        for future in as_completed(futures):
            conversation_id = futures[future]
            try:
                batch = future.result()
            except Exception as exc:
                conversation_status[conversation_id] = {
                    "status": _STATUS_FAILED_INGEST,
                    "stage": "ingest",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "ingested": False,
                }
                atomic_write_json(paths.conversation_status_path, conversation_status)
                logger.log_event(
                    "conversation_failed",
                    {
                        "conversation_id": conversation_id,
                        "stage": "ingest",
                        "error_type": type(exc).__name__,
                    },
                )
                raise
            if efficiency_store is not None:
                efficiency_store.merge_observations(batch.observations)
            if batch.session_reports:
                session_report_records = _merge_session_report_records(
                    existing=session_report_records,
                    conversation_id=batch.conversation_id,
                    new_reports=batch.session_reports,
                )
                _persist_session_memory_reports(
                    paths=paths,
                    session_report_records=session_report_records,
                )
            returned_id = batch.conversation_id
            conversation = next(
                item
                for item in pending
                if item.conversation_id == returned_id
            )
            if _uses_turn_resume(system, conversation):
                checkpoint_store.mark_conversation_completed(
                    conversation_id=returned_id,
                    total_turns=_conversation_turn_count(conversation),
                )
            conversation_status[returned_id] = {
                "status": _STATUS_COMPLETED,
                "ingested": True,
            }
            completed += 1
            atomic_write_json(paths.conversation_status_path, conversation_status)
            progress.update_conversations(
                completed=completed,
                total=len(conversations),
                current_conversation_id=returned_id,
            )
            logger.log_event(
                "conversation_ingested",
                {"conversation_id": returned_id},
            )


def _preflight_ingest_checkpoints(
    conversations: list[Conversation],
    system: BaseMemorySystem | MemoryProvider,
    policy: PredictionRunPolicy,
    conversation_status: dict[str, Any],
    checkpoint_store: TurnIngestCheckpointStore,
) -> dict[str, TurnIngestCheckpoint | None]:
    """在创建任何 worker 前读取并验证全部 conversation checkpoint。

    返回:
        dict: conversation id 到已验证 checkpoint 的映射；无文件时值为 `None`。

    说明:
        预检先完成所有读取和错误判断，再修复 coarse 状态，保证任一 `in_flight`
        都会在 method 调用前终止整个 resume。
    """

    checkpoints: dict[str, TurnIngestCheckpoint | None] = {}
    for conversation in conversations:
        total_turns = _conversation_turn_count(conversation)
        checkpoint = checkpoint_store.load(
            conversation.conversation_id,
            total_turns=total_turns,
        )
        checkpoints[conversation.conversation_id] = checkpoint
        if checkpoint is None:
            continue
        if not _uses_turn_resume(system, conversation):
            raise ConfigurationError(
                "Turn ingest checkpoint exists, but method does not enable "
                "turn-level resume for conversation: "
                f"{conversation.conversation_id}"
            )
        if not policy.resume:
            raise ConfigurationError(
                "Turn ingest checkpoint exists for a non-resume run: "
                f"{conversation.conversation_id}"
            )
        if checkpoint.status == "in_flight":
            raise ConfigurationError(
                "Cannot automatically resume an in_flight turn for conversation: "
                f"{conversation.conversation_id}"
            )
        coarse_status = conversation_status.get(
            conversation.conversation_id, {}
        ).get("status")
        if coarse_status == "completed" and checkpoint.status != "completed":
            raise ConfigurationError(
                "Conversation coarse status is completed but turn checkpoint is not: "
                f"{conversation.conversation_id}"
            )

    for conversation in conversations:
        conversation_id = conversation.conversation_id
        checkpoint = checkpoints[conversation_id]
        if checkpoint is None:
            continue
        if checkpoint.status == "completed":
            conversation_status[conversation_id] = {"status": "completed"}
        elif checkpoint.status == "ready":
            conversation_status[conversation_id] = {
                "status": "ready_for_turn_resume"
            }

    return checkpoints


def _ingest_one(
    system: BaseMemorySystem | MemoryProvider,
    conversation: Conversation,
    run_id: str,
    checkpoint_store: TurnIngestCheckpointStore,
    checkpoint: TurnIngestCheckpoint | None,
    efficiency_collector: EfficiencyCollector | None,
) -> _ConversationIngestBatch:
    """worker 内重建公开 conversation，并选择完整或逐 turn 写入路径。"""

    public_conversation = _make_public_conversation(conversation)
    validate_no_private_keys(public_conversation.to_public_dict())
    if efficiency_collector is not None and efficiency_collector.enabled:
        with efficiency_collector.conversation_scope(
            conversation.conversation_id
        ) as scope:
            started_ns = perf_counter_ns()
            session_reports = _add_public_conversation(
                system=system,
                public_conversation=public_conversation,
                run_id=run_id,
                checkpoint_store=checkpoint_store,
                checkpoint=checkpoint,
            )
            efficiency_collector.record_memory_build_total_latency(
                latency_ms=_elapsed_ms(started_ns)
            )
        return _ConversationIngestBatch(
            conversation_id=conversation.conversation_id,
            session_reports=session_reports,
            observations=scope.records,
        )

    session_reports = _add_public_conversation(
        system=system,
        public_conversation=public_conversation,
        run_id=run_id,
        checkpoint_store=checkpoint_store,
        checkpoint=checkpoint,
    )
    return _ConversationIngestBatch(
        conversation_id=conversation.conversation_id,
        session_reports=session_reports,
    )


def _add_public_conversation(
    *,
    system: BaseMemorySystem | MemoryProvider,
    public_conversation: Conversation,
    run_id: str,
    checkpoint_store: TurnIngestCheckpointStore,
    checkpoint: TurnIngestCheckpoint | None,
) -> tuple[dict[str, Any], ...]:
    """执行一次公开 conversation 写入，并校验 method 返回 id。"""

    if _uses_turn_resume(system, public_conversation):
        total_turns = _conversation_turn_count(public_conversation)
        start_turn_index = (
            checkpoint.next_turn_index if checkpoint is not None else 0
        )
        result = system.add_from_turn(
            conversation=public_conversation,
            start_turn_index=start_turn_index,
            on_turn_started=lambda turn_index, turn: checkpoint_store.mark_started(
                conversation_id=public_conversation.conversation_id,
                turn_index=turn_index,
                turn_id=turn.turn_id,
                total_turns=total_turns,
            ),
            on_turn_completed=lambda turn_index, turn: checkpoint_store.mark_turn_completed(
                conversation_id=public_conversation.conversation_id,
                turn_index=turn_index,
                turn_id=turn.turn_id,
                total_turns=total_turns,
            ),
        )
    elif isinstance(system, MemoryProvider):
        return _ingest_memory_provider_conversation(
            provider=system,
            public_conversation=public_conversation,
            run_id=run_id,
        )
    else:
        result = system.add([public_conversation])
    if public_conversation.conversation_id not in result.conversation_ids:
        raise ConfigurationError(
            "Method add result did not include expected conversation_id: "
            f"{public_conversation.conversation_id}"
        )
    return ()


def _ingest_memory_provider_conversation(
    *,
    provider: MemoryProvider,
    public_conversation: Conversation,
    run_id: str,
) -> tuple[dict[str, Any], ...]:
    """用 v3 conversation batch 调用 provider.ingest 并完成边界回调。"""

    isolation_key = default_isolation_key(run_id, public_conversation.conversation_id)
    events = tuple(build_turn_events(public_conversation, isolation_key))
    session_report_records: list[dict[str, Any]] = []
    units = tuple(
        GranularityAggregator(provider.consume_granularity).aggregate(
            events,
            isolation_key=isolation_key,
        )
    )
    for unit in units:
        if _is_ingest_unit(unit):
            result = provider.ingest(unit)
            session_report_records.extend(
                _session_reports_from_ingest_result(
                    provider=provider,
                    unit=unit,
                    result=result,
                    conversation_id=public_conversation.conversation_id,
                )
            )
            continue
        if isinstance(unit, SessionRef):
            report = provider.end_session(unit)
            if report is not None:
                session_report_records.append(
                    _session_memory_report_payload(
                        report=report,
                        conversation_id=public_conversation.conversation_id,
                        source="end_session",
                    )
                )
            continue
        if isinstance(unit, UnitRef):
            provider.end_conversation(unit)
    if provider.session_memory_report and not session_report_records:
        raise ConfigurationError(
            "Provider declared session_memory_report=True but returned no "
            f"session memory reports: {public_conversation.conversation_id}"
        )
    return tuple(session_report_records)


def _merge_session_report_records(
    *,
    existing: list[dict[str, Any]],
    conversation_id: str,
    new_reports: tuple[dict[str, Any], ...],
) -> list[dict[str, Any]]:
    """按 conversation 替换 session report 记录。

    retry 重新 ingest 同一 conversation 时，旧记录必须被整体替换而不是追加，
    否则 HaluMem extraction 类评测会重复计数。
    """

    kept = [
        record
        for record in existing
        if record.get("conversation_id") != conversation_id
    ]
    kept.extend(new_reports)
    return kept


def _is_ingest_unit(unit: object) -> bool:
    """判断 stream signal 是否应投递给 provider.ingest。"""

    return isinstance(
        unit,
        TurnEvent | TurnPair | SessionBatch | ConversationBatch,
    )


def _session_reports_from_ingest_result(
    *,
    provider: MemoryProvider,
    unit: IngestUnit,
    result: IngestResult | None,
    conversation_id: str,
) -> tuple[dict[str, Any], ...]:
    """把 IngestResult.session_memories 转成 artifact records。"""

    if not provider.session_memory_report or result is None:
        return ()
    if not result.session_memories:
        return ()
    session_ref = _session_ref_from_ingest_result(unit=unit, result=result)
    return (
        {
            "conversation_id": conversation_id,
            "source": "ingest_result",
            "session_ref": asdict(session_ref),
            "memories": list(result.session_memories),
            "metadata": dict(result.metadata),
        },
    )


def _session_ref_from_ingest_result(
    *,
    unit: IngestUnit,
    result: IngestResult,
) -> SessionRef:
    """从 ingest unit/result 中推断 session memory report 的 session ref。"""

    if isinstance(result.unit_ref, SessionRef):
        return result.unit_ref
    if isinstance(unit, SessionBatch):
        return unit.ref
    if isinstance(unit, TurnEvent):
        return SessionRef(
            isolation_key=unit.isolation_key,
            session_id=unit.session_id,
        )
    if isinstance(unit, TurnPair):
        return SessionRef(
            isolation_key=unit.isolation_key,
            session_id=unit.session_id,
        )
    return SessionRef(
        isolation_key=unit.isolation_key,
        session_id=None,
    )


def _session_memory_report_payload(
    *,
    report: SessionMemoryReport,
    conversation_id: str,
    source: str,
) -> dict[str, Any]:
    """把 SessionMemoryReport 转成公开 artifact record。"""

    return {
        "conversation_id": conversation_id,
        "source": source,
        "session_ref": asdict(report.session_ref),
        "memories": list(report.memories),
        "metadata": dict(report.metadata),
    }


def _uses_turn_resume(
    system: BaseMemorySystem | MemoryProvider,
    conversation: Conversation,
) -> bool:
    """判断当前 method/conversation 是否使用逐 turn checkpoint。"""

    return isinstance(system, BaseResumableMemorySystem) and system.supports_turn_resume(
        conversation
    )


def _conversation_turn_count(conversation: Conversation) -> int:
    """返回按 session 原顺序展开后的 turn 总数，并拒绝空历史。"""

    total_turns = sum(len(session.turns) for session in conversation.sessions)
    if total_turns < 1:
        raise ConfigurationError(
            f"Conversation has no turns: {conversation.conversation_id}"
        )
    return total_turns


def _persist_session_memory_reports(
    *,
    paths: ExperimentPaths,
    session_report_records: list[dict[str, Any]],
) -> None:
    """稳定写入 provider session memory report artifact。"""

    if not session_report_records:
        return
    atomic_write_jsonl(paths.session_memory_reports_path, session_report_records)
