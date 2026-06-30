# EvoEmo Sampled Memory / Strategy Audit No-API Plan

生成时间：2026-06-30T05:05:50.594199+00:00

本文件只是抽样和预算计划，不包含 API judge 结果，不能作为 audit 结论。

## Design Rationale

- 优先审计 `pm` vs `strong_rule` / `best_fixed`：V4 response quality 接近，但 PM 更省资源。
- 纳入 `pm` vs `session_rag_rs`：session_rag 分数较高但成本更大，用于审计 quality-cost tradeoff。
- 纳入 `pm` vs `no_memory_r0`：用于检查资源使用是否造成不必要暴露或过度结构化。
- 覆盖 PM 高资源、低资源/R0、罕见 action，避免 audit 被 `MSE+RS` 主导。

## Sample Summary

- selected items: 40
- unique users: 18
- unique scenarios `(user_id, topic_index)`: 34
- unique topics: 3
- turn counts: {'3': 22, '8': 18}
- PM action counts: {'MSE+RS': 14, 'MP+RS': 11, 'MPMS+RS': 6, 'MSE+R0': 4, 'MS+RS': 2, 'MP+R0': 1, 'MS+R0': 1, 'MPE+RS': 1}
- focus condition counts: {'pm': 40, 'strong_rule': 14, 'best_fixed': 10, 'no_memory_r0': 6, 'session_rag_rs': 6}
- audit module counts: {'selected_evidence_misuse': 30, 'unnecessary_exposure': 26, 'source_set_appropriateness': 16, 'unsupported_personal_claim': 14, 'strategy_overuse': 12, 'omission_with_authorized_context': 10, 'stale_or_conflict': 8, 'strategy_omission': 4, 'response_support_sufficiency': 4, 'positive_control_resource_saving': 4}

## Cost Estimate

- selected-evidence / strategy calls: 70
- authorized-context omission calls: 10
- total estimated calls: 80
- estimated input tokens: 178975
- estimated output tokens: 36000
- estimated cost: $0.81

真实 audit API 脚本仍必须先做 dry-run hash、budget gate 和小样本 pilot；不能直接 full-run。

## Preview Items

| id | user | topic | seed | turn | pm_action | focus | covered_strata |
| --- | --- | --- | --- | --- | --- | --- | --- |
| audit_v4_001 | p1 | 1 | 101 | 8 | MSE+RS | pm,no_memory_r0 | pm_vs_no_memory_quality_loss,pm_high_resource_exposure,pm_quality_tie_or_win_with_savings |
| audit_v4_002 | p10 | 1 | 101 | 8 | MSE+RS | pm | pm_high_resource_exposure,pm_quality_tie_or_win_with_savings |
| audit_v4_003 | p11 | 1 | 101 | 8 | MSE+R0 | pm,strong_rule | pm_low_resource_or_r0 |
| audit_v4_004 | p11 | 1 | 202 | 8 | MSE+RS | pm,no_memory_r0 | pm_vs_no_memory_quality_loss,pm_high_resource_exposure |
| audit_v4_005 | p12 | 1 | 202 | 3 | MP+RS | pm,session_rag_rs | pm_vs_session_quality_cost_tradeoff,rare_pm_actions |
| audit_v4_006 | p13 | 1 | 101 | 3 | MPMS+RS | pm,session_rag_rs | pm_vs_session_quality_cost_tradeoff,pm_quality_tie_or_win_with_savings,rare_pm_actions |
| audit_v4_007 | p13 | 1 | 202 | 8 | MSE+R0 | pm,strong_rule | pm_low_resource_or_r0 |
| audit_v4_008 | p14 | 1 | 101 | 8 | MSE+RS | pm,no_memory_r0 | pm_vs_no_memory_quality_loss,pm_quality_tie_or_win_with_savings |
| audit_v4_009 | p15 | 1 | 101 | 3 | MSE+RS | pm,no_memory_r0 | pm_vs_no_memory_quality_loss,pm_quality_tie_or_win_with_savings |
| audit_v4_010 | p16 | 1 | 101 | 8 | MPMS+RS | pm,strong_rule | pm_vs_strong_rule_action_disagreement,pm_vs_best_fixed_resource_saving,pm_quality_tie_or_win_with_savings,rare_pm_actions |
| audit_v4_011 | p16 | 1 | 202 | 8 | MSE+RS | pm | pm_high_resource_exposure |
| audit_v4_012 | p17 | 1 | 202 | 3 | MP+R0 | pm,strong_rule | pm_vs_strong_rule_action_disagreement,pm_vs_best_fixed_resource_saving,pm_low_resource_or_r0,pm_quality_tie_or_win_with_savings,rare_pm_actions |
| audit_v4_013 | p18 | 1 | 303 | 8 | MSE+RS | pm | pm_high_resource_exposure,pm_quality_tie_or_win_with_savings |
| audit_v4_014 | p2 | 1 | 202 | 3 | MPMS+RS | pm,best_fixed | pm_vs_best_fixed_resource_saving,pm_quality_tie_or_win_with_savings,rare_pm_actions |
| audit_v4_015 | p3 | 1 | 303 | 3 | MS+R0 | pm,strong_rule | pm_vs_strong_rule_action_disagreement,pm_vs_best_fixed_resource_saving,pm_low_resource_or_r0,pm_quality_tie_or_win_with_savings,rare_pm_actions |
| audit_v4_016 | p4 | 1 | 303 | 8 | MSE+RS | pm | pm_high_resource_exposure,pm_quality_tie_or_win_with_savings |
| audit_v4_017 | p5 | 1 | 101 | 3 | MPMS+RS | pm,strong_rule,best_fixed | pm_quality_tie_or_win_with_savings,rare_pm_actions |
| audit_v4_018 | p6 | 1 | 101 | 8 | MS+RS | pm,strong_rule | pm_vs_strong_rule_action_disagreement,pm_quality_tie_or_win_with_savings,rare_pm_actions |

## Audit Modules

- `selected_evidence_misuse`: selected memory 是否被错误使用、过度使用或引入 unsupported personal claim。
- `unnecessary_exposure`: 资源是否暴露了当前回复不需要的个人事实。
- `stale_or_conflict`: selected memory 是否与更新信息冲突或被过时使用。
- `source_set_appropriateness`: PM 选择的 source set 是否相对 baseline 足够。
- `strategy_overuse`: Strategy RAG 是否导致过度结构化、过早建议或语气不自然。
- `strategy_omission`: PM 关闭或弱化 strategy 时是否遗漏明显需要的支持策略。
- `omission_with_authorized_context`: 少量高价值样本使用 evaluator-only context 审计遗漏，必须严格限量。
