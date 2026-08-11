# PM V1.5 V5.3 指标、Oracle、责任归因与三外部实验冻结

日期：2026-08-09

机器权威合同：

- `data/pm_v1_5_contracts/v5_3_metric_responsibility_and_oracle_v1.json`
- `data/pm_v1_5_contracts/v5_3_external_complementary_evidence_v1.json`

## 1. 本次到底补全了什么

V5.3 仍然是四个组件位 `MP/MS/ME/RS` 投影到完整 16 动作；没有退回四个互不相干的二元实验。
当前正式 576 组 paired effects 的职责是学四个低容量边际价值头；它们通过后，再在 32–48 个相同
current state 上把 16 个动作全部执行，测交互、可接受动作集合和 policy regret。

本次解决了原方案中四个散落而未统一的问题：

1. 旧 `minimum_publishable_metric_registry_v1.json` 的 binary Brier learnability gate 与当前连续
   uplift 目标冲突；现在只在“组件学习/正确调用”范围由新合同替代，旧的 response quality、risk、cost
   定义中仍适用的部分被明确继承。
2. “PM 调用对了”不再依赖一个臆造的唯一 gold action，而分为组件 resolved label 与完整动作 oracle set。
3. 失败不再只看最终回复倒推 PM，而同时保存 deployment ITT 与机制责任账本。
4. ESConv、EvoEmo response、ES-MemEval QA 三条互补证明链及其 baseline、资源 mask、指标边界被写入
   同一机器合同。

这些合同在正式 effect 聚合和 V5.3 外部执行前冻结；不修改正在运行、已有内容哈希授权的 generator、judge、
typed executor 或 formal runner。

## 2. PM 怎么才算“学会”

“学会”分三层，不用一个 accuracy 混过去。

### 2.1 四个 head 的预测学习

每个训练单位是同一 state、同一 actual Rank-1、同一 seed 下的 ON/OFF paired response。三个 seed 先聚合，
目标是连续 `positive_support_contribution` uplift；tie 保持 0，负收益保持负值。正式 OOF 门仍为：

- MSE 至少比各 fold 训练均值预测器低 5%；
- OOF Spearman 至少 0.15；
- target 和 prediction 非常数，且至少覆盖 12 个独立 cluster；
- balanced accuracy 只作诊断，因为连续收益不应被硬切成伪二分类。

任一 head 不通过就固定 fail closed，不能通过看 outcome 后换 representation、补“好学”的 state 或降低门槛。

### 2.2 单组件调用是否正确

训练仍用连续值；只有诊断时，在执行和测量足够可靠的组上产生四类标签：

| 标签 | 含义 |
|---|---|
| `ON_ONLY` | 资源被正确执行，且 Q uplift `> +0.10` |
| `OFF_ONLY` | 资源被正确执行，且 Q uplift `< -0.10` |
| `EITHER` | 资源被正确执行，且 `|Q uplift| <= 0.10`；开关都不算 value PM 错 |
| `UNRESOLVED` | 缺 Q 结果、评审冲突、transport/fallback、资源未真正使用或候选无效 |

`0.10` 是在 `[-1,1]` contribution 量尺上的预冻结实际无差异带；同时报告 `0.05/0.15` 敏感性，但不能替换
主定义。cost 不改变这个组件价值标签：若 ON/OFF 质量等价，cost 在最终动作投影里偏向 OFF。

Risk 另记 `SAFE/UNSAFE/UNRESOLVED` overlay，不能把“Q 有贡献但有风险”篡改成“Q 没贡献”。最终部署和 16-action
safe oracle 会排除 `UNSAFE`；benefit-only 正确率则在 resolved Q 分母上报告。这样 Q/R 定义独立，又不会因为只抽样
人审 risk 让绝大多数 value label 变成 unknown。

因此“正确率”至少报告 beneficial false-off、harmful false-on、EITHER compatibility accuracy、resolved coverage、
unsafe-selected rate、risk-resolved coverage 和 unresolved 原因；绝不把 `UNKNOWN`、tie、candidate presence、
construction condition 或 executor failure 变成 OFF gold。

### 2.3 完整 16 动作是否选对

同一个 state 必须执行全部 16 个动作。先排除结构无效、wrong-owner、future 或 material/critical-risk 动作；再保留质量
距最佳不超过 `0.10` 的所有动作；最后只在质量等价的安全动作间取 deterministic incremental injected-prompt
tokens 的精确最低成本 frontier，成本相同的动作全部保留。这样得到的是
oracle set，不是假装每个状态只有一个绝对正确动作。

主指标为：oracle-set inclusion accuracy、quality regret、质量 frontier 上的 excess deterministic cost、
critical-invalid action rate、requested-realized exact match，以及多组件逐位
`requested → received → used → functional` 漏斗。Q 与 cost regret 分开，不造一个隐藏加权总分。

## 3. Q、R、F、C、D 为什么必须分开

| 轴 | 回答的问题 | 是否进入组件训练标签 |
|---|---|---|
| Q: positive support contribution | 这个资源给回复增加了多少目标推进、情绪支持、具体帮助和自然度 | 是，连续 uplift |
| R: material interaction/grounding risk | 是否违反明确边界、说错人/历史、过度指令或增加负担 | 否，独立 guardrail |
| F: functional execution | generator 是否真正收到、使用并完成该资源要求的贡献 | 否，机制诊断 |
| C: cost | 实际注入、输入/输出 tokens、价格、延迟、fallback/recovery | 否，只进联合投影和报告 |
| D: decision correctness | PM 是否命中可接受动作集合、regret 和错开/错关 | 由前四轴构造的评测 |

这里“独立”是定义和记录独立，不是假设它们统计上互不相关。比如一个具体记忆可以同时增加支持贡献并造成
过度确定的个人判断；两件事都必须保留，不能相互抵消成一个黑箱总分。

## 4. 失败到底是谁的责任

最终部署结果按 ITT 计入 learned policy，但机制归因同时找最早有证据的失败阶段：

| 观察 | 主要责任 |
|---|---|
| 合法历史没有被 materialize，或 owner/time/version 源字段错误 | catalog / adapter |
| 合法候选存在但 actual Rank-1 选成同主题干扰、旧版本或错人 | retriever |
| 部署可见资格/窄语义门错误 hard-off 或错误放行 | eligibility / semantic interface |
| resolved oracle 要 ON 而 PM 关，或要 OFF 而 PM 开 | PM |
| PM 请求正确但证据没收到/没用、动作未实现、泄露 scaffold 或 fallback | Step2 / generator |
| 候选、PM、执行都正确，资源干净使用后仍降质/增风险 | resource × generator interaction |
| judge/human 冲突、缺结果、风险未裁决 | measurement |
| 超出冻结语义/表示支持范围并 fail closed | scope / OOD |

所以论文可以同时回答两个不同问题：部署这条 policy 最终造成了什么，以及发生问题时最应该修哪一层。

## 5. 三个外部实验缺一不可

### 5.1 ESConv response

ESConv 没有可靠纵向私有记忆，机械 mask `MP/MS/ME`，只测同一六卡 RS Bank 下的即时策略开关、明确边界、
回复 quality/risk/cost 和 memory bits 能否稳定关闭。正式评价使用 held-out validation/test，Bank 只来自经过
EvoEmo 血缘隔离的 train lineage。主要条件是 always-off、fixed-high、transparent rule、learned RS、
cost-matched fixed 和 cost/on-rate-matched random。

### 5.2 EvoEmo longitudinal response

使用全部 18 用户与已有 204-state panel，所有 learned 预测 user-held-out/cross-fitted。只允许同用户严格过去历史，
测 MP profile/constraint、MS continuity/observation、实际可得到的 ME action-result、RS 联合动作，以及 evidence-aware
whole-response 的 owner/time/grounding、quality/risk/cost 和责任漏斗。Raw Session Top-4 与 All Raw Sessions 只作
记忆表示次表，不冒充合法 16-action PM arm。

### 5.3 ES-MemEval QA

使用公开 v1.0.0 的全部 18 用户、1,427 题，测 information extraction、temporal reasoning、conflict detection、
user modeling 和 abstention。五个主条件沿用 V5.2：no-memory、full-history、official session-RAG Top-4、typed
fixed-high、typed learned PM。

question 可以给生成器；answer、evidence、capability、question group 和 official evidence mapping 只能在 prediction
不可变后由 evaluator 关联。主指标是官方对齐 Token F1、固定版本 BERTScore F1、五能力分层、abstention/false-answer、
conflict，以及只在可确定映射题上的 Recall@4/nDCG@4。它不承担 response QRC 通过门。

三条结果按任务分别报告，不合并扩大样本量：ESConv 不能证明长期记忆，EvoEmo response 不能替代 QA 时间/冲突/
拒答，QA 也不能替代支持回复 quality/risk。

## 6. “同一套 RAG”现在还要不要管

要管，但按 estimand 精确定义：

- learned PM、fixed、rule、matched-random 等路由策略比较，必须共享候选池、retriever、actual Rank-1、Step2、
  generator 和 evaluator；否则 PM 的收益可能只是换了 RAG。
- ESConv 与 EvoEmo 的 RS 必须共享同一冻结六卡 Bank 与 RS 检索器。
- QA 的 official session-RAG、full-history 和 typed-memory 是故意比较不同表示方法，因此可以保留各自预注册的
  representation/retriever；但必须共享源历史、用户/时间边界和 gold 不可见性。

所以现在没有“训练一套 RAG、测试换另一套 RAG”的漏洞，也不会荒唐地强迫事实 QA 的 session retrieval 与支持回复
的 RS Bank 变成同一种算法。

## 7. 禁止回到 V5.1/V5.2 的机械拼接

V5.3 的硬门是：generator 在生成前看到 typed response program 与 literal authorized evidence，一次生成完整自然回复
和私有 evidence-use trace。下列情况直接算协议失败：

- `primary_response + locked_clauses`；
- 生成后追加检索内容或固定 memory wrapper；
- prompt 中有证据就宣称“已使用”；
- 用户可见文本出现组件名、resource ID 或内部 scaffold。

多组件正式面板前还必须报告逐组件 received/used/functional、partial use、evidence competition、fallback 和 overload。
这一步非常重要，因为单组件执行合格并不自动保证四个资源同时打开时 generator 仍能自然整合。

## 8. 当前能否保证 PM 及格

现在能保证的是：训练目标有真实 paired causal signal、特征低容量且可部署、测试是 OOF、失败 head 会关机、正确调用
和责任归因已有可执行定义，外部三条证明链不会互相冒充。

不能在看完正式 576 组前数学保证四个 head 都通过。但 development pilot 已给出四个 head 都超过均值基线且达到预冻
Spearman 门的方向性证据；因此“有希望学出来”已经不是空想。真正及格仍需按顺序完成：六 fold effect → 正式 OOF →
多组件资格 → 16-action oracle panel → 三外部实验。任何失败都按冻结门报告，不再通过重写训练数据把结果调成 PASS。

## 9. 2026-08-09 三外部源机械预检

零 API 预检见 `outputs/pm_v1_5_v5_3_external_source_readiness_20260809/report.json`，状态为
`SOURCE_PASS_V53_REMATERIALIZATION_REQUIRED`：

- ESConv split 为 train 934 / validation 186 / test 180；84 个 EvoEmo 血缘 dialogue 已绑定隔离，最终可用
  test 为 169。
- EvoEmo 为 18 用户、401 个 `(user_id, session_id)` 会话，既有 response selection panel 正好 204 state。
- ES-MemEval 公开 artifact 为 1,427 题；五能力计数为 extraction 309、temporal 284、conflict 267、
  user modeling 306、abstention 261。

但旧 V5.2 物化文件不能直接拿来跑 V5.3：旧 ESConv panel 只有 122 state；旧 EvoEmo 204-state
`runtime_state` 含当前未关闭 session 的 `current_session_summary`；旧 QA evaluator-only 文件只有 418 题。
因此要保留既有 204 个 selection identity，重新从合法 visible prefix 物化状态；并新物化 169 个 ESConv state 与
1,427 题 question/gold 物理分离计划。这个结论没有读取任何旧 quality/risk/outcome，不是为了结果重挑样本。

## 10. Baseline 冻结

机器权威合同新增 `data/pm_v1_5_contracts/v5_3_baseline_matrix_v1.json`。V5.2/旧方案可以直接复用的是
“比较问题和任务结构”，不是旧 response outcome。V5.3 response 主表固定六个逻辑条件：

1. `always_off`：回答可选资源相对无资源是否有条件收益；
2. `fixed_high_eligible`：回答 PM 能否相对资源全开降低风险/成本而保留质量；
3. `transparent_rule`：回答 learned 是否超过简单可审计规则；
4. `learned_pm_qualified`：正式通过的 head 使用 cross-fitted 预测，失败 head 明确 fail closed；
5. `cost_matched_fixed`：回答相近成本的一种固定资源包是否已经足够；
6. `cost_and_on_rate_matched_random`：回答收益是否来自语义选择，而不只是少开资源。

前四个是稳定主条件；后两个必须先通过 matching 资格，不能只挂名字。`cost_matched_fixed` 的 deterministic
injected-token cost 与 learned 相差不得超过 5%；matched-random 必须保持组件 ON counts、总 deterministic cost
误差不超过 5%，且至少 25% state 的动作真的不同于 learned。

旧 matched-random 以完全相同 token vector 作 cell key，真实数据上容易产生 singleton 并退化成 learned alias；当前
planner 已改为 `broad stratum × exact eligible mask` 内的 outcome-blind constrained permutation，选择 cost mismatch
最小的确定性置换，并显式输出 `qualified`。若失败，只报告 alias/mismatch，不得声称 learned 胜过随机选择。

EvoEmo 的 Raw Session Top-4/All Raw Sessions 继续作为记忆表示次表；它们不是合法 16-action PM arm。
ES-MemEval 继续沿用 V5.2 五条件，但扩为全部 1,427 题。V1.0/V5.1/V5.2 旧分数只作历史背景；除非在最终
V5.3 state、generator、seed、evaluator 上精确 current-stack replay，否则不能与 V5.3 主表做显著性比较。
