# Mimo-v2.5 与 GPT-4o-mini synthetic token probe

日期：2026-08-27

状态：`SYNTHETIC_SCALAR_CONVERSION_REJECTED`

真实 API：OpenCodeGo `mimo-v2.5` 5 次 + APILIO `gpt-4o-mini` 5 次；每端点
`max_retries=0`。第一次尝试在本地 client 构造阶段因重复 `timeout` 参数失败，零 HTTP 调用；
修正后才执行以下 10 次请求。

## 1. 问题

LightMem 的 Mimo calibration 已有真实 SDK usage；用户原计划用 GPT-4o-mini 重跑同一组三个
LoCoMo isolation，再求 token 换算比例。由于完整 isolation 成本较高，本探针先用五组 paired
synthetic payload 检验“是否存在近似稳定的单一换算倍率”。若该更弱的必要条件已经失败，就不能
把完整实验总 token 乘一个常数冒充目标模型预算。

这不是 LightMem、LoCoMo 或正式结果；不进入 QA 分数、method 排名或 calibration cohort。

## 2. 固定调用条件

- 两端使用完全相同的 messages、temperature 与 max tokens；
- Mimo 沿 current calibration transport 发送 `thinking.type=disabled`；实测 reasoning tokens=0；
- APILIO 实际返回 `gpt-4o-mini-2024-07-18`；
- token 只认 SDK response usage；
- 三组 control 强制短输出，用于观察 input/chat-template 计数；一组 JSON memory extraction 与一组
  LoCoMo-style short answer 用于观察自然生成差异。

## 3. 原始收据

| sample | Mimo prompt/out/total | GPT prompt/out/total | GPT/Mimo prompt | GPT/Mimo out | GPT/Mimo total | 输出相同 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| short control | 254 / 2 / 256 | 12 / 3 / 15 | 0.047 | 1.500 | 0.059 | 否（2 vs 3 chars） |
| long English control | 3,223 / 2 / 3,225 | 2,532 / 2 / 2,534 | 0.786 | 1.000 | 0.786 | 是 |
| long Chinese control | 3,110 / 2 / 3,112 | 2,711 / 2 / 2,713 | 0.872 | 1.000 | 0.872 | 是 |
| memory extraction JSON | 1,403 / 91 / 1,494 | 1,401 / 214 / 1,615 | 0.999 | 2.352 | 1.081 | 否 |
| LoCoMo-style short answer | 1,554 / 2 / 1,556 | 1,272 / 2 / 1,274 | 0.819 | 1.000 | 0.819 | 是 |
| **任意样本合计** | **9,544 / 99 / 9,643** | **7,928 / 223 / 8,151** | **0.831** | **2.253** | **0.845** | 不适用 |

延迟只作当前两个 gateway 的诊断，不作模型速度结论：Mimo 五次约 29.20s，APILIO GPT 五次约
11.55s。provider、区域与负载不同，不能从该值外推正式 runtime。

## 4. 裁决

单一总 token 倍率被拒绝，原因不是统计噪声，而是机制性分叉：

1. **prompt 长度/语言依赖**：GPT/Mimo prompt ratio 从长英文 0.786、中文 0.872 到 extraction
   0.999；不同 tokenizer/chat template 不形成统一斜率；
2. **短请求固定开销**：同一 22-char prompt，Mimo usage=254、GPT=12，说明 Mimo endpoint 的
   计费 prompt 含明显固定模板/服务端开销；短调用占比高的方法会被强烈放大；
3. **生成内容反向改变 output 与后续 input**：同一 extraction prompt，GPT completion=214、
   Mimo=91。真实 memory method 又会把生成记忆送入后续检索/更新，因此差异会级联；
4. **合计 0.845 没有 estimand**：它只由本次任意五个 synthetic sample 的权重产生，改变样本配比
   就会改变，禁止拿它乘 8,620,622 或 30,894,972。

## 5. 后续边界

- 若只需要粗预算，可以继续报告 Mimo 的真实 SDK usage，并把 GPT 成本列为“未实测，无法用单
  scalar 转换”；
- 若确实需要 LightMem × LoCoMo 的 GPT 预算，下一步应先只跑 paired p50 `conv-50`，分别报告
  memory build / answer / judge 的调用数、input/output 与总 token；只有该真实 workload 有价值；
- 另外两个 p25/p75 isolation 仅在 p50 的 stage ratio 足以影响预算决策、且用户再次批准时追加；
- 即便三个 LoCoMo isolation 都完成，结论仍只适用于 LightMem × LoCoMo，不跨 benchmark/method
  传播。
