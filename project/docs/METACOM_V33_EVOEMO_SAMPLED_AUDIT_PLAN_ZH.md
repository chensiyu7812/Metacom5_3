# MetaCom V3.3 EvoEmo Sampled Memory / Strategy Audit Plan

更新时间：2026-06-30

## 1. 当前阶段

EvoEmo Response Eval V4 已完成，结论是：

> PM 在 fixed-input response quality 上与 strong_rule / best_fixed 大体持平，同时降低资源成本；但它不是 response quality 全面最优策略。

因此下一步不是继续全量 response judge，而是做小样本 memory / strategy audit，检查 PM 的真实优势是否体现在：

- memory misuse 更低；
- unnecessary exposure 更低；
- stale/conflict 更少；
- unsupported personal claim 更少；
- strategy over-structuring / premature advice 更少；
- source set 更节省但没有遗漏关键支持证据。

本计划只是 no-API sample plan，不包含任何新 judge 结果。

## 2. 为什么不直接跑全量 audit

全量 audit 会重新进入高成本风险，并且很多 turn 对论文主张的边际价值很低。

本轮 audit 应服务主线：

- PM vs strong_rule：质量接近，PM 更省资源；
- PM vs best_fixed：质量接近，PM 更省资源；
- PM vs session_rag_rs：session_rag_rs 分数略高，但成本更大；
- PM vs no_memory_r0：no_memory_r0 分数高时，检查 PM 是否出现不必要资源暴露或过度结构化；
- PM 内部高资源 / 低资源 / rare action：检查 PM 边界行为。

不应把 `full_history_rs` 或 `no_memory_r0` 作为唯一审计重点。

## 3. No-API Planner

脚本：

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/17d_plan_evoemo_sampled_audit.py
```

输入：

- `outputs/evoemo_response_v4/response_scores.jsonl`
- `outputs/evoemo_selective/turns.jsonl`

输出：

- `outputs/evoemo_sampled_audit_plan/audit_sample_plan.json`
- `outputs/evoemo_sampled_audit_plan/audit_items.jsonl`
- `outputs/evoemo_sampled_audit_plan/audit_sample_plan.md`

## 4. Sample Summary

当前 no-API plan：

- selected items: 40
- unique users: 18
- unique scenarios `(user_id, topic_index)`: 34 / 34
- turn counts: turn 3 = 22, turn 8 = 18
- estimated audit calls: 80
- estimated input tokens: 178,975
- estimated output tokens: 36,000
- estimated GPT-4o cost without cache discount: about 0.81 USD

PM action coverage:

| PM Action | Count |
|---|---:|
| MSE+RS | 14 |
| MP+RS | 11 |
| MPMS+RS | 6 |
| MSE+R0 | 4 |
| MS+RS | 2 |
| MP+R0 | 1 |
| MS+R0 | 1 |
| MPE+RS | 1 |

Focus condition coverage:

| Condition | Count |
|---|---:|
| pm | 40 |
| strong_rule | 14 |
| best_fixed | 10 |
| no_memory_r0 | 6 |
| session_rag_rs | 6 |

## 5. Audit Strata

The selected items cover:

| Stratum | Purpose |
|---|---|
| `pm_vs_strong_rule_action_disagreement` | PM and strong_rule choose different actions while response quality is broadly comparable. |
| `pm_vs_best_fixed_resource_saving` | PM uses fewer resources than best_fixed; audit whether skipped sources were unnecessary. |
| `pm_vs_session_quality_cost_tradeoff` | session_rag_rs scores higher but costs more; audit possible omission vs resource saving. |
| `pm_vs_no_memory_quality_loss` | no_memory_r0 scores higher; audit whether PM's resources caused exposure or over-structuring. |
| `pm_high_resource_exposure` | PM uses high memory / strategy resources; audit exposure, stale/conflict, unsupported claims. |
| `pm_low_resource_or_r0` | PM suppresses Strategy RAG or chooses R0; audit strategy omission. |
| `pm_quality_tie_or_win_with_savings` | Positive controls where PM ties or wins while saving resources. |
| `rare_pm_actions` | Covers rare PM actions so the audit is not dominated by `MSE+RS`. |

## 6. Audit Modules

Recommended audit labels:

- `selected_evidence_misuse`
- `unnecessary_exposure`
- `stale_or_conflict`
- `unsupported_personal_claim`
- `source_set_appropriateness`
- `strategy_overuse`
- `strategy_omission`
- `omission_with_authorized_context`
- `response_support_sufficiency`

Important cost guardrail:

> `omission_with_authorized_context` should remain limited. It is useful, but it is the only module that needs evaluator-only broader history/context and can become expensive if expanded.

## 7. Required API Safety Gates

Audit implementation now preserves the V4 discipline:

1. no-API dry-run;
2. real prompt construction and token estimate;
3. cost estimate hash;
4. small pilot only, recommended first pilot = 8 items;
5. exact output validation before summary / attestation;
6. manual raw row gate:

```text
raw_rows <= expected_calls * 1.10
```

No full audit should run until the pilot passes.

## 8. Current Evaluator / Dry-Run Status

新增 evaluator：

- `src/metacom_pm/evo_sampled_audit.py`
- `scripts/17e_eval_evoemo_sampled_audit.py`
- `scripts/20d_freeze_evoemo_sampled_audit_eval.py`

Evaluation freeze：

- path: `outputs/evoemo_sampled_audit_eval_freeze.json`
- sha256: `4d4cd3ca98617da93c38107dbedaa2ce20bb8aad6a08723054f27dada92858ce`

Pilot dry-run：

- calls: 16
- selected-resource calls: 12
- authorized-context omission calls: 4
- input tokens: total 50,419 / mean 3,151 / max 3,606
- estimated GPT-4o cost: about 0.20 USD
- cost hash: `ed3c6ce44045bbb798678c26857919df0d97c7c978b4fac91d3ac06e2488ef32`

Full sampled audit dry-run：

- calls: 80
- selected-resource calls: 70
- authorized-context omission calls: 10
- input tokens: total 243,590 / mean 3,045 / max 4,369
- estimated GPT-4o cost: about 0.97 USD
- cost hash: `380d149f48965391c96adac6b72dc301a40672caef806df2867966058daa6555`

API calls so far: none.

Recommended pilot command:

```bash
PYTHONNOUSERSITE=1 PYTHONPATH=src \
  OPENAI_API_KEY="$OPENAI_API_KEY" \
  /home/tokkio/miniconda3/envs/sim_eval/bin/python \
  scripts/17e_eval_evoemo_sampled_audit.py \
  --pilot \
  --pilot-items 8 \
  --accept-cost-estimate-sha256 ed3c6ce44045bbb798678c26857919df0d97c7c978b4fac91d3ac06e2488ef32 \
  --max-estimated-usd 2 \
  --max-input-tokens-per-call 8000
```

Pilot pass criteria:

- `outputs/evoemo_sampled_audit/pilot_summary.json` exists;
- `status == "PASS"`;
- `output_validation.ok == true`;
- `completed_calls == expected_calls`;
- `score_rows == expected_calls`;
- `raw_rows <= expected_calls * 1.10`.

If the pilot passes, full sampled audit must still use the full dry-run hash:

```text
380d149f48965391c96adac6b72dc301a40672caef806df2867966058daa6555
```

## 9. Paper Position

If audit supports PM:

> PM does not universally maximize response quality, but it can preserve comparable quality against conservative memory policies while reducing resource use and avoiding unnecessary or risky evidence exposure.

If audit is mixed:

> PM primarily provides a controllable resource-quality tradeoff; guardrails or safety-first variants remain needed for omission-sensitive settings.

Either outcome is compatible with the current paper boundary.
