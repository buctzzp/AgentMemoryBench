# MemOS v2.0.25 async lifecycle R2 架构师强验收

日期：2026-07-26

被验 commit：`d1a0178`

actor worktree：`/Users/wz/Desktop/mb-actor-memos-r2`

source lock：`MemOS v2.0.25@e820406269537b97d270687e3e40eea2f015f81a`

## 0. 判词

```text
REWORK_REQUIRED(
  reader-internal failures are still swallowed;
  merged-from archive failure still completes;
  full async trace is not full;
  commit fails whitespace gate
)
```

`d1a0178` 暂不 cherry-pick，首轮 implementation note 的
`READY_FOR_MEMOS_ADAPTER` 判词撤回。当前唯一入口是
[`R2-R1 返工卡`](../cards/actor-prompt-memos-v2-0-25-async-lifecycle-r2-r1.md)。

这次不是简单把责任推给 actor：首轮 R2 卡把 nested patch 允许清单限定在 handler/DB，
却同时要求“fine-transfer LLM failure 必须 failed”；current active reader 在更内层先吞掉
LLM/parser/embedding 异常。**卡的允许清单本身定窄了**，R2-R1 已显式扩到
`multi_modal_struct.py`。

## 1. 结构与可复现性

### 1.1 范围

首轮 commit 实际 6 个文件、`+1877/-1`，与首轮卡父仓允许清单一致；actor worktree 只有
未暂存的 local-only `third_party/methods/MemOS` 软链。

### 1.2 Patch identity

当前 nested tree 对 patch 的 reverse-check 通过：

```text
git -C third_party/methods/MemOS apply --unidiff-zero --reverse --check \
  /Users/wz/Desktop/mb-actor-memos-r2/scripts/patches/memos-product-runtime-observability.patch

exit 0
```

所以 nested dirty 可解释，patch bytes 与已应用的五文件改动一致。

### 1.3 Commit whitespace 门失败

actor 报告的 `git diff --check → exit 0` 是 commit 后对空 working diff 的检查，不能证明
提交本体。架构师改查 commit：

```text
git show --check --oneline d1a0178

exit 2
```

`scripts/patches/memos-product-runtime-observability.patch` 有 23 个 context 空行被写成
`+ `，均为 trailing whitespace。R1 必须用 zero-context patch 重生，并检查
`git show --check HEAD`，不能再用 commit 后的空 `git diff --check` 代替。

## 2. 定向测试复跑

```text
uv run pytest -q tests/test_memos_lifecycle.py tests/test_documentation_standards.py

37 passed, 4 warnings in 6.70s
```

首轮 note 仍写“32 passed”，与真实收尾数不一致。四个 warning 中两个是测试用
`MemoryManager.__new__` 后未补齐析构依赖产生的
`PytestUnraisableExceptionWarning`，并非 upstream 稳定 warning；R1 应修正测试对象，
不能把自己的析构错误长期留在门内。

## 3. “完整共享 trace”并不完整

首轮用例 `test_async_mem_read_happy_path_shared_trace` 的实际断言只有：

```text
text_mem.get:raw-1
mem_reader.fine_transfer_simple_mem
text_mem.add:n=1
text_mem.delete:['raw-1']
memory_manager.remove_and_refresh_memory
```

它从 raw 已经存在后的 handler 才开始，缺少：

- typed `AddHandler` / `SingleCubeView.add_memories`；
- fast reader 与 initial fast write；
- `_schedule_memory_tasks`；
- `BaseSchedulerQueueMixin.submit_messages` 与 local queue；
- dispatcher wrapper 的 started/completed；
- framework waiter 返回。

此外 `text_mem.add/delete` 与 `memory_manager.remove_and_refresh_memory` 均由测试类覆写，
没有在同一 trace 里经过 patched `TreeTextMemory` / `MemoryManager` 实现。单独的 catch
边界测试有价值，但不能据此把 handler-only trace 升级为完整 product-chain trace。

## 4. Reader 内部仍把真实失败改写成成功

### 4.1 LLM 异常被伪造成 UserMemory

current `MultiModalStructMemReader._get_llm_response()`：

```python
try:
    response_text = self.llm.generate(messages)
    response_json = parse_json_result(response_text)
except Exception:
    response_json = {
        "memory list": [{
            "memory_type": "UserMemory",
            "value": mem_str,
            ...
        }],
        "summary": mem_str,
    }
```

因此首轮测试让 fake `fine_transfer_simple_mem()` 直接 raise，只证明**高层 fake**能穿过
handler；真实 LLM failure 在到达 handler 前就已被 reader 改写成成功结果。它没有关闭卡内
“fine-transfer LLM failure”这一承重门。

### 4.2 Embedding 全失败仍正常返回

架构师直接调用 current production `_embed_memory_items()`，让 batch 与逐项 embedder
都抛 `PROBE_EMBED_FAILURE`，输出：

```text
[MultiModalStruct] Error batch computing embeddings: PROBE_EMBED_FAILURE
[EMBED_FALLBACK] batch_size=1
[MultiModalStruct] Error computing embedding for item: PROBE_EMBED_FAILURE
{'returned_normally': True, 'embedding': None}
```

后续 `Neo4jCommunityGraphDB.add_nodes_batch()` 对 `embedding is None` 标
`vector_sync="skipped"`，仍可继续写 graph。结果是 memory 对 fast vector search
不可见，但 add/MEM_READ 仍可能 completed。

批量 embedding 失败后逐项 fallback 是合理容错；**所有逐项 fallback 成功**可以继续，
但任一逐项仍失败必须在全部 fallback settle 后 aggregate raise。

### 4.3 其他 active chat catch

current active chain 还有三层 partial-success catch：

- `_read_memory()` 吞 scene future exception；
- `_process_multi_modal_data()` 吞逐 message parser future exception；
- `_process_transfer_multi_modal_data()` 吞 fine worker exception。

这些 catch 会把“部分输入处理失败”降成较短列表或空列表。合法零抽取只指成功的 LLM
响应明确返回空 memory list，不包括 transport/parser/embedding/worker 异常。

## 5. `merged_from` archive 失败仍 completed

架构师从 production `MemReadMessageHandler` 的最低 graph leaf 注入
`graph_db.update_node()` 失败。真实输出：

```text
[Scheduler] Failed to archive merged_from memory old-1: PROBE_ARCHIVE_FAILURE
{
  'returned_normally': True,
  'trace': [
    'text_mem.get:raw-1',
    'mem_reader.fine_transfer_simple_mem',
    'text_mem.add:n=1',
    'graph.update_node:failed',
    "text_mem.delete:['raw-1']",
    'memory_manager.remove_and_refresh_memory'
  ]
}
```

即新 fine memory 已写入、旧 merged memory 未 archive、raw 被删除、refresh 完成，handler
仍正常返回；dispatcher 会把 task 标 completed。它属于真实 graph write failure，必须在
尝试完本 batch 所有 old ids 后 aggregate raise。

## 6. Tracker anti-corruption 反例

首轮 tracker 对 callback 过度宽容。架构师探针：

```text
failed_then_completed {
  'status': 'completed',
  'failed_at': '...',
  'error': 'boom',
  'completed_at': '...'
}

B1 {
  'status': 'in_progress',
  'item_statuses': ['waiting']
}
B2 {
  'status': 'in_progress',
  'item_statuses': ['waiting']
}
```

第一例说明 late `completed` 可覆盖 `failed`；第二例说明同一 internal item id 被改绑到新
business task 后，旧/new 两个 business index 同时指向已被覆写的同一 waiting record。
current 正常路径会生成 UUID item id，但严格完成门不应在 replay/重复 callback 时把失败变
成功。R1 锁定 terminal 单调性、同身份幂等与跨 business rebind fail-fast。

## 7. 保留的正面结论

首轮并非无效：

- patch 与当前 nested bytes 的 reverse identity 成立；
- handler、TreeTextMemory、MemoryManager、Neo4jCommunity 与 submit 的多个
  log-and-continue catch 已被真实函数测试覆盖；
- local tracker 的 namespace/business/label、timeout、数量、shutdown 基础设计方向正确；
- `BaseSchedulerHandler.process_grouped_messages` 的额外吞错发现准确，MEM_READ 局部覆写比
  扩改所有 handler 更克制；
- HaluMem fine-output 仍应保持
  `pending(adapter 需纯观测 sidecar)`，本次反证不改变这一裁决。

问题在于判词超出了证据能承载的范围，不能直接进入 adapter。
