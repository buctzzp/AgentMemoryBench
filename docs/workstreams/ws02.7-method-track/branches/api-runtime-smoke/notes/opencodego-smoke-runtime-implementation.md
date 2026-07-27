# opencodego smoke runtime 实施记录

日期：2026-07-27
执行：GPT-5.6 sol（架构师直接施工）

## 1. 用户裁决

新 smoke 使用 `.env` 中的 opencodego 配置；正式 `official_full` 仍保留 primary
`gpt-4o-mini`。两种 runtime 的结果不能当作同模型效果对比。

## 2. 实现

- `OpenAISettings` 增加稳定 `provider` 与 `judge_transport`；
- `smoke → opencodego/deepseek-v4-flash`，`official_full/author_* →
  primary/gpt-4o-mini`；
- 六个已接入 method 的 `[smoke]` 显式声明新 LLM 模型，非 LLM 参数不变；
- prediction manifest 写 `api_runtime v1`，resume 对 provider/model/transport 任一变化
  fail-fast；
- `.env` 在全部 child preflight 后才读取，读出的运行身份必须与 manifest 一致；
- API evaluator 继承 prediction run 身份；离线 evaluator 不读取 API 配置；
- opencodego 通用 judge 走 Chat Completions，不尝试 Responses 后静默回落；
- reasoning 模型遇官方 answer/judge `max_tokens < 128` 时仅在 smoke 抬到 128，并在
  manifest 披露兼容身份。

secret 与 base URL 均未写入 tracked config、manifest 测试 fixture或下述输出。

## 3. 最小真调用证据

当前 endpoint：

```text
Chat Completions plain text                PASS
Chat Completions temperature=0 judge shape PASS
Chat Completions json_object mode          PASS
Responses API                              HTTP 400 upstream request failed
```

JSON mode 最小探针的安全输出：

```text
provider=opencodego
model=deepseek-v4-flash
transport=chat_completions
json_mode=true
visible_content_nonempty=true
prompt_tokens=117
completion_tokens=43
```

这只验证 API transport，不是 MemOS/B11 smoke，不启动 Neo4j/Qdrant，不生成 benchmark
结果。

## 4. 强反例

- provider 与 judge transport 互相矛盾：构造期拒绝；
- `.env` model 与 prediction manifest 不同：evaluate 在 evaluator 构造前拒绝；
- API runtime 任一 nested 字段变化：resume 双向 mismatch；
- 离线 metric 即使面对新 manifest 也不得加载 API settings；
- child destination/path preflight 继续早于 secret load 与 model consistency check。

## 5. 验证

定向集合：

```text
382 passed in 20.96s
```

完整无 API 回归：

```text
1879 passed, 3 deselected, 11 warnings, 29 subtests passed in 132.87s
compileall exit 0
git diff --check exit 0
```

warning 画像与 MemOS M4 基线相同：vendored LightMem Pydantic deprecation、MemOS
`datetime.utcnow()` deprecation 与 MemOS config Pydantic serialization warning；无新增
warning 类别。最终 commit 快照由父 ws02.7 README 记录。
