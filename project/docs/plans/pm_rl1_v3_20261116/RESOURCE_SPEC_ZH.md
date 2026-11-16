# PM-RL1 四资源组织、时序证据图与检索施工规范（V3.1-R1）

日期：2026-11-16。适用仓库：chensiyu7812/Metacom5_3。

**状态：PR #4 的候选技术规范，尚未实施，也不表示 V3.1 已正式采用。** 研究者合并 PR #4 后，方按主方案的 H0 规则启用执行。此规范是主方案项目文档 PM_RL1_SOLUTION_PLAN_V3_20261116_ZH.md 的 **C0、A1、A1b、A2、A3、A4、A5、A6 与 B5/B9 接口补充**。研究目标、奖励资格、训练路线、科学主张、预算、冻结规则以主方案 §0、§5、§6.8–6.11 为准。本规范负责落实四类资源的字段、关系、检索、可见性与具体回归测试；不能凭这份设计声称已有性能收益。

## 0. 明确交付什么，避免再次绕圈

本轮必须建设并运行的能力：**合法历史 → 带来源的四类资源 → 时间/关系组织 → 真正使用 BGE 的候选检索 → 有证据的阅读正文 → GET/STOP → G 请求包**。完成后分别开展 G1、BC/PPO 和人评；检索质量未达预期时，修正对应环节、保留 oracle 归因条件和工程训练，不把所有推进无限期停在检索诊断。

**不做：**将四头全部当作同一种文本向量；把图关系当作无需证据的事实；把 BGE 相似度当作资源实际收益；把没有专业审查的 RS 方法声称临床有效；擅自改 Paper-1 冻结产物、私有训练/测试身份、人工评审或付费许可；为写入新设计而提前宣称 PR 已被合并。

术语：RS=支持方法/案例；MP=个人画像的时间版本状态；ME=事件、行动阶段及结果；MS=会话目录、摘要和完整 RAW。四头是 PM 的**读取动作接口**；它们可以共用底层事实来源、事件关系和编码模型，但**不能共用一套不区分类别的排序规则**。

## 1. 仓库中哪些资产要复用、哪些能力仍不存在

| 现存资产 | 复用方法 | 当前边界 |
|---|---|---|
| rl1/temporal_evidence_ledger.py | 复用 SourceTurn、精确字符跨度、来源闭包、关系种类和严格过去检查，向 rl1v3 做适配 | 关系只有索引身份，默认 semantic_support=unverified，不能直接更新人物状态 |
| rl1/resource_organization.py | 保留 OrganizedItem、四头目录与词语重合排名作为对照 | rank() 仍按词交集排序；GET 当前取第一条，不是混合检索 |
| paper1/embeddings/bge_m3.py | 固定模型 revision、权重 SHA、CLS、1024维和规范化；统一查询与文档编码身份 | 当前 SentenceTransformer 封装只产生 dense 向量，不等于原生 BGE sparse/ColBERT 已接通 |
| rl1/organized_encoding.py | 在 PM 可见观察中使用已读正文的 BGE 特征 | 这是**状态编码**，不是四类 bank 的在线检索器 |
| 现有 713 MP、1,523 ME、MS-RAW | A1b 转成只读 bank-v0；供 B 线立即运行工程环境 | 旧归纳已出现阶段/结果语义漂移，不能默认为 v1 可信 |
| 11/11 QA 测试 | 复现 OFF 0/14、正确会话 13/14、BGE 第一片段 10/14、前二 12/14 的同源基线 | 小规模事实检索结果，不证明自然支持或时序有效性 |
| 11/15 的 12 案例和 3 方法草稿 | 作为 RS 有来源的候选和负例审查资产 | 0 张已证明能提高自然情感支持；不得强充正式金标 |
| 11/16 session-summary 方案/提示 | A2 异步写 SUM、逐命题跨度、RAW 保留 | 当前 MS 主要是整段 RAW，SUM 与父 RAW 回查未接生产 |

复用原模块，不以原地改动旧 frozen 接口实现新方案。新增模块写在 **project/src/metacom_pm/rl1v3/**，所有派生 bank/index/校验日志带独立版本与内容 hash。

## 2. 不得妥协的事实、时间和权限规则

**I1 数据合法性：**每个查询绑定 owner_id、dataset/family、PrefixSpec、cutoff_rank/cut_turn。来源严格来自同 owner 的既往完整会话；当前会话只能使用在 cut_turn 及之前的当前可见原文。RS 仅使用许可合规、谱系不重叠的 train 来源及允许的方法材料。禁止未来来源、其他 owner、target-family 资料。

**I2 来源胜于归纳：**所有 MP、ME、MS 衍生命题都要保留准确的原文跨度、speaker、session/turn 身份和输入依赖闭包。字符偏移按原始 Unicode 字符串验证；引用能证明“这句话出现过”，不等于语义归纳、世界真实性或因果关系正确。

**I3 报告与事件区分：**reported_at/known_at 表示系统何时得知；event_time 表示用户所谈事件何时发生；valid_from/valid_to 表示描述的状态何时有效；ready_at 表示派生资源何时写入完成。不能将四者混为一个日期。只有已合法报告的未来计划可以被看到，不能写成已经完成的未来事件。日期未知时保留 null 和可比较的 session_rank，绝不臆造精确日期。

**I4 不确定不等于否定：**源文本明确报告、用户意向、助手建议、抽取模型推测、未知必须分开。user-reported 不升级为 verified-world-fact；没有 outcome 不意味着失败；旧版本和冲突版本不静默删除。

**I5 关系有证据：**updates、contradicts、follows、follow_up、outcome_of、mentions、derived_from、parent_session、about_entity 必须有端点、方向、来源和验证状态；LLM 生成的未经核验的关系不得参与当前真值投影或自动传播。一跳关系扩展不能绕过 owner/cutoff/证据门。

**I6 隐私与公平：**PM/critic 只能看 Observation；Generator 只能看当前前缀与已购买的 reading_view。未读的 bank 内容、来源密钥、人物身份、图邻居、NeedCard、裁判标签、future、privileged oracle 都是私有信息。GET 不能调用 Generator/Judge。预计算元数据如获准暴露，所有 arm 必须获得同一视图并计入真实查询成本。

**I7 可回放：**每个 Source、Record、Index、Query、Rank、Read、Render、Terminal 都有不可变版本/hash；新 writer、新排序或新 packing 产生新版本，不把旧终点/奖励继承过来。

**I8 两种价值分离：**检索证据是否可达，可以用机械/事实任务验收；资源是否真正改善自然回复，必须通过同前缀、同 G 的配对结果、适当人评与反馈资格检验。不能把 Recall@k、BGE 余弦或方法标签直接当 PPO 奖励。

## 3. C0 必须冻结的数据模型与共用接口

在 V3.1 主方案 §5 已定义的 9 种契约之上，C0 再冻结 **SourceSpan、TemporalClaim、TemporalRelation、IndexManifest、RetrievalTrace**。它们是 A 侧 bank/retrieval 的内部对象，不得自动暴露到 B 侧 actor 状态；B 侧仅接收 SourceSession、PrefixSpec、ReadingView、可见 Observation 和批准的交互 API。

### 3.1 SourceSpan

字段：source_key、owner_id、session_id、source_rank、turn_index、speaker、start_char、end_char、exact_quote、raw_turn_sha256。机械检查原文切片完全等于 exact_quote；同一文字重复出现必须使用完整轮次身份，不用模糊序号猜测位置。source_key 可以保持旧 namespace 但必须经映射核验。

### 3.2 ResourceRecord

共用字段沿用主方案：record_id、bank_version、head、view、owner_id、source_refs、reported_at、event_time、valid_from、invalid_at、stage、body、reading_text、index_keys、review_status、writer_identity。增加明确的可选内部字段：

- source_rank / ready_at / origin_dataset / family_id / original_raw_identity；
- subject_id、entity_ids、parent_session_id、parent_event_id、related_claim_ids；
- evidence_status = exact_span_verified / semantically_supported / uncertain / rejected；
- epistemic_status = user_reported / supporter_suggestion / reported_intention / inferred_unverified / unknown；
- raw_view_identity、summary_view_identity、relation_index_version；
- license_scope、risk_tier（仅 RS）。

所有可选字段都必须明确 null 语义，禁止用空字符串表示已知否定。阅读正文独立于索引文本：索引可以含实体别名、事实键和主题，但 Generator 的 reading_view 只能包含白名单字段与有根据的自然表述。

**双时间字段对齐：**主方案中 ResourceRecord.invalid_at 解释为“系统在何时得知旧记录被更正/失效”的记录时间；TemporalClaim.valid_to 才是“原事实在现实叙述中到何时仍有效”的事件时间。两者不能互相直接复制。若旧值终止日期未知，valid_to=null；若知道新的更正来源，保留 invalidated_knowledge_rank 及其 source span。C0 必须把这三者的映射写成可检查的 Schema，而不能只用一个 invalid_at 代替双时间。

### 3.3 TemporalClaim / TemporalRelation

TemporalClaim：claim_id、head、subject_id、predicate、object、reported_at、source_rank、event_time、valid_from、valid_to、invalidated_knowledge_rank、epistemic_status、evidence_spans、semantic_support、version_group。

TemporalRelation：edge_id、relation_type、left_id、right_id、direction、evidence_spans、reported_at、derivation_identity、review_status、semantic_support。关系类型只允许预注册白名单；**相关不等于同一，先后不等于因果**。outcome_of 表示用户明确关联的报告结果，不等于该行动在现实世界中造成结果的因果证明。

### 3.4 时间与快照规则

API：materialize_mp(owner_id, prefix) / timeline_me(entity_or_event, prefix) / get_session_parent(sum_id, prefix)。先按来源合法性与 ready_at 过滤，再按 valid interval、更新边和阶段得出当时投影；不得先构建含未来信息的最新图后仅在最后过滤显示。

在同 slot 多条记录冲突且没有明确更新关系时，返回 conflict/unknown + 各来源，不按“最后一条一定为真”强行覆盖。原文明确更正时允许 ADD/UPDATE/INVALIDATE/NOOP，旧记录保持可追溯。对于习惯/偏好可设置 tentative/supported 等证据状态，但**不要凭出现次数自动声称用户长期稳定特质**。

### 3.5 冻结的跨工作线调用

- A 提供 source_registry.build、bank_v0.load、bank_v1.load、retrieve.search、retrieve.read、render.request_packet、bank.validate。
- B 提供 PrefixSpec、engine.step(GET_H/STOP)、TerminalKey、Needs/Judge/Reward；B 不可自行修改 A 的检索排序或按人工评判修正 bank。
- retrieve.search(head,prefix,acquired,bank_version,index_version,query_mode) 返回**仅供环境执行器使用**的有序私有候选和 Query/Index 身份；read(key) 才把资源正文转为 ReadingView 并真正计成本。
- query_mode=static 只看合法当前前缀，adaptive 只能追加已经购买的阅读正文。相同输入、bank 和编码器 identity 必须得到相同排名及 hash。

## 4. 四头分别如何写、存、检索和交付

### 4.1 MP：带版本的当前画像

单位：每个可核实的个人陈述一个原子 claim，而不是给人物贴一大段自由文本。建议 slot 族：person/relationship、location、occupation、routine、preference、constraint、health_report、goal；词表可扩展，扩展需版本化。subject 必须区分用户、朋友、配偶、孩子等，不能因名字相近混用。

写入：逐会话 RAW → 候选抽取 → 精确 span → 蕴含/角色验证 → 与同 owner+subject+slot 旧状态比对 → ADD/UPDATE/INVALIDATE/NOOP → 时间快照。只在用户明确报告变化时变更当前状态；“想要搬家”是计划事件，不等于居住地已更新。

检索：当前语句的指代与 slot 识别 → 当前时点的字段/实体索引优先 → BGE 同义表达补召回 → 源跨度回查。避免全 MP 文本 Top-10 无差别注入。Phase-1 为保持16终点，可仍用**一次 GET_MP 的确定性限额包**（最多10条/约350 tokens），但实际条数依证据和预算可少于上限；Phase-2 才检验多次 GET/可变预算收益。

交付：按“用户在某次历史对话中提到……”而非绝对真实身份表达，显示已知时间、目前有效/有冲突/不确定；内部 record_id、推测状态与排序分数不直接展示给 G。

### 4.2 ME：事件、阶段、反馈、后续

事件应有 event_group_id、actor、other_entities、action、object、event_time、reported_at、stage、reported_reaction、reported_outcome、unresolved、source_spans。阶段推荐 suggested / intended / attempted / completed / outcome_reported / unknown，并保留原 v0 编码映射；assistant 提出建议不能映射为用户已经执行。

关系索引：same_event_group、follows、follow_up、updates、contradicts、outcome_of、about_entity。只有经原文验证的关系可用于事实视图；相似文本仅形成候选 relation，不能直接定性为 follow_up。每组事件保留事件顺序、原话与可溯源的最后报告状态。

检索：BGE/BM25 查事件候选 → actor/实体/时间/状态校验 → 同 event_group 有证据的一跳前因和结果扩展 → 去重/重排 → 阅读单元。Phase-1 GET_ME 可上限3个相关事件，但**事件链完整性优先**：如果 3 个原子片段拼不出清楚含义，使用一条有证据的短事件链视图作为一个逻辑读取单位，记录真实 token 与组成记录。

例：先报告“打算给 Henry 打电话”，后报告“已经打了且争吵”，再报告“对方主动联系”。不得把第一句当当前建议的新事实；也不得把关系缓和解释成客观已修复。

### 4.3 MS：RAW、SUM、索引目录和父文展开

**MS-RAW 永远保留并不可变**，逐轮、说话者、完整内容、source_rank、时间及 hash 均保存。会话结束且完整 RAW 可得后才异步产生一份 **MS-SUM**；同当前会话未结束时不读取其总结。SUM 与 RAW 必须有不同 ResourceRecord、render/response/result 身份。

SUM 单位为一个完成的会话，字段含 session_date/rank、participants、topics、source-backed propositions、user_need、action_stage_and_feedback、unresolved、summary_text、raw_parent_id、ready_at、writer_identity。每句重要陈述绑定 RAW 精确 span；任何“已做/做得好/得到治疗”都须由用户报告支持。

索引文本可以是 SUM + 同 session 的 MP/ME 事实键 + 实体别名 + 日期/主题；另建 RAW 的 BM25/罕见实体倒排索引，以防摘要删掉专有名词。**索引命中不等于正文已交付**。若 RAW 命中但 SUM 没有对应证据，必须显式选择：Phase-1 标记 SUM 无足够答案（或另立带证据片段的阅读条件），Phase-2 由 EXPAND_MS(j) 计费回读完整父 RAW；不能静默将 RAW 塞进纯 SUM 实验条件。

默认读取只返回会话 SUM。EXPAND_MS(j) 仅允许 j 为本回合**已经读取**、且 parent 已验证、合法历史内的 SUM 可见序号；完全原文计算额外 token/等待，不退款。RAW 超模型原生上下文时返回明确 capacity failure，或使用有独立身份的定向源片段 view；不得无记录地截断。

### 4.4 RS：方法优先，案例从属，适用性单独验证

METHOD：method_id、goal、support_move、when_to_use、when_not_to_use、action_options、common_misuse、limits、source/title/url/section/license、risk_tier、review_status。CASE：case_id、parent_dialogue_id、legal_turn_window、user_context、support_move、followup_user_reaction、source_spans、candidate_quality、negative_reason、family_id。来源同源或未知谱系按主方案排除；FailedESConv 只作负例/检查，不解释成策略失败的因果证据。

检索顺序：当前用户真正的请求/情绪/建议意愿 → 方法适用性规则与风险排除 → BGE/BM25 对方法描述召回 → 适用/不适用条件重排 → 有来源的一个完整案例（如确实需要）。方法卡和案例分开编号，切勿将 ESConv 标签当有效性金标。F-resident 短方法目录是主方案强基线，不得删掉。

RS 未经过适当专业审核的医疗/危机类内容只保留 research_only；不能将模型或 Codex 检查称为专业批准。输出不得诱导 G 复述案例支持者的个人经历、健康保证或未经证实的承诺。

## 5. 关系图和检索器的真实衔接

图是 A 线的**轻量时序证据关系索引**，不是第五个 PM head，也不是先部署 Neo4j/Graphiti/GNN 的理由。节点为 Owner、Person/Entity、Session、SourceTurn、MPClaim、MEEvent、RSMethod/RSCase；边为来源、人物、同事件组、时间后续、明确更新、冲突、父 RAW 和适用条件。只有来源及语义核验合格的关系可改变读取选择；拒收/未验证边只供离线审查。

离线建索引过程：

1. 按 owner、dataset family 和严格过去形成来源闭包；Session RAW 必须独立保存。
2. 各类 writer 产出经过跨度验证的资源与拒收队列；归并实体和事件时保留不确定。
3. 构建每头独立 index_text、dense vector、BM25、时间/实体/slot 倒排与关系边；统一提交 IndexManifest、模型 revision/hash、索引版本、构建时间、输入 bank 哈希。
4. 既有 BGE-M3 的 SentenceTransformer 编码器作为**dense-only** 版本；本阶段稀疏分量采用 BM25。若后续要使用原生 BGE sparse 或 ColBERT，必须另实现 FlagEmbedding 对应头和检索器，并换新的 encoder/index 身份。

在线检索过程：

1. **过滤先行：**严格合法 owner、rank/ready_at、dataset/family、RS risk/review，不把未来资料提前放进向量候选后再删除。
2. **查询构造：**static=当前可见 user turn + 前面不超过3轮；adaptive=static + 已经买到的 reading_view 中最多200词。必要的实体/时间短语只能从上述可见文字抽出，不能读取私有候选或 NeedCard。查询解释器若另用模型，身份、计算和等待必须记录。
3. **候选召回：**每头 BGE dense cosine 与 BM25 并行；按倒数排名融合 RRF(score)=Σ 1/(60+rank)，无结果时允许空集和 STOP。实体/时间/slot 精确查询可增候选，但不能绕过来源合法性。
4. **结构化校验/图扩展：**MP 做时点投影；ME 检验 actor、stage 并允许已验证的一跳事件链；MS 定位 parent；RS 检查方法适用条件。未经验证关系不得作为事实。保留原始 dense/BM25/结构命中和拒收原因供审计。
5. **候选去重与排序：**对相同来源/同事件链合并证据，确定性 tie-break 用可复现 record_id；排序参数、top candidate 数和查询变体只在 train/dev 冻结，禁止根据 test/评分现场调整。
6. **按头打包：**只取得当前 GET 对应的一个确定性 reading unit，不让 PM 任意看全部候选。Phase-1 固定 query、每头最多一次 GET，保留16个可重放终点；Phase-2 才允许读后改 query、同头至多2次、EXPAND_MS、总GET≤5。区别“候选池数量”和“实际交付条数”，不能把 Phase-1 固定打包说成已实现学习的可变 top-k。
7. **读取计账：**READ 成功时返回 ReadingView，更新 Observation、累积输入 token、首响应成本和调用身份；原生上下文不够则 mask/明确失败，不因便利截掉原文。GET 只做检索与读取，**不调用 G/J**。

### 5.1 检索与 PM 特征不能混为一谈

BGE 用作资源检索时的输入是 query 和 bank 内每头 index_text，输出是私有 candidate ranks；BGE 用作 PM 状态编码时，输入必须是当前可见 prefix 和**已经 GET 的** reading_view，输出给 actor 的可见状态向量。二者分别缓存、分别绑定身份。不能因为 organized_encoding.py 已能输出 BGE 向量，就称 resource_organization.py 已实现 BGE 检索。

V3.1 Phase-1 曾建议给 actor“每头前三个候选的分数与大小元数据”。这属于主动的预检索设计，不是免费公开事实：必须有 prefix-only 产生方式、检索成本、可见性审计和对所有 baseline 的同等暴露。若与既有 actor 边界不符，先退回 availability/count-only，另将 scored metadata 作为有身份的消融条件；**绝不暴露记录 ID、未读正文、个人关系或 oracle 需求标签**。

### 5.2 reading_view 白名单与全文保留

仅交付 head、按读取顺序的 ordinal、基于来源的自然叙述、合法报告时间、事件阶段、对用户有帮助的必要上下文及实际 tokens。可附“用户曾报告/计划/尝试”之类认识论提醒；但内部 owner_id、source identity、事件图 ID、retrieval score、审阅标签、裁判答案、source-hash、数据划分不能进入 G 文本。模型指令只允许使用其中有依据且对当下适用的部分；**可选记忆即使相关也可以不提**。

## 6. A6 bank_validator 必须包含的七组检查

1. **身份与谱系：**owner/session/family 无串库；RS train 与对照/测试谱系不重叠；原始字节和派生 lineage 都存在。
2. **严格过去与写入就绪：**不存在 cut 后来源、未完成当前会话 SUM、未来派生 ready_at 的读取；未来计划保留“计划”阶段而非“已完成”。
3. **原文与依赖闭包：**所有 SourceSpan 的 role、字符偏移、quote、sha 匹配；完整输入依赖和 RAW parent 均能回溯；同文多处出现不猜位置。
4. **语义与阶段：**逐命题 source-entailment、人物指代、建议/意向/尝试/结果不混淆；已知三条 MP/ME 失真回归必须过；unverified 不升为 confirmed。
5. **时间投影与图关系：**明确更新、相互冲突、事件先后、父 SUM/RAW、关系方向在合法时点可重放；无证据关系不能自动 supersede 或派生疗效。
6. **RS 授权与适用性：**许可证、原始出处、风险等级、案例完整上下文、无专业批准的研究-only 隔离、负例不当正例、F-resident 对照均保留。
7. **读取/渲染/版本：**Graph/NeedCard/hidden ID/未来或未读正文不能进入 actor/G；token 数、原生 capacity、Query/Index/Renderer/Terminal hash、GET/EXPAND 成本与回放一致；失败时不静默截断。

## 7. 可直接写成 pytest 的回归矩阵（至少这些）

| 测试 ID | 输入情形 | 必须观察到的行为 |
|---|---|---|
 T01 | 同名不同 owner | 全程不能跨 owner 召回 |
 T02 | 未来会话中的真实旧事实 | 因来源未来而被拒收，不能事后归因 |
 T03 | 当前会话未完成却有预制 SUM | ready_at/cutoff 拒绝 GET_MS |
 T04 | 用户说“打算搬家” | MP 当前地址不能被更新为新城市 |
 T05 | 用户明确报告已经搬家 | 新地址生效，旧值保留版本链 |
 T06 | 同 slot 冲突却无更正证据 | materialize 返回 conflict/unknown，而非强选最近 |
 T07 | 支持者建议“打电话” | ME stage 不得自动变成用户尝试 |
 T08 | 用户报告已经打电话且吵架 | ME 阶段与自报结果正确，原建议被正确更新 |
 T09 | “关系好像好些” | 不变成“关系已经修复”的确定事实 |
 T10 | 同名不同人、同人不同称谓 | 仅经校验合并，未验证不串实体 |
 T11 | 摘要删掉罕见汽车零件名 | RAW 倒排仍能定位父会话；纯 SUM 不假装含原文答案 |
 T12 | EXPAND_MS 对未读 SUM/错 parent | 拒绝并无资源/成本侧效应 |
 T13 | 一句源文重复出现在两个 turn | 引文定位歧义时失败关闭 |
 T14 | LLM 产出无证据 updates/outcome_of | 只能存未验证候选，不改变有效状态 |
 T15 | 许可不符或高风险 RS 方法 | 不进入部署可调用候选 |
 T16 | RS 标签高但案例内容不当 | 保留审计负例，不能直接加入正例训练 |
 T17 | 没有匹配资源的前缀 | 可返回空候选，环境允许 STOP |
 T18 | static 查询、bank/model/seed 相同 | RRF 排名及 Query/Index hash 完全相同 |
 T19 | adaptive 查询含已读正文 | 能调整排名，但不能包含未读文字/NeedCard |
 T20 | GET 成功、被拒及容量不足 | 真实 token/latency/capacity 记账正确，无 silent truncate |
 T21 | 改任何 TerminalKey 字段 | hash 改变；不得复用旧答复/奖励 |
 T22 | 未读 BGE similarity、图邻居、隐藏字段 | actor、critic、G 不可见；每个 baseline 观察范围相同 |
 T23 | 用户来源文本含指令式 prompt injection | 只作为 quoted data，不能成为系统指令 |
 T24 | RS 与 EvoEmo 来源祖先重叠 | 由 family 闭包过滤 |
 T25 | MP/ME 的时间只知 session rank | 可以合法按 rank 回放，不能编造 calendar date |

测试用人工构造的**确定性小样例**先通过，无模型、GPU、外部 API。随后用旧的三条失真案例、11/11 事实14题和冻结的 ES-MemEval train/dev QA 做回归；不得在 final/test 上反复调 prompt、索引权重或抽取规范。

## 8. 检索与最终回复分别怎样验收

**能力测试（A5/A6）：**分头报告有证据来源的 Recall@1/3、MRR、时间/人物/阶段正确性、完整证据链、SUM 事实保留率、RAW 回查定位成功率、错 owner/未来/未验证关系泄漏数、p50/p95 检索与序列化等待、实际 token。与词面、BGE Dense、BM25、Dense+BM25、加时间/结构、加图扩展逐层比较。可用 11/11 已有14事实题和 ES-MemEval train/dev 的正确原文来源，注意独立 owner 数与任务数不能混淆；计划中的1,261 QA 数量须用本次实际可用 manifest 核验。

**价值测试（B线和G线）：**同一合法前缀同一 G，对照 OFF、固定检索、自动混合、oracle source、RAW、SUM、SUM→RAW、无关/过期/冲突资源。先分离“源不可达”“表示错误”“G 不会利用”“PM 不该读”，再分别修复。资源确实能帮事实问答不等于自然支持一定改善；没有增益时仍可以推进 G1 训练、BC/PPO 工程级更新，但正式主张须由校准反馈和留出人评决定。

对照绝不因为 R4 比 R2 复杂就默认为好：图扩展如果放大抽取错误，退回 R3 并留因果归因记录。没有可靠关系时只用时序源证据，不伪造图优势。Latency、构建成本和 G 的可用上下文共同决定部署方案。

## 9. 两条 Codex 如何施工，不互相覆盖

**C0（集成负责人/WS-A 主写，WS-B 审核）：**按本规范 §2–3 冻结 SourceSpan、ResourceRecord、TemporalClaim、TemporalRelation、ReadingView、RetrievalTrace、TerminalKey 的 dataclass 与 JSON Schema；定义 canonical JSON/hash/nullable-time，给出至少10正10负 contract 测试；确认旧 PrefixSpec 适配及 schema 版本。C0 完成之前不要让 A 与 B 各造一个互不兼容的 contract。

**WS-A（资源与 Generator 文件所有者）：**

- A1：复用严格过去 source_registry，保留401 EvoEmo完整会话、原文角色与谱系、许可、来源哈希。所有派生先从 RAW 来。
- A1b：加载旧 713 MP/1,523 ME/MS-RAW 与 RS 草稿作为 bank-v0，明确 unverified；让 B 线能立即使用。
- A2：按 §4.3 构建异步 MS-SUM/RAW/源跨度/父文回读，交付所有会话的 OK 或 unusable/reason 记录。
- A3：按 §3/§4.1/§4.2 建 MP 版本快照、ME 事件组/阶段/有来源的关系图；先过三条已知反例和 T04–T14。
- A4：按 §4.4 构造 RS 方法/案例和适用条件，负例、高风险与许可分开。
- A5：按 §5 真正接 BGE dense+BM25+RRF，建立每头独立索引及 manifest，保证源码索引与模型身份可重建。
- A6：按 §5.2/§6 完成 reading_view、GET/STOP 请求包、bank_validator 与 T01–T25，冻结 bank-v1；无 G/J 调用。
- A7–A11：依主方案固定 G0、构建 G1 条件训练并检验资源利用；此规范不改变生成器、QLoRA 或独立偏好资格。

**WS-B（反馈、环境、策略文件所有者）：**

- B0：继续合法 prefix 普查与 owner/family 先行折分；不等待 A1/A5。
- B5：以 C0 Observation/ReadingView 构建同一有限四头环境，GET 不调用 G/J，空头与原生容量正确 mask；保留16个纯静态终点。
- B1/B2/B3：NeedCard、检查项和判官仅评价侧可见；资源 v0 标签等级不得升级；未确认软质量仍按 unknown。
- B6e/B8e：在 bank-v0 上实际做可回放工程终点与 BC/PPO optimizer 更新，不因 A5/B3 未合格而零训练；标 engineering_only。
- B6/B8/B9：等冻结 bank-v1、校准反馈与 G0 后做正式同条件比较；Phase-2 的 adaptive、EXPAND_MS 与隐私掩码使用 A 线已冻结 API，不私下改 A 的排序。

**集成负责人独占**：跨工作线接口、状态表 EXECUTION_STATE.json、sync point 合并及身份登记。两 Codex 各在计划指定的 WS-A/WS-B 分支施工，独立 PR 进 integration；不要同时编辑主状态表或共用文件。任何修改都写 task RESULTS_ZH.md、输入/输出 hash、运行等级、未过/替代设计与复核命令。

## 10. 阻塞、替代设计与真正的完成定义

| 发现的问题 | 立即执行的修复 | 仍不足时的分支 |
|---|---|---|
 人物/关系误提取 | 角色/实体 disambiguation、精确原文蕴含、双模型校验、拒收 | 不写确认画像；退到带来源的 RAW 片段 |
 事件阶段混乱 | action_stage 与 user reaction 分开提取，已知反例回归 | stage=unknown，不向 G 断言已完成 |
 BGE 召回不足 | BM25+exact entity/slot+时间过滤，调整 index keys | 在 B 线增特权 oracle-source 对照；自动检索失败单列，不停 G/PM 工程 |
 关系图噪声放大 | 只用确认边、一跳限制、来源闭包和时间门 | 退回时间索引+无图的 R3，不强训 GNN |
 SUM 漏掉关键证据 | 原文事实键索引、句级回引、重写不合格摘要 | unusable+RAW fallback 另立条件；Phase-2 EXPAND |
 RS 案例/方法无帮助 | 修适用条件、案例质量、负例和 G1 OFF-better 训练 | 仅方法/常驻 F 对照；不虚造正例 |
 模型用错了正确资源 | Step-2 计划、相关/无关/冲突/OFF 条件 SFT | G0/G1 失败明确报告并继续修训练，不把错归检索 |
 PPO 不胜强固定或 BC | 检查读后可见信息、停止、动态查询与奖励稀疏 | 保留完整失败结果；不降低对照强度或直接宣称成功 |

**资源系统“完成”的必要证据**：代码/JSON Schema/25 组回归测试；可重建的四头 bank 与索引；至少一条实际 Prefix→GET_RS/MP/ME/MS→STOP→Renderer 的纯本地端到端回放；来源/时间/阶段/关系和私有观测的反例均被拦截；旧事实 QA 与新检索消融报告；MS-SUM/RAW 的合法父文回读；manifest 身份和等待/token；没有触碰历史 frozen 结果。这是可验收的工程里程碑，**不是资源改善自然支持或论文可发表的保证**。

## 11. 可溯源研究方法（参考而非软件依赖）

- BGE-M3 原论文及官方 FlagEmbedding： https://arxiv.org/abs/2402.03216 ； https://github.com/FlagOpen/FlagEmbedding/tree/master/research/BGE_M3 。官方支持 dense/sparse/multi-vector；当前仓库装配的模型封装是 dense。
- LongMemEval（ICLR 2025）： https://proceedings.iclr.cc/paper_files/paper/2025/hash/d813d324dbf0598bbdc9c8e79740ed01-Abstract-Conference.html 。借用会话分解、事实键增强、时间查询与知识更新/弃答分项测试，不将该 benchmark 当自然支持终局质量金标。
- Zep 时序知识图谱： https://arxiv.org/abs/2501.13956 ； https://github.com/getzep/graphiti 。借用事实有效时间、记录时间、来源及关系更新语义；不要求当前立刻部署其完整数据库、自动实体推断或 GNN。

**与主计划冲突时的处理**：研究目标、实验动作域、奖励资格和权限以主方案 §0 优先；此规范为 A1–A6 的具体 schema/检索/校验细化。若需改变 Phase-1 的16终点、公开 observation、TerminalKey 或研究对照，必须由集成负责人以独立版本变更记录明确批准，不能由某个 Codex 在实现细节里静默替换。
