# Policy Manager（PM）第一篇论文研究包

> **方法名不是 MetaCom。** `Metacom5_3` 仅为历史仓库/工程名称。
>
> **2026-08-14 起唯一研究主线：**
> `docs/PM_FINAL_FROZEN_RESEARCH_PROGRAM_20260814_ZH.md`
>
> **机器可读冻结合同：**
> `data/pm_v1_5_contracts/pm_final_frozen_research_program_20260814_v1.json`
>
> 仓库根目录 `AGENTS.md` 对 Codex/其他 agent 固定了防漂移规则。旧 PM-v1/v1.5/v2/V3/V5、synthetic-user、EvoEmo external、Function/Risk/Quality gate 文档和代码保留为历史/诊断/可复用实现证据；若与 2026-08-14 authority 冲突，以新 authority 为准。

## 当前 Paper-1 一句话定义

Policy Manager 把 **Strategy-RAG（RS）** 与三类长期记忆 **MP/MS/ME** 视为四种可选外部资源。Retriever/candidate layer 负责找具体候选；Step 1 的四个低容量二分类 head 决定当前是否值得使用；Step 2 只执行已经批准的资源；冻结 Generator 负责生成自然语言。

Primary learner 是四个 **L2-regularized logistic regression** heads，监督信号来自 matched ON/OFF component-effect labels；不训练直接 16-class classifier，也不把 RS 改成 ESConv strategy-category predictor。

## 第一篇正式证据结构

- **RQ0 / Generator qualification：** ESC-Eval。
- **RQ1 / Selective Strategy-RAG：** ESConv train-only 构建/训练 Strategy-RAG，最终在 ESC-Eval 上比较 `R0 / RS Fixed-High / RS Matched-Random / Learned RS-PM`。
- **RQ2 / Selective typed memory：** ES-MemEval 上比较 `No Memory / Full History / Official RAG Top-4 / Typed Fixed-High / Typed Matched-Random / Learned Typed-Memory PM`。
- **Ablation：** `Learned - MP / -MS / -ME`，不重新训练 PM。
- **Cost：** 真实记录 generator input tokens、resource-injected tokens、latency、total tokens、API cost 等；目标是官方 benchmark performance 不出现 material degradation 时减少资源/生成成本。

Published historical baseline scores 只作参考。正式 PM 主张必须在同一个冻结 Generator、同一个 task prompt、同一个 scorer 下重跑 same-stack baselines。

## 当前执行顺序

1. 完成正在运行的 ESC-Eval Generator qualification；
2. 冻结一个 Generator；
3. 做 bounded official-protocol sanity reproduction；
4. 冻结 Strategy Bank、strict-past typed memory catalog 和 training-only outcome measurement；
5. 生成 RS/MP/MS/ME matched ON/OFF effect labels；
6. 训练四个 L2 logistic heads；
7. 冻结 PM、same-stack baselines、matched-random schedules；
8. 跑 RQ1 ESC-Eval；
9. 跑 RQ2 ES-MemEval QA/Summary/DG；
10. 跑 MP/MS/ME component-minus ablation；
11. 汇总 official metrics + Cost + cluster-aware uncertainty + 最小 integrity diagnostics；
12. main outcomes 解封后不得改变 Generator、prompt、retriever、margin、sample subset 或成功定义。

详细字段、baseline、表格模板、统计单位、success/stop rules、责任划分与防泄漏要求全部见唯一 authority 文档。