# Policy Manager Paper 1 最终训练合同（2026-08-16，public-data-only 修正版）

状态：`ACTIVE / SUBORDINATE TO PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`

> **执行覆盖说明：** 本文件中的主观 utility-like feature、70%/0.75/10% qualification、96/128 minimum 与 hard-label 条款，已由 `PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md` 覆盖。active implementation 使用 outcome-blind raw features 与 soft/binomial effect targets。

> **硬规则：Paper 1 的训练数据、effect states、candidate contents 和 final labels 只来自公开先行研究资源。旧 synthetic 80-user/11-user 资产全部退出 active pipeline，不得再读取、采样、审计、修复、编译、训练或作为 evidence 使用。**

本合同回答：四个 head 看什么 outcome-blind features；训练数据怎样构造；哪些公开资源负责训练/评价；以及 Generator 已冻结后怎么立即推进。

---

## 1. 数据源先说清：不是“11 人”，也不是 synthetic 80 人

Paper 1 整条实验链涉及 **三个先行研究资源**：

1. **ESConv**：RQ1 的 Strategy-RAG 资源与 RS 训练来源；
2. **ESC-Eval**：RQ1 的最终公开 benchmark，只用于评价，不进入训练；
3. **ES-MemEval（其底层 longitudinal corpus 是 EvoEmo）**：RQ2 的 MP/MS/ME 训练/候选来源与最终 benchmark。

因此：

- 若问“有几个训练数据源”：**两个**——`ESConv` 与 `ES-MemEval/EvoEmo`；
- 若问“整篇论文用了几个先行研究资源”：**三个**——`ESConv`、`ESC-Eval`、`ES-MemEval/EvoEmo`；
- `EvoEmo` 不单独算第四个独立 benchmark，因为 ES-MemEval 就是从 EvoEmo 构建长期对话与任务；
- `ESC-Eval` 只负责 RQ1 最终测量，不训练 PM。

旧目录 `project/data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/` 已明确 deprecated，Paper 1 不得使用。

---

## 2. 总原则：路线 A / first-order factorized

每个 component `c ∈ {RS, MP, MS, ME}` 的正式 effect estimand：

> 在其他 optional resources 全部 OFF 的 canonical background 下，保持 current state、exact candidate/bundle、Generator、base prompt、Step2、decoding 与 seed schedule 不变，只切换目标 component OFF↔ON，估计该 component 自身是否产生 material marginal benefit。

因此：

- final head 不读取其他 component ON/OFF bits；
- 不学习 background-conditioned interaction；
- 16 个 runtime combination 只是四个独立决定的组合；
- Paper 1 不尝试回答“其他资源开得对不对以后我还值不值得开”。

---

## 3. 四头 ontology

### RS

- Strategy-RAG candidate 来自 **ESConv train-only Strategy Bank**；
- PM 判断当前是否值得注入已检索的 strategy card / atomic move；
- 不是 ESConv 八类 strategy classifier。

### MP

- **Profile Memory only**；
- 只包括 EvoEmo/ES-MemEval strict-past history 中可追溯、当前有效的 user profile facts；
- `MP_PREFERENCE` / `response_preference_history` 完全退出 Paper 1。

### MS

- strictly-past same-user cross-session event/session-continuity information；
- current turn / last-message fallback / future session 不属于 MS。

### ME

- strictly-past **action → user-observed outcome** experience；
- 必须有明确 action 与用户实际观察到的 result/outcome；
- unresolved/context-only event 不是 ME。

---

## 4. `ineligible` 与 learned OFF

先做 source-specific eligibility：

- `ineligible`：candidate absent、wrong owner、future、inactive/superseded profile、current conflict、非法 MS、ME 无 action+observed outcome、RS atomic move 与明确 boundary 冲突等；**deterministic OFF，不进入 classifier 负例**；
- `eligible + positive_open`：ON materially better；
- `eligible + nonpositive_off`：OFF materially better，或 ON/OFF materially equivalent；
- `eligible + unknown`：执行/测量不稳定或不可裁定，训练排除。

真正最有价值的 OFF 是：candidate 完全正确、合法、甚至相关，但当前 context 已经够、Generator 本身会做、信息重复、profile 不改变当前回复、MS 已被用户重述、ME 不适合当前情境等。

---

## 5. Feature 共通禁区

四个 head 禁止读取：

- generated response；
- training judge / official benchmark outcome；
- final label；
- gold answer / gold strategy / gold evidence；
- future session/event；
- split identity / dataset name；
- opaque user/candidate/card ID；
- construction intent；
- 其他 component ON/OFF bits；
- preference-specific metadata。

允许读取：

- runtime 可见 current state / task type；
- fixed Retriever 已产生的 candidate/bundle descriptors；
- owner/time/version/lineage 等 eligibility metadata；
- outcome-blind semantic / structural match；
- incremental-information / redundancy；
- relative age 等 runtime 可见属性。

连续 feature 在 fit fold 内 standardized；zero-variance feature 在 outcome 解封前删除并记录。

---

## 6. RS final feature schema

Primary 建议 4 项：

1. `rs_candidate_state_match`：冻结 Retriever/ranker 的 state↔card match；
2. `rs_atomic_move_fit`：candidate atomic move 与当前 visible support goal/request 的 fit；
3. `rs_recent_move_nonredundancy`：最近是否已完成同类 atomic move；
4. `rs_burden_fit`：当前 interaction burden 与 candidate 结构负担是否匹配。

可选：`rs_candidate_incremental_tokens`，仅在 pre-outcome variance/capacity audit 证明有必要时加入。

不加入：gold strategy family one-hot、background resource bits。

---

## 7. MP final feature schema — Profile only

MP candidate 只来自 public EvoEmo/ES-MemEval history 中可追溯 profile facts，例如 age、occupation、education、location、stable family/social role 等。

Primary 建议：

1. `mp_profile_state_relevance`：profile 与当前 query/state 是否相关；
2. `mp_incremental_information`：当前 visible context 是否已完整出现；
3. `mp_response_feasibility_impact`：该 profile 是否有能力改变现实可行性/个性化解释；
4. `mp_profile_scope_specificity`：profile applicability 与当前 task/goal 的具体匹配。

禁止 preference feature。

---

## 8. MS final feature schema

Primary 建议：

1. `ms_state_topic_match`：当前 state 与 prior-session candidate 的语义/线程匹配；
2. `ms_continuity_need`：当前是否需要跨 session continuity / temporal reasoning；
3. `ms_incremental_information`：过去信息是否尚未在 current context 充分出现；
4. `ms_state_change_or_open_thread_value`：candidate 是否包含 evolving/unresolved thread、状态变化或关键 prior distinction；
5. `ms_relative_age`：距当前 session 的时间距离。

MS hard gate：same owner、strictly prior、no future/current、no last-message fallback、entity/time/thread valid、visible update 优先。

---

## 9. ME final feature schema

ME hard gate：same owner、strict past、action present、**user-observed outcome present**、action↔outcome lineage traceable、no visible conflict、ordinary safe transfer scope。

Primary 建议：

1. `me_state_experience_match`；
2. `me_goal_action_fit`；
3. `me_transferability`；
4. `me_incremental_information`；
5. `me_relative_age`。

`action_present` / `outcome_present` 属于 hard eligibility，不作为 learned feature 来弥补非法 candidate。

---

## 10. task_type 是否进入 memory heads

因为同一 MP/MS/ME head 要运行 QA / Summarization / Dialogue Generation，可选两个 runtime-known dummy：

- `task_is_summary`
- `task_is_dialogue_generation`

QA 为 reference category。

是否启用必须在任何 effect outcome 解封前，通过 public ES-MemEval zero-outcome coverage/feature audit 冻结；一旦启用，三个 memory heads 使用同一 encoding。

---

## 11. Memory training 如何只用公开 ES-MemEval/EvoEmo 又保持公平

ES-MemEval 只有 18 个长期用户，Paper 1 不要求完全 unseen-user generalization，但必须 outcome-isolated cross-fitting。

对 QA/Summary/DG targets：

- target question/reference/outcome 不进入为该 target 预测的训练 fold；
- 同 fact/event cluster 的 target outcomes 绑定在同一 fold；
- runtime PM 只能看 target 时点之前的 EvoEmo history；
- gold answer / gold evidence / reference summary / future session 禁止进入 runtime features；
- 同一用户其他 strict-past、非 target-cluster 信息允许用于 longitudinal adaptation；
- 最终统计仍以 18 个 user 为最高 cluster，不能把 1,000+ item 当独立用户。

这不是“untouched zero-shot”，而是预先声明的 **within-benchmark longitudinal adaptation + outcome-isolated cross-fitting**；论文 claim 必须按这个边界写。

---

## 12. Repeated-effect measurement qualification

正式批量生成 final labels 前：

- 每 head 8 个 **public-source eligible states**，共 32；
- 每 state 独立生成 3 组 matched ON/OFF；
- 96 pairs = 192 Generator responses；
- A/B side 随机盲化；
- primary reviewer 判 `ON better / OFF better / equivalent / uncertain`；
- second reviewer 覆盖 32 个预冻结 shared pairs。

Gates：

- ≥70% states 达到 2/3 non-uncertain direction 一致；
- inter-reviewer exact agreement ≥0.75；
- uncertain fraction ≤0.10。

qualification state 也必须来自 `ESConv` 或 `ES-MemEval/EvoEmo`，**不得用 synthetic 11/80-user states 替代**。

若 fail：禁止批量 single-pair hard labels，改 repeated/soft target 或停止该 head。

---

## 13. Formal effect dataset 最小结构

每个 contrast group：

```json
{
  "effect_group_id": "...",
  "component": "MP",
  "source_dataset": "ESConv|ES-MemEval",
  "task_type": "qa|summary|dialogue_generation|esc_response",
  "grouping_user_id": "AUDIT_ONLY",
  "fact_event_cluster_id": "AUDIT_ONLY",
  "visible_state": {...},
  "candidate_bundle": {...},
  "candidate_lineage": {...},
  "eligibility": {"status": "eligible|ineligible", "hard_reasons": []},
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
  "training_outcome": {"verdict": "positive_open|nonpositive_off|unknown"},
  "cost": {...}
}
```

`grouping_user_id`、cluster id、candidate identity 仅 audit/grouping，不进模型。

---

## 14. 现有资产：只继承代码/协议，不继承旧 synthetic 数据

### 可继承

- ESConv train-only Strategy Bank **构建代码/逻辑**，但最终 Bank 必须从 public ESConv train 重新物化并 hash；
- candidate/owner/time/version/compiler 的通用代码；
- Step2 typed executor 的 attribution / temporal / forbidden-inference 代码；
- official ESC-Eval / ES-MemEval adapter、scorer、metric code；
- 旧 root-cause 文档只作为工程历史，不参与新数据选择。

### 不得继承为 active Paper-1 data/evidence

- synthetic 80-user corpus；
- tracked 11-user intake 与该目录任何内容；
- synthetic MP_PROFILE / MP_PREFERENCE / MS / ME candidates；
- old 256 paired labels；
- old background-conditioned effect rows；
- old MS fallback labels；
- 任何依赖旧 Generator/旧 ontology 的 effect winner。

**Final training data 从零按 public sources 重新物化。**

---

## 15. Formal N 不再由 synthetic 用户数决定

不要再讨论“80 synthetic users 是否够”。

先对 public data 做 zero-outcome coverage audit，再在任何 effect outcome 解封前冻结每 head N。

建议 target：

- ≥128 eligible contrast groups/head；
- preferred minimum ≥96/head；
- effective independent grouping ≥ `max(48, 5 × effective_feature_count)`；
- memory heads 尽量覆盖 ≥12/18 EvoEmo users；
- 不强行做 50:50 ON/OFF；
- 某 head public natural evidence 不足 → `not identifiable on this benchmark`，不 synthetic rescue。

---

## 16. Evaluation 不变：最终能力全部由先行研究 benchmark 判断

### RQ1

训练：ESConv train-only。

正式 ESC-Eval arms：

- R0
- RS Fixed-High
- RS Matched-Random
- Learned RS-PM

全部报告官方七维：Fluency / Expression / Empathy / Information / Skillful / Humanoid / Overall。

### RQ2

公开 ES-MemEval arms：

- No Memory
- Full History
- Official RAG Top-4
- Typed Fixed-High
- Typed Matched-Random
- Learned Typed-Memory PM

指标全部用官方定义：

- QA final answer quality：F1 / BERTScore / LLM-as-Judge；retrieval diagnostic：Recall@k / nDCG@k；
- Summary：ROUGE-1/2/L、Event P/R/F1、official LLM Score；
- DG：Observation Recall / Weighted Score、LT-Memory / Personalization / Emotional Support。

不造跨任务总分，不在结果后只挑赢的指标。

---

## 17. 立刻执行顺序（Generator 已冻结）

1. **代码迁移**：Paper-1 MP 只接 public `MP_PROFILE`；final head 移除 background bits；synthetic 11/80-user paths 从 active config/runner/test 中断开；
2. **public zero-outcome coverage audit**：只扫描 ESConv + ES-MemEval/EvoEmo，统计 RS/MP/MS/ME eligible candidate/state、18-user coverage、QA/Summary/DG distribution、ME action→observed-outcome coverage、feature variance；
3. 冻结 source-specific candidate bundle top-k/token caps；
4. 冻结 final feature schema与 cross-fit K；
5. 跑 32-state public-source repeated-effect qualification；
6. 通过后冻结 formal N / splits / API call plan；
7. 生成 final matched ON/OFF effect responses；
8. 完成 training-only blind outcome review；
9. 训练四个 L2 first-order heads；
10. freeze thresholds / PM checkpoint / same-stack baselines / matched-random schedules；
11. RQ1 ESC-Eval；
12. RQ2 ES-MemEval；
13. −MP/−MS/−ME；
14. official metrics + Cost + cluster uncertainty + minimal integrity report。

从第 5 步开始，Generator、base prompt、Retriever、candidate compiler、feature schema 任何变化都要求重新评估 effect-label validity。
