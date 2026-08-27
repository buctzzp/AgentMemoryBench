# API runtime profile 与 smoke provider

> 长期参考页。本文只记录 provider、model、transport、manifest/resume 和 secret
> 边界；method 算法参数仍归各自 TOML，benchmark answer/judge prompt 仍归统一
> builder/evaluator。

## 1. 当前裁决

自 2026-07-27 起，新运行按 profile 显式选择 API runtime：

| run profile | provider | model | answer transport | judge transport | 用途 |
| --- | --- | --- | --- | --- | --- |
| `smoke` | `opencodego` | `ox-alpha-free` | Chat Completions | Chat Completions | 极小裁剪的流通验证 |
| `pilot` | `opencodego` | `ox-alpha-free` | Chat Completions | Chat Completions | 一个完整 isolation 的调用拓扑与成本 observation |
| `calibration` | `opencodego` | `mimo-v2.5` | Chat Completions | Chat Completions | 显式完整 cohort 的预算与扩大稳定性实验 |
| `official_full` | `primary` | `gpt-4o-mini` | Chat Completions | Responses；官方 evaluator 自带 Chat 路径时保持其路径 | 主配置正式实验 |
| `author-locomo` | `apilio` | `gpt-4o-mini` | Chat Completions | Chat Completions | LightMem LoCoMo paper row 作者校准 |

这是**运行身份差异**，不是暗中 fallback。新 `smoke` 与旧
历史 `deepseek-v4-flash`/`muse-spark-1.2-contributor`/旧 `mimo-v2.5` smoke、旧 `gpt-4o-mini` smoke 与
`official_full` 的分数均不得
直接比较；smoke 只证明当前 method、
benchmark、artifact、resume 和 evaluator 链路在声明的 provider/model 上可运行。
非 LLM 的 embedding、检索深度、update、summary、storage 等 method 参数不因 provider
切换而改变。

`pilot` 是公开运行范围，不是第三套 method 算法参数：它复用各 method TOML 的
`[smoke]` section，但在 manifest 中独立盖 `run_scope=pilot`，输出也进入 `pilot/`
目录。它保留一个完整 isolation 及其全部问题，不允许再传 rounds/conversations/question
等裁剪参数；因此不能把 `smoke` 的裁剪 artifact 冒充完整成本样本，也不能为使用便宜模型
而把 `official_full` 强行映射到 OpenCodeGo。

## 2. 配置入口与 secret 边界

`.env` 只保存连接信息，当前 loader 接受：

```text
opencode_go_key       / OPENCODE_GO_KEY
opencode_base_url     / OPENCODE_BASE_URL
opencode_model_name   / OPENCODE_MODEL_NAME
opencode_model_name_2 / OPENCODE_MODEL_NAME_2
opencode_model_name_3 / OPENCODE_MODEL_NAME_3
opencode_model_name_4 / OPENCODE_MODEL_NAME_4
APILIO_API_KEY
APILIO_base_url       / APILIO_BASE_URL
APILIO_model_name     / APILIO_MODEL_NAME
```

小写键优先。当前新 smoke 使用第四槽 `opencode_model_name_4`，并必须逐字等于 tracked
identity `ox-alpha-free`；第一槽保留旧 `deepseek-v4-flash`，第二槽保留旧
`muse-spark-1.2-contributor`，第三槽保留旧 `mimo-v2.5` artifact 的 evaluate/readback。
四个槽都是可审计 identity，不是失败后自动轮询的 fallback 列表。
第三槽当前同时供新 `calibration` profile 精确选择 `mimo-v2.5`；它仍可回读同模型的旧 artifact，
但 run scope/profile/manifest 不同，不会因此混成同一实验。
任何 key 值与 base URL 都不得写入 TOML、manifest、artifact、note 或测试 stdout。
tracked TOML 只声明公开模型身份。prediction 在 secret load 前用 tracked identity 预检，
evaluate 则按旧 run manifest 的模型在已配置 slot 中精确匹配；找不到就 fail-fast，不能用
当前默认模型改写历史。

`author-locomo` 使用独立 APILIO 槽；model 必须逐字等于 `gpt-4o-mini`。它不是 primary
失败后的 fallback，也不会被其他 author profile 自动继承。key/base URL 仍只在 secret load
阶段读取，manifest 只写 `provider=apilio`、model 与 Chat transport identity。

## 3. Transport 兼容性

2026-07-27 对当前 opencodego endpoint 做过最小真调用：

- Chat Completions 普通文本：通过；
- 与框架通用 judge 相同的 `temperature=0` 形状：通过；
- LoCoMo judge 使用的 `response_format={"type": "json_object"}`：通过；
- Responses API：HTTP 400，upstream request failed。

因此 `opencodego` runtime 的 judge transport 固定为 `chat_completions`。框架通用
`LLMJudgeEvaluator` 会把字符串 prompt 映射成单条 user message，把已有 role-tagged
message list 原样复制；不会先尝试 Responses 再隐藏回落。`primary` runtime 的通用
judge 继续走 Responses，LoCoMo/LongMemEval 等已有官方 Chat Completions 调用形状不改。

2026-08-21 对两个候选模型又用当前生产形状做了极小真调用：Chat Completions、
`temperature=0`、JSON mode 与 `thinking={"type":"disabled"}` 同时启用。Muse 虽 HTTP 成功，
但返回 `content=""`、`finish_reason=None`，判为语义不可用；Mimo 返回
`{"ok": true}`、`finish_reason=stop`，usage 为 263 prompt / 6 completion tokens。由此新
smoke 默认从 Muse 迁到 Mimo。框架不会在某个 run 请求失败后静默换模型：迁移发生在 run
创建前，旧 Muse run 仍只能按原 manifest 回读或用新 run_id 重跑。

2026-08-26 用户为完整 isolation 预算实验重新选择 `mimo-v2.5`。该选择进入独立
`calibration` profile；OpenCodeGo transport 显式发送
`thinking={"type":"disabled"}`，manifest 写 `thinking_mode="disabled"`。method 算法参数继续
读取单一 `[method]`，answer role/temperature/max_tokens/top_p 继续按 benchmark 统一 resolver；
只有既有的 OpenCodeGo×LoCoMo 4096 completion 安全阀继续作为公开 provider compatibility 生效。
`predict formal --profile calibration` 使用 FULL run scope、完整问题集、显式 isolation cohort 与
严格 resume identity；不是旧 `predict pilot` 固定首 isolation 的别名。

同日稍后，用户新增第四槽限时免费 `ox-alpha-free` 并恢复 ws05。实测该模型始终启用
reasoning：`thinking={"type":"disabled"}` 与把 low 写进 thinking body 都返回 HTTP 400；
顶层 `reasoning_effort="low"` 才是兼容请求。普通文本、JSON object judge 与
LongMemEval 短 yes/no 三种生产形状均 HTTP 200，成功响应都含 prompt/completion/total
usage；并发阶梯 4 与 8 均全成功。服务未返回 rate-limit header，因此该结果只证明当前
安全下界 ≥8，不证明最大并发。首批 pilot 仍以全局 API semaphore=4 启动，避免把一次探针
当成容量承诺。一次双并发响应未严格服从“精确回显”文本，故 ox 只用于工程流通、调用拓扑
和 observation，不能据此与正式模型比较效果分数。

两类 method 专属 transport 差异也已用真实调用闭合：

- ox 会接受 A-Mem 发出的 `response_format.type=json_schema`，但不遵守其中 schema；A-Mem
  仅在 ox 的真正发送边界把它降为已验证的 `json_object`，prompt 与产品解析逻辑不改；
- SimpleMem 的官方调用是 streaming。共享 transport 给 streaming 请求加入
  `stream_options.include_usage=true`，等调用方完整消费 stream 后读取最终 usage chunk；
  真实 run 的 memory-build/retrieval observation 因而使用 `api_usage`。只有没有 raw SDK
  response 的 fake/兼容 client 才允许退回 tokenizer estimate。

历史 `deepseek-v4-flash` 在未成功关闭 thinking 时，reasoning token 与可见回答共享
completion budget。2026-08-11 用生产代码实际发送的
`thinking={"type":"disabled"}` 分别以 `max_tokens=32/256` 做最小真调用，二者均返回
`finish_reason=stop`、可见 `pong`、`completion_tokens=2`，且 usage 中没有 reasoning
tokens；这与临时调查中测试的 `enable_thinking=false` 不是同一种请求形状，不能混为
一谈。

即便当前生产 override 有效，LoCoMo 官方的 32-token 小上限仍会把 smoke 绑定在一个
脆弱的 provider 行为上。用户裁定后，框架对 **OpenCodeGo + LoCoMo** 把未设置或低于
4096 的 answer 上限改成显式 4096；prompt、temperature、top-p 与 primary 正式轨均不改。
4096 是几乎不触发的可复现安全阀，不是 API 默认的无限预算。answer manifest 写：

```text
provider_compatibility = "opencodego_locomo_explicit_completion_cap_4096_v3"
```

该兼容层按 provider + benchmark 判定，不靠 `smoke` 字符串猜运行身份；当前
`official_full` 固定使用 primary，因此继续保留 LoCoMo 官方 `max_tokens=32`。其他
benchmark、primary provider，以及已经显式高于 4096 的配置均保持原值。

## 4. Manifest 与 resume

新 prediction 在 `method.answer_reader.api_runtime` 写入：

```json
{
  "contract_version": "v2",
  "provider": "opencodego",
  "model": "ox-alpha-free",
  "answer_transport": "chat_completions",
  "judge_transport": "chat_completions",
  "thinking_mode": "reasoning_effort_low"
}
```

该对象不含 key/base URL，参与 method manifest 与 resume identity：

1. prediction 在所有 child path/manifest preflight 完成后才读 `.env`；
2. 读出的 provider/model/transport 必须与预检身份逐字段相同；
3. API evaluator 继承 prediction run 的 runtime identity，不用当前默认模型重写旧 run；
4. 离线 evaluator 不解析、不加载 API 配置，已有 artifact 仍可免费重算；
5. 完全没有 `api_runtime` 的历史 manifest 保持旧 primary 懒加载语义，不改写历史身份。

## 5. 修改模型时的正确路径

若以后更换 smoke provider/model，必须同批修改并验收：

1. tracked runtime 常量与各 method `[smoke]` 的公开模型字段；
2. provider transport 能力探针；
3. prediction manifest/resume 强反例；
4. evaluate 对 run identity 的继承与环境漂移反例；
5. 本页与 `AGENTS.md`。

2026-08-21 的 Muse→Mimo→ox 迁移继续保留三代旧模型 slot，目的不是让同一 run 动态换模型，
而是保证旧 artifact 可回读、新 run 身份唯一。模型拒绝可选参数、返回空 choice 或区域错误时
必须先停工裁定，不能隐藏 fallback。

## 6. 成本 pilot 的模型转移边界

ws05 可以用 ox 跑较大但受控的成本 pilot，观测调用次数、input/output token、latency
与 method 产生的记忆规模；再用 `gpt-4o-mini` 价格对**同一份 token 账**计算一个
`token-price projection`。这个数不是正式 GPT 成本真值：构建记忆的 LLM 输出会改变后续记忆
数量、检索上下文和调用拓扑。正式预算报告必须同时披露模型转移假设，并至少跑一个极小
`gpt-4o-mini` calibration cell 校验调用拓扑/倍率；不得只用“免费模型 token × 目标单价”冒充正式成本真值。

只改 `.env` 然后复用旧 run_id 属身份污染，框架应拒绝。

当前 `predict pilot` 的完整 isolation 口径固定为：LoCoMo 第一条完整 conversation；
LongMemEval 第一条完整 instance；BEAM 第一条完整 conversation；HaluMem 第一条完整 UUID；
MemBench 在**同一个 run/process** 中从四条默认 source lane 各取第一条完整 tid。MemBench
没有为了追求“一 tid 一进程”制造四份低收益物理进程；conversation namespace 与 state 仍按
每个 tid 隔离。矩阵运行受全局 API 并发上限 4 约束，重型本地 runtime 可进一步串行，不能把
“端点 8/8 HTTP 成功”误读成应同时启动 50 格。

## 7. 统一 LLM transport 的长期边界

后续可继续把无状态、跨 method 重复的能力收敛到公共 transport：provider/model identity、
request override、timeout/retry policy、usage extraction、secret redaction、错误分类与效率
observation。公共层不得改写 method prompt、消息顺序、JSON 解析或产品算法。

“统一调用工具”也不等于一个跨 run 的全局 client singleton。持有 conversation state、内部
retry、stream 生命周期、scheduler、连接池或产品 callback 的 client/LLM wrapper 仍由各 method
runtime 按进程和 isolation 管理；它们只复用同一套无状态 transport policy。这样既减少十家
重复接线，也不会把 namespace、失败域或实验身份意外耦合在一起。
