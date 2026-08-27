# LightMem × LoCoMo `(0.7,512)` 作者校准：取证与运行合同

日期：2026-08-27

状态：`PREDICTION_ACCEPTED_JUDGE_PENDING`

## 1. 复现目标与一手身份

目标是论文表 3 的 `LightMem(0.7,512)`：GPT-4o-mini，ACC 71.95%，且表注明 ACC 是
offline update 后的结果。current vendored official README 同样列出 71.95，并给出完整
LoCoMo 构建+回答 token 总量约 5,005.851k；judge usage 没有计入该 answer token 表。

- vendored/upstream commit：`b4ef1dd289880d4e7ecb88c503e2d51bb9ffdfaf`；
- paper PDF SHA-256：
  `7e9a8e9f39c616528d543ce8520606d47d56032eb004b55d452d0dce5725c23e`；
- dataset SHA-256：
  `79fa87e90f04081343b8c8debecb80a9a6842b76a7aa537dc9fdf651ea698ff4`；
- dataset：10 conversations / 1,986 raw QA；category 1–4=1,540，category 5=446。

## 2. current source 的内部冲突

`experiments/locomo/add_locomo.py` 当前常量写 `rate=.6`，但论文表与同 commit README 的
已报告行都是 `(0.7,512)`。这不是把 source 冲突“平均掉”的理由。本支线明确选择
**paper/README reported row** `.7/512`；current script 只提供其余 topology、输入与调用形状证据。
若将来复现 `.6` current-script 行，必须使用新 profile/run id，不能改写本支线。

## 3. 最终 effective contract

| 轴 | 作者一手行为 | framework author profile |
| --- | --- | --- |
| utterance | `user(real)+assistant("")` | 同；placeholder 仅满足产品 pair 结构 |
| role filter | `user_only` | `user_only` |
| caption | `text + " (image description: caption)"` | `author_harness_v1` 逐字渲染 |
| time | session time，`%Y-%m-%d %H:%M:%S` | 同；缺失 fail-fast |
| compression | pre-compress, rate=.7 | 同 |
| STM | paper row 512；current product 实际固定 512 | identity + product=512 |
| extraction | flat + topic segment + metadata + text summary | 同 |
| final flush | 全 conversation 最后一条 force | 同 |
| update | full-library offline update, threshold .9 | 同，QA 前完成 |
| retrieval | combined cosine top-60 | Qdrant product cosine top-60 |
| answer layout | 按 top-60 首次命中 speaker 顺序分两槽 | 同；0/1/2 speaker 强反例锁定 |
| answer call | one system message, temp=0 | 同；max_tokens/top_p 不发送 |
| judge | one user message, JSON object, temp=0 | 显式 `lightmem_locomo_paper` |
| scored QA | category 1–4 | canonical dataset 只公开 1–4 |

## 4. 不冒充的差异

1. 官方 search harness 先 `get_all(with_vectors=True)`，再在 Python/NumPy 手算 cosine；
   framework 为遵守“method 通用产品接口”使用同一 MiniLM 向量与 Qdrant cosine top-60。
   这是 product-equivalent retrieval，不是 byte-identical harness。运行后需抽查 score/order；
   tie 或 backend 排序差异必须披露。
2. 官方脚本配置 GPU；当前本机 author profile 使用 CPU。算法开关、模型 bytes、dimension 和
   distance 不变，但不能宣称 runtime 秒数与论文硬件直接可比。
3. workers=10 是用户选择的 isolation 并发；官方脚本示例默认 5。conversation 状态物理隔离，
   不改变单 conversation 算法；API rate limit 与本地内存压力只影响执行稳定性。
4. 本项目 vendored LightMem 含已审计的 benchmark 兼容/可观测 patch；source closure v2 与
   adapter v8 会进入 manifest，不能把结果冒充未修改 upstream 二进制。

## 5. 成本与停工门

授权边界是 10 个 conversation、1,540 answer、1,540 judge、workers=10，不自动扩样。
官方 README 给出 build+answer 约 5.006M tokens；judge 另计。Mimo 历史 token 只作拓扑参考，
不得用 scalar 换算 GPT usage。

遇到以下任一情况暂停新调用并保留已完成 isolation：

- APILIO provider/model/transport 与 tracked identity 不一致；
- 系统性 401/403/429/5xx、连续空 response 或 SDK usage 缺失；
- conversation 失败率不再是孤立重试可解释事件；
- 机器出现明显内存压力/swap 抖动或 worker 非预期退出；
- manifest、最终 answer messages、offline update 或 category 分母与本合同不符。

## 6. 运行命令身份

prediction：

```bash
uv run memory-benchmark predict formal \
  --root . \
  --method lightmem \
  --benchmark locomo \
  --profile author-locomo \
  --run-id lm-author-locomo-gpt4omini-r07-th512-postupdate-v1 \
  --workers 10 \
  --allow-api
```

作者 ACC judge：

```bash
uv run memory-benchmark evaluate \
  --root . \
  --run-id lm-author-locomo-gpt4omini-r07-th512-postupdate-v1 \
  --metric locomo-judge \
  --judge-profile lightmem_locomo_paper \
  --workers 10 \
  --allow-api
```

其余当前可重算指标另跑 `locomo-f1`、`f1`、`normalized-em`、`substring-em`、
`locomo-recall`。README 报告的 BLEU-1 当前尚未注册为框架 evaluator，因此本批不能把它
伪装成“已复现”；ACC 71.95 是本支线主对表指标。

## 7. 开跑前验收收据

- 真实 canonical 数据探针：10 conversations / 1,540 questions；category
  `1=282, 2=321, 3=96, 4=841`；
- first turn：`D1:1` → `user + blank assistant`，两侧时间均
  `2023-05-08 13:56:00`；首个图片 turn `conv-26/D1:5` 只出现一次作者
  `(image description: ...)` wrapper；
- runtime secret-free identity：`apilio/gpt-4o-mini/chat_completions`、W10；
- 极小真实 API transport probe：system-only answer `25 in / 3 out`，官方 JSON judge
  `388 in / 7 out`，均 `finish_reason=stop`，judge label 精确 `CORRECT`；
- 定向门：`591 passed`；历史 native/current author decode 解耦后：`163 passed`；
- current 全量门：
  `2383 passed, 3 deselected, 25 warnings, 29 subtests passed in 154.68s`；
- 追加 explicit author-judge/run-identity 双向配对强反例后：`157 passed`；
- `git diff --check` clean；本环境未安装 ruff，未把工具缺席伪装成通过。

## 8. Prediction 与 compact artifact 修复收据

正式 prediction 由 commit `21abf25` 启动并完成：

- 10/10 conversations、1,540/1,540 answers、0 failed；W10 墙钟 17m37s；
- 每题实际 `retrieved_items=60`。逐题 `retrieval_query_top_k=10` 是 benchmark query 的
  通用请求字段，author method config 的 product retrieve limit=60 已真实生效，不得误读为
  top-10；
- memory-build：420 calls，796,832 input + 207,778 output = 1,004,610 tokens；
- answer：1,540 calls，4,133,746 input + 10,057 output = 4,143,803 tokens；
- 两阶段合计 1,960 calls / 5,148,413 tokens，全部 `token_measurement_source=api_usage`；
- 15,188 次 embedding observation 仍按本地 tokenizer 估算，未混入上述 API token；
- 1,540 个公开 question、private label、prediction、answer artifact id 集合精确相同，空答案 0，
  公开 question 的 gold/private key 负空间通过。

开跑后机器门发现一个只影响 artifact resume/身份、未改变已生成 answer 的缺口：author builder
虽已注册，但 v2 serializer 删除了逐题 `prompt_messages`；旧 builder 又只透传 runtime 临时
messages，artifact-only resume 无法重建。修复没有退回逐题复制完整 prompt，而是：

1. adapter v9 给每个结构化 top-60 item 增加 `speaker_name` 与 `weekday`；timestamp、content、
   score、source ids 原字段不变；
2. author builder 由 ordered items 确定性重建首次命中 speaker 分组与 pretty-date memory；静态
   官方模板仍只由 run builder identity 保存一次；
3. 本次 v8 artifact 从 10 个已关闭的 Qdrant 库只读 4,970 points，给 1,540 行补齐两个字段；
   零 retrieve、零 embedding、零 API。迁移前后 SHA-256 分别为
   `9f8fb5f1fc821b57b801d6d1f5a29ede44a953d4d33d08833cf4c123a6a4e198` 与
   `e58c1f5859113e548a6b85b56badd4c3e3fc3f3fbf28732e06feedb8ea2c7b28`，大小从
   46,866,045 增至 50,844,933 bytes；其余 prediction artifact hash 全部守恒；
4. `ALL_AUTHOR_PROMPT_REBUILDS_MATCH rows=1540 conversations=10` 与最终
   `PREDICTION_AND_COMPACT_REBUILD_GATE_PASS` 均通过。run 内机器收据位于
   `summaries/author_prompt_artifact_repair.json`。

run 级 `prompt_track=unified` 在此只表示“registered deterministic builder path”；真正的 prompt
来源必须读 `answer_builder=lightmem_locomo_paper_native_v1`，不能再用旧二元字段推断
benchmark-vs-author。逐题 metadata 已同步该执行语义，作者来源仍由 builder/profile/official_source
三字段锁定。
