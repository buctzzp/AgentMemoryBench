# M1：十家配置字段 census 与迁移账

日期：2026-08-24
状态：`READY_FOR_TYPED_COMPOSITION_ROOT`
边界：current source/TOML 静态审计；零真实 API、零 artifact 改写。

## 1. 判定方法

每个字段只允许一个 owner：

- **method**：upstream 公开 seam 暴露、会改变记忆构建/更新/检索语义或产品实现选择；
- **API runtime**：provider/model/base URL/credential/timeout/retry/request capability；
- **benchmark evaluation**：answer/judge builder、decode、parse 与 benchmark 官方口径；
- **execution**：workers、进程/队列/启动/排空超时、日志输出治理与裁剪。

一个字段“当前写在 method dataclass”不等于它天然属于 method。迁移也不把值写死进代码：
composition root 必须组合强类型对象，并把公开身份写进 manifest/resume；secret 继续只从环境读取。

## 2. 共同迁移项

十个 TOML 都重复 `[smoke]` 与 `[official_full]`。除下列差异外，算法字段逐字相同：

- 十家生成模型均为 `ox-alpha-free` 对 `gpt-4o-mini`；归 API runtime；
- 九家 `max_workers=1` 对 `10`，Letta/MemOS 两侧均为 `1`；归 execution；
- EverOS embedding provider/credential 与 rerank capability 随 provider 能力变化；这不是两套主算法，
  而是 current runtime 尚未提供统一本地 embedding/rerank transport 的缺口；
- Graphiti `structured_output_mode=json_object/json_schema` 是 provider capability adapter；归 runtime
  compatibility，prompt/解析与图算法不变。

共同字段迁移：

| current 字段 | 目标 owner | 迁移规则 |
| --- | --- | --- |
| `answer_builder` | benchmark evaluation | 从 method section 移入组合 envelope；作者 builder 只在显式 `author_<benchmark>` profile 出现 |
| `llm_model` / `extraction_model` / `reader_model` | API runtime | method 只声明算法角色；实际 provider/model 由 runtime 注入并盖 manifest |
| `api_timeout_seconds` / `api_max_retries` 与通用 backoff | API runtime | 使用一个强类型网络 policy；产品确有不同 retry 算法时才保留 method override |
| `max_workers` | execution | CLI 显式 override 优先，否则从 execution profile 取；不再经 method getter |
| `worker_request_timeout_seconds` / `task_timeout_seconds` / `drain_timeout_seconds` | execution/lifecycle | 保持分方法默认值，但 owner 是 execution，不复制成 smoke/full 算法参数 |
| `suppress_official_stdout` | execution observability | 由统一日志策略注入；不进入 method 算法身份 |
| `*_credential_env`、DB host/port/URI/user/name、container image/startup timeout | runtime infrastructure | manifest 只写非 secret endpoint/driver identity；credential 值永不落盘 |

## 3. 逐家 method-owned 字段

下表只列迁移后仍应由 method config 拥有的主字段；embedding 完整 identity 另在 §4 盖章。

| method | method-owned 主字段 | 备注 |
| --- | --- | --- |
| A-Mem | `retrieve_k`, `use_product_layer` | product layer 是 implementation identity；stdout 开关移出 |
| EverOS | `memory_mode`, `search_method`, `add_batch_size`, embedding/rerank build choice | `app_id/project_id` 是 namespace/runtime identity，不是算法超参 |
| Graphiti | `llm_temperature`, `llm_max_tokens`, embedding build, `query_limit` | `structured_output_mode` 随 provider capability；`max_coroutines` 归 execution，但必须盖执行身份 |
| LangMem | embedding build, `query_limit`, `max_steps`, `enable_inserts`, `enable_deletes` | update policy 属算法；worker timeout 移出 |
| Letta | `context_window`, `max_tokens`, `temperature`, `max_steps`, `max_messages_per_batch`, block limits | 这些是 official agent/product 配置；Postgres lifecycle 移出；embedding 为 N/A |
| LightMem | embedding/LLMLingua build、retrieve/extract/update 阈值、compression/STM/topic/summary、lifecycle、timestamp policy、`messages_use` | stdout、API policy、workers 移出 |
| Mem0 | embedding build、`top_k`, `ingestion_chunk_size`, `infer` | extraction/reader 实际模型由 runtime 注入；若两角色未来分模型，runtime 显式声明两个 role binding |
| MemoryOS | embedding build、三层容量/阈值、retrieval top-k | `longmemeval_prompt_profile` 是未清完的 benchmark-specific readout debt，M1 不把它误归成通用算法字段 |
| MemOS | embedding/memory/reader/reranker backend，async/reorganize/search/dedup/rerank/include/discovery policy | DB endpoints/credentials 与 task timeout 移出；并发 dispatch 会影响 lifecycle，保留 method 语义身份而非通用 worker 数 |
| SimpleMem | embedding build、window/overlap、三路 top-k、planning/reflection 与 product parallel-processing/retrieval 开关 | product 自身并行开关可能改变调度/结果，仍属 method；框架 conversation workers 另归 execution |

## 4. controlled embedding 迁移矩阵

| method | current | M1 动作 |
| --- | --- | --- |
| A-Mem / Graphiti / LangMem / LightMem / Mem0 / MemoryOS / MemOS / SimpleMem | 实际消费 MiniLM-384 | 保持数值；补齐 revision/tokenizer/instruction/normalization/distance 的 concrete identity 与 resume 门 |
| EverOS | Qwen3-Embedding-4B/1024，经 OpenAI-compatible remote seam | 先实现受控 MiniLM-compatible provider，闭合 384 dimension 与 distance；全量重建后才切主配置 |
| Letta | current core-block profile 不消费 embedding | 显式 N/A；不得写假 MiniLM identity |

MiniLM 的“同模型”只解决 backbone 公平性，不抹平各产品的 chunk、index、distance 或 normalization。
这些差异必须留在 identity 中，不能用一个 `embedding_model` 字符串覆盖。

## 5. 迁移与退出门

实施分三步，禁止一次大爆炸式改写：

1. 新建强类型 runtime/execution composition 对象；新 run 同时写 composition v1 identity，旧
   `smoke/official_full` section 仍能严格读取；
2. 各 method dataclass 逐家移除 runtime/execution 字段，TOML 收敛到一份 `[method]`；每迁一家都用
   old/new 等价 fixture 证明生产 payload 与算法 manifest 不变；
3. 十家迁完、registry getter 清零、resume mismatch 门转绿后，才删除旧 section loader。旧 artifact
   永久按原 v1 identity 只读回放，不做就地升级。

M1 不顺带修改 metric 资格、算法默认值或真实 run。EverOS 的 provider 实现若不能无损提供
MiniLM-384，就保留 pending/product-default 补充轨，而不是为了完成表格强改第三方算法。
