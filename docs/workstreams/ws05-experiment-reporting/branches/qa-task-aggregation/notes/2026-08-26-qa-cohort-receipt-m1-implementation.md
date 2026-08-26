# QA cohort receipt M1 实现记录

日期：2026-08-26。范围：零 API 的 cohort 身份收据与 report 写出面。

## 1. 结果

- `qa-cohort-receipt-v1` 对调用方显式给出的 run 目录逐一复用现有
  `load_qa_run_score()`；没有新增 outputs discovery、数据库或第二套聚合公式。
- 每格收据锁 method/benchmark/variant/run-id/scope、dataset、answer、evaluator、纳入题池、
  isolation/task/capability、score input 与排除题集哈希；不写本机绝对路径或 secret。
- 同 benchmark 十家必须共享 variant、dataset、answer、evaluator 与完整 question identity。
  question-id 相同但 isolation/task/capability 不同也按 mismatch 阻断。
- writer 只落三份派生产物：`qa-cohort-receipt.json`、`qa-aggregate-report.json`、
  `qa-aggregate-report.md`。缺格/错 scope/身份漂移时写诊断但不写部分 overall。

## 2. ledger 基线修复

五份 ledger 都只落后当前 v1 模板的同两条 requirement：HaluMem 从历史 W1 文案升级为 UUID
worker-lane，parallel gate 明确 W2 是最小竞态哨兵而非能力上限。EverOS、Graphiti、LangMem、
Letta、Supermemory 仅机械同步这十处文字；各家 status、evidence、ruling、next 均未改写。

## 3. 不能提前伪造的东西

当前尚无满足新 source/embedding/runtime identity 的完整 10×5 formal artifact，因此本批只完成
收据机制，不能生成 `status=ok` 的实物收据，更不能发布排名。首批 formal 完成后，必须显式提交
50 个 run 目录再生成收据；历史 smoke/pilot 不自动混入。

## 4. 停手线

本批不新增 CLI 子系统、自动 run 发现、cohort 数据库、bootstrap、显著性检验或真实 API。M2 的
paired cluster bootstrap 继续等待完整 cohort；后续若需要命令面，只给现有三个薄函数增加组合根，
不复制 identity/聚合逻辑。

## 5. 验证

- ledger + QA aggregation 定向门：`31 passed in 0.48s`。
- Python 编译通过；`git diff --check` 干净。
- workspace 未安装 `ruff`，命令返回 `No such file or directory`，未据此修改代码。
- 全量零 API门：`2333 passed, 3 deselected, 25 warnings, 29 subtests passed in 172.29s`。
