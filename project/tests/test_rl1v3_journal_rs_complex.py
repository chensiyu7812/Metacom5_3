"""Retrieval isolation, paired denominators and separately authorised RS scope."""
import copy
import json
import os
from pathlib import Path

import pytest

from metacom_pm.rl1v3.io import object_sha256, file_sha256
from metacom_pm.rl1v3.journal.rs_complex import ARMS, materials_for
from metacom_pm.rl1v3.journal.rs_complex_run import RUN_PROTOCOL, JOB_KIND, admit, validate_pairing, check


def test_gold_canaries_cannot_change_visible_retrieval_or_enter_material():
    task=dict(task_id='opaque',turns=[dict(role='seeker',text='practical schedule')],timestamp=None,
              private_condition='CANARY_GOLD',requirements=['CANARY_GOLD'])
    skills=[dict(skill_id='a',method_reading='practical schedule',raw_reading='original a'),
            dict(skill_id='b',method_reading='unrelated',raw_reading='original b')]
    first,selected=materials_for(task,skills,dict(direct_skill_id='b',gold='CANARY_GOLD'))
    second,other=materials_for(task,skills,dict(direct_skill_id='a',gold='CHANGED_GOLD'))
    assert selected['retrieved_skill_id']==other['retrieved_skill_id']=='a'
    assert first[4]==second[4] and first[2]!=second[2]
    assert not any('CANARY' in json.dumps(r) or 'CHANGED_GOLD' in json.dumps(r) for r in first+second)
    assert first[0]['readings']==[]


def pairing_fixture():
    frozen=[]
    for t in range(12):
        for arm in ARMS:
            physical='DP-Method' if arm=='RET-Method' else arm
            rid=f'{t}:{physical}'
            frozen.append(dict(domain='rs',task_id=str(t),arm=arm,logical_id=f'rs:{t}:{arm}',
                               request_id=rid,model_input={'same':rid}))
    logical=copy.deepcopy(frozen[:18]);unique={}
    for r in logical:unique.setdefault(r['request_id'],r)
    rows=list(unique.values())
    plan=dict(batch_number=1,task_ids=['0','1','2'],logical_requests=18,max_calls=15)
    return plan,rows,logical,frozen


def test_exact_reuse_preserves_all_six_logical_arms():
    validate_pairing(*pairing_fixture())


@pytest.mark.parametrize('mutation', ['missing_arm','changed_reuse','extra_call','wrong_batch','changed_task','duplicate_logical'])
def test_incomplete_or_changed_pairing_rejected(mutation):
    plan,rows,logical,frozen=pairing_fixture()
    if mutation=='missing_arm':logical.pop()
    if mutation=='changed_reuse':logical[4]['model_input']={'changed':'yes'}
    if mutation=='extra_call':rows.append(rows[0]);plan['max_calls']+=1
    if mutation=='wrong_batch':plan['batch_number']=2
    if mutation=='changed_task':logical[0]['task_id']='99'
    if mutation=='duplicate_logical':logical[1]=logical[0]
    with pytest.raises(ValueError):validate_pairing(plan,rows,logical,frozen)


@pytest.mark.parametrize('protocol,kind', [('pmrl1-j-smoke-run-v1','JOURNAL_SMOKE'),
    ('pmrl1-j-paired-batch-v1','JOURNAL_PAIRED_BATCH'),('pmrl1-j-memory-repr18-run-v1','JOURNAL_MEMORY_REPR18')])
def test_old_or_other_task_approval_never_transfers(protocol,kind):
    plan=dict(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,max_calls=16)
    auth=dict(authorized=True,protocol=protocol,job_kind=kind,plan_sha256=object_sha256(plan),
              max_calls=16,max_model_loads=1,researcher='fixture',decision_evidence='fixture')
    with pytest.raises(ValueError,match='cannot transfer'):admit(plan,auth)


def test_pending_is_not_authorization_and_plan_hash_is_binding():
    plan=dict(protocol=RUN_PROTOCOL,job_kind=JOB_KIND,max_calls=16)
    auth=dict(authorized=False,protocol=RUN_PROTOCOL,job_kind=JOB_KIND,plan_sha256=object_sha256(plan),
              max_calls=16,max_model_loads=1,researcher='fixture',decision_evidence='fixture')
    with pytest.raises(ValueError,match='explicit complex RS'):admit(plan,auth)
    auth['authorized']=True;auth['plan_sha256']='other'
    with pytest.raises(ValueError,match='plan hash'):admit(plan,auth)


ROOT=os.environ.get('JOURNAL_RS_COMPLEX')


@pytest.mark.skipif(not ROOT,reason='actual private package not supplied')
def test_actual_four_admissions_source_identity_and_no_runtime_gold():
    root=Path(ROOT);summary=json.loads((root/'SUMMARY.json').read_text())
    assert summary['tasks']==12 and summary['logical_requests']==72
    assert summary['native_delivery_checks']==summary['readable_content_checks']==72
    assert summary['unique_physical_requests']==68 and summary['direct_retrieval_exact_match']==4
    assert summary['new_generation_calls']==summary['new_model_loads']==summary['qualified_rewards']==0
    assert summary['no_truncation'] and not summary['authorized']
    tasks=[json.loads(l) for l in (root/'TASKS.runtime.jsonl').read_text().splitlines()]
    evals=[json.loads(l) for l in (root/'EVALSPEC.private.jsonl').read_text().splitlines()]
    assert file_sha256(root/'TASKS.runtime.jsonl')=='98bd8305826ac99a3b085cf54e8b21f1de1d5497710811c64324dca0bc61ca75'
    assert file_sha256(root/'EVALSPEC.private.jsonl')=='687b53e816dd908bcb47b88cb34bbb69f737ab3f18490efbd9f8b1706d14f80b'
    seen=set()
    for batch in summary['batches']:
        plan,rows,_=check(batch['plan_path'])
        assert len(rows)==batch['physical_calls']
        assert not seen&{r['request_id'] for r in rows}
        seen.update(r['request_id'] for r in rows)
        for row in rows:
            content=json.dumps(row['model_input']['messages'])
            assert row['task_id'] not in content
            assert all(e['source_family_ids'][0] not in content for e in evals)
            assert 'direct_skill_id' not in content and 'criterion' not in content
    assert len(seen)==68 and len(tasks)==len(evals)==12
