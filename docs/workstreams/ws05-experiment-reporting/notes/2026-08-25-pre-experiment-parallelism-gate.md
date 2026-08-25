# 开跑前 isolation 并行门（2026-08-25）

## 1. 裁决

conversation/UUID 并发资格与“最小用 W2 验证”必须分开：W2 是抓共享状态竞态的最小
强反例，不是 method 能力天花板。只要每个 worker 的可变 runtime/state 独立、每个
isolation 的 namespace 完整、worker lane 内调用顺序稳定，并发规模应由统一
execution/resource policy 控制，不在 adapter 或 method TOML 写死 2。

当前 execution profile 只提供保守**默认值**：smoke/pilot 默认 W1、official 默认 W10；
它们不是上限。CLI 显式 `--workers N` 接受任意正整数，真实启动数仍是
`min(N, selected isolations)`。method registry 只有在产品确有不可绕过的硬约束时才声明 cap；
Letta、MemOS 与当前其余内置 method 均不把 2 或 10 冒充能力天花板。实际可放多少由操作者当前
资源预算决定，后续资源调度器应做 admission control/排队，而不是 adapter 静默截断。

## 2. 四层不能混淆

1. **benchmark isolation**：LoCoMo conversation、LongMemEval instance、MemBench tid、
   BEAM conversation、HaluMem UUID 是相互独立的实验单元。
2. **method namespace**：同一 runtime 内的读、写、删必须完整带 isolation identity；逻辑隔离
   不等于线程安全，但它决定业务状态能否复用一个 worker runtime。
3. **runtime ownership**：tokenizer、scheduler、stdio worker、container、临时 DB 等可变对象
   是 per-worker 还是全进程共享。并发事故通常发生在这一层。
4. **resource policy**：主机实际允许多少 Docker、模型副本、DB 连接与 API 请求。资源上限应
   fail-loud 或排队，不能静默降级、换配置或改变分数。

共享只读 dataset bytes、immutable embedding weights 或 stateless transport 属另一层工程优化；
在输入顺序、随机性、namespace、retry/resume 与 artifact 等价门通过前，不与本次并行修复混做。

## 3. HaluMem UUID 并行

- operation-level runner 不再把整个 benchmark 硬锁 W1。
- 并行轴只在 UUID；一个 UUID 内仍严格按 session 原序执行
  `ingest → end_session/extraction → update probe → QA → end_conversation`。
- 完整 selected UUID 顺序按 `index % worker_count` 稳定映射到 `worker_<idx>`，所以同一
  `run_id + max_workers` 的 resume 不会把 UUID 换到另一份 state root。
- 每个 worker 独占一份 provider/runtime，在 lane 内串行复用；不是每个 UUID 重启一次 method。
  worker 只把完整 UUID batch 交给 coordinator，artifact/status/efficiency 仍由 coordinator
  单线程提交并按 dataset 顺序重排。
- `max_new_conversations` 在 operation-level 同样按 UUID 生效；HaluMem 的 UUID 就是成本校准的
  isolation，不再需要外造“W1 child run 分片器”。

## 4. Letta

- 每个 worker storage root 参与 runtime identity，派生不同 PostgreSQL container、volume 与
  runtime tag；不同 worker 不共享 AgentLoop/stdio transport。
- 一个 worker lane 内复用自己的 product runtime，并用 subject/agent identity 隔离多个
  conversation。
- 零 API 强反例断言两个 worker 的 identity/container/volume/runtime tag 全部不同。
- 每多一个 worker 就多一套 PostgreSQL + worker，故“语义可横向扩展”不等于主机应无界放行；
  实际数量归统一资源政策。

## 5. MemOS v6

### 5.1 历史失败根因

v5 的两个 isolated provider 默认落到同一个进程级 `_MemosRuntimeOwner`，从而共享同一
SentenceTransformer tokenizer；真实 LongMemEval W2 触发 `RuntimeError: Already borrowed`。
该反例证明共享 runtime 不安全，不证明 MemOS 的 namespace 不能并行。

### 5.2 修复

- 默认每个 provider/worker 新建自己的 `_MemosRuntimeOwner`、runtime、embedder 与 scheduler；
  删除无人消费的全局 owner 常量。
- `init_server()` 读取/恢复 process-global `os.environ` 的短构造区间用进程锁串行；构造完成后
  ingest/retrieve 不持该锁，业务并发没有被伪装成串行。
- clean hook 构造的临时 provider 自己验证 namespace 并在 `finally` 收敛 runtime，不再期待根
  provider 接管全局 owner。
- adapter version 由 `memos-v2.0.25-product-v5` 升为 `...-v6`；旧 state/artifact 不重标、不 resume。

零 API强反例让两个默认 provider 的 runtime factory 在 barrier 同时会合；若恢复旧全局 owner，
第二个线程会被同一 owner lock 阻塞并使测试失败。另用两份真实本地
`SentenceTransformer(models/all-MiniLM-L6-v2)` 同时 encode，得到两个 `(1, 384)` 结果且
模型对象不同，未再出现 tokenizer borrow 竞态。

## 6. 资格边界与下一门

本批不调用真实 API，也不把零 API ownership 证明冒充产品吞吐压测。开成本校准前还需用新
run 做最小真实 sentinel：Letta 与 MemOS 各至少两个完整 isolation，HaluMem 选择至少两个 UUID，
并核对并发重叠、namespace、cleanup、efficiency scope、artifact 顺序与失败传播。sentinel 用
W2 即可暴露共享状态；通过后可按资源政策选择 W3、W10 或更高，无需逐个并发值重新证明算法
资格。更高并发仍须做容量/限流压力门，但那是资源资格，不是改写 method 算法能力。

未来共享 dataset/embedding 服务只有在相同 source/model identity、不可变输入、稳定顺序、
相同随机种子与 serial-vs-shared artifact/score 等价门通过后才可启用。此类工程优化原则上不应
改变测评结果；若结果变化，它就不是纯优化，必须作为新的实验身份处理。

## 7. 零 API验收收据

- CLI/planner：MemOS `--workers 16` 可生成原样 argv；registered resolver 接受 W37，只有显式
  产品硬 cap 才拒绝。execution profile 的 W1/W10 继续是默认值，最终选择写入 composition
  manifest 与 resume identity。
- operation runner：`max_workers=16`、4 个 UUID 的强反例真实启动
  `worker_0..worker_3` 四条 lane；不是内部截成 W2。W2+3 UUID 又证明一个 lane 只 prepare/
  cleanup 一次并串行复用两个 UUID。
- 失败边界：同一 lane 后续 UUID 失败时，先前两个完整 UUID 保持 `completed` 且 artifact 可读；
  lane cleanup 失败会向顶层抛错，但不会把已提交 business batch 伪写成 `failed_ingest`。
- MemOS source identity 复算仍为
  `602678ba7fe3995a582627de4e14a91d89dea2c33827e98314b24209f5e1206d`。
- 定向联合门：`603 passed, 12 warnings`。
- current 全量门：`2304 passed, 3 deselected, 25 warnings, 29 subtests passed in 238.87s`；
  `git diff --check` 干净。全程未调用真实 API。
