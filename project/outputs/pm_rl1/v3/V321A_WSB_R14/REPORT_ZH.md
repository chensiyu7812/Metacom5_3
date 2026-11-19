# WS-B 第 14 轮：研究决定收口与真实人工筛查启动准备

- **执行量**：GPU 0、Generator 0、Judge 0、BC/PPO 0、付费 API 0、合并 0。
- **没有做的事**：没有发送邮件，没有改仓库设置，没有删除或改写任何内容，没有新增协议或许可调查。
- **RAW 自检**：本轮全部输出的指纹命中为 0，真实任务包都在仓库外。

| # | 交付 | 文件 |
|---|---|---|
| 1 | 研究决定最终签署候选，以及 Gate 状态（PASS 7 / PENDING 26 / BLOCKED 31；E6 与 M4 转为 PASS） | [RESEARCHER_DECISION_V321A_FINAL_CANDIDATE_ZH.md](decision/RESEARCHER_DECISION_V321A_FINAL_CANDIDATE_ZH.md)、[GATES_R14.json](gates/GATES_R14.json) |
| 2 | 人工筛查可执行包与人员登记需求 | [SCREENING_KIT_ZH.md](kit/SCREENING_KIT_ZH.md)、[CURATOR_GUIDE_ZH.md](kit/CURATOR_GUIDE_ZH.md)、[STAFF_REGISTRY_TEMPLATE.csv](kit/STAFF_REGISTRY_TEMPLATE.csv)、[KIT_REGISTRY.json](kit/KIT_REGISTRY.json) |
| 3 | PP1 真实评审准备情况（含译文建议与工作量） | [PP1_READINESS_ZH.md](pp1/PP1_READINESS_ZH.md) |
| 4 | 需要研究者亲自完成的最小决定清单 | [MIN_DECISIONS_ZH.md](MIN_DECISIONS_ZH.md) |
| — | 数据使用决定登记（研究者决定，不是新许可） | [DATA_DECISION_R14_ZH.md](governance/DATA_DECISION_R14_ZH.md) |

**R1–R5**：

- R3、R4 已修复（第 13 轮，`8198f09d`），等待 WS-A 签收；
- R1、R2、R5 保持为在线环境的独立待办；
- 它们不阻止 A0、PP1 或静态 FC-MS。

**本轮新增代码**：

- [V321A_r14.py](../../../../scripts/rl1v3/V321A_r14.py)：kit / receive / report / decision / gates / selftest；
- [screen_report.py](../../../../src/metacom_pm/rl1v3/review/screen_report.py)：预先固定的重叠、重叠一致性；
- 测试：[test_rl1v3_v321a_r14.py](../../../../tests/test_rl1v3_v321a_r14.py)。
