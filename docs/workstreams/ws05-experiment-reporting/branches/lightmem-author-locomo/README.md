# LightMem × LoCoMo GPT-4o-mini 作者复现支线

状态：`in-progress`

父任务：[ws05 experiment reporting](../../README.md)

## 目标

用当前框架独立复现 LightMem 论文表 3 的 `LightMem(0.7,512)`、LoCoMo、GPT-4o-mini、
**post offline update** 结果。该支线只验证作者校准身份，不替代 Phase 1 主表的
`hybrid + online_soft + benchmark builder` 配置。

## 锁定范围

- dataset：项目 source-lock 下的 `data/locomo/locomo10.json`，10 个 conversation；
  canonical adapter 按既有政策排除 category 5，最终 1,540 个 category 1–4 QA；
- method：LightMem flat extraction，`pre_compress=true`、`r=.7`、STM=512、
  `messages_use=user_only`、combined cosine top-60；
- input：每条 LoCoMo utterance 映射成真实 user + 空 assistant；caption 使用作者
  `(image description: ...)`，session 时间转 `%Y-%m-%d %H:%M:%S`；
- lifecycle：最后一条 utterance force segment/extract，随后
  `construct_update_queue_all_entries()` + `offline_update_all_entries(.9)`；
- answer：LightMem `experiments/locomo/prompts.py::ANSWER_PROMPT`，单条 system message，
  `temperature=0`，不额外发送 max_tokens/top_p；
- judge：显式 evaluator profile `lightmem_locomo_paper`，逐字使用
  `experiments/locomo/llm_judge.py::ACCURACY_PROMPT`，JSON object、temperature 0，
  metric tier=`author_calibration`；answer builder 不会暗中切换 judge；
- runtime：`.env` APILIO 槽的 `gpt-4o-mini`，Chat Completions；workers=10；
- run id：`lm-author-locomo-gpt4omini-r07-th512-postupdate-v1`。

## 当前进度

- [x] 论文 PDF、当前官方 README、add/search/judge 源码交叉取证；
- [x] 解释 current script `.6` 与论文/README 已报告 `.7` 的冲突，并锁定目标 row；
- [x] 建立独立 `author-locomo` method/runtime/execution profile；
- [x] 闭合 author 图片、时间、role、末批 force、offline update、answer builder 与 judge profile；
- [x] 完成 current 全量零 API 回归；待提交源代码身份；
- [ ] 执行全量 prediction（10 conversation / 1,540 QA / W10）；
- [ ] 执行官方 author judge 与全部现有 LoCoMo 离线/补充指标；
- [ ] 验收 SDK usage、失败账、分母、prompt/judge identity 与论文数字差异。

## 当前断点

用户已于 2026-08-27 明确授权本支线的全量 prediction + evaluation。只要零 API
回归与 APILIO runtime identity 门通过，架构师直接启动，不扩到其他 method/benchmark。
current 全量门：`2383 passed, 3 deselected, 25 warnings, 29 subtests passed`；历史
native bundle 与 current author decode 已解耦，追加 judge identity 强反例后定向门
`157 passed`。
完整证据、可比性边界与运行收据见
[preflight and run contract](notes/preflight-and-run-contract.md)。
