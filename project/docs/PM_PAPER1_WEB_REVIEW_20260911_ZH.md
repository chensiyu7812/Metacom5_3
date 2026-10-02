# Paper-1 网页版审阅入口（2026-09-11）

> 历史快照：人评与 Gemini 的最新收口、Summary 编码修复和后续候选提案见 [2026-09-17 审阅入口](PM_PAPER1_WEB_REVIEW_20260917_ZH.md)。下文的待评状态和零 Gemini 调用属于当日记录。

本页集中呈现当前研究方案、本轮人评 V2、全过程审计和自动裁判选型调研，供研究负责人交给网页版继续分析。当前工作位于 `work/paper1-rq1-integration-20260816` 分支及 [PR #3](https://github.com/chensiyu7812/Metacom5_3/pull/3)，请读取该分支，不要仅根据 `main` 判断最新状态。

这次发布不启动研究实验，不修改已有评分，也不批准新增裁判。工程核验通过不等于 PM 效果已经成立。

## 建议阅读顺序

1. [仓库研究约束与修订优先级](../../AGENTS.md)、[当前配置](../configs/paper1_public_only.yaml)、[执行清单](PM_PAPER1_EXECUTION_CHECKLIST_20260903_ZH.md)。
2. [完整研究方案及主张](PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md)、[二元实质收益与预算修订](PM_PAPER1_BINARY_BENEFIT_SCOPE_AND_API_BUDGET_AMENDMENT_20260903_ZH.md)、[当前 Pre-Effect 方案](PM_PAPER1_PRE_EFFECT_STABILIZATION_20260904_ZH.md)。8 月方案须按后续条款的明确覆盖范围解读。
3. [研究过程审计与后续推进](reviews/20260907/研究审计与后续推进.md)、[V1 人评开评前检查](reviews/20260907/人评卷开评前检查.md)。两篇保留当日发现，需结合下面的修复状态阅读。
4. [已授权的 V2 修订](PM_PAPER1_HUMAN_REFERENCE_V2_AMENDMENT_20260908_ZH.md)、[V2 人评交付说明](PM_PAPER1_HUMAN_REFERENCE_V2_HANDOFF_20260908_ZH.md)、[交付核验报告](reviews/20260908/新版人评卷交付核验.md)。
5. [自动裁判选型调研与建议](reviews/20260911/自动裁判选型调研与建议.md)、[三个候选的逐题输入长度预检](reviews/20260911/context_length_preview.json)、[模型版本及配置摘要](reviews/20260911/sources/candidate_metadata_summary.json)。候选优先级来自公开证据与接口适配分析，还没有本项目准确率结果。

## 研究要回答什么

Policy Manager 的四个 L2 logistic heads 分别学习：在冻结生成栈下，打开 RS 策略资源、MP 当前稳定画像、ME 严格过去原子事件/经历、MS 完整过去会话，是否有 task-defined material positive effect。训练一个头的 ON/OFF 对照时，其余 optional resources 全 OFF；成本不进入质量标签。

RQ1 使用 ESConv 资源，在 ESC-Eval 验证策略资源选择；RQ2 使用公开 ES-MemEval/EvoEmo，在官方 QA、Summary、DG 任务验证记忆选择。正式能力结论采用各自官方指标；Matched-Random、Fixed-High、相同生成栈、资源量与实际客户端延迟共同支持选择是否有价值的判断。当前四头不预测逐请求收益幅度，也不学习动态 top-k 或头间交互。

## 当前已有结果及其边界

| 项目 | 已记录状态 | 解读限制 |
|---|---|---|
| DG seeker | 新增 8/8 次 GPT-4o 调用成功，usage 按冻结费率计 $0.1013300 | 不是模拟器总体成功率证明 |
| 本地生成 | 142/142 个非空输出，额外 API 费用 $0 | 28 个触达输出长度上限，影响 26/80 个基础 pair；保留原输出 |
| Teacher 人评 | 80 基础 pair + 16 反序；两位评审各 96 题 | 192 是主评次数，不是独立样本量；DG 基础 pair 共享 9 个情境 |
| V2 | 原 142 条回复、题目及题序保持，DG 增加完整严格过去历史 | 是评审证据修订，不是新生成或 PM 效果结果 |
| 当前费用基线 | Paper-1 已记账 $1.44178151；$50 硬上限下剩余 $48.55821849 | 含失败/未知调用的保守记账，不等于全量发票已核销；完整后续预算尚未闭合 |
| 正式研究 | Gemini teacher 调用 0，formal outcome 0，PM training 0；四把锁 CLOSED | 真正 amount/top-k、正式标签及最终效果均未完成 |

上述运行与费用来自已存审计和生成工件。本次仅发布文件，新增模型调用与 API 费用均为 0。未读取或汇总任何后来提交的人评答案；空白卷交付不代表人評已经完成。

## 审计问题目前如何处理

| 问题 | 截至本次发布的状态 |
|---|---|
| V1 DG 仅展示部分历史，无法覆盖允许使用的全部证据 | 已由获授权 V2 修订；两位主评与 teacher 使用相同完整过去历史，保留原相关摘录；63 个候选来源实例覆盖核验通过 |
| JSON 重复键静默覆盖 verdict | 已修复严格解析；人评导入也拒绝重复键和原题篡改 |
| 入口与当前人评版本漂移 | README、AGENTS、配置及执行清单已指向 V2 / qualification plan V3 |
| Summary equivalent 的部分路径编码为 uncertain | 尚未修复；正式 effect labels 前须按现行契约修复及回归核验 |
| Teacher 记忆目标与未来 outer evaluation 重叠 | 隔离决策待冻结；35 个目标所属 35 个 exact-evidence components 展开涉及 97 targets；调整主分析人口仍是未批准提案 |
| 完整 DG / 后续阶段预算闭合 | 尚待 exact call manifest 重算；不能用旧 $22 envelope 或硬上限保护代替完整可执行预算 |
| 输出长度触顶、p95 相加缺乏一般上界保证 | 已披露；保留真实输出，正式延迟结论需实际 client E2E 数据 |
| 专用本地裁判替代或补充 Gemini | Selene Mini 8B、CompassJudger-2 7B 为优先试验建议，M-Prometheus 14B 备选；新增候选尚未授权、适配或实测 |

## 人评与裁判的用途

本轮人评提供裁判资格审查的测量参照。两位主评独立完成并封存后，先统计原始一致性和反序稳定性，再按已预定共识流程另列处理分歧；共识先于查看 Gemini 判定封存。这些评分不直接用于 PM 训练，也不替代另行设计的 natural-turn appropriateness 人评。

当前研究契约仍以 Gemini 等已允许的候选家族为准。调研建议先使用现成专用权重和四类 rubric 适配，并不建议用现有 80 个基础 pair 微调后再在同卷宣称独立准确率。Selene/Compass 的二选一模板、equivalent/uncertain 区分及长 DG 历史都需要验证。模型架构能容纳输入不代表长历史判断准确。

后续依次完成：原始人评与共识封存、测量开发和验证的隔离决策、单独授权的 teacher qualification、真正 RS/MP/ME/MS amount/top-k/cap calibration、最终 `k*`/容量及全栈与折分冻结、正式 effect labels、四头 PM 训练与官方评测。当前 `k∈{1,2,4}` 只是资格样本的资源量覆盖。

## 可检查的实现与证据

- [人评四类定义和逐任务规则](../data/paper1_authority/paper1_pairwise_teacher_human_instrument_20260908_v2.json)、[双评与共识设计](../data/paper1_authority/paper1_pairwise_teacher_human_reference_design_20260908_v2.json)、[资格审查计划 V3](../data/paper1_authority/paper1_pairwise_teacher_qualification_plan_v3.json)。
- [V2 制卷与离线核验](../scripts/paper1/61_materialize_human_reference_v2.py)、[答卷完整性接收 CLI](../scripts/paper1/62_validate_human_reference_v2_submission.py)、[参考与提交校验实现](../src/metacom_pm/paper1/evaluation/human_reference.py)、[离线表单 HTML](../src/metacom_pm/paper1/evaluation/human_reference_form.html)、[表单交互 JS](../src/metacom_pm/paper1/evaluation/human_reference_form.js)。
- [表单、源数据与 teacher 请求哈希清单](../data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json)、[V2 回归测试](../tests/test_paper1_human_reference_v2.py)。
- [2026-09-07 独立审计机器证据](reviews/20260907/evidence.json)、[V1 人评覆盖证据](reviews/20260907/human_sheet_readiness_evidence.json)、[V2 浏览器检查 33 项](reviews/20260908/browser_qa.json)、[分发包检查 28 项](reviews/20260908/package_qa.json)、[V2 集成检查 32 项](reviews/20260908/integration_validation.json)。V2 交付时的非 GPU Paper-1 suite 为 817 项通过。
- [发布来源与哈希清单](reviews/publication_manifest_20260911.json)记录哪些副本与原审计逐字节一致，哪些 Markdown 仅增加了发布说明和仓库内链接。历史脚本保留原环境路径和依赖，属于核验溯源，不应直接当作全新 clone 的即用命令。

按照 [.gitignore](../../.gitignore) 的产物规则，原始问卷正文、分发 HTML/ZIP、已填答卷、coordinator 请求、API 原始日志和缓存保持本地。GitHub 包含完整规则、表单源代码、装配过程、无回答文本的来源/哈希清单和审计统计；只凭 GitHub 不能逐题重做人类语义判断。第三方全文和分词器缓存也未复制入库，模型卡及论文链接、固定版本、分词器哈希已列入调研证据。

## 可直接交给网页版的审阅要求

> 请以本分支 AGENTS.md 的当前研究契约和修订优先级为准，先掌握研究目的、主张、RQ1/RQ2、四头标签与官方评测分工，再检查人评 V2 和自动裁判选型。区分已修复问题、当前未完成问题、未授权提案及已取得的实测结果。重点分析：本轮人评能识别什么；四类裁判是否匹配 material benefit；长历史和教师选型是否引入偏差；teacher 与最终验证如何隔离；Summary 编码与全流程预算还需哪些修复。请给出逐项有来源的意见，不把工程 PASS、模型卡排名或输入长度预检当作 PM 有效或裁判准确率证据，也不把当前资源量探测当作最终 top-k。
