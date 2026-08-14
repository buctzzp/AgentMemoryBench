# 十家 method 后的可维护性审计与 M1 裁决（2026-08-14）

## 0. 总判词

**暂停 ws05 成本 pilot，ws03 升为当前唯一 P0；先做一轮有停手线的 M1，不做全仓美化式
重写。**

5×10 smoke 已使十家 method 的真实接口样本齐全，且尚未进入昂贵 official/full 实验。现在
是消除迁移期控制面和结构债的正确窗口。目标是降低下一次改动的波及范围，不是追求目录
完全对称、删除量或漂亮行数。

M1 只处理四条承重线：

1. live 文档 freshness 与依赖方向；
2. `unified/native` 活跃选择器迁到 TOML profile，旧 artifact 只读兼容保留；
3. 四家隔离 method 的共享 JSON-lines transport；
4. `prediction.py` 的稳定职责拆分。

达到 §7 停手线后回到 ws05/指标/作者校准的用户选择，不把“长期优化”变成永无止境的主线。

## 1. 本轮证据边界

本轮只读检查了当前 `main@553bc9c` 的源码、测试、配置与 live 文档；没有调用 API、改
third-party、数据、模型或 outputs。工作树中既有五项用户未跟踪资产保持不动。

关键现场：

- `src/memory_benchmark/` 约 58k 行；`runners/prediction.py` 3,336 行，
  `methods/registry.py` 2,325 行；六家 adapter 超过 1,700 行；
- `metrics/` 已有纯 text/retrieval/ranking kernel；`evaluators/common/` 已有 artifact 与
  retrieval 编排共壳；
- `lightmem_native_prompts.py`、`mem0_native_prompts.py`、
  `memoryos_native_prompts.py` 都只有 re-export，canonical owner 已在 `prompts/author/`；
- EverOS、Graphiti、LangMem、Letta 各有独立 worker，并在 adapter 重复主进程
  `_request/_drain_worker_stderr/_terminate_worker` 等 transport；
- MemOS 的 lifecycle 是本地 task tracker + business-task waiter，不是上述 subprocess
  transport；
- 当前没有 `.github` CI，`pyproject.toml` 也没有 lint/type gate；本批不因此一口气引入
  全套工具，先建立能抓当前真实风险的边界测试；
- 本批开工时 `docs/README.md` 指向不存在的 `reference/code-structure-principles.md`；M1-A0
  已补齐该稳定页，后续要用 live-link gate 防止复发；
- roadmap 已写 5×10 closed，但 ws02 仍是唯一 `in-progress/P0`，会把 compaction hook 引向
  过时任务线；ws03 README 还写“下一步回 MemOS”。

## 2. 用户点名问题的逐项裁决

### 2.1 `metrics/` 与 `evaluators/` 不重复

- `metrics/` 是不认识 benchmark/method/artifact 的纯函数层；
- `evaluators/` 负责 artifact 读取、gold view、排除政策、资格、N/A/pending、summary 与
  LLM judge。

Recall 公式应只有一份，但 LoCoMo、LongMemEval、MemBench、BEAM 的 gold unit、空 gold、
排除规则和诊断字段不能被抹平。当前“纯内核 + common shell + 薄 benchmark policy”方向正确。
后续可以把 policy 物理归到 `evaluators/benchmarks/`，但搬目录不是 M1 优先级。

### 2.2 `_worker.py` / lifecycle 的不对称是合理组合

EverOS、Graphiti、LangMem、Letta 的 worker 解决第三方 Python 版本、依赖树、数据库/产品
runtime 隔离；它们不读取 gold，也不负责最终 answer。MemOS lifecycle 解决进程内异步
scheduler 的精确完成、失败传播和 cleanup。

它们与普通 adapter 的公共接口相同，内部资源约束不同。强制十家都只有一个 adapter 文件，
反而会把进程和生命周期耦合塞回大类。应统一“可选组件何时出现”的规则，不统一文件数量。

### 2.3 `lightmem_native_prompts.py` 是兼容债，不是第二份 prompt

该文件当前只有 4 行 re-export；真实实现已迁到 `prompts/author/lightmem.py`。Mem0、MemoryOS
同理。它们仍被旧测试和 `config_track` 测试 import，所以现在直接删除会制造无意义回归。

裁决：M1 先把仓库内部消费者迁到 canonical path，并加“新代码不得 import shim”边界门；
再按 §6 兼容预算删除。名字中的 `native` 不再进入新设计。

### 2.4 巨型文件是真结构债，但不能按行数机械切

`prediction.py` 同时负责 work plan、manifest/resume preflight、ingest、answer、并行 worker、
artifact/efficiency 收口。它有多个独立变化原因，应优先拆。目标结构是由原入口保留薄编排，
逐批抽出 planning/preflight、ingest、answer、parallel leaf；每批保持公开函数与 artifact 字节。

`registry.py` 同时承载十家 factory、source/build/embedding identity、clean hook 与注册表。它也
应拆，但排在 prediction 之后，避免两个中心模块同批 churn。adapter 只在共享 transport 抽取后
按每家真实职责继续拆，不把“低于 N 行”设成 KPI。

## 3. 两个优先级高于“搬文件”的依赖倒置

### 3.1 `runners → cli`

`runners/cost_calibration.py` 从 `cli/run_prediction.py` import
`PredictionBatchResult` 与 `run_registered_conversation_qa_prediction`。CLI 应是最外层，runner
反向依赖 CLI 会形成 `cli ↔ runners` 环。

修法：把 registered prediction application service 与结果 contract 下沉到中立模块；CLI 和
cost calibration 都依赖它。不得用局部 import 或 `TYPE_CHECKING` 掩盖运行时环。

### 3.2 `prompts → evaluators`

`prompts/author/lightmem.py` 与 `prompts/author/mem0.py` 直接保存 evaluator class。prompt 资产
因此反向依赖执行层，形成 `evaluators ↔ prompts` 环。

修法：author profile 只声明稳定 judge profile key/数据；evaluator registry 在组合根把 key
解析成 class。prompt 包不再 import evaluator。现有 `test_prompt_layering.py` 只守住
`prompts/benchmarks → methods`，M1 要补整包依赖方向门。

## 4. `unified/native` 的准确迁移边界

旧双轨不是“一删文件”能结束。当前仍有三类事实混在 `config_track.py`：

1. **应迁走的活跃选择策略**：CLI `--config-track unified/native`、native bundle、按 track
   分支选择 answer settings/builder；
2. **仍有价值的新 run identity**：implementation/build/embedding/readout 的强类型声明；
3. **必须保留的历史回读**：Phase 1 旧 manifest 的 `TrackIdentity v1` 与输出目录中的
   `unified/native` segment。

M1 裁决：

- 新 run 只选择 method TOML section（`smoke`、`official_full`、稀疏
  `author_<benchmark>`），由 section 声明完整 `answer_builder`；
- 把通用 run/build/embedding identity 从旧选择器模块拆出，名称不再暗示双轨；
- 旧 `TrackIdentity v1` parser、旧 artifact evaluate/cost readback 长期保留，不改写历史；
- 旧 CLI 不再出现在 live docs；待 profile 路径闭合后发 deprecated warning，随后删除“生成新
  native run”的能力；
- 不在本轮虚构作者没跑过的 `author_*` section，也不自动按 benchmark 切配置。

## 5. M1 实施顺序

### M1-A：freshness 与依赖方向（先做）

1. 修正 roadmap/ws02/ws03/ws05 当前状态，建立唯一恢复入口；
2. 补稳定结构判据页与 live-link 检查的最小覆盖；
3. 切断 `runners → cli`、`prompts → evaluators` 两条反向边；
4. 新增 AST/import architecture test，只守当前明确层级，不做全仓形式主义规则；
5. 盘点 shim/legacy 的真实消费者、公开承诺与退出门。

验收：零 API；定向 import/CLI/prompt/cost tests + compileall + 无 API 全量回归；manifest、prompt
和 cost command 行为守恒。

### M1-B：TOML profile 取代活跃 config-track

1. loader/registry 解析 section 与完整 builder identity；
2. manifest/resume 锁 section、解析配置、builder 与 runtime；
3. 分离 active run identity 与 legacy `TrackIdentity v1` readback；
4. 迁移 live CLI/docs/tests；旧 artifact evaluator 保持可读；
5. 内部 canonical import 清零后退出三家 `*_native_prompts.py` shim。

本批可能改变新 run 的 manifest/output identity，必须另立迁移 note；不复用旧 run_id，不调用 API。

### M1-C：共享隔离 worker transport

只抽 adapter 主进程侧已经四次出现且语义等价的 JSON-lines transport：request id、锁、stdout
response、stderr 尾部、timeout、终止与 secret-safe 错误。每家保留自己的 worker engine、环境、
Docker/DB 启动、conversation namespace 和 cleanup。

先以 EverOS/Graphiti 两家锁等价，再接 LangMem/Letta；异常、超时、坏 JSON、worker 提前退出、
二次 cleanup 均需 mutation/强反例。不要把 standalone worker 内的产品 schema 强行通用化。

### M1-D：prediction 编排拆责

按 leaf-first 顺序抽 planning/preflight → ingest → answer → parallel。原
`runners.prediction` 保留公开 façade；不得同批改 registry、metric、prompt、resume schema。
完成后再决定 registry registration descriptor 是否进入 M1-E，不能预先承诺大搬家。

## 6. 兼容与文档退出预算

| 资产 | 当前分类 | 退出门 |
| --- | --- | --- |
| `BaseMemoryRetriever` | 零生产引用候选 | 内部/公开引用扫描 + core/CLI/full tests；确认无外部稳定 API 承诺 |
| `methods/*_native_prompts.py` | 薄 import shim | 内部 import 清零 + canonical parity test + config-track active path 退出 |
| `evaluators/{answer_text,retrieval_metrics,halumem_prompts}.py` | 薄 shim | 内部 import 清零；逐个评估外部示例与历史扩展，不捆绑删除 |
| `BaseResumableMemorySystem` / `LegacyProviderBridge` | 活跃兼容 | 先迁生产调用；当前禁止删除 |
| `TurnIngestCheckpointStore` | 活跃 resume 能力 | 保留，不因 `ingest_resume.py` 名字误判 |
| `runners/memoryos_locomo_{smoke,full}.py` | 冻结的 legacy reproduction capsule | 新 run 禁止使用；受保护旧产物仍需复现，先迁 `legacy/` 命名空间并保留 import shim，不删逻辑 |
| `dual-track-config-policy.md` | superseded 历史政策 | live inbound link 清零后迁 archive，保留历史链接映射 |
| 旧 artifact `TrackIdentity v1` | 历史事实 | 长期只读兼容，不删除、不改写 |

本项目版本为 `0.1.0`，尚无已声明稳定 Python import API。因此内部 shim 不需要永久保留；但公开
CLI 和已有实验 artifact 的审计价值高于源码洁癖，分别按迁移公告与只读兼容处理。

## 7. 停手线与非目标

M1-A 至 M1-D 完成且以下条件全绿即停止本轮 ws03：

- 两条已知依赖环消失，并有自动防回归；
- 新 run 不再由 `unified/native` 选择行为，旧 artifact 仍能 evaluate/readback；
- 四家共享 transport 只有一份主进程实现，产品 worker/lifecycle 差异仍显式；
- prediction 入口成为薄编排，planning/preflight/ingest/answer/parallel 可独立测试；
- active docs 无已知断链，roadmap 只有一个正确的 `in-progress/P0`；
- 每批无 API 全量测试通过。

明确不在 M1：

- 不改 metric 公式、gold policy、prompt 字节、method 算法或第三方源码；
- 不跑成本 pilot、official full 或任何真实 API；
- 不统一十家 adapter 的文件数量；
- 不按行数删除代码，不批量格式化全仓；
- 不一次引入 Ruff、mypy、coverage、CI 全家桶。工具按真实缺陷采用 ratchet，另批落地；
- 不移动/删除 `data/`、`models/`、`outputs/`、third-party 或用户未跟踪资产。

## 8. 文档治理后续

M1-A 先覆盖 live 入口链接；不让 archive 的历史断链拖成无边界修复。后续按三类处理：

- **稳定页**：`reference/`、`survey/`，只保留架构师验收后的 current 事实；
- **证据页**：workstream notes/cards，完整保留命令、反例、改判；关闭后从热入口降权，不删除；
- **历史页**：superseded spec/status 迁 `archive/`，保留跳转；
- **scratch**：未验收聊天粘贴与临时调查默认不跟踪，吸收精华后删除需逐项授权。

文档 freshness 由状态唯一写点、live link gate、superseded 链和恢复胶囊共同保证；不靠每次全文
阅读，也不靠把全部聊天倾倒进仓库。

## 9. M1-A0 文档基础批结果

本 note 同批完成以下零生产行为变更：

- ws03 设为唯一 `in-progress/P0` 并新增短恢复胶囊；
- ws02/ws05 按用户裁决标 `paused`，ws02 的旧流水账显式降为历史断点；
- 新增稳定 [`code-structure-principles.md`](../../../reference/code-structure-principles.md)，
  修复 `docs/README.md` 的 live 断链；
- 刷新 TOML/answer-builder 政策中已完成的旧“当前主线”；
- 把“必要不对称”和“重构停手线”写入架构师热手册。

自检：`uv run pytest -q tests/test_documentation_standards.py` → `5 passed in 1.26s`；本批 8 份
changed/live 文档相对链接探针 `missing=0`；`git diff --check` 无输出。M1-A 尚未完成，下一批
才切依赖环和落仓库内自动 architecture/live-link gate。
