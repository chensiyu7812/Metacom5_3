# Policy Manager（PM）第一篇论文研究包

> **方法名不是 MetaCom。** `Metacom5_3` 仅为历史仓库/工程名称。

## Active authority

按下面顺序阅读：

1. `docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md` — 研究范围与论文 claim；
2. `docs/PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md` — **最新 implementation / measurement / execution authority**；
3. `data/pm_v1_5_contracts/pm_paper1_final_execution_blueprint_20260816_v1.json` — machine-readable execution contract；
4. `data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`；
5. `docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md` — 较早 subordinate training reference；若 implementation detail 冲突，以新的 execution blueprint 为准。

## 三个先行研究资源，两个训练数据源

Paper 1 只使用公开先行研究资源：

- **ESConv**：RS Strategy-RAG 的资源/训练来源；
- **ESC-Eval**：RQ1 正式 evaluation，只评不训；
- **ES-MemEval / EvoEmo**：MP/MS/ME 的 public longitudinal training/candidate source，以及 RQ2 正式 evaluation。

所以：

- active training data source = `ESConv` + `ES-MemEval/EvoEmo`；
- formal evaluation benchmark = `ESC-Eval` + `ES-MemEval`；
- paper 涉及三个 prior-work resources：ESConv、ESC-Eval、ES-MemEval/EvoEmo。

## 旧 synthetic 数据全部退出

旧 synthetic 80-user / tracked 11-user longitudinal 数据不是“待补完训练集”，而是**完全过期路线**。

整个目录：

`data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/`

不得被 active Paper-1 code/agent 读取、采样、审计、修复、编译、训练或引用。

## 当前 Paper-1 一句话定义

Policy Manager 把 **Strategy-RAG（RS）**、**Profile Memory（MP）**、**cross-session Memory（MS）** 与 **Experience Memory（ME）** 视为四种可选外部资源。Retriever/constructor 先产生候选，source-specific eligibility 只判断候选是否合法；四个低容量 L2 logistic heads 分别学习 first-order `state × eligible candidate` marginal utility。正式 effect contrast 时其他 optional resources 全 OFF；运行时四个独立 decision 可以组合，但 Paper 1 不学习高阶 resource interaction。

不可再漂移：

1. **MP = Profile Memory only**；无 MP_PREFERENCE；
2. **路线 A / first-order factorized**；final head 不读 background resource bits；
3. Generator 已冻结，但正式 effect 前必须有 Paper-1 full-stack freeze manifest；
4. 训练数据 public-data-only；
5. **relevance ≠ utility**：feature 只能描述 state/candidate，不能由人工/LLM 前置估计“值不值得开”。

## 最新 feature 原则

允许：fixed similarity、raw type、already-visible/redundancy、relative age、deterministic entity/thread overlap、显式 request marker、结构 token cost。

禁止：`worth_opening`、主观 helpfulness、`mp_response_feasibility_impact`、`mp_profile_scope_specificity`、主观 `transferability`、主观 `continuity_need`、主观 `goal_action_fit`、其他 component bits、preference metadata、response/judge/gold/future。

四头 exact v1 schema、eligibility 与删除项见 `docs/PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md`。

## 正式证据

- RQ1：ESConv train-only -> `R0 / Fixed-High / Matched-Random / Learned RS-PM` -> ESC-Eval 七维 + Cost；
- 因 Strategy Bank 来源于 ESConv，RQ1 primary transfer slice = **non-ESConv-source English role cards**，完整 English set secondary，ESConv-derived slice 单独 sensitivity；
- RQ2：ES-MemEval/EvoEmo -> `No Memory / Full History / Official RAG Top-4 / Typed Fixed-High / Typed Matched-Random / Learned PM` -> ES-MemEval QA/Summary/DG official metrics + Cost；
- Ablation：`Learned - MP / -MS / -ME`，不重训；至少 2/3 memory heads 有可复现正贡献才保留 typed-memory mechanism claim。

## 接下来只按阶段推进

**现在不要直接开正式训练。**

1. repository-to-contract audit；
2. **Phase 0**：active code/CI/config public-only migration，断开 synthetic，移除 MP_PREFERENCE/background bits/utility-like features，加入 fail-closed guard；
3. **Phase 1**：只扫 ESConv + ES-MemEval/EvoEmo 的 zero-outcome coverage audit；
4. **Phase 2**：在任何 formal effect outcome 解封前冻结 candidate bundle/top-k/token cap、exact feature、cross-fit、formal N、task-specific comparator/margin、cost threshold、Generator full-stack manifest、qualification sample 与 API plan；
5. **Phase 3**：32-state repeated-effect qualification；
6. **Phase 4–5**：final matched public-source effect data + 四个 L2 heads；
7. **Phase 6**：冻结 thresholds / same-stack baselines / Matched-Random；
8. **Phase 7–8**：RQ1 ESC-Eval + RQ2 ES-MemEval；
9. **Phase 9**：component-minus + official metrics + Cost + cluster uncertainty + integrity report。

详细 phase gates、已知代码冲突、RS leave-current-dialogue-out leakage rule、memory cross-fitting、training Quality/Risk/Cost 正交规则和 Codex handoff 见最终 execution blueprint。
