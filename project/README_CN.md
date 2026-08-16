# Policy Manager（PM）第一篇论文研究包

> **方法名不是 MetaCom。** `Metacom5_3` 仅为历史仓库/工程名称。
>
> **2026-08-16 起唯一研究主线：**
> `docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260816_ZH.md`
>
> **机器可读冻结合同：**
> `data/pm_v1_5_contracts/pm_final_frozen_research_program_20260816_v2.json`
>
> **正式训练合同：**
> `docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`
>
> 仓库根目录 `AGENTS.md` 对 Codex/其他 agent 固定了防漂移规则。2026-08-14 authority 及更早 PM-v1/v1.5/v2/V3/V5、synthetic-user、EvoEmo external、Function/Risk/Quality gate 文档和代码保留为历史/诊断/可复用实现证据；若冲突，以 2026-08-16 authority 为准。

## 当前 Paper-1 一句话定义

Policy Manager 把 **Strategy-RAG（RS）**、**Profile Memory（MP）**、**cross-session Memory（MS）** 与 **Experience Memory（ME）** 视为四种可选外部资源。Retriever/candidate layer 负责找具体候选；Step 1 的四个低容量二分类 head 分别学习 first-order state×candidate marginal utility；Step 2 只执行已经批准的资源；冻结 Generator 负责生成自然语言。

### 两条不可再漂移的修正

1. **MP = Profile Memory only。** `MP_PREFERENCE` / `response_preference_history` 不属于 Paper 1。
2. **Paper 1 采用路线 A / first-order factorized PM。** 每个 component 的正式 ON/OFF effect contrast 都在“其他 optional resources 全 OFF”的 canonical background 下产生；其他 component ON/OFF bits 不进入 final head features。16 个 runtime combination 仍保留，但不学习高阶 interaction。

Primary learner 仍是四个 **L2-regularized logistic regression** heads；监督来自 matched ON/OFF component-effect labels；不训练 16-class classifier，也不把 RS 改成 ESConv strategy-category predictor。

## 第一篇正式证据结构

- **Generator：** 已在本次训练设计更新前冻结；后续不得根据 PM 结果再换。
- **RQ1 / Selective Strategy-RAG：** ESConv train-only 构建/训练 Strategy-RAG，最终在 ESC-Eval 上比较 `R0 / RS Fixed-High / RS Matched-Random / Learned RS-PM`。
- **RQ2 / Selective typed memory：** ES-MemEval 上比较 `No Memory / Full History / Official RAG Top-4 / Typed Fixed-High / Typed Matched-Random / Learned Typed-Memory PM`。
- **Ablation：** `Learned - MP / -MS / -ME`，不重新训练 PM。
- **Official metrics：** ESC-Eval 与 ES-MemEval 原指标全部透明报告；不造跨任务自定义总分，不在结果后只挑对 PM 有利的指标。
- **Cost：** generator input tokens、resource-injected tokens、latency、total tokens、API cost 等独立报告。

## 当前数据 readiness

现有 longitudinal/profile/MS/ME/old effect artifacts 是有价值的开发资产，但**最终 Paper-1 effect-training dataset 尚未完成**：

- tracked formal longitudinal intake 不是完整 80-user corpus；
- preference 数据必须排除；
- old 256 effect labels 只作 heterogeneity diagnostic；
- old MS effect labels 不符合 strictly-prior MS construct，正式训练必须重做；
- final route A 需要重新生成 canonical-background matched effects；
- full-scale labels 前必须先通过 repeated-effect measurement qualification。

Paper 1 不再要求先补完 synthetic 80-user corpus。RS 直接使用 ESConv train-only；MP/MS/ME 优先使用 ES-MemEval/EvoEmo strict-past histories，并采用 outcome-isolated cross-fitting。

## 当前执行顺序

1. 迁移代码到 MP_PROFILE-only，删除 final head background-bit features；
2. 跑 zero-outcome ES-MemEval/EvoEmo coverage audit；
3. 冻结 candidate-bundle top-k/token caps 与 final feature schema；
4. 跑 32-state repeated-effect qualification；
5. qualification 通过后冻结 formal N/splits/call plan；
6. 生成 final RS/MP/MS/ME matched ON/OFF effect data；
7. 训练四个 L2 first-order heads；
8. 冻结 thresholds、same-stack baselines、matched-random schedules；
9. 跑 RQ1 ESC-Eval；
10. 跑 RQ2 ES-MemEval QA/Summary/DG；
11. 跑 MP/MS/ME component-minus ablation；
12. 汇总 official metrics + Cost + cluster-aware uncertainty + minimal integrity diagnostics。

详细 feature schema、effect row、数据复用/重做边界、qualification gates 和 formal N 冻结规则见 `docs/PM_FINAL_TRAINING_CONTRACT_20260816_ZH.md`。
