# PM-v1.5 SupportNeedObservation 人工标注指南

## 1. 这份标注在判断什么

标注对象是用户**此刻需要怎样被支持**，不是给 PM 直接指定动作，也不是判断应否
开启 RS、MP、MS 或 ME。资源是否存在、资源是否匹配以及使用后是否改善回复，会由后续
独立的 opportunity/effect 数据判断。

每条记录只显示当前用户话语、最近对话和当前会话摘要。不得根据题目来源、ESConv
metadata、未来 supporter 回复、strategy annotation、survey、internal-test 或 external
outcome 推测答案。

## 2. 固定判定顺序

1. **明确边界。** 用户是否要求只倾听、拒绝建议、明确请求建议、要求一个小步骤，或
   暗示此时只能承受一个问题/任务。
2. **当前目标。** 用户主要想被听见、理解发生了什么、先稳定下来、作决定，还是采取
   行动。
3. **对话阶段。** 当前仍在探索、需要安慰稳定，还是已经准备行动。
4. **非临床紧迫度。** 只判断本轮支持的紧迫程度；不得作疾病、诊断或危机分类。危机
   safety policy 独立于小样本 PM。
5. **不确定就 abstain。** 信息不足或两个 mode 无法可靠区分时，不要勉强制造标签。

## 3. support mode 的可观察定义

| mode | 选择条件 | 不应选择的情况 |
|---|---|---|
| `listen` | 用户主要想说出来、明确要求先听、当前不宜推进解决方案 | 用户明确请求澄清问题或实际步骤 |
| `explore` | 一个低负担问题能澄清感受、事实或目标 | 连续追问、多问题盘问，或用户明确要求不追问 |
| `comfort_reassure` | 当前先需要承接、安慰、正常化感受或降低情绪负荷 | 用空泛赞美替代对具体感受的回应 |
| `light_guidance` | 用户愿意接受一个可拒绝、低门槛的小建议 | 用户只要倾听，或问题需要多步规划 |
| `structured_planning` | 用户明确准备行动，且需要共同拆解步骤、权衡或计划 | 尚未搞清目标，或当前负担不允许多步骤 |
| `abstain` | 可见信息不足、冲突或过于含混 | 仅仅因为标注者犹豫；能由明确边界解决时不应 abstain |

“用户请求建议”只是 `light_guidance/structured_planning` 的必要线索之一，不是 RS
标签。即使允许建议，Strategy Bank 也可能没有匹配资源；即使未请求建议，reflection 或
comfort 也可能适用。

## 4. goals、phase 与 urgency

`goals` 可以多选：

- `be_heard`：被听见、被承接；
- `make_sense`：理解感受、事实、关系或冲突；
- `stabilize`：先降低当下负荷；
- `decide`：作选择或明确方向；
- `act`：执行一个步骤或计划。

非 `abstain` 条目至少选择一个 goal。

`dialogue_phase`：

- `exploration`：信息/感受/目标仍待澄清；
- `comforting`：当前重点是承接和稳定；
- `action`：已准备讨论选择或执行。

`nonclinical_urgency`：

- `routine`：普通支持节奏；
- `elevated`：当下明显承压，需要更快、更聚焦地承接；
- `acute`：本轮应优先稳定并降低负担，但这仍不是临床诊断或危机标签。

## 5. 五个显式边界字段

字段可填 `true`、`false` 或 `unknown`。只有文字明确支持时才填 `true/false`；信息不足
填 `unknown`。

- `advice_rejected`：用户明确拒绝建议或只要求倾听；
- `advice_requested`：用户明确请求建议、帮助决定或规划；
- `one_small_step_requested`：用户明确只要一个小而可做的步骤；
- `listen_first_requested`：用户明确要求先听/先理解；
- `question_or_task_burden_limit`：此时最多适合一个简短问题或一个小任务。

## 6. 质量要求

- `confidence` 为 1–5；3 以下必须在 `notes` 说明歧义。
- 不使用身份、problem/emotion 标签或未来答案作推断。
- 不把情绪强度等同于建议需求。
- 不把“有可用记忆/策略”当作已知；本包不展示这些资源。
- 不为追求类别平衡而改变单条判断。
- 人工锚点是弱监督可靠性与 sanity 参照，不是自动 gold，也不单独决定 PM 动作。

## 7. 第一批标注后的语义修正

第一批 24 条标注显示，旧字段 `question_or_task_burden_limit` 实际主要被用来表达
“标注者认为下一条回复应保持低负担”，而不是“用户逐字明确说只能承受一个问题/任务”。
二者不能共用一个 target：

- **用户明确边界**是可观察输入，必须能给出可见 user 文本中的精确引文；
- **建议回复负担**是上下文相关的人类 partial label，可以是
  `minimal_presence`、`one_focus` 或 `multi_step_ok`；
- 没有找到明确引文表示“没有已核实的显式证据”，不得自动编码成用户明确说了 false。

第一批原始标注保持逐字节不变，并通过 normalized V2 binding 保留。扩展包采用上述新
schema，不要求返工第一批；两批都不是 PM action gold。
