# 分批 paid judge 增量复用 M2

日期：2026-08-26

## 1. 触发原因

`predict formal --resume` 会在同一 run 中追加第二批 isolation 的 prediction。旧 evaluator
runner 每次都遍历当前全部 prediction；若直接重跑 judge，会再次付费评测首批 582 次调用，
并可能让同 observation id 的新响应与旧 token 冲突。用户明确要求按 method 完整记录 token，
且目标模型预算有限，因此付费重复不是可接受的“实现简单”取舍。

## 2. 合同

- 只对声明 efficiency observability 的 LLM judge 启用 paid score 复用；离线公式继续从当前
  artifact 全量重算，成本近似为零。
- 任何新 API 调用前，既有 score 必须同时具有同 metric model inventory 与非空 efficiency
  observation ledger；缺一项即 fail-fast，不重打、不补猜 token。
- model inventory 与当前 evaluator 不同也在 API 前失败。旧 score 的 metric、question/
  conversation 或 artifact unit identity 必须仍属于当前 prediction 输入，重复、越界或错配均拒绝。
- answer-level LoCoMo/LongMemEval 以 `question_id` 复用；BEAM rubric 与 HaluMem QA 同样按
  `question_id`；HaluMem update 使用
  `(conversation_id, session_id, gold_memory_index)`，避免跨 UUID 的 `s1` 碰撞。
- 新单元才进入有界线程池；最终 score rows 按当前公开输入顺序合并旧、新记录。既有 token
  observation 保留，新 observation 继续按确定性 id 幂等 merge。
- HaluMem extraction 当前不进入实验，且其一 session 多 score 的 cache contract 尚未实现；若
  已有 extraction paid score 后重复执行，runner 明确拒绝，而不是静默全量重打。

## 3. 强反例

1. 普通 answer-level judge：首批 1 题，再追加 1 题；第二个 client 恰好 1 次调用，最终 2 条
   score、2 条 token observation，input/output token 总和 36/3。
2. BEAM artifact judge：首批 1 个 rubric question，再追加 1 个；第二个 client 恰好 1 次调用，
   旧 1.0 与新 0.5 顺序保持，token 总和 16/3。
3. HaluMem update：首批 `(user-1,s1,2)`，再追加 `(user-1,s1,1)`；第二个 client 恰好 1 次
   调用，tuple identity 无碰撞，token 总和 18/3。
4. 删除已有 judge token ledger 后重跑：在新 client 零调用时抛
   `existing judge scores require existing efficiency observations`。

定向零 API 门：

```text
126 passed in 18.65s
```

current 全量零 API 门：

```text
2364 passed, 3 deselected, 25 warnings, 29 subtests passed in 256.57s
```

同时 `git diff --check` 干净。

## 4. 本轮使用方式

第二批 prediction 完成后，离线 metric 可直接重算；五个 paid judge 使用与首批相同的 Mimo
runtime、metric 与 compact profile。runner 读取首批 score/token，只为新增 LoCoMo/LME/BEAM/
HaluMem QA/update 单元调用 API。机器验货必须同时核：

- `new API call count == 新增可评测单元的官方调用拓扑`；
- 累计 score 分母等于首批 + 第二批；
- 累计 token ledger 旧 observation 数不减少、旧记录逐字不变；
- failed attempt 单独累计，不从成功 token 中消失。

该能力是分批 calibration 的防重复计费门，不是允许跨模型、跨 prompt 或跨 evaluator 版本复用
score。语义身份变化必须新 metric/run，不能强行吃旧 cache。

## 5. 真实最小增量哨兵

LongMemEval-S 首批已有 1 条 paid score / 1 条 `api_usage` observation。第二批 prediction 追加两题
后，以相同 Mimo runtime、compact profile 与 metric 运行 evaluator：最终 3/3 score，observation
恰好由 1 增至 3，累计 input/output token 为 1,495/6；首批 score 原文与首批 observation 原文
都仍存在。随即在没有新增 prediction 的前提下再运行一次，score JSONL 与 observation JSONL 的
SHA-256 前后逐字一致，证明零新增单元时不会发起隐藏重打或改写 token 账。
