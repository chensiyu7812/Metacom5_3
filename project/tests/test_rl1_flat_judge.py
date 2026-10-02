import json
import pytest
from test_rl1_scoped_judge import fixture
from metacom_pm.rl1.judge_flat import parse_flat, messages_and_schema


def flat_fixture():
    value, bindings = fixture()
    for a in value['assessments']:
        if a.pop('kind') == 'non_factual': a['relation'] = 'non_factual'
    return value, bindings


def test_flat_scope_preserves_m_and_does_not_claim_semantic_validation():
    v, b = flat_fixture(); r = parse_flat(json.dumps(v), **b)
    assert r['measurement_status'] == 'measured_candidate' and r['m'] == 1
    assert r['flat_judge_output'] == v and not r['semantic_validation'] and not r['reward_eligible']


@pytest.mark.parametrize('relation,severity', [('unsupported', 0), ('non_factual', 1), ('supported', .25), ('uncertain', 1)])
def test_illegal_combinations_are_not_repaired(relation, severity):
    v, b = flat_fixture(); v['assessments'][0].update(relation=relation, severity=severity)
    assert parse_flat(json.dumps(v), **b)['measurement_status'] == 'parse_or_evidence_failure'


def test_evidence_and_uncertainty_still_required():
    v, b = flat_fixture(); v['assessments'][1].update(relation='contradicted', source_turn_ids=[])
    assert parse_flat(json.dumps(v), **b)['measurement_status'] == 'parse_or_evidence_failure'
    v, b = flat_fixture(); v['assessments'][1].update(relation='uncertain', severity=0)
    assert parse_flat(json.dumps(v), **b)['measurement_status'] == 'parse_or_evidence_failure'
    v.update(status='uncertain', q=None, uncertainty_reasons=['Ambiguous.'])
    r = parse_flat(json.dumps(v), **b)
    assert r['measurement_status'] == 'semantic_uncertainty' and r['m'] is None


def test_redundant_kind_is_rejected():
    v, b = flat_fixture(); v['assessments'][0]['kind'] = 'personal_fact'
    assert parse_flat(json.dumps(v), **b)['measurement_status'] == 'parse_or_evidence_failure'
