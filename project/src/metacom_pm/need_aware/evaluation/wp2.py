"""Frozen WP2 evaluation. This module never loads models or changes run conditions.

Gold joins live only here. Failed/unexecuted outcomes are unknown, not wrong model
answers; structural Direct gaps never enter the evaluable denominator.
"""
from collections import Counter
import math

from .aggregate import paired_cluster
from .mcq import score_one

MODELS = ('G0e', 'Qwen35')
ARMS = ('A', 'B', 'C', 'D')
STATUSES = {'completed', 'failed', 'missing', 'not_evaluable', 'capacity_exceeded'}
FAILURES = {'timeout', 'runtime_error', 'invalid_output', 'interrupted', 'unattempted', 'capacity_exceeded'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(rows, key):
    out = {r[key]: r for r in rows}
    require(len(out) == len(rows), 'duplicate ' + key)
    return out


def validate_population(tasks, evaluations, policy):
    ids = {t.task_id for t in tasks}
    require(len(ids) == len(tasks) == policy['populations']['all'], 'frozen task count')
    require(len({t.persona_group for t in tasks}) == len(tasks), 'one task per persona required')
    require(set(evaluations) == ids, 'evaluation task population mismatch')
    require(all(t.task_mode == 'mcq' and t.split == 'val' for t in tasks), 'WP2 val MCQ only')
    groups = populations(evaluations)
    for k, n in policy['populations'].items():
        require(len(groups[k]) == n, 'frozen population mismatch: ' + k)
    missing = Counter(evaluations[t].category['pref_type'] for t in groups['direct_missing'])
    require(dict(missing) == policy['direct_missing_pref_type'], 'Direct missingness changed')
    return groups


def populations(evaluations):
    groups = {'all': set(evaluations), 'direct': set(), 'direct_missing': set(),
              'representative': set(), 'hard': set()}
    for tid, ev in evaluations.items():
        groups['direct' if ev.direct_status == 'located_unique' else 'direct_missing'].add(tid)
        layer = ev.category['selection_layer']
        groups['representative' if layer == 'representative' else 'hard'].add(tid)
        for k, v in ev.category.items():
            groups.setdefault(f'{k}:{v}', set()).add(tid)
    for layer in ('representative', 'hard'):
        groups['direct/'+layer] = groups['direct'] & groups[layer]
    return groups


def validate_requests(tasks, evaluations, requests):
    """Validate the whole manifest index before opening any predictions."""
    ix = unique(requests, 'logical_id')
    expected = {f'{t.task_id}|{a}|{m}' for t in tasks for a in ARMS for m in MODELS}
    require(set(ix) == expected, 'manifest logical population mismatch')
    task_map = {t.task_id: t for t in tasks}
    for lid, r in ix.items():
        tid, arm, model = r['task_id'], r['arm'], r['model_label']
        require(lid == f'{tid}|{arm}|{model}', 'logical identity mismatch')
        require(r['persona_group'] == task_map[tid].persona_group, 'manifest persona mismatch')
        structural = arm in 'CD' and evaluations[tid].direct_status != 'located_unique'
        require(r['status'] == ('not_evaluable' if structural else 'ready'), 'unexpected request eligibility')
        require((r.get('request_sha256') is None) == structural, 'request hash/eligibility mismatch')
    return ix


def score_cell(tasks, evaluations, requests, predictions, *, model, arm, kind='model'):
    require(model in MODELS and arm in ARMS, 'unknown cell')
    require(kind in {'model', 'plumbing'}, 'explicit result kind')
    pm = unique(predictions, 'task_id')
    require(set(pm) == {t.task_id for t in tasks}, 'export must include all frozen slots, including missing')
    records, run_ids = [], set()
    for task in tasks:
        tid = task.task_id
        ev, p = evaluations[tid], pm[tid]
        lid = f'{tid}|{arm}|{model}'
        req = requests[lid]
        require(p.get('logical_id') == lid and p.get('arm') == arm and p.get('model_label') == model,
                'prediction logical/cell mismatch')
        require(p.get('result_kind') == kind, 'plumbing/model provenance mismatch')
        require(p.get('model_id') == req['model_id'], 'prediction model identity mismatch')
        require(p.get('request_sha256') == req.get('request_sha256'), 'prediction request identity mismatch')
        require(bool(p.get('run_id')), 'missing run identity')
        run_ids.add(p['run_id'])
        status = p.get('status')
        require(status in STATUSES, 'unknown prediction status')
        eligible = req['status'] == 'ready'
        require((status == 'not_evaluable') == (not eligible), 'structural status mismatch')
        require(isinstance(p.get('output'), str), 'output must be text')
        require(type(p.get('attempt_count')) is int and 0 <= p['attempt_count'] <= 2, 'attempt count missing/invalid')
        n = p['attempt_count']
        failure = p.get('failure_kind')
        if status == 'completed':
            require(n > 0 or p.get('reused_exact') is True, 'completion without physical attempt/reuse')
            require(p.get('finish_reason') in {'eos', 'length'}, 'unvalidated finish reason')
            require(failure is None, 'completed slot has terminal failure')
            result = score_one(p['output'], task, ev)
            outcome = 'correct' if result['correct'] else 'wrong_answer' if result['parse_valid'] else 'parse_failure'
        else:
            require(p['output'] == '' and p.get('finish_reason') is None, 'failed/structural slot contains selected output')
            if status == 'not_evaluable':
                require(n == 0 and failure is None, 'structural slot attempted')
            elif status == 'missing':
                require(failure == ('interrupted' if n else 'unattempted'), 'missing slot failure classification')
            elif status == 'capacity_exceeded':
                require(n == 0 and failure == 'capacity_exceeded', 'capacity failure classification')
            else:
                require(n > 0 and failure in FAILURES - {'unattempted', 'capacity_exceeded'}, 'failed slot classification')
            result = dict(task_id=tid, predicted_choice=None, parse_valid=None, correct=None)
            outcome = 'structural_not_evaluable' if not eligible else failure
        result.update(persona_group=task.persona_group, category=ev.category,
                      direct_status=ev.direct_status, eligible=eligible, status=status,
                      outcome=outcome, failure_kind=failure, attempt_count=n,
                      finish_reason=p.get('finish_reason'), reused_exact=p.get('reused_exact', False),
                      result_kind=kind, run_id=p['run_id'], model=model, arm=arm,
                      request_sha256=p.get('request_sha256'))
        records.append(result)
    require(len(run_ids) == 1, 'mixed runs within export cell')
    return records


def wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    d = 1 + z*z/n
    center = (k/n + z*z/(2*n))/d
    half = z*math.sqrt(k/n*(1-k/n)/n + z*z/(4*n*n))/d
    return [max(0., center-half), min(1., center+half)]


def counts(rows):
    eligible = [r for r in rows if r['eligible']]
    done = [r for r in eligible if r['status'] == 'completed']
    n, c = len(eligible), len(done)
    correct = sum(r['correct'] for r in done)
    eos = [r for r in done if r['finish_reason'] == 'eos']
    attempts = sum(r['attempt_count'] for r in eligible if not r['reused_exact'])
    return dict(planned_slots=len(rows), predefined_evaluable=n, structural_not_evaluable=len(rows)-n,
                completed=c, completion_rate=c/n if n else None,
                attempted_slots=sum(r['attempt_count'] > 0 for r in eligible), physical_attempts=attempts,
                retries=sum(max(0, r['attempt_count']-1) for r in eligible if not r['reused_exact']),
                technical_uncompleted=n-c,
                failures=dict(sorted(Counter(r['failure_kind'] for r in eligible if r['status'] != 'completed').items())),
                correct=correct, parse_failures=sum(not r['parse_valid'] for r in done),
                valid_wrong=sum(r['parse_valid'] and not r['correct'] for r in done),
                status=dict(sorted(Counter(r['status'] for r in rows).items())),
                accuracy_on_completed=correct/c if c else None, completed_wilson_ci95=wilson(correct, c),
                fixed_denominator_success_sensitivity=correct/n if n else None,
                unknown_outcome_bounds=[correct/n, (correct+n-c)/n] if n else None,
                length_stops=sum(r['finish_reason'] == 'length' for r in done),
                eos_only_completed=len(eos),
                eos_only_accuracy=sum(r['correct'] for r in eos)/len(eos) if eos else None)


def exact_mcnemar(repairs, regressions):
    n, k = repairs+regressions, min(repairs, regressions)
    return min(1., 2*sum(math.comb(n, i) for i in range(k+1))/(2**n)) if n else 1.


def compare(left, right, policy):
    """Same predefined eligible set; complete-case and fixed-denominator analyses."""
    a, b = unique(left, 'task_id'), unique(right, 'task_id')
    require(set(a) == set(b), 'unequal comparison populations')
    require(all(a[t]['eligible'] == b[t]['eligible'] for t in a), 'unequal evaluable denominators')
    ids = sorted(t for t in a if a[t]['eligible'])
    x, y = [a[t] for t in ids], [b[t] for t in ids]
    params = policy['paired_inference']
    result = paired_cluster(x, y, seed=params['bootstrap_seed'], replicates=params['bootstrap_replicates'])
    result.update(planned_slots=len(a), structural_pairs=len(a)-len(ids), predefined_evaluable_pairs=len(ids))
    result['mcnemar_p_two_sided'] = exact_mcnemar(result['repairs'], result['regressions']) if result['complete_pairs'] else None
    paired = [t for t in ids if a[t]['status'] == b[t]['status'] == 'completed']
    result['left_correct_on_pairs'] = sum(a[t]['correct'] for t in paired)
    result['right_correct_on_pairs'] = sum(b[t]['correct'] for t in paired)
    result['left_accuracy_on_pairs'] = result['left_correct_on_pairs']/len(paired) if paired else None
    result['right_accuracy_on_pairs'] = result['right_correct_on_pairs']/len(paired) if paired else None
    failures_zero = lambda r: int(bool(r['correct'])) if r['status'] == 'completed' else 0
    result['fixed_denominator_difference_sensitivity'] = sum(failures_zero(b[t])-failures_zero(a[t]) for t in ids)/len(ids) if ids else None
    lo = hi = 0
    for t in ids:
        av, bv = failures_zero(a[t]), failures_zero(b[t])
        lo += bv - (av if a[t]['status'] == 'completed' else 1)
        hi += (bv if b[t]['status'] == 'completed' else 1) - av
    result['unknown_outcome_difference_bounds'] = [lo/len(ids), hi/len(ids)] if ids else None
    natural = [t for t in paired if a[t]['finish_reason'] == b[t]['finish_reason'] == 'eos']
    result['eos_only_pairs'] = len(natural)
    result['eos_only_difference'] = sum(int(b[t]['correct'])-int(a[t]['correct']) for t in natural)/len(natural) if natural else None
    return result


def holm(rows):
    # Missing comparisons remain in the planned family, conservatively as p=1.
    ordered = sorted(enumerate(rows), key=lambda x: x[1]['mcnemar_p_two_sided'] if x[1]['mcnemar_p_two_sided'] is not None else 1.)
    running = 0.
    for rank, (_, r) in enumerate(ordered):
        p = r['mcnemar_p_two_sided']
        running = max(running, min(1., (len(rows)-rank)*(p if p is not None else 1.)))
        r['mcnemar_p_holm_8'] = running if p is not None else None


def analyze(cells, evaluations, policy):
    require(set(cells) == {f'{m}|{a}' for m in MODELS for a in ARMS}, 'eight cells required')
    groups = populations(evaluations)
    take = lambda key, ids: [r for r in cells[key] if r['task_id'] in ids]
    summaries = {key: {g: counts(take(key, ids)) for g, ids in groups.items()} for key in cells}
    primary = []
    for population, left, right in policy['primary_paired_family']:
        r = compare(take(left, groups[population]), take(right, groups[population]), policy)
        r.update(population=population, left=left, right=right)
        primary.append(r)
    holm(primary)
    secondary = {}
    contrasts = [(m+'|'+a, m+'|'+b, 'all' if a+b == 'AB' else 'direct')
                 for m in MODELS for a, b in [('A', 'B'), ('B', 'C'), ('C', 'D')]]
    contrasts += [('G0e|'+a, 'Qwen35|'+a, 'all' if a in 'AB' else 'direct') for a in ARMS]
    for left, right, population in contrasts:
        for g, ids in groups.items():
            if g == 'all':
                continue
            selected = groups[population] & ids
            secondary[f'{left}->{right}/{g}'] = compare(take(left, selected), take(right, selected), policy)
    matched_tables = {}
    for name, keys in [('G0e_four_arms', ['G0e|'+a for a in ARMS]),
                       ('Qwen35_four_arms', ['Qwen35|'+a for a in ARMS]),
                       ('both_models_eight_cells', list(cells))]:
        selected = set(groups['direct'])
        for key in keys:
            selected &= {r['task_id'] for r in cells[key] if r['status'] == 'completed'}
        matched_tables[name] = dict(predefined_evaluable=207, common_completed=len(selected),
                                   excluded_incomplete=207-len(selected),
                                   cells={k: counts(take(k, selected)) for k in keys})
    missingness = {g: {'all': len(ids), 'direct_located': len(ids & groups['direct']),
                      'direct_missing': len(ids & groups['direct_missing'])} for g, ids in groups.items()}
    return dict(protocol=policy['protocol'], cell_summaries=summaries, primary_paired=primary,
                descriptive_paired=secondary, common_completed_tables=matched_tables,
                structural_missingness=missingness,
                primary_ci_multiplicity='CI unadjusted; Holm p-values across fixed 8; all subgroup contrasts descriptive')
