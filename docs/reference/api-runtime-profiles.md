# API runtime profile 与 smoke provider

> 长期参考页。本文只记录 provider、model、transport、manifest/resume 和 secret
> 边界；method 算法参数仍归各自 TOML，benchmark answer/judge prompt 仍归统一
> builder/evaluator。

## 1. 当前裁决

自 2026-07-27 起，新运行按 profile 显式选择 API runtime：

| run profile | provider | model | answer transport | judge transport | 用途 |
| --- | --- | --- | --- | --- | --- |
| `smoke` | `opencodego` | `deepseek-v4-flash` | Chat Completions | Chat Completions | 低预算流通与接口验证 |
| `official_full` | `primary` | `gpt-4o-mini` | Chat Completions | Responses；官方 evaluator 自带 Chat 路径时保持其路径 | 主配置正式实验 |

这是**运行身份差异**，不是暗中 fallback。新 `smoke` 与旧
`gpt-4o-mini` smoke、`official_full` 的分数不得直接比较；它只证明当前 method、
benchmark、artifact、resume 和 evaluator 链路在声明的 provider/model 上可运行。
非 LLM 的 embedding、检索深度、update、summary、storage 等 method 参数不因 provider
切换而改变。

## 2. 配置入口与 secret 边界

`.env` 只保存连接信息，当前 loader 接受：

```text
opencode_go_key       / OPENCODE_GO_KEY
opencode_base_url     / OPENCODE_BASE_URL
opencode_model_name   / OPENCODE_MODEL_NAME
```

小写键优先。任何 key 值与 base URL 都不得写入 TOML、manifest、artifact、note 或测试
stdout。tracked TOML 只声明公开模型身份；当前六个已接入 method 的 `[smoke]` section
显式锁定 `deepseek-v4-flash`。若 `.env` model 与 tracked profile/manifest 不一致，
prediction/evaluate 必须在真实调用前 fail-fast，不能静默覆盖。

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

`deepseek-v4-flash` 在未成功关闭 thinking 时，reasoning token 与可见回答共享
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
  "contract_version": "v1",
  "provider": "opencodego",
  "model": "deepseek-v4-flash",
  "answer_transport": "chat_completions",
  "judge_transport": "chat_completions"
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

只改 `.env` 然后复用旧 run_id 属身份污染，框架应拒绝。
