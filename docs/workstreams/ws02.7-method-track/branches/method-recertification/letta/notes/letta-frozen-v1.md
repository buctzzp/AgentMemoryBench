# Letta/MemGPT method-frozen-v1

日期：2026-08-12

架构师：GPT-5.6 sol

方法身份：legacy Letta `0.16.8` 内核 + official `ai-memory-sdk v0.2.0` 产品契约

adapter：`letta-sleeptime-product-v2`

状态账：[Letta/MemGPT Method Integration Ledger v1](./letta-integration-ledger.md)

## 0. 冻结判词

```text
LETTA_METHOD_FROZEN_V1(
  product_surface = in-process SyncServer + managers + AgentLoop,
  storage = one owner-labelled PostgreSQL volume per run runtime,
  isolation = one tagged subject/agent per conversation,
  input = session, at most 10 canonical messages per SDK wrapper,
  placeholders = none,
  readout = query-independent all attached public core blocks,
  provenance_and_ranking = N/A for evolved core blocks,
  workers = W1-only with pre-runtime W2 rejection,
  halumem = extraction N/A, update and QA valid, memory-type N/A
)
```

`method-frozen-v1` 证明 current source、产品调用链、五格输入与 readout、11 份极小真实
smoke、artifact/效率/隐私门和代码回归闭合。它不表示极小样本可用于效果排名，也不把
active Letta Code、HTTP/cloud 产品或 direct archival memory 冒充本轨算法。

## 1. 冻结身份与产品边界

| 项 | 冻结值 |
| --- | --- |
| upstream | `https://github.com/letta-ai/letta.git` |
| legacy release / commit | `0.16.8` / `1131535716e8a31c9a437f8695e25ac98f203a24` |
| vendored pin | `b76da9092518cbaa2d09042e52fdcbde69243e18` |
| product contract | `ai-memory-sdk v0.2.0@4494e004...` |
| license | Apache-2.0 |
| product entry | direct in-process `SyncServer`、manager 与 `AgentLoop.step()` |
| storage | `ankane/pgvector:v0.5.1`；每个 run runtime 一个 owned named volume |
| build LLM | smoke=`opencodego/deepseek-v4-flash`；official-full=`primary/gpt-4o-mini` |
| embedding | N/A / `None` |
| answer/judge | benchmark unified builder；Letta 无 Phase 1 官方 benchmark harness |

worker 只隔离 legacy dependency graph；算法仍穿过同一产品内核。active Letta Code
`v0.30.1` 是 `ALGORITHM_VARIANT`；direct archival insert/search 是
`MECHANISM_BYPASS`。current official repos 没有 Phase 1 五 benchmark 的完整 harness，故五格
都是 product-faithful framework extension，不虚构 `author_<benchmark>`。

## 2. B0-B11 对表

| 门 | 结论 | 冻结证据 |
| --- | --- | --- |
| B0 official harness | `closed / N/A payload` | 六个 current official repo 均无 Phase 1 harness；主轨只复用 official sleeptime SDK formatter 与产品调用图 |
| B1 source/product | `closed` | legacy source、SDK contract、direct product core 与变体边界均锁定 |
| B2 granularity | `closed` | session 内原序；每批最多 10 message；singleton 合法；无 placeholder、不跨 session |
| B3 isolation/parallel | `closed` | run runtime 独占 DB volume；conversation 独占 tagged subject/agent；W2 在 runtime/API 前拒绝 |
| B4 input/readout | `closed` | role/speaker/content/time/place/caption 沿 canonical→SDK wrapper 实证；全部 attached public core blocks 进入 answer context |
| B5 provenance/rank | `closed as N/A` | evolved blocks 无 source-exact semantic lineage；query-independent 全量 readout 不是 top-k ranking |
| B6 completion | `closed` | official Run `create→step(run_id)→terminal`；异常与 usage 缺失均 fail-fast |
| B7 observability | `closed` | build exact provider usage；retrieve 零 LLM/embedding；answer/judge scope 与 operation runner manifest 实测 |
| B8 side effects/resume | `closed` | retrieve 只读；两阶段 journal；pending 拒绝重放；namespace-safe clean retry |
| B9 identity | `closed` | source/wrapper/API runtime/build/answer/judge identity 入 manifest；secret/base URL 不落 artifact/log |
| B10 TOML/builder | `closed for main` | smoke/official-full 两主 section；五格统一 benchmark builder；无 author section |
| B11 smoke/freeze | `closed` | 11 份 current machine plan、17 conversation/question、全 evaluator、artifact machine gate 与最终代码门 |

## 3. 五 benchmark 主轨与真实 smoke

| Benchmark | 主轨输入与异常处置 | current 真实 run | 资格边界 |
| --- | --- | --- | --- |
| LoCoMo | 固定 `speaker_a→user`、`speaker_b→assistant`；真实 speaker 前缀、time 与共享 caption wrapper；未知 speaker 拒绝 | `letta-locomo-v3-r1q1-w1` | retrieval lineage/rank N/A；answer/judge 与离线指标可算 |
| LongMemEval | raw role/order；assistant-first、连续同 role、singleton/奇数尾不修复；session 内只作产品 batch 切分 | S/M 各一份 W1 | Recall/NDCG N/A；judge 与 answer 指标可算 |
| MemBench | First canonical child role 保真；Third user-only；原 place/time 文本不删、typed time 不重复；100k missing time 保持 None | 0-10k/100k 各一份 W1 | retrieval metric N/A；source accuracy 与 answer 指标可算 |
| BEAM | 四 variant 原 canonical id/role/order；10M orphan/mismatch 不补写或位置重配 | 100k/500k/1m/10m 各一份 W1 | Recall N/A；rubric judge 可算 |
| HaluMem | fixed 四 session 原序；private memory point 不进 build；current blocks 进入 update/QA | Medium/Long 各一份固定 W1 | extraction N/A；update/QA valid；memory-type N/A |

current machine plan 是
[`letta-smoke-plans-v3.json`](./letta-smoke-plans-v3.json)。11 份 plan 共 17 个 conversation、
17 个 public question。旧 v1 失败资产只保存 Docker、PostgreSQL readiness、official Run lifecycle
与 OpenCodeGo 403 的阶段证据；`predict smoke` 不支持 resume，current v3 全部使用新 run identity，
没有拼接失败 checkpoint。

## 4. Artifact、效率、隐私与外部状态机器门

机器逐 run 核对 plan/root、manifest/source/wrapper、API runtime、完整 efficiency identity、公开
question/prediction/answer context、private-label 负空间、evaluator score/summary、operation sidecar、
日志与所有 Letta-owned Docker 资源：

```text
LETTA_B11_CURRENT_ARTIFACT_GATE_PASS
{"all_owned_volumes": 30, "answer_calls": 17, "build_calls": 45,
 "conversations": 17, "current_runs": 11,
 "current_secret_or_endpoint_hits": 0, "current_volumes": 11,
 "historical_letta_secret_or_endpoint_hits": 0, "judge_calls": 24,
 "owned_containers": 0, "private_workspace_url_hits": 0,
 "questions": 17, "superseded_preserved_volumes": 19}
```

- 11 个 current run 对应 11 个 owner-labelled volume；当前没有 owned container 残留。
- 19 个旧 volume 来自 superseded/失败身份，按审计资产保留，未误算为 current state，也未擅删。
- build 45、answer 17、judge 24 均由 artifact observation 实数聚合，不由 add/session 数推测。
- BEAM 1M 一题有 event-equivalence 与 rubric 两次 judge，是 evaluator 的真实调用拓扑，不是重复计费。
- HaluMem update 请求 top-k=10、QA=20；extraction/memory-type 的 N/A/null 传播正确。
- 所有 question 的 `answer_context` 与真实 `formatted_memory` 一致且非空；产品 readout 不泄露
  query/private gold。
- current 与历史 Letta 输出中，API key、base URL 和私有 workspace URL 命中均为零。

## 5. 真实运行暴露并关闭的问题

1. **PostgreSQL readiness 竞态**：容器内裸 `pg_isready` 会误认初始化临时 Unix server；改为
   最终 TCP 地址执行 `SELECT 1`。
2. **official Run lifecycle**：真实 `AgentLoop.step()` 要求 `run_id`；现严格执行
   `create→step→terminal(success/failure)`，失败 metadata 只留异常类型。
3. **OpenCodeGo 403**：账户区域 opt-in 是外部门；解除后用 fresh v3 identity 跑通，不 resume
   旧失败 smoke。
4. **answer context 元数据**：BEAM/HaluMem builder 虽已把 memory 写入 prompt，旧 metadata 未写
   `answer_context`；现补齐该公共观测字段，不改变 prompt 字节。
5. **operation efficiency identity**：operation runner 旧 manifest 少于 generic runner；现复用同一
   contract builder，模型 inventory、instrumentation/version 与 resume identity 对齐。
6. **第三方日志脱敏**：Letta/httpx 日志可能回显 endpoint；worker 在产品构造前安装 handler
   filter，parent stderr tail 再做第二层 key/base URL 脱敏，历史失败日志也已清除私密 URL。
7. **执行纪律**：曾手抄 planner 命令加入非法 shape 参数，CLI 在 runtime/API 前正确拒绝；current
   v3 全部直接执行 planner `argv`。这不是 method regression，但已升格为长期规则。

## 6. 冻结后声明缺口与解冻条件

1. W2 为产品所有权未证下的 N/A；不能复制共享 runtime 假装 parallel support。
2. evolved core blocks 不能无损映射 source gold unit，Recall/Precision/F1@k、NDCG 与 stable
   ranking 继续 N/A。
3. HaluMem 没有 product-level session-local delta，extraction 与依赖它的 memory-type N/A；
   current-state update/QA 不受连坐。
4. 五格无 current official harness，主表是 product-faithful framework extension；未来新增官方
   harness 时需单独审计 author calibration，不能暗改主配置。
5. smoke 只证明可达性，不证明效果。official-full、真实 resume、成本 pilot、全量效果与论文/产品
   数字对表仍未执行。
6. named PostgreSQL volume 是本机外部 resume 状态；只复制 `outputs/` 到另一机器不足以 resume。
7. legacy source、SDK formatter、core-block readout、API runtime、wrapper hash、worker ownership、
   benchmark canonical contract 或 metric 资格任一实质变化，均触发版本化解冻与影响分析。

## 7. 最终验收门

同批冻结提交前现场结果：

- Letta/runner/prompt 定向门：`240 passed in 9.97s`；
- ledger/doc 最终门：`11 passed in 1.16s`；ledger validator `methods=5` PASS；
- 全量 pytest：`2145 passed, 3 deselected, 13 warnings, 29 subtests passed in 154.02s`；
- compileall：`exit 0`；
- `git diff --check`：`exit 0`；
- Letta-owned container 残留：`0`；current/superseded volume 账：`11 / 19`。

冻结证书只为 current identity 背书；任何极小 smoke 分数都不得进入效果排名或预算外推。
