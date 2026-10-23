# Paper-1 网页版审阅入口（2026-09-17）

当前工作在 `work/paper1-rq1-integration-20260816` 分支、[PR #3](https://github.com/chensiyu7812/Metacom5_3/pull/3)。请读该分支最新版本，并按 [AGENTS.md](../../AGENTS.md) 解释历史合同的修订优先级。本文更新进展，不授权新实验。

本轮本地开发结果已写入工作区，尚未提交或推送；GitHub 的 `ba69170` 不包含本轮新增结果。

## 最新变化

| 项目 | 已完成内容 |
|---|---|
| 裁判研究保留 | 已写成探索性测量分析与结果段落，输出 PNG／PDF／SVG 图、CSV 表及来源记录；RQ1／RQ2 主体保持不变 |
| 具体校准准备 | 85 QA＋63 Summary，18 owners／5 folds，1,924 条生成请求、2,220 行分析映射；官方评分模板逐字核对，等待本地生成后填入 prediction |
| 人评与复核 | A 原始联合人评、探索性 AI B、六题复核和用户更正均已收口；保留原始文件，敏感性视图分别统计 |
| Gemini 资格测试 | 96/96 呈现完成尝试，100 次物理调用，92 个严格解析成功，4 个最终解析失败；不提升为正式 teacher |
| 主要测量发现 | 原始 A 对照 7/77 base 同判；49/54 个人评 equivalent 被判成明确胜负；反序 8/13 一致，另 3 组缺失 |
| 费用 | 本批保守记账 $0.0654614；累计 $1.50724291，余额 $48.49275709；未结算 reservation 为 0 |
| 实现修复 | Summary 的合格 pairwise equivalent 优先于连续指标方向；不覆盖机械无效和参考事件清单冲突；已加入回归测试 |
| 本地裁判执行 | 三款共 480 条已完成；Qwen 换序 70/80、Compass 55/80、Selene JSON 11/80；Selene 先理由后结论另 160 条，换序 48/77、3 对缺失 |
| 完整历史诊断 | Summary 三配置各 52 条、共 156 条全部自然结束；原短摘要确有事实遗漏，完整历史修正了部分错误理由，但不保证全部判断正确 |
| 本轮用途与消耗 | Qwen 优先作本地开发／事实核查，Compass 作补充；未提升自动全任务收益标注。计划内 822 条已处理、821 正常停止、1 循环超时；保守生成墙钟 3.02 小时，API 增量 $0 |
| 自然结束 | 原 26 个 Summary 请求全部自然停止；12 条旧截断均消除、14 条旧正常回复逐字保持；事实错误仍单独评估 |
| 开发方式与 top-k | 允许读题、复用和有记录的开发调整；已物化 20,176 条静态 top-k 全量候选配置用于盘点，尚未选择付费校准样本或 k* |
| 正式研究 | formal outcome 0，PM training 0，四把 outcome lock CLOSED；真正 amount/top-k calibration 尚未完成 |

上述 7/77 是 Gemini 原严格解析视图下与原始 A 的同判率，不是独立金标准准确率；旧 A 也包含已复核的事实问题。原始 A 的 80 个 base 中，始终判 equivalent 可得 56/80 = 70% 同判率，因此不能按总一致率单独挑裁判。Gemini 的 4 个失败均因理由超出原冻结 600 字符解析上限；原执行记录不改写。本轮零调用重解析敏感性恢复了 4 条可读判决，得到原始 A 7/80 同判、旧 16 对反序 10/16 一致，仍不足以改变用途结论。

## 建议阅读顺序

1. [完整研究方案](PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md)、[二元实质收益与预算修订](PM_PAPER1_BINARY_BENEFIT_SCOPE_AND_API_BUDGET_AMENDMENT_20260903_ZH.md)、[当前配置](../configs/paper1_public_only.yaml)、[执行清单](PM_PAPER1_EXECUTION_CHECKLIST_20260903_ZH.md)。PM 的目标仍是四个资源 head 的 task-defined material-benefit 选择，最终能力主张由官方指标支持。
2. [人评复核收口](PM_PAPER1_HUMAN_REVIEW_CLOSEOUT_20260917_ZH.md)及其[机器记录](../data/paper1_authority/paper1_human_review_closeout_20260917_v1.json)。实际来源、六题处理和用户关于 A3 的更正均在这里。
3. [Gemini 资格结果与后续边界](PM_PAPER1_GEMINI_QUALIFICATION_RESULTS_20260917_ZH.md)、[执行授权说明](PM_PAPER1_GEMINI_QUALIFICATION_APPROVAL_20260917_ZH.md)、[结果机器收口](../data/paper1_authority/paper1_gemini_qualification_closeout_20260917_v1.json)。首题用量修复有独立记录，不能据请求 thinkingBudget=0 声称实测零 thinking。
4. [可公开复算的比较统计](reviews/20260917/qualification_statistics.json)：保留原始 A、六题覆盖、助手事实敏感性三种视图，混淆矩阵、各任务类别召回、换序和分组区间；不含题面、原始答卷理由或 API 响应正文。
5. [原本地两候选提案](PM_PAPER1_LOCAL_TEACHER_COMPARISON_PROPOSAL_20260917_ZH.md)、[候选能力与任务适配分析](reviews/20260917/裁判候选能力与任务适配分析.md)、[12 个模型的版本和配置来源](reviews/20260917/candidate_capability_metadata.json)。这些文献判断不能写成实测能力排名。
6. [当前三候选／务实开发／自然结束执行记录](PM_PAPER1_PRACTICAL_DEVELOPMENT_AND_NATURAL_END_20260917_ZH.md)、[Summary 实测](PM_PAPER1_SUMMARY_NATURAL_END_RESULTS_20260917_ZH.md)、[top-k 准备](PM_PAPER1_TOPK_PREPARATION_20260917_ZH.md)。该范围已获研究者授权。
7. **本轮新增结果**：[本地裁判比较与用途结论](PM_PAPER1_LOCAL_TEACHER_DEVELOPMENT_RESULTS_20260917_ZH.md)、[Summary 完整历史对照](PM_PAPER1_SUMMARY_SOURCE_EVIDENCE_DIAGNOSTIC_20260917_ZH.md)、[模型聚合统计](reviews/20260917/local_teacher_comparison_statistics.json)、[执行记录](reviews/20260917/local_teacher_execution_summary.json)、[机器收口](../data/paper1_authority/paper1_local_teacher_development_closeout_20260917_v1.json)。完整逐题 HTML／CSV 与原始输出随本地结果包提供。
8. **研究者要求继续推进后的新增产物**：[裁判测量研究稿](PM_PAPER1_JUDGE_MEASUREMENT_STUDY_20260917_ZH.md)、[具体校准包](PM_PAPER1_STATIC_AMOUNT_CALIBRATION_PACKAGE_20260917_ZH.md)、[准备汇总](reviews/20260917/static_amount_calibration_preparation.json)。A6000 被其他项目占用，尚未启动新生成；新 API $0。费用情景不等于全批保证价，拟议 $15 评分阶段尚未授权。

## 可检查的实现

- [人评 intake 和复核收口](../scripts/paper1/63_prepare_teacher_review_closeout.py)。
- [预算受控的 Gemini 执行器](../scripts/paper1/64_run_gemini_teacher_qualification.py)、[transport 与计费实现](../src/metacom_pm/paper1/evaluation/gemini_teacher.py)、[执行器回归](../tests/test_paper1_gemini_teacher.py)。
- [离线审计入口](../scripts/paper1/65_audit_gemini_teacher_qualification.py)、[统计与换序诊断](../src/metacom_pm/paper1/evaluation/teacher_diagnostics.py)、[诊断测试](../tests/test_paper1_teacher_diagnostics.py)。
- [Summary 编码实现](../src/metacom_pm/paper1/evaluation/effect_coding.py)、[对应回归测试](../tests/test_paper1_effect_coding.py)。
- [本地候选请求准备](../scripts/paper1/66_prepare_local_teacher_comparison.py)：仅获取公开配置与 tokenizer，不下载权重、不推理。
- [发布来源与校验清单](reviews/20260917/publication_manifest.json)。原始工件哈希供本地复核，不意味着公开仓库包含原始工件。

## 仍需处理的工作

本轮比较已完成，主要未解问题是实质差异判定，不能用换序一致或更贴人评代替。Qwen 为后续本地开发首选，Compass 是补充；不继续无限增加小模型名单。现有参考可以继续用于开发，结果明确称开发证据；不要求所有材料“完全未触碰”，也不自动剔除 97 个关联目标。保留分组交叉拟合、运行时答案／未来信息排除和相同条件的基线比较；后续实际调用预算仍须核算。

之后在相应批准下完成真正的 RS/MP/ME/MS amount/top-k 和容量校准，冻结各 head 的 `k*`、完整生成与评分栈、特征和折分，再生成正式 effect labels 并训练四个 L2 head。没有合格 pairwise 确认时，Summary/DG 的连续指标微差不能直接充当 material-benefit 标签；uncertain 不能填成 0。

产物分发沿用已有规则：仓库收录新代码、研究记录、提案、公开聚合统计和来源哈希；完整题面、已填答卷、API 缓存、账本与模型请求正文仍保存在本地。网页版可审计方法与统计，但仅凭公开文件不能逐题重做语义判定。
