"""离线实验分析工具。

本包只读取已经落盘的标准 artifact 或强类型 observation，负责在实验完成后做聚合、
成本换算等派生分析。这里的计算不会反向修改 prediction/evaluation 的不可变结果。
"""

from .cost import APIEmbeddingPrice, APILLMPrice, CostReport, calculate_cost
from .run_cost_report import RunCostReport, TokenSourceMix, build_run_cost_report
from .efficiency import (
    EfficiencySummary,
    EmbeddingTokenSummary,
    LLMTokenSummary,
    NumericStats,
    aggregate_efficiency,
)
from .qa_task_aggregation import (
    PHASE1_QA_BENCHMARKS,
    PHASE1_QA_METHODS,
    PRIMARY_QA_METRIC_BY_BENCHMARK,
    QA_TASK_AGGREGATION_CONTRACT_VERSION,
    QACapabilitySlice,
    QANativeTaskScore,
    QAQuestionScore,
    QARunScore,
    build_qa_aggregate_report,
    classify_qa_task,
    load_qa_run_score,
)

__all__ = [
    "APIEmbeddingPrice",
    "APILLMPrice",
    "CostReport",
    "RunCostReport",
    "TokenSourceMix",
    "build_run_cost_report",
    "EfficiencySummary",
    "EmbeddingTokenSummary",
    "LLMTokenSummary",
    "NumericStats",
    "aggregate_efficiency",
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
    "calculate_cost",
]
