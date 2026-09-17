# Paper 1 四任务 paired-effect 编码草案（2026-08-16）

状态：`PRE_OUTCOME_IMPLEMENTATION_DRAFT_AWAITING_EXPLICIT_RULE_FREEZE`。本文件低于现有 execution reconciliation 与 frozen research program；它提出一个可测试的无权重 Pareto overlay，但官方 benchmark 本身只给出多指标向量，并未规定如何把向量压成单个 ON/OFF 训练结果。在该 overlay、scorer identity 与 seed schedule 被明确预冻结前，不授权正式 outcome 调用。

## 1. 共同语义

对固定 state、固定 candidate、固定 Generator stack，比较 matched `ON` 与 `OFF`。原始结果始终保留为：

- `on_better`：进入 likelihood，target = 1；
- `off_better`：进入 likelihood，target = 0；
- `equivalent`：可靠的非正增益，进入 likelihood，target = 0；
- `uncertain`：指标方向冲突或 scorer 无法可靠区分，不进入 likelihood；
- `invalid`：技术交付、身份、泄漏、绑定或解析失败，不进入 likelihood，并保留 integrity reason。

Cost 不参与标签。semantic non-use 不使 pair invalid。这里没有经验性 PASS 门、最小效应百分比或 `2/3` 硬标签；重复 seed 后直接汇总为 binomial positive-effect target。

## 2. 四任务规则

### RS / ESC response

ESC-Eval 七维仅用于正式 RQ1 能力评价，不替代 RS 的训练标签。RS 训练使用 blind ON/OFF pairwise weak supervision，编码器只接受 `ON better / OFF better / equivalent / uncertain` 原始 verdict；确切 judge 模型、prompt 与 fail-closed parser 尚待冻结。

### 多指标共同草案规则

对 QA、Summary 与 DG，目前的项目草案不设 primary/guard、不加权、不丢弃任一官方能力维度：

- 所有官方指标 exact tie：`equivalent`；
- 所有非零指标方向均为 ON：`on_better`；
- 所有非零指标方向均为 OFF：`off_better`；
- 同时存在正向和反向指标：`uncertain`。

这是项目提出的 conservative Pareto coding，**不是官方 scorer 自带规则，也尚未冻结**。它避免自创权重或让某一维抵消另一维；代价是 uncertain 可能较多，正式调用前必须明确接受或替换。

### QA

方向向量完整包含官方 F1、BERTScore、`LLM-as-Judge` 0–2 三项。Recall@k 与 nDCG@k 是 retrieval diagnostics，不进入 realized generation effect 标签。

### Summary

用官方 judge 返回的离散 event counts 精确计算：

\[
EventF1=\frac{2\cdot recalled}{reference+generated}.
\]

方向向量完整包含 ROUGE-1/2/L、Event Precision/Recall/F1 与官方 0–5 LLM Score。若 ON/OFF 的 reference-event count 不一致，说明同一 reference 的 judge extraction 不稳定，记为 `uncertain`。

### Dialogue Generation

严格复现官方代码协议：10 个 interaction rounds，即 20 条生成 role utterances，另有一条固定 supporter greeting。Observation 指标只聚合第 1–5 轮；相关度 1/2/3 映射为权重 0/1/2。方向向量完整包含 Observation Recall、Weighted Score，以及全 10 轮的 LT-Memory、Personalization、Emotional Support（各 1–5）。第 1–5 轮与全部预期 observation 的网格必须完整；缺行、重复行或内部不一致一律不能形成标签。

决定方向时使用整数与 `Fraction` 精确比较，不引入 0.01、5% 或其他人为 margin。

## 3. 尚未解除的正式调用 blocker

1. 上述全官方维度 Pareto coding 必须明确接受或替换；目前只是项目草案。
2. RS blind pairwise judge 的确切模型、prompt、parser 尚未冻结。
3. 官方 ES-MemEval 代码写的是移动别名 `gpt-4o`，正式运行需冻结可复现 identity，或明确记录 provider snapshot 的不可完全复现限制。
4. DG turn judge 的 `Mistral-Small-3.1-24B-Instruct-2503` 需绑定确切本地权重 revision。
5. repeated-effect seed schedule 尚未冻结。

因此当前完成的是 scorer source audit 和纯函数编码，不是 outcome measurement。`outcome_calls = 0`，`training_calls = 0`。

## 4. 审计入口

- 实现：`src/metacom_pm/paper1/evaluation/effect_coding.py`
- 测试：`tests/test_paper1_effect_coding.py`
- pinned source audit：`data/paper1_authority/paper1_official_scorer_surface_audit_v1.json`
- 构建脚本：`scripts/paper1/05_build_official_scorer_surface_manifest.py`
