#!/usr/bin/env python3
"""为本项目的 Codex 生命周期注入压缩恢复门与 commit 纪律提醒。"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
ACTIVE_WORKSTREAM_ROW = re.compile(
    r"\|\s*\[[^]]+\]\((workstreams/[^)]+/README\.md)\)\s*\|"
    r"[^|]*\|\s*in-progress\s*\|\s*P0\s*\|"
)
GIT_COMMIT_COMMAND = re.compile(r"\bgit\b[^\n;&|]*\bcommit\b")
RECOVERY_HEADING = "## Codex 恢复胶囊"
IDLE_CAPSULE_HEADING = "## Codex 空闲恢复胶囊"
IDLE_CAPSULE_TARGET = "docs/roadmap.md"
MAX_STATUS_LINES = 20
MAX_EVENT_TEXT = 512
MAX_CAPSULE_CHARS = 6_000


def _active_capsule_target() -> str:
    """从 roadmap 解析唯一 P0 活跃行；合法空闲态回到 roadmap。"""

    roadmap = REPO_ROOT / "docs" / "roadmap.md"
    try:
        matches = ACTIVE_WORKSTREAM_ROW.findall(roadmap.read_text(encoding="utf-8"))
    except OSError:
        matches = []
    if len(matches) == 1:
        return f"docs/{matches[0]}"
    if not matches:
        return IDLE_CAPSULE_TARGET
    return (
        "当前 workstream README（先只用 rg 定位 docs/roadmap.md 的 in-progress P0 行；"
        "若当前阶段已关闭，则在 docs/workstreams/ 下只选用户本轮明确指向的一份 README）"
    )


def _event_text(event: dict[str, Any], key: str) -> str:
    """把 hook 事件文本压成单行有界值，避免畸形字段污染恢复 context。"""

    value = event.get(key)
    if not isinstance(value, str) or not value.strip():
        return "unavailable"
    return " ".join(value.split())[:MAX_EVENT_TEXT]


def _run_git(*args: str) -> tuple[str, ...] | None:
    """执行一个只读 Git 查询并返回有界行；失败时交给四步兜底。"""

    try:
        completed = subprocess.run(
            ["git", "-C", str(REPO_ROOT), *args],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return tuple(line for line in completed.stdout.splitlines() if line.strip())


def _git_snapshot() -> str | None:
    """生成 hook 时刻的 Git status/log 快照，避免压缩后重复读取。"""

    status = _run_git("status", "--short")
    log = _run_git("log", "-5", "--oneline")
    if status is None or log is None:
        return None
    if status:
        visible_status = status[:MAX_STATUS_LINES]
        status_text = "\n".join(visible_status)
        if len(status) > MAX_STATUS_LINES:
            status_text += f"\n... {len(status) - MAX_STATUS_LINES} more status lines"
    else:
        status_text = "<clean>"
    log_text = "\n".join(log) if log else "<no commits>"
    return f"git status --short:\n{status_text}\ngit log -5 --oneline:\n{log_text}"


def _read_capsule(capsule_target: str) -> str | None:
    """读取活跃 README 胶囊；无活跃线时生成有界空闲胶囊。"""

    if not capsule_target.startswith("docs/"):
        return None
    path = REPO_ROOT / capsule_target
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if capsule_target == IDLE_CAPSULE_TARGET:
        return f"""{IDLE_CAPSULE_HEADING}

- `docs/roadmap.md` 当前没有 `in-progress` P0 workstream；这是合法暂停态，不是恢复失败。
- 先使用 hook 注入的 Git 快照判断是否有未提交收尾；没有用户新指令时不得自行重开已关闭 workstream。
- 用户恢复工作后，按 roadmap 与本轮目标选择或新建唯一活跃 workstream，再读取对应恢复胶囊。
""".strip()
    start = text.find(RECOVERY_HEADING)
    if start < 0:
        return None
    tail = text[start:]
    next_heading = re.search(r"^##\s+", tail[len(RECOVERY_HEADING) :], re.MULTILINE)
    if next_heading is None:
        capsule = tail
    else:
        end = len(RECOVERY_HEADING) + next_heading.start()
        capsule = tail[:end]
    capsule = capsule.strip()
    if not capsule:
        return None
    return capsule[:MAX_CAPSULE_CHARS]


def _fallback_recovery_context(capsule_target: str) -> str:
    """当 hook 无法生成热快照时返回原四步恢复门。"""

    return f"""[Codex 压缩恢复兜底]
热快照生成失败。在任何项目判断、编辑或大范围读文档前，只执行：
1. git status --short
2. git log -5 --oneline
3. 读取 {capsule_target} 顶部“Codex 恢复胶囊”
4. 只定点读取当前动作对应的一份判据或 note
禁止为恢复全局而通读全部 workstream/手册/历史；不得把压缩摘要冒充完整记忆。
"""


def _recovery_context(event: dict[str, Any]) -> str:
    """生成含 Git、热胶囊和会话定位器的有界压缩恢复 context。"""

    capsule_target = _active_capsule_target()
    snapshot = _git_snapshot()
    capsule = _read_capsule(capsule_target)
    if snapshot is None or capsule is None:
        return _fallback_recovery_context(capsule_target)
    session_id = _event_text(event, "session_id")
    transcript_path = _event_text(event, "transcript_path")
    return f"""[Codex 压缩热恢复]
session_id: {session_id}
transcript_path: {transcript_path}

[hook 时刻 Git 快照]
{snapshot}

[恢复胶囊: {capsule_target}]
{capsule}

恢复规则：
- 上述快照与胶囊已完成原四步门的 1-3；若二者一致，直接续接，只有承重细节缺失时才读胶囊链接的一份当前 note。
- status 非空时先判明 tracked/untracked 资产归属；若 Git、胶囊、用户本轮目标冲突，以 Git + 最新裁决 note 为准并停下消歧。
- transcript 只在逐字旧对话实质影响裁决时定点回查；它证明“当时说过什么”，不是当前项目真理，禁止全文注入或替代代码/数据/裁决。
- 恢复在后台完成。除非用户明确询问，或缺失上下文影响本轮可靠性，不自动播报 compaction。
- 默认派发权仍在用户；未经明确授权不自动启动 Codex subagent。
"""

COMMIT_REMINDER = (
    "[commit 纪律 hook] 提交前完成 playbook 三问；git add 只用显式路径，禁 -A/.；"
    "先查看 git status --short 与 cached diff，确认未暂存用户资产。"
)


def _read_event() -> dict[str, Any]:
    """从标准输入读取 Codex hook 事件；畸形输入安全地视为空事件。"""

    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _emit(payload: dict[str, Any]) -> None:
    """以 UTF-8 JSON 输出 Codex hook 响应。"""

    sys.stdout.write(json.dumps(payload, ensure_ascii=False))


def main() -> None:
    """按事件类型输出压缩恢复 context 或 commit 提醒；其余事件静默放行。"""

    event = _read_event()
    event_name = event.get("hook_event_name")
    if event_name == "SessionStart" and event.get("source") == "compact":
        _emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": _recovery_context(event),
                }
            }
        )
        return

    if event_name != "PreToolUse":
        return
    tool_input = event.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(command, str) and GIT_COMMIT_COMMAND.search(command):
        _emit({"systemMessage": COMMIT_REMINDER})


if __name__ == "__main__":
    main()
