# Policy Manager Paper 1 执行统一修正（2026-08-16）

状态：`ACTIVE / HIGHEST-PRECEDENCE PAPER-1 EXECUTION OVERRIDE / PRE-OUTCOME`

机器合同：`project/data/paper1_authority/paper1_execution_reconciliation_20260816_v1.json`

本文件只修正现有 authority 中仍残留、但已被研究者明确否决的执行规则。未被本文件覆盖的路线 A、public-data-only、四头 ontology、官方 benchmark 优先级与同栈实验要求继续有效。

若本文件与 2026-08-16 的 frozen research program、official-evaluation priority、execution blueprint、training contract 或旧 V5.3 实现冲突，**以本文件为准**。

## 1. 已冻结且不得重开的选择

- Generator 已最终选定为 NVIDIA hosted NIM 的 `meta/llama-3.1-8b-instruct`；RQ0 研究选择已完成，不再重新比较模型。
- Paper 1 使用路线 A：每个 head 的 effect contrast 中其他 optional resources 全 OFF；runtime 可组合独立 head，但不学习 interaction。
- 正式能力结论只来自 ESC-Eval / ES-MemEval 官方指标；Cost 是独立效率轴；内部 Q/R 只用于 RS 弱监督或补充诊断。
- ES-MemEval 主任务名称固定为 `ES-MemEval-Public-v1.0.0-1427`。这是 pinned public artifact，不是论文 1209-QA 行级精确复现。

## 2. 训练目标改为 materially-positive realized effect

每个 eligible state 保存全部 repeated ON/OFF 原始结果：`ON better`、`OFF better`、`equivalent`、`uncertain` 与 `invalid`。不得先用 `2/3`、70% 或其他比例制造 hard PASS state，也不得把 uncertain 与机械 invalid 混为一类。

Primary estimand 是：

```text
q_h(x,c) = P(Y_ON materially better than Y_OFF | x, c, frozen stack)
```

其中 `materially better` 与 `equivalent` 必须按 ESC response、QA、Summary、DG 的官方 outcome surface 分任务在 M2 预冻结，不能看过正式结果后改。训练计数固定为：`ON better = 1`；`OFF better = 0`；`equivalent = 0`；`uncertain = missing`；`invalid = missing + integrity record`。因此：

```text
positive_effect_fraction = on_better / (on_better + off_better + equivalent)
```

可用 repeats 的数量进入 binomial likelihood/样本权重；不另设 minimum-N PASS gate。原始五类 outcome 必须保留，供 uncertainty、measurement quality 与错误分析使用。这个 learner 估计的是“出现实质正收益的概率”，不是 Quality、Risk、Cost 或任意 utility magnitude。Cost 不进入 label、loss、`CostWorthIt` 或 `positive_open` 派生门。

Primary policy rule 预冻结为：

```text
eligible AND predicted_positive_effect_probability > 0.5 -> ON
```

`0.5` 是透明的 policy rule，不是论文合格线。OOF calibration、Brier、log loss 与 threshold/ON-rate 曲线只作报告和敏感性分析，不设 calibration PASS gate，不看结果后换 primary threshold。

## 3. 取消经验性 PASS gate

以下旧规则全部退出 active Paper-1 执行：

- state direction reproducibility ≥70%；
- inter-reviewer exact agreement ≥0.75；
- uncertain fraction ≤0.10；
- minimum 96/128 effect groups；
- minimum 10% cost reduction；
- MP/MS/ME 至少 2/3 heads 才能保留主张；
- internal Quality/Risk/Cost 组成 Paper-1 PASS/FAIL。

Repeated pairs 继续保留，用于 soft/noise supervision 和 uncertainty。公开数据自然 coverage 不足时报告 realized N、coverage 与不确定性，并收缩该 head 的 claim；不得 synthetic rescue，但也不得用任意数字宣布研究禁止继续。

## 4. measurement validity 的唯一 hard-invalid 边界

只允许机械、可复核的完整性错误使 row/run invalid：

- compiler/schema 无法形成 treatment；
- ON prompt 未包含冻结 resource block，或 block 被错截断、错绑定；
- wrong owner、future、gold/reference leakage；
- arm/seed/prompt/candidate identity mismatch；
- API 空输出、终止失败或 official scorer 无法解析。

资源已经正确送达 Generator 后，Generator 忽略、误用、没有提及或导致结果变差，都是**有效的 realized end-to-end treatment effect**，不得用 post-treatment semantic-use checker 删除。semantic adoption 只可作为 mediator/diagnostic。

因此活动 schema 使用 `treatment_delivery_trace`，不使用含糊的 `semantic_execution_pass` 作为纳入条件。

## 5. 最小必要 cross-fitting

Paper 1 明确是 `within-benchmark cross-fitted longitudinal adaptation`，不主张 untouched-user zero-shot。

Primary grouping 必须机械化：

1. 同一 target 的 ON/OFF、全部 seeds/repeats/candidates/arms 同 fold；
2. QA 按 `owner + question_group_id`；
3. Summary 按 `owner + summary target + exact evidence/reference-set fingerprint`；
4. DG 按 `owner + topic/scenario id`，完整 10-round scenario 同 fold；
5. 跨任务只在 exact canonical target/evidence-set fingerprint 相同时 union；
6. 广义 shared-session / semantic fact-event connected component 只作为 strict sensitivity，不作为 primary 强制分组。

target gold/reference/outcome 只能由 evaluator 读取。正式 RQ2 分数必须来自 fold-specific PM 的 OOF decisions 与 fresh frozen evaluation generations；全数据 checkpoint 只能用于论文后的部署。

## 6. 正式证据结构，不设论文总 PASS

- Learned vs R0：资源系统整体价值；
- Learned vs Matched-Random：相同 realized ON rate / **相同 injected-token budget** 下的 state-dependent selection 价值；若原始候选长度不能精确匹配，须在正式运行前冻结 padding/token-bin construction，不得以“相近”替代主对照；
- Learned vs Fixed-High：官方能力与客观成本的 tradeoff；
- RQ2 Typed Fixed-High：区分 typed representation 与 learned selection；
- `-MP/-MS/-ME`：逐头按官方指标报告贡献，支持几头就主张几头。

RQ1 报告 ESC-Eval 七维完整 outcome family；核心是预注册 contrast，不把饱和的单一 `Overall` 变成唯一裁判。RQ2 不造跨 QA/Summary/DG composite。

所有正式结果报告 paired effect、dialogue/user clustered uncertainty 与 Cost；不得把 CI、effect size 或 head 数量转换成自定义 PASS/FAIL。

## 7. outcome lock 与下一步

在 public-only zero-outcome census 完成并生成 freeze manifest 前：

- 不调用正式 ON/OFF effect outcome；
- 不训练正式 PM；
- 不打开正式 benchmark outcome；
- 允许做固定样本、只看 finish reason/token usage 的 256/512 ESC cap 工程检查，但不得读取 ESC capability score 来选 cap。

zero-outcome census 后一次性冻结 candidate/bundle、feature schema、exact fold grouping、四类任务的 materially-better/equivalent/uncertain/invalid coding、Generator/Step2/runtime manifest、seed schedule、primary threshold 和 matched-random construction。正式 N 使用 outcome-blind 的 available/budgeted sample 并报告 realized N，不设效果资格线。

## 8. 一句话冻结

> 同行官方指标评价最终能力；Matched-Random 识别 selection value；Cost 单独评价效率；训练只学习 materially-positive realized paired effect 的概率；硬失败只保护实验完整性，不再发明经验性通过门。
