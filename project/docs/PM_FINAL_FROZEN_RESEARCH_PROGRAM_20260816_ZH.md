# Policy Manager 第一篇论文最终冻结研究方案（2026-08-16）

状态：`ACTIVE / SINGLE SOURCE OF RESEARCH TRUTH / PAPER-1 FIRST-ORDER ROUTE`

机器可读合同：`project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`

训练合同：`project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`

> **本文件取代 2026-08-14 版本成为 Paper 1 的研究 authority。**
>
> **方法名仍为 Policy Manager（PM），不叫 MetaCom。** `Metacom5_3` 只是历史仓库名。
>
> **Generator 已在本次设计更新之前完成冻结。** 本文件不重新选择或改变 Generator；后续 effect generation、baseline、PM 与正式评测必须使用同一冻结 Generator、base prompt、mode、decoding 与 seed schedule。若 Generator 身份变化，新的 effect labels 必须全部重做。

---

## 1. Paper 1 到底研究什么

情绪支持对话中的 Strategy-RAG 与长期记忆都是可选外部资源。资源真实、相关、能够被检索到，并不意味着每一轮都值得注入；不必要的资源会增加 Generator context、成本、噪声和误用机会。

Paper 1 只回答：

> **一个低容量、可审计的 pre-injection / pre-generation Policy Manager，能否分别学习 Strategy-RAG、Profile Memory、cross-session Memory 与 Experience Memory 的 first-order marginal utility，在公认 benchmark 上保持或改善性能，同时减少不必要的资源注入和 Generator 成本？**

这是 **selective external-resource allocation** 研究，不是策略类别预测，不是端到端心理咨询模型，也不是高阶资源交互建模。

### 1.1 Paper 1 明确不主张

- 不诊断用户的“真实心理需求”或临床状态；
- 不预测 ESConv 八类 strategy category；
- 不训练直接 16-class action classifier；
- 不声称已经学习 RS×MP×MS×ME 高阶 interaction；
- 不声称完全 unseen-user 人群泛化；
- 不研究 Tokkio 多模态、记忆写回或端到端 RL；
- 不把旧自建 Quality/Function/Risk 总分作为论文主 verdict。

---

## 2. 四类资源：2026-08-16 唯一定义

| Head | Paper 1 固定定义 | Candidate layer 负责 | Step 1 PM 负责 |
|---|---|---|---|
| **RS** | ESConv train-only Strategy Bank 检索出的 Strategy-RAG card / atomic move | 找到一个合法、当前相关的 strategy candidate/bundle | 当前是否值得注入 RS |
| **MP** | **Profile Memory only**：真实、当前有效的长期 user profile facts | 找到当前用户严格可用的 profile candidate/bundle | 当前是否值得用这些 profile facts |
| **MS** | strictly-past cross-session event / session continuity memory | 找到严格过去、同用户、时间和线程正确的 MS candidate/bundle | 当前是否值得承接这些跨 session 信息 |
| **ME** | strictly-past **action → user-observed outcome** experience memory | 找到包含明确行动与用户实际观察结果的 ME candidate/bundle | 当前是否值得作有限经验类比 |

### 2.1 MP_PREFERENCE 从 Paper 1 删除

`MP_PREFERENCE`、`response_preference_history` 以及 preference-specific features 不参加 Paper 1：

- 不进入 MP training；
- 不进入 MP runtime candidate pool；
- 不进入 ES-MemEval 正式实验；
- 不进入 MP component-minus claim。

旧 synthetic assets 中的 preference 数据只保留为历史/未来工作，不得被当前代码自动并入 `MP`。

### 2.2 Candidate 可以是 bounded bundle

为兼容 ES-MemEval 的多证据任务，component candidate 不强制只能是一条 item。Candidate layer 可以按冻结的 source-specific top-k / token cap 构成一个 **bounded candidate bundle**。关键要求：

- 同一 state 的 ON/OFF pair 使用完全相同的 exact bundle；
- Typed Fixed-High、Matched-Random、Learned 使用相同 candidate machinery；
- top-k / token cap 必须在 main outcome 前冻结；
- PM 决定 component 是否打开，不负责重新挑 bundle 内 item。

---

## 3. Paper 1 选择路线 A：first-order factorized PM

### 3.1 核心定义

四个 head **不以其他三个 PM 决策作为输入**。每个 head 学习：

> 在当前 state + 当前合法 candidate 下，目标 component 自身是否具有值得注入的 first-order marginal value。

正式 effect contrast 对目标 component `c` 使用统一 canonical background：

> **其他 optional components 全部 OFF。**

即：

- RS effect：`M0+R0` vs `M0+RS`；
- MP effect：只有 MP bit 改变；RS/MS/ME 均 OFF；
- MS effect：只有 MS bit 改变；RS/MP/ME 均 OFF；
- ME effect：只有 ME bit 改变；RS/MP/MS 均 OFF。

### 3.2 为什么不采用 background-conditioned 路线 B

B 会使一个 component 的 label 取决于其他资源是否已经被正确或错误地打开，并产生 state×candidate×background 的快速组合增长与责任混淆。Paper 1 为了可识别、可审计和可控，明确不学习这种 interaction-aware value。

历史上不同 background 下 effect rate 的变化保留为 **interaction diagnostic / future work**，不再作为 Paper 1 learner 的 feature 或训练目标。

### 3.3 Runtime 仍允许 16 种组合

四个独立 head 分别输出 ON/OFF 后可以组成 `2^4=16` 种 runtime resource combination；但这些组合只是四个 first-order decisions 的合成，不代表 PM 学会了组合交互。

Paper 1 runtime：

1. source-specific eligibility；
2. 四个独立 first-order head；
3. 每头冻结 threshold；
4. 合成四 bit；
5. deterministic hard-conflict / prompt-cap projection；
6. Step 2 执行。

**不得把 `background_MP_on / background_MS_on / background_ME_on / background_RS_on` 作为 Paper-1 final head features。**

---

## 4. 固定运行链

```text
Current state
    │
    ├── Strategy candidate discovery ── RS candidate
    ├── Profile candidate discovery ─── MP_PROFILE candidate
    ├── Session/event discovery ─────── MS candidate
    └── Experience discovery ────────── ME action→outcome candidate
                         │
                         ▼
              source-specific eligibility
                         │
              ineligible ──→ deterministic OFF
                         │ eligible
                         ▼
              Step 1: four first-order heads
              RS / MP / MS / ME ON/OFF
                         │
                         ▼
              deterministic projection
                         │
                         ▼
                 Step 2 typed executor
                         │
                         ▼
                   frozen Generator
                         │
                         ▼
               official benchmark outcome
```

### 4.1 `ineligible` 不等于 learned OFF

必须区分：

- `ineligible`：candidate absent、wrong owner、future、superseded/stale、hard conflict、source construct 不成立等；规则直接 OFF，不进入 classifier 负例；
- `eligible + nonpositive_off`：candidate 正确、合法，但实测无边际价值/更差/等效而额外增加成本；这是 PM 最重要的 OFF supervision；
- `eligible + positive_open`：实测 ON 有 material benefit 且没有 material violation；
- `eligible + unknown`：treatment 不稳定、未有效执行、测量不可裁定；训练排除。

---

## 5. 四头 source-specific eligibility

### 5.1 RS

Hard eligibility 至少要求：

- ordinary ESC scope；
- candidate 来自冻结 ESConv-train-only Strategy Bank；
- candidate query/current state 对齐；
- candidate atomic move 与当前明确 boundary 兼容；
- no structural hard exclusion；
- 没有明确重复最近已经执行的同一 atomic move。

`listen-only` 不等于整个 RS hard-OFF；它只 hard-block 不兼容的 Suggestion / probing Question 等 move，Reflection/Affirmation 等合法 move仍可成为 candidate。

### 5.2 MP = Profile only

Hard eligibility 至少要求：

- same owner；
- profile fact 有可追溯 source；
- 当前版本 active；
- 未被 supersede；
- strict-past / target 时点可见；
- 不与 visible current update 冲突；
- 不把当前已经明确给出的事实伪装成新增记忆；
- 敏感 profile 在没有当前明确相关性时不得强行暴露；
- `MP_PREFERENCE` 永久排除于 Paper 1。

### 5.3 MS

Hard eligibility 至少要求：

- same owner；
- strictly prior session/event；
- current/future session 禁止；
- **last-user-message/current-message fallback 禁止冒充 MS**；
- 时间、实体、thread 正确；
- visible current update 优先于旧状态；
- 不允许 wrong-person / unsupported inference。

当前 session 已经完整覆盖的 past information 一般属于“无增量价值”机会信号，而不是 material safety violation；若 candidate 本身仍合法，可进入 learned OFF 对照。

### 5.4 ME

Hard eligibility 比 MS 更严格：

- same owner；
- strictly past；
- 有明确 action / coping attempt / support choice；
- 有**用户实际观察到的 outcome**；
- outcome 不能由系统事后推测；
- action 与 outcome lineage 可追溯；
- unresolved/context-only event 不能伪装成 reusable ME；
- 不与当前 visible update 冲突；
- 高风险/医疗/法律等经验不能普通迁移；
- Step 2 只允许有限类比，禁止“过去有效→现在一定有效”。

---

## 6. 学习方法与 outcome-blind features

Primary learner 仍为：

> **4 个 standardized L2-regularized logistic regression binary heads**

不因为 Paper-1 采用路线 A 而改用大模型 policy。

Final feature contract 见训练合同。总原则：

- 每头只看 current state + exact candidate 的 outcome-blind observable descriptors；
- 不看其他 component ON/OFF bits；
- 不看 response、judge、gold action、external outcome、split、dataset identity、opaque ID；
- 尽量保持每头 4–6 个有效标量/低基数特征；
- zero-variance feature 在 fit 前删除并记录；
- feature schema 在正式 effect outcomes 前冻结。

---

## 7. 训练数据：当前状态与正式要求

### 7.1 当前已有资产不是 final effect-training dataset

现有仓库中的 longitudinal catalog、profile facts、MS/ME examples、旧 paired outcomes 仍有开发价值，但**不能整体直接视为 Paper-1 final training data**。

特别地：

- tracked formal longitudinal intake 当前只覆盖少量用户，不能等同于曾规划的完整 80-user formal corpus；
- 其中 historical preference 数据必须从 Paper-1 MP 中排除；
- 旧 256 effect labels 只作为 learnability / heterogeneity diagnostic；
- 旧 MS effect treatment 已被 root-cause audit 判定不符合当前 strictly-prior MS construct，正式训练必须重做；
- Generator 已重新冻结，因此依赖旧 Generator 的 effect labels 不自动迁移成 final gold。

### 7.2 正式数据生成前必须完成 repeated-effect qualification

在全量 effect generation 前，先验证“一次 matched ON/OFF pair 能否作为 expected marginal effect 的可接受 noisy proxy”。

冻结 qualification：

- 每 head 8 个 eligible states，共 32 states；
- 每 state 独立生成 3 组 ON/OFF pairs；
- primary 看至少 2/3 non-uncertain direction 一致；
- state-level reproducible-direction rate 目标 ≥70%；
- uncertain fraction ≤10%；
- 固定 overlap 由第二 reviewer 独立复核，exact agreement 目标 ≥75%。

若 qualification 不通过：禁止把 single-pair winner 当 hard training label；改用 repeated/soft effect target 或收窄 claim。

### 7.3 正式 effect row 的最小结构

每个 effect row/group 必须记录：

- `effect_group_id`；
- `component`；
- `user_id` / fact-event cluster（grouping only，禁止模型读取）；
- `task_type`（适用时，runtime 可见）；
- current state / visible context；
- exact candidate/bundle identity 与 lineage（audit only）；
- eligibility status + hard reasons；
- frozen model features；
- `canonical_background = all_other_optional_components_off`；
- ON/OFF treatment；
- generator / prompt / executor / seed hashes；
- anonymous A/B responses；
- treatment execution / uptake trace；
- training-only outcome verdict；
- `positive_open / nonpositive_off / unknown`；
- input/resource/output tokens 与 latency。

`ineligible` rows 可以保留用于真实部署分布审计，但不进入 learned OFF 训练。

---

## 8. 数据来源

### 8.1 RQ1 / RS

- ESConv **train-only**：Strategy Bank、Retriever、RS effect training；
- ESConv held-out：in-domain diagnostic，不作为 PM final verdict；
- ESC-Eval：RQ0 与 RQ1 最终外部 ESC benchmark。

### 8.2 RQ2 / MP-MS-ME

- ES-MemEval / EvoEmo strict-past histories：正式 long-term memory candidate source；
- evaluation target/gold/future session 永远不进入 runtime PM；
- 允许 same-user longitudinal adaptation，但 evaluation target outcome 与同 fact/event cluster 必须 fold-isolated；
- MP 只使用 Profile Memory；
- ME 若在自然 benchmark history 中没有足够 eligible action→observed-outcome states，则报告 `not identifiable on this benchmark`，禁止生成 synthetic gold 来救 head。

旧 synthetic longitudinal catalog 只用于 compiler/eligibility qualification、edge-case testing、历史诊断或实现复用，不自动替代公开 benchmark 的正式证据。

---

## 9. Evaluation：只用公认 benchmark 判断主要能力

### 9.1 RQ1：ESC-Eval

正式 arms：

1. `R0 / No Strategy-RAG`
2. `RS Fixed-High`
3. `RS Matched-Random`
4. `Learned RS-PM`

所有 arms 同 Generator、同 base prompt、同 role card、同 Retriever、同 candidate identity、同 seed schedule、同 scorer；唯一核心差异是 RS allocation policy。

全部报告 ESC-Eval 官方七维：

- Fluency
- Expression
- Empathy
- Information
- Skillful
- Humanoid
- Overall

不把 ESConv strategy ACC、BLEU、ROUGE 作为 PM primary verdict；它们只能做 Retriever / in-domain diagnostics。

### 9.2 RQ2：ES-MemEval

正式 arms：

1. `No Memory`
2. `Full History`
3. `Official RAG Top-4`
4. `Typed Fixed-High`
5. `Typed Matched-Random`
6. `Learned Typed-Memory PM`

其中：

- `Typed Fixed-High` 与 Learned 使用完全相同 MP/MS/ME candidate machinery，只是所有 eligible types 都开；
- `Typed Matched-Random` 按 component 匹配 Learned 的 ON rate / injected-token budget，但随机决定 eligible states 的 opening location；
- RS 在 ES-MemEval official main analysis 固定，不与 memory 同时变化。

### 9.3 ES-MemEval 指标解释冻结，但不事后挑“赢的一个”

Paper 1 不自己造跨任务总分，也不在结果出来后把“最有利指标”宣布为唯一 primary。

提前冻结各官方 metric family 的解释：

**QA**
- Final answer quality：F1 / BERTScore / LLM-as-Judge；
- Retrieval diagnostics：Recall@k / nDCG@k。

**Summarization**
- Reference overlap：ROUGE-1/2/L；
- Historical event coverage：Event Precision / Recall / F1；
- Semantic faithfulness：official LLM Score。

**Dialogue Generation**
- Memory utilization：Observation Recall / Weighted Score；
- Long-term support profile：LT-Memory / Personalization / Emotional Support。

所有官方指标透明报告。结果出来后可以解释不同指标的含义和 trade-off，但不得 post-hoc 隐藏不利指标或重新定义成功标准。

---

## 10. Baseline comparison 什么才叫有意义

### 10.1 同栈公平是硬条件

Formal causal comparison 必须保持：

- frozen Generator；
- same task prompt / Step 2 compiler；
- same candidate machinery；
- same token cap；
- same role-card/item × seed schedule；
- same official scorer；
- main outcomes 前冻结 threshold、random schedule、sample subset。

Published historical scores 只是范围参考，不是 PM 因果 baseline。

### 10.2 RQ1

- vs R0：Learned 不得 material overall degradation；selected-ON slice 应有正向 Strategy-RAG uplift；
- vs Fixed-High：official ESC performance 非劣，同时 `generator_input_tokens` 至少下降 10% 才计 material efficiency gain；
- vs Matched-Random：同使用率/成本下 Learned 出现正向 paired effect，证明 opening location 有信息。

### 10.3 RQ2

- vs No Memory：说明长期记忆总体是否有价值；
- vs Full History / Official RAG：与公认高资源 / 固定 RAG 条件定位；
- vs Typed Fixed-High：隔离 typed representation 与 selective gating；
- vs Typed Matched-Random：证明不是“少用 memory”本身，而是 state-dependent selection。

不允许用 Cost 抵消 material quality failure 或 pipeline-invalid integrity failure。

---

## 11. Memory component-minus ablation

主 Learned PM 冻结后，不重训，运行：

- `Learned - MP`
- `Learned - MS`
- `Learned - ME`

一个 memory head 被计为 `useful` 需要：

- eligible slice 在 outcome 前冻结；
- full-minus-head 相对 full Learned 在至少一个与该资源能力直接相关的官方 metric family 出现正向 paired effect；
- aggregate direction 为正；
- 正方向跨至少两个 user / fact-event cluster；
- 全部负例与 cluster uncertainty 透明报告。

Paper 1 typed-memory 机制主张仍要求 MP/MS/ME 至少两个获得可复现支持；若只有一个，必须降级 claim。

---

## 12. Cost 与 integrity

Primary cost：

- `generator_input_tokens`
- `resource_injected_tokens`

同时记录：output/total tokens、retrieval/embedding calls、retrieval/generator/end-to-end latency、p95、retry、可恢复 API cost。

只保留 minimal integrity audit：

- wrong owner / cross-user retrieval；
- future leakage；
- fabricated/unsupported personal history；
- stale/conflicting memory misuse；
- explicit boundary violation；
- excessive directiveness；
- internal scaffold/resource-label exposure。

不合成 Risk 总分，不与 official quality 加权。

---

## 13. 训练 readiness：现在可以推进什么

Generator 已冻结，下一步不是再改 RQ，而是立即推进：

1. 代码迁移到本 authority：MP_PROFILE only，删除 final head 的 background bits；
2. 跑 ES-MemEval/EvoEmo 18-user natural-history coverage audit，统计 MP/MS/ME eligible states 与 ME action→observed-outcome coverage；
3. 冻结 source-specific candidate bundle top-k/token cap；
4. 完成 32-state repeated-effect qualification；
5. qualification 通过后生成 final matched-effect training data；
6. 训练四个 L2 first-order heads；
7. 冻结 thresholds / same-stack baseline / matched-random schedules；
8. RQ1 ESC-Eval；
9. RQ2 ES-MemEval；
10. component-minus；
11. official outcome + Cost + cluster uncertainty + integrity report。

---

## 14. Stop rules

- MP_PREFERENCE 混入 Paper 1 → pipeline invalid，修复后重跑；
- final head 读取其他 component background bits → 不符合路线 A，修复后重跑；
- 旧 MS fallback treatment 被复用作 formal label → invalid；
- repeated-effect qualification 不通过 → single-pair hard label 禁止；
- 某 head 自然 eligible evidence 不足 → `not identifiable`，不 synthetic rescue；
- Learned ≈ Matched-Random → 没有 selector evidence，不能只拿成本低宣称 learned routing 成功；
- Learned < Fixed-High 且无预注册 efficiency trade-off → RQ 失败，如实报告；
- main outcomes 后改 Generator/prompt/retriever/feature/sample/threshold → 只能 exploratory。

---

## 15. Paper 1 最终一句话

> **Policy Manager 在一个冻结 Generator 之前，对 Strategy-RAG、Profile Memory、cross-session Memory 与 Experience Memory 分别学习 first-order state×candidate marginal utility；四个独立决定组合成资源配置，但 Paper 1 不建模资源间高阶交互。Strategy 侧由 ESConv train-only 提供资源与监督、ESC-Eval 提供最终多轮 ESC 评价；Memory 侧由 ES-MemEval/EvoEmo strict-past history 提供资源，并使用 ES-MemEval 官方 QA/Summary/DG 指标评价。PM 的价值由 same-stack Fixed/Random/official baselines 与真实 Cost 共同判断，而不是由自建标签本身宣布。**
