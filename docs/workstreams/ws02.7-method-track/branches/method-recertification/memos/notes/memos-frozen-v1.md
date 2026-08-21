# MemOS method-frozen-v1

日期：2026-07-29

架构师：GPT-5.6 sol

方法版本：`MemTensor/MemOS v2.0.25@e820406`
adapter：`memos-v2.0.25-product-v4`

> 2026-08-21 勘误：memory-type 的 N/A 不源于 MemOS taxonomy 名称不同；该 evaluator
> 按 benchmark gold-side Event/Persona/Relationship 分组，并继承 upstream extraction 的
> N/A。本页 §3.5/§6 已按 current evaluator contract 订正，不改变 frozen 运行身份或分数。

## 0. 冻结判词

```text
MEMOS_METHOD_FROZEN_V1(
  product_surface =
    init_server
    → shared HandlerDependencies
    → typed AddHandler / SearchHandler,

  lifecycle =
    async fast write
    → exact business-task terminal
    → MEM_READ fine write
    → raw cleanup / refresh,

  main_input =
    LoCoMo official dual namespace + reverse roles + per-view batch_size=2
    and all other benchmarks one lossless canonical session,

  framework_workers = 1,
  framework_parallelism = N/A(product runtime shared embedder is not thread-safe),

  retrieval_semantic_provenance = pending,
  retrieval_stable_ranking = pending,

  halumem =
    QA valid
    + update evaluator valid but tiny-smoke zero-hit N/A
    + extraction N/A
    + memory-type N/A
)
```

`pending/N/A` 是诚实的能力边界，不是接入失败。极小 smoke 的答案分数只证明链路，
不能评价 MemOS 效果。

## 1. 冻结身份

| 项 | 值 |
| --- | --- |
| upstream | `https://github.com/MemTensor/MemOS.git` |
| release / commit | `v2.0.25` / `e820406269537b97d270687e3e40eea2f015f81a` |
| source mode | `vendored-memos-product-plus-patch-plus-wrapper` |
| source SHA-256 | `5eb27819a4f239400a1ac30d061d6524adc06adce8a9dde622cfa4b3e012f39e` |
| vendored source SHA-256 | `430c8476520a14078385a27e01f5e2d749c1d7e6ee94f5b46356756c67cb74bb` |
| patch SHA-256 | `bfe70f8dff8f6bf9918cb7ef00f77554e6a2ea9e7a69433d532d24aff0449773` |
| adapter SHA-256 | `f6365b54ed9b53d7dff5e23e07a5386c480dfd9748c4f1d07b534d2b545e32b9` |
| implementation | `typed-product-handler` |
| build | `tree_text + MultiModalStructMemReader + async fast→fine` |
| embedding | local `all-MiniLM-L6-v2`, 384, model-pipeline L2, Qdrant cosine |
| smoke API | `opencodego/deepseek-v4-flash`, Chat Completions, thinking disabled |
| official-full API | `primary/gpt-4o-mini` |

本项目不启动 HTTP host。typed handler 与 host router 委托的是同一产品组件；绕过的是
transport，不是 memory algorithm。patch 只增加失败可见性、暴露 factory 已支持的
SentenceTransformer 配置、关闭不可达 internet component、约束 JSON output，以及提供
成功 response usage callback；成功路径算法与返回内容不变。

## 2. B0-B11 对表

| 门 | 结论 | 冻结证据 |
| --- | --- | --- |
| B0 官方 harness | `closed` | LoCoMo 最终 payload 为双 namespace、正反 role、每视角位置切 2、双路各取 top-k；LongMemEval 官方 pair/8000 截断留在待校准作者轨；其余三格是 framework extension |
| B1 source/interface | `closed` | source lock 固定；调用 `init_server → HandlerDependencies → typed handlers`；不使用 method 自带答题 |
| B2 granularity | `closed` | framework `session`；LoCoMo adapter 内部再按官方每视角 batch=2；奇数尾 singleton、无 placeholder |
| B3 isolation | `closed at W1` | `namespace == user_id == cube_id`；真实 LoCoMo 双库、MemBench 多 conversation 与 clean readback 均通过；framework W2 单独判 N/A |
| B4 public input/readout | `closed` | role/content/time/place/image/message_id 沿 canonical event 到最终 request 强反例；typed search 只读 `text_mem`，零命中与 backend failure 分离 |
| B5 provenance/rank | `pending` | generated fine memory 的 source 只证明参与生成，不证明 current memory 仍承载每个 fact；MMR/rerank 稳定顺序未证 |
| B5+ 无损改造 | `closed` | 不为 Recall/NDCG 伪造 lineage；HaluMem task-local fine output 不在公开完成门，extraction 诚实 N/A |
| B6 lifecycle/flush | `closed` | exact business-task terminal 后才视为 ingest 完成；reader/storage/archive/delete/refresh/scheduler 任一失败可见 |
| B7 observability | `closed` | build LLM 使用真实 `api_usage`；local embedding 使用真实 tokenizer estimate；async callback 经 completion-buffered replay 回到原 scope |
| B8 clean/retry | `closed` | namespace-scoped delete + readback；LoCoMo 双 namespace 先统一 pending preflight；runtime partial-stop 永久 fail-closed |
| B8+ resilience | `closed for smoke` | API retry/timeout、scheduler terminal、graph/vector/read failure 均显式；不把传输/解析失败伪装成合法零抽取 |
| B9 model identity | `closed` | build LLM、embedding、reranker、answer、judge 分角色入 manifest；smoke 与 official runtime 不混分 |
| B10 TOML/builder | `closed for main` | 单一 TOML 的 `smoke/official_full` 主 section；五格统一 benchmark builder；作者校准列 declared gap |
| B11 smoke/freeze | `closed` | product-v3 五格真实 smoke + product-v4 LoCoMo/HaluMem B7 哨兵 + 全量/compileall/patch/document gates；W2 以真实反例和 CLI fail-fast 判 N/A |

## 3. 五 benchmark 主轨

### 3.1 LoCoMo

- 从公开 metadata 读取真实 `speaker_a/speaker_b`；
- view A：`speaker_a→user / speaker_b→assistant`；
- view B：role 反转；
- content 保留真实 speaker 前缀，图片使用共享
  `[Sharing image that shows: {caption}]`；
- 每视角按位置切 `batch_size=2`，奇数尾 singleton，不造 placeholder；
- 两路 add 全部先 submit，再逐 task 等 terminal；
- 检索时每路各取完整 `query.top_k`，保持各路内部产品顺序，按真实 speaker 槽位合并；
  不宣称跨库 global rank 或总 top-k。

主轨在输入与 readout 拓扑上跟随官方 harness，但 answer 仍走 benchmark unified
builder，top-k/preference/server env 也未达到 paper-number parity。

### 3.2 LongMemEval

- 一个完整 canonical session 对应一个 product add request；
- 原 role、原顺序、全 content 无损保留；
- assistant-first、连续同 role、singleton、奇数尾合法；
- 不加 placeholder、不按 role 修复、不重排；
- `question_date` 只进入 answer/query channel，不作 history filter。

官方 wrapper 的位置切 pair、`content[:8000]`、top-k 与 builder 属
`author_longmemeval` 待校准身份；current wrapper 还存在 `reference_time` 签名漂移，
不能把主轨结果当论文复现。

### 3.3 MemBench

- first-person pair 在 canonical 层展开为真实 user/assistant child；
- third-person user-only 合法，不加假 assistant；
- 原 content 尾部 place/time 逐字保留，抽取出的时间另写 `chat_time`；
- 100k noise 无时间时显式 `chat_time=None`；
- gold 空/越界只在 evaluator-private 层处理，method 不可见。

### 3.4 BEAM

- 使用 canonical session/turn id，不信 raw 重复/跳跃 id；
- role/content/order 原样；
- 10M 两处 dangling/misaligned 数据不跨 session 修复、不造回复；
- BEAM recall 因 gold unit 与 generated memory lineage 不匹配为 N/A/pending，不硬算。

### 3.5 HaluMem

- 每 session 一个 add request，并等待该 business task exact terminal；
- QA=`valid`；
- update evaluator contract=`valid`，但本次 7 个 current-state probe 全 zero-hit，
  聚合为 `N/A/no_nonempty_retrieval`，不是 0 分；
- completion gate 不公开该 task 新生成的 fine memories，extraction=`N/A`；
- `halumem_memory_type` 是消费 extraction/update artifact 后按 gold-side
  Event/Persona/Relationship 分组的 composite evaluator，不要求 MemOS 使用同名 taxonomy；
  本格为 `N/A` 的真实原因是 upstream extraction 已因 task-local fine output 不可见而 N/A，
  composite 按契约传播 `upstream_extraction_n_a`。

## 4. 真实 smoke 资产

### 4.1 product-v3 五格功能链

| benchmark | run | 机器结果摘要 |
| --- | --- | --- |
| LoCoMo | `memos-locomo-v3-r3q1-w1` | 1/1 conversation，1/1 question；五个适用 metric 均落盘，Recall pending |
| LongMemEval S | `memos-lme-v3-r1q1-w1-s-cleaned` | 1/1，1/1；answer metrics 落盘，Recall/rank pending |
| MemBench 0-10k | `memos-membench-v3-r1q1-ps1-w1-0-10k` | 4/4，4/4；四 source 全链 |
| MemBench 100k | `memos-membench-v3-r1q1-ps1-w1-100k` | 2/2，2/2；missing-time sentinel |
| BEAM 100K | `memos-beam-v3-r1q1-w1-100k` | 1/1，1/1；rubric judge 落盘，recall N/A |
| BEAM 10M | `memos-beam-v3-r1q1-w1-10m` | 1/1，1/1；rubric judge 落盘，recall N/A |
| HaluMem Medium | `memos-halumem-v3-r1-w1-medium` | 固定 4-session shape；四类 evaluator 均产生诚实结果 |

### 4.2 product-v4 B7 哨兵

product-v4 只增加观测 callback/回放，不改变 memory payload、算法、search 或返回值，
所以五格功能资产继承 v3；另外重跑两条承重路径：

| run | 实测 |
| --- | --- |
| `memos-locomo-v4-b7-r1q1-w1` | build LLM 2 次、3286 input / 325 output，均为 `api_usage`；build embedding 4 次；双路 retrieval embedding 2 次 |
| `memos-halumem-v4-b7-r1-w1-medium` | build LLM 4 次均为 `api_usage`；build embedding 9 次；7 update probes + 1 QA 共 8 次 retrieval embedding |

LoCoMo v4 的 F1=`0.6667`、judge=`0`；HaluMem v4 QA=`1.0`。这些分数不用于
效果排序，只说明结果与 evaluator 接线完整。

## 5. framework W2 最终裁决

`supports_shared_instance_parallelism=False` 只能让 runner 构造两个 provider；MemOS 的
`MemosRuntimeOwner` 仍按同一 config 复用**同一个进程级 runtime/embedder**，所以这不是
两个真正隔离的 runtime。

诊断资产：

- `memos-locomo-v4-r3q1-c2-w2` 曾完成 2/2，但一次成功不能证明线程安全；
- `memos-lme-v4-r1q1-c2-w2-s-cleaned` 实测 1/2：
  `e47becba=failed_answer`、`118b2229=completed`；
- 失败来自两个检索并发调用共享 SentenceTransformer tokenizer：
  `RuntimeError: Already borrowed`；
- 该命令没有 conversation budget，故不是正常 pending；
- 旧 command summary 没有失败计数，导致 shell 错返 0；现已新增
  `failed_conversations/failed_count`，predict 对部分失败返回 1，`run` 不再给失败 child
  继续评分。

最终资格：

```text
framework conversation workers > 1 = N/A / unsupported
MemOS internal async dispatcher       = 保持 product default true
smoke/official_full max_workers       = 1
CLI --workers override                = runtime/API 前 fail-fast
```

不通过锁、复制 runtime 或改存储拓扑“修到能并行”；那会形成新的 implementation
identity，不能为了填 checklist 改写 current product。

## 6. 冻结后声明缺口

1. generated fine memory semantic provenance 与 Recall/NDCG；
2. MMR/rerank stable ordering；
3. HaluMem task-local fine output；memory-type 资格随 extraction composite 传播，不另设
   method taxonomy 门；
4. HaluMem update 的非空 current-state 命中哨兵；
5. `author_longmemeval` pair/truncation/builder/reference-time 校准；
6. LoCoMo preference/top-k/server-env 与 paper-number parity；
7. framework W2（明确 N/A，不是待补 smoke）；
8. formal/full 真实 resume 与成本 pilot。

上述缺口不会被“后续版本顺手补上”。若 source lock、patch、adapter、benchmark
canonical contract、API runtime identity 或主 profile 改变，必须版本化解冻并做影响分析。

## 7. 最终验收门

- MemOS/runner/CLI/文档定向门：
  `504 passed, 12 warnings in 15.40s`；
- 全量 pytest：
  `1902 passed, 3 deselected, 13 warnings, 29 subtests passed in 129.84s`；
- compileall：`exit 0`；
- patch reverse-check：
  `git -C third_party/methods/MemOS apply --reverse --check --unidiff-zero ...`
  `exit 0`；
- W2 预启动拒绝：
  `Error: MemOS does not support --workers override`，`exit 2`，且零 run directory；
- `git diff --check`：`exit 0`。

13 个 warning 全是既有 LightMem Pydantic deprecation、MemOS `utcnow()` deprecation
与 MemOS config Pydantic serialization warning；无
`PytestUnraisableExceptionWarning`。
