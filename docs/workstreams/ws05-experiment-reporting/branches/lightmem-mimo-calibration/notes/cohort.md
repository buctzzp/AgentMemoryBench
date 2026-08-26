# LightMem × 五 benchmark Mimo calibration cohort（2026-08-26）

## 1. 用户裁决与运行身份

- 本轮只运行 LightMem；其余九家等待后续 call。
- API runtime：`opencodego/mimo-v2.5`，读取 `.env` 第三槽；Chat Completions 请求显式发送
  `thinking={"type":"disabled"}`。
- 公开 profile：`calibration`。它复用同一 `[method]` 算法参数，FULL run scope、完整 isolation、
  全部问题、严格 manifest/resume；不是 smoke crop 或固定首 isolation 的 pilot。
- answer role/temperature/max_tokens/top_p 仍按五家 benchmark 统一 resolver。LoCoMo 继续应用既有
  OpenCodeGo completion cap 4096；这是已记录的 provider compatibility，不是 Mimo 专调。
- `--workers 10` 从首轮进入 resume identity；它是上限，不保证首轮真实启动 10 个 worker。

本 note 只锁配置、cohort 与命令形状，未调用 API。

## 2. 公开 shape 选样规则

候选只读取 canonical public conversation 的 session/turn/question、speaker/content/time、图片 caption
与公开 options；不读取 gold answer、evidence、judge label 或 method 输出。对每个 isolation 计算：

1. session 数；
2. turn 数；
3. history token proxy；
4. question 数；
5. question token proxy。

token proxy 使用本地 `cl100k_base`，把数据中的保留字面量也按普通文本编码；它只用于确定性排序，
不冒充 Mimo 的 API billing token。每个特征先转为当前 dataset（MemBench 为当前 source lane）内的
经验百分位，再按到目标 `(p,p,p,p,p)` 的欧氏距离选择最近 isolation。目标顺序固定为
`p50 → p25 → p75 → p10 → p90`，逐次无放回，距离并列按 isolation id 排序。

该 cohort 用于预算与扩大稳定性，不宣称五条样本足以给出正式效果排名。

## 3. 五家 ordered cohort

### LoCoMo `locomo10`

run id：`lm-cal-mimo25-locomo-p5-v1`

1. p50 `conv-50` — 30 sessions / 568 turns / 21,671 history proxy tokens / 158 questions
2. p25 `conv-26`
3. p75 `conv-43`
4. p10 `conv-30`
5. p90 `conv-48`

### LongMemEval `s_cleaned`

run id：`lm-cal-mimo25-lme-s-p5-v1`

1. p50 `561fabcd` — 49 sessions / 495 turns / 104,393 history proxy tokens / 1 question
2. p25 `0ea62687`
3. p75 `1d4da289`
4. p10 `gpt4_d6585ce9`
5. p90 `e982271f`

### HaluMem `medium`

run id：`lm-cal-mimo25-halumem-medium-p5-v1`

1. p50 `42f702e3-750c-1acc-9101-051f1f75991e` — 70 sessions / 3,156 turns /
   228,532 history proxy tokens / 169 questions
2. p25 `2f1f897e-d67f-dbc5-6a7b-b7634a9e294f`
3. p75 `5c005ed8-0d18-99f8-a20e-6a776a7ea30a`
4. p10 `91b283d7-7236-3b83-abeb-f0a159564f45`
5. p90 `ffccb278-6ad3-7c1b-e682-44543d5a12cb`

### BEAM `100k`

run id：`lm-cal-mimo25-beam-100k-p5-v1`

1. p50 `16` — 5 sessions / 322 turns / 133,365 history proxy tokens / 20 questions
2. p25 `1`
3. p75 `20`
4. p10 `2`
5. p90 `11`

### MemBench `0_10k`

run id：`lm-cal-mimo25-membench-0-10k-p5x4-v1`

每一轮按 `first-high → first-low → third-high → third-low` 排列，确保全局 budget 可按四条 source
lane 公平推进：

| round | first-high | first-low | third-high | third-low |
| --- | --- | --- | --- | --- |
| p50 | `first-high-highlevel_rec-food-12` | `first-low-noisy-events-18` | `third-high-highlevel-book-76` | `third-low-noisy-roles-49` |
| p25 | `first-high-highlevel-food-87` | `first-low-lowlevel_rec-book-22` | `third-high-highlevel-book-62` | `third-low-noisy-events-19` |
| p75 | `first-high-highlevel_rec-food-55` | `first-low-noisy-roles-49` | `third-high-highlevel-food-18` | `third-low-noisy-hybrid-47` |
| p10 | `first-high-highlevel-movie-78` | `first-low-lowlevel_rec-food-23` | `third-high-highlevel-movie-17` | `third-low-comparative-events-15` |
| p90 | `first-high-highlevel_rec-book-5` | `first-low-noisy-roles-47` | `third-high-highlevel-book-96` | `third-low-simple-hybrid-13` |

四条 lane 的当前数量分别为 700 / 900 / 400 / 1,400，本 cohort 不存在耗尽。未来若使用相同规则
生成更长名单，某 lane 无剩余时只是不再追加该 lane，不跨 lane 补数。

## 4. 分批预算与实际并发

| run | 首批 budget | 首批实际最多活跃 worker | 第二批增量 | 第三批增量 |
| --- | ---: | ---: | ---: | ---: |
| LoCoMo / LME-S / HaluMem-Medium / BEAM-100k | 1 | 1 | 2 | 2 |
| MemBench 0-10k 四 lane | 4 | 4 | 8 | 8 |

`workers=10` 固定在 manifest。首批只有 1 或 4 个 pending isolation，所以不会为凑 W10 空启动十份
业务工作；后续按固定 cohort index 映射到稳定 `worker_N` state root。

特别注意：完整 isolation 不等于小调用。首个 HaluMem UUID 有 3,156 turns / 169 QA，首个 LoCoMo
conversation 有 158 QA；`conversation-budget=1` 不会把它们裁成 1 个 question。本轮应先逐 run
执行 prediction 并验货，再决定是否调用 API judge，避免把 answer/build 与 evaluator 成本混在一个
无法定位的失败里。

## 5. 开跑门

开跑前必须同时满足：

1. `calibration` 零 API配置门与全量测试通过；
2. 五个 run 目录均不存在，全部使用上述新 run id；
3. 用户确认上述完整-isolation 规模，尤其 HaluMem/LoCoMo 的全部问题数；
4. 用户明确授权真实 API；
5. 首批只运行 prediction，完成后逐项核 manifest、state、answer prompt、efficiency observation、
   completed/failed checkpoint 与 API usage，再开启下一 run 或 evaluator。

## 6. 零 API预检收据

- `.env` 第三槽存在且逐字为 `mimo-v2.5`；未打印 key/base URL。
- current composition：profile=`calibration`、provider=`opencodego`、model=`mimo-v2.5`、
  `thinking_mode=disabled`、structured output=`json_object`、default/resolved workers=10。
- LightMem resolved profile：public=`calibration`、section=`method`、run scope=`full`、
  injected build LLM=`mimo-v2.5`。
- 五个首批 argv 已经 argparse/normalizer：均为 `confirm_api=True`、`confirm_full=True`、workers=10；
  四个普通 benchmark 为 5-id cohort + budget 1，MemBench 为 20-id cohort + budget 4。
- 五个 run id 在当前 `outputs/` 均不存在。
- 配置/registry/CLI/文档定向门：`343 passed, 12 warnings in 8.36s`；`git diff --check` 干净。
- current 全量零 API 门：
  `2350 passed, 3 deselected, 25 warnings, 29 subtests passed in 171.63s`。

## 7. 首批 prediction 命令

以下命令是首批实际执行命令的冻结收据。五格 prediction 已于 2026-08-26 完成；执行后字段验货、
框架进度修复与效率汇总见 [首批 prediction 验货收据](first-batch-prediction-receipt.md)。

```bash
uv run memory-benchmark predict formal --root . \
  --method lightmem --benchmark locomo --variant locomo10 \
  --profile calibration --run-id lm-cal-mimo25-locomo-p5-v1 \
  --workers 10 --conversation-budget 1 --allow-api \
  --isolation-id conv-50 --isolation-id conv-26 --isolation-id conv-43 \
  --isolation-id conv-30 --isolation-id conv-48
```

```bash
uv run memory-benchmark predict formal --root . \
  --method lightmem --benchmark longmemeval --variant s_cleaned \
  --profile calibration --run-id lm-cal-mimo25-lme-s-p5-v1 \
  --workers 10 --conversation-budget 1 --allow-api \
  --isolation-id 561fabcd --isolation-id 0ea62687 --isolation-id 1d4da289 \
  --isolation-id gpt4_d6585ce9 --isolation-id e982271f
```

```bash
uv run memory-benchmark predict formal --root . \
  --method lightmem --benchmark halumem --variant medium \
  --profile calibration --run-id lm-cal-mimo25-halumem-medium-p5-v1 \
  --workers 10 --conversation-budget 1 --allow-api \
  --isolation-id 42f702e3-750c-1acc-9101-051f1f75991e \
  --isolation-id 2f1f897e-d67f-dbc5-6a7b-b7634a9e294f \
  --isolation-id 5c005ed8-0d18-99f8-a20e-6a776a7ea30a \
  --isolation-id 91b283d7-7236-3b83-abeb-f0a159564f45 \
  --isolation-id ffccb278-6ad3-7c1b-e682-44543d5a12cb
```

```bash
uv run memory-benchmark predict formal --root . \
  --method lightmem --benchmark beam --variant 100k \
  --profile calibration --run-id lm-cal-mimo25-beam-100k-p5-v1 \
  --workers 10 --conversation-budget 1 --allow-api \
  --isolation-id 16 --isolation-id 1 --isolation-id 20 \
  --isolation-id 2 --isolation-id 11
```

```bash
uv run memory-benchmark predict formal --root . \
  --method lightmem --benchmark membench --variant 0_10k \
  --profile calibration --run-id lm-cal-mimo25-membench-0-10k-p5x4-v1 \
  --workers 10 --conversation-budget 4 --allow-api \
  --isolation-id first-high-highlevel_rec-food-12 \
  --isolation-id first-low-noisy-events-18 \
  --isolation-id third-high-highlevel-book-76 \
  --isolation-id third-low-noisy-roles-49 \
  --isolation-id first-high-highlevel-food-87 \
  --isolation-id first-low-lowlevel_rec-book-22 \
  --isolation-id third-high-highlevel-book-62 \
  --isolation-id third-low-noisy-events-19 \
  --isolation-id first-high-highlevel_rec-food-55 \
  --isolation-id first-low-noisy-roles-49 \
  --isolation-id third-high-highlevel-food-18 \
  --isolation-id third-low-noisy-hybrid-47 \
  --isolation-id first-high-highlevel-movie-78 \
  --isolation-id first-low-lowlevel_rec-food-23 \
  --isolation-id third-high-highlevel-movie-17 \
  --isolation-id third-low-comparative-events-15 \
  --isolation-id first-high-highlevel_rec-book-5 \
  --isolation-id first-low-noisy-roles-47 \
  --isolation-id third-high-highlevel-book-96 \
  --isolation-id third-low-simple-hybrid-13
```

第二批必须原样重复全部 `--isolation-id` 与 `--workers 10`，增加 `--resume`；普通四格把 budget
改为 2，MemBench 改为 8。第三批同理再用 2 / 8。任何 runtime、名单、顺序、worker、variant 或
run id 变化都新建 run，不能强行 resume。
