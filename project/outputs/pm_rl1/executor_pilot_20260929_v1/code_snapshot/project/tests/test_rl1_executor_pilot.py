import copy
from types import SimpleNamespace
import pytest

from metacom_pm.rl1.executor_pilot import accumulation_groups, admitted_rows
from metacom_pm.rl1.schema import digest


def fixture():
    conditions=[];jobs=[];requests={};raws={};reviews={}
    for index in range(1,6):
        split='train' if index<5 else 'dev'
        messages=[dict(role='user',content=f'Current turn {index}')]
        c=dict(index=index,condition='R',split=split,owner=f'owner{index}',head='MS',
               prefix_identity=str(index),messages=messages,messages_identity=digest(messages))
        conditions.append(c)
        payload=dict(messages=messages,executor_identity='author',seed=17)
        key=digest(payload);requests[key]=dict(**payload,request_id=key)
        jobs.append(dict(index=index,condition='R',split=split,request_id=key))
        raws[key]=dict(request_id=key,runtime_identity='author',text='A suitable answer',finish_reason='natural_stop')
        reviews[key]=dict(request_identity=key,raw_identity=digest(raws[key]),messages_identity=digest(messages),
            status='accept',rationale='Reviewed against source and current request',checks=dict(grounding=True),
            unresolved_claims=[],historical_uptake=True)
    return dict(conditions=conditions),jobs,requests,raws,reviews


def test_complete_admission_retains_exact_input():
    args=fixture();rows=admitted_rows(*args)
    assert len(rows)==5 and rows[0]['messages']==args[0]['conditions'][0]['messages']
    assert 'checks' not in rows[0] and 'rationale' not in rows[0]


@pytest.mark.parametrize('mutation', ['missing_review','changed_reply','hidden_input','changed_split',
                                      'incomplete','unresolved','no_resource_uptake','rejected_condition','base_runtime'])
def test_admission_fails_closed(mutation):
    c,j,q,raw,r=fixture();key=j[0]['request_id']
    if mutation=='missing_review': del r[key]
    elif mutation=='changed_reply': raw[key]['text']='Different output'
    elif mutation=='hidden_input': q[key]['messages'].append(dict(role='system',content='Hidden history'))
    elif mutation=='changed_split': c['conditions'][0]['split']='test'
    elif mutation=='incomplete':
        raw[key]['finish_reason']='technical_timeout';r[key]['raw_identity']=digest(raw[key])
    elif mutation=='unresolved': r[key]['unresolved_claims']=['An unresolved presupposition']
    elif mutation=='no_resource_uptake': r[key]['historical_uptake']=False
    elif mutation=='rejected_condition': r[key]['status']='reject'
    elif mutation=='base_runtime': raw[key]['runtime_identity']='different'
    with pytest.raises(ValueError):admitted_rows(c,j,q,raw,r)


def test_partial_accumulation_uses_actual_target_denominator():
    examples=[({},SimpleNamespace(target_tokens=n)) for n in (2,5,3,11,7)]
    groups=list(accumulation_groups(examples,3))
    assert [len(g) for g,n in groups]==[3,2]
    assert [n for g,n in groups]==[10,18]
