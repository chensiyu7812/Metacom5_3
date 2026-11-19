# 数据使用与 GitHub：研究者决定登记（第 14 轮）

## 1. 研究者已明确决定

1. 本研究属于**非商业学术用途**。
2. GitHub 仓库**继续公开**。
3. 论文和项目文档要正确说明并引用数据来源（引用文本见 §3）。
4. **当前不发送**许可确认邮件；上一轮的草稿保留，不发送。
5. **当前不执行**仓库私有化、数据删除或 Git 历史改写。

## 2. 仍存在的不确定性（如实登记）

- **这不是新的许可**：以上是研究者的决定，**不是**作者给出的新许可；本项目没有从 ES-MemEval 或 ESConv 作者处获得任何新的明确许可。
- **EvoEmo**：数据文件本身没有明确的许可声明。GitHub 仓库没有 LICENSE；Zenodo 记录（10.5281/zenodo.18338564）是“软件”类型，许可为 CC BY 4.0，是否覆盖数据没有写明。
- **ESConv**：CC BY-NC 4.0，README 写明“仅限学术研究”。EvoEmo 中有 85 个会话来自 ESConv。
- **现状**：上一轮的清单显示，仓库各分支中有 4,172 个文件含 RAW，其中 3,989 个自 2026-06-28 起就在 `main` 上（[治理记录](../../V321A_WSB_R13/governance/DATA_GOVERNANCE_ZH.md)）。
- **不再调查**：按研究者指示，不再开展同类的许可调查；以后如果出现明确的新限制，另行报告。

## 3. 引用与来源说明（供论文和项目文档使用）

> 本研究使用 ES-MemEval 提供的 EvoEmo 数据集（Zenodo 10.5281/zenodo.18338564；arXiv 2602.01885），其中部分会话来源于 ESConv（Liu et al., 2021, *Towards Emotional Support Dialog Systems*, ACL 2021；CC BY-NC 4.0，仅限学术研究）。本研究为非商业学术研究。

英文版：

> We use the EvoEmo data released with ES-MemEval (Zenodo 10.5281/zenodo.18338564; arXiv:2602.01885). Part of its sessions derive from ESConv (Liu et al., 2021, ACL; CC BY-NC 4.0, academic research use only). This work is non-commercial academic research.

## 4. 对执行的影响

| 事项 | 做法 |
|---|---|
| 数据使用范围（Gate M4） | 按研究者决定记为 PASS，备注上述不确定性 |
| 人工任务包 | 仍放在仓库外，只交给研究者指定的人员。**受限研究共享范围**（人员、承诺、用后删除）仍需研究者确认，这是分发前的最后一项 |
| 新的 RAW 派生内容 | 本轮没有新提交（指纹自检见 [交付总览](../REPORT_ZH.md)） |
