# MemOS v2.0.25 M1 R1 架构裁决

日期：2026-07-26

## 0. 判词

```text
ACCEPT_M1_STOP_AND_CONTINUE_R1(
  current product = tree_text + MultiModalStructMemReader + typed handlers;
  explicit chat_time=None is the missing-time representation;
  message_id reader transport is proven but metric eligibility remains pending;
  local /scheduler/wait is forbidden as a completion gate;
  R1 first proves sync+fine+serial-dispatch completion and single-namespace isolation
)
```

首轮 actor 在 `13edb3a` 命中停工条件是正确行为。错误来自架构卡把三条未经 current
active call graph 完整核实的判断写成了“承重事实”，不是 actor 未完成任务。首轮 note
保留为一手停工证据；本裁决只改写 R1 的验证基线，不要求重做已闭合取证。

## 1. 强验收结论与一处勘误

架构师已独立亲读 `v2.0.25@e820406` current source，确认：

1. 默认 product reader 是 `MultiModalStructMemReader`；它只继承
   `SimpleStructMemReader.get_memory()` 与 `coerce_scene_data()` 外壳，实际滑窗和
   fine/fast extraction 走自己覆写的 `_process_multi_modal_data()` 链；
2. 每条消息显式携带 `chat_time=None` 时会保留 `None`；只有完全缺少 key 的消息才会被
   首个兄弟时间或 wall clock 补齐；
3. active user/assistant parser 会把 `message_id` 写进 `SourceMessage`，窗口与 fine
   extraction 在 reader 内继续携带该对象；
4. scheduler task tracker 的注册键是 request `user_id`，不是 cube id。

首轮 note 对无 Redis wait 的**结果判断正确、对象解释不精确**。真实关系是：

- scheduler 内部 tracker 在 local queue 下为 `None`；
- router 另行构造 `TaskStatusTracker(redis=None)`；
- 该对象查询返回空集合，`/scheduler/wait` 因 `not []` 立即返回 idle。

因此 local product 下 wait 仍是 fail-open，但后续文档和实现不得再写成“router 把
`None` tracker 传给 wait”。

## 2. R1 锁定裁决

### 2.1 产品身份与调用面

- Phase 1 主候选锁定 self-host product 的 `tree_text` 算法与
  `MultiModalStructMemReader`，不改回 `MOS.simple()` 的 `general_text`。
- framework worker 内调用 `init_server()` 返回的 official components，再构造
  `HandlerDependencies`、`AddHandler` 和 `SearchHandler`；禁止 import
  `server_router`，也不启动 HTTP host。
- raw `MemReader + TreeTextMemory` 只能用于定位或 hermetic 探针，不能冒充主产品。
- 主配置只使用一个 cube；`CompositeCubeView` 的并行合并无全局重排/截断，不进入
  Phase 1 主 profile。

### 2.2 时间

adapter 后续必须给**每条** outgoing message 显式写 `chat_time` key：

```text
canonical turn time → canonical session time → None
```

值为 source timestamp 或显式 `None`；不得省略 key，不得用 question time、兄弟 turn、
wall clock、空串或非法 sentinel。current upstream 已支持这一表示，不写 missing-time
兼容补丁。

### 2.3 Scheduler 完成门

- local queue 下禁止把 `/scheduler/wait` 当完成门；也不为修这个接口强制引入 Redis。
- R1 首选验证 product 原生组合：
  `APIADDRequest(async_mode="sync", mode="fine")` +
  `MOS_SCHEDULER_ENABLE_PARALLEL_DISPATCH=false`。
- 选择理由：sync/fine 在 request 线程完成 active reader 与 tree write；`ADD` 是
  `LEVEL_1` task，serial dispatch 候选应在调用栈内完成并传播失败。
- 这仍只是**待证明候选**。R1 必须对照 async/fast → `MEM_READ` 与 sync/fine → `ADD`
  的算法职责，证明它不是删掉产品算法阶段的“快捷绕行”。若异常仍被吞、或两条路径的
  记忆算法实质不同，立即停工，不用 polling 猜完成。
- author harness 的 async 默认只能作为单独配置身份；不得暗中混进主 smoke。

### 2.4 隔离

首版每个独立 memory universe 使用一个确定性 namespace：

```text
namespace_id = run identity + benchmark + variant + public sample/conversation identity
user_id = namespace_id
writable_cube_ids = [namespace_id]
readable_cube_ids = [namespace_id]
session_id = canonical session identity
```

这不是宣称 user 与 cube 永远同义，而是首版故意收敛二维隔离，镜像 official harness
姿势并避免 wait/search/cleanup 交叉命名。R1 必须用双 universe 强反例证明不可串库，并
闭合 clean retry；证明失败则停工。

### 2.5 Lineage 与 metric 资格

- `message_id` 到 reader `metadata.sources` 已由一手源码证明，不再调查第一个 reader drop。
- R1 只追剩余链：graph serialization → scheduler evolution/merge → search result →
  formatter/readout。
- source id 存在只证明参与生成；fine window 把一组 sources 赋给抽取 memory，不能据此
  自动宣称 turn-exact semantic provenance。
- 必须分别判断 fast/fine/mixture 返回单位、score 与顺序。Recall/NDCG、HaluMem
  extraction/update 等资格在 R1 结束前保持 `pending`，不得先写 `valid`。

## 3. R1 退出条件

R1 只完成 MemOS 产品机制闭合，不写 adapter、不重查五个 benchmark。必须交付：

1. typed handler 与 HTTP router 的逐项 parity/差量表；
2. sync/fine/serial completion 与失败传播判词；
3. source time/message_id 的 end-to-end 保留或首个真实 drop 点；
4. single-namespace 隔离、cleanup 与 retry 判词；
5. search top-k/score/order/readout、服务与效率观测表；
6. 五 benchmark metric/HaluMem 资格矩阵；
7. M2-M5 所需的最小实现输入与明确 N/A/pending。

旧 M1 卡已被首轮停工 supersede。当前唯一入口是
[`../cards/actor-prompt-memos-v2-0-25-product-runtime-preflight-r1.md`](../cards/actor-prompt-memos-v2-0-25-product-runtime-preflight-r1.md)。
