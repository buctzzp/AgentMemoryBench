"""QA task taxonomy 与跨 benchmark 聚合的纯离线强反例。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from memory_benchmark.analysis.qa_task_aggregation import (
    PHASE1_QA_BENCHMARKS,
    QA_TASK_AGGREGATION_CONTRACT_VERSION,
    QACapabilitySlice,
    QANativeTaskScore,
    QAQuestionScore,
    QARunScore,
    build_qa_aggregate_report,
    classify_qa_task,
    load_qa_run_score,
)
from memory_benchmark.core import ConfigurationError
from memory_benchmark.storage import (
    ExperimentPaths,
    atomic_write_json,
    atomic_write_jsonl,
)


_BEAM_ABILITIES = (
    "abstention",
    "contradiction_resolution",
    "event_ordering",
    "information_extraction",
    "instruction_following",
    "knowledge_update",
    "multi_session_reasoning",
    "preference_following",
    "summarization",
    "temporal_reasoning",
)

_MEMBENCH_TASKS = (
    "simple",
    "conditional",
    "comparative",
    "aggregative",
    "post_processing",
    "lowlevel_rec",
    "RecMultiSession",
    "knowledge_update",
    "highlevel",
    "highlevel_rec",
    "noisy",
)


def test_taxonomy_keeps_personalization_and_instruction_following_separate() -> None:
    """偏好应用与指令遵循不是同一能力族。"""

    _, preference = classify_qa_task(
        "beam", "preference_following", question_id="q-preference"
    )
    _, instruction = classify_qa_task(
        "beam", "instruction_following", question_id="q-instruction"
    )

    assert preference == "personalization"
    assert instruction == "instruction_following"
    assert preference != instruction


def test_longmemeval_abstention_suffix_overrides_native_question_type_once() -> None:
    """_abs 题只进入 answerability boundary，原 question_type 不重复计权。"""

    native_task, capability = classify_qa_task(
        "longmemeval",
        "single-session-user",
        question_id="0862e8bf_abs",
    )

    assert native_task == "abstention"
    assert capability == "answerability_boundary"


def test_conflict_and_update_share_memory_revision_parent() -> None:
    """Conflict 保留 native task，但不另造第二个跨 benchmark 父能力。"""

    _, beam_conflict = classify_qa_task(
        "beam", "contradiction_resolution", question_id="q-conflict"
    )
    _, beam_update = classify_qa_task(
        "beam", "knowledge_update", question_id="q-update"
    )
    _, halumem_conflict = classify_qa_task(
        "halumem", "Memory Conflict", question_id="q-memory-conflict"
    )

    assert beam_conflict == beam_update == halumem_conflict == "memory_revision"


def test_generalization_is_not_collapsed_into_personalization() -> None:
    """常识/新场景应用与偏好个性化保留不同失败语义。"""

    _, locomo = classify_qa_task("locomo", "3", question_id="q-commonsense")
    _, halumem = classify_qa_task(
        "halumem",
        "Generalization & Application",
        question_id="q-application",
    )
    _, preference = classify_qa_task(
        "longmemeval",
        "single-session-preference",
        question_id="q-preference",
    )

    assert locomo == halumem == "generalization_application"
    assert preference == "personalization"


def test_membench_recommendation_memory_keeps_recall_granularity() -> None:
    """单域推荐回顾是事实回顾，跨域多会话推荐才进入多证据能力。"""

    _, single = classify_qa_task(
        "membench", "lowlevel_rec", question_id="q-single-recommendation"
    )
    _, cross_session = classify_qa_task(
        "membench", "RecMultiSession", question_id="q-multi-recommendation"
    )

    assert single == "factual_recall_extraction"
    assert cross_session == "multi_evidence_recall_reasoning"


def test_unknown_native_task_fails_loud() -> None:
    """数据源新增类型时必须 bump/审查合同，不能静默塞进 misc。"""

    with pytest.raises(ConfigurationError, match="unknown QA native task"):
        classify_qa_task("locomo", "99", question_id="q-unknown")


def test_beam_loader_uses_tau_norm_for_event_ordering(tmp_path: Path) -> None:
    """event_ordering 必须按官方 report consumer 读 tau_norm，而非 rubric score。"""

    public_rows = []
    score_rows = []
    for ability in _BEAM_ABILITIES:
        question_id = f"conv-1:{ability}:q1"
        public_rows.append(
            {
                "question_id": question_id,
                "conversation_id": "conv-1",
                "question_text": ability,
                "category": ability,
            }
        )
        score_rows.append(
            {
                "question_id": question_id,
                "conversation_id": "conv-1",
                "metric_name": "beam_rubric_judge",
                "score": 0.0,
                "ability": ability,
                "details": (
                    {"event_ordering_tau_norm": 1.0}
                    if ability == "event_ordering"
                    else {}
                ),
            }
        )
    run_dir = _write_run(
        tmp_path / "beam-run",
        benchmark="beam",
        method_display_name="A-Mem",
        public_rows=public_rows,
        score_rows=score_rows,
    )

    result = load_qa_run_score(run_dir)

    event = next(
        item for item in result.question_scores if item.native_task == "event_ordering"
    )
    temporal_slice = next(
        item
        for item in result.capability_slices
        if item.capability == "temporal_event_reasoning"
    )
    assert event.score == 1.0
    assert result.benchmark_score == pytest.approx(0.1)
    assert temporal_slice.score == pytest.approx(0.5)


def test_capability_slice_macro_averages_native_tasks_not_question_counts(
    tmp_path: Path,
) -> None:
    """一个原生 subtype 题多时不得在 capability 内获得额外权重。"""

    public_rows = []
    score_rows = []
    for task in _MEMBENCH_TASKS:
        count = 10 if task == "conditional" else 1
        for index in range(count):
            question_id = f"{task}:q{index}"
            public_rows.append(
                {
                    "question_id": question_id,
                    "conversation_id": f"tid-{task}",
                    "question_text": task,
                    "category": task,
                }
            )
            score_rows.append(
                {
                    "question_id": question_id,
                    "conversation_id": f"tid-{task}",
                    "metric_name": "membench_choice_accuracy",
                    "score": 1.0 if task == "conditional" else 0.0,
                }
            )
    run_dir = _write_run(
        tmp_path / "membench-run",
        benchmark="membench",
        method_display_name="A-Mem",
        public_rows=public_rows,
        score_rows=score_rows,
    )

    result = load_qa_run_score(run_dir)
    reasoning = next(
        item
        for item in result.capability_slices
        if item.capability == "multi_evidence_recall_reasoning"
    )

    # 五个 native tasks 等权：conditional=1，其余四类=0，所以是 1/5；
    # lowlevel_rec 已按显式回顾归入 factual，不再混进推理分母。若错误按题
    # micro-average，这里会得到 10/14。
    assert reasoning.score == pytest.approx(1 / 5)
    assert reasoning.question_count == 14


def test_overall_gives_each_benchmark_one_vote_not_each_question() -> None:
    """五格等权；三格胜两格的 method 获得更高 overall。"""

    runs: list[QARunScore] = []
    for index, benchmark in enumerate(PHASE1_QA_BENCHMARKS):
        a_score = 1.0 if index < 3 else 0.0
        b_score = 1.0 - a_score
        runs.extend(
            [
                _synthetic_run("amem", benchmark, a_score),
                _synthetic_run("mem0", benchmark, b_score),
            ]
        )

    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert report["status"] == "ok"
    assert report["contract_version"] == QA_TASK_AGGREGATION_CONTRACT_VERSION
    assert report["contract_version"] == "qa-task-aggregation-v2"
    assert report["overall"][0]["method"] == "amem"
    assert report["overall"][0]["overall_qa_score"] == pytest.approx(60.0)
    assert report["overall"][1]["overall_qa_score"] == pytest.approx(40.0)


def test_equal_scores_receive_average_rank() -> None:
    """完全同分时两家均为 1.5 名和 50 分，不靠名字破 tie。"""

    runs = [
        _synthetic_run(method, benchmark, 0.5)
        for benchmark in PHASE1_QA_BENCHMARKS
        for method in ("amem", "mem0")
    ]

    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert [row["mean_rank"] for row in report["overall"]] == [1.5, 1.5]
    assert [row["overall_qa_score"] for row in report["overall"]] == [50.0, 50.0]


def test_missing_cell_is_incomplete_without_zero_fill_or_smaller_denominator() -> None:
    """缺格不得生成部分 overall，也不得补零。"""

    runs = [
        _synthetic_run(method, benchmark, 0.5)
        for benchmark in PHASE1_QA_BENCHMARKS
        for method in ("amem", "mem0")
        if not (method == "mem0" and benchmark == "halumem")
    ]

    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert report["status"] == "incomplete"
    assert report["overall"] == []
    assert report["coverage"]["missing_cells"] == [
        {"method": "mem0", "benchmark": "halumem"}
    ]


def test_smoke_run_is_not_publication_eligible() -> None:
    """smoke/pilot 可验管线，但不能混入 formal 主榜。"""

    runs = [
        _synthetic_run(
            method,
            benchmark,
            0.5,
            run_scope=(
                "smoke"
                if method == "mem0" and benchmark == "beam"
                else "formal"
            ),
        )
        for benchmark in PHASE1_QA_BENCHMARKS
        for method in ("amem", "mem0")
    ]

    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert report["status"] == "incomplete"
    assert report["overall"] == []
    beam_table = next(
        item for item in report["benchmark_tables"] if item["benchmark"] == "beam"
    )
    assert beam_table["status"] == "incomplete"
    assert report["coverage"]["invalid_cells"] == [
        {
            "method": "mem0",
            "benchmark": "beam",
            "reasons": ["run_scope='smoke'"],
        }
    ]


def test_answer_identity_mismatch_blocks_benchmark_and_overall() -> None:
    """同 benchmark 的 answer model/prompt identity 不同不得同场排名。"""

    runs = [
        _synthetic_run(method, benchmark, 0.5)
        for benchmark in PHASE1_QA_BENCHMARKS
        for method in ("amem", "mem0")
    ]
    target = next(
        index
        for index, run in enumerate(runs)
        if run.method_name == "mem0" and run.benchmark_name == "locomo"
    )
    runs[target] = replace(runs[target], answer_identity_sha256="different-answer")

    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert report["status"] == "incomplete"
    assert report["overall"] == []
    assert report["coverage"]["benchmark_identity_errors"] == {
        "locomo": ["answer_identity_sha256_mismatch"]
    }
    locomo = next(
        item
        for item in report["benchmark_tables"]
        if item["benchmark"] == "locomo"
    )
    assert locomo == {
        "benchmark": "locomo",
        "status": "identity_mismatch",
        "rows": [],
    }


def test_report_explicitly_excludes_retrieval_and_halumem_operation_metrics() -> None:
    """QA 合同必须公开排除面，不能靠读者猜。"""

    report = build_qa_aggregate_report([], expected_methods=("amem", "mem0"))

    assert report["excluded_surfaces"] == [
        "retrieval_metrics",
        "halumem_extraction",
        "halumem_update",
        "halumem_memory_type",
    ]


def _write_run(
    run_dir: Path,
    *,
    benchmark: str,
    method_display_name: str,
    public_rows: list[dict[str, object]],
    score_rows: list[dict[str, object]],
) -> Path:
    """写入 loader 强反例所需的最小标准 artifacts。"""

    paths = ExperimentPaths.create(run_dir)
    metric = {
        "beam": "beam_rubric_judge",
        "membench": "membench_choice_accuracy",
    }[benchmark]
    atomic_write_json(
        paths.manifest_path,
        {
            "schema_version": 2,
            "run_id": run_dir.name,
            "benchmark_name": benchmark,
            "method_name": method_display_name,
            "model_name": "model",
            "dataset_sha256": "dataset",
            "source_fingerprint_sha256": "source",
            "benchmark_variant": "variant",
            "run_scope": "formal",
            "method": {
                "answer_reader": {
                    "answer_protocol": "retrieve_first_v1",
                    "answer_prompt_profile": "benchmark",
                    "answer_model": "model",
                    "answer_parameters": {"temperature": 0.0},
                },
                "prompt_track": "profile",
            },
        },
    )
    atomic_write_jsonl(paths.public_questions_path, public_rows)
    atomic_write_jsonl(paths.metric_scores_path(metric), score_rows)
    atomic_write_json(
        paths.metric_summary_path(metric),
        {
            "metric_name": metric,
            "official_source": "fixture",
            "profile_note": "fixture",
        },
    )
    if metric == "beam_rubric_judge":
        atomic_write_json(
            paths.evaluator_model_inventory_path(metric),
            {
                "schema_version": 1,
                "models": [
                    {
                        "model_id": "judge",
                        "model_name": "model",
                        "model_role": "judge_llm",
                        "execution_mode": "api",
                    }
                ],
            },
        )
    return paths.run_dir


def _synthetic_run(
    method: str,
    benchmark: str,
    score: float,
    *,
    run_scope: str = "formal",
) -> QARunScore:
    """构造总榜算法测试用的完整 run，不测试 artifact loader。"""

    question = QAQuestionScore(
        method_name=method,
        benchmark_name=benchmark,
        question_id=f"{benchmark}:q1",
        isolation_id=f"{benchmark}:isolation-1",
        source_native_task="fixture",
        native_task="fixture",
        capability="fixture_capability",
        score=score,
    )
    native = QANativeTaskScore(
        native_task="fixture",
        score=score,
        question_count=1,
        question_ids=(question.question_id,),
    )
    capability = QACapabilitySlice(
        capability="fixture_capability",
        score=score,
        question_count=1,
        native_tasks=(native,),
        question_ids=(question.question_id,),
    )
    return QARunScore(
        run_dir=Path(f"/{method}/{benchmark}"),
        run_id=f"{method}-{benchmark}",
        method_name=method,
        benchmark_name=benchmark,
        benchmark_variant="variant",
        run_scope=run_scope,
        dataset_identity_sha256=f"dataset-{benchmark}",
        answer_identity_sha256=f"answer-{benchmark}",
        evaluator_identity_sha256=f"evaluator-{benchmark}",
        evaluator_identity_complete=True,
        metric_name=f"metric-{benchmark}",
        benchmark_score=score,
        question_scores=(question,),
        capability_slices=(capability,),
        expected_native_tasks=("fixture",),
        observed_native_tasks=("fixture",),
        missing_native_tasks=(),
        missing_question_ids=(),
        extra_score_question_ids=(),
    )
