# PM V1.5 V5.3 正式失败结果与 V5.4 可学习性恢复

日期：2026-08-09

机器结果：`outputs/pm_v1_5_v5_3_public_formal_oof_20260809/formal_oof_report.json`  
失败诊断：`outputs/pm_v1_5_v5_3_formal_head_failure_diagnosis_20260809/report.json`  
恢复合同：`data/pm_v1_5_contracts/v5_4_semantic_contrast_learnability_recovery_v1.json`

> 2026-08-10 更新：双 reviewer 的 composite candidate suitability 与四原子语义轴都未通过预冻一致性和双向支持门。原合同中“用 reviewer 语义判断产生 should-open gold”的部分已由
> `data/pm_v1_5_contracts/v5_4_factorial_outcome_oracle_learning_v1.json` 取代。公共 anchor 与 outcome-blind current-state contrast 继续保留，但 construction assignment 只负责数据支持和表示可观测性审计；真正调用价值来自随机同状态 outcome。

## 0. 2026-08-10 最终修正：怎样避免再次造出学不会的标签

本次实际校准表明，问题不是把一句复合问题拆成四句就能解决。62 个共同样本中，四轴 agreement 为
`.677–.790`、κ 为 `-.047–.305`，投影后 agreement/κ 仅 `.613/.208`；四组件也都没有足够的共识
OPEN 与 OFF。因此任何 LLM reviewer 的“这段记忆可能有用”都不再充当 PM 金标签。

V5.4 改用以下顺序：

1. 机器只裁决候选存在、owner、strict-past、version、source lineage 和硬安全；Rank-1 只是冻结的生产候选，不是 gold。
2. 围绕公共数据 anchor outcome-blind 地写同候选 current-state 对照，只审核世界忠实、单轴变化可见和无标签泄漏，不审核“应该开”。
3. 在零 outcome 下先测冻结 PM 表示能否 family-held-out 地识别这项受控语义变化；识别不了就停，责任在表示/数据，而不是 PM learner。
4. 通过后才在同状态随机 ON/OFF，使用 requested-action 的真实 deployment ITT Q effect 作为连续训练目标。generator 不使用或 fallback 保留在 ITT 中，同时在机制账本单列，不能被隐藏。
5. 小规模 development 必须先证明 high/low variant 的真实 effect 可分，并且低容量 head 在 family-held-out 上超过均值；否则不启动 fresh formal。
6. head 合格后在 32 个自然 state 上完整运行 16 动作，构造安全、Q 等价、成本最低的 oracle set；正确调用以 oracle inclusion 和 regret 衡量，而不是四个主观二元标签硬拼。

这不能数学保证论文一定得到正结果，但能保证：正式训练启动时，表示已经看得见差异、实际 generator effect 已经随差异变化、低容量 head 已经在未见 family 上学得到；以后再失败，才有资格归因到 PM 泛化，而不是明显不可学习的数据。

## 1. 结论

V5.3 的 576 个正式 paired-effect group 已全部完成：六折各 96，MP/MS/ME/RS 各 144，quality 与
function 完整，transport-repair 目标为零，manifest hash 和 fold 绑定全部通过。但四个冻结 head 均未通过：

| Head | relative MSE | Spearman | 正式结论 |
|---|---:|---:|---|
| MP | 0.955 | 0.236 | 排序过、MSE 差 0.005，仍正式失败 |
| MS | 0.990 | 0.047 | 失败 |
| ME | 1.050 | 0.008 | 失败 |
| RS | 1.017 | -0.006 | 失败 |

因此 V5.3 不能生成 `learned_pm_qualified` 外部主臂，不能把 transparent rule 或 fixed policy 改名为
learned PM，也不能事后放宽门槛或换模型重算为 PASS。

## 2. 不是哪里出了问题

这次失败不是因为：

- 只生成了半批数据：正式分母是完整 576/576；
- component 或 fold 不平衡：每组件 144、每折每组件 24；
- transport 丢失：六折需要 identical replay 的组均为零；
- target 完全恒定：四组件 target 和 prediction 都非恒定；
- 独立 group 数机械不足：memory 有 18 个用户簇，RS 有 144 个 dialogue group；
- 仅仅 Ridge 容量太小：post-hoc 的全部透明标量 Ridge、Huber、浅树和 depth-2 forest 仍不能稳定通过。

## 3. 真正根因

### 3.1 state 主要证明“合法 Rank-1 通常有用”，没有形成可学习的开关条件

正式 target 为正的 group：MP 113/144、MS 106/144、ME 116/144、RS 85/144。候选全部是合法
actual Rank-1，而且 generator 大多能够使用，导致数据更擅长教 fixed-high，而不是教“何时开”。

本来用于解释条件价值的语义变量几乎没有支持：

- MP `profile_goal_needs_advice_or_arrangement=true` 仅 1/144；
- MS `continuity_request=true` 仅 7/144；
- ME `current_action_invitation=true` 仅 1/144；
- memory 的 `current_redundant=true` 不但没有产生低收益，平均 effect 反而更高。

最后一点说明自动特征并没有测到想要的“当前消息已经足够、候选没有边际贡献”。它更可能测到当前文本与候选
同主题，因而让 generator 更容易自然吸收资源。

### 3.2 标签有噪声，但不是完全不可学

三个 seed 的两两 Spearman 大致为 0.35–0.60；按 replicate 聚合后估算的可重复组间信号比例为 MP 0.665、
MS 0.663、ME 0.631、RS 0.576。这不足以支持任意复杂语义，却也没有低到“任何 PM 都不可能学习”。

因此主要责任是：输入侧没有把可重复 effect 差异组织成运行时可观察、跨 family 可运输的条件对比。

### 3.3 BGE 压缩不是统一解法

outcome-open 容量扫描显示，MP 单用 state BGE 的 3–5 PCA 维可达到 relative MSE 约 0.94、Spearman
约 0.236；说明 MP 有一个较弱但真实的语义面。这个结果已经看过正式 outcome，只能用于 V5.4 开发，不能
重判 V5.3。

MS、ME、RS 扩到 10–20 维仍没有稳定改善。继续增加 embedding 维度或模型复杂度只会扩大 overfit 风险，
不会自动创造缺失的 high/low opportunity 对比。

## 4. V5.4 怎样优先保证训练数据可学

V5.4 不生成新的长期用户。它使用 ESConv/EvoEmo 的公共 source anchor，只生成 outcome-blind current-state
variants 与正式 paired whole responses。

一个训练 family 固定同一 public anchor、同一 owner/time/version-valid candidate，再产生 2–4 个 current-state
变体，覆盖：

1. 候选有明确且具体的当前贡献槽；
2. 当前消息已包含等价信息，候选相关但不增量；
3. 用户明确或隐含拒绝该资源功能；
4. 同主题但当前 response act 不匹配；
5. explicit cue 与自然 paraphrase/implicit cue；
6. 长度、标点、模板、主题和 candidate age 等 nuisance 配平。

construction condition 只用于设计与审计，不能进入 effect label，也不能直接进入 worth-opening 标签。模型只可读取
经独立语义门验证、运行时确实可得到的 observation。

## 5. 三道门与责任

### 门 A：语义可观测性，零 effect API

每组件至少 48 variants、12 families。双人盲标 runtime-visible condition，family-held-out macro-F1 至少
0.80，critical boundary recall 至少 0.90，owner/time/version 和未来泄漏为零。若失败，责任在 semantic
observation/data construction，禁止花 effect API 预算。

### 门 B：effect feasibility，128 groups

每组件 16 families × high/low 两个 primary variants × 三个 paired seeds。每组件必须同时达到：

- high-minus-low 平均 uplift 至少 0.12；
- family 方向一致率至少 0.70；
- two-seed mean 到 third-seed Spearman 至少 0.35；
- clean ON functional use 至少 0.80；
- wrong owner/future critical event 为零。

若语义门已过但这里失败，责任在 state contrast、资源实际效用、Step2 generator 或 effect measurement，不能把
问题写成 PM 没学会。

### 门 C：fresh confirmation，384 groups

只有 A、B 同时通过后，才冻结每组件 48 个新 family × high/low 两个 variants，共 96 group/组件、384 总组。
family 必须整组进同一 fold。模型、features、threshold、fold、prompt 和 seed 在 outcome 前一次冻结。

正式 head 仍需 relative MSE ≤0.95、Spearman ≥0.15，并与 transparent rule 比较。失败 head fail closed。

## 6. Baseline 与外部实验

V5.3 已冻结的 baseline 矩阵继续有效：always-off、fixed-high-eligible、transparent-rule、qualified learned、
qualified cost-matched-fixed、qualified cost/on-rate-matched-random。ES-MemEval 仍使用五条件 QA 设计。

但在 V5.4 至少一个可部署 learned head set 和 joint projection 冻结之前，不运行 learned external 主臂。ESConv、
EvoEmo response 与 ES-MemEval 的源数据可继续做零 outcome 的准备审计，不能提前打开正式测试结果。

## 7. “保证学会”的准确含义

不能保证科学结果一定好看。可以保证的是：在正式训练前先证明输入语义可观测、high/low state 的真实 effect
可分、Step2 能做功、标签有 seed 可重复性。这样如果正式 OOF 再失败，才有资格说是 PM 模型的责任；不会再像
V5.3 一样，先花完 576 组才发现训练数据没有提供清晰的开关条件。
