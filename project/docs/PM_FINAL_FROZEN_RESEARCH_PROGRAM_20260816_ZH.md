# Policy Manager 第一篇论文最终冻结研究方案（2026-08-16，public-data-only 修正版）

状态：`ACTIVE / SINGLE SOURCE OF RESEARCH TRUTH / PAPER-1 FIRST-ORDER ROUTE`

机器可读合同：`project/data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`

训练合同：`project/docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`

> **执行覆盖说明：** 本文件中的 CostWorthIt、70%/0.75/10% qualification、96/128 minimum、10% cost 与 2-of-3 head 条款，已由 `PM_PAPER1_EXECUTION_RECONCILIATION_20260816_ZH.md` 明确覆盖，不再是 active gate。

> **方法名：Policy Manager（PM），不是 MetaCom。**
>
> **Generator 已冻结。** 后续 effect generation、PM、baseline 与正式 evaluation 使用同一 Generator / base prompt / mode / decoding / seed schedule；若更换 Generator，effect labels 必须重做。
>
> **Paper 1 数据硬规则：训练数据与 formal effect states 完全基于公开先行研究资源。旧 synthetic 80-user/11-user 纵向数据全部退出 active pipeline，不得再读取、采样、审计、修复、编译、训练或作为 Paper-1 evidence。**

---

## 1. 研究问题

情绪支持中的 Strategy-RAG 与长期记忆并不是每轮都值得注入。Paper 1 只回答：

> **一个低容量、可审计的 pre-injection / pre-generation Policy Manager，能否分别学习 Strategy-RAG、Profile Memory、cross-session Memory 与 Experience Memory 的 first-order state×candidate marginal utility，在公认 benchmark 上保持或改善性能，同时减少不必要的 Generator context 与成本？**

这是一项 **selective external-resource allocation** 研究。

Paper 1 不主张：

- 诊断用户真实心理需求/临床状态；
- 直接预测 ESConv strategy category；
- 训练 16-class policy；
- 学习 RS×MP×MS×ME 高阶 interaction；
- 完全 unseen-user population generalization；
- synthetic 80-user/11-user 泛化结论；
- 旧自建 Quality/Function/Risk 总分作为论文主 verdict。

---

## 2. 三个先行研究资源，各负其责

整篇 Paper 1 涉及 **三个先行研究资源**：

### 2.1 ESConv

只负责 RQ1 的 Strategy-RAG：

- train split 构建 Strategy Bank；
- train/dev 产生 RS matched ON/OFF effect states；
- held-out 做 Retriever / in-domain diagnostic。

ESConv gold strategy 不是 RS ON/OFF gold，也不是 PM primary outcome。

### 2.2 ESC-Eval

只负责：

- 已完成的 Generator qualification；
- RQ1 最终多轮 ESC evaluation。

**ESC-Eval 不进入 PM 训练。**

### 2.3 ES-MemEval / EvoEmo

ES-MemEval 是正式 long-term memory benchmark；EvoEmo 是其底层 longitudinal emotional-support corpus。

它负责：

- MP/MS/ME strict-past candidate source；
- MP/MS/ME training/effect states（通过 outcome-isolated cross-fitting）；
- RQ2 QA / Summarization / Dialogue Generation 正式 evaluation。

EvoEmo 不单独作为第四个独立 benchmark。

因此：

> **训练数据源有两个：ESConv + ES-MemEval/EvoEmo。**
>
> **正式 evaluation benchmark 有两个：ESC-Eval + ES-MemEval。**
>
> **整篇涉及三个先行研究资源：ESConv、ESC-Eval、ES-MemEval/EvoEmo。**

---

## 3. 四类资源固定定义

| Head | Paper 1 唯一定义 |
|---|---|
| **RS** | 是否注入从 ESConv-train-only Strategy Bank 检索到的 Strategy-RAG card / atomic move |
| **MP** | **Profile Memory only**：是否使用当前有效的 user profile facts |
| **MS** | 是否使用 strictly-past same-user cross-session event/session-continuity memory |
| **ME** | 是否使用 strictly-past same-user **action → user-observed outcome** experience memory |

### 3.1 MP_PREFERENCE 永久退出 Paper 1

- `MP_PREFERENCE` / `response_preference_history` 不进入 training；
- 不进入 runtime candidate pool；
- 不进入 ES-MemEval；
- 不进入 component-minus claim；
- 旧 synthetic preference assets 不得被 active code 自动读入。

---

## 4. 路线 A：first-order factorized PM

每个 head 只学：

> **当前 state + 当前 eligible exact candidate 本身值不值得开。**

正式 effect contrast 的 canonical background：

> **其他三个 optional resources 全部 OFF。**

- RS：只 toggle RS；MP/MS/ME OFF；
- MP：只 toggle MP；RS/MS/ME OFF；
- MS：只 toggle MS；RS/MP/ME OFF；
- ME：只 toggle ME；RS/MP/MS OFF。

Final head **不读取其他 component ON/OFF bits**。

Runtime 仍可由四个独立决策形成 16 种 resource combination，但 Paper 1 不解释为 interaction-aware optimal action learning。

历史 background-conditioned effects 只属于 future interaction-aware extension，不进入 Paper-1 evidence。

---

## 5. 固定运行链

```text
Current state
   │
   ├─ Strategy candidate ── RS
   ├─ Profile candidate  ── MP
   ├─ Session candidate  ── MS
   └─ Experience candidate ─ ME
                 │
                 ▼
       source-specific eligibility
                 │
        ineligible → deterministic OFF
                 │ eligible
                 ▼
      four first-order L2 heads
                 │
                 ▼
      deterministic budget/conflict projection
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

### 5.1 `ineligible` 不等于 learned OFF

- `ineligible`：candidate absent / wrong owner / future / superseded / conflict / invalid MS / ME 无 action+observed outcome / RS move 被明确 boundary 禁止等；规则直接 OFF，不作为 classifier 负例；
- `positive_open`：eligible 且 ON materially better；
- `nonpositive_off`：eligible 且 OFF better，或 ON/OFF materially equivalent；
- `unknown`：执行或测量不稳定，训练排除。

真正重要的 OFF 是“资源正确但当前没增量”，而不是“垃圾候选被过滤”。

---

## 6. Source-specific eligibility

### RS

- ESConv-train-only Bank；
- current query/state 对齐；
- atomic move 与当前明确 boundary 兼容；
- no hard exclusion；
- recent exact/same-move repetition 可作为 nonredundancy signal。

`listen-only` 只阻挡不兼容 Suggestion/probing Question，不等于整个 RS OFF。

### MP = Profile only

- same owner；
- profile fact 从 public EvoEmo strict-past history 可追溯；
- target 时点有效；
- no current conflict；
- current visible update 优先；
- sensitive profile 无当前相关性不得强行暴露；
- no preference subtype。

### MS

- same owner；
- strictly prior session/event；
- no current/future；
- no last-user-message/current-message fallback；
- entity/time/thread valid；
- current visible update 优先。

### ME

- same owner；
- strictly past；
- explicit action/coping attempt；
- **user-observed outcome**；
- action↔outcome lineage traceable；
- no current conflict；
- ordinary safe transfer scope；
- Step2 只能有限类比，禁止“过去有效→现在一定有效”。

---

## 7. 学习器与 feature 原则

Primary learner：

> **4 个 standardized L2-regularized logistic regression binary heads。**

四头只看 runtime 可见 current state + exact eligible candidate 的 outcome-blind descriptors。

禁止：response、judge、gold answer/strategy/evidence、future、dataset/split identity、opaque ID、construction intent、其他 component bits、preference metadata。

详细 feature schema 见 training contract。

---

## 8. Public-data-only training protocol

### 8.1 RS

Formal RS training/effect data：**ESConv train/dev only**。

### 8.2 MP/MS/ME

Formal memory training/effect data：**ES-MemEval/EvoEmo public artifact only**。

采用 outcome-isolated cross-fitting：

- target question/reference/outcome 不进入为该 target 预测的训练 fold；
- same fact/event cluster targets 同 fold；
- runtime PM 只看 target 时点以前 history；
- gold answer/evidence/reference/future session 禁止；
- same-user 其他 strict-past non-target-cluster history 可以用于 longitudinal adaptation；
- 统计以 18 个 user 为最高 cluster。

这是 **within-benchmark longitudinal adaptation**，不是 untouched zero-shot；论文必须如实声明。

### 8.3 旧 synthetic 数据全部 deprecated

整个目录：

`project/data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/`

以及任何 synthetic 80-user/11-user 派生数据：

> **不得参与 active Paper-1 数据/feature/coverage/qualification/training/evaluation。**

它们仅历史留档，已另有 archive branch 和目录 deprecation marker。

---

## 9. 正式 effect data 前先做 repeated-effect qualification

只用 public-source eligible states：

- 8 states/head × 4 heads = 32；
- 3 independent ON/OFF pairs/state；
- 96 pairs = 192 responses；
- blind A/B；
- second reviewer 固定覆盖 32 pairs。

Gates：

- ≥70% states 达到 2/3 non-uncertain direction 一致；
- inter-reviewer exact agreement ≥75%；
- uncertain ≤10%。

若 fail：禁止批量 single-pair hard labels。

---

## 10. RQ1：Selective Strategy-RAG

正式 arms：

1. R0 / No Strategy-RAG
2. RS Fixed-High
3. RS Matched-Random
4. Learned RS-PM

同 Generator、同 prompt、同 Retriever、同 candidate identity、同 role card × seed、同 scorer。

全部报告 ESC-Eval 官方七维：

- Fluency
- Expression
- Empathy
- Information
- Skillful
- Humanoid
- Overall

Cost 单独报告。

有意义的结论：

- vs R0：不能 material degradation；
- vs Fixed-High：质量非劣时 generator input tokens 至少下降 10% 才算 material efficiency；
- vs Matched-Random：同 ON rate/预算下 Learned 更好，证明 opening location 有信息。

---

## 11. RQ2：Selective typed memory

正式 arms：

1. No Memory
2. Full History
3. Official RAG Top-4
4. Typed Fixed-High
5. Typed Matched-Random
6. Learned Typed-Memory PM

RS 在 ES-MemEval main analysis 固定。

### QA 官方指标

- final answer quality：F1 / BERTScore / LLM-as-Judge；
- retrieval diagnostics：Recall@k / nDCG@k。

### Summarization

- ROUGE-1/2/L；
- Event Precision / Recall / F1；
- official LLM Score。

### Dialogue Generation

- Observation Recall / Weighted Score；
- LT-Memory / Personalization / Emotional Support。

所有官方指标透明报告；不造跨任务总分，不在结果后只挑最有利指标。

---

## 12. Memory component-minus

不重训：

- Learned − MP
- Learned − MS
- Learned − ME

Typed-memory 主张要求至少两个 head 在预冻结 eligible slice 上获得可复现、正向 official-metric-family contribution；否则降级 claim。

---

## 13. Cost 与 integrity

Primary cost：

- generator_input_tokens
- resource_injected_tokens

同时记录 output/total tokens、retrieval/embedding calls、latency、p95、retry、可恢复 API cost。

minimal integrity：wrong owner、future leakage、fabricated personal history、stale/conflict misuse、explicit boundary violation、excessive directiveness、scaffold exposure。

不合成 Risk 总分，不让 Cost 抵消 material quality/integrity failure。

---

## 14. Generator 已冻结后的立即执行顺序

1. **代码迁移**：MP_PROFILE-only；去除 final background-bit features；所有 synthetic 11/80-user active path/config/test 断开；
2. **public zero-outcome coverage audit**：只读 ESConv + ES-MemEval/EvoEmo，统计 RS/MP/MS/ME eligible states、18-user coverage、QA/Summary/DG distribution、ME action→observed-outcome occurrence、feature variance；
3. 冻结 candidate bundle top-k/token caps；
4. 冻结 feature schema与 cross-fit K；
5. 跑 32-state public repeated-effect qualification；
6. 通过后冻结 formal N/split/API call plan；
7. 生成 final matched ON/OFF effect data；
8. training-only blind outcome review；
9. 训练四个 L2 first-order heads；
10. 冻结 thresholds / PM checkpoint / same-stack baselines / matched-random schedules；
11. RQ1 ESC-Eval；
12. RQ2 ES-MemEval；
13. −MP/−MS/−ME；
14. official metrics + Cost + cluster uncertainty + minimal integrity report。

---

## 15. Stop rules

- synthetic 11/80-user 内容进入 active pipeline → invalid；
- MP_PREFERENCE 进入 Paper 1 → invalid；
- final head 读取 background bits → 违反路线 A；
- old MS fallback labels 被复用 → invalid；
- repeated-effect qualification fail → single-pair hard label 禁止；
- public natural evidence 对某 head 不足 → `not identifiable`，不 synthetic rescue；
- Learned ≈ Matched-Random → 没有 selector evidence；
- main outcomes 后改 Generator/prompt/retriever/feature/sample/threshold → exploratory only。

---

## 16. 一句话论文主线

> **Policy Manager 在冻结 Generator 之前，分别学习 Strategy-RAG、Profile Memory、cross-session Memory 与 Experience Memory 的 first-order state×candidate marginal utility。RS 只用 ESConv 训练、由 ESC-Eval 最终测量；MP/MS/ME 只用 ES-MemEval/EvoEmo public longitudinal data 训练，并由 ES-MemEval 官方 QA/Summary/DG 指标测量。PM 价值通过同栈 Fixed/Random/official baselines 与真实 Cost 证明，而不是通过旧 synthetic 数据或自建标签自行宣布。**
