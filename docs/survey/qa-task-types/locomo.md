# LoCoMo QA 任务类型

更新日期：2026-08-26。数据源：`data/locomo/locomo10.json`，10 个 conversation、1,986 道
原始 QA；Phase 1 当前排除 category 5，主 QA cohort 为 1,540 道。

## 原生类型

数字到语义的映射由论文任务定义、官方 scorer 分支和 current 数据交叉确认。answer/evidence
只在下表作为解释，运行时仍是 evaluator-private。

| category | 数量 | 定义 | 真实例子 | 官方/现行主分 |
| --- | ---: | --- | --- | --- |
| `4` Single-hop | 841 | 从一个局部对话事实直接作答 | `conv-26 / qa[82]`：慈善赛为何提高意识？→ `mental health`，evidence=`D2:2` | token F1 |
| `1` Multi-hop | 282 | 综合多个 session/utterance 的证据 | `conv-42 / qa[1]`：Joanna 和 Nate 有哪些共同兴趣？→ watching movies、making desserts，证据跨 D1/D3/D4/D10/D20 | 多答案 token F1 |
| `2` Temporal | 321 | 利用日期、时间线或先后关系 | `conv-43 / qa[20]`：John 去 Chicago 前在哪座城市？→ `Seattle` | token F1；answer prompt 带日期 |
| `3` Open-domain / commonsense | 96 | 把人物记忆与常识结合，答案未必在原文逐字出现 | `conv-26 / qa[22]`：Caroline 书架上可能有 Dr. Seuss 吗？→ 根据她收藏经典童书推断 yes | token F1；gold 分号后解释按官方规则截断 |
| `5` Adversarial / unanswerable | 446 | 故意把人物或事实错配，期待指出未提及 | `conv-26 / qa[192]` 询问 Caroline 的儿子，但相关历史属于 Melanie | 官方拒答判定；Phase 1 当前未纳入 |

## 横向映射（2026-08-26 裁定）

- category 4：事实回顾/信息抽取。
- category 1：多证据/跨会话推理。
- category 2：时间与事件顺序。
- category 3：泛化应用；`evidence=[]` 的 4 题继续保留 provenance 提示。
- category 5：Phase 1 继续排除，不进入可答性边界或 overall。

横向聚合使用固定 framework answer LLM 的输出，经冻结 LoCoMo semantic judge 得到逐题
`0/1` credit；token F1 继续作为 LoCoMo 原生指标单独报告，不与其他 benchmark 的不同公式直接
平均。

## 需要保留的争议

- category 3 有 4 道 `evidence=[]`。它们仍可进入 LoCoMo 官方 QA 分，但不能不加说明地宣称
  100% 是 memory-grounded generalization。
- category 5 的 446 道题绝大多数使用 `adversarial_answer` 而不是普通 `answer`；当前 adapter
  在构造主 QA 前排除它们，因此 v3 固定题池同样排除，不能拿来计算 memory boundary。
- LoCoMo 论文还有 event summarization，但那是独立 task family，不属于本文 QA category。

完整数据/异常/流程入口：[benchmark 卡](../benchmarks/LoCoMo.md)、
[dataset 卡](../datasets/locomo.md)、[workflow 卡](../workflows/locomo.md)。
