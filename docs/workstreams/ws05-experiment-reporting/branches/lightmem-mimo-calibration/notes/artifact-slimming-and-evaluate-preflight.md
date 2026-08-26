# LightMem 首批 artifact 瘦身与 evaluate 预检

日期：2026-08-26

## 1. 裁决

- HaluMem QA/update 均消费 method 自然返回的 memory window。官方 Mem0 wrapper 的
  `top_k=20/10` 不是 benchmark-wide 截断，LightMem 当前 top-60 prediction 无需重跑。
- `answer_prompts.prediction.jsonl` 的精确 API 请求由 `prompt_messages` 保存；逐题再写完整
  `answer_prompt`、与顶层相同的 `metadata.answer_context`、以及仅供 method 调试的
  `metadata.retrieved_memories` 是重复存储，不属于 scorer 合同。
- BEAM evaluator 只消费 gold answer/evidence groups、`ability`、`rubric`、`difficulty` 与
  ambiguity/unmatched 计数。生成期的 conversation 级大字段由 source lock 保存，不逐题复制。
- formal `conversation_budget` 首批只产生已完成问题的 answer artifact，而 public/private
  标签覆盖完整选中 cohort。retrieval evaluator 应验证完整标签彼此一致，再投影到已完成
  answer 子集；不能要求三份集合在首批就完全相等。

## 2. 实现边界

新 prediction artifact：

- 保留 `prompt_messages`、`formatted_memory`、`retrieved_items`、query K、evidence 与非重复
  metadata；
- 不再写 `answer_prompt`；resume 继续从 `prompt_messages` 重建兼容文本视图，实际 API
  message 字节不变；
- 只在 `answer_context == formatted_memory` 时删除该 metadata 副本；
- 删除 scorer 不消费的 `retrieved_memories` 调试副本。原始 product state 与 canonical
  readout/provenance 均仍保留。

BEAM private label 不再逐题复制 `conversation_seed/user_profile/conversation_plan/
user_questions/narratives` 或完整 question object。旧 run 可由同一确定性投影离线瘦身；不重跑
method、answer LLM 或 judge。

## 3. Judge 调用预览

首批当前完成题面：

| evaluator | 必需 API 调用 |
| --- | ---: |
| LoCoMo judge | 158 |
| LongMemEval judge | 1 |
| BEAM rubric judge | 49 rubric + 2 整题顺序 judge + 0–32 equivalence = 51–83 |
| HaluMem extraction | 680 integrity + 2,209 accuracy = 2,889 |
| HaluMem update | 171 |
| HaluMem QA | 169 |

HaluMem 全部三类合计 3,229 次 judge。extraction 是最大成本项，命令必须与 QA/update 分开，
不能把“本地并行不吃资源”误解为远端 provider 没有并发/速率限制。

## 4. 验收

现有五格 artifact 已用同一确定性投影离线瘦身，未调用 API：

| artifact | before | after |
| --- | ---: | ---: |
| BEAM answer prompts | 930,638 | 663,103 |
| HaluMem answer prompts | 9,065,340 | 6,278,518 |
| LoCoMo answer prompts | 13,753,589 | 4,912,800 |
| LongMemEval answer prompts | 98,241 | 37,303 |
| MemBench answer prompts | 218,851 | 81,134 |
| BEAM private labels | 7,705,204 | 109,806 |

合计减少 19,689,199 bytes。行数、question id、`prompt_messages`、canonical memory/items、
gold answer/evidence groups 与 scorer 必需字段均保持；prediction 与 method state 未改。

定向代码门：`376 passed in 13.11s`。五个现有 run 的 retrieval evaluator 只读预检：

```text
locomo-recall records=158 mean=0.6518987341772152 statuses=ok
longmemeval-recall records=1 mean=null statuses=n/a
longmemeval-retrieval-rank records=1 mean=null statuses=n/a
beam-recall records=20 mean=null statuses=n/a
membench-recall records=4 mean=0.5833333333333334 statuses=ok
OFFLINE_RETRIEVAL_PREFLIGHT_PASS
```

其中 N/A 是 LightMem 逐题 evidence 的既有诚实裁决，不是 artifact 缺失或本批回归。

最终 current 全量零 API 门：

```text
2356 passed, 3 deselected, 25 warnings, 29 subtests passed in 182.80s (0:03:02)
```

文档/registry/新合同定向门：`31 passed in 3.06s`；`git diff --check` 干净。
