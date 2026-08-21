# ws04 M1 heartbeat 与第三方输出治理记录

日期：2026-08-21
状态：架构师验收通过

## 1. 范围与不变量

本批只改运行观测，不改 benchmark 输入、method payload、检索、answer/judge prompt、metric
或 artifact 业务语义。全程零真实 API，未写 `outputs/`、`data/`、`models/` 或
`third_party/`。

同时按用户裁决把新 smoke runtime 从 OpenCodeGo 第一槽的历史
`deepseek-v4-flash` 切到第二槽 `muse-spark-1.2-contributor`。旧 artifact 的 model/provider/
transport 仍按 manifest 精确回读，不能被新默认覆盖；正式 `official_full` 继续
`primary/gpt-4o-mini`。

## 2. isolated heartbeat

实现位于：

- `src/memory_benchmark/runners/prediction_parallel.py`
- `src/memory_benchmark/observability/progress_reporter.py`

worker 只向进程内 queue 发送不可变公开事件；coordinator 独占 Rich、`progress.json` 与
`events.jsonl`。阶段固定为 `starting / ingesting / answering / completed / failed /
cancelled`，载荷只含 worker index、公开 conversation/question id 和 turn/question 计数。
阻塞于 method 调用时，每 0.5 秒只刷新内存快照的 phase elapsed；不增加业务完成数，也不
为刷新重复写 heartbeat event。

这不是 tracing 系统：没有 prompt、answer、gold、method payload、secret 或 traceback。
真实失败详情继续走既有 `conversation_failed_isolated` 事件。

## 3. method.log 输出治理

### 3.1 标准 logging

`method_log_scope` 继续拥有 run-scoped root handler。新增 active-handler 登记与
`ensure_method_log_handler()`：isolated factory 若重配 root logger，worker 构造完成后只会
恢复当前 active run 的同一 handler；作用域外不会猜路径或新建 handler，退出仍摘除并关闭。

### 3.2 in-process print/tqdm

LightMem、A-Mem、MemoryOS 已有的窄第三方调用边界改用共用
`capture_method_output()`：stdout/stderr 始终先捕获、按当前 API key/base URL 精确脱敏后
追加到 `logs/method.log`；`suppress_official_stdout=false` 只把捕获文本镜像回进入作用域前的
terminal stream，不改变是否落盘。禁止在整个并行 run 外层重定向 `sys.stdout/stderr`。

### 3.3 JSON-lines subprocess

Letta、LangMem、EverOS、Graphiti 的共用 `JsonLinesWorkerTransport` 通过显式
`diagnostic_log_path` 依赖，把调用方 redactor 处理后的 stderr 全量追加到同一
`method.log`；有限 deque tail 仍只服务失败摘要。stdout 继续专属于 JSON-lines 协议，未加入
任何诊断镜像。

`diagnostic_log_path` 从 run composition root 经 `MethodBuildContext` 注入，不进入 TOML、
manifest、resume identity 或 method 算法配置。isolated worker 只改变 storage root，沿用同一
run 日志路径；共享写锁保证 logging 与直接 writer 不把两条记录拼成一行。

## 4. 强反例

- 四 worker 交错：每个 worker 均出现阶段事件，最终 active count 为 0；全局完成数只在 batch
  提交后增加。
- 长阻塞：elapsed 增长，但真实 heartbeat event 数不增长。
- 非法 phase、负数/越界计数和空白公开 id 在入 queue 前 fail-fast。
- factory 摘除并 close handler 后可恢复；scope 结束后不能复活。
- in-process stdout/stderr 在成功与异常路径均落盘，secret/base URL 不出现；显示开关只影响
  terminal mirror。
- subprocess stderr 的完整五行落盘，tail 只留两行；stdout request/response 字节与序号测试
  保持通过。
- 无诊断路径时 helper no-op，不创建猜测文件。

## 5. 模型切换与成本投影边界

`load_openai_settings()` 默认从 `opencode_model_name_2` 选择 Muse；evaluate 按 manifest model
可从第一、第二或可选第三槽精确匹配。新 run 的十家 smoke TOML 和 answer reader identity
均改为 Muse。只读取 `.env` 的公开 provider/model 自检结果为：

```text
{'provider': 'opencodego', 'model': 'muse-spark-1.2-contributor', 'judge_transport': 'chat_completions'}
```

该自检没有发 HTTP。Muse 的真实 Chat/JSON 可选参数兼容性仍须在下一次用户批准的极小 smoke
中由真实调用证明，不能继承 DeepSeek 的模型级结论。

未来成本 pilot 可以用 Muse 观测调用量、token、latency 与记忆规模，并按 GPT-4o-mini 单价对
同一 token 账做 `token-price projection`；这不是 GPT 真值，因为模型输出会反过来改变记忆数、
上下文和调用拓扑。正式预算必须披露模型转移假设，并补一个极小 GPT 校准 cell。

## 6. 已知边界与停手线

- 当前 top-level CLI 一次只执行一个 run；run 内各 worker 共享同一 method.log 是设计行为。
  不支持在同一 Python 进程里并发启动两个 top-level run 并依赖 root logger 做严格隔离；若未来
  增加 multi-run coordinator，应改成 run-local logger dependency，而不是继续叠 root handler。
- in-process `redirect_stdout/stderr` 是第三方 adapter 既有窄边界；本批没有把它扩大到整个 run。
  若未来要让多个 in-process method 调用在同一进程真正并发且逐字隔离任意 `print()`，应采用
  子进程隔离，不能再造一个全局 stream singleton。
- heartbeat/output/cosmetic 三门关闭后停止，不扩成分布式 tracing，也不在 ws04 顺手拆 runner。

## 7. 验证

- output/heartbeat 定向与受影响 adapter/runner 回归：先后通过 `184 passed`、
  `656 passed`、`390 passed` 等窄门；新增输出路由专测 `107 passed`。
- 文档、hook、架构边界门：`21 passed in 3.06s`。
- `python -m compileall -q src/memory_benchmark tests`：exit 0。
- 最终无 API 全量：

```text
2243 passed, 3 deselected, 25 warnings, 29 subtests passed in 229.16s (0:03:49)
```

第一次全量的两个失败只因 `_FakeMemoryOS` 未镜像新增的显式
`diagnostic_log_path` factory 参数；生产路径没有失败。测试替身补成显式参数后，定向门与第二次
全量均通过。warning 画像仍是既有 LightMem Pydantic、legacy CLI FutureWarning 与 MemOS
datetime/Pydantic serialization，不含新增 unraisable/thread warning。
