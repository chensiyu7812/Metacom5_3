# WS-B 第 15 轮：按人分配的中文人评交接

- **执行量**：GPU 0、Generator 0、Judge 0、训练/BC/PPO 0、付费 API 0、合并 0。
- **没有做的事**：没有发送邮件，没有改仓库设置，没有删除或改写任何数据，也没有开展许可调查。
- **含原文的文件**：全部放在仓库外的交接目录，仓库里只有代码、哈希清单和不含原文的说明。
- **RAW 自检**：对本轮 69 个会进仓库的文件，与全部 8,085 个来源句段的 90,913 个 8 词片段逐一比对，命中 0。

## 交付

| # | 交付 | 文件 |
|---|---|---|
| 1 | 从这里开始 | [START_HERE_ZH.md](docs/START_HERE_ZH.md) |
| 2 | 四人分工 | [ROLE_ASSIGNMENTS_ZH.md](docs/ROLE_ASSIGNMENTS_ZH.md) |
| 3 | 各人的 HTML 与 SHA 清单 | 交接目录 `wsb-v321a-handover-r15/`（在仓库外）；哈希见 [HANDOVER_MANIFEST.json](HANDOVER_MANIFEST.json) |
| 4 | 给 ChatGPT 的统一转换说明 | [CHATGPT_转换说明_ZH.md](docs/CHATGPT_转换说明_ZH.md) |
| 5 | 练习、导出、导入、收件的最简说明 | [OPS_ZH.md](docs/OPS_ZH.md)、[REVIEWER_GUIDE_ZH.md](docs/REVIEWER_GUIDE_ZH.md)、[CURATOR_GUIDE_R15_ZH.md](docs/CURATOR_GUIDE_R15_ZH.md)、[PP1_AFTER_GENERATION_ZH.md](docs/PP1_AFTER_GENERATION_ZH.md)、[DP_PREP_ZH.md](docs/DP_PREP_ZH.md) |
| 6 | DP v2 独立复验回执 | [WSB_DPV2_RECEIPT_ZH.md](dpv2/WSB_DPV2_RECEIPT_ZH.md) |
| 7 | 状态表 | [STATUS_ZH.md](docs/STATUS_ZH.md) |

## 与指令不同的两处

1. **ChatGPT 不接收任务 HTML，只接收小文本批次。**
   - 任务页里有哈希链日志、阶段锁定和盲态逻辑。整页交给 ChatGPT 重排之后，无法保证这些逻辑保持不变。
   - 改为由 ChatGPT 逐行翻译批次（55 个，每个约 3,000 词），`zh` 命令逐行检查译文后，把译文放进已验证的页面。
   - 中文优先、英文逐句可展开，由页面本身实现。如果有人仍然改了页面，`check` 命令负责把关。
2. **ChatGPT 的操作人改为两名整理者交叉担任，R1 不操作。**
   - 研究者本人是 R1。操作翻译就要读完全部历史，这会破坏 Q0（不看历史）和 QH（只看此刻之前的历史）。
   - 整理者如果翻译自己组的人物，就会在标注较早的前缀之前先读到较晚的会话。
   - 交叉操作的结果：正式 90 条没有一条提前读到更晚的会话；交叉复核 11 条、PP1 8 条会提前读到，已登记。
   - 生成回复（Y01）由 CUR2 操作翻译。

## 本轮代码

- **评审工具显示层**（规则不变）：[pp1_tool.py](../../../../src/metacom_pm/rl1v3/review/pp1_tool.py)、[pp1_ui.js](../../../../src/metacom_pm/rl1v3/review/pp1_ui.js)。
  - 逐句无损切分；中文优先，英文原文（权威）可以展开；F 中可一键“引用此句”。
  - 筛查页显示题号和来源校验码，网页和 Python 两边算法相同。
  - 导出格式没有改变。
- **流程脚本** [V321A_r15.py](../../../../scripts/rl1v3/V321A_r15.py)：packages、batches、zh、check、receive、report、practice、part2、dryrun、replybatch、reviewers、part2real、selftest。
- **交接目录生成** [V321A_r15_docs.py](../../../../scripts/rl1v3/V321A_r15_docs.py)；浏览器冒烟测试 [V321A_r15_smoke.mjs](../../../../scripts/rl1v3/V321A_r15_smoke.mjs)。
- **分发检查** [dist_gate.py](../../../../src/metacom_pm/rl1v3/review/dist_gate.py)：调用 A 的 `check_reviewer`，并执行裁决者冲突规则。
- **DP v2 复验脚本** [V321A_dpv2_harness.py](../../../../scripts/rl1v3/V321A_dpv2_harness.py)。
- **测试** [test_rl1v3_v321a_r15.py](../../../../tests/test_rl1v3_v321a_r15.py)：21 项。

## 验证结果

| 检查 | 结果 |
|---|---|
| 5 个英文源包与 PR #25 S-v2 任务包的一致性 | 4 个逐字节相同；PP1 只换了代码（CURP → CUR1） |
| 浏览器端到端（模拟） | 原路径 101/101（[pp1_e2e_regression](pp1_e2e_regression/E2E_REPORT.json)）；中文路径 107/107（[pp1_e2e_zh](pp1_e2e_zh/E2E_REPORT.json)） |
| 交接流程自测（真实英文包 + 假译文） | 27/27（[R15_SELFTEST.json](selftest/R15_SELFTEST.json)）：植入的四类错误都被拦下；修正文件生效；5 个包全部生成；6 种页面篡改被拒绝；浏览器导出和导入通过；收件顺序规则生效；PP1 生成后的命令试跑通过。测试页面用后已删除 |
| 练习第二部分流程（浏览器） | 6/6（[PRACTICE_PART2_FLOW_CHECK.json](practice/PRACTICE_PART2_FLOW_CHECK.json)） |
| DP v2 复验 | 61/61；2 项缺陷（同一个问题）；7 项观察 |
| V3 测试（与 CI 命令相同） | 713 passed，0 skipped |
