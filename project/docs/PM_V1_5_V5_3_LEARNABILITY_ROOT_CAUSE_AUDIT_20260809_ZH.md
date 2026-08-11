# PM V1.5 V5.3 可学习性失败根因审计

日期：2026-08-09  
性质：结果开放后的法证审计；不是 V5.3 重新及格，也不是新版本方案  
机器审计：`outputs/pm_v1_5_v5_3_learnability_root_cause_audit_20260809/report.json`

## 一句话结论

V5.3 冻结的四个 Q head 确实全部没有通过正式门，但现有证据不能推出“PM 本身学不会”。能够推出的是：**这次实验没有干净地提供并测量“什么时候该开组件”的监督信号。**

失败不是单一原因，而是五层问题叠加：

1. 功能使用标签存在定义上不可能为真的 `USED`，测量工具已经硬失败；
2. Step2、guard 和 fallback 明显污染了本应描述 pre-action 语义价值的标签；
3. 576 组是自然 state 的 ON/OFF 回复对，没有同能力 high/low current-state 反事实家族；
4. 仅 3 个长期用户的 pilot 决定了 5–6 维 memory head，每个开发折实际只用 2 个用户训练；
5. intended semantic conditions 几乎没有支持，candidate ontology 又与组件声称的功能错位。

因此，继续增加相同类型自然 state、继续重调 Ridge/PCA、换一个更大 embedding，或者直接把现有标签送入监督学习，都不能从根本解决问题。

## 已经做到什么程度

- 正式 paired-effect 生成完成：576/576 groups，每组 3 个 ON/OFF paired seeds。
- 正式外层 OOF 完成：MP、MS、ME、RS 各 144 groups。
- 四个冻结 Q head 均 fail-closed：
  - MP：relative MSE `0.9546`，Spearman `0.2355`；排序门通过，MSE 门要求 `≤0.95`，差 `0.0046`。
  - MS：relative MSE `0.9904`，Spearman `0.0469`。
  - ME：relative MSE `1.0501`，Spearman `0.0084`。
  - RS：relative MSE `1.0170`，Spearman `-0.0056`。
- 这个正式失败结论保持不变，任何 post-hoc 结果都不能救回 V5.3。
- 但“正式 head 失败”只表示冻结的 response-level Q uplift predictor 失败；risk 未进入正式标签，function 只作诊断且诊断工具已失效，cost 完全分开。因此它不是“完整 16 动作 oracle 正确率”的失败结论。

## 根因一：功能使用标签不可信

正式结果中 ON arm 共出现 70 个 replicate-level deterministic fallback。最终回复只是固定的 context-only 句子，例如：

> It sounds like that's been weighing on you.

这类回复不含任何授权 candidate，按定义只能是 `NOT_USED`。但现有 function judge 在 70 条中将 28 条判成 `USED`，错误率为 `40%`。

这不是“judge 可能有一点噪声”，而是硬逻辑矛盾。部分例子中，judge 还把当前 visible dialogue 的句子填入 `evidence_excerpt`，仿佛它来自 typed candidate。机器 validator 只检查 `response_excerpt` 是否逐字存在于回复，没有检查 `evidence_excerpt` 是否逐字来自 candidate。

所以此前“ON candidate 约 95% 被功能使用”这一结论无效，不能用于证明 executor 合格，也不能用于构造 PM oracle。

## 根因二：Step2 / guard / fallback 与 Step1 语义价值混在一起

V5.3 使用 requested-action ITT：PM 请求组件之后，无论 generator 漏用、guard 误杀还是 fallback，都计入该请求的最终质量。这对“部署整套系统会发生什么”是合理的，但对训练“当前 state 语义上是否值得开组件”不是同一个 estimand。

实际污染很大：

| Head | 有 ON fallback 的 groups | 这些 groups 的平均 Q effect | 无 ON fallback 的平均 Q effect | 负 effect groups 中含 ON fallback |
|---|---:|---:|---:|---:|
| MP | 5 | -0.292 | 0.263 | 5/25（20%） |
| MS | 25 | -0.120 | 0.269 | 13/25（52%） |
| ME | 21 | -0.133 | 0.296 | 12/23（52%） |
| RS | 4 | -0.021 | 0.092 | 1/45（2%） |

MS 与 ME 超过一半负例含 ON fallback。主要错误是词面 trace guard 判 `EVIDENCE_CLAIMED_USED_BUT_NO_WORD_TRACE_IN_REPLY`。这说明负标签中的相当部分不是“语义上不该调用”，而是“调用后没有被当前 executor/guard 链正确实现”。

更关键的是，正式 paid effects 前的 Q64 Step2 资格赛没有语义收口：64 条中 50 条直接通过、14 条 fallback；旧 runner 没保存这 14 条 guard 前的原始 provider 回复，无法区分 generator 未用证据和 guard 过严。正式 effects 在这个阻塞未解决时继续执行，重新踩中了失败清单 `V15-ENG-25`。

## 根因三：ON/OFF 因果效应不等于“何时调用”的可学习对比

每个正式 group 的 ON 与 OFF 确实共享同一个 current state，这能估计“在这个 state 注入 candidate 后，最终回复相对 context-only 改变了多少”。这一点是对的。

但正式 selector 做的是：每个 EvoEmo 用户、每个 memory head，从自然 state 池中按 candidate subtype、词面相关性桶、年龄桶、`current_redundant` 等稀疏 strata 的新颖性选 8 条。它没有：

- `counterfactual_family`；
- `state_family_id`；
- 同一 broad capability 的 high-value / low-value current state；
- 证明这些 high/low state 仅改变“是否值得调用”的人工语义裁决。

所以 576 groups 增加了 effect 均值的精度，却没有自动创造“什么时候开”的识别支持。模型看到的是大量不同用户、不同话题、不同 candidate、不同生成表达，同时 effect 由这些因素共同决定。

## 根因四：开发 pilot 不足以选择 memory head

MP、MS、ME 的开发 pilot 都只有 `p12`、`p13`、`p18` 三个独立用户，共 24 rows/head。Leave-One-User-Out 时，每个模型用 2 个用户、16 rows 训练，再测试第 3 个用户。

冻结的模型维数却是：MP 6、MS 5、ME 6。换成人话：MP/ME 相当于每个训练用户承担 3 个模型维度，MS 为 2.5 个。三次 generator seed 和同一用户的 8 个 state 不能把独立用户数从 2 变大。

因此 pilot 的及格很容易受用户特性、候选类型和随机 winner's curse 影响。正式 18 用户结果回归均值不是意外。这个问题重复了历史清单：

- `V15-PM-25`：正式实现违反低容量门；
- `V15-DATA-39`：把 rows 当成 independent groups；
- `V15-MEAS-61`：特征数必须由独立用户与反事实 group 共同约束。

## 根因五：语义条件与 candidate ontology 没有提供声明中的能力

正式 candidate 组成：

| Head | Candidate 构成 |
|---|---|
| MP | 120 relationship updates；24 onboarding profiles；0 preference |
| MS | 104 turn observations；40 session summaries |
| ME | 120 context events；24 reusable action-result |
| RS | 六种 atomic support cards |

ME 声称最容易学的核心功能是“过去采取了某动作，观察到某结果，当前出现迁移机会”，但正式数据 83.3% 是 context event。它主要测了“旧事件内容能不能帮助当前回复”，不是 reusable outcome 的调用条件。这重复了 `V15-MEM-50` 与 `V15-DATA-79` 对构念混用的警告。

显式 semantic opportunity 的支持也接近于零：

- MP `profile_goal_needs_advice_or_arrangement=true`：1/144；
- MS `continuity_request=true`：7/144；
- ME `current_action_invitation=true`：1/144；
- RS `card_already_executed_last_turn=true`：0/144。

`current_redundant=true` 反而在 MP/MS/ME 都对应更高平均 effect，说明这个字段测到的更像“话题重合、容易吸收”，不是“信息已经冗余、无需打开”。RS 的 `card_precondition_met=true` 平均 effect 也低于 false，说明透明规则与当前 generator 的实际增益未对齐。

## 根因六：标签大多为正，固定全开天然很强

- MP：113 positive / 25 negative / 6 tie；
- MS：106 / 25 / 13；
- ME：116 / 23 / 5；
- RS：85 / 45 / 14。

这说明 actual Rank-1 candidate 在现有 generator 下通常会让回复更具体或更长。负例既少，又混合了语义不适用、executor 漏用、guard fallback、生成表达差等不同原因。监督学习自然难以从这些异质负例中学会 abstention。

同时 ON 回复平均比 OFF 长很多：MP +50 词、MS +46、ME +58、RS +21。group-level 回复长度差与 Q effect 的相关约为 `0.28–0.42`。这不能证明 judge 只偏好长度，但证明 Q 中存在显著 surface-form 通道；它不是纯粹的“资源语义贡献”。

## 为什么还不能说 PM 没希望

第一，三次 paired seeds 的一致性不是零。已有审计估计 replicate-aggregated signal fraction 为 MP `.665`、MS `.663`、ME `.631`、RS `.576`。也就是说存在稳定 variation，只是当前特征和标签定义没有把它解释成“何时开”。

第二，MP 已经出现弱而一致的正式语义信号：Spearman `.236` 通过门，relative MSE `.9546` 只比 `.95` 门差 `.0046`。结果开放后的 PCA probe 还能超过门，但不能追认 V5.3。这说明 bounded semantic representation 不是完全无效。

第三，V5.2 已经展示 learned routing 相比 always-off 的质量差约 `+0.273`，相比 transparent rule 约 `+0.172`；它最后失败在 fixed-high noninferiority 与 fabricated recall 风险，不是“路由完全没有条件性价值”。V5.2 的 generator 实现不可直接复用，但它提供了 PM 概念存在信号的历史证据。

所以准确判断是：**PM 有希望学出有限、可审计的调用策略，但当前 V5.3 数据不能证明它，直接训练也没有足够把握及格。**

## 从根本解决：先建立五个互不串责的真值

这不是另起一个版本号，而是任何后续实现都必须满足的必要条件。

### 1. Candidate 真值

问题：生产检索器给出的 actual Rank-1 是否 owner/time/version 正确、与 current state 语义相关、属于正确 subtype？

责任：retrieval/candidate layer。  
测量：blind reviewer 或冻结语义 rubric；不能用最终回复好坏倒推换 candidate。

### 2. PM 调用真值

问题：在假设 qualified executor 能忠实使用 candidate 的前提下，这个 state 是否存在打开该组件的正当机会？

责任：Step1 PM。  
标签：16 动作 `oracle_set`，而不是强迫唯一动作。若多个动作都合理，则都算调用正确。

这个标签必须由 current observable state、合法 candidate、明确语义 rubric 与 clean paired effect 共同形成。construction condition 只能保证采样覆盖，不能单独冒充最终 worth-opening 标签。

### 3. Executor 真值

问题：收到授权 candidate 后，generator 是否在回复中形成了可见、具体、符合时态与 owner 的功能贡献？

责任：Step2/generator。  
测量：保存 raw first-pass reply；functional evidence 必须逐字绑定 candidate 和 final response；fallback 自动为 `NOT_USED`；不能让同一个 LLM judge 自由编造 evidence attribution。

### 4. Guard 真值

问题：guard 拦下的是实际违规回复，还是已经语义使用、但未满足词面 trace 的正常回复？

责任：guard。  
测量：在 raw first-pass reply 上计算 false accept / false reject，不能只审 fallback 后的最终句子。

### 5. 系统 ITT 真值

问题：PM 请求动作经过真实 generator、guard、fallback 后，部署系统最终的 Q/R/F/C 是什么？

责任：完整系统。  
用途：baseline 比较与论文最终结果；不能反过来当作纯 Step1 语义标签，除非模型同时显式学习 executor failure probability。

## 怎样让“调用对了的正确率”可测

对每个 current state，枚举 16 个动作的可用 outcome；对每个动作独立记录：

- candidate valid；
- requested / received / used / functional / realized；
- positive-support contribution；
- absolute material risk；
- cost；
- fallback / guard outcome。

定义满足最低质量贡献、无 material risk、功能实现、成本在冻结预算内的所有动作组成 `oracle_set(s)`。然后：

- `PM action accuracy = 1[requested_action ∈ oracle_set(s)]`；
- `policy regret = max_{a∈oracle_set} U(s,a) - U(s,requested)`；
- 若没有任何可靠 action outcome，则该 state 为 `UNRESOLVED`，不得硬贴正负标签；
- PM 选对但 generator 未用，记 Step1 correct、Step2 failure；
- PM 选错，即便 generator 偶然写出好回复，也记 Step1 wrong、system outcome separately good。

这样才真正回答“失败是谁的责任”。

## 如何处理有限语义能力

本研究不应假装一个低容量监督模型能理解全部人类复杂语义。合理边界是：

- 只声明若干可观察、可复核的 broad capabilities；
- BGE/BAAI embedding 只提供相似性、topic 与候选关系信号，不宣称完整理解；
- 每个 capability 必须在不同用户/对话中同时出现 clear-positive、clear-negative、ambiguous；
- ambiguous 不强制二分类，进入 `UNRESOLVED` 或透明规则 fallback；
- 测试“在冻结支持范围内是否学会”，外部三考卷测运输边界，而不是把所有失败都归因于语义模型。

这不是逃避语义问题，而是把研究问题限制在当前技术真正可测的范围。

## “保证能学出来”的科学含义

任何数据合同都不能在看 outcome 前数学保证论文一定过门。能够保证的是：失败会在小规模阶段被发现，而且正式实验只在以下条件全部成立后启动：

1. label validity：function/guard/judge 的硬逻辑测试全部通过；
2. causal support：每个 capability 有跨独立 clusters 的 clear-positive 与 clear-negative；
3. executor qualification：raw→realized 链闭合，fallback 原因可裁决；
4. capacity support：参数/特征数由训练折中的独立 clusters 决定；
5. learnability gate：在未参与模型选择的 grouped holdout 上，简单 head 明显优于 fold-mean 与 always-off；
6. policy gate：16 动作 oracle accuracy/regret 优于 transparent rule、fixed-high、always-off 和 cost-matched fixed；
7. 任何 head 不满足，就缩小 component claim 或 fail closed，不靠继续改门槛“及格”。

真正的根治不是承诺“无论数据是什么都能学会”，而是让训练信号在正式花费前具备：**真值可信、责任独立、正负支持充分、模型容量匹配、外层验证可复现。**

## 现在应做什么

在提出任何新版本前，只做不改变方法的根因闭环：

1. 对现有 576 groups 做 deterministic function audit：fallback 全部固定为 `NOT_USED`，检查 evidence excerpt 的 candidate/response literal binding；不调用 API。
2. 抽取分层盲审样本，分别审核 candidate relevance、raw/realized functional use、Q preference；把三项分开，不让一个总分掩盖责任。
3. 仅在 clean executor 子集上估计 semantic-value target，并与 deployment ITT 并列报告；前者用于判断数据是否可学，后者用于最终系统比较。
4. 检验哪些 broad capabilities 在现有 ESConv/EvoEmo/ES-MemEval 中确实有跨 cluster 正负支持；没有支持的能力不进入第一篇 PM claim。
5. 完成以上证据后，才决定现有 576 outputs 能保留多少、是否只需补少量 paired effects、还是必须放弃某个 head。

在这五步完成前，V5.4 draft 与 48 anchors 只保留为未授权草稿，不继续生成、不调用 API、不改正式结论。

## 与历史失败清单的对应

| 本次根因 | 已记录旧问题 | 复发形式 |
|---|---|---|
| Pilot 独立组不足 | V15-PM-25 / V15-DATA-39 / V15-MEAS-61 | 3 用户选择 5–6 维 memory head |
| Judge 缺 verified past | V15-MEAS-48 | V5.3 Q judge 再次只看 current dialogue + A/B |
| MS/ME 构念漂移 | V15-MEM-50 / V15-DATA-79 | ME 83.3% 为 context event；MS 主要为 turn observation |
| Step2 测量未闭合 | V15-ENG-25 | Q64 14 条 fallback 无 raw response，正式 effect 仍启动 |
| Rows 代替可识别对比 | V15-DATA-39 | 576 natural groups 没有 semantic high/low families |

这说明问题不是“方案还缺一段文字”，而是过去已经知道的机器门没有进入真正的生成、测量和启动顺序。
