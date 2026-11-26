# PM-RL1-J：相关工作与可检验贡献审查

检索日期：2026-11-26（Asia/Tokyo）。工作起点：`0f3d9842d5b1a5e7e211c319beddc7477705ff76`。本文是公开文献审查及新研究身份的贡献候选分析，不修改历史协议、任务、评分或结果。未读取本轮私有源、未运行模型、未执行训练。下载了 8 份公开 PDF（7 项工作，其中 Memory-R1 保留两个版本），逐份 SHA256、原文 URL、阅读范围及仓库快照见 [RELATED_WORK_SOURCES.json](RELATED_WORK_SOURCES.json)。

**判断：新的 SEARCH / EXPAND / STOP 动作名、POMDP 表述、RL、结构化 memory 或“读后继续搜索”都不足以构成独立贡献。** 最接近的机制先例是 MemRetriever；最接近的支持任务先例是 ENPMR-Bench；状态维护与证据核验需正面对照 ProgMem。可继续检验的空间是：在相同真实资源、信息边界和成本下，目标与读后证据是否共同改善获取决策，并将事实正确、支持要求、额外错误和成本分开验证。这个空间目前是研究假设，不是已证实的新颖性或有效性。

**1. 论文身份与可复核范围**

| 工作 | 已核对的正式名称、版本 | 实读依据 |
|---|---|---|
| ENPMR-Bench | Fu 等，*ENPMR-Bench: Benchmarking Proactive Memory Retrieval for Emotional Support Agents*；Findings ACL 2026，2026.findings-acl.2080，41910–41933 | [正式页与 PDF](https://aclanthology.org/2026.findings-acl.2080/)；§3–6、Limitations、附录 B.1–B.2；[官方仓库](https://github.com/xingqwq/ENPMR-Bench/tree/f46921bc42c14c1cc57d68a364bee7a3a7dcc1d2) |
| MemRetriever | Jiang、Li、Li，*MemRetriever: Learning to Search, Reflect, and Retrieve from Long-Term Memory*；arXiv:2609.11951v1 | [arXiv 元数据](https://arxiv.org/abs/2609.11951)、[版本原文](https://arxiv.org/html/2609.11951v1)；§3–7，尤其 §3.2 奖励与 §4.1 工具循环 |
| ProgMem | Zheng 等，*ProgMem: Programmatic Belief-State Memory for Long-Horizon Conversational Agents*；Findings IJCNLP-AACL 2026，2026.findings-aacl.120，2363–2376 | [正式页与 PDF](https://aclanthology.org/2026.findings-aacl.120/)；§3–4、Limitations |
| Memory-R1 | Yan 等，*Memory-R1: Enhancing Large Language Model Agents to Manage and Utilize Memories via Reinforcement Learning*；ACL 2026，2026.acl-long.583，12805–12825；另保留 arXiv:2508.19828v5 | [ACL 正式版](https://aclanthology.org/2026.acl-long.583/)、[版本历史](https://arxiv.org/abs/2508.19828)；§3、§4.4、Limitations、附录算法及延迟分析；[官方代码](https://github.com/yansikuan/memory-r1/tree/f5ca10a45a08320b60575010c622fed6d3b3c686) |
| Active Feature Acquisition，代表方法 | Shim、Hwang、Yang，*Joint Active Feature Acquisition and Classification with Variable-Size Set Encoding*；NeurIPS 2018 | [正式页与 PDF](https://papers.nips.cc/paper_files/paper/2018/hash/e5841df2166dd424a57127423d276bbe-Abstract.html)；§3–5；[官方实现](https://github.com/OpenXAIProject/Joint-AFA-Classification/tree/55811e71376ed6d90a4f2012694cb3891ac48a56) |
| AFA，评价与识别 | von Kleist 等，*Evaluation of Active Feature Acquisition Methods for Time-varying Feature Settings*；JMLR 26(60):1–84，2025 | [正式页与 PDF](https://jmlr.org/papers/v26/23-1635.html)；§3.1、§3.5、§9–10及各识别视角的假设入口；未声称复核全部 84 页证明 |
| Dream to Chat / DreamCUB | Zhao 等，*Dream to Chat: Model-based Reinforcement Learning on Dialogues with User Belief Modeling*；Findings EMNLP 2025，2025.findings-emnlp.256，4764–4781 | [正式页与 PDF](https://aclanthology.org/2025.findings-emnlp.256/)；§3、算法1、§4、§7 |

身份核对得到三个需保留的差异。MemRetriever 官方 abs 的提交历史和 HTML 均显示 **2026-07-29**，但标识为 **2609.11951**，abs 的浏览月份也指向 2026-09；本文原样记录，不推断正确日期或据此排列优先权。ENPMR 论文 §3.3 报告 **1,872** 个支持对话，当前固定仓库 README 报告 **2,692** 个 dialogue records；两处都报告 11,846 条 memories。后者是 README 数字，本轮未重新计数数据文件，不能混为同一评价集。[MemRetriever 元数据](https://arxiv.org/abs/2609.11951)，[ENPMR 论文](https://aclanthology.org/2026.findings-acl.2080.pdf)，[固定 README](https://github.com/xingqwq/ENPMR-Bench/blob/f46921bc42c14c1cc57d68a364bee7a3a7dcc1d2/README.md)。

Memory-R1 的搜索缓存仍可能显示“代码即将发布”，但当前固定官方 README 已给出 Memory Manager、Answer Agent、训练及评价目录和执行流程，因此不能再以未开源为理由排除它。MemRetriever 指向的 MemOS 是完整记忆系统仓库；本轮核对 README 及固定递归树，没有确认与该论文训练权重和流程一一对应的发行物。ProgMem、DreamCUB 的已读论文及有限精确标题搜索未定位官方实现；这只是本轮定位范围，不证明代码不存在。[Memory-R1 README](https://github.com/yansikuan/memory-r1/blob/f5ca10a45a08320b60575010c622fed6d3b3c686/README.md)，[MemOS 快照](https://github.com/MemTensor/MemOS/tree/3a16e5fe3048a209f722806f4123fa2e533588fd)。

**2. 方法层面的直接重叠**

ENPMR 是需求驱动检索的诊断 **benchmark**，不是已经学好的获取策略。§3.1 要求每轮召回一条相关记忆并用于回复；其需求到记忆类型的映射和目标记忆参与构造。它直接排除“首次把情绪支持目标用于个人记忆检索”的主张，但不能直接回答应否读取或何时 STOP。论文明确映射是理论和专家设计，尚非实证最优；短合成对话及小规模人评限制了真实支持效益外推。[§3–6、Limitations](https://aclanthology.org/2026.findings-acl.2080.pdf)。

MemRetriever 是独立于回答模型的获取 **agent**：根据问题、已有证据及工具历史生成 parallel/serial 查询，以 reflection 去噪并决定 `done:true`。SFT 后用 GRPO；搜索奖励含证据覆盖增量与查询成本，停止奖励连接下游答案。它与拟议的目标条件化、读后补缺、充分性判断和停止高度重叠。§6 有同三工具流程的策略模型比较；QA 表混列不同原协议和指标，不能据表宣称统一条件下全面领先。表中 token 与正文主要讨论最终证据压缩，不足以确认全部搜索、思考、工具及回答的端到端成本口径。[§3.2、§4.1、§5–6](https://arxiv.org/html/2609.11951v1)。

ProgMem 编译对话事件为写程序，维护 stable/dynamic/plan 状态及原文锚点；按问题路由检索，再核验状态答案与来源，不足时 Unknown。图中的 refinement 属于入库程序编译，不能误读为读取后改写检索 query。它已覆盖更新、计划取消、溯源和拒答；两阶段消融同时移除锚点路径与仲裁，不能隔离其中单项。其平均/P95 延迟高于 Mem0，DialSim 大量不可答题且使用 token F1，不能把总体 F1 当已验证的有用拒答。[§3.2–3.4、§4.6–4.8、Limitations](https://aclanthology.org/2026.findings-aacl.120.pdf)。

Memory-R1 学习 ADD/UPDATE/DELETE/NOOP，并学习对相似检索返回的候选做 distillation 后回答。§3.2 使用固定检索候选，再做筛选；这与多轮 query refinement 应区分。两个代理分别训练、另一端冻结，以答案结果反馈；§4.4 已比较组件、RL/监督、reward 和 reranker。EM 与模型评价出现不同偏好，提醒我们不能把单一自动 reward 上升等同任务改善。[§3、§4.4、Limitations](https://aclanthology.org/2026.acl-long.583.pdf)。

AFA 早已把“观察当前已获信息→选下一特征或停止→终局预测”与获取成本联合优化。2018 方法中 STOP 始终可选，已读特征不可重复取，终局损失来自分类器；这是预算获取的直接机制先例，尽管特征不是自然语言记录。2025 AFAPE 研究的是回顾数据下的策略评价与可识别性，区分获取是否改变底层值（NDE）、是否存在未记录信息影响获取（NUC）及 positivity；不是另一个支持对话 benchmark。[AFA §3–5](https://papers.nips.cc/paper_files/paper/2018/file/e5841df2166dd424a57127423d276bbe-Paper.pdf)，[AFAPE §3.5、§9–10](https://jmlr.org/papers/volume26/23-1635/23-1635.pdf)。

DreamCUB 以情绪、情感极性、意图为隐藏用户状态，动作含回复策略与回复；世界模型预测后续用户状态/话语，PPO 利用想象轨迹。它已经把支持相关对话建为 POMDP 并联合训练策略、critic 与世界模型。这里的“query”常指用户下一句，不是向记忆库提交检索式；不能混同。其对话质量和人工评分不能替代真实长期支持收益；局限还将个人习惯与记忆列为待扩展状态。[§3、算法1、§4、§7](https://aclanthology.org/2025.findings-emnlp.256.pdf)。

**3. 机制矩阵**

“未确认”只表示上述原文范围没有确认该机制或对照，不是检索穷尽后的不存在证明。表格沿用上一节的原文章节与引用。

| 工作 | 目标与 query | 读／写和长期更新 | belief／充分性／停止 | 支持决策 | 成本与对照的实际范围 |
|---|---|---|---|---|---|
| ENPMR | 需求驱动选择；未确认观察后迭代改写 | 历史库及已有系统写入；不训练统一读写策略 | 每轮必须选记忆，未提供可选 no-read STOP 目标 | 核心评价对象 | Base、CoT、golden；系统候选范围不完全一致 |
| MemRetriever | 明确依据目标及已获证据补缺 | 多轮读、筛选证据；未确认学习持久库更新 | 明确 evidence sufficiency 与 done | 主要为记忆/多跳 QA | 查询成本奖励；同工具策略比较；全端成本待核 |
| ProgMem | query 路由；未确认读后 query 重写 | 写程序、时序/计划生命周期、原文锚点 | typed state、核验、Unknown；非通用 learned STOP | 主要为对话记忆 QA | 入库/注入 token、延迟；路由/核验消融 |
| Memory-R1 | 问题检索后学习筛选 | 明确持久写操作及使用记忆 | 任务结果 reward；未确认反复搜索 STOP 策略 | 主要为记忆 QA | 组件/RL/reward/reranker及延迟比较 |
| AFA 2018 | 条件于已观察特征选下一项 | 获取数值特征；非记忆写入 | 明确 acquire/stop-and-predict | 分类而非支持 | 显式获取成本及分类损失 |
| AFAPE 2025 | 评价获取策略 | 时变底层特征及部分可见记录 | 识别假设，不是新对话控制器 | 不评价支持回复 | 讨论成本/错误及反事实识别 |
| DreamCUB | 当前对话→用户状态→策略/回复 | 交互状态演变；未确认个人库读写 | 用户潜在状态和世界模型；非记忆读取 STOP | 明确策略与回复生成 | world model、belief、RL 消融；非检索 noText |

上述三种状态不能只因都使用 belief 一词就合并：用户心理状态推断、符号化事实/计划状态、任务所需证据的充分程度。PM-RL1-J 如果只实现可追溯证据集合及未解决问题，宜如实称 evidence state；没有校准或后验语义时不要宣称已学到用户 belief posterior。

本轮没有在这些已读评价部分确认严格的“同调用、同预算、同位置，仅移除有效正文”的 noText 因果对照。这个有限发现不能支持“首次采用 noText”。若内容移除同时改变长度、工具状态或停止机会，差异也不能直接归为正文的信息效应。

**4. 与原 RQ 和受限动作域的关系**

[原 MASTER §0](../../journal_20261125/MASTER_PLAN_ZH.md) 的 RQ1 要求条件能力增量，RQ2 问资源组织及互补，RQ3 问学习获取与序贯相对 OneShot/普通工具 Agent 的增量，RQ4 问自然互动与实际代价。文献不能替代本项目这些实证结果；已有供证检查或 CPU 接口通过也不能替代它们。

原每头最多一次 GET、固定 query、固定候选环境，只能检验该动作域内的读后分支价值。若读后无法改变下一 query、候选或展开范围，其负结果不能证明一般序贯获取无用。新 SEARCH / EXPAND / STOP 必须另立身份并记录读后真实可改变的操作；不能重新解释旧结果。反过来，拓展动作域也不自动产生贡献，因为 MemRetriever 和 AFA 已覆盖相当部分机制。

个人历史随时间增加属于资源更新。只有策略动作实际改变后续可观察用户状态，并有对应的转移数据、评价与授权，才能主张跨轮控制或长期支持效果。现有静态历史重放不能充当 DreamCUB 式交互动力学或真实用户改善的验证。

**5. 最多三个可检验的贡献候选**

以下是本项目相对所读工作的研究定位，不是“前人均未做”的结论；不自动新增任务包或运行许可。优先检验候选 A，B 与 C 可作为同一有限试验的诊断层。

| 候选 | 可区分的具体假设 | 必需证据 | 否证与收缩分支 |
|---|---|---|---|
| A：任务条件与读后证据共同决定下一步的价值 | 在相同来源和预算下，已读内容帮助选择真正缺失的下一项证据，并改善最终任务；价值超过仅由当前目标重写 query | 同初始信息、合法池和候选预算；记录第一步观察、第二步 query/展开定位及结果；与 OneShot、目标条件化但读后不适应、普通工具 Agent 比较；按源组外评价 | 下一动作虽不同但无任务改善，不算有效；若目标条件化 OneShot 已解释全部增量，收缩为检索/查询工程结果；若 noText 同样有效，不支持读后正文驱动机制 |
| B：时态、来源与支持边界约束使获取更可靠 | 读取更新/取消/限定证据后，减少陈旧事实断言或违反明确支持要求，而非增加固定回忆量 | 证据更新前后的可追踪差异；区分事实真值、必须回答项、可隐式背景、支持行为和新增错误；允许不读 RS 或合理替代方法 | 单靠结构化表示/规则已获得同样效果，则不能归于 learned sequential policy；仅用事实 QA 不足以支持支持行为增益；不具备独立 RS 增量时不主张 Memory×RS 互补 |
| C：可归因的任务—错误—成本评价 | 同资源供给和 G 下，能区分检索缺失、表示丢失、G 执行失败与测量未知，并识别真实成本前沿 | 保留完整配对、失败与未知；等预算 noText/错配控制；供证与回答分别评分；完整获取/展开/重写/生成成本；必要的人类评价仍 pending | 若自动评分不能区分关键错误，收缩为测量局限；若成本降低依赖任务下降，不主张改进；只有开发诊断则不写独立确认效果 |

A 的潜在增量在具体可验证任务及可归因效果，而不在再次提出 active retrieval。B 的潜在增量在约束如何影响最终行为，而不在再次给 memory 添加类型。C 可以支持边界或评价研究，但不保证构成方法论文贡献。

**6. 最小否证实验与公平比较约束**

先使用已获授权的新身份下的有限真实任务，不为制造第二步优势而编造隐藏事实、遮住本来可见的信息或把成功条件写成“必须调用”。若合法池中没有独立第二项证据，记录 STOP／无第二资源的真实范围。

1. **目标条件化与读后适应分开。** OneShot、同目标 query 改写、读后条件化策略共享起点与预算。将“改写了问题”与“根据第一次结果改变了下一动作”分开计量。可以在相同初始可见信息、不同合法已返回内容的配对诊断中检验第二步是否随证据变化；若环境不允许这样的合法配对，就不声称已识别该机制。
2. **文本价值与调用痕迹分开。** noText 保留合法目录、调用历史、槽位和计费；正文替换方案与长度控制提前固定，避免从长度/标识泄漏答案。错配正文只能使用合法隔离的材料，不引入他人或未来记录。工具调用成功不能抵扣错误答案。此控制估计的是指定软件干预效果，不自动识别真实用户的长期因果收益。
3. **获取与回答分开。** 先报告所需证据是否真的返回；再用同最终证据的冻结 G 重放诊断区分供给和表达。任何参考证据 locator、正确下一动作或 evaluator 字段都只在评价端。不得用终局答案或人工引用直接生成 runtime query。
4. **强基线与训练贡献分开。** 原样可运行的官方实现优先；改编到相同接口的 MemRetriever 风格基线必须标“机制复现”，不能冒充原论文结果。至少保留无需训练的规则/工具 Agent；只有它们被公平比较后，才有理由检验 PPO 对等反馈 BC 的增量。本文未运行这些基线。
5. **预算与不确定性完整保留。** 固定 G、decode、合法池、可见输入及上限，同时报告实际消耗；计入搜索重写、工具、展开、重复读取、注入与回答，不能只计最终 memory tokens。按真实源组划分并报告配对区间；不重复抽样挑赢家，未资格化语义不转成确定 reward。

这些约束来自本项目要识别的差异，不是对所列论文已经缺失的逐项断言。对于冻结的只读库，获取通常不改变源值；对于向用户给建议、追问或施加干预，底层用户状态可能改变。后一情形不能直接沿用 AFA 的 NDE 假设；回顾日志若缺少驱动原决策的信息，也不能假设 NUC 或足够 overlap。[AFAPE §3.5、§9](https://jmlr.org/papers/volume26/23-1635/23-1635.pdf)。

**7. 可用与不可用的主张**

当前可以写：“我们在保留来源与时点约束的有限任务上，研究目标条件化及读后证据如何影响获取和停止，并将供证、最终任务与成本分开评价。”若后续公平实验支持，可进一步写出准确的数据范围、基线和效应区间。

当前不能写：“首次 POMDP 支持 Agent”“首次 RL 记忆读写”“首次动态检索/证据充分性 STOP”“首次结构化或程序记忆”“首次需求感知支持检索”，也不能写“已经优于 MemRetriever / ProgMem / Memory-R1”。代码接通、真实获取、source coverage、开发示例或形式化动作域，都不能独自证明这些主张。

如果新的读后策略仍无相对强基线的独立增量，应保留负结果，结束该机制扩张；可以将已核实的资源与测量边界作为收口材料。不得把原受限 FiniteHead 的结论扩大到所有序贯策略，也不得借扩大动作域反复重置失败标准。五项真人复核继续保留 pending，本文作者的文献或开发审阅不替代独立人评。
