# BEAM canonical identity 与紧凑 artifact 投影 R1

日期：2026-08-26

## 1. 断点

第二批 BEAM resume 在 API 前被拒：

```text
Error: Resume manifest mismatch: dataset, method or run policy changed
```

逐字段比较证明唯一差异是 `dataset_sha256`：首批 manifest 为
`2a752f9a...00a7`，current adapter 为 `ad1c2587...cc66`。原始 BEAM source fingerprint、
method identity、run policy 与 cohort 均未变化。

根因是首批之后的 artifact slimming 把 BEAM 大块私有 metadata 直接从 canonical
`GoldAnswerInfo` 删除。虽然这些字段不进入 scorer，修改 canonical Dataset 仍正确触发 dataset
identity 门；“artifact 需要变小”不应通过改写 adapter 事实层实现。

## 2. 修复

- canonical BEAM gold 恢复 source-locked `q_obj`、row 私有上下文与 evidence mapping；
- 使用无新增 dataclass 字段的 `BeamGoldAnswerInfo` 子类提供
  `evaluator_artifact_metadata()`；`asdict()` 内容与历史 `GoldAnswerInfo` 相同，因此 canonical
  dataset identity 不因落盘策略改变；
- 通用 `evaluator_private_label_record()` 仅在 gold 显式提供 projector 时消费紧凑 metadata，
  其他四家与旧对象保持原样；projector 非 dict fail-fast。

这不是放宽 resume 比较，也没有白名单某个 SHA。正确层次是：adapter 保留完整事实，artifact
serializer 负责稳定投影。

## 3. 一手守恒

在当前绝对 project root 与 full 100K 数据上重算：

```text
dataset_sha256 = 2a752f9af0541daaecab4970ae91ca0f20a95048da699524ba7a33860fc900a7
```

逐字命中首批 manifest。对锁定的五个 BEAM cohort isolation 重新生成输入 artifact：

```text
public_equal True 100
private_equal True 100
```

即 canonical 事实恢复后，method 公开输入与当前紧凑 evaluator label 都没有发生字节漂移。
第一次失败发生在 manifest preflight，零 API、零半写；修复后同一 resume 命令通过身份门并只选择
新增 isolation `1` 与 `20`。

定向零 API 门：

```text
209 passed, 4 subtests passed in 21.01s
```

与增量 evaluator 修复合并后的 current 全量零 API 门为：

```text
2364 passed, 3 deselected, 25 warnings, 29 subtests passed in 256.57s
```

## 4. 长期规则

未来压缩 answer/private/debug artifact 时，先确认字段属于 canonical fact、method-visible input、
evaluator semantic input 还是重复 provenance。只允许在 serializer 投影层删重复字段；若必须改变
canonical Dataset，则旧 run 按新 identity 不 resume。不得因为“method 看不到 gold”就绕过完整
dataset identity 门。
