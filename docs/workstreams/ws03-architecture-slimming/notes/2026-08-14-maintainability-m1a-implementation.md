# Maintainability M1-A：依赖方向、freshness 与恢复自举

日期：2026-08-14

状态：架构师验收通过，M1-A 关闭

范围：零真实 API；不改 metric、prompt 字节、method 算法、artifact schema 或第三方源码

## 1. 判词

M1-A 只处理已经由 current-source 审计坐实的两条反向依赖，并给 live 文档与依赖方向加
最小自动门。它不是按文件数“整理目录”，也不提前执行 M1-B 的 config-track 迁移。

本批目标态：

1. `runners` 不再 import 最外层 `cli`；
2. `prompts` 只保存 prompt/profile 数据和稳定 evaluator key，不持有 evaluator class；
3. live 入口相对链接与上述两条依赖方向有自动回归门；
4. compact 恢复直接获得有界 Git 快照、唯一热胶囊和 transcript 定位器；
5. shim/legacy 的消费者与退出门落盘，禁止下一批凭名字误删。

## 2. `runners → cli` 切割

原 `runners/cost_calibration.py` 从 `cli/run_prediction.py` import application service，造成
内层 runner 反向依赖外层 CLI。现把 registered prediction application service 移到
[`runners/registered_prediction.py`](../../../../src/memory_benchmark/runners/registered_prediction.py)：

- `cli/commands.py` 与 `runners/cost_calibration.py` 都依赖 canonical service；
- 历史 `memory_benchmark.cli.run_prediction` 变成薄兼容模块；
- shim 用同一个 module object 代理 canonical module，而不是逐项复制符号。这保住旧测试/
  扩展对 module attribute 的 monkeypatch 语义，也避免两份模块级状态；
- canonical module 暂时仍包含旧 argparse `main()`，因为把 application service 再拆成
  planning/ingest/answer/parallel 属 M1-D。M1-A 只修依赖方向，不偷做第二种重构。

扫描结果：`src/` 内旧 CLI import 为 0；旧路径只剩 5 个测试文件消费。architecture test
锁住 `runners/` 对 `memory_benchmark.cli` 的绝对和相对 import。

## 3. `prompts → evaluators` 切割

`prompts/author/{lightmem,mem0}.py` 原本把 evaluator class 存进 judge profile，使纯资产层
反向依赖执行层。现改为 `evaluator_key`：

| author profile | key |
| --- | --- |
| LightMem LoCoMo | `locomo-judge` |
| LightMem LongMemEval | `longmemeval-judge` |
| Mem0 LoCoMo | `locomo-judge` |
| Mem0 LongMemEval | `longmemeval-judge` |
| Mem0 BEAM | `beam-rubric-judge` |

LoCoMo 的历史 native prompt override 仍只在 evaluator composition root 装配，并额外校验
profile key 与请求 metric 一致。其余 profile 过去保存的 class 没有生产消费；改为 key 不改变
judge prompt、settings、skip policy 或评分路由。全 `prompts/` AST 门禁止重新 import
`memory_benchmark.evaluators`。

## 4. freshness 与 compact 自举

### 4.1 live-link gate

`tests/test_documentation_standards.py` 只扫描热入口，而不把 archive 历史断链扩成无边界工程：

- `AGENTS.md`、根 README、docs README、roadmap；
- 架构师 onboarding/playbook/代码结构判据；
- 当前唯一 P0 workstream README。

第一轮门真实抓出根 README 三条迁移后未更新的链接；已分别改到
`docs/reference/` 和 `docs/archive/logs/` 的现存 canonical 文件。不是为测试造空壳。

### 4.2 compact 热快照

项目 `SessionStart(source=compact)` hook 现在注入：

- hook 时刻 `git status --short`（有界）与 `git log -5 --oneline`；
- roadmap 解析出的唯一 P0 README 中，仅“Codex 恢复胶囊”一节；
- `session_id` 与 `transcript_path` 定位器；
- Git/胶囊冲突、按需回查 transcript、静默后台恢复等判据。

Git 或胶囊读取失败时才退回原四步门。hook 不自动总结聊天、不修改文档，也不把 transcript
当项目事实源。长期记忆仍由“稳定落点 + 索引入口 + 任务读取触发器 + supersede 路径”组成；
transcript 只是逐字飞行记录器。hook 配置有改动，合入后须由用户在 `/hooks` 重新审核信任。

## 5. shim / legacy 消费者与退出预算

以下为 2026-08-14 current-main 的引用扫描，不把“零生产引用”自动等同“本批删除”：

| 资产 | current 消费者 | 分类 | 退出门 |
| --- | --- | --- | --- |
| `cli/run_prediction.py` | `src/` 0；5 个 tests | 新兼容 shim | M1-D 完成 service/facade 拆分、测试迁 canonical、旧 module CLI parity 有替代后退出 |
| `methods/{lightmem,mem0,memoryos}_native_prompts.py` | `src/` 0；5 个 tests | 旧 import shim | M1-B 让新 run 不再走 config-track，测试迁 canonical，并通过 prompt parity + 全量门后退出 |
| `evaluators/{answer_text,retrieval_metrics,halumem_prompts}.py` | `src/` 0；4 个 tests | 旧 import shim | 逐个迁测试并复核公开示例/扩展；不和 M1-B 捆绑删除 |
| `BaseMemoryRetriever` | 只在 `core` 定义/re-export；生产/测试无实例 | 确认 legacy 候选 | 独立小批移除；先确认 0.1.0 未承诺稳定 Python import API，再跑 core/CLI/full 门 |
| `BaseResumableMemorySystem` | `prediction.py` 与 Mem0 adapter 生产可达 | 活跃兼容 | 当前禁止删除；先迁 Mem0 与 turn-resume 调用 |
| `LegacyProviderBridge` | `prediction.py` 生产可达且有协议强校验 | 活跃兼容 | 当前禁止删除；v2-bridged production path 清零后另裁 |
| `TurnIngestCheckpointStore` | `prediction.py` / `ingest_resume.py` 生产可达 | 活跃 resume 能力 | 保留；不能因文件名含 ingest/legacy 误删 |
| `memoryos_locomo_{smoke,full}.py` | 新生产入口 0；两套专属 tests | 冻结 reproduction capsule | 先迁 `legacy/` 命名空间并保留 shim；受保护旧产物可复现前不删逻辑 |
| `TrackIdentity v1` / `config_track.py` | prediction、evaluate、cost readback 均生产可达 | 活跃迁移 + 历史回读 | M1-B 只退出新 run 选择器；旧 artifact parser/readback 长期保留 |

这张表的读取触发器是：删除/移动 shim、legacy、runner、resume 或 config-track 前。新证据推翻
任一行时，先更新本表或给出 superseding note，再施工。

## 6. 行为边界

本批明确未改变：

- prediction output 目录、manifest/resume identity、run plan；
- unified/native 现行行为（它的退出是 M1-B）；
- answer/judge prompt 字节、LLM settings 与 evaluator 公式；
- method ingest/retrieve、worker/lifecycle、data/models/outputs/third-party；
- 任何真实 API 或实验资产。

## 7. 验收

定向守恒门：

```text
234 passed in 12.27s
```

覆盖 architecture、hook、prompt、config-track、cost calibration、prediction CLI、main CLI 与
live 文档链接。

```text
uv run python -m compileall -q src/memory_benchmark tests
exit 0

OPENAI_KEY=offline-dummy ... uv run pytest -q -m 'not api'
2164 passed, 3 deselected, 13 warnings, 29 subtests passed in 173.27s (0:02:53)
```

全量门把 primary 与 OpenCodeGo transport 都覆盖成 `offline-dummy` + 本机拒绝端口；没有真实
API 调用。13 个 warning 均来自既有 LightMem Pydantic 与 MemOS datetime/Pydantic 警告。
最终 `git diff --check` 无输出。
