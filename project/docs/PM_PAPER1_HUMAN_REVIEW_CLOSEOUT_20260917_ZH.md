# Paper-1 人评收口与后续推进（2026-09-17）

本轮接受研究者的事实核查反馈，不再新增人评卷或要求重做 96 题。原始 A、AI B 和六题复核保留原文件；后续说明写入独立记录。

同日后续进展：live runner、模拟传输测试、模型元数据和 96 条官方 token 计数均已完成；研究者随后批准 `$0.10`，资格测试也已执行并收口。最新状态见[Gemini 资格测试结果](PM_PAPER1_GEMINI_QUALIFICATION_RESULTS_20260917_ZH.md)。本记录下方保留初始收口时的估算、待办及流程提案，不能作为当前未执行状态。

## A3 的澄清与六题处理

研究者说的“B”指 **AI 评审 B**，不是题中的候选回答 B。最新消息是接受关于狗这一细节的分析，不能记录成用户直接填写了 `B_better`。

| 题目 | 本轮收口 |
|---|---|
| A3 | 英文历史只明确宠物、责任和工时；候选 A 的狗及费用担忧缺乏对应依据。保留初评、复核和最新澄清。助手后续分析认为另一候选更忠实，单列为分析方向。 |
| A11 | A 已将分手写成同居和关系加强；补充这一事实反转，保留六题复核的 `uncertain`。 |
| A27 | 保留六题复核的 `B_better`：California 与参考一致。 |
| A64 | 保留六题复核的 `equivalent`：两段回复逐字相同，即使同样差也相当。 |
| A81 | 接受 B 自行生成的 HR 日期不能作为证据；保留提交记录，助手敏感性分析按 `uncertain` 处理其不可靠胜出方向。 |
| A95 | 保留 `equivalent`；没有题中已知的风格偏好，不强行分胜负。 |

机器记录：`project/data/paper1_authority/paper1_human_review_closeout_20260917_v1.json`。其中助手补充方向明确标记，不作为新的人评、独立金标准或 PM 训练标签。

## 已落地

1. 新增 `63_prepare_teacher_review_closeout.py`：校验原始三份提交的 hash、canonical 空白卷、A/B 内容和方向、96 个 presentation ID，以及全部 Gemini 请求与原始英文题面的逐项一致性。
2. 新增离线裁判对照模块：原始 A、六题人工复核、助手事实核查敏感性分析分别统计；80 个 base 为主描述分母，16 个 reversal 单列。未返回的 Gemini 判定记为缺失，不伪造 `uncertain` 或零分。
3. 修复 `code_summary_effect` 与已有 V2 合同不一致的分支：明确的合格 pairwise-equivalent 在 Event-F1 持平且 LLM Score 不持平、或二者方向相反时仍保留 equivalent。原始指标差、机械 invalid 和参考事件数量不一致检查继续保留。
4. 新增回归测试先复现 4 个失败组合，再验证修复。针对性测试 51 项通过；完整 public-only Paper-1 非 GPU 测试、集成检查与编译检查全部通过。正式 outcome、PM training 和本轮新增 API 费用均为 0。

## 对照结果如何使用

| 对照视图 | 与探索性 AI B 同判 / 80 base | 原始方向翻转复现 / 16 |
|---|---:|---:|
| 原始 A | 27 / 80 | 15 / 16 |
| 覆盖六题人工复核 | 28 / 80 | 15 / 16 |
| 助手事实核查敏感性分析 | 29 / 80 | 14 / 16 |

这些是描述性人机对照，不是独立金标准准确率。复核发生在问题分析之后；只改变已讨论的 presentation，不联动改写另一侧重复题来提高一致率。不能依据 27→29 宣称裁判被校准好了。Gemini 尚无返回结果，其对照分数保持缺失。

## 下一步已经具体化

既有 96 条 Gemini 请求全部通过离线核验，仍使用冻结的 `gemini-2.5-flash-lite` 和 V2 英文 rubric，包含 ESC 32、QA 16、Summary 16、DG 32。人工答案、AI B 理由和本次事实核查未加入请求。不能再用这些已见答案修改 prompt 并报告同卷提升。

按当前官方 Standard 文本价，输入每百万 token $0.10，输出 $0.40；原有 o200k 代理计数估算一轮为 **$0.0636498**，阶段上限 **$0.10**。代理估算不含重试，不是 provider 最坏费用保证。执行前仍需模型元数据、provider countTokens、逐次预留、可恢复 live runner 及模拟传输测试。来源：[Google 官方价格](https://ai.google.dev/gemini-api/docs/pricing#gemini-2.5-flash-lite)、[countTokens API](https://ai.google.dev/api/tokens)，2026-09-17 核查。

实际累计账本核验为 **$1.44178151**，余额 **$48.55821849**。本轮无计费模型调用。

后续顺序：补齐裁判执行入口 → 在现有 $0.10 阶段上限内完成单独授权的 Gemini 资格测试 → 按任务报告测量可靠性和失败类型 → 在对应校准授权下执行真正的 RS/MP/ME/MS amount/top-k calibration → 冻结各 head 的 `k*`、容量和全栈身份 → 正式 effect labels 与四头 PM 训练。

生成器方面已有 Summary OFF 11/13、ON 1/13 达到长度上限的非对称现象，应继续作为工程诊断处理；不能删除这些输出，也不能在本轮静默改官方 prompt、cap 或重生成已评试题。

## 原计划与实际执行的衔接提案

**PROPOSED RESEARCH CHANGE — NOT AUTHORIZED**（本文件不激活改动）

- 修改条款：V2/V3 原定两份独立人评及预先 consensus 的参照流程，改为如实记录的“两名评审共同审阅、一份 A 联合答卷”；未修改的 A 为主要联合参照，六题复核及助手分析单列敏感性结果。AI B 只作探索性对照。
- 原因：实际提交方式已明确，研究者要求继续并不再增加人评；复核不能追溯性变成原始盲评。
- 失效范围：不能报告已完成原定 192 份独立 primary judgments 或两份独立人评一致率；旧空白卷与所有生成记录仍作为来源保留。
- 重跑范围：不要求人评重做，也不重生成 142 个输出；尚未执行的 Gemini 资格测试按如实记录的参照流程运行。本文没有修改任何已有 Gemini 结果。
- 主张边界：人机一致性是针对联合参照的测量诊断；官方 RQ1/RQ2 能力结论和 PM 研究主张不变。

收费执行的单独授权来源是仓库 `AGENTS.md` 的执行顺序及 `paper1_gemini_pairwise_teacher_identity_20260908_v2.json` 中的 `paid_calls_authorized_by_this_identity: false`。本轮只完成记录、实现修复与离线准备，未自行打开这些权限或四把 outcome lock。

## 复现入口

在 `project/` 下使用现有 Paper-1 Python 环境运行：

```bash
python scripts/paper1/63_prepare_teacher_review_closeout.py \
  --human-a /home/tokkio/paper1_pairwise_teacher_rater_a_sheet_v2_zh_v1_rated.json \
  --ai-b-html /home/tokkio/AI_B_中文评审结果.html \
  --followup /home/tokkio/六题复核_完整记录.json \
  --output outputs/paper1_pairwise_teacher/review_closeout_20260917_v1
```

输出包含 `reference_trace.json`、`intake_result.json`、`closeout_record.json`，均在忽略的 `outputs/` 中；不包含新卷子。
