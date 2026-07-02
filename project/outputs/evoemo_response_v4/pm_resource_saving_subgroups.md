# PM Resource Saving Subgroup Analysis

No API was used. This report joins EvoEmo Response V4 score rows, generated turn cost metadata, and sampled audit rows.

## Main Answer

- PM does not mainly win by raising average response quality. Its stronger evidence is that it often uses fewer input tokens than rule or fixed structured baselines while keeping turn level quality close.
- The saved resource cases are not automatically proof that PM skipped only unnecessary memory, but they are a useful diagnostic: if quality does not collapse when resources are removed, the extra evidence was often not decisive for fixed input response quality.
- The sampled audit linkage is especially important because retrieved personal evidence is not only a cost. It also creates risk surface for misuse, exposure, stale conflict, and unsupported personal claims.

## PM Saving Subgroups

| Baseline | All units | PM saves input | Mean tokens saved | Mean reduction | Mean overall delta in saved cases | Saved and tie/win | Saved but lower |
| --- | --- | --- | --- | --- | --- | --- | --- |
| strong_rule | 204 | 101 | 672.1 | 0.426 | 0.030 | 92/101 | 9/101 |
| best_fixed | 204 | 204 | 360.1 | 0.224 | -0.005 | 178/204 | 26/204 |
| session_rag_rs | 204 | 204 | 1938.6 | 0.600 | -0.093 | 168/204 | 36/204 |
| full_history_rs | 204 | 204 | 12785.2 | 0.902 | 0.039 | 158/204 | 46/204 |
| no_memory_r0 | 204 | 0 | NA | NA | NA | 0/0 | 0/0 |

## Saved Cases by Turn

| Baseline | Turn | All units | PM saves input | Mean tokens saved | Mean overall delta | PM higher/tie/lower |
| --- | --- | --- | --- | --- | --- | --- |
| strong_rule | 3 | 102 | 83 | 745.7 | -0.012 | 8/66/9 |
| strong_rule | 8 | 102 | 18 | 332.9 | 0.222 | 4/14/0 |
| best_fixed | 3 | 102 | 102 | 634.1 | 0.059 | 18/72/12 |
| best_fixed | 8 | 102 | 102 | 86.2 | -0.069 | 6/82/14 |
| session_rag_rs | 3 | 102 | 102 | 2226.2 | -0.137 | 8/73/21 |
| session_rag_rs | 8 | 102 | 102 | 1650.9 | -0.049 | 10/77/15 |
| full_history_rs | 3 | 102 | 102 | 13072.3 | 0.098 | 29/52/21 |
| full_history_rs | 8 | 102 | 102 | 12498.1 | -0.020 | 21/56/25 |
| no_memory_r0 | 3 | 102 | 0 | NA | NA | 0/0/0 |
| no_memory_r0 | 8 | 102 | 0 | NA | NA | 0/0/0 |

## Sampled Audit Linkage

| Subset | n | Misuse >0 | Exposure >0 | Stale/conflict >0 | Unsupported claim >0 | Strategy omission >0 | Overall risk >0 | Verdicts |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pm_rows | 50 | 0 | 0 | 0 | 0 | 1 | 1 | {'acceptable': 49, 'minor_issue': 1} |
| pm_rows_with_input_savings_vs_focus_baseline | 32 | 0 | 0 | 0 | 0 | 1 | 1 | {'acceptable': 31, 'minor_issue': 1} |
| pm_rows_without_input_savings_vs_focus_baseline | 18 | 0 | 0 | 0 | 0 | 0 | 0 | {'acceptable': 18} |

## Interpretation

The cleanest claim is not that PM produces better responses. It is that PM preserves comparable quality to Rule Policy and Fixed Structured while reducing evidence injection. This matters because extra retrieved personal evidence is a cost, latency, and risk surface rather than a harmless prompt addition.

A safe paper sentence:

> In resource saving subgroups, the learned PM frequently removed input evidence relative to rule or fixed structured baselines without a large average quality collapse. In the sampled audit, PM had no observed selected evidence misuse, unnecessary exposure, stale conflict, or unsupported personal claim across 50 PM audited cases, although the audit is descriptive and not a full safety guarantee.

A sentence to avoid:

> PM proves that the skipped evidence was always unnecessary or that PM is universally safer.
