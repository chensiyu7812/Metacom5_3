# EvoEmo Balanced Paired Evidence Audit Plan

Generated at: 2026-07-02T13:08:28.925709+00:00

This is a no-API plan. It is not an audit result.

## Purpose

The earlier sampled audit was descriptive because policies were not audited on the same units and baseline sample sizes were small. This plan selects the same 50 V4 fixed-input units for four policies: Learned PM, Rule Policy, Fixed All Structured, and Session Retrieval.

## Pre-registered Risk Metrics

- Primary: major evidence risk indicator, defined as any severity >= 2 in selected evidence misuse, unnecessary exposure, stale/conflict, or unsupported personal claim.
- Primary severity score: max severity over the four evidence risk fields above.
- Secondary: strategy overuse and strategy omission, reported separately from evidence misuse.
- Secondary: source set appropriateness and response support sufficiency.
- Cost and response quality are not folded into the risk score; they are reported as separate tradeoff dimensions.

## Selection Summary

- selected units: 50
- planned selected audit calls: 200
- unique users: 18
- unique topic index values: 3
- unique scenarios: 34
- turn counts: {'3': 34, '8': 16}
- PM action counts: {'MP+RS': 16, 'MSE+RS': 15, 'MPMS+RS': 12, 'MS+RS': 3, 'MPE+RS': 2, 'MP+R0': 1, 'MS+R0': 1}
- focus condition counts: {'pm': 50, 'strong_rule': 50, 'best_fixed': 50, 'session_rag_rs': 50}
- primary stratum counts: {'pm_quality_tie_or_win_with_savings': 20, 'pm_saves_but_quality_lower': 15, 'session_quality_higher_cost_tradeoff': 10, 'pm_high_resource': 5}
- covered strata counts: {'pm_high_resource': 37, 'session_quality_higher_cost_tradeoff': 23, 'pm_quality_tie_or_win_with_savings': 20, 'pm_saves_but_quality_lower': 15}

## Planning Cost Estimate

- planned calls: 200
- planning estimated input tokens: 504383
- planning estimated output tokens: 90000
- planning estimated GPT-4o cost: $2.16

The evaluator dry-run remains authoritative and must be run before any API call.

## Preview

| id | user | topic | seed | turn | pm_action | primary | covered |
| --- | --- | --- | --- | --- | --- | --- | --- |
| paired_audit_v1_001 | p1 | 1 | 101 | 3 | MPMS+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower |
| paired_audit_v1_002 | p1 | 1 | 101 | 8 | MSE+RS | pm_high_resource | pm_high_resource |
| paired_audit_v1_003 | p1 | 1 | 202 | 3 | MPMS+RS | pm_quality_tie_or_win_with_savings | pm_quality_tie_or_win_with_savings,pm_high_resource |
| paired_audit_v1_004 | p10 | 1 | 101 | 8 | MSE+RS | pm_high_resource | pm_high_resource |
| paired_audit_v1_005 | p11 | 1 | 202 | 8 | MSE+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower,session_quality_higher_cost_tradeoff,pm_high_resource |
| paired_audit_v1_006 | p12 | 1 | 202 | 3 | MP+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower,session_quality_higher_cost_tradeoff,pm_high_resource |
| paired_audit_v1_007 | p13 | 1 | 101 | 3 | MPMS+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower,session_quality_higher_cost_tradeoff,pm_high_resource |
| paired_audit_v1_008 | p14 | 1 | 303 | 8 | MSE+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower,pm_high_resource |
| paired_audit_v1_009 | p15 | 1 | 303 | 3 | MPMS+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower,session_quality_higher_cost_tradeoff,pm_high_resource |
| paired_audit_v1_010 | p16 | 1 | 101 | 8 | MPMS+RS | pm_quality_tie_or_win_with_savings | pm_quality_tie_or_win_with_savings,pm_high_resource |
| paired_audit_v1_011 | p16 | 1 | 202 | 3 | MSE+RS | session_quality_higher_cost_tradeoff | session_quality_higher_cost_tradeoff |
| paired_audit_v1_012 | p16 | 1 | 202 | 8 | MSE+RS | pm_high_resource | pm_high_resource |
| paired_audit_v1_013 | p17 | 1 | 202 | 3 | MP+R0 | pm_quality_tie_or_win_with_savings | pm_quality_tie_or_win_with_savings,pm_high_resource |
| paired_audit_v1_014 | p18 | 1 | 101 | 8 | MSE+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower,session_quality_higher_cost_tradeoff,pm_high_resource |
| paired_audit_v1_015 | p2 | 1 | 101 | 3 | MPMS+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower,session_quality_higher_cost_tradeoff |
| paired_audit_v1_016 | p2 | 1 | 202 | 3 | MPMS+RS | pm_quality_tie_or_win_with_savings | pm_quality_tie_or_win_with_savings,pm_high_resource |
| paired_audit_v1_017 | p2 | 1 | 303 | 3 | MP+RS | pm_saves_but_quality_lower | pm_saves_but_quality_lower,session_quality_higher_cost_tradeoff |
| paired_audit_v1_018 | p3 | 1 | 303 | 3 | MS+R0 | pm_quality_tie_or_win_with_savings | pm_quality_tie_or_win_with_savings,pm_high_resource |
| paired_audit_v1_019 | p4 | 1 | 202 | 3 | MPMS+RS | pm_quality_tie_or_win_with_savings | pm_quality_tie_or_win_with_savings,pm_high_resource |
| paired_audit_v1_020 | p5 | 1 | 303 | 8 | MSE+RS | pm_high_resource | pm_high_resource |
