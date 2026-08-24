# M3：HaluMem session extraction 资格裁决与实现

日期：2026-08-24
状态：`ACCEPTED_BY_M5_NO_API_REGRESSION`
边界：不调用真实 API，不把 source lineage、raw input 或强制 lifecycle flush 冒充产品记忆。

## 1. 统一判据

HaluMem extraction 要的是“当前 session 经方法处理后产生或改写的产品记忆”，不是：

- 把本 session 原始 turn 原样回显；
- 给任意 memory metadata 塞入 `session_id` 后全库过滤；
- 把截至当前的累计 memory 全部当成本 session 增量；
- 为了拿到中间产物，强制触发产品原本不会在每个 session 执行的迁移、consolidation 或 flush。

本批只接受两种产品级证据：产品事务直接返回 changed units，或同一 namespace 的完整
stable-ID product state 在事务前后的 delta。`session_memory_report` 是实例级能力声明；runner
不再通过“类是否覆写 `end_session()`”猜测资格。

## 2. 四家裁决

| method | 裁决 | 产品级报告单元 | 关键边界 |
| --- | --- | --- | --- |
| LangMem | valid | `ainvoke()` changed keys 在提交后 exact store snapshot 中对应的 current values | insert/update 后的 evolved memory；不是 raw turn，也不外推 Recall lineage |
| Letta | valid | attached core blocks 的 stable-ID before/after changed values | 只读同一 agent 全部 blocks；baseline/result 写入 crash-safe sidecar journal |
| MemOS | valid | async business task 唯一 terminal success 后，完整 `GetMemory` stable-ID delta | 未分页、namespace 一致、ID 唯一；scheduler 日志与 source metadata 不作替代 |
| MemoryOS | N/A | 无合格 session-local derived-memory unit | 新增 STM QA page 仍是 raw input；MTM/LPM 只有按原 lifecycle 迁移后才是派生记忆，强制逐 session flush 会改算法 |

valid 只表示 HaluMem extraction evaluator 可以消费这些 current product units。它不自动赋予
Recall/NDCG 资格；三家 evolved memory 仍不能 lossless 映射到 source gold turn。

## 3. 实现摘要

### 3.1 LangMem product-v2

- worker state/adapter 升 v2；completed operation 同时保存
  `changed_memory_keys` 和同序 `changed_memories[{key,value}]`；
- manager 返回重复 key、changed key 不存在于事务提交后 store、value 非 JSON object 均
  fail-fast；
- adapter 只格式化 current value，并在 `end_session()` 报告；result-loss replay 读取同一
  completed operation，不重新运行 manager。

### 3.2 Letta product-v3

- sidecar schema 升 v2；HaluMem session 首个 build batch 前原子保存 input digest 与 normalized
  attached-block baseline；
- 全部 build operation terminal 后重新读取相同 agent、验证既有 block owner，再按 stable ID
  计算非空 changed values并持久化；
- 产品完成而 report 落盘前崩溃时，重放跳过 completed build operation，用持久 baseline 与
  当前 blocks 恢复同一 delta。

### 3.3 MemOS product-v5

- runtime 通过 host router 同源的 typed `handle_get_memories(GetMemoryRequest(...))` 读取 text
  memory；不启动 HTTP host；
- request 同时约束 `mem_cube_id=user_id=namespace`，关闭 preference/tool/skill，`page=None`、
  `page_size=None`；response 必须恰有一个同 namespace text bucket，且
  `total_nodes == len(memories)`；
- 每个 memory 必须有唯一非空 stable ID 与非空 current text；只有所有 async business task
  唯一 terminal success 后才读取 after snapshot并报告 new/changed values。

### 3.4 Runner capability

operation runner 现在只读取实例级 `provider.session_memory_report`。实现了钩子但 profile
关闭时写 `status=n/a`，不会误调用；profile 声明开启时空 delta 写 `status=empty`，与 N/A 和
真实非空 report 三者可区分。

## 4. HaluMem memory-type 与其他 metric

HaluMem memory-type 是 extraction 与 update artifact 上的 evaluator-private gold-type 合成，
Event/Persona/Relationship 不要求 method 自身使用同名 taxonomy。因此 LangMem、Letta、MemOS
的 extraction 升级后，memory-type 也具备 evaluator 资格；某次极小运行没有 update 路由或
得到零分，属于该 run 的结果，不反向取消静态资格。

MemoryOS extraction 继续 N/A，memory-type 仍按既有 canonical N/A 传播。四家的
Recall/Precision/F1@k、NDCG 与 stable ranking 判词均不因本批自动变化。

## 5. 身份与重建

本批改变 adapter/state contract：LangMem v1→v2、Letta v2→v3、MemOS v4→v5。旧 method
state 和真实 smoke artifact 保留历史可读，但不得 resume 到新版本或重标为新结果；下一次
真实 smoke/pilot 使用新 run id 全量重建。MemoryOS 身份不变。

## 6. 零 API 验收

本批定向门：

```text
OPENAI_KEY=dummy BASE_URL=http://127.0.0.1:9 uv run pytest -q \
  tests/test_langmem_adapter.py tests/test_langmem_worker.py \
  tests/test_langmem_registered_prediction.py tests/test_letta_adapter.py \
  tests/test_letta_worker.py tests/test_letta_registered_prediction.py \
  tests/test_memos_adapter.py tests/test_memos_registered_prediction.py \
  tests/test_operation_level_runner.py tests/test_halumem_registered_prediction.py \
  tests/test_method_registry.py tests/test_prediction_runner.py
476 passed in 9.01s
```

强反例覆盖：current-value 而非 raw echo、LangMem result-loss replay、Letta report
落盘前 crash replay、MemOS terminal 前后 stable-ID delta、capability 显式关闭，以及各
registered HaluMem artifact 的 `ok/empty/n/a` 分流。M5 仍须执行更宽无 API 回归与架构门，
本节不提前宣称全量冻结。
