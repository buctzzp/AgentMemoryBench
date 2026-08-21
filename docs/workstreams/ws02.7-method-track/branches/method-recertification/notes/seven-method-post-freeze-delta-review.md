# 七家 method 冻结后轻量差量核对表

> 范围：A-Mem、SimpleMem、MemOS、Letta/MemGPT、LangMem、EverOS、Graphiti。
>
> 性质：冻结后的**短表复核**，不是重新执行 B1-B11，也不是新一轮 method 接入。
> LightMem、Mem0、MemoryOS 已由用户与架构师逐格共同压实，不在本表重复审查。

## 1. 执行裁决

审查维度要完整，执行重量必须受控。七家 method 已有 integration page、冻结 note、测试和
真实 smoke；本轮默认复用这些证据，只回答一个问题：**current source / shared contract / 新的一手
官方材料，是否与冻结判词发生实质矛盾？**

本轮明确不做：

- 不重扫五个 benchmark 的 schema、异常 census 或 gold；
- 不机械重跑 B1-B11、全量 pytest、compileall 或真实 smoke；
- 不为每家复制一份新 dossier、ledger 或五格说明；
- 不把作者 harness、第三方框架或 README 自动当成高于 current product source 的权威；
- 不因措辞、行号或待做 author profile 就撤销 frozen。

只有出现下列**已证实红线**，才重开受影响的单个 B/GRID 格，不把整家 method 推倒重来：

1. private gold/evidence/judge label 可达 method；
2. canonical event 被静默丢失、重复、跨 session 重配或伪造 role/time/content；
3. namespace 串写、清理越界，或 async 未完成就进入 retrieve；
4. 当前主轨与 method 官方已覆盖 benchmark 的算法身份/final payload 实质冲突；
5. evolved/synthesized memory 被错误宣称为 lossless source unit，导致 Recall/NDCG 等误标
   `valid`；
6. HaluMem session-local extraction 依赖 sidecar 猜测、清空长期记忆或混入旧 session；
7. 为拓展 metric/HaluMem 改变 method 核心 build/retrieve 算法，却未声明 variant。

其余差异分两类：

- `DOC_FIX`：措辞、索引、旧行号、错误理由；就地修文档，不阻塞研究主线；
- `BACKLOG`：author 校准、效果参数、上游漂移观察或暂无能力的 `N/A/pending`；进入已有声明
  缺口，不新开施工线。

## 2. 每家只对照七项

1. **source/official coverage**：锁定版本是否漂移；官方实际覆盖哪些 benchmark，入口是否最终
   调到当前 product surface。
2. **final ingest payload**：最终 add 次数、原生粒度、role/speaker/content/time/image、namespace、
   batch/window；不能只看外层 wrapper。
3. **病态 message grammar**：singleton、assistant-first、连续同 role、odd tail、单 role session、
   空白/image-only、time 缺键/`None`/空串是否被当前算法正确消费；只有原生语法要求时才补结构
   placeholder，且必须证明 placeholder 不进入语义记忆。
4. **lifecycle/isolation**：完成门、flush/finalize、失败传播、clean retry、W1/W2 所有权是否仍与
   冻结身份一致。
5. **product readout**：答题前产品真正返回的全部记忆层、item 粒度、顺序/top-k、source semantic
   lineage 是否与 artifact 声明一致。
6. **metric/HaluMem 资格**：Recall/Precision/F1/NDCG 与 HaluMem extraction/update/QA/
   memory-type 分开判；`N/A` 不视为接入失败。
7. **artifact truth**：manifest/source identity、效率 observation、公开/private 负空间与稳定文档
   是否仍如实描述运行时。

证据顺序固定为：current product source → 官方 final payload → 当前 adapter → 既有强反例/
artifact → 文档。已有证据一致即打勾；只有矛盾行才写最小零 API probe。没有 adapter/source/
run identity 改动，不重烧 smoke。

## 3. 七家基线与唯一差量问题

下表是**核对起点，不是未经复核的新判词**。详情一律回到链接的稳定 integration page；本表只留
每家最值得确认的一处差量，防止审查面膨胀。

| Method | 当前产品 ingest / retrieve | message grammar 基线 | 当前 metric / HaluMem 边界 | 本轮只核的差量 |
| --- | --- | --- | --- | --- |
| [A-Mem](../../../../../reference/integration/amem.md) | turn：`analyze_content()` + `add_note()`；`search_agentic()` | role/speaker 渲染进 content；不配 pair、不造 placeholder | evolution 后 memory 非原 source unit，qrel/rank metric=N/A；session new-note delta 支持 extraction | current product source 未漂移；session delta 没把旧 note evolution 误算成新 session extraction |
| [SimpleMem](../../../../../reference/integration/simplemem.md) | turn：`add_dialogue(speaker, content, timestamp)`；`hybrid_retriever.retrieve()` | 原生 turn；不配 pair；顺序窗口 + `finalize()` | semantic fusion 使 qrel metric=N/A；session finalize delta 支持 extraction | 主轨仍禁 build parallel，session finalize 后只清 transient context、不清长期 memory |
| [MemOS](../../../../../reference/integration/memos.md) | session：typed product add/search handler；内部位置 batch=2、odd tail singleton | LoCoMo 双 namespace/正反 role；其余保留原序；不造 placeholder；async exact terminal | Recall/NDCG pending；QA valid；extraction N/A；update 独立判 | 新增 OmniMemEval 官方材料与 pinned MemOS v2.0.25 是否同产品/版本，五格 final payload 是否推翻现有主轨；顺手更正 memory-type N/A 的错误理由 |
| [Letta/MemGPT](../../../../../reference/integration/letta.md) | session：official formatter → `AgentLoop.step()`；read attached core blocks | wrapper 内保留 role 序列；不要求 pair、不补 placeholder | evolved core blocks 无 source qrel；extraction/type N/A，update/QA valid | formatter/legacy product pin 未漂移；wrapper 外层 `role=user` 没有掩盖内部 assistant/same-role 语义 |
| [LangMem](../../../../../reference/integration/langmem.md) | session：manager `ainvoke(messages)`；`asearch()` | 接受 assistant-first/same-role/singleton/odd tail；不补 placeholder | evolved memory qrel=N/A；extraction/type N/A，update/QA valid | current async manager 仍是实际产品路径，未退化为 raw store 或 hot-path agent variant |
| [EverOS](../../../../../reference/integration/everos.md) | session：official lifespan 内 typed `memorize/search/get` | canonical 原序；纯 assistant session 有无 source identity 的结构 user anchor | qrel=N/A；HaluMem 四类 valid | 结构 anchor 仍不进入语义 memory/source lineage；current release/source lock 未漂移 |
| [Graphiti](../../../../../reference/integration/graphiti.md) | turn：`add_episode()`；edge `search()` | 原 turn，不配 pair；`reference_time` 必填，缺时拒绝而非伪造 | current 判 provenance/rank valid；HaluMem 四类 valid | 只有 source/adapter 漂移时才重核 transformed graph fact 的 semantic source mapping、merge/update 与稳定 rank |

## 4. OmniMemEval 参考资产

| 项 | 锁定值 |
| --- | --- |
| upstream | `https://github.com/MemTensor/OmniMemEval` |
| 本地镜像 | `第三方框架参考/OmniMemEval/`（gitignored，不进入本仓） |
| 本次 source lock | `main@0b1ea8d28aa2d3e03ac4a6aee17b3006a131da7d` |
| 覆盖 | User Memory：LoCoMo、LongMemEval、BEAM、PersonaMem v2、HaluMem；另有 Agent Memory track |
| 主要入口 | `scripts/client_factory/` + 各 benchmark `*_ingestion.py` / `*_search.py` + `run_*_eval.sh` |

使用边界：

- 它是与本框架类似的独立评测工程，可帮助发现官方团队实际采用的 add/search payload、batch、
  namespace 和 benchmark coverage；它不是 benchmark gold 规则或 method current product source。
- 对 MemOS 尤其有参考价值：其 local client 使用 `/product/add|search|delete_memory`，LoCoMo 采用
  双 user namespace/正反 role，HaluMem 按 session add。但使用前仍须比较 OmniMemEval commit
  所面向的 MemOS API 与本项目 pinned `v2.0.25`，不能跨版本直接宣布 parity。
- 本地参考仓不得随手 `git pull` 后让旧裁决静默漂移。需要引用新版本时，先记录新 SHA，再只
  重开受影响的行。
- PersonaMem v2 不在 Phase 1 五 benchmark，本轮不扩 scope。

## 5. 结果记录与停手线

实际核对只在下表追加七行；不再生成七份报告。

| Method | current commit/source | 复用证据 | 新矛盾 | Verdict | 只重开哪一格 |
| --- | --- | --- | --- | --- | --- |
| A-Mem | product pin 与 upstream `main` 均为 `ceffb860` | integration + frozen note + adapter/test + 真实 LoCoMo artifact | 文档判 retrieval qrel=N/A，runtime 却盖 `semantic_provenance=valid`、`provenance_granularity=turn` | **`RED`** | **B5 + GRID retrieval eligibility** |
| SimpleMem | pin `60a48e83`；upstream `main=db80b6a`，稳定 tag 仍为 `v0.3.0` | integration + frozen note + patch reverse-check | 算法判词无反证；MANIFEST 漏记实际恢复 patch；新 main 有未评估产品漂移 | **`DOC_FIX + BACKLOG`** | none |
| MemOS | pin `v2.0.25@e820406`；upstream `main=be68e2f` | integration + frozen note + patch reverse-check + OmniMemEval `0b1ea8d` | memory-type N/A 理由写错；同团队 Omni 默认 batch=20 与 pinned method harness batch=2 冲突，不能跨版本代裁 | **`DOC_FIX + BACKLOG`** | none |
| Letta/MemGPT | legacy pin `0.16.8@b76da909`；archive head `87fd37a`，最新稳定 tag 仍为 `0.16.8` | integration + ledger + dossier + frozen note + formatter/source | 外层 SDK `role=user` 未掩盖 wrapper 内原始 role；无 current 反证 | **`UNCHANGED`** | none |
| LangMem | pin `56d8593`；upstream `main=29cbe41` | integration + ledger + dossier + frozen note + source diff | 四个新 commit 只改 `uv.lock`；产品路径无漂移，依赖刷新留正式实验前 | **`BACKLOG`** | none |
| EverOS | stable pin `v1.2.3@48fc908`；upstream `main=d07cddc`，无新稳定 tag | integration + ledger + dossier + frozen note + patch reverse-check | assistant-only anchor 仍为 source-less 结构占位；新 main 不静默替换稳定身份 | **`UNCHANGED`** | none |
| Graphiti | stable pin `v0.29.3@021d3a5`；upstream `main=993e081`，仅有 `v0.30.0pre*` | integration + ledger + dossier + frozen note + current merge/edge lineage source | active edge `episodes` 仍只承载当前事实来源；矛盾 edge 会失效；无 provenance/rank 反例 | **`UNCHANGED`** | none |

### 5.1 一手核对摘要

- **A-Mem**：产品 `add_note()` 每次先创建新 note，evolution 只更新邻居链接、context 与 tags；
  session report 只取本 session 新建 note id，故 HaluMem extraction 没把旧 note 误报成当前
  session 新产物。真正的红点只在 retrieve：
  `amem_adapter.py:663-667` 和 `test_amem_adapter.py:605-607` 把 evolved current memory
  宣称为 lossless turn evidence；冻结 LoCoMo artifact 也实际落了 `valid/turn/valid`。
  “没有调用 retrieval evaluator”不能让错误 capability stamp 变安全。

  ```text
  artifact = outputs/runs/amem/locomo/smoke/unified/
             amem-locomo-v2p-r3q1-w1-r2/artifacts/answer_prompts.prediction.jsonl
  retrieval_evidence = {
    semantic_provenance: {status: valid},
    provenance_granularity: turn,
    stable_ranking: {status: valid}
  }
  ```
- **SimpleMem**：主配置仍关闭 build parallel，retrieval multi-query parallelism 不改变 build
  窗口顺序；session `finalize()` 后只清 `previous_entries` transient context，不清长期记忆。
  `simplemem-product-compat.patch` 的两项实际作用是 LanceDB 新版 native FTS 兼容和线程池中
  `ContextVar` 传播，均不改 text product 算法；恢复清单必须如实列出。
- **MemOS**：pinned method repo 自带 LoCoMo/LongMemEval harness 都是位置 batch=2；
  OmniMemEval 的通用 MemOS client 使用 `/product/add|search|delete_memory`，但环境默认
  `MEMOS_BATCH_SIZE=20`。两者都是有价值的一手入口，却没有共同 version contract；当前主轨继续
  服从已锁定的 `v2.0.25` method repo，Omni 差异只进入作者校准/升级 backlog。
- **Letta/LangMem/EverOS/Graphiti**：逐家从产品 formatter/manager/lifespan/edge resolution
  复核最终 payload 与 lifecycle，没有发现 canonical message 损失、namespace 串写、未完成先
  retrieve 或指标资格的新反例。remote `main` 漂移不等于冻结身份自动漂移。

### 5.2 精确重开裁决

本轮唯一 `RED` 是 **A-Mem B5/GRID retrieval eligibility**。重开范围严格限定为：

1. runtime `RetrievalEvidence` 必须与“evolved current memory 不可作为原 turn qrel”一致；
2. LoCoMo、LongMemEval、MemBench、BEAM 的 Recall/Precision/F1/NDCG 资格保持 N/A，不因
   sidecar id 存在自动解锁；
3. stable product ranking 可以单独判，不能反推 semantic provenance；
4. 旧 artifact 永久按旧 adapter identity 回读，不改写历史；修复只需零 API 强反例和文档/
   GRID 对表，**不重烧五格 build smoke，不重开 A-Mem 其余 B 门**。

SimpleMem 与 MemOS 的 `DOC_FIX` 在本轮直接修正稳定文档。全部 `BACKLOG` 都是 source upgrade、
author calibration 或正式实验前依赖刷新，不改变当前 frozen build。

停手线已达到：七行都有 verdict。六家保持当前 frozen build；A-Mem 只临时重开 B5/GRID，
待一张小修关闭后恢复完整 frozen。这样保留完整审查视野，同时不让复核吞掉 ws05/后续主线。
