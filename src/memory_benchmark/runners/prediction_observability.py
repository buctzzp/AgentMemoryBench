"""Prediction runner 的效率摘要与耗时观测辅助函数。"""

from __future__ import annotations

from time import perf_counter_ns

from memory_benchmark.analysis.efficiency import build_efficiency_report_payloads
from memory_benchmark.observability.efficiency import EfficiencyArtifactStore
from memory_benchmark.storage import ExperimentPaths, atomic_write_json


def _write_prediction_efficiency_summaries(
    *,
    paths: ExperimentPaths,
    efficiency_store: EfficiencyArtifactStore,
) -> None:
    """从 raw observation 派生 prediction 阶段的人类可读效率摘要。

    输入:
        paths: 当前 run 的标准路径集合。
        efficiency_store: prediction 阶段 observation 存储。

    输出:
        None。函数会原子写入 overall、by_conversation 和 by_question 三个 JSON。
    """

    overall, by_conversation, by_question = build_efficiency_report_payloads(
        efficiency_store.read_observations()
    )
    atomic_write_json(paths.prediction_efficiency_overall_summary_path, overall)
    atomic_write_json(
        paths.prediction_efficiency_by_conversation_summary_path,
        by_conversation,
    )
    atomic_write_json(
        paths.prediction_efficiency_by_question_summary_path,
        by_question,
    )


def _elapsed_ms(started_ns: int) -> float:
    """把 ``perf_counter_ns()`` 起点转换为非负的毫秒耗时。"""

    return max((perf_counter_ns() - started_ns) / 1_000_000, 0.0)
