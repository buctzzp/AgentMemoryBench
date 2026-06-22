"""core 层统一导出入口。"""

from .capabilities import MethodCapability, TaskFamily, validate_compatibility
from .entities import (
    AddResult,
    AnswerPromptResult,
    AnswerResult,
    Conversation,
    Dataset,
    EvaluationResult,
    GoldAnswerInfo,
    ImageRef,
    MetricResult,
    PromptMessage,
    Question,
    RetrievedMemory,
    Session,
    Turn,
)
from .exceptions import (
    AdapterAlreadyRegisteredError,
    ConfigurationError,
    DataLeakageError,
    DatasetNotFoundError,
    DatasetValidationError,
    JudgeOutputError,
    MemoryBenchmarkError,
    UnknownBenchmarkError,
)
from .interfaces import (
    BaseMemoryProvider,
    BaseMemoryRetriever,
    BaseMemorySystem,
    BaseResumableMemorySystem,
)
from .results import DryRunSummary

__all__ = [
    "AddResult",
    "AnswerPromptResult",
    "AdapterAlreadyRegisteredError",
    "AnswerResult",
    "BaseMemoryProvider",
    "BaseMemoryRetriever",
    "BaseResumableMemorySystem",
    "BaseMemorySystem",
    "ConfigurationError",
    "Conversation",
    "DataLeakageError",
    "Dataset",
    "DatasetNotFoundError",
    "DatasetValidationError",
    "DryRunSummary",
    "EvaluationResult",
    "GoldAnswerInfo",
    "ImageRef",
    "JudgeOutputError",
    "MethodCapability",
    "MemoryBenchmarkError",
    "MetricResult",
    "PromptMessage",
    "Question",
    "RetrievedMemory",
    "Session",
    "TaskFamily",
    "Turn",
    "UnknownBenchmarkError",
    "validate_compatibility",
]
