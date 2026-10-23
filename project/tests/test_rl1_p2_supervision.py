import json
import pytest
from metacom_pm.rl1.p2_supervision import CHECKS,validate_review,review_messages


def example():
    docs=[dict(id='C0',scope='VISIBLE',text='I intend to call tomorrow.'),
          dict(id='S0',scope='SOURCE',text='The user already met a friend.')]
    value=dict(status='accept',checks={k:True for k in CHECKS},
        claims=[dict(output_quote='You plan to call',verdict='supported',
            evidence=[dict(document_id='C0',quote='intend to call tomorrow')],reason='Intention, not completed action.')],
        resource_behavior='none',rationale='Matches the reported intention.',repairable=False,repair_instruction='')
    return docs,value


def test_valid_citation_is_weak_supervision_not_reward():
    d,v=example();r=validate_review(json.dumps(v),'You plan to call tomorrow.',d)
    assert 'weak supervision' in r['review_type'] and 'reward' in r['review_type']


@pytest.mark.parametrize('mutation', ['quote','output','hidden','verdict','check','repair','omission'])
def test_uncertain_or_unbound_review_cannot_enter_accept(mutation):
    d,v=example();c=v['claims'][0]
    if mutation=='quote':c['evidence'][0]['quote']='already called'
    elif mutation=='output':c['output_quote']='You already called'
    elif mutation=='hidden':c['evidence']=[dict(document_id='S0',quote='already met a friend')]
    elif mutation=='verdict':c['verdict']='uncertain'
    elif mutation=='check':v['checks']['speaker_identity']=False
    elif mutation=='repair':v['repairable']=True;v['repair_instruction']='Fix attribution'
    else:del v['checks']['speaker_identity']
    with pytest.raises(ValueError):validate_review(json.dumps(v),'You plan to call tomorrow.',d)


def test_reviewer_input_does_not_modify_student_messages():
    d,_=example();slot=dict(messages=[dict(role='user',content='Help')]);original=json.dumps(slot)
    m=review_messages(slot,'Can you say more?',d)
    assert json.dumps(slot)==original and 'SOURCE-only' in m[0]['content']
