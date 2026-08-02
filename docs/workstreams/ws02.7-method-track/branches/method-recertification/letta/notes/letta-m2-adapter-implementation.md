# Letta/MemGPT sleeptime-memory product adapter M2 实现记录

日期：2026-08-02
状态：`READY_FOR_B11_REAL_SMOKE_APPROVAL`
adapter：`letta-sleeptime-product-v1`

## 1. 结论

Letta 主轨已经从 source/product identity 落成可运行的 provider v3 adapter，并通过
零外部 API 的真实 PostgreSQL migration、`SyncServer`、sleeptime agent、core blocks、
namespace 删除和进程清理验证。它不是 HTTP client，也不是 archival vector-store 替代品：
独立 Python 3.12 worker 内直接调用 legacy Letta V1 `0.16.8` 的产品内核，复现 official
`ai-memory-sdk v0.2.0` 的 message wrapper、memory-only agent 与 core-block readout。

当前结论是“可申请 B11 真实 smoke”，**不是冻结**。真实 build LLM、framework answer LLM、
judge、artifact 开箱与最终全量门仍待用户按 planner 给出的预算、规模和 run id 单独批准。

## 2. 主调用图

```text
generic / operation-level runner
  └─ provider.prepare(RunContext)                    每个有工作项的 runtime 一次
      └─ LettaRuntime.ensure_started()
          ├─ 校验 vendored Python 3.12 runtime
          ├─ 创建/验证 owned pgvector volume + container
          ├─ CREATE EXTENSION IF NOT EXISTS vector
          ├─ alembic upgrade head
          └─ 启动 JSON-lines worker
              ├─ SyncServer(init_with_default_org_and_user=False)
              ├─ default organization / actor / base tools
              └─ OpenAI transport + exact usage observer

SessionBatch ingest
  ├─ ensure_subject(subject_id)
  │   ├─ AgentType.sleeptime_agent
  │   ├─ human(10000) + summary(1000)
  │   ├─ memory_finish_edits / insert / replace / rethink
  │   ├─ embedding_config=None
  │   └─ 唯一 initializer passage（embedding=None）
  ├─ canonical events → official role/content messages
  ├─ 当前 session 内按最多 10 message 切 batch
  ├─ sidecar pending_operation_id 原子落盘
  ├─ AgentLoop.step(MessageCreate(role="user", content=wrapper, otid=operation_id))
  ├─ 验收 end_turn/tool_rule + step_count + 每次 API usage
  └─ sidecar completed_operation_ids 原子提交

RetrievalQuery
  └─ query 不送进 Letta
      └─ 读取全部 attached blocks → 按 (label,id) 稳定排序 → formatted_memory

provider.cleanup()
  └─ worker shutdown → close_db → 删除 owned container；保留 labeled volume 供 resume
```

独立 worker 只解决依赖树和 Letta 进程全局状态隔离。它不是第二套算法服务；stdio 只是本机
窄协议，业务调用仍落到同一个 `SyncServer`、manager 与 `AgentLoop`。

## 3. 运行接口与数据契约

### 3.1 `ensure_subject`

输入只有 opaque `subject_id`。返回并写入 sidecar：

```json
{
  "subject_id": "...",
  "agent_id": "agent-...",
  "block_ids": ["block-human", "block-summary"],
  "archive_id": "archive-..."
}
```

worker 用 `runtime_tag + subj:{subject_id}` 双 tag 查找唯一 agent；已存在资源的 agent type、
完整 LLM config、embedding、tool set、block label/description/limit、唯一 archive、SDK initializer
与 tags 任一漂移均 fail-fast。adapter 还会把 ensure/ingest/readout 返回的 subject、agent、archive、
block id 与 sidecar 交叉验证，防止协议污染把另一个 namespace 的资源注入当前答案。

### 3.2 `ingest`

adapter 传入 `subject_id / operation_id / content`。`content` 是 official SDK formatter 的完整
字符串：

```text
<messages>The following message interactions have occured:
user: ...
assistant: ...</messages>
```

worker 返回 `subject identity + stop_reason + usage[] + step_count`。usage 必须来自 provider
真实响应；Chat Completions 的 `prompt_tokens/completion_tokens` 与 Responses 风格的
`input_tokens/output_tokens` 都映射为逐调用 observation，缺失、布尔或负数立即失败。

### 3.3 `read_blocks`

输入 `subject_id + sidecar agent_id`；返回每个 attached block 的
`id/label/description/value`。它不接受 query、top-k 或 question time，不调用 LLM/embedding，
也不读取 archival passages。adapter 以 XML-like block 包装形成 framework answer builder
可直接消费的 `formatted_memory`。

### 3.4 `delete_subject`

clean retry 先验证 sidecar 与真实 agent/archive/block 集合一致，再拒绝删除任何仍有外部 owner
的 block/archive；随后依次删 agent、独占 archive、orphan blocks，并重新按 subject tags 验证
agent 已不存在。只有 worker 返回 `{"deleted": true}` 后才删除 sidecar。

## 4. 五 benchmark payload 裁决

共同规则：`consume_granularity=session`；一个 canonical 非空 event 恰好生成一条 message；
session 内至多 10 条一批，不跨 session，不补 placeholder，不重新排序。source time 唯一顺序为
`turn → session → None`，从不借 question time、相邻消息或 wall clock。

| Benchmark | role / speaker | content 与时间 | 已知异形处置 |
| --- | --- | --- | --- |
| LoCoMo | 从公开 `speaker_a/speaker_b` 固定映射为 `user/assistant`；content 保留真实 speaker 前缀 | `[Turn time]`，无 turn time 时 `[Session time]`；图片统一追加 `[Sharing image that shows: ...]` | 不按首发猜 role；speaker 缺失、相同或出现第三 speaker 均拒绝；gold evidence 异常永不进 method |
| LongMemEval | 保留 canonical user/assistant 原 role 与原序 | turn time 优先，通常回落 session time | assistant-first、连续同 role、singleton/奇数尾原样保留；blank 已由稳定 benchmark contract 处理，不制造假回复 |
| MemBench | FirstAgent pair 已在 canonical 层拆成两个 child turn；ThirdAgent 保持 user-only | 原 content 尾部 place/time 保留；严格 boolean marker 防止重复前缀；100k noise 为 None | 不把 question time 当 message time；gold 越界/缺失只在 evaluator-private group contract 处理 |
| BEAM | 保留 canonical user/assistant；不按 raw id 配对 | 有 source time 才前置，无则 None | 10M 两处 orphan/mismatch 原样进入同一 session；不位置重配、不补 placeholder；canonical turn id 不依赖重复 raw id |
| HaluMem | 保留 canonical user/assistant | 每 session source time 进入每条 message | 固定 operation 顺序；extraction N/A，current-state update 与 QA valid，memory-type 因 extraction N/A 而 N/A |

五格完整异常、隐私与失效触发器见
[Letta 五格安全档案](letta-five-benchmark-safety-dossier.md)。

## 5. Readout 与 metric 资格

Letta 的主产品输出是持续改写的 `human/summary` core blocks，不是 query-ranked source items：

| 能力 | 判词 | 理由 |
| --- | --- | --- |
| 五格 Recall/Precision/F1@k | N/A | 当前 block 无法无损拆回 benchmark gold evidence unit |
| LongMemEval NDCG / stable ranking | N/A | readout 是全部 blocks 的展示顺序，不是 query rank |
| HaluMem extraction | N/A | 产品没有公开 session-local 新 memory point/delta |
| HaluMem update | valid | 官方按更新后的 memory content 查询**当前系统记忆**再判替换正确性；演化 block 正是被评对象，不要求 source lineage |
| HaluMem QA | valid | framework answer builder 消费当前全部 blocks |
| HaluMem memory type | N/A | composite 依赖 extraction；Letta block label 也不是 Event/Persona/Relationship |

这订正了 M1 的初判：M1 把 update 与 extraction 一起要求 session-local delta，实际官方
`evaluation.py` 的 update 路径消费 search/readout 的 current state。`RetrievalEvidence=N/A`
只否定 source-qrel/rank 指标，不能连坐否定 HaluMem update。

## 6. Resume、失败与清理

### 6.1 两阶段 operation journal

每批 wrapper 的 operation id 由 adapter version、subject、session、batch index 与 wrapper hash
确定性生成：

1. product 调用前写 `pending_operation_id`；
2. 只有 terminal、step count 与完整 usage 都验收后，才移动到 `completed_operation_ids`；
3. 已完成批重放直接跳过，不重复写；
4. 存在 pending 表示“产品可能已写但框架未确认”，禁止猜测重放，必须先走 conversation
   namespace clean retry，再由 runner 从头重放。

这不声称 Letta 的 `otid` 本身提供 durable dedup；防重事实由 framework sidecar 明确承担。

### 6.2 外部状态 ownership

- container 与 volume 名来自不含 secret 的 runtime identity，并带 owner/runtime 双 label；同名
  无标签对象一律拒绝接管或删除；
- worker 环境采用 allowlist，不继承宿主任意数据库/API secret；build key 只以
  `MEMORY_BENCHMARK_LETTA_BUILD_API_KEY` 进入 worker，并只在一次 `AgentLoop.step` 最窄作用域
  临时映射为 `OPENAI_API_KEY`；
- 正常 close 删除 container、保留 volume 供同 run resume；cleanup 失败不提交 `_closed`；
- W2 未证明，TOML 强制 `max_workers=1`，registry 禁止 smoke worker override，planner 在启动
  runtime/API 前拒绝 `--workers 2`。

## 7. 观测身份

model inventory 只有 `letta-build-llm`，角色为 `memory_build_llm`，无 embedding model。
instrumentation identity 同时哈希 adapter、worker 与 vendored source，并声明：

```text
exact_api_usage            worker_openai_response_usage_v1
build_llm_response_contract
  provider-aware-v1:opencodego=chat_completions+thinking_disabled;
                    primary=chat_completions+provider_default
retrieval_observation      core_block_read_wall_clock_v1
```

`opencodego/deepseek-v4-flash` 只在 smoke 使用；worker 对该 provider 追加
`thinking={type: disabled}`。`primary/gpt-4o-mini` 的 official_full 不追加该字段。二者 transport
身份进入 manifest/resume，不允许混分。

## 8. 验证记录

### 8.1 零 API product proof

使用 localhost 拒绝连接端点和假 key，实际运行 Docker pgvector、Alembic、`SyncServer`、
sleeptime agent、blocks、initializer passage、namespace delete 与 `close_db`；没有调用
LLM/embedding：

```text
LETTA_ZERO_API_PRODUCT_CHAIN_PASSED
{'agent_id_stable': True, 'block_labels': ['human', 'summary'], 'namespace_deleted': True}
```

该证明在 worker env allowlist 与上述完整资源身份校验落地后重新执行，仍逐字通过。证明结束后
owned container 与 volume 均已清除，Docker owner label 查询为空。

### 8.2 离线强反例

当前定向集合覆盖 config 漂移、pgvector migration 前置、worker env secret 负空间、两种 usage
格式、五格 registry/payload、LoCoMo image/speaker/time、MemBench time 去重、role 异形、10+1
batch、operation journal、clean retry、query-independent readout、HaluMem operation route、runner
prepare/cleanup 与 isolated RunContext。

扩展定向命令覆盖 Letta 三份测试、registry、generic/operation runner、prediction/main CLI、
smoke planner、ledger、artifact evaluator、HaluMem evaluator 与文档门，尾行为：

```text
458 passed in 9.94s
```

主树全量：

```text
1968 passed, 3 deselected, 13 warnings, 29 subtests passed in 131.45s (0:02:11)
```

13 个 warning 均为既有 vendored LightMem Pydantic 与 MemOS datetime/Pydantic serialization
warning；无新增 Letta warning。随后 `python -m compileall -q src/memory_benchmark tests`、
`git diff --check`、plan JSON parse 与 ledger validator 均为 exit 0。vendored identity 现场复核：

```text
commit=b76da9092518cbaa2d09042e52fdcbde69243e18
file_count=20
source_sha256=f1746df1f16f52eb8d951b0473f59d13f72c541cfd5b6cfc0593787f8e64461d
```

nested repo 唯一状态是用户放入且明确排除 source identity 的论文 PDF；无 tracked diff。本文仍只
声明 M2 offline acceptance，不把上述结果冒充 B11 real smoke。

## 9. 机器 smoke 计划

`plan-smoke` 已对 11 个 concrete variant 全部生成并审阅；原始 JSON 保存在
[`letta-smoke-plans-v1.json`](letta-smoke-plans-v1.json)。所有运行固定 W1。croppable 格为
history=1 / isolation=1 / question=1；HaluMem 保持注册表 fixed 4-session / 1-isolation /
1-question，未误传通用裁剪参数。multi-variant method 使用共同 base run id，child 后缀由
planner 追加；run id 与 evaluator 清单见安全档案 §8。

## 10. 未关闭项

1. 用户尚未批准真实 build/answer/judge API 预算与 run ids；
2. B11 artifact gate、真实效率 observation、实际 block 学习效果尚未开箱；
3. `official_full` 与任何效果型 run 尚未执行；
4. W2 是明确未支持能力，不以“两个 provider 对象”外推；
5. PostgreSQL named volume 是本机外部状态，跨机器只复制 `outputs/` 不足以 resume；缺 volume
   时 sidecar/agent identity 会 fail-fast，但正式长期保存策略留到 full-run 运维批次。

判词：

```text
READY_FOR_B11_REAL_SMOKE_APPROVAL(
  product surface direct and source-locked;
  five payload paths lossless within the declared product contract;
  current-state update and QA valid, extraction/ranking metrics N/A;
  zero-api product chain and failure boundaries proven;
  real API artifacts not yet claimed
)
```
