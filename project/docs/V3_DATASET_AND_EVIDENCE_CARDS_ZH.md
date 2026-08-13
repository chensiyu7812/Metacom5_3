# MetaCom V3 数据集与证据卡

日期：2026-08-13
状态：`ACTIVE P0 AUDIT`

结构化卡片：

- `data/v3_authority/dataset_cards/esconv_dataset_card_v1.json`
- `data/v3_authority/dataset_cards/evoemo_dataset_card_v1.json`
- `data/v3_authority/dataset_cards/es_memeval_dataset_card_v1.json`
- `data/v3_authority/dataset_cards/esc_eval_dataset_card_v1.json`

| 数据源 | 来源与性质 | 主要单位 | 允许检验 | 关键风险 | 当前状态 |
|---|---|---|---|---|---|
| ESConv | 人工众包、单会话、带支持策略标签 | dialogue | RS、即时支持 | ESC-Eval role cards 可能同源；无纵向 owner | 可用；只进 RS track |
| EvoEmo | GPT 生成并人工多阶段复核的合成长程数据 | 18 users / 401 sessions | longitudinal response、RS/MP/MS/ME | 合成、N=18、与ES-MemEval同源 | 可用；按user聚类 |
| ES-MemEval | WWW 2026；由 EvoEmo 构造 QA/summary/generation | 18 users | extraction、temporal、conflict、abstention、user modeling | 1209/1427/418版本不一致 | 阻塞正式运行，先对齐 |
| ESC-Eval | EMNLP 2024；655张角色卡，来自7个数据源并用模拟用户交互 | role card/dialogue | generator多轮ESC能力 | GPT-4抽卡、模拟用户、与ESConv/ExTES重叠、rubric偏好建议数量 | 候选主资格考卷 |
| ESC-Judge | EMNLP 2025；合成角色、E-I-A理论、成对自动judge | synthetic role | generator相对支持策略 | 小角色集、judge依赖、非绝对分数 | robustness候选 |
| 内部P2R/开发panel | 项目自建、outcome-blind或开发消费 | owner/group | treatment/selector开发 | 不能叫外部、不能从结果扩样 | development only |

## ES-MemEval 版本对齐任务

2026-08-13 的官方仓库实查已经把“可能不一致”升级为“确定不一致”：GitHub `v1.0.0` tag 指向 commit `6926242`，其中 `data/evo_emo.json` SHA-256 为 `f30698e8...d420`，实际包含18 users、401 sessions、1,427 QA、125 summaries、34 generation scenarios；WWW 2026正式论文则报告1,209 QA，其他三个总数一致。

五类 QA 的公开文件/正式论文差异依次为：IE 309/271、TR 284/236、CD 267/226、UM 306/251、Abstention 261/225，总计多218道。仅凭计数无法知道正式论文删掉了哪218道，因此正式 V3 当前仍阻塞。机器审计见 `data/v3_authority/es_memeval_repository_reconciliation_v1.json`。

必须产生一个逐文件、逐题的 reconciliation artifact：

- WWW 2026 paper：1209 QA；
- 官方公开 `v1.0.0` artifact：1,427 questions；
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
