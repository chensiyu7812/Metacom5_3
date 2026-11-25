"""Synthetic source/response fixtures only."""
import pytest

from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.temporal_outcomes import (
    join_temporal_outputs,representation_oracle,temporal_aggregate,validate_temporal_review)


def test_oracle_chooses_whole_arm_not_atomwise_union():
    audits={'t':dict(atoms=[dict(atom_id=x,required=True,status_end_history='supported') for x in ('a','b')])}
    rows=[dict(task_id='t',arm=arm,atoms=[dict(atom_id='a',observed=a),dict(atom_id='b',observed=b)])
          for arm,a,b in [('RAW','complete','omitted'),('SPAN','omitted','complete'),('TYPED_OR_SUM','omitted','omitted')]]
    report=representation_oracle(rows,audits)
    assert report['taskwise']==dict(complete_atoms=1,complete_tasks=0)
    assert report['rows'][0]['selected_whole_representation']=='SPAN'
    assert report['atom_splicing'] is False and report['reward'] is None


def test_unknown_only_cannot_be_complete():
    audits={'t':dict(atoms=[dict(atom_id='a',required=True,status_end_history='unknown')])}
    rows=[dict(task_id='t',arm=a,atoms=[dict(atom_id='a',observed='uncertain')]) for a in ('RAW','SPAN','TYPED_OR_SUM')]
    assert representation_oracle(rows,audits)['taskwise']==dict(complete_atoms=0,complete_tasks=0)
    with pytest.raises(ValueError):representation_oracle(rows+rows[:1],audits)


def test_logical_reuse_requires_identical_payload():
    payload=dict(messages=[dict(content='fixture')],input_ids=[1])
    sha=object_sha256(payload)
    logical=[dict(logical_id=a,request_id='r',payload_sha256=sha,model_input=payload) for a in ('one','two')]
    physical=[dict(request_id='r',request=logical[0],output=dict(text='response'),output_sha256='output')]
    joined=join_temporal_outputs(logical,physical)
    assert len(joined)==2 and all(r['physical_reuse_count']==2 for r in joined)
    with pytest.raises(ValueError):join_temporal_outputs(logical,physical*2)
    wrong=[{**logical[0],'model_input':dict(messages=[])}]
    with pytest.raises(ValueError):join_temporal_outputs(wrong,physical)


def test_source_output_date_and_reward_boundaries():
    audit=dict(task_id='task',atoms=[dict(atom_id='a',required=True,status_explicit_date='supported')])
    joined=dict(logical_id='logical',request_id='r',output_sha256='o',request=dict(original_task_id='task',arm='fixture',model_input=dict(messages=[dict(content='The puzzle is only planned.'),dict(content='When?')])),output=dict(text='It is planned.'))
    review=dict(logical_id='logical',request_id='r',original_task_id='task',arm='fixture',output_sha256='o',source_sessions_count=1,future_sources=0,atoms=[dict(atom_id='a',reference_status='supported',observed='complete',output_quotes=['planned'],source_quotes=[dict(quote='only planned')])],additional_findings=[],formal_semantic_status='uncertain',reward=None)
    delivery=dict(cutoff='2031-04-01',source_reports=['2031-03-31'],source_sessions=['fixture'])
    assert validate_temporal_review(review,joined,audit,delivery)
    with pytest.raises(ValueError):validate_temporal_review(review,joined,audit,{**delivery,'source_reports':['2031-04-02']})
    with pytest.raises(ValueError):validate_temporal_review({**review,'reward':1},joined,audit,delivery)
    with pytest.raises(ValueError):validate_temporal_review({**review,'atoms':[]},joined,audit,delivery)


def test_costs_and_reuse_are_separate_from_logical_arm_totals():
    rows=[]
    for arm in ('Time-Lexical','Hybrid'):
        rows.append(dict(arm=arm,request_id='one-physical',atoms=[dict(reference_status='supported',observed='complete',frozen_group_covered=True,source_quotes=[dict(quote='fixture')])],source_sessions_count=4,future_sources=0,abstention_status='none',technical=dict(input_tokens=10,output_tokens=3,seconds=2)))
    result=temporal_aggregate(rows)
    assert result['physical_outputs']==1 and result['logical_outputs']==2
    assert result['physical_seconds']==2 and result['physical_input_tokens']==10
    assert result['by_arm']['Hybrid']['source_sessions_delivered']==4
