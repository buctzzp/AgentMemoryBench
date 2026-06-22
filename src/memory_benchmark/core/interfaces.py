"""method / memory module 抽象接口。

Phase 1 当前正在从完整 memory system 协议迁移到 retrieve-first memory module
协议。新 adapter 应优先实现 `BaseMemoryProvider`；旧 `BaseMemorySystem` 暂时保留
用于迁移期兼容。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from .entities import (
    AddResult,
    AnswerPromptResult,
    AnswerResult,
    Conversation,
    Question,
    Turn,
)


class BaseMemoryProvider(ABC):
    """retrieve-first memory module 主接口。

    新 method 只需要实现 conversation 写入和 question 检索。最终答案由 framework
    reader 统一生成。
    """

    @abstractmethod
    def add(self, conversation: Conversation) -> AddResult:
        """写入单个公开 conversation。

        输入:
            conversation: 已清洗的公开 Conversation，不含 gold answer/evidence。

        输出:
            AddResult: 至少包含当前 conversation_id。
        """

        raise NotImplementedError

    @abstractmethod
    def retrieve(self, question: Question) -> AnswerPromptResult:
        """根据公开问题返回 method 构造好的完整 prompt messages。

        输入:
            question: method 可见公开问题。

        输出:
            AnswerPromptResult: `prompt_messages` 是 answer LLM 的完整输入。
        """

        raise NotImplementedError


class BaseMemorySystem(ABC):
    """迁移期完整记忆系统接口。

    该接口代表旧的 `add + get_answer` 协议。新 method 应优先实现
    `BaseMemoryProvider`。
    """

    @abstractmethod
    def add(self, conversations: list[Conversation]) -> AddResult:
        """写入一个或多个 conversation。

        输入:
            conversations: 已完成校验的公开 conversation 列表，不含私有 gold answers。

        输出:
            AddResult: 写入结果，只包含 conversation ids 和公开元信息。
        """

        raise NotImplementedError

    @abstractmethod
    def get_answer(self, question: Question) -> AnswerResult:
        """基于已写入的 conversation 回答公开问题。

        输入:
            question: method 可见问题，不含 gold answer/evidence。

        输出:
            AnswerResult: method 生成答案。
        """

        raise NotImplementedError


class BaseResumableMemorySystem(BaseMemorySystem):
    """可选的逐 turn 安全续写能力。

    普通 benchmark runner 仍只依赖 `BaseMemorySystem`。长 conversation runner
    可以检测该子类，并在每个 turn 前后持久化 method 私有 checkpoint。
    """

    def supports_turn_resume(self, conversation: Conversation) -> bool:
        """返回当前 conversation 是否支持逐 turn 安全续写。

        输入:
            conversation: 已清洗的公开 conversation。

        输出:
            bool: `True` 表示 runner 可以调用 `add_from_turn()`；`False` 表示应退回
            完整 `add([conversation])`，只使用 conversation-level resume。
        """

        return True

    @abstractmethod
    def add_from_turn(
        self,
        conversation: Conversation,
        start_turn_index: int,
        on_turn_started: Callable[[int, Turn], None],
        on_turn_completed: Callable[[int, Turn], None],
    ) -> AddResult:
        """从指定扁平 turn index 开始继续写入一个 conversation。

        输入:
            conversation: 已清洗的公开 conversation。
            start_turn_index: 下一条尚未确认成功的零基 turn index。
            on_turn_started: method 调用前执行的 callback。
            on_turn_completed: method 成功返回后执行的 callback。

        输出:
            AddResult: 当前 conversation 的写入结果。
        """

        raise NotImplementedError


class BaseMemoryRetriever(ABC):
    """历史可选记忆检索接口。

    新主协议已经由 `BaseMemoryProvider` 表达；该类保留给旧测试和迁移期引用。
    """

    @abstractmethod
    def retrieve(self, question: Question) -> AnswerPromptResult:
        """根据公开问题返回完整 prompt messages。

        输入:
            question: method 可见问题。

        输出:
            AnswerPromptResult: method 构造好的完整 prompt messages。
        """

        raise NotImplementedError
