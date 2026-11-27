"""Deterministic review census fixed by WP2's pre-output error-review rule.

These observable transitions are not semantic/causal error labels. A subsequent
source review must leave ambiguous causes unresolved; it cannot alter scores.
"""
from collections import Counter, defaultdict

from .wp2 import MODELS, unique, require


def error_census(cells):
    indexed = {key: unique(rows, 'task_id') for key, rows in cells.items()}
    ids = set(next(iter(indexed.values())))
    require(all(set(rows) == ids for rows in indexed.values()), 'review populations differ')
    queue = defaultdict(list)
    transitions, errors = defaultdict(Counter), defaultdict(Counter)
    for model in MODELS:
        for tid in sorted(ids):
            rows = {arm: indexed[model+'|'+arm][tid] for arm in 'BCD'}
            for arm in 'CD':
                row = rows[arm]
                if row['status'] == 'completed' and not row['correct']:
                    queue[tid].append(model+'|'+arm+'_error')
                    for group in ('all', 'pref_type:'+row['category']['pref_type'],
                                  'selection_layer:'+row['category']['selection_layer']):
                        errors[model+'|'+arm+'/'+group][row['outcome']+'/'+row['finish_reason']] += 1
            for left, right in [('B', 'C'), ('C', 'D')]:
                a, b = rows[left], rows[right]
                if a['status'] != 'completed' or b['status'] != 'completed':
                    continue
                transition = a['outcome']+' -> '+b['outcome']
                for group in ('all', 'pref_type:'+a['category']['pref_type'],
                              'selection_layer:'+a['category']['selection_layer']):
                    transitions[model+'|'+left+'->'+right+'/'+group][transition] += 1
                if a['correct'] != b['correct']:
                    queue[tid].append(model+'|'+left+'->'+right+'_discordance')
    return dict(sorted(queue.items())), dict(
        review_tasks=len(queue),
        review_rule='All completed C/D errors and complete B->C/C->D correctness discordances; union by task. No score changes.',
        errors_by_observed_outcome={k: dict(v) for k, v in sorted(errors.items())},
        complete_pair_transitions={k: dict(v) for k, v in sorted(transitions.items())},
        semantic_attribution='Not automatically inferred. Inspect private source-bound review packets; ambiguous causes remain unresolved.')
