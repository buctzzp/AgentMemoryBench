# Runtime 配置与模型观测规格

## 1. 配置所有权

一次 run 的配置由四个正交但显式组合的所有者构成：

| 所有者 | 负责 | 不负责 |
| --- | --- | --- |
| method | 作者公开的算法旋钮、产品 implementation 选择 | key/base URL、通用 timeout/retry、runner workers、数据裁剪 |
| API runtime | provider、model、transport、credential env、timeout/retry、provider request override | method 内部算法阈值、benchmark prompt |
| benchmark evaluation | answer/judge builder、decode、parse、metric policy | method build 参数、存储生命周期 |
| execution | workers、裁剪、队列/资源配额、日志与输出位置 | 修改 method 算法或模型身份 |

判断一个字段是否属于 method TOML，必须同时回答：

1. upstream 是否通过公开 constructor/config/CLI 暴露；
2. 改变它是否会改变 method 的算法行为或产品 surface；
3. 它是否只因本框架调用 API、调度进程或做 smoke 裁剪才存在。

前两项成立且第三项不成立，才属于 method。作者写死且未提供支持 seam 的内部常量不因“方便
调参”而强行暴露；通用网络参数也不因十个 adapter 都要用而复制十份。

## 2. 主配置与作者校准

- 新主 run 不再把 `smoke`/`official_full` 当作两套 method 算法参数；两者首先是 API runtime
  与 execution scope。
- method 主参数只有一份。确有一手官方 benchmark 配置时，才允许稀疏
  `author_<benchmark>` 算法覆盖；选择必须显式进入 run identity。
- 迁移必须先支持旧 section 的严格只读解析；不得改写旧 artifact，也不得让旧 run resume 到
  新配置。

## 3. Controlled embedding 主比较

主比较使用 `all-MiniLM-L6-v2`、384 维，但只适用于产品路径**实际消费 embedding**且能通过
公开配置无损替换的 method。身份至少包含：provider、model/path、revision 或 unpinned 状态、
dimension、normalization、instruction、distance 与 tokenizer。任何一项变化都要求重建并造成
resume mismatch。

这不是“十家都必须填同一个字符串”：

- 产品不消费 embedding 时记 `N/A`；
- 需要专用多模态/图向量且不能等价替换时记 `unsupported/pending`；
- 作者/product-default 配置保留为补充校准，不与 controlled 主比较混名；
- performance 层不得为了共享模型暗中改 method 身份。

## 4. 模型调用与效率账

任何算法运行期间发生的 LLM、embedding 或 model-based reranker 调用，都必须拥有：stage、scope、
model identity、latency、token measurement source 和成功/失败状态。API 返回 usage 时以 usage 为准；
缺失时只能用带 tokenizer 身份的估算并显式标注。失败请求已经产生的真实花费进入 append-only
attempt ledger，不能因算法状态回滚而一并消失。

`formatted_memory` 注入 answer 的 token 数与 retrieval 阶段内部模型调用是两件独立 observation，
不得互相代替。

## 5. HaluMem session extraction 资格

`SessionMemoryReport` 必须是当前 session 导致创建或变化的**产品记忆单元**。以下均不合格：

- 原始输入回显；
- top-k query retrieval；
- 整库累计快照；
- framework 根据 lineage 自行改写出的“好看摘要”。

可接受的证据只有产品事务直接返回 changed units，或在完成门之后对具备稳定 ID 的完整产品
记忆做 before/after delta。若 API 不完整、ID 不稳定或后台任务未终态，则保持 N/A。

## 6. 资源共享与隔离

优先共享 immutable、同 identity、并发安全的 tokenizer/embedder、连接池和只读 dataset storage；
method memory、事务、scheduler、mutable store 与 private labels 保持 run-local。逻辑 namespace、
进程隔离和依赖共享是三条不同轴。先记录 RSS/PSS、模型副本、decode 次数、队列与吞吐，再决定
是否引入服务化或同进程复用。
