# 历史资产迁移：只检查当前实际依赖

基点`c7a83bfb`和GE2实际59次调用、37个终局保留。没有重开J00/G0e/E6/A0，没有重算旧结果以提高成绩。以下区分可复用工程与未解决的语义能力。

| 资产 | 本次实际使用/迁移 | 不继承的假设或资格 |
|---|---|---|
| SourceRegistry / As-of / Ledger | 原GE2Factory→`prepare_source_port`，来源可见性、角色、严格先前/官方完整历史QA各自身份 | 来源合法不代表归一化解释正确；完整历史QA不被改叫泄漏 |
| RAW/SPAN、Memory Port | 原始话轮及相邻上下文，实际read_intervals；无新数据库 | 不把MS-SUM导航当全量事实记忆，MP/ME仍pending/mask |
| GE2工具/运行时/计量 | BM25 Top4原query和父展开；被动首文字观察器、同boot计量、设备/进程/预算守卫 | 不继承“ToolAgent有效”或“本地首文字就是有效语音” |
| Paper1 Semantic Compiler | 复用source-only/grounding/version-parent设计，在线解释另设薄层 | 旧抽取器与复核器相同，不是独立语义裁判 |
| `paper1/semantic_memory/grounding.py` | 逐字引用、角色、turn index、字符跨度的可核验原则 | 引用和结构通过不蕴含归一化事实；不能授权心理推断 |
| `versioning.py` | 继承明确版本父链及过去可见性 | 旧`conflicts_with`也会使较早记录失活；新解释保留冲突，不自动认为更新者为真 |
| `input_projection.py` | 离线构建只看当前源会话及严格过去已接受项；无测试问题/答案 | 旧离线禁词含question/target/evidence等，不能照搬为禁止在线合法用户目标；两种投影分开 |
| 旧MP/ME错误/U1 | 主体、行动阶段、日期、更新的回归动机和评价边界 | U1严格JSON0/6及后续语义错用保留，不能把CPU候选说成真实模型更新成功 |
| P1表示修复 | 保留latest native user与历史来源角色隔离；GSWS在原RAW基础上附加未验证解释 | 表示修复不能证明G已理解历史支持者角色 |
| P2执行器与9月LoRA | 单加载、checkpoint、LoRA参数隔离、请求与终点日志可用于未来另立训练身份 | NLL下降、EOS和格式通过不等同支持质量提升；不把旧adapter直接当更强语义模型 |
| SC36可核验反馈 | 严格JSON、来源/字段约束、原结果分解；同一语法mask基础 | SC36有限结构化成功不迁移成自由文本或自然支持reward |
| 既有Judge/NLI/人评 | 保留失败、unknown和暴露身份；明确事实可用原有限校准辅助 | 不启动万能Judge竞赛；助手历史审阅不晋级独立人评；五项待复核不动 |
| BC/PPO、FiniteHeadEnv、终点表 | 将来复用动作mask、终点绑定、训练/评估分离和算法接口 | 本次无训练、无可训练自然支持reward；静态子集终点不证明读后序贯价值 |

## 为什么过去的强模型、结构化Memory和LoRA没有解决问题

八月Qwen3-235B语义编译器方案明确source-only，且区分抽取、逐字grounding和语义复核。它使用同一模型抽取/复核，文件本身就注明不独立；JSON object也不等于严格语义schema。`GroundingResult.valid`核实的是角色、引用、跨度与结构，不能证明自由文本中的主体、因果或结果真实。旧ME定义很窄，要求已执行方法及用户报告结果；大量候选不准入不能简单解释为“没有记忆价值”。这套机制没有给当前目标条件化的PM/G共同理解带来独立资格。

八月Step-2即使结构通过，仍出现角色归属错误；旧MP有时间顺序/版本问题，当前U1也未完成合格的模型语义链更新。结构化字段使错误更可检查，却没有消灭错误。P1的来源角色和最后user位置修复解决了部分表示诱因，仍记录历史支持者被归为自身等残余错误。

9月训练155条弱监督回复（103训练/52开发），只覆盖0/1/2 GET，缺少3/4 GET。原LoRA三轮训练的NLL下降不是独立自然质量证据；EOT及人工可确认错用也不能由语言模型损失掩盖。P2另用493条弱目标训练了新adapter，证明更完整的执行链可运行，但语义目标仍有弱标注、角色和评价限制。不能把“曾训练过LoRA”当作主体/阶段/来源理解已经合格，更不能用同一批弱回复再训练一次寻求正结果。[9月结果](../PM_RL1_COVERAGE_TRAINING_RESULTS_20260930_ZH.md)、[P1](../PM_RL1_P1_REPRESENTATION_RESULTS_20261001_ZH.md)、[P2](../PM_RL1_P2_EXECUTOR_RESULTS_20261001_ZH.md)。

历史Judge暴露同样持续存在：稳定性不是正确性，单一共同参考不独立，支持行为标签不是支持质量。当前主线因此把语义理解和资源使用重新列为待验证对象，而不是增加一个新名字后宣称历史问题消失。[已有历史瓶颈审查](ge2_v1/HISTORICAL_SEMANTIC_BOTTLENECKS_ZH.md)。

## 依赖身份与复现边界

本轮独立分支`pmrl1-j/gsws-phase1-20261126`；历史journal分支及所有A/B/G树保持原样。新执行器是冻结GE2 packages-v2闭包加GSWS文件，**不能把新的公开提交当作单一完整本机运行栈**。

原组合栈来源：Journal基线`b07db1046c948a77643a646bb845a21e74c10044`；A `df21b11c96165c1a3dd8ef0edf76df2788ee3e45`；B `7eeff1cf8dcd889e4a08e9a2a723dbe3f864e118`；G `73fdb12f29b6970a268eeda704d73e1bd35b1c3e`。GE2后续新增文件的实际字节由旧packages-v2 inventory固定，本轮再以642个project文件及vendor/runtime哈希绑定新执行器。来源台账、私有任务、tokenizer、模型权重和HF环境均需本机依赖，GitHub不含RAW/gold。

[完整依赖版本和文件SHA](gsws_phase1/DEPENDENCIES_PUBLIC.json)；[四包固定身份](gsws_phase1/RUN_MANIFEST_PUBLIC.json)。运行时校验实际import模块字节，旧stack的journal符号链接仍指向旧工作树，不可误用它来执行新代码。CPU复跑和实际运行都应从本次冻结executor的PYTHONPATH启动。
