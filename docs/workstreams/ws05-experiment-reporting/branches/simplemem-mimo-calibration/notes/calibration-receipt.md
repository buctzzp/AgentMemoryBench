# SimpleMem × Mimo calibration 实验收据

日期：2026-08-27

状态：`FINAL`

## 1. 身份与样本

- runtime：`opencodego/mimo-v2.5`，thinking disabled；profile=`calibration`；workers=10。
- LoCoMo、LongMemEval-S、BEAM-100K、HaluMem-Medium：逐字复用 LightMem 的
  p50→p25→p75→p10→p90 ordered cohort，本批 budget=3。
- MemBench 0-10K：逐字复用四 lane 五点 cohort，本批 budget=20。
- 五个 run 全是 fresh-state；未复用或重标历史 SimpleMem artifact。

run id：

1. `simplemem-cal-mimo25-locomo-p5-v1`
2. `simplemem-cal-mimo25-lme-s-p5-v1-s-cleaned`
3. `simplemem-cal-mimo25-beam-100k-p5-v1-100k`
4. `simplemem-cal-mimo25-membench-0-10k-p5x4-v1-0-10k`
5. `simplemem-cal-mimo25-halumem-medium-p5-v1-medium`

## 2. 开跑门

- 五个 run 目录启动前均不存在。
- current SimpleMem source/config/metric 资格沿用冻结页与 current 201-test 定向门；本批不升级
  upstream、不改 W40/O2、planning/reflection、串行 build 或 controlled MiniLM。
- 真实 Mimo streaming 最小探针经同一 OpenAI-compatible transport 得到 SDK usage：input=254、
  output=2、total=256；证明 provider 返回 `stream_options.include_usage=true` 尾块。
- HaluMem 最先启动；随后按内存与外部并发实测逐条填入 LME、BEAM、LoCoMo、MemBench。五条
  prediction 同时在途时，本机 memory free 仍约 43%，最大活跃 isolation 约 22，未出现失败账。
- MemBench 已完成 20/20 isolation/question、零失败；173 次 API LLM call / 458,800 tokens，
  memory_build=47 次 / 286,078 tokens、retrieval=106 / 145,307、answer=20 / 27,415；全部为
  `api_usage`。这同时证明 SimpleMem planning/reflection 没有被错记到 build，也没有因 streaming
  transport 退回估算。离线结果：choice/source accuracy 均为 0.75，Recall 诚实为 N/A。
- LongMemEval-S 已完成 3/3 isolation/question、零失败；prediction 61 次 API LLM call /
  719,772 tokens（build=678,102、retrieval=37,210、answer=4,460），judge 3 次 / 1,510 tokens，
  全部 `api_usage`。结果：judge=0.6666666667、F1=0.0768622438、normalized EM=0、substring
  EM=0.6666666667；Recall/rank 均诚实为 N/A。无新增单元立即重跑 judge 后 score/observation
  SHA-256 逐字不变。
- BEAM-100K 已完成 3/3 isolation、60/60 question、零失败；prediction 430 次 API LLM call /
  1,373,514 tokens（build=601,149、retrieval=695,184、answer=77,181），rubric judge 300 次 /
  224,506 tokens，全部 `api_usage`。rubric score=0.3685515873，Recall 诚实为 N/A；无新增单元
  立即重跑 judge 后 score/observation SHA-256 逐字不变。
- LoCoMo 已完成 3/3 conversation、488/488 question、零失败；prediction 3,279 次 API LLM call /
  6,876,314 tokens（build=389,177、retrieval=5,862,582、answer=624,555），judge 488 次 /
  319,372 tokens，全部 `api_usage`。结果：judge=0.5204918033、official-style F1=0.3619570546、
  generic F1=0.3495403088、normalized EM=0.1680327869、substring EM=0.2192622951；Recall
  诚实为 N/A。无新增单元立即重跑 judge 后 score/observation SHA-256 逐字不变。
- HaluMem-Medium 已完成 3/3 UUID、9,172/9,172 turn、517/517 QA、零失败；prediction 7,055 次
  API LLM call / 19,666,880 tokens（build=2,271,386、retrieval=16,095,419、answer=1,300,075），
  QA judge 517 次 / 641,807 tokens，update judge 481 次 / 612,497 tokens，全部为 SDK
  `api_usage`。结果：QA=0.5319148936、update=0.7027027027、F1=0.3084882500、normalized
  EM=0.0773694391、substring EM=0.1121856867；按既定资格不运行 extraction/memory-type，
  Recall/NDCG 继续 N/A。
- HaluMem paid evaluator 幂等门通过：无新增评测单元立即重跑约 4 秒完成、零新 API 调用；QA
  score/usage SHA-256 分别为 `3a75c562...7c9d` / `1591d4d4...8954`，update 分别为
  `29dde27b...ec5` / `0b20f2f5...69bf`，重跑前后逐字不变。

## 3. Token 验收口径

最终 API 计费表只纳入 `observation_type=llm_call` 且
`token_measurement_source=api_usage` 的 input/output token。SimpleMem 的 memory build、retrieval
planning/reflection、framework answer 与 paid judge 都必须满足；本地 embedding 的
`tokenizer_estimate` 单列，不混入 API token。任何成功 API LLM call 缺 SDK usage，则对应 run
收据标 incomplete，禁止用估算补齐。

## 4. 五格真实 API 总账

| benchmark | API LLM calls | prediction tokens | judge tokens | SDK `api_usage` tokens |
|---|---:|---:|---:|---:|
| MemBench 0-10K | 173 | 458,800 | 0 | 458,800 |
| LongMemEval-S | 64 | 719,772 | 1,510 | 721,282 |
| BEAM-100K | 730 | 1,373,514 | 224,506 | 1,598,020 |
| LoCoMo | 3,767 | 6,876,314 | 319,372 | 7,195,686 |
| HaluMem-Medium | 8,053 | 19,666,880 | 1,254,304 | 20,921,184 |
| **累计** | **12,787** | **29,095,280** | **1,799,692** | **30,894,972** |

累计 input=27,422,304、output=3,472,668。按 stage 汇总：memory build=4,225,892、
retrieval=22,835,702、answer=2,033,686、judge=1,799,692。12,787 条 API LLM observation
逐条均为 `api_usage`，非 API usage 条数为 0；本地 MiniLM embedding 的 tokenizer estimate 未计入
上述 API 总账。

## 5. 自适应样本停表

三个 paired isolation 的总 API token 区间如下（含适用 judge）：

| benchmark | min | median | max | max/min |
|---|---:|---:|---:|---:|
| LongMemEval-S | 217,007 | 242,639 | 261,636 | 1.21× |
| BEAM-100K | 483,529 | 520,199 | 594,292 | 1.23× |
| LoCoMo | 2,045,203 | 2,408,294 | 2,742,189 | 1.34× |
| HaluMem-Medium | 6,275,147 | 6,804,443 | 7,841,594 | 1.25× |

上述区间不会改变 SimpleMem 的成本等级判断，因此四格在 p25/p50/p75 三点停止首轮预算外推，
不再机械补 p10/p90。这个结论只表示“当前公开 shape 分层下，三点足以作首轮预算申请”，不冒充
总体置信区间或正式效果推断。

MemBench 20 个 isolation 的 API token 为 6,217–71,191（11.45×），且四条 source lane 的形状
不同；因此保留每 lane 五点，不把它压回三个混合样本。该差异也验证“分布不均匀时多跑一些”应
落实为分层增加样本，而不是无结构地随机加量。

## 6. 最终裁决

SimpleMem × Mimo 五格 calibration 已完成并冻结：全部 conversation/question 零失败，适用指标与
paid evaluator 已收口，token 总账只含真实 SDK usage。SimpleMem 的主要成本瓶颈是 retrieval
planning/reflection（22,835,702 / 30,894,972，约 73.9%），因此它虽然比 A-Mem 更适合作为后续
GPT-4o-mini 候选，仍应先用本收据按目标模型实价外推，再决定正式覆盖规模；不能把 Mimo 的分数、
速度或 token 数伪装成 GPT-4o-mini 实测。
