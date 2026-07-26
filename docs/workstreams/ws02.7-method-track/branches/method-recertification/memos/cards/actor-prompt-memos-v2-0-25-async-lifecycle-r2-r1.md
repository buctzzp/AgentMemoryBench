# Actor 返工卡：MemOS v2.0.25 async lifecycle R2-R1

**本卡被发送到当前 actor 会话即代表用户已完成选择与授权；直接执行，不要再选择、派发或
等待另一个 actor。**继续使用既有 worktree
`/Users/wz/Desktop/mb-actor-memos-r2` 与 branch
`actor/memos-v2-0-25-async-lifecycle-r2`，在首轮 `d1a0178` 之上追加一个 follow-up
commit；不得 amend、rebase、merge、push 或开始 adapter。

本卡只修架构师强验收已复现的 R2 缺口。主 profile 仍锁定
`typed AddHandler → async+fast → local MEM_READ → fine`；不得改成 sync/fine，不调用
真实 API、模型、数据库、HTTP、Redis 或网络。

## 0. 首轮判词与本批唯一目标

首轮 `d1a0178` **未通过架构师验收**，不能使用其
`READY_FOR_MEMOS_ADAPTER` 判词。以下四项已由架构师在 current source 上独立复现：

1. `git show --check d1a0178` 以 exit 2 失败，patch 文件有 23 处尾随空白；
2. `test_async_mem_read_happy_path_shared_trace` 从 `text_mem.get(raw-1)` 才开始，
   未经过 fast reader/write、scheduler submit、local queue、dispatcher/tracker，也没有
   `completed`；其 fine write/delete/refresh 又由测试类覆写，因此不是卡 §6.2 要求的
   完整 product-chain trace；
3. `MultiModalStructMemReader._get_llm_response()` 把真实 LLM/JSON 异常改写成
   “原文作为 UserMemory”的成功结果；`_embed_memory_items()` 在 batch 与逐项 fallback
   全失败后仍正常返回且 embedding 为 `None`；
4. `MemReadMessageHandler` 对 `merged_from` 旧记忆的 `graph_db.update_node()` 失败
   仍只 warning，随后删除 raw、refresh 并正常返回。

因此本批唯一允许的终态是：

```text
READY_FOR_MEMOS_ADAPTER(
  product reader failures are observable;
  full async chain reaches one exact terminal state;
  patch and report are self-consistent
)
```

或：

```text
BLOCKED(<无法在 success-path 守恒下关闭的首个问题>)
```

## 1. 最小必读与 source identity

只读：

1. `AGENTS.md`
2. `docs/workstreams/ws02.7-method-track/README.md` 顶部恢复胶囊
3. `docs/reference/actor-handbook.md`
4. 首轮 R2 卡与首轮 implementation note
5. 本卡点名的 current source/test

nested source 必须仍是：

```text
/Users/wz/Desktop/memoryBenchmark/third_party/methods/MemOS
v2.0.25
e820406269537b97d270687e3e40eea2f015f81a
```

开工先验证 dirty 恰好等于首轮 patch；若多出无法解释的改动，立即停工。

## 2. 锁定裁决

### 2.1 “合法零抽取”的边界

只有 **LLM 调用成功、结果成功解析、生产 reader 明确产出空 memory list** 才是合法零抽取，
可以 completed。下列情况一律不是合法零抽取：

- LLM transport/generation/JSON parse 抛异常；
- parser worker 或 fine worker 抛异常；
- memory item 构造或 embedding 抛异常；
- batch embedding 失败后任一逐项 fallback 仍失败；
- 有 `merged_from` 却无法完成旧记忆 archive。

不得继续用“让 fake `fine_transfer_simple_mem()` 直接 raise”证明内部 catch 已关闭；异常必须
从真实最低层 production 叶子注入，并穿过 current reader 自己的 catch 边界。

### 2.2 Reader 失败传播

把下列 **current chat 主路径**的 silent partial/fallback 改成失败可见，且所有已经启动的
并行项先 settle 再 aggregate raise：

- `MultiModalStructMemReader._read_memory()` 的 scene future；
- `_process_multi_modal_data()` 的逐 message parser future；
- `_embed_memory_items()`：
  - batch 成功：行为不变；
  - batch 失败但全部逐项 fallback 成功：行为不变；
  - 任一逐项 fallback 失败：尝试完其余项后 aggregate raise；
- `_get_llm_response()` 的 LLM/parse exception：不得再伪造原文 UserMemory；
- `_process_transfer_multi_modal_data()` 的 fine worker；
- `_process_one_item()` 内 LLM 调用与 memory item 构造失败：不得静默降为空或部分结果。

只处理 benchmark chat 主路径；不要顺手改 tool trajectory、memory-version-on、文档/图片
真实 vision 路径或成功态的 chunk fallback。所有新增行为只能发生在已有 exception/
invalid-result 路径。

### 2.3 Fine archive 失败传播

`MemReadMessageHandler._process_memories_with_reader()` 中：

- 对同一 fine batch 的所有 `merged_from` old ids 都先尝试 archive；
- 任一 `graph_db.update_node()` 失败，最终 aggregate raise；
- 若确实出现 `merged_from` 但 `mem_reader.graph_db is None`，fail-fast，不得完成；
- 无 `merged_from` 时的成功路径字节、调用序和结果不变。

### 2.4 Tracker anti-corruption

本地 tracker 是严格完成门，不继承 upstream Redis tracker 的 permissive 坏状态：

- 同一 `(user_id, item_id)` 不得被静默改绑到另一个 business task；
- 相同身份的重复 `task_submitted` 只能幂等，不能把 started/terminal 重置为 waiting；
- `failed` 与 `completed` 是单调终态，后来的冲突 callback 不得覆盖原终态；
- started/completed/failed 遇到从未 submitted 的 item 必须 fail-fast，不能创建无
  business-index 的 orphan record。

正常 current dispatcher 的单次提交/单次终态行为必须保持。

## 3. 允许文件

父仓库只允许：

```text
scripts/patches/memos-product-runtime-observability.patch
scripts/fetch_third_party_methods.sh
third_party/methods/MANIFEST.md
src/memory_benchmark/methods/memos_lifecycle.py
tests/test_memos_lifecycle.py
docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-async-lifecycle-r2-implementation.md
docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-async-lifecycle-r2-r1-implementation.md
```

nested repo 只允许由 patch 表达：

```text
src/memos/mem_reader/multi_modal_struct.py
src/memos/mem_scheduler/task_schedule_modules/handlers/mem_read_handler.py
src/memos/multi_mem_cube/single_cube.py
src/memos/memories/textual/tree.py
src/memos/memories/textual/tree_text_memory/organize/manager.py
src/memos/graph_dbs/neo4j_community.py
```

若需要其他生产文件，停工。fetch/MANIFEST 若无需语义变化可保持不动，不制造空 diff。

## 4. 必须新增的强反例

### 4.1 完整 async product chain

新增一条**单一共享 trace**，至少从真实
`AddHandler.handle_add_memories(APIADDRequest)`（若装饰器使 hermetic 构造不可行，最窄
可接受降级是 `SingleCubeView.add_memories(APIADDRequest)`，但必须在 note 解释）开始，
穿过：

```text
fast reader
→ fast TreeTextMemory.add / MemoryManager batch write
→ SingleCubeView._schedule_memory_tasks
→ BaseSchedulerQueueMixin.submit_messages
→ local queue
→ SchedulerDispatcher real wrapper
→ MemReadMessageHandler
→ fine reader
→ fine TreeTextMemory.add / MemoryManager batch write
→ raw TreeTextMemory.delete
→ refresh
→ tracker.completed
→ wait_for_business_task 返回
```

保持 product-default `enable_parallel_dispatch=true`；测试可以等待真实 executor future，
但不得把 dispatcher 改成同步来简化。外部 LLM/embedder/graph/vector 叶子可 hermetic fake，
不能覆写上述 MemOS 算法函数或 framework tracker callback 来跳过链路。

### 4.2 Reader 与 archive 强反例

至少覆盖：

1. LLM generation 抛错，真实 `_get_llm_response` 不再生成 raw fallback；
2. batch embedding 失败、所有逐项 fallback 成功仍通过；
3. batch 与至少一个逐项 embedding 都失败，全部逐项尝试后 raise；
4. initial parser 一项失败、一项成功，等二者 settle 后整体失败且不写 partial fast memory；
5. fine worker 一项失败、一项成功，等二者 settle 后 task failed；
6. fine memory item 构造/embedding 失败不能变成合法零抽取；
7. 成功且空的 LLM result 仍 completed；
8. `merged_from` archive 一项失败、一项成功，两个 old id 都尝试且最终 task failed；
9. `merged_from + graph_db=None` fail-fast。

异常必须注入到真实 LLM/embedder/parser/graph leaf；不得直接让高层 reader fake raise。

### 4.3 Tracker 强反例

至少覆盖：

- `failed → completed` 冲突不会把失败改成成功；
- completed item 的重复 identical submit 不会退回 waiting；
- 相同 item id 改绑另一个 business id fail-fast，旧 business index 不被污染；
- 未 submit 的 started/completed/failed fail-fast；
- 原有并发、namespace、数量、timeout、shutdown 用例全部保留。

### 4.4 Mutation

对 reader LLM fallback、embedding fallback、fine worker aggregate、merged-from archive 四类
各做至少一个临时去 hunk mutation，证明对应新用例在旧行为下转红；记录真实失败测试名，
临时变体不提交。

## 5. Patch 与文档卫生

- 重新生成零 context patch（例如 `git diff --unified=0`），避免 context 空行被写成
  `+ `；fetch 仍用既有 `--unidiff-zero`；
- 必须同时验证 clean checkout forward-check、当前 applied tree reverse-check、第二次
  apply 幂等；
- 首轮 note 顶部明确标记“首轮 READY 判词被架构师验收撤回，见 R1 note”；不得继续把
  五步 handler-only trace 称为完整 async trace；
- 首轮 `32 passed` 与真实 `37 passed` 的差异要说明，不悄悄改写历史；
- 新测试不得留下 `PytestUnraisableExceptionWarning`；正确初始化测试对象的析构依赖。

## 6. 自检与回报

只运行：

```bash
uv run pytest -q tests/test_memos_lifecycle.py tests/test_documentation_standards.py
git diff d1a0178..HEAD --check
git show --check --oneline HEAD
```

另做 patch forward/reverse/idempotence checks；不跑全量 pytest/compileall，不读 `.env`，
不调用真实服务。commit 前只显式 add 实际改动路径，过目 `git status --short`。

按 actor-handbook §4 回报，并额外逐字给出：

1. follow-up commit hash；
2. 三个自检尾行/exit；
3. full-chain trace 原文；
4. patch 新增触及的 upstream 函数；
5. 四类 mutation 的失败测试名；
6. 偏差/停工点、subagent、真实模型/入口；
7. 最终 `READY_FOR_MEMOS_ADAPTER(...)` 或 `BLOCKED(...)`。

到此停止，不开始 adapter。
