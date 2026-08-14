# TOML profile 与新运行身份迁移 M1-B（2026-08-14）

## 0. 总判词

**新 run 已从 `unified/native` 双轨选择器迁到 method TOML profile；旧 artifact 保持严格
只读兼容，没有被改写或伪装。**

本批只改变控制面、manifest/resume 身份和新 run 分层路径，不改 method 算法、benchmark
数据、prompt 字节、metric 公式、API runtime 或旧 outputs。没有调用真实 API，也没有创建
`author_<benchmark>` 配置。

## 1. 为什么不能直接删 `config_track.py`

旧模块原来混合了三类责任：

1. 新 run 的 unified/native 行为选择；
2. build/embedding 的强类型事实；
3. 旧 `TrackIdentity v1` manifest 的 parser、evaluate 与 cost 回读。

第 1 类已经退出；第 2 类迁到中立的 `methods/run_identity.py`；第 3 类必须保留，因为历史
实验身份不能因源码重构消失。故本批的完成标准不是“仓库里再也搜不到 config_track”，而是
**新 prediction 不再 import 或调用它，旧 artifact 仍能原样校验与评估**。

## 2. 新 profile envelope

十家 method 的 `smoke` 与 `official_full` section 现在都显式包含：

```toml
answer_builder = "benchmark"
```

loader 分两层：

- `load_profile_section()` 只定位并校验 TOML table；
- `build_typed_profile()` 把登记过的 framework key 与 method 参数分开，未知的其他 key 仍
  fail-fast；
- `resolve_method_profile()` 是新 run 的组合根，必须同时得到公开 profile 名、实际 section、
  非空 builder identity 与强类型 method config。

旧的 `load_typed_profile()/load_method_profile()` 继续服务 config-only 消费者。它们可以忽略
已登记的 framework key，但不具备创建新运行的资格；这避免为了兼容读取把新运行的 builder
必填门放宽。

## 3. `MethodRunIdentity v1`

新 method manifest 使用独立字段：

```json
{
  "run_identity": {
    "contract_version": "v1",
    "profile": {"name": "official-full", "section": "official_full"},
    "answer_builder": "benchmark",
    "build": {
      "implementation_variant": "product",
      "embedding_profile": "...",
      "historical_controlled_build_equivalent_to_current_main": false,
      "embedding": {"provider": "...", "model": "...", "dimension": 384}
    }
  }
}
```

实际 embedding 对象还严格保存 revision/status、normalization、instruction、distance 与
identity status；上例只为阅读省略。profile、builder、build/embedding 任一变化或字段缺失，
resume 都双向拒绝。新 `run_identity` 不能与旧 `config_track`、`contract_version`、
`track_identity` 混写。

## 4. CLI、builder 与输出路径

- `predict smoke` 固定选择 `smoke`，拒绝额外 `--profile`；
- `predict formal` 默认 `official-full`，允许显式选择 registry 已登记的稀疏作者 profile；
- 任何非 smoke profile 都要经过 `--confirm-full`；
- `--config-track native` 在 runtime、dataset、output 前 fail-fast；显式 unified 仅发弃用警告；
- 旧 `predict --profile ...` 仍能归一化，但发弃用警告；
- 新分层路径为 `.../{smoke|formal}/{profile}/{run_id}`，不查找、移动或 resume 旧
  `.../{mode}/{unified|native}/{run_id}`；
- 当前只注册 `answer_builder="benchmark"`，解析为 benchmark registry 的完整统一 builder。
  `prompts/author/` 中已有素材不等于作者 profile 已闭合；未注册名字在 API/runtime 前失败。

所有 adapter 中过去硬编码的 `answer_builder` manifest 字段已经删除，builder 身份只由 TOML
profile envelope 声明一次。

## 5. 历史兼容边界

| 资产 | 新 run | 旧 artifact |
| --- | --- | --- |
| TOML profile + `MethodRunIdentity v1` | 唯一主路径 | 不回填 |
| `config_track=unified/native` | native 拒绝；unified deprecated no-op | 原样解析 |
| `TrackIdentity v1` / native bundle | 不生成 | evaluate/cost 严格回读 |
| track 分层输出目录 | 不写、不探测 | 原目录保留 |
| 旧 manifest 缺新 identity | 不允许 resume 新 run | 按旧 schema 评估 |

成本报告对新 artifact 明示 `config_track="profile"`，并新增 `profile_name` 与
`answer_builder`；旧报告仍返回旧 track，无法读取或损坏的文件保持 `unknown`。

## 6. Prompt shim 退出

仓库内部测试和代码已全部改为直接 import `prompts/author/` canonical owner；以下三个仅有
re-export 的内部 shim 已删除：

- `methods/lightmem_native_prompts.py`
- `methods/mem0_native_prompts.py`
- `methods/memoryos_native_prompts.py`

architecture test 同时锁住“文件不得恢复”和“内部不得再 import”。benchmark/evaluator 下的
其他 shim 有不同消费者与退出门，本批没有捆绑删除。

## 7. 强反例与验收

本批测试覆盖：framework key 与 method config 严格分层、缺/空/未知 builder、公开名与 section
映射、运行身份严格 round-trip、非法 token/枚举/维度、profile/builder/embedding resume
mismatch、旧 identity 回读、新旧字段混写、CLI formal/smoke/native/unified 行为、成本报告、
新 profile 路径、registered/operation/isolated prediction 与 canonical prompt import。

验收结果：

- 承重定向集：`569 passed, 12 warnings in 10.47s`；
- 文档门单跑：`6 passed in 1.17s`；
- `uv run python -m compileall -q src/memory_benchmark tests`：exit 0；
- `git diff --check`：exit 0；
- 无 API 全量：`2204 passed, 3 deselected, 25 warnings, 29 subtests passed in 150.99s`。

新增 12 条 warning 是专门覆盖 legacy CLI 的测试触发本批新增 `FutureWarning`；其余为既有
LightMem/MemOS 第三方 deprecation/serialization warning。动态 commit hash 仍以 Git log 为准，
不在施工 note 预写。

## 8. 明确未做与下一批

- 不修改 `official_full` 效果参数；
- 不发明任何作者没跑过的 section，不把 prompt 文件存在误当完整 builder 已注册；
- 不删除 `config_track.py`、旧 parser、evaluation 路由或成本回读；
- 不改 metric、method、benchmark、third-party、outputs 或 API；
- 不提前拆 `prediction.py`。

M1-B 关闭后，下一批严格为 M1-C：只抽 EverOS/Graphiti/LangMem/Letta 已重复且语义相同的
主进程 JSON-lines transport，保留各产品 worker、环境、DB、namespace 和 cleanup 差异。
