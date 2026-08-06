# PM V1.5 V5.3 外部实验定义与双 Codex 并行运行手册

状态：`COORDINATION AUTHORITY / PRE-P2 / NO FORMAL OUTCOME YET / 2026-08-06`

科学事实源仍为以下三份，本文件不建立第四套科学合同：

1. `docs/PM_V1_5_V5_3_INTEGRATED_EVIDENCE_EXECUTION_PLAN_20260805_ZH.md`
2. `data/pm_v1_5_contracts/v5_3_integrated_evidence_execution_v1.json`
3. `docs/PM_V1_TO_V1_5_GLOBAL_FAILURE_LEDGER_ZH.md`

本文件只承担两项职责：

- 把三个外部实验的可测能力、指标、判定口径和 baseline 集中展开；
- 规定两个 Codex 会话的任务边界、依赖顺序和唯一交接点，避免同时修改同一事实源或提前消费 outcome。

如本文件与上述三份事实源冲突，停止执行，由 leader 做一次三源同步后再继续。正式环境固定为：

```text
/home/tokkio/snap/metacom_v33_pm_v1_5_repair/.venv-pm-v1-5
PYTHONNOUSERSITE=1
PYTHONPATH=src
```

任何付费 API 调用仍需独立的 stage、identity、精确费用上限和用户明确授权；本文不是付费授权。

---

## 1. 当前判断：已经确定了什么，尚未达到什么

### 1.1 已经由真实外部数据反推并冻结的方法边界

外部数据要求的不是一个“理解一切复杂心理语义”的大模型 PM，而是下列有限、可审计系统：

```text
dataset adapter / current visible state
  -> same-user strictly-past private resource store
  -> source-specific Top-k candidate discovery
  -> exact Rank-1 execution candidate
  -> machine-provable hard eligibility
  -> four source-specific low-capacity value heads (MP/MS/ME/RS)
  -> 16-action joint projection, including legal M0+R0
  -> typed response program
  -> one evidence-aware whole-response generation
  -> structural/binding guard and deterministic M0 fallback
  -> stagewise accountability ledger
  -> separate quality, risk, cost and mechanism evaluation
```

三个外部考卷反推出的最低能力分别是：

| 外部域 | 实际要求 PM/链路做到什么 | 不要求它证明什么 |
|---|---|---|
| ESConv | 在没有纵向私有记忆时自然 mask MP/MS/ME；RS 能识别当前支持动作、已执行动作、显式边界与重复；允许 M0+R0 | 不证明长期记忆或个性化 |
| EvoEmo response | 同用户、严格过去、大候选池；区分 MP profile/constraint、MS continuity/observation、ME action-result；拒绝 wrong-owner、current echo、冲突和只同主题的干扰项；Step2 真正吸收证据 | 不证明 MP preference、真实临床效果或所有16动作的自然覆盖 |
| ES-MemEval QA | 对历史进行检索、读取、时间/冲突/拒答推理并生成短答案；gold 对生成侧不可见 | 不等价于支持回复 QRC，也不能证明四个 response head 都学会 |

这部分方法规格已经足够明确，不应再因某个外部分数临时更改本体、组件定义或职责划分。

### 1.2 当前还不能写成“已经达到”的部分

截至本文件建立时，V5.3 达到的是“可进入正式 P2 冻结前资格收尾”，不是“PM 已经学会并泛化”：

- 新 Step1 特征、typed Step2、M0 规范化和逐层账本已有实现或原型；
- V5.3 四个 value head 尚未获得正式 paired ON/OFF outcome 并训练；
- `stagewise_accountability` schema 已冻结，但正式 runner 仍未接线；
- ME 受控稀疏池的 Rank-1 绑定不能代表 EvoEmo 真实候选密度；
- 三态行动准备度在70条真实 EvoEmo 发言上零假阳性，但 INVITES_ACTION 只有2个正例且只命中1个，DECLINES_ACTION 没有自然正例，故只能称保守精度初步合格，不能称召回已完整资格；
- MP/MS 域对比正在由另一 Codex 实现，RS 域对比与全新 ME superdomain 尚待正式交付；
- V5.3 external plan、call plan 和 outcome 都尚未物化。

本文件建立期间，Worker随后提交的域审计又进一步确认：EvoEmo没有`MP_PREFERENCE`内容，故该子构念只能
内部验证；MS候选编译资格内外均有支持，但`continuity_request`槽位内外都未触发；RS旧训练构造使用直接向
generator下指令的语言，真实runtime在160条上0触发。这些不是“外测不公平”，而是P2必须重建训练
superdomain、并把外部不可测能力留在内部实验的直接证据。

因此当前准确状态是：

> 外测需要的 PM 和链路已经定义；主要 V5.2 架构错误已有对应修复；但“修改后的完整系统已达到外测要求”仍须经过 P2 冻结、P3 FIT、P4 fresh confirmation 后才能成立。

---

## 2. 所有 response 实验共用的评测合同

### 2.1 公平性与同栈约束

所有 response baseline 必须共享：

- 相同 state、当前可见对话和同用户私有历史；
- 相同 memory compiler、Strategy Bank、query builder、候选池和 exact Rank-1；
- 相同 hard eligibility；
- 相同 typed Step2、generator、temperature、seed、token cap、guard 和 fallback；
- 相同评审页面、rubric、聚类单位和置信区间算法。

不同条件唯一允许变化的是资源开关策略。资源正文、检索排名、generator 或 evaluator 不得随 baseline 改变。

### 2.2 机制指标：先分责，再看最终回复

每个 domain、policy、component 都必须报告：

| 层 | 指标 |
|---|---|
| Retrieval | candidate-present、Top-1 fit、owner/time正确率、abstention、候选池规模、retrieval margin；可比时报告 Recall@k/nDCG@k |
| Eligibility | owner/time、goal/function、boundary/burden、specific increment 四门及 hard denial 率 |
| PM Step1 | ON/OFF率、概率与阈值、hard-gate violation、BA/recall/specificity/Brier（只在有gold的内部域）、相对 matched-random 的选择增益 |
| Step2 | requested-realized exact match、generator received/used evidence、required-contribution、functional contribution、grounding fidelity、atomic-move compliance、scaffold exposure、fallback |
| End-to-end | quality NetWin、material-risk rate、critical events、prompt/total tokens、API cost；latency只作描述性诊断 |

最终 quality 差不能自动归罪 PM：必须按 `retrieval_fit × pm_correct × execution_valid` 分层。

### 2.3 Response quality

Primary 是同状态匿名 A/B 采用判断：

- 页面显示相同可见对话；若存在经过验证的过去背景，两臂显示同一份中性背景面板；
- 不显示 policy、component、action、cost 或资源开关；
- `A materially better / B materially better / tie / uncertain`；
- 只有足以改变实际采用决定的差异才选 A/B；轻微文风、温度或长度差异为 tie；
- decisive criteria 固定为：
  `grounded_context_fidelity`、`emotional_understanding`、
  `request_and_dialogue_fit`、`immediate_helpfulness`、
  `clarity_naturalness_not_overloaded`、`materially_equivalent`。

主统计：

```text
NetWin = P(learned better) - P(learned worse)
```

报告 win/loss/tie 原始数、cluster-level NetWin、95% cluster bootstrap CI。ESConv 按 dialogue/user 聚类，EvoEmo 按 user 聚类。同一状态不同 seed 不得当独立人。

实际人类标注才可称 human primary。ChatGPT、Claude、Gemini 或其他模型产生的标注必须记录为 `annotator_type=llm`，只能称 model panel / LLM sensitivity，不得改称人评。

### 2.4 Interaction-and-grounding material risk

Risk 独立于 quality。页面显示当前对话、该回复真实获准的证据/边界和单条回复，只判断严重到足以改变是否采用的风险，不评价帮助性或资源是否做功。

固定类别：

1. `stale_or_conflicting_use`
2. `unsupported_personal_claim`
3. `overgeneralized_pattern_or_cause`
4. `fabricated_recall`
5. `explicit_boundary_violation`
6. `excessive_directiveness`
7. `internal_resource_label_exposure`

另从证据 owner 绑定派生 `wrong_owner_personalization` critical flag；它不能被淹没在普通 unsupported claim 中。

主统计为每独立 cluster 的 `any_material_risk`、各类别事件率、learned-minus-comparator risk difference 和 95% cluster bootstrap CI。资源未做功可以是 `risk=no`；真实过去信息未在当前回合重述也不自动等于 stale。

### 2.5 Cost

Primary cost 是真实 generator input/prompt tokens。另报告 completion tokens、total tokens、API价格换算、retrieval/embedding本地计算开销和 observed latency。Latency 不是随机化性能结论。

主系统相对 `fixed-high-eligible` 必须至少降低10%平均 input tokens。cost-matched/random-matched 的动作和 seed 必须在任何测试 outcome 前冻结。

### 2.6 Response 系统判定门与外部证据层级

learned-PM-full 的正式 QRC 判定由 **P4内部fresh confirmation** 承担，沿用机器合同：

1. 对 always-off：质量非劣（NetWin 95% CI下界 `>= -0.05`），且预测 ON strata 的质量 NetWin 点估计 `> 0`；
2. 对 fixed-high：质量非劣；risk difference 的95% CI上界 `<= +0.05`；input tokens至少下降10%；
3. 对 transparent-rule：质量和risk非劣，并在quality或cost至少一个维度严格改善；
4. 对 cost/on-rate-matched-random：quality点估计更好或risk更低，证明不是单纯“少开”；
5. `fabricated_recall`、`wrong_owner_personalization`、`explicit_boundary_violation` 三类 critical event 在正式判定单位上为0；
6. 任一 material misuse 不得被质量或成本抵消；
7. 每个可测组件必须单列 coverage、ON/OFF、functional use、risk 和 requested-realized，不能只报总平均。

P5的ESConv/EvoEmo使用同一estimand、同一`-0.05/+0.05/10%`参考线并报告完整CI，但不承担新的
confirmatory二元pass。现有power simulation最保守约需1095个独立group，而ESConv只有122个dialogue、
EvoEmo只有12个正式response用户cluster；把turn当独立人会虚增精度。故P5只回答方向、运输、机制和失败边界。
外部各域也不互相合并成一个“总通过率”。即使点估计达到参考线，也不能冒充全新外部确认；若论文需要
正式external noninferiority，必须新增真正未触碰且规模足够的用户/数据集。

### 2.7 评审波次

P5 外部 response 只进行一次合并语义评测波次：

- 一套 primary；
- 预冻结20%独立 overlap；
- 一次集中分歧裁决；
- 全量独立 LLM judge 只作敏感性；
- 禁止小包人评—修prompt—再人评。

---

## 3. 外部实验一：ESConv response replication

### 3.1 数据与单位

- 当前可执行参考集：122个独立 ESConv test dialogues；正式 V5.3 物化前仍须重新验证 hash、dialogue 去重和无 corpus-level `situation` 泄漏；
- memory unavailable：MP/MS/ME 结构性 mask；
- 独立统计单位：dialogue/user，不是单条 supporter turn；
- 身份：corrected repaired replication，不用 ESConv outcome 训练或调 PM。

### 3.2 测什么

- RS exact Rank-1、动作前提、非冗余、上一轮已执行与显式边界；
- learned RS head 是否比固定全开/人工规则更会选择；
- M0+R0 是否在不需要策略时保留质量并节省成本；
- RS Step2 是否只执行一个原子动作、没有追加第二建议/问题。

不能由 ESConv 声称 MP/MS/ME 长期记忆泛化。

### 3.3 指标与标准

- 机制：RS candidate coverage、eligible rate、ON/OFF、Top-1 fit、requested-realized、atomic compliance、fallback；
- quality/risk/cost：第2节全部指标；同一QRC参考线用于解释，但不把122个dialogue包装成有充分power的外部确认门；
- RS 子域成功还要求：有实质 ON 和 OFF 覆盖，不能通过“恒关”得到 QRC；具体最低 ON/OFF 支持由 P2 power/sample freeze 在 outcome 前写入机器合同；
- 若 cost-matched-fixed 与 always-off 完全 alias，只生成一次物理回复并在逻辑表保留两个条件。

### 3.4 Baselines

主表：

1. `always_off`：M0+R0；
2. `fixed_high_eligible`：所有 eligible RS 开；
3. `transparent_rule`：冻结人工规则；
4. `learned_pm_full`：外部动作空间仍为16动作，但 MP/MS/ME被结构性mask，实际检验RS bit；
5. `cost_matched_fixed`：当前栈、outcome-blind冻结；
6. `cost_and_on_rate_matched_random`：按RS开启率/成本和预冻结seed随机。

次表：RS单bit oracle上界可作诊断；Legacy V1.0 只有在当前 V5.3 栈精确 replay 时才能进入次表，否则只列历史数字。

---

## 4. 外部实验二：EvoEmo longitudinal response replication

### 4.1 数据与单位

- 数据为18个合成长历史用户；p1–p6只用于开发/兼容性，不进入正式 P5 主统计；
- p7–p18共12个用户、138个现有 response states，可作 V5.3 repaired replication 参考分母；正式物化须保持既有 state 集，不按 V5.2 outcome 重选；
- 每个 state 只能访问该 user 且严格早于 current session 的历史；未来会话、其他用户和全库混检为机械无效；
- 独立统计单位为 user；138个state绝不能当138个独立用户；
- 所有 p1–p18 已有不同程度开发/结果暴露，不能称 pristine lockbox。

### 4.2 测什么

- MP_PROFILE/constraint 是否只在会改变建议范围、时机或负担时开启；
- MS 是否找回并使用具体旧目标、观察或未完成线程，而不是只找同主题摘要；
- ME 是否在当前允许行动时检索真实 action-result/mechanism，并作为可拒绝选项使用；
- 大候选池、同主题干扰、wrong owner、current echo、age/conflict 下的检索与路由；
- RS 在纵向回复中的联合动作表现；
- Step2 是否真正融合证据、保留过去/当前时态、归属和自然表达；
- quality—risk—cost 运输及各层失败责任。

不能由此证明 MP_PREFERENCE、完整16动作自然覆盖、真实临床效果或全新用户泛化。

### 4.3 指标与标准

- 第2节所有机制、quality、risk、cost指标；
- candidate池按组件报告中位数/分位数、Top-1 fit、wrong-owner/未来泄漏必须为0；
- user-cluster bootstrap为主；state-level结果只能作描述性；
- 第2.6节QRC参考线用于判断方向是否与内部一致，但因12个用户和既有暴露，最高只能称 repaired replication，
  不给本域单独贴confirmatory PASS/FAIL；
- MP/MS/ME 每个组件均报告 available、eligible、ON、used、functional、risk 的完整漏斗；候选缺席或 UNKNOWN 不得从分母静默删除；
- Raw-session比较只回答“结构化表示与原始session上下文”的次问题，不替代policy主表。

### 4.4 Baselines

主表：

1. `always_off`；
2. `fixed_high_eligible`；
3. `transparent_rule`；
4. `learned_pm_full`；
5. `cost_matched_fixed`；
6. `cost_and_on_rate_matched_random`。

次表/消融：

- `learned_full_minus_MP/MS/ME/RS` 四个单bit消融；
- MP/MS/ME/RS单组件 fixed arms；
- `raw_session_top4_plus_same_strategy`；
- `all_raw_sessions_plus_same_strategy`；
- oracle candidate/effect只作不可部署上界；
- Legacy V1.0仅在当前栈精确replay时作次表，否则只列历史结果。

所有 raw-session 条件也必须同用户、严格过去，并使用同一个generator/seed/evaluator。

---

## 5. 外部实验三：ES-MemEval QA diagnostic

### 5.1 数据与单位

- 官方公开 v1.0.0 artifact 共1,427题；当前已冻结、可与 V5.2 对照的 task-disjoint 主切片为 p13–p18 的418题；
- V5.3 主诊断继续使用同一418题，不因既有分数重抽题。若以后扩到1,427题，必须建立独立 protocol，不能与418题混为同一确认；
- 五类：information extraction、temporal reasoning、conflict detection、user modeling、abstention；
- 生成只看到 question 与该condition允许的历史，不看到 answer、evidence、capability 或 group；
- 聚类单位为 user，另报告question-level bootstrap作敏感性。

### 5.2 测什么

- 记忆检索是否找对session；
- 历史事实、时间、冲突和拒答是否读对、答对；
- typed-memory与raw-session/full-history表示的准确率—成本关系；
- response-utility PM 在明确历史QA上的有限跨任务运输。

ES-MemEval不做情绪支持response quality，也不做第2.4节的 interaction-and-grounding risk 主张。QA中的幻答、错误归属和应拒不拒单列为 QA error/abstention diagnostic，不与response material-risk率合并。

### 5.3 指标

Objective primary：

1. 官方 normalization 后的 set-overlap Token F1；
2. `bert-score==0.3.13`、`bert-base-uncased`、不rescale的 BERTScore F1；
3. 按全部418题和五种capability分别macro average；
4. abstention accuracy、should-abstain false-answer rate；
5. conflict-detection单列；
6. 对可完整映射official evidence的341题报告session Recall@4和nDCG@4；其余无gold/拼写映射不完整题不得伪造检索分；
7. prompt/completion/total tokens、调用成本与latency诊断。

LLM-as-Judge 0–2只能作第三敏感性指标，必须独立冻结prompt/model并报告与objective指标的一致性；不得作为训练gold或替代Token F1/BERTScore。

### 5.4 判定标准

ES-MemEval是诊断，不承担V5.3 response QRC的二元通过门。必须报告每个condition的绝对分、与 `typed_memory_fixed_high` / `official_session_rag_top4` 的同题paired差、user-cluster 95% CI和token成本。

允许的结论只有：

- 检索/回答是否改善；
- learned PM是否表现出有限QA运输；
- 哪些capability或资源schema不在当前支持范围。

不得把“QA learned输给fixed-high”写成response PM整体失败，也不得把“QA分数更高”写成四组件QRC通过。由于既有418题结果已经可见，V5.3不再事后发明QA非劣阈值；本域不使用新的二元pass/fail标签。

### 5.5 Baselines

1. `no_memory`；
2. `full_history`；
3. `official_session_rag_top4`；
4. `typed_memory_fixed_high`；
5. `typed_memory_learned_pm`。

`transparent_rule`可作预冻结次要诊断，但不进入官方五条件主表；cost-matched不适用于QA；RS对事实QA结构性N/A；Legacy V1.0不适用。

---

## 6. 三个外部实验的 baseline 总矩阵

| Baseline/condition | ESConv response | EvoEmo response | ES-MemEval QA |
|---|---|---|---|
| always-off / no-memory | 主 | 主 | 主 |
| fixed-high-eligible / typed fixed-high | 主（RS） | 主 | 主 |
| transparent-rule | 主 | 主 | 可选次表 |
| learned-PM-full / typed learned | 主（RS子域） | 主 | 主压力测试 |
| cost-matched-fixed | 主，alias则去重 | 主 | 不适用 |
| cost/on-rate-matched-random | 主 | 主 | 不适用 |
| Raw Session Top-4 | 不适用 | 次表 | 主 |
| All Raw Sessions / full history | 不适用 | 次表 | 主 |
| learned-full-minus-one | 内部/可选RS消融 | 次表 | 不适用 |
| Legacy V1.0 current-stack replay | 条件性次表 | 条件性次表 | 不适用 |

---

## 7. 双 Codex 不冲突执行协议

### 7.1 单一领导与共享文件规则

- Leader Codex负责：本运行手册、三份权威事实源同步、P2 gate签字、正式生成计划、外部指标/baseline和最终聚合。
- Worker Codex负责：预先分配的独立诊断/资格脚本、独立output目录和分项报告。
- Worker不得直接修改三份权威事实源；完成后以commit、报告路径和机器结果交给leader，由leader一次性同步。
- 两个会话都不得使用`git add .`、不得amend/rebase对方commit、不得覆盖对方output目录。
- 开始任务前先运行`git status --short`；发现对方未跟踪文件时不得移动、格式化或纳入自己的commit。
- 当前已知Worker所有权文件：
  `scripts/v1_5/64_mp_ms_contribution_slot_domain_comparison_v1_5.py`及其专属output；leader不得修改。

### 7.2 Worker工作流 W：P2前置数据与运输资格

可以并行、零API：

| ID | 任务 | 输出边界 | 完成定义 |
|---|---|---|---|
| W1 | 三态观察器内容独立资格补全 | 新脚本/新output/分项报告 | 不只随机自然频率；另有内容独立、措辞多样的INVITES/DECLINES/UNKNOWN平衡资格集；报告recall/precision/混淆，UNKNOWN不作OFF gold |
| W2 | MP/MS contribution-slot train-vs-external域审计 | Worker现有script 64及独立output | 同一候选级代码；Rank-1与Top-k不混写；按user/family报告，不把state当独立人 |
| W3 | RS域审计 | 新script/output/report | card precondition、nonredundancy、burden fit、already executed在训练域与ESConv/EvoEmo的支持范围可比 |
| W4 | 全新ME superdomain与真实密度审计 | 新数据构造脚本、manifest、零outcome报告 | 外部文本零复制；正/非正、至少8族；同用户多候选、同topic不同事件碰撞；intended-positive compiler-valid且exact Rank-1绑定 |
| W5 | shortcut/leakage/duplicate审计 | 新report | topic/长度/前缀/候选数/subtype与标签解耦；user/family/group split零交叉；没有未来/他人历史 |

W1–W5只产生观察/资格/数据构造证据，不生成paired response outcome，不训练head，不读quality/risk。

### 7.3 Leader工作流 L：执行器、账本与外部合同

可与 W1–W5 并行：

| ID | 任务 | 完成定义 |
|---|---|---|
| L1 | 正式runner接入`StagewiseAccountabilityRow` | 每个 expected `state×policy×seed`恰好一行；五层字段完整；缺行/重复行fail-closed |
| L2 | Step2全动作兼容门 | 历史已消费case；覆盖M0+R0、M0+RS、四单组件和联合动作；schema/evidence binding 100%，atomic compliance≥95%，required-contribution自动率≥90%，内部标签/未授权专名数字0 |
| L3 | V5.3 baseline materializer | 六主baseline同候选/执行器/generator/seed；alias物理去重；cost/random在outcome前冻结 |
| L4 | power与评测freeze | FIT/confirmation/sealed的N、split、quality/risk/cost、cluster bootstrap、20% overlap和裁决协议写入机器合同 |
| L5 | 外部plan scaffold | 只物化数据身份、state、candidate lineage和逻辑条件，不生成回复；ESConv/EvoEmo/QA hash与gold边界检查通过 |

L1–L5不读取新的质量/risk outcome。L2若需真实付费compatibility调用，必须另行产生预算identity并请求用户授权。

L2 当前有四项已核实阻塞，不能只跑现有单测后宣布通过：

1. 机器合同规定 `second_free_llm_fallback_allowed=false`，主计划也规定guard失败后直接确定性M0；但当前
   `call_with_guard_and_rewrite()`仍会进行第二次自由LLM rewrite。必须在P1内二选一统一，默认以机器合同为准：
   删除正式runner中的第二次自由调用，首轮失败直接保留错误并进入确定性M0；历史rewrite试验只作开发证据。
2. 当前机器guard尚未完整实现“未授权专名/数字”检查；必须基于运行时授权实体/数值集合，而不是自然语言黑名单。
3. `atomic_move_budget`目前主要是prompt约束；RS原子动作数、列表长度和一点式边界还缺可靠的结构化实现/校验。
   在无法机器确定的语义边界上不得假装硬判，必须在程序输出schema中把response acts结构化，再检查计数。
4. RS资产尚有同栈漂移：当前V3训练候选审计记录的是80-card Strategy Bank，而近期V5.3 RS pilot读取的是
   6-card `strategy_cards_v1_5_minimal.jsonl`。P1必须选择一个正式Bank，并把path、SHA、card count写进机器合同；
   FIT、ESConv、EvoEmo和所有baseline共享同一份，80-card训练证据与6-card运行结果不得混称同栈。

### 7.4 唯一汇合门 G-P2

只有以下全部满足，leader才能把状态从P1改为P2 frozen：

- W1–W5报告完成，已独立核对而非只接受结论；
- realistic-density ME Rank-1支持通过；
- MP/MS/RS域差异已量化，任何out-of-support轴有明确UNKNOWN/OOD处理；
- Strategy Bank path/SHA/card count唯一冻结，训练、FIT、confirmation、ESConv、EvoEmo和baseline无漂移；
- L1账本runner、L2执行器兼容门、L3 baseline、L4 power/metric、L5外部scaffold完成；
- 新superdomain的内容、用户、family、group split和hash冻结；
- 三份权威事实源由leader做一次同步commit；
- 工作树无双方遗留的冲突修改；
- 明确记录哪些外部数据已暴露，不能称lockbox。

当前RS域审计可作为一个有限域描述，但不能直接完成G-P2：脚本已经正确地从训练`current_user_text`用
当前runtime重算，0/160触发是值得保留的训练构造缺口；然而ESConv代码默认只取文件前300段对话，
与docstring声称的1300段全量不一致，而且报告只有触发率、没有gold precision/recall。W3必须先修正文档/采样
身份、写入输入与实现hash，并增加有独立gold的资格层；不得把3.4%/10.1%触发率直接解释成准确率。

### 7.5 P2之后严格串行

```text
G-P2 PASS
  -> P3: 一次整批 paired ON/OFF FIT生成
  -> 一次primary + 20% overlap + 一次裁决
  -> 一次四head训练/阈值冻结
  -> P4: 一次fresh confirmation；失败不建第二份
  -> 通过后一次sealed internal
  -> P5: 同一release内运行ESConv + EvoEmo + ES-MemEval
  -> 自动机制/cost/QA指标
  -> 一次合并外部human/model panel
  -> 最终聚合与论文表
```

四组件 paired ON/OFF response generation 属于P3，不是P2前置任务。P2前可以构造state/candidate与调用计划，但不能生成或查看paired outcome。

### 7.6 P5内部可并行但必须同一release

P5冻结后：

- ES-MemEval QA生成可与response生成并行，因为不读取response outcome；
- ESConv与EvoEmo可并行生成，但必须共享同一executor/generator release hash；
- 自动cost/coverage/routing可边生成边写账本，但最终聚合须等expected keys完整；
- 人评页面可由冻结plan生成schema，不得在回复未完成时抽样；
- LLM judge和human review可在全部回复seal后并行，双方不得看到彼此结果；
- 最终裁决和聚合最后执行。

任何一个域发现机械错误，只允许版本化重跑受影响单元；质量差、risk高或输给baseline不是机械错误，不能回头修方法。

---

## 8. 给 Worker Codex 的启动指令

Worker开始新任务前必须先读本文件和三份权威事实源，然后回复以下六项，不满足不得开工：

1. 当前任务ID（W1–W5中的一个）；
2. 将创建/修改的精确文件路径；
3. 明确不会修改的共享文件；
4. 是否读取任何已有quality/risk/outcome；
5. 是否调用API及预算identity（默认必须为否）；
6. 完成后提供commit、命令、测试、output和仍未解决限制。

Worker建议读取命令：

```bash
cd /home/tokkio/snap/metacom_v33_pm_v1_5_repair/project
git status --short
sed -n '1,260p' docs/PM_V1_5_V5_3_EXTERNAL_EXPERIMENT_AND_PARALLEL_RUNBOOK_20260806_ZH.md
jq . data/pm_v1_5_contracts/v5_3_integrated_evidence_execution_v1.json
```

禁止把“脚本能运行”“开发集回放通过”“候选存在”分别写成“PM学会”“fresh资格通过”“资源产生质量收益”。

---

## 9. 当前下一步

1. Worker继续完成其已占用的script 64，再依次提交W2、W3、W4/W5；W1现有70条自然样本结果保留，但必须承认正例不足，是否补平衡资格集由P2 gate统一决定。
2. Leader不触碰script 64，先完成L1的formal ledger runner接线审计与L2全动作兼容门设计。
3. 两边完成后只在G-P2汇合一次；此之前不生成正式paired outcome、不训练正式heads、不运行外部response/QA。
4. G-P2未通过时，准确报告缺失项；不得用旧V5.2结果或EvoEmo开启率替代。
