import json
from dataclasses import replace
from pathlib import Path
import pytest
from metacom_pm.need_aware.data.contracts import RuntimeTask,text_hash
from metacom_pm.need_aware.data.history import HistoryResolver
from metacom_pm.need_aware.data.personamem import match_snippet,sha_file
from metacom_pm.need_aware.evaluation.contracts import EvalTask
from metacom_pm.need_aware.evaluation.mcq import extract_final_answer,make_options,official_messages,score_one
from metacom_pm.need_aware.evaluation.score import score_predictions
from metacom_pm.need_aware.evaluation.aggregate import paired_cluster
from metacom_pm.need_aware.data.prefeval import history_messages


@pytest.fixture
def case(tmp_path):
    messages=[{'role':'user','content':'I used to like tea.'},
              {'role':'user','content':'Forget that preference.'},
              {'role':'assistant','content':'Understood.'}]
    p=tmp_path/'h.json';p.write_text(json.dumps({'owner_id':'p1','source_family':'h1','messages':messages}))
    opts,gold=make_options('one',['two','three','four'],31)
    t=RuntimeTask('t','rev','val','p1','h1','h.json',sha_file(p),2,[],'What shall I drink?','mcq',opts)
    e=EvalTask('t',gold,'one','private',[],{},[],'missing')
    return t,e,HistoryResolver(tmp_path)


def test_runtime_rejects_gold_and_nested_markers(case):
    t,_,_=case
    with pytest.raises(TypeError):RuntimeTask.from_dict({**t.to_dict(),'gold_choice_id':'A'})
    with pytest.raises(ValueError):replace(t,options=[{**o,'correct':True} for o in t.options])
    with pytest.raises(ValueError):replace(t,current_messages=[{'role':'user','content':'x','preference':'gold'}])
    with pytest.raises(ValueError):replace(t,task_mode='generation')
    with pytest.raises(ValueError):replace(t,split='test')


def test_owner_cutoff_hash_and_path(case):
    t,_,resolver=case
    records=resolver.resolve(t);assert len(records)==2
    assert records[-1].original_text=='Forget that preference.'
    assert all(r.validity=='unknown' and r.reported_at is None for r in records)
    for bad in [replace(t,persona_group='wrong'),replace(t,cutoff=99),replace(t,history_sha256='bad')]:
        with pytest.raises(ValueError):resolver.resolve(bad)
    with pytest.raises(ValueError):replace(t,history_ref='../gold.json')


def test_direct_requires_complete_role_bound_visible_source(case):
    t,_,resolver=case;records=resolver.resolve(t)
    snippet=[{'role':'user','content':r.original_text} for r in records]
    status,spans=match_snippet(snippet,records);assert status=='located_unique'
    assert match_snippet([{'role':'assistant','content':records[0].original_text}],records)==('missing',[])
    assert match_snippet(snippet,records+records)==('ambiguous',[])
    manifest={'task_id':t.task_id,'status':status,'spans':spans}
    assert resolver.resolve_direct(t,manifest,'C')==resolver.resolve_direct(t,manifest,'D')
    with pytest.raises(ValueError):resolver.resolve_direct(t,manifest,'B')
    with pytest.raises(KeyError):resolver.resolve_direct(replace(t,cutoff=1),manifest,'C')


@pytest.mark.parametrize('output,expected',[('', ''),('A',''),('A.','A'),('Answer: c','C'),
                         (r'Final Answer: B then \boxed{D}','D'),('Final Answer: Z','Z')])
def test_upstream_parser_edge_cases(output,expected):
    assert extract_final_answer(output)==expected


def test_score_denominator_and_provenance(case):
    t,e,_=case
    assert score_one(f'Final Answer: {e.gold_choice_id}',t,e)['correct']
    assert not score_one('unparseable',t,e)['correct']
    records,summary=score_predictions([t],{'t':e},[],'model')
    assert summary['planned']==1 and summary['completed']==0 and records[0]['status']=='missing'
    p={'task_id':'t','output':'A.','result_kind':'plumbing'}
    with pytest.raises(ValueError):score_predictions([t],{'t':e},[p],'model')
    with pytest.raises(ValueError):score_predictions([t],{'t':e},[p,p],'plumbing')


def test_generation_has_no_options_or_eval(case):
    t,_,_=case;t=replace(t,task_mode='generation',options=[])
    messages=official_messages(t,[])
    assert len(messages)==1 and messages[0]['role']=='user'
    assert 'private' not in json.dumps(messages) and 'following options' not in json.dumps(messages)


def test_prefeval_implicit_never_reads_label():
    row={'preference':'DO NOT EXPOSE LABEL','conversation':{'query':'Help?','assistant_options':'a or b',
         'user_selection':'b','assistant_acknowledgment':'okay'}}
    msgs=history_messages(row,'choice')
    assert [m['role'] for m in msgs]==['user','assistant','user','assistant']
    assert row['preference'] not in json.dumps(msgs)


def test_cluster_pairs_keep_failed_and_require_same_tasks():
    rows=[{'task_id':str(i),'persona_group':str(i//2),'status':'completed','correct':False} for i in range(6)]
    other=[{**r,'correct':True} for r in rows];other[-1]['status']='missing'
    r=paired_cluster(rows,other,replicates=100)
    assert r['planned_pairs']==6 and r['complete_pairs']==5 and r['missing_or_failed_pairs']==1
    assert r['repairs']==5 and r['ci95']==[1.0,1.0]
    with pytest.raises(ValueError):paired_cluster(rows,other[:-1])
