import pytest
from metacom_pm.rl1v3.journal.eval_calibration import benefit,completion_reference,metrics,program


def test_actual_missing_enum_is_not_silently_relabelled_unknown():
    assert completion_reference('missing')=='fail'
    assert completion_reference('abstained')=='fail'
    assert completion_reference('underspecified')=='unknown'
    with pytest.raises(ValueError,match='unrecognized atomic observation'):completion_reference('new_unhandled_status')


def test_unknown_reference_never_becomes_negative():
    result=metrics([dict(reference='unknown',prediction='pass'),dict(reference='unknown',prediction='unknown')])
    assert result['false_pass_rate'] is None and result['false_fail_rate'] is None
    assert result['reference_known']==0 and result['unsupported_pass_on_unknown']==1
    assert result['unknown_rate']==.5


def test_unknown_prediction_preserves_known_denominator():
    result=metrics([dict(reference='fail',prediction='unknown'),dict(reference='pass',prediction='fail')])
    assert result['false_pass']==0 and result['false_fail']==1
    assert result['negative_reference_denominator']==1 and result['unknown_on_known_reference']==1


def test_source_delivery_requires_complete_conjunctive_group():
    payload=dict(delivered_sessions=['s1'],requirements=[dict(reference_state='supported',groups=[['s1:1','s2:5']])])
    assert program(payload,'source_coverage')=='fail'
    payload['delivered_sessions'].append('s2')
    assert program(payload,'source_coverage')=='pass'
    payload['requirements'][0]['reference_state']='scope_conflict'
    assert program(payload,'source_coverage')=='unknown'


def test_month_interval_is_not_silently_end_of_month():
    payload=dict(cutoff=dict(lower='2025-01-01',upper='2025-01-31'),sources=[dict(date='2025-01-15')])
    assert program(payload,'temporal_legality')=='unknown'
    payload['cutoff']['upper']='2025-01-01'
    assert program(payload,'temporal_legality')=='fail'


def test_literal_target_substring_is_not_semantic_pass():
    assert program(dict(response='Not blue',target='blue'),'atomic_completion')=='unknown'
    assert program(dict(response='I do not know, but perhaps blue',target='blue'),'atomic_completion')=='unknown'
    assert program(dict(response='blue',target='blue'),'atomic_completion')=='pass'


def test_historical_ties_are_nonpositive_and_unknown_is_separate():
    assert benefit('equivalent','A')=='fail'
    assert benefit('uncertain','B')=='unknown'
    assert benefit('B_better','B')=='pass'
