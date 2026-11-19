# V3.2.1-A 研究决定回执（候选，待研究者签署）

- **机器可读版本**：[RESEARCHER_DECISION_RECEIPT_CANDIDATE.json](RESEARCHER_DECISION_RECEIPT_CANDIDATE.json)（内含 `receipt_sha256`）。
- **性质**：这是 WS-B 对研究者第 13 轮指令的记录，状态为 `CANDIDATE_PENDING_RESEARCHER_SIGNATURE`，研究者明确签署后才生效。
- **不修改**：#22 的候选协议（`27df254f`）、V3.2.1（`d2fde5db`）、#17（`b28cf37b`）、P2 v1（`2b6057c8`），以及 H0 和 EXECUTION_STATE。
- **不自动 PASS**：采纳协议不会让许可、人员、GPU、E6 或 G0e 冻结中的任何一项变为 PASS。

## 1. 拟采纳

| 项 | 理由 | 适用范围 |
|---|---|---|
| A1–A15 的总体结构 | 版本 A：PM Step-1 负责资源获取，Step-2 保持 no-plan，Generator 隐式判断资源是否适用、是否使用、是否提及 | FC-MS-1 及后续同族比较 |
| QH 为长期支持主指标；Q0 为即时质量保护；F 为事实与安全约束；三者不合成总分 | 与研究目标一致；没有提及记忆不算错误 | 全部 FC 族 |
| 唯一主比较：S1 中 DP-MS 对 OFF 的 QH | 先回答资源的潜在价值；只设一个主检验，避免结果驱动更换指标 | FC-MS-1 |
| 次要机制比较：RET−OFF、DP−RET（主检验为 superior 时做 Holm） | 把检索质量与资源价值分开 | FC-MS-1 |
| 暂不采用 −0.10 非劣界 | 17 组下 ICC ≥ 0.05 时不可达；不显著只写 inconclusive | FC-MS-1 |
| PP1 只作程序试点，不并入正式 FC-MS | PP1 用旧 renderer，FC-MS 用新 renderer；PP1 只测程序 | PP1 |
| Step-2 维持 G0e no-plan；新的 applicability prompt 不进入当前实验族 | 保持单因素；新提示须版本化另行评价 | 当前实验族 |

## 2. 拟选择

| 项 | 身份 | 状态 |
|---|---|---|
| FC-MS renderer：#21 line-quote-1 | `renderer-fcms:e675b435…`（B 已重算） | **候选通过，待正式 DP 样本复验**。限定条件：<br>• 每个 MS 请求约 10%–20% 的 token 改变，见 [renderer 差异](../renderer_diff/RENDERER_DIFF_ZH.md)；<br>• 行为层面的注入防护与情感支持效应未实测；<br>• PP1 旧 renderer 的回复不得并入 |
| 主要 DP-MS：A 的人工选材 | #21 `46349ccf` 中的 DP 选材工具 | 需补齐：覆盖、时效、阶段字段；选择者 ≠ 审阅者；选择时间早于生成。见 [DP 对齐](../dp_alignment/DP_MS_ALIGNMENT_ZH.md) |
| Rule-DP：B 的确定性规则，作为次要诊断基线 | 协议 A4 的规则 | 只计算选中的会话，暂不生成 |
| 预算：暂定中等方案 | [fcms_replan.py](../../../../../src/metacom_pm/rl1v3/evaluate/fcms_replan.py) | 90 条真实 S 标签产生之后、任何 FC-MS 生成结果出现之前最终冻结；见 [重新规划](../replan/REPLAN_ZH.md) |

## 3. 单列、不因本回执改变的事项

| 事项 | 现状 |
|---|---|
| 数据许可与公开仓库 | 待研究者决定，见 [治理决策表](../governance/DATA_GOVERNANCE_ZH.md) |
| 人员 | 整理者、审阅者、裁决者均未指定 |
| GPU | A0、PP1、FC-MS 生成均未授权 |
| E6 | #21 不签收；#23 HEAD `67169816` 复跑后签收（CPU 故障注入范围），见 [E6 回执](../e6_receipt/WSB_E6_RECEIPT_PR21_ZH.md)；签收不是运行授权 |
| G0e 研究身份 | 研究者拟把 #10 `73fdb12f` 固定为研究级 G0e 身份。正式冻结签收待办；它不等于 merge，也不授予运行许可。本回执可以作为 integration coordinator 所问“研究身份冻结记录”的出处，但其中这一项仍是“拟固定”，不是“已冻结” |

## 4. 签署（研究者填写）

- [ ] 同意 §1、§2 全部条目
- [ ] 同意，但有以下修改：____
- 签署人 ____ 日期 ____
