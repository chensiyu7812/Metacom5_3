# MetaCom V3.3 EvoEmo Response Eval V4 方案

更新时间：2026-06-30

## 1. 为什么需要 V4

上一轮 EvoEmo pairwise-only evaluation 已完成 816/816 API calls，但 10-turn bundle pairwise prompt 的 AB/BA orientation consistency 未达到预注册门槛 `0.80`。因此该结果只能作为诊断，不能作为 confirmatory 外部 response-quality 证据。

V4 的目标不是“换个 judge 重跑”，而是修正测量设计：

- 从 10-turn bundle pairwise 改为 single-turn fixed-input absolute scoring；
- 每个 fixed turn 内同时呈现多个匿名候选；
- 每个候选独立打 1-5 分；
- 正式 API 跑之前必须先 no-API dry-run 和小样本 pilot；
- 任何 API 模式都必须匹配 dry-run cost estimate hash；
- pilot 不通过时禁止 full-run。

## 2. V4 主评测单位

评测 unit：

```text
(user_id, topic_index, seed, simulator_id, interaction_mode, turn_index)
```

默认抽样：

```text
34 topics × 3 seeds × turns {3, 8} = 204 units
```

默认候选条件：

```text
pm
strong_rule
best_fixed
session_rag_rs
full_history_rs
no_memory_r0
```

每个 unit 内，所有候选必须具有完全相同的 fixed seeker input：

- `track_id`
- `state_id`
- `context_sha256`
- `context_before_turn`
- `seeker_message`

否则脚本 fail-closed。

## 3. Judge 输出

每个候选独立评分：

- `emotional_support`
- `personalization`
- `memory_appropriateness`
- `factual_grounding`
- `temporal_consistency`
- `non_intrusiveness`
- `overall`

分数范围均为整数 `1..5`。候选用 `C1`, `C2`, ... 匿名呈现，prompt 不暴露 policy name。

## 4. 顺序与 position bias 控制

V4 不再使用 AB/BA pairwise preference，因此消除了旧协议里的“同一对候选换左右顺序后 preference 翻转”的主问题。

但 absolute scoring 并不自动消除 candidate position bias。因此 V4 做两件事：

1. 正式 full-run 使用 deterministic balanced order，使每个 condition 在各候选位置上尽量均衡；
2. pilot 对同一 unit 跑两个 order variants，并计算：
   - 同一 condition 在两个 order 下的 `overall` mean absolute difference；
   - 每个 position 的平均 `overall` 与全局平均的最大偏移。

默认 pilot gate：

```text
max_order_mean_abs_diff = 0.75
max_position_mean_shift = 0.50
```

这些阈值不是论文结论本身，只是判断当前 prompt 是否足够稳定进入 full-run 的工程门。

## 5. 成本与预算门

V4 入口：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/17b_eval_evoemo_response_v4.py
```

V4 evaluation freeze：

```text
outputs/evoemo_response_v4_eval_freeze.json
freeze sha256: cda4b6542d42c457c26ae97d73c1831fe346679d0707e751c27a189b3cdbed7b
```

冻结入口：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/20c_freeze_evoemo_response_v4_eval.py
```

任何 API 模式前必须先 dry-run。dry-run 输出：

- `outputs/evoemo_response_v4/sample_plan.json`
- `outputs/evoemo_response_v4/cost_estimate_pilot.json`
- `outputs/evoemo_response_v4/cost_estimate_full.json`
- 对应 `*_calls.jsonl`

默认预算门：

```text
max_api_calls = 250
max_estimated_usd = 6.0
max_input_tokens_per_call = 12000
estimated_output_tokens_per_call = 1000
```

注意：旧建议中的 `max_input_tokens_per_call=6000` 太低。实测 full-context V4 单 call 平均约 6-7k input tokens，p95 超过 10k，主要固定开销来自 evaluator-only authorized ground truth。

## 6. 推荐运行顺序

### 6.1 Pilot dry-run

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/17b_eval_evoemo_response_v4.py \
  --dry-run \
  --dry-run-target pilot \
  --max-estimated-usd 2 \
  --overwrite
```

读取：

```text
outputs/evoemo_response_v4/cost_estimate_pilot.json
cost_estimate_sha256: ea3eb4d4da21ae21e29a6383a3e7e6bed2deaa098d87d465d0eeb999f9dac73a
```

### 6.2 Pilot API

只有接受上一步 hash 后才允许：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/17b_eval_evoemo_response_v4.py \
  --pilot \
  --accept-cost-estimate-sha256 <pilot_cost_estimate_sha256>
```

输出：

```text
outputs/evoemo_response_v4/pilot_scores.jsonl
outputs/evoemo_response_v4/pilot_judgments.jsonl
outputs/evoemo_response_v4/pilot_raw_calls.jsonl
outputs/evoemo_response_v4/pilot_summary.json
```

只有 `pilot_summary.json` 的 `status` 为 `PASS`，才允许 full-run。

### 6.3 Full dry-run

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/17b_eval_evoemo_response_v4.py \
  --dry-run \
  --dry-run-target full \
  --max-estimated-usd 10 \
  --overwrite
```

读取：

```text
outputs/evoemo_response_v4/cost_estimate_full.json
cost_estimate_sha256: 3c309933ab90dc7d1f909a398ae2dfe4d9d0abd87e1144cf6ce1af84ec95114b
```

### 6.4 Full API

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/17b_eval_evoemo_response_v4.py \
  --full-run \
  --pilot-summary outputs/evoemo_response_v4/pilot_summary.json \
  --accept-cost-estimate-sha256 <full_cost_estimate_sha256>
```

输出：

```text
outputs/evoemo_response_v4/response_scores.jsonl
outputs/evoemo_response_v4/response_judgments.jsonl
outputs/evoemo_response_v4/response_raw_calls.jsonl
outputs/evoemo_response_v4/response_summary.json
outputs/evoemo_response_v4/artifact_attestation.json
```

## 7. Ground Truth 模式

默认：

```text
--ground-truth-mode full
```

这沿用现有 evaluator context，包括 profile、timeline、related sessions 和 current topic。

可选：

```text
--ground-truth-mode compact_related
```

该模式只保留 profile、current topic、related session summaries 和 observations，去掉完整历史 dialogue text 和 all-session timeline。它更省钱，但如果用于正式结果，必须在 dry-run / pilot / full-run 前明确冻结该选择。

## 8. 论文使用边界

V4 如果 pilot 通过并 full-run 完成，可作为 EvoEmo fixed-input longitudinal response-quality 外部结果。

仍然不能主张：

- 真实用户 distress 改善；
- 临床疗效；
- official ES-MemEval reproduction；
- PM 全面优于 strong rule。

正确写法仍应是：

> Under controlled fixed-input longitudinal evaluation, PM shows a response-quality/cost/misuse tradeoff relative to fixed and rule baselines.
