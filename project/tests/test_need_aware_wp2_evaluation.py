"""Synthetic contract regressions, never model capability evidence."""
from copy import deepcopy
import json
import pytest

from metacom_pm.need_aware.data.contracts import RuntimeTask
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.wp2 import (
    score_cell, counts, compare, holm, exact_mcnemar,
)
from metacom_pm.need_aware.evaluation.score import score_predictions
from metacom_pm.need_aware.evaluation.export import read_ledger, predictions_from_ledger, execution_metrics
from metacom_pm.need_aware.data.contracts import digest
from metacom_pm.need_aware.evaluation.review import error_census


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


def test_error_review_census_includes_all_errors_and_discordances_not_noncompletion(sample):
    rows = score(sample)
    for r in rows:
        r['category']['pref_type'] = 'third_party'
    cells = {m+'|'+a: deepcopy(rows) for m in ('G0e', 'Qwen35') for a in 'ABCD'}
    # B error repaired by C must enter even though both C and D are correct.
    cells['G0e|B'][0].update(correct=False, outcome='wrong_answer')
    queue, report = error_census(cells)
    assert set(queue) == {'t0', 't1', 't2'}
    assert queue['t0'] == ['G0e|B->C_discordance']
    assert set(queue['t2']) == {'G0e|C_error', 'G0e|D_error', 'Qwen35|C_error', 'Qwen35|D_error'}
    assert report['review_tasks'] == 3
    assert report['complete_pair_transitions']['G0e|B->C/all'] == {
        'wrong_answer -> correct': 1, 'wrong_answer -> wrong_answer': 1,
        'parse_failure -> parse_failure': 1}
    assert report['errors_by_observed_outcome']['G0e|C/all'] == {'wrong_answer/eos': 1, 'parse_failure/eos': 1}
    cells['G0e|B'].pop()
    with pytest.raises(ValueError): error_census(cells)


def ledger_events(sample):
    events = []
    def add(event, **kw):
        e = dict(event=event, seq=len(events), manifest_sha256='manifest',
                 previous_event_sha256=events[-1]['event_sha256'] if events else None, **kw)
        e['event_sha256'] = digest(e); events.append(e)
    add('RUN_START', result_kind='plumbing')
    for i, terminal in [(0, 'ATTEMPT_RESULT'), (1, 'ATTEMPT_FAILED'), (2, 'ATTEMPT_INVALID'), (3, None)]:
        fields = dict(logical_id=f't{i}|C|G0e', model_label='G0e', request_sha256=f'req{i}', attempt=1)
        add('ATTEMPT_START', **fields)
        if terminal:
            add(terminal, **fields, text='Final Answer: B', finish_reason='length', plumbing=True, error='TimeoutError')
    return events, add


def test_ledger_adapter_classifies_timeout_invalid_interrupted_and_not_attempted(sample):
    events, _ = ledger_events(sample)
    rows, run_id = predictions_from_ledger(list(sample[2].values()), events, kind='plumbing')
    assert [r['failure_kind'] for r in rows] == [None, 'timeout', 'invalid_output', 'interrupted', 'unattempted', None]
    assert rows[0]['status'] == 'completed' and rows[-1]['status'] == 'not_evaluable'
    assert all(r['run_id'] == run_id for r in rows)
    with pytest.raises(ValueError): predictions_from_ledger(list(sample[2].values()), events, kind='model')


def test_ledger_adapter_retries_failed_only_and_first_success_is_preserved(sample):
    events, add = ledger_events(sample)
    fields = dict(logical_id='t1|C|G0e', model_label='G0e', request_sha256='req1', attempt=2)
    add('ATTEMPT_START', **fields)
    add('ATTEMPT_RESULT', **fields, text='Answer: A', finish_reason='eos', plumbing=True)
    rows, _ = predictions_from_ledger(list(sample[2].values()), events, kind='plumbing')
    assert rows[1]['status'] == 'completed' and rows[1]['attempt_count'] == 2
    add('ATTEMPT_START', logical_id='t0|C|G0e', model_label='G0e', request_sha256='req0', attempt=2)
    with pytest.raises(ValueError): predictions_from_ledger(list(sample[2].values()), events, kind='plumbing')


def test_ledger_hash_chain_and_torn_tail(sample, tmp_path):
    events, _ = ledger_events(sample)
    f = tmp_path/'LEDGER.001.jsonl'
    f.write_text(''.join(json.dumps(e)+'\n' for e in events)+'{"torn":')
    actual, tails = read_ledger(tmp_path, 'manifest')
    assert actual == events and len(tails) == 1
    events[1]['attempt'] = 100
    f.write_text(''.join(json.dumps(e)+'\n' for e in events))
    with pytest.raises(ValueError): read_ledger(tmp_path, 'manifest')


def test_cost_accounting_preserves_interrupted_timeout_and_unknown_latency():
    events = [dict(event='LOAD_START', model_label='G0e', session_id='one', session_elapsed_s=0, max_seconds=900),
              dict(event='MODEL_SESSION_END', model_label='G0e', session_id='one', session_elapsed_s=25),
              dict(event='ATTEMPT_START', model_label='G0e', session_id='two', session_elapsed_s=7, max_seconds=300),
              dict(event='LOAD_FAILED', model_label='Qwen35', session_id='three', session_elapsed_s=19)]
    m = execution_metrics(events)
    assert m['per_model']['G0e']['ledger_accounted_gpu_seconds'] == 332
    assert m['ledger_accounted_gpu_seconds'] == 351
    assert m['per_model']['Qwen35']['load_failures'] == 1
    assert m['per_cell']['G0e|A']['internal_first_token_seconds']['p50'] is None
