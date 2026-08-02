"""测试新 method 接入 ledger 的机器完整性门。"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from scripts.validate_method_integration_ledgers import (
    EXPECTED_CHECKPOINT_IDS,
    LedgerCheckpoint,
    LedgerValidationError,
    ParsedLedger,
    _validate_structured_record,
    parse_ledger,
    validate_instance,
    validate_repository,
    validate_template,
)


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "reference" / "templates" / "method-integration-ledger.md"
LETTA_LEDGER = (
    ROOT
    / "docs"
    / "workstreams"
    / "ws02.7-method-track"
    / "branches"
    / "method-recertification"
    / "letta"
    / "notes"
    / "letta-integration-ledger.md"
)


pytestmark = pytest.mark.unit


def test_repository_method_ledgers_pass_machine_gate() -> None:
    """当前仓库所有受 ledger v1 约束的新 method 都必须通过完整门。"""

    ledgers = validate_repository(ROOT)

    assert [ledger.metadata["method_id"] for ledger in ledgers] == ["letta"]


def test_template_has_exact_protected_checkpoint_order() -> None:
    """模板不得漏删、改名或重排 33 个受保护检查点。"""

    template = parse_ledger(TEMPLATE)

    validate_template(template)
    assert tuple(checkpoint.checkpoint_id for checkpoint in template.checkpoints) == (
        EXPECTED_CHECKPOINT_IDS
    )


def test_new_method_directory_without_ledger_fails(tmp_path: Path) -> None:
    """新增 method 支线但没实例化 ledger 时，仓库门必须 fail-fast。"""

    template_path = tmp_path / "docs" / "reference" / "templates" / TEMPLATE.name
    template_path.parent.mkdir(parents=True)
    template_path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "configs" / "methods").mkdir(parents=True)
    method_root = (
        tmp_path
        / "docs"
        / "workstreams"
        / "ws02.7-method-track"
        / "branches"
        / "method-recertification"
        / "newmethod"
    )
    method_root.mkdir(parents=True)

    with pytest.raises(LedgerValidationError, match="missing integration ledgers"):
        validate_repository(tmp_path)


def test_instance_missing_one_checkpoint_fails(tmp_path: Path) -> None:
    """实例少一格时即使其余记录有效也不得通过。"""

    template = parse_ledger(TEMPLATE)
    source = parse_ledger(LETTA_LEDGER)
    ledger_path = tmp_path / "letta" / "notes" / LETTA_LEDGER.name
    ledger_path.parent.mkdir(parents=True)
    (ledger_path.parent.parent / "README.md").write_text(
        f"[{ledger_path.name}]({ledger_path.name})", encoding="utf-8"
    )
    truncated = ParsedLedger(
        path=ledger_path,
        metadata=source.metadata,
        checkpoints=source.checkpoints[:-1],
    )

    with pytest.raises(LedgerValidationError, match="differ from the v1 template"):
        validate_instance(ROOT, template, truncated)


def test_pass_checkpoint_requires_clickable_evidence() -> None:
    """把状态改成 PASS 却不给证据链接时必须拒绝假完成。"""

    checkpoint = LedgerCheckpoint(
        checkpoint_id="B1-SOURCE-LOCK",
        requirement="来源已锁",
        status="PASS",
        record="evidence=我看过源码; ruling=来源可信; next=none",
    )

    with pytest.raises(LedgerValidationError, match="requires a Markdown evidence link"):
        _validate_structured_record(checkpoint, LETTA_LEDGER)


def test_ready_for_smoke_rejects_early_pending_gate(tmp_path: Path) -> None:
    """B0-B10 尚有 PENDING 时不能用 ready_for_smoke 越过前置门。"""

    template = parse_ledger(TEMPLATE)
    source = parse_ledger(LETTA_LEDGER)
    ledger_path = tmp_path / "letta" / "notes" / LETTA_LEDGER.name
    ledger_path.parent.mkdir(parents=True)
    (ledger_path.parent.parent / "README.md").write_text(
        f"[{ledger_path.name}]({ledger_path.name})", encoding="utf-8"
    )
    metadata = dict(source.metadata)
    metadata["ledger_state"] = "ready_for_smoke"
    checkpoints = tuple(
        replace(
            checkpoint,
            status="PENDING",
            record=(
                "evidence=[待闭合](pending.md); ruling=TOML identity 尚未完成; "
                "next=补齐 TOML 与 manifest"
            ),
        )
        if checkpoint.checkpoint_id == "B10-TOML-MANIFEST"
        else checkpoint
        for checkpoint in source.checkpoints
    )
    premature = replace(
        source,
        path=ledger_path,
        metadata=metadata,
        checkpoints=checkpoints,
    )

    with pytest.raises(LedgerValidationError, match="pre-smoke PENDING"):
        validate_instance(ROOT, template, premature)
