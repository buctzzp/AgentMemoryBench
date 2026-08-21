# ws04 终端观测契约

## 1. 问题边界

ws04 只改善人和机器观察运行状态的能力，不改变实验 estimand：同一输入、method 配置、
provider 调用和 answer/judge 调用必须保持不变。观测失败可以使运行 fail-fast，但不得吞掉
原始业务失败，也不得把未完成工作显示成 completed。

## 2. isolated heartbeat

worker 线程只向 coordinator 发送公开、小对象事件；coordinator 是 Rich、`progress.json`
和 heartbeat event 的唯一写者。每个事件至少包含：worker index、conversation id、阶段、
turn 总数/已完成数、question 总数/已完成数和当前 question id。gold、answer、prompt、secret、
method payload 与 traceback 不得进入 heartbeat。

阶段集合第一版固定为 `starting / ingesting / answering / completed / failed / cancelled`。
阻塞在一个 method 调用期间，coordinator 可刷新该阶段的存活时间，但不能虚增 turn/question
完成数。终端只显示最近活跃 worker 摘要，不创建 N 条永久进度条。

## 3. 第三方输出

输出按运行边界分类：

1. Python `logging`：现有 run-scoped handler 追加写 `logs/method.log`。
2. in-process `print/tqdm`：只能在 adapter 已拥有的窄调用边界捕获；禁止在并行 run 外层
   全局重定向 `sys.stdout/stderr`。
3. JSON-lines subprocess：stdout 永远只承载协议；普通第三方输出走 stderr，经 secret
   redactor 后持续落盘，有限 tail 只用于异常摘要。
4. warning：保留 WARNING 及以上；只过滤已有明确低价值名单的 INFO。

默认终端保持整洁，完整诊断落盘；显式显示开关只能镜像已脱敏文本，不能改变是否落盘。

## 4. 非目标与停手线

- 不把 heartbeat 扩成分布式 tracing 系统。
- 不为每个 method 新建专用进度协议。
- 不把性能/成本 observation 混入 heartbeat。
- 不因文件较大重拆 runner；ws03 的责任边界保持不动。
- heartbeat、输出落盘、cosmetic 回归三门关闭后停止，不继续追求终端动画效果。
