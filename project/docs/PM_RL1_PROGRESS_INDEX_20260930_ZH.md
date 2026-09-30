# PM-RL1 研究进展与结果索引（2026-09-30）

此入口汇总本轮对话的新方案、代码、结果、失败分析及数据诊断。旧 Paper-1 记录作为历史保留。原始实验目录与旧身份没有被上传过程改写；公开包只提升可审阅的报告、统计、代码和测试。

## 当前结论

已完成单轮资源环境、可重放工程检查、有限环境的 PPO 学习验证、执行器弱监督与 LoRA 开发、有限裁判实验，以及公开数据与派生资产普查。自然支持任务的可靠 reward 尚未建立，没有启动该任务的正式 PPO，没有宣称 LoRA 改善支持质量。

最近一轮发现：RS 的自我披露与真人 supporter→AI assistant 身份映射存在冲突风险；部分 MP 更新缺少新证据确认；QA 的引用、时间范围和可见性需要区分；SFT 只覆盖 0/1/2 条资源而环境允许 3/4 条及同类多取。下一步是版本化数据／身份修复、固定执行器对照与覆盖补齐，然后验证测量。

## 建议阅读顺序

| 阶段 | 报告 | 阅读要点 |
|---|---|---|
| 用户新方案 | [原始方案](PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md)、[实施范围](PM_RL1_SCOPED_IMPLEMENTATION_20260928_ZH.md) | 单轮、最多四次获取、先执行器后 PM；与旧四头研究的关系 |
| 环境与费用 | [工程进展](PM_RL1_ENGINEERING_PROGRESS_20260928_ZH.md)、[费用重估](PM_RL1_COST_REASSESSMENT_20260928_ZH.md) | 自然停止；资源预算与回复截断不同；沿用全局费用边界 |
| 评价准备 | [评价设计](PM_RL1_EVALUATION_DESIGN_DRAFT_20260928_ZH.md)、[评价就绪分析](PM_RL1_EVALUATION_READINESS_AND_NEXT_STEPS_20260928_ZH.md) | 旧人评、考卷与新 q/m 的适用性 |
| 首轮测量 | [测量小样](PM_RL1_MEASUREMENT_PILOT_RESULTS_20260928_ZH.md)、[解决路径](PM_RL1_MEASUREMENT_RESOLUTION_PLAN_20260929_ZH.md) | 解析、换序、重复与真实语义问题 |
| 测量与 PPO 工程 | [E0 与测量收口](PM_RL1_RESOLUTION_AND_E0_RESULTS_20260929_ZH.md) | 工程学习成功不等于真实支持奖励可用 |
| 执行器初版 | [pilot 结果](PM_RL1_EXECUTOR_PILOT_RESULTS_20260929_ZH.md) | 弱监督准入与来源问题 |
| 来源修复 | [来源修复及工程结果](PM_RL1_SOURCE_REPAIR_AND_ENGINEERING_RESULTS_20260929_ZH.md) | 旧状态刷新、主体／时间、有限修复范围 |
| 执行器覆盖 | [覆盖与停止分析](PM_RL1_EXECUTOR_COVERAGE_AND_STOPPING_20260929_ZH.md)、[训练结果](PM_RL1_COVERAGE_TRAINING_RESULTS_20260930_ZH.md) | 155 条接纳数据、选定 epoch、真实失败案例、能力边界 |
| R04B | [测量及有限人评方案](PM_RL1_R04B_MEASUREMENT_AND_SINGLE_HUMAN_CAMPAIGN_20260929_ZH.md)、[候选结果](PM_RL1_R04B_CANDIDATE_RESULTS_20260930_ZH.md) | Prometheus／Skywork 原生接口实验；均未获训练 reward 资格 |
| 数据本身 | [全数据诊断与研究路线](PM_RL1_DATASET_DIAGNOSTICS_AND_RESEARCH_PATH_20260930_ZH.md) | 全量结构、固定来源抽查、角色／时效／证据／动作覆盖 |
| 上传与测试 | [CI 问题及修复](PM_RL1_PUBLICATION_AND_CI_20260930_ZH.md) | 历史失败根因、干净检出复现和可移植修复 |

这些是按时间保存的记录。早期文档里的“尚未实现”代表当时状态；当前状态以最新阶段结果为准，不回写旧报告制造事后完成。

## 可直接查看的结果

- [75 个公开结果与来源 SHA256 清单](reviews/20260930/pm_rl1/MANIFEST.json)
- [环境与来源冻结](reviews/20260930/pm_rl1/source_and_capacity_20260928_v1/dataset_freeze.json)
- [E0 对照](reviews/20260930/pm_rl1/measurement_resolution_20260929_v1/e0_comparison.json)
- [执行器训练统计](reviews/20260930/pm_rl1/executor_training_20260930_v1/results_summary.json)
- [R04B 统计](reviews/20260930/pm_rl1/r04b_measurement_20260930_v1/results_summary.json)及[候选处置](reviews/20260930/pm_rl1/r04b_measurement_20260930_v1/decision.json)
- [数据普查](reviews/20260930/pm_rl1/dataset_diagnostics_20260930_v1/census.json)、[动作可达性](reviews/20260930/pm_rl1/dataset_diagnostics_20260930_v1/capacity.json)、[可移植 notebook](reviews/20260930/pm_rl1/dataset_diagnostics_20260930_v1/dataset_diagnostics.ipynb)
- [全部本地 PM-RL1 产物的路径、大小与哈希](reviews/20260930/pm_rl1/LOCAL_ARTIFACT_INVENTORY.json)
- [用户提供的两轮网页版建议原文](reviews/20260930/discussion/MANIFEST.json)：历史提案，不代表已验证结论；后续 R04B 和数据诊断保留了反证与修正。

统计表与 notebook 在 GitHub 可读，运行 notebook 仅需 Python 标准库。完整训练／模型推理脚本仍需对应本地模型、冻结输入与实验环境。公开统计不是原始调用日志；模型权重、盲映射、完整人工表和私有请求／响应仍留本地，以哈希登记，没有伪装成可凭仓库独立重跑的 GPU 实验。

## 代码定位

- `project/src/metacom_pm/rl1/`：环境、白名单观测、资源渲染、生成、测量适配、执行器与 E0 工程模块。
- `project/scripts/rl1/01–68`：前缀准备、费用、测量、来源修复、执行器训练及 R04B。
- `project/scripts/rl1/69–73`：数据特征、可达动作、证据审查、notebook 与哈希收口。
- `project/scripts/rl1/74_publish_research_snapshot.py`：显式白名单生成本公开快照，无推理／训练／上传调用。
- `project/tests/test_rl1_*.py`：CPU 回归测试，与旧 Paper-1 活跃测试共同阻断 CI。

## 上轮尚未上传的承接内容

同时补齐了 9 月 17–19 日本地裁判、自然结束、静态校准及费用报价记录，避免本次 config／脚本引用远端不存在的文件：

- [本地裁判结果](PM_PAPER1_LOCAL_TEACHER_DEVELOPMENT_RESULTS_20260917_ZH.md)、[测量研究](PM_PAPER1_JUDGE_MEASUREMENT_STUDY_20260917_ZH.md)
- [静态校准准备](PM_PAPER1_STATIC_AMOUNT_CALIBRATION_PACKAGE_20260917_ZH.md)、[执行记录](PM_PAPER1_STATIC_AMOUNT_EXECUTION_20260917_ZH.md)
- [后续费用计划](PM_PAPER1_FOLLOWUP_BUDGET_PLAN_20260918_ZH.md)及 `reviews/20260918/` 下的原始报价统计。

该部分保留旧官方评价口径与锁，不因此开启付费执行或旧路线正式训练。
