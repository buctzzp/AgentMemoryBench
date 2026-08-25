# A-Mem 接入实例（B1-B11）

> adapter：`src/memory_benchmark/methods/amem_adapter.py`
>
> 状态：**`method-frozen-v1`**。2026-08-21 冻结后差量审计发现 runtime evidence stamp
> 与 B5 的 N/A 裁决矛盾；现已把 semantic provenance 改为 N/A/none，同时独立保留
> stable product ranking=valid，B5/GRID 小修关闭且无需重烧 build smoke。
>
> 当前新 smoke/ws05 pilot 使用 `opencodego/ox-alpha-free`；既有冻结 run 仍按
> `gpt-4o-mini` 历史身份解释。现行运行身份见
> [`../api-runtime-profiles.md`](../api-runtime-profiles.md)。

> **历史 artifact 边界**：小修前的 artifact 可能仍写
> `semantic_provenance=valid + provenance_granularity=turn`；它们只按当时 manifest 回读，
> 不得据此补算 Recall/Precision/F1/NDCG，也不改写历史文件。

> **ws05.1 source/profile 边界（2026-08-25）**：`method-frozen-v1` 只说明现有
> `agiresearch/A-mem@ceffb860` controlled product profile 已通过五格运行门，不等于论文结果
> 复现身份已认证。论文 v11 链接的 `WujiangXu/A-mem-sys@f303dfc` 在真实 neighbor id、
> metadata-enhanced embedding 与 auto-analysis 上不同；LoCoMo GPT-4o-mini paper k 还是按类别
> `40/40/50/50/40`，不是主配置 10。完整证据见
> [`amem-profile-provenance.md`](../../workstreams/ws05.1-method-profile-provenance/notes/amem-profile-provenance.md)；
> M11 已裁定不静默换源且仍为 `AUTHOR_NOT_READY`。主配置改用内容锁定的项目本地 MiniLM，
> 新 run 以 7-file `amem-product-main-v2` source closure + run identity v2 生成，历史 build 不宣称
> 等价、不得 resume。收据见
> [M11 implementation](../../workstreams/ws05.1-method-profile-provenance/notes/m11-effective-config-source-embedding-implementation.md)。

## 接口调用面

| framework | A-Mem 产品调用 | 裁决 |
|---|---|---|
| `ingest(TurnEvent)` | `AgenticMemorySystem.analyze_content()` + `add_note()` | turn；不配 pair，不造 placeholder |
| `retrieve(RetrievalQuery)` | `search_agentic(query, k)` | 只读产品 Chroma + linked neighbors；framework 自己回答 |
| `end_session` | 读取本 session 新 note delta | HaluMem extraction 可测 |
| `end_conversation` | pickle note + JSON lineage | resume 不重跑 LLM |
| clean retry | 删除该 conversation 独占 state dir | 物理隔离 |

## 产品接口契约（参数、返回与批次）

完整跨 method 粒度矩阵见
[`../method-interface-inventory.md`](../method-interface-inventory.md)。A-Mem 的产品入口不是
list batch：框架五格均以 `TurnEvent` 调一次 `ingest()`，每个真实非空 turn 恰好创建一条
新 `MemoryNote`，不配 pair、不造 placeholder。

| 产品调用 | 参数类型与本项目传值 | 产品返回 | adapter 映射 |
| --- | --- | --- | --- |
| `AgenticMemorySystem.analyze_content(content: str) -> dict` | `content` 是已渲染 speaker/role、图片 caption 的单 turn 文本 | `dict`，期望 `keywords: list[str]`、`context: str`、`tags: list[str]`；产品失败时会给空/General fallback | adapter 要求返回 dict，并把固定失败 sentinel 升格为异常；存在的三个键再作为下一步 `add_note(**analysis)` metadata，不直接公开 |
| `add_note(content: str, time: Optional[str] = None, **kwargs) -> str` | `content: str`；`time` 取 `turn → session → None`；`kwargs` 传上一步 metadata | 新 `MemoryNote.id: str`；写入 current memory、Chroma 与 evolution links | `IngestResult(unit_ref=UnitRef(...))`；note id→source turn id 进入审计 sidecar，HaluMem 边界可据新 id delta 生成 `SessionMemoryReport` |
| `search_agentic(query: str, k: int = 5) -> list[dict[str, Any]]` | `query=query.query_text`，`k=query.top_k` | 有序列表；每项至少可含 `id/content/context/keywords/tags/timestamp/category/score/is_neighbor` | 强校 list，保留产品顺序与 score，构造 `tuple[RetrievedItem, ...]` 和完整 `formatted_memory` |

`retrieve(RetrievalQuery) -> RetrievalResult` 的逐项 `source_turn_ids` 只保留“参与过演化”的
审计 lineage。current memory 的 content/context/tags/links 可能已被后续 turn evolution，故
`semantic_provenance=n_a`、`provenance_granularity=none`；`search_agentic()` 的产品返回顺序
未被 adapter 重排，所以 `stable_ranking=valid`。这两个 assertion 彼此独立。

## B1-B11

- **B1 ✅（current controlled product）**：`third_party/methods/A-mem-product` 锁
  `agiresearch/A-mem@ceffb860f0712bbae97b184d440df62bc910ca8d`，MIT；现有 artifact 按此
  identity 回读。它不再被表述成唯一“论文官方产品”；paper-linked source 的差异留 M11 裁决。
- **B2 ✅**：五格均 turn ingest；LoCoMo speaker name，其余 canonical role；无 pair 约束。
- **B3 ✅**：每 conversation 独占 persistent Chroma；100-evolution consolidation 仍落回同一
  scoped retriever；clean retry 物理删除。
- **B4 ✅**：content/role/speaker/caption 无损；typed time 走
  `turn → session → None`；formatted_memory 回带 time/context/keywords/tags。
- **B5 ✅（retrieval qrel metric=N/A）**：Chroma 检索对象是 evolution 后的当前
  `MemoryNote`，其 links/context/tags 已不是原始 dataset turn；即使 content/id/source time
  字段仍稳定，sidecar 也只能证明该 turn 参与过生成，不能把当前记忆重新解释成原始 evidence。
  因此 Recall@K/Precision@K/F1/NDCG 不运行、不报告；sidecar 只用于审计、HaluMem delta 与
  隔离验货。runtime、registry、manifest 与零 API 强反例现均声明 N/A/none；排序 assertion
  仍独立为 valid，不推翻 B1-B4/B6-B11，也不要求重烧 build smoke。
- **B6 ✅**：add_note 同步完成 note 写入与 evolution；无待 flush 的 buffer。
- **B7 ✅**：build LLM、embedding、retrieval 与 framework answer 真实 observation 可落盘。
  2026-08-21 的 ox 真实 run `ws05-ox-p1-amem-locomo-r2` 已证明 memory-build 与 answer
  均读取 SDK `response.usage`，而不是把 tokenizer estimate 当 API 真值。ox 对
  `json_schema` 的“HTTP 成功但不遵守 schema”仅在 A-Mem 发送边界降为 `json_object`；
  prompt、分析字段与其他 provider 保持不变。
- **B8 ✅**：检索只读；官方 swallow-error 两处在 wrapper fail-fast；endpoint/timeout/retry 注入。
- **B9 ✅**：`gpt-4o-mini` + product-default MiniLM-384/Chroma cosine；revision 诚实 unpinned。
- **B10 ✅（主表隔离）**：主 TOML 跨五 benchmark 固定；作者 LoCoMo builder/复现参数不混入
  主表。author profile 尚未完成，不能从“未混入”推导出“已经可复现论文”。
- **B11 ✅**：最终主树全量 `1680 passed`、compileall 0；五 benchmark 共 11 个真实 run
  覆盖 W1/W2、BEAM 100K/10M、HaluMem extraction/update/QA/type，artifact/state/
  efficiency 机器门全部通过；冻结记录见
  [`amem-frozen-v1.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/amem/notes/amem-frozen-v1.md)。

实现与算法证据见
[`amem-official-product-r1-implementation.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/amem/notes/amem-official-product-r1-implementation.md)。
