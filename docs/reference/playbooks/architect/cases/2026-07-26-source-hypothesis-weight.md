---
id: architect-case-source-hypothesis-weight
date: 2026-07-26
triggers: [source lock, third-party upgrade, actor card, active call graph]
supersedes: []
---

# 刚换锁版本的假设不得冒充承重事实

## 1. 观察到了什么

MemOS 从旧快照换锁到 `v2.0.25` 后，架构师虽读过部分 current source，却把三条尚未完成
active-call-graph 证明的判断写进 actor 卡“承重事实”：默认 reader 继续走父类窗口、
显式 `chat_time=None` 会被 wall clock 覆盖、active reader 会丢 `message_id`。actor 亲核后
证明三条均不成立，并按停工协议在 `13edb3a` 停工。

## 2. 原裁决为何不够

“源码中存在某函数/字段”不等于 default product 可达。继承关系也不等于子类没有覆写。
风险索引如果被写成锁死起点，actor 只能停工，造成一次不必要的回卡；若 actor 没停，错误
假设还会进入 adapter 和 metric 资格。

## 3. 新裁决及边界

第三方刚换锁时，卡内事实分两类：

- **锁定事实**：架构师已亲核 current default 构造、动态 dispatch 或完整静态 call graph；
- **待证假设**：从旧版、父类、字段存在性或局部 grep 推出的风险。

待证假设可以成为任务目标和停工触发器，但不得用“actor 不得推翻”的口吻写进承重事实。
只有 source identity、默认构造和 active dispatch 三者闭合后，才能锁成后续实现前提。

## 4. 一手证据

- stop note：
  `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-product-runtime-preflight.md`
- 架构改判：
  `docs/workstreams/ws02.7-method-track/branches/method-recertification/memos/notes/
  memos-v2.0.25-m1-r1-ruling.md`
- actor commit：`13edb3a`

## 5. 何时重读

source lock 升级、vendored method 大版本切换、父类/子类 dispatch、官方 harness 与 current
product 分叉、准备把局部源码判断写进 actor 卡“锁定事实”时。

## 6. 退出或 supersede 条件

若项目以后引入自动生成并验证 default product call graph 的 source-lock 工具，使卡内
承重事实均由机器证据生成，可由新的机制卡 supersede 本经验。
