"""Evidence/reuse/uncertainty guardrails; no semantic labels are inferred here."""
import copy
import json
import os
from pathlib import Path

import pytest

from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal import closeout_rs as R


def fixture_rows():
    logical=[];unique={}
    for task in ['a','b','c']:
        for arm in ['R0','Generic','DP-RAW','DP-Method','RET-Method','F-resident']:
            identity=task+':'+('DP-Method' if task=='a' and arm=='RET-Method' else arm)
            row=dict(task_id=task,arm=arm,request_id=identity,payload_sha256=identity,model_input={'message':identity})
            logical.append(row);unique.setdefault(identity,row)
    return dict(batch_number=3,task_ids=['a','b','c'],ordered_request_ids=list(unique)),list(unique.values()),logical


def test_complete_pairing_uses_exact_payload_identity(monkeypatch):
    plan,physical,logical=fixture_rows();monkeypatch.setitem(R.PLAN_SHAS,3,object_sha256(plan))
    R.validate_rows(plan,physical,logical)
    logical[4]=dict(logical[4],model_input={'message':'different'})
    with pytest.raises(ValueError,match='nonidentical'):R.validate_rows(plan,physical,logical)


@pytest.mark.parametrize('mutation',['plan','drop','duplicate_arm','reorder'])
def test_changed_plan_incomplete_batch_or_wrong_arm_rejected(monkeypatch,mutation):
    plan,physical,logical=fixture_rows();monkeypatch.setitem(R.PLAN_SHAS,3,object_sha256(plan))
    if mutation=='plan':plan['batch_number']=2
    if mutation=='drop':logical.pop()
    if mutation=='duplicate_arm':logical[1]=dict(logical[1],arm='R0')
    if mutation=='reorder':physical.reverse()
    with pytest.raises(ValueError):R.validate_rows(plan,physical,logical)


def test_interval_overlap_is_not_a_win_and_exact_reuse_is_not_replication():
    rows=[]
    for task,a,b,identical in [('a',[1,1],[0,1],False),('b',[1,1],[0,0],False),('c',[1,1],[1,1],True)]:
        for arm,val in [('DP-Method',a),('RET-Method',b)]:
            rows.append(dict(task_id=task,arm=arm,request_id=task if identical else task+arm,
                development_interval=val,items=[dict(item_id='r1',observation='pass' if val==[1,1] else 'fail' if val==[0,0] else 'uncertain')]))
    result=R.paired_comparison(rows,'DP-Method','RET-Method')
    assert result['task_interval_comparison']=={'uncertain_overlap':1,'left_better':1,'tie':1}
    assert result['exact_shared_physical_outputs']==1


def packet_fixture(tmp_path):
    frozen=tmp_path/'frozen';frozen.mkdir();bank=tmp_path/'bank.json';queue=tmp_path/'queue.json'
    bank.write_text(json.dumps({'supplements':[]}));inputs=[];refs=[];rows=[]
    for n in range(5):
        item=dict(item_id=str(n),source_group='synthetic',stratum='official_behavior',premise='Synthetic question.',hypothesis='Synthetic proposition.')
        ref=dict(item_id=str(n),reference='fail',evidence={},provenance='synthetic fixture')
        inputs.append(item);refs.append(ref);rows.append(dict(reason='official_primary_behavior_disagreement',input=item,reference=ref,prediction={'prediction':'pass'}))
    for name,records in [('INPUTS_PRIVATE.jsonl',inputs),('REFERENCES_PRIVATE.jsonl',refs)]:
        (frozen/name).write_text(''.join(json.dumps(r)+'\n' for r in records))
    (frozen/'PROTOCOL_FROZEN.json').write_text(json.dumps({'inputs_sha256':{str(bank):R.file_sha256(bank)}}))
    queue.write_text(json.dumps({'rows':rows}));return queue,frozen,bank


def test_finite_packet_keeps_pending_human_and_original_reference(tmp_path):
    queue,frozen,bank=packet_fixture(tmp_path)
    original=queue.read_bytes();out=tmp_path/'out';result=R.human_packet(queue,frozen,bank,out)
    assert queue.read_bytes()==original and result['pending_real_human']==5
    assert result['new_human_judgments']==result['reference_replacements']==0
    assert all(r['human_decision'] is None and r['human_reviewer'] is None for r in R.jl(out/'ITEMS_PRIVATE.jsonl'))
    assert 'Synthetic question.' not in (out/'SUMMARY_PUBLIC.json').read_text()


def test_modified_queue_reference_rejected(tmp_path):
    queue,frozen,bank=packet_fixture(tmp_path);rows=json.loads(queue.read_text());rows['rows'][0]['reference']['reference']='pass';queue.write_text(json.dumps(rows))
    with pytest.raises(ValueError,match='queue differs'):R.human_packet(queue,frozen,bank,tmp_path/'out')


ROOT=os.environ.get('JOURNAL_CLOSEOUT_RS')
@pytest.mark.skipif(not ROOT,reason='actual private full closeout review not supplied')
def test_actual_all_twelve_tasks_and_privacy():
    root=Path(ROOT);rows=R.jl(root/'PAIRED_REVIEW_PRIVATE.jsonl');s=json.loads((root/'SUMMARY_PUBLIC.json').read_text());public=json.dumps(s)
    assert len(rows)==72 and len({r['request_id'] for r in rows})==68
    assert len({r['task_id'] for r in rows})==12
    assert sum(s['physical_item_observations'].values())==272
    assert sum(s['logical_item_observations'].values())==288
    assert s['actual_compute']['physical_calls']==68 and s['qualified_reward_count']==0
    for r in rows:
        assert r['response'] not in public and r['question'] not in public
        assert r['formal_reward'] is None and all(i['criterion'] not in public for i in r['items'])
    assert s['by_original_task_strata']['direct_coverage']['core_applicable']['DP-Method']['tasks']==7
    assert s['by_original_task_strata']['direct_coverage']['partial_coverage']['DP-Method']['tasks']==5
    assert s['by_original_task_strata']['ret_applicability_class']['entry_or_stop_boundary_requires_nonapplication']['RET-Method']['tasks']==3
