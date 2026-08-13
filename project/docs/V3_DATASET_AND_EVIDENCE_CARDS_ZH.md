# MetaCom V3 数据集与证据卡

日期：2026-08-13
状态：`ACTIVE P0 AUDIT`

| 数据源 | 来源与性质 | 主要单位 | 允许检验 | 关键风险 | 当前状态 |
|---|---|---|---|---|---|
| ESConv | 人工众包、单会话、带支持策略标签 | dialogue | RS、即时支持 | ESC-Eval role cards 可能同源；无纵向 owner | 可用；只进 RS track |
| EvoEmo | GPT 生成并人工多阶段复核的合成长程数据 | 18 users / 401 sessions | longitudinal response、RS/MP/MS/ME | 合成、N=18、与ES-MemEval同源 | 可用；按user聚类 |
| ES-MemEval | WWW 2026；由 EvoEmo 构造 QA/summary/generation | 18 users | extraction、temporal、conflict、abstention、user modeling | 1209/1427/418版本不一致 | 阻塞正式运行，先对齐 |
| ESC-Eval | EMNLP 2024；655张角色卡，来自7个数据源并用模拟用户交互 | role card/dialogue | generator多轮ESC能力 | GPT-4抽卡、模拟用户、与ESConv/ExTES重叠、rubric偏好建议数量 | 候选主资格考卷 |
| ESC-Judge | EMNLP 2025；合成角色、E-I-A理论、成对自动judge | synthetic role | generator相对支持策略 | 小角色集、judge依赖、非绝对分数 | robustness候选 |
| 内部P2R/开发panel | 项目自建、outcome-blind或开发消费 | owner/group | treatment/selector开发 | 不能叫外部、不能从结果扩样 | development only |

## ES-MemEval 版本对齐任务

必须产生一个逐文件、逐题的 reconciliation artifact：

- WWW 2026 paper：1209 QA；
- 当前本地方案：1427-question public artifact；
- 历史 V5.2：418-question subset；
- 对每个集合记录来源 tag/commit、路径、SHA-256、question ID、capability、owner、是否 answerable、是否进入历史运行；
- 解释新增/删除/重编号，而不是只比较总数；
- 正式 V3 只能选择一个 pinned official identity，并把其他集合标为历史版本或 subset。

## 数据泄漏与重叠

- ESC-Eval role cards 来自包括 ESConv、ExTES 在内的公开数据；若 generator SFT 使用这些来源，必须先冻结测试身份并做 source/dialogue/semantic overlap；
- EvoEmo/ES-MemEval 不得同时被当作两个独立人群；
- ES-MemEval answer/evidence gold 不进入 response PM 训练；
- 外部结果不得用于选择 generator、threshold、sample 或 baseline；
- public benchmark 预训练污染无法完全排除，必须披露，并优先依靠同栈 reference 和受控 PM contrasts。
