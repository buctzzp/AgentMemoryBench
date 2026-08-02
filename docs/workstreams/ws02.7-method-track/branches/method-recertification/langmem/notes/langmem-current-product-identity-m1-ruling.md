# LangMem current source / product identity M1 裁决

日期：2026-08-02
状态：`ARCHITECT_ACCEPTED_READY_FOR_M2`
范围：锁 current source、官方 benchmark 覆盖、产品 surface、主轨身份与 M2 边界；不宣称
adapter、真实 smoke 或冻结已完成。

## 1. 结论

LangMem 主轨采用官方公开的 **background `create_memory_store_manager()` + async
`ainvoke()` + `MemoryStoreManager.asearch()`**：每个 canonical session 作为完整 messages
列表交给 manager，manager 自己检索旧 memory、抽取/合并/更新并写入官方 `BaseStore`。
框架只在产品边界补 namespace、持久化、输入保真、效率观测与 `formatted_memory`，不让
answer agent 决定是否记忆，也不绕过算法直接 `store.put()` raw turn。

官方 current repo 对 Phase 1 五个 benchmark 均无 harness，所以五格全部是
product-faithful `framework extension`，当前不存在 `author_<benchmark>` 配置。检索命中是
会持续更新/合并的 current memory；稳定 key 不能证明 current text 仍承载每个 gold source，
故 provenance retrieval metric N/A。HaluMem update/QA 为直接支持候选，extraction/type N/A。

## 2. Current source lock

- upstream：`https://github.com/langchain-ai/langmem.git`
- vendored：`third_party/methods/langmem`
- current remote/local HEAD：`56d85939d80bb731bd5e237567148d817d7bfd16`
- package：`langmem==0.0.30`、Python `>=3.10`
  （`third_party/methods/langmem/pyproject.toml:1-17`）
- license：MIT；`LICENSE` SHA-256：
  `98af1351ea856e008c835bc89a312905960a318072f950732bf346c741027c7d`
- selected product source SHA-256：
  `50999bd9675304d514d86218033898ac1930a57958aeda95cb967f22f59753fb`

selected set 用“相对路径长度 + 路径 bytes + 内容长度 + 内容 bytes”顺序哈希：`LICENSE`、
`README.md`、`pyproject.toml`、`src/langmem/__init__.py`、
`src/langmem/knowledge/{extraction,tools}.py`、`src/langmem/utils.py`、
`docs/docs/background_quickstart.md`、`docs/docs/guides/delayed_processing.md`。

旧 pin `c01e273b...` 到 current HEAD 的 tracked delta 只有 `uv.lock` 47 行；README、docs、
`src/langmem/`、`pyproject.toml` 均零 diff。产品逻辑未因本次 fast-forward 漂移，但恢复脚本
与 manifest 仍已同步 current pin。无 patch；只有 selected source、官方版本或公开入口漂移
才重开 M1。

```text
git -C third_party/methods/langmem rev-parse HEAD
56d85939d80bb731bd5e237567148d817d7bfd16

git diff c01e273b..56d8593 --stat
uv.lock | 47 ++++++++++++++++++++++++++---------------------
1 file changed, 26 insertions(+), 21 deletions(-)
```

## 3. B0：官方 benchmark 覆盖为空

对 current repo 排除 docs/uv.lock/.venv 后搜索
`locomo|longmemeval|halumem|membench|beam` 为零命中；repo 只有通用 package、docs、
examples 与 short-term tests。因此五格均为 framework extension。第三方 mem0 evaluation
和 LightMem 内的 LangMem layer 只作外部先例，不进入 official parity matrix。

官方 harness 集为空时，B0-FINAL-PAYLOAD 的正确状态是 N/A；不能把 README quickstart
伪装成作者 benchmark payload。

## 4. 产品 surface 三分法

官方 README 明确提供 functional primitives、hot-path tools、background manager
（`README.md:7-16`）。

### 4.1 主轨：background manager

`background_quickstart.md:8-16,48-63` 把 `create_memory_store_manager()` 定义为从
conversation 自动抽取/整合 memory 的产品入口；`delayed_processing.md:8-17,56-67`
明确逐 message 会冗余且缺 incomplete context，debounce 是为了完整 conversation context。

主轨因此锁定：一个 canonical session 一次 `ainvoke`；role 原序保留、不重配、不补
placeholder；每 isolation 独立 namespace；retrieve 用 `asearch(query, limit)`；framework
reader 独立答题。

### 4.2 两条非主轨

- hot-path 示例由 `create_react_agent()` 让 answer agent 自己决定何时存/搜
  （`README.md:30-84`），混入 tool policy，分类 `ALGORITHM_VARIANT`。
- direct `BaseStore.put(raw turn)` 绕过 old-memory search、LLM extraction、update 与
  consolidation，分类 `MECHANISM_BYPASS`。

`create_memory_searcher()` 另用 query LLM 生成 search tool calls，是 optional retrieval
variant；主轨不额外加入 query LLM。

## 5. Product default 与两处文档漂移

公共 factory 签名 `extraction.py:1666-1681` 锁：default schema `Memory(content)`、
`enable_inserts=True`、`enable_deletes=False`、`query_model=None`、`query_limit=5`、动态
namespace 和可插拔 store。update 在内部 `MemoryManager` 默认开启
（`:217-235,253-260`）。

两处 docstring 与代码冲突，代码优先：

1. `:1706-1707` 写 delete 默认 True，但公共签名 `:1675` 是 False，构造转发
   `:2092-2104` 也保留 False。
2. `:1708-1710` 写 query_model=None 使用 primary model；实际 `:855-895` 令
   `query_gen=None`，`:1030-1037` 直接用 message window 做 embedding search。

`query_limit=5` 时 `get_dialated_windows(messages, query_limit // 4)` 的 N=1，只用当前
session 最后一条 message 搜旧 memory。M2 保留 current public factory 默认，不按 benchmark
偷偷扩窗口。

## 6. 为什么锁 async

异步路径 `extraction.py:1006-1137`：先搜当前 namespace 旧 memory；把完整 messages 与旧
memory 交给 MemoryManager；生成 `final_puts/final_deletes`；等待全部 `aput/adelete` 完成后
才返回 changed puts。因此 `ainvoke()` 返回就是精确完成门，无额外 sleep/flush。

同步 `invoke()` 在无 query model 时先直接执行一遍 search（`:1165-1172`），又提交同样的
queries 再执行一遍（`:1173-1183`）。零 API 探针实测：

```text
LANGMEM_SYNC_SEARCH_CALLS 2
```

主轨选择同一官方产品的 async surface，分类
`UPSTREAM_SYNC_DUPLICATE_SEARCH_AVOIDED`；不 patch 算法。

## 7. Message contract 与粒度

`utils.get_conversation()` 用 LangChain `merge_message_runs()` 后按 role pretty-print
（`src/langmem/utils.py:98-100`）。零 API 探针覆盖 assistant-first、same-role、user-only、
assistant-only、odd tail：每个 content 恰出现一次且不报错；same-role 只在算法 prompt 中合并
成一个同角色 run。

```text
[assistant_first] Ai(A0) -> Human(U1)
[same_role] Human(U0\nU1) -> Ai(A2)
[user_singleton] Human(U0)
[assistant_singleton] Ai(A0)
[odd_tail] Human(U0) -> Ai(A1) -> Human(U2)
LANGMEM_MESSAGE_SHAPES_PASSED
```

裁决：`consume_granularity=session`；所有异形原序交付；不补 placeholder、不跨 session。

## 8. Store、namespace 与 persistence 边界

README 使用 `InMemoryStore` 并明确进程退出丢失，生产可换 Postgres
（`README.md:40-62`；`background_quickstart.md:72-77`）。store 是公开可插拔边界，M2
采用 official InMemoryStore + controlled local MiniLM-384 + 每 isolation 动态 namespace。

为了支持 runner resume，adapter 可原子快照 exact key/value/order，并经同一 `store.put()`
恢复与重建 vector。这只补 storage durability，不改变 extraction/update/search；但必须以同一
原子文件提交 namespace snapshot + completed operation journal，闭合 ambiguous replay、
rollback、单 namespace clean 与 W2 ownership。M1 不提前把这些实现门判绿。

`MemoryStoreManager.asearch()` 保留 namespace/key/value/score 与产品顺序
（`extraction.py:1513-1578`）。created/updated 是 store 墙钟，不是 source time，不能显示成
benchmark 时间。

## 9. 零 API product probe

current nested runtime 中以真实 `MemoryStoreManager.ainvoke()`、真实 `InMemoryStore`、fake
manager output 和 deterministic fake embedding 实测：

```text
LANGMEM_PRODUCT_PROBE_PASSED
first_puts:  mem-1 = Alice lives in Seattle
second_puts: mem-1 = Alice moved from Seattle to Boston
ranked:      mem-1, score=0.5773502691896258
other namespace: []
search_calls=4, manager_calls=2, doc_calls=2, query_calls=4
```

这证明 insert→update、namespace search isolation、query score/order 与 changed-memory
return；不证明真实 LLM 效果、持久化或并行。

独立 runtime 也已从本地模型加载受控 embedding：

```text
LANGMEM_EMBEDDER_OK (1, 384) 1.000000238418579
max_seq_length 256
token_count 4
```

M2 必须加入 reproducible bootstrap lock；未跟踪 `.venv` 不是交付物。

## 10. 五格输入裁决

- **LoCoMo**：固定 `speaker_a→user`、`speaker_b→assistant`；content 带真实 speaker name；
  共享 image helper；source time 用 turn→session→None。
- **LongMemEval**：完整 session 一次；assistant-first、连续同 role、singleton、odd tail
  原序；不按 pair 丢 blank，不按 question date 过滤。
- **MemBench**：FirstAgent child roles 与 ThirdAgent user-only 原序；正文尾部 place/time 不删
  不重复；100k missing-time 保持缺失。
- **BEAM**：各 variant canonical session 原序；10M orphan/mismatch 不修 raw、不跨 session。
- **HaluMem**：每 session 一次；返回时 current state 已更新，可立即 update/QA probe；changed
  puts 不冒充严格 session-local extraction gold。

source id 只用于 framework operation identity，不塞进 memory prompt。question time、gold、
evidence、judge label 不可达 manager。

## 11. Metric eligibility

LangMem 将 relevant old memory 与新 session 交给 LLM update/consolidate
（`extraction.py:1039-1104`）。current key 标识演化对象，不提供 lossless output-to-source
mapping；把参与输入的 turn ids 求并仍不证明 current content 保留相应事实。

| 能力 | M1 裁决 | 理由 |
| --- | --- | --- |
| semantic provenance | N/A | 演化 current memory 无 lossless mapping |
| stable product ranking | valid 候选 | BaseStore 返回实际 cosine score/order，M2 需锁 tie/resume |
| Recall/Precision/F1@k | N/A | 缺 current item 到 gold source 的语义对应 |
| NDCG | N/A | rank 稳定仍不等于 relevance 可证明 |
| HaluMem extraction | N/A | changed put 可融合旧 memory，不是严格本 session point |
| HaluMem update | valid 候选 | 读取每 session 后 current evolved state |
| HaluMem QA | valid 候选 | framework reader 消费 product search readout |
| HaluMem memory type | N/A | 依赖 extraction point，不能从 free text 猜类型 |

这是区分“能检索 current memory”与“能计算 gold source retrieval metric”，不是宣称 LangMem
没有检索能力。

## 12. M2 强制门

1. 独立 worker 只用 current lock；Chat Completions、timeout/retry、secret 脱敏可证。
2. snapshot + operation journal 单文件原子提交；失败 rollback，ambiguous replay 为零。
3. W2 的 worker/model/store/state root 真独立，不共享 tokenizer。
4. build LLM exact API usage 与 local embedding tokenizer/latency 逐 scope 可观测。
5. 五格 role/time/place/image/异常/零命中/private negative-space 有 production 强反例。
6. HaluMem update/QA 与 extraction/type N/A 从 runtime evidence 导出，不建 metric 白名单。
7. source identity 含 selected upstream、adapter、worker、bootstrap 与补充 lock。
8. 无 API full regression 和 registry planner 通过后才请求真实预算。

最终判词：

```text
READY_FOR_LANGMEM_M2(
  source and empty official harness matrix are locked;
  async background manager is the product-faithful main surface;
  session ingest needs no placeholder;
  semantic provenance and session-local extraction are N/A;
  persistence, observability, parallel ownership and five-grid payload remain M2 gates
)
```
