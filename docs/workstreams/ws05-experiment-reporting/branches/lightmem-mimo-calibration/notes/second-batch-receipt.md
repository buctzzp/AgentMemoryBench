# LightMem × Mimo calibration 第二批 resume 收据

日期：2026-08-27

状态：`FINAL_ACCEPTED_AT_ADAPTIVE_STOP`

## 1. 范围与当前判词

本批严格复用首批五个 run identity、完整 ordered cohort 与 `workers=10`：LoCoMo、
LongMemEval-S、BEAM-100K、HaluMem-Medium 各新增 2 个 isolation；MemBench 第二批四 lane 共新增
8 个。三点敏感性门显示 MemBench lane 内 token 仍明显异质，故只对 MemBench 条件执行第三批、
再增加 p10/p90 共 8 个；其余四格停在 p25/p50/p75。全程没有改 profile、runtime、worker、
variant、run id 或 cohort 顺序。

五格 conversation/question 均零失败。HaluMem extraction 与 memory-type 继续按用户裁决缺席，
不因扩大样本恢复。

## 2. 已完成 prediction

| benchmark | 累计 isolation | 累计问题 | 本批新增 isolation | 失败 |
| --- | ---: | ---: | --- | ---: |
| LoCoMo | 3 | 488 | `conv-26`, `conv-43` | 0 |
| LongMemEval-S | 3 | 3 | `0ea62687`, `1d4da289` | 0 |
| BEAM-100K | 3 | 60 | `1`, `20` | 0 |
| MemBench 0-10K | 20 | 20 | p25/p75 与条件 p10/p90，四 lane 共 16 条 | 0 |
| HaluMem-Medium | 3 | 517 | 两个锁定 UUID | 0 |

BEAM 首次 resume 在任何 API 调用前因 `dataset_sha256` 漂移被正确拒绝；根因与 serializer-layer
修复见 [BEAM R1](beam-resume-artifact-projection-r1.md)。同一原 run 修复后只选择 `1`、`20`，
没有产生半写或重复 isolation。

## 3. 本批新增 prediction token

下表只计本批新增 isolation；所有 LLM token 来源均为 API 返回的 `api_usage`。本地 embedding
token 仍以 `tokenizer_estimate` 单列在原始 observation，不混入本表。

| benchmark | build calls / in / out | answer calls / in / out | 新增 prediction tokens |
| --- | --- | --- | ---: |
| LoCoMo | 64 / 162,603 / 54,639 | 330 / 862,838 / 3,095 | 1,083,175 |
| LongMemEval-S | 94 / 228,393 / 37,747 | 2 / 5,411 / 287 | 271,838 |
| BEAM-100K | 87 / 196,458 / 37,722 | 40 / 116,288 / 3,645 | 354,113 |
| MemBench 0-10K | 36 / 61,763 / 11,552 | 8 / 12,041 / 16 | 85,372 |
| HaluMem-Medium | 250 / 602,219 / 150,641 | 348 / 1,180,878 / 3,364 | 1,937,102 |
| MemBench 条件 p10/p90 | 34 / 60,626 / 13,321 | 8 / 13,403 / 16 | 87,366 |

本批新增 prediction 合计 3,818,966 API tokens，prediction failed-attempt ledger 均为 0。

## 4. 已完成 evaluator 与增量付费守恒

离线 metric 从累计 prediction 全量重算；paid judge 使用
[M2 增量复用合同](incremental-paid-judge-resume-m2.md)，旧 score/token 不重打。

| benchmark | 累计主分 | 累计分母 | 本批新增 judge calls / in / out | 失败 |
| --- | ---: | ---: | --- | ---: |
| LoCoMo judge | 0.6475409836 | 488 | 330 / 212,892 / 3,282 | 0 |
| LongMemEval judge | 1.0 | 3 | 2 / 1,065 / 4 | 0 |
| BEAM rubric judge | 0.4418253968 | 60 | 198 / 145,627 / 12,461 | 0 |
| HaluMem QA | 0.5783365571 | 517 | 348 / 394,407 / 38,632 | 0 |
| HaluMem update | 0.7650727651 | 481 | 310 / 1,090,625 / 42,696 | 0 |
| MemBench choice/source accuracy | 0.7 / 0.7 | 20 / 20 | N/A（离线） | 0 |

其他累计结果：LoCoMo official-style F1=0.4598101317、generic F1=0.4420374483、recall=
0.6741022639；LongMemEval generic F1=0.0791047117、recall/rank 继续为 N/A；BEAM recall
继续为 N/A；MemBench recall=0.7341666667；HaluMem generic F1=0.3487308751、normalized
EM=0.1083172147、substring EM=0.1508704062。

本批新增 judge 合计 1,941,691 API tokens；连同 prediction，本批共新增 5,760,657 API tokens。
五格当前累计 prediction=5,670,438、judge=2,950,184，总计 8,620,622 个真实 API tokens。
LoCoMo、LongMemEval、BEAM 的首批 score/observation 保留门已通过；HaluMem QA/update 首批 score
前缀 SHA-256 分别仍为 `9f27a761…` / `7dffc438…`。两项在无新增单元下立即复跑，四份最终
score/observation SHA-256 全部不变。全部 API LLM observation 都是 `api_usage`，没有用 tokenizer
估算补账。

> 2026-08-27 freshness correction：首版 source accuracy 行停在第二批中途的 12 题派生
> summary；prediction/choice score 已达到 20 题。answer artifact v2 验收时用既有 choice score
> 零 API重跑 source evaluator，current source accuracy 为 14/20=0.7。本修正不改变任何 prediction、
> choice score、LLM judge 或 token observation。

## 5. 自适应停表依据

按 isolation 合并 prediction 与该 benchmark 的 paid judge 后，依次按 p25 / p50 / p75 的三点真实
API token 为：LoCoMo 581,128 / 634,423 / 718,221；LongMemEval-S 131,351 / 134,653 /
141,556；BEAM-100K 247,968 / 239,605 / 264,233；HaluMem-Medium 1,640,515 / 1,802,704 /
1,862,947。四格没有出现会
改变预算量级的新尾部，继续跑 p10/p90 的边际收益不足以抵消真实调用成本。

MemBench 的五点 lane 范围仍明显不同：first-high 4,696–11,405、first-low 6,066–45,228、
third-high 2,414–6,469、third-low 2,802–9,018 API tokens。条件第三批因此是必要的；现在每 lane
已有 p10/p25/p50/p75/p90 五点，预算分层已闭合，不再追加。

## 6. 预算解释边界

本轮 Mimo token 是低价 runtime 的真实用量，可在同调用拓扑与 prompt shape 假设下乘目标模型
当期价格做预算区间；它不是 GPT-4o-mini 的实测 token、分数、速度或价格。目标模型经费优先
覆盖由 observation 证明效率较高的方法（当前候选含 LightMem、SimpleMem）；A-Mem 等高调用
方法允许只提供低价模型 token 外推，并必须明确标注未做目标模型 full。

## 7. 最终判词

`LIGHTMEM_MIMO_CALIBRATION_ACCEPTED_AT_ADAPTIVE_STOP`：五格已完成当前预算外推所需 paired
cohort、适用 evaluator、SDK usage、增量复用与零新增幂等门。LightMem 不再继续真实 API；下一条
关键路径切换到 SimpleMem，并复用同一 cohort。MemBench 因 benchmark 异质性直接复用完整五点
四 lane，其他四格复用三点。
