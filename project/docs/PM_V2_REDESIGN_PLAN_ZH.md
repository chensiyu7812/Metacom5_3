# MetaCom PM-v2：重新设计、数据、标签、训练与验证方案

## 1. 为什么不是在 PM-v1 上改一个 epsilon

PM-v1 的外部结果暴露了四个相互关联的问题：

1. synthetic current-user text 过少，user-fold 仍复用了 semantic family；
2. 拟合型 TF-IDF 在 EvoEmo 自然表达上覆盖明显下降；
3. silver response/risk 标签存在低区分度，原 `overall` 与 support 字段完全重复；
4. 冻结选择规则是 quality-first、risk-filtered、cost tie-break，`epsilon=0` 使成本几乎不参与决策。

因此 PM-v2 不是“调参补丁”，而是保持 16 个动作不变、重新设计完整学习链路。

## 2. PM-v2 的核心目标

PM-v2 必须可学习并可验证地完成：

- 在无需外部资源时选择 `M0+R0`；
- 在需要历史但不需要策略卡时选择如 `ME+R0`；
- 在 Strategy RAG 有边际收益时开启 RS；
- 在不同状态下选择不同 MP/MS/ME 组合；
- 将预测质量、风险、成本和不确定性同时纳入最终 utility，而不是仅用成本打破并列；
- 在严重 OOD 时使用预注册保守回退并记录，而不是静默外推。

## 3. 数据重新生成

### 3.1 数据来源边界

- 仅使用训练许可的 seed dialogues / role cards 作为题材启发；
- 不使用 EvoEmo test states、test responses 或 test judge labels 生成 PM-v2 开发数据；
- train、calibration、internal-test 的用户、semantic family、normalized current text 全部不重叠；
- 每个状态都保留 `M0+R0`，确保 abstention 在训练中真实可学。

### 3.2 强制覆盖的 resource-need regimes

每个数据批次必须覆盖：

- context only；
- profile needed；
- summary needed；
- event needed；
- multi-source needed；
- memory harmful；
- strategy helpful；
- strategy harmful；
- ambiguous / several actions competitive。

这些 regime 只用于数据覆盖和审计，绝不暴露给 PM。

### 3.3 生成输出

`scripts/20_generate_pm_v2_development_data.py` 输出：

- `pm_v2_bundles.jsonl`：完整 synthetic longitudinal bundles；
- `pm_v2_states.jsonl`：PM-v2 pre-retrieval states；
- `runtime_states.jsonl`：兼容既有 16-action sweep；
- `memory_backend.jsonl`：兼容既有 retrieval/generation；
- `pm_v2_data_report.json`：split、regime、重复和覆盖审计。

## 4. 标签重新设计

### 4.1 不再让 LLM 输出 Overall

PM-v2 judge 只输出六个独立维度：

- emotional support；
- personalization；
- memory appropriateness；
- factual grounding；
- temporal consistency；
- non-intrusiveness。

原始 judge schema 中不存在 `overall` 字段。若论文需要 composite，只能使用配置文件中冻结的确定性 `pmv2-quality-v1`，并同时报告全部子维度。

### 4.2 多 judge family 与 fail-closed gate

- 每条正式训练标签至少来自两个声明独立的模型 family；
- 取各维度中位数；
- 记录 MAD；
- judge family 不足、可靠标签率低、维度恒定或两维逐行重复率超过 98% 时，整个标签批次 FAIL；
- forced-swap pairwise 仅用于 audit，不再作为唯一质量标签来源。

### 4.3 风险与质量分开

风险 judge 单独评价：

- selected-context misuse；
- unnecessary exposure；
- stale/conflicting use；
- unsupported personal claim；
- memory omission；
- strategy overuse；
- strategy omission。

成本直接来自 generation logs，不由 LLM 打分。

## 5. 表示与模型

### 5.1 取消 fitted TF-IDF 作为主文本表示

PM-v2 默认使用固定 word hashing + char hashing，因此新词不会无声变成全零。若存在预计算语义 embedding，可追加到状态表示；没有 embedding 时仍可运行并显式记录 feature mode。

### 5.2 直接预测多维 action outcomes

对每个 state-action 预测六个 response dimensions 和七个 risk dimensions。模型采用 state-group bootstrap ensemble，输出 mean 与 uncertainty，而不是只给一个无置信度的分数。

### 5.3 训练权重

同一 state 的所有动作总权重相同，避免某些 action-availability 较多的状态支配训练。每个 bootstrap 按 state_id 抽样，不能把同一状态的动作拆散造成伪独立。

## 6. 选择规则

PM-v2 的选择不是 quality winner-take-all：

1. 预测每个动作的 response dimensions、risk dimensions 和 uncertainty；
2. 计算 quality lower confidence bound 和 risk upper confidence bound；
3. 风险超阈值的动作排除；
4. memory-on 动作必须通过相对 `M0+R0` 的 resource-benefit gate，或 M0 omission risk 明确过高；
5. RS 动作必须通过相同 memory subset 下相对 R0 的 strategy-benefit gate，或 R0 strategy-omission risk 明确过高；
6. 对剩余动作直接计算：

```
conservative utility
= quality LCB
- risk_weight × risk UCB
- cost_weight × normalized cost
```

7. 选择 utility 最大的动作；
8. 严重 OOD 时执行预注册 fallback，默认 `M0+R0`。

成本从一开始进入 utility，不再只处理并列。

## 7. Split 与校准

- train：训练 outcome heads；
- calibration：只用于选择 risk/cost weights、resource/strategy gain threshold；
- internal test：只评一次；
- external EvoEmo：只在完整冻结后运行。

禁止在 external results 上反向选择阈值、权重或 composite。

## 8. 必须超过或正面报告的基线

PM-v2 外部评测至少包括：

- Context Only (`M0+R0`)；
- Cost-Matched Event Memory (`ME+R0`)；
- 一个与 PM-v2 observed token cost 最接近的 fixed action；
- Structured high-resource baseline；
- Raw Session Top-k；
- Full History。

若 PM-v2 未超过同预算 fixed action，必须如实报告，不能只和 full history 比。

## 9. 不可协商的自动测试

`tests/test_pm_v2.py` 检查：

- judge schema 禁止 `overall`；
- M0+R0 可以被选择；
- memory-on + R0 可以被选择；
- cost 直接影响 utility；
- severe OOD fail-closed；
- joint split overlap 直接失败。

正式运行还必须通过：

- action sweep 完整性；
- judge family 独立性；
- duplicate-dimension gate；
- reliable-label-rate gate；
- user/semantic/text 三重 split audit；
- internal test 上与 cost-matched fixed baseline 的比较；
- 关键外部 claim 的 forced-swap 或小规模人工复核。

## 10. 运行顺序

```bash
# A. 生成 longitudinal development data（先 dry-run）
python scripts/20_generate_pm_v2_development_data.py \
  --seed-dialogues data/esconv/train_seed_dialogues.jsonl

# B. 使用既有 16-action sweep，输入改为 data/pm_v2/runtime_states.jsonl
python scripts/06_run_action_sweep.py \
  --runtime data/pm_v2/runtime_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --out-dir outputs/pm_v2_sweep

# C. 多 family judging（先 dry-run）
python scripts/21_judge_pm_v2_action_sweep.py \
  --judge-endpoints judge_openai,judge_anthropic

# D. 训练、calibration、internal test
python scripts/22_train_pm_v2.py

# E. 完整冻结后，先只在 external states 上看动作与 OOD
python scripts/23_select_pm_v2_actions.py \
  --runtime outputs/evoemo_fixed/runtime_states.jsonl
```

## 11. 诚实边界

这套代码解决的是 PM-v1 已确认的结构性问题，并提供 fail-closed tests。它不能在没有实际生成、judge、人工校准和 external evaluation 的情况下保证 PM-v2 必然超过所有基线。任何“保证一定成功”的承诺都会违反研究方法。正确标准是：数据、标签、代码和阈值均预先冻结，强基线齐全，结果无论正负都能被复现和解释。
