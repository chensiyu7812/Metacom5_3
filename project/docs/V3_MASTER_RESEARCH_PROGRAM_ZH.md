# MetaCom V3 总研究方案：从有效历史证据到可审计的最终主张

日期：2026-08-13
状态：`ACTIVE V3 MASTER PLAN / NO API EXECUTION AUTHORITY`

机器权威：

- `data/v3_authority/v3_research_authority_v1.json`
- `data/v3_authority/v3_asset_compatibility_manifest_v1.json`
- `data/v3_authority/v3_evaluation_freeze_contract_v1.json`

## 当前最高优先级：先冻结判卷规则

V3-P0 完成前，禁止新增 head 调参、selector refit、正式 judge、generator 微调或正式外测通过声明。原因不是保守，而是当前还没有完整回答五个先验问题：数据是哪一版、考卷测什么、及格线从哪里来、独立统计单位是什么、结果允许支持哪条主张。

当前四张结构化 dataset card 已建立，P0九门已有五门完成，但尚未整体通过：

- ESConv 的 commit、文件哈希、1,300 个 dialogue 与 38,365 个 turn 已核验；
- EvoEmo/ES-MemEval 公开 `v1.0.0` tag 和 `evo_emo.json` 哈希已核验；
- 正式论文是 1,209 道 QA，公开 `v1.0.0` 文件实际是 1,427 道，差异 218 道且覆盖五种 capability；
- ESC-Eval/ESC-Judge 本地零调用协议已物化（655卡、25/100角色、150个双向E-I-A单元）；228张ESConv/ExTES同源卡的全文源比对和语义邻居也已冻结；
- scorer校准、same-stack reference、pass margin和Risk双人fixture资格仍未完成。

因此，现在可以做的是版本对齐、scorer 资格设计、重叠筛查和 Risk adjudication；不能再用同一批内部样本迭代一个自建总分来宣布“学会/没学会”。

## 结论先行

V3 不再把“继续修 head”“继续打一个 Quality/Risk 分数”和“跑外部数据”混成一条循环。研究拆成四层证据：

1. **Generator 资格**：ESC-Eval 为主，ESC-Judge 为稳健性；回答执行器是否具备基本情绪支持能力。
2. **长期记忆能力**：ES-MemEval；回答信息提取、时间、冲突、拒答和用户建模能力。
3. **PM 因果价值**：同状态、同 generator、同候选和同执行栈的 baseline 矩阵；回答 learned policy 是否比固定、规则和匹配随机策略更会选。
4. **个性化完整性**：原子化 source-aware Risk；回答是否发生错人、过期升级、冲突误用或敏感信息无关暴露。

第一篇论文的目标保持为：

```text
RS_pass
AND count_pass(MP, MS, ME) >= 2
AND generator qualified
AND ESConv track pass
AND EvoEmo track pass
AND ES-MemEval track pass
```

最快目标组合是 `RS + MP + MS`。ME 不删除，但在前三个 head、generator 和三条外测主链稳定前不抢占关键路径。

## 当前真正拥有的东西

### 可直接使用

- 当前 commit `ef318c3` 的代码、脚本、配置、合同、公开 ESConv/EvoEmo 数据和测试历史；
- V4 `R0 + component delta` compiler；
- MS `USE / ASK / IGNORE` pre-decision，IGNORE 资源物理缺席；
- source-aware 六维 Risk reviewer；
- MP profile-delta 模板与 plan-first 修复基础；
- 已完成的 42/90 外部语料 stress-test 回复和冻结的 48-call continuation preflight；
- 当前 MS/MP V1.1 原始生成与盲评输出，作为开发失败归因证据。

### 可以使用，但必须改变解释

- 旧 RS 失败证明旧 replacement/restatement treatment 不成立，不能证明 additive RS 永远无效；
- MS/MP V1.1 证明候选与 executor 接口仍不足，不是风险失败，也不是正式 head verdict；
- V5.2 ES-MemEval 结果只能是旧 stack 的客观诊断，不能确认 V3；
- Function 只能是机制证据，不能让一个难以稳定识别的主观判断单独否决同状态正向 Quality/Risk/Cost 结果。

### 不能直接使用

- 旧 `paper1_active_execution_bundle_v1.json` 作为 V3 唯一 authority：它引用大量未提交的历史输出并混合已消费阶段；
- 全部旧 pytest 作为 clean-clone release gate：大量测试读取已经消费或失效的人评包；
- snap 下的 5.2GB editable venv 作为可移植环境：其中 `.pth` 指向旧 snap 源码；
- 失败、空白、方法失效的人评包作为证据；
- ES-MemEval “1209 / 1427 / 418”差异保留为版本边界；V3主任务已冻结为可复现的`ES-MemEval-Public-v1.0.0-1427`，不声称精确复现论文1209题。

## 当前科学状态

| Head / 系统 | 当前结果 | 正确解释 | 下一步 |
|---|---|---|---|
| RS | 旧 treatment 下 baseline 近乎全面获胜 | replacement treatment 失败；additive V4 尚未被外测裁定 | 完成 V4 外部 stress diagnostic，估计 full-minus-RS |
| MS | V1.1 Quality 1胜3负2平；Risk 安全；Function 0/6 | 候选“新颖”不等于对当前 response plan 有增量，executor 也可忽略 | 用 P1 外部边际结果决定是否做 response-plan-relevant USE/ASK 修复 |
| MP | V1.1 Quality 5胜1负1平；Risk 安全；Function 0/5 | 通用职业/教育事实没有改变一个具体 slot | 固定 R0 plan 后，只允许可修改建议、时间、格式、物流的 constraint |
| ME | 尚未重建为可靠第一版 head | 不影响先完成 RS+MP+MS 组合 | 主链成功后有界救援 |
| Generator | Llama 3.1 8B 已用于大量诊断 | 尚无公认 ESC benchmark 资格 | ESC-Eval 主测 + ESC-Judge 稳健性 + evidence-conditioned executor test |
| 外部 stress test | 42/90 完成；48 个 429 | arm 不完整，禁止任何科学比较 | 经新批准后仅补 48 个缺失调用 |

## 评价体系

### Generator 及格

不能直接把 ESC-Eval 论文中 Llama3-8B 的公开分数当作当前 Llama 3.1 8B 的硬线。正式做法是：

- pin 官方代码 commit、role-card identity、ESC-Role/ESC-RANK identity、turn cap、prompt、sampling 和 scorer；
- 本地复核 scorer 在公开人工标注上的可用性；
- 在同一执行栈中运行一个冻结 reference；
- 用 role-card/dialogue 聚类区间定义 noninferiority，而不是拍脑袋定 60/70 分；
- 完整报告七维，特别防止 suggestion 数量奖励掩盖低负担支持原则；
- ESC-Judge 只作 E-I-A 成对稳健性分析，不取代绝对能力定位。

Generator 资格不证明 PM。有必要时另做 executor realization：给定 current context、已经批准的 response plan 和 evidence，只检查生成器是否自然、准确地执行，不允许它重新决定资源开关。

### PM 及格

| Comparator | 必须证明的价值 |
|---|---|
| always-off | 可选资源整体不伤 Quality/Risk；learned-ON slice 有正向价值 |
| fixed-high | Quality/Risk 非劣，实际 generator input tokens 至少低 10% |
| transparent rule | learned model 不只是复杂化；至少一项预注册 selection outcome 严格更好 |
| cost-matched fixed | 不是同成本固定 bundle 就能解释 |
| cost/ON-rate-matched random | 不是只因为少开或开启率相同；state-action 匹配真正有用 |
| full-minus-component | 每个计入成功的 head 具有独立边际贡献，不能搭便车 |
| safe oracle frontier | joint action 无结构非法，regret 与 excess cost 在冻结区间内 |

Quality、Risk、Function、Cost 不合成一个总分。Function 作为 mechanism support；主要 estimand 是 same-state deployment-ITT。

### Risk 及格

Risk 取消单一 1–5 印象分，记录以下事件：

- wrong owner/entity；
- future exposure；
- past-to-current upgrade；
- stale/conflict misuse；
- fabricated personal history；
- irrelevant sensitive exposure；
- explicit boundary violation；
- internal scaffold exposure；
- uncertain。

每项按 reply、exposure 和 owner 三种分母报告。Critical 事件逐案披露；`UNCERTAIN` 不强行归入“无风险”。该审计只支持 personalized-memory integrity，不支持临床安全主张。

## 三项正式外测

### ESConv：RS 单会话

- MP/MS/ME 结构性 OFF；
- 比 always-off、fixed-high、transparent rule、cost-matched 和 matched random；
- 整体 Quality/Risk 非劣，ON slice 正向；
- learned selection 严格优于至少一个非学习对手；
- wrong-owner/future/scaffold 为 0。

### EvoEmo：纵向响应与联合系统

- 统计单位是 18 个 user，不是 state 数；
- 比 always-off、fixed-high、rule、matched controls、RS-only、component fixed、full-minus-component、raw-session RAG、full history、safe oracle；
- RS 及至少两个 memory heads 各自有安全的边际价值；
- 联合 policy 的 adaptive value 和 interaction 风险均通过。

### ES-MemEval：长期记忆能力

- 使用已冻结的`ES-MemEval-Public-v1.0.0-1427`逐题身份；历史418只作诊断，论文1209只作不可精确复现的文献边界；
- 条件为 no-memory、full history、official session-RAG Top4、typed fixed-high、typed learned PM；
- answerable memory-required QA 优于 no-memory；
- 相对 fixed-high 准确性/false-answer/abstention 非劣且 input tokens 至少低 10%；
- extraction、temporal、conflict、user modeling、abstention 分别报告；
- EvoEmo 与 ES-MemEval 同源 18 users，禁止称两个独立人群复现。

## Generator 微调决策

```text
ESC-Eval 不合格
  -> leakage-screened、train-only ESC execution SFT

ESC-Eval 合格，但 evidence-conditioned realization 不合格
  -> 只微调给定 plan/evidence 的执行能力

两者都合格，但 PM 结果差
  -> 修 candidate / treatment / selector，不改 generator

两者都合格且 PM 成功
  -> 冻结；需要 generator-agnostic 主张时才加一个强 generator replication
```

训练 generator 前必须冻结 benchmark test identity，并对 ESConv、ExTES、ESC-Eval role-card 来源做 source/dialogue/semantic overlap screening。所有 PM 与 baseline arm 使用同一个冻结 generator。

## 最短落地顺序

1. **V3-P0：完成评测冻结。** 对齐四个 dataset card、ES-MemEval 版本、ESC scorer/reference、Risk adjudication、primary outcomes、NI margin 和 active test profile；未通过前不调 head。
2. **V3-P1：完成当前外部诊断。** 只补冻结的 48 个缺失调用；不更改 prompt/seed/arm；完成后按 Quality/Risk/Cost 主指标和 Function 次指标闭环。
3. **V3-P2：Generator 资格。** ESC-Eval 主测、ESC-Judge 稳健性、executor realization；决定是否需要执行型 SFT。
4. **V3-P3：只修真正失败的 treatment。** 避免再做大而泛的内部循环。
5. **V3-P4：selector 与 baseline 一次冻结。** 只有固定 treatment 有用后才学 selector。
6. **V3-P5：三项正式外测。** 分轨、分簇、不可替代、不可池化。
7. **V3-P6：强 generator 与 ME。** 只扩展已经成立的主张，不用于救失败结果。

## 成功与诚实失败

V3 的目标仍是得到有意义且符合主张的正面结果，但不能保证自然数据一定支持它。可以保证的是：

- 不再让 generator 缺陷、PM treatment、selector 和 judge 模糊地互相背锅；
- 每次失败都定位到数据、执行器、resource delta、selector 或 measurement；
- 通过线在 outcome 前冻结；
- 正面结果能经得住 baseline、版本、统计单位和泄漏审查；
- 如果完整主张未成立，也能产出清晰的条件性价值与失败边界，而不是一堆无法解释的人评分数。
