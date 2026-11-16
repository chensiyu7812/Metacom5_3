import json
from metacom_pm.rl1.judge_scoped import parse_scoped


def fixture():
    evidence = dict(current_date='2025-01-01', legal_past_sessions=[], current_prefix=[
        dict(id='C:T000', role='seeker', text='I am considering asking my manager for help.')])
    reply = 'That sounds encouraging. You have already asked your manager and it worked.'
    value = dict(status='scored', q=1,
        q_rationale=dict(current_need='Discuss a possible request.', response_unit_ids=['R001', 'R002'],
                         source_turn_ids=['C:T000'], reason='Completion is not established.'),
        assessments=[dict(response_unit_id='R001', kind='non_factual', relation='not_applicable', severity=0,
                          source_turn_ids=[], reason='Supportive evaluation, not a personal factual assertion.'),
                     dict(response_unit_id='R002', kind='personal_fact', relation='unsupported', severity=1,
                          source_turn_ids=['C:T000'], reason='An intention establishes neither action nor success.')],
        coverage='Both reply units checked.', uncertainty_reasons=[])
    bindings=dict(evidence=evidence,reply=reply,runtime_identity='test',draw_id='test',finish_reason='natural_stop')
    return value, bindings


def test_explicit_scope_and_derived_severity_preserve_full_audit():
    value, bindings=fixture(); result=parse_scoped(json.dumps(value),**bindings)
    assert result['measurement_status']=='measured_candidate'
    assert result['m']==1 and result['derived_error_indexes']==[0]
    assert len(result['scoped_judge_output']['assessments'])==2
    assert len(result['parsed']['claims'])==1
    assert not result['reward_eligible']


def test_no_parser_guess_of_nonfactual_scope():
    value,bindings=fixture()
    value['assessments'][0].update(kind='personal_fact',relation='unsupported')
    assert parse_scoped(json.dumps(value),**bindings)['measurement_status']=='parse_or_evidence_failure'


def test_supported_assertion_and_nonfactual_do_not_get_penalties():
    value,bindings=fixture()
    value['assessments'][1].update(relation='supported',severity=0)
    result=parse_scoped(json.dumps(value),**bindings)
    # This deliberately false support assignment passes mechanical validation;
    # illustrates why citations/syntax alone must not be called semantic truth.
    assert result['m']==0 and result['semantic_validation'] is False


def test_uncertainty_not_replaced_with_zero():
    value,bindings=fixture()
    value.update(status='uncertain',q=None,uncertainty_reasons=['Ambiguous claim.'])
    value['assessments'][1].update(relation='uncertain',severity=0)
    result=parse_scoped(json.dumps(value),**bindings)
    assert result['measurement_status']=='semantic_uncertainty' and result['m'] is None


def test_nonfactual_kind_cannot_hide_severity_or_bad_ids():
    value,bindings=fixture()
    value['assessments'][0]['severity']=.25
    assert parse_scoped(json.dumps(value),**bindings)['measurement_status']=='parse_or_evidence_failure'
    value,bindings=fixture();value['assessments'][0]['source_turn_ids']=['H999:T000']
    assert parse_scoped(json.dumps(value),**bindings)['measurement_status']=='parse_or_evidence_failure'
