# LightMem × LoCoMo GPT-4o-mini 作者复现支线

状态：`done`

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
- [x] 完成 current 全量零 API 回归并锁定源代码身份 `21abf25`；
- [x] 执行全量 prediction（10 conversation / 1,540 QA / W10，0 failed）；
- [x] 验收并修复 author compact artifact 的确定性重建字段，1,540 题零 API parity；
- [x] 执行官方 author judge 与全部现有 LoCoMo 离线/补充指标；
- [x] 验收 SDK usage、失败账、分母、prompt/judge identity 与论文数字差异。

## 当前断点

支线已关闭。prediction：10/10 conversations、1,540/1,540 answers、0 failed、W10 墙钟
17m37s；420 次 memory-build + 1,540 次 answer 全部是 SDK `api_usage`，合计
5,148,413 tokens。official strict judge：`1114/1540 = 72.3377%`，比论文 71.95%
高 6 题/0.3896 个百分点；1,540 次 judge 另计 631,065 SDK tokens。artifact repair 没有
重跑 retrieve/API，1,540/1,540 system prompt 可从 compact artifact 独立重建。

离线补充指标：LoCoMo F1=`0.506778`、通用 F1=`0.495327`、normalized EM=`0.221429`、
substring EM=`0.331818`；post-update semantic lineage 不可证明，LoCoMo Recall 诚实为 N/A。
BLEU-1 尚未注册，未伪装成已复现。current repair 后全量零 API门为
`2387 passed, 3 deselected, 25 warnings, 29 subtests passed in 158.69s`。
完整证据、可比性边界与运行收据见
[preflight and run contract](notes/preflight-and-run-contract.md)。
