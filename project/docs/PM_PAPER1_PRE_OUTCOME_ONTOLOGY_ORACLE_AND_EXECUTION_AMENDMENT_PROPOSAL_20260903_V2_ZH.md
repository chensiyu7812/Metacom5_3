# Paper-1：Ontology、训练—考试对齐、Pairwise Effect Oracle 与执行修订提案 v2

> `HISTORICAL APPROVED-IN-PRINCIPLE PROPOSAL — SUPERSEDED BY ACTIVE V2.1`
>
> 日期：2026-09-03
> 状态：`SUPERSEDED BY PM_PAPER1_V2_1_CONSISTENCY_AMENDMENT_20260903_ZH.md`
> 本文件只提出研究修订。它不修改 active authority，不打开任何 outcome lock，不授权 API/GPU outcome 调用，也不授权正式 PM training。

## 1. 本次修订要解决的不是新“门”，而是可识别性

Paper-1 目前有两个不同问题：

1. 旧 MP/MS/ME ontology 不能稳定表达 ES-MemEval 的 profile、event timeline 与 raw session；
2. 现有实现虽然保留 `ON better / OFF better / equivalent / uncertain / invalid`，但没有证明这些标签由能分辨 ON/OFF 条件效用的老师产生。

第二个问题不能用更多 compiler precision gate 解决。它要求事先说明：

- “正确 ON/OFF”相对于什么目标成立；
- 判卷老师看见什么、依据什么 rubric、看不见什么；
- official final scorer 与 training-effect teacher 的关系；
- evaluator disagreement、等价和动态轨迹如何处理；
- PM 学到正确决策与完整系统获得收益分别如何证明。

本提案不保证阳性结果。它的目标是在不读取 confirmatory outcome、不泄漏 gold/future、不按有利结果挑 judge/metric 的前提下，最大化训练信号与最终考试的构念一致性和检测功效。

## 2. v1 中保留的研究修订

如获批准，继续采用：

- `MP = current Profile view`：稳定、slot-like 的当前 profile facts；
- `ME = atomic Event/Experience timeline`：发生过的事件、变化、阶段性状态与 action→outcome subtype；
- `MS = full strictly-past raw SessionDocument`：完整历史 session，不是另行生成的 session summary；
- 同一 source span 可合法投影到多个 view，但必须保存统一 lineage；
- user-anchored third-party facts 可以进入相应 view；
- 展示名由 Typed Memory 改为 Multi-View Memory，machine enum 可为兼容保留；
- RQ2 所有主 arms 中 RS 固定为 OFF；
- ESC-RANK 继续是 RQ1 official final scorer，alternative family 只能做 measurement sensitivity；
- v7/v8/v9 precision 资产仅为历史工程 regression，不再承担研究有效性解锁；
- semantic uptake、compiler percentage、calibration score 不作为经验性 PASS gate；
- official ES-MemEval QA/Summary/DG metric families 分任务报告，不构造跨任务 composite。

MP 边界进一步收紧：临时情绪、短期压力、一次性处境和时变关系状态属于 ME timeline，不因其“现在仍成立”就全部吞入 MP。MP 只保留身份、稳定关系/偏好/约束等可维护的 current slots。

## 3. v1 必须纠正的条款

### 3.1 operating point

不得恢复固定 `0.5` primary。继承 2026-08-31 active amendment：

- `0.5`、always-ON、always-OFF 是 mandatory transparent references；
- RQ1 primary operating point 只由 grouped OOF effect evidence 选择；
- RQ2 每个 outer fold 的 head×task operating point 只由 outer-training / inner-OOF evidence 选择；
- 选择规则仍为 quality-first one-SE admissible set，再取 minimum mean Generator-input tokens，其后依次 lower ON rate、higher threshold、canonical order；
- confirmatory 和 held-out outer-target outcomes 永不参与 threshold 选择。

### 3.2 Matched-Random

Matched-Random 只随机 eligible states 的 opening location：

- 每个 state 保持自己的 exact frozen retrieved bundle；
- 不跨 state 交换 candidate，不把 A 的 memory 给 B；
- 在 head×task×fold 内匹配 realized ON count，并按预冻结 token bins 匹配打开集合的资源长度分布；
- 无法 exact match 时，报告剩余 imbalance 并用预冻结 schedule，不在 outcome 后改 bins 或换 seed。

### 3.3 联合 packing

在 MP/ME/MS 联合部署前冻结 outcome-blind global context policy：

- 总资源 token budget；
- 每 view 的 canonical order；
- MS whole-session packing；
- 同 lineage 重复投影的 deterministic collision 标记；
- overflow 时的固定裁剪优先级；
- treatment trace 中记录 requested、delivered、dropped 与原因。

factorial interaction audit 只作诊断，不用于 outcome 后调 policy。若 interaction 很强，论文收缩为“first-order isolated selection signals / frozen-system value”，不声称学到最优联合 memory policy。

### 3.4 factuality audit

保留一次性、预冻结、分层的 resource factuality/integrity audit，错误类型至少包括 wrong-owner、future leakage、gold leakage、fabrication、temporal inversion、duplicate projection 与 source mismatch。

- 机械错误仍可 hard-invalid；
- semantic non-use/misuse/harm 是有效 realized effect；
- formal effects 前若发现系统性实现 bug，只允许一次适用于全 catalog 的 general repair，然后按相同抽样规则重审；
- 不反复更换 DEV 样本或 percentage threshold 直到“通过”。

### 3.5 amount 与 held-out dose response

执行顺序为 `Amount → Effect → Selector → Confirmatory`。`k*` 只由 calibration / outer-training evidence 选择。

如果论文要写“more is not always better”或“diminishing returns”，另行预注册 held-out dose-response secondary slice；它不反向改变 `k*`。若 held-out 曲线不支持饱和/下降，只保留“calibrated sufficient amount”与实际 cost 曲线，不作更强主张。

## 4. “正确 ON/OFF”的操作性定义

不存在脱离目标函数的绝对“正确 ON/OFF”。本研究使用以下可检验定义：

> 对冻结的 state、candidate bundle、Generator、prompt、decoding 与输出限制，只改变该 head 是否交付资源；若 ON 的 realized response 在预声明的 task-specific official outcome hierarchy 上有可分辨的正增益，则为 `oracle-beneficial ON`。若 ON 更差或不可分辨地等价，则 deployment target 为 OFF。冲突或老师不能分辨时为 uncertain，不强制制造 0/1。

因此：

- `ON better → target 1`；
- `OFF better → target 0`；
- `equivalent → target 0`，含义是“无可分辨增益，部署时因成本选择不打开”，不是声称资源错误；
- `uncertain / invalid` 不进入 likelihood；
- Cost 不进入 label 或 loss，只用于 OOF operating-point 选择和最终效率报告；
- label 是冻结 stack 下的局部 counterfactual effect，不是资源相关性标签，也不是全局最优 policy ground truth。

论文中使用 `oracle-beneficial / oracle-nonbeneficial`，避免把测量构念写成形而上的绝对真值。

## 5. Training–Evaluation Alignment Contract

每个 effect row 必须绑定：

- 同一 task target、current visible state 与 strict-past boundary；
- 同一 exact eligible bundle、retriever、renderer、amount 与 token accounting；
- 同一 frozen Generator/base prompt/decoding/output normalization；
- OFF 与 ON 只差该 head treatment delivery，其他 optional heads OFF；
- 同一 official benchmark scorer surface 与预声明 task-specific hierarchy；
- target/evidence lineage 与 outer fold 隔离；
- gold/reference/official observation 只在 outcome scoring 后使用，绝不进入 PM feature、retrieval query、candidate construction 或 runtime prompt（除非 official generation protocol本来就允许）；
- official capability labels只用于最终分层报告，不用于 PM feature 或 outcome-blind curriculum 选择。

训练 curriculum 可以按 runtime-visible proxy strata 丰富：candidate age、current-context redundancy、entity/thread overlap、resource length、stable-vs-transient field、明确记忆请求、历史内容已在当前输入重复、以及 valid-but-low-overlap resource。不能按 effect outcome 补正例，也不能用 gold capability label制造看起来平衡的数据。

## 6. 判卷老师怎样“知道标准”

### 6.1 两种老师必须分开

1. `Resource correctness auditor`：检查候选本身是否真实、strict-past、owner 正确。它可以看到 source lineage，但不判 ON 是否值得。
2. `Realized-effect judge`：比较 ON/OFF 产生的匿名 responses。它不看候选 bundle 或 PM 决策，以免“看到用了记忆”本身被当作更好；它只看该 official task 允许评价器看到的 context/reference。

### 6.2 统一盲评接口

机器和人类 pairwise judge 均接收：

- task-specific context；
-匿名 `Response A / Response B`；
- exact task rubric；
- official protocol允许的 gold/reference/observation；
- 五类输出：`A better / B better / equivalent / uncertain / mechanically invalid`；
- evidence-based short rationale 与 rubric dimension；
-禁止猜测哪边有 memory、哪边是 Ours/PM、哪边 ON。

正式 pair 的 A/B 顺序由 freeze hash 决定。机器 qualification 对同一 pair 做 A/B 与 B/A；顺序反转改变实质 verdict 时记为 order-unstable，而不是多数投票硬凑标签。

### 6.3 task-specific 可见性

| Task | effect judge 必须看到 | 不应看到 |
|---|---|---|
| ESC response | 当前对话 prefix、两个候选 supporter response、ESC-Eval rubric | resource bundle、arm、ON/OFF、PM score |
| QA | question、gold answer、两个答案、官方 0/1/2 correctness rubric | evidence passage若 official scorer 不使用；PM feature/arm |
| Summary | summary request、reference summary、一个共同冻结的 reference-event inventory、两个 summaries | 每个 arm 分别重抽的 reference events、resource bundle |
| DG local | 固定 prefix、当前 seeker utterance、scenario-related evaluator-only observations、两个 next responses；分别执行 relevance/use 与 support-quality rubric | PM decision、resource bundle、未来 seeker continuation |
| DG end-to-end | 完整生成 dialogue 与 official scenario metadata | paired local oracle label不能替代完整 official scorer |

给老师 rubric 不是额外发明 benchmark：QA、Summary、DG 的基础 rubric 来自 pinned ES-MemEval 实现；ESC 来自 pinned ESC-Eval 七维 rubric。项目新增的只有“怎样把两份匿名输出转成训练 effect 类别”的 overlay，必须公开、冻结并与 official raw scores一同保存。

## 7. task-specific effect coding v2

现有 `effect_coding.py` 的“所有官方指标等权、任意非零差值、Pareto 同向才判胜”提案应撤回。它与 active amount authority 的 primary/guard/explanatory 层级冲突，也会把浮点微差当实质效果。

### 7.1 ESC response

Raw surface 保留七维 ESC-RANK 0–4 absolute scores。训练 direction 使用：

1. `Overall` 是 primary anchor，至少一个 ordinal step 才能单独构成可分辨方向；
2. `Empathy` 与 `Information` 是 harm guards；primary 改善但任一 guard 反向下降时记 uncertain；
3. `Overall` 相等时，使用经人类 reference 校准的 ESC-rubric pairwise teacher 解决可分辨 preference；
4. pairwise teacher 与 non-tied Overall 相反时记 uncertain；
5. pairwise teacher 稳定判 equivalent，且无 guard 冲突时记 equivalent；
6. 其余五维完整报告并用于 error/sensitivity，不做 outcome 后择优。

ESC-RANK 仍是 final official scorer；pairwise teacher 只产生 training/local-audit effect，不替换 final benchmark。

### 7.2 QA

1. official GPT-4o 0/1/2 semantic correctness 是 primary anchor；
2. question+gold 的 blinded pairwise correctness teacher 用于解决 primary tie、检查明显的方向冲突和等价；
3. F1/BERTScore 原值完整保存，作为辅助/tie evidence 与 final reporting，不允许一个极小连续差值否决明确的 semantic-correctness 改善；
4. abstention 项对 `unknown` 的正确性按 gold 和 official rubric 判，gold 只在 scorer 内可见；
5. primary 与 pairwise teacher 实质冲突为 uncertain。

### 7.3 Summary

1. 对同一 target 只生成并冻结一次 reference-event inventory；ON/OFF 共用它，避免 arm-specific reference extraction noise；
2. Event F1 是 primary；event precision/recall 保留；
3. official 0–5 LLM Score 是 semantic/faithfulness guard 与 tie evidence；
4. ROUGE-1/2/L 是 explanatory，不进入 direction veto；
5. Event F1 与 LLM/pairwise semantic judgement相反时记 uncertain；Event F1 tie 时只有 LLM 与 pairwise teacher 同向才判 direction；其余 equivalent/uncertain。

common reference-event inventory 是项目的 paired-effect measurement overlay，final benchmark 仍另行执行 pinned official scoring，并披露二者区别。

### 7.4 Dialogue Generation

官方实现实际使用 Mistral‑24B 对每轮 observation 做 1/2/3 relevance 与 boolean usage，映射到论文的 0/0.5/1；GPT‑4o 对完整对话给 Memory、Personalization、Emotional Support 1–5。

局部 effect coding：

1. 固定 prefix/current seeker utterance，两个 next responses共享相同 observation relevance；
2. relevant-observation utilization delta 是 memory-specific primary；
3. blinded pairwise teacher检查 memory correctness、personalization 与 emotional-support non-harm；
4. utilization 改善且 pairwise judge不判更差 → ON better；utilization下降或引入错误历史 → OFF better；
5. utilization 相同但 pairwise teacher稳定识别出个性化/支持质量增益或损害时可判 direction；否则 equivalent；
6. observation 与 pairwise judgement冲突、order-unstable 或 hallucination status不清时为 uncertain。

完整 DG scenario 的 official Weighted Score、Observation Recall 与三项 1–5 rating 才是 final end-to-end evidence。局部 label 不能被称为全局 sequential-policy oracle。

## 8. Pairwise teacher human-reference 计划

新建固定 96-pair measurement set，不复用此前 24 条 ESC absolute-score 样本：

- ESC 32；QA 16；Summary 16；DG 32；
- 按 task、resource head、candidate age/redundancy/length、当前显式记忆请求、valid-low-overlap、边界型 observable strata 预冻结抽样；
- 不看 ON/OFF outcome 抽样，不按 official capability gold label抽样；
- 两位人类独立盲评；分歧保留，并由第三位或预声明 consensus procedure adjudicate；
- 人评界面展示本文件第 6 节规定的 task rubric 和输入；20% 随机 pair 用反序 duplicate 测位置稳定性；
- human uncertain 不强迫 adjudicate 成 A/B。

候选 pairwise teachers 的身份、prompt、parser、temperature、返回模型 identity 和最大费用在任何 pair outcome 前冻结。候选可以包含现有 Claude/Gemini family 与 official-score-derived decision，但不得按“谁产生更多 ON”或“谁让 PM 最好”选择。

选择层级预先固定为：

1. human decisive/equivalent macro agreement（报告 clustered CI 与完整 confusion matrix）；
2. pair-order stability；
3. equivalent recall 与 arm-position bias；
4. parse/operational reliability；
5. cost。

这是 measurement model selection，不设新的研究 PASS/FAIL 百分比。若所有 candidate 对某 task 都不可靠：

- 不阻塞整个 Paper-1；
- 该 task 只用 official primary anchor产生可分辨 labels；
- tied/conflicted cases 保留 uncertain；
- 缩小相应 head/task 的“decision correctness”主张，不换到能制造更多正例的 judge。

## 9. 重复生成与 evaluator noise：必须分开

当前 Generator 是 temperature=0、provider seed=null 的冻结 stack。对完全相同 prompt 重跑得到相同文本时，这些不是独立 effect observations，不能把三个相同输出当作 `n=3` binomial evidence。

本提案修订旧 repeated-effect 解释：

- primary effect unit 是独立 state/group，不是同 prompt 的伪重复；
- 每个 state 生成一个 identity-matched deterministic ON/OFF pair；
- transport retry 只恢复同一 call，不计新 replicate；
- 若 backend 仍出现多个 unique outputs，全部保存作 robustness/measurement variance，但不自动当独立 state；
- scorer repeat 只在固定 qualification sample 上估计 stochastic judge stability；deterministic ESC-RANK 与 deterministic lexical metrics不做无意义重复；
- 不采用 `3/3`、`2/3` 之类规则来制造 hard labels。

这会 scoped override 旧 authority 中“可用 repeats进入 binomial likelihood”的默认执行，原因是冻结生成 stack下同 prompt repeats 不满足独立性。若研究者希望真正估计生成随机性，必须另行授权一个预冻结 stochastic Generator protocol，并重做与 final stack 的对齐论证；本 v2 不推荐该扩张。

## 10. 怎样证明 PM 学会了对的 ON 和 OFF

需要两个不同层次的证据，不能互相替代。

### 10.1 held-out local decision correctness

第一层使用 grouped OOF / outer-fold-held-out effect rows：

- PM 对从未用于该 fold fitting 的 state 给出 probability 与 frozen decision；
- paired oracle 已由同一 target 的 ON/OFF counterfactual产生，但该 row 不参与本 fold训练；
- 报告 correct-ON recall、correct-OFF specificity、unnecessary-open、missed-benefit、balanced decision accuracy、Brier、log loss、calibration curve；
- equivalent 单列，并在 deployment decision中算 nonbeneficial OFF；uncertain/invalid 不进入 accuracy 分母但完整报告比例与原因；
- 按 head×task 报告，不做跨任务 composite。

另预注册一个不参与 amount/threshold/model choice 的 confirmatory local-audit slice。PM decision先 sealed，再生成未选 arm counterfactual。该 slice 只验证局部选择机制，不回流训练或 threshold。

### 10.2 end-to-end selector/system value

第二层是 final benchmark：

- Learned vs Matched-Random，在相同 realized ON count 与匹配 token distribution 下检验 opening location 是否含 state-dependent information；
- Learned vs Fixed-High 同时报告 official quality 与 Cost，检验是否以更少资源保留/提升能力；
- Learned vs No-Memory、Full-History、official RAG Top-4 给出方法定位；
- RQ1 用 official ESC-RANK；RQ2 用 official QA/Summary/DG families；
- 所有差异报告 clustered uncertainty，不转成自建 PASS/FAIL。

对 RQ1 ESC 互动和 RQ2 DG，local fixed-prefix decision correctness 是 myopic conditional effect；PM 的响应会改变后续 seeker trajectory，因此不能把 local audit 的错误率称为全局 policy regret。全局价值只由完整交互 arms 的随机化/配对比较识别。

只有同时看到：

1. held-out local decision metrics 显示 PM 对 oracle-beneficial 与 nonbeneficial states有区分；
2. Learned 在 matched exposure 下优于 Matched-Random；
3. end-to-end official outcomes 与 cost支持相应对照；

论文才可写“PM 学到了何时打开”。若只满足其中一部分，按证据收缩为“OOF effect prediction”“cost-aware exposure reduction”或“system-level improvement”，不越级解释。

## 11. 仍需防止的相邻混淆

- `resource correct` 不等于 `ON beneficial`：真实但冗余/陈旧/当前不需要的资源是重要负例；
- `ineligible` 是 deterministic OFF，不是 learned negative；
- `equivalent` 是无可分辨增益，不是证明两输出字面相同；
- evaluator noise floor 只能告诉我们老师能否分辨，不能证明 deterministic F1 的任意 epsilon 都有语义意义；因此连续辅助指标不单独决定 label；
- gold/reference/observations 可以教 outcome scorer，但不能成为 PM 输入；
- DG observation utilization可能奖励生硬提及，必须由 memory correctness/support non-harm检查；
- same-source MP/ME/MS 投影产生的 redundancy 属于联合系统问题，不能被 isolated head effect掩盖；
- public ES-MemEval v1.0.0-1427 与论文 1209 QA 的版本差异继续披露；本研究是 public-version within-benchmark cross-fitted evidence，不声称 untouched external generalization；
- EvoEmo 是 18 个 virtual users 的 synthetic/curated benchmark，不外推真实临床效果。

## 12. 获批后的完整执行清单

### A. authority 与零 outcome 实现

1. 将本 v2 转为 machine-readable active amendment，并更新 master register、AGENTS precedence 与 lock prerequisites。
2. 重建 MP/ME/MS contracts/compiler/runtime，归档 v7/v8/v9 active references。
3. 修订 official scorer surface audit，撤回 unweighted no-margin Pareto overlay。
4. 新建并冻结：
   - `paper1_training_evaluation_alignment_contract_v1.json`；
   - `paper1_pairwise_effect_oracle_contract_v1.json`；
   - `paper1_pairwise_teacher_qualification_plan_v1.json`；
   - `paper1_task_effect_coding_v1.json`；
   - `paper1_decision_correctness_evaluation_v1.json`。
5. 冻结 global packing/budget/collision/overflow、matched-random、Generator/Step2、folds 与 cost ledger。

### B. 一次性质量与 measurement work

6. 完成 fixed-sample resource factuality/integrity audit；仅在系统性 bug 时做一次 general repair。
7. 对 401 sessions 重建候选、strict-past pools、coverage 与 token census。
8. materialize amount grids；在授权 calibration evidence上选择 `k*`，并另冻 held-out dose-response slice。
9. 生成 96-pair human reference UI/key；完成人评与预冻结 candidate pairwise teacher evaluation。
10. 冻结每 task 的 teacher identity、prompt/parser、reference-event inventory规则与 scorer snapshot disclosure。

### C. effect、PM 与 formal evaluation

11. 按独立 state 生成 deterministic ON/OFF effect pairs；不做伪重复。
12. 产生五类 raw effect labels，保留 raw official scores、teacher verdict、order stability 与 disagreement。
13. 训练四个 standardized L2 heads，产生 grouped/outer-fold OOF probabilities。
14. 按 2026-08-31 规则选择 operating points；冻结 PM checkpoints、thresholds 与 matched-random schedules。
15. sealed local decision-correctness audit；不将结果回流模型。
16. 打开 confirmatory locks 后跑 RQ1/RQ2 official end-to-end arms、component-minus system ablations 与预注册 dose-response secondary。
17. 按 task/head 报告 official quality、decision correctness、Cost、coverage、uncertainty 与 failures。

此顺序中只有机械 integrity failure 会阻止相应 call。人机 judge agreement、label prevalence、PM accuracy 和 effect size都是结果，不再变成不断回修的经验性硬门。

## 13. 对既有结果/代码的影响

### 必须失效或重建

- v1 所列全部旧 ontology-derived MP/MS/ME catalogs、amount/effect/features/checkpoints/schedules；
- `effect_coding.py` 当前 unweighted exact-difference Pareto direction 及相应 tests；
- 未绑定 task-specific teacher 的 `blind_pairwise_verdict`；
- arm-specific Summary reference-event extraction用于 paired label 的做法；
- 将相同 deterministic repeats 当作独立 binomial evidence的 effect execution；
- 任何把 local DG/ESC next-response oracle解释成 global optimal policy 的文案。

### 保留

- public source/split/strict-past lineage基础设施；
- frozen Generator identity（但 repeat interpretation修订）；
- ESC-RANK official parser/runtime/human-reference closeout；
- official ES-MemEval metric implementation与 pinned upstream identity；
- BGE-M3、official RAG Top-4、RS catalog与 treatment-delivery traces中不依赖旧 ontology 的部分；
- 8/31 operating-point amendment。

当前 formal outcome=0、formal PM training=0，因此本修订不删除已观察的 confirmatory结果，也不是按结果调 evaluator。

## 14. 对论文主张的影响

核心 RQ 不变，但主张被更精确地分层：

- `Amount claim`：资源量在 calibration中被选择；只有 held-out dose-response支持时才写 diminishing returns / non-monotonicity。
- `Effect-prediction claim`：PM 能在 grouped/outer-fold-held-out states上预测 oracle-beneficial effect。
- `Selector claim`：Learned 优于 matched-exposure Random 才证明 opening location有信息。
- `System claim`：official end-to-end benchmark对照支持真实系统价值。
- `Global-policy claim`：本研究不声称学习交互式多轮任务的全局最优策略。

如果某 task 的 pairwise teacher或 local effect不可可靠测量，收缩该 task 的 effect/decision claim，但仍可保留 official end-to-end system comparison。

## 15. 需要研究者明确批准的 scoped overrides

批准本 v2 即批准：

1. v1 ontology/Multi-View/RS=OFF/RQ2 baseline命名与历史资产清退条款；
2. 以本文件第 3 节纠正 v1 的固定 0.5、Matched-Random、packing、audit与 dose-response条款；
3. 新增 Training–Evaluation Alignment、Pairwise Effect Oracle、人类 pairwise reference 与 Decision-Correctness Audit；
4. 用第 7 节 official-anchor hierarchy替换当前 unweighted Pareto effect coding；
5. 用独立-state deterministic pairs替换相同 prompt repeats的 binomial interpretation；
6. local decision correctness 与 end-to-end system value分开解释；
7. 创建第 12 节 machine artifacts并据此修改正式代码；
8. outcome locks在所有预调用 identity/contract冻结完成前继续 CLOSED。

未经明确批准，只允许继续只读审计、完善本提案和准备不包含 outcome 的 fixture；不得激活上述修订。
