# 2026-08-26 Boundary 与文档拆分重开记录

## 用户纠正

1. 项目要评测 memory module；boundary 题若 provider 检索出无关记忆，不能仅因 answer LLM
   最终拒答就称记忆模块正确。empty retrieval 或明确的“没有相关记忆”都可接受。
2. 本轮所需交付是五个 benchmark 各一份 task-type 文档，再单独一份 aggregation draft；用户先
   阅读、再与架构师讨论，不能先宣布 taxonomy/权重定稿。

## 架构订正

- Boundary 拆成 `retrieval_boundary` 与 `answer_abstention`。free-form sentinel 应由 adapter
  转成 typed outcome，不能靠字符串匹配计分。
- current `_retrieved_items_payload()` 把 `RetrievalResult.items=None` 与 `items=()` 都写成 `[]`。
  前者可能是 method 不提供结构化 items，后者才是真实 0-hit，因此旧 artifact 暂时不能可靠计算
  strict retrieval-boundary。
- MemBench `noisy` 一手复核发现：原生 task 由 `DialogueGeneration/noise.py` 与
  `DialogueGenerationCouple/CoupleNoise.py` 给**问题**加无关 murmuring + 转折，再提出真正问题；
  主分仍为 A/B/C/D choice accuracy。100K 向历史注入 NoiseData 是另一条长度/干扰轴。
- `qa-task-aggregation-v2` 降为 `qa-task-aggregation-v2-draft`；branch 重回 in-progress，formal
  ranking 与 M1 cohort 继续暂停。

## 当前交付

- `docs/survey/qa-task-types/{locomo,longmemeval,beam,membench,halumem}.md`
- `docs/survey/qa-task-types/aggregation-draft.md`
- `docs/survey/qa-task-types/README.md`

五份单家文档中的 source/task/count/example/scorer 是调查事实；横向映射、boundary headline 和
权重方案全部留作用户讨论项。

零 API 定向门：`66 passed in 4.42s`；`git diff --check` 无输出。未生成排名、未改旧 artifact、
未调用真实 API。
