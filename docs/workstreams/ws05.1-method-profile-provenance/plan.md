# ws05.1 计划：十家逐一闭合

> 每一家独立完成“现有资产检索 → current source 复核 → prompt/parameter 矩阵 → 稳定页回填 →
> 架构验收”后，才进入下一家。默认全程零真实 API；不得为了速度把十家调查一起铺开。

## M0 规则与资产模板

- [x] 把参数语义、证据来源、主配置/作者配置边界写入长期政策。
- [x] 建立独立 workstream、恢复胶囊、spec 与串行计划。
- [x] 建立 `notes/method-profile-provenance-matrix.md`，预填十家已有 repo/论文/官方 benchmark
  覆盖与 `src/memory_benchmark/prompts/author/` 现状。
- [x] 给每家 note 固定同一字段模板，并加文档标准门，防止十份记录逐渐漂移。
- [x] 模板首屏固定包含论文/技术报告 identity、算法阶段图、current source 对应调用链；没有论文时
  记录官方替代材料与证据等级，禁止跳过机制理解直接填写参数表。

## M0.5 第三方框架配置策略对照

- [x] 盘点 `第三方框架参考/` 根目录，筛出真正覆盖多 method × 多 benchmark 且具有可追配置链的
  框架；至少包括 OmniMemEval、MemoryData、EverOS/EverCore evaluation，并判断 MemEval、
  agent-memory-benchmark、memorybench 是否达到深读门槛。
- [x] 对每个入选框架追踪“声明配置 → merge/override → adapter/product 最终参数”，不能只读
  `env_examples`、YAML 文件名或 README。
- [x] 逐 method 判断其策略属于跨 benchmark 真统一、repo default、per-benchmark 调参、混合/
  隐式覆盖或证据不足；同时记录 embedding、LLM、prompt/judge 与 runtime 参数是否被混在一起。
- [x] 产出 `notes/third-party-framework-config-strategy-audit.md`，提炼可借鉴机制与不可照搬风险；
  第三方选择不得直接生成本项目 author profile。
- [x] 根据对照结果只修订本 spec/长期配置政策的判据，不直接修改十家 TOML；参数改动仍须等
  对应 method 的官方一手证据批次。

## M1-M10 单 method 顺序

- [ ] **M1 LightMem**：用 `pre_compress` 三证闭环校准方法；复核 LoCoMo/LME author builder、
  `messages_use`、segmentation/summary/update lifecycle 与全部高影响数值。
- [ ] **M2 A-Mem**：优先读取独立官方评测仓库 `third_party/methods/A-mem`，补齐已知遗漏的
  LoCoMo prompt、decode/parse 与 reported config；与通用产品 `third_party/A-mem` 算法身份对表。
- [ ] **M3 Mem0**：区分 current product、current memory-benchmarks 与旧论文 harness；双 namespace/
  role reversal 若属 topology variant，不压成普通 author TOML。
- [ ] **M4 MemoryOS**：闭合官方 LoCoMo 角色扮演 builder、paper/eval/PyPI 参数矛盾与 readout-native
  边界。
- [ ] **M5 MemOS**：核官方 LoCoMo/LongMemEval harness、product typed-handler effective config 与
  author batching/readout 差异。
- [ ] **M6 SimpleMem**：核论文完整三阶段、串并行窗口语义、官方 benchmark/prompt 可得性及高影响
  window/overlap/retrieval 参数。
- [ ] **M7 Letta/MemGPT**：锁 legacy/product 版本与官方 eval 覆盖；区分省略 embedding、core-block
  profile 和作者 prompt，不用 hosted 默认倒推。
- [ ] **M8 LangMem**：锁官方公开 benchmark 覆盖、manager/strategy 参数、反思/update/delete 开关
  与最终 prompt；无官方 harness 时诚实留空 author section。
- [ ] **M9 EverOS**：对齐 current EverOS/EverAlgo/独立 evaluation config，区分 product chat、paper
  identity 与 controlled embedding；找不到公开 harness 的结果不伪造。
- [ ] **M10 Graphiti OSS**：只声明 Graphiti，不借 Zep hosted prompt/结果；核 episode extraction、
  graph search/rerank 参数和公开 eval 资产。

## M11 横向裁决与实现

- [ ] 对十家矩阵做重复值/矛盾/缺源审查；标出 `MAIN_CONFIRMED`、`AUTHOR_READY`、`PENDING`、
  `SOURCE_UNAVAILABLE`、`IMPLEMENTATION_VARIANT`。
- [ ] 只对证据要求的字段修改 `configs/methods/*.toml` 与强类型 config；不借机调优。
- [ ] 为 `AUTHOR_READY` 格注册完整 builder 与稀疏 profile；未知名称或变量链不完整时 pre-API
  fail-fast。
- [ ] method 官方 judge 只形成候选清单；未经独立 metric/tier 裁决不进入主 evaluator registry。
- [ ] 运行定向 mutation、prompt final-message parity、manifest/resume、文档标准与无 API全量门。
- [ ] 更新父 ws05 重建矩阵；由用户重新批准预算、规模、run_id 后才恢复 pilot。
