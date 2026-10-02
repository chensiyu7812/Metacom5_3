import pytest
from metacom_pm.rl1.executor_engineering import admitted_rows
from metacom_pm.rl1.executor_pilot import admitted_rows as research_admission
from metacom_pm.rl1.schema import digest

@pytest.fixture
def batch():
    # Minimal unit-test records, not research supervision. Include one rejected
    # cell: engineering admission may retain it as missing, research may not.
    contract=dict(status='POST_HOC_ENGINEERING_ONLY',eligible_for_research_or_rl=False,conditions=[])
    jobs=[];requests={};raws={};reviews={}
    for index in range(1,6):
        split='train' if index<5 else 'dev'
        for condition in ('OFF','R','L'):
            messages=[dict(role='user',content=f'Unit-test current turn {index}, condition {condition}')]
            contract['conditions'].append(dict(index=index,condition=condition,split=split,owner=f'fixture{index}',
                head=None if condition=='OFF' else 'MS',prefix_identity=str(index),messages=messages,messages_identity=digest(messages)))
            payload=dict(messages=messages,executor_identity='unit-test-author',seed=17)
            key=digest(payload);requests[key]=dict(**payload,request_id=key)
            jobs.append(dict(index=index,condition=condition,split=split,request_id=key))
            raw=dict(request_id=key,runtime_identity='unit-test-author',text='Unit-test answer',finish_reason='natural_stop')
            raws[key]=raw
            reviews[key]=dict(request_identity=key,raw_identity=digest(raw),messages_identity=digest(messages),
                status='reject' if index==1 and condition=='R' else 'accept',rationale='Unit-test bound review',
                checks=dict(grounding=True),unresolved_claims=[],historical_uptake=condition=='L')
    return contract,jobs,requests,raws,reviews

def test_engineering_uses_all_and_only_accepted_rows_and_does_not_pass_research_gate(batch):
    rows=admitted_rows(*batch)
    assert len(rows)==14
    assert {r['request_id'] for r in rows}=={k for k,v in batch[-1].items() if v['status']=='accept'}
    with pytest.raises(ValueError,match='per prefix-condition'):research_admission(*batch)

def test_cannot_silently_promote_engineering_adapter_to_research(batch):
    batch[0]['eligible_for_research_or_rl']=True
    with pytest.raises(ValueError,match='engineering-only'):admitted_rows(*batch)

def test_changed_response_cannot_inherit_original_review(batch):
    rid=next(k for k,r in batch[-1].items() if r['status']=='accept')
    batch[3][rid]['text']='silently improved response'
    with pytest.raises(ValueError,match='review not bound'):admitted_rows(*batch)
