"""Prospective P3 arithmetic, not a source of human labels or PPO permission.

The caller must supply source-confirmed factual adjudications and validated
independent human submissions. Coordinator-authored control intentions never
count as source confirmations. No measurement is imputed when missing.
"""
from collections import Counter

SEVERE_TYPES = {'identity', 'subject', 'currentness', 'intent_to_result'}


def utility(score):
    if not isinstance(score, dict) or score.get('q') is None or score.get('m') is None:
        return None
    q, m = score['q'], score['m']
    if type(q) is not int or q not in range(5) or type(m) not in (int, float) or m not in (0, .25, 1):
        raise ValueError('invalid candidate score')
    return q / 4 - m


def direction(scores):
    values = [utility(s) for s in scores]
    if len(values) != 2:
        raise ValueError('exactly two candidate replies required')
    if None in values:
        return None
    return 'left' if values[0] > values[1] else 'right' if values[0] < values[1] else 'tie'


def confirmed(record):
    """Require explicit human/source provenance, not an expected-answer key."""
    return (record.get('source_confirmed') is True
        and record.get('confirmation_kind') in ('independent_human', 'human_fact_adjudication')
        and isinstance(record.get('human_review_identity'), str)
        and len(record['human_review_identity']) == 64
        and bool(record.get('source_ids')))


def decide(*, natural, controls, repeats, technical, raters):
    if len(raters) not in (1, 2) or len(set(raters)) != len(raters):
        raise ValueError('one or two distinct human raters required')
    if len(natural) not in (16, 24) or len({r['pair_id'] for r in natural}) != len(natural):
        raise ValueError('fixed 16 natural pairs, or all 8 prelocked reserve pairs, required')
    if len(controls) != 8 or len(repeats) != 12:
        raise ValueError('fixed control/repeat denominators required')
    failures, insufficient = [], []
    if (technical['planned'] < 1 or technical['first_valid'] / technical['planned'] < .95
            or technical['processable_after_recovery'] != technical['planned']):
        failures.append('technical_structure_or_processing')
    counts = Counter(); individual = {r:Counter() for r in raters}; catastrophic = []
    for row in natural:
        if set(row['human']) != set(raters):
            raise ValueError('all planned rater labels must be present, including uncertainty')
        preferences = [row['human'][r] for r in raters]
        if any(p not in ('left','right','tie','uncertain') for p in preferences):
            raise ValueError('unknown human preference')
        auto = direction(row['scores'])
        for rater, pref in zip(raters, preferences):
            individual[rater][pref] += 1
            if pref != 'uncertain':
                individual[rater]['comparable'] += 1
                individual[rater]['matched'] += int(pref == auto)
        if len(set(preferences)) == 1 and preferences[0] != 'uncertain':
            pref = preferences[0]
            kind = 'ties' if pref == 'tie' else 'clear'
            counts[kind] += 1
            counts[kind+'_matched'] += int(pref == auto)
        else:
            counts['disagreed_or_uncertain'] += 1
        counts['missing_auto'] += int(auto is None)
        for fact in row.get('severe_facts', []):
            if not confirmed(fact):
                continue
            side = fact['side']
            if side not in (0, 1):
                raise ValueError('unknown adjudicated side')
            if auto == ('left','right')[side] and row['scores'][side]['m'] < 1:
                catastrophic.append(row['pair_id'])
    if catastrophic:
        failures.append('prefers_source_confirmed_severe_natural_error_and_misses_risk')

    seen = set()
    for row in controls:
        kind = row['control_type']; scores = row['scores']
        if kind in SEVERE_TYPES:
            if kind in seen:
                raise ValueError('duplicated severe control category')
            seen.add(kind)
            if not confirmed(row):
                insufficient.append('unconfirmed_control:'+kind)
                continue
            good, bad = row['good_side'], row['bad_side']
            if {good,bad} != {0,1}:
                raise ValueError('control side binding mismatch')
            ug, ub = utility(scores[good]), utility(scores[bad])
            if ug is None or ub is None or scores[bad]['m'] != 1 or not ub < ug:
                failures.append('severe_control:'+kind)
        elif kind in ('general_support','equivalent_wording'):
            if not confirmed(row):
                insufficient.append('unconfirmed_neutral_control')
            elif any(utility(s) is None or s['m'] == 1 for s in scores):
                failures.append('severe_false_positive_on_neutral_control')
        else:
            raise ValueError('unknown control category')
    if seen != SEVERE_TYPES:
        raise ValueError('all four severe categories must be retained')
    if Counter(r['control_type'] for r in controls) != Counter(
            dict(identity=1,subject=1,currentness=1,intent_to_result=1,equivalent_wording=2,general_support=2)):
        raise ValueError('control composition drift')
    repeat_same, repeat_flip, repeat_missing = 0, 0, 0
    for row in repeats:
        if row['cache_hit'] or row['primary_draw'] == row['repeat_draw']:
            raise ValueError('independent repeat must not be a cache hit or same draw')
        first, second = row['primary'], row['repeat']
        u1, u2 = utility(first), utility(second)
        if u1 is None or u2 is None:
            repeat_missing += 1
            continue
        repeat_same += int(u1 == u2)
        repeat_flip += int((first['m'] == 1) != (second['m'] == 1))
    if repeat_same < 11 or repeat_flip or repeat_missing:
        failures.append('single_reply_repeat_instability_or_missingness')
    tie_ok = counts['ties'] >= 5 and counts['ties_matched'] / counts['ties'] >= .8
    if counts['clear'] >= 8:
        if counts['clear_matched'] / counts['clear'] < .75:
            failures.append('natural_direction_agreement')
        if counts['ties'] >= 5 and not tie_ok:
            failures.append('natural_tie_agreement')
        candidate = 'CALIBRATED_FOR_BOUNDED_STUDY'
    elif tie_ok and counts['clear_matched'] == counts['clear']:
        candidate = 'CALIBRATED_LOW_CONTRAST'
    else:
        insufficient.append('natural_human_information')
        candidate = 'INSUFFICIENT_HUMAN_INFORMATION'
    status = 'MEASUREMENT_UNQUALIFIED' if failures else (
        'INSUFFICIENT_HUMAN_INFORMATION' if insufficient else candidate)
    return dict(status=status, failures=failures, insufficient_evidence=insufficient,
        natural=dict(counts), per_rater={k:dict(v) for k,v in individual.items()},
        sample=dict(pairs=len(natural), owners=len({r['owner'] for r in natural}),
            prefixes=len({r['prefix_identity'] for r in natural}), raters=len(raters)),
        catastrophic_pairs=catastrophic, repeat_same_utility=repeat_same,
        repeat_severe_flips=repeat_flip, repeat_missing=repeat_missing,
        reserve_eligible_only_by_information=counts['clear'] < 8 and len(natural) == 16,
        requires_128_episodes=status=='CALIBRATED_LOW_CONTRAST',
        automatic_training_authorization=False,
        scope='Arithmetic on validated calibration inputs only; final measurement/runtime freeze and independent task evaluation still required.')
