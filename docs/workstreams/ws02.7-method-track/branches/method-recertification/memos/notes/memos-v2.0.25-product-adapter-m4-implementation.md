# MemOS v2.0.25 product v3 adapter M4 施工记录

日期：2026-07-27
分支：`actor/memos-v2-0-25-product-adapter-m4`（worktree `/Users/wz/Desktop/mb-actor-memos-adapter`）
基线：`main@130016e`

## 0. 判词

```text
READY_FOR_MEMOS_M5_PREFLIGHT(
  product runtime is reached without HTTP host;
  async completion and cleanup are exact;
  five benchmark input shapes are lossless;
  zero-hit is distinct from backend failure;
  metric eligibility is truthful
)
```

## 1. Source / patch / adapter identity

```text
upstream   https://github.com/MemTensor/MemOS.git
release    v2.0.25
commit     e820406269537b97d270687e3e40eea2f015f81a
patch      scripts/patches/memos-product-runtime-observability.patch
           sha256 5531e33f36e47413...（build_memos_source_identity() 现算）
adapter    src/memory_benchmark/methods/memos_adapter.py
           sha256 8e62d82aaf3e9539...（同上）
version    memos-v2.0.25-product-v1
identity   typed-product-handler
mode       vendored-memos-product-plus-patch-plus-wrapper
```

派发时一手核验（主树 nested repo）：

```text
git rev-parse HEAD           → e820406269537b97d270687e3e40eea2f015f81a
git describe --tags          → v2.0.25
git status --porcelain       → 仅 R2 patch 覆盖的 6 个文件 M
```

**首轮 reverse-check 曾失败**：该 patch 是 zero-context（`-U0`）生成，必须带
`--unidiff-zero`。加上该 flag 后 `git apply --reverse --check` exit 0。fetch 脚本
本来就用 `--unidiff-zero`，未受影响。

patch 更新后的等价判词（脚本化复核，两次都做过）：

```text
git archive HEAD | tar -x -C <tmp>          # clean v2.0.25
git apply --unidiff-zero <patch>            # exit 0
diff -r <tmp> third_party/methods/MemOS     # 唯一差异 MemOS.pdf（gitignored 论文附件）
→ EQUIVALENT
```

新 patch 现覆盖 7 个文件（R2 的 6 个 + `src/memos/api/config.py`），
`git diff --check` exit 0，仍是 zero-context，fetch 脚本仍只 apply 一次。

## 2. M4 新增的两个 patch hunk

只改**失败可见性**与**已有能力暴露**，成功路径算法与返回内容零变化。

### 2.1 `APIConfig.get_embedder_config()`

- 新增 `sentence_transformer` 分支，返回 `EmbedderFactory` 已原生支持的
  `backend / model_name_or_path / embedding_dims / max_tokens / trust_remote_code`；
- `else` 由「静默落入 Ollama」改为显式 `ValueError` fail-fast；
- `ollama`（含 env 未设的默认路径）与 `universal_api` 两个既有分支对象守恒——
  强反例逐字段比对整个返回 dict。

### 2.2 `SingleCubeView._search_text()`

- `except Exception` 保留原日志后 `raise`（原为 `return []`）；
- 非法 search mode 由 `return []` 改为 `ValueError`；
- 合法 backend 空结果仍是 `[]`（zero-hit 与 backend failure 就此可区分）。

## 3. Runtime / handler / namespace / lifecycle 图

```text
MemOS(provider)
 └─ _MemosRuntimeOwner（进程内、按 config identity 单例、RLock、可 reset）
     └─ MemosRuntime（每 provider 只构造一次）
         ├─ _scoped_environment(...)  # 安装非 secret 参数 + OpenAI settings
         │                            # 成功/失败都恢复 os.environ
         ├─ init_server()             # 唯一入口；不 import server_router
         ├─ HandlerDependencies.from_init_server(components)
         ├─ AddHandler / SearchHandler（共用同一 dependencies）
         └─ install_local_tracker(scheduler) → MemosLocalTaskTracker

ingest(SessionBatch)
 → 生成 business task_id: "{namespace}-s{session_slug}-{seq:06d}"
 → APIADDRequest(user_id=ns, writable_cube_ids=[ns], session_id=public,
                 async_mode="async", mode=None, task_id=business)
 → AddHandler.handle_add_memories()
 → tracker.wait_for_business_task(user_id=ns, business_task_id=..., expected=1)
 → failed / timeout / missing / multiple 全部 fail-fast；合法零抽取仍成功

cleanup()
 → owner.release(runtime) → runtime.close()
 → tracker.assert_no_pending_tasks() 先行；再 scheduler.stop() 恰好一次
 → 重复 cleanup 幂等，不二次 stop
```

namespace：

```text
mb + sanitize(isolation_key)[:24] + sha256(storage_root_relative|isolation_key)[:32]
```

`storage_root_relative` 是 storage_root 相对项目根的 posix 路径，已编码
`benchmark/variant/run_id`（以及 isolated 路径的 `worker_N`）。因此同一 conversation
的 add/search/clean 同 namespace；两个 conversation / 两个 run / 两个 worker 必不同。
只含 `[0-9a-z]`，无绝对路径、无 gold、无 question id、无随机 UUID。
storage_root 若不在项目根内则 fail-fast（否则 namespace 会带机器路径）。

## 4. 五格最终 payload 矩阵

每个保留 event 恰好一条 message，`{role, content, chat_time, message_id}`；
`chat_time` key 始终存在，无时间写显式 `None`。

| benchmark | role 来源 | content | chat_time | 反例覆盖 |
| --- | --- | --- | --- | --- |
| LoCoMo | `speaker_a→user` / `speaker_b→assistant`（与首发无关） | `"{真实 speaker}: {原文}[ Sharing image…]"` | turn→session | speaker_b 首发、逆序仍同映射、第三 speaker fail-fast、缺声明/同名 fail-fast、正文+caption / caption-only / 多 caption、无 path/query 泄漏、无 `(image description:)` 双拼 |
| LongMemEval | canonical role 原样 | 原文 | turn→session→None | assistant 开头、连续同 role、奇数尾、singleton session、跨 session 不合并 |
| MemBench | canonical role 原样 | 原文（尾部 place/time **保留**） | canonical 解析时间；100k noise `None` | 无 `[Turn time]` 二次前缀 |
| BEAM | canonical role 原样 | 原文 | session | canonical turn id（`raw_9/raw_3/raw_7`）进 message_id，不按 raw id 重排/配对，dangling 尾部保留 |
| HaluMem | canonical role 原样 | 原文 | session | 整 session 一批、task 与 session 一一对应、`session_memory_report=False`、`end_session()` 返回 None |

共同断言（五格 parametrize）：每个 canonical 非空 event 恰好一次、顺序全等、
每个 request 只带本 session 的 turn、`session_id` 对齐、无
`gold_answers/evidence/answer/answer_session_ids`、`info` 为空。

空 content event fail-fast（不制造 placeholder，也不落入 upstream `if content:`
丢 time/message_id 的分支）；非 LoCoMo 的非 canonical role fail-fast；
非 SessionBatch 单元 fail-fast。

## 5. search result → RetrievalResult 字段映射

| RetrievedItem | 来源 | 失败处理 |
| --- | --- | --- |
| `item_id` | memory `id` | 缺/空 fail-fast |
| `content` | memory `memory` | 缺/空 fail-fast |
| `score` | `metadata.relativity` | None 合法；非数值（含 bool）fail-fast |
| `timestamp` | `metadata.created_at` | 无则 None，不猜 |
| `source_turn_ids` | `metadata.sources[].message_id` | 保序去重；非 str/空跳过 |
| `metadata` | 公开审计字段 | 去 `embedding`、去不可序列化对象 |

`data["text_mem"]` 的多个 bucket 按产品返回顺序扁平化，**不**二次排序、**不** set 化、
**不**再截断一次（`top_k` 已由 handler 处理）。bucket 非 list / 非 mapping 均 fail-fast。
`formatted_memory` 只按该顺序连接 memory 文本；零命中用
`(No relevant memories found)`（framework 既有非空 sentinel 约定）。

`APISearchRequest` 精确锁定：`user_id/readable_cube_ids=[ns]`、`mode=fast`、
`top_k=query.top_k`、`relativity=0.45`、`dedup=mmr`、`rerank=True`、
`include_preference/search_tool_memory/include_skill_memory/neighbor_discovery/
internet_search` 全 False、`chat_history=[]`、`filter=None`、`session_id=None`、
`reference_time=query.question_time`。

**`reference_time` 一手核验**：全仓 `grep -rn "reference_time" src/memos/` 只有 1 处命中，
即 `product_models.py` 的 schema 定义；current search 代码零消费。因此忠实传入但公开
metadata 标 `reference_time_effect="declared_but_unwired_v2.0.25"`，不宣称时间过滤生效。

## 6. Clean retry 前后置条件

前置：本 process tracker 中该 namespace 无 pending task，否则拒绝删除（不发 delete）。

```text
DeleteMemoryRequest(writable_cube_ids=[ns], user_id=ns)   # memory_ids 保持 None
→ handle_delete_memories → data.status 必须 == "success"
→ handle_get_memories(mem_cube_id=ns, user_id=ns,
                      include_preference/tool/skill 全 False)
→ 每个 bucket 的 memories 为空且 total_nodes falsy
```

绝不 `delete_by_memory_ids()`，绝不无 namespace 清全库，handler failure 不当成功。
clean hook 与 factory 复用同一 config/namespace 算法，通过同一 `_MemosRuntimeOwner`
取 runtime，不会二次 `init_server()`。

**一处实现修正（由强反例发现）**：`TaskRecord.to_payload()` 不导出 `user_id`，只导出
`mem_cube_id`。首版按 `user_id` 过滤 pending，导致守门恒为空、形同虚设；
`test_clean_refuses_when_namespace_has_pending_tasks` 直接转红。已改为按
`mem_cube_id in (namespace, None)` 判定——本拓扑 namespace == user_id == cube_id，
且 `mem_cube_id` 缺失时作用域不可判定，对删除守门从严拒绝。

## 7. Metric valid / N/A / pending 矩阵

逐题 `RetrievalEvidence` 一律：

```text
semantic_provenance.status = pending
  reason_code = memos_generated_memory_semantic_lineage_unverified
provenance_granularity     = none
stable_ranking.status      = pending
  reason_code = memos_product_rerank_stability_unverified
```

理由：MemOS fine memory 是窗口生成物，`sources[].message_id` 只证明该 source
进入生成窗口，不证明生成后的 memory 仍语义承载每个 source fact；真实
Neo4j/Qdrant + MMR/rerank 的稳定次序尚未 B11 一手验证。零命中不改变这一静态事实
（有专门 parametrize 覆盖命中与零命中两种情况）。

| 格 | 结论 |
| --- | --- |
| 五 benchmark Recall / NDCG / stable ranking | pending |
| HaluMem QA | valid 候选，待真实服务 smoke |
| HaluMem extraction | **N/A** — async `MEM_READ` 未公开 task-scoped fine output；本卡不改算法/handler 返回值强行取出 |
| HaluMem update | pending — 普通 `memory_update_probe` 可检索 current memory 且忠实用 `query.top_k`（无 benchmark 特判），但资格待真实 DB smoke |
| HaluMem memory type | N/A — MemOS `Working/LongTerm/User/Outer` ≠ Event/Persona/Relationship |

注册：`provenance_granularity="none"`、`retrieval_evidence_contract_version="v1"`。

## 8. Registry / manifest / resume

```text
list_methods() → ['amem','lightmem','mem0','memoryos','memos','simplemem']
protocol_version                        v3
consume_granularity（五 benchmark 恒）  session
requires_api                            True
max_workers（smoke = official_full）    1
allow_smoke_worker_override             False
supports_shared_instance_parallelism    False
clean_failed_ingest_state               已注册
```

build identity：

```text
implementation_variant = product
embedding_profile      = controlled_embedding_v1
embedding              = sentence_transformer / models/all-MiniLM-L6-v2 / 384
                         / local_unpinned / model_pipeline_l2 / qdrant-cosine
historical_controlled_build_equivalent_to_current_main = false
```

`normalization` **不是猜的 `internal_l2`**，而是 source-proven：
`SenTranEmbedder.embed()` 调 `model.encode(texts, convert_to_numpy=True)`，
**不**传 `normalize_embeddings`（MemOS 自身不归一化）；受控 MiniLM 目录的
`modules.json` 含 `2_Normalize`，故 L2 来自模型 pipeline。记为
`model_pipeline_l2` 以区别于「method 代码内归一化」。
`distance=qdrant-cosine`：`get_neo4j_community_config()` 里 `distance_metric`
硬编码 `"cosine"`。

model inventory 三条，本地 reranker 不伪装成 LLM：
`memos-build-llm`(api, gpt-4o-mini) / `memos-embedding`(local, 384) /
`memos-reranker`(local, cosine_local)。

instrumentation identity 显式带 `exact_api_usage="pending_m5_preflight"`：
MemOS current `OpenAILLM.generate()` 返回纯文本并丢掉 response usage，async worker
脱离 framework question context，**不**用 add pair 数或 `len(text)/4` 伪造。

resume 身份：`to_manifest()` 含全部 build/search/lifecycle 参数 + `adapter_version`；
7 个参数变化的 parametrize 断言 manifest 必变。

## 9. 偏差与设计裁决

1. **`*_env` 字段改名**（唯一实质偏差）。卡 §4.2 允许 config 用 `*_env` 引用 secret、
   manifest 只写环境变量名。但 framework 既有 manifest secret 扫描
   （`prediction.py` `forbidden_fragments = ("api_key","secret","password")`）
   会拒绝**任何**含这些片段的 key，包括只存变量名的 `graph_db_password_env`。
   放宽该守门属于隐私边界变更，按 `AGENTS.md` 必须经架构师 review，因此**不动守门**，
   改为把字段命名为 `graph_db_credential_env` / `vector_db_credential_env`
   （值仍是 `MEMOS_NEO4J_PASSWORD` / `MEMOS_QDRANT_API_KEY` 这两个变量**名**）。
   若架构师认为 `*_env` 应被白名单豁免，可另开一卡改守门。
2. **worktree 资产软链/拷贝**：`third_party/methods/MemOS` 与 `models/` 都是
   gitignored、只存在于主树。`PathSettings.resolve_third_party_method_path()`
   会 `.resolve()` 后做包含性检查，软链会被判定「escapes methods root」，
   因此 MemOS 采用 `rsync`**拷贝**（排除 `.git`，33M），`models/` 采用软链
   （该路径只做 `.is_dir()`，不触发包含性检查）。两者都未进 git（已用
   `git status --short` 复核）。
3. **patch 复现测试改写**：worktree 内的 MemOS 拷贝没有 `.git`，原先基于
   `git archive` 的 clean-checkout 测试会 skip。改为「只复制 patch 触及的文件 →
   reverse-apply 还原 clean → forward-apply → 与 vendored 树逐字节比对 →
   再次 forward-apply 必须被拒」，不依赖 nested `.git`，在拷贝环境同样有效。
   主树上基于真实 `git archive` 的等价判词已在 §1 手工完成。
4. 允许清单外文件零改动；`memos_lifecycle.py`（R2 产物）只读消费，未修改。

## 10. 停工点

无。卡 §6 列出的停工条件均未命中：current source 未推翻 §4 锁定身份；
未改任何 async 成功路径 / reader / extraction / search / rerank 算法；
未扩 allowlist（改名在允许文件内）；source lock 与 patch 全程可解释；
clean retry 做到 namespace-scoped + readback empty；generic cleanup 未破坏
legacy / operation-level 语义（有专门反例）；全程零真实 API/DB/模型/网络。

「真实服务隔离、stable ranking、精确 token usage 仍 pending」按卡要求不作停工，
它们是 M5 入口。

## 11. Mutation 结果

每处修复各做一次「去掉 → 转红 → 恢复 → 转绿」，临时变体未提交：

| mutation | 转红用例 |
| --- | --- |
| 删除 `sentence_transformer` 分支 + 还原 unknown backend 静默落 Ollama | `test_sentence_transformer_branch_returns_exact_controlled_fields`、`test_sentence_transformer_config_is_accepted_by_real_factory_schema`、`test_unknown_embedder_backend_fails_fast`（3 failed, 1 passed） |
| `_search_text` 还原为吞错 `return []` + 非法 mode `return []` | `test_search_backend_failure_propagates_instead_of_zero_hit`、`test_unsupported_search_mode_fails_fast`（2 failed, 4 passed） |
| `_cleanup_memory_provider` 变 no-op | `test_shared_v3_provider_is_cleaned_up_once_on_success`、`..._on_ingest_failure`、`..._on_answer_failure`、`test_cleanup_failure_is_visible_and_run_is_not_completed`、`test_cleanup_failure_preserves_primary_exception_context`、`test_isolated_worker_v3_provider_is_cleaned_up_once_per_worker`、`..._on_failure`（7 failed, 2 passed） |

恢复后复核：worktree MemOS 拷贝与主树 patched 源逐字节一致；
主树 nested repo 对新 patch 的 `--unidiff-zero --reverse --check` exit 0。

## 12. 定向自检尾行

```text
uv run pytest -q tests/test_memos_lifecycle.py tests/test_memos_adapter.py \
  tests/test_memos_registered_prediction.py tests/test_method_registry.py \
  tests/test_prediction_runner.py tests/test_prediction_cli.py \
  tests/test_documentation_standards.py

356 passed, 10 warnings in 6.92s
```

```text
git diff --check
exit=0
```

10 个 warning 全部是既有的 MemOS `datetime.utcnow()` deprecation 与 MemOS config
Pydantic serialization warning，与 R2 验收 note 记录的 warning 画像一致；
无 `PytestUnraisableExceptionWarning`。

未跑全量 pytest / compileall / 真实 API 或服务（卡 §7 明确限定）。
`compileall` 只对本次改动的两个文件做过语法检查，未做全仓。

## 13. 仍然 pending（交 M5 preflight）

- 真实 Neo4j/Qdrant 跨 namespace 隔离与 MMR/rerank stable ranking；
- window-generated memory 的 semantic provenance 与 Recall/NDCG 资格；
- HaluMem update current-state 与 QA 的真实服务 smoke；
- MemOS async worker 的精确 per-call token/cost 观测；
- official LoCoMo 双 namespace reproduction harness（主 profile 仍一 conversation 一 cube）；
- 跨 conversation 并行资格（首版 workers=1、禁 smoke override、禁共享实例并行）；
- 依赖/服务：Neo4j community + Qdrant server + `sentence-transformers` 运行时依赖，
  以及 `MEMOS_NEO4J_PASSWORD` / `MEMOS_QDRANT_API_KEY` 两个环境变量，
  都要在 M5 preflight 前落地。

---

# M4-R1 返工记录（生命周期闭环）

日期：2026-07-27
follow-up commit 基线：`a87353a`

上文 §1–§13 是首轮 `a87353a` 的原始记录，**保留原样**（含当时的偏差与输出）；
本节只追加架构师强验收后关闭的两个生命周期缺口与两组漏测。

## R1.0 判词

```text
READY_FOR_MEMOS_M4_ARCHITECT_RECHECK(
  cleanup refusal is retryable;
  early failures cannot leak the shared runtime;
  environment scope and typed-handler sharing are proven
)
```

## R1.1 缺口一：cleanup 状态“先提交后执行”导致孤儿 runtime

`a87353a` 的三处都在**成功之前**就提交了状态：

| 位置 | 首轮写法 | 后果 |
| --- | --- | --- |
| `_MemosRuntimeOwner.release()` | 先 `self._runtime = None`，锁外再 `runtime.close()` | close 被拒 → owner 丢引用 |
| `MemOS.cleanup()` | 先 `_cleaned = True`、`_runtime = None`，再 release | 拒绝后无法重试 |
| `MemosRuntime.close()` | 先 `_closed = True`，再 `stop()` | stop 抛错仍被标成已关闭 |

修复统一为**成功后才提交**，并把 `close()` 移进 owner 锁内以满足裁决 §2.1.5
（close 未完成时并发 `acquire()` 不得构造第二个同 config runtime）。
`MemosRuntime` 另加 `_stop_attempted`：`stop()` 抛错照常上抛（失败可见），
但重试不会二次调用同一 scheduler 的 `stop()`。

架构师原探针在修复后的输出（同一命令口径）：

```text
FIRST_CLEANUP_ERROR: ConfigurationError MemOS scheduler 仍有 1 个未完成 task，拒绝静默关闭
AFTER_FIRST:            {'provider_cleaned': False, 'provider_runtime_is_none': False,
                         'owner_runtime_is_none': False, 'runtime_closed': False, 'stop_calls': 0}
AFTER_RETRY:            {'provider_cleaned': True,  'provider_runtime_is_none': True,
                         'owner_runtime_is_none': True,  'runtime_closed': True,  'stop_calls': 1}
AFTER_IDEMPOTENT_RETRY: {'provider_cleaned': True,  'provider_runtime_is_none': True,
                         'owner_runtime_is_none': True,  'runtime_closed': True,  'stop_calls': 1}
```

即：拒绝前后引用全保留 → task 转终态后重试真正 close → `stop()` 总计恰好一次 →
再次 cleanup 幂等。

## R1.2 缺口二：clean-hook → 根 provider 的单 runtime 交接

新增窄方法 `_MemosRuntimeOwner.release_current_for_config(config)`：

```text
owner 为空        → no-op 返回 None（绝不为 cleanup 反向构造 runtime）
identity 一致     → close 并释放，返回该 runtime
identity 冲突     → ConfigurationError fail-fast，绝不关闭别的配置
```

`MemOS.cleanup()` 在 `self._runtime is None` 时走该路径，因此
「clean hook 用临时 provider 先 lazy 建好共享 runtime、根 provider 自己从未
`_require_runtime()`」的边界也能收敛。未改成「clean hook 成功后立即 close 再让正式
ingest 第二次 `init_server()`」——首轮裁决要求 clean 与正式 run 复用同一 runtime。
未引入第二套全局缓存、弱引用注册表或 benchmark 特判。

## R1.3 缺口三：generic runner 保护区起点

`a87353a` 的保护区只包住 ingest/answer；clean hook、checkpoint preflight 与
work-plan 都在保护区之前。改为：

- `use_isolated` 计算上移到 clean hook 之前；
- 用 `contextlib.ExitStack` 在**前置阶段之前**注册 `_cleanup_memory_provider`；
- 正常路径在原完成点（`Completed` stage 之前）显式 `lifecycle_stack.close()`，
  `close()` 会弹出回调，因此 context 退出时不重复；
- isolated 路径不注册根 system；legacy bridge 与 operation-level 语义不变。

`git diff -w` 显示该文件的实质改动仅为：`import contextlib`、`use_isolated` 上移、
ExitStack 包裹与注册、原 `try/finally` 移除、完成点显式 `close()`。

## R1.4 漏测一：环境作用域恢复

新增 hermetic 反例（fake `init_server`，零真实服务）：

- 预置「将被覆盖」的 `MOS_CHAT_MODEL=preexisting-model`、
  `MEMSCHEDULER_USE_REDIS_QUEUE=true`、无关键 `MEMOS_ONLY_PREEXISTING=keep-me`，
  并确保 `MOS_EMBEDDER_BACKEND` / `MOS_EMBEDDER_DIMS` / `NACOS_ENABLE_WATCH` /
  `NEO4J_PASSWORD` 原先不存在；
- 作用域内断言 config/OpenAI/secret 精确可见（含
  `OPENAI_API_KEY=sk-super-secret`、`NEO4J_PASSWORD=super-secret-neo4j`）；
- 成功与 `init_server()` 抛错两种情况都断言 `dict(os.environ) == before`：
  被覆盖的回原值、原先不存在的重新消失；
- 抛错时断言 secret 不出现在异常文本中；
- 另补：secret 只从声明的环境变量名读取，缺失时 fail-fast。

## R1.5 漏测二：真实 `MemosRuntime.__init__` 装配面

穿过真实 `MemosRuntime.__init__`（只 fake 外部组件叶子）断言：

- `init_server()` 恰好一次；
- 真实 `AddHandler` 与 `SearchHandler` 的 `.deps` 是**同一** `HandlerDependencies`
  对象，且就是 `runtime.dependencies`；
- `scheduler` / `naive_mem_cube` / `tracker` 都来自同一 bundle，
  `scheduler.status_tracker` 与 `dispatcher.status_tracker` 是同一个 tracker；
- `memos.api.routers.server_router` 仍未被 import。

该用例暴露了真实装配面的一手事实（首轮 `_FakeRuntime` 覆盖不到）：
`SearchHandler` 还要求 `searcher` / `deepsearch_agent`，`AddHandler` 还要求
`mem_reader` / `feedback_server`；且 current `BaseHandler` 把依赖存成 `.deps`
而非 `.dependencies`。测试的叶子集合按 current `_validate_dependencies` 对齐。

## R1.6 顺带修掉的测试隔离缺陷

首轮 `tests/test_memos_adapter.py` 里只有请求 `memos_product_models` 的用例才做
MemOS import 引导，其余 provider 级用例隐式依赖同文件执行顺序——按 node id 单独跑
`test_one_session_batch_emits_one_add_request_and_one_terminal` 会
`ModuleNotFoundError`。已加 module 级 autouse 引导 fixture 消除该顺序依赖；
两个用例现在单独跑也通过（`2 passed`）。

这不是本卡缺口，但属于同一允许文件内我自己引入的脆弱点，一并修正并在此披露。

## R1.7 Mutation 结果

| mutation | 转红用例 |
| --- | --- |
| 还原「close 前先清 owner/provider 引用」（即 `a87353a` 顺序） | `test_cleanup_refusal_keeps_every_retryable_reference`、`test_cleanup_succeeds_after_task_reaches_terminal_with_single_stop`、`test_scheduler_stop_failure_is_visible_and_owner_keeps_reference`、`test_root_provider_closes_runtime_created_by_clean_hook`、`test_root_cleanup_fails_fast_on_conflicting_owner_identity`（5 failed, 76 passed） |
| 把 runner lifecycle guard 移回 clean hook / preflight 之后 | `test_clean_hook_failure_still_cleans_up_shared_provider_once`、`test_checkpoint_preflight_failure_still_cleans_up_shared_provider_once`（2 failed, 129 passed） |

两次 mutation 后都已恢复并复跑绿。临时变体未提交。

## R1.8 定向自检尾行

```text
uv run pytest -q tests/test_memos_adapter.py tests/test_prediction_runner.py \
  tests/test_memos_registered_prediction.py tests/test_memos_lifecycle.py

270 passed, 10 warnings in 5.92s
```

10 个 warning 仍是既有 MemOS `datetime.utcnow()` deprecation 与 MemOS config
Pydantic serialization warning，与首轮及 R2 验收 note 一致。

未跑全量 pytest、compileall、真实服务/API/模型（本卡 §5 限定）。

## R1.9 偏差与停工点

无停工点。改动严格限于本卡 §3 允许的 5 个文件；未触碰 CLI、registry、
provider protocol、vendored MemOS、patch、TOML 与其他测试。

一处需架构师知悉的实现选择：`MemosRuntime` 新增 `_stop_attempted`，使
`stop()` 抛错后重试 `close()` 不再二次 stop。裁决 §2.1.6 只要求「错误可见 +
不丢孤儿」，未规定重试是否应再次 stop；此处按「同一 scheduler 不重复 stop」取舍，
若架构师希望重试时重新 stop，可在复核时改判。
