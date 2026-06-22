# Claude Code Codex Subagent 通道

本文记录本机 Claude Code 的最小可用入口，避免每次重新查询。Claude Code 的定位不是
OpenCode 那种在 Codex 额度空档期独立推进项目的外部 agent，而是 Codex 当前工作流里
可以主动调用的 subagent / 副手，用于协助只读审查、局部实现、验证和资料整理。

Claude Code 的输出不能自动进入主线结论；Codex 需要复核其结果、检查 diff、运行测试，
再决定是否采纳。

用户已授权 Codex 自由使用 Claude Code，并尽量发挥其能力。实际使用策略不是预设
“只能做简单任务”，而是根据 Claude Code 在本项目中的真实表现动态调整：

- 如果 Claude Code 在只读审查、局部实现或测试修复中表现稳定，可以逐步分配更复杂任务。
- 如果 Claude Code 出现遗漏上下文、误改架构、测试不充分等问题，应降低任务难度或只让它
  做分析/草案。
- 关键路径任务仍由 Codex 最终裁定和验收。

## 已确认命令

本机 CLI 路径：

```bash
/opt/homebrew/bin/claude
```

只读确认命令：

```bash
which claude
claude --help
```

2026-06-20 最小连通性复验通过：

```bash
claude -p "Reply with exactly: ok"
# ok
```

## 非交互任务

使用 `-p/--print` 可以发送一次性任务并把结果打印到 stdout：

```bash
claude -p "请只读审查 docs/task-ledger.md，总结仍然 open 的 P0 项。"
```

建议 Codex 调用 Claude Code 时把任务写清楚：

- 只读还是允许改文件。
- 允许读取哪些目录。
- 产出写到哪个文件，例如 `opencode/claude_result.md` 或 `docs/handoffs/...`。
- 不允许启动真实 API 实验，除非用户和 Codex 已明确确认。

## 会话恢复

继续当前目录最近会话：

```bash
claude --continue
```

按 session id 恢复：

```bash
claude --resume <session-id>
```

恢复时 fork 新会话：

```bash
claude --resume <session-id> --fork-session
```

## 权限和安全建议

- 默认不要使用 `--dangerously-skip-permissions`。
- 默认不要让 Claude Code 直接跑全量真实 API 实验。
- 对复杂任务，优先让 Claude Code 输出分析或补丁计划，再由 Codex 审查执行。
- 如果 Claude Code 修改代码，Codex 必须检查 git diff、运行相关测试，并把结论写入
  `docs/task-ledger.md` 或 handoff。

## 推荐交接格式

让 Claude Code 输出到固定文件，便于 Codex 恢复时读取：

```text
任务：
执行范围：
修改文件：
验证命令和结果：
未解决问题：
建议下一步：
```
