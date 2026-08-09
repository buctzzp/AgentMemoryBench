# EverOS v1.2.3 source drift M1-R1 裁决

日期：2026-08-09
状态：`ARCHITECT_ACCEPTED_READY_FOR_M2`
替代范围：只替代
[M1 §2 的 v1.2.1 source/runtime identity](./everos-current-source-product-m1-ruling.md)；
M1 的官方 benchmark 覆盖、最终 payload、typed product surface 与五格方法学边界继续有效。

## 1. 判词

EverOS 主轨从 `v1.2.1@4256419` 线性升级到官方最新稳定版
`v1.2.3@48fc9084888bc17100053227284f939a5aca5e91`。这不是为了追新而追新：v1.2.3
已经修改 Cascade/OME 的失败可见性、后台循环监督、LanceDB 维护和查询向量宽度校验，且把
`everalgo-user-memory`、`everalgo-agent-memory` 升至 0.4.0；继续在 v1.2.1 上实现 M2 会制造
一份刚落地即过期的 runtime identity。

本次不推倒 M1 重查。`v1.2.1..v1.2.3` 间，官方 LoCoMo harness、typed add/search/get DTO 与
service 文件逐字未变，因此 B0 payload、官方覆盖分类和
`TRANSPORT_EQUIVALENT_PRODUCT_SURFACE` 裁决均继承。M2 必须直接以 v1.2.3 实现，并重新依据
新 completion/health surface 锁 exact drain 强反例。

## 2. Current stable source lock

- upstream：<https://github.com/EverMind-AI/EverOS.git>
- release：[`v1.2.3`](https://github.com/EverMind-AI/EverOS/releases/tag/v1.2.3)，
  2026-08-07 发布
- tag commit：`48fc9084888bc17100053227284f939a5aca5e91`
- package：`everos==1.2.3`，Python `>=3.12`
- license：Apache-2.0
- local-only path：`third_party/methods/EverOS`
- project patch：无
- local PDF：`EverMemOS.pdf` 仍为用户本地论文附件，不属于 source lock 或恢复资产

承重 hash：

```text
748007f17980117469390a385c37423c4bea2b0627cb6be00be315f9e64fc020  LICENSE
75c6ac0669f59f5f09641aa66e68c86a2ec3540b2a8b7f84c942a70e91e3f2d8  pyproject.toml
888ea91883afe40fd40524b8af7a7c29863a9d6d00924a5a812bad9f3ac5d3fb  uv.lock
8188863c28ef6fa1498924b1702301b6ac7d13312f2d705d5d7761f9d5e707a9  benchmarks/run.py
3ea2b4bcfdcf1e8668a214233a611c4f1950688a41fecb01649f3bc7a4400568  src/everos/service/memorize.py
19ab8e7cb0f4e72512a6d3870d8268c230fd5aa9a016a884fe9c4986372a7566  src/everos/service/search.py
af47cc55f0b2b74eb162ba651aa663b489aaacada75efd44269844ca4e10f834  src/everos/service/get.py
903ffa79a3df04b0abdc4f093e32d99862ebcd9e9ac1bc5aa9ed63d1bde5733e  src/everos/entrypoints/api/routes/memorize.py
a600ed61ab46e17c1aea737f1a1ed34d20c895a9219ed199d179453831252950  src/everos/memory/search/dto.py
ede004964a055f7e78359c032c41a7267cbf363d350e6ce35106da2d9580343e  src/everos/memory/get/dto.py
```

`uv lock --project third_party/methods/EverOS --check` 已通过；恢复脚本必须 checkout 上述 commit，
不得随 `main` 漂移。

## 3. 算法依赖身份

v1.2.3 的 `uv.lock` 是运行锚，EverAlgo 精确 tag 是公开源码审计锚：

| package | runtime version | official source tag / commit | sdist SHA-256 |
| --- | --- | --- | --- |
| everalgo-user-memory | 0.4.0 | `everalgo-user-memory/v0.4.0@6be77fe3` | `68dca5d49a8586caa734f862ae64ad63178f32c6b9d10341ba69c0a2f58b43b9` |
| everalgo-agent-memory | 0.4.0 | `everalgo-agent-memory/v0.4.0@d26fb2fd` | `58364d4c78b39b91d1eb93489c7d37fa9343e696987ac0c21631a8bb1099ec57` |
| everalgo-rank | 0.4.1 | `everalgo-rank/v0.4.1@673ace5e` | `0c4c0e72f11530ac2bcc7bca3aa1eaecbee1b5667811fd88ea15c12a1fb7cf19` |
| everalgo-knowledge | 0.1.1 | `everalgo-knowledge/v0.1.1@61e9ff99` | `64bcf2c88a4507a3bf704d7c7813956ede55a4575cf63424786f1fa65f4b3200` |
| everalgo-boundary | 0.2.1 | `everalgo-boundary/v0.2.1@088102d1` | `23a93bb36b06251e5a85765f68640c55bcfe0f1faf8b025e44ef8857a5ce36f9` |
| everalgo-clustering | 0.2.1 | `everalgo-clustering/v0.2.1@088102d1` | `30fd973f68520e778d3d1bd659198c59f49cf602e9c24b3962297d7c8293ab7e` |
| everalgo-core | 0.3.0 | `everalgo-core/v0.3.0@1152725e` | `cd91204a336ad459ae1c03eda97cdb0575534b675523cb775188debacc8f241b` |
| everalgo-parser | 0.2.1 | `everalgo-parser/v0.2.1@088102d1` | `5fec4d4c5743514a2cdbf756a34bc6ef987ea7503082768a8d6d764032a78992` |

其中 user-memory 0.4.0 会改变 Episode 生成语义：时间展示改为 24 小时 UTC、语言约束加强、
空白 LLM Episode 输出改为失败；这足以要求新 run 使用新的 source/model identity。agent-memory
0.4.0 虽不在主 `chat` profile 的用户记忆路径上，仍属于完整 runtime identity。

## 4. M1 可直接继承的部分

对以下文件执行 `git diff --quiet v1.2.1..v1.2.3 -- <paths>`，结果为 exit 0：

- `benchmarks/run.py`
- `src/everos/service/{memorize,search,get}.py`
- `src/everos/entrypoints/api/routes/memorize.py`
- `src/everos/memory/search/dto.py`
- `src/everos/memory/get/dto.py`

由此只继承这些有充分证据的结论：

1. current product official harness 仍只覆盖 LoCoMo；LongMemEval 仍是论文报告但公开 payload
   缺失，HaluMem、BEAM、MemBench 仍是 framework extension；
2. LoCoMo 最终 add/search payload、role/owner、session flush 与主/author 差异未漂移；
3. 主轨仍在 official FastAPI lifespan 内直接调用 typed service，省略 HTTP transport 而不绕过
   产品算法；
4. Message/Search/Get DTO 契约未漂移，M1 的输入、readout 与隔离问题清单仍是 M2 的边界。

这不是“版本号相近所以猜测兼容”，而是对承重文件做过字节级差量核验。

## 5. v1.2.3 对 M2 的实质影响

### 5.1 exact completion 有了更强的一手 surface

- `routes/ome.py:47-72,91-118`：manual trigger 现在区分 `ok`、`timeout`、
  `not_dispatched`，并返回逐 run terminal status/error；
- `infra/ome/engine.py:878-912`：可按 `event_id` 等待全部相关 run 到达 terminal；
- `routes/health.py:39-51,78-138`：Cascade readiness 暴露 pending、retryable/permanent failure
  与 worker operational health；permanent 数据质量 backlog 不被偷换成“后台线程健康”；
- `memory/cascade/worker.py:174-185,501-577`：后台 loop 被监督并在异常后重启，不再允许
  静默永久死亡；重试预算与 backoff 也成为 completion 判据的一部分。

因此 M2 不再照抄旧 harness 的“两次 pending=0”轮询。adapter 必须把 scoped event/run terminal、
Cascade pending/failure 与 worker health 合成 exact drain，并把 timeout、dead-letter、
not-dispatched 与 backend failure 分开。

### 5.2 retrieval/runtime identity 更严格

- `memory/search/manager.py:717-737` 会验证 query embedding 的实际宽度与 provider 声明维度；
- `lancedb` 升到 `>=0.34,<0.35`，包含 schema/locking/index maintenance 变化；
- 新旧 run 不得 resume 互认，manifest 至少要盖章 EverOS commit、`uv.lock` hash、EverAlgo
  versions、LanceDB range、embedding dimension/transport 与 adapter contract version。

## 6. M2 边界与停点

本批只完成 source drift 裁决，没有 adapter/TOML/tests/真实 API/模型下载/实验输出。M2 继续按
既有 ledger 顺序关闭：isolated worker + official lifespan、missing source time、assistant-only
owner、LoCoMo owner merge、exact drain、Episode readout/lineage、HaluMem 四格、observability、
resume/cleanup 与五格零 API 强反例。

真实 build/embedding/rerank/answer/judge smoke 仍必须在 machine plan 完成后另获用户预算批准。

最终判词：

```text
EVEROS_V1_2_3_SOURCE_DRIFT_ACCEPTED_READY_FOR_M2(
  final payload and typed product surface are byte-stable;
  runtime and algorithm identity are upgraded;
  exact completion must use the v1.2.3 failure surfaces
)
```
