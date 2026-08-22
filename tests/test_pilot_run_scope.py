"""测试成本 pilot 读取完整首 isolation，而不是放大版 smoke crop。"""

from __future__ import annotations

from pathlib import Path

import pytest

from memory_benchmark.benchmark_adapters import beam, halumem, locomo, membench
from memory_benchmark.benchmark_adapters import registry as benchmark_registry
from memory_benchmark.benchmark_adapters.contracts import (
    BenchmarkLoadRequest,
    RunScope,
)
from memory_benchmark.core import (
    Conversation,
    Dataset,
    GoldAnswerInfo,
    Question,
    Session,
    Turn,
)


pytestmark = pytest.mark.unit


def _dataset(conversation_id: str, *, turn_count: int = 5) -> Dataset:
    """构造含完整 history 与两个问题的公开测试 Dataset。"""

    question_ids = (f"{conversation_id}:q1", f"{conversation_id}:q2")
    return Dataset(
        dataset_name="fake",
        conversations=[
            Conversation(
                conversation_id=conversation_id,
                sessions=[
                    Session(
                        session_id=f"{conversation_id}:s1",
                        turns=[
                            Turn(
                                turn_id=f"{conversation_id}:t{index}",
                                speaker="user" if index % 2 else "assistant",
                                content=f"message {index}",
                            )
                            for index in range(1, turn_count + 1)
                        ],
                    )
                ],
                questions=[
                    Question(
                        question_id=question_id,
                        conversation_id=conversation_id,
                        text=f"question {index}",
                    )
                    for index, question_id in enumerate(question_ids, start=1)
                ],
                gold_answers={
                    question_id: GoldAnswerInfo(
                        question_id=question_id,
                        answer=f"answer {index}",
                    )
                    for index, question_id in enumerate(question_ids, start=1)
                },
            )
        ],
    )


@pytest.mark.parametrize(
    ("module", "adapter_name", "prepare", "variant"),
    [
        (locomo, "LoCoMoAdapter", locomo.prepare_locomo_run, "locomo10"),
        (
            benchmark_registry,
            "LongMemEvalAdapter",
            benchmark_registry._prepare_longmemeval_run,
            "m_cleaned",
        ),
        (beam, "BeamAdapter", beam.prepare_beam_run, "100k"),
        (halumem, "HaluMemAdapter", halumem.prepare_halumem_run, "medium"),
    ],
)
def test_pilot_loads_one_complete_isolation_without_history_or_question_crop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    module,
    adapter_name: str,
    prepare,
    variant: str,
) -> None:
    """四家单源 benchmark 的 pilot 应调用 load(limit=1) 并保留全部内容。"""

    load_limits: list[int | None] = []
    source = _dataset("conv-1")

    class FakeAdapter:
        """记录 prepare 传入的加载上限。"""

        def __init__(self, *_args, **_kwargs) -> None:
            """忽略路径与 variant。"""

        def load(self, limit: int | None = None) -> Dataset:
            """返回完整 fake isolation。"""

            load_limits.append(limit)
            return source

    monkeypatch.setattr(module, adapter_name, FakeAdapter)

    prepared = prepare(
        tmp_path,
        BenchmarkLoadRequest(
            variant=variant,
            run_scope=RunScope.PILOT,
            smoke_conversation_limit=1,
        ),
    )

    assert load_limits == [1]
    assert prepared.run_scope is RunScope.PILOT
    assert prepared.dataset.metadata["run_scope"] == "pilot"
    conversation = prepared.dataset.conversations[0]
    assert len(conversation.sessions[0].turns) == 5
    assert len(conversation.questions) == 2


def test_membench_pilot_selects_one_complete_tid_from_each_declared_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """MemBench pilot 应一次装配四 lane，各一条完整 trajectory。"""

    loaded_paths: list[Path] = []

    class FakeMemBenchAdapter:
        """按单个 source path 返回一条唯一 conversation。"""

        name = "membench"

        def __init__(
            self,
            _project_root: Path,
            *,
            variant: str,
            source_relative_paths: tuple[Path, ...],
        ) -> None:
            """保存当前单 source 身份。"""

            assert variant == "0_10k"
            assert len(source_relative_paths) == 1
            self.source_path = source_relative_paths[0]

        def load(self, limit: int | None = None) -> Dataset:
            """返回当前 source 的首个完整 tid。"""

            assert limit == 1
            loaded_paths.append(self.source_path)
            return _dataset(self.source_path.stem)

    monkeypatch.setattr(membench, "MemBenchAdapter", FakeMemBenchAdapter)
    monkeypatch.setattr(
        membench,
        "_combined_source_sha256",
        lambda _root, _paths: "0" * 64,
    )

    prepared = membench.prepare_membench_run(
        tmp_path,
        BenchmarkLoadRequest(
            variant="0_10k",
            run_scope=RunScope.PILOT,
            smoke_conversation_limit=1,
        ),
    )

    assert tuple(loaded_paths) == membench.MEMBENCH_0_10K_SOURCE_PATHS
    assert len(prepared.dataset.conversations) == 4
    assert all(
        len(conversation.sessions[0].turns) == 5
        for conversation in prepared.dataset.conversations
    )
    assert prepared.dataset.metadata["pilot_source_counts"] == {
        path.as_posix(): 1 for path in membench.MEMBENCH_0_10K_SOURCE_PATHS
    }
