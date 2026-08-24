# M2：模型调用观测与失败尝试成本账

日期：2026-08-24
状态：`ACCEPTED_BY_M5_NO_API_REGRESSION`
边界：零真实 API；不改算法状态提交语义，不回写旧 artifact。

## 1. 本批关闭的缺口

| 缺口 | current 处置 |
| --- | --- |
| SimpleMem operation-level update probe 中 retrieval 内部模型调用被归为 build | runner 在 probe 外显式进入 `EfficiencyStage.RETRIEVAL`；普通 build/retrieve 路径保持不变 |
| MemoryOS 本地 SentenceTransformer 完全无 observation | 在 vendored `get_embedding()` 成功出口安装纯观测 hook；build/retrieval 均记录 tokenizer estimate、framework timer 与真实 stage |
| LangMem retrieve 一旦未来触发 LLM 会绕过 callback | retrieve config 与 build 使用同一 usage callback；零调用仍为零，意外调用会进入 retrieval stage |
| Letta collector buffer 未激活时静默丢 usage | 改为 fail-loud；worker command 失败时把已完成 usage 经结构化错误详情交回 adapter |
| Mem0 内置 reranker 未来启用会绕过当前观测 | current `rerank=false` 进入强类型配置与 manifest；启用在 client/API 前 fail-fast，补齐 reranker 观测前不得运行 |

MemoryOS 对 `third_party/methods/MemoryOS-main/memoryos-pypi/utils.py` 的改动只包裹
SentenceTransformer `encode()` 的成功出口，不改变输入、输出、batch、normalization 或异常传播；源码
位置和 observer identity 已进入 method instrumentation manifest。

## 2. append-only failed-attempt ledger

prediction 与 evaluator 各自拥有独立 JSONL：

- `artifacts/efficiency_attempts.prediction.jsonl`
- `artifacts/efficiency_attempts.<metric>.jsonl`

一次 runner scope 捕获异常时，collector 把异常发生前已经完成且已拿到 usage/latency 的 LLM/
embedding observations 写入账本，再让原异常继续传播。正常 observation 仍只在 scope 成功退出时合并；
因此算法 artifact/state 可以回滚，已经发生的成本事实不会随之消失。每次 retry 使用新的
`collector_session_id + attempt_index`，即使内部 call observation id 相同也不会合并。

账本不保存异常正文、endpoint、credential 或产品 payload，只保存异常类型名与公开 scope id。
worker 隔离方法通过 `WorkerCommandError.error_details` 回放已完成 observation；LangMem、Letta、
EverOS、Graphiti 与 MemOS 已覆盖。EverOS 若失败详情含当前契约不支持的真实 rerank 调用，会
fail-loud，绝不静默丢账。

## 3. 完整度边界

本账只陈述 `caught_scope_exception_completed_model_calls_only`：

- 已返回 usage 的成功调用可精确记账；
- 本地 embedding 已完成调用可记录 tokenizer estimate + timer；
- 网络请求在返回 usage 前失败、进程被 SIGKILL、机器断电或第三方 SDK 在进程外吞掉数据时，
  framework 无法凭空得知 token/cost；账本不得宣称覆盖这些负空间。

LLM 的 token 事实按每次调用保存；wall-clock 仍以 conversation build、question retrieval/answer 与
evaluator unit scope 的 framework timer 为主。只有产品公开 seam 已提供逐调用 timer 时才保存更细
粒度，不为“字段整齐”给所有第三方调用增加侵入式双重计时。该口径满足成本外推与阶段瓶颈分析，
也避免把同一延迟同时算成 call latency 和 stage latency 后误加总。

## 4. 身份与兼容

新 method manifest 的 efficiency observability 增加
`failed_attempt_ledger_contract=append-only-caught-scope-completed-calls-v1`。旧 manifest 缺该字段时
与新 run 严格 resume mismatch；旧 observation 文件仍按原 schema 只读，不做就地升级。

## 5. 零 API 验证

- collector/storage：`31 passed`
- worker transport + 五家隔离 worker + adapters + prediction/operation runners：`489 passed`
- manifest/runner/evaluator 回归：`270 passed` 与 evaluator 定向 `77 passed`

M5 已把本批与 M1/M3 合在同一无 API 总门复跑；最终全仓结果与重建矩阵见
[`2026-08-24-m5-no-api-acceptance.md`](2026-08-24-m5-no-api-acceptance.md)。
