import json

from metacom_pm.rl1.pair_review import messages_and_schema, parse_pair


def fixture():
    item = dict(evidence=dict(current_date='2025-01-01', legal_past_sessions=[],
                             current_prefix=[dict(id='C:T000', role='seeker', text='I only want to talk.')]),
                replies={'A': 'I am listening.', 'B': 'You must take my advice.'})
    v = dict(assessments={label: dict(decisive_reason='Bound test rationale', source_turn_ids=['C:T000'],
                                    response_unit_ids=['R001'], limitations='', status='scored', q=q, m=m)
                         for label, q, m in [('A', 4, 0), ('B', 1, 1)]},
             comparison_reason='Reply A respects the stated need.', pairwise='A_better')
    return item, v


def test_blind_payload_has_no_method_or_scores():
    item, _ = fixture()
    item.update(condition='SECRET_ARM', expected_q=4, training_judge_score=99)
    messages, schema = messages_and_schema(item)
    assert 'SECRET_ARM' not in json.dumps(messages)
    assert 'training_judge_score' not in json.dumps(messages)
    assert schema['properties']['assessments']['properties']['A']['properties']['source_turn_ids']['items']['enum'] == ['C:T000']


def test_valid_review_is_model_diagnostic_not_reward():
    item, v = fixture()
    result = parse_pair(json.dumps(v), item, 'natural_stop')
    assert result['status'] == 'model_review_candidate'
    assert result['reviewer_kind'] == 'model'
    assert not result['reward_eligible'] and not result['semantic_validation']


def test_unknown_source_and_response_are_rejected():
    for field, bad in [('source_turn_ids', 'H999:T000'), ('response_unit_ids', 'R999')]:
        item, v = fixture()
        v['assessments']['A'][field] = [bad]
        assert parse_pair(json.dumps(v), item, 'natural_stop')['status'] == 'parse_failure'


def test_uncertainty_remains_null_not_zero():
    item, v = fixture()
    v['assessments']['A'].update(status='uncertain', q=None, m=None, limitations='Evidence ambiguous.')
    v['pairwise'] = 'uncertain'
    result = parse_pair(json.dumps(v), item, 'natural_stop')
    assert result['verdict']['assessments']['A']['q'] is None
    v['assessments']['A']['m'] = 0
    assert parse_pair(json.dumps(v), item, 'natural_stop')['status'] == 'parse_failure'


def test_technical_failure_does_not_parse_a_partial_verdict():
    item, v = fixture()
    result = parse_pair(json.dumps(v), item, 'context_exhausted')
    assert result['status'] == 'technical_failure' and result['verdict'] is None


def test_duplicate_final_verdict_is_not_silently_overwritten():
    item, v = fixture()
    raw = json.dumps(v)[:-1] + ', "pairwise": "B_better"}'
    assert parse_pair(raw, item, 'natural_stop')['status'] == 'parse_failure'
