# PM-RL1 阶段与证据时间线

整理于2026-10-22。最新结论以[当前状态](../PM_RL1_CURRENT_STATUS.md)为准。下表将生成G、测量/审查J、人评与工程分开；不把不同阶段的调用数混成独立样本数。

| 日期/阶段 | 已做的工作与结果 | 主要证据 |
|---|---|---|
| 09-28 原始方向 | 从Paper-1扩展为单轮有限步资源获取；建立观测、动作、预算及执行边界 | [原始方案](../PM_RL1_ORIGINAL_IMPLEMENTATION_PLAN_20260928_ZH.md)、[实施范围](../PM_RL1_SCOPED_IMPLEMENTATION_20260928_ZH.md) |
| 09-28—29 环境/E0 | 实现GET/STOP、冻结来源、有限环境PPO与初始化；不代表自然任务成功 | [工程进展](../PM_RL1_ENGINEERING_PROGRESS_20260928_ZH.md)、[E0结果](../PM_RL1_RESOLUTION_AND_E0_RESULTS_20260929_ZH.md) |
| 09-29—30 初版执行器 | 155条接纳弱目标的旧一轮训练；覆盖不足，后被P1/P2新版本承接 | [覆盖与停止](../PM_RL1_EXECUTOR_COVERAGE_AND_STOPPING_20260929_ZH.md)、[旧训练结果](../PM_RL1_COVERAGE_TRAINING_RESULTS_20260930_ZH.md) |
| 09-30 R04B | Prometheus/Skywork有限原生接口实验均未获reward资格 | [R04B结果](../PM_RL1_R04B_CANDIDATE_RESULTS_20260930_ZH.md) |
| 09-30 完成方案v2 | 收敛至单冻结执行器下完整资源策略研究，明确P0—P7与备用路线 | [唯一主方案](../PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md)；其下半部“P1尚未开始”为历史时点 |
| 10-01 P1 | 72 MP＋24 ME有限审查；88条生成诊断，修复角色/来源交付并复算容量 | [P1结果](../PM_RL1_P1_REPRESENTATION_RESULTS_20261001_ZH.md) |
| 10-01 P2 | 493条弱目标、一次三epoch LoRA、639条比较回复；披露重复键与跨加载限制 | [P2结果](../PM_RL1_P2_EXECUTOR_RESULTS_20261001_ZH.md) |
| 10-01—02 P3初版 | 32条开发主评分＋1次完整来源复核；40对人评工具；奖励未合格 | [P3记录](../pm_rl1_completion_20260930_v2/p3_development_results.json)、[发布说明](../PM_RL1_STAGE_PUBLICATION_20261002_ZH.md) |
| 10-14 开发接收 | 开发16题有实质备注；Du为派生；24封存对与12复评未据此通过 | [开发结案](../PM_RL1_DEVELOPMENT_CLOSEOUT_20261014_ZH.md) |
| 10-15 Gemma A/B | A/B开发及接续遇语义/技术STOP；没有确定合格配置 | [A/B结果](../../outputs/pm_rl1/judge_selection_preparation_20261014_v1/AB_development_20261015/RESULTS_ZH.md)、[接续结果](../../outputs/pm_rl1/judge_selection_preparation_20261014_v1/AB_diagnostic_continuation_20261015/RESULTS_ZH.md) |
| 10-15 DeepSeek C/D | 首轮8次；C遇等义分差STOP；D接续13次，最后重复JSON键失败；当时累计120 | [C/D结果](../../outputs/pm_rl1/judge_selection_preparation_20261014_v1/CD_engineering_20261015/RESULTS_ZH.md)、[D结果](../../outputs/pm_rl1/judge_selection_preparation_20261014_v1/D_development_20261015/RESULTS_ZH.md) |
| 10-19 人评与澄清 | 同研究者八条原标注、三项补充；保留04B双读、06B行动预设、16A亲历归属 | [人评包](/home/tokkio/PM-RL1/02_阶段交付/2026-10-19/PM_RL1_ANNOTATION_REVIEW_20261019/README_ZH.md)、[补充判断](/home/tokkio/PM-RL1/02_阶段交付/2026-10-19/PM_RL1_REFERENCE_UPDATE_20261019/FOLLOWUP_AND_NEXT_STEP_ZH.md) |
| 10-19 联合/分步 | 24J完成，累计144；没有已证实的上下文修复，不升级分步流程 | [配对结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-19/PM_RL1_PAIRED_DIAGNOSTIC_RESULTS_20261019/RESULTS_ZH.md) |
| 10-19 RS适用性 | 16G完成；一个已知求职套用错误得到局部修复；J仍144 | [RS结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-19/PM_RL1_RS_APPLICABILITY_RESULTS_20261019/RESULTS_ZH.md) |
| 10-20 本地与闭环 | 45计划槽中41G自然完成、4不具库存；没有新q/m和自然训练 | [结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_LOCAL_AND_LOOP_RESULTS_20261020/RESULTS_ZH.md) |
| 10-20 行动提醒 | 9J后稳定性STOP，累计153；06B同输入U差0.5 | [行动诊断](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_ACTION_STAGE_DIAGNOSTIC_RESULTS_20261020/RESULTS_ZH.md) |
| 10-20 奖励噪声 | 48J完成，累计201；平均未达到推进条件 | [噪声结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_REWARD_NOISE_RESULTS_20261020/RESULTS_ZH.md) |
| 10-20 七组方向人评 | 六组相当、一组A；旧P04另列复用；同一研究者开发参照 | [方向结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_HUMAN_DIRECTION_RESULTS_20261020/RESULTS_ZH.md) |
| 10-20 锚点校准 | 24J完成，累计225；04B仍波动，06B未完整修复 | [锚点结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_ANCHOR_CALIBRATION_RESULTS_20261020/REPORT_ZH.md) |
| 10-21 关系参照 | 28J完成，累计253；06B事实关系局部改善，q仍波动 | [关系结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-21/PM_RL1_RELATION_REFERENCE_RESULTS_20261021/REPORT_ZH.md) |
| 10-21 任务参照 | 32J完成，累计285；未显示B额外任务卡增益 | [任务结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-21/PM_RL1_TASK_REFERENCE_RESULTS_20261021/REPORT_ZH.md) |
| 10-22 反馈原型/实跑 | 原型离线完成；实际第6次因schema合同缺口STOP，累计291，5有效1失败 | [反馈结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-22/PM_RL1_FEEDBACK_RESULTS_20261022/REPORT_ZH.md) |
| 10-22 source_evidence | 新增11次有效，累计302；原阶段17次、3/4配对完整，唯一补核未改分 | [接续结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-22/PM_RL1_SOURCE_EVIDENCE_RESULTS_20261022/REPORT_ZH.md) |
| 10-22 评分关联审查 | 离线候选后实跑2次，累计304；1有效、1末尾额外括号失败 | [评分审查](/home/tokkio/PM-RL1/02_阶段交付/2026-10-22/PM_RL1_SCORE_AUDIT_RESULTS_20261022/REPORT_ZH.md) |
| 10-22 strict接续 | 新增3次，累计307；2有效1格式失败；原8槽合计3有效/5尝试/8计划，3未派发 | [最新结果](/home/tokkio/PM-RL1/02_阶段交付/2026-10-22/PM_RL1_STRICT_DELIVERY_RESULTS_20261022/REPORT_ZH.md) |

## 如何判定一个目录的性质

`PREPARATION/PROPOSAL/READY/START/OFFLINE`主要记录准备或离线实现；必须另找真实运行、started记录和结果收口。`RESULTS`也可能是技术STOP后的部分结果，不能只按名字认定完成。目录中的`authorization/PENDING`可能是冻结前快照，须结合之后的授权及CLOSEOUT；同样，旧包中的“可以继续”不能覆盖最新STOP。

当前原始证据链主要在`project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/`。这个名字看似10月14日选型准备，实际上持续容纳到10月22日的多个研究阶段，是混乱的重要来源；本轮用分类导航解决查找问题，保留原位置以维持合同和缓存身份。

HOME包是便于阅读与交付的快照；代码仓库中的当前文档、冻结运行目录和原始记录承担不同作用。ZIP与解压目录可能属于不同快照，不能未经核对删除其中一份。本轮对照结果在[整理记录](/home/tokkio/PM-RL1/90_整理记录/20261022)。
