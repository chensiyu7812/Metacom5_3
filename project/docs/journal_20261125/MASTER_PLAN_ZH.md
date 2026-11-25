# PM-RL1-J：期刊收口主方案（2026-11-25）
状态：RESEARCH_PROPOSAL / 实际数据开发探针已执行 / 尚未获得研究级效益。以 J00 审计为起点，不修改历史协议、H0、C0、旧研究结论或已有运行授权。研究者采纳后执行本方案；模型运行需按既有机器安全及身份约束单独批准。此分支不是 A/B 的合并结果。

## 0. 科学问题、边界和最小成功定义
研究对象：具有长期个人知识（MP/ME/MS）与外部支持方法知识（RS）的非临床支持 Agent。研究在给定当前用户对话、资源目录、有限读取预算时，如何决定读取什么、读后继续还是停止。G0e 固定，Step-2 隐式，无临床诊断或疗效主张，无跨轮真实用户转移、多模态或主动服务。PM+Generator+资源+运行时是一个 Agent。GET/STOP 每头至多一次；本版先不增加 EXPAND/重复 GET。读后决策和跨会话记忆不是跨轮 RL。
主 RQ：
- RQ1：可追溯的个人知识和专业方法知识，是否具有可验证的条件能力增量？区分资源不存在、存在但不可用、检索遗漏、表示遗漏、应用错误、自然支持无明显增量。
- RQ2：在相同 G、候选信息和预算下，真实资源供给与组织方式有何影响；M×RS 的互补、冗余和失配是否存在？
- RQ3：预算下学习获取能否提高可验证任务成功率/降低错误或成本？序贯读取是否超过 OneShot、普通工具调用 Agent？PPO 相对等反馈 BC 是否有增量？
- RQ4：在独立自然支持与官方记忆评价中，最终系统能否保留互动质量；实际端到端代价如何？
期刊候选贡献：①源证据与方法适用性约束的异质资源组织及其干预证据；②个人知识—程序性支持知识联合获取与读后信息价值的学习机制；③可复现的分层能力/错误/成本测试与自然对话外部验证。并非首次 RAG、memory、skill 或 RL。至少应有可靠的资源能力证据和相对有竞争力的基线的可辨别增量（质量、可靠性或效率之一且其他指标满足预定保护条件），才能写方法有效性主张。全部机制负结果时，只能报告边界/测量研究，不能保证作为原定方法论文发表；禁止以一个代理 reward 提升冒充贡献。是否达到统计精度、非劣界与投稿条件在 J10 评估；不承诺正结果。

## 1. 固定现状与本轮实际证据
原始本地审计 V/journal-j00-20261125，136 资产，26/26 核验，非重新运行结果。代码底座 integration 320a33d1d871199d171f998300ce926b341ca1a8；A df21b11c96165c1a3dd8ef0edf76df2788ee3e45；B 7eeff1cf8dcd889e4a08e9a2a723dbe3f864e118；G 73fdb12f29b6970a268eeda704d73e1bd35b1c3e；历史 M 10307c62f5175fcad62558e9e20d4d881b3d9238。PR #23/#26/#27 未合并。G0e 有书面有限研究身份确认，E6 已签收，不再重复。A0 4 OFF 和 PP1 16 请求未见真实运行回执。R3/R4 已修待独立签收，R1/R2/R5 未解决。64 MP/ME 候选、SUM 0、METHOD 0 为正式语义批准现状，不因开发探针改变。

实际数据探针：project/scripts/rl1v3/journal_source_probe.cjs（真实源文件通过 GitHub blob 读取，在网页连接器的 JS 运行环境执行；只输出统计、不发布原文）。EvoEmo 18构造人物、401会话，4,119个有严格过去且当前seeker下一轮为supporter的切点；QA 1,427行，1,420唯一规范问题哈希，355 owner/question-group；IE309/TR284/CD267/Abs261/UM306。260无证据引用；1,144非空且全部引用可映射至来源会话，319涉及多会话；18部分可解析、5完全未解析。现有词面公式适配到全文QA全历史诊断（不是生产检索执行或as-of结果）：1,144题中Top1任一来源336/1144，全部256/1144；Top4任一684/1144、全部520/1144。问题分组与证据时点不可混同：在非空且组名为会话的题中，仅80题所有已解析来源严格早于该组会话，989有同会话或更后来源；必须依据官方问答语义冻结cutoff，不用组名假定前缀时间。
AnnoMI-full.csv 实际13,551行、133 transcripts、119归并视频地址组、110高质量/23低质量会话；6,826支持者话语；simple/complex reflection 1070/951，open/closed question 1340/973，information/advice/negotiation/options 690/246/199/81；4,743个相邻client→therapist位置（其中高质量4,331），过去3个client话语同时有change/sustain标注的代理情境288。视频组确定性80/20近似划分：96组3932训练位置、23组811测试位置，重叠0。预测已观察支持者主行为（非正确策略/收益金标）：多数类262/811=32.31%；词面重叠context247/811=30.46%；case223/811=27.50%；client词面余弦229/811=28.24%。仅说明这种词面相似的开发诊断不能证明适用性；原词面公式采用同分时输入顺序的适配，不是生产record_id tie-break，不能称为复现旧RS完整结果。无模型生成、无模型训练、无GPU、无Judge、无临床结果。以上数据划分均已有开发暴露，不称独立确认。
源身份以脚本内固定 Git blob 为准；原始数据留本地受控目录。AnnoMI扩展论文Data Availability称数据Public Domain，示范视频取得同意；仍需本地文件来源和适用范围登记。TIP35 2019 NCBI公开报告 Public Domain（NBK571071，Chapter3 NBK571068），原始领域为物质使用治疗，仅适配低风险非临床沟通。LongMemEval-cleaned 官方HF dataset标MIT（采用固定revision，先 oracle 及 S；M不是必需）。不把论文可见性当成其他资源许可，不外传RAW。

## 2. 立即行动：从准备转向真实试验
J00 CLOSED，不再整体盘点。研究者如采纳，授权A/B CPU开发、从上述公开源取得所需固定文件并本地使用（不得扩大既有数据发布决定），A0单独批准后尽快实际执行；PP1在原准入满足后单独运行；J02/J03/J04准备与PP1并行。不得把自然支持显著正收益作为QA/RS行为机制开发的门槛。已有E6、G0e同身份不再签收。
三条工作流：
- A-run：使用#23 67169816干净checkout、原A0 plan 43f175c5…和binding c9eb9169…，按原4次OFF及1200s硬上限、1 load、0 retry，启动前查设备独占、磁盘、模型SHA、日志。PP1仍为原8×2=16请求、原renderer及独立授权，未达准入不跑；A0失败只修实际技术原因，保存日志，新身份不覆盖旧。J04新研究调用另立manifest；任何改权重、解码、renderer为新实验身份。
- A-resource：取得Annomi-full.csv、TIP35 Chapter3/6或相关准确小节、许可元数据；本地跑source probe重算；编译MS/MP/ME及RS小集，接现有PrefixPort。
- B-task：完成R1/R2/R5、R3/R4交叉验收（仅在线学习前置）；并行建设实际任务/评价，先使用QA源引用，再用独立方法任务。B不用等自然人评。原DP UI仅修阻碍真实PP1/FC-MS的bug；不扩大界面工作。
A/B交接：每次交固定HEAD/依赖、输入输出manifest、实际命令、stdout/失败记录、对方复验。协调者先在临时集成工作树组合A、B、G依赖，确认共享C0字节不变；不把一条线的HEAD当全栈，不自动合并任何PR。

## 3. 数据入口、最小代码改动
先复用A sources/source_registry.py、compile/asof.py (PrefixAsOf/SourceFrontier/Ledger/ materialize)、compile/qualification.py、bank/v0_port.py、retrieve/v0.py；G render/request_packet.py；B env/finite_head.py、asof/binding.py、evaluate/terminal_registry.py、train/real_instances.py、train/supervised.py、train/ppo.py、needs/checklist/judge/review。C0 0.2.0不改。
建议新增 rl1v3/journal/ 下的薄层，而非平行重造：source_adapter.py（四源解析，QA证据resolver仅评价侧）、writer_adapter.py（映射既有Ledger）、skills.py（SkillRecord及审查状态）、port.py（As-of及技能读取适配）、tasks.py（TaskSpec）、evalspec.py（私有目标）、checkers.py、outcome_adapter.py（现TerminalRegistry/RealInstance桥）、baselines.py（Tool Agent）、report.py。现已有功能则用现有模块，不建立空壳重复。
TaskSpec runtime：task_id的opaque标识（或执行器私有）、当前可见对话、合法prefix identity、public inventory、预算；不得有任务类别、目标技能、gold证据、答案、needs标签。EvalSpec私有：task_id,source_family_ids,origin,cutoff,requirements[{id,criterion,allowed_alternatives,source_locator,verification_type}], prohibitions, optional, answerability, evidence_sets, rubric_version, review_state。任务分层只用于生成前抽样及分析。任何来源/角色/时间/任务/评分变更写新版本、保留原始输入。先用 allowlist 序列化，做 canary 泄漏测试，禁止敏感字段通过日志、payload、特征/embeddings、mask或长度编码泄漏。目标答案不能被任务模板注入前缀。
从源历史读入：source immutable→每完成会话才写 ledger→prefix cutoff物化。保留event_time/reported_at/ready_at/valid_from/valid_to及主体、来源。对旧324隔离MP不解隔离，旧bank只作历史baseline。首版 Writer 对机械可核验的原文引用和模型生成的语义主张分开：不得把所有派生断言自动批准。可新建 SOURCE_EXACT 开发视图（引用可证、标明未知；不是官方人工批准typed claim）；若正式用自动抽取，新增研究身份、来源忠实性/错误率的分层校准、明确失效/fallback；不能修改既有human_approved gate来假装已审核。MS原文作为第一可读头；8摘要试验为开发，比较源命题覆盖和错误，若损失关键证据则RAW，新增摘要不得从未来生成。先运行小规模真实Writer/summary模型候选（需授权），不要求401会话全部人工审核。
RS：独立方法知识库，不把案例当用户事实。SkillRecord {skill_id,version,source_refs,original_domain,adapted_domain,objective,required_observable_conditions,exclusions,allowed_moves,conditional_steps,stop_conditions,prohibited_moves,positive_case_ids,negative_case_ids,review_status,license}. CASE保留源video_family/可见前情/专家行为标签/后续反应（仅审计，运行时不得把目标用户未来或标签泄漏），不以MI质量直接判断单个行动是否最优。先构建六类低风险候选：双向顾虑、反映、尊重自主、许可式信息、用户主导行动、拒绝后的调整；每类1个METHOD/PROCEDURE，2–4个来源不同CASE或反例。用TIP35准确小节+独立AnnoMI标注验证内容，原有3草稿、12ESConv仅开发/legacy。专家只需审核方法的非临床适用边界，不为所有终点打主观分；若专业审核无法取得，限于可验证的沟通行为研究，不称专业资格。资源未核准保持隔离。
Renderer必须解决一个实质问题：G0e的Notes将外部内容视为数据而非指令，不能直接把专业方法当可执行系统指令。新的journal renderer保持相同固定系统基线，明确区分历史事实/外部可选方法/外部示范；方法为有边界的可选指导，不得覆盖用户明确要求、安全规则或身份；CASE不是个人历史。所有实验臂使用同一新renderer身份，OFF空块不附额外信息；另保留旧G0e渲染对照用于检查差异。新G0e renderer不是旧PP1身份，不允许复用旧奖励。
检索：首先Direct（评价特权诊断）与真实RET区分；RAW、SUM、typed同源；语义检索BGE已存在但必须绑定模型版本，开发对照lexical/BGE/混合（不要用测试题调参），RS目录少时比较基于可见条件的选择与常驻F，不强做大型向量库。所有读取私有结果、失败、耗时均记录；工具planner和学习策略共享端口、可见字段、可用资源、预算。现v0在legal mask中做读/测量，可能产生预取成本和泄漏；明确 mask只给可用性/合法性，预取实际耗时计入所有策略，禁止暴露未读正文/分数。若每个头固定Top1且相同子集生成完全一致，只是有界部分可观察获取，不声称学习了检索重写或顺序本身改变G。

## 4. 第一次真实科学实验：小规模并行，两条独立证据线
以下规模均开发预算，事先冻结，结果不作最终确认或真实用户疗效。先实际执行J01；J04须新请求manifest及独立批准，不能把4/16授权挪用。先做每臂2个请求的技术冒烟（包含在开发总量内），只看结构/容量，科学失败不重抽。停止按异常/授权/资源预算，不按结果好坏。
M-pilot：30个开发QA（四种answerable能力各6，加6 abstention；尽量覆盖12个多来源题，若覆盖不足登记而非补造）。按已冻结owner/family开发折、能力、证据数、合法性、固定hash选样，不使用旧14事实题或回复结果择优。官方v1.0.0 1427题为版本化对象，不写成论文1209题。使用原问句及原gold，不加答案信息；只有官方语义证明可用的完整历史才当任务输入，明确 end-of-history QA vs prefix QA；不能用group id推定cutoff。解析每个引用为原会话/turn或event→来源会话，后者只是候选，不能把event gold文本注入；未解析引用单列。Gold来源集合仅评价/DP；禁止正常RET、PM看到。OFF、DP（合法标注证据来源集合）、RET（预冻结Top4，预算限制）、matched-other（同owner非标注来源、尽量等长，不能断言无用）4臂×30=120 G上限；DP预算不足或没有合法证据记录不可达，不伪造/用更易题替换。另在可读同源样本比较RAW/SUM/typed的独立小包，最多12×3=36请求（复用同身份）。报告答案准确率/错误/拒答，gold evidence hit-any/hit-all、来源合法率；证据hit-all不是必要性/充分性证明。答案若自由语义只用合格独立判定；无法确定为unknown；分开官方评估和严格可核验子集。已知11/11 14事实题的OFF 0、DP 13、BGE top1 10/top2 12只作开发先验，不能迁移到G0e。
RS-pilot：12个不同video_family的低风险来源情境，覆盖六候选技能每域2个家族，每个生成原目标+仅改变明确用户需求/许可/时机的最小反事实（24个任务；明确为constructed，不是原始临床任务），保留普通/不适用/不确定反例。方法知识、示范素材与任务分组隔离；源标签只作行为识别监督，不作为“下一动作必须复现”的金标。通过明确目标、禁用行为、可接受替代方式判断，不要求术语或固定回复。6臂：R0、等质量Generic、Legacy-RS、同源Professional RAW、Method、F-resident（同一小技能库常驻）×24=144 G上限；方法+CASE条件另立至多24请求，仅在预定的表示问题触发，保留全部开发结果。对比RAW vs Method时保持同源并记录token；F-resident同内容范围但不强行等token。所有临床特定目标排除出日常支持任务，危机走独立安全处理。先用已有标注训练/验证支持行为分类器（见第5节），以可核验的行为/约束成功率、错误与自然质量保护测量，不用一个“MI忠实度分”定义真实帮助。
联合-pilot（J06）：24个新开发前缀/任务，按生成前来源条件均衡四种信息需求：只记忆、只技能、二者、二者都不要求，各6。来源不足报告，构造任务明确标记。Memory固定为按任务合法选定且对所有臂同一的资源组合，不按生成后赢家选。M0R0/M1R0/M0R1/M1R1四格×24=96请求上限。若单臂尚无研究级收益也可作为机制负对照，但不得声称协同。交互 Y11−Y10−Y01+Y00；同时报告各条件、分层、错误、成本，允许负交互。四格相同生成配置和预算口径，不能以四种不同语言或prompt混杂。
早期新增开发最大计划：M120 + 表示36 + RS144 + 条件Case24 + Joint96 =420 G（不包含A0/PP1及后续训练表；每次按实际可达/精确复用扣减；不是授权）。使用A0实测每token速度、长度分布和作业加载开销推算批次时限；分批、GPU独占、无自动重跑。任何预算扩大须记录新版本。
自然线：保留PP1/FC-MS-1与旧QH/Q0/F、S1主比较、既定缺失/分组/盲态/判定规则，另立身份而不重写协议；主观显著性不阻塞上述受控开发。最终报告中自然线与GST线完全分开；不以受控成功替代自然支持好感。FC-MS统计组最多17，现有功效有限，不宣称不显著=无效。

## 5. 评价和训练信号：不是全靠人评，也不是拿自动标签自证
E0硬工程不变量：hash/时序/角色/许可/预算/泄漏/非法GET等；失败不可给正奖励。E1确定事实：答案类型、实体/日期/数量/明确否定、明确用户限制，可程序判定者用精确规范化+别名（拒绝靠字符串匹配复杂语义）。E2语义约束：每项pass/fail/uncertain及证据；允许合法替代，不要求显式提及历史、引用策略或复现单一金回复；不适用任务不会因调用RS本身被判失败。E3自然互动：Q0/QH/F、ESC-Eval官方维度，单独报，不合成自造总分。正式的证据核验和行为评价器必须独立于资源编译模型和测试输出。
AnnoMI可直接检验行为分类器，而非训练帮助性Judge。以视频家族切分（当前探针96/23已开发暴露，另冻结交叉验证/后续独立组）；原始支持者话语输入行为识别器，使用专家主/子类标签，先majority、TF-IDF logistic，再选现有DeBERTa或本地模型小样本；识别指标macro-F1/每类precision recall/confusion，罕见类单独。使用源标签、反例和人工核验的最小改写校准程序与语义约束；不要用“预测下一句专家标签”当最优行动或完整质量奖励。支持行为标签不能代替任务目标。选用机器可核验事实/显式约束作为主训练通道；自动语义评价有可靠性/覆盖门槛后才纳入，至少固定开发/独立校准集合、评估各类false-pass、false-fail、abstention coverage、95%区间。目标建议：关键事实反例零容忍的工程拒绝；统计资格不能用0观察宣称0风险；校准预算先60–100原子项（平衡pass/fail/uncertain、来源家族、任务域），阈值由开发集和研究者在确认集揭晓前冻结；不够精度就只用确定事实/约束，其他保留区间和有限人评。自然回复少量独立双盲验证，记录审阅者差异；不要把以前单一研究者的17 ties当人群标注。
任务级 Y：所有预定必要目标满足、没有预定禁止项则1，明确必要项失败则0，未知且未有确定失败则pending/区间[0,1]，技术失败独立状态。严重安全/来源错误为硬约束（失败保留）。收益按匹配状态：修复OFF失败率、引入OFF成功→失败率、净差、真实成本。未知不填0；分母固定，报告完整覆盖和上下界，不能各臂独立剔除unknown。只有完整可比较、奖励资格已确认的终点表进入RealInstance，训练/测试按同一预定缺失处理报告排除覆盖和敏感性；若未知太多则停该奖励线，先修可验证目标或限定研究范围，不能调Judge到满意。
统计单位：EvoEmo17个连通owner/family组（p13/p18合并）而不是1427独立人；AnnoMI视频/跨源家族；构造变体共享家族。正式评估在新一轮设计冻结前锁定fold、seed、抽样、主比较、最小有意义差异、置信区间和多重比较；现有开发暴露登记不宣称全新独立人群。开发用group-level bootstrap/配对差和错误分析，不能将几次输出当独立样本。最终另做6折组外训练/测试（同族不可跨折）或新的独立数据验证；明确既往曝光。

## 6. J07/J08：只有发现可学空间才运行正式学习
首先对冻结任务及真实RET运行全部合法subset终点：四头至多一次，最多16子集/65顺序，缺资源或预算不足按合法掩码减少。不把DP/理想证据注入实际终点。首个开发表48前缀×≤16=≤768 G，先检查小表完整性和逐条来源；三种子CPU学习可重用同表，不能算独立用户。先计算每前缀受预算约束的oracle上界与训练折Fixed-best差、每种资源条件边际效果、各类任务的可行成功/失败覆盖、区间。oracle只作诊断；如果oracle与固定策略无可辨别差异，不做无意义PPO。
状态只含当前前缀、已取得ReadingView、合法availability及已用预算；资源目标、未读正文、gold、来源家族身份、隐藏答案、终点表/得分不进入策略特征。保留真实action traces和真实每路径成本，canonical subset G输入共享仅在字节完全一致时；顺序成本仍需实测。若查询随已读文本更新、重复GET/expand则另立新动作域和终点身份，当前不默默扩展。
策略先比较 OFF、ALL（可达）、训练折Fixed-best、同预算Random、legacy Top-k/Rule、F-resident、OneShot、同端口LLM Tool Agent（额外规划调用成本全计）、Seq-BC、Seq-BC-NoText。PPO与PPO-NoText、等反馈BC-union在共同训练数据、反馈/环境交互次数、种子、模型容量、优化预算下运行；学习目标任务成功−预冻结成本权重或预算网格，安全/事实硬约束独立。不要仅用cost代理训练然后主张支持改善。学习率等超参在dev确定，held-out只跑冻结方法。三种子各自报告，不能选择最好seed。
关键机制检验：真实任务中相同或相近初始可见信息、不同读后证据是否有条件增量；为同一合法历史设计有来源的最小对照改变资源内容/可用性（单列constructed、同家族）；检查NoText、OneShot在相同观察及预算下是否明显损失。固定检索结果情况下顺序不改变最终子集回复，不能把枚举DP当序贯优势。若OneShot相当，报告静态选择足够；若PPO不优于BC，采用简单策略，RL非必要。若仅oracle强而学习弱，检查observable signal、标签不确定、分布/样本和特征，再允许一次基于明确根因的开发修订；最终确认集不调整。

## 7. J09/J10：正式评价及发表证据
冻结最终G/renderer/资源/检索/策略，选择不依赖测试结果。主确认任务规模根据开发效应/独立组方差/预定最小有意义差异做功效分析；建议起始规划120–240受控任务（各域分层、独立组优先，若无足够来源不凑数量），单次生成上限16×N仅在确需完整表的子集，外评运行真实策略不穷举。若新AnnoMI开发暴露过多则用未用于方法开发的视频组或新来源；独立LongMemEval-cleaned oracle/S检验记忆检索，QA与ESC能力分开。ESC-Eval官方ESC-Role/ESC-RANK冻结版本和角色卡，ES-MemEval官方QA/summary/dialogue的适用任务及指标，保留1427 vs1209差异；不能用自己GST分冒充官方结果。自然盲评只抽预冻结代表性成组样本、少量自动语义争议，不把全16子集都交给人。真实时延：初始化/编码/检索/PM/Generator首token/首有效内容/完整回复，Tokkio可行时首语音，报告p50/p95、超时/失败及输入输出tokens、调用数；3秒额外等待暂定约束，若未完成真实链路仅报告组件。QA/RS/自然三线不能相互代替。
论文表：T1资源组织与来源忠实性；T2真实资源收益及DP/RET差；T3 M×RS四格、交互与适用性；T4同预算策略/强Agent基线/消融；T5官方外评与自然盲评；T6实际耗时、故障与成本。完整负结果和未决项进入附录。根据实际结果选择可支持的主张：①专业技能无增量→保留诚实负结果，若RAW有效修结构；②直接有效但RET无效→检索/适用性；③RAW/SUM/typed有效但G使用不稳→新renderer或有限显式Step-2/条件SFT独立试验（仅一次根因驱动开发，仍固定G主线）；④F-resident相同且快→采用常驻，不强称动态RS必要；⑤所有RS无增量→不要降低G制造效果，收窄领域/报告失败，不得把memory-only假装双能力贡献；⑥自然支持不理想→限定受控能力主张，不声称帮助改善；⑦策略/RL无增量→报告简单策略或放弃原定方法主张。最终是否投稿需研究者根据证据判断。

## 8. 执行记录及 Codex 启动方式
J00现有6份产物仅保存在实验机，不复制到公开GitHub。本方案作为独立提案，采纳后建立JOURNAL_EXECUTION_STATE v2（单一协调者负责，保留J00状态），每一包记录 proposal/frozen/running/complete/failed/inconclusive/pending、代码与数据SHA、调用额度、证据级别、失败与重跑规则；不触碰旧状态。新增资产以manifest记录，公开只提交代码、方案及聚合结果，不包含RAW/私人评审/答案或权重。
第一批A任务：并行处理A0已准备的真实运行申请及DP UI bug；取得并解析实际AnnoMI/TIP35，执行journal_source_probe.cjs；核对输出、形成6个技能候选和源定位；现有As-of Writer/port增加SOURCE_EXACT开发适配，实际输出12–24个合法prefix下的真实读取；给B所有新身份及可读接口；不要等待全部401会话编译或所有人工审批才准备小实验。A0已确认身份及E6不再重签；实际运行须单独批准。
第一批B任务：R1/R2/R5修复与R3/R4验收；并行实现证据resolver/TaskSpec/EvalSpec/checker及30 QA+24 RS抽样manifest（只用生成前条件）；使用AnnoMI实际标签进行行为识别器开发/校准；用同源真实案例检验评价器错误，完成M/RS pilot每臂请求清单和预定统计脚本。先冻结后申请执行。真实数据/评价缺失明确标注，不以mock冒充。
协调者：不要重新J00；每包至少一次实际数据运行或测试，报告真实命令、输入输出计数和失败。优先解锁首批A0+M/RS开发生成，不扩大人工评审和重建优化器。每一项既有授权仍按原边界，不代签，不启动收费API或擅自占用GPU。完成开发后依据实际结果推进J05–J10；如假设失败按第7节处理。
