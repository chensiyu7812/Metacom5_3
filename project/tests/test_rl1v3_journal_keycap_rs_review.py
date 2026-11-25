"""Original rubric/evidence and exact reuse guardrails; never semantic grading."""
import copy
import json
import os
from pathlib import Path

import pytest

from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal import keycap_rs_review as R


def observation_fixture():
    case=dict(case_id='masked',task_id='task',response='Exact observed reply.',response_sha256='hash',
        technical_status='returned_eos',evalspec=dict(requirements=[dict(id='r1',criterion='fixture necessary')],
        prohibitions=[dict(id='p1',criterion='fixture prohibited')]))
    observation=dict(case_id='masked',task_id='task',response_sha256='hash',qualified_reward=None,auxiliary_flags=[],
        items=[dict(item_id=i['id'],criterion=i['criterion'],observation='pass',formal_verdict='uncertain',
            evidence_quote=case['response'],start_char=0,end_char=len(case['response']),reason='evidence reasoning')
            for i in case['evalspec']['requirements']+case['evalspec']['prohibitions']])
    return case,observation


def test_unknown_is_not_success_failure_and_explicit_failure_dominates():
    case,observation=observation_fixture()
    assert R.validate_observation(observation,case)==[1,1]
    observation['items'][0]['observation']='uncertain'
    assert R.validate_observation(observation,case)==[0,1]
    observation['items'][1]['observation']='fail'
    assert R.validate_observation(observation,case)==[0,0]


@pytest.mark.parametrize('mutation',['quote','negative_offset','empty_span','new_criterion','duplicate_criterion','reward','self_qualified','technical_as_pass','new_flag_criterion'])
def test_modified_evidence_or_qualification_rejected(mutation):
    case,observation=observation_fixture()
    if mutation=='quote':observation['items'][0]['evidence_quote']='invented evidence'
    if mutation=='negative_offset':observation['items'][0]['start_char']=-1
    if mutation=='empty_span':observation['items'][0].update(start_char=0,end_char=0,evidence_quote='')
    if mutation=='new_criterion':observation['items'][0]['criterion']='posthoc new condition'
    if mutation=='duplicate_criterion':observation['items'][1]=copy.deepcopy(observation['items'][0])
    if mutation=='reward':observation['qualified_reward']=1
    if mutation=='self_qualified':observation['items'][0]['formal_verdict']='pass'
    if mutation=='technical_as_pass':case['technical_status']='technical_length'
    if mutation=='new_flag_criterion':observation['auxiliary_flags']=[dict(flag='x',quote='Exact',start_char=0,end_char=5,part_of_frozen_rubric=True)]
    with pytest.raises(ValueError):R.validate_observation(observation,case)


def test_exact_dp_ret_payload_reuse_is_one_physical_reply(monkeypatch):
    logical=[];unique={}
    for task in ['a','b','c']:
        for arm in ['R0','Generic','DP-RAW','DP-Method','RET-Method','F-resident']:
            identity=task+':'+('DP-Method' if task!='a' and arm=='RET-Method' else arm)
            row=dict(task_id=task,arm=arm,request_id=identity,payload_sha256=identity,model_input={'message':identity})
            logical.append(row);unique.setdefault(identity,row)
    physical=list(unique.values());plan=dict(task_ids=['a','b','c'],ordered_request_ids=list(unique))
    monkeypatch.setattr(R,'R1_PLAN_SHA',object_sha256(plan))
    R.validate_rows(plan,physical,logical)
    assert len(physical)==16 and len(logical)==18
    logical[-2]=dict(logical[-2],model_input={'message':'changed'})
    with pytest.raises(ValueError,match='nonidentical'):R.validate_rows(plan,physical,logical)


@pytest.mark.parametrize('mutation',['wrong_input','fake_eos','after_eos','invalid_time'])
def test_worker_measurement_and_termination_mismatch_rejected(mutation):
    row=dict(input_tokens=20,model_input=dict(decode=dict(eos_token_id=[1],max_new_tokens=4)))
    value=dict(input_tokens=20,token_ids=[3,1],text='fixture reply',seconds=1.0,finish_reason='eos')
    R.validate_worker_return(row,value)
    if mutation=='wrong_input':value['input_tokens']=21
    if mutation=='fake_eos':value['token_ids']=[3,4]
    if mutation=='after_eos':value['token_ids']=[3,1,2]
    if mutation=='invalid_time':value['seconds']=float('nan')
    with pytest.raises(ValueError):R.validate_worker_return(row,value)


ROOT=os.environ.get('JOURNAL_KEYCAP_RS')


@pytest.mark.skipif(not ROOT,reason='actual private R1 review not supplied')
def test_actual_review_denominators_and_public_no_raw_or_gold():
    root=Path(ROOT)
    rows=R.jl(root/'PAIRED_REVIEW_PRIVATE.jsonl');summary=json.loads((root/'SUMMARY_PUBLIC.json').read_text())
    assert len(rows)==18 and len({r['request_id'] for r in rows})==16
    assert sum(r['exact_physical_reuse'] for r in rows)==2
    assert sum(summary['physical_item_observations'].values())==64
    assert sum(summary['logical_item_observations'].values())==72
    assert summary['supply_strata']['entry_or_stop_boundary_requires_nonapplication']['logical_arms']==0
    assert summary['qualified_reward_count']==0
    serialized=json.dumps(summary)
    for row in rows:
        assert row['formal_reward'] is None and row['formal_task_interval']==[0,1]
        assert row['response'] not in serialized and row['question'] not in serialized
        assert all(i['criterion'] not in serialized for i in row['items'])
    for request_id in {r['request_id'] for r in rows}:
        paired=[r for r in rows if r['request_id']==request_id]
        if len(paired)>1:
            assert {r['arm'] for r in paired}=={'DP-Method','RET-Method'}
            assert paired[0]['response']==paired[1]['response'] and paired[0]['items']==paired[1]['items']
