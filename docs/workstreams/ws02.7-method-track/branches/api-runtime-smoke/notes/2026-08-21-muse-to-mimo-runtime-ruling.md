# Muse → Mimo smoke runtime 改判

日期：2026-08-21

## 1. 触发

用户在 `.env` 增加 `opencode_model_name_3=mimo-v2.5`，要求 Muse 因区域或兼容性不可用时
改用 Mimo。架构师没有实现请求级自动 fallback；同一 run 混用模型会污染 manifest、resume、
分数与成本账。

## 2. 最小真调用

只调用 OpenCodeGo Chat Completions，不启动 benchmark、method、数据库或 run。两个候选使用
同一生产兼容形状：`temperature=0`、`max_tokens` 小上限、JSON mode 与
`thinking={"type":"disabled"}`。

```text
MODEL_PROBE model=muse-spark-1.2-contributor result=PASS finish_reason=None content_chars=0
MODEL_PROBE model=mimo-v2.5 result=PASS finish_reason=stop content='{"ok": true}' prompt_tokens=263 completion_tokens=6
```

Muse 的 HTTP 成功不能掩盖语义失败：空 content 与空 finish reason 无法作为 answer/judge
runtime。Mimo 在相同请求面正常完成，故新 smoke 默认改为 `opencodego/mimo-v2.5`。

## 3. 身份与回读

- 第一槽 `opencode_model_name`：旧 DeepSeek artifact；
- 第二槽 `opencode_model_name_2`：旧 Muse artifact；
- 第三槽 `opencode_model_name_3`：current Mimo smoke；
- 新 run 的 TOML、answer runtime、method build runtime、manifest 与 resume identity 必须全为
  Mimo；
- 已创建的 Muse run 不得原地切模型 resume，只能按原 identity 回读，或另用新 run_id 重跑。

## 4. 成本边界

ws05 可用 Mimo 采集 token、调用数、latency 与记忆规模，再按 GPT-4o-mini 单价作
token-price projection；模型输出可能改变后续调用拓扑，因此仍须极小 GPT-4o-mini calibration，
不能把单价换算冒充正式成本真值。

## 5. 验收

- 受模型身份影响的 tests：`905 passed, 12 warnings in 50.15s`；
- hook/config/docs/architecture 定向：`77 passed in 4.51s`；
- compileall：exit 0；
- 无 API 全量：`2198 passed, 3 deselected, 25 warnings, 29 subtests passed in 176.60s`。

首轮全量在 ws03 刚关闭、没有活跃 P0 时暴露 compact hook 的“必须有唯一活跃线”旧假设；
生产与 model tests 已通过，只有两条 hook 测试失败。最终修成合法空闲态注入 roadmap 胶囊后，
全量复跑如上全绿；没有为通过测试而把已完成 ws03 伪标回进行中。
