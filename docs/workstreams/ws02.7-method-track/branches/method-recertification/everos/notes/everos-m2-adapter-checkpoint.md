# EverOS v1.2.3 product adapter M2 检查点

日期：2026-08-09
状态：`READY_FOR_B11_REAL_SMOKE_APPROVAL`
用途：跨 task / compaction 的最小恢复入口。

## 1. 已锁身份

- source：`EverOS v1.2.3@48fc908`，Apache-2.0；runtime 算法包由 vendored `uv.lock` 固定；
- product：官方 `create_app()` lifespan 内 typed `memorize/search/get`，不启动 HTTP host；
- patch：只聚合并上抛 lifespan provider shutdown failure，成功路径不变；
- adapter：`everos-product-chat-v1`，session 粒度，内部 batch=25，public HYBRID Episode readout；
- 主配置：smoke `opencodego/deepseek-v4-flash`，official full `primary/gpt-4o-mini`，
  Qwen3-Embedding-4B/1024/LanceDB L2。

## 2. M2 已闭合

1. 每 provider 独占 Python 3.12 worker/lifespan；每 conversation 物理 root；
2. LoCoMo all-user real speaker owners + 多 owner merge；其余四格 canonical role 原序；
3. assistant-only 只加空、无 source identity 的结构 user anchor；
4. missing source time 与 product operational ms 分层，派生时间不进 answer context；
5. OME terminal + Cascade health/failure + 双稳定零 exact drain；
6. completed-operation journal、digest drift、物理 tombstone clean retry 与 shutdown fail-visible；
7. Episode 完整 readout、zero-hit、stable rank、semantic provenance N/A；
8. HaluMem extraction/update/QA valid candidate，memory type N/A；
9. exact LLM/embedding usage wrapper、rerank capability 零调用断言、secret negative-space、
   isolated W1/W2 ownership；
10. 五格安全档案与 20 份 machine smoke plan；扩展定向 `480 passed`、主树全量
    `2078 passed, 3 deselected, 13 warnings, 29 subtests passed`、compileall 与 patch/source
    identity 门均通过。

## 3. 当前恢复入口

- 机制与验证：[M2 实现记录](everos-m2-adapter-implementation.md)；
- 五格异常/metric：[安全档案](everos-five-benchmark-safety-dossier.md)；
- 逐门状态：[ledger](everos-integration-ledger.md)；
- B11 命令事实：[machine plans](everos-smoke-plans-v1.json)。

只有 source/product/benchmark 契约出现新反证才重开 M1/raw census；正常 B11 恢复不读历史 M1
全文。

## 4. 当前唯一批准门

1. 用户重新批准 EverOS 真实 B11 的预算、20 份 plan 与 run ids；
2. 执行 predict/evaluate 后开箱 manifest、prediction、formatted memory、private negative-space、
   efficiency、state、summary 与 W1/W2；
3. 全部门通过后才写 frozen note、把 ledger/总表/roadmap 同步为 frozen。

当前环境缺 `EVEROS_DEEPINFRA_API_KEY`；未经新批准不得补 key 或启动真实 build/embedding/rerank/
answer/judge。HaluMem plan 是 fixed shape，禁止添加通用裁剪参数。
