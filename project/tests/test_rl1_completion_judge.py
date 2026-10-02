import json
import pytest
from test_rl1_flat_judge import flat_fixture
from metacom_pm.rl1.judge_completion import (
    messages_and_schema, parse_completion, score_identity, ROLE_CONTRACT, RUBRIC_ID)


def test_current_speaker_is_bound_without_method_metadata_or_losing_source():
    _, b = flat_fixture()
    messages, _ = messages_and_schema(b['evidence'], b['reply'])
    assert ROLE_CONTRACT in messages[0]['content']
    payload = json.loads(messages[1]['content'])
    assert payload['legal_evidence'] == b['evidence']
    assert set(payload) == {'legal_evidence', 'reply', 'response_units'}
    with pytest.raises(ValueError):
        messages_and_schema(dict(b['evidence'], plan=[0, 0, 0, 0]), b['reply'])


def test_same_reply_cache_key_and_independent_draws():
    _, b = flat_fixture()
    args = (b['evidence'], b['reply'])
    a = score_identity(*args, runtime_identity='fixed')
    assert a == score_identity(*args, runtime_identity='fixed')
    assert a != score_identity(*args, runtime_identity='fixed', repeat_draw='repeat1')
    assert a != score_identity(*args, runtime_identity='fixed', recheck=True)
    assert a != score_identity(*args, runtime_identity='changed')


def test_duplicates_and_nonfinite_cannot_be_hidden_by_projection():
    v, b = flat_fixture()
    raw = json.dumps(v)
    for invalid in [raw.replace('"q": 1', '"q": 4, "q": 1'),
                    raw.replace('"severity": 1', '"severity": NaN')]:
        r = parse_completion(invalid, **b)
        assert r['q'] is None and r['m'] is None and r['candidate_utility'] is None
        assert r['measurement_status'] == 'parse_or_evidence_failure'


def test_uncertain_and_technical_are_pending_not_zero():
    v, b = flat_fixture()
    v.update(status='uncertain', q=None, uncertainty_reasons=['Source unclear.'])
    v['assessments'][1].update(relation='uncertain', severity=0)
    r = parse_completion(json.dumps(v), **b)
    assert r['candidate_utility'] is None and r['m'] is None
    r = parse_completion('', **dict(b, finish_reason='technical_timeout'))
    assert r['measurement_status'] == 'technical_failure' and r['candidate_utility'] is None


def test_exact_source_resolution_is_not_semantic_qualification():
    v, b = flat_fixture()
    r = parse_completion(json.dumps(v), **b)
    assert r['m'] == 1 and r['candidate_utility'] == -.75
    assert r['rubric_identity'] == RUBRIC_ID
    assert not r['reward_eligible'] and not r['semantic_validation']


def test_recheck_uses_same_evidence_same_schema_no_previous_numeric_scores():
    _, b = flat_fixture()
    first, schema = messages_and_schema(b['evidence'], b['reply'])
    recheck, second_schema = messages_and_schema(b['evidence'], b['reply'], recheck=True)
    assert first[1] == recheck[1] and schema == second_schema
    assert 'ONE PREDECLARED ADDITIONAL FULL-SOURCE CHECK' in recheck[0]['content']
