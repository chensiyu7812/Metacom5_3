# PM-RL1 记忆侧离线准备与组织建议（2026-11-15）

状态：已完成 24 段完整既有导出会话的确定性抽样及单助手语义首审。没有改生产代码，没有读取 test gold、混合原始 EvoEmo 或废弃 11/80 目录，没有 G/J/embedding/付费调用。以下新语义记录属于研究准备材料，不是人工金标、训练标签或收益结论。

## 1. 来源、抽样和复算

仅使用 `completion_20260930_v2/P3/common_evidence/` 中冻结的 `evidence_pool_private.json` 和 `source_map_private.json`。共有 42 个 train/dev 前缀、15 owners；去重后可用 216 个严格过去会话。`94_prepare_p3_common_evidence.py:58` 和 `evidence.py:12` 表明原导出取该前缀全部合法历史会话及全部 turns。本次保留这些完整导出，不重新打开混合原始数据；完整性的准确表述是“完整冻结导出会话”，并非“本次重新对原始语料认证完整”。

固定 seed=`pmrl1-memory-preparation-20261115-v1`。owner 按 sha256(seed|owner|owner_id) 排序，每个 owner 的会话按 sha256(seed|session|owner/session) 排序；round-robin 取到 24 段。结果覆盖全部 15 owners，每人 1–2 段；train 18 / dev 6。没有按结果、关键词、当前质量挑选。

所有 24 段约 10,596 英文词均已逐段读完，形成 88 条带原文 turn/role/offset/source hash 的首审记录。类别不是互斥标签，也没有穷尽全部事件：建议 17 条、意向 20 条、实际尝试 18 条、主观结果 18 条、明确偏好 3 条、特定未知/未验证 12 条。主观结果见于 16 个样本，包含即时聊天感受、行动后自述及混合结果，不能当 16 个有效干预，更不能拿这些数除以前述 4 个 ME `observed_outcome` 推算召回率；分母、抽取对象和覆盖范围不同。

复算顺序：

```bash
python project/outputs/pm_rl1/research_preparation_20261115_v1/memory/prepare_inventory.py
python project/outputs/pm_rl1/research_preparation_20261115_v1/memory/record_semantic_review.py
python project/outputs/pm_rl1/research_preparation_20261115_v1/memory/validate_preparation.py
```

第一步重建抽样；第二步回放已明确写入脚本、基于本次逐段阅读的语义审查，不是自动重新做语义审查；第三步验证 hash、owner、时间、引用等结构性约束。

输入 SHA256：

- `evidence_pool_private.json`: `88d30758332c796146afccd48f406747ee3580737eb0e84ed630c12bbabe3f68`
- `source_map_private.json`: `11cfc82d6d0c1db8a21c68bc430efe1f894120050966243032d7e3bdf426012e`
- `input_freeze.json`: `6d4c3f749d1c6649870e4fbea2dc249cf77c2546eb33f1fd24dc111793c5ee8b`

每段源文本 hash 和可用前缀严格过去证明在 `SAMPLE_MANIFEST.json`；所有新文件 hash 在 `OUTPUT_HASHES.json`。

## 2. 原文已能证明什么

| 样本 | 实际证据 | 能用于什么；不能推出什么 |
|---|---|---|
| M17 p8/esc242 | T7/8 多次要求结束电话但模式复发；T11 实际挂断后对方生气；T22 “Talking to him is just not working.”；T33 “I don't really like to draw...” | ME 记录已尝试与不良结果；活动偏好记入来源观察。避免把“再沟通/画画”当全新合适方案；不能保证任何替代建议成功。 |
| M16 p6_conv_5 | T9 日记有帮助但焦虑有时仍很强；T19 冥想或散步有一点帮助 | 保存部分收益、剩余困难和不确定归因；不要压成“日记有效/无效”。两个活动作用不能硬拆。 |
| M04 p2_conv_10 | T11 参加写作工作坊且 helped，但冒名顶替感仍出现；T7 治疗后释然和焦虑并存 | 有行为后主观结果，字段稀少不代表源头全无结果；仍不构成治疗因果证据。 |
| M15 p17/esc85 | T18 从未使用清单/计划本；T26 将尝试 | 意向不能记成已执行；感谢不是执行后的效果。 |
| M21 p13_conv_3 | 已领养小狗；T4 愧疚，T10 分散注意与训练负担并存 | 一个事件可以有正负并存的结果，不能只留“领养有帮助”。 |
| M24 p1_conv_11 | T15 问绘画是否帮助，T16 “It does help.” | 结果记录必须带 T15 问句先行词；孤立摘句不足。 |
| M23 p18_conv_1 | T14 “used to enjoy going for walks” | 是过去偏好；不能自动继承为当前有效建议。 |

这些证据足以推翻“现有数据完全没有行动和结果可用”的强断言；尚不足以证明历史记忆能提高 G，更不足以证明 PM 策略学得出正收益。下一步应定位抽取、组织、召回、消费、测量哪一层丢失了价值。

## 3. MP/ME/MS 应如何分层

**底层是单一来源账本，三类资源是有成本的读取视图。** 同一 owner/session/turn 只存一次不可变原文及 hash。所有 MP/ME 都回指同一 MS 来源；派生事实必须有主体、说话者、报告时间、可知时间、事件时间（可未知）、来源片段和完整推导依赖。不要再把三类当互不相干的三套语料。

| 层/类型 | 应保存与返回 | 当前实现对应 | 还缺什么 |
|---|---|---|---|
| 来源账本 | owner/session/turn、完整文字、角色、rank/date/hash、导出完整性证明 | `evidence.py:12`；`temporal_evidence_ledger.py:21,44` | ledger 的 session_directory 目前明确仅认证 registered turns，必须增加完整性证据，不能靠名称猜完整。 |
| MP | 目标时刻仍有证据支持的相对稳定档案，带 as-of 和有效状态；事件性的压力、刚收到反馈不能长期固定为人格 | `representation.py:61`；`resource_organization.py:122` | 失效/改述/未知的显式投影与来源审查。明确偏好先作为研究来源观察；不静默改旧 Paper1 的 MP 字段或塞入自动推测的回复风格偏好。 |
| ME | 一个事件/应对经历的版本链：背景约束→建议→意向→尝试→自述结果；每步独立证据，不强制齐全 | `temporal_evidence_ledger.py:116` 支持 stage/outcome；`resource_organization.py:126` | 现有 stage/outcome 很多未知，只映射旧字段；需要来源首审/复核后编译，明确即时反馈与后续报告、正负混合结果。 |
| MS | 完整原会话，承担指代、遗漏、冲突复核，保持原始 MS 合同 | `resource_organization.py:130`；`typed_resource_views.py:50` 的 full | quote±1 不能保证语义依赖闭合。短证据视图若作为可购买资源须独立身份/费用/边界；不能用摘要悄悄替换完整 MS。 |

读取上先允许便宜而可靠的 MP/ME 片段满足需求，再按不确定性和潜在边际价值升级到完整 MS；这只是待比较的策略，不强制所有问题固定 MP→ME→MS 顺序。STOP、单类、多类顺序都应可选。相同历史内容在 MP/ME/MS 重复出现不算独立三份信息；来源 footprint 应记录新增和重复证据以及真实 token/时延。

对 RS 的连接应由已付费获取的记忆形成用户特定约束：M17 已尝试沟通无改善、不喜欢画画；M16 日记仅部分帮助。不能让未读取的 ME 隐藏标签提前改善 RS 排名，也不能把结构链接直接宣称为策略适用或收益标签。

## 4. 四类组织故障的处理

1. **时间与失效**：append-only 保留原报告。查询先做同 owner、strict-past rank 和 reported_at 过滤，再投影目标时刻状态。事件时间与报告时间分开；新报告“以前曾喜欢”不能覆盖成“现在喜欢”。只有明确可支持的更新才 supersede；缺失不等于失效，未知不等于 false。
2. **冲突**：区分随时间改变、不同情境、真正矛盾、无法判定。记录两个来源及差异，不凭最新一条或向量相似度删除旧事实。关系归并需要证据和复核；当前 ledger `add_relation` 明确 index-only/no automatic supersession，保持这道边界。
3. **指代与身份**：主体/人物别名绑定至来源，历史 supporter 不是当前 AI。引用先取完整句与必需问题/先行词；无法闭合就升级完整 MS 或保持歧义，不用字符串拼接产生确定人物关系。M24 的 It does help 是最小验收样例。
4. **重复**：source-level exact dedup 与 claim/event-level semantic dedup 分开。相同引文可确定去重；不同时间类似措辞不等于同一事件。事件合并须关系证据，否则保留多条。去重不能抹掉否定、日期、混合结果或完整 MS。训练和评测按 owner/事件依赖聚类，不能把同一历史跨前缀复用当独立样本。

## 5. 具体下一步与通过条件

A. **完成样本复核与字段契约**：用本批 24 段作为冻结的首审底稿，由独立人类/第二复核者核对行动阶段、结果归因、角色和指代，保留分歧。验收：24/24 阅读状态明确；每条输出均有可复核 exact span；建议→尝试、意向→完成、支持者经历→用户经历三类非法升级为 0；未知字段不能被填成 negative。当前已通过结构检验，独立复核 pending。

B. **补齐抽取断点审计**：对这 24 段逐条追踪原文→历史编译输出→目标时刻 MP/ME→检索候选→G 实收内容。逐条列原因：源无结果、原文有但未抽出、抽出但被投影丢掉、未召回、未被读、读到未用。验收：关键观察都有唯一去向或明确 unresolved，不能拿 `observed_outcome` 总数替代这张表。禁止只看最终 top-4 后就宣称编译缺失。

C. **建新版本候选视图**：保持源账本和原 MS 不变，增加经过复核的 MP/ME 字段和依赖闭合短视图；冻结 candidate identity、retrieval policy、序列化与费用。验收：所有派生依赖同 owner/strict-past、完整 source footprint、零原文静默截断、quote-role-offset 100% 回放；指代样例、意向样例、混合结果样例不误写。

D. **先测资源价值再做 PM 学习**：相同 G、提示、预算和随机种子，比较当前前缀、正确历史、等成本无关历史/错误关联、完整历史上限，并将历史事实正确性、当前回应适切性及成本分开评分。错误历史仅作离线控制，不能写回真实记忆。验收：正确历史优于等成本干扰且没有明显当前回应伤害，并由人类校验评分；逐 owner 报告效应和不确定性。失败先定位链路，不能直接多跑 PPO。具体最小重要差异与样本量须在独立结果前冻结；本批 15 owners 不足以预先许诺统计成功。

E. **够用才训练，并保留退出条件**：当确认“有些情境值得读、有些不值得读、不同类型/顺序有差异”，再训练仅见公共观测和已获资源的 PM，并比较 STOP、固定读取、便宜启发式、全读和 PM。正式 held-out 需隔离当前已开发数据；本次 dev 已参与研究准备，不再把它当最终独立检验。若正确历史上限在修复和合格测量后仍无收益，应缩窄研究适用情境或接受否定结果，而不是承诺必成功。

未解决字段：88 条记录的 event_identity/跨会话关系均未强填；目标时刻有效性未重新确认；独立人类判定 pending；全历史抽取召回率未知；新视图的正式 token/latency 费用与接口未冻结；G 的可消费收益、RS 条件适配收益、自然支持 reward 资格均未得到本次验证。

## 6. 三个已精确连接当前 MP/ME 的问题（不是只看原文推测）

已从冻结 `resource_organization_20261029_v1` train/dev catalogs 逐文件核验原 OUTPUT_MANIFEST hash；比较结果及出现前缀在 `CURRENT_VIEW_COMPARISONS_PRIVATE.json`，输入 hash 在 `COMPARISON_INPUT_HASHES.json`。复算：`python .../memory/compare_current_views.py`。

1. **M17 → MP `mp::mvu_2a73b2853cdd499d576e2ab5`**：源文明确 “I have hung up, but he gets extremely offended easily.”；当前 `past_report` 却是 “avoids hanging up to prevent offense despite frustration”。已尝试且有不良后果被陈述成避免尝试，有语义偏移。引用本身仍保留原文，因此不能说 G 一定没有见到真实证据。
2. **M04 → MP `mp::mvu_785a6f6f9e719c52ef13fc57`**：源文 “joined a writing workshop that helped, but the imposter syndrome creeps in”；当前 `past_report` 只有参加工作坊应对 writer's block。帮助与残留问题没有进入结构化摘要；原 quote 仍完整保留，属于表征未充分利用，尚不能说检索/交付丢失。
3. **M04 → ME `me::mvu_c8da36ab41b1d4da5464dd8d`**：引用 “It helps to know I'm not alone. The online community has been supportive too.”；当前 `action_stage=unknown, observed_outcome=null`。已有主观感受未结构化，但也没有足够证据把它归因某个单项干预，不能机械补成“完成且有效”。

M16/p6_conv_5 在该 owner 当前所有冻结目标目录的 MP/ME 中未命中。它是可复核的目录缺口候选；当前目录不是完整历史编译库，故编译漏抽还是目标投影/筛选丢弃仍为 pending。未对 typed-view 实际 G receipt 全链路逐条检查。

抽样只依赖冻结合法来源、owner/session ID 和固定 seed；没有读取收益文件、G 回复或评测标签参与选择。先前审计启发了需要查“阶段/结果/指代”的问题，但没有用它来挑本批会话。所有合法前缀绑定已在脚本验证 rank<cutoff 且报告日期≤目标日期；所有 source spans 校验通过。

## 7. 三条候选修复 sidecar（尚未接入）

`CANDIDATE_VIEW_REPAIRS_PRIVATE.json` 已保存三条独立候选，包含完整旧快照、旧内容与 OrganizedItem identity、所有实际前缀绑定、原文完整 evidence 数组、新候选 identity、新 past_report/search_text，以及分开的 historical_action/self_reported_reaction/context 字段。`prepare_candidate_repairs.py` 可复算；`CANDIDATE_REPAIR_VALIDATION.json` 证明 4 个涉及的既有 catalog 文件 hash 不变、旧引用与旧身份保留，未应用任何替换。

- 挂电话条目候选改为 **历史 ME 事件**：已做过挂电话及自报朋友生气；不再推断稳定的 MP“避免挂断”特征。
- 工作坊条目候选表达：已加入、主观有帮助、冒名顶替感仍反复；加入不等于完成整个工作坊，也不等于治愈。
- 社群条目分两项：**知道自己不孤单有帮助**；**社群曾提供支持**。无特定行为、无可确认因果连接，行动仍 unknown。

所有候选当前有效性保持 unknown，事件时间未知，不是正式训练标签，不宣称已接入检索或 G。还需独立语义复核、候选接口与费用冻结和受控消费实验。
