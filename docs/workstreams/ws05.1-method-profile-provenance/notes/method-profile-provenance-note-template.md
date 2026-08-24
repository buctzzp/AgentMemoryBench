# Method profile provenance note 模板

> 每家 method 复制本模板形成 `notes/<method>-profile-provenance.md`。章节不可删除；无证据时填
> `PENDING`、`SOURCE_UNAVAILABLE` 或 `N/A`，不能留空或用推测补齐。

## 0. 身份与范围

- method：
- 审计日期：
- paper/technical-report identity：
- current product repo/commit/tag/license：
- official evaluation repo/commit：
- 本次不覆盖：

## 1. 算法机制先行

### 1.1 论文/技术报告阶段图

| 阶段 | 输入 | 状态/输出 | 是否可选 | 一手出处 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

### 1.2 current source 对应关系

| 论文阶段 | current module/function | 控制参数 | 版本漂移/缺失 | 判词 |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

没有正式论文时，列出官方 technical report、design doc、README architecture 与源码证据等级；禁止
直接从 constructor default 倒推算法。

## 2. 官方 benchmark 覆盖

| benchmark | 论文报告 | 公开 harness | dataset/version | topology | source status |
| --- | --- | --- | --- | --- | --- |
| LoCoMo |  |  |  |  |  |
| LongMemEval |  |  |  |  |  |
| HaluMem |  |  |  |  |  |
| BEAM |  |  |  |  |  |
| MemBench |  |  |  |  |  |

## 3. Prompt / judge 合同

每个有公开 harness 的 benchmark 独立填写：

- template path/commit：
- 全部变量及公开来源：
- 最终 `PromptMessage[]` role/顺序/内容：
- model/temperature/max_tokens/top_p/response-format/reasoning：
- parser/abstention/特殊路由：
- method harness judge 与 benchmark judge 的关系：
- final-message parity 测试：
- 裁决：`AUTHOR_READY` / `INCOMPLETE` / `SOURCE_UNAVAILABLE` / `IMPLEMENTATION_VARIANT`

## 4. 参数矩阵

| parameter path | upstream default | paper role | official effective values | current main | call site/最终 payload | 分类 | state/rebuild impact | 裁决 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |

至少覆盖所有 method-owned bool/enum 与高影响数值；runtime/credential/worker/crop 只需证明已被移出
method TOML。

## 5. 配置流与强反例

- TOML → typed config → factory/constructor → product object/payload：
- unknown/type validation：
- dead/overridden config 探针：
- 关键 bool/enum mutation：
- embedding/build identity 与 fresh-state 条件：

## 6. 主配置与作者配置裁决

- framework main 固定值及理由：
- `author_<benchmark>` 候选：
- product-default 补充身份：
- topology variant（不能只靠 TOML 表达）：
- 禁止进入配置的 upstream 内部常量：

## 7. Manifest / resume / artifact

- 必须进入 identity 的字段：
- 变更是否要求全量重建：
- 旧 artifact 回读政策：
- secret/private/gold 边界：

## 8. 未闭合项与停工点

| item | status | 已查范围 | 下一条一手证据 |
| --- | --- | --- | --- |
|  |  |  |  |

## 9. 验证记录

- 零 API 命令：
- 真实尾行：
- diff/source hash：
- 架构验收：
