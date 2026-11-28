"""New reply data/evaluation contracts. Unit fixtures are NOT model capability results."""
import json
from types import SimpleNamespace
import pytest
from metacom_pm.need_aware.agent import reply_protocol as RP
from metacom_pm.need_aware.data.response_data import advice_screen,selection
from metacom_pm.need_aware.data.contracts import RuntimeTask,digest,text_hash
from metacom_pm.need_aware.data import reply_objective as O
from metacom_pm.need_aware.evaluation.wp4_mcq import paired,clusters
from metacom_pm.need_aware.evaluation.agent_system import check_trace,check_reply
from metacom_pm.need_aware.evaluation.export import execution_metrics


def task(tid='x',owner='o',family='f'):
    return RuntimeTask(tid,'revision','train',owner,family,'histories/x.json','sha',2,[],
        'Help me arrange a birthday gift for my sister.', 'mcq',
        [{'id':k,'text':'answer '+k} for k in 'ABCD'])


def test_complete_owner_selection():
    ts=[task(str(i),str(i//3),str(i//3)) for i in range(12)]
    rows={t.task_id:{'who':'others'} for t in ts}
    result=selection(ts,rows,{'development':['0','1','2','3']},limit=7)
    assert len(result[1])==2 and len(result[2])==6
    assert result==selection(list(reversed(ts)),rows,{'development':['0','1','2','3']},limit=7)
    for owner in result[1]:assert {t.task_id for t in ts if t.persona_group==owner}<=set(result[2])


def test_competitive_rules_and_ablations():
    t=task();evidence='[H1] Sister likes maps. [H2] User likes tea.'
    for arm in ('U0','U1','U1+'):
        m=RP.messages(t,evidence,arm,mcq=True)
        assert m[-1]['content'].startswith(evidence)
        assert all(o['text'] in m[-1]['content'] for o in t.options)
    assert 'never discard' in RP.U1 and 'if the request is for that friend' in RP.U1_PLUS
    no=str(RP.messages(t,evidence,'No-memory',mcq=True));opts=str(RP.messages(t,evidence,'Options-only',mcq=True))
    assert evidence not in no and t.user_query in no
    assert t.user_query not in opts and evidence not in opts
    assert 'birthday' not in opts


def test_screen_holds_hidden_facts_but_permits_nonassertive_advice():
    q='What are some ways to relax at home?'
    assert advice_screen(q,'You could relax with a quiet craft project at home.')[0]
    assert not advice_screen(q,'Since you have diabetes, relax with a snack.')[0]
    assert not advice_screen(q,'You could continue your father’s diabetes treatment.')[0]
    assert not advice_screen(q,'You could visit Paris next weekend.')[0]
    assert not advice_screen('How can I relax without music?','You could relax with music.')[0]


def test_reply_loss_masks_and_gradients():
    import torch
    p=torch.tensor([-2.,-3.],requires_grad=True);n=torch.tensor([-1.,-1.],requires_grad=True)
    mask=torch.tensor([1.,0.])
    u2=O.loss(p,n,mask,method='U2');assert u2.item()==2.5
    u2.backward(retain_graph=True);assert n.grad is None
    p.grad.zero_();u3=O.loss(p,n,mask,method='U3');u3.backward()
    assert n.grad[0]>0 and n.grad[1]==0 and u3>u2
    assert O.loss(p,n,torch.zeros(2),method='U3').item()==2.5


def test_actual_causal_step_on_cpu_fixture():
    import torch
    class Tiny(torch.nn.Module):
        def __init__(self):super().__init__();self.emb=torch.nn.Embedding(8,4);self.lm=torch.nn.Linear(4,8)
        def forward(self,input_ids,**kw):return SimpleNamespace(logits=self.lm(self.emb(input_ids)))
    m=Tiny();seq=lambda x:dict(input_ids=x,reply_mask=[0,0,1,1])
    e=dict(positive=seq([1,2,3,4]),rejected=seq([1,2,5,4]),pair_mask=True,class_weight=1.)
    value,receipt=O.step_loss(m,e,method='U3');value.backward()
    assert receipt=={'positive_forwards':1,'negative_forwards':1,'processed_tokens':8}
    assert m.lm.weight.grad.abs().sum()>0


def row(tid,c,correct,status='completed'):
    return dict(task_id=tid,cluster=c,correct=correct,status=status,eligible=True)


def test_pairing_and_owner_clusters_not_iid_questions():
    a=[row('a','o1',False),row('b','o1',False),row('c','o2',True),row('d','o2',None,'missing')]
    b=[row('a','o1',True),row('b','o1',True),row('c','o2',False),row('d','o2',True)]
    p=paired(a,b,replicates=1000)
    assert (p['complete_pairs'],p['complete_clusters'],p['repairs'],p['regressions'])==(3,2,2,1)
    assert p['micro_difference']==pytest.approx(1/3) and p['owner_macro_difference']==0
    assert p['fixed_denominator_difference_sensitivity']==.5
    assert p['unknown_difference_bounds']==[.25,.5]
    with pytest.raises(ValueError):paired(a,b[:-1])
    c=clusters([task('a','x','f'),task('b','y','f'),task('c','y','g')]);assert len(set(c.values()))==1


def test_lifecycle_checks_do_not_score_helpfulness():
    t=dict(task_id='x',owner='me',cutoff=3,available_skill_ids=['s'])
    reply='Here is a useful reply.';h=text_hash(reply)
    events=[dict(task_id='x',event=e,reply_sha256=h) for e in ('need_understood','reply_emitted','history_appended','followup_ready')]
    result=check_trace(t,events,reply);assert result['lifecycle_complete']
    assert result['semantic_help_quality']=='requires_reply_review'
    events.append(dict(task_id='x',event='history_read',owner='other',cutoff=3,source_ids=['a'],source_hashes=['b']))
    assert 'foreign_owner' in check_trace(t,events,reply)['provenance_violations']
    spec=dict(task_id='x',personal_fact_references=[dict(id='f1',acceptable=['roughly 3'])])
    assert check_reply('three',spec)['facts'][0]['semantic_completion'].startswith('needs_review')


def test_export_accepts_new_arms_without_old_metric_cells():
    result=execution_metrics([],arms=['B1','E0s'])
    assert set(result['per_cell'])=={'Qwen35|B1','Qwen35|E0s','G0e|B1','G0e|E0s'}
