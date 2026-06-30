# 给 GPT-5.5 Pro 的 V4 修正说明

更新时间：2026-06-30

你的大方向是对的：旧 EvoEmo 10-turn bundle pairwise 主评测必须废弃，下一版应先 dry-run，再 pilot，再 full-run；主评价应从 bundle pairwise 改为 single-turn fixed-input scoring。

但原方案里有几个会导致再次失败或预算误判的问题，V4 已做修正。

## 1. Token / cost 估算偏低

原估算约 `3000 tokens/call`，实际用现有 EvoEmo generated dialogues 和 full evaluator context dry-run 后，V4 full-run 约为：

```text
204 calls
mean input tokens/call ≈ 6970
p95 input tokens/call ≈ 10706
max input tokens/call ≈ 11289
total input tokens ≈ 1.42M
estimated cost ≈ 5-6 USD with GPT-4o pricing assumptions
```

差异主要来自 evaluator-only authorized ground truth。它包含 profile、timeline、related sessions 和 current topic，是每个 call 的固定大头。原方案没有充分计入这个固定开销。

V4 修正：

- 不再用理论 token 估算决定是否开跑；
- 必须用真实 generated dialogues 构造 prompt 并 dry-run；
- API 模式必须传入对应 `cost_estimate_sha256`；
- 默认 `max_input_tokens_per_call` 提高到 `12000`。

## 2. `max_input_tokens_per_call=6000` 太低

实测 full-context V4 平均单 call 就超过 6000 tokens，p95 超过 10000。若 gate 设为 6000，会把大量正常样本误拦掉，导致 pilot/full-run 无法按预注册样本执行。

V4 修正：

```text
default max_input_tokens_per_call = 12000
```

同时保留 hard budget gate。如果 dry-run 发现 max/p95 继续上升，脚本会先拒跑，而不是 API 跑到一半才发现。

## 3. Absolute scoring 仍可能有 position bias

把 pairwise 改成 absolute scoring 能解决旧协议最严重的 AB/BA orientation flip，但不能自动消除“候选排在第几个位置会不会更容易得高分”的 position bias。

V4 修正：

- full-run 使用 deterministic balanced candidate order；
- pilot 对同一 unit 跑两个 order variants；
- pilot 统计同一 condition 换位置后的 `overall` mean absolute difference；
- pilot 统计各 candidate position 的平均分偏移；
- pilot 不过，不允许 full-run。

## 4. Turn 3/8 不能假定一定区分策略

选择 turn 3/8 是合理的省钱抽样，但必须验证这些 turn 上 PM 与 baselines 的 action 是否真的有差异。如果 PM 和 strong_rule 在抽样 turn 上大量选择相同 action，response scoring 对 policy allocation 的区分力会降低。

V4 修正：

dry-run 的 `sample_plan.json` 和 `cost_estimate_*.json` 会记录 action sensitivity：

- 每个 turn 的 action difference rate；
- `pm_vs_baseline_same_action_rate`；
- 每个 unit 的 condition action map。

这样可以在 API 前判断抽样是否有区分度。

## 5. Client adapter 问题

旧 `evo_metrics.py` 在部分位置直接使用 `OpenAICompatibleClient`，绕开了 `make_client()`，这会让 Claude native endpoint 等非 OpenAI-compatible endpoint 失效。

V4 修正：

新模块 `src/metacom_pm/evo_response_v4.py` 使用：

```python
make_client(judge_endpoint)
```

因此 OpenAI-compatible 和 Anthropic native endpoint 都走统一入口。

## 6. 新执行路径

新增：

```text
src/metacom_pm/evo_response_v4.py
scripts/17b_eval_evoemo_response_v4.py
scripts/20c_freeze_evoemo_response_v4_eval.py
```

V4 evaluation freeze：

```text
outputs/evoemo_response_v4_eval_freeze.json
sha256: c9ccd1d21d1da8571710361ed9648b6696964edaf45d45067cea2887185c4bb3
```

推荐顺序：

1. `--dry-run --dry-run-target pilot`
2. `--pilot --accept-cost-estimate-sha256 <pilot_hash>`
3. 若 `pilot_summary.json.status == PASS` 且与当前 full-run 配置兼容：
4. `--dry-run --dry-run-target full`
5. `--full-run --pilot-summary ... --accept-cost-estimate-sha256 <full_hash>`

这解决了旧方案最大的问题：不再允许一次性全量烧钱，任何 API 运行前都必须有真实 prompt 构造出的预算 hash。

## 7. 二次审查后的 fail-closed 补丁

你指出的两个补丁是对的，已经修正：

1. `artifact_attestation.json` / `pilot_artifact_attestation.json` 的 `study_freeze_sha256` 现在绑定 V4 evaluation freeze，而不是 generation freeze。
2. summary 和 attestation 写入前会调用 exact output validation，强制检查 judgment rows、score rows、raw successful calls、重复 key、missing key、extra key，以及每个 judgment 的 candidate IDs / condition set 完整性。

同时默认 pilot 改为：

```text
pilot_units = 24
max_order_mean_abs_diff = 0.50
max_position_mean_shift = 0.40
```

新的 pilot dry-run：

```text
calls = 48
estimated cost = 1.31 USD
cost_estimate_sha256 = 3f4c38cdb21d3e0e545bafd652cf6b7fcaedc159f83ef0919b9dfcd24ca3b661
```

## 8. 三次审查后的 pilot/full-run compatibility 补丁

你指出 full-run 不能只检查旧 `pilot_summary.status == PASS`，这个判断是正确的。单看 PASS 会留下证明链一致性漏洞：旧 pilot 可能使用了不同 judge、conditions、turns、ground truth mode、generation/evaluation freeze 或 pilot thresholds，却仍被 full-run 接受。

V4 现在新增 `_require_pilot_compatible_with_current_run(...)`，full-run 前逐项检查：

- `protocol == "evoemo_response_v4"`；
- `mode == "pilot"`；
- `status == "PASS"`；
- judge model / family 与当前 endpoint 一致；
- `ground_truth_mode` 一致；
- `conditions` 一致；
- `turn_indices` 一致；
- generation freeze sha256 一致；
- evaluation freeze sha256 一致；
- `max_order_mean_abs_diff` 和 `max_position_mean_shift` 一致。

不一致时 fail-closed，禁止 full-run。对应新增 3 个单测：完全匹配通过、conditions mismatch 失败、evaluation freeze mismatch 失败。
