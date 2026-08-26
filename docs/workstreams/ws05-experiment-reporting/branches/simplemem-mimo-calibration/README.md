# SimpleMem × Mimo calibration 实验支线

状态：`in-progress`

父任务：[ws05 experiment reporting](../../README.md)

## 目标与边界

本支线在 LightMem 收口后，使用同一份公开 shape paired cohort 验证 SimpleMem 五格
`calibration`、形成真实 API token 与 runtime 收据，并执行适用 evaluator。它不升级
SimpleMem source、不改算法参数，也不为了补齐 Recall/NDCG 伪造 synthesized entry 的 source
membership。

## 锁定身份与样本门

- method：`simplemem`
- API runtime：`opencodego/mimo-v2.5`，thinking disabled
- profile：`calibration`
- execution identity：`workers=10`
- cohort：逐字复用
  [LightMem cohort](../lightmem-mimo-calibration/notes/cohort.md) 的全部 ordered IDs；四个普通
  benchmark 首轮推进 p25/p50/p75，MemBench 直接复用已验证异质的四 lane 五点。
- 调度：先启动 HaluMem-Medium，再在资源门允许时填充其他四格；关键路径优先只缩短 makespan，
  不改变 isolation 内顺序、method 参数或 artifact 身份。

LoCoMo、LongMemEval-S、BEAM-100K、HaluMem-Medium 首轮各运行 3 个完整 isolation；MemBench
0-10K 运行 20 个。MemBench 的 p10/p25/p50/p75/p90 是 paired benchmark strata，不因 method
变化缩水；其他四格只有同 method 内的 SDK token 或 runtime 敏感性足以改变预算结论，才追加
p10/p90。

## Token 完整性硬门

SimpleMem 的 memory build、retrieval planning/reflection、framework answer 和 paid judge 都属于
API LLM 调用。计费收据只接受 OpenAI-compatible SDK response 的 `usage`，每条 observation 必须
标为 `api_usage`；任何成功 API LLM 调用退回 `tokenizer_estimate`，该 run 立即标为 token receipt
incomplete，不能拿估算值补账。受控本地 MiniLM embedding 的 tokenizer estimate 只单列为本地
工作量。

开跑前先用当前 Mimo streaming transport 做一次最小真实 usage 探针，证明
`stream_options.include_usage=true` 的尾块能穿过 SimpleMem 产品 client 与 observer；探针通过后
才启动完整 HaluMem isolation。

## Metric 边界

- 五格离线答案指标与 benchmark 官方/统一 judge：按现有 eligibility 执行。
- SimpleMem synthesized entry 不保留 exact source membership：Recall/NDCG 继续 N/A。
- HaluMem 本批只评 QA、update 与离线答案指标；按用户当前裁决不运行 extraction/memory-type。
- retrieval planning/reflection 的 API 调用必须记在 `retrieval` stage，不得并入 memory build。

## 当前动作

- [x] LightMem 第二/条件第三批最终收据已闭合。
- [ ] 运行 SimpleMem × Mimo streaming exact-usage 最小探针。
- [ ] 确认五个新 run id 不存在并完成 manifest/配置零 API 门。
- [ ] HaluMem 优先启动，其余四格在资源门下推进。
- [ ] 完成适用 evaluator、SDK usage/failed-attempt/幂等门与预算敏感性判断。
- [ ] 写最终实验收据并同步父 README。
