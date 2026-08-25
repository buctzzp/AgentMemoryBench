# M4 零 API 资源画像与隔离裁决

日期：2026-08-24
状态：`ACCEPTED_BY_M5_NO_API_REGRESSION`；其中 Letta/MemOS 的 W1 临时裁决已由
[2026-08-25 isolation 并行门](../../../notes/2026-08-25-pre-experiment-parallelism-gate.md)
取代，下面保留当时证据，不再作为 current worker 能力口径。

## 1. 问题与边界

本批回答两个窄问题：当前进程模型是否真的会重复 materialize；已有隔离契约是否允许为了省
内存直接改成全局 singleton。它不是效果 pilot，也不是 product runtime 吞吐基准。

探针全程零 API，只执行：

1. production benchmark registration 的 `prepare(..., RunScope.PILOT)`；
2. 本地 `models/all-MiniLM-L6-v2` 的真实 `SentenceTransformer` 构造；
3. 一条文本的真实 `encode()`；
4. 每个 child 在自身进程内读取 `psutil` memory snapshot，再等待 parent 统一释放。

没有构造 method product、DB、HTTP client、scheduler 或 answer/judge LLM。因此 DB/HTTP connection、
queue depth 与端到端 product throughput 在本批均为 **N/A/not measured**，不能由下面的 loader/model
耗时外推。资源探针是一次性命令，没有为一次画像向生产仓新增 profiler 框架。

## 2. 机器结果

共同条件：macOS、CPU、本地 offline 模型、每个 child 一个真实模型实例。LoCoMo 与
LongMemEval 都只取一个完整 isolation；后者使用 `s_cleaned`。PSS 在该 macOS/psutil 运行时没有
暴露，记 `N/A`；USS 可由 child 自测取得。RSS/USS 是瞬时值，不等于磁盘模型目录大小。

| 场景 | child | dataset materialization | MiniLM 实例 | RSS 合计 | USS 合计 | PSS |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| 单 LoCoMo run | 1 | 1 次；1 conv / 19 session / 419 turn / 152 question | 1 | 524.86 MiB | 388.95 MiB | N/A |
| 同 LoCoMo 双 run | 2 | 每 child 各 1 次，同一 isolation 被独立 decode 两次 | 2 | 954.86 MiB | 679.25 MiB | N/A |
| LoCoMo + LongMemEval 双 run | 2 | 各 1 次；LME 为 1 conv / 53 session / 550 turn / 1 question | 2 | 1026.49 MiB | 754.71 MiB | N/A |

阶段明细：

| 场景/child | prepare | model load | one-text encode | encode 后 RSS / USS |
| --- | ---: | ---: | ---: | ---: |
| 单 LoCoMo | 0.0239s | 0.1328s | 0.1147s | 524.86 / 388.95 MiB |
| LoCoMo 双 run #1 | 0.0173s | 0.1140s | 0.0310s | 473.31 / 337.41 MiB |
| LoCoMo 双 run #2 | 0.0179s | 0.1125s | 0.0325s | 481.55 / 341.84 MiB |
| 跨 benchmark LoCoMo | 0.0177s | 0.1067s | 0.0184s | 514.27 / 378.38 MiB |
| 跨 benchmark LongMemEval | 0.1672s | 0.0998s | 0.0133s | 512.22 / 376.33 MiB |

三点可直接从结果成立：

- 当前独立 run 确实各建一个 Python model 对象；统一模型身份不等于自动共享实例。
- 同一 benchmark 的 Python dataset 对象也会按 run 独立 materialize。OS 文件页缓存可能复用底层
  文件页，但这不等于 Python object、iterator 或 private gold view 被安全共享。
- 两个 child 的 RSS/USS 明显增加，资源 admission 是正式 5×10 并发前的真实问题；一次 one-text
  encode 的耗时不代表 method ingestion throughput。

## 3. 当前隔离分类

| method | 当前业务状态隔离 | 本批裁决 |
| --- | --- | --- |
| Mem0 | worker 内 product-native `run_id`；worker 间物理 backend | 保持混合隔离；可共享连接/模型仍需单独证明 |
| Letta | product-native subject/agent/core blocks；run-owned PostgreSQL lifecycle | 历史 W1；现已改为每 worker 独立 PostgreSQL/runtime，无 method 硬上限，仍不得共享 mutable agent/DB lifecycle |
| LangMem | worker 内 `langgraph_user_id` namespace；W2 建独立 worker/store | 保持混合隔离；不因 InMemoryStore 有 namespace 就共享非线程安全 tokenizer/model |
| MemOS | product-native user/cube namespace，同 process runtime owner | 历史 W1；`Already borrowed` 否决的是共享 singleton，现 v6 改为每 worker 独立 runtime、无 method 硬上限 |
| A-Mem | per-conversation Chroma/state root | 当前必须物理隔离；只把 embedder 视为未来候选依赖 |
| MemoryOS | per-conversation product object/storage root | 当前必须物理隔离 |
| LightMem | per-conversation Qdrant collection/path | 当前必须物理隔离；collection 名不能证明整个 runtime 可共享 |
| SimpleMem | per-conversation system/LanceDB/state root | 当前必须物理隔离 |
| EverOS | per-conversation official lifespan/product root | 当前必须物理隔离 |
| Graphiti | per-conversation FalkorDB Lite root | 当前必须物理隔离 |

这里的“物理隔离”约束业务 mutable state，不否定未来共享 immutable tokenizer/model 或连接池；
“product-native namespace”也不自动证明 scheduler、client、tokenizer 和模型能并发复用。两者是不同轴。

## 4. 裁决

1. **不引入全局 embedding singleton。**重复模型实例已被测量证明，但十家 adapter 分属不同
   Python 环境、设备/normalization/distance 与 lifecycle；尚无统一 service 的并发安全、失败
   隔离、backpressure、observation scope 和语义守恒证据。
2. **先做 bounded admission control。**正式 5×10 是队列，不是同时放飞 50 个 process；按
   local-embedding、Docker/DB、API-only、W1-only 资源类设配额，是不改变算法身份的第一选择。
3. **dataset cache 暂不进入 correctness path。**未来优先研究 mmap/Arrow/source index 与只读
   decode cache；crop、iterator cursor、gold/private label view 必须 run-local。
4. **共享 embedding service 只有在 pilot 画像后立项。**验收至少包括同 embedding identity、
   thread/process safety、批处理顺序、token/latency observation 归属、失败影响面与前后 artifact
   语义守恒。收益不足时不为架构整洁而服务化。

M4 因而完成的是“测量 + 停手线”，不是提前实现一个可能错误的共享层。产品 connection、queue、
CPU/GPU utilization 与真实吞吐会随获批 pilot 一起观测，而不是在零 API 探针里伪造。
