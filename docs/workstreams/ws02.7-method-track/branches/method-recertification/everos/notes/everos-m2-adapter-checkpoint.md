# EverOS v1.2.3 product adapter M2 检查点

日期：2026-08-09；冻结同步：2026-08-14
状态：`METHOD_FROZEN_V1`
用途：跨 task / compaction 的最小恢复入口。

## 1. 已锁身份

- source：`EverOS v1.2.3@48fc908`，Apache-2.0；runtime 算法包由 vendored `uv.lock` 固定；
- product：官方 `create_app()` lifespan 内 typed `memorize/search/get`，不启动 HTTP host；
- patch：只聚合并上抛 lifespan provider shutdown failure，成功路径不变；
- adapter：`everos-product-chat-v6`，worker protocol v2，sidecar v2；session 粒度，内部
  batch=25，public HYBRID Episode readout；
- 主配置：smoke `opencodego/deepseek-v4-flash`，official full `primary/gpt-4o-mini`，
  Qwen3-Embedding-4B/1024/LanceDB L2。smoke 的同模型 embedding 由
  OpenRouter OpenAI-compatible `/embeddings` 承载；official full 保持 DeepInfra 默认
  transport。provider/base URL/credential name 是运行身份，secret 值不落 artifact。

## 2. M2 已闭合

1. 每 provider 独占 Python 3.12 worker/lifespan；每 conversation 物理 root；
2. LoCoMo all-user real speaker owners + 多 owner merge；其余四格 canonical role 原序；
3. assistant-only 只加空、无 source identity 的结构 user anchor；
4. source-derived time only；LoCoMo official `+30s` 排序不冒充 source time；其余缺时在 API 前
   拒绝，MemBench 100k 诚实 unsupported；
5. OME terminal + Cascade health/failure + 双稳定零 exact drain；
6. completed-operation journal、digest drift、物理 tombstone clean retry 与 shutdown fail-visible；
7. Episode 完整 readout、zero-hit、stable rank、semantic provenance N/A；
8. HaluMem extraction/update/QA valid candidate；Medium 真实 B11 又证 memory type 可按两项合法
   score artifact 的 evaluator-private gold 标签汇总，旧 N/A 判断已撤回；
9. exact LLM/embedding usage wrapper、rerank capability 零调用断言、secret negative-space、
   isolated W1/W2 ownership；
10. 五格安全档案与 18 份 current v6 machine smoke plan；35 个 question/conversation、真实 W1/W2、
    HaluMem 四类指标、artifact/效率/隐私/state 门均关闭；最终全量
    `2158 passed, 3 deselected, 13 warnings, 29 subtests passed`，compileall、patch/source
    identity 与 diff 门均通过。

## 3. 当前恢复入口

- 机制与验证：[M2 实现记录](everos-m2-adapter-implementation.md)；
- 五格异常/metric：[安全档案](everos-five-benchmark-safety-dossier.md)；
- 逐门状态：[ledger](everos-integration-ledger.md)；
- B11 命令事实：[machine plans](everos-smoke-plans-v1.json)。

只有 source/product/benchmark 契约出现新反证才重开 M1/raw census；正常 B11 恢复不读历史 M1
全文。

## 4. 冻结结论

18 份 current v6 plan 已全部 fresh 执行；8 个 croppable concrete variant 均有 W1/W2，HaluMem
Medium/Long 按 fixed W1。权威证书为 [everos-frozen-v1](everos-frozen-v1.md)，逐门账为
[ledger](everos-integration-ledger.md)。本 checkpoint 自此只承担压缩恢复入口，不再列待执行门。

2026-08-12 live preflight 已证 OpenCodeGo 只提供 Chat Completions，不能承载 embedding；现有
OpenRouter key 对 `Qwen/Qwen3-Embedding-4B` 精确模型名、1024 维请求返回成功 usage。因此 smoke
显式使用 OpenRouter embedding transport，不把其 key 冒充 DeepInfra key，也不改变模型、维度、
LanceDB distance 或产品算法。HYBRID Episode 主轨允许 optional rerank capability 缺失，但任一
真实 rerank 调用仍 fail-fast；official full 的 DeepInfra 配置不变。HaluMem plan 是 fixed shape，
禁止添加通用裁剪参数。

2026-08-12 首轮 live 到 MemBench 100K 时停在 `year 31969`。进一步审读产品 Episode prompt 后
改判：即使把 sentinel 调到合法毫秒，它仍会进入生成记忆，成为 answer-visible 伪事实。因此 v6
删除 operational fallback，并由 registry variant gate 在任何 runtime/API/output 前拒绝 100k；旧
v2-v5 run 只保留诊断价值，冻结矩阵全部 fresh v6。

2026-08-13 Medium evaluate 首次返回 memory-type 数值时，架构师误以为与既定 N/A 冲突而暂停
Long；复核 evaluator 后改判：该指标不消费 EverOS `Conversation` kind，而是将 extraction/update
逐点得分按私有 gold `memory_type` 分组。Medium 结果有效；Long 中断 run 不 resume，改用 fresh
`everos-halumem-v6-w1-long`。

2026-08-14 冻结前又发现 v5 把 upstream `default.toml`（含 provider endpoint 默认值）复制到
run-local `everos.toml`。v6 只保留产品运行时实际 watch 的 `ome.toml`，默认配置继续从 vendored
package 读取、transport 由受限环境覆盖；18 个 run 的 key/base URL/upstream endpoint 精确值扫描
均为零命中。exact drain 同时由固定 100 次紧循环改为 wall-clock deadline + event-loop yield，
避免已被后台 worker claim 的行因调度饥饿被误判未完成。
