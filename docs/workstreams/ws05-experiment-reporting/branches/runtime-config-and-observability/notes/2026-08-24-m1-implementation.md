# M1：配置组合根与 controlled embedding 实现

日期：2026-08-24
状态：`ACCEPTED_BY_M5_NO_API_REGRESSION`
边界：零真实 API；没有改写旧 artifact，也没有把 v6 EverOS 状态重标成 v7。

## 1. 结果

十家 method 的主算法参数已从两份重复的 `[smoke]` / `[official_full]` 收敛到一份
`[method]`。`smoke`、`pilot`、`official_full` 现在选择的是独立 API runtime 与 execution
profile；benchmark answer/judge 继续由 benchmark 注册层拥有。一次 run 的公开组合身份完整进入
manifest/resume，provider、model、request policy、structured-output mode、execution timeout 和
并发默认值发生变化时均不能静默续跑。

旧 checkout/测试 fixture 若仍只有 `[smoke]` / `[official_full]`，loader 会严格回读对应旧 section；
current TOML 一旦存在 `[method]` 就不会再读取旧双 section。旧 artifact 仍按原 manifest
artifact-only 回读，不做就地升级。

## 2. 配置所有权

- `configs/methods/<method>.toml`：upstream 公开且会改变 method/product 行为的参数；
- `configs/runtime/api.toml`：API provider/model、timeout/retry、structured-output transport；
- `configs/execution/prediction.toml`：conversation worker 默认值、worker/drain/task/startup timeout、
  method stdout policy；
- benchmark evaluation：answer/judge builder、prompt、decode、parse 与 metric policy。

现有 adapter dataclass 尚保留少量 runtime/execution constructor 字段。registry 的 composition root
只把目标 dataclass 实际声明的字段显式注入，并在公开 method config manifest 中剔除这些兼容绑定；
这是一条有退出门的 schema 迁移桥，不允许 runtime 字段重新写回 method TOML。新增架构测试会拒绝
current method 主 section 出现通用 API、worker、timeout 或 answer-builder 字段，也拒绝
`smoke/pilot/official_full` 算法双轨复活；稀疏 `author_<benchmark>` 仍被允许。

## 3. Embedding 主比较

- A-Mem、Graphiti、LangMem、LightMem、Mem0、MemoryOS、MemOS、SimpleMem 保持实际消费的
  `all-MiniLM-L6-v2` / 384；provider、normalization、distance 等产品差异继续单独盖 identity。
- Letta current profile 只读 attached core blocks，显式 `embedding_config=None` 且
  `skip_vector_storage=True`。run identity 新增 `not_applicable_v1`，所有 concrete embedding 字段
  必须为 null；不得用假 MiniLM 填表。
- EverOS 从远端 Qwen/1024 切到本地 MiniLM/384。该变化要求新 run-id 与全量重建；旧 v6
  Qwen artifact 永久按原 identity 回读，不能 resume 到 v7。

## 4. EverOS public seam 与可重放 patch

EverOS upstream 已公开 `EmbeddingProvider` protocol 与进程级 `EmbeddingCapability`。v7 worker 在
官方 `create_app()` lifespan **之前**把本地 SentenceTransformer provider 注入该 capability；
此后 Cascade、LanceDB 与 HYBRID SearchManager 仍走官方产品链，没有直接写库或另造检索器。

upstream v1.2.3 的六张 LanceDB 表把向量宽度写死为 1024，且 OpenAI provider factory 默认参数也
固定 1024。项目新增
`scripts/patches/everos-configured-embedding-dimension.patch`，使 provider 与六张 schema 表共同读取
公开 `embedding.dimensions`；默认未配置时仍保持 upstream 1024。patch 不改变 chunk、Cascade、
Episode、distance、search method 或 rank。`scripts/fetch_third_party_methods.sh` 可在 clean
`48fc908` 上依次重放 observability patch 与 dimension patch。

v7 使用 `scripts/requirements/everos-controlled-embedding.txt` 锁定的本地 overlay，其中
`sentence-transformers==5.5.1`、`torch==2.12.0`、`transformers==5.9.0`。该解析唯一升级的
upstream 共享依赖是 `click 8.3.3→8.4.2`，因为 `huggingface-hub==1.28.0` 明确要求
`click>=8.4.2`；版本已显式锁定并进入 source identity，不是运行时 resolver 漂移，也不参与
memory pipeline。`scripts/bootstrap_everos_runtime.sh` 安装并核版本。模型目录必须位于
`models_root`，worker 强制
HF/Transformers offline。模型自身含 Normalize module，因此 LanceDB L2 在受控向量上与 cosine
排序单调等价；manifest 仍诚实写 `model-internal-l2 + lancedb-l2`，不把两者混成相同实现。

效率观测现在只声明两类真实消费者：build LLM 的 response usage，以及本地 embedding 的实际
tokenizer 输入量与 wall-clock latency。reranker 保持 product capability `None`；若 ambient 配置
意外启用 reranker，worker 在 SearchManager 构造前 fail-fast。

## 5. 零 API 验收证据

- clean detached upstream 依次应用两份 patch，reverse-check、`git diff --check` 与 current vendored
  九个目标文件逐字比较：`EVEROS_PATCH_REPLAY_OK`；
- EverOS Python 3.12 隔离环境 bootstrap：`EverOS runtime ready`；
- 本地 MiniLM 两条文本：两条 384 维向量、L2 norm≈1，tokenizer observation 非空：
  `EVEROS_LOCAL_MINILM_PROBE_OK`；
- 六张真实 LanceDB schema：`agent_case/agent_skill/atomic_fact/episode/foresight/knowledge_topic`
  均解析为 384：`EVEROS_LANCEDB_SCHEMA_DIMENSION_OK`；
- 不可达 dummy API URL 下进入官方 `create_app()` lifespan 并正常 shutdown，未发生网络调用：
  `EVEROS_ZERO_API_PRODUCT_LIFESPAN_OK`；
- EverOS/config/registry/CLI 定向门：`227 passed`；
- 十五份 registered prediction 回归首轮仅一处旧 expected 缺 composition，新语义未失败；修正后
  对应用例 `1 passed`，M5 将再跑完整集合与全量门。

## 6. 重建与停手线

EverOS adapter/worker identity 由 v6/protocol-v2 升为 v7/protocol-v3，source identity 同时哈希两份
patch、bootstrap 与 wrapper。所有旧 Qwen/1024 product root 不得复用。此前 18 份 v6 smoke 仍是
冻结历史证据，但不证明 v7 controlled build；v7 真实 smoke/pilot 要等 M5 无 API 门关闭并由用户
重新批准规模/run-id 后另跑。

本批没有启动 pilot、answer/judge、memory-build API，也没有修改 metric 资格。
