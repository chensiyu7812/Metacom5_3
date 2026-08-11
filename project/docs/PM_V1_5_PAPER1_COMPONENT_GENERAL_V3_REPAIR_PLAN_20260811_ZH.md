# PM V1.5 Paper 1 共同 V3 全链路修复方案

日期：2026-08-11

状态：`G4A_V2_PACKET_AND_CONTROL_AUDIT_PASS / G4B_REVIEW_PHASE_DESIGN_NEXT / OLD_ARTIFACTS_IMMUTABLE`

Git 基线：`8337f15`（`Checkpoint accumulated PM V5.3-V5.4 and Paper1 recovery`）

机器合同：`data/pm_v1_5_contracts/paper1_component_general_v3_repair_contract_v1.json`

上位救援决策：`data/pm_v1_5_contracts/paper1_memory_head_rescue_decision_v2.json`

## 结论

下一步不是继续调旧 MS 阈值，也不是再生成长期用户或 paired effects。必须先把共同执行层、
候选单位、训练 gold、四组件组合、guard/fallback 和定责一次修正，再允许 MP_PROFILE/MS 的新标签与
拟合。

本方案保留全部旧合同、代码、输出和失败报告作为只读证据。V2 的
`v1_5_memory_realization_v2.py`、`v1_5_memory_response_plan_v2.py` 不原位改写；V3 使用新文件和新
protocol。旧 same-stack 的 68 states、136 calls、盲评结果永久属于 V2 development diagnosis，不能
作为 V3 confirmation，也不能被 V3 的结果覆盖。

Paper 1 的最低成功结构保持为：

> **RS 必须成立，且 MP_PROFILE、MS、ME 至少一个记忆头具有 cross-fitted routing signal、真实
> functional contribution，并在同栈比较中不以不可接受的质量或 material risk 为代价。**

优先争取 RS + MP_PROFILE + MS；ME 按公共数据真实 action-result 覆盖能学到多少报告多少。四头全都
完美从来不是最低要求；只有 RS 而没有任何记忆做功仍不满足论文的 memory-PM 主张。

## 1. 本次修复回答的核心问题

### 1.1 旧 MS 实际学到了什么

冻结 same-stack 的 68 states / 17 connected groups 显示：

- learned MS 对 always-off：7 胜、26 负、35 平，NetWin `-0.279`；
- learned MS 对 fixed-high：26 胜、2 负、40 平；
- predicted-ON 的 ON executor clean rate 为 `30/37=81.1%`；predicted-OFF 的反事实 ON 为
  `17/31=54.8%`，富集 `+26.2pp`；
- 68 个 ON 中只有 15 个形成独立过去信息贡献，只有 7 个满足完整 MS function；
- 21 个 fallback 在盲质量比较中全部输给 OFF。

所以旧模型不是纯随机；它学到了一部分“哪些 surface 更容易被旧 executor 接受”。但它没有学到
“actual exact candidate 何时真正应改变当前回复”，而旧 executor 又把候选强迫写进回复，进一步压低
系统结果。

### 1.2 直接实现缺陷

V2 同时存在四个不可继续带入 V3 的机器行为：

1. prompt 要求 `Use this exact prior-user statement`；
2. MS/ME 恒设 `requires_literal_mention=true`；
3. guard 以旧句与回复的词面重合验证所谓 use；
4. 无重合或 generator 安全不使用时，整条回复被替换为固定
   `It sounds like that's been weighing on you.`。

这不是 meaning absorption，而是 literal splice。它会制造角色错位、过去升级为现在、无关旧事件
硬接、低质量 fallback，并把 executor failure 误计成 PM failure。

### 1.3 角色骨架不等于联合逻辑完成

V2 已经提出 MP=`SILENT_RESPONSE_MODIFIER`、MS=`TENTATIVE_CONTINUITY_BRIDGE`、
ME=`DECLINABLE_PAST_OPTION`、RS=`PRIMARY_SUPPORT_ACT`，但机器只显式处理 MS–ME 一组关系。
MP–MS、MP–ME、MP–RS、MS–RS、ME–RS 的重复、冲突、负担和主动作竞争没有完整规则。

因此 V3 必须同时修候选、gold、planner、prompt、guard 和 measurement，不能只改一句 prompt。

## 2. 不改变的研究对象和主张边界

### 2.1 仍是四头、16 个 requested actions

PM 仍输出 MP/MS/ME/RS 四个 bit，合法 requested action 仍为 16 个组合。V3 新增的是：

```text
requested
  → structurally eligible
  → jointly planned
  → generator claimed
  → offline verified functional
```

五层 action 必须分开保存。联合 projector 只可以因为候选缺失、owner/time/version/compiler 非法或明确
hard safety/boundary veto 把 requested bit 投影为 planned OFF；冲突、冗余或负担只作为 synthesis 条件和
interaction outcome 记录，不能在 outcome 前删 bit。projector 不能悄悄改变 requested policy，也不能把
16 动作改写成少数离散类别。

### 2.2 有限语义，不声称开放式人类理解

PM 学习 bounded resource suitability：当前目标、候选增量、可实现的组件功能、owner/time、
boundary、重复/冲突和有限 use mode。它不声称理解任意隐喻、讽刺、多实体隐含因果或真实临床需求。

无法在冻结语义范围内解析的 case 记为 `SEMANTIC_ABSTAIN`，运行时 OFF，并报告 coverage。这不是把
语义问题假设不存在，也不是把 unknown 强压成负例。

### 2.3 三个公共实验仍全部保留

- **ESConv**：RS routing、结束/listen-only/重复/ordinary-card 边界和即时支持结果；
- **EvoEmo**：MP_PROFILE、MS、ME 的纵向 personalization/continuity/action-result 运输；
- **ES-MemEval**：独立 QA retrieval、multi-evidence、时间/更新/冲突、user modeling 和 abstention。

ES-MemEval QA gold 不训练 response PM。EvoEmo response 与 ES-MemEval QA 共享纵向来源，不重复计算
为两份独立用户证据。

## 3. 四头的最终定义

### 3.1 RS：主要原子支持动作

- RS 是回复的唯一 primary discourse act；RS OFF 时由 R0 担任 primary act。
- 已通过的 RS grouped OOF 结果按精确 hash 保留，不重训、不改门。
- V3 只验证它与 memory component 共同执行时不被第二个问题、第二个建议或额外负担破坏。

### 3.2 MP_PROFILE：Profile-based Personalization

Paper 1 永久取消 MP_PREFERENCE。以下字段和概念不得重新进入：

- `MP_PREFERENCE`；
- `candidate_is_preference`；
- `preference_applies_to_response_act`。

MP minimum 是：profile fact 静默改变至少一个回复约束、现实细节、framing choice 或必要前提。

正例示意：根据轮班工作这个稳定约束，把固定早睡建议改成跨班次可执行的微步骤。

负例示意：仅写出“既然你是 office worker”；使用当前对话已经出现的事实；从职业、地点、性别、
国籍、年龄推断未经支持的性格或后果。

PM 只允许看 profile field type、scope-fit、novelty、age、retrieval score/margin、bounded constraint
indicator 和 token cost；不得看姓名、原始职业值、地点、国籍、性别或完整 profile 文本作为身份特征。

### 3.3 MS：原子化、严格过去的连续性线索

- session/event 只证明 provenance、owner 和严格过去；
- actual Rank-1 是一个完整 atomic seeker evidence，不是父 session 中任意一句；
- phatic、感谢、空泛 meta-memory、不完整指代、当前语义 echo、同主题错误事件、stale/resolved/conflict
  在 gold 前作为明确 negative/invalid family 记录；
- MS minimum 是：一条当前未重复的、当前目标相关的过去事实/episode，能改变理解、提问、约束或
  当前 option，同时明确允许“现在可能已经变化”。

`influenced_by` 只作 evaluator-only lineage/provenance 和 split grouping，永远不再直接定义 ON/OFF。

### 3.4 ME：可拒绝的过去 action-result

- 候选必须有 typed exact action + observed result；
- 只能作为 tentative、declinable option；
- 不得写成个人规律、因果结论或结果保证；
- 若 RS 已经提供微步骤，ME 不得另起第二个建议；除非两者在冻结 pair relation 中被判定为同一动作。

ME 先做零 API coverage audit。真实独立 group 和双向 action-readiness 不足时固定 OFF，不用合成事件
补数量。

## 4. Suitability gold：一个决定，四项检查，不再四轴独立追门

每个学习单位是：

> 一个 runtime-visible current state + 一个冻结 actual Rank-1 atomic candidate + 一个 component。

机器先确定 candidate presence、owner、strict-past、version、typed compiler 和 exact source。结构非法、
候选缺席或 Rank-1 miss 不产生 PM semantic negative，分别进入 source/retrieval/compiler 责任层。

语义审核只产生一个主决定：

- `SUITABLE`；
- `NOT_SUITABLE`；
- `SEMANTIC_ABSTAIN`。

审核者使用四项 checklist：

1. 当前 target/entity/response function 是否匹配；
2. candidate 是否提供当前不可见的 specific increment；
3. 当前下一回复是否能实现该 component minimum；
4. 当前 boundary 是否允许。

这里的“一个主决定”严格指**每个 `state × component × actual Rank-1 candidate` 产生一个标签**，不是
“每个 state 只能选一个 component”。MP、MS、ME、RS 的 suitability 相互非排他；同一 state 可以有
四个 `SUITABLE`，随后形成完整 `MP+MS+ME+RS` requested/planned action。禁止将此任务实现为 softmax、
winner-take-all、one-of-K 或“最多一个 positive memory”的标注器。

四项彼此逻辑耦合，不再分别要求 κ/accuracy 门，也不分别作为四个训练标签。最终 decision 必须绑定
预编号 source/current span 和一个 primary reason code。结构 hard negative 可机器判；material-use-plan、
current echo 和 boundary 的语义边界使用 anchored 双人校准。未解决 case 不以多数票或 LLM 默认值补齐。

禁止读取 future supporter reply、summary、observation、event outcome、QA answer/evidence、generator
response、Q/R/F/C outcome、PM prediction、fold 或 identity。

## 5. 共同 V3 realization、planner 与 generator program

### 5.1 Component use plan

每个 planned component 必须先生成 typed use plan：

- component；
- owner；
- time status；
- candidate meaning；
- allowed response change；
- forbidden inference；
- literal mention policy；
- burden units；
- relation to primary response act。

Exact source 是 audit evidence，不是待复制的回复片段。V3 禁止任何 personal component 要求 literal
mention 或 lexical overlap。

### 5.2 全 pair 联合规则

| 组合 | 规则 |
|---|---|
| MP + 任意组件 | MP 只能静默修改已选 primary act；若只能念 profile 或引入 stereotype，MP OFF |
| MS + ME | 只要二者各自 structurally eligible 且无 hard safety/boundary veto，就允许同时进入联合规划；relation 用于组织 coherent synthesis 和分层测量，不得在看到 outcome 前自动删 bit |
| MS + RS | MS 只能为 RS 提供上下文，不能增加第二个问题、解释任务或建议 |
| ME + RS | 两个 requested/planned bit 均保留；ME 必须尝试作为 RS primary act 的证据、实例或同一动作内的可拒绝选项，不另起第二个 primary task；若无法自然做功，记 generator/offline non-use，不回写 planned bit |
| MP + MS/ME | MP 可改变记忆表达的约束/负担，但不能把 profile 当作支持 memory 真实性的证据 |
| UNKNOWN/REDUNDANT/CONFLICT | 不在正式 16-action interaction 前自动压制 component；分别用澄清、合并或显式冲突处理指导 synthesis，并记录 claimed/verified use、负担、Quality、Risk、Function、Cost |

回复组织固定为：恰好一个 primary act、最多一个低负担 invitation，但**不设置全局单记忆上限**。
MS 与 ME 可同时支持同一个 primary act；MP 不占显式 act，但必须产生可审计的 response-choice delta。
当 MP/MS/ME/RS 均 structurally eligible 且无 hard veto 时，完整 `MP+MS+ME+RS` 是合法的 jointly
planned action。只有 candidate absent、owner/time/version/compiler invalid 或明确 hard safety/boundary veto
可以在 outcome 前把 requested bit 投影为 OFF。冗余、冲突、负担和 generator non-use 是要测的交互结果，
不能由透明规则预先消灭。

### 5.3 Meaning absorption prompt

Generator 必须先根据 current visible dialogue 组织完整回复，再把授权 meaning cue 当作可能的约束或
线索。Prompt 明确：

- 禁止逐字复制 first-person user source；
- 禁止为了证明调用而提及 profile/history/event；
- 禁止把过去升级为当前、把一次结果写成规律或保证；
- cue 不能自然改善回复时可以不用；
- 使用 memory 时必须 tentative，并允许用户说明情况已变化；
- 输出是一条自然、连贯回复，不是四组件清单。

### 5.4 Guard 和 fallback

Guard 只处理可机器验证的污染和结构错误，不判断 semantic function：

- unauthorized evidence ID、internal scaffold/ID leak、speaker/owner 反转、明确 past→present 错归、
  malformed structured output；
- 不以词面重合、generator 自报或长度证明 function；
- safe non-use：保留当前 grounded 回复，把 claimed/realized bit 降 OFF；
- owner/time/scaffold 污染：删除被污染 personal component，保留独立安全 RS，并至多一次冻结重生成；
- transport/schema 无 completion：所有 policy/baseline 使用相同 fallback 和成本账本。

Function 只能由离线 source-aware 审核确认，telemetry 只表示 generator claimed use。

## 6. Q / Risk / Function / Cost 和责任

四个对象继续完全分开：

- **Suitability**：生成前资源是否适合打开；训练 PM 的主监督；
- **Function**：生成后 candidate contribution、component minimum、candidate-own owner/time/use boundary
  是否都成立；
- **Quality**：arm-blind 单回复 absolute anchors 后在同 state/seed 内作差，只评支持贡献和整体可接受性；
- **Risk**：两臂逐族绝对 literal event + 可归因方向；不把冗长、帮助程度或普通低质量计为 risk；
- **Cost**：deterministic injected tokens 与 provider input/output/latency/USD 分开；只进入 16-action joint
  projection，不污染 component positive label。

责任同时报告两种视角：

1. deployment ITT：policy 对 requested action 后全部后果负责；
2. mechanism blame：归到有证据支持的最早失败层：source → retrieval → suitability observation → PM →
   projection → realization → generator → guard → measurement → system outcome。

PM 调用正确率只在 prospective suitability gold 已解决的 state 上测。请求与 gold 不兼容归 PM；请求正确
但候选未被正确计划/使用归 projection/executor；guard 误杀归 guard；数据不足保持 unresolved。

## 7. 训练与泛化

### 7.1 数据和独立单位

- ESConv 训练 RS；EvoEmo 训练 MP_PROFILE/MS/ME；
- p13/p18 等共享 raw source 的 wrapper 必须绑定同一 connected group/fold；
- 17 个 longitudinal connected groups 是不确定性的真实上限；session/state 不冒充独立 user；
- 不生成 80 个长期 synthetic users 扩大 N，也不把 ES-MemEval 同源用户再算一遍。

### 7.2 模型

- primary：StandardScaler + L2 logistic，低容量、概率输出；
- 每 head 的特征 schema 在标签前冻结；原始 identity/profile value 禁止；
- full-dialogue × actual-candidate BGE relation 只允许一个预登记 challenger；
- grouped OOF、owner-cluster bootstrap、BA/recall/specificity/AUC/Brier/calibration/ON-OFF fraction 全报告；
- 不用一个差 `.00067` 的机械门替代最终判断，也不在结果后降门、换 encoder、换 packet 或追阈值。

训练是否值得进入同栈由开发前冻结的综合规则决定：存在非平凡 cross-fitted discrimination，Brier/proper
score 胜 prevalence，预测 ON/OFF 均非退化，主要 negative family 有覆盖。论文是否及格最终由 held-out
same-stack policy 对 baselines 的 Q/R/F/Cost 和 functional memory contribution 决定。

## 8. Baselines 和 16-action 验证

所有策略共享 current state、actual Rank-1、realizer、projector、generator、seed、guard、evaluator 和
成本口径：

- always-off；
- RS-only；
- fixed-high eligible；
- transparent suitability rule；
- learned qualified；
- cost-matched fixed；
- cost-and-ON-rate-matched random。

全 16-action interaction 在同一 state 上运行，不允许不同 action 分配不同 state。当候选均 structurally
eligible 且无 hard veto 时，16 个 requested actions 必须保持为对应的 16 个 jointly planned actions。报告：

- 四 bit Hamming/exact/oracle-compatible；
- requested→eligible→planned→claimed→verified funnel；
- Quality regret、oracle-set inclusion；
- material/critical risk 两臂绝对率；
- frontier excess cost；
- component pair 的结构投影原因、claimed/verified non-use、fallback 和 burden；不得把语义 pair relation
  本身报告成 pre-outcome suppression。

透明规则不是稻草人。如果 learned 只能复现规则，就主张“低容量模型复现 bounded routing”；只有 held-out
结果确实更好才主张 learned superiority。

## 9. 单向执行阶段

### G0 — Git 与权威冻结

- `8337f15` 保存此前全部历史；
- V3 只用新文件；V2 文件只读；
- active authority 已绑定并关闭 G2、G3、G4 design 与 G4A V2 packet/control 物化；当前只允许 G4B
  reviewer qualification/review phase 的零 API 设计；reviewer/API、label、fit 权限保持 false。

### G1 — 合同和问题账本

- 本方案、机器合同、全局 failure ledger 和 authority hash 一致；
- validator 检查 MP_PROFILE scope、16 actions、all-pair rules、no-literal/no-lexical/no-generic-fallback、
  五层 action 和三外部轨。

### G2 — V3 实现与零 API 测试

- 新建 V3 realization/planner/response-program/guard；
- 旧 V2 代码不改；
- 覆盖全部 16 actions、6 component pairs、missing candidate、redundant/conflict/unknown、safe non-use、
  owner/time/scaffold contamination、RS-preserving regeneration；
- 测试任何 literal-use、lexical-use 和 generic-safe-nonuse fallback 都 fail closed。

### G3 — 公共候选面审计

- MP_PROFILE 846 candidates 的 field/scope/group/current-redundancy 分布；
- atomic MS 的 informative/echo/stale/wrong-event/use-mode 分布；
- ME 417 candidates 的 typed action-result/readiness/transfer/group 双向支持；
- identity shortcut、future/summary/QA leakage 为零。

已完成结果：

- 4,689 states、18 runtime wrappers、17 connected groups；
- MP/MS/ME present 分别为 846/4,442/417；
- atomic MS 保留 21 条 low-information 与 32 条 current echo 作为 G4 的高价值候选面，不自动贴负标；
- 93 个 state 同时存在 MP+MS+ME，证明公共面真实支持多组件并存；
- ME 虽 417 行全部 typed compiler-valid，但只有 15 groups、23 个 distinct action-result，故保持 provisional。

### G4 — Suitability 资格和一次性标签

- MP_PROFILE、MS 使用全新 anchored binary packet；
- 四项 checklist 只作解释，不设独立轴门；
- 双人 overlap 先证明 binary decision 和 primary reason code 可复现；
- unresolved 保留，禁止 LLM 默认填 0/1。

已完成的 design gate 固定：

- 学习/审核单位是 `state × component × actual Rank-1`，不是每 state 一项；
- 同一 state 可在 MP/MS/ME 三包中各出现一次，三项可同时 `SUITABLE`；禁止 one-of-K、softmax、
  winner-take-all 和最多一个 positive memory；
- MP=204（每 connected group 12）、MS=204（每 group 12）、ME=99（15 groups、每 group 最多 7），
  共 507 cases；14 个存在三组件共现的 groups 至少保留一个共享 state 的三条独立 case；
- 四项 checklist 只要求审核者确认已经考虑，不提交四个 YES/NO/UNKNOWN，不计算四轴 κ/accuracy；
- 每个 component 的资格、agreement 和 label-capacity 独立判定，一个头失败不再机械关闭其他头；
- 只把双评 `SUITABLE/SUITABLE` 或 `NOT/NOT` exact consensus 用作 primary binary label；分歧或任一
  abstain 保持 unresolved/runtime OFF；第三方裁决不能回写 pre-adjudication agreement；
- 该设计没有授权 packet materialization、reviewer/API、label、fit、generator、baseline 或 external。

G4A 已完成：

- V1 首次物化的 507-case 公共选择与盲化机器门通过，但在 reviewer 调用前的语义复核中发现 5 个 MP
  正 control 已在 current turn 泄露 profile fact，另 1 个 ME 负 control 允许合理的 tentative 用法；
- V1 没有 reviewer call 或标签，所有输出保留且标为 control semantic fail，不覆盖、不伪装成通过；
- V2 仅改这 6 个 control surface，其他 30 controls 不变；507 cases、A/B packet 与 private case key 的
  SHA-256 与 V1 完全相同；
- V2 独立审计确认 MP/MS/ME=`204/204/99`、17/17/15 groups、14 个 all-three shared groups、全部 21
  low-information MS、32 echo MS、12 MP redundancy 和 23 ME candidates 均被保留；
- 公共 payload 无 gold、group/fold/owner alias、score/margin、future/summary/QA/outcome/PM prediction；
  reviewer calls、labels、PM fit、generator calls 均为 0；
- 下一阶段必须先冻结 G4B 的 reviewer 身份/模型、资格 controls、批次、schema、raw-first ledger、费用上限和
  component-specific stop rule，不能直接拿现成环境变量启动调用。

### G5 — 一次 grouped OOF

- RS 精确 hash carry；MP/MS 并行；ME coverage 允许时加入；
- 每 head 一次 primary OOF，不追门；
- 失败 head 固定 OFF，仍报告连续指标。

### G6 — Executor 小资格

- hand-confirmed suitable/unsuitable states；
- 验证 absorption、silent MP、tentative MS、declinable ME、RS primary、safe non-use 和污染重生成；
- 通过前不启动正式 generator scale-up。

### G7 — 冻结 same-stack baselines

- 同 state/seed、全 16 actions 或预冻结 balanced incomplete block；
- Quality/Risk/Function/Cost 独立；
- 结果后不改 prompt、guard、threshold、sample、feature 或 baseline。

### G8 — 三个公共实验和终局

- ESConv、EvoEmo、ES-MemEval 分轨报告；
- 只按实际通过 head 和 gate 写主张；
- 只有 RS 则 memory-PM 主张失败；RS + 任一 memory head 才满足最低目标。

## 10. 必须成为机器测试的不可回归项

1. V2 文件 hash 不变；
2. MP_PREFERENCE 和两个 legacy preference feature 不出现在 V3；
3. 所有 16 requested actions 可编译；
4. 所有 component pair 都有显式 relation，不允许隐式 evidence union；
5. MS/ME/MP 不存在 `requires_literal_mention=true`；
6. guard 不读取 lexical overlap 判断 function；
7. safe non-use 不替换成固定 generic M0；
8. first-person user source 不得作为 assistant 复制目标；
9. RS ON 时仍是唯一 primary act；
10. MP 只作 silent profile modifier；
11. requested/eligible/planned/claimed/verified 五层分别落盘；
12. suitability 是每个 component candidate 的非排他 binary/abstain 决定，禁止 one-of-K、softmax、
    winner-take-all 或每 state 最多一个 positive memory；
13. source/retrieval invalid 不生成 PM semantic negative；
14. `influenced_by`、summary、observation、future、QA gold 不进入 x、prompt 或 runtime；
15. generator telemetry 不产生 function gold；
16. cost 不进入 head positive label；
17. baseline 共用同一 V3 stack；
18. transport retry 只允许无有效 completion，且 raw-first 持久化；
19. paid release、label creation、fit 和 external 默认 false，必须新 phase manifest 精确授权。

## 11. 当前准确位置

截至 G4A V2 独立审计完成时：

- 旧 V2 RS 已通过，MS 路由正式失败但有 directional signal；
- 旧 same-stack 已证明 hard splice / lexical guard / generic fallback 是系统瓶颈；
- MP 已纠正为 profile-only 并恢复为第一优先级；
- V3 共同执行逻辑、16-action planner、meaning-absorption prompt、五层 action accounting、safe non-use、
  owner 检查和污染重试已经完成零 API 实现并通过 G2；
- G3 已确认 MP/MS 可进入 G4，ME 结构合法但因 15 groups/23 candidates 保持 provisional；
- G4 已冻结并物化 507-case 非排他单决定盲包与 36 个 fresh controls；V2 独立审计通过，但尚未执行任何
  reviewer、创建 gold 或运行 OOF；
- 没有新 API、标签、fit、baseline 或 external outcome；
- 下一步唯一允许工作是 G4B reviewer qualification 与 public dual-review phase 的零 API 设计；必须先
  绑定两个独立 reviewer、controls、strict schema、raw-first ledger、component-specific gate 和费用上限。
  在 G4B 新 phase 明确授权前，不得调用 reviewer、创建 suitability 标签、拟合新 head 或调用 generator。

### G4B1 V1 控制资格结果与一次性 V2 修复

G4B1 V1 已实际完成 72/72 控制题：72 次均首轮得到合法严格结构，raw-first 完整，费用
`$0.13455725`，未读取 public packet、未创建标签、未 fit、未调用 generator。随后独立零 API 打开
gold，三组件按冻结门均未资格化；这份 FAIL 永久保留。

但该 FAIL 不能解释成三头不可学。Reviewer A 对全部 30 个明确 SUITABLE/NOT 控制为 30/30，仅
`SEMANTIC_ABSTAIN` 为 1/6；Reviewer B 对明确题为 21/30、abstain 为 0/6。实现审计同时发现：G4
设计明确要求 `worked_training_anchors_before_qualification=true`，实际 provider-visible prompt 没有
任何 worked anchor，旧 preflight/validator 也漏检了这个前置要求。因此 V1 的正确状态是
`INSTRUMENT_IMPLEMENTATION_FAIL`，不是 `MP/MS/ME_FIXED_OFF`。

只允许一次 G4B1 V2：把原本已冻结要求的 component-specific 三分类 worked anchors 真正放入 prompt，
使用与 V1 controls、507 public cases 内容不相交的 fresh held-out controls；reviewer、三分类、12/head
构成、10/12、9/10、2/2、critical-boundary 门全部不变。V2 仍必须 controls-first、runner 不读 gold、
raw-first、结果冻结后再单独开 gold。若 V2 再失败，不得第三轮调 prompt/control/门槛。

### G4B1 anchored V2 最终资格结果

anchored V2 在 72 个全新 held-out controls 上完成一次冻结资格判定。两位 reviewer 的身份、三分类、
样本构成与门槛均未改变，gold 只在 72 个 primary decisions 落盘后首次打开；没有 public review、训练标签、
PM fit 或 generator call。

- Reviewer A：MP `12/12`、MS `11/12`、ME `12/12`，三组件均资格化；
- Reviewer B：MP `11/12`，资格化；MS `7/12`、ME `10/12` 但 resolved 仅 `8/10`，均未资格化；
- component-specific 结果：仅 MP 同时通过两位 reviewer；MS、ME 在本条 LLM 标注路线固定 OFF，不进行
  第三轮 prompt/control/gate 修改；
- 一条 MS 回复的 primary decision、span 与 checklist 完整，但辅助 reason code 违反 component 白名单；
  在 gold 打开前只冻结 primary decision并保留 auxiliary-invalid 标记，没有重试或修理由。该题不是 critical
  boundary，不能用来翻转 Reviewer B 的 MS 资格失败；
- 下一阶段只允许为 204 个 MP cases 设计两位已资格 reviewer 的 408-call public review。公共双评完成前不打开
  private case mapping；只有 `SUITABLE/SUITABLE` 与 `NOT/NOT` exact consensus 才能形成 primary binary
  label，分歧或 abstain 一律 unresolved/runtime OFF。

这使 Paper 1 的最低可行结构从“只有 RS”推进为“已通过的 RS + 可进入正式标签/OOF 的 MP”。这仍不是 MP
已经学会的证明；下一道科学门是 17 connected groups 上的一次 grouped OOF，之后才是同栈 executor 与
baseline 结果。

### G4B2/G4B3 公共 MP 双评实测

204 个 MP public cases 已由两位资格化 reviewer 独立完成。主运行 408 次物理调用中 407 条合法，1 条
Anthropic HTTP 529 无 completion；后者通过独立、同 prompt/seed/item 的一次 no-completion continuation
补齐，其余 407 条零重跑。主运行费用 `$0.88741975`，continuation 不读 private mapping；两人各 204 条
冻结后才首次打开 case mapping。

pre-adjudication 结果：exact three-class agreement=`0.6667`、resolved binary agreement=`0.7234`、
Gwet AC1=`0.5660`，均未过预冻结的 `0.75/0.80/0.60` 门。尽管 exact resolved consensus 已有 136 条
（ON=52、OFF=84、17 groups、两类各至少 12/15 groups），当前合同仍判 MP 正式标签路线 FAIL；不得用
第三人裁决回写 agreement，也不得在看到结果后降门直接 OOF。

分歧诊断显示并非单一 field 可安全删除：Reviewer A=`126 NOT/62 YES/16 ABSTAIN`，Reviewer B=`105
NOT/99 YES/0 ABSTAIN`；最大分歧为 A NOT/B YES 42 条，且遍布 job、location、education 与所有 folds。
这说明 held-out controls 能通过不等于真实公共 surface 上的 material personalization 边界已稳定。下一步必须
先做方法级定责：判断 136 条高置信 consensus 是否可被预先缩窄为“可实现语义范围”的探索性训练集，或改用
真正的人类 source-aware annotation；在新合同明确前，MP fit、generator 与 baseline 均保持关闭。
