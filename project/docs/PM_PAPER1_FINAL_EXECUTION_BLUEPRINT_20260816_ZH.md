# Policy Manager Paper 1 最终落地与执行蓝图（2026-08-16）

状态：`ACTIVE / PAPER-1 EXECUTION AUTHORITY / PRE-OUTCOME FREEZE PLAN`

> **执行覆盖说明：** 本文件中的 empirical qualification、minimum-N、CostWorthIt、broad fact/event union、semantic treatment execution 与 2-of-3 head 条款，已由 `PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md` 覆盖。其余路线 A、public-only、feature 与 official benchmark 规则继续有效。

本文件的目的不是重新讨论研究方向，而是把已经确认的研究问题、尚未落地的实现缺口、科学测量规则、代码迁移顺序、停止条件和最终成功标准放在同一个可执行合同里。

**优先级规则：**

1. 研究范围与论文主张仍由 `PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md` 决定；
2. **实现级 feature schema、数据迁移、测量、freeze、CI、执行顺序，以本文件为最新 authority；**
3. 若 `PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`、旧 V5.3 代码、旧 config/test 与本文件冲突，**不得让旧实现反向修改研究设计**；先按本文件报告冲突，再做最小迁移；
4. main outcome 解封以后，任何改变 Generator / prompt / Retriever / candidate compiler / feature / split / threshold / evaluator 的修改只能进入新版本 exploratory run，不能回写正式结果。

---

# 1. 现在最终研究到底是什么

Paper 1 研究的是：

> **Selective external-resource allocation。**
>
> Retriever / memory construction 先产生一个合法候选资源，Policy Manager 再判断：在当前 state 下，把这个资源额外注入冻结 Generator 是否有值得付出成本的 first-order marginal benefit。

四类资源固定为：

| Head | 唯一定义 |
|---|---|
| **RS** | 是否注入从 ESConv-train-only Strategy Bank 检索出的 Strategy-RAG card / atomic move |
| **MP** | **Profile Memory only**：是否注入当前有效、strict-past 可追溯的 user profile fact |
| **MS** | 是否注入 strictly-past same-user cross-session event / continuity memory |
| **ME** | 是否注入 strictly-past same-user `action → user-observed outcome` experience memory |

Paper 1 不研究：

- ESConv 八类 strategy classification；
- 临床/心理状态诊断；
- 16-class policy；
- RS×MP×MS×ME 高阶 interaction learning；
- synthetic 80-user/11-user 泛化；
- Generator fine-tuning；
- 用自建总分替代 ESC-Eval / ES-MemEval 正式 benchmark。

路线固定为 **A / first-order factorized**：训练一个 head 时，其他三个 optional resources 全部 OFF。运行时四个独立 decision 仍可组成 16 种合法组合，但 Paper 1 不解释为 interaction-aware optimal policy。

---

# 2. 数据与最终考试已经冻结

Active Paper-1 数据只来自公开先行研究资源：

- **ESConv**：RS Strategy Bank、Retriever、RS effect/training source；
- **ESC-Eval**：RQ1 正式多轮 ESC evaluation，只评不训；
- **ES-MemEval / EvoEmo**：MP/MS/ME candidate/effect/training source，以及 RQ2 正式 evaluation。

旧 synthetic 80-user / tracked 11-user 数据及其 derived labels、old MS fallback、old 256 effect labels、old background-conditioned rows 都不得进入 active pipeline。

最终 benchmark：

- **RQ1：ESC-Eval**，报告官方 Fluency / Expression / Empathy / Information / Skillful / Humanoid / Overall；
- **RQ2：ES-MemEval**，报告官方 QA / Summarization / Dialogue Generation 指标；
- Cost 单独记录；不造跨任务总分，不在结果出来后只挑赢的指标。

---

# 3. 整个 PM 的统一科学原则

最重要的一句话：

> **Resource available / retrievable / relevant ≠ worth opening。**

Retriever 回答：

> “现在有什么候选资源？”

Eligibility 回答：

> “这个候选有没有资格进入决策？”

PM 回答：

> “这个合法候选现在是否值得额外注入？”

因此正式链路固定为：

```text
Current state
   │
   ├─ Strategy candidate  ── RS
   ├─ Profile candidate   ── MP
   ├─ Session candidate   ── MS
   └─ Experience candidate── ME
                 │
                 ▼
       source-specific eligibility
                 │
         ineligible → deterministic OFF
                 │ eligible
                 ▼
      outcome-blind raw descriptors
                 │
                 ▼
       four low-capacity L2 heads
                 │
                 ▼
      budget / conflict projection
                 │
                 ▼
          Step-2 typed executor
                 │
                 ▼
           frozen Generator
                 │
                 ▼
       benchmark / training outcome
```

---

# 4. Feature 哲学：前面只描述“眼前是什么”，不能提前给答案

这是本版必须收紧的核心。

**任何 feature 都先问：**

> “如果我知道这个 feature 的值，我是不是已经几乎知道正确 ON/OFF 了？”

如果答案接近“是”，它就不应该作为 PM feature。

因此禁止：

- `resource_helpfulness_score`；
- `worth_opening_score`；
- 人工/LLM 打出的 `response_feasibility_impact`；
- 人工/LLM 打出的 `transferability`；
- 人工/LLM 打出的 `continuity_need`；
- 人工/LLM 打出的 `scope_specificity`；
- 任何“该不该开”“会不会改善回复”的前置评分；
- response、judge、label、gold answer/strategy/evidence、future、dataset/split identity、opaque ID、construction intent、其他 component bits。

允许的 feature 必须满足：

1. runtime 可见；
2. outcome-blind；
3. 固定、确定性或冻结 encoder/retriever 可重复计算；
4. 描述 state/candidate，而不是估计 utility；
5. 在 outcome 解封前冻结；
6. zero-variance / shortcut feature 在 outcome 解封前删除并记录。

**相似 ≠ 有用。** fixed embedding similarity 是允许的，因为它只表示相关性；真正的 marginal utility 仍由 ON/OFF outcome 学。

---

# 5. 四头最终 eligibility 与第一版 feature schema

## 5.1 RS — Strategy-RAG

### Hard eligibility

- candidate 来自 ESConv-train-only Strategy Bank；
- current state 对应的 query/candidate binding 正确；
- atomic move 与用户**明确** boundary 兼容；
- no structural hard exclusion；
- treatment 能够被 Step2 实际执行。

`listen-only` 不等于整个 RS OFF：它只 hard-block 不兼容的 suggestion / probing question；Reflection / Affirmation 仍可成为合法 candidate。

### 第一版 model features

建议只用 raw observables：

1. `rs_state_candidate_similarity`：冻结 Retriever/ranker 的 state↔card similarity；
2. `rs_atomic_move_type`：candidate 自己的 atomic-move / strategy family 类型（不是 ESConv gold strategy）；
3. `rs_recent_same_move_count` 或 `rs_recent_same_move_visible`：最近 supporter 是否已做同类 move；
4. `rs_explicit_request_flags`：当前用户文本中可确定解析出的 advice-request / listen-only / no-probing 等显式 signal；
5. `rs_candidate_token_cost`：candidate 注入的固定 token/结构成本，可选，是否保留由 zero-outcome audit 决定。

不得使用人工/LLM 的 `atomic_move_fit`、`burden_fit` 等 utility-like score。

### RS 特殊 leakage rule

Formal RS effect construction 必须 **leave-current-dialogue-out / fold-exclusive Strategy Bank**：给某个 ESConv dialogue/state 构造 RS candidate 时，Bank 不得包含该 dialogue 自己的 supporter evidence。否则存在隐性 gold leakage。

---

## 5.2 MP — Profile Memory only

### Hard eligibility

- same owner；
- public EvoEmo/ES-MemEval strict-past provenance 可追溯；
- target 时点仍有效；
- inactive / superseded / future / wrong owner → ineligible；
- current visible update 优先；
- no current conflict；
- sensitive profile 在没有当前相关性的情况下不得强行暴露；
- **无 MP_PREFERENCE**。

### 第一版 model features

1. `mp_state_profile_similarity`：固定 embedding/semantic similarity；
2. `mp_profile_already_visible`：当前窗口是否已经明确包含该 fact；
3. `mp_profile_field_type`：occupation / age / education / location / stable social-role 等 raw type；
4. `mp_profile_relative_age`：距最近一次可追溯确认的 session/time distance。

**删除：**

- `mp_response_feasibility_impact`；
- `mp_profile_scope_specificity`。

`already_visible=1` 不 hard-OFF。真实、合法、相关，但当前 context 已经包含，正是高价值 learned OFF。

---

## 5.3 MS — Cross-session continuity memory

### Hard eligibility

- same owner；
- strictly prior **completed session/event**；
- no current/future；
- no last-user-message / current-message fallback；
- entity / time / thread lineage 合法；
- current visible update 优先；
- current conflict 下旧 memory 不能继续当当前事实。

### 第一版 model features

1. `ms_state_memory_similarity`：当前 state↔prior-session candidate 固定 similarity；
2. `ms_memory_already_visible`：当前窗口是否已把该历史完整重述；
3. `ms_relative_age`；
4. `ms_thread_entity_overlap`：确定性 entity/thread overlap count/flag；
5. `ms_explicit_return_marker`：当前用户是否明确出现 again / last time / before / still 等 return/continuity marker。

**删除 utility-like：**

- 主观 `ms_continuity_need`；
- 主观 `ms_state_change_or_open_thread_value`。

如果需要表达“状态变化/open thread”，必须拆成可确定计算的 structural flags，而不是让 LLM 先判断“它有多有价值”。

---

## 5.4 ME — Experience / action→outcome memory

### Hard eligibility

- same owner；
- strictly past；
- explicit action / coping attempt；
- explicit **user-observed outcome**；
- action↔outcome lineage traceable；
- no current conflict；
- ordinary safe transfer scope；
- unresolved/context-only event 不是 ME；
- Step2 只允许 tentative analogy，不允许“过去有效→现在一定有效”。

### 第一版 model features

1. `me_state_experience_similarity`：当前 state↔过去 action-context 的固定 semantic similarity；
2. `me_experience_already_visible`；
3. `me_relative_age`；
4. `me_historical_outcome_type`：positive / negative / mixed / neutral 等 past-outcome raw property；
5. `me_current_action_request`：当前文本是否明确请求建议/下一步/怎么做；
6. `me_candidate_token_cost`：可选，由 zero-outcome audit 决定。

**删除 utility-like：**

- 主观 `me_goal_action_fit`；
- 主观 `me_transferability`。

过去经验与当前是否“值得迁移”正是 ME head 要学的答案，不能由前置 scorer 先给分。

---

# 6. `ineligible`、learned OFF、unknown 必须彻底分开

正式状态只有四类：

### A. `ineligible`

根本不存在合理选择空间：

- absent；
- wrong owner；
- future；
- stale/superseded；
- current explicit conflict；
- invalid MS；
- ME 无 action/outcome；
- RS candidate 与明确 boundary 冲突。

规则直接 OFF，**不作为 classifier 负例**。

### B. `positive_open`

candidate 合法，而且 matched ON/OFF 证明 ON 有 material marginal benefit，且没有不可接受 integrity/risk，成本值得。

### C. `nonpositive_off`

candidate 合法，但合格测量证明：

- OFF 明显更好；或
- ON/OFF **materially equivalent**，而 ON 有额外资源成本。

这才是真正教会 PM “相关但没必要用”的负例。

### D. `unknown`

- treatment 没真正执行；
- candidate lineage 不清；
- scorer/reviewer 不稳定；
- repeated generation 方向不稳定；
- 指标冲突无法按预注册 comparator 裁定。

**训练排除。**

关键区分：

> `materially equivalent` 是测量确认“差不多”，可以因成本成为 OFF；
>
> `uncertain` 是“我们不知道谁更好”，不能伪装成 OFF。

---

# 7. 训练标签：Quality / Risk / Cost 责任必须正交

训练用 outcome measurement 与最终 benchmark 分离。

## 7.1 Quality 只测正向支持价值

训练专用 pairwise quality 只允许用：

1. Goal Fulfillment；
2. Emotional Support Value；
3. Useful Contribution；
4. Clarity & Naturalness。

不得在 Quality 中再次扣：boundary、unsupported personal claim、stale evidence、excessive directiveness。

## 7.2 Risk / integrity 只测 material violation

训练与执行 audit 保留：

1. explicit boundary violation；
2. grounding / personal-evidence violation；
3. excessive directiveness / interaction burden。

工程完整性单独记录：wrong owner、future leakage、scaffold exposure、treatment failure。

## 7.3 Cost 独立

Cost 不与 Quality/Risk 混成一个不可解释总分。

决策逻辑是：

```text
eligible
  AND material quality benefit
  AND no material violation
  AND benefit worth cost
      -> positive_open
```

Cost 永远不能抵消 material quality / integrity failure。

---

# 8. RS 与 memory 的 training outcome 不完全相同

## 8.1 RS

ESConv 没有 RS ON/OFF gold，因此正式训练信号来自：

- 同 state；
- 同 exact Strategy candidate；
- 同 Generator / prompt / decoding / seed schedule；
- 其他三资源 OFF；
- `R0` vs `RS ON` blind pairwise outcome。

训练用 scorer 只产生弱监督；最终 RQ1 成败由 ESC-Eval 决定。

## 8.2 MP/MS/ME

ES-MemEval 自身有 task-specific official outcomes，因此 memory effect label 应尽量锚定官方任务目标，而不是再造一个万能 judge。

在**任何正式 effect outcome 解封前**必须冻结 task-specific comparator：

- **QA**：LLM-as-Judge semantic correctness 作为 primary anchor；F1/BERTScore 作为辅助/tie evidence；
- **Summary**：Event F1 作为 coverage anchor；official LLM Score 作为 faithfulness/semantic guard；ROUGE 作为解释指标；
- **Dialogue Generation**：Weighted Score 作为 memory-use anchor；LT-Memory / Personalization / Emotional Support 作为 guard/explanatory metrics。

若 primary 与 guard 指标发生 material conflict，默认 `unknown`，不得为了多造标签事后挑 favorable metric。

具体 material margin / tie-break rule 不允许从旧 config 直接继承，必须在 Phase 2 的 pre-outcome calibration 中冻结。

---

# 9. Repeated-effect qualification 继续保留

正式批量 labels 前，先证明“state effect”不是单次 LLM 随机波动。

- 8 public-source eligible states / head；
- 4 heads = 32 states；
- 3 independent ON/OFF pairs/state；
- 96 pairs = 192 responses；
- A/B side randomized；
- primary blind reviewer；
- second reviewer 覆盖 32 个预冻结 pair。

最低 qualification：

- ≥70% states 达到 2/3 non-uncertain direction 一致；
- inter-reviewer exact agreement ≥0.75；
- uncertain fraction ≤0.10。

Fail：禁止批量 single-pair hard label。可改 repeated/soft target，或声明该 head 当前 benchmark 不可识别。

---

# 10. Memory cross-fitting 与 leakage boundary

ES-MemEval/EvoEmo 允许 same-user longitudinal adaptation，但必须 outcome-isolated：

- target question/reference/outcome 不进该 target 的训练 fold；
- same fact/event cluster targets 同 fold；
- runtime 只看 target 时点以前 history；
- gold answer/evidence/reference summary/future session 禁止；
- same-user 其他 strict-past、非 target-cluster history 可以使用；
- 最终 uncertainty / inference 以 18 users 为最高 cluster，不能把 1,000+ items 当独立用户。

这应在论文中明确写成：

> `within-benchmark longitudinal adaptation with target/fact-event outcome isolation`

而不是 untouched zero-shot。

---

# 11. ESC-Eval source-overlap 必须恢复为正式边界

Strategy Bank 来自 ESConv，因此 ESC-Eval 中来自 ESConv source 的 role cards 不能包装成完全 independent transfer。

RQ1 报告：

- **primary：non-ESConv-source English role-card slice**；
- secondary：完整冻结 English set；
- ESConv-derived slice：单独作为 in-distribution / overlap sensitivity。

所有 arm 必须同一 role card × seed schedule。

---

# 12. 正式 baseline 不再漂移

## RQ1 — Selective Strategy-RAG

1. `R0 / No Strategy-RAG`
2. `RS Fixed-High`
3. `RS Matched-Random`
4. `Learned RS-PM`

四个 arm：同 Generator、base prompt、Retriever、candidate identity、Step2、token cap、role card、seed、official scorer。

- vs R0：Strategy resource 不能造成 material degradation；
- vs Fixed-High：证明 selective use 能保留能力并减少资源；
- vs Matched-Random：同 ON rate/预算下 Learned 更好，才能证明 opening location 有信息。

ESConv gold strategy 仅作 Retriever diagnostic，不是 PM gate gold。

## RQ2 — Selective typed memory

1. `No Memory`
2. `Full History`
3. `Official RAG Top-4`
4. `Typed Fixed-High`
5. `Typed Matched-Random`
6. `Learned Typed-Memory PM`

RS 在 ES-MemEval main analysis 固定。

Typed Fixed-High 必须保留：它把“typed representation 的收益”和“learned selection 的收益”分开。

## Ablation

不重训：

- `Learned - MP`
- `Learned - MS`
- `Learned - ME`

至少 2/3 memory heads 在预冻结 eligible slice 上出现可复现、正向 official-metric-family contribution，才保留 typed-memory mechanism 主张。

---

# 13. Performance–Cost 成功定义

Paper 1 不需要一个人为总分。

真正需要证明的是 **same-stack Pareto improvement / useful tradeoff**。

RQ1 最低证据结构：

1. Learned vs R0：官方 ESC 能力不能 material worse；
2. Learned vs Fixed-High：在能力非劣前提下明显降低 generator input/resource tokens；
3. Learned vs Matched-Random：相似 ON rate/cost 下 Learned 更好。

RQ2 最低证据结构：

1. Learned 与 Full-History / Official RAG / Typed Fixed-High 比较官方任务指标与成本；
2. Learned 与 Typed Matched-Random 在相似 budget 下比较选择价值；
3. 至少 2 个 memory heads 通过 component-minus 证明独立贡献。

历史上使用过的“≥10% input-token reduction”可以作为候选 engineering effect-size threshold，但**不得不经检查直接从旧 config 当成新正式 freeze**。Phase 2 必须在 main outcome 前确认并写入新的 freeze manifest。

---

# 14. 现在仓库已知的 implementation conflicts

Codex 必须先审计并逐项关闭，不能默认“文档已经改了所以代码也对”。

当前已知至少包括：

1. `v1_5_d3_features.py` 仍把 `background_MP_on / background_MS_on / background_ME_on / background_RS_on` 输入 final head；违反路线 A；
2. 同一文件仍有 `candidate_is_preference`；
3. `v1_5_typed_resource_adapter.py` 仍定义 `MP_PREFERENCE` 为合法 subtype；
4. active V5.3 CI 会执行读取 deprecated 11-user synthetic intake 的测试；
5. `test_v1_5_v5_3_formal_longitudinal_entity_grounding.py` 直接读取 deprecated canonical users；
6. 通用 `experiment.yaml` 仍保留 synthetic generator / P2 synthetic data generator / synthetic mode 等旧入口；
7. public-only zero-outcome coverage audit 尚未形成 active implementation artifact；
8. 旧 D3 Generator manifest 不能自动视为新的 Paper-1 full-stack freeze manifest；
9. active code 仍可能假定每 component 只有 Rank-1 single item；memory bundle size 必须先由 public zero-outcome audit 决定，不能让旧 Rank-1 假设先验锁死；
10. ES-MemEval public artifact identity / count 必须重新审计并 hash；论文原文 QA=1209，仓库旧记录曾出现 public artifact 1427，不能含糊带过。

Codex 若发现新的冲突，应加入同一 conflict ledger；**不允许静默兼容旧逻辑。**

---

# 15. 可控、透明、可复现：正式实验必须留下什么

每个冻结阶段必须生成 manifest，而不是只靠聊天/README。

至少记录：

- dataset artifact hash / version；
- Strategy Bank hash；
- Retriever model/version/index hash；
- candidate compiler hash；
- feature schema version + code hash；
- cross-fit split manifest；
- Generator exact model ID / endpoint mode / base prompt hash；
- Step2 executor hash；
- decoding parameters；
- seed schedule；
- training comparator / evaluator version；
- threshold/margin；
- formal N；
- matched-random schedule；
- baseline configs；
- cost accounting version。

每个 effect row 至少保存：

- visible state；
- exact candidate/bundle + lineage；
- eligibility + hard reasons；
- exact model features；
- OFF/ON treatment；
- treatment-execution trace；
- blinded pair mapping；
- repeated seed ID；
- reviewer/scorer output；
- final training verdict；
- token / latency / API cost；
- hashes。

模型只读取 `model_features`。audit-only ID、user ID、candidate ID、gold、judge、response 全部不能进入 learner。

---

# 16. 最终执行分阶段计划

## Phase 0 — Repository alignment / code hard migration

**目标：先保证 active code 不会偷偷走旧路线。**

Codex 工作：

- 新建/启用 Paper-1 public-only config；
- final MP candidate pool = MP_PROFILE only；
- final feature builder 删除所有 background bits、preference features、utility-like scores；
- active Step2 删除 MP_PREFERENCE path；
- synthetic 11/80-user path/config/runner 从 active pipeline 断开；
- synthetic tests 移到 legacy/diagnostic，不再作为 active blocking suite；
- 增加 fail-closed CI guard：active Paper-1 source/config/test 中出现 deprecated path、`MP_PREFERENCE`、`background_*_on`、old MS fallback 就 fail；
- 建 public-source audit entrypoint。

**Phase 0 不允许调用正式 Generator outcome，不训练 PM。**

Deliverables：

- `repo_alignment_report.json/md`
- `paper1_public_only_config.*`
- active CI guard tests

Go condition：所有 active forbidden-reference checks = 0。

---

## Phase 1 — Public zero-outcome coverage audit

只扫描 ESConv + ES-MemEval/EvoEmo，不生成 ON/OFF response，不读取正式 outcomes。

必须输出：

- RS/MP/MS/ME eligible state/candidate counts；
- 18-user memory coverage；
- QA/Summary/DG 分布；
- strict-past provenance coverage；
- ME action→user-observed-outcome occurrence；
- candidate token-length distribution；
- candidate bundle coverage vs k/token cap；
- 每个 feature 的 variance / correlation / missingness / shortcut report；
- candidate already-visible rate；
- candidate age distribution；
- task-type conditional distributions；
- RS leave-dialogue-out coverage；
- ES-MemEval artifact identity/hash/count audit。

Phase 1 只能回答“有多少合法学习机会、feature 是否可计算、有无方差”；**不能利用 outcome 反向选 feature。**

Go condition：每个拟保留 head 有足够 natural eligible coverage；证据不足的 head标记 `not identifiable`，禁止 synthetic rescue。

---

## Phase 2 — Pre-outcome freeze

根据 Phase 1，**在任何 effect outcome 解封前**一次性冻结：

- candidate single/bundle design；
- top-k / token cap；
- exact feature schema；
- memory task dummy 是否启用；
- cross-fit K / grouping rule；
- formal N target；
- task-specific training comparator；
- material-equivalence / NI margin；
- cost threshold；
- Generator full-stack manifest；
- repeated qualification sample；
- reviewer overlap sample；
- API call plan / budget。

这些项目是“pre-outcome implementation freeze”，不是开放研究方向。Codex 可以根据 zero-outcome audit 推荐，但**不能看 main outcome 后再改。**

---

## Phase 3 — 32-state repeated-effect qualification

按第 9 节执行。

Go：通过 reproducibility / reviewer / uncertainty gate。

No-Go：禁止 full-scale single-pair hard labels；进入 repeated/soft-target redesign 或停止相应 head。

---

## Phase 4 — Formal public-source effect dataset

- RS：ESConv train/dev，fold-exclusive Bank；
- MP/MS/ME：ES-MemEval/EvoEmo outcome-isolated cross-fitting；
- canonical background = 其他三资源 OFF；
- exact candidate/bundle frozen；
- same Generator/prompt/Step2/decoding/seed schedule；
- blind training-only measurement；
- `unknown` 排除。

建议 target：≥128 eligible contrast groups/head；preferred minimum ≥96/head；memory 尽量覆盖 ≥12/18 users。最终 exact N 必须在 Phase 2 freeze。

---

## Phase 5 — Train four L2 first-order heads

Primary learner 不变：

> standardized L2-regularized logistic regression × 4。

必须报告：

- class distribution，但不把 ON 比例当成价值判断；
- grouped CV / cross-fit performance；
- calibration；
- coefficients + CI / stability；
- feature variance / VIF or correlation diagnostics；
- always-off / always-on / transparent eligibility-only internal diagnostics；
- threshold selection protocol；
- user/fact-event grouped uncertainty。

如果 Learned≈简单 eligibility rule，必须如实降低“learned selector”主张；不能为了追分事后换 neural policy。

---

## Phase 6 — Freeze final PM and same-stack baselines

冻结：

- PM checkpoints；
- thresholds；
- Fixed-High；
- Matched-Random schedule；
- Typed Fixed-High；
- Official RAG adapter；
- role-card/item × seed schedule；
- scorer versions；
- cost logging。

从此以后 main evaluation 前不再调参。

---

## Phase 7 — RQ1 ESC-Eval

四臂同栈运行。

Primary analysis：non-ESConv-source English cards；完整 English set secondary；ESConv-source slice sensitivity。

报告七维 + completion/reliability + RS ON rate + injected/input/total tokens + median/p95 latency + recoverable cost。

不使用 ESConv ACC 作为 PM 成败指标；gold strategy family match 仅 Retriever diagnostic。

---

## Phase 8 — RQ2 ES-MemEval

六臂同栈运行，RS fixed。

QA：F1 / BERTScore / LLM-as-Judge + retrieval diagnostics；
Summary：ROUGE / Event P-R-F1 / official LLM Score；
DG：Observation Recall / Weighted Score / LT-Memory / Personalization / Emotional Support；
全部附 input/resource tokens、latency、cost。

统计以 user cluster 为最高层级。

---

## Phase 9 — Component-minus + final claims

不重训：`-MP / -MS / -ME`。

只在预冻结 eligible slices 上解释 contribution。

至少两头具有可复现正向 official-metric-family contribution，才保留 typed-memory mechanism claim。

最终 claim 只说数据支持的内容，不因为某一头失败就临时改 ontology 或补 synthetic。

---

# 17. 什么叫“成功”

Paper 1 的最低成功不是“PM 跑完”或“ON 比例漂亮”。

必须同时有：

1. **RS selection evidence**：Learned RS 在 same-stack ESC-Eval 上相对 R0/Fixed/Matched-Random 形成有意义的 performance–cost tradeoff，且不是只靠少开；
2. **Memory selection evidence**：Learned typed-memory PM 相对 Full History / Official RAG / Typed Fixed-High / Matched-Random 形成有意义的 official-metric–cost tradeoff；
3. **Mechanism evidence**：MP/MS/ME 至少 2/3 在 component-minus 中有可复现正向 contribution；
4. **No leakage / integrity failure**：wrong owner、future leakage、gold leakage、stale/conflict misuse、scaffold exposure 等必须透明报告并受控；
5. **No post-hoc drift**：main outcome 以后不能改 feature / threshold / baseline / subset 来救结果；
6. **Uncertainty honest**：以 dialogue/user/fact-event cluster 报 uncertainty，不把重复 item 冒充独立样本。

如果 RS 不成立但 memory 成立，可以诚实收缩论文 claim；如果某 memory head natural evidence 不足，标记 not identifiable，不 synthetic rescue。

---

# 18. 为什么这条路线科学上站得住

直接先行研究给出的启发与本方法边界是一致的：

- ESC-Eval 已指出单一 lexical ground-truth metric 不足以评价多轮 ESC，因此 RQ1 用其多维 role-playing evaluation，而不是自己创造 PM quality 总分；
- ES-MemEval 明确显示 RAG 可提升 factual consistency/personalization，但对 temporal dynamics、evolving states、abstention 并非统一受益，并且 retrieval k/granularity 的“找得更多”不等于最终 answer 最优——这直接支持“relevance ≠ utility / memory should not be blindly always-on”；
- D2RCU 使用 persona + current post 做固定 semantic retrieval，说明将 similarity 作为 candidate descriptor 是合理的；但本研究进一步问的是“检到了以后是否值得注入”；
- ESCA 等工作重点是“选什么 support strategy”，本研究的核心问题是“额外 Strategy-RAG / typed memory 此时是否值得调用”，problem formulation 不同。

因此第一篇最清楚的 contribution 不是“四个分类器”，而是：

> **把 heterogeneous external resources 的 availability/relevance 与 realized marginal utility 分开，通过 source-specific eligibility + outcome-blind observables + matched counterfactual outcomes，学习可审计的 selective resource allocation。**

---

# 19. 给 Codex 的第一项任务

**不要立即开正式训练，不要自行重新设计研究。**

请先按本文件完成一次 repository-to-contract audit，至少输出：

1. 每条本文件规则对应到当前哪些 source/config/test/docs；
2. 哪些已经符合；
3. 哪些存在直接冲突；
4. 哪些只是缺实现；
5. 哪些需要删除 active wiring、哪些只需要 legacy isolation；
6. Phase 0 最小 PR/commit 顺序；
7. Phase 1 zero-outcome audit 的输入、输出 schema 与预计 coverage；
8. 所有仍需要研究者拍板的 pre-outcome freeze 项，**不得由 Codex 静默决定**。

然后优先完成 Phase 0 + Phase 1。只有 zero-outcome audit 出来后，才进入 Phase 2 freeze 和 repeated-effect qualification。

若 Codex 认为本文件任何条款无法从公开 ESConv / ES-MemEval/EvoEmo 自然实现，必须明确标记：

> `IMPLEMENTATION BLOCKER — RESEARCHER DECISION REQUIRED`

并说明：缺什么公开 evidence、会影响哪个 head/RQ/claim、有哪些最小替代方案。不得回到 synthetic 80-user/11-user 路线兜底。
