import json
from test_rl1_flat_judge import flat_fixture
from metacom_pm.rl1.judge_flat import messages_and_schema as old_messages
from metacom_pm.rl1.judge_explicit import messages_and_schema,parse_explicit


def test_transport_structure_is_visible_without_changing_grammar_or_user_evidence():
    _,b=flat_fixture();new,schema=messages_and_schema(b['evidence'],b['reply'])
    old,previous=old_messages(b['evidence'],b['reply'])
    assert schema==previous and new[1:]==old[1:]
    text=new[0]['content']
    for field in ('q_rationale: an OBJECT','response_unit_ids:','assessments: an ARRAY',
                  'response_unit_id:','source_turn_ids:','uncertainty_reasons: ARRAY'):
        assert field in text


def test_prepared_parser_retains_score_math_but_never_qualifies_reward():
    v,b=flat_fixture();r=parse_explicit(json.dumps(v),**b)
    assert r['q']==1 and r['m']==1 and not r['reward_eligible']
    assert r['evaluator_execution_status']=='PREPARED_NOT_LIVE_VALIDATED'
