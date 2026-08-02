#!/usr/bin/env python3
"""校验新 method 接入 ledger 的结构、状态迁移与可检索性。

该脚本只验证“必填格是否存在、状态是否自洽、证据入口是否可定位”，不替代
架构师对一手证据真实性和方法学合理性的复核。
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence


LEDGER_CONTRACT_VERSION = "method-integration-ledger-v1"
TEMPLATE_RELATIVE_PATH = Path("docs/reference/templates/method-integration-ledger.md")
RECERTIFICATION_RELATIVE_PATH = Path(
    "docs/workstreams/ws02.7-method-track/branches/method-recertification"
)
METHOD_CONFIG_RELATIVE_PATH = Path("configs/methods")

# 这六家在 ledger v1 生效前已经冻结；不为整理历史而强制补写 33 格。
# 新目录或新 TOML 不在此名单时，会自动进入 ledger 强制门。
GRANDFATHERED_METHOD_IDS = frozenset(
    {"amem", "lightmem", "mem0", "memoryos", "memos", "simplemem"}
)

EXPECTED_CHECKPOINT_IDS = (
    "B0-OFFICIAL-BENCHMARKS",
    "B0-FINAL-PAYLOAD",
    "B0-DIFFERENCE-RULING",
    "B1-SOURCE-LOCK",
    "B1-PRODUCT-SURFACE",
    "B1-LIFECYCLE-CALLGRAPH",
    "B2-GRANULARITY",
    "B3-ISOLATION-CLEAN",
    "B3-PARALLEL-OWNERSHIP",
    "B4-INPUT-VISIBILITY",
    "B4-READOUT-COMPLETENESS",
    "B5-PROVENANCE",
    "B5-RANKING-TOPK",
    "B5-LOSSLESS-RETROFIT",
    "B6-FLUSH-COMPLETION",
    "B7-OBSERVABILITY",
    "B8-RETRIEVAL-SIDE-EFFECTS",
    "B8-RESILIENCE-RESUME",
    "B9-MODEL-IDENTITY",
    "B10-TOML-MANIFEST",
    "B10-ANSWER-JUDGE-BUILDER",
    "GRID-LOCOMO",
    "GRID-LONGMEMEVAL",
    "GRID-MEMBENCH",
    "GRID-BEAM",
    "GRID-HALUMEM",
    "B11-DOSSIER",
    "B11-SMOKE-PLAN",
    "B11-REAL-SMOKE",
    "B11-ARTIFACT-GATE",
    "B11-PARALLEL-GATE",
    "B11-REGRESSION-GATE",
    "B11-FREEZE-SYNC",
)

ALLOWED_CHECKPOINT_STATUSES = frozenset({"PASS", "N/A", "PENDING", "BLOCKED"})
ALLOWED_LEDGER_STATES = frozenset({"in_progress", "ready_for_smoke", "blocked", "frozen"})
POST_SMOKE_CHECKPOINT_IDS = frozenset(
    {
        "B11-REAL-SMOKE",
        "B11-ARTIFACT-GATE",
        "B11-PARALLEL-GATE",
        "B11-REGRESSION-GATE",
        "B11-FREEZE-SYNC",
    }
)
REQUIRED_METADATA_KEYS = frozenset(
    {
        "contract_version",
        "method_id",
        "display_name",
        "ledger_state",
        "integration_page",
        "dossier",
        "frozen_note",
    }
)
INSTANCE_PLACEHOLDERS = ("<method", "<display", "<填写", "TBD", "TODO", "UNSET", "???")
METADATA_PATTERN = re.compile(
    r"<!--\s*method-integration-ledger\s*\n(?P<body>.*?)\n-->", re.DOTALL
)
CHECKPOINT_BLOCK_PATTERN = re.compile(
    r"<!--\s*ledger-checkpoints:start\s*-->(?P<body>.*?)"
    r"<!--\s*ledger-checkpoints:end\s*-->",
    re.DOTALL,
)
STRUCTURED_EVIDENCE_PATTERN = re.compile(
    r"^evidence=(?P<evidence>.+?);\s*ruling=(?P<ruling>.+?);\s*next=(?P<next>.+)$"
)
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\([^)]+\)")


class LedgerValidationError(ValueError):
    """表示 ledger 内容不满足机器可验证契约。"""


@dataclass(frozen=True)
class LedgerCheckpoint:
    """表示 ledger 中一个带状态的必填检查点。"""

    checkpoint_id: str
    requirement: str
    status: str
    record: str


@dataclass(frozen=True)
class ParsedLedger:
    """表示从 Markdown ledger 解析出的结构化内容。"""

    path: Path
    metadata: Mapping[str, str]
    checkpoints: tuple[LedgerCheckpoint, ...]


def _parse_metadata(path: Path, content: str) -> dict[str, str]:
    """解析 ledger 顶部的单值元数据块。"""

    match = METADATA_PATTERN.search(content)
    if match is None:
        raise LedgerValidationError(f"{path}: missing method-integration-ledger metadata block")
    metadata: dict[str, str] = {}
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip():
            raise LedgerValidationError(f"{path}: malformed metadata line {raw_line!r}")
        normalized_key = key.strip()
        if normalized_key in metadata:
            raise LedgerValidationError(f"{path}: duplicate metadata key {normalized_key!r}")
        metadata[normalized_key] = value.strip()
    return metadata


def _is_markdown_separator(cell: str) -> bool:
    """判断 Markdown 表格单元格是否只是表头分隔线。"""

    compact = cell.replace(":", "").replace("-", "").strip()
    return not compact


def _parse_checkpoints(path: Path, content: str) -> tuple[LedgerCheckpoint, ...]:
    """解析标记区间内的四列表格并拒绝重复检查点。"""

    match = CHECKPOINT_BLOCK_PATTERN.search(content)
    if match is None:
        raise LedgerValidationError(f"{path}: missing ledger-checkpoints marker block")
    checkpoints: list[LedgerCheckpoint] = []
    seen: set[str] = set()
    for raw_line in match.group("body").splitlines():
        line = raw_line.strip()
        if not line or not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if cells[0] == "ID" or _is_markdown_separator(cells[0]):
            continue
        if len(cells) != 4:
            raise LedgerValidationError(
                f"{path}: checkpoint row must have exactly 4 cells, got {len(cells)}: {raw_line!r}"
            )
        checkpoint_id, requirement, status, record = cells
        if checkpoint_id in seen:
            raise LedgerValidationError(f"{path}: duplicate checkpoint {checkpoint_id!r}")
        seen.add(checkpoint_id)
        checkpoints.append(
            LedgerCheckpoint(
                checkpoint_id=checkpoint_id,
                requirement=requirement,
                status=status,
                record=record,
            )
        )
    if not checkpoints:
        raise LedgerValidationError(f"{path}: checkpoint table is empty")
    return tuple(checkpoints)


def parse_ledger(path: Path) -> ParsedLedger:
    """从磁盘读取并解析一份 method integration ledger。"""

    content = path.read_text(encoding="utf-8")
    return ParsedLedger(
        path=path,
        metadata=_parse_metadata(path, content),
        checkpoints=_parse_checkpoints(path, content),
    )


def validate_template(template: ParsedLedger) -> None:
    """验证模板本身没有漏掉或重排受保护检查点。"""

    if template.metadata.get("contract_version") != LEDGER_CONTRACT_VERSION:
        raise LedgerValidationError(
            f"{template.path}: contract_version must be {LEDGER_CONTRACT_VERSION!r}"
        )
    actual_ids = tuple(checkpoint.checkpoint_id for checkpoint in template.checkpoints)
    if actual_ids != EXPECTED_CHECKPOINT_IDS:
        raise LedgerValidationError(
            f"{template.path}: checkpoint IDs drifted; expected {EXPECTED_CHECKPOINT_IDS!r}, "
            f"got {actual_ids!r}"
        )
    for checkpoint in template.checkpoints:
        if not checkpoint.requirement:
            raise LedgerValidationError(
                f"{template.path}: {checkpoint.checkpoint_id} has an empty requirement"
            )
        if checkpoint.status != "PENDING":
            raise LedgerValidationError(
                f"{template.path}: template checkpoint {checkpoint.checkpoint_id} must start PENDING"
            )


def _resolve_declared_path(root: Path, owner: Path, raw_value: str, field: str) -> Path:
    """把 ledger 声明路径解析为仓库内既存文件并阻止越界。"""

    candidate = Path(raw_value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise LedgerValidationError(f"{owner}: {field} must be a repository-relative path")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise LedgerValidationError(f"{owner}: {field} escapes repository root")
    if not resolved.is_file():
        raise LedgerValidationError(f"{owner}: {field} does not exist: {raw_value}")
    return resolved


def _validate_structured_record(checkpoint: LedgerCheckpoint, path: Path) -> None:
    """验证一个检查点的证据、裁决与下一步三段式记录。"""

    if checkpoint.status not in ALLOWED_CHECKPOINT_STATUSES:
        raise LedgerValidationError(
            f"{path}: {checkpoint.checkpoint_id} has illegal status {checkpoint.status!r}"
        )
    if any(token.casefold() in checkpoint.record.casefold() for token in INSTANCE_PLACEHOLDERS):
        raise LedgerValidationError(
            f"{path}: {checkpoint.checkpoint_id} still contains a template placeholder"
        )
    match = STRUCTURED_EVIDENCE_PATTERN.fullmatch(checkpoint.record)
    if match is None:
        raise LedgerValidationError(
            f"{path}: {checkpoint.checkpoint_id} must use "
            "'evidence=...; ruling=...; next=...'"
        )
    evidence = match.group("evidence").strip()
    ruling = match.group("ruling").strip()
    next_action = match.group("next").strip()
    if not evidence or not ruling or not next_action:
        raise LedgerValidationError(
            f"{path}: {checkpoint.checkpoint_id} has an empty structured record field"
        )
    if checkpoint.status in {"PASS", "N/A"}:
        if MARKDOWN_LINK_PATTERN.search(evidence) is None:
            raise LedgerValidationError(
                f"{path}: {checkpoint.checkpoint_id} {checkpoint.status} requires a Markdown evidence link"
            )
        if next_action.casefold() != "none":
            raise LedgerValidationError(
                f"{path}: {checkpoint.checkpoint_id} {checkpoint.status} must declare next=none"
            )
    elif next_action.casefold() in {"none", "n/a"}:
        raise LedgerValidationError(
            f"{path}: {checkpoint.checkpoint_id} {checkpoint.status} requires a concrete next action"
        )
    if checkpoint.checkpoint_id.startswith("GRID-"):
        for key in ("stable=", "payload=", "metric=", "privacy=", "smoke="):
            if key not in evidence:
                raise LedgerValidationError(
                    f"{path}: {checkpoint.checkpoint_id} evidence is missing {key!r}"
                )
    if checkpoint.checkpoint_id == "GRID-HALUMEM" and "operations=" not in evidence:
        raise LedgerValidationError(
            f"{path}: GRID-HALUMEM evidence must cover extraction/update/QA/memory-type via operations="
        )


def validate_instance(root: Path, template: ParsedLedger, ledger: ParsedLedger) -> None:
    """验证一份具体 method ledger 的完整性与状态转换。"""

    metadata_keys = frozenset(ledger.metadata)
    if metadata_keys != REQUIRED_METADATA_KEYS:
        missing = sorted(REQUIRED_METADATA_KEYS - metadata_keys)
        extra = sorted(metadata_keys - REQUIRED_METADATA_KEYS)
        raise LedgerValidationError(f"{ledger.path}: metadata mismatch; missing={missing}, extra={extra}")
    if ledger.metadata["contract_version"] != LEDGER_CONTRACT_VERSION:
        raise LedgerValidationError(
            f"{ledger.path}: unsupported contract_version {ledger.metadata['contract_version']!r}"
        )
    method_id = ledger.metadata["method_id"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", method_id):
        raise LedgerValidationError(f"{ledger.path}: invalid method_id {method_id!r}")
    expected_method_id = ledger.path.parent.parent.name
    if method_id != expected_method_id:
        raise LedgerValidationError(
            f"{ledger.path}: method_id {method_id!r} does not match branch directory "
            f"{expected_method_id!r}"
        )
    ledger_state = ledger.metadata["ledger_state"]
    if ledger_state not in ALLOWED_LEDGER_STATES:
        raise LedgerValidationError(f"{ledger.path}: illegal ledger_state {ledger_state!r}")

    actual_signature = tuple(
        (checkpoint.checkpoint_id, checkpoint.requirement) for checkpoint in ledger.checkpoints
    )
    expected_signature = tuple(
        (checkpoint.checkpoint_id, checkpoint.requirement) for checkpoint in template.checkpoints
    )
    if actual_signature != expected_signature:
        raise LedgerValidationError(
            f"{ledger.path}: checkpoint IDs or requirements differ from the v1 template"
        )
    for checkpoint in ledger.checkpoints:
        _validate_structured_record(checkpoint, ledger.path)

    statuses = {checkpoint.checkpoint_id: checkpoint.status for checkpoint in ledger.checkpoints}
    blocked = {checkpoint_id for checkpoint_id, status in statuses.items() if status == "BLOCKED"}
    pending = {checkpoint_id for checkpoint_id, status in statuses.items() if status == "PENDING"}
    if blocked and ledger_state != "blocked":
        raise LedgerValidationError(f"{ledger.path}: BLOCKED checkpoint requires ledger_state=blocked")
    if ledger_state == "blocked" and not blocked:
        raise LedgerValidationError(f"{ledger.path}: ledger_state=blocked requires a BLOCKED checkpoint")
    if ledger_state == "in_progress" and not pending:
        raise LedgerValidationError(f"{ledger.path}: in_progress ledger must retain at least one PENDING gate")
    if ledger_state == "ready_for_smoke":
        illegal_pending = pending - POST_SMOKE_CHECKPOINT_IDS
        if illegal_pending:
            raise LedgerValidationError(
                f"{ledger.path}: ready_for_smoke has pre-smoke PENDING gates {sorted(illegal_pending)}"
            )
    if ledger_state == "frozen" and (pending or blocked):
        raise LedgerValidationError(
            f"{ledger.path}: frozen ledger cannot contain PENDING/BLOCKED checkpoints"
        )

    integration_page = _resolve_declared_path(
        root, ledger.path, ledger.metadata["integration_page"], "integration_page"
    )
    branch_readme = ledger.path.parent.parent / "README.md"
    if not branch_readme.is_file():
        raise LedgerValidationError(f"{ledger.path}: method branch README.md is missing")
    for index_path in (integration_page, branch_readme):
        if ledger.path.name not in index_path.read_text(encoding="utf-8"):
            raise LedgerValidationError(
                f"{ledger.path}: {index_path} must link the ledger by filename"
            )

    if ledger_state in {"ready_for_smoke", "frozen"}:
        if ledger.metadata["dossier"] == "none":
            raise LedgerValidationError(f"{ledger.path}: {ledger_state} ledger requires a dossier")
        _resolve_declared_path(root, ledger.path, ledger.metadata["dossier"], "dossier")
    if ledger_state == "frozen":
        if ledger.metadata["frozen_note"] == "none":
            raise LedgerValidationError(f"{ledger.path}: frozen ledger requires a frozen_note")
        frozen_note = _resolve_declared_path(
            root, ledger.path, ledger.metadata["frozen_note"], "frozen_note"
        )
        if ledger.path.name not in frozen_note.read_text(encoding="utf-8"):
            raise LedgerValidationError(
                f"{ledger.path}: frozen_note must link back to the completed ledger"
            )


def required_method_ids(root: Path) -> set[str]:
    """返回 ledger v1 生效后必须存在实例的 method id 集合。"""

    recertification_root = root / RECERTIFICATION_RELATIVE_PATH
    branch_ids = {
        path.name
        for path in recertification_root.iterdir()
        if path.is_dir() and path.name not in GRANDFATHERED_METHOD_IDS
    }
    config_root = root / METHOD_CONFIG_RELATIVE_PATH
    config_ids = {
        path.stem
        for path in config_root.glob("*.toml")
        if path.stem not in GRANDFATHERED_METHOD_IDS
    }
    return branch_ids | config_ids


def validate_repository(root: Path) -> tuple[ParsedLedger, ...]:
    """验证仓库模板及所有受 ledger v1 约束的新 method。"""

    normalized_root = root.resolve()
    template = parse_ledger(normalized_root / TEMPLATE_RELATIVE_PATH)
    validate_template(template)

    recertification_root = normalized_root / RECERTIFICATION_RELATIVE_PATH
    discovered_paths = sorted(recertification_root.glob("*/notes/*-integration-ledger.md"))
    ledgers: dict[str, ParsedLedger] = {}
    for path in discovered_paths:
        ledger = parse_ledger(path)
        validate_instance(normalized_root, template, ledger)
        method_id = ledger.metadata["method_id"]
        if method_id in ledgers:
            raise LedgerValidationError(f"duplicate integration ledger for method {method_id!r}")
        ledgers[method_id] = ledger

    required = required_method_ids(normalized_root)
    missing = sorted(required - set(ledgers))
    if missing:
        raise LedgerValidationError(f"new methods missing integration ledgers: {missing}")
    return tuple(ledgers[method_id] for method_id in sorted(ledgers))


def build_parser() -> argparse.ArgumentParser:
    """构造 ledger 校验脚本的命令行参数。"""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="仓库根目录")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """执行仓库级 ledger 校验并打印稳定摘要。"""

    args = build_parser().parse_args(argv)
    try:
        ledgers = validate_repository(args.root)
    except (OSError, LedgerValidationError) as exc:
        print(f"FAIL method integration ledger: {exc}")
        return 1
    methods = ", ".join(ledger.metadata["method_id"] for ledger in ledgers) or "none"
    print(
        f"PASS method integration ledger: contract={LEDGER_CONTRACT_VERSION}, "
        f"methods={methods}, count={len(ledgers)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
