# A-Mem 接入实例（B1-B11）

> adapter：`src/memory_benchmark/methods/amem_adapter.py`
>
> 状态：current product/source、输入、lifecycle 与既有 smoke 资产仍保持
> `method-frozen-v1`；2026-08-21 冻结后差量审计发现 runtime evidence stamp 与 B5 的
> N/A 裁决矛盾，故**仅 B5/GRID retrieval eligibility 临时重开**。
>
> 2026-08-21 后的新 smoke 改用 `opencodego/mimo-v2.5`；既有冻结 run 仍按
> `gpt-4o-mini` 历史身份解释。现行运行身份见
> [`../api-runtime-profiles.md`](../api-runtime-profiles.md)。

> **当前红点**：adapter 与既有测试/LoCoMo artifact 实际声明
> `semantic_provenance=valid + provenance_granularity=turn + stable_ranking=valid`；但产品检索
> 对象是 evolution 后的 current memory，sidecar id 不能证明它仍是原 dataset turn。
> 在小修关闭前，所有 provenance-qrel retrieval metric 仍按 N/A 解释；旧 artifact 只按旧
> adapter identity 回读，不得据其 `valid` stamp 补算 Recall/Precision/F1/NDCG。

## 接口调用面

| framework | A-Mem 产品调用 | 裁决 |
|---|---|---|
| `ingest(TurnEvent)` | `AgenticMemorySystem.analyze_content()` + `add_note()` | turn；不配 pair，不造 placeholder |
| `retrieve(RetrievalQuery)` | `search_agentic(query, k)` | 只读产品 Chroma + linked neighbors；framework 自己回答 |
| `end_session` | 读取本 session 新 note delta | HaluMem extraction 可测 |
| `end_conversation` | pickle note + JSON lineage | resume 不重跑 LLM |
| clean retry | 删除该 conversation 独占 state dir | 物理隔离 |

## B1-B11

- **B1 ✅**：官方通用仓库 `third_party/methods/A-mem-product`，upstream
  `ceffb860f0712bbae97b184d440df62bc910ca8d`，MIT；不用 LoCoMo 复现 engine。
- **B2 ✅**：五格均 turn ingest；LoCoMo speaker name，其余 canonical role；无 pair 约束。
- **B3 ✅**：每 conversation 独占 persistent Chroma；100-evolution consolidation 仍落回同一
  scoped retriever；clean retry 物理删除。
- **B4 ✅**：content/role/speaker/caption 无损；typed time 走
  `turn → session → None`；formatted_memory 回带 time/context/keywords/tags。
- **B5 🟡（目标裁决仍为 retrieval metric=N/A；runtime stamp 待修）**：Chroma 检索对象是 evolution 后的当前
  `MemoryNote`，其 links/context/tags 已不是原始 dataset turn；即使 content/id/source time
  字段仍稳定，sidecar 也只能证明该 turn 参与过生成，不能把当前记忆重新解释成原始 evidence。
  因此 Recall@K/Precision@K/F1/NDCG 不运行、不报告；sidecar 只用于审计、HaluMem delta 与
  隔离验货。当前 adapter 的 `valid/turn` capability stamp 违反本裁决，重开范围仅限 B5/GRID；
  不推翻 B1-B4/B6-B11，也不要求重烧 build smoke。
- **B6 ✅**：add_note 同步完成 note 写入与 evolution；无待 flush 的 buffer。
- **B7 ✅**：build LLM、embedding、retrieval 与 framework answer 真实 observation 可落盘。
- **B8 ✅**：检索只读；官方 swallow-error 两处在 wrapper fail-fast；endpoint/timeout/retry 注入。
- **B9 ✅**：`gpt-4o-mini` + product-default MiniLM-384/Chroma cosine；revision 诚实 unpinned。
- **B10 ✅**：主 TOML 跨五 benchmark 固定；作者 LoCoMo builder/复现参数不混入主表。
- **B11 ✅**：最终主树全量 `1680 passed`、compileall 0；五 benchmark 共 11 个真实 run
  覆盖 W1/W2、BEAM 100K/10M、HaluMem extraction/update/QA/type，artifact/state/
  efficiency 机器门全部通过；冻结记录见
  [`amem-frozen-v1.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/amem/notes/amem-frozen-v1.md)。

实现与算法证据见
[`amem-official-product-r1-implementation.md`](../../workstreams/ws02.7-method-track/branches/method-recertification/amem/notes/amem-official-product-r1-implementation.md)。
