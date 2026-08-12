# Letta B11 首次真实链路尝试与 R1 修复

日期：2026-08-09
状态：`SUPERSEDED_EXTERNAL_GATE_RESOLVED；READY_FOR_FRESH_SMOKE`
adapter：`letta-sleeptime-product-v2`

## 1. 判词

用户已经批准 Letta/LangMem/EverOS 的 `smoke` 使用
`opencodego/deepseek-v4-flash`。架构师按
[`letta-smoke-plans-v1.json`](letta-smoke-plans-v1.json) 的第一份 LoCoMo W1 machine plan
启动真实链路；没有手写或缩改 planner 命令。

这次尝试先后暴露并关闭两项真实产品链缺口，随后请求已经到达 OpenCodeGo，但服务端以 HTTP
403 拒绝当前 workspace 未完成的 China-hosted model opt-in。因此：

```text
LETTA_PRODUCT_CHAIN_R1_ACCEPTED
LETTA_B11_NOT_STARTED_TO_COMPLETION
ALL_OPENCODEGO_SMOKE_PAUSED_UNTIL_USER_OPT_IN
```

403 发生后没有继续跑剩余 Letta plan，也没有把同一必败 runtime 扩散到 LangMem/EverOS。

## 2. 第一次尝试：Docker Desktop 未运行

第一份 plan 在 PostgreSQL container 创建前即因 Docker daemon 不可达退出。该项属于本机环境
前置，不是 adapter 算法错误。启动 Docker Desktop 后重新执行同一 machine plan。

失败资产保留在：

```text
outputs/failed-smoke-attempts/letta-locomo-v1-r1-docker-not-running-20260809/
```

## 3. 第二次尝试：Postgres 临时初始化 server 被误判 ready

### 3.1 根因

官方 Postgres image 首次初始化时，会短暂启动只监听 Unix socket 的临时 server，完成建库后
关闭它，再启动最终 TCP server。旧 `_wait_for_postgres()` 只执行容器内裸 `pg_isready`，会在
临时 server 阶段过早返回；紧随其后的 pgvector extension 初始化可能正好撞上临时 server
关闭，从而出现 socket 消失竞态。

### 3.2 修复

`LettaRuntime._wait_for_postgres()` 改为容器内执行：

```text
psql -h 127.0.0.1 -Atqc "SELECT 1" -U letta -d letta
```

只有最终 TCP server 能实际执行 SQL 才算 ready。强反例先返回 connection refused，再返回
`1`，并锁定 ready 之前不得读取宿主机随机映射端口。

失败资产保留在：

```text
outputs/failed-smoke-attempts/letta-locomo-v1-r1-postgres-init-race-20260809/
```

## 4. 第三次尝试：official run lifecycle 缺失

### 4.1 根因

真实 `AgentLoop.step()` 的产品路径默认 `enforce_run_id_set=True`。旧 worker 直接调用 step，未像
官方 REST `send_message` 路径那样先创建 `Run`，因此在 LLM 成功调用前触发：

```text
AssertionError: run_id is required when enforce_run_id_set is True
```

### 4.2 修复

worker 现在镜像官方产品生命周期：

1. `run_manager.create_run(Run(...))`；
2. 把返回的 `run.id` 传给 `AgentLoop.step(...)`；
3. 成功时按真实 stop reason 写 terminal status；
4. 失败时写 `RunStatus.failed` 后继续传播原异常；
5. artifact-safe metadata 只保留异常类型，不保存 message、key 或 endpoint。

强反例分别锁定成功顺序
`create_run → step(run_id) → update(completed)` 与失败顺序
`create_run → step(run_id) → update(failed)`，并验证失败时 usage buffer 被清空。

失败资产保留在：

```text
outputs/failed-smoke-attempts/letta-locomo-v1-r1-missing-run-lifecycle-20260809/
```

## 5. 第四次尝试：OpenCodeGo 外部 opt-in 门

两项本地缺口修复后，同一 plan 已穿过 Docker、PostgreSQL/pgvector、migration、`SyncServer`、
subject/agent/run 创建并抵达真实 OpenAI-compatible endpoint。服务端返回 HTTP 403
`RegionError`：该 workspace 尚未显式 opt in China-hosted model。服务端给出的用户动作入口为：

用户账户侧的 OpenCodeGo workspace model opt-in 页面（私有 workspace 链接不落仓库）。

这是账户条款/地域选择，必须由用户本人完成；架构师不代点、不更换用户已裁定的 smoke
provider/model，也不靠无限 retry 消耗预算。失败资产保留在：

```text
outputs/failed-smoke-attempts/letta-locomo-v1-r1-opencodego-region-403-20260809/
```

canonical run 目录已移出，所有 owner-labeled container/volume 在核对 identity 后安全清理；当前
没有遗留 Letta Docker 资源。`.env` 的 key、base URL 与 secret 未写入本 note 或 artifact。

## 6. 验证

两项修复后的直接相关回归：

```text
120 passed in 2.16s
```

`compileall` exit 0，`git diff --check` clean。真实 B11 仍为 PENDING：HTTP 403 不是成功 run，不能
用“请求曾到达 endpoint”冒充 smoke 通过。

## 7. 恢复动作（2026-08-11 外部门解除后）

用户已完成 opt-in。current `predict smoke` 不支持 resume，且 LoCoMo OpenCodeGo answer
compatibility 已改为显式 4096；因此旧失败 run 只保留作四段失败边界证据，不复用其
checkpoint/state。后续动作是：

1. 用 current planner 生成新 identity 的 Letta plans，先执行全新 LoCoMo W1；
2. 对 prediction、manifest、formatted memory、efficiency 与 evaluator artifact 开箱；
3. 第一份通过后再按 JSON 顺序运行其余 10 份 Letta plan；
4. Letta 关闭 B11 后，再执行 LangMem/EverOS，避免共享外部阻点造成批量失败资产。

不得重新手写 smoke 命令，也不得把这次 403 记成 method regression。
