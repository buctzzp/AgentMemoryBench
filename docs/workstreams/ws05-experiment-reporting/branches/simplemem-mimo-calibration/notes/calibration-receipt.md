# SimpleMem × Mimo calibration 实验收据

日期：2026-08-27

状态：`PREDICTION_IN_PROGRESS`

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

## 3. Token 验收口径

最终 API 计费表只纳入 `observation_type=llm_call` 且
`token_measurement_source=api_usage` 的 input/output token。SimpleMem 的 memory build、retrieval
planning/reflection、framework answer 与 paid judge 都必须满足；本地 embedding 的
`tokenizer_estimate` 单列，不混入 API token。任何成功 API LLM call 缺 SDK usage，则对应 run
收据标 incomplete，禁止用估算补齐。

## 4. 当前断点

五格 prediction 已启动，HaluMem 为关键路径。完成顺序不影响 paired cohort 或 run identity；每格
完成即先验 conversation/question/failure、manifest、stage、SDK usage，再执行适用 evaluator。
HaluMem extraction/memory-type 继续缺席；Recall/NDCG 对 synthesized entry 继续 N/A。
