# 人工筛查准备：实际分发包与标注报告

## 1. 分发包（表单 S-v2）

本轮的变化：表单 S 增加了 **S-2b “满足这一需要，是否必须结合多个过去会话？”**（一个即可 / 必须结合多个 / 无法判断）。选 S1 时必填，选 S2 时可选，用来报告“同一 S1 是否需要结合多个会话”。

| 包 | 条数 | 任务包 sha256 | 盲态扫描 |
|---|---|---|---|
| PP1 整理者（代码 CURP，占位） | 8 | `bc43ba5e…` | 0 处 |
| 正式筛查 CUR1（占位） | 40 | `afc60209…` | 0 处 |
| 正式筛查 CUR2（占位） | 50 | `6f577ca5…` | 0 处 |

- **登记**：[DISTRIBUTION_REGISTRY.json](DISTRIBUTION_REGISTRY.json)。
- **存放位置**：任务包在仓库外的 `/opt/tokkio-data0/tokkio_projects/pmrl1-validation/wsb-v321a-private/r13/`，仓库只记录哈希。
- **40/50 的分工**：沿用上一轮，同一 owner 组不拆开。
- **换成真实代码**：研究者指定人员并给出匿名代码后，运行

  ```
  python scripts/rl1v3/V321A_r13.py screenprep --codes <代码1>,<代码2> --pp1-code <代码>
  ```

  重新生成实际分发包和哈希。内容不变，只有代码和哈希改变。代码与真实身份的对照只由研究者保管。
- **发送条件**：研究者确认受限共享条件（见 [治理决策表](../governance/DATA_GOVERNANCE_ZH.md)），并指定人员之前，**不向任何外部人员发送** RAW 包。

## 2. 标注完成后的报告（自动生成）

工具：[screen_report.py](../../../../../src/metacom_pm/rl1v3/review/screen_report.py)。输入是整理者的最终文件（先经 `verify_export` 核验）和审计映射，输出研究者要求的各项：

| 项 | 字段 |
|---|---|
| S1/S2/S0/S7 实际数量（以及 unclear） | `counts` |
| 有 S1 的独立 owner 组数，以及各组 S1 数 | `groups_with_s1`、`s1_per_group` |
| 同一 S1 是否存在多个必须结合的会话 | `s1_sessions_needed`、`s1_multi_session_share` |
| none/uncertain 比例 | 标签侧：`unclear_share`；DP 选材侧：A 的回执中 none_suitable 与 uncertain 的比例（另行汇总） |
| 人工阅读与标注的真实耗时 | `time`（总小时、单件中位数与 P90）、`curators` |
| 历史阅读方式 | `history_use`：展开过去对话、使用搜索的比例 |

- **只统计，不改动**：报告不改变任何标签，也不读取任何回复或模型结果。
- **之后**：真实标签产生后，`fcms_replan` 用它们重新规划（见 [重新规划](../replan/REPLAN_ZH.md)）。

## 3. 两件事都不需要 GPU，人员与条件确认后即可开始

1. PP1 的 8 条生成前 S 标注：1.5–2.8 小时。
2. 正式 90 条筛查：两人合计约 15–29 小时。
