# ws04 施工计划

## M1-A：isolated heartbeat

- [x] 定义不可变 worker heartbeat 实体与公开字段强校验。
- [x] worker 在 conversation/ingest/question/terminal 边界发事件。
- [x] coordinator 用进程内 queue 消费事件，独占更新 Rich 与 `progress.json`。
- [x] 阻塞期间只刷新存活时间，不伪造完成计数。
- [x] 用受控 fake worker 锁定交错、失败、取消与隐私负空间。

## M1-B：第三方输出

- [x] 复验现有 `method.log` handler 在 isolated factory 重配 root logger 后是否仍存活。
- [x] in-process adapter 的 suppressed stdout 从“丢弃”改为“脱敏后落盘”，保持原显示开关。
- [x] 共用 worker transport 把脱敏 stderr 全量落盘；tail 继续仅服务失败摘要。
- [x] 锁定 stdout JSON-lines 不受污染、跨 run 不串写、secret/private 负空间。

## M1-C：收口

- [x] 复验 elapsed、双 worker 交错和 progress disabled 文件快照。
- [x] 文档标准、compileall、无 API 全量回归。
- [x] 更新 README/roadmap，写一份自包含实现 note，达到停手线后关闭 ws04。

## 串行约束

M1-A 先于 M1-B；M1-B 不能借 heartbeat queue 偷运第三方任意文本。真实 API smoke 不是
本 workstream 的代码完成门，若未来需要视觉验货，必须另行取得用户对 run_id/预算的授权。
