# M1-C：四家 isolated worker transport 单源化

日期：2026-08-14

范围：EverOS / Graphiti / LangMem / Letta adapter 主进程侧 JSON-lines transport

性质：零 API、算法与产品 lifecycle 守恒的结构减重

## 1. 裁决

四家 adapter 已把同一套主进程机械协议复制了四次：`Popen` pipe、stderr drain、请求锁与
递增 id、JSON-lines 写入、selector timeout、response identity、result 形状、错误尾部和
terminate/kill fallback。M1-C 将这些职责收敛到：

- `src/memory_benchmark/methods/worker_transport.py`
- `JsonLinesWorkerTransport`

只抽机械 transport，不抽 standalone worker 的产品 schema，也不抽 initialize/shutdown
payload、数据库、Docker、conversation namespace、journal、产品完成门或 provider cleanup。
MemOS 的 in-process scheduler/task tracker 不属于该协议，明确不进入本批。

## 2. 抽取前的真实差异矩阵

| 产品 | request key 排序 | timeout 后 | 坏 JSON / id 错配后 | terminate 后 handle | stderr 字符尾部 | 最终 lifecycle |
| --- | --- | --- | --- | --- | ---: | --- |
| EverOS | `sort_keys=True` | terminate | terminate | 忘记，可在清 root 后切 conversation | 3000 | patched lifespan + conversation root |
| Graphiti | insertion order | terminate | terminate | 保留退出对象，拒绝隐式重启 | 3000 | Graphiti shutdown + FalkorDB state |
| LangMem | insertion order | terminate | terminate | 保留退出对象，journal 是 resume authority | 3000 | manager shutdown + operation journal |
| Letta | insertion order | 只报错 | 只报错 | 保留 | 2000 | worker + owned PostgreSQL container |

因此“协议重复”成立，但“失败策略完全相同”不成立。共享类通过窄构造 policy 保存上表差异；
尤其没有把前三家的主动终止强加给 Letta，也没有把 Letta 的 Docker cleanup 塞进公共层。

## 3. 所有权边界

### 3.1 公共 transport 拥有

- 子进程 stdin/stdout/stderr pipe 与 stderr drain thread；
- 单 transport 请求锁和单调 request id；
- JSON request 字节、selector timeout 与 response contract；
- 已脱敏 stderr 有界尾部；
- terminate → 5 秒 wait → kill fallback → pipe close；
- transport 级幂等终止。

### 3.2 各产品 runtime 继续拥有

- Python runtime、argv、cwd、allowlisted env 与 secret 选择；
- stderr 中哪些值需要以什么占位符脱敏；
- initialize identity 与产品 payload；
- ingest/retrieve/delete/shutdown 命令的业务含义；
- conversation/namespace/subject root；
- EverOS root 切换、Graphiti/LangMem journal、Letta PostgreSQL container；
- provider cleanup 的“失败后能否重试/是否永久 fail-closed”。

四家仍保留很薄的 `_request()` / `_terminate_worker()` 产品入口，但它们只委托公共类；
Popen、selector、thread、协议解析和 kill fallback 已只有一份生产实现。

## 4. source / resume identity

共享代码改变会同时改变四家 method build。故四家的 `build_*_source_identity()` 均把
`src/memory_benchmark/methods/worker_transport.py` 纳入 `wrapper_hashes`：

- EverOS
- Graphiti
- LangMem
- Letta

这是必要的 identity 修复，不是 manifest schema 变更。旧 run artifact 保持原样可读；新 run
会得到新的组合 `source_sha256`，因此不能与抽取前 build 静默 resume。adapter version、worker
schema、payload 与 method 算法均未变化。

## 5. 强反例

新增 hermetic 子进程协议测试覆盖：

1. Unicode/request 字节与 EverOS `sort_keys=True`；
2. 同 transport request id 单调递增；
3. 多线程 caller 由一把锁串行化，response 不串题；
4. worker `ok=false` 与非 object result fail-fast；
5. 坏 JSON 终止并按 policy 忘记 handle；
6. response id 错配终止但按 policy 保留失败 handle；
7. Letta timeout 只报错、worker 保持运行；
8. LangMem 类 policy timeout 后终止并保留 journal-authority 错误句；
9. stdout 提前关闭时 stderr 尾部脱敏；
10. 重复 terminate 幂等；
11. worker 忽略 terminate 时进入 kill fallback；
12. 非法 transport policy 在 Popen 前拒绝。

四家既有 provider cleanup 强反例继续锁“第一次 close 失败不提交 cleaned，成功后第二次
cleanup 幂等”。新增架构门禁止四个 adapter 重新引入 `selectors`、`threading.Thread` 或
`subprocess.Popen`，并要求它们依赖 canonical transport。

## 6. 文件与行为守恒

生产改动仅为：

- 新增 `methods/worker_transport.py`；
- 四家 adapter 改为组合该 transport，并更新 source identity；
- standalone worker 文件零修改；
- config/TOML/registry/runner/metric/prompt/artifact schema 零修改；
- data/models/outputs/third_party 与真实 API 零触碰。

结构收益是四份机械实现收成一份；产品不对称仍显式。行数减少不是验收 KPI，真正完成门是
异常/timeout/cleanup/identity 守恒及自动防回归。

## 7. 验证

- transport + architecture + 四家 adapter/registered prediction + registry/prediction + 文档门：
  `469 passed in 4.54s`；
- `uv run python -m compileall -q src/memory_benchmark tests`：exit 0；
- 无 API 全量：`2225 passed, 3 deselected, 25 warnings, 29 subtests passed in 149.88s`；
- `git diff --check`：通过。

全量首跑为 `1 failed, 2224 passed, 3 deselected`。唯一失败不是生产行为回归，而是
`tests/test_graphiti_worker.py` 仍向已退出的旧私有字段 `runtime._worker` 注入替身，导致测试
没有进入新的 canonical transport shutdown 分支。测试改为向
`runtime._transport._process` 注入同一替身后，原 fail-closed 断言转绿；没有删除断言或绕过
shutdown failure。第二次全量给出上面的最终全绿尾行。

## 8. 关闭边界与下一动作

M1-C 只在定向门、compileall、文档门和无 API 全量门全部通过后关闭。关闭后严格进入 M1-D：
按 leaf-first 拆 prediction planning/preflight → ingest → answer → parallel；不顺带修改
registry、metric、prompt、resume schema，也不继续扩出 M1-E。
