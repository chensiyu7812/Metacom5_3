# PM V1.5 V5.3 现有 576 Effect 数据分层语义审计

日期：2026-08-09  
性质：outcome-stratified、outcome-hidden 单 reviewer 法证审计；不是独立人工确认  
样本：32 groups（MP/MS/ME/RS 各 8），96 replicate-level final ON/OFF pairs

## 技术结论

现有正式数据不能直接作为“何时调用组件”的可信监督。原因已经从推测变成了实际样本证据：

- 32 个分层 groups 中，仅 14 个 candidate 被判为 `CLEARLY_APPLICABLE`；其余为冗余 6、相关但无用 7、无关或可能误导 5。
- 82 个可审核功能使用 replicates 中，原 function judge 把 46 个不构成合格功能使用的回复判成了 `USED`，占 `56.1%`。
- 32 个 group 的人工 ON/OFF 偏好方向与原 Q effect 符号仅 17 个一致，一致率 `53.1%`。
- 只有 7/32 groups 同时满足：candidate 明显适用、三条回复均可审、至少两条真正功能使用、零 boundary violation。这个干净子集中，人工偏好为 5 positive、1 tie、1 negative。

这些比例不能外推为完整 576 的总体发生率，因为样本特意覆盖 strong positive、strong negative、near-zero 与 fallback 四个 outcome strata。但它足以证明：**candidate applicability、functional realization 和 final response preference 是三种不同变量，当前正式标签把它们混在了一起。**

## 审计对象与定义

### Group grain

每个 group 固定：

- 一个 current visible dialogue；
- 一个 actual Rank-1 typed candidate；
- 三个 paired generator seeds；
- 每个 seed 一个 final ON reply 和一个 final OFF reply。

### Candidate relevance

- `CLEARLY_APPLICABLE`：candidate 提供当前回复确实需要的合法过去信息或明确适用的 card。
- `RELATED_BUT_REDUNDANT`：相关，但当前 turn 已经说出同一信息。
- `RELATED_BUT_NOT_USEFUL`：主题相关，但对当前 response act 没有边际功能。
- `IRRELEVANT_OR_MISLEADING`：无关、错人、错事件或容易造成错误 continuity。
- `UNCERTAIN`：可见材料不足。

### Functional use

- `FUNCTIONAL_USE`：candidate 形成了可见、具体、边界正确的功能贡献。
- `SURFACE_ECHO_ONLY`：只复述 candidate/current turn，没有新增功能。
- `NOT_USED`：回复没有使用 candidate。
- `BOUNDARY_VIOLATION`：错 owner、错时态、内部 ID 泄漏，或违反 card 的关键边界。
- `UNREVIEWABLE_RAW_REPLY_MISSING`：final reply 为 fallback，guard 前 raw reply 未保存。

### Response preference

只判断 final ON/OFF 哪个更好，不推断好坏是否由 candidate 导致。该变量与 functional use 分开。

## 方法与防止看答案审题

1. 由脚本按 component × outcome stratum 选择 32 groups：每个 component 各 2 个 strong-positive clean、strong-negative clean、ON-fallback 和 near-zero clean。
2. reviewer packet 隐藏 sampling stratum、原 Q effect、原 Q judge 与原 function judge 标签。
3. 先完成并冻结 32 groups 的语义判断，记录 SHA256。
4. 冻结后才打开 private outcome key 做一致性分析。
5. 没有进行任何 API 调用，也没有修改原正式 outcome。

冻结判断 SHA256：`2332795d4b507257abf1079323f04cf6f1685a593b3bd7a5a530874966c994b6`。

## 发现一：强正 Q 不等于 candidate 真正适用

隐藏的 strong-positive-all-clean stratum 共 8 groups，其中：

- `CLEARLY_APPLICABLE`：1；
- `RELATED_BUT_REDUNDANT`：3；
- `RELATED_BUT_NOT_USEFUL`：4；
- `IRRELEVANT_OR_MISLEADING`：0。

也就是说，7/8 个强正 Q group 并不是清楚的“这个 candidate 在这里应该开”。它们常见的实际机制是：ON generator 写得更长、更具体、提出了建议，尽管这些内容没有来自 candidate 的合法边际功能。

因此 `Q(ON) > Q(OFF)` 不能单独成为组件值得打开的标签。必须额外满足 functional mediation：candidate 确实被合法使用，并且回复改进可以归因于该组件的声明功能。

## 发现二：强负 Q 也不等于 PM 不该调用

隐藏的 strong-negative-all-clean stratum 共 8 groups，其中 5 个 candidate 被判为 `CLEARLY_APPLICABLE`。

典型例子是：过去同事 James 的 falling-out 确实解释当前对新工作的恐惧；但是 ON generator 过早建议联系 James 或采取行动，OFF 只是继续澄清，因而 OFF 更好。

这类失败应记录为：

- candidate layer：correct；
- PM semantic opportunity：plausibly correct；
- generator response act：poor/over-directive；
- system ITT：negative。

如果把它直接作为 `MP=OFF` 的监督，模型学到的会是“不要调用有用过去”，而不是“调用后不要让 generator 过度建议”。

## 发现三：Function judge 不能区分使用、复述与越界

96 replicates 中 14 个因 raw reply 缺失而不可审核；剩余 82 个中：

| 冻结盲审 | 原 judge `USED` | 原 judge `NOT_USED` |
|---|---:|---:|
| 合格 `FUNCTIONAL_USE` | 32 | 0 |
| 非合格使用：echo / not-used / boundary violation | 46 | 4 |

原 judge 的主要问题不是漏判，而是把“提到了相似内容”当成“candidate 产生了功能贡献”。例如：

- 当前 turn 已经说 therapist，ON 再说 therapist，被判 `USED`；
- candidate 是用户过去“向别人求助后得到视角”，generator 写成助手“我曾向朋友求助”，仍被判 `USED`；
- RS card 要求一个 correction check，回复只做陈述性 paraphrase，没有给纠正空间，仍被判使用；
- card 明确只允许一个步骤，generator 堆出多个活动，仍被判使用。

所以 function label 不能再由一个宽泛 prompt 自由判断。它必须具备 candidate literal binding、response literal binding、owner/time/card-boundary 三类机器与人工联合条件。

## 发现四：原 Q 方向需要独立重校准

冻结单 reviewer 的 group-level preference sign 与原 Q effect：

- 同方向：17/32；
- 不同方向或一方为 tie：15/32。

这不是足以宣布原 Q judge “错误 46.9%”的 confirmatory inter-rater estimate，因为：

- 只有一个新的 AI reviewer；
- 样本按 outcome strata 选取；
- 新 reviewer 使用三分类整体偏好，原 Q 是四维、正反顺序平衡后的连续值。

但它是 High-severity construct-validity warning：原 Q 不能在没有 human calibration overlap 的情况下被当作连续真值。尤其 near-zero 组中，有多条 reviewer 认为 ON 明显更好；strong-negative 中也有 reviewer 认为 ON 更好。

## 发现五：真正可用的 semantic-value groups 很少

严格定义一个诊断性 clean subset：

- candidate `CLEARLY_APPLICABLE`；
- 三个 replicates 全部可审核；
- 至少两个 `FUNCTIONAL_USE`；
- 零 `BOUNDARY_VIOLATION`。

只有 7/32 groups 满足：MS 4、MP 1、ME 1、RS 1。其人工偏好方向为：positive 5、tie 1、negative 1。

这提示一个重要但尚不能外推的事实：当 candidate 确实适用、generator 也确实执行时，组件更可能带来正贡献；现有失败主要发生在进入这个干净因果路径之前。但必须用独立人工复核和更大、outcome-blind 支持样本确认。

## 责任分解已经可以明确

| 观察结果 | Candidate | PM | Step2 | Guard | Judge | System ITT |
|---|---|---|---|---|---|---|
| candidate 无关或冗余 | 失败 | 不应开或 unresolved | 不评价 | 不评价 | 应识别 | 记录最终结果 |
| candidate 适用且被正确使用，ON 更好 | 正确 | 开启可算正确 | 正确 | 正确 | 应识别 | 正收益 |
| candidate 适用，但 generator 未用/越界 | 正确 | 不能仅据此判错 | 失败 | 视 raw reply 裁决 | 应分开 | 保留负 ITT |
| PM 选对但 guard 误杀 | 正确 | 正确 | 可能正确 | 失败 | 应分开 | 保留 fallback ITT |
| candidate 未用，但 ON 随机写得更好 | 无功能中介 | 不能形成开标签 | 非功能实现 | 可能正确 | Q 可为正、F 应为否 | 正 ITT但非语义监督 |

## 为什么换成强化学习也不能自动解决

如果环境、状态、动作、转移和奖励都已经科学正确，强化学习确实可以自己探索。但当前最困难的恰恰是这些对象尚未被定义成可判定量：

- “回复更长更具体”是否等于 reward？
- generator 没执行 card，是 policy 错还是 environment transition 错？
- candidate 错人时，action reward 能否反向训练 PM？
- 用户支持对话不存在可安全反复探索的真实环境，离线数据也没有完整 action coverage。

把当前混合 Q 当 reward 做 RL，只会让 agent 学会 exploit judge，例如更长、更多建议、更强情绪语言。RL 不会消除 reward ambiguity，只会更有效地利用它。

当前问题更接近一个**带 executor 的 offline contextual bandit**：

- context：当前可见对话 + 合法 candidate descriptors；
- action：16 个组件组合；
- executor：generator + guard；
- outcome vector：Q、absolute risk、functional realization、cost；
- policy：PM；
- unknown：candidate/semantic/executor outcome 不可确定时进入 `UNRESOLVED`，不是硬贴标签。

在这个定义下，可以先把一轮决策测清楚；没有必要假装已经有可信的长期状态转移模型。

## 现在如何把模糊系统变成可判定系统

不是继续增加方案文字，而是要求每条训练/测试记录都有以下 typed truth：

1. `candidate_status ∈ {VALID_APPLICABLE, VALID_REDUNDANT, VALID_NOT_USEFUL, INVALID, UNRESOLVED}`；
2. `pm_oracle_set ⊆ 16 actions`，只由 pre-action 可见信息和冻结 rubric 决定；
3. `execution_status ∈ {RECEIVED, USED, FUNCTIONAL, BOUNDARY_FAILURE, NOT_USED, UNRESOLVED}`；
4. `guard_status ∈ {TRUE_ACCEPT, TRUE_REJECT, FALSE_ACCEPT, FALSE_REJECT, UNRESOLVED}`；
5. `outcome = {Q, absolute R events, F, C}`；
6. `responsible_layer` 由以上字段机械计算，不由 reviewer 写一段自由解释。

语义模型的边界也必须成为字段：

- clear case 才给监督；
- ambiguous case 为 `UNRESOLVED`；
- OOD 或支持不足时 fail closed；
- 论文只声明 clear capability family 的表现。

## 数据质量结论

| 数据用途 | 当前结论 |
|---|---|
| 部署系统 ITT 诊断 | 可保留，但必须披露 fallback/guard 与 judge 问题 |
| 训练纯 Step1 semantic-value head | 当前不安全 |
| 证明 Step2 已 qualified | 不支持 |
| 证明 function-use rate 很高 | 原结论撤回 |
| 直接训练完整 16-action oracle | 不支持 |
| 作为下一轮人工校准与错误类型发现池 | 可用 |

## 下一步只做检查，不启动新版本

1. 将现有 576 groups 中 deterministic fallback 的 function 状态机械改为 `NOT_USED_FINAL`，raw execution 保持 `UNRESOLVED`；不覆盖原 artifact，生成派生审计表。
2. 从 576 groups 分层抽取独立人工 overlap，至少双 reviewer，分别审核 candidate、F、Q；先测一致率，不先定训练门。
3. 对全量数据运行可机械判定的 candidate redundancy、owner、event identity、card-boundary 检查。
4. 只在 candidate clear + executor functional 的子集评估 Q 可重复性；与 deployment ITT 分栏，不互相覆盖。
5. 完成后再决定现有 paired outcomes 中哪些可训练、哪些只能作系统诊断。

在这些检查结束前，不继续 V5.4、不增加长期用户、不用新模型重跑 effect。
