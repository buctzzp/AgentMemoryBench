# EverOS v1.2.3 product-chat adapter M2 实现记录

日期：2026-08-09
状态：`READY_FOR_B11_REAL_SMOKE_APPROVAL`
adapter：`everos-product-chat-v1`

## 1. 结论

EverOS current product surface 已接入 provider v3。每个 provider 独占一个 Python 3.12
worker；worker 进入官方 `create_app()` lifespan 后，直接调用和 HTTP route 相同的 typed
`memorize/search/get` service。框架没有启动 HTTP host，也没有绕过 boundary、Episode、OME、
Cascade、SQLite 或 LanceDB。

当前只完成离线 adapter 门，不能标 frozen。真实 build/embedding/rerank/answer/judge、artifact 开箱和
最终 B11 仍需用户重新批准预算后执行。

## 2. 产品调用图

```text
generic / operation-level runner
  └─ EverOS.prepare()                         只核 source 与独立 runtime
      └─ 首个 conversation 懒启动 EverOSRuntime
          ├─ 每 conversation 一个物理 product root
          ├─ official everos.toml + ome.toml 模板
          └─ Python 3.12 JSON-lines worker
              └─ create_app() official lifespan

SessionBatch ingest
  ├─ canonical event → MessageItemDTO 字段
  ├─ 每 25 条 MemorizeAddRequest → service.memorize
  ├─ 空 messages + is_final=True 强制 session flush
  ├─ OME terminal + Cascade 双稳定零 exact drain
  ├─ public GetRequest(session_id filter)
  └─ 原子 completed-operation sidecar

RetrievalQuery
  ├─ 每个 product owner 一次 SearchRequest(HYBRID, top_k)
  ├─ score↓ → owner 首见顺序 → product rank → id 稳定合并
  └─ Episode 全字段 → RetrievedItem → formatted_memory

failed retry / cleanup
  └─ close worker → root marker → cleanup marker → rename tombstone → rmtree
```

stdio 只解决主框架与 EverOS 依赖树的 Python 版本隔离，不是第二套算法服务。

## 3. Source lock 与最小 patch

- EverOS：`v1.2.3@48fc9084888bc17100053227284f939a5aca5e91`，Apache-2.0；
- runtime：vendored `uv.lock`，由 `scripts/bootstrap_everos_runtime.sh` 以 `uv sync --frozen`
  建立独立 `.venv`；
- patch：`scripts/patches/everos-product-runtime-observability.patch`；
- patch 唯一行为：official lifespan 关闭时依次 settle 全部 provider，把所有 shutdown error
  聚合为 `ExceptionGroup`；成功路径、provider 顺序与算法返回值不变；
- source identity 同时覆盖 selected upstream files、`uv.lock`、patch、adapter、worker、bootstrap
  和两份 product root config 模板。

真实零 API probe 已证明：三个 provider 逆序全部执行，首尾两个 shutdown error 同时上抛；
空 product lifespan 可启动并完整关闭。nested source 的 reverse patch check 通过。

## 4. 配置与模型身份

`configs/methods/everos.toml` 只有 `smoke` 与 `official_full`。两者共同锁定：

- `memory_mode=chat`、session 输入、official add batch `25`；
- public `HYBRID` Episode search，`enable_llm_rerank=false`；
- DeepInfra OpenAI-compatible `Qwen/Qwen3-Embedding-4B`、1024 维、LanceDB L2；
- 已声明 `Qwen/Qwen3-Reranker-4B` 产品身份；current `chat` 只产 user Episode，user HYBRID
  走 hierarchy fusion，不可达 agent-skill cross-encoder reranker。worker 仍在 capability 层安装
  纯透传观测，主轨任一非空 rerank 调用都会 fail-fast，防止未来 source/config drift 静默烧 API；
- `app_id=memorybenchmark`、`project_id=phase1`；
- smoke build LLM 为 `opencodego/deepseek-v4-flash`，official full 为
  `primary/gpt-4o-mini`。

secret/base URL 只经受限 worker 环境进入产品配置，不写 TOML、manifest、sidecar、stderr 或
artifact。embedding/rerank key 使用环境变量名 `EVEROS_DEEPINFRA_API_KEY`；当前环境没有该 key，
因此真实 smoke 未被误启动。

## 5. 五格输入契约

共同规则：一个 canonical session 一次 ingest；每个非空 event 恰好一条产品 message；不按位置
重新配对，不跨 session。完整异常处置见
[五格安全档案](everos-five-benchmark-safety-dossier.md)。

| Benchmark | role / owner / content | 时间与结构差量 |
| --- | --- | --- |
| LoCoMo | 与 current official harness 一致：两位真实 speaker 都是 `role=user`，各自 sender/owner；主轨检索所有 owner 后稳定合并 | session source time 起点，按 utterance `+30s`；shared caption helper 保留 image，不沿用官方 image-only 丢失 |
| LongMemEval | canonical user/assistant 原序、完整 session | assistant-first、same-role、singleton/odd tail 原样；纯 assistant session 只加一个空、无 source id 的结构 user owner anchor |
| MemBench | FirstAgent 拆分后的 child role 与 ThirdAgent user-only 原序 | 原 content 尾部 place/time 不删不重拼；100k noise 缺时只获 operational order time |
| BEAM | 四 variant canonical role/order 原样 | 10M orphan/mismatch 不修 raw、不位置重配；session 边界内使用 source time |
| HaluMem | 每 session 完整 role/content 一次 flush | public get 只读取该 product session 的 Episode，供 session report |

LoCoMo caption 经共享 helper 渲染为 `[Sharing image that shows: ...]`；path、query、locator 不进入
算法。gold answer/evidence、target ids、memory points/type、abstention 与 judge label 均不进入
worker request。

## 6. 时间语义

产品 DTO 强制正整数 Unix ms，而部分 benchmark 的 source time 合法为 `None`。adapter 将两层
语义分开：

1. source time 只按 `turn → 当前 session → None` 读取；不借 question time、兄弟 turn 或墙钟；
2. 缺失 source time 使用稳定 operational epoch+序号，只为满足产品排序/存储契约；
3. sidecar 逐 message 保存 source time、product ms 与 `timestamp_kind`；
4. 只要 Episode 所属 session 含 operational/derived time，或 Episode 已合并到无法回指的
   `session_id=None`，`RetrievedItem.timestamp=None` 且 `formatted_memory` 不渲染
   `product_time`；产品原时间只留在审计 metadata。

这关闭了一个审读时发现的双通道漏洞：旧实现虽然把公开 `timestamp` 置空，却又从 metadata
把派生时间写回 answer context；强反例现已锁死。

## 7. Completion、resume 与 cleanup

每次 session flush 后依次：

1. `OME.wait_idle(timeout)`；
2. 按 event 聚合所有 run：running、dead-letter、crashed、未恢复 failed 均失败；同 event 的
   failed→success retry 链合法；
3. `Cascade.sync_once()`，检查 operational health、pending、retryable/permanent failure；
4. 连续两次 `processed=0 && pending=0`；
5. 再次 OME idle/terminal，覆盖 Cascade 产生的传递任务。

成功后才写 sidecar 的 operation journal；相同 operation+input 直接复用，digest 漂移 fail-fast。
任何 ambiguous partial write 由 generic clean retry 删除整个 conversation 物理 root 后重建，
不猜测部分数据库状态。

cleanup 先核 root identity，再写独立 cleanup marker、rename tombstone、递归删除。即使进程在 rename
后或 rmtree 中途失败，下次也从同一受身份保护 tombstone 继续；不会把“live root 已不在原路径”
误报成清理成功。provider/runtime cleanup 均在成功后才提交 closed 状态。

## 8. Readout、metric 与 HaluMem

Episode formatter 保留 subject、summary、episode、atomic facts、score、product rank 和有资格的
source-derived time；zero hit 是 `items=()` + 明确 sentinel，backend/protocol error 一律抛出。

| 能力 | 裁决 |
| --- | --- |
| stable product ranking | valid：product rank 与确定性多-owner merge 均保留 |
| semantic provenance | N/A：Episode/atomic fact 是合成记忆，没有 lossless source-qrel 映射 |
| Recall/Precision/F1@k、NDCG | N/A；有检索接口不等于有语义 qrel 资格 |
| HaluMem extraction | valid candidate：每次 flush 后 public get 只读当前 session Episode |
| HaluMem update | valid candidate：probe query 读取累计 current product state |
| HaluMem QA | valid candidate：framework builder 消费同一 public HYBRID readout |
| HaluMem memory type | N/A：产品 `Conversation` 类型不等于 Event/Persona/Relationship gold taxonomy |

“candidate”表示离线产品链与 runner 接线已闭合；最终有效性仍由真实 B11 artifact gate确认。

## 9. Observability 与并行 ownership

worker 在 product singleton 上安装纯透传 wrapper：

- build LLM 从成功 `ChatResponse.usage` 读取 exact prompt/completion tokens；
- embedding 从成功 OpenAI-compatible response usage 读取 tokens，用 framework timer 记录 latency；
- reranker capability 先于 lazy `SearchManager` 安装透传 wrapper；当前 chat/Episode 主轨必须返回
  `rerank_observations=[]`，任一非空调用在 build/retrieval 均 fail-fast。公共效率协议不伪造
  rerank token，用零调用断言证明本 profile 没有隐藏外部 rerank；
- observation buffer 覆盖同步 ingest 与 exact-drained 后台任务，只有业务 operation 成功才回放；
- retrieval 单独记 embedding scope；HYBRID 若意外调用 LLM 或 reranker 会 fail-fast；
- answer/judge 继续走 framework 既有观测。

一个 provider 独占一个 worker/lifespan/root；generic isolated W2 建两套 provider、process 和物理
root。`supports_shared_instance_parallelism=false` 禁止同一实例并发，但 planner 允许 smoke W2
override。HaluMem operation runner 按固定协议保持 W1。

## 10. 离线验收与当前门

架构师在主树完成的离线验收如下：

- 扩展定向门（adapter、worker、五格 registered runner、HaluMem operation、registry、CLI、
  planner、ledger、效率公共门与文档标准）：`480 passed in 25.98s`；
- 全量：`2078 passed, 3 deselected, 13 warnings, 29 subtests passed in 127.82s`；13 个 warning
  全来自既有 vendored LightMem/MemOS 依赖；
- `python -m compileall -q src/memory_benchmark tests`、parent/nested `git diff --check` 与
  EverOS patch reverse-check 均为 exit 0；
- source identity：`48fc9084888bc17100053227284f939a5aca5e91`，14 个输入文件，digest
  `c921a23f1d339ef11b43d4dcd5241826967d2b918956c0565c2bef4b2bd5cea9`；
- 真实 official lifespan 零 API 探针通过，shutdown 多 failure 会 settle 后聚合上抛；
- 机器计划由 `plan-smoke` 生成并保存在
  [everos-smoke-plans-v1.json](everos-smoke-plans-v1.json)：9 个 croppable concrete variant
  各 W1/W2，2 个 HaluMem fixed variant 各 W1，共 20 份。

当前未关闭：

1. 真实 build/embedding/rerank/answer/judge API 与 20 份 artifact 尚未运行；
2. 真实 W2 资源峰值、usage 完整性与 multi-owner search 需开箱；
3. official full、作者 LoCoMo calibration 与效果实验不在本次批准门；
4. B11 通过前不得写 frozen note。

判词：

```text
READY_FOR_B11_REAL_SMOKE_APPROVAL(
  typed product lifecycle and exact completion are wired;
  five payloads, time semantics, cleanup and metric eligibility are explicit;
  no real API result is claimed
)
```
