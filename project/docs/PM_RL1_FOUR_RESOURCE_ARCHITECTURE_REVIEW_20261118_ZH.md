# 四资源架构与能力缺口审查

日期：2026-11-18。作者：WS-A。范围：CPU 架构审查及最小验证提案，**不是研究方案修订、bank-v1、A5、A7 或运行授权**。

## 1. 结论与证据边界

当前系统已经证明四头资源可以带来源、按合法前缀、确定性地送到生成请求；**尚未证明 RS/MP/ME/MS 各自具有相对于 OFF 的自然支持增量价值**。四头的潜在价值也不同：MP 提供当时有效的人物约束，ME 提供事件进展和已尝试/拒绝的行动，MS 提供可回查的完整背景，RS 提供可选支持技能及其适用边界。文本变多、命中有词面相似、事实问答答对，分别只是中间证据。

这里要区分三种“增量”：相对当前前缀多了一段文字；多了前缀没有、且有证据支持的信息；该信息改变了正确支持行为并改善回复。MP/ME 来自同一批 MS-RAW，并不是三个独立知识源；它们可能提供的能力是更可靠的压缩、时点查询和事件组织。相同原话被三个头重复送入 G，不能记作三份独立信息增益。RS 则可能只是提醒 G 已有技能；方法“正确”也不保证此次提醒值得额外等待。

**RS 不必采用 RAG。** 如果所需技能是少量通用倾听动作，G 本身或简短常驻目录可能已经足够。只有在同 G、同前缀下，经过适用性核验的方法读取相对 R0/F-resident 带来可重复的质量或成本优势，外部检索才有实证理由。完整案例还需要证明其在相同方法之上的额外收益。当前 875 个 RS 案例与八类 ESConv 注释目录均不能代替这两个证明。

建议保持一个不可变来源库，建立四种有类型的查询/阅读投影，而非四套不加区分的向量库。先修人物、时间、阶段、可选使用和适用性，再比较排序。图只承担有证据的关系连接；没有确认关系时，时间表和来源索引更诚实，也更便于归因。

本轮不改 C0、不重建 bank、不换排序、不调用模型。集成基线为 `320a33d1d871199d171f998300ce926b341ca1a8`；G0e 候选实现和既有请求核查固定为 `8ba20d21da4bdcbb552946241563bd41dbe46c6c`（PR #12，叠在 PR #10）。审查时 PR #4、#10、#12 尚未合并；C0 0.2.0 的工程冻结与 PR #4 的研究者采用是两件事。V3.1-R1 是候选施工规范，不能把它写出的字段/API 视为当前已实现能力。

证据分三层，不能混用：

- **本轮重算**：固定 bank 的 3,188 条记录加载及 37,894 个来源跨度引用验证；83 条既有开发样本的全部合法候选、分数、排名、查询身份重算一致；120 份既有 CPU 请求的正文白名单、源记录、TerminalKey/ExecutionTrace、已存 token IDs 长度和容量检查通过。跨度数是引用次数，不是独立事实数。本轮未重新分词。
- **引用已集成证据**：4,119 前缀的 16,476 次 GET 中 15,956 次成功；B5 的 24 前缀/360 可达终点/1,413 顺序。它们证明读取和回放，不证明质量；本轮未重跑这些大表。
- **尚缺**：独立候选适用性标签，当前 G 的语义阅读实测，同 G 的 OFF 配对质量、资源交互、真实模型端到端等待。它们保持 pending，不能由前两层推导。

## 2. 历史失败与当前实现的对应

本次核对了下列七份指定文档；账本按资源、来源、生成、归因和统计相关条目核对，并非重新裁决全部 503 个历史 issue。输入文件 SHA 见本轮 [CPU manifest](../outputs/pm_rl1/v3/resource_architecture_review_20261118/cpu/MANIFEST.json)。引用历史比例只说明当时发现问题的证据，**不作为当前 bank-v0 的失败率**。历史文档中的旧硬门、旧测试折和旧运行许可不转成当前授权。

| 历史证据与根因 | 当前已做的防护 | 尚未排除的根因；下一层验证 |
|---|---|---|
| [全局账本](PM_V1_TO_V1_5_GLOBAL_FAILURE_LEDGER_ZH.md) V1-SYS-01、V15-ACT-09：训练/比较/外部使用不同 bank、prompt 或生成合同 | source/bank/index、renderer、G、decode、Step-2、请求/终点都有版本；新 G0e 不重命名旧 key | 同模型真实运行还未发生；未来换表示/排序后必须重建终点，不能迁移旧质量标签 |
| 同账本 V1-RETR-01、V15-ACT-08/13：source-on 与实际选中条目错位；把机会、库覆盖、排序失败合成一种错误 | 先合法过滤、完整私有检索轨迹、每次 GET 绑定自己的记录组 | v0 无适用性门、无相关性下限；合法候选非空就取 Top-1。须分别标注“没有安全适用候选”“候选存在但排序错”“本来无需读取” |
| 同账本 V15-DATA-17、V1-CREDIT-01：有效/无关资源混入同一 treatment，多源干扰被归给 PM | 有同前缀固定子集身份与 OFF 请求 | 当前尚无当前 G 的单头效应或交互效应；先 D，再 E；不能用 ALL 好坏代表各头价值 |
| 同账本 V15-DATA-01/27、V1-DATA-02：同源重叠、全局 situation/summary 特权泄漏 | 84 个 ESConv 重叠 family 排除；保留 esc1198 多 owner 关联及同折约束；registry 只取对话话语，G 只投影可见前缀/已读正文 | 同库历史曝光仍存在；source lineage 合法不代表独立确认。禁止把重新 hash 的材料称为从未见过的测试 |
| [Memory 根因](PM_V1_5_MEMORY_FAILURE_ROOT_CAUSE_20260802_ZH.md)：MP preference/profile 混义；ME outcome/routine/context 混义；旧 gold 没绑定实际返回候选 | 三条已知失真有独立修复映射；其余 unverified；ME 不强推完成阶段 | 当前 MP 不是 slot 查询，ME 仍大多 unknown；“原话出现过”不证明归纳/阶段正确。标签须绑定 exact candidate + view + query，而非 head 名称 |
| [V5.3 汇总](PM_V1_5_V5_3_CONSOLIDATED_FINDINGS_20260806_ZH.md)：旧 ME 编译 3/747，严格“行动+结果”门使覆盖塌缩 | v0 迁移保留历史原话，并不要求都带结果 | 1,525 条 ME 多不具备阶段/后续结构；不能用较大条数宣称事件理解已修复。A3 保留建议/意向/尝试/自报结果，不能回到只接受成功行动的旧定义 |
| 同汇总：MP 的 `Job:`、`progress` 撞词及伴侣/本人混淆 | 当前未直接把旧 `Job:` slot 字段拼入 MP 阅读，正文主要为原话 | 当前匹配完整 reading_text，通用提示词/对话词仍参与打分；subject/entity 为空，用户与第三方的指代未结构化解决。不能照搬旧 24/68 数字或声称当前同样失败率 |
| 同汇总：MS 高频通用词混淆；BGE 开发差异按用户聚类后不显著 | 当前保留可重放词面基线及完整来源 | 当前 v0 也不是当年的 typed-tiered baseline；旧 BGE 优势不能迁移。长 RAW/CASE 覆盖更多词会更易获得交集，分数又没有文档长度归一化；这是算法风险，不是已测准确率 |
| 同汇总及 Memory 根因：强制用全部证据使 MP+MS 触发兜底，ME 与低负担 RS 指令冲突 | G0e Notes 明确允许相关记忆不提及；没有“逐条必须引用”守卫 | 文案取消强制不等于 G 已学会忽略。必须测可选不提、已拒建议、不同头冲突，保留负效应和兜底成本 |
| 同汇总：结构 guard 10/10 通过仍出现第一人称冒用；后续修复了当时的针对性案例 | RS/RAW 保留 seeker/supporter；Notes 说明外部案例不是当前用户经历，文本作 quoted data | 没有当前 G0e 的人物/说话者语义实测；历史修复不等于新 prompt 自动合格。转述者、被谈论者、当前用户、助手四者必须区分 |
| [Strategy RAG 需求](PM_V1_5_STRATEGY_RAG_REQUIREMENTS_AND_ESCONV_ADEQUACY_ZH.md)、[RS 卡质量](PM_V1_5_RS_CARD_QUALITY_ZH.md)：数量、标签和来源反馈被误当方法有效性 | 875 仅叫完整案例；11,590 strategy 与 13,172 treatment 保留多对多谱系；八类目录定义 unknown、只供工程 NeedCard | 没有经验证的方法卡、使用/禁用条件或专业资格；当前研究案例允许读，不代表安全适用或部署合格 |
| 全局账本 V1-EVAL、V1-STAT、V15-ACT-04/05：单判官、顺序偏差、同前缀/同 prompt 冒充独立样本、去重抹掉成本 | C0 固定前缀检查表/分母，pending/uncertain 分离，执行轨迹独立于规范化终点 | Judge 资格和自然支持人评仍缺；重复路径不是新增样本；共享回复缓存也不能删除每次路径的读取/等待成本 |

历史 RS 小样本通过、历史 ME 抽取失败、旧 BGE 的优势和代价，都只对各自的输入、实现、G 与评估身份成立。尤其不能据旧 ME 失败永久禁止 A3/G1，也不能据旧 RS 人评把当前原始案例升级为专业方法。

## 3. 当前四头真正是什么

### 3.1 持久化、写入与更新

来源是 JSONL `Entry → SourceSession → SourceTurn`，私有索引按 owner/session/source_id 查找；记录保存于统一 `records.jsonl`，迁移账在 `migration.jsonl`。当前 `index.json` 固定词面查询/排序/单整条打包身份，**没有持久化 dense 向量或 BM25 索引**。实际查询扫描已合法的记录，用缓存的词集合算交集。

| 头 | 实际持久化/阅读对象与实测数量 | 哪些是可信证据，哪些不是 | 当前写入/更新/失效能力 |
|---|---|---|---|
| MP | 387 条 `assertion`；正文“历史自报、当前有效性未验证”+原话；旧编译 unit/slot 留在私有 body | 精确引用与 speaker/rank 可验；`user_reported` 是来源立场，不是世界事实；没有当前画像投影 | 从旧池迁移一次，所有 387 条 unverified；无语义 ADD/UPDATE/INVALIDATE 或冲突裁决 |
| ME | 1,525 条 `event`；原话+未知阶段警示，修复条目含纠正转述；1,523 unknown、2 attempted | 3 条 development_reviewed 不等于独立确认；无结果不表示失败；自报结果不表示因果疗效 | 旧 1,523 加 2 条 MP→ME；1 条原 ME 修复；无 event_group/有证据后续链投影 |
| MS | 401 条 `raw`，整个已结束会话逐轮 seeker/supporter 原文 | 原始话语准确，不保证原始 supporter 建议正确；不是摘要 | RAW 不变；没有生产 MS-SUM、事实键索引、SUM→RAW 回查；ReadingView.expandable=False |
| RS | 875 条 `case`，完整 ESConv train 对话及外部案例警示 | 来源与全文可验；不证明支持动作有效/适用；不是 875 种方法 | 由旧 strategy/treatment 来源并集回到案例；旧 12 案例草稿中 6 repair/6 quarantine、3 方法草稿 quarantine 未纳入 |

实测全部 3,188 条的 `subject_id`、`entity_ids`、`event_time`、`valid_from`、`valid_to`、`invalid_at`、`parent_event_id`、`related_claim_ids`、`index_keys` 均为空；`semantically_supported` 为 0。字段存在于 C0 Schema 不等于编译器已填好。1,912 条 MP/ME 的私有 `body.legacy_unit` 保留历史归纳，**当前普通 GET 不把这些旧归纳全部传给 G**；这是保守降级，不可描述为已验证原子事实库。

registry 已有附证据的行政 INVALIDATE 和快照差分 ADD/UPDATE/INVALIDATE/NOOP；当前固定快照操作数为 0。行政源版本变化不是人物状态理解。bank 加载会核对 source、manifest、span、family 与版本，不允许未验证关系传播；要采用新 registry 仍需生成新的 bank/index，不能把旧 bank 接到新源快照上。

**MP 的重要剩余问题：**713 个编译 MP 中，387 保留 MP、2 按已有证据转 ME、324 隔离。旧池 388 来自各 owner/slot 在**全部轨迹上**取最新 rank；325 个未入旧池条目中一个经明确修复转 ME，其余 324 的 replacement 都来自更晚会话（本轮逐项核对）。当前读取不会传送未来正文，但入池资格已受全轨迹投影影响，不能称为“截至任意前缀当时能写出的画像库”。它会造成过去版本覆盖不足，也留下 availability 依赖未来建库选择的风险；这是研究级时点建库资格问题，不等于已证明 G 看到了未来事实。A3 应从合法源逐步重放写入并做“追加未来会话不改变旧时点投影”检查，逐条复核被隔离旧项；**不能直接把 324 条放回 bank 来凑覆盖率**。

### 3.2 候选、排序、阅读与 G 的实际输入

统一过程为 `Registry.context → Bank.candidates → retrieve.v0.search → Reader.read → RequestPacket`：

1. 前缀须匹配源文、fold 与 family；记忆仅同 owner/dataset、source_rank 严格过去、日期不晚于当前、ready rank 已到。RS 只含预装 train、排除 84 重叠 family 及当前祖先闭包。保留 esc1198 的 p13/p18 来源关联，而非用字符串去重消灭其中一个 owner。
2. 查询仅取合法前缀最后三轮（含 supporter），词表为小写 `[a-z0-9']+`。分数为 `|query_words ∩ reading_words| / |query_words|`；RS 平分按 record_id，记忆平分按较近 source_rank 再 record_id。没有 BM25、dense、RRF、实体/slot 查询、阶段或 RS 适用性重排；不能把只在平分时偏近当作事实时效判断。
3. GET 只取第一条完整记录，MP/ME 也不是候选规范的 10 条/3 事件包。来源合法但得分 0 仍可能被取；没有合法候选返回 typed unavailable，容量不足返回 capacity；不偷偷换下位条目或截断。失败不产生成功 ReadingView、不推进获取序号。availability 是合法池大小，不是收益概率，也不是最终可读条数。
4. ReadingView 只含 head/view/ordinal/正文/报告时间/tokens/阶段/展开标记。正文附 `[头; reported 日期; stage …]`。ME 的信息主要仍在原话里；对未知日期和阶段不造精度。
5. [G0e 候选 renderer](https://github.com/chensiyu7812/Metacom5_3/blob/8ba20d21da4bdcbb552946241563bd41dbe46c6c/project/src/metacom_pm/rl1v3/render/request_packet.py) 把已读块按 RS→MP→ME→MS 排序、HTML escape，放在一条 user-role Notes 中，再放当前可见对话。它重读核验 acquired，才创建请求；私有 envelope 保存 TerminalKey/ExecutionTrace，发送模型的只有 messages/input_ids/decode。OFF 完全不含 Notes。合法不同 GET 顺序保留各自执行轨迹，但同子集形成同一规范化正文/终点。

G0e 身份为 `G0e:b624c7c3f99ffe6b35eca29e2f93ea9e624e66b31303415e4b9c4b1bc4c6c07e`，renderer `renderer:e04b6de4d78624db4379c25537b9e6f8571b00b4c4edee681c7b5b3e31bb3d27`，decode `decode:de376c64c6da1bc02d0752811d8a0dffeec41f2bd9cf869a1e8c1af16f448069`，Step-2 为 `pmrl1v3-g0e-no-plan-1`。这不是 A7 研究级 G0；旧 bank-v0 tokenizer-only renderer 是另一身份。本轮核查的是上述固定 CPU 请求，未运行 Gemma。

### 3.3 当前保护的实际限度

- `reported_at` 是来源会话日期/rank；个人来源 `ready_at=r+1` 是**逻辑回放会话结束边界**，不是测得的异步 writer 完成时间。RS 日期未知、按预装快照合法性处理，不能与个人会话 rank 硬比。`event_time/valid_to/invalidated_knowledge_rank` 不应相互替代。
- owner 过滤保证资源属于该用户的历史，**不保证原话里的“他/我伴侣”指的就是用户本人**。原始角色存在，但命题人物未结构化。
- RS `risk_tier=unknown / usage_scope=research_only / positive_eligible=False`；C0 对高风险部署有约束，但当前 engineering 检索没有完成每案安全/适用性审查。不能称当前候选已全部“安全适用”。
- EvoEmo 上游许可在 registry 中仍标 unresolved/inherited engineering scope；ESConv 标学术研究范围。可追溯不等于获得部署或再分发的新许可。
- 白名单阻止私有 ID、NeedCard、Judge、未读正文和未来源文被序列化；HTML escape/“quoted data”只提供结构边界，**不证明模型能抵抗原文中的指令诱导**。

## 4. 应采用的载体：共同底座，分头语义

以下是待验证设计，不修改当前 C0。先用 JSONL/SQLite 等可审计表实现即可；向量数据库数量不是研究问题。

| 头 | 建议主载体与索引 | 写入/更新/失效 | 普通 RAG 对照及预期差异 | 交付单位 |
|---|---|---|---|---|
| MP | 原子 claim 表，键含 owner、subject、slot、版本；实体别名候选表；slot/时间倒排；语义召回只补候选 | 会后抽取→原话/人物/蕴含审查→同 slot 比对；明确更正才 supersede；冲突保留双方；known-at 与有效期分开 | 对照同样源文/同预算的纯语义 Top-k；检验人物和时点错误是否减少，不能仅看召回词相近 | 当时可知的少量状态+出处语气+未知/冲突边界，不用“最后一条一定真” |
| ME | 事件表（actor、对象、阶段、用户反应、结果）；event_group 候选和已确认边分表；时间/实体索引 | 建议、意向、尝试、完成、自报结果分别保留；有源证据才连 follow_up/updates/outcome_of；未知不补因果 | 同候选集合下比较语义召回、加阶段/时间、再加已验证一跳关系；图的贡献单独消融 | 一段可理解的事件链或原话事件；不把“建议过”改成“做过”，不把“觉得好些”改成“治疗有效” |
| MS | 不可变 RAW/turn/span；独立 SUM/proposition→span；事实键/罕见实体索引；SUM→RAW parent | 会话完成后才写 SUM；逐句审查/拒收；SUM 失败保持 unusable。真实 ready_at 与逻辑重放 rank 分开记录 | 比较单会话 RAW、同源 SUM、事实键召回、定向源片段、全合法历史注入；容量不够明确不可行，不能截前 N 词 | Phase-1 每条件固定一种 view；Phase-2 从已读 SUM 可见序号展开父 RAW，全文和等待计账 |
| RS | METHOD 与 CASE 分表；方法出处/动作/边界/风险；方法↔案例证据关系；case 标签仅索引 | 专业材料按许可/风险审查；更新另立版本；案例反应是观察，不作因果认证；不合格案例留负例 | R0、F-resident、Method、Method+case；同方法集合、同 G，应用门与排序分开检查 | 方法优先；案例只有必要时才附，并明确其人物/情境是外部个案 |

共同底座建议包含 `source_session / source_turn / source_span / claim_version / event / entity_candidate / verified_relation / method / case / materialization / index_manifest`。关系表必须保留端点、证据跨度、认识状态、获知时点与版本；未验证关系表可供离线审查，不能进入当前真值投影。共享 dense 编码器、BM25 或同一存储后端可以减少重复计算，但每头独立索引文本、合法候选、排名和打包规则。

**双时间最小例子**：在会话 r5 才得知“我三月搬家了”，不能让 r4 的画像提前改变；即使事实有效期从三月开始，系统获知更正仍在 r5。r5 当前可见话语能否更新长期 bank，须按 writer 提交边界区分；当前回复可直接使用合法前缀，不必偷偷从未 ready 的派生记录取得它。只有 rank 时保留 rank，未知日期仍未知。

统一端口保持 C0 的 `PrefixSpec → 私有候选/来源 → GET → ReadingView / ReadFailure → RequestPacket`。结构化查询、关系扩展和源回查都在私有 executor 内，不能让 PM 免费查看未读 slot、事件邻居或候选正文。PM 仍先看批准的 availability/count 和已读文本；若未来要给预检索元数据，需单独审阅观察范围、等待和公平对照。

## 5. RS：四种实现必须直接比较

| 方案 | 可能的增量能力 | 风险与成本 | 必须排除的替代解释 |
|---|---|---|---|
| R0 | G 自身的支持技能足够；无额外信息也可能最佳 | 不提供外部方法，可能漏掉特定技能 | R0 必须真正没有资源/常驻目录；与其他头使用同一组合 |
| F-resident | 少量技能提醒，避免每次检索和误选案例 | 每请求都增加 token/prefill/context；目录过长可能稀释当前用户诉求 | 相对 R0 的变化是提示干预，不是免费资源；不能把含 F 的“零 GET”混叫真正 OFF |
| Method retrieval | 从较大、异质的技能集合中读取适用方法和边界 | 需要可靠材料、适用性和召回；检索可能比方法本身更难 | 必须与同一个方法集合的常驻短目录比较；不能换更高质量库后把收益全归 RAG |
| Method + case | 说明具体如何实施方法、如何响应用户反应 | 更长、案例主体误认、模仿不当建议/自我披露、情境不适用 | 保持 Method 条目完全相同，只增关联案例；案例情绪改善不证明方法因果有效 |

当前 case-only bank-v0 是额外工程参照，不能重命名为 Method+case。RS-v0 目录八类中七类可供 NeedCard writer 选择，定义仍 unknown；“Providing Suggestions”这样的注释不等于有适用/不适用条件的专业方法。11,590 策略层和 13,172 treatment 层相互派生，绝不相加为 24,762 个独立方法。

最小下一步是少量、来源明确、低风险、能给出实际使用边界的候选方法，保留 R0；不先追求 24–40 数量。F-resident 是否足够、检索是否节省上下文、案例是否增加误用，均为待验证假设。若 Method 相对 F 没有收益，不必为了维持“RAG 四头”叙事强行检索；若案例有害可只保留方法。改变正式对照/动作语义须走版本与集成审阅，本报告不自行实施。

## 6. Generator 阅读表示：当前 Notes 与备选

**当前 G0e Notes 本质上仍是带全局提醒和资源标签的文本拼接。** 它已优于无边界原文堆叠：有头标签、报告时间、阶段提醒、角色原文、外部案例警示和可选不提原则；而且 G 确实会收到正文，不同于历史 V5.2 中 G 根本不看 MS/ME 原文的机械回复拼接。但它还没有逐命题的主体/有效性/使用边界，也没有当前 G 的阅读理解证据。结构改善不等于语义问题已经消失。

建议先做离线的“有边界阅读块”对照，不增加私有字段曝光，不改冻结 ReadingView Schema。公开文本只表达已有证据能支持的内容：

| 公开段落 | 可以提供什么 | 不得提供什么 |
|---|---|---|
| 内容 | 原话/有跨度支持的自报命题，或有许可出处的方法动作 | 未验证归纳、关系传播新事实、隐藏候选内容 |
| 人物与报告时间 | “你曾报告”“你当时提到的伴侣”“外部案例的支持者”；已有日期或相对会话信息 | owner/source/record/图 ID；无依据把第三方绑定为用户 |
| 有效性/阶段 | “当时计划；尚无执行报告”“是否仍有效未知”“当时两条报告冲突” | 当前未出现的更正；把 uncertain 写成 false；宣称独立验证 |
| 使用条件 | 方法材料已支持的适用条件；一般“仅当与当前问题有关时参考” | NeedCard 的 required 标签、oracle 的应读/最优子集、判官结论 |
| 不使用条件 | 已证据化的限制；“不要把外部个案当作用户经历”“不要把支持者建议当成已执行” | 开发者针对该前缀的效果判断/成功率暗示 |
| 可选性 | 相关信息可以只约束措辞、不必主动提及；可直接回应当下情绪 | “每条都必须用”“为了得分提及历史” |

例如来源只说 “I'll let him know”，阅读块应保留原话及“当时表达意向；未确认已告知”，不能补一个完成事件。来源是另一人和狗的支持对话时，应称“外部案例；案例支持者的自我披露不能当作你的经历”，而非把原文第一人称改成助手事实。这些是表示规则示意，不是本轮生成的新用户事实或已合格方法卡。

边界提示可以放进现有 `reading_text` 做候选，但**文字、token、bank/renderer/request/TerminalKey 必须有新身份**。只改变格式的 C 层实验需保持原始证据内容完全相同；若同时新增实体审查/时间判断，另立内容改进因素，不能把全部收益归给格式。要新增结构化公共字段，则需要 C0 新版本及 B 审阅；不能把私有 body 直接 dump 给 G。

G 的比较分开进行，避免把检索、表示与训练一起更改：

1. **G0 no-plan**：固定权重/backend/decode，先作为 D/E 的共同基线；不按哪个 G 放大资源收益选模型。
2. **同 G0 + 显式 SupportPlan**：只能引用已读公开序号，use 不强制提及，允许 avoid；计划不给用户。单次两段与两次调用须分别绑定身份，统一最终回复上限，记录额外计划 token、调用、校验/重写和首个可见回复等待。不能把未显示计划的首 token 当用户已收到回复。
3. **真正训练的 G1**：后续按授权进行资源采用/核对/适当忽略训练，含 OFF-better、无关、冲突、已拒建议、相关但无需提及；严格 owner/family 留出，独立偏好资格。新 prompt 不是 G1，训练 loss 或多提历史也不是自然支持收益。

先用同 G 比较资源，再做 G×资源因素实验；不一开始交叉所有检索器、提示和模型。复杂计划若只增加等待，应保留 no-plan。无效资源应修其来源/表示，不能把所有失败都推给 G，也不能用不可靠 Judge 为 G1 自证。

## 7. 最小、逐层资格实验

机器可读方案：[resource_qualification_proposal_v1.json](../configs/rl1v3/resource_qualification_proposal_v1.json)。已有输入提案：[PROPOSED_JOBS.json](../outputs/pm_rl1/v3/resource_architecture_review_20261118/cpu/PROPOSED_JOBS.json)。这些文件**不是新的模型执行清单或 GPU 申请**。

| 层 | 最小比较与观测 | 判定与失败去向 |
|---|---|---|
| A 来源/时间 | 现有全 bank 精确 span、owner/family/cutoff、前缀/manifest；新 writer 再做逐会话增量重放、追加未来不改变旧快照、ready_at 更晚、明确更正/无明确更正对照 | 机械越权必须 0；语义蕴含、主体、事实有效性单列 unknown，不能被字符串匹配替代。失败交 A1/A2/A3；当前已完成机械部分不代表时点投影已完成 |
| B 候选准确性/适用性 | 复用 83 行开发包（四头、15 owner、fold1–5、不同 rank、6 个无合法候选）；两名独立审阅者在看回复前标注源支持、人物、时效、主题、读取必要性、提及必要性、RS 适用性/风险 | 先分“库中无合格证据/有但排错/可用但不该读”；Top-1 评审只产生 precision/适用性诊断。Recall 必须另有完整或明确受限的相关证据集合，不能只审 Top-1 就报 Recall；分歧需单列/裁决 |
| C 阅读理解 | 六类挑战：本人/伴侣、建议/尝试、旧事实/当前更正、外部案例/用户经历、可选不提、引用指令诱导。相同源片段下当前 Notes vs 边界块 | 观察误用、归属、阶段、非强制采用；事实挑战正确不等于自然支持更好。程序 lint + 独立语义审查，失败交 renderer/G 条件训练；不改检索补偿 |
| D 增量质量 | 固定八个已曝光开发前缀，各自 OFF 与实际可达单头，共 **39** 个不同输入；同 G、同合法前缀、固定读取/解码，真实输出之后盲评质量、事实误用、安全和等待 | 不能把调用成功、引用率或 GSC 当主要自然支持结论；保留 ties/uncertain。oracle-source 只作私有归因上界，另记材料，不进入 PM/G 的需求标签 |
| E 组合效应 | 在 D 相同前缀上增加 **7 个 MP+MS、8 个 ME+MS**，共 15 个输入；重点检验重复/冲突和历史强制采用 | 若有共同可解释的标量质量，计算 `Iij=Yij−Yi−Yj+YOFF`；只有序数偏好时报告配对组合差异，不硬做加法。缺失/不可达的单元不填零；以后按需要加 RS×记忆、ALL，不先跑全组合网格 |
| F 在线等待 | 真实 cold/warm、队列、过滤/检索、序列化/分词、prefill/decode、首可见 token、计划/失败/重试到最终回复；分响应缓存命中/未命中 | p50/p95、实际输入/输出 token、完整墙钟及正常/截断/失败率；CPU 请求构造不能替代模型延迟。额外读取/计划只有在质量-等待权衡上成立才保留 |

D/E 合计 **54 个现有输入提案**，按来源身份从既有 120 份 CPU 请求中选出，不是启动 B 的 120 终点实验。八前缀中一个无 MP，故两项 MP 条件不可达，明示原因；不新造空 ReadingView 或零奖励。它们都是已曝光开发材料，没有独立确认资格。预算数字是去重后的输入数，**不是已经批准或已经完成的模型调用数**；Judge、人评和重复运行另需安排。

RS 四方案另做小模块：先完成低风险小方法集合审查，再从不同 owner 中按结果盲选四个开发前缀，覆盖欢迎建议/不欢迎建议、无需额外方法、适用性不确定。共享 R0，F/Method/Method+case 最多增加 12 个不同回复条件。材料不足就标 unavailable，不凭标签现场写方法。选择同一被检索方法时 Method+case 仅增案例；比较 R0/F 时其它记忆组合相同。当前没有这些方法输入，不能假称此模块已经 ready。

分层设计还需以下控制：

- 先冻结候选/查询/view 再标注和生成；不得根据未来真实终点评分调 ranker。12 条已有开发诊断继续保留，83 行审阅字段仍 pending；开发者标签不是独立金标。
- 当前 v0 与拟议结构查询的机制比较先在相同来源闭包做；改变 writer/入池和改变排序分两次比较。使用 oracle 源仍遵守合法时间/owner；特权仅指选择信息，不允许未来原文。
- 不同前缀不能因真实回复质量差而删除；技术失败记录成本、原因、未完成状态，语义失败作为观察结果保留。重试不能直到“生成好看”为止。兜底若存在，明确为另一个已绑定路径并计成本。
- owner 是重复测量的聚类单位，shared family 还需共同分组；54 条输入、471 个顺序都不是 54/471 个独立用户。报告实际 owner/family 数、小样本不确定性，不据开发显著性做主张。未来独立确认需未参与修复的合法材料或明确承认同库曝光限制。
- 判官必须分事实/安全与自然支持资格，J2 未运行不是 uncertain，硬约束未测仍 pending。固定前缀检查表分母，RS/表示不同也不能各删不利检查项。

## 8. 版本边界与 A2–A7 施工优先级

| 改进 | 是否可在现有消费接口下准备 | 必须新建的身份/审核 |
|---|---|---|
| 本审查、离线标注表、只读核验、未知能力清单 | 是，不改变任何运行输入 | 独立报告/输入 manifest；不修改 EXECUTION_STATE |
| 私有实体/slot/关系候选表，但尚不参与读写选择 | 可作 sidecar | sidecar 版本；不能声称已完成 A3，也不能放进 actor |
| 新 MP/ME/SUM/方法内容、纠正阶段/人物、采用更正/失效 | 消费者可继续使用 C0，但运行语义改变 | 新 writer/source 或 bank、index、reading/request/key；重新验收，不迁移旧奖励 |
| 同 Schema 的边界阅读文字、Notes/系统提示变化 | 接口可兼容，实验身份不兼容 | 新 bank（若 reading_text 改）、renderer/prompt、请求/终点；B 绑定复审 |
| dense/BM25/slot/时间排序、打包条数、图扩展 | C0 结果形状可兼容 | 新 index/query/ranker/packing 身份及对应 key；A5 对照，不能覆盖词面结果 |
| 新公共字段、预检索分数可见、F-resident 改观察/动作含义 | 不能单方静默变更 | 跨线协议审阅、必要时 C0 新版本及 schema；F 的常驻 token 与“零 GET”语义另立条件 |
| EXPAND_MS/adaptive/同头重复 GET | 超出 finite_head_v1 | adaptive_v1、mask/parent/trace/cost 联合验收；不能复用 Phase-1 的 16 子集结论 |

**建议按根因推进、保留 DAG 依赖，不在本轮改任务状态：**

1. **A3 的确定性基础优先预备**：人物/slot/事件阶段/双时间/冲突表及三条已知失真回归；补 MP prefix-extension invariance。不要先扩大抽取量或把所有 unknown 自动改确认。对未能可靠抽取的条目维持有角色的原话。
2. **A2**：RAW 与精确 span 作为底座，先准备事实键/父文定位/摘要忠实性验收；模型写 SUM 另待授权。SUM 是压缩和组织，不是天然更好；保留 RAW、unusable 与带身份 fallback。全历史直注入作为有容量边界的参照。
3. **A4**：先小规模可靠方法与适用/禁用条件，再比较 R0/F/Method/Method+case；负例和高风险隔离。既有来源量够多不意味着必须扩大案例库。
4. **A6 的表示原型可先独立准备**：用相同证据设计边界阅读并列出 C 层挑战，不动现有端口；正式 bank-v1/A6 完成仍依赖 A2–A5 及 T01–T25 全部实际验收。
5. **A5**：待内容/适用性已可评价后，按候选规范比较词面、Dense、BM25、Hybrid、加时间、再加已验证图。先诊断候选覆盖还是排序错；无证据关系时不加图。保留文本索引和阅读文本分离，长源按可回查边界拆索引而不静默截正文。
6. **A7**：A0 实测可行性、A6 及 B3 资格满足后，再正式冻结 G0 和 no-plan/plan 选择。G0e 只是工程起点。资源与阅读问题不自动证明 G 不会用资源；后续 G1 仍按真实正/负/可忽略条件训练并独立验证。本轮不启动或申请 GPU。

## 9. 现有证据不能支持的主张

- “3,188 条资源都是已验证事实”“875 个 RS 方法有效”“八类标签足以指导专业支持”。
- “GET 成功率高，所以召回准确/资源有用”“有 BGE 状态编码，所以资源检索已混合化”。
- “旧 MS BGE 结果证明新 A5 会更好”“旧 ME 抽取失败证明 ME 没价值”。
- “span 匹配证明 current validity/人物归属/语义蕴含”“owner 一致说明句中主体就是用户”。
- “当前 MP 是当时可写出的完整画像”“ready_at 已经测过真实异步写入延迟”。
- “Notes/HTML escape 已解决人物冒用与注入”“SupportPlan 必然提高质量”“复杂图总优于时序表”。
- “加入全部资源一定优于单头或 OFF”“更多提及记忆就是更好支持”“独立人评可由同一未经验证 Judge 替代”。
- “当前 120 份请求已经生成/评分”“A0/A7 已完成”“历史曝光被换一个 fold/hash 后消失”。

## 10. 可复核入口

新增只读命令（需候选 checkout 包含 PR #12 固定文件；不会加载 tokenizer/权重，不会重建来源库）：

```bash
CUDA_VISIBLE_DEVICES='' OMP_NUM_THREADS=1 PYTHONPATH=project/src \
  /opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python \
  project/scripts/rl1v3/resource_architecture_review.py \
  --candidate-root /opt/tokkio-data0/tokkio_projects/Metacom5_3-wsa-g0e-binding \
  --out /opt/tokkio-data0/tokkio_projects/pmrl1-validation/resource-review-repeat
```

输出目录必须不存在；manifest 固定输入 commit/相对路径/文件 SHA，拒绝读取被改写输入。`AUDIT.json` 与 `CANDIDATE_CHECKS.json` 是机械验证；`PROPOSED_JOBS.json` 的 quality/result 保持 null，执行次数为零。新方案参数文件与报告均是提案，不被任何 production loader 自动读取。来源与 bank 的完整身份、分头数量、历史可读率及本轮验证值均见 [AUDIT.json](../outputs/pm_rl1/v3/resource_architecture_review_20261118/cpu/AUDIT.json)。

交付/测试结果见 [RESULTS_ZH.md](../outputs/pm_rl1/v3/resource_architecture_review_20261118/RESULTS_ZH.md)。历史日志、A1/A1b 产物、C0 冻结、PR #10/#12 输入及全局状态表均保持原样。
