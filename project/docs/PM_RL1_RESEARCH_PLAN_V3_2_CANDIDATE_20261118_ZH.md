# PM-RL1 V3.2：时间一致的长期记忆与按需资源获取——完整研究方案（候选）

日期：2026-11-18（日本时间）  
性质：研究方案修订候选 / 审阅稿；不是 GPU 授权、正式实验预注册、研究者 H0 采纳记录或对旧状态表的覆写。  
仓库：chensiyu7812/Metacom5_3  
基线：pmrl1-v3/integration（审阅时 320a33d1）；V3.1 候选 PR #4；A G0e PR #10、A 补充 PR #12、B S3 PR #11、四资源审查 PR #13。  
上游参考：PM_RL1_SOLUTION_PLAN_V3_20261116_ZH.md、RESOURCE_SPEC_ZH.md、PM_RL1_FOUR_RESOURCE_ARCHITECTURE_REVIEW_20261118_ZH.md、现有 C0 契约与全部冻结 manifest。

> **研究者已经同意更新研究方案，但这不等于自动合并 PR #4、#10–#13，或批准 GPU、模型生成、判官、训练和付费 API。** 本文提出新的科研目标和施工优先级。正式采用时由 integration owner 记录采用提交与迁移决定；在此之前只允许独立、可保全的 CPU 准备，不得将候选方案覆盖现有 EXECUTION_STATE。

## 0. 执行摘要与核心判断

第一篇 MetaCom Policy Manager 研究采用生成前一次性资源分配；其结果说明节省输入 token 不等于证明实际帮助提升，Context Only 及 Event Memory Only 强对照暴露了额外资源可能无益甚至干扰的问题。PM-RL1 的新研究问题不是让模型尽量检索，而是：

**长期伴随用户状态持续变化时，一个外置 Policy Manager 能否在合法且时间一致的记忆条件下，依据当前需要序贯获取或拒绝外部资源，并在事实、安全和用户实际等待约束下改善自然支持的适当性？**

当前的四头合法读取、回放、hash、TerminalKey 和 CPU 测试证明了工程身份与信息边界，**没有证明**：每个历史时点都能重建当时可得记忆；人物/事件当前状态正确；MS 压缩有益；RS 确实提供 G 缺失能力；同 G 相对 OFF 的增量支持质量；J1 具备足够可靠的训练奖励；A6000 实时端到端能力。因此 V3.2 采用“先验证外部资源的存在价值，再冻结环境与奖励，最后比较学习策略”的科研顺序，同时允许有边界的 engineering_only 优化器自检。

本次只新增三个必要层：

1. **外层时间一致环境（As-of Memory Environment）**：离线按用户会话顺序写入与更新资源，给每个待回复前缀物化唯一、可复现的历史快照；同样的代码可在模拟部署中逐会话流式运行。
2. **资源能力资格与表示试验**：四个头是四个可选择的读取视图，不预设四套 RAG；分别证明“合法来源→相关候选→正确阅读→自然帮助”，包括合法但无益、有害、无需主动引用的条件。
3. **可审计奖励及真实等待约束**：来源/时序/安全硬约束与人评校准的软支持质量分离；未知不作零；在线首有效回复和完整回复的 p50/p95 优先于 token 代理。

## 1. 研究范围、科学问题与可证伪假设

### 1.1 本论文范围

- 目前 PM-RL1 研究**文本情感支持中的单轮回复前资源决策**；长期记忆会随历史推进，但正式离线训练时当前前缀的外层历史固定、可重置，单轮内执行 GET/STOP。
- 保留 Step-1 获取、可选 Step-2 支持表达决策、冻结 Generator 生成的分层结构；不把 G1 训练和多模态、生活提醒、心理状态轨迹、Tokkio 真人效果强行算作本论文已完成贡献。
- 最终博士主线仍是长期陪伴数字人，未来可扩展事件提醒、日常帮助、情绪轨迹、多模态和主动行动；当前实验不声称已验证这些能力。

### 1.2 研究问题（RQ）和失败分支

| RQ | 研究问题 | 主要证据 | 可能的负结果及解释 |
|---|---|---|---|
| RQ0 环境可信性 | 历史时点的存储内容是否只依赖当时已知信息，能否与逐会话在线写入一致？ | as-of / prefix-extension / source-span / 延迟写入测试 | 不一致则不能做研究级资源收益比较，先修 Writer |
| RQ1 资源能力 | 经过合法、适用性审查的 MP/ME/MS/RS 是否在部分情境相对真实 OFF 改善支持；不需时是否可能无益或有害？ | 同前缀同 G 的直接提供、单头、组合、R0/F/Method/Case 盲评 | 资源未改善应如实报告，不能继续以“存在即有效”训练 |
| RQ2 供应与使用 | 一条有价值的资源为什么可能没起作用：源缺失、时点建库、检索排名、渲染、G 误用，还是当时根本无需读取？ | 分层召回/适用性/阅读诊断和 Oracle-direct 对照 | 仅检索 Recall 提高不能声称支持增益 |
| RQ3 情境与序贯 | 在同一可见信息与预算下，PM 是否优于强固定/规则/OneShot；读到正文后再决定是否继续有何增量？ | Phase-1 的 16 子集、NoText 消融；Phase-2 内容自适应的 GET/EXPAND | 如果顺序不胜 OneShot，就不宣称读后决策有价值 |
| RQ4 强化学习增量 | 相同资源、奖励、数据、观察与反馈预算下，PPO 是否优于 BC/BC-union？ | owner/family 留出、多个 seed、同成本比较 | PPO 不优于 BC，则贡献可在决策机制和环境，不强称 RL 必要 |
| RQ5 用户体验 | 在安全/质量约束下，按需获取是否改善或合理控制真实在线等待与失败率？ | p50/p95 首有效回复、完整回复、Tokkio 首语音、失败/回退 | token 更少而延迟更大时不得声称体验改善 |
| 扩展 RQ6 | G1 的资源理解训练是否增加正确采用与合理忽略，同时保持 OFF 基础质量？ | G0/G1 × 资源 × PM 消融；独立人评 | G1 无益可从主实验退出，不能反向选择最有利 G0 |

**不可替代的区分**：R0“没有额外支持资源”不等于 Generator 禁止使用已掌握的支持技能；OFF“没有额外资源”不等于没有当前用户话语和固定基本系统提示。F-resident 有常驻技能文本，永远不与真正 OFF 混称。

### 1.3 主张证据等级

- engineering_only：来源、回放、renderer、终点、CPU 测试、FIXTURE BC/PPO 或未校准代理结果，仅证明代码与机制可运行。
- research_qualified：来源与时点、资源定义、用户划分、G、reward/judge、检索器、等待测量、统计协议事前冻结并完成相应资格，才能提出对应 RQ 实验结论。
- human_confirmed：冻结后的独立盲评给出方向及其不确定性；不以训练用 J1 自评代替。
- deployment_validated：指定真实硬件/Tokkio 流程的性能与可靠性；不等于真实长期心理改善或临床疗效。

## 2. 文献与数据集怎么用，不混淆能力与收益

| 来源 | 可以直接借的方法或数据 | 禁止偷换的结论 / 使用边界 |
|---|---|---|
| EvoEmo / ES-MemEval（WWW 2026；18 虚拟用户、401 会话） | 主要长期历史、碎片披露、矛盾、时序任务、内部 owner/family 分折 | ES-MemEval 来自同一 EvoEmo 轨迹，不是与训练历史独立的新用户确认集；核对官方 QA 1,209 与 V3.1 文档 1,261 口径 |
| ESConv（Liu 等，2021） | 支持对话策略语料、案例及误用开发；保留重叠 family 隔离 | 注释策略/对话正例不等于某当前前缀必须调用 RS，更不是方法有效性证明 |
| LongMemEval（ICLR 2025；500 QA） | 时间、更新、跨会话推理、abstention；独立记忆诊断 | Oracle/evidence-session 标注不得流入 PM；QA 不是帮助性奖励，S/M/oracle 不能累计成独立人数 |
| LoCoMo（ACL 2024） | 事件链、会话摘要、父文回查、时序诊断 | 只有少量生成长对话；现有观察/摘要若使用后验历史必须重建 as-of；遵守 CC BY-NC |
| MemoryAgentBench（ICLR 2026） | 增量交互、知识修订、选择性遗忘压力测试 | 杂合 QA/长上下文任务，不能作为自然支持人评 |
| Mem0、Zep/Graphiti、Memory-R1 | ADD/UPDATE/INVALIDATE/NOOP，双时间，事件关系证据 | 不直接训练 Writer RL；图谱是可选存储实现，不等于四头质量提升 |
| MemoryArena（ICML 2026） | 交互环境接口、memory-environment loop 与可重放状态 | 仅“新建记忆环境”不具独占创新性；任务与情绪支持不同 |
| LifeSide（2026）及 ETrajEval | 隐藏生活状态与可见披露分离、长期事件扰动 | 模拟任务/情绪不等于现实长期心理效果；使用前核对官方数据开放与许可 |
| PPDPP、ESCA、ESC-Eval、RLCF/rubric RL | 支持策略规划与表达分离、实例级评价、盲测 | 自动检查表会被奖励优化迎合；必须有独立人评和难例校准 |

**数据分工**：核心模型开发使用已许可的 EvoEmo / ESConv 与固定排除关系；MemoryAgentBench、LongMemEval、LoCoMo 用于 memory-only 压力测试；独立支持质量需要未参与修复的前缀/用户以及盲评。REALTALK 等真实聊天可作为额外选项，隐私、研究复用许可和具体释放版本未经确认前不进入训练。

**暴露声明**：18 个虚拟人物已在多轮实验中被浏览、开发、择优和报告。重新 hash、重新分折或换 TerminalKey 都不能使它们成为“全新独立人群”。所有开发、模型选择、judge 调参、方法卡创建、最终确认须保留 source_family 和 exposure registry。18 owner/6 折可用于策略的 out-of-fold 评估；论文不自动宣称系统全链对全新用户泛化。

## 3. 新增的时间一致长期记忆环境

### 3.1 外层和内层是两种不同时间

外层时间 t：用户跨会话、跨日期生活/披露推进；完成会话后 Writer 更新长期资源。离线以合法历史固定下一会话，不由当前 G 生成回复改变用户未来话语。  
内层时间 k：给定同一合法前缀和 as-of 资源快照，PM 可以 STOP 或 GET_RS/MP/ME/MS，已成功获取的 ReadingView 更新可见状态；之后 G 产生**本轮**回复与终点结果。

因此正式 Phase-1/2 是“外层离线重放 + 内层有界序贯决策”，不是已经实现了真实长期用户的交互式 POMDP。要做用户对生成回复的动态反馈，须另立经过独立验证的模拟器和长期研究实验。

### 3.2 数据单元与三时钟

1. SourceTurn / SourceSpan：只存真实原文、说话人、会话内 rank/日期、owner/family、出处与许可，作为不可变真相基座。
2. Fact/Event/SessionSummary/Method：是从上述来源构建、证据可回查的**派生状态**，不是另一个未经验证真值。
3. 每一条个人记忆至少区分 event_time（事实生效/事情发生，可能未知）、known_at 或 reported_at（系统何时得知）、ready_at（Writer 何时完成且可读）；另留事实有效区间 valid_from/valid_to 和失效记录的 knowledge_time。
4. 只有 rank 没有可靠日期时，以 rank 定序并保留 event_time=unknown；不倒推出精确日期，不把报告时间当发生时间。
5. 个人事实为“用户曾报告”，不能凭用户报告推出客观疗效或第三人确定状态；系统不能把支持者的建议写成用户已执行。

**as_of(prefix) 合法条件**：当前可见 prefix 直接供 PM/G 使用；长期资源仅来自当前 cutoff 之前**已完成**且在当时已获知、已 ready 的来源。外部 RS 有独立版本/许可生效时间，不与用户会话 rank 硬比。新增发生在前缀后的材料无论文本是否存在于离线文件都不能进入内层动作状态、候选、排名、记忆写入选择或 Generator。

### 3.3 新存储结构与构建顺序

- Immutable Source：原始 turn/span、hash、owner/family、来源内容和法定范围；保持完整 RAW。
- Append-only Memory Ledger：候选事实、主体、slot、事件组、阶段、来源、时间、更正/矛盾/失效和 writer 版本。更正追加新版本，不物理删除旧版；不把相矛盾记录强行选为“唯一事实”。
- Materialization：在每个合法 cutoff 从已提交 ledger 派生 MP / ME 当前或历史可知视图，并绑定 writer、输入 source frontier 和 snapshot hash。
- MS：每个已结束会话分别保留 RAW 与可审核的 SUM；摘要逐命题连回 RAW span，摘要失败显示 unusable，RAW fallback 另立身份。
- RS：独立于用户私有记忆，方法/案例分表；方法许可、适用与禁忌、风险审查和版本分开。
- Index/Catalog：每头可使用不同实体/时间索引、词面/BM25/dense；候选结果与 PM 可见 ReadingView 分离。起步用 JSONL/SQLite 即可，不要求知识图谱服务。

**离线部署等价性**：单次按会话顺序批量重放，与逐会话 append+materialize 应在相同 writer 和同一 cutoff 产生相同视图 hash。动态写入发生在会话完成后，线上只读已提交状态；真实异步延迟不可假装由逻辑 ready_at=r+1 实测得知。

### 3.4 必过的不变量与失败路径

| 类别 | 检验 | 失败处理 |
|---|---|---|
| 未来不变性 | 给某 owner 追加未来会话，早期 snapshot、candidate membership、ranking 输入和可读正文完全不变 | fail-closed；拒绝研究级 bank，回查全轨迹 latest 池选择 |
| 时间切断 | 来源/获知/ready 不晚于 cutoff；当轮未结束的信息只可作为当前前缀 | 拒绝写入，保留源跨度和错误 |
| 主体正确 | 用户、伴侣、医生、外部案例主体不混淆 | uncertain/quarantine，必要时退化为有角色原话 |
| 阶段正确 | suggested、intended、attempted、completed/outcome_reported、rejected、unknown 严格区别 | 证据不足保持 unknown，禁止隐式结果 |
| 更正透明 | r5 才获知的二月搬家事实不出现在 r4；旧版本可追溯 | 追加新版本/失效边，禁止重写旧 snapshot |
| 存储与引用 | 每个断言有精确源文、家族/许可和合法窗口 | 无源不入库，缺失不能编造 |
| 流式一致 | 批量 as-of 与逐会话写入结果一致；进程失败与重复写幂等 | 不一致停止，保留 WAL/版本以恢复 |
| 派生泄漏 | NeedCard、CheckList、Judge、oracle、私有 ID/分数及未来字幕不进入 PM/G/索引 | fail-closed 且重建请求身份 |
| 版本不可混合 | writer、bank、index、query、renderer、G、decode、Step-2 任变均产生新请求/终点身份 | 禁止挪用旧 key 结果及旧奖励 |

原 bank-v0 的 MP 是从全历史最新池筛选，PR #13 核实存在 324 条被更晚替代的隔离 MP。它证明**当时的入池选择存在前缀时点风险**，并不证明未来正文已经发给 G。V3.2 应从 RAW 按时间重编译 as-of 的 MP/ME，不把 324 条直接塞回旧库凑覆盖率；旧 bank 全部作为冻结工程对照保留。

## 4. 四个可读头的能力与载体

**通用底座、分头语义、统一 GET 接口**，而非四套同质化 RAG。

| 头 | 为 G 补什么 | 主要载体和更新 | 首轮读取/诊断方案 | 失败重点 |
|---|---|---|---|---|
| MP（人物/当前约束） | 当前前缀未表达的个人背景、偏好、关系、约束及其时点有效性 | 原子 claim+subject+slot+版本+source；会后 ADD/UPDATE/INVALIDATE/NOOP | 先按人/slot/时间筛，再以受审原话提供小型投影 | 错主体、无依据的稳定人格、未来更正反写、过时状态 |
| ME（事件经历） | 事件进展、用户尝试/拒绝/完成及自报反应 | Event record+stage+follow-up 证据边，动态修订 | 优先可解释事件单位，按阶段排序而非关键词 Top-1 | 把建议当完成、把自报改善当疗效、事件阶段错 |
| MS（会话脉络） | 事件卡难以压缩的语境、谈话过程和罕见细节 | 独立 RAW、SUM、span/父文索引，SUM 拒收与回退有版本 | 比 RAW/SUM/事实键/定向回查；EXPAND 仅在 Phase-2 | 摘要遗漏、会话切段、身份重复、RAW过长 |
| RS（支持方法） | G 自身缺乏或容易误用的支持行动及适用边界 | 有许可、审查的 METHOD 卡＋可选外部 CASE 示例 | R0、F-resident、METHOD、METHOD+CASE 四臂直接比较 | 无增量、案例当用户、误用方法、过度建议或时间成本 |

RS-v0 的 875 项是 ESConv **案例**，不能称为 875 种有效方法；八类策略标签不是使用指征。先审一小组低风险方法，包含 when_to_use、when_not_to_use、action_options、common_misuse、source/licence、review_status；案例从属于方法且注明是别人的会话。医疗、危机、心理治疗类内容未经过合格专业审核前只作研究隔离材料，不进入部署可用知识。

**RS 决策树**：如果 R0 已足够，允许 STOP；若常驻短 F 和按需方法同等且 F 更快，可以采用 F；若 METHOD 超过 F，再考察检索是否胜过确定性匹配；若 METHOD+CASE 无额外帮助或误用上升，去掉 CASE。不要先把 A5 的 RAG/图谱复杂化设为“创新性”必经之路。

## 5. 检索、阅读、Generator 的分层资格

### 5.1 五个不同实验对象

E0 输入合法：as-of、family、来源、时间、许可和 hash 正确。  
E1 资源内容能力：直接给 G 合法、精确审核的材料，相对 OFF/F 有何增量，是否被正确使用/忽略。  
E2 索引与召回：有合法有用候选却没找到，是缺库、遗漏、排名、适用过滤还是写入延迟；单独记录无合法候选。  
E3 Reader/Renderer：同一来源、相同文本证据，对比当前 Notes 与带主体/阶段/可选使用边界的表示；新表示另立身份。  
E4 PM：当前前缀和已读正文下，学习 GET/STOP 的收益；不让 PM 为 E0–E3 错误背锅。

首次资格**先做直接给定**少量经审核材料的机制实验，减少“资源有价值但检索不到”的混淆；之后才比较 lexical-v0、dense、BM25、hybrid、实体/时间和一跳经核验关系。所有 retriever 比较保持同一源集合、cutoff、packing、G、renderer。BGE 相似度或语义重排改进不能直接充当支持质量提升。

PR #13 的 83 条检索样本、1,876 条候选和 12 项开发诊断继续复用；人工盲核前不得写成独立 Recall@k 金标。Recall 须定义完整或受限的相关证据集合，分清“无可用来源”“没找到”“找到但不必读”。

### 5.2 G0/G0e/G1 边界

G0e 是已实现的 Gemma-4-12B-it 初始 no-plan 请求接口，合规 renderer 和合法终点已 CPU 演练；未证明模型能加载或读取正确。G0 研究身份只在 A0 真机加载/吞吐/显存、阅读诊断和正式版本冻结之后成立。当前 vLLM 未支持 Gemma4Unified 的证据应保留，先检查指定 HF fallback；不得自动更换为 Llama 或静默量化/降级。

G0 各臂**相同权重、tokenizer、系统提示基线、decode 与硬件条件**；阅读呈现版本属于独立实验因素。OFF 绝不附带 Notes；F-resident 单独标签。记录 TTFT，但用户看到第一个有效文字的时间才是产品延迟；Step-2 隐藏计划输出和无效 JSON 不算首个可见回复。

G1（RAFT 式条件 SFT/QLoRA）是后续研究，前置要求：G0 能正确运行、资源确有信息增量、人工/独立偏好有资格、训练源与留出 owner/family 不交叉。训练组含 REL/RET/DIS/OFF/CONFLICT/OPTIONAL/RS-NEG；正确目标既包括“该引用时引用”，也包括“相关但此刻不要主动提及”。教师生成、GSC 筛选、同裁判评估不得构成自证闭环。DPO 仅在独立偏好证据合格后正式采用；没有成功则以 G0 收口。

## 6. 奖励与 Judge：正式 RL 前的科学门槛

### 6.1 需求卡预先冻结

B1 NeedCard writer 只读当前可见前缀、严格过去 RAW/已审核摘要、可用方法目录；检查表在任何候选 G 回复出现前冻结。历史条目角色区分：

- required：缺此事实会妨碍回答当前明确需求，才能成为 H+ 正向要求；
- relevant_optional：相关但无需主动提及；不提历史不能扣分；
- must_not_contradict：明确失败/拒绝/更正/时间/人物条件必须尊重。

一个合法来源存在不等于“必须读取”；NeedCard 分层仅用于抽样、评价，不进入 PM/G 的 observation。

### 6.2 反馈分离与不确定

| 通道 | 内容 | 主要用法 |
|---|---|---|
 F：事实/时序 | 主体、发生/报告时间、阶段、来源、过去被拒建议 | 程序化优先，难例人工确认；明显错误门槛 |
 S：安全 | 高风险内容、危险建议或失当干预 | 不允许以低延迟抵消；不确定要进入审查 |
 Q：支持适当性 | 同理、自然、澄清时机、建议是否合适、尊重自主性 | 盲评成对质量，跨裁判和人工校准 |
 R：检索适用性 | 候选存在、可用、值得读取、是否影响回复 | 用于资源诊断，不直接充当最终 Q |
 T：等待 | 首可见有效回复、完整回复、失败/兜底 | 实际设备测量和可校准预测 |

同一个 prefix 的所有可比较资源子集共享固定 ChecklistItems 与权重分母。J1/J2 每项给 pass/fail/uncertain，原子错误 L1–L8 保留冲突归属；uncertain 形成上下界，**绝不填零**，不能把不同终点各自剔除未知项后使用不同分母。只有可信且可比较的评分可进入研究级 Oracle/BC/PPO；缺失终点维持 pending，不能视为 OFF/差评。

Qwen3.5-9B J1 的原 800 输出 token 静态风险已确认：某些 13–40 项检查表可能截断。任何新 decode 上限都必须在首次 J1 真正调用前经研究者审核、重新冻结 JudgeIdentity，登记 finish_reason、超限预阻塞；不能在受限贪心输出上原样无限重问，也不能擅自把 J1 v3 改成 v4。

### 6.3 训练 reward 与最终论文结果分离

训练时可采用明示、版本固定的 R_proxy，但它只能产生 engineering_only 的 BC/PPO 学习曲线。正式反馈必须有：逐类别来源/时序/安全难例、真实人评小样本、两个相对独立判官、平局/未知覆盖、资格报告和冻结后的留出评价；如果代理 reward 增加但独立人评无改进，报告 reward hacking 风险。

正式目标更适合写成：**在安全与事实可靠性门槛下，寻求帮助质量与真实用户等待的 Pareto 前沿**；经验证的 dev 偏好才决定是否采用标量 R=Q−λT。p95 不是逐 GET 简单相加就能准确求得，必须实测并作约束/分层报告；λ 不由 token 节约比例推导。

## 7. 强化学习环境、基线和可解释归因

### 7.1 环境契约

每个 episode 固定一个合法 prefix、as-of resource snapshot、G/renderer/检索版本及已冻结的 source_family。状态只暴露当前会话、允许的 inventory metadata、成功 GET 的 ReadingView 和真实可见的已获取摘要；NeedCard、评估标签、oracle、未读文本/分数及未来 history 不进入 PM。检索预取元数据如产生等待，所有基线公平计成本。

动作（Phase-1）是 STOP、GET_RS、GET_MP、GET_ME、GET_MS，每头至多一次；终点最多 16 个合法资源子集（并非每个 prefix 都有 16 可达）；无合法候选要 typed failure，不伪造空资源。相同子集若最终规范化渲染一致，可共享 Generator 请求身份；不同合法读取顺序的执行轨迹和真实等待分别记录。只在 STOP 时给终点 reward；保持环境确定性。

Phase-2 才考虑内容自适应 query、同头重复 GET 和 EXPAND_MS(j)；每条轨迹含父文和重复读取的完整成本与状态，另立新的 adaptive env version，不把有限头 16 子集结果误写成动态多次读的证明。

### 7.2 主基线与匹配条件

必须比较真实 OFF、ALL、Fixed-best（仅训练折选）、有竞争力的 F-resident、Rule、同预算 Random、OneShot、Seq-BC、BC-union、PPO、PPO-NoText；Oracle 只做特权诊断，不入部署。关键对照：

- PPO vs 最佳固定：情境化是否比“不学”好；
- Seq vs OneShot：读后决策是否带来增量；
- PPO vs BC-union：控制反馈数量的 RL 增量；
- PPO vs NoText：读到的正文是否真被用于下一步；
- 直接提供 vs 实际检索：检索损失；
- 资源表示相同 vs 不同：内容与包装的独立效应。

所有主比较同一个 G0、split、来源、检索器、判官版本、硬件条件和训练/评估预算。不能从 PPO rollouts 总数推出独立用户数，也不能因重放缓存已经存在就隐去它在部署时的首次生成或检索成本。

### 7.3 统计与实验分层

单位为 owner/source family 的重复测量，避免把一个 owner 的几十个前缀当成独立用户；保留 6 折既定家族划分，标明整体方案调参已经接触过哪些 owner。预先冻结主要比较、方向、置信区间、非劣界（若使用）、多重比较方法和缺失处理。18 个 owner 的精度有限；开发上的探索不能变相叫独立确认。自然前缀分布是主报告，历史需要/不需要类别的均衡过采样只能作为训练或诊断分层，须给自然权重与覆盖率。

## 8. 用户延迟、Tokkio 和动态模拟三级验证

**在线用户经历**：用户请求结束→首个有效且可显示文本；用户请求结束→完整文本；Tokkio 用户话语结束→首个有效语音；p50/p95、超时、重试、失败、回退。区分 cold/warm、cache miss/hit 和设备队列、PM/编码/检索、prefill/decode、隐藏 Step-2、TTS/A2F。生成的首 token 若仅为不可见计划 JSON 不得计为用户实际见到的第一段。

**离线开销**：B1 NeedCard writer、J1/J2 判官、checklist、人评、构建/重索引、训练、批量预计算不能加到用户在线响应时间中；其 GPU 时间与成本单独核算。

**验证级别**：
1. 离线会话时间重放：同历史能够稳定构建合法 as-of 资源，证明记忆正确与局部资源因果对照。
2. 交互式自动用户模拟：可研究事件披露/更正及多会话稳定性，但必须把模拟器隐藏真值与智能体观察严格隔离，不能声称真实心理效果。
3. Tokkio staging 自动对话与音频重放：检验真实系统集成、异步 Writer、首语音/p95、掉线/恢复与多轮日志；使用独立服务/测试用户数据，不控制真实实验室设备或真实用户活动。真人长期效果另需伦理与参与者设计。

## 9. 正式分阶段推进路线与验收门

| 阶段 | 目的 | WS-A 主责 | WS-B 主责 | 成功门/失败分支 |
|---|---|---|---|---|
| P0 版本保全 | 不丢失既有 G0e、B、PR #13、状态和冻结证据 | 对照 #10/#12/#13 manifests；只建新分支 | 保留 #11 Draft 与旧 B5，联合接口审阅 | CI 和所有 frozen SHA 相同；integration owner 串行合并 |
| P1 时间一致 CPU | 明确每个历史 cutoff 真正可得资源 | 新 as-of replay / MP/ME stage 与版本 sidecar；MS RAW 证据 | Prefix-as-of manifest、反例和交叉重放校验 | 所有机械未来/owner/family 越界为零；不合格事实 unknown/quarantine |
| P2 资源资格 | 先回答“外部资料有无真收益” | 少量可信 MP/ME/MS/RS 与 Notes/边界块，RS 四方案 | 固定 54 开发输入的 as-of eligibility、随机盲评试验方案 | 同 G 的 OFF/单头/组合直接提供；若无益查源/表示，不升级 bank |
| P3 G0/A0 与反馈资格 | 获得真实可运行 G 与可信 J | 完整 A0 CPU 前置与待授权 A6000 方案 | 20 NeedCard 试点申请、J1 capacity 修订提案、人评/跨判官校准 | 授权前 0 GPU/生成；后续逐类评估，不得以未解析 pending 填零 |
| P4 bank-v1 | 研究级四视图与索引 | 从时间源重编译，分头 ranking；RS 决策性比较；A6 | 新终点/key/legacy mapping 不迁移 reward | source→view→renderer→key 一致，内容增量与适用性有实证 |
| P5 Phase-1 正式 | 完整有限头 16 子集及强对照 | 冻结 G0/资源版本，提供响应 | 在合格表上 BC/PPO/NoText，owner-family 检验 | S=288/M=482/L-realized=748 仅为现有计划档位，实际规模/等待据资格与实测决定；不能复活不可行 L=960 |
| P6 Phase-2/G1 | 进一步读后查询/生成能力 | 可选 G1 SFT，独立于 G0 主比较 | Adaptive GET/EXPAND 与 OneShot、公平反馈 | 若无内容读后/训练增量，报告负结果且不扩大 |
| P7 真实部署与论文 | 判断是否有独立可重复帮助 | A 提供稳定只读服务与版本 | 盲人评、外部记忆诊断、Tokkio 测试、统计 | 不以 QA、模拟情绪、工程 CI 代替自然支持结论 |

**先做 P0–P2 的 CPU 机制准备**，它们不要求一次建完整 bank-v1，也不要求先跑满 120 B6e 终点；A0、NeedCard、J1 等模型实验各自仍需独立授权。老 P/S/A/B 任务编号继续保留为历史/当前状态映射，新的 P0–P7 是研究阶段而非擅自修改原状态表的任务 ID。

## 10. A/B 两线所有权、合并队列和下一轮最小交付

### 10.1 唯一合并与研究状态规则

- 当前 integration 已合入 C0/A1/A1b/B5；PR #10 G0e、#11 B S3、#12 A/B 补充、#13 审查分别保留。#4 是尚未采纳的 V3.1 候选。新 V3.2 文档单独作为 proposal PR，不覆盖 #4，也不将文档合并等同 H0。
- integration owner 优先核验、合入 #10；B 从新 integration 正式重建 G0e 附录后 #11 转 ready；#12 在 #10 合入后重新定 base 并按实际兼容性合入；#13 是只读审查，可独立审阅合入。每个 PR 都需要最终 HEAD CI 和真实 integration-base 核验，顺序发生变化须重查。
- 若 #13 或 V3.2 文档合入但业务未变，只能说明分析文档可用；不改变 bank/judge/G 的资格。所有新设计默认独立分支与新 manifest，不推送到旧冻结 PR；main、H0、EXECUTION_STATE 仅由有权的集成负责人按已批准规则变更。
- WS-A 拥有源/Writer/bank/retrieve/reader/G；WS-B 拥有 prefixes/NeedCard/judge/reward/env/policies/evaluation。C0 公共 schema 或可见观察、动作语义修改必须跨线审核。

### 10.2 WS-A 下一轮 CPU 任务

1. 对齐最新 integration、#10/#12/#13；从已通过 A1 的 RAW/Registry 和现有 C0 写一个**只读或独立 sidecar** 的 chronological materializer 原型（先少量 owner/会话），明确 known/valid/ready 与 writer identity。
2. 建立 prefix-extension、批量/流式等价、人物/阶段/时间、更正、建议/执行/失败等 CPU 必过反例；复现 PR #13 提示的 MP 全局 latest 选择偏差，按各历史 cutoff 生成真实 as-of eligibility 证据。禁止往 bank-v0 恢复被隔离 324 条。
3. 对 MP/ME 设计 typed claim/event；MS 的 RAW/SUM/父文结构先提供 CPU 接口和真实来源记录；RS 先少量低风险方法卡、许可和四方案公平对照 manifest，未生成/审查的卡仍 pending。
4. 审核 83 条候选材料和 54 输入是否 as-of 合法，仅出 eligibility/provenance/表示候选/输入身份；不得靠结果排序改检索，不实施 A5 或声称 A4/A6/A7。
5. 保留 G0e/A0 身份和 100 OFF token IDs；提出实时延迟埋点与新增资源组合长度计划。GPU/模型/付费使用 0，提交 CPU 测试与版本证明。

### 10.3 WS-B 下一轮 CPU 任务

1. 在 #10 合入后，用正式 G0ePrefixPort 完成新身份的 8 prefix/120 endpoint 加录，保留旧 B5 键；未合入前仅做安全的兼容准备，不在历史冻结目录写回。
2. 与 A 对齐 PrefixAsOf 绑定字段、cutoff、writer/bank/index identity、source family；建立独立 evaluator 可知/PM 可见/Generator 可见三张字段白名单及泄漏测试。
3. 对 54 个提案和 RS 的 R0/F/Method/Method+case 设计**前冻结**研究协议：适用 prefix、不可达、已曝光开发身份、盲评对照、定向组合、候选使用/误用分类、实际等待测量。实际生成等单独授权。
4. 保留 20-call、0-retry NeedCard pilot v2 计划（plan SHA b1d3225b…）与 8 valid 卡门槛；核对需求层与 F/H-/I/S 规则。独立提出 J1 800-token 风险的 decode 修订评审稿，须批准再冻结，不擅改 judge v3 运行身份。
5. 继续有限头环境/DP、reward 未知区间、owner/family 划分和缺失终点 fail-closed 的 CPU tests；不能在无真实终点时推出训练收益，不启动 120 个 G0 或 J1 最多 360 的 B6e 实验。

两线交换的最小文件应包含：INPUT_MANIFEST、CODE_SHA、AS_OF_SOURCE_FRONTIER、SNAPSHOT_SHA、READING_VIEW_WHITELIST、NEW_TERMINAL_KEY_RULES、ELIGIBILITY/REVIEW_PENDING、CPU_JUNIT、BLOCKERS 和对方验收记录。所有摘要明确 engineering_only。

## 11. 人力、资源与决策界限

**需要研究者明确批准的事项**：V3.2 正式成为执行主方案的 H0；新的共享 C0 schema 或动作语义；Gemma/Qwen A6000 有界模型加载和数量、是否可切换 G0；NeedCard 试点具体 plan SHA 与上限；J1 解码配置；正式 B6e 或主实验及其上限；外部高风险 RS 的专业审查；额外数据和伦理许可；付费 API 上限。

**本次更新不批准**：任何 GPU 模型加载、需要付费的调用、真实生成与判官、120 个 B6e 终点、G1 QLoRA、训练或擅自合并。CPU 文本、契约、测试、可追溯方案可先进行，但不改变旧输出或全局执行状态。

**失败情况下的诚实收口**：

- as-of 构建不合格 → 只允许工程 replay，修 Writer；不做基于错误记忆的科研结论。
- 资源合法却无额外帮助 → 保留 OFF/合理不读作为有价值的负结果，不虚构“有效检索”。
- 正确材料被 G 误用 → 隔离 renderer/G 的问题，再考虑有条件的 G1；不归咎 PM。
- RS 的 F 常驻已够用 → 不强制 RAG；检索仅在有差异或扩展性证据时保留。
- J1 不稳定/大量 uncertain → 不补零、不无限重问；工程优化器结果仅作 engineering_only。
- PPO 不比 BC/OneShot 强 → 正式论文按实际主张收窄，不靠多轮挑 seed。
- Tokkio 延迟过高 → 从 PM/检索/G/语音拆分性能，设计缓存或异步 writer 再独立验证；不得靠少 token 的观察替代秒数。

## 12. 推荐论文主张与局限写法

拟议贡献（须由结果支持）：

1. **一种针对长期支持对话的时间一致、可重放和可审计的外部资源环境**，区分过去的可观察披露与后验世界事实，能直接支持 GET/STOP 的比较。
2. **一种把资源“存在、可召回、可正确使用、真正增益”分离的策略与评价框架**，允许最优决策选择 OFF、单头或组合，而不会强制使用无效历史。
3. **对有界序贯资源决策的强基线与质量—安全—实际等待权衡检验**，比较 PPO 与 BC/OneShot/NoText，并报告自然支持的独立人评和负结果。

既有 Mem0、LongMemEval、MemoryAgentBench、MemoryArena、LifeSide、PPDPP 等已有动态记忆/记忆测试/RL/交互研究，不能宣称我们首次引入动态记忆、建立图谱、使用 RL 或设计带记忆的智能体。真正的新颖性须落在**时间合法的个体资源、对负信息价值的主动 STOP、支持质量可靠奖励、与真实延迟结合**这一经过实验验证的结合点。

限制：主要训练历史来自虚拟人物；固定未来离线回放只能测给定状态的即时回复，不等于改变 G 回复后真实未来用户行为；18 个 owner 无法证明广泛人群泛化；自动 judge 不是临床真实结局；Tokkio 运行测试不等于长期心理疗效。以上作为正式论文显式限制而非回避。

## 附录 A：版本与已知事实核对

- 已正式集成：C0、A1、A1b、B0、B5；截至本轮 integration 状态表 A0/B1/B2 in_progress，A2/A3/A4/A5/A6/A7/B6e/B8e 等不能称 completed。
- 固定 bank-v0：3,188 条（MP387、ME1525、MS401、RS875），其中现有来源合法与读取可重现≠语义已核验。
- PR #13 CPU 核验：37,894 次来源跨度**引用次数**，不是独立事实条数；83 条候选开发包、120 份请求投影；54 个 D/E **待执行输入提案**没有生成或质量分。
- 旧 G0e：工程 no-plan 候选；真实 A0 GPU 兼容性、峰值显存、吞吐、TTFT/TTFV 与 J1 仍未实测。NeedCard 20 张未生成，8 个有效卡门槛尚未证实，B6e STOP 保持 pending。
- 官方 ES-MemEval 论文是 1,209 QA、125 Summary、34 DG；V3.1 §6.5 中写“1,261 QA train/dev”需由实际本地版本、去重、拆分及证据来源查清，不能未经校验用于 Recall 金标。

## 附录 B：主要参考（方案依据，不代表已导入数据）

1. LongMemEval（ICLR 2025）：https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html；https://github.com/xiaowu0162/LongMemEval
2. MemoryAgentBench（ICLR 2026）：https://proceedings.iclr.cc/paper_files/paper/2026/hash/fd1eff9dd295df50a41f2521942fa31d-Abstract.html；https://github.com/HUST-AI-HYZ/MemoryAgentBench
3. MemoryArena（ICML 2026）：https://proceedings.mlr.press/v306/he26am.html
4. LifeSide（2026）：https://arxiv.org/abs/2606.04660
5. ES-MemEval / EvoEmo（WWW 2026）：https://github.com/slptongji/ES-MemEval；https://arxiv.org/abs/2602.01885
6. LoCoMo（ACL 2024）：https://github.com/snap-research/locomo
7. Mem0（2025）：https://arxiv.org/abs/2504.19413
8. Graphiti / Zep（2025）：https://arxiv.org/abs/2501.13956
9. Memory-R1（ACL 2026）：https://aclanthology.org/2026.acl-long.583/
10. ESC-Eval（EMNLP 2024）：https://aclanthology.org/2024.emnlp-main.883/
11. PPDPP（ICLR 2024）：https://proceedings.iclr.cc/paper_files/paper/2024/hash/29e8437db7b549160ce03d336ff66f65-Abstract-Conference.html
12. ESCA（AAAI 2026）：https://ojs.aaai.org/index.php/AAAI/article/view/38807
13. Value Reinforcement（ACL 2025）：https://aclanthology.org/2025.acl-long.1395/
14. Reward hacking in rubric-based RL（2026）：https://arxiv.org/abs/2605.12474

---

**最终执行原则：方案先科研合格、版本再正式采用；先证明“什么时候资源有用”，再证明“PM 学得会选择”，最后证明“用户真的少等且得到合适回应”。任何证据层的失败都保留为结果，不能用其他层的工程成功掩盖。**
