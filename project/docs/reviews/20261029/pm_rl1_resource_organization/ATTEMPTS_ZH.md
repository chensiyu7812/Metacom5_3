# 既往路线与防重复登记

按主要机制登记，不把调用数相加，也不声称本轮重新审阅所有历史原始输出。每行来源hash和旧时间线链接见 [ATTEMPT_REGISTER.json](ATTEMPT_REGISTER.json)。当前308是后续试验计数口径，不是全研究全部本地模型调用总量。

| ID / 路线 | 已有结果 | 后续不能重复的误区 | 何种新信息才值得再试 | 证据 |
|---|---|---|---|---|
| J01 Qwen 首轮联合q/m与引文规范化 | 55次严格22有效；仅字形规范化26；编号接口追加5次均结构可读。 | 机械引用恢复不等于语义蕴含；不可只报有效子集。 | 明确新的输入/解析差异及完整分母，不能重抽好分。 | [来源1](../../../../docs/PM_RL1_MEASUREMENT_PILOT_RESULTS_20260928_ZH.md) |
| J02 Qwen 编号引用、relation/schema简化 | v2 49/55有效；v3结构冲突；v4 64/67可解析但仍有事实/严重度矛盾和重复分差。v5仅离线准备。 | 不能把grammar和同分缓存当可靠测量。 | 针对已证机制的实际wire核对与语义独立参照；不能把准备版本记为实跑。 | [来源1](../../../../docs/PM_RL1_RESOLUTION_AND_E0_RESULTS_20260929_ZH.md) |
| J03 Compass 复杂结构及一次简化 | 复杂版12次失败；简化版12次可读但无要求的来源ID，存在选项/理由冲突。 | 控制中5/6可能等于总选A；不同checkpoint不自动是独立模型家族。 | 改变能力或输入机制并用平衡/反序及证据核验。 | [来源1](../../../../docs/PM_RL1_RESOLUTION_AND_E0_RESULTS_20260929_ZH.md) |
| J04 Prometheus 原生相对评分 | 88调用；86可解析，换序与虚构比较理由问题。 | 相同回复也能编造差异；不能投票掩盖这种错误。 | 新任务适配/监督证据，而非原配置重复跑熟题。 | [来源1](../../../../docs/PM_RL1_R04B_CANDIDATE_RESULTS_20260930_ZH.md) |
| J05 Skywork 原生标量排序 | 94条可读，2条范围外未调用；确定性重复仍可强烈偏好错误自传。 | 稳定不是正确；epsilon不能修正大幅错误方向；raw logit不能冒充q/m。 | 明确用途和有依据的语义校准，不能事后调阈值宣称原卷通过。 | [来源1](../../../../docs/PM_RL1_R04B_CANDIDATE_RESULTS_20260930_ZH.md) |
| S01 MP更新来源隔离与时点投影 | 旧101次更新复核、部分抑制；先选当时最新再隔离，不自动回退旧事实。 | 找得到quote不代表支持完整属性；抑制不等于事实全假。 | 有新增原文依据可修复；时间链只由当时可知来源生成。 | [来源1](../../../../docs/PM_RL1_SOURCE_REPAIR_AND_ENGINEERING_RESULTS_20260929_ZH.md) |
| G01 作者弱目标第二批与工程LoRA | 108回复；90接纳弱目标，原全格准入未过；61/29工程训练，MP训练0。 | 不能不断补抽到全格通过；NLL下降不是支持质量。 | 明确覆盖和监督缺陷后的新数据方案，旧失败保留。 | [来源1](../../../../docs/PM_RL1_SOURCE_REPAIR_AND_ENGINEERING_RESULTS_20260929_ZH.md) |
| G02 旧155弱目标覆盖训练 | 覆盖不足，后由P1/P2新版本承接。 | 不能将该批作为完整四头资源利用监督。 | 依据最终数据覆盖/来源变化重建训练身份。 | [来源1](../../../../docs/PM_RL1_EXECUTOR_COVERAGE_AND_STOPPING_20260929_ZH.md)、[来源2](../../../../docs/PM_RL1_COVERAGE_TRAINING_RESULTS_20260930_ZH.md) |
| S02 P1来源/角色/原生user接口 | 72 MP、24 ME有限审查；88生成诊断；现DirectReplyRenderer。 | 历史supporter不是当前AI；整体JSON曾导致第三人称分析。 | 实际新输入变化才重测受影响项，不重复已完成集成。 | [来源1](../../../../docs/PM_RL1_P1_REPRESENTATION_RESULTS_20261001_ZH.md) |
| G03 P2 493弱目标和三epoch LoRA | 413/80目标；586主回复与53同输入base对照；4条重复键准入缺陷，质量收益未证明。 | 作者与核验同模型、use/ignore自报不作金标；不按NLL直接宣称获益。 | 先分析现成同输入对照，再决定新监督/训练是否必要。 | [来源1](../../../../docs/PM_RL1_P2_EXECUTOR_RESULTS_20261001_ZH.md) |
| J06 P3初版结构化裁判和人工材料 | 32主评分＋1复核；40对材料设计。 | 有数值和交卷工具不等于资格。 | 固定新候选及原人工用途。 | [来源1](../../../../docs/pm_rl1_completion_20260930_v2/p3_development_results.json)、[来源2](../../../../docs/PM_RL1_STAGE_PUBLICATION_20261002_ZH.md) |
| H01 开发16题接收与派生记录 | 已有实质备注；Du为派生，不能算第二位独立人。 | 重复材料/AI复核不增加独立人群或评审者。 | 仅对新且必要的未知点收集参照，不重发整套旧题。 | [来源1](../../../../docs/PM_RL1_DEVELOPMENT_CLOSEOUT_20261014_ZH.md) |
| J07 Gemma A/B及接续 | 语义与技术STOP，未选出合格配置。 | 模型名或格式修复不能继承资格。 | 机制变化、固定开发比较和独立参照。 | [来源1](../../../../outputs/pm_rl1/judge_selection_preparation_20261014_v1/AB_development_20261015/RESULTS_ZH.md)、[来源2](../../../../outputs/pm_rl1/judge_selection_preparation_20261014_v1/AB_diagnostic_continuation_20261015/RESULTS_ZH.md) |
| J08 DeepSeek C/D及D接续 | C等义分差；D接续末尾重复JSON键失败，当时累计120。 | 已知格式失败不可当能力失败，失败结果不可覆盖。 | 完整wire交付与语义结果分开验证。 | [来源1](../../../../outputs/pm_rl1/judge_selection_preparation_20261014_v1/CD_engineering_20261015/RESULTS_ZH.md)、[来源2](../../../../outputs/pm_rl1/judge_selection_preparation_20261014_v1/D_development_20261015/RESULTS_ZH.md) |
| J09 联合评分 vs 分步提取 | 24J，没有已证明的上下文修复，不升级分步。 | 多一步不自动改善；同模型抽取不能自证事实。 | 新的缺失能力/监督证据，不重复原拆分提示。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-19/PM_RL1_PAIRED_DIAGNOSTIC_RESULTS_20261019/RESULTS_ZH.md) |
| G04 RS适用性指导对照 | 16G，一处已知求职套用得到局部修复。 | 局部修复不推广为普遍正确，也不能为涨效果无条件替换冻结G。 | 固定新开发材料；来源条件化RS与原版同输入对照。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-19/PM_RL1_RS_APPLICABILITY_RESULTS_20261019/RESULTS_ZH.md) |
| G05 本地执行与闭环生成诊断 | 45计划槽，41G自然完成，4无库存；无新合格q/m。 | 生成成功、随机初始化诊断不能称真实BC/PPO。 | 合格反馈后使用真实初始化与完整自然轨迹。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_LOCAL_AND_LOOP_RESULTS_20261020/RESULTS_ZH.md) |
| J10 行动阶段提醒 | 9J后稳定性STOP，06B同输入U差0.5。 | 强调意向/行动不等于稳定q。 | 独立核查事实读取和量化后果，不能继续只加提醒。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_ACTION_STAGE_DIAGNOSTIC_RESULTS_20261020/RESULTS_ZH.md) |
| J11 四次重复与均值诊断 | 48J覆盖12终点，5终点U变化；平均未建立推进条件。 | 重复不是新独立样本；不能平均掉定义歧义或按喜欢的分数选。 | 明确测量政策/监督或真实机制差异，独立repeat保留独立draw。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_REWARD_NOISE_RESULTS_20261020/RESULTS_ZH.md) |
| H02 七组方向人工及旧ME偏好 | 后7组6平1偏OFF；旧ME局部正例后来P04复用。 | 不遗漏正例，也不双计；平局不强行拉开。 | 按原低差异分支；保留STOP情境。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_HUMAN_DIRECTION_RESULTS_20261020/RESULTS_ZH.md) |
| J12 锚点校准 | 24J；04B仍波动、06B未完整修复。 | 熟题锚点不能自动变泛化能力。 | 新监督或可检验机制变化，另用未调规则材料。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-20/PM_RL1_ANCHOR_CALIBRATION_RESULTS_20261020/REPORT_ZH.md) |
| J13 关系参照 | 28J；06B关系局部改善，q仍2/3。 | 事实判断和评分后果不可混为一个成功指标。 | 采用有效分项，另校准质量尺度；这不禁止来源图优化。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-21/PM_RL1_RELATION_REFERENCE_RESULTS_20261021/REPORT_ZH.md) |
| J14 任务参照卡 | 32J；同期两臂共同变化，未显示新增卡片增益。 | 不能把共同变化归功于新增提示。 | 能区分新增机制贡献的固定比较，而非继续加卡。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-21/PM_RL1_TASK_REFERENCE_RESULTS_20261021/REPORT_ZH.md) |
| J15 初评—审查—补核原型与source_evidence接续 | 6＋11次；原17次3/4配对完整，唯一补核未改分；原审查缺完整量表。 | 回复有错不等于初评漏判；本地schema不能替代发送给模型。 | 真实wire全量核验、收益与成本、有限S/A路线选择。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-22/PM_RL1_FEEDBACK_RESULTS_20261022/REPORT_ZH.md)、[来源2](/home/tokkio/PM-RL1/02_阶段交付/2026-10-22/PM_RL1_SOURCE_EVIDENCE_RESULTS_20261022/REPORT_ZH.md) |
| J16 评分关联审查 | 2次，1有效、1多余括号失败。 | 解析有效不保证依据/量表执行正确。 | 完整输入交付修复明确、技术和语义独立验收。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-22/PM_RL1_SCORE_AUDIT_RESULTS_20261022/REPORT_ZH.md) |
| J17 Beta strict接续 | 3次，2有效1格式失败；有效输出仍有q3条款矛盾；旧3槽未派发。 | strict参数不是验收；不自动恢复旧STOP或挪旧剩余额。 | 新完整阶段和有限恢复，不能原配置逐错逐次续命。 | [来源1](/home/tokkio/PM-RL1/02_阶段交付/2026-10-22/PM_RL1_STRICT_DELIVERY_RESULTS_20261022/REPORT_ZH.md) |
| J18 Claude试用配置 | 1次评分请求配置拒绝；workspace查询403；无评分结果。 | 配置/账户问题不能诊断Claude语义能力；未用额度不转移。 | 账户归属/配置明确且具体阶段获批后才有能力实验。 | [来源1](../../../../docs/pm_rl1_workspace_20261022/ORIGINAL_PLAN_RESUMPTION_ZH.md) |
| E01 内容评分复用、有限恢复、统一学习队列 | 主要工程缺口已修；合成BC/完整batch接线通过。 | 缓存同分不是准确性；mock通过不代表真实评分流程完整。 | 生产版本变化时测接线；不重复以测试数代替研究结果。 | [来源1](../../../../docs/reviews/20261022/pm_rl1_backend/BACKEND_REVIEW_ZH.md) |
| E02 真实G/BGE固定集成 | EOS tuple/list误拒绝已修，另批准8G/8编码完成；回复与历史对应相同。 | 不把同输入复现算新增训练样本，不重复运行已收口探针。 | 实际模型/runtime/接口变动后才验证受影响部分。 | [来源1](../../../../docs/reviews/20261023/pm_rl1_local_execution/EXECUTION_ZH.md)、[来源2](../../../../docs/reviews/20261023/pm_rl1_local_success/RESULTS_ZH.md) |
| E03 E0合成环境真实学习 | 有真实优化与价值初始化证据，属于已知小任务。 | toy可学不证明自然任务可学；未测自然终值不可补oracle。 | 只在算法/接线变动或出现新失败时回归。 | [来源1](../../../../docs/PM_RL1_RESOLUTION_AND_E0_RESULTS_20260929_ZH.md) |
| O01 来源机会审计与最小时序索引 | 114前缀、586回复重核；MS179位置阻塞；52同内容高成本；原始ID/盲化序号适配修复。 | 不要把每条quote存在当语义正确；不要把旧硬预算当不可改前提。 | 研究者本轮已要求解除人为限制，开始新组织对照。 | [来源1](../../../../docs/reviews/20261029/pm_rl1_reorganization/REPORT_ZH.md) |
| P01 自然BC与PPO | 合格BC检查点0、自然更新0。 | 不能写成PM已经学失败；不能用新索引轨迹代替训练。 | 合格反馈、冻结同域基线及版本后开展真实闭环。 | [来源1](../../../../docs/reviews/20261029/pm_rl1_reorganization/J1_READINESS.json) |

这份登记不是禁止改进：关系参照只改善事实读取，可以保留该局部能力继续优化；不能因此宣称q标尺已合格。新资源索引和组织方式已改变具体机制，不属于原提示原样重跑。

以后每项提案先写明引用哪条旧失败、这次变化及身份、可检验差异、参照来源、成本与收口出口。工程已修复项作为回归保留；不重新购买相同探针，不按分数满意与否决定重试。
