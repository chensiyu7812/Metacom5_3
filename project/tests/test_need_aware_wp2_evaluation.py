"""Synthetic contract regressions, never model capability evidence."""
from copy import deepcopy
import pytest

from metacom_pm.need_aware.data.contracts import RuntimeTask
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.wp2 import (
    score_cell, counts, compare, holm, exact_mcnemar,
)
from metacom_pm.need_aware.evaluation.score import score_predictions


@pytest.fixture
def sample():
    tasks, ev, req, pred = [], {}, {}, []
    for i in range(6):
        tid = f't{i}'
        tasks.append(RuntimeTask(tid, 'revision', 'val', f'p{i}', f'h{i}', f'h{i}.json', 'a'*64,
                                 1, [], 'Synthetic question', 'mcq',
                                 [{'id': chr(65+j), 'text': str(j)} for j in range(4)]))
        ev[tid] = EvalTask(tid, 'A', '0', 'private', [], {'selection_layer': 'representative'}, [],
                          'missing' if i == 5 else 'located_unique')
        lid = tid+'|C|G0e'
        req[lid] = dict(logical_id=lid, task_id=tid, arm='C', model_label='G0e', persona_group=f'p{i}',
                        model_id='model-fixed', status='not_evaluable' if i == 5 else 'ready',
                        request_sha256=None if i == 5 else 'req'+str(i))
        pred.append(dict(task_id=tid, logical_id=lid, arm='C', model_label='G0e', model_id='model-fixed',
                         result_kind='plumbing', run_id='test-run', request_sha256=req[lid]['request_sha256'],
                         status='completed', output='Final Answer: A', attempt_count=1,
                         failure_kind=None, finish_reason='eos', reused_exact=False))
    pred[1]['output'] = 'Final Answer: B'
    pred[2]['output'] = 'A'  # official parser intentionally refuses bare letters
    pred[3].update(status='failed', output='', failure_kind='timeout', finish_reason=None, attempt_count=2)
    pred[4].update(status='missing', output='', failure_kind='unattempted', finish_reason=None, attempt_count=0)
    pred[5].update(status='not_evaluable', output='', finish_reason=None, attempt_count=0)
    return tasks, ev, req, pred


def score(sample):
    t, e, r, p = sample
    return score_cell(t, e, r, p, model='G0e', arm='C', kind='plumbing')


def policy():
    return {'paired_inference': {'bootstrap_seed': 20261127, 'bootstrap_replicates': 100}}


def test_structural_technical_parse_and_wrong_are_separate(sample):
    r = score(sample)
    assert [x['outcome'] for x in r] == ['correct', 'wrong_answer', 'parse_failure', 'timeout', 'unattempted', 'structural_not_evaluable']
    assert all(x['correct'] is None for x in r[3:])
    c = counts(r)
    assert (c['planned_slots'], c['predefined_evaluable'], c['completed'], c['structural_not_evaluable']) == (6, 5, 3, 1)
    assert c['accuracy_on_completed'] == 1/3
    assert c['fixed_denominator_success_sensitivity'] == 1/5
    assert c['completion_rate'] == 3/5 and c['unknown_outcome_bounds'] == [1/5, 3/5]
    assert c['parse_failures'] == c['valid_wrong'] == 1
    assert c['physical_attempts'] == 5 and c['retries'] == 1


@pytest.mark.parametrize('mutation', ['wrong_request', 'wrong_model', 'wrong_run', 'duplicate', 'missing', 'provenance', 'structural', 'attempt', 'unknown_failure'])
def test_export_mismatch_fails_closed(sample, mutation):
    t, e, r, p = sample
    if mutation == 'wrong_request': p[0]['request_sha256'] = 'other'
    if mutation == 'wrong_model': p[0]['model_id'] = 'other'
    if mutation == 'wrong_run': p[0]['run_id'] = 'other'
    if mutation == 'duplicate': p.append(p[0])
    if mutation == 'missing': p.pop()
    if mutation == 'provenance': p[0]['result_kind'] = 'model'
    if mutation == 'structural': p[4].update(status='not_evaluable', failure_kind=None)
    if mutation == 'attempt': p[0]['attempt_count'] = 0
    if mutation == 'unknown_failure': p[3]['failure_kind'] = 'maybe'
    with pytest.raises(ValueError): score(sample)


def test_pairing_uses_identical_completed_tasks_not_marginals(sample):
    x = score(sample); y = deepcopy(x)
    y[0].update(status='missing', correct=None, parse_valid=None, failure_kind='unattempted', attempt_count=0, finish_reason=None)
    y[1].update(correct=True)
    y[4].update(status='completed', correct=True, parse_valid=True, failure_kind=None, attempt_count=1, finish_reason='eos')
    a = compare(x, y, policy())
    assert a['predefined_evaluable_pairs'] == 5 and a['structural_pairs'] == 1
    assert a['complete_pairs'] == 2 and a['missing_or_failed_pairs'] == 3
    assert a['repairs'] == 1 and a['regressions'] == 0
    assert a['paired_difference'] == .5  # not the difference of the marginal accuracies
    assert a['fixed_denominator_difference_sensitivity'] == .2
    assert a['unknown_outcome_difference_bounds'] == [-.2, .6]
    assert a['ci95'] == [0., 1.]
    with pytest.raises(ValueError): compare(x, y[:-1], policy())
    y[5]['eligible'] = True
    with pytest.raises(ValueError): compare(x, y, policy())


def test_length_scored_and_eos_sensitivity(sample):
    sample[3][0]['finish_reason'] = 'length'
    r = score(sample); c = counts(r)
    assert c['length_stops'] == 1 and c['correct'] == 1 and c['eos_only_accuracy'] == 0
    assert compare(r, r, policy())['eos_only_pairs'] == 2


def test_zero_evaluable_is_unknown_not_zero_accuracy(sample):
    c = counts(score(sample)[-1:])
    assert c['predefined_evaluable'] == 0 and c['accuracy_on_completed'] is None
    assert c['fixed_denominator_success_sensitivity'] is None


def test_multiplicity_and_all_incomplete(sample):
    assert exact_mcnemar(8, 0) == .0078125
    rows = [{'mcnemar_p_two_sided': v} for v in [.01, .02, .2, None]]
    holm(rows)
    assert [r['mcnemar_p_holm_8'] for r in rows] == [.04, .06, .4, None]
    r = score(sample)[3:]
    a = compare(r, deepcopy(r), policy())
    assert a['complete_pairs'] == 0 and a['paired_difference'] is None and a['mcnemar_p_two_sided'] is None


def test_compatibility_scorer_accepts_structural_null_request_without_miscount(sample):
    tasks, ev, _, predictions = sample
    predictions[-1]['result_kind'] = 'model'
    records, summary = score_predictions(tasks[-1:], {'t5': ev['t5']}, predictions[-1:], 'model')
    assert summary['structural_not_evaluable'] == 1 and summary['evaluable'] == 0
    assert summary['fixed_denominator_success_sensitivity'] is None
    assert records[0]['correct'] is None
