# M5 无 API 验收与重建矩阵

日期：2026-08-24
状态：`READY_FOR_USER_PILOT_RULING`

## 1. 验收结果

全程未调用真实 API、未创建新实验 output、未修改旧 artifact。

| 门 | 结果 |
| --- | --- |
| 本批 34 个 changed/new test 文件 | `875 passed in 26.48s` |
| 架构边界 + 文档标准 + current TOML/profile 门 | `24 passed in 4.47s` |
| `python -m compileall -q src/memory_benchmark tests` | exit 0，无输出 |
| 首轮全量 | `3 failed, 2256 passed, 3 deselected, 29 subtests passed` |
| 三条旧口径测试定点迁移后 | `110 passed in 1.01s` |
| 最终全量 | `2259 passed, 3 deselected, 25 warnings, 29 subtests passed in 251.14s` |

首轮三个失败都不是生产回归：两条 MemoryOS、一条 LightMem 测试仍直接调用低层
`load_typed_profile(..., "smoke"/"official_full")`，要求 current method TOML 保留已退出的双 section。
修复没有恢复重复配置，而是让测试走公开 `resolve_method_profile()`：公开 profile 名保持
`smoke/official-full`，method section 单一为 `method`，API runtime 与 execution 由组合根注入；
两条 profile 的 `method_config_manifest` 必须相同。

25 个 warning 均来自既有第三方 Pydantic/`datetime.utcnow()`、CLI deprecation 与 MemOS serializer；
没有 `PytestUnraisableExceptionWarning`，没有网络失败或真实 secret 读取导致的失败。

## 2. 零成本契约哨兵

- **manifest/resume**：`test_run_profiles.py`、`test_run_identity.py`、`test_prediction_cli.py` 与
  registered-prediction 全家锁定 composition v1、runtime provider/model/request policy、execution、
  embedding identity 与旧 manifest mismatch；旧 artifact 只能 artifact-only 回读。
- **模型阶段与失败成本**：collector/storage、prediction/evaluation、operation-level 与
  worker-transport 测试锁定 build/retrieval/answer/judge stage，API 失败已发生的 spend 进入
  append-only attempt ledger，算法状态回滚不能抹账。
- **HaluMem session delta**：LangMem 读产品 changed items；Letta 用 crash-safe core-block
  before/after；MemOS 在 async terminal 后做 stable-ID 全产品 delta；MemoryOS 保持 N/A。fake 与
  registered operation-level 路径均覆盖，不用 raw input 或 lineage 伪造 memory point。
- **secret 负空间**：runtime manifest 只写 provider/model/transport 与 credential env 名；worker
  payload、attempt ledger、error、method state 和 artifact 对 key/base URL value 保持负空间。
- **Letta embedding N/A**：`not_applicable_v1` 要求 provider/model/dimension/revision/normalization/
  instruction/distance 全为 null；任何 concrete embedding 字段混入均 fail-fast。

## 3. Current pilot build identity

零 API机器解析十家 `pilot` profile：全部使用 `opencodego/ox-alpha-free`，当前 execution 默认
worker=1。embedding 结果如下；“历史等价”只说明 controlled memory-build 内容是否可能与 current
主配置等价，**不**授权旧 artifact 静默 resume 到 composition v1。

| method | embedding profile | provider / model / dim | historical controlled equivalent |
| --- | --- | --- | --- |
| A-Mem | `product_default_v1` | sentence-transformers / all-MiniLM-L6-v2 / 384 | true |
| EverOS | `controlled_embedding_v1` | sentence-transformers-local / local MiniLM / 384 | false |
| Graphiti | `controlled_embedding_v1` | sentence-transformers-local / local MiniLM / 384 | false |
| LangMem | `controlled_embedding_v1` | sentence-transformers-local / local MiniLM / 384 | false |
| Letta | `not_applicable_v1` | N/A / N/A / N/A | false（不消费 embedding，不是待补） |
| LightMem | `product_canonical_required_config_v1` | huggingface-local / local MiniLM / 384 | true |
| Mem0 | `controlled_embedding_v1` | huggingface / all-MiniLM-L6-v2 / 384 | false |
| MemoryOS | `product_default_v1` | sentence-transformers / all-MiniLM-L6-v2 / 384 | true |
| MemOS | `controlled_embedding_v1` | sentence-transformers-local / local MiniLM / 384 | false |
| SimpleMem | `controlled_embedding_v1` | sentence-transformers-local / local MiniLM / 384 | true |

EverOS 是硬重建：v6 Qwen/1024 与 v7 MiniLM/384 的产品状态不可复用。其余 method 即使上表为
true，也必须使用新 run-id：旧 run 缺 composition v1 或 current run identity，且 state 路径按 run
scoped；本批不设计“借旧 memory、补新 manifest”的旁路。历史 artifact 永久按原身份可读。

## 4. 新 run-id 计划

若用户批准恢复一个完整 isolation pilot，使用统一模板：

```text
ws05-rco-v1-<method>-<benchmark>-<variant>-p1
```

其中 `rco-v1` 表示 runtime-config-observability v1，`p1` 表示首个新身份 pilot，不复用 2026-08-21
及更早的 run-id。variant 必须显式保留，例如 `longmemeval-m-cleaned`、`beam-100k`、
`membench-0-10k`、`halumem-medium`；LoCoMo 使用 `locomo10`。每个 method × benchmark 独立 root，
禁止把不同 dataset variant 塞进同一 run。

建议恢复顺序不是一次放飞 50 格：

1. 先选一条 controlled MiniLM 方法和 Letta N/A 各跑一个最小完整 isolation，验证新 manifest、
   efficiency 与 attempt ledger；
2. 再按 M4 资源类分批：W1-only/Docker、local-embedding、普通 API-only；全局 API semaphore 保持
   受控，资源 admission 不等同于 CLI worker；
3. 每批验收后再扩到下一批。任何失败先检查 append-only attempt ledger 与 clean retry，不能换
   run-id 掩盖半写状态。

本 note 只给出可审计方案，不构成真实 API、规模或 run-id 的自动授权。
