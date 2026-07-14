# MetaCom PM-v2：重新设计、数据、标签、训练与验证方案

> PM-v1 的完整失败、限制、负面结果与根因复盘见：
> [`PM_V1_FAILURE_LIMITATION_POSTMORTEM_ZH.md`](PM_V1_FAILURE_LIMITATION_POSTMORTEM_ZH.md)。

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

注意：PM 是一条 learned policy；16 个选项是 resource actions，不是 16 个不同 policy。

## 3. 数据重新生成

### 3.1 Train-only seed lineage

`scripts/18_prepare_pm_v2_seed_dialogues.py` 只允许从有明确 train split 的原始数据中抽取 seed dialogues：

- 不自动猜测缺失 split 的样本；
- 若原始文件没有 split，必须显式提供 train dialogue IDs；
- 可显式排除与外部评测有关的 dialogue IDs；
- 输出 seed 文件与 lineage audit、源文件哈希和输出哈希。

### 3.2 数据来源边界

- 仅使用训练许可的 seed dialogues / role cards 作为题材启发；
- 不使用 EvoEmo test states、test responses 或 test judge labels 生成 PM-v2 开发数据；
- train、calibration、internal-test 的用户、semantic family、normalized current text 全部不重叠；
- 每个状态都保留 `M0+R0`，确保 abstention 在训练中真实可学。

### 3.3 强制覆盖的 resource-need regimes

每个 synthetic user bundle 必须恰好包含以下九类状态：

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

### 3.4 生成输出

`scripts/20_generate_pm_v2_development_data.py` 是可断点续跑、可重试、fail-closed 的数据生成入口，输出：

- `pm_v2_bundles.jsonl`：完整 synthetic longitudinal bundles；
- `pm_v2_states.jsonl`：PM-v2 pre-retrieval states；
- `runtime_states.jsonl`：兼容既有 16-action sweep；
- `memory_backend.jsonl`：兼容既有 retrieval/generation；
- `pm_v2_data_report.json`：split、regime、重复、配置和 seed lineage 审计。

## 4. 严格的 pre-retrieval 因果边界

PM-v2 可使用：

- 当前用户文本、近期对话、session summary；
- source availability、count、age、estimated size；
- 缓存的 source-level catalog centroid 及其与当前 query 的 centroid similarity。

PM-v2 不可使用：

- actual memory snippets；
- selected memory IDs；
- item-level top-1、max 或 P90 similarity；
- 针对当前状态的 conflict oracle；
- generated response、judge score 或未来状态。

训练数据中可保留 stale/conflict ground truth 用于风险标签和审计，但当前状态冲突标记不会进入 PM 的 feature vector。

## 5. 标签重新设计

### 5.1 不再让 LLM 输出 Overall

PM-v2 judge 只输出六个独立维度：

- emotional support；
- personalization；
- memory appropriateness；
- factual grounding；
- temporal consistency；
- non-intrusiveness。

原始 judge schema 中不存在 `overall` 字段。训练所需的 `pmv2-quality-v1` 是配置文件中预先冻结的确定性 composite，只用于训练 utility，不冒充人类 holistic overall；论文必须同时报告全部子维度。

### 5.2 多 judge family 与 fail-closed gate

- 每条正式训练标签至少来自两个声明独立的模型 family；
- 取各维度中位数；
- 记录每个维度的 MAD；
- judge family 不足、可靠标签率低、response 或 risk 维度恒定、两维逐行重复率超过 98% 时，整个标签批次 FAIL；
- `scripts/21_judge_pm_v2_action_sweep.py` 支持断点续跑，并拒绝把不同 endpoint/config 的 raw rows 混入同一 run；
- forced-swap pairwise 仅用于 audit，不再作为唯一质量标签来源。

### 5.3 风险与质量分开

风险 judge 单独评价：

- selected-context misuse；
- unnecessary exposure；
- stale/conflicting use；
- unsupported personal claim；
- memory omission；
- strategy overuse；
- strategy omission。

成本直接来自 generation logs，不由 LLM 打分。

### 5.4 人工校准不可省略

多 LLM family 仍可能共享偏差，因此正式冻结前必须完成一个盲化 human audit：

1. `scripts/27_prepare_pm_v2_human_audit.py` 按 regime 抽取样本，隐藏 action 和 policy name；
2. 至少两名 annotator 独立填写六个 response 和七个 risk 维度；
3. `scripts/28_analyze_pm_v2_human_audit.py` 检查 human–LLM MAE、Spearman、within-one rate 和 human inter-rater weighted kappa；
4. human audit 未通过时，`scripts/26_freeze_pm_v2_study.py` 禁止创建 reportable freeze。

## 6. 数据与标签多样性 gate

`scripts/19_audit_pm_v2_data_labels.py` 在训练前检查：

- 每个 state 的所有 legal actions 都已生成并有标签；
- reliable label rate 达标；
- oracle best action 不被单一动作主导；
- oracle 中 M0、R0、RS 均有足够覆盖；
- 至少出现预注册数量的不同 oracle actions；
- 每种 resource-need regime 与实际 action outcomes 有基本一致性。

若标签本身仍然把 `ME+R0` 或高资源动作变成近常量最优，训练会在此处停止，而不是把坏标签继续训练成新 PM。

## 7. 表示与模型

### 7.1 取消 fitted TF-IDF 作为主文本表示

PM-v2 使用固定 word hashing + char hashing，因此新词不会因为 fitted vocabulary 而无声变成全零。若 state 文件中已有同一语义模型生成的 embedding，可追加到状态表示；实际 feature mode、维度和哈希必须写入 checkpoint report。

### 7.2 只允许 source-centroid relevance

为了保持“先决策、后检索”：

- query relevance 只允许与缓存的 source-level catalog centroid 比较；
- item-level max/P90 similarities 不进入模型；
- current-state conflict oracle 不进入模型。

### 7.3 直接预测多维 action outcomes

对每个 state-action 预测六个 response dimensions 和七个 risk dimensions。模型采用 state-group bootstrap ensemble，输出 mean 与 epistemic uncertainty，而不是只给一个无置信度的分数。

### 7.4 训练权重

同一 state 的所有动作总权重相同，避免 action-availability 较多的状态支配训练。每个 bootstrap 按 state_id 抽样，不能把同一状态的动作拆散造成伪独立。

## 8. 选择规则

PM-v2 的选择不是 quality winner-take-all：

1. 预测每个动作的 response dimensions、risk dimensions 和 uncertainty；
2. 计算 quality lower confidence bound 和 risk upper confidence bound；
3. 风险超阈值的动作排除；
4. memory-on 动作必须通过相对 `M0+R0` 的 resource-benefit gate，或 M0 omission risk 明确过高；
5. RS 动作必须通过相同 memory subset 下相对 R0 的 strategy-benefit gate，或 R0 strategy-omission risk 明确过高；
6. 对剩余动作直接计算：

```text
conservative utility
= quality LCB
- risk_weight × risk UCB
- cost_weight × normalized cost
```

7. 选择 utility 最大的动作；
8. 严重 OOD 时执行预注册 fallback，默认 `M0+R0`。

成本从一开始进入 utility，不再只处理并列。

## 9. Split、校准与内部 reportability gate

- train：只训练 outcome heads；
- calibration：只选择 risk/cost weights、resource/strategy gain threshold，并选择 cost-matched fixed baseline；
- internal test：只评一次；
- external EvoEmo：只在所有内部 gate 和 human audit 完成后运行。

禁止在 external results 上反向选择阈值、权重、composite 或 baseline。

`scripts/22_train_pm_v2.py` 会在 internal test 检查：

- 相对 calibration-selected cost-matched fixed action 的质量与 utility；
- PM 是否真正使用多个动作；
- M0 和 R0 是否达到最低覆盖；
- regime alignment 是否达标。

任一条件失败时，状态为 `NONREPORTABLE`，默认抛错并禁止 external generation。

## 10. 必须超过或正面报告的基线

PM-v2 外部评测至少包括：

- Context Only (`M0+R0`)；
- Cost-Matched Event Memory (`ME+R0`)；
- calibration split 中选择、与 PM-v2 observed token cost 最接近的 fixed action；
- Structured high-resource baseline；
- Raw Session Top-k；
- Full History。

若 PM-v2 未超过同预算 fixed action，必须如实报告，不能只和 full history 比。

## 11. 外部生成与评测

### 11.1 Study freeze

`scripts/26_freeze_pm_v2_study.py` 只有在以下条件全部通过时才创建 freeze：

- seed lineage；
- data/split audit；
- action judging quality gate；
- risk/response dimension health；
- human-versus-LLM judge calibration；
- internal reportability checks；
- checkpoint/config/hash 一致性。

### 11.2 EvoEmo generation

`scripts/24_run_pm_v2_evoemo.py`：

- 复用现有 policy-independent fixed seeker tracks；
- 只新增 PM-v2 condition，不重跑旧 baseline；
- API 调用前先运行全部 external states 的 OOD/action preflight；
- OOD fallback rate 超过预注册阈值时 fail before API；
- 记录完整 action predictions、选择原因、成本和 provenance。

### 11.3 外部 judge

`scripts/25_eval_pm_v2_external.py`：

- 每次 prompt 只评一个匿名候选，避免不同候选集合改变绝对分；
- 至少两个独立 judge families；
- 不请求 `overall`；
- 检查所有 condition 的 fixed input 完全一致；
- 聚合中位数、MAD，并做 response dimension duplicate/constant gate；
- 按 scenario 和 user 做 cluster bootstrap。

关键 claim 仍需 forced-swap 或小规模人工复核。

## 12. 不可协商的自动测试

`tests/test_pm_v2.py` 检查：

- judge schema 禁止 `overall`；
- M0+R0 可以被选择；
- memory-on + R0 可以被选择；
- cost 直接影响 utility；
- severe OOD fail-closed；
- joint split overlap 直接失败。

GitHub Actions 还会重新运行既有 contract、scientific safeguard 和 freeze-gate tests。

## 13. 推荐运行顺序

```bash
# 0. 从明确的 train split 构建 seed file
python scripts/18_prepare_pm_v2_seed_dialogues.py \
  --inputs <ESCONV_OR_OTHER_TRAIN_SOURCE> \
  --out data/pm_v2/train_seed_dialogues.jsonl

# 1. 生成 longitudinal development data（先 dry-run，再 --run）
python scripts/20_generate_pm_v2_development_data.py \
  --seed-dialogues data/pm_v2/train_seed_dialogues.jsonl

# 2. 使用既有 16-action sweep，输入改为 PM-v2 runtime/backend
python scripts/06_run_action_sweep.py \
  --runtime data/pm_v2/runtime_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --out-dir outputs/pm_v2_sweep

# 3. 多 family judging（先 dry-run，再 --run；支持续跑）
python scripts/21_judge_pm_v2_action_sweep.py \
  --judge-endpoints judge_family_a,judge_family_b

# 4. 训练前 data/label diversity gate
python scripts/19_audit_pm_v2_data_labels.py

# 5. 训练、calibration、internal reportability test
python scripts/22_train_pm_v2.py

# 6. 盲化 human audit
python scripts/27_prepare_pm_v2_human_audit.py
python scripts/28_analyze_pm_v2_human_audit.py \
  --completed <ANNOTATOR_1.csv> <ANNOTATOR_2.csv>

# 7. 创建不可变 study freeze
python scripts/26_freeze_pm_v2_study.py \
  --seed-audit data/pm_v2/train_seed_dialogues.jsonl.audit.json

# 8. 仅做 external action/OOD preflight（no API）
python scripts/23_select_pm_v2_actions.py \
  --runtime <FIXED_EXTERNAL_RUNTIME_STATES>

# 9. 固定输入 EvoEmo PM-v2 generation
python scripts/24_run_pm_v2_evoemo.py \
  --freeze outputs/pm_v2_study_freeze.json

# 10. 多 family external response evaluation
python scripts/25_eval_pm_v2_external.py \
  --judge-endpoints judge_family_a,judge_family_b
```

所有 API 脚本先 dry-run，确认调用数、估算成本、输入哈希和 freeze 后再加 `--run`。

## 14. 诚实边界

这套代码解决的是 PM-v1 已确认的结构性问题，并提供 fail-closed tests。它不能在没有实际生成、multi-family judge、人工校准、内部 holdout 和 external evaluation 的情况下保证 PM-v2 必然超过所有基线。

任何“保证一定成功”的承诺都会违反研究方法。这里能保证的是：

- 不会因为 overall 字段复制 support 而静默继续；
- 不会因为风险维度全为零而静默继续；
- 不会因为标签只偏向一个动作而静默继续；
- 不会因为 M0/R0 没学会而直接烧 external API；
- 不会因为同预算固定 baseline 更强而把它藏起来；
- 不会在 external results 上反向调参。

正确标准是：数据、标签、代码、阈值和强基线均预先冻结；任何负面结果也能被复现、定位和诚实解释。
