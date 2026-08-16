# Policy Manager（PM）第一篇论文研究包

> **方法名不是 MetaCom。** `Metacom5_3` 仅为历史仓库/工程名称。
>
> Active authority：
> - `docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
> - `data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
> - `docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`

## 三个先行研究资源，两个训练数据源

Paper 1 只使用公开先行研究资源：

- **ESConv**：RS Strategy-RAG 的资源/训练来源；
- **ESC-Eval**：RQ1 正式 evaluation，只评不训；
- **ES-MemEval / EvoEmo**：MP/MS/ME 的 public longitudinal training/candidate source，以及 RQ2 正式 evaluation。

所以：

- active training data source = `ESConv` + `ES-MemEval/EvoEmo`（两个）；
- formal evaluation benchmark = `ESC-Eval` + `ES-MemEval`（两个）；
- paper 涉及三个 prior-work resources：ESConv、ESC-Eval、ES-MemEval/EvoEmo。

## 旧 synthetic 数据全部退出

旧 synthetic 80-user / tracked 11-user longitudinal 数据不再是“没完成的训练集”，而是**完全过期的旧路线**。

整个目录：

`data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/`

已标注 `DEPRECATED_DO_NOT_USE_FOR_PAPER1.md`；Codex/agent 不得为 Paper 1 阅读、采样、审计、修复、编译、训练或引用其中数据。归档 branch 仅用于历史 provenance。

## 当前 Paper-1 一句话定义

Policy Manager 把 **Strategy-RAG（RS）**、**Profile Memory（MP）**、**cross-session Memory（MS）** 与 **Experience Memory（ME）** 视为四种可选外部资源。四个 L2 logistic heads 分别学习 first-order state×candidate marginal utility；正式 effect contrast 时其他 optional resources 全 OFF；运行时四个独立决定可以组合，但 Paper 1 不学习高阶 resource interaction。

不可再漂移：

1. **MP = Profile Memory only**；无 MP_PREFERENCE。
2. **路线 A / first-order factorized**；final head 不读 background resource bits。
3. **Generator 已冻结。**
4. **训练数据 public-data-only。**

## 正式证据

- RQ1：ESConv train-only -> `R0 / Fixed-High / Matched-Random / Learned RS-PM` -> ESC-Eval 七维 + Cost。
- RQ2：ES-MemEval/EvoEmo public longitudinal data -> `No Memory / Full History / Official RAG Top-4 / Typed Fixed-High / Typed Matched-Random / Learned PM` -> ES-MemEval QA/Summary/DG official metrics + Cost。
- Ablation：`Learned - MP / -MS / -ME`，不重训。

## 当前执行顺序

1. 断开所有 synthetic 11/80-user active path/config/test；
2. MP 改为 public MP_PROFILE-only，删除 final background-bit features；
3. 只扫 ESConv + ES-MemEval/EvoEmo 做 zero-outcome coverage audit；
4. 冻结 candidate bundles / feature schema / cross-fit；
5. public-source 32-state repeated-effect qualification；
6. 通过后生成 final matched ON/OFF effect data；
7. 训练四个 L2 first-order heads；
8. 冻结 thresholds / same-stack baselines / Matched-Random；
9. RQ1 ESC-Eval；
10. RQ2 ES-MemEval；
11. component-minus；
12. official metrics + Cost + cluster uncertainty + minimal integrity。
