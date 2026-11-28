"""A/B reply supervision and scoring joins. Fixtures are never model results."""
from copy import deepcopy
from dataclasses import replace
import pytest
from test_need_aware_agent import runtime
from test_need_aware_w4_revision import ident
from metacom_pm.need_aware.data.contracts import digest
from metacom_pm.need_aware.data.reply_bridge import row
from metacom_pm.need_aware.data.short_protocol import PROTOCOL
from metacom_pm.need_aware.memory.writer import MemoryWriter,write_for_task
from metacom_pm.need_aware.memory import reader as R
from metacom_pm.need_aware.agent import behavior as B,companion as C
from metacom_pm.need_aware.runtime import requests as Q,models as M,training as T
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.wp4_mcq import score,validate_cell_binding
from metacom_pm.need_aware.evaluation.agent_system import check_trace


def test_reply_bridge_uses_same_real_records_and_masks_unknown_negatives(tmp_path):
    task,resolver=runtime(tmp_path,task_mode='generation',options=[])
    store=write_for_task(resolver,MemoryWriter(),task);packed=R.pack(store.units,lambda s:len(s.split()),10000)
    supply=dict(task_sha256=digest(task.to_dict()),trace=R.trace(packed,'raw'),
        evidence_records=[dict(source_id=u.unit_id,original_text_sha256=u.original_text_sha256) for u in packed.units])
    c=dict(task_id=task.task_id,owner=task.persona_group,split='fit',sft_eligible=True,positive='chosen reply',
        negatives=['reviewed relative negative','reasonable alternative','unknown'],pair_negative_indices=[0],
        source_reply_sha256=digest('chosen reply'),source_negative_sha256=digest(['reviewed relative negative','reasonable alternative','unknown']),
        source_row=3,runtime_sha256='sha',positive_status='source reviewed')
    r=row(c,task,supply,store)
    assert r['messages']==B.build('U0',task,store,packed)[0]
    assert r['rejected']==['reviewed relative negative'] and 'chosen reply' not in str(r['messages'])
    assert 'persona profile' not in str(r['messages'])
    assert row(dict(c,pair_negative_indices=[]),task,supply,store)['rejected']==[]
    with pytest.raises(ValueError,match='fit/tune'):row(dict(c,split='development'),task,supply,store)
    with pytest.raises(ValueError,match='positive changed'):row(dict(c,positive='tampered'),task,supply,store)
    s=deepcopy(supply);s['evidence_records'][0]['original_text_sha256']='wrong'
    with pytest.raises(ValueError,match='evidence bytes'):row(c,task,s,store)


def test_adapted_model_and_condition_aliases_score_strictly(tmp_path):
    task,_=runtime(tmp_path);dec=M.QWEN35.decode(64)
    for arm,model in [('NoMem','Qwen35'),('OptOnly','Qwen35'),('U2','Qwen35+U2'),('U3','Qwen35+U3'),
                      ('U2:NoMem','Qwen35+U2'),('U3:OptOnly','Qwen35+U3')]:
        req=Q.make(task,arm,M.QWEN35,[dict(role='user',content='fixture')],[1,2],dec,{},dict(fits=True),{})
        gid=M.QWEN35.g_id if model=='Qwen35' else M.adapted_binding(M.QWEN35,ident(arm.split(':')[0]),dec)['g_id']
        req.update(model_label=model,g_id=gid,logical_id=f'{task.task_id}|{arm}|{model}',
            task_sha256=digest(task.to_dict()),scoring_protocol=PROTOCOL)
        req['request_sha256']=Q.physical_identity(gid,req['messages'],req['input_ids'],dec)
        pred=dict(task_id=task.task_id,logical_id=req['logical_id'],arm=arm,model_label=model,
            model_id=req['model_id'],request_sha256=req['request_sha256'],result_kind='plumbing',run_id='fixture',
            status='completed',output='Final Answer: B',attempt_count=1,finish_reason='eos',failure_kind=None)
        ev=EvalTask(task.task_id,'B',task.options[1]['text'],'',[],{},[],'not_used',PROTOCOL)
        rows=score([task],{task.task_id:ev},[req],[pred],model=model,arm=arm,kind='plumbing')
        assert rows[0]['correct'] is True
        cap=dict(req,status='capacity_exceeded',capacity=dict(fits=False,input_tokens=12001,input_cap=12000,backend_cap=16384))
        failed=dict(pred,status='capacity_exceeded',output='',attempt_count=0,finish_reason=None,failure_kind='capacity_exceeded')
        result=score([task],{task.task_id:ev},[cap],[failed],model=model,arm=arm,kind='plumbing')[0]
        assert result['eligible'] and result['outcome']=='capacity_exceeded' and result['correct'] is None
        broken=dict(req,request_sha256='unbound')
        with pytest.raises(ValueError,match='physical request'):validate_cell_binding(broken,model,arm)
    with pytest.raises(ValueError,match='method/model'):validate_cell_binding(req,'Qwen35','U3')


def test_fair_training_comparison_checks_realized_steps_and_cfg():
    r=dict(candidate_sha256='c',train_data_sha256='d',base_g_id='g',init_adapter_sha256='i',adapter_config_sha256='l',
        trainer=dict(steps=25,stop='epoch_done',cfg=dict(seed=7,rank_weight=.1)))
    a,b=dict(deepcopy(r),method='U2'),dict(deepcopy(r),method='U3')
    assert T.validate_reply_comparison([a,b])['matched_steps']==25
    b['trainer']['steps']=24
    with pytest.raises(T.ContractError,match='unequal'):T.validate_reply_comparison([a,b])
    b=deepcopy(dict(r,method='U3'));b['trainer']['cfg']['rank_weight']=.2
    with pytest.raises(T.ContractError,match='configuration'):T.validate_reply_comparison([a,b])


def test_companion_emits_actual_lifecycle_with_shorter_legal_prefix(tmp_path):
    h=C.History('owner',path=tmp_path/'history.jsonl')
    for i in range(4):h.add('user' if i%2==0 else 'assistant','past fixture '+str(i))
    agent=C.CompanionAgent(h,lambda m:dict(text='PLUMBING ONLY',g_id='fixture'),
        C.Memory(lambda s:len(s.split()),500),policy='always_memory',recent_turns=2)
    result=agent.step('Recall what we discussed.',task_id='task')
    check=check_trace(dict(task_id='task',owner='owner',cutoff=4,available_skill_ids=[]),
        result['trace']['events'],result['reply'])
    assert check['lifecycle_complete'] and h.turns[-1]['text']==result['reply']
    assert check['semantic_help_quality']=='requires_reply_review'
    assert 'MP' in check['missing_role_evidence']  # missing telemetry is reported, never invented


def test_lexical_person_cues_are_not_semantic_labels():
    assert 'not a beneficiary label' in B.served_line('I feel hurt by my sister; please help me cope.')
    assert 'none detected' in B.served_line('Find a gift for Alex.')
    assert 'Infer whom' in B.served_line('Find a gift for Alex.')
