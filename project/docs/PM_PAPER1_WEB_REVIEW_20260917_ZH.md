# Paper-1 网页版审阅入口（2026-09-17）

当前工作在 `work/paper1-rq1-integration-20260816` 分支、[PR #3](https://github.com/chensiyu7812/Metacom5_3/pull/3)。请读该分支最新版本，并按 [AGENTS.md](../../AGENTS.md) 解释历史合同的修订优先级。本文更新进展，不授权新实验。

## 最新变化

| 项目 | 已完成内容 |
|---|---|
| 人评与复核 | A 原始联合人评、探索性 AI B、六题复核和用户更正均已收口；保留原始文件，敏感性视图分别统计 |
| Gemini 资格测试 | 96/96 呈现完成尝试，100 次物理调用，92 个严格解析成功，4 个最终解析失败；不提升为正式 teacher |
| 主要测量发现 | 原始 A 对照 7/77 base 同判；49/54 个人评 equivalent 被判成明确胜负；反序 8/13 一致，另 3 组缺失 |
| 费用 | 本批保守记账 $0.0654614；累计 $1.50724291，余额 $48.49275709；未结算 reservation 为 0 |
| 实现修复 | Summary 的合格 pairwise equivalent 优先于连续指标方向；不覆盖机械无效和参考事件清单冲突；已加入回归测试 |
| 本地裁判提案 | Selene Mini 8B、CompassJudger-2 7B 的固定版本及 320 条请求完成准备；没有新候选推理，提案未获执行授权 |
| 正式研究 | formal outcome 0，PM training 0，四把 outcome lock CLOSED；真正 amount/top-k calibration 尚未完成 |

上述 7/77 是与当前参考的同判率，不是独立金标准准确率；旧 A 也包含已复核的事实问题。原始 A 的 80 个 base 中，始终判 equivalent 可得 56/80 = 70% 同判率，因此不能按总一致率单独挑裁判。Gemini 的 4 个失败均因理由超出原冻结 600 字符解析上限；本批没有事后放宽规则。

## 建议阅读顺序

1. [完整研究方案](PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md)、[二元实质收益与预算修订](PM_PAPER1_BINARY_BENEFIT_SCOPE_AND_API_BUDGET_AMENDMENT_20260903_ZH.md)、[当前配置](../configs/paper1_public_only.yaml)、[执行清单](PM_PAPER1_EXECUTION_CHECKLIST_20260903_ZH.md)。PM 的目标仍是四个资源 head 的 task-defined material-benefit 选择，最终能力主张由官方指标支持。
2. [人评复核收口](PM_PAPER1_HUMAN_REVIEW_CLOSEOUT_20260917_ZH.md)及其[机器记录](../data/paper1_authority/paper1_human_review_closeout_20260917_v1.json)。实际来源、六题处理和用户关于 A3 的更正均在这里。
3. [Gemini 资格结果与后续边界](PM_PAPER1_GEMINI_QUALIFICATION_RESULTS_20260917_ZH.md)、[执行授权说明](PM_PAPER1_GEMINI_QUALIFICATION_APPROVAL_20260917_ZH.md)、[结果机器收口](../data/paper1_authority/paper1_gemini_qualification_closeout_20260917_v1.json)。首题用量修复有独立记录，不能据请求 thinkingBudget=0 声称实测零 thinking。
4. [可公开复算的比较统计](reviews/20260917/qualification_statistics.json)：保留原始 A、六题覆盖、助手事实敏感性三种视图，混淆矩阵、各任务类别召回、换序和分组区间；不含题面、原始答卷理由或 API 响应正文。
5. [本地两候选提案](PM_PAPER1_LOCAL_TEACHER_COMPARISON_PROPOSAL_20260917_ZH.md)、[提案绑定](../data/paper1_authority/paper1_local_teacher_comparison_proposal_20260917_v1.json)、[原始选型调研](reviews/20260911/自动裁判选型调研与建议.md)。两名候选是待检验建议，不能写成已知最佳模型。用户最新要求是进一步分析最适合任务的能力与候选范围。
6. [最新候选能力与任务适配分析](reviews/20260917/裁判候选能力与任务适配分析.md)、[12 个模型的版本和配置来源](reviews/20260917/candidate_capability_metadata.json)。建议把通用推理模型纳入比较，区分文献能力、长文配置与本项目实测；对原两模型方案的扩展仍为未授权提案。

## 可检查的实现

- [人评 intake 和复核收口](../scripts/paper1/63_prepare_teacher_review_closeout.py)。
- [预算受控的 Gemini 执行器](../scripts/paper1/64_run_gemini_teacher_qualification.py)、[transport 与计费实现](../src/metacom_pm/paper1/evaluation/gemini_teacher.py)、[执行器回归](../tests/test_paper1_gemini_teacher.py)。
- [离线审计入口](../scripts/paper1/65_audit_gemini_teacher_qualification.py)、[统计与换序诊断](../src/metacom_pm/paper1/evaluation/teacher_diagnostics.py)、[诊断测试](../tests/test_paper1_teacher_diagnostics.py)。
- [Summary 编码实现](../src/metacom_pm/paper1/evaluation/effect_coding.py)、[对应回归测试](../tests/test_paper1_effect_coding.py)。
- [本地候选请求准备](../scripts/paper1/66_prepare_local_teacher_comparison.py)：仅获取公开配置与 tokenizer，不下载权重、不推理。
- [发布来源与校验清单](reviews/20260917/publication_manifest.json)。原始工件哈希供本地复核，不意味着公开仓库包含原始工件。

## 仍需处理的工作

首先判断裁判是否能依据完整历史、事实与任务目标区分实质收益、相当和不确定，而不是只学习表达偏好。复用已有参考开展有限适用性研究；不把同卷提示搜索或微调后的成绩称为独立验证。原有 teacher 与后续 outer evaluation 的隔离决策、完整后续预算闭合仍须处理，详见 [9 月 11 日问题清单](PM_PAPER1_WEB_REVIEW_20260911_ZH.md)。

之后在相应批准下完成真正的 RS/MP/ME/MS amount/top-k 和容量校准，冻结各 head 的 `k*`、完整生成与评分栈、特征和折分，再生成正式 effect labels 并训练四个 L2 head。没有合格 pairwise 确认时，Summary/DG 的连续指标微差不能直接充当 material-benefit 标签；uncertain 不能填成 0。

此次发布遵循已有产物规则：GitHub 收录新代码、研究记录、提案、公开聚合统计和来源哈希；完整题面、已填答卷、API 缓存、账本与模型请求正文仍保存在本地。网页版可审计方法与统计，但仅凭公开文件不能逐题重做语义判定。
