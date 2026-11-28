"""Contract regressions only; synthetic outputs never model capability results."""
from copy import deepcopy
from dataclasses import replace
import json
import pytest
from metacom_pm.need_aware.data.contracts import RuntimeTask,digest,text_hash
from metacom_pm.need_aware.data.v11 import new_history
from metacom_pm.need_aware.data.training_v11 import group_rows,runtime_projection,validate_rows
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.short_mcq import extract_short_answer,score_short,PROTOCOL
from metacom_pm.need_aware.evaluation.wp3 import score_requests,paired_on_joint_eligible,paired_frozen_subset,holm_family
from metacom_pm.need_aware.evaluation.wp2 import counts
from metacom_pm.need_aware.evaluation.open_reply import action_score,adjudicate_two,paired_open,score_open_predictions,DIMENSIONS,RUBRIC


@pytest.mark.parametrize('text,expected',[('Final Answer: A','A'),('\nFinal Answer: D\n','D'),
    ('Final Answer: [A]',''),('A',''),('Answer: A',''),('Final Answer: a',''),
    ('Final Answer: A\nReason: x',''),('Final Answer: A\nFinal Answer: B',''),('Final Answer: Z','')])
def test_short_protocol_never_relaxes_official_or_explanatory_text(text,expected):
    assert extract_short_answer(text)==expected


def cell():
    t=RuntimeTask('t','rev','val','p','f','h.json','a'*64,1,[],'query','mcq',[dict(id=x,text=x.lower()) for x in 'ABCD'])
    e=EvalTask('t','A','a','private',[],{'evidence_sufficiency':'unknown'},[],'located_unique')
    r=dict(logical_id='t|C|G0e',task_id='t',arm='C',model_label='G0e',persona_group='p',model_id='fixed',
        scoring_protocol=PROTOCOL,task_sha256=digest(t.to_dict()),status='ready',decode={'max_new_tokens':64},request_sha256='request')
    p=dict(logical_id=r['logical_id'],task_id='t',arm='C',model_label='G0e',model_id='fixed',result_kind='plumbing',
        run_id='synthetic-contract-test',request_sha256='request',status='completed',output='Final Answer: A',
        attempt_count=1,finish_reason='eos',failure_kind=None)
    return t,e,r,p


def test_short_scores_and_official_gold_binding():
    t,e,r,p=cell()
    result=score_requests([t],{'t':e},[r],[p],model='G0e',arm='C',kind='plumbing')
    assert result[0]['correct'] and result[0]['official_parser_choice_diagnostic']=='A'
    with pytest.raises(ValueError):score_short('Final Answer: A',t,replace(e,reference_answer='different'))
    r['task_sha256']='tampered'
    with pytest.raises(ValueError):score_requests([t],{'t':e},[r],[p],model='G0e',arm='C',kind='plumbing')


def test_direct_over_cap_structural_requires_actual_token_receipt():
    t,e,r,p=cell();r.update(status='not_evaluable',request_sha256=None,structural_reason='direct_over_cap')
    p.update(status='not_evaluable',request_sha256=None,output='',attempt_count=0,finish_reason=None)
    with pytest.raises(ValueError):score_requests([t],{'t':e},[r],[p],model='G0e',arm='C',kind='plumbing')
    r.update(full_direct_tokens=12001,input_cap=12000)
    rows=score_requests([t],{'t':e},[r],[p],model='G0e',arm='C',kind='plumbing')
    assert counts(rows)['structural_not_evaluable']==1 and counts(rows)['accuracy_on_completed'] is None


def test_non_direct_capacity_is_technical_in_planned_denominator():
    t,e,r,p=cell()
    for x in (r,p):x.update(arm='B0',logical_id='t|B0|G0e')
    r.update(status='capacity_exceeded',capacity=dict(fits=False,input_tokens=12001,input_cap=12000,backend_cap=16384))
    p.update(status='capacity_exceeded',output='',attempt_count=0,finish_reason=None,failure_kind='capacity_exceeded')
    rows=score_requests([t],{'t':e},[r],[p],model='G0e',arm='B0',kind='plumbing')
    assert counts(rows)['predefined_evaluable']==1 and counts(rows)['technical_uncompleted']==1
    assert counts(rows)['structural_not_evaluable']==0 and r['status']=='capacity_exceeded'


def test_joint_eligible_and_frozen_subset_not_marginals():
    t,e,r,p=cell();rows=score_requests([t],{'t':e},[r],[p],model='G0e',arm='C',kind='plumbing')
    other=deepcopy(rows);other[0].update(eligible=False,status='not_evaluable',correct=None)
    policy=dict(paired_inference=dict(bootstrap_seed=1,bootstrap_replicates=100))
    result=paired_on_joint_eligible(rows,other,policy)
    assert result['joint_predefined_evaluable']==0 and result['right_structural']==1
    assert result['paired_difference'] is None
    with pytest.raises(ValueError):paired_frozen_subset(rows,other,['not_selected'],policy)
    assert paired_frozen_subset(rows,rows,['t'],policy)['complete_pairs']==1


def test_missing_assistant_payload_preserves_coordinate_and_rejects_other_damage(tmp_path):
    path=tmp_path/'source.json';raw=dict(metadata=dict(persona_id='p',total_messages=3),chat_history=[
        {'role':'user','content':'first'},{'role':'assistant'},{'role':'user','content':'last'}])
    original=json.dumps(raw);path.write_text(original)
    messages,gaps=new_history(path,'p')
    assert gaps==[1] and messages[1]['content']=='' and messages[2]['content']=='last'
    assert path.read_text()==original
    raw['chat_history'][1]={'role':'user'};path.write_text(json.dumps(raw))
    with pytest.raises(ValueError):new_history(path,'p')


def training_group():
    u=dict(unit_id='unit',split='fit',dataset='fixture',owner_id='p',family='f',refs=[dict(source_id='f:m1')],
           response_support='fixture',revision='rev',license='fixture',source_evidence_hash=text_hash('I like quiet places.'))
    return list(group_rows(u,'self',[dict(role='user',content='I like quiet places.')],'Suggest a place.','Try a quiet park.',beneficiary='me',holder='current_user'))


def test_training_does_not_transfer_holder_or_negative_acceptable_behavior():
    rows=training_group();a=dict(old_excluded_owners=['dev','p'],training_owners={'fit':['p']},wp3_owners=['confirm'])
    assert validate_rows(rows,a)
    assert len({r['evidence_sha256'] for r in rows})==1
    assert set(runtime_projection(rows[0]))=={'task_id','source_family','messages'}
    rows[1]['acceptable_actions'].append(rows[1]['rejected_action'])
    with pytest.raises(ValueError):validate_rows(rows,a)


def test_training_split_owner_family_leak_fails():
    rows=training_group();other=deepcopy(rows)
    for r in other:r.update(group_id='other',variant_id=r['variant_id']+'other',split='tune')
    with pytest.raises(ValueError):validate_rows(rows+other,dict(old_excluded_owners=['p'],training_owners={'fit':['p']},wp3_owners=[]))


def test_identical_redacted_inputs_do_not_become_independent_families():
    rows=training_group();other=deepcopy(rows)
    for r in other:r.update(group_id='other',variant_id=r['variant_id']+'other',owner_id='p2',source_family='f2',split='tune')
    with pytest.raises(ValueError,match='duplicate runtime input'):
        validate_rows(rows+other,dict(old_excluded_owners=['p','p2'],training_owners={'fit':['p'],'tune':['p2']},wp3_owners=[]))


def test_open_action_correct_is_not_semantic_success_and_rater_disagreement_unknown():
    row=training_group()[0];s=action_score(row,row['target_text'])
    assert s['action_correct'] and s['semantic_success'] is None
    a=dict(rater_id='one',rubric=RUBRIC,**{d:1 for d in DIMENSIONS});b={**a,'rater_id':'two','task_complete':0}
    result=adjudicate_two([a,b]);assert result['semantic_success'] is None and 'task_complete' in result['disagreements']
    with pytest.raises(ValueError):adjudicate_two([a,a])


def test_pair_objective_mask_and_gradient_are_plumbing_only():
    import torch
    from metacom_pm.need_aware.data.training_objective import objective,masked_action_logp
    s=torch.tensor([1.,2.],requires_grad=True);c=torch.tensor([0.,0.],requires_grad=True);r=torch.tensor([0.,0.],requires_grad=True)
    u2=objective(s,c,r,torch.tensor([True,False]),method='U2');assert u2.item()==1.5
    u2.backward(retain_graph=True)
    assert bool((c.grad==0).all()) and bool((r.grad==0).all())
    u3=objective(s,c,r,torch.tensor([True,False]),method='U3');u3.backward()
    assert c.grad[0]<0 and r.grad[0]>0 and c.grad[1]==r.grad[1]==0
    assert objective(s,c,r,torch.tensor([False,False]),method='U3').item()==1.5
    logits=torch.zeros(1,3,4,requires_grad=True);ids=torch.tensor([[0,1,2]]);mask=torch.tensor([[0,0,1]])
    lp=masked_action_logp(logits,ids,mask);assert lp.shape==(1,)
    with pytest.raises(ValueError):masked_action_logp(logits,ids,torch.zeros_like(mask))


def test_open_complete_export_does_not_invent_semantic_scores():
    rows=training_group();req=[];pred=[]
    for row in rows:
        tid=row['variant_id'];lid=tid+'|U0|Qwen35'
        req.append(dict(task_id=tid,logical_id=lid,model_id='fixed',request_sha256='req-'+tid,status='ready',runtime_sha256=digest(runtime_projection(row))))
        pred.append(dict(task_id=tid,logical_id=lid,model_id='fixed',request_sha256='req-'+tid,status='completed',
            run_id='fixture',result_kind='plumbing',output=row['target_text'],attempt_count=1,finish_reason='eos',failure_kind=None))
    scored,receipt=score_open_predictions(rows,req,pred,[],method='U0',model='Qwen35',kind='plumbing')
    assert receipt['completed']==3 and receipt['semantic_rated']==0 and receipt['matched_group_success'] is None
    assert receipt['semantic_unknown_bounds']==[0,1]
    assert paired_open(scored,scored,replicates=100)['complete_pairs']==0
    pred[0].update(status='missing',output='',attempt_count=0,finish_reason=None,failure_kind='unattempted')
    _,receipt=score_open_predictions(rows,req,pred,[],method='U0',model='Qwen35',kind='plumbing')
    assert receipt['technical_uncompleted']==1 and receipt['completed']==2
    with pytest.raises(ValueError):score_open_predictions(rows,req,pred[:-1],[],method='U0',model='Qwen35',kind='plumbing')
