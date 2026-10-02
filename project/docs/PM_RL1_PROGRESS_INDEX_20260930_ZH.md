# PM-RL1 研究进展与结果索引（2026-09-30）

此入口汇总本轮对话的新方案、代码、结果、失败分析及数据诊断。旧 Paper-1 记录作为历史保留。原始实验目录与旧身份没有被上传过程改写；公开包只提升可审阅的报告、统计、代码和测试。

## 当前接续方案

2026-10-02 整理本阶段公开发布：[发布说明与验证](PM_RL1_STAGE_PUBLICATION_20261002_ZH.md)、[26份结果及16份分析资产清单](reviews/20261002/pm_rl1/MANIFEST.json)、[公开结果 notebook](reviews/20261002/pm_rl1/stage_results.ipynb)。保留P1/P2缺陷披露和P3未校准状态；含在用控制题与分组的95、96制卷脚本暂缓公开，仅登记哈希，原文件与现有人评包不变。

2026-10-01 P3已完成初版评分器试跑及40对盲评交接包：[结构化进展与实测费用](pm_rl1_completion_20260930_v2/p3_development_results.json)、[操作入口](pm_rl1_completion_20260930_v2/runbook.md)。32条开发评分及1次预定完整来源复核均自然结束、解析成功；引擎耗时约29.18分钟，新增API费0美元。开发／封存按整位用户的事实沿革分离，人工标签逐题加密，尚未收到任何真人标签，也没有打开封存评分或执行12次稳定性复评分。候选仍有需核对的风险程度判断，不能因结构成功就用于自然PPO。CI范围1,206通过、1项旧路径依赖跳过，旧2,735个产物哈希未变。

2026-10-01 P2已收口：实际冻结493条弱目标（train413、dev80），完成唯一一次三epoch LoRA和36条行为检查，选中第三轮并通过NLL重载；586条主回复＋53条base对照全部自然结束。4条已纳入目标的重复JSON键准入缺陷、6组跨加载重复输入仅2组回复逐字一致的限制均已披露，原数据／训练不回写。见[P2实施记录](PM_RL1_P2_EXECUTOR_RESULTS_20261001_ZH.md)、[结构化结果](pm_rl1_completion_20260930_v2/p2_results.json)及[复现补充](pm_rl1_completion_20260930_v2/p2_replay_addendum.json)。输入／目标覆盖、弱目标NLL与质量收益分开报告，奖励尚未校准。

2026-10-01 已完成 [P1表示、来源与接口实施](PM_RL1_P1_REPRESENTATION_RESULTS_20261001_ZH.md)：新增72条MP和24条ME的有限来源审查，完成新版交付、共同70计划特征及容量复算；原定72条诊断加一次明确记账的16条接口修复，全部自然结束。该阶段176项RL1测试通过，旧2,735个产物哈希不变，并冻结后续684个示范输入和12个行为检查输入；P2的后续进展见上文。

同日的[目标能力反推与任务适配性分析](PM_RL1_CAPABILITY_BACKWARD_DESIGN_20261001_ZH.md)保留为P1之前的设计依据；其中“P1尚未实施”是该文写作时状态。当前采用最新一句原生user＋历史角色引用的 `DirectReplyRenderer`；旧LoRA仍有历史话语归属残留错误，不宣称身份问题或reward已完全解决。

2026-09-30 后续讨论已整理为 [可行执行与研究完成方案 v2](PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md)，以及 [执行手册](pm_rl1_completion_20260930_v2/runbook.md)、[结构化工作包](pm_rl1_completion_20260930_v2/execution_contract.json)、[基线核对](pm_rl1_completion_20260930_v2/execution_manifest.json)、[计算与人工预算](pm_rl1_completion_20260930_v2/budget_estimate.json)。网页版原方案另存原文快照。

v2已完成P0、P1、P2，并完成P3的统一来源、固定考卷、初版开发测量及可填写交接包；P2按披露准入及复现限制的弱监督开发实验解释。真正的人类校准、奖励资格及自然PPO仍待完成。主攻一个冻结执行器下的四类资源策略，保留有条件的人工终值表备用路线。以下历史结果不因新计划存在而变成已完成的新实验。

## 当前结论

已完成单轮资源环境、可重放工程检查、有限环境的 PPO 学习验证、执行器弱监督与 LoRA 开发、有限裁判实验，以及公开数据与派生资产普查。自然支持任务的可靠 reward 尚未建立，没有启动该任务的正式 PPO，没有宣称 LoRA 改善支持质量。

最近两阶段已将来源／角色边界转化为实际交付字段、来源核验和开发回归。新库存下114个train/dev前缀均支持3条、4条及同类多取；本轮493条接纳目标中六类条件均覆盖全部12个train用户。模型仍会误判话语归属和事实前提，资源行为自报也不可靠；覆盖与NLL不代替回复质量和奖励校准。

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
| P1实施与P2准备 | [表示、来源和接口结果](PM_RL1_P1_REPRESENTATION_RESULTS_20261001_ZH.md) | 72＋24来源核查、72＋16生成、6,899可达计划、残留错误和684个后续输入 |
| P2执行器 | [弱目标与执行器实施记录](PM_RL1_P2_EXECUTOR_RESULTS_20261001_ZH.md) | 493条弱目标、一次训练、639条比较回复；准入缺陷及跨加载限制完整披露 |
| P3评分与人工工具 | [初版开发结果](pm_rl1_completion_20260930_v2/p3_development_results.json)、[填写与接收流程](pm_rl1_completion_20260930_v2/runbook.md) | 32＋1次本地评分、40对固定盲评、用户／事实分组、加密封存、实际吞吐；尚未校准合格 |

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
- [P1实际汇总](pm_rl1_completion_20260930_v2/p1_results.json)、[P2固定输入统计](pm_rl1_completion_20260930_v2/p2_input_summary.json)：保留输入准备时的快照，后续结果另记，不回写这些旧统计。
- [P2实际汇总](pm_rl1_completion_20260930_v2/p2_results.json)、[跨加载复现补充](pm_rl1_completion_20260930_v2/p2_replay_addendum.json)、[P3统一来源准备](pm_rl1_completion_20260930_v2/p3_evidence_preparation.json)。本阶段CI范围1,172通过、1项旧tokenizer路径依赖跳过，旧2,735个产物哈希未变。

统计表与 notebook 在 GitHub 可读，运行 notebook 仅需 Python 标准库。完整训练／模型推理脚本仍需对应本地模型、冻结输入与实验环境。公开统计不是原始调用日志；模型权重、盲映射、完整人工表和私有请求／响应仍留本地，以哈希登记，没有伪装成可凭仓库独立重跑的 GPU 实验。

## 代码定位

- `project/src/metacom_pm/rl1/`：环境、白名单观测、资源渲染、生成、测量适配、执行器与 E0 工程模块。
- `project/scripts/rl1/01–68`：前缀准备、费用、测量、来源修复、执行器训练及 R04B。
- `project/scripts/rl1/69–73`：数据特征、可达动作、证据审查、notebook 与哈希收口。
- `project/scripts/rl1/74_publish_research_snapshot.py`：显式白名单生成本公开快照，无推理／训练／上传调用。
- `project/scripts/rl1/75–80`：P1来源记录、表示冻结、自然结束诊断、一次接口修复、结果收口及P2输入准备。
- `project/scripts/rl1/81–93`：P2弱目标准入、有限修复、一次LoRA、行为选模与共同回复池。
- `project/scripts/rl1/94_prepare_p3_common_evidence.py`：P3共同前缀的完整合法来源、角色约定及来源token计数；不生成裁判或人工标签。
- `project/scripts/rl1/95–104`：先锁条件、生成40对盲审包、冻结／试跑初版裁判、只接收开发标签、核对浏览器交付与全来源长度、记账。`calibration_decision.py`只计算经核验的准入输入，不自动开启训练。
- `project/tests/test_rl1_*.py`：CPU 回归测试，与旧 Paper-1 活跃测试共同阻断 CI。

## 上轮尚未上传的承接内容

同时补齐了 9 月 17–19 日本地裁判、自然结束、静态校准及费用报价记录，避免本次 config／脚本引用远端不存在的文件：

- [本地裁判结果](PM_PAPER1_LOCAL_TEACHER_DEVELOPMENT_RESULTS_20260917_ZH.md)、[测量研究](PM_PAPER1_JUDGE_MEASUREMENT_STUDY_20260917_ZH.md)
- [静态校准准备](PM_PAPER1_STATIC_AMOUNT_CALIBRATION_PACKAGE_20260917_ZH.md)、[执行记录](PM_PAPER1_STATIC_AMOUNT_EXECUTION_20260917_ZH.md)
- [后续费用计划](PM_PAPER1_FOLLOWUP_BUDGET_PLAN_20260918_ZH.md)及 `reviews/20260918/` 下的原始报价统计。

该部分保留旧官方评价口径与锁，不因此开启付费执行或旧路线正式训练。
