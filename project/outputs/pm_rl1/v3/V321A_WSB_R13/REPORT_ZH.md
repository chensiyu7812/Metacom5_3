# WS-B 第 13 轮交付总览（V3.2.1-A 决策收口、#21 E6、人工筛查准备、数据治理）

- **执行量**：GPU 0、Generator 0、Judge 0、训练 0、付费 API 0、合并 0。没有改仓库隐私设置，没有删除文件，没有改写历史，没有发送邮件。
- **一页准入表**：[admission/ADMISSION_ONE_PAGE_R13_ZH.md](admission/ADMISSION_ONE_PAGE_R13_ZH.md)。

## 交付对照

| # | 研究者要求 | 交付 |
|---|---|---|
| 1 | #21 E6 独立验收回执 | [WSB_E6_RECEIPT_PR21_ZH.md](e6_receipt/WSB_E6_RECEIPT_PR21_ZH.md)：<br>• #21 **不签收**：47 项中 43 项通过，4 项缺陷（高 2、中 1、低 1）附修复要求；<br>• A 在本轮期间提交了修复 #23，同一 harness 复跑后**签收**：3.11 下 49/49，3.12 进程路径 20/20，范围为 CPU 故障注入；<br>• harness 见 [V321A_e6_harness.py](../../../../scripts/rl1v3/V321A_e6_harness.py) |
| 2 | V3.2.1-A 研究决定回执候选 | [RESEARCHER_DECISION_RECEIPT_ZH.md](decision/RESEARCHER_DECISION_RECEIPT_ZH.md)，待研究者签署 |
| 3 | 人工 DP-MS 规则对齐 | [DP_MS_ALIGNMENT_ZH.md](dp_alignment/DP_MS_ALIGNMENT_ZH.md)：A 工具独立核验通过，列出需要补齐的项；15% 双人重叠方案 |
| 4 | 人工筛查准备 | [SCREEN_PREP_ZH.md](screen_prep/SCREEN_PREP_ZH.md)：表单 S-v2、实际分发包哈希、真实代码替换命令、标注报告工具 |
| 5 | PP1 真实人评准备 | [PP1_REAL_REVIEW_PREP_ZH.md](pp1_prep/PP1_REAL_REVIEW_PREP_ZH.md)：培训、收发清单、锚点登记表、SOP、双语显示、翻译流程；表单 S-v2 后 E2E 重跑 101/101，见 [E2E_REPORT.json](pp1_e2e/E2E_REPORT.json) |
| 6 | 统计与预算 | [REPLAN_ZH.md](replan/REPLAN_ZH.md)：只用标签重算的工具；模拟演示显示，只靠 90 条很可能需要扩展筛查 |
| 7 | renderer 与研究范围 | [RENDERER_DIFF_ZH.md](renderer_diff/RENDERER_DIFF_ZH.md)：候选通过，待正式 DP 样本复验；每个 MS 请求约 10%–20% 的 token 改变 |
| 8 | 公开仓库与数据许可 | [DATA_GOVERNANCE_ZH.md](governance/DATA_GOVERNANCE_ZH.md)：RAW 清单与 A/B/C 决策表；[许可确认邮件草稿](governance/EMAIL_DRAFT_ES_MEMEVAL_LICENSE.md)（不发送） |
| 9 | R1–R5 | [R1_R5_STATUS_ZH.md](r1r5/R1_R5_STATUS_ZH.md)：R3、R4 已修复，测试先红后绿，待 WS-A 签收；R1、R2、R5 待对齐 |

## 运行与复现

| 内容 | 位置 |
|---|---|
| 脚本 | [V321A_r13.py](../../../../scripts/rl1v3/V321A_r13.py)（e6 / rdiff / inventory / dpcheck / screenprep / replan / decision / admission）；[V321A_e6_harness.py](../../../../scripts/rl1v3/V321A_e6_harness.py) |
| 测试 | [test_rl1v3_v321a_r13.py](../../../../tests/test_rl1v3_v321a_r13.py)；R3/R4 的测试在 [test_rl1v3_v32_wsb.py](../../../../tests/test_rl1v3_v32_wsb.py) |
| 仓库外的分发包 | `/opt/tokkio-data0/tokkio_projects/pmrl1-validation/wsb-v321a-private/r13/` |
| 本轮新提交的 RAW 派生内容 | 0（见治理文档 §1 的自检） |
