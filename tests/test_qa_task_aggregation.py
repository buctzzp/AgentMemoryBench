"""QA task taxonomy 与跨 benchmark 聚合的纯离线强反例。"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from memory_benchmark.analysis.qa_task_aggregation import (
    PHASE1_QA_BENCHMARKS,
    QA_COHORT_RECEIPT_CONTRACT_VERSION,
    QA_TASK_AGGREGATION_CONTRACT_VERSION,
    QACapabilitySlice,
    QANativeTaskScore,
    QAQuestionScore,
    QARunScore,
    build_qa_aggregate_report,
    build_qa_cohort_receipt,
    classify_qa_task,
    load_qa_run_score,
    render_qa_aggregate_report_markdown,
    write_qa_cohort_artifacts,
)
from memory_benchmark.core import ConfigurationError
from memory_benchmark.metrics import (
    BEAM_ORDINARY_QUESTION_CREDIT_PROFILE,
    BEAM_QUESTION_CREDIT_CONTRACT_VERSION,
)
from memory_benchmark.prompts.benchmarks.beam import (
    BEAM_EVENT_ORDERING_CREDIT_PROMPT_PROFILE,
)
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


def test_v3_primary_metric_uses_locomo_semantic_judge() -> None:
    """LoCoMo 横向题分必须读冻结 semantic judge，F1 只保留 native 旁表。"""

    from memory_benchmark.analysis.qa_task_aggregation import (
        PRIMARY_QA_METRIC_BY_BENCHMARK,
    )

    assert PRIMARY_QA_METRIC_BY_BENCHMARK["locomo"] == "locomo_judge_accuracy"


def test_longmemeval_abstention_suffix_overrides_native_question_type_once() -> None:
    """_abs 题只进入 answerability boundary，原 question_type 不重复计权。"""

    native_task, capability = classify_qa_task(
        "longmemeval",
        "single-session-user",
        question_id="0862e8bf_abs",
    )

    assert native_task == "abstention"
    assert capability == "answerability_boundary"


def test_update_false_premise_and_history_conflict_are_separate() -> None:
    """三种失败语义不得重新压进一个 memory-revision 父类。"""

    _, beam_conflict = classify_qa_task(
        "beam", "contradiction_resolution", question_id="q-conflict"
    )
    _, beam_update = classify_qa_task(
        "beam", "knowledge_update", question_id="q-update"
    )
    _, halumem_conflict = classify_qa_task(
        "halumem", "Memory Conflict", question_id="q-memory-conflict"
    )

    assert beam_update == "memory_update"
    assert beam_conflict == "history_contradiction_resolution"
    assert halumem_conflict == "false_premise_correction"
    assert len({beam_update, beam_conflict, halumem_conflict}) == 3


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


@pytest.mark.parametrize(
    ("benchmark", "task"),
    [("locomo", "5"), ("membench", "noisy")],
)
def test_explicitly_excluded_native_tasks_do_not_receive_a_capability(
    benchmark: str,
    task: str,
) -> None:
    """排除项只能由 artifact loader 记账并跳过，不能伪装成 primary 能力。"""

    with pytest.raises(ConfigurationError, match="explicitly excluded"):
        classify_qa_task(benchmark, task, question_id="q-excluded")


def test_beam_loader_uses_v3_question_credit_not_tau_or_rubric_mean(
    tmp_path: Path,
) -> None:
    """event ordering 聚合读整题三档 credit；native tau/rubric 只作旁报。"""

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
                "score": 1.0,
                "ability": ability,
                "details": (
                    {"event_ordering_tau_norm": 1.0}
                    if ability == "event_ordering"
                    else {}
                ),
                "aggregation_question_credit": (
                    0.5 if ability == "event_ordering" else 0.0
                ),
                "aggregation_question_credit_contract_version": (
                    BEAM_QUESTION_CREDIT_CONTRACT_VERSION
                ),
                "aggregation_question_credit_source": (
                    "ordered_compound_rubric_llm"
                    if ability == "event_ordering"
                    else "rubric_item_tristate"
                ),
                "aggregation_question_credit_profile": (
                    BEAM_EVENT_ORDERING_CREDIT_PROMPT_PROFILE
                    if ability == "event_ordering"
                    else BEAM_ORDINARY_QUESTION_CREDIT_PROFILE
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
    assert event.score == 0.5
    assert result.benchmark_score == pytest.approx(0.05)
    assert temporal_slice.score == pytest.approx(0.25)
    assert result.evaluator_identity_complete is True


def test_beam_loader_rejects_old_artifact_without_v3_question_credit(
    tmp_path: Path,
) -> None:
    """旧 BEAM artifact 不得静默回落 rubric mean 或 tau。"""

    run_dir = _write_run(
        tmp_path / "beam-old",
        benchmark="beam",
        method_display_name="A-Mem",
        public_rows=[
            {
                "question_id": "conv-1:event_ordering:q1",
                "conversation_id": "conv-1",
                "question_text": "order",
                "category": "event_ordering",
            }
        ],
        score_rows=[
            {
                "question_id": "conv-1:event_ordering:q1",
                "conversation_id": "conv-1",
                "metric_name": "beam_rubric_judge",
                "score": 1.0,
                "ability": "event_ordering",
                "details": {"event_ordering_tau_norm": 1.0},
            }
        ],
    )

    with pytest.raises(ConfigurationError, match="v3 question-credit contract"):
        load_qa_run_score(run_dir)


def test_capability_slice_pools_questions_and_excludes_membench_noisy(
    tmp_path: Path,
) -> None:
    """能力分一题一票；noisy 保留原生评测但不进入 v3 分母。"""

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

    assert reasoning.score == pytest.approx(10 / 14)
    assert reasoning.question_count == 14
    assert result.excluded_question_ids == ("noisy:q0",)
    assert all(item.native_task != "noisy" for item in result.question_scores)


def test_longmemeval_abstention_loader_needs_only_answer_judge_artifacts(
    tmp_path: Path,
) -> None:
    """M0 boundary 不读取 retrieval artifact，固定 reader 的 answer judge 即为题分。"""

    run_dir = _write_run(
        tmp_path / "lme-abs",
        benchmark="longmemeval",
        method_display_name="A-Mem",
        public_rows=[
            {
                "question_id": "0862e8bf_abs",
                "conversation_id": "0862e8bf",
                "question_text": "What was the hamster called?",
                "category": "single-session-user",
            }
        ],
        score_rows=[
            {
                "question_id": "0862e8bf_abs",
                "conversation_id": "0862e8bf",
                "metric_name": "longmemeval_judge_accuracy",
                "score": 1.0,
                "details": {
                    "prompt_profile": "longmemeval_official_evaluate_qa_v1"
                },
            }
        ],
    )

    result = load_qa_run_score(run_dir)

    assert len(result.question_scores) == 1
    assert result.question_scores[0].native_task == "abstention"
    assert result.question_scores[0].capability == "answerability_boundary"
    assert result.question_scores[0].score == 1.0


def test_overall_pools_questions_instead_of_giving_each_benchmark_one_vote() -> None:
    """高题量 benchmark 的逐题分母可推翻 benchmark 等权多数。"""

    runs: list[QARunScore] = []
    for benchmark in PHASE1_QA_BENCHMARKS:
        question_count = 10 if benchmark == "locomo" else 1
        a_score = 0.0 if benchmark == "locomo" else 1.0
        b_score = 1.0 - a_score
        runs.extend(
            [
                _synthetic_run(
                    "amem", benchmark, a_score, question_count=question_count
                ),
                _synthetic_run(
                    "mem0", benchmark, b_score, question_count=question_count
                ),
            ]
        )

    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert report["status"] == "ok"
    assert report["contract_version"] == QA_TASK_AGGREGATION_CONTRACT_VERSION
    assert report["contract_version"] == "qa-task-aggregation-v3"
    assert report["aggregation"]["weighting"] == "question_pooled_micro"
    assert report["overall"][0]["method"] == "mem0"
    assert report["overall"][0]["overall_qa_score"] == pytest.approx(10 / 14)
    assert report["overall"][1]["overall_qa_score"] == pytest.approx(4 / 14)
    assert {row["question_count"] for row in report["overall"]} == {14}


def test_equal_scores_receive_average_rank() -> None:
    """完全同分时两家均为 1.5 名和 0.5 分，不靠名字破 tie。"""

    runs = [
        _synthetic_run(method, benchmark, 0.5)
        for benchmark in PHASE1_QA_BENCHMARKS
        for method in ("amem", "mem0")
    ]

    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert [row["rank"] for row in report["overall"]] == [1.5, 1.5]
    assert [row["overall_qa_score"] for row in report["overall"]] == [0.5, 0.5]


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


def test_cohort_receipt_is_deterministic_and_contains_no_absolute_run_paths() -> None:
    """显式 run 选择顺序不影响收据，且收据不泄露机器绝对路径。"""

    runs = [
        _synthetic_run(method, benchmark, 0.5)
        for benchmark in PHASE1_QA_BENCHMARKS
        for method in ("amem", "mem0")
    ]

    receipt = build_qa_cohort_receipt(
        runs,
        expected_methods=("amem", "mem0"),
    )
    reversed_receipt = build_qa_cohort_receipt(
        reversed(runs),
        expected_methods=("amem", "mem0"),
    )

    assert receipt == reversed_receipt
    assert receipt["contract_version"] == QA_COHORT_RECEIPT_CONTRACT_VERSION
    assert receipt["status"] == "ok"
    assert len(receipt["cells"]) == 10
    assert len(receipt["receipt_sha256"]) == 64
    assert all("run_dir" not in cell for cell in receipt["cells"])
    assert all(len(cell["cell_identity_sha256"]) == 64 for cell in receipt["cells"])


def test_cohort_receipt_carries_identity_mismatch_without_publishing_rank() -> None:
    """身份漂移必须进入收据诊断，不能因已经能算均值就发布。"""

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
    runs[target] = replace(runs[target], answer_identity_sha256="drifted")

    receipt = build_qa_cohort_receipt(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert receipt["status"] == "incomplete"
    assert receipt["coverage"]["benchmark_identity_errors"] == {
        "locomo": ["answer_identity_sha256_mismatch"]
    }


def test_same_question_id_with_different_isolation_is_not_the_same_cohort() -> None:
    """question_id 相同也不能掩盖 isolation/task identity 漂移。"""

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
    run = runs[target]
    runs[target] = replace(
        run,
        question_scores=(
            replace(run.question_scores[0], isolation_id="different-isolation"),
        ),
    )

    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )

    assert report["status"] == "incomplete"
    assert report["coverage"]["benchmark_identity_errors"] == {
        "locomo": ["question_cohort_mismatch"]
    }


def test_writer_reads_only_explicit_runs_and_withholds_incomplete_ranking(
    tmp_path: Path,
) -> None:
    """writer 不扫描其它 outputs；缺 49 格时仍写诊断但不写部分排名。"""

    run_dir = _write_run(
        tmp_path / "one-explicit-run",
        benchmark="longmemeval",
        method_display_name="A-Mem",
        public_rows=[
            {
                "question_id": "q1",
                "conversation_id": "c1",
                "question_text": "question",
                "category": "single-session-user",
            }
        ],
        score_rows=[
            {
                "question_id": "q1",
                "conversation_id": "c1",
                "metric_name": "longmemeval_judge_accuracy",
                "score": 1.0,
            }
        ],
    )
    manifest_before = (run_dir / "manifest.json").read_bytes()

    receipt_path, report_path, markdown_path = write_qa_cohort_artifacts(
        [run_dir],
        tmp_path / "report",
    )

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    markdown = markdown_path.read_text(encoding="utf-8")
    assert receipt["status"] == report["status"] == "incomplete"
    assert receipt["coverage"]["observed_cell_count"] == 1
    assert report["overall"] == []
    assert "Ranking withheld: cohort is incomplete." in markdown
    assert (run_dir / "manifest.json").read_bytes() == manifest_before


def test_complete_markdown_renders_question_pooled_overall() -> None:
    """完整 cohort 的人类表只呈现现有 pooled-micro 结果，不另造排名公式。"""

    runs = [
        _synthetic_run(method, benchmark, 0.5)
        for benchmark in PHASE1_QA_BENCHMARKS
        for method in ("amem", "mem0")
    ]
    report = build_qa_aggregate_report(
        runs,
        expected_methods=("amem", "mem0"),
    )
    receipt = build_qa_cohort_receipt(
        runs,
        expected_methods=("amem", "mem0"),
    )

    markdown = render_qa_aggregate_report_markdown(receipt, report)

    assert "| rank | method | QA score | credit sum | questions |" in markdown
    assert "| 1.5 | amem | 0.500000 | 2.500 | 5 |" in markdown
    assert "Ranking withheld" not in markdown


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
        "halumem": "halumem_qa",
        "locomo": "locomo_judge_accuracy",
        "longmemeval": "longmemeval_judge_accuracy",
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
            **(
                {
                    "aggregation_question_credit_contract_version": (
                        BEAM_QUESTION_CREDIT_CONTRACT_VERSION
                    )
                }
                if metric == "beam_rubric_judge"
                else {}
            ),
        },
    )
    if metric in {
        "beam_rubric_judge",
        "halumem_qa",
        "locomo_judge_accuracy",
        "longmemeval_judge_accuracy",
    }:
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
    question_count: int = 1,
) -> QARunScore:
    """构造总榜算法测试用的完整 run，不测试 artifact loader。"""

    questions = tuple(
        QAQuestionScore(
            method_name=method,
            benchmark_name=benchmark,
            question_id=f"{benchmark}:q{index}",
            isolation_id=f"{benchmark}:isolation-{index}",
            source_native_task="fixture",
            native_task="fixture",
            capability="fixture_capability",
            score=score,
        )
        for index in range(question_count)
    )
    native = QANativeTaskScore(
        native_task="fixture",
        score=score,
        question_count=question_count,
        question_ids=tuple(item.question_id for item in questions),
    )
    capability = QACapabilitySlice(
        capability="fixture_capability",
        score=score,
        question_count=question_count,
        native_tasks=(native,),
        question_ids=tuple(item.question_id for item in questions),
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
        question_scores=questions,
        capability_slices=(capability,),
        expected_native_tasks=("fixture",),
        observed_native_tasks=("fixture",),
        missing_native_tasks=(),
        missing_question_ids=(),
        extra_score_question_ids=(),
        excluded_question_ids=(),
    )
