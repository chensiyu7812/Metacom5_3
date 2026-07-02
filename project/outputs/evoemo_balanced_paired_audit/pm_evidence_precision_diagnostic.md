# PM Evidence Precision Diagnostic

No API calls were made. This report diagnoses the balanced paired audit pilot.

## Main Finding

The pilot does not show a global response-quality collapse. It shows a more specific failure mode: PM high-resource actions can route into weakly focused memory retrieval. PM is acting as a coarse resource router, not as a fine-grained evidence selector.

## PM Action Concentration

- PM all generated turns: 1020
- PM all generated action counts: `{'MSE+RS': 521, 'MPMS+RS': 165, 'MP+RS': 128, 'MS+RS': 72, 'MPE+RS': 62, 'ME+RS': 34, 'MSE+R0': 27, 'ME+R0': 3, 'MPMS+R0': 3, 'MS+R0': 2, 'MP+R0': 2, 'MPMSME+RS': 1}`
- Balanced pilot PM actions: `{'MSE+RS': 6, 'MPMS+RS': 5, 'MP+RS': 1}`
- Balanced pilot risky PM actions: `{'MSE+RS': 4}`

All PM pilot issues occur under `MSE+RS`.

## Pilot Sample Enrichment

- Pilot primary strata: `{'pm_saves_but_quality_lower': 6, 'pm_high_resource': 3, 'pm_quality_tie_or_win_with_savings': 2, 'session_quality_higher_cost_tradeoff': 1}`
- PM high-resource coverage in pilot: 10/12
- PM high-resource coverage in full plan: 37/50

The pilot is therefore a stress sample, not a population estimate.

## Pilot Risk Summary

| Policy | n | Acceptable | Minor | Major | Mean evidence misuse | Mean overall risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| pm | 12 | 8 | 1 | 3 | 0.583 | 0.583 |
| strong_rule | 12 | 9 | 1 | 2 | 0.417 | 0.417 |
| best_fixed | 12 | 9 | 1 | 2 | 0.333 | 0.333 |
| session_rag_rs | 12 | 11 | 0 | 1 | 0.000 | 0.000 |

## Retrieval Relevance

| Policy | mean selected memory count | mean current-turn lexical relevance | risky-case relevance |
| --- | ---: | ---: | ---: |
| pm | 4.33 | 0.264 | 0.408 |
| strong_rule | 5.00 | 0.364 | 0.352 |
| best_fixed | 7.00 | 0.262 | 0.284 |
| session_rag_rs | 4.00 | 0.421 | NA |

Lexical relevance alone does not explain the judge scores. Some long memories have lexical overlap with the current turn while carrying unrelated private events.

## Response Scores For PM Pilot Units

| PM pilot subset | n | overall | memory appropriateness | non intrusive |
| --- | ---: | ---: | ---: | ---: |
| risky PM units | 4 | 3.000 | 4.250 | 3.500 |
| clean PM units | 8 | 3.500 | 4.000 | 4.250 |

The risky PM units are not evidence that the generator collapses. They indicate that selected memory sets can be weakly focused even when the response remains supportive.

## Audit Schema Note

Schema/verdict mismatch rows: 1. This supports separating evidence relevance from actual response misuse.

## Recommended Interpretation

1. PM is a coarse pre-evidence router, not a fine-grained evidence selector.
2. The main failure source is retrieval/source granularity under high-resource actions.
3. The pilot is a stress diagnostic because it over-represents high-resource PM cases.
4. Future tables should report evidence relevance, response misuse, source excess, and response support separately.

## Recommended Next Step

Do not use an evidence gate to claim PM itself selected evidence correctly. If a gate is added, report it as a separate execution-layer module: `PM + evidence gate`.
