"""Phase 1 QA 任务类型映射与跨 benchmark artifact-only 聚合。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from memory_benchmark.core import ConfigurationError
from memory_benchmark.storage import ExperimentPaths, read_jsonl


QA_TASK_AGGREGATION_CONTRACT_VERSION = "qa-task-aggregation-v2"

PHASE1_QA_BENCHMARKS: tuple[str, ...] = (
    "locomo",
    "longmemeval",
    "beam",
    "membench",
    "halumem",
)

PHASE1_QA_METHODS: tuple[str, ...] = (
    "amem",
    "memoryos",
    "memos",
    "lightmem",
    "simplemem",
    "mem0",
    "letta",
    "everos",
    "langmem",
    "graphiti",
)

PRIMARY_QA_METRIC_BY_BENCHMARK: Mapping[str, str] = {
    "locomo": "locomo_f1",
    "longmemeval": "longmemeval_judge_accuracy",
    "beam": "beam_rubric_judge",
    "membench": "membench_choice_accuracy",
    "halumem": "halumem_qa",
}

_TASK_TO_CAPABILITY: Mapping[str, Mapping[str, str]] = {
    "locomo": {
        "1": "multi_evidence_recall_reasoning",
        "2": "temporal_event_reasoning",
        "3": "generalization_application",
        "4": "factual_recall_extraction",
    },
    "longmemeval": {
        "single-session-user": "factual_recall_extraction",
        "single-session-assistant": "factual_recall_extraction",
        "single-session-preference": "personalization",
        "multi-session": "multi_evidence_recall_reasoning",
        "knowledge-update": "memory_revision",
        "temporal-reasoning": "temporal_event_reasoning",
        "abstention": "answerability_boundary",
    },
    "beam": {
        "abstention": "answerability_boundary",
        "contradiction_resolution": "memory_revision",
        "event_ordering": "temporal_event_reasoning",
        "information_extraction": "factual_recall_extraction",
        "instruction_following": "instruction_following",
        "knowledge_update": "memory_revision",
        "multi_session_reasoning": "multi_evidence_recall_reasoning",
        "preference_following": "personalization",
        "summarization": "long_horizon_summarization",
        "temporal_reasoning": "temporal_event_reasoning",
    },
    "membench": {
        "simple": "factual_recall_extraction",
        "conditional": "multi_evidence_recall_reasoning",
        "comparative": "multi_evidence_recall_reasoning",
        "aggregative": "multi_evidence_recall_reasoning",
        "post_processing": "multi_evidence_recall_reasoning",
        "lowlevel_rec": "factual_recall_extraction",
        "RecMultiSession": "multi_evidence_recall_reasoning",
        "knowledge_update": "memory_revision",
        "highlevel": "personalization",
        "highlevel_rec": "personalization",
        "noisy": "noise_robustness",
    },
    "halumem": {
        "Basic Fact Recall": "factual_recall_extraction",
        "Multi-hop Inference": "multi_evidence_recall_reasoning",
        "Dynamic Update": "memory_revision",
        "Memory Boundary": "answerability_boundary",
        "Memory Conflict": "memory_revision",
        "Generalization & Application": "generalization_application",
    },
}

_METHOD_ALIASES: Mapping[str, str] = {
    "amem": "amem",
    "a-mem": "amem",
    "memoryos": "memoryos",
    "memos": "memos",
    "lightmem": "lightmem",
    "simplemem": "simplemem",
    "mem0": "mem0",
    "letta": "letta",
    "letta/memgpt": "letta",
    "everos": "everos",
    "langmem": "langmem",
    "graphiti": "graphiti",
    "graphiti oss": "graphiti",
}

_LLM_JUDGED_PRIMARY_METRICS = frozenset(
    {
        "longmemeval_judge_accuracy",
        "beam_rubric_judge",
        "halumem_qa",
    }
)


@dataclass(frozen=True)
class QAQuestionScore:
    """一条已完成 QA evaluation 的规范化题分。"""

    method_name: str
    benchmark_name: str
    question_id: str
    isolation_id: str
    source_native_task: str
    native_task: str
    capability: str
    score: float


@dataclass(frozen=True)
class QANativeTaskScore:
    """一个 method×benchmark 内的原生 task 宏平均输入。"""

    native_task: str
    score: float
    question_count: int
    question_ids: tuple[str, ...]


@dataclass(frozen=True)
class QACapabilitySlice:
    """一个 method×benchmark×capability 的原生 task 宏平均。"""

    capability: str
    score: float
    question_count: int
    native_tasks: tuple[QANativeTaskScore, ...]
    question_ids: tuple[str, ...]


@dataclass(frozen=True)
class QARunScore:
    """从一次不可变 run artifact 重建的 QA 聚合输入。"""

    run_dir: Path
    run_id: str
    method_name: str
    benchmark_name: str
    benchmark_variant: str
    run_scope: str
    dataset_identity_sha256: str
    answer_identity_sha256: str
    evaluator_identity_sha256: str | None
    evaluator_identity_complete: bool
    metric_name: str
    benchmark_score: float | None
    question_scores: tuple[QAQuestionScore, ...]
    capability_slices: tuple[QACapabilitySlice, ...]
    expected_native_tasks: tuple[str, ...]
    observed_native_tasks: tuple[str, ...]
    missing_native_tasks: tuple[str, ...]
    missing_question_ids: tuple[str, ...]
    extra_score_question_ids: tuple[str, ...]

    @property
    def question_coverage_complete(self) -> bool:
        """返回公开问题与 score rows 是否一一对应。"""

        return not self.missing_question_ids and not self.extra_score_question_ids

    @property
    def native_task_coverage_complete(self) -> bool:
        """返回 Phase 1 variant 是否覆盖全部预期原生类型。"""

        return not self.missing_native_tasks

    @property
    def publication_input_complete(self) -> bool:
        """返回本 run 是否具备正式聚合的最小 artifact 完整性。"""

        return (
            self.benchmark_score is not None
            and self.question_coverage_complete
            and self.native_task_coverage_complete
            and self.evaluator_identity_complete
        )


def classify_qa_task(
    benchmark_name: str,
    native_task: str,
    *,
    question_id: str,
) -> tuple[str, str]:
    """把官方原生 task 映射为互斥 primary capability。

    返回 ``(effective_native_task, capability)``。LongMemEval ``_abs`` 是官方
    显式 abstention 身份，因此优先覆盖其普通 ``question_type``。
    """

    benchmark = _normalize_benchmark_name(benchmark_name)
    source_task = _require_non_empty_string(native_task, "native task")
    qid = _require_non_empty_string(question_id, "question_id")
    effective_task = (
        "abstention"
        if benchmark == "longmemeval" and qid.endswith("_abs")
        else source_task
    )
    mapping = _TASK_TO_CAPABILITY[benchmark]
    if effective_task not in mapping:
        raise ConfigurationError(
            "unknown QA native task for aggregation contract "
            f"{QA_TASK_AGGREGATION_CONTRACT_VERSION}: "
            f"benchmark={benchmark!r}, task={effective_task!r}"
        )
    return effective_task, mapping[effective_task]


def load_qa_run_score(run_dir: str | Path) -> QARunScore:
    """从标准 run artifacts 重建一份 QA 聚合输入，不调用任何模型。"""

    paths = ExperimentPaths(run_dir=Path(run_dir).resolve())
    manifest = _read_required_json_object(paths.manifest_path, "manifest")
    benchmark = _normalize_benchmark_name(manifest.get("benchmark_name"))
    method = _normalize_method_name(manifest.get("method_name"))
    run_id = _require_non_empty_string(manifest.get("run_id"), "manifest run_id")
    variant = _require_non_empty_string(
        manifest.get("benchmark_variant"), "benchmark_variant"
    )
    run_scope = _require_non_empty_string(manifest.get("run_scope"), "run_scope")
    dataset_sha256 = _require_non_empty_string(
        manifest.get("dataset_sha256"), "dataset_sha256"
    )
    source_fingerprint_sha256 = _require_non_empty_string(
        manifest.get("source_fingerprint_sha256"),
        "source_fingerprint_sha256",
    )
    metric_name = PRIMARY_QA_METRIC_BY_BENCHMARK[benchmark]

    public_rows = _read_required_jsonl(paths.public_questions_path, "public_questions")
    public_by_id = _index_unique_rows(public_rows, "public_questions")
    score_rows = _read_required_jsonl(
        paths.metric_scores_path(metric_name),
        f"answer_scores.{metric_name}",
    )
    score_by_id = _index_unique_rows(score_rows, f"answer_scores.{metric_name}")

    missing_question_ids = tuple(sorted(set(public_by_id) - set(score_by_id)))
    extra_score_question_ids = tuple(sorted(set(score_by_id) - set(public_by_id)))

    question_scores: list[QAQuestionScore] = []
    for question_id in sorted(set(public_by_id) & set(score_by_id)):
        public_row = public_by_id[question_id]
        score_row = score_by_id[question_id]
        source_native_task = _native_task_for_row(
            benchmark,
            public_row=public_row,
            score_row=score_row,
        )
        native_task, capability = classify_qa_task(
            benchmark,
            source_native_task,
            question_id=question_id,
        )
        question_scores.append(
            QAQuestionScore(
                method_name=method,
                benchmark_name=benchmark,
                question_id=question_id,
                isolation_id=_isolation_id(public_row, score_row),
                source_native_task=source_native_task,
                native_task=native_task,
                capability=capability,
                score=_primary_score_for_row(benchmark, score_row),
            )
        )

    observed_native_tasks = tuple(
        sorted({item.native_task for item in question_scores})
    )
    expected_native_tasks = tuple(sorted(_TASK_TO_CAPABILITY[benchmark]))
    missing_native_tasks = tuple(
        sorted(set(expected_native_tasks) - set(observed_native_tasks))
    )
    complete_question_coverage = (
        not missing_question_ids and not extra_score_question_ids
    )
    benchmark_score = (
        _benchmark_primary_score(benchmark, question_scores)
        if complete_question_coverage and not missing_native_tasks
        else None
    )
    evaluator_identity_sha256, evaluator_identity_complete = (
        _evaluator_identity(paths, metric_name, score_rows)
    )

    return QARunScore(
        run_dir=paths.run_dir,
        run_id=run_id,
        method_name=method,
        benchmark_name=benchmark,
        benchmark_variant=variant,
        run_scope=run_scope,
        dataset_identity_sha256=_stable_sha256(
            {
                "benchmark": benchmark,
                "variant": variant,
                "dataset_sha256": dataset_sha256,
                "source_fingerprint_sha256": source_fingerprint_sha256,
            }
        ),
        answer_identity_sha256=_answer_identity(manifest),
        evaluator_identity_sha256=evaluator_identity_sha256,
        evaluator_identity_complete=evaluator_identity_complete,
        metric_name=metric_name,
        benchmark_score=benchmark_score,
        question_scores=tuple(question_scores),
        capability_slices=_build_capability_slices(question_scores),
        expected_native_tasks=expected_native_tasks,
        observed_native_tasks=observed_native_tasks,
        missing_native_tasks=missing_native_tasks,
        missing_question_ids=missing_question_ids,
        extra_score_question_ids=extra_score_question_ids,
    )


def build_qa_aggregate_report(
    runs: Iterable[QARunScore],
    *,
    expected_methods: Sequence[str] = PHASE1_QA_METHODS,
    require_run_scope: str = "formal",
) -> dict[str, Any]:
    """构造固定 roster 的 benchmark 总榜与 capability 榜。

    不完整 cohort 仍返回 coverage diagnostics，但 ``overall`` 为空，避免把部分榜
    误当最终排名。
    """

    roster = tuple(_normalize_method_name(item) for item in expected_methods)
    if len(roster) < 2 or len(set(roster)) != len(roster):
        raise ConfigurationError(
            "expected_methods must contain at least two unique methods"
        )
    indexed: dict[tuple[str, str], QARunScore] = {}
    for run in runs:
        key = (run.method_name, run.benchmark_name)
        if key in indexed:
            raise ConfigurationError(
                "duplicate QA run for method×benchmark: " f"{key[0]}×{key[1]}"
            )
        if run.method_name not in roster:
            raise ConfigurationError(
                f"unexpected method outside fixed QA roster: {run.method_name}"
            )
        indexed[key] = run

    missing_cells = [
        {"method": method, "benchmark": benchmark}
        for method in roster
        for benchmark in PHASE1_QA_BENCHMARKS
        if (method, benchmark) not in indexed
    ]
    invalid_cells: list[dict[str, Any]] = []
    for (method, benchmark), run in sorted(indexed.items()):
        reasons: list[str] = []
        if run.run_scope != require_run_scope:
            reasons.append(f"run_scope={run.run_scope!r}")
        if not run.question_coverage_complete:
            reasons.append("question_coverage_incomplete")
        if not run.native_task_coverage_complete:
            reasons.append("native_task_coverage_incomplete")
        if not run.evaluator_identity_complete:
            reasons.append("evaluator_identity_incomplete")
        if run.benchmark_score is None:
            reasons.append("benchmark_score_unavailable")
        if reasons:
            invalid_cells.append(
                {"method": method, "benchmark": benchmark, "reasons": reasons}
            )

    benchmark_identity_errors = _benchmark_identity_errors(indexed, roster)
    benchmark_tables = _build_benchmark_tables(
        indexed,
        roster,
        require_run_scope=require_run_scope,
        blocked_benchmarks=set(benchmark_identity_errors),
    )
    cohort_complete = not (
        missing_cells or invalid_cells or benchmark_identity_errors
    )
    overall = (
        _build_overall_table(benchmark_tables, roster) if cohort_complete else []
    )
    capabilities = _build_capability_tables(
        indexed,
        roster,
        require_run_scope=require_run_scope,
        blocked_benchmarks=set(benchmark_identity_errors),
    )

    return {
        "contract_version": QA_TASK_AGGREGATION_CONTRACT_VERSION,
        "status": "ok" if cohort_complete else "incomplete",
        "roster": list(roster),
        "benchmarks": list(PHASE1_QA_BENCHMARKS),
        "coverage": {
            "expected_cell_count": len(roster) * len(PHASE1_QA_BENCHMARKS),
            "observed_cell_count": len(indexed),
            "missing_cells": missing_cells,
            "invalid_cells": invalid_cells,
            "benchmark_identity_errors": benchmark_identity_errors,
        },
        "benchmark_tables": benchmark_tables,
        "overall": overall,
        "capabilities": capabilities,
        "excluded_surfaces": [
            "retrieval_metrics",
            "halumem_extraction",
            "halumem_update",
            "halumem_memory_type",
        ],
    }


def _build_capability_slices(
    questions: Sequence[QAQuestionScore],
) -> tuple[QACapabilitySlice, ...]:
    """先按原生 task 取均，再按 capability 对原生 task 宏平均。"""

    by_capability_task: dict[str, dict[str, list[QAQuestionScore]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for item in questions:
        by_capability_task[item.capability][item.native_task].append(item)

    slices: list[QACapabilitySlice] = []
    for capability in sorted(by_capability_task):
        native_scores: list[QANativeTaskScore] = []
        all_question_ids: list[str] = []
        for native_task in sorted(by_capability_task[capability]):
            rows = by_capability_task[capability][native_task]
            question_ids = tuple(sorted(item.question_id for item in rows))
            native_scores.append(
                QANativeTaskScore(
                    native_task=native_task,
                    score=_mean(item.score for item in rows),
                    question_count=len(rows),
                    question_ids=question_ids,
                )
            )
            all_question_ids.extend(question_ids)
        slices.append(
            QACapabilitySlice(
                capability=capability,
                score=_mean(item.score for item in native_scores),
                question_count=sum(item.question_count for item in native_scores),
                native_tasks=tuple(native_scores),
                question_ids=tuple(sorted(all_question_ids)),
            )
        )
    return tuple(slices)


def _benchmark_primary_score(
    benchmark: str,
    questions: Sequence[QAQuestionScore],
) -> float:
    """按 benchmark primary aggregation 计算 raw score。"""

    if not questions:
        raise ConfigurationError("QA score rows must not be empty")
    if benchmark != "beam":
        return _mean(item.score for item in questions)
    by_ability: dict[str, list[float]] = defaultdict(list)
    for item in questions:
        by_ability[item.native_task].append(item.score)
    expected = set(_TASK_TO_CAPABILITY["beam"])
    if set(by_ability) != expected:
        raise ConfigurationError("BEAM primary score requires all ten abilities")
    return _mean(_mean(by_ability[ability]) for ability in sorted(expected))


def _build_benchmark_tables(
    indexed: Mapping[tuple[str, str], QARunScore],
    roster: Sequence[str],
    *,
    require_run_scope: str,
    blocked_benchmarks: set[str],
) -> list[dict[str, Any]]:
    """为每个具备完整同场 roster 的 benchmark 构造排名表。"""

    tables: list[dict[str, Any]] = []
    for benchmark in PHASE1_QA_BENCHMARKS:
        if benchmark in blocked_benchmarks:
            tables.append(
                {"benchmark": benchmark, "status": "identity_mismatch", "rows": []}
            )
            continue
        cells = [indexed.get((method, benchmark)) for method in roster]
        if any(
            cell is None
            or cell.run_scope != require_run_scope
            or not cell.publication_input_complete
            or cell.benchmark_score is None
            for cell in cells
        ):
            tables.append(
                {"benchmark": benchmark, "status": "incomplete", "rows": []}
            )
            continue
        scores = {
            method: float(cell.benchmark_score)
            for method, cell in zip(roster, cells, strict=True)
            if cell is not None and cell.benchmark_score is not None
        }
        ranks = _average_ranks(scores)
        tables.append(
            {
                "benchmark": benchmark,
                "status": "ok",
                "metric_name": PRIMARY_QA_METRIC_BY_BENCHMARK[benchmark],
                "rows": _ranked_rows(scores, ranks),
            }
        )
    return tables


def _build_overall_table(
    benchmark_tables: Sequence[dict[str, Any]],
    roster: Sequence[str],
) -> list[dict[str, Any]]:
    """把五个 benchmark 的 rank-score 等权平均成 overall。"""

    contributions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table in benchmark_tables:
        if table["status"] != "ok":
            raise ConfigurationError("overall requires five complete benchmark tables")
        for row in table["rows"]:
            contributions[row["method"]].append(
                {
                    "benchmark": table["benchmark"],
                    "raw_score": row["raw_score"],
                    "rank": row["rank"],
                    "rank_score": row["rank_score"],
                }
            )
    rows = []
    for method in roster:
        items = contributions[method]
        if len(items) != len(PHASE1_QA_BENCHMARKS):
            raise ConfigurationError("overall contribution count mismatch")
        rows.append(
            {
                "method": method,
                "overall_qa_score": 100 * _mean(x["rank_score"] for x in items),
                "mean_rank": _mean(x["rank"] for x in items),
                "benchmark_contributions": items,
            }
        )
    return sorted(rows, key=lambda item: (-item["overall_qa_score"], item["method"]))


def _build_capability_tables(
    indexed: Mapping[tuple[str, str], QARunScore],
    roster: Sequence[str],
    *,
    require_run_scope: str,
    blocked_benchmarks: set[str],
) -> list[dict[str, Any]]:
    """构造跨 benchmark capability 榜与单 benchmark diagnostic。"""

    capability_benchmarks: dict[str, list[str]] = defaultdict(list)
    for benchmark, mapping in _TASK_TO_CAPABILITY.items():
        for capability in sorted(set(mapping.values())):
            capability_benchmarks[capability].append(benchmark)

    tables: list[dict[str, Any]] = []
    for capability in sorted(capability_benchmarks):
        benchmarks = tuple(
            benchmark
            for benchmark in PHASE1_QA_BENCHMARKS
            if benchmark in capability_benchmarks[capability]
        )
        benchmark_contributions: list[dict[str, Any]] = []
        complete = True
        for benchmark in benchmarks:
            if benchmark in blocked_benchmarks:
                complete = False
                continue
            slices: dict[str, QACapabilitySlice] = {}
            for method in roster:
                run = indexed.get((method, benchmark))
                if (
                    run is None
                    or run.run_scope != require_run_scope
                    or not run.publication_input_complete
                ):
                    complete = False
                    break
                match = next(
                    (
                        item
                        for item in run.capability_slices
                        if item.capability == capability
                    ),
                    None,
                )
                if match is None:
                    complete = False
                    break
                slices[method] = match
            if len(slices) != len(roster):
                continue
            question_sets = {item.question_ids for item in slices.values()}
            if len(question_sets) != 1:
                complete = False
                continue
            scores = {method: item.score for method, item in slices.items()}
            ranks = _average_ranks(scores)
            benchmark_contributions.append(
                {
                    "benchmark": benchmark,
                    "rows": _ranked_rows(scores, ranks),
                }
            )

        cross_benchmark = len(benchmarks) >= 2
        result_rows: list[dict[str, Any]] = []
        if (
            complete
            and cross_benchmark
            and len(benchmark_contributions) == len(benchmarks)
        ):
            by_method: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for contribution in benchmark_contributions:
                for row in contribution["rows"]:
                    by_method[row["method"]].append(
                        {
                            "benchmark": contribution["benchmark"],
                            "raw_score": row["raw_score"],
                            "rank": row["rank"],
                            "rank_score": row["rank_score"],
                        }
                    )
            for method in roster:
                items = by_method[method]
                result_rows.append(
                    {
                        "method": method,
                        "capability_score": 100
                        * _mean(item["rank_score"] for item in items),
                        "mean_rank": _mean(item["rank"] for item in items),
                        "benchmark_contributions": items,
                    }
                )
            result_rows.sort(
                key=lambda item: (-item["capability_score"], item["method"])
            )
        tables.append(
            {
                "capability": capability,
                "kind": "cross_benchmark" if cross_benchmark else "diagnostic",
                "status": "ok" if complete else "incomplete",
                "benchmarks": list(benchmarks),
                "benchmark_tables": benchmark_contributions,
                "rows": result_rows,
            }
        )
    return tables


def _benchmark_identity_errors(
    indexed: Mapping[tuple[str, str], QARunScore],
    roster: Sequence[str],
) -> dict[str, list[str]]:
    """检查同一 benchmark 的 data/question/answer/evaluator 身份。"""

    errors: dict[str, list[str]] = {}
    for benchmark in PHASE1_QA_BENCHMARKS:
        runs = [
            indexed[(method, benchmark)]
            for method in roster
            if (method, benchmark) in indexed
        ]
        if len(runs) != len(roster):
            continue
        reasons: list[str] = []
        for field_name in (
            "benchmark_variant",
            "dataset_identity_sha256",
            "answer_identity_sha256",
            "evaluator_identity_sha256",
        ):
            values = {getattr(run, field_name) for run in runs}
            if len(values) != 1:
                reasons.append(f"{field_name}_mismatch")
        question_sets = {
            tuple(item.question_id for item in run.question_scores) for run in runs
        }
        if len(question_sets) != 1:
            reasons.append("question_cohort_mismatch")
        if reasons:
            errors[benchmark] = reasons
    return errors


def _average_ranks(scores: Mapping[str, float]) -> dict[str, float]:
    """按降序计算平均并列名次；不做隐式近似 tie。"""

    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ranks: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = ((index + 1) + end) / 2
        for method, _ in ordered[index:end]:
            ranks[method] = average_rank
        index = end
    return ranks


def _ranked_rows(
    scores: Mapping[str, float],
    ranks: Mapping[str, float],
) -> list[dict[str, Any]]:
    """返回同时含 raw、rank 和归一 rank-score 的有序行。"""

    method_count = len(scores)
    if method_count < 2:
        raise ConfigurationError("rank aggregation requires at least two methods")
    rows = [
        {
            "method": method,
            "raw_score": score,
            "rank": ranks[method],
            "rank_score": (method_count - ranks[method]) / (method_count - 1),
        }
        for method, score in scores.items()
    ]
    return sorted(rows, key=lambda item: (item["rank"], item["method"]))


def _native_task_for_row(
    benchmark: str,
    *,
    public_row: Mapping[str, Any],
    score_row: Mapping[str, Any],
) -> str:
    """按 benchmark 的公开/score contract 读取原生 task。"""

    if benchmark == "beam":
        value = score_row.get("ability")
    elif benchmark == "halumem":
        value = score_row.get("question_type")
    else:
        value = public_row.get("category")
    return _require_non_empty_string(value, f"{benchmark} native task")


def _primary_score_for_row(
    benchmark: str,
    score_row: Mapping[str, Any],
) -> float:
    """读取 benchmark task-aware QA primary score。"""

    if benchmark == "beam" and score_row.get("ability") == "event_ordering":
        details = score_row.get("details")
        if not isinstance(details, Mapping):
            raise ConfigurationError("BEAM event_ordering details are required")
        value = details.get("event_ordering_tau_norm")
    else:
        value = score_row.get("score")
    if type(value) not in (int, float):
        raise ConfigurationError("QA primary score must be numeric")
    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
        raise ConfigurationError("QA primary score must be finite and within [0, 1]")
    return score


def _isolation_id(
    public_row: Mapping[str, Any],
    score_row: Mapping[str, Any],
) -> str:
    """读取 paired cluster bootstrap 所需 isolation id。"""

    value = score_row.get("conversation_id", public_row.get("conversation_id"))
    return _require_non_empty_string(value, "conversation/isolation id")


def _answer_identity(manifest: Mapping[str, Any]) -> str:
    """提取跨 method 必须相同的 framework answer 身份。"""

    method = manifest.get("method")
    if not isinstance(method, Mapping):
        raise ConfigurationError("manifest method object is required")
    answer_reader = method.get("answer_reader")
    if not isinstance(answer_reader, Mapping):
        raise ConfigurationError("manifest method.answer_reader is required")
    run_identity = method.get("run_identity")
    run_answer_identity: Any = None
    if isinstance(run_identity, Mapping):
        run_answer_identity = {
            "answer_builder": run_identity.get("answer_builder"),
            "answer_builder_identity": run_identity.get("answer_builder_identity"),
        }
    return _stable_sha256(
        {
            "model_name": manifest.get("model_name"),
            "answer_reader": dict(answer_reader),
            "run_answer_identity": run_answer_identity,
            "prompt_track": method.get("prompt_track"),
        }
    )


def _evaluator_identity(
    paths: ExperimentPaths,
    metric_name: str,
    score_rows: Sequence[Mapping[str, Any]],
) -> tuple[str | None, bool]:
    """读取 evaluator model 与 prompt/profile 收据；LLM judge 缺 inventory 即不完整。"""

    summary = _read_required_json_object(
        paths.metric_summary_path(metric_name),
        f"summary.{metric_name}",
    )
    inventory_path = paths.evaluator_model_inventory_path(metric_name)
    inventory: Any = None
    if inventory_path.is_file():
        inventory = _read_required_json_object(
            inventory_path,
            f"model_inventory.{metric_name}",
        )
    prompt_profiles = sorted(
        {
            profile
            for row in score_rows
            if isinstance(row.get("details"), Mapping)
            and isinstance((profile := row["details"].get("prompt_profile")), str)
        }
    )
    complete = metric_name not in _LLM_JUDGED_PRIMARY_METRICS or inventory is not None
    payload = {
        "metric_name": metric_name,
        "model_inventory": inventory,
        "official_source": summary.get("official_source"),
        "profile_note": summary.get("profile_note"),
        "prompt_profiles": prompt_profiles,
    }
    return _stable_sha256(payload), complete


def _normalize_benchmark_name(value: Any) -> str:
    """规范化并校验 Phase 1 benchmark registry 名。"""

    benchmark = _require_non_empty_string(value, "benchmark name").lower()
    if benchmark not in PHASE1_QA_BENCHMARKS:
        raise ConfigurationError(f"unsupported QA aggregation benchmark: {benchmark}")
    return benchmark


def _normalize_method_name(value: Any) -> str:
    """把 manifest 展示名规范化为 method registry key。"""

    method = _require_non_empty_string(value, "method name").lower()
    if method not in _METHOD_ALIASES:
        raise ConfigurationError(f"unknown Phase 1 method name: {value!r}")
    return _METHOD_ALIASES[method]


def _index_unique_rows(
    rows: Sequence[Mapping[str, Any]],
    label: str,
) -> dict[str, Mapping[str, Any]]:
    """按 question_id 建唯一索引。"""

    indexed: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        question_id = _require_non_empty_string(row.get("question_id"), "question_id")
        if question_id in indexed:
            raise ConfigurationError(f"duplicate question_id in {label}: {question_id}")
        indexed[question_id] = row
    return indexed


def _read_required_json_object(path: Path, label: str) -> dict[str, Any]:
    """读取必需 JSON object。"""

    if not path.is_file():
        raise ConfigurationError(f"{label} is missing: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"{label} must be a JSON object")
    return value


def _read_required_jsonl(path: Path, label: str) -> list[dict[str, Any]]:
    """读取非空标准 JSONL。"""

    if not path.is_file():
        raise ConfigurationError(f"{label} is missing: {path}")
    rows = read_jsonl(path)
    if not rows or any(not isinstance(row, dict) for row in rows):
        raise ConfigurationError(f"{label} must contain non-empty JSON objects")
    return rows


def _require_non_empty_string(value: Any, label: str) -> str:
    """读取必填非空字符串。"""

    if type(value) is not str or not value.strip() or value != value.strip():
        raise ConfigurationError(f"{label} must be a non-blank trimmed string")
    return value


def _stable_sha256(value: Any) -> str:
    """对 JSON-compatible identity 做稳定哈希。"""

    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _mean(values: Iterable[float]) -> float:
    """计算非空有限数列的算术平均。"""

    materialized = tuple(float(value) for value in values)
    if not materialized or any(not math.isfinite(value) for value in materialized):
        raise ConfigurationError("mean requires non-empty finite values")
    return sum(materialized) / len(materialized)


__all__ = [
    "PHASE1_QA_BENCHMARKS",
    "PHASE1_QA_METHODS",
    "PRIMARY_QA_METRIC_BY_BENCHMARK",
    "QA_TASK_AGGREGATION_CONTRACT_VERSION",
    "QACapabilitySlice",
    "QANativeTaskScore",
    "QAQuestionScore",
    "QARunScore",
    "build_qa_aggregate_report",
    "classify_qa_task",
    "load_qa_run_score",
]
