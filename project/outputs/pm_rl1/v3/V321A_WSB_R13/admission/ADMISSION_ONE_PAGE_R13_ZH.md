# 一页准入表（第 13 轮，2026-11-19）

- **门禁状态**：7 个 Gate 全部是 BLOCKED。逐项共 PASS 6、PENDING 27、BLOCKED 31；明细见 [ADMISSION_TABLE_R13.json](ADMISSION_TABLE_R13.json)。
- **本轮用量**：GPU 0、Generator 0、Judge 0、训练 0、付费 API 0、合并 0。没有改仓库隐私设置，没有删除任何数据。

## 已通过 / 已完成（CPU）

| 项 | 证据 |
|---|---|
| **E6**：#21 不签收（43/47，4 项缺陷）。A 在 #23 修复后，同一 harness 复跑：**签收**（3.11 下 49/49；3.12 进程路径 20/20；CPU 故障注入范围） | [E6 回执](../e6_receipt/WSB_E6_RECEIPT_PR21_ZH.md) |
| renderer 机械回执：候选通过，待正式 DP 样本复验；新旧 token 差异已记录 | [renderer 差异](../renderer_diff/RENDERER_DIFF_ZH.md) |
| DP 选材池独立核验：8 个池恰好等于合法会话（87 个），文本与 RAW 相同，没有排名或结果字段 | [DP 对齐](../dp_alignment/DP_MS_ALIGNMENT_ZH.md) |
| 表单 S-v2（增加“是否需要结合多个会话”）、实际分发包（哈希）、标注报告与重新规划工具；E2E 101/101 | [筛查准备](../screen_prep/SCREEN_PREP_ZH.md)、[重新规划](../replan/REPLAN_ZH.md) |
| PP1 真实人评准备：培训、收发清单、锚点登记表、SOP、双语显示、翻译流程 | [PP1 准备包](../pp1_prep/PP1_REAL_REVIEW_PREP_ZH.md) |
| R3、R4 已修复（待 WS-A 签收） | [R1–R5 进度](../r1r5/R1_R5_STATUS_ZH.md) |
| 公开仓库 RAW 清单与治理决策表；许可确认邮件草稿 | [治理决策表](../governance/DATA_GOVERNANCE_ZH.md) |

## 待研究者

| 事项 | 解除哪些项 |
|---|---|
| 签署 [研究决定回执候选](../decision/RESEARCHER_DECISION_RECEIPT_ZH.md) | C1、C9、P5、C6/C7（renderer）、C10（DP） |
| 正式签收 G0e 研究身份冻结（#10 `73fdb12f`） | E1 |
| 选择治理方案 A/B/C；确认受限共享条件；是否发送许可确认邮件 | M4；人工筛查能否开始 |
| 指定 PP1 整理者 1 名、审阅者 2 名、裁决者 1 名；正式筛查整理者 1–2 名，并给出匿名代码 | P3、P4、C2、C5 |
| 是否提供中文译文；如提供，由人工还是本地模型完成 | P5 |

## 待工程

| 谁 | 事项 | 解除哪些项 |
|---|---|---|
| WS-A | DP 选材工具补齐：覆盖、时效、阶段字段；回执 sha 绑定到 FC-MS 计划 | C10 |
| WS-A / WS-B | R1、R2、R5 对齐；R3、R4 签收 | G-RWD R4 |
| WS-B | 正式样本请求导出后，复验 renderer（RA1–RA7）和 token 差异 | C7 |

## 待授权

E6 已在 #23 上签收，但 A0 和 PP1 仍需满足各自的前提：

- **A0 的 4 次调用**：还需要 E1（G0e 研究身份正式冻结签收）和研究者的单独授权。授权须绑定 A0 binding `c9eb9169…` 与最终 checkout HEAD。
- **PP1 的 16 次调用**：还需要 A0 实测通过、PP1 协议获批、筛查标签和 QH 冻结、人员到位，以及研究者的单独授权（绑定 PP1 binding `2a14cac2…`）。

## 下一次可执行的动作

1. **不需要 GPU，条件一确认就能开始**：
   - 研究者确认共享条件并指定整理者；
   - 用真实代码运行 `V321A_r13.py screenprep --codes …` 生成实际分发包；
   - 先做 PP1 的 8 条 S 标注，再做正式 90 条筛查；
   - 标注完成后，用 `screen_report` 得到真实的 S1 数量与耗时，再用 `fcms_replan` 冻结预算。
2. **E6 已签收**：研究者正式签收 G0e 研究身份后，可以单独授权 A0（4 次调用，全阶段硬上限 1,200 秒）。A0 通过之后，PP1 只差人员和人工标注。
3. **DP 选材**：正式样本的 DP 选材与 90 条筛查同步进行，由同一整理者在同一阅读顺序中完成；重叠 15% 由第二人另做。
