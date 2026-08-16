# Policy Manager Paper 1 最终训练合同（2026-08-16）

状态：`ACTIVE / SUBORDINATE TO PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`

本合同回答四件马上要执行的问题：

1. 四个 head 最终看哪些 outcome-blind features；
2. matched ON/OFF effect row 到底长什么样；
3. 现有数据哪些能继承、哪些必须重做；
4. Generator 已冻结后，下一步按什么顺序正式开始训练。

---

## 1. 总原则：路线 A

Paper 1 使用 **first-order factorized resource utility**。

每个 component `c ∈ {RS, MP, MS, ME}` 的正式 effect estimand：

> 在其他 optional resources 全部 OFF 的 canonical background 下，保持 current state、exact candidate/bundle、Generator、base prompt、Step2、decoding 与 seed schedule 不变，只切换目标 component OFF↔ON，估计该 component 是否产生 material marginal benefit。

因此：

- final head 不读取其他 component ON/OFF bits；
- old background-conditioned effects 只作 interaction diagnostic；
- 16 个 runtime combinations 只是四个独立 head 的组合，不是 16-class learner；
- 不尝试回答“如果另一个资源开错了，这个资源该怎么办”。

---

## 2. Final learned target

每个 head 输出：

`P(material_benefit | current_state, eligible_exact_candidate)`

训练 label：

- `positive_open`：ON materially better；
- `nonpositive_off`：OFF materially better，或 ON/OFF materially equivalent；
- `unknown`：无法稳定裁定、treatment 未有效执行、lineage/measurement 无资格。

`unknown` 不训练。

`ineligible` 在 learned label 之前单独处理，不属于 `nonpositive_off`。

Cost 不作为 LLM judge 的主观分数。若 quality 真正等效，额外资源有正成本，因此部署决定 OFF；material quality gain 是否值得最终成本由冻结 threshold / Cost report 与 same-stack evaluation共同解释。

---

## 3. Feature 共通禁区

四个 head 都禁止读取：

- generated response；
- training judge / official benchmark score；
- final label；
- gold answer / gold strategy / gold evidence；
- future session / future event；
- split identity；
- dataset name；
- opaque user/candidate/card ID；
- construction intent / synthetic answer key；
- 其他 component 的 ON/OFF bits；
- `MP_PREFERENCE` 或 preference-specific metadata。

允许读取：

- runtime 可见 current state / task type；
- fixed Retriever 已经产生的 candidate/bundle descriptors；
- owner/time/version/lineage 等 eligibility metadata；
- outcome-blind semantic / structural match factors；
- incremental-information / redundancy factors；
- candidate age 等 runtime 可见属性。

所有连续 feature 在 fit fold 内 standardized；所有 zero-variance feature 在 outcome 解封前自动删除并记录。

---

## 4. RS head：Final feature schema

RS 只在 eligible Strategy-RAG candidate/bundle 上学习。

建议 final primary features（目标 4 个）：

1. `rs_candidate_state_match`
   - 冻结 Strategy Retriever / ranker 给出的 state↔card 相关性；
   - 不使用 ESConv gold strategy label。

2. `rs_atomic_move_fit`
   - 0–1 或 {0,0.5,1}；
   - candidate atomic move 与当前 visible support goal / request 的 outcome-blind fit；
   - explicit incompatible boundary 已在 eligibility hard-off，不在这里作为 noisy label。

3. `rs_recent_move_nonredundancy`
   - 最近 assistant 是否已经完成相同/高度同类 atomic move；
   - 完全重复倾向低值，但若 candidate 仍合法可以成为 learned OFF。

4. `rs_burden_fit`
   - 当前负担/回复容量与 candidate 的结构性 burden 是否匹配；
   - 只描述负担，不直接编码“正确答案”。

可选 challenger feature（只有 pre-outcome audit 证明有独立变异且不超容量才加入）：

- `rs_candidate_incremental_tokens`。

不加入：strategy gold family one-hot、background resource bits。

---

## 5. MP head：Profile Memory only

### 5.1 Candidate ontology

Paper 1 MP candidate 只能来自 `MP_PROFILE`。典型 field 包括：

- age；
- job/occupation；
- education；
- location；
- stable social/family role；
- 其他可验证、当前有效的长期 profile facts。

`response_preference_history` 全部排除。

### 5.2 Final feature schema

建议 primary features：

1. `mp_profile_state_relevance`
   - current state / query 与 profile fact/bundle 的冻结语义或 scope relevance。

2. `mp_incremental_information`
   - profile 是否已经在当前 visible context 中完整重述；
   - 合法但已充分可见是典型 learned-OFF 场景。

3. `mp_response_feasibility_impact`
   - outcome-blind 结构分：这个 profile 是否有能力改变建议可行性、时间、现实约束或个性化解释；
   - 例如 job/location/education 在相关任务可较高，name/age/gender 不因存在而自动高。

4. `mp_profile_scope_specificity`
   - candidate applicability scope 与 current task/goal 的具体匹配程度；
   - 不能直接使用作者预写的 `worth_opening` 类字段。

Memory benchmark 统一 head 如需区分官方 task format，可额外加入两个 runtime-known dummy：

5. `task_is_summary`
6. `task_is_dialogue_generation`

QA 为 reference category。

是否启用 task dummies 在正式 effect outcome 前由 zero-outcome coverage audit 冻结；一旦启用，MP/MS/ME 使用相同 task encoding。

---

## 6. MS head：strictly-past cross-session continuity

### 6.1 Candidate ontology

MS 只能来自严格过去的完整 session/event/continuity information。禁止：

- current message fallback；
- last-user-message 当 session summary；
- future session；
- wrong owner；
- visible current update 已明确推翻的旧状态。

### 6.2 Final feature schema

建议 primary features：

1. `ms_state_topic_match`
   - current state 与 prior-session candidate/bundle 的语义相关性。

2. `ms_continuity_need`
   - 当前 turn 是否存在“again / still / last time / what changed / same issue”等 continuity opportunity，或任务本身需要跨 session reasoning。

3. `ms_incremental_information`
   - prior-session information 是否尚未在 current visible context 中充分出现。

4. `ms_state_change_or_open_thread_value`
   - candidate 是否包含 unresolved/evolving thread、状态变化、时间区分或当前任务可能需要的 prior distinction；
   - 这是 candidate 描述，不是 response outcome。

5. `ms_relative_age`
   - 距当前 session 的标准化时间距离；
   - 只作为连续变量/粗 bucket，不把“越近必定越好”写成规则。

若统一 memory head 需要 task encoding，可加同样的 `task_is_summary / task_is_dialogue_generation`。

---

## 7. ME head：strict action → observed outcome

### 7.1 Hard construct gate

ME candidate 必须同时有：

- `action_present = true`；
- `user_observed_outcome_present = true`；
- action↔outcome lineage 可追溯；
- strictly past；
- same owner；
- no visible conflict；
- ordinary safe transfer scope。

没有 outcome 的 unresolved/context event 是 **ineligible for ME reuse**，不能作为“聪明 OFF”训练样本。

### 7.2 Final feature schema

建议 primary features：

1. `me_state_experience_match`
   - 当前问题与过去 experience 的语义/问题结构相关性。

2. `me_goal_action_fit`
   - 当前用户目标是否允许/需要行动层面的参考；
   - explicit incompatible boundary 已在 eligibility / Step2 处理。

3. `me_transferability`
   - 当前情境与过去 action→outcome 的可比程度；
   - 不等于“过去成功所以现在成功”。

4. `me_incremental_information`
   - 过去经验是否已经在 visible context 中完整提过。

5. `me_relative_age`
   - 经验距当前的时间距离。

若启用 task encoding，同样加入 `task_is_summary / task_is_dialogue_generation`。

不允许把 `me_contains_action`、`me_contains_result` 当 learned feature来弥补非法 candidate；这两项已经属于 hard eligibility。

---

## 8. Source-specific eligibility 与 learned OFF 的边界

### 8.1 只做 hard eligibility 的情况

以下情况不进入 classifier：

- candidate absent；
- wrong owner；
- future；
- inactive / superseded profile；
- current explicit update 冲突；
- MS 不是 prior-session construct；
- ME 没有 action + observed outcome；
- RS atomic move 被当前明确 boundary 硬禁止；
- candidate lineage 不可审计。

### 8.2 最有价值的 learned OFF

正式数据必须刻意覆盖：

- candidate 完全正确、合法，但 current context 已经足够；
- candidate 相关，但 Generator 无需它也能完成同样支持功能；
- candidate 加入后造成重复/过度结构/信息负担；
- profile 真实但对当前回复没有实际个性化增量；
- prior session 相关但当前用户已经重述；
- ME 真实有效但当前情境不可迁移。

这类 OFF 才证明 PM 学的是“worth using”，而不是“垃圾过滤器”。

---

## 9. Repeated-effect measurement qualification

正式全量标签之前先跑：

- 4 heads × 8 eligible states = 32 states；
- 每 state 3 组独立 matched ON/OFF；
- 共 96 paired contrasts，192 Generator responses；
- A/B side 随机并盲化；
- primary reviewer 对全部 96 pair 判 `ON better / OFF better / equivalent / uncertain`；
- second reviewer 独立覆盖 32 个预冻结 shared pairs。

Qualification gates：

- ≥70% states 达到 2/3 non-uncertain direction 一致；
- shared-pair exact inter-reviewer agreement ≥0.75；
- uncertain fraction ≤0.10。

通过后：正式 effect training 可使用单 pair 作为 noisy supervision，但保留预冻结 replicate audit slice。

未通过：不得继续批量制造 single-pair hard gold；必须改用 repeated/soft target 或停止该 head。

---

## 10. Formal effect dataset 的数据结构

推荐 JSONL 每个 contrast group 至少含：

```json
{
  "effect_group_id": "...",
  "component": "MP",
  "task_type": "qa|summary|dialogue_generation|esc_response",
  "user_id": "GROUPING_ONLY",
  "fact_event_cluster_id": "GROUPING_ONLY",
  "current_session_index": 12,
  "visible_state": {...},
  "candidate_bundle": {...},
  "candidate_lineage": {...},
  "eligibility": {
    "status": "eligible|ineligible",
    "hard_reasons": []
  },
  "model_features": {...},
  "canonical_background": "all_other_optional_components_off",
  "off_treatment": {...},
  "on_treatment": {...},
  "generator_freeze_hash": "...",
  "base_prompt_hash": "...",
  "executor_hash": "...",
  "seed_schedule_id": "...",
  "anonymous_pair": {...},
  "treatment_execution": {...},
  "training_outcome": {
    "verdict": "positive_open|nonpositive_off|unknown"
  },
  "cost": {...}
}
```

`user_id`、cluster id、candidate identity 只用于 grouping/audit，不进入模型。

---

## 11. Split / cross-fitting

### 11.1 RS

- Strategy Bank：ESConv train only；
- effect-fit / effect-dev 只能取 ESConv train/dev 允许范围；
- dialogue / semantic group 不跨 fit/dev；
- ESC-Eval 完全不用于 RS feature、threshold 或 training-label tuning。

### 11.2 MP/MS/ME

ES-MemEval 只有 18 个长期用户，因此不把上千 item 当独立用户。

正式采用 **outcome-isolated cross-fitting**：

- 最高 grouping 单位仍是 user；
- target/fact-event cluster 必须绑定在同一 fold；
- 某 target 的 PM prediction 必须来自未见过该 target outcome 与同 cluster outcome 的 fit；
- runtime PM 只能看 target 时点以前的 history；
- gold answer/evidence/reference/future session 不进 runtime feature；
- 同一用户的其他严格过去、非 target-cluster 信息可用于 longitudinal adaptation；
- user-cluster uncertainty 在最终报告中保留。

Cross-fit fold 数在 coverage audit 后、outcome 解封前冻结；默认优先 5-fold，若 cluster 数不支持则降到能保持每 fold 足够独立 cluster 的最小 K，并记录理由。

---

## 12. 现有数据：哪些能继承

### 12.1 可以直接继承为“资源/编译器资产”

- ESConv train-only Strategy Bank 构建逻辑与可审计 card schema；
- 已验证的 strict owner/time/version profile schema；
- existing `MP_PROFILE` facts；
- 合格的 prior-session MS summary/event assets；
- 合格的 ME action→observed-outcome examples；
- Step2 typed executor 的正确 attribution / temporal / forbidden-inference 约束；
- old 256 labels 的 label-distribution / heterogeneity 结论；
- old root-cause audit 对 feature capacity、background collapse、MS fallback 的诊断。

### 12.2 只能用于开发/资格化，不能当 final training label

- 旧 RS/MP/ME paired effect winners；
- 旧 synthetic 80-user 设计蓝图；
- 当前仓库 tracked formal longitudinal intake 中的少量 synthetic users；
- preference 数据；
- old background-conditioned interaction examples。

原因：Generator / measurement / ontology / Paper-1 route 已变化，不能把旧 outcome 自动升级为 final gold。

### 12.3 必须重做

- **所有 formal MS effect labels**；
- 使用 MP_PREFERENCE 的 MP effect rows；
- final four-head effect labels under route A canonical background；
- final feature extraction without background bits；
- repeated-effect qualification；
- final threshold/calibration；
- matched-random schedules；
- same-stack formal baseline outcomes。

---

## 13. 当前仓库数据 readiness 的事实判断

当前 tracked formal longitudinal intake 不是完整 80-user corpus；现有 repair manifest 只记录 **11 users**，状态仍为 `MACHINE_PASS_BATCH_AND_SEMANTIC_REVIEW_PENDING`。因此它不能被描述成“最终 80-user training set 已准备完成”。

Paper 1 不再要求先补完 synthetic 80-user corpus 才能训练。下一步应优先从正式公开数据角色出发：

- RS：ESConv train-only；
- MP/MS/ME：ES-MemEval/EvoEmo strict-past histories + outcome-isolated cross-fitting；
- synthetic 11-user/历史资产用于 eligibility/feature/compiler/debug。

在任何 paid/full effect generation 前必须先跑一个 **zero-outcome coverage audit**，统计：

- 每个 head eligible candidate 数；
- memory head 覆盖的用户数；
- fact/event cluster 数；
- QA/Summary/DG task distribution；
- ME action→observed-outcome 的自然 occurrence；
- feature variance 与 feature shortcut。

数据量不为追求 50:50 ON/OFF 人工平衡；目标是覆盖真实 positive、合法 nonpositive、边界和 unknown。

---

## 14. Formal N 的冻结方法

不要现在拍脑袋承诺 80 users 或固定 50:50 label。

Coverage audit 后、任何 effect outcome 解封前冻结每头 N。建议：

- **target**：≥128 eligible contrast groups / head；
- **preferred minimum**：≥96 eligible contrast groups / head；
- effective independent grouping 必须满足 `>= max(48, 5 × effective_feature_count)`；
- memory head 尽量覆盖 ≥12/18 users；
- 若某 head 自然 evidence 达不到最低可识别规模，标记 `not identifiable`，不 synthetic rescue。

这些是训练规模门，不是要求 label 50:50。

---

## 15. 训练完成后的最小内部 learnability report

每头至少报告：

- grouped/cross-fitted balanced accuracy；
- positive recall；
- specificity；
- Brier / calibration；
- predicted ON/OFF rate；
- always-off / always-on 对照；
- transparent eligibility-only rule diagnostic；
- feature coefficient / confidence stability；
- user/fact-event cluster uncertainty。

内部 classifier 指标只回答“head 能不能学到训练 proxy”，**不代替 ESC-Eval/ES-MemEval Paper-1 outcome**。

不再强制“预测 ON 和 OFF 都至少 20%”作为科学成功条件；class proportion 本身不是研究目标。

---

## 16. 立刻执行顺序

Generator 已冻结后，按以下顺序推进，不再重新讨论 Paper-1 大框架：

1. 迁移代码：MP_PROFILE only；移除 final head background bits；
2. 写/跑 zero-outcome coverage audit；
3. 冻结 source-specific candidate bundle top-k/token caps；
4. 冻结 feature schema；
5. 跑 32-state repeated-effect qualification；
6. 通过后 freeze formal N / split / call plan；
7. 生成 final RS/MP/MS/ME matched ON/OFF responses；
8. 完成训练专用 blind outcome review；
9. 训练四个 L2 heads；
10. freeze thresholds / PM checkpoint / baseline configs；
11. 生成 Matched-Random schedules（outcome 前）；
12. RQ1 ESC-Eval；
13. RQ2 ES-MemEval QA/Summary/DG；
14. −MP/−MS/−ME；
15. official metrics + Cost + cluster uncertainty + minimal integrity report。

从第 5 步开始，任何 Generator、base prompt、Retriever、candidate compiler、feature schema 变化都要求重新评估 effect-label validity。
