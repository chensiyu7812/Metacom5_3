# MetaCom PM-v2 可执行运行手册

> 本手册只适用于 `pm-v2-redesign` 分支。PM-v1 的冻结结果不被覆盖。

## 0. 环境与原则

```bash
git checkout pm-v2-redesign
git pull
cd project
PYTHONNOUSERSITE=1 PYTHONPATH=src pytest -q tests/test_pm_v2.py
```

正式流程必须遵守：

1. 先 dry-run，再 API run；
2. seed 只来自明确 train split；
3. 不使用 EvoEmo 调权重、阈值或 composite；
4. data/label/human/internal gate 任一失败，停止，不跑 external；
5. `overall` 不存在；论文只报告六个 response dimensions 和预注册 composite；
6. cost-matched fixed 与 `ME+R0` 必须进入外部比较。

## 1. 生成 train-only seed dialogues

```bash
python scripts/18_prepare_pm_v2_seed_dialogues.py \
  --inputs <ESCONV_SOURCE.jsonl> \
  --out data/pm_v2/train_seed_dialogues.jsonl \
  --minimum-seeds 100
```

若原文件没有 split 字段，必须增加：

```bash
  --train-ids <TRAIN_DIALOGUE_IDS.txt>
```

输出：

- `data/pm_v2/train_seed_dialogues.jsonl`
- `data/pm_v2/train_seed_dialogues.jsonl.audit.json`

## 2. 数据生成 pilot

先用小规模检查 prompt/schema，不用于论文：

```bash
python scripts/20_generate_pm_v2_development_data.py \
  --seed-dialogues data/pm_v2/train_seed_dialogues.jsonl \
  --train-users 3 --calibration-users 1 --internal-test-users 1 \
  --out-dir data/pm_v2_pilot

# 确认 dry-run 后再加 --run
```

每个用户必须生成九个 regime，每个 state 必须有 MP/MS/ME，因此暴露完整 16 actions。任一不满足会重试并最终 fail closed。

## 3. 正式数据生成

```bash
python scripts/20_generate_pm_v2_development_data.py \
  --seed-dialogues data/pm_v2/train_seed_dialogues.jsonl

python scripts/20_generate_pm_v2_development_data.py \
  --seed-dialogues data/pm_v2/train_seed_dialogues.jsonl \
  --run
```

默认规模：

- 24 train users；
- 6 calibration users；
- 6 internal-test users；
- 9 states / user；
- 324 states；
- 5,184 state-action outcomes。

## 4. 16-action generation sweep

```bash
python scripts/06_run_action_sweep.py \
  --runtime data/pm_v2/runtime_states.jsonl \
  --backend data/pm_v2/memory_backend.jsonl \
  --out-dir outputs/pm_v2_sweep \
  --generator-endpoint generator
```

先用 `--max-cards 3` 做非正式 pilot；正式结果不加该参数。

期望：每个 state 的 16 个动作全部完成，无 duplicate key、无缺失 action。

## 5. Multi-family judging

在 `configs/experiment.yaml` 中配置至少两个不同模型 family，例如：

- `judge_family_a`；
- `judge_family_b`。

先 dry-run：

```bash
python scripts/21_judge_pm_v2_action_sweep.py \
  --judge-endpoints judge_family_a,judge_family_b \
  --max-api-calls 25000
```

正式运行：

```bash
python scripts/21_judge_pm_v2_action_sweep.py \
  --judge-endpoints judge_family_a,judge_family_b \
  --max-api-calls 25000 \
  --run
```

默认 5,184 outcomes、2 families、response/risk 两次调用，最多约 20,736 judge calls。脚本支持续跑；不要删除 raw rows 后局部重跑，也不要更换 endpoint 后接着旧目录跑。

自动 gate：

- 两个 family 缺一不可；
- response/risk 维度恒定失败；
- 任意两个维度逐行复制率 ≥98% 失败；
- reliable label rate <80% 失败。

## 6. Data/label diversity gate

```bash
python scripts/19_audit_pm_v2_data_labels.py
```

通过标准包括：

- 所有 legal actions 都有 outcome/label；
- oracle best action 至少覆盖多个动作；
- 单一动作不能占比过高；
- M0、R0、RS 均有真实可学样本；
- 九个 regime 与实际 action outcomes 基本一致。

未通过时不能继续训练。应重新检查生成 prompt、memory quality 或 judge rubric，而不是手工改标签。

## 7. 训练、校准和 internal test

```bash
python scripts/22_train_pm_v2.py
```

流程：

- train：训练六个 response heads 和七个 risk heads；
- calibration：选择 quality/risk/cost 参数，选择 cost-matched fixed action；
- internal test：只评一次。

默认 reportability gate 要求：

- 与 calibration-selected cost-matched fixed 相比，quality 不低于 -0.02；
- utility 不低于 fixed；
- risk 不高于 +0.02；
- cost 不超过 fixed 的 1.10 倍；
- 至少使用 4 个动作；
- M0 ≥5%；
- R0 ≥10%；
- regime alignment ≥50%。

任一失败，`training_report.json` 状态为 `NONREPORTABLE`，默认抛错；此时禁止 external API。

## 8. 盲化人工 label audit

生成 packet：

```bash
python scripts/27_prepare_pm_v2_human_audit.py
```

至少两位 annotator 分别复制并填写 packet，保持以下内容不可见：

- action ID；
- policy name；
- LLM judge scores。

分析：

```bash
python scripts/28_analyze_pm_v2_human_audit.py \
  --completed <ANNOTATOR_A.csv> <ANNOTATOR_B.csv>
```

阈值全部从 `configs/pm_v2.yaml` 读取，不能用命令行放宽。未通过时不可冻结。

## 9. 生成固定基线 checkpoint

```bash
python scripts/29_prepare_pm_v2_fixed_baselines.py
```

输出：

- calibration-selected cost-matched fixed checkpoint；
- `ME+R0` checkpoint；
- 固定动作、源 checkpoint 与哈希报告。

固定 baseline 和 learned PM 使用同一套 state construction、retrieval、prompt、generator 和 fixed seeker tracks。

## 10. 创建 reportable study freeze

```bash
python scripts/26_freeze_pm_v2_study.py \
  --seed-audit data/pm_v2/train_seed_dialogues.jsonl.audit.json
```

只有 seed lineage、judge gate、data/label gate、human audit、internal gate、checkpoint/config hash 全部一致时才创建 freeze。

## 11. External no-API action/OOD preflight

```bash
python scripts/23_select_pm_v2_actions.py \
  --runtime <EVOEMO_FIXED_RUNTIME_STATES.jsonl>
```

重点检查：

- M0/R0/action entropy；
- OOD fallback rate；
- 是否再次近常量退化。

不允许根据该结果改阈值；若不满足 freeze 中的 gate，external generation 停止。

## 12. EvoEmo fixed-input generation

Learned PM-v2：

```bash
python scripts/24_run_pm_v2_evoemo.py \
  --freeze outputs/pm_v2_study_freeze.json \
  --checkpoint outputs/pm_v2_model/pm_v2.joblib \
  --condition pm_v2 \
  --out-dir outputs/evoemo_pm_v2
```

Calibration-selected cost-matched fixed：

```bash
python scripts/24_run_pm_v2_evoemo.py \
  --freeze outputs/pm_v2_study_freeze.json \
  --checkpoint outputs/pm_v2_model/pm_v2_cost_matched_fixed.joblib \
  --condition pm_v2_cost_matched_fixed \
  --out-dir outputs/evoemo_pm_v2_cost_matched_fixed
```

固定 `ME+R0`：

```bash
python scripts/24_run_pm_v2_evoemo.py \
  --freeze outputs/pm_v2_study_freeze.json \
  --checkpoint outputs/pm_v2_model/pm_v2_me_r0_fixed.joblib \
  --condition pm_v2_me_r0_fixed \
  --out-dir outputs/evoemo_pm_v2_me_r0_fixed
```

三者共享同一 fixed-input tracks、同一生成器和同一生成参数。

## 13. External multi-family response evaluation

Dry-run：

```bash
python scripts/25_eval_pm_v2_external.py \
  --judge-endpoints judge_family_a,judge_family_b
```

正式：

```bash
python scripts/25_eval_pm_v2_external.py \
  --judge-endpoints judge_family_a,judge_family_b \
  --run
```

特点：

- 每个 prompt 只评一个匿名 response；
- 不请求 `overall`；
- 六维分别报告；
- quality composite 是冻结公式，不是 judge overall；
- 同一 unit 的 context/seeker input 必须完全一致；
- scenario/user cluster bootstrap；
- PM-v2、cost-matched fixed、ME+R0、Context Only、Raw Top-4、Structured、Full History 全部比较。

## 14. 关键结论的人工/forced-swap 复核

若 PM-v2 在关键比较中优于同预算 fixed，应对 40–72 个 matched units 进行：

- 匿名；
- 双顺序；
- 至少两名人工评审；
- Support、Personalization、Preference；
- 不一致计 tie。

该复核用于支持关键外部 claim，不用于调模型。

## 15. 什么才算 PM-v2 成功

最低标准不是“某个平均分最高”，而是：

1. 数据、label、human、internal、freeze gate 全部通过；
2. external 不出现 M0=0、RS≈100% 或单动作塌缩；
3. 相对同预算 fixed，质量非劣且 utility/risk/cost 至少一项有明确优势；
4. 相对高资源 baseline 显著节省 tokens；
5. 关键结论经 forced-swap 或人工复核；
6. 所有负面结果完整报告。

在这些结果实际产生前，只能说“PM-v2 的实验链路已完成并具备 fail-closed safeguards”，不能预先声称方法一定成功。
