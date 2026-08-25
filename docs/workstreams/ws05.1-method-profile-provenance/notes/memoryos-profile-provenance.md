# MemoryOS profile provenance（M4）

> **后续状态（2026-08-25）**：本文的 M11 待办属于当时断点；已由
> [M11 implementation](m11-effective-config-source-embedding-implementation.md) 关闭或显式保留为
> 独立 variant。本文保留 M4 一手证据，不改写成新 run 收据。

> 判词：`M4_EVIDENCE_COMPLETE / CURRENT_PRODUCT_SOURCE_LOCKED /
> EVAL_PRODUCT_IMPLEMENTATION_VARIANT / FINAL_MESSAGE_TEMPLATE_PARITY_PASS /
> AUTHOR_NOT_READY`。
>
> 本文只关闭论文、current product、官方 LoCoMo eval 与 framework main 四种身份的证据门。
> 不在本批修改 TOML、切换引擎、注册 author profile、调用真实 API 或调优效果；最终判词和验证
> 记录均已由两路只读调查收据与架构师一手抽锚闭合。

## 0. 身份与范围

- method：MemoryOS（BAI-LAB 的分层 STM/MTM/LPM 方法；不是 MemTensor/MemOS）。
- 审计日期：2026-08-25。
- paper identity：`Memory OS of AI Agent`，arXiv `2506.06326`；本机
  `third_party/methods/MemoryOS-main/Paper-MemoryOS.pdf`，SHA-256=
  `b251fe65d6778e26054c41c7f64328f002ac298279bf857ce9ddbd41f054dbcc`。PDF 共 9 页，
  是当前 checkout 中的阅读材料；source 恢复仍以官方 URL 与 hash 为准。
- current official product：`BAI-LAB/MemoryOS@587ed7755c7aed179965792830ff1b5ad9a6fa92`
  （2026-07-07，Apache-2.0）。现场 `git ls-remote` 与 shallow clone 一致；该 commit 晚于
  `V1.2` tag，不能只用 tag 名概括。
- framework current product：上述 commit 的 `memoryos-pypi/` + 四处 benchmark compatibility/
  observability patch + framework adapter。vendored 12-file identity=
  `5a9af420f01285b0b0ed2846864dbd20cfa78a61b977c2d4352eba4211ce08dd`；加入 adapter 后
  combined identity=`7c82b26967a57715b91c968cf177f27f2161ede4d0727a5f4c783dd431b37e9b`。
- official evaluation：同一 upstream commit 的 `eval/main_loco_parse.py` + `evalution_loco.py`；
  本地除 `main_loco_parse.py` 的 answer-context 纯观测 callback 外，其余七个 eval 核心文件与
  current upstream 逐字一致；dataset SHA-256=
  `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`。
- 本次不覆盖：真实 LoCoMo 效果复现、ChromaDB fork、MCP/hosted product、GVD（非 Phase 1）、
  参数 sweep、author profile 注册以及官方 metric 是否进入 framework 主表。

## 1. 算法机制先行

### 1.1 论文阶段图

| 阶段 | 输入 | 状态/输出 | 是否可选 | 一手出处 |
| --- | --- | --- | --- | --- |
| Storage | 带时间的 user/model QA page | FIFO STM、按主题组织的 MTM segment、LPM user profile/knowledge | 论文核心 | PDF pp.3-4，Fig. 2-3 |
| Updating | STM page、MTM segment、访问/交互/时近信号 | STM→MTM 合并/新建；热 segment 归纳进 LPM | 论文核心 | PDF pp.4-5，Eq. 1-4 |
| Retrieval | query + 三层状态 | 全部 STM、MTM top-m segment 内 top-k page、LPM profile/knowledge | 论文核心 | PDF p.5，Fig. 4 |
| Response | query + 三层检索结果 | role-aware answer prompt 与最终 response | 论文核心 | PDF pp.3,5 |

论文不是“存一段文本后做一次向量搜索”。承重机制包括：QA page、STM→MTM 迁移、segment
连续性/主题合并、heat 更新、LPM profile/knowledge 更新以及三层 readout。关闭其中任一阶段都不能
仅叫“参数不同”。

### 1.2 current product 对应关系

```text
Memoryos.add_memory(user_input, agent_response, timestamp, meta_data)
  -> STM 满时先 Updater.process_short_term_to_mid_term()
  -> 保存一页 QA 到 STM
  -> 热度过阈值时并行更新 user profile + user/assistant knowledge

Retriever.retrieve_context(query)
  -> MTM segment/page 检索
  -> user knowledge 检索
  -> assistant knowledge 检索
  -> 三路并行合并
```

| 论文阶段 | current module/function | 控制参数 | 版本漂移/缺失 | 判词 |
| --- | --- | --- | --- | --- |
| QA page / STM | `memoryos.py:add_memory`、`short_term.py` | STM capacity | 产品把 user/assistant knowledge 分成两库；framework patch 允许合法单侧 page、显式保留缺失时间与 metadata | `CURRENT_PRODUCT_COMPATIBLE` |
| STM→MTM | `updater.py:process_short_term_to_mid_term` | MTM capacity、topic threshold、build LLM | 产品在新 page 加入前迁移，eval 是加入后检测；边界归属不同 | `IMPLEMENTATION_VARIANT` |
| segment merge/heat | `mid_term.py` + `Memoryos._trigger_profile_and_knowledge_update_if_needed` | similarity、heat threshold；alpha/beta/gamma 为内部常量 | 产品与论文系数一致，eval 系数不同 | `CURRENT_PRODUCT` |
| LPM | `long_term.py` | knowledge capacity、threshold、top-k | 产品拆 user/assistant LTM 且有 FIFO capacity；eval 单对象、无同等容量语义 | `IMPLEMENTATION_VARIANT` |
| retrieval | `retriever.py:retrieve_context` | queue capacity、三阈值、top-k sessions/knowledge | 产品三路并行且 MTM 不再调用 query-keyword LLM；eval 为串行 + keyword extraction | `IMPLEMENTATION_VARIANT` |
| response | `Memoryos.get_response` | product prompt、temperature/max tokens | 函数末尾会把 query/response 再写回 memory；framework 故意拆出纯 retrieval，由 reader 答题 | `READOUT_NATIVE_BOUNDARY` |

framework 不调用 `get_response` 不是删掉 MemoryOS 的 memory 算法：它仍执行产品 add、update、
三层 retrieval 与检索副作用，只剥离“method 自己回答并把测试问答写回记忆”这一段，以符合全框架
统一 reader 和 private-label 隔离。作者 LoCoMo 校准可替换 answer builder，但不能把测试问答写回。

### 1.3 current upstream 与 framework patch

2026-08-25 将 vendored 目录与 official `587ed775…` 逐文件比较，只有四个 product 文件不同：

1. `memoryos.py`：允许 user/assistant 任一侧非空的 QA page；只有省略 timestamp 才生成 wall
   clock；显式 `None` 保持缺失；保存 `meta_data`。
2. `short_term.py`：只在 timestamp key 缺失时补 wall clock，显式 `None` 不改写。
3. `updater.py`：单侧 page 也能迁移；timestamp/metadata 原样进入 MTM page。
4. `utils.py`：增加 embedding 成功回调，只观测真实 encode，不改变 embedding。

这些 patch 解决五 benchmark 的单侧 turn、missing-time 与 provenance/效率观测，不改变 page
合并、heat、LPM 或 search score。官方 eval 另只有一处可选 context observer。故当前 source 是
`CURRENT_UPSTREAM_PLUS_DECLARED_COMPAT_PATCHES`，不是年代不明的 fork；patch 仍须进入 source identity。

## 2. 官方 benchmark 覆盖

| benchmark | 论文报告 | 公开 harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo | 论文主实验 | `eval/main_loco_parse.py` | `locomo10.json`；harness 本身未锁 dataset hash | conversation→QA page；speaker_a 开 page，另一 speaker 回填；专用 eval engine | `IMPLEMENTATION_VARIANT` |
| LongMemEval | 未报告 | 无 | N/A | framework extension | `SOURCE_UNAVAILABLE` |
| HaluMem | 未报告 | 无 | N/A | framework extension | `SOURCE_UNAVAILABLE` |
| BEAM | 未报告 | 无 | N/A | framework extension | `SOURCE_UNAVAILABLE` |
| MemBench | 未报告 | 无 | N/A | framework extension | `SOURCE_UNAVAILABLE` |

论文另报告 GVD，但它不在 Phase 1。官方仓库只有 LoCoMo 的公开完整 benchmark 入口；README
把更多 benchmark integration 列为后续工作。因此后四格没有 `author_<benchmark>`，不从别家框架
或 benchmark prompt 反推一个“MemoryOS 官方配置”。

### 2.1 官方 LoCoMo topology 的目的与边界

官方脚本把 speaker_a 固定放进 `user_input`、另一 speaker 放进最近 page 的
`agent_response`，再用角色扮演 prompt 把真实 speaker 名恢复到 readout。这个选择与 MemoryOS 的
QA-page 数据模型一致：它让同一 page 同时具有 user/assistant 两侧，同时又不在存储文本里增加
额外 speaker 前缀。

但 current harness 的具体实现没有把 session 当 page 边界：`processed` 跨全部 session 累积，
speaker_b 开头的后续 session 会继续回填上一 session 的最后 page。对锁定的 10-conversation
`locomo10.json` 复算得到 272 sessions/5,882 turns，其中 124 个 session 以 speaker_b 开头、118 个
不是首 session；这 118 个跨 session 回填里，57 次填空侧，61 次覆盖上一 page 已有的
`agent_response`。官方转换共形成 2,957 pages，其中 87 个 user-only、6 个 assistant-only；eval
随后只迁移两侧都非空的 page，因此 93 个单侧 page 不进入 MTM。

这不是把官方方案简单判“错”：固定角色映射与 QA page 是作者的明确设计；跨 session 回填和
单侧丢弃则是 exact harness topology 的一部分，会影响作者数字。忠实数值复现应保留并命名为
`repo_eval_exact`；跨 benchmark 主表优先保住每个真实 turn、避免跨 session 覆盖，属于
`framework_corrected_product`。两条 estimand 不得共用同一 identity。

framework main 不是简单拒绝官方设计，而是保留其不变量并收紧异常边界：LoCoMo 仍按 session
投递、在 adapter 内用 speaker_a/speaker_b 组 page；session 之间不回填，assistant-first 或 dangling
turn 形成单侧 page，真实 turn 不被虚构 placeholder 内容替代。图片采用全框架共享的
`[Sharing image that shows: ...]` 契约，而不是官方 `(image description: ...)` 字符串；这属于可审计
的 cross-benchmark compatibility extension，不是 LoCoMo author payload parity。

## 3. Prompt / judge 合同

### 3.1 官方 LoCoMo final messages

official eval 的 answer 调用链为：

```text
STM.get_all + retrieval_queue + user profile/knowledge + assistant knowledge
  -> history_text / retrieval_text / background / assistant_knowledge_text
  -> [{role: system, content: role-playing prompt},
      {role: user, content: context+memory+traits+question prompt}]
  -> OpenAIClient.chat_completion(
       model="gpt-4o-mini", temperature=0.7, max_tokens=2000)
  -> 原样 response string
```

全部变量都来自公开 method state、真实 speaker 与 public question；gold answer/evidence 不参与 answer
payload。官方 response 没有 `ANSWER:`/JSON 等 parser，只取 SDK 返回的 content。`evalution_loco.py`
随后做本地 token-set F1，仓库没有 LoCoMo LLM judge prompt/model。

`src/memory_benchmark/prompts/author/memoryos.py` 已经：

- 用 AST parity test 锁住 official system/user 最终字符串；
- 保留 `system,user` role 顺序；
- 记录 `gpt-4o-mini / temperature=.7 / max_tokens=2000`；
- 提供“已组装字符串 → final messages”的可调用 helper。

但它要求调用者先自行构造 history/retrieval/background/assistant-knowledge，未把 method state
到这些变量的官方格式化链封装成 framework `AnswerPromptBuilder`；也没有显式 `.strip()` parser，
尚未被 `author_locomo` TOML/registry 选择。new registered run 只接受
`answer_builder="benchmark"`。因此准确状态是：

```text
FINAL_MESSAGE_TEMPLATE_PARITY_PASS / COMPLETE_AUTHOR_BUILDER_NOT_READY
```

而不是完整 `AUTHOR_READY`。完整 author reproduction 还要声明 build engine 是 `eval/` 还是
`memoryos-pypi/`、采用哪组冲突参数、图片格式和 ingestion topology；其中 eval 与 product 的差异
超出普通 TOML override。

### 3.2 main 与 author readout 的关系

- main：五 benchmark 都用 benchmark-owned answer builder，确保 method 间只比较 memory。
- author LoCoMo candidate：使用官方角色扮演 builder，作为补充校准；不能混入主表。
- judge：official MemoryOS 没有 LLM judge；main 继续使用 benchmark judge/程序 metric，不把“无
  official judge”解释成可自由选择 method judge。
- adapter 仍能生成 LoCoMo `prompt_messages`，但 registered answer composition 会用所选 builder
  明确覆盖；必须以 registry reachability，而不是“文件里存在 prompt”判断 active 身份。

## 4. 参数矩阵

| parameter path | upstream default | paper role | official effective values | current main | call site/最终 payload | 分类 | state/rebuild impact | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| engine/source | current PyPI | 分层 STM/MTM/LPM | LoCoMo `eval/` | patched current PyPI | registry + source identity | build/topology | 变化须全量重建 | eval/product=`IMPLEMENTATION_VARIANT` |
| build LLM | `gpt-4o-mini` | 论文实验含 GPT-4o-mini/Qwen2.5-3B | eval helper 默认/调用为 GPT-4o-mini | runtime profile 注入 | constructor→all product LLM helpers | build | 模型变化须重建 | main 锁 runtime identity；author 单列 |
| build LLM per-call decode | helper 内部 .0/.3/.7 与 10/100/2000 等 | 论文未逐调用披露 | eval helper 自带值 | 保持 current product 调用点 | `utils.py` helpers→OpenAI payload | internal build | 变化须重建 | 算法内部常量，不为统一而强改 |
| embedding | `all-MiniLM-L6-v2` | paper 未点名 | eval MiniLM | controlled MiniLM/384 | constructor→all local embed calls | build | identity 变化须重建 | `MAIN_CONFIRMED_CONTROLLED_AND_PRODUCT_EQUIVALENT` |
| STM page capacity | 10 | 7 | eval 1 | 10 | `ShortTermMemory(max_capacity)` | build | 改变迁移边界，须重建 | 三岔，main=current product |
| MTM capacity / segment length | product 只有 2000 session capacity | 200（maximum segment length） | eval 2000 session capacity | 2000 session capacity | `MidTermMemory(max_capacity)` | build | 改变淘汰，须重建 | current source 没有论文 200 的同义 cap，禁止把 2000 当成 paper value |
| LPM knowledge capacity | 100 | 100 | eval 无同等有界 deque | 100 | `LongTermMemory(knowledge_capacity)` | build | 改变淘汰，须重建 | main与paper/product一致 |
| retrieval page queue | 7 | LoCoMo 10、GVD 5 | eval 10 | 7 | `Retriever(queue_capacity)` | readout | memory 可复用；retrieval artifact 新 identity | main=current product；author LoCoMo=10 candidate |
| heat threshold | 5 | 5 | 5 | 5 | `_trigger_profile...` | build | 改变 LPM 更新，须重建 | 一致 |
| heat alpha/beta/gamma | 1/1/1 internal | 1/1/1 | .8/.8/.0001 | 1/1/1 internal | `compute_segment_heat` | build | 须重建 | eval/product variant，禁止伪装同参 |
| heat recency | 24h internal | `mu=1e7` seconds | 24h helper；retrieval recency 实际固定 1 | 24h internal | `compute_segment_heat`；search time-decay 被注释 | build/readout | 改变 heat/promotion 与排名，须按面重建/重检索 | paper/eval/product 三岔 |
| topic merge threshold | .6 | .6 | .6 | .6 | `Updater(topic_similarity_threshold)` | build | 改变 segment，须重建 | 一致 |
| segment/page thresholds | .1/.1 | 未披露 | .1/.1 | .1/.1 | `retrieve_context` | readout | retrieval identity 变化 | main=current product/eval；非 paper-reported |
| knowledge threshold | .01 | 未披露 | .1 | .01 | `retrieve_context` | readout | retrieval identity 变化 | product/eval 分叉 |
| top-k sessions | 5 | 5 | effective 5 | 5 | MTM search | readout | retrieval identity 变化 | 一致 |
| top-k knowledge | 20 | top-10 each | eval user=10、assistant=all | 20/20 | user/assistant LTM search | readout | retrieval identity 变化 | paper/eval/product 三种语义 |
| keyword contribution | query keyword set 强制为空 | semantic + keyword/Jaccard 属合并与检索机制 | eval 调 LLM 抽 query/page keyword | main 继承 product：query keyword disabled，summary keyword 仍参与 merge | `mid_term.py:281-330` | build/readout | 改变 segment 与检索，须重建/重检索 | `ALGORITHM_VARIANT`，不是可忽略优化 |
| product response decode | temp .7/max 1500 | 未逐调用披露 | eval temp .7/max 2000 | main 不调用 product response | `get_response` step 9-10 | answer topology | 不改 memory build；改变 answer 且会写回 | author LoCoMo 采用 eval 2000，不采用 product 1500 |
| `longmemeval_prompt_profile` | N/A | N/A | N/A | TOML 有值但无消费者 | 只在 validation/manifest | dead | 删除不得改变新 run 行为；旧 artifact 只读 | `DEAD_ACTIVE_CONFIG`，M11 退出 |
| product `get_response` | enabled public API | response module | eval 直接生成 answer | main 不调用 | adapter pure retrieval + reader | topology/readout | 改变会写测试 Q/A 入 memory | main 保持剥离；author 只换 builder |

`MemoryOSPaperConfig` 这个类名也会误导：它承载 current product + runtime/execution composition，
不是论文参数。M11 应在兼容迁移下改名；类中的 timeout/retry/workers 字段来自独立配置根，不是
重新塞回 method TOML。

## 5. 配置流与强反例

- method TOML → `MemoryOSPaperConfig`：11 个产品参数进入强类型对象；runtime LLM、timeout/retry、
  stdout 与 workers 来自独立 composition root，不在 method TOML 复制 smoke/full。
- factory → product：capacity、threshold、LLM、embedding 逐字段传入 `Memoryos`；retrieval 阈值与
  top-k 在每次 `Retriever.retrieve_context` 显式传入。
- unknown/type/range：未知 key、非正 capacity/top-k、越界 threshold、空模型名均在 API 前拒绝。
- dead field：`longmemeval_prompt_profile` 只被 dataclass validation/manifest 流经，retrieve 不按它
  分支；它是“能解析”但“不控制行为”的强反例。
- dead helper：`Updater._process_page_embedding_and_keywords()` 未被真实 STM→MTM 调用；其中未显式
  传 configured model 的 `_get_embedding_for_page()` 因此不是现行 effective embedding seam。真正
  的 page/session embedding 在 `MidTermMemory` 内使用 `self.embedding_model_name`。不能看到函数名就
  把 dormant 代码升级为运行参数。
- source identity：现行 12-file product hash包含 README/LICENSE，却不含 official eval/prompt asset；
  author profile 应另有 builder/harness source identity，不能继续把两类来源混成一个 hash。
- embedding：MiniLM 与产品默认语义相同，仍须锁 provider/model/revision/dimension/normalization/
  tokenizer；不能只因字符串相近就允许旧 state resume。

## 6. 主配置与作者配置裁决

- framework main：维持 patched current PyPI、跨五格同一产品参数、controlled MiniLM、benchmark
  builder。它回答的是“同一 current product 在五种任务上的可比表现”，不是论文数字复现。
- `author_locomo` candidate：final-message template parity 已完整，完整 builder/格式化/parser/注册尚未
  完成；参数也不能先随意选一套。paper-reported、repo-eval-exact 与 current-product-readout 至少
  是三个可区分 identity。
- product-default：current main 已基本等于 product defaults；它仍须显式标为 product identity，不能
  被 `MemoryOSPaperConfig` 名称重标成 paper。
- topology variant：eval engine 的 STM 迁移、heat 系数、单 LTM、keyword retrieval、page queue 与
  product engine 不同，完整官方复现需要独立 implementation variant，不是一个
  `[author_locomo]` scalar overlay 就能诚实表达。
- 第三方框架若选择 per-dataset 参数，有合理目标：逼近作者分数或适配各任务规模；本项目主表
  选择跨 benchmark 固定参数，是在优化 method 间可比性。二者 estimand 不同，不能互相判错；若
  引入 per-benchmark author profile，必须把目标和身份写入 manifest。

## 7. Manifest / resume / artifact

必须进入 identity：

- product upstream commit、vendored patch/source hash、adapter version；
- engine=`memoryos-pypi` 或显式 eval implementation variant；
- build LLM/transport 与 per-call algorithm decode source；
- embedding 全 identity；
- STM/MTM/LPM capacity、heat/merge 参数；
- retrieval queue/threshold/top-k；
- ingestion granularity/page mapping、timestamp/missing-time、caption 与 provenance patch；
- namespace/storage strategy；
- answer builder、official harness/prompt hash、decode/parser identity。

source、build LLM、embedding、capacity、heat/merge、page mapping 或 engine 变化必须全量重建。仅
retrieval top-k/threshold 或 answer builder 变化通常可以复用 memory state，但必须产生新的
retrieval/answer identity，且不能与旧 artifact resume。历史 config-track/readout-native artifact
永久按旧 manifest 回读，不回填新 author/main 标签。

gold answer/evidence/judge labels 不得进入 MemoryOS payload、metadata、formatted memory 或 answer
builder 的 public variable；official LoCoMo builder 只读 public question 与 method state。

## 8. 未闭合项与停工点

| item | status | 已查范围 | M11 下一条一手证据/动作 |
| --- | --- | --- | --- |
| paper MTM `200` 实现 | `MISSING_IN_CURRENT_SOURCE` | PDF p.6 与 product/eval constructor | 查补充材料/作者 issue；未闭合前不生成 paper TOML，也不拿 2000 替代 |
| eval/product author identity | `IMPLEMENTATION_VARIANT` | storage/update/retrieval/response 调用链 | 若要复现官方数字，建独立 engine/profile identity；不能冒充 product overlay |
| author LoCoMo builder/registry | `AUTHOR_NOT_READY` | template/final roles/decode 已闭合；变量格式化/parser/可达性未闭合 | M11 添加稀疏 profile、完整 builder/parser/source identity 与 fake-client parity |
| dataset identity | `PENDING` | official harness 只读裸 `locomo10.json` | author run 使用 framework LoCoMo source lock 并写 manifest |
| official metric adoption | `PENDING_METRIC_TIER` | official 仅 token-set F1 | 与 framework 通用 F1 公式逐项对表后再注册，不在 profile 批暗换 |
| dead config/class name | `PENDING_IMPLEMENTATION` | `longmemeval_prompt_profile` 无消费者；类名误导 | M11 迁移并保留旧 artifact reader |

本批没有需要提前修改生产代码的停工点；先完成十家证据矩阵，再在 M11 用一套配置模型施工。

## 9. 验证记录

- 调查：调度层明确请求两路 `gpt-5.6-luna` / `reasoning_effort=max` 只读调查，分别覆盖
  paper/current product 与 official LoCoMo harness。两个子任务的运行时自报只能看到泛化的
  `Codex/GPT-5` 身份，故本文不拿自报模型名证明路由；以调度请求作执行记录，以 claim-evidence
  收据和架构师独立复核判断事实质量。
- 架构师没有按两个回报“投票”。对承重接缝独立复算：current upstream commit/license、四个
  product patch、eval observer diff、LoCoMo 272-session census、跨 session 回填/覆盖、单侧 page、
  official final messages/decode、registered builder 可达性、paper 参数页和 TOML 最终消费面。
- 一个候选回报把 upstream+overlay 统称为 source pending；逐文件比较证明未 patch 文件与 current
  upstream 对齐，故最终裁为“current source + declared patches”可锁，而不是年代不明 mixed fork。
- 架构师现场 source probe：`file_count=12`、vendored source=
  `5a9af420f01285b0b0ed2846864dbd20cfa78a61b977c2d4352eba4211ce08dd`、combined source=
  `7c82b26967a57715b91c968cf177f27f2161ede4d0727a5f4c783dd431b37e9b`、wrapper=
  `64946cdf67ebc6158e9491900f1241f17a2baf08e6073ed4d45e4144c8f49bd4`。
- current upstream probe：`587ed7755c7aed179965792830ff1b5ad9a6fa92`；对比确认四个 product
  patch 文件，official eval 只有纯 observer 差异。
- 零 API命令：`uv run pytest -q tests/test_memoryos_adapter.py
  tests/test_memoryos_registered_prediction.py tests/test_memoryos_native_prompts.py
  tests/test_config_profiles.py tests/test_method_registry.py tests/test_documentation_standards.py
  tests/test_codex_project_hooks.py`。
- 最终复验尾行：`255 passed in 10.96s`。
- `git diff --check`：无输出。
- 架构验收：`ACCEPTED`。验收只关闭 M4 证据门；M11 前不把 author helper 写成可运行 profile，
  不把 paper/eval/product 参数揉成一份 TOML，也不恢复真实 API pilot。
