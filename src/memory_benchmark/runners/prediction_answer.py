"""Prediction runner 的 retrieve-first 回答与 answer artifact 流程。

本模块拥有公开 question 的检索、answer builder、framework reader、回答校验与
answer prompt 持久化；它不负责 manifest、记忆写入或 worker 进程调度。
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from time import perf_counter_ns
from typing import Any, Callable

from memory_benchmark.core import (
    AnswerPromptResult,
    AnswerResult,
    PromptMessage,
    Question,
)
from memory_benchmark.core.exceptions import ConfigurationError
from memory_benchmark.core.interfaces import BaseMemorySystem
from memory_benchmark.core.provider_protocol import (
    MemoryProvider,
    RetrievalQuery,
    RetrievalResult,
)
from memory_benchmark.core.validators import validate_no_private_keys
from memory_benchmark.observability import ProgressReporter
from memory_benchmark.observability.efficiency import (
    EfficiencyArtifactStore,
    EfficiencyCollector,
    EfficiencyObservation,
    EfficiencyStage,
    RetrievalObservationContract,
    extract_api_token_usage,
    resolve_token_usage,
)
from memory_benchmark.readers.answer import AnswerLLMResponse, FrameworkAnswerReader
from memory_benchmark.runners.conversation_qa import _make_public_question
from memory_benchmark.runners.event_stream import default_isolation_key
from memory_benchmark.runners.prediction_observability import _elapsed_ms
from memory_benchmark.runners.prediction_planning import PredictionRunPolicy
from memory_benchmark.runners.prediction_preflight import _is_memory_provider
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_jsonl,
    read_jsonl,
)
from memory_benchmark.utils.run_logger import RunLogger


_CONVERSATION_LEVEL_METADATA_KEYS: frozenset[str] = frozenset({"system_prompt"})


@dataclass(frozen=True)
class _ConversationAnswerBatch:
    """单个 worker 返回的不可变回复批次。"""

    conversation_id: str
    predictions: tuple[dict[str, Any], ...]
    retrievals: tuple[dict[str, Any], ...] = ()
    session_reports: tuple[dict[str, Any], ...] = ()
    observations: tuple[EfficiencyObservation, ...] = ()
    ingested: bool = False


class _RetrieveFirstAnswerError(RuntimeError):
    """retrieve-first answer 失败时携带已完成的 retrieval records。"""

    def __init__(
        self,
        *,
        original_error: Exception,
        retrievals: tuple[dict[str, Any], ...],
    ) -> None:
        """保存原始异常和已安全生成的 retrieval records。"""

        super().__init__(str(original_error))
        self.original_error = original_error
        self.retrievals = retrievals


def _answer_pending_questions(
    conversations: list[Conversation],
    selected_questions: dict[str, list[Question]],
    system: BaseMemorySystem | MemoryProvider,
    run_id: str,
    policy: PredictionRunPolicy,
    prediction_records: dict[str, dict[str, Any]],
    question_status: dict[str, dict[str, Any]],
    question_order: list[str],
    paths: ExperimentPaths,
    progress: ProgressReporter,
    logger: RunLogger,
    efficiency_collector: EfficiencyCollector | None,
    efficiency_store: EfficiencyArtifactStore | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
    answer_reader: FrameworkAnswerReader | None,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ),
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None,
) -> None:
    """按 conversation 并发回答问题，并由协调线程提交完整 batch。"""

    progress.set_stage("Answer questions", step_index=2, step_count=3)
    answer_prompt_records = {
        record["question_id"]: record
        for record in read_jsonl(
            paths.answer_prompts_path,
            recover_torn_tail=policy.resume,
        )
    }
    completed = sum(
        1 for question_id in question_order if question_id in prediction_records
    )
    pending_by_conversation: dict[str, list[Question]] = {}
    for conversation in conversations:
        pending_questions = [
            question
            for question in selected_questions[conversation.conversation_id]
            if question.question_id not in prediction_records
        ]
        if pending_questions:
            pending_by_conversation[conversation.conversation_id] = pending_questions

    _answer_question_progress_total = completed + sum(
        len(qs) for qs in pending_by_conversation.values()
    )

    with ThreadPoolExecutor(max_workers=policy.max_workers) as executor:
        futures: dict[Future[_ConversationAnswerBatch], str] = {
            executor.submit(
                _answer_conversation_questions,
                system,
                run_id,
                conversation_id,
                questions,
                efficiency_collector,
                retrieval_observation_contract,
                answer_reader,
                unified_prompt_builder,
                prediction_transform,
                answer_prompt_records,
            ): conversation_id
            for conversation_id, questions in pending_by_conversation.items()
        }
        for future in as_completed(futures):
            conversation_id = futures[future]
            try:
                batch = future.result()
            except Exception as exc:
                logged_error: Exception = exc
                if isinstance(exc, _RetrieveFirstAnswerError):
                    logged_error = exc.original_error
                    for answer_prompt_record in exc.retrievals:
                        answer_prompt_records[answer_prompt_record["question_id"]] = (
                            answer_prompt_record
                        )
                    _persist_answer_prompt_records(
                        paths=paths,
                        answer_prompt_records=answer_prompt_records,
                        question_order=question_order,
                    )
                logger.log_event(
                    "question_batch_failed",
                    {
                        "conversation_id": conversation_id,
                        "stage": "answer",
                        "error_type": type(logged_error).__name__,
                    },
                )
                if isinstance(exc, _RetrieveFirstAnswerError):
                    raise exc.original_error from exc
                raise
            if efficiency_store is not None:
                efficiency_store.merge_observations(batch.observations)
            for answer_prompt_record in batch.retrievals:
                answer_prompt_records[answer_prompt_record["question_id"]] = (
                    answer_prompt_record
                )
            for record in batch.predictions:
                prediction_records[record["question_id"]] = record
                question_status[record["question_id"]] = {
                    "question_id": record["question_id"],
                    "conversation_id": record["conversation_id"],
                    "status": "completed",
                }
                completed += 1
                progress.update_questions(
                    completed=completed,
                    total=_answer_question_progress_total,
                    current_conversation_id=record["conversation_id"],
                    current_question_id=record["question_id"],
                )
                logger.log_event(
                    "question_answered",
                    {
                        "conversation_id": record["conversation_id"],
                        "question_id": record["question_id"],
                    },
                )
            atomic_write_jsonl(
                paths.method_predictions_path,
                [
                    prediction_records[question_id]
                    for question_id in question_order
                    if question_id in prediction_records
                ],
            )
            _persist_answer_prompt_records(
                paths=paths,
                answer_prompt_records=answer_prompt_records,
                question_order=question_order,
            )
            atomic_write_jsonl(
                paths.question_status_path,
                [
                    question_status[question_id]
                    for question_id in question_order
                    if question_id in question_status
                ],
            )


def _persist_answer_prompt_records(
    *,
    paths: ExperimentPaths,
    answer_prompt_records: dict[str, dict[str, Any]],
    question_order: list[str],
) -> None:
    """按 question_order 稳定写入 method 生成的完整 answer prompt artifact。"""

    if not answer_prompt_records:
        return
    atomic_write_jsonl(
        paths.answer_prompts_path,
        [
            answer_prompt_records[question_id]
            for question_id in question_order
            if question_id in answer_prompt_records
        ],
    )


def _answer_conversation_questions(
    system: BaseMemorySystem | MemoryProvider,
    run_id: str,
    conversation_id: str,
    questions: list[Question],
    efficiency_collector: EfficiencyCollector | None,
    retrieval_observation_contract: RetrievalObservationContract | None,
    answer_reader: FrameworkAnswerReader | None,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ) = None,
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None = None,
    existing_retrieval_records: dict[str, dict[str, Any]] | None = None,
) -> _ConversationAnswerBatch:
    """worker 内串行回答一个 conversation 的所有待处理问题。"""

    records: list[dict[str, Any]] = []
    retrieval_records: list[dict[str, Any]] = []
    observations: list[EfficiencyObservation] = []
    existing_retrieval_records = existing_retrieval_records or {}
    for source_question in questions:
        question = _make_public_question(source_question)
        validate_no_private_keys(question.to_dict())
        if efficiency_collector is not None and efficiency_collector.enabled:
            with efficiency_collector.question_scope(
                conversation_id,
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
                else:
                    if not isinstance(
                        retrieval_observation_contract,
                        RetrievalObservationContract,
                    ):
                        raise ConfigurationError(
                            "Enabled efficiency observability requires an explicit "
                            "retrieval observation contract"
                        )
                    prediction = system.get_answer(question)
                    retrieval_record = None
                    if not retrieval_observation_contract.supported_by_method:
                        efficiency_collector.record_retrieval_unsupported_if_missing(
                            retrieval_observation_contract.unsupported_reason or ""
                        )
                if retrieval_record is not None:
                    retrieval_records.append(retrieval_record)
            observations.extend(scope.records)
        else:
            if _is_memory_provider(system):
                prediction, retrieval_record = _answer_question_retrieve_first_or_reuse(
                    provider=system,
                    question=question,
                    run_id=run_id,
                    answer_reader=answer_reader,
                    efficiency_collector=None,
                    unified_prompt_builder=unified_prompt_builder,
                    existing_retrieval_records=existing_retrieval_records,
                )
                if retrieval_record is not None:
                    retrieval_records.append(retrieval_record)
            else:
                prediction = system.get_answer(question)
                retrieval_record = None
        prediction = _transform_prediction_if_needed(
            prediction,
            prediction_transform,
        )
        _validate_prediction(prediction, question)
        validate_no_private_keys(prediction.metadata)
        records.append(
            {
                "question_id": question.question_id,
                "conversation_id": conversation_id,
                "question_text": question.text,
                "answer": prediction.answer,
                "metadata": prediction.metadata,
            }
        )
    return _ConversationAnswerBatch(
        conversation_id=conversation_id,
        predictions=tuple(records),
        retrievals=tuple(retrieval_records),
        observations=tuple(observations),
    )


def _answer_question_retrieve_first(
    *,
    provider: MemoryProvider,
    question: Question,
    run_id: str,
    answer_reader: FrameworkAnswerReader | None,
    efficiency_collector: EfficiencyCollector | None,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ) = None,
) -> tuple[AnswerResult, dict[str, Any]]:
    """执行 retrieve -> framework reader，并返回 prediction 和 answer prompt record。"""

    if answer_reader is None:
        raise ConfigurationError("Retrieve-first prediction requires answer_reader")

    query = _retrieval_query_from_question(question=question, run_id=run_id)
    started_ns = perf_counter_ns()
    if efficiency_collector is not None and efficiency_collector.enabled:
        with efficiency_collector.operation_stage(EfficiencyStage.RETRIEVAL):
            retrieval_result = provider.retrieve(query)
    else:
        retrieval_result = provider.retrieve(query)
    retrieval = _answer_prompt_from_retrieval_result(
        question=question,
        retrieval_result=retrieval_result,
        unified_prompt_builder=unified_prompt_builder,
    )
    _validate_retrieval(retrieval, question)
    if efficiency_collector is not None and efficiency_collector.enabled:
        efficiency_collector.record_retrieval_result_if_missing(
            latency_ms=_elapsed_ms(started_ns),
            injected_memory_context_tokens=_count_answer_context_tokens(
                retrieval.metadata,
                answer_reader.client.model_name,
            ),
        )

    answer_prompt_record = {
        "question_id": retrieval.question_id,
        "conversation_id": retrieval.conversation_id,
        "answer_prompt": retrieval.answer_prompt,
        "prompt_messages": [
            message.to_dict() for message in retrieval.prompt_messages
        ],
        "metadata": retrieval.metadata,
        "formatted_memory": retrieval_result.formatted_memory,
        "retrieved_items": _retrieved_items_payload(retrieval_result),
        "retrieval_query_top_k": query.top_k,
        "retrieval_evidence": _retrieval_evidence_payload(retrieval_result),
    }
    validate_no_private_keys(answer_prompt_record)

    answer_started_ns = perf_counter_ns()
    try:
        prediction, answer_prompt, answer_response = answer_reader.generate_answer_with_trace(
            question=question,
            retrieval=retrieval,
        )
    except Exception as exc:
        raise _RetrieveFirstAnswerError(
            original_error=exc,
            retrievals=(answer_prompt_record,),
        ) from exc
    if efficiency_collector is not None and efficiency_collector.enabled:
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
    return prediction, answer_prompt_record


def _answer_question_retrieve_first_or_reuse(
    *,
    provider: MemoryProvider,
    question: Question,
    run_id: str,
    answer_reader: FrameworkAnswerReader | None,
    efficiency_collector: EfficiencyCollector | None,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ),
    existing_retrieval_records: dict[str, dict[str, Any]],
) -> tuple[AnswerResult, dict[str, Any] | None]:
    """复用已落盘 retrieval，或执行新的 retrieve-first question 流程。"""

    existing_record = existing_retrieval_records.get(question.question_id)
    if existing_record is not None:
        if answer_reader is None:
            raise ConfigurationError("Retrieve-first prediction requires answer_reader")
        retrieval = _retrieval_from_record(existing_record)
        _validate_retrieval(retrieval, question)
        answer_started_ns = perf_counter_ns()
        prediction, answer_prompt, answer_response = answer_reader.generate_answer_with_trace(
            question=question,
            retrieval=retrieval,
        )
        if efficiency_collector is not None and efficiency_collector.enabled:
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
        return prediction, None

    return _answer_question_retrieve_first(
        provider=provider,
        question=question,
        run_id=run_id,
        answer_reader=answer_reader,
        efficiency_collector=efficiency_collector,
        unified_prompt_builder=unified_prompt_builder,
    )


def _retrieval_query_from_question(
    *,
    question: Question,
    run_id: str,
) -> RetrievalQuery:
    """由公开 Question 构造 v3 RetrievalQuery。"""

    return RetrievalQuery(
        query_text=question.text,
        isolation_key=default_isolation_key(run_id, question.conversation_id),
        question_time=question.question_time,
        top_k=10,
        purpose="qa",
        source_question=question,
    )


def _answer_prompt_from_retrieval_result(
    *,
    question: Question,
    retrieval_result: RetrievalResult,
    unified_prompt_builder: (
        Callable[[Question, RetrievalResult], AnswerPromptResult] | None
    ) = None,
) -> AnswerPromptResult:
    """把 v3 RetrievalResult 转换为现有 answer reader 输入。"""

    if unified_prompt_builder is not None:
        return unified_prompt_builder(question, retrieval_result)
    if not retrieval_result.prompt_messages:
        raise ConfigurationError(
            "RetrievalResult.prompt_messages is required while prompt_track is native: "
            f"{question.question_id}"
        )
    legacy_answer_prompt = retrieval_result.metadata.get("bridge_legacy_answer_prompt")
    return AnswerPromptResult(
        question_id=question.question_id,
        conversation_id=question.conversation_id,
        answer_prompt=legacy_answer_prompt if isinstance(legacy_answer_prompt, str) else "",
        prompt_messages=list(retrieval_result.prompt_messages),
        metadata=dict(retrieval_result.metadata),
    )


def _retrieved_items_payload(retrieval_result: RetrievalResult) -> list[dict[str, Any]]:
    """把 v3 retrieved items 转成 artifact 载荷。"""

    if retrieval_result.items is None:
        return []
    return [asdict(item) for item in retrieval_result.items]


def _retrieval_evidence_payload(
    retrieval_result: RetrievalResult,
) -> dict[str, Any] | None:
    """把逐题 RetrievalEvidence 原样序列化为 artifact 载荷；缺失时写 null。

    不读取旧 manifest 或静态声明拼凑逐题值：provider 未返回 evidence 时如实写 None。
    """

    if retrieval_result.evidence is None:
        return None
    return asdict(retrieval_result.evidence)


def _retrieval_from_record(record: dict[str, Any]) -> AnswerPromptResult:
    """从 answer prompt artifact 还原 AnswerPromptResult。"""

    prompt_messages = [
        PromptMessage(
            role=str(message["role"]),
            content=str(message["content"]),
        )
        for message in record.get("prompt_messages") or []
    ]
    return AnswerPromptResult(
        question_id=str(record["question_id"]),
        conversation_id=str(record["conversation_id"]),
        answer_prompt=str(record.get("answer_prompt") or ""),
        prompt_messages=prompt_messages,
        metadata=dict(record.get("metadata") or {}),
    )


def _transform_prediction_if_needed(
    prediction: AnswerResult,
    prediction_transform: Callable[[AnswerResult], AnswerResult] | None,
) -> AnswerResult:
    """按 benchmark 可选规则规整 prediction。"""

    if prediction_transform is None:
        return prediction
    transformed = prediction_transform(prediction)
    if not isinstance(transformed, AnswerResult):
        raise ConfigurationError("prediction_transform must return AnswerResult")
    return transformed


def _validate_retrieval(retrieval: AnswerPromptResult, question: Question) -> None:
    """校验 retrieve 输出与公开问题严格对齐。"""

    if retrieval.question_id != question.question_id:
        raise ConfigurationError(
            f"Retrieval question_id mismatch: {retrieval.question_id} != "
            f"{question.question_id}"
        )
    if retrieval.conversation_id != question.conversation_id:
        raise ConfigurationError(
            "Retrieval conversation_id mismatch: "
            f"{retrieval.conversation_id} != {question.conversation_id}"
        )
    if not retrieval.prompt_messages:
        raise ConfigurationError(
            f"Retrieval prompt_messages is empty: {question.question_id}"
        )
    if not retrieval.answer_prompt.strip():
        retrieval.answer_prompt = "\n\n".join(
            f"[{message.role}]\n{message.content}"
            for message in retrieval.prompt_messages
        )
    validate_no_private_keys(retrieval.metadata)


def _count_answer_context_tokens(
    metadata: dict[str, Any],
    model_name: str,
) -> int | None:
    """如果 method 提供 answer_context，则计算该诊断字段的 token 数。"""

    answer_context = metadata.get("answer_context")
    if not isinstance(answer_context, str) or not answer_context.strip():
        return None
    return _count_openai_compatible_tokens(answer_context, model_name)


def _count_openai_compatible_tokens(text: str, model_name: str) -> int:
    """按 framework answer LLM 的 OpenAI-compatible tokenizer 估算文本 token。"""

    if not text:
        return 0
    try:
        import tiktoken
    except Exception as exc:
        raise ConfigurationError(
            "tiktoken is required for framework answer context token estimation"
        ) from exc
    try:
        encoding = tiktoken.encoding_for_model(model_name)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


class _OpenAICompatibleTokenCounter:
    """按 OpenAI-compatible 模型名计数 token 的 runner 侧轻量 wrapper。"""

    def __init__(self, model_name: str) -> None:
        """保存模型名，encoding 懒加载。"""

        self.model_name = model_name
        self._encoding = None

    def count_tokens(self, text: str) -> int:
        """返回文本 token 数；未知模型回退到 cl100k_base。"""

        if self._encoding is None:
            try:
                import tiktoken
            except Exception as exc:
                raise ConfigurationError(
                    "tiktoken is required for framework answer token estimation"
                ) from exc
            try:
                self._encoding = tiktoken.encoding_for_model(self.model_name)
            except KeyError:
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text or ""))


def _record_framework_answer_llm_call(
    *,
    efficiency_collector: EfficiencyCollector,
    model_id: str,
    model_name: str,
    prompt_text: str,
    answer_text: str,
    response: AnswerLLMResponse,
) -> None:
    """记录 framework reader answer LLM 的 token usage。"""

    api_input_tokens, api_output_tokens = extract_api_token_usage(response.usage)
    token_usage = resolve_token_usage(
        api_input_tokens=api_input_tokens,
        api_output_tokens=api_output_tokens,
        prompt_text=prompt_text,
        output_text=answer_text,
        tokenizer=_OpenAICompatibleTokenCounter(model_name),
    )
    efficiency_collector.record_llm_call(
        model_id=model_id,
        input_tokens=token_usage.input_tokens,
        output_tokens=token_usage.output_tokens,
        token_measurement_source=token_usage.source,
    )


def _validate_prediction(prediction: AnswerResult, question: Question) -> None:
    """校验 method 返回值与公开问题严格对齐。"""

    if prediction.question_id != question.question_id:
        raise ConfigurationError(
            f"Prediction question_id mismatch: {prediction.question_id} != "
            f"{question.question_id}"
        )
    if prediction.conversation_id != question.conversation_id:
        raise ConfigurationError(
            f"Prediction conversation_id mismatch: {prediction.conversation_id} != "
            f"{question.conversation_id}"
        )
    if not prediction.answer.strip():
        raise ConfigurationError(
            f"Method returned an empty answer for question: {question.question_id}"
        )


def _build_conversation_prompts(
    prediction_records: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """从已完成预测记录中提取每个 conversation 的共享 prompt 文本。

    同一 conversation 的首条记录的 `metadata.system_prompt` 被作为该 conversation
    的共享 prompt。后续问题记录中该字段已去重移除。
    """

    prompts: dict[str, dict[str, Any]] = {}
    for record in prediction_records.values():
        conv_id = record["conversation_id"]
        if conv_id in prompts:
            continue
        extracted: dict[str, Any] = {}
        for key in _CONVERSATION_LEVEL_METADATA_KEYS:
            value = record.get("metadata", {}).get(key)
            if value is not None:
                extracted[key] = value
        if extracted:
            prompts[conv_id] = extracted
    return prompts


def _strip_conversation_metadata(
    prediction_records: dict[str, dict[str, Any]],
) -> None:
    """从所有预测记录的 metadata 中移除已去重的 conversation 级字段。"""

    for record in prediction_records.values():
        metadata = record.get("metadata", {})
        if not metadata:
            continue
        for key in _CONVERSATION_LEVEL_METADATA_KEYS:
            metadata.pop(key, None)
