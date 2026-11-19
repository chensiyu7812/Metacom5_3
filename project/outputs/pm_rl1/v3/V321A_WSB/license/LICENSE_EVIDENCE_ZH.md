# EvoEmo / ESConv 来源与许可证据表

- **核查日期**：2026-11-19。
- **方法**：
  - 用 GitHub API 读取仓库元数据、LICENSE 与 README；
  - Zenodo 页面读取一次（它的 API 拒绝了自动访问）；
  - 本地 artifact 计数。
- **机器可读版本**：[LICENSE_EVIDENCE.json](LICENSE_EVIDENCE.json)。
- **声明**：这是证据整理，不是法律意见，最终由研究者决定（必要时咨询所在机构）。

## 1. 证据

| 编号 | 来源 | 内容 | 链接 |
|---|---|---|---|
| L1 | ESConv 仓库 LICENSE | CC BY-NC 4.0 全文 | [LICENSE](https://github.com/thu-coai/Emotional-Support-Conversation/blob/main/LICENSE) |
| L2 | ESConv README 首行 | “Copyright © 2021 CoAI Group, Tsinghua University. All rights reserved. Data and codes are for academic research use only.” | [仓库](https://github.com/thu-coai/Emotional-Support-Conversation) |
| L3 | ESConv（Hugging Face） | 数据卡写 cc-by-nc-4.0；只在 refs/pr/2 分支看到，主分支未核实 | [数据集](https://huggingface.co/datasets/thu-coai/esconv) |
| L4 | ES-MemEval / EvoEmo 仓库 | 没有 LICENSE 文件，GitHub 的 license 字段为 null；README 写明 EvoEmo 在 `data/evo_emo.json` | [仓库](https://github.com/slptongji/ES-MemEval) |
| L5 | Zenodo 10.5281/zenodo.18338564 | 资源类型为 Software，许可 CC BY 4.0，2026-01-22 发布，1 个 zip（798 kB）；没有数据来源、使用条款或伦理说明 | [记录](https://zenodo.org/records/18338564) |
| L6 | ES-MemEval 论文 | 论文文本是 CC BY 4.0；这只覆盖论文本身 | [arXiv 2602.01885](https://arxiv.org/abs/2602.01885) |
| L7 | 本项目的 sanitized artifact | 401 个会话中，85 个来自 ESConv（`escNNN`），316 个是 EvoEmo 生成的会话 | 本地计数 |
| L8 | WS-A 的来源登记（#18） | `ESConv_academic_research_only`（8 条）；`inherited_research_scope; upstream_EvoEmo_license_unresolved`（261 条） | #18 bundle |
| L9 | 本仓库 | **公开**。已经包含 `data/external/ESConv.json`（9.0 MB）、`data/external/evo_emo.json`（4.5 MB）、sanitized artifact，以及 #20 提交的 8 份 QH 背景（RAW 派生） | `gh api` |

## 2. 按使用方式区分

| 使用方式 | 结论 | 依据 | 条件 |
|---|---|---|---|
| **内部研究**（团队内、非商业学术研究） | 有证据支持，前提待确认 | L1、L2：ESConv 允许非商业学术研究使用，须署名。L5：EvoEmo 的发布记录为 CC BY 4.0；其中 ESConv 派生的部分仍受 L1 约束 | 研究者确认本项目属于非商业学术研究；署名 ESConv 与 ES-MemEval；Tokkio 等商业部署用途不在此证据范围内 |
| **人工审阅共享**（把含 RAW 的任务包交给整理者、审阅者、裁决者） | 可行，但须附条件，并由研究者确认 | L1：BY-NC 允许以非商业目的分享，须附署名与许可链接。L2：仅限学术研究 | 任务包附来源署名与许可说明；参与者书面承诺只用于本研究、不转发、结束后删除；支付评审劳务是否影响“非商业”的判断，需研究者或机构确认；内容涉及情绪困扰，须事先说明并保留退出权；遵守所在机构的伦理与数据管理要求 |
| **公开再分发**（公开仓库、公开任务包、论文附录中的长段原文） | **未确立** | L1 允许非商业再分发，但 L2 写有“All rights reserved … academic research use only”。L4：数据仓库没有 LICENSE。L5 的 CC BY 4.0 属于“软件”记录，是否覆盖数据文件没有写明。CC BY 4.0 不能为 ESConv 派生部分（L7 的 85 个会话）去掉 NC 限制。EvoEmo 生成会话所用的生成模型及其条款未知 | 不能只凭“数据公开”推断可以公开再分发 |

## 3. 需要研究者决定的事

1. **确认用途**：本项目是否属于非商业学术研究。这决定了内部研究这一行能否成立。
2. **人工审阅共享**：是否接受上表中的条件；参与者承诺书的模板见 [角色与操作说明](../pp1_tool/ROLES_AND_SOP_ZH.md) §5。
3. **公开仓库现状**（L9）：
   - 选项 A：仓库转为私有；
   - 选项 B：移除原始数据与 RAW 派生文件，只保留哈希和获取脚本；注意历史提交中仍然存在，彻底移除需要改写历史；
   - 选项 C：在确认许可之后维持现状，并补上署名与许可说明。
   - 本轮新生成的 PP1 和筛查任务包已经放在仓库外，只提交哈希。
4. **上游询问**：如需确定 EvoEmo 数据本身的许可，可以向 ES-MemEval 作者询问数据许可，以及生成会话所用模型的条款。
