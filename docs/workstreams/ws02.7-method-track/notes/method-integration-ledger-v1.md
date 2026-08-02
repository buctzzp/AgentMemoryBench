# 新 method 强制接入 Ledger v1

日期：2026-08-02

## 1. 问题与裁决

旧结构已有三类材料：B0–B11 政策原文、`integration-status.md` 勾选总表、各 method
稳定事实页。它们分别回答“什么算完成”“现在大概到哪”“已经验收了什么”，但没有强制
每次施工把 33 个承重点逐格实例化。因此判据可能完整，实际推进仍会靠架构师记忆，在 CLI
撞错后才想起 HaluMem fixed shape、官方 harness、worker 所有权或 metric 资格。

本批裁决：新增 `method-integration-ledger-v1` 作为**执行账**，不重写 B0–B11。每家新 method
在 M-1 取证前复制模板，五格分别记录状态、证据、裁决与下一动作；同一份 ledger 穿过
M1、M2、smoke 和 frozen，不再给每阶段造一份互相漂移的 checklist。

## 2. 四层职责

| 层 | 回答的问题 | 是否机器校验 |
| --- | --- | --- |
| B0–B11 checklist | 什么才算完成 | 结构入口受保护，方法学由架构师判断 |
| method ledger | 这家 method 每一格做没做、证据在哪、下一步是什么 | 是 |
| integration-status | 十家横向看谁到哪 | 否，作为人读总表 |
| integration stable page | 已验收的接口与能力事实是什么 | ledger 强制链接，内容由架构师验收 |

机器只验证完整性与状态机，**不宣称能判断源码是否读对**。把自动化扩大到“判断 provenance
是否语义有效”会制造更危险的假安全感。

## 3. 契约

- 33 个 checkpoint ID 与顺序受保护；包括 B0–B11 的细分门和五个独立 `GRID-*`。
- 每格状态只能是 `PASS/N/A/PENDING/BLOCKED`。
- 每格记录固定为 `evidence=...; ruling=...; next=...`。
- `PASS/N/A` 必须给 Markdown 证据链接且 `next=none`；`PENDING/BLOCKED` 必须有具体 next。
- `GRID-*` 必须同时覆盖 stable fact、最终 payload、metric、privacy、smoke；HaluMem 还须覆盖
  extraction/update/QA/memory-type 四类 operation。
- 状态机为 `in_progress → ready_for_smoke → frozen`；任何 BLOCKED 会强制顶层 `blocked`。
- `ready_for_smoke` 前只能剩真实 smoke 之后的五个门；`frozen` 不得剩 pending/blocker，且
  dossier 与 frozen note 必须存在、可定位并回链。
- 新 method 支线目录或新 TOML 任一出现就必须有 ledger。v1 前已冻结的 LightMem、Mem0、
  MemoryOS、A-Mem、SimpleMem、MemOS 被明确 grandfather，不为整理历史重造证据。

## 4. 首个实例

[Letta/MemGPT ledger](../branches/method-recertification/letta/notes/letta-integration-ledger.md)
在 source audit 与 adapter 之前创建。当前 33 格均为诚实 `PENDING`，每格已写具体下一动作；
没有把旧 MemGPT 印象或 README 宣传提前标成 current Letta 事实。

## 5. 交付与验证

主要交付：

- `docs/reference/templates/method-integration-ledger.md`
- `scripts/validate_method_integration_ledgers.py`
- `tests/test_method_integration_ledgers.py`
- Letta 支线 README、ledger 与稳定事实入口页
- checklist、assembly line、architect playbook、文档地图、总表和热恢复胶囊接线

本批定向门：

```text
PASS method integration ledger: contract=method-integration-ledger-v1, methods=letta, count=1
11 passed in 1.09s
git diff --check: clean
```

最终门：

```text
1923 passed, 3 deselected, 13 warnings, 29 subtests passed in 144.84s
compileall: exit 0
git diff --check: clean
```

13 个 warning 与上一基线画像一致：vendored LightMem Pydantic deprecation、MemOS
`datetime.utcnow()` deprecation 与 MemOS config serialization warning；本批没有新增 warning。
