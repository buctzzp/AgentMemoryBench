# MemOS v2.0.25 product adapter M4 架构师最终验收

日期：2026-07-27  
架构师：GPT-5.6 sol

## 1. 最终接收范围

主线线性合入：

```text
dff8185  feat(memos): implement product v3 adapter m4
02ffc9d  fix(memos): close product adapter lifecycle gaps m4-r1
3e1d621  fix(memos): make scheduler stop failure permanently fail-closed
```

它们分别对应 actor 分支的 `a87353a`、`de29c4c`、`f6e725e`。接收内容包括：

- MemOS `v2.0.25@e820406` product typed-handler v3 adapter；
- `sentence_transformer` config 暴露与 search failure 可见性 patch；
- session 输入、五 benchmark payload、namespace、search/readout、manifest/resume；
- generic shared/isolated v3 provider cleanup；
- namespace-safe failed-ingest clean retry；
- runtime owner、环境作用域与 typed-handler 共享 dependencies；
- pending refusal 可重试与 scheduler stop failure 永久 fail-closed。

M4 不包含真实 Neo4j/Qdrant/API smoke，也不把 M5 pending 能力提前写成 valid。

## 2. 两次强验收纠偏

### 2.1 pending refusal 后孤儿 runtime

首轮 `a87353a` 在 `runtime.close()` 成功前就清空 provider/owner 引用并写
`_cleaned=True`。pending task 触发拒绝后，runtime 仍未关闭却无人持有，后续 cleanup
直接 no-op。M4-R1 改为“成功后提交状态”，并把 generic runner lifecycle guard 前移到
clean hook/preflight 之前。

### 2.2 stop failure 不能伪装成幂等成功

`de29c4c` 用 `_stop_attempted` 保证 stop 只调用一次，但允许第二次 cleanup 跳过 stop 后
标记 closed。架构师复核 upstream
`mem_scheduler/base_mixins/queue_ops.py` 后否决该取舍：

```text
stop_consumer() 先写 _running=False
→ dispatcher.shutdown()
→ dispatcher_monitor.stop()
```

后两步抛错时 scheduler 可能只关闭一部分，而下一次 upstream `stop()` 会因
`_running=False` 直接返回。因此最终状态机锁为：

```text
pending refusal
→ 不改变状态；task terminal 后可重试

stop success
→ closed；owner/provider 释放；重复 cleanup 幂等

stop failure
→ close_failed；closed=false；owner/provider 永久保留
→ 后续 close/cleanup 稳定 fail-fast，链回首次异常
→ owner.acquire 禁止复用，也禁止构造第二份 runtime
```

这不是普通 retryable error，而是当前进程内永久 poisoned runtime。当前 run 必须失败，
不得生成 completed summary。

## 3. 架构师独立验证

follow-up 分支定向门：

```text
380 passed, 10 warnings in 8.04s
compileall exit 0
```

生产 `MemosRuntime.close()` 独立探针：

```text
FIRST RuntimeError dispatcher shutdown exploded
RETRY_2 ConfigurationError RuntimeError
RETRY_3 ConfigurationError RuntimeError
FINAL {'closed': False, 'close_failed': True, 'stop_calls': 1, 'same_cause': True}
```

合流后主树全量无 API 门：

```text
1863 passed, 3 deselected, 11 warnings, 29 subtests passed in 156.95s
compileall exit 0
git diff --check exit 0
```

warning 画像：

- 1 条既有 vendored LightMem Pydantic deprecation；
- MemOS `datetime.utcnow()` deprecation；
- MemOS config Pydantic serialization warning。

无 `PytestUnraisableExceptionWarning`，无新增失败。

patch 门：

```text
git -C third_party/methods/MemOS apply --unidiff-zero --reverse --check \
  ../../../scripts/patches/memos-product-runtime-observability.patch
exit 0
```

证明 current nested MemOS 可由父仓单一 patch 反向还原；M4-R1 两个 follow-up 未改 patch。

## 4. Actor 评价与流程升级

Opus 5 的主体实现、证据披露和 follow-up 响应均属强交付。尤其是它主动把
`_stop_attempted` 的未裁取舍交回架构师，没有用绿测试掩盖不确定性；这不应简单记作
“actor 又犯错”。

返工次数暴露的是卡片设计缺口：首卡写了“pending 拒绝”“stop 恰好一次”“cleanup 幂等”，
却没有预先列全 `open / pending-refused / close-failed / closed` 四态及转移。以后凡后台
runtime/事务/队列卡，必须先写完整状态转移表，并把“幂等”限定为**已证实成功后的重复调用**；
partial failure 不能靠布尔 flag 猜成成功。

## 5. 最终判词与下一门

```text
ACCEPTED_MEMOS_M4(
  product typed-handler adapter is integrated;
  generic lifecycle ownership is exact;
  cleanup refusal is retryable;
  stop failure is permanently fail-closed;
  five benchmark offline contracts are covered;
  main no-API regression is green
)
```

下一步是 M5 B11 前置与真实服务 smoke。继续保持 pending：

- 真实 Neo4j/Qdrant 跨 namespace 隔离；
- MMR/rerank stable ranking；
- generated-memory semantic provenance 与 Recall/NDCG；
- HaluMem update/QA 的真实 current-state 行为；
- task-scoped fine output 缺失导致的 HaluMem extraction N/A；
- async worker 精确 per-call token/cost；
- image/vision 与 author LoCoMo 双 namespace variant。

未经用户确认服务环境、预算、规模与 run_id，不启动真实 DB/API smoke。
