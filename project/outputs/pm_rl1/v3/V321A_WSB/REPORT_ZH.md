# WS-B 第 12 轮交付总览（V3.2.1-A；CPU，候选）

- **执行量**：Generator 0、GPU 0、Judge 0、奖励训练 0、付费 API 0、合并 0。所有协议都是候选（PROPOSED_NOT_ADOPTED）。
- **未修改**：冻结的 P2 v1、H0、EXECUTION_STATE，以及 #17、#20 的候选文件。
- **一页准入表**：[admission/ADMISSION_ONE_PAGE_ZH.md](admission/ADMISSION_ONE_PAGE_ZH.md)。

## 交付对照

| # | 研究者要求 | 交付 |
|---|---|---|
| 1 | V3.2.1-A 协议修订候选及逐条差异 | [协议文档](../../../../docs/PM_RL1_V321A_PROTOCOL_REVISION_CANDIDATE_ZH.md)（sha `27df254f…`）、[PROTOCOL_V321A_CANDIDATE.json](protocol/PROTOCOL_V321A_CANDIDATE.json)、[DIFF_VS_V321.json](protocol/DIFF_VS_V321.json)、[GATES_V321A.json](gates/GATES_V321A.json) |
| 2 | 中文 PP1 盲评 HTML 工具 | [PP1_REVIEW_TOOL.html](pp1_tool/PP1_REVIEW_TOOL.html)（离线，单文件）；源码在 [review/](../../../../src/metacom_pm/rl1v3/review/)；PP1 整理者真实任务包的登记见 [PP1_CURATOR_PACKAGE_REGISTRY.json](pp1_tool/PP1_CURATOR_PACKAGE_REGISTRY.json)（任务包放在仓库外） |
| 3 | PP1 完整程序模拟与失败测试 | [E2E_REPORT_ZH.md](pp1_e2e/E2E_REPORT_ZH.md)：101/101 通过，其中篡改测试 9 项；另有单元测试 15 项 |
| 4 | 评审人员职责模板和操作说明 | [ROLES_AND_SOP_ZH.md](pp1_tool/ROLES_AND_SOP_ZH.md) |
| 5 | FC-MS 主比较、统计功效与预算 | [FCMS_DESIGN_POWER_BUDGET_ZH.md](fcms/FCMS_DESIGN_POWER_BUDGET_ZH.md) |
| 6 | 90 条正式筛查执行包 | [SCREEN90_EXECUTION_ZH.md](screen90/SCREEN90_EXECUTION_ZH.md) |
| 7 | A renderer 候选的独立验收计划 | [RENDERER_ACCEPTANCE_PLAN_ZH.md](renderer/RENDERER_ACCEPTANCE_PLAN_ZH.md)（A 的候选尚未提交） |
| 8 | 一页准入表 | [ADMISSION_ONE_PAGE_ZH.md](admission/ADMISSION_ONE_PAGE_ZH.md) |
| — | R1–R5 修复计划 | [R1_R5_REPAIR_PLAN_ZH.md](r1r5/R1_R5_REPAIR_PLAN_ZH.md) |
| — | EvoEmo 来源与许可证据表 | [LICENSE_EVIDENCE_ZH.md](license/LICENSE_EVIDENCE_ZH.md) |

## 最重要的几点

1. **版本 A 的主比较**：S1 上 DP-MS 相对 OFF 的 QH 净偏好，是唯一的主检验。
   - 次要比较（RET−OFF、DP−RET）在主检验为 superior 时才做 Holm 检验；
   - Q0 与 F 是保护和约束；
   - 结论只限于资源潜在价值和检索质量。
2. **精度上限**：17 个 owner 组下，每组 2 个 S1 时 MDE 约 0.38，每组 4 个时约 0.29。
   - 同一 owner 加再多前缀，ICC 0.1 时也降不到约 0.16；
   - −0.10 非劣界在 ICC ≥ 0.05 时不可达。
3. **工具已可用**：
   - Q0 部分不含历史；QH/F 部分只能在协调人登记 Q0 锚点之后载入；
   - 位置完全平衡，两名审阅者镜像；
   - 锁定后不能修改；导出文件由 Python 独立复核。
4. **转义**：现行 `html.escape` 改变了 56% 的 RAW 轮次。建议统一 renderer 采用原文加边界检查，并让 DP 与 RET 使用相同的块框架。
5. **许可**：本仓库是公开的，已经包含 ESConv 与 EvoEmo 的原始数据。ESConv 是 CC BY-NC 4.0 并注明“仅限学术研究”，EvoEmo 数据本身没有明确的许可。公开再分发尚未确立，需要研究者决定。本轮新生成的任务包都放在仓库外。

## 运行与复现

| 内容 | 位置 |
|---|---|
| 各步骤日志 | [logs/](logs/) |
| 清单 | 各子目录下的 `MANIFEST.json` |
| 脚本 | [V321A_wsb.py](../../../../scripts/rl1v3/V321A_wsb.py)：e2e / protocol / tool / fcms / screenpack / renderer / license / admission；浏览器驱动 [V321A_pp1_e2e.mjs](../../../../scripts/rl1v3/V321A_pp1_e2e.mjs) |
| 测试 | [test_rl1v3_v321a_pp1_tool.py](../../../../tests/test_rl1v3_v321a_pp1_tool.py)、[test_rl1v3_v321a_protocol.py](../../../../tests/test_rl1v3_v321a_protocol.py) |
| 仓库外的任务包 | `/opt/tokkio-data0/tokkio_projects/pmrl1-validation/wsb-v321a-private/` |
