"""Synthetic CPU integration; no pretrained model, provider or research labels."""
from copy import deepcopy

import pytest
import torch

from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.measurement_identity import binding
from metacom_pm.rl1.organized_oneshot import ProgramReturnModel, program_tensor
from metacom_pm.rl1.organized_supervision import (endpoint, training_menu, prepare_targets,
    prepare_supervised, comparison_union)
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import fit_supervised, load_initialization
from test_rl1_organized_learning_bridge import episode, item, setup, route_for, raw, view


def materials(programs=((0,),(2,0),(3,3,3,3,3,3,0)), *, qualified=True, identical=False):
    c,r=setup([item('p','MP')]+[item(str(i),text='source text '*80) for i in range(6)])
    route=route_for(c,r) if qualified else None
    factory=lambda:episode(c,r,route)
    endpoints=[];responses={};receipts={};exports=[]
    for actions in programs:
        x,e=endpoint(factory,actions);endpoints.append(x)
        for role,req in e.requests.items():
            text='same' if identical else ('OFF' if role=='OFF' or actions==(0,) else 'answer '+str(actions))
            responses[req['request_id']]=raw(req,text)
            if route:
                query=binding(req['request_id'],digest(text),digest(e.evidence),route.bundle['freeze'],route.qualification)
                q=2 if identical or text=='OFF' else 4
                receipts[req['request_id']]=dict(binding=query,measurement_status='measured_candidate',q=q,m=0)
        if route:
            e.advance(lambda req:responses[req['request_id']],lambda q,*_:receipts[q['generation_request_id']])
            exports.extend(e.feedback_export())
    menu=training_menu(endpoints,source_identity='synthetic schedule before scores')
    return menu,{c.prefix.identity:factory},responses,receipts,exports


def test_full_programs_select_measured_bc_and_keep_missing_unknown():
    menu,fs,rs,js,_=materials()
    ready=prepare_targets(menu,factories=fs,responses=rs,receipts=js)
    assert ready['status']=='READY' and ready['targets'][0]['actions']==[2,0]
    assert any(len(x['actions'])==7 for x in ready['measured'])
    assert ready['unmeasured_programs_are_negative'] is False
    missing=deepcopy(js);key=menu['endpoints'][-1]['requests']['ON']['request_id'];missing.pop(key)
    pending=prepare_targets(menu,factories=fs,responses=rs,receipts=missing)
    assert pending['targets']==pending['measured']==[] and pending['complete_endpoints']==2
    missing[key]=dict(js[key],measurement_status='semantic_uncertainty',q=None,m=None)
    assert prepare_targets(menu,factories=fs,responses=rs,receipts=missing)['targets']==[]


def test_unqualified_and_wrong_binding_cannot_become_labels():
    menu,fs,rs,js,_=materials(qualified=False)
    assert all(x['reason']=='missing_qualification' for x in prepare_targets(menu,factories=fs,responses=rs,receipts=js)['pending'])
    menu,fs,rs,js,_=materials();bad=deepcopy(js);next(iter(bad.values()))['binding']['measurement_purpose']='independent_repeat'
    with pytest.raises(ValueError,match='binding'):prepare_targets(menu,factories=fs,responses=rs,receipts=bad)
    bad=deepcopy(menu);bad['endpoints'][1]['resource_tokens']+=1
    with pytest.raises(ValueError):prepare_targets(bad,factories=fs,responses=rs,receipts=js)


def test_content_consistency_and_shared_input_noise_not_false_resource_gain():
    menu,fs,rs,js,_=materials(identical=True)
    ready=prepare_targets(menu,factories=fs,responses=rs,receipts=js)
    assert ready['targets'][0]['actions']==[0]
    assert ready['sensitivity'][0]['shared_input_q_step_switches']==[]
    bad=deepcopy(js);bad[menu['endpoints'][1]['requests']['ON']['request_id']]['q']=3
    with pytest.raises(ValueError,match='conflicting labels'):prepare_targets(menu,factories=fs,responses=rs,receipts=bad)


def test_sensitivity_reports_possible_argmax_switch_without_relabeling():
    menu,fs,rs,js,_=materials()
    # Same utility, different resource cost; one q-step can reverse the winner.
    ready=prepare_targets(menu,factories=fs,responses=rs,receipts=js)
    assert ready['sensitivity'][0]['shared_input_q_step_switches']
    assert ready['targets'][0]['labels']['ON']['q']==4


def test_order_is_not_merged_into_counts():
    c,r=setup([item('a','RS','kindness'),item('z','RS','cycling'),item('p','MP','cycling')])
    factory=lambda:episode(c,r,route_for(c,r))
    xs=[endpoint(factory,p)[0] for p in ((0,),(1,2,0),(2,1,0))]
    menu=training_menu(xs,source_identity='before')
    assert len(menu['endpoints'])==3
    assert xs[1]['requests']['ON']['request_id']!=xs[2]['requests']['ON']['request_id']
    with pytest.raises(ValueError,match='duplicate'):training_menu(xs+[xs[1]],source_identity='before')


def test_bc_value_targets_and_notext_use_existing_optimizer_and_reload(tmp_path):
    menu,fs,rs,js,_=materials(programs=((0,),(3,3,3,3,3,3,0)))
    v=view(tmp_path)
    prepared=prepare_supervised(menu,factories=fs,responses=rs,receipts=js,view=v,method='BC-init')
    assert len(prepared['rows'])==7 and prepared['rows'][-1]['return_target']==.5
    assert prepared['rows'][0]['return_target']<prepared['rows'][-1]['return_target']
    nv=view(tmp_path,no_text=True)
    hidden=prepare_supervised(menu,factories=fs,responses=rs,receipts=js,view=nv,method='PPO-NoText')
    assert all(row['features'][2:10]==(0.,)*8 for row in hidden['rows'])
    assert prepared['rows'][2]['features'][6:8]!=(0.,0.)
    receipt=fit_supervised(prepared,seed=17,directory=tmp_path/'bc')
    model,state=load_initialization(prepared,seed=17,path=tmp_path/'bc/checkpoint.pt',receipt=receipt)
    assert receipt['optimizer_steps']==50 and receipt['value_steps']==500
    assert receipt['actor_unchanged_during_value_initialization'] and not state['ppo_optimizer']['state']
    # Genuine research data still require the existing explicit bound approval.
    natural=stamp({k:v for k,v in prepared.items() if k!='identity'} | dict(scope='QUALIFIED_NATURAL_STUDY'))
    with pytest.raises(ValueError,match='authorization'):fit_supervised(natural,seed=17,directory=tmp_path/'forbidden')


def complete_comparison(menu,fs,exports):
    e=next(iter(fs.values()))();qid=e.route.qualification['identity']
    scale=stamp(dict(version='synthetic organized comparison',executors=[e.executor_identity],
        qualification_identity=qid,seeds=[17,29,43],learning_methods=['PPO','PPO-NoText'],
        episodes=128,scale_evidence={'source_identity':'synthetic throughput'},dev_checks=[64,128]))
    manifests=[];completions=[];batches=[]
    for method in scale['learning_methods']:
        for seed in scale['seeds']:
            trajectories=[dict(trajectory_id=f'{method}-{seed}-{i}',prefix_identity=e.catalog.prefix.identity,
                evidence_identity=digest(e.evidence),renderer_identity=e.renderer.identity) for i in range(128)]
            m=stamp(dict(study_scale=scale,episodes=128,qualification_identity=qid,scale_evidence=scale['scale_evidence'],
                executors=[e.executor_identity],method=method,seed=seed,max_updates=8,batch_size=16,
                trajectories=trajectories,initial_menu_identity=menu['identity']))
            manifests.append(m);local=[]
            for version in range(1,9):
                rows=[]
                for tr in trajectories[(version-1)*16:version*16]:
                    rows.extend(dict(r,trajectory_id=tr['trajectory_id']) for r in exports[-2:])
                b=stamp(dict(run_identity=m['identity'],policy_version=version,completed_episodes=version*16,
                    training_feedback=rows,after=f'synthetic-parameters-{version}'))
                batches.append(b);local.append(b)
            completions.append(stamp(dict(run_identity=m['identity'],status='FIXED_TRAINING_ENDPOINT_COMPLETED',
                episodes=128,updates=8,update_receipt_identities=[b['identity'] for b in local],parameters=local[-1]['after'])))
    return dict(study=scale,manifests=manifests,completions=completions,batches=batches,
        initial_menu=menu,initial_feedback=exports,factories=fs)


def test_common_union_requires_all_seeds_methods_and_routes_to_both_baselines(tmp_path):
    menu,fs,rs,js,exports=materials(programs=((0,),(2,0)))
    kw=complete_comparison(menu,fs,exports)
    final,rs,js,proof=comparison_union(**kw)
    assert len(proof['completed_runs'])==6 and len(proof['batches'])==48
    for method in ('BC-union','OneShot'):
        p=prepare_supervised(final,factories=fs,responses=rs,receipts=js,view=view(tmp_path),method=method,union_proof=proof)
        assert p['status']=='READY' and p['metadata']['menu_identity']==final['identity']
        if method=='OneShot':
            assert len(p['rows'])==len(final['endpoints']) and p['rows'][0]['program']==[0]
            rec=fit_supervised(p,seed=29,directory=tmp_path/'one')
            model,_=load_initialization(p,seed=29,path=tmp_path/'one/checkpoint.pt',receipt=rec)
            assert isinstance(model,ProgramReturnModel) and rec['value_steps']==0
    bad=dict(kw,completions=kw['completions'][:-1])
    with pytest.raises(ValueError,match='every method/seed'):comparison_union(**bad)
    with pytest.raises(ValueError,match='provenance'):
        prepare_targets(final,factories=fs,responses=rs,receipts=js)
    bad=deepcopy(js);bad.pop(next(iter(bad)))
    with pytest.raises(ValueError,match='common feedback'):
        prepare_targets(final,factories=fs,responses=rs,receipts=bad,union_proof=proof)
    bad=dict(kw,initial_feedback=[r for r in exports if r['role']=='OFF'])
    with pytest.raises(ValueError,match='initial pool must be complete'):
        comparison_union(**bad)


def test_oneshot_sees_initial_only_preserves_order_and_whole_program(tmp_path):
    torch.manual_seed(17)
    model=ProgramReturnModel(29)
    programs=[[0],[1,2,0],[2,1,0],[3]*9+[0]]
    tensor=program_tensor(programs);x=torch.zeros(4,29)
    result=model(x,tensor)
    assert result[1]!=result[2] and tensor.shape==(4,10)
    assert torch.allclose(model(x[:1],tensor[:1,:1]),result[:1],atol=1e-7)
    bad=tensor.clone();bad[1,0]=-1
    with pytest.raises(ValueError,match='padding'):model(x,bad)
    c,r=setup([item('p','MP')]);e=episode(c,r)
    v=view(tmp_path);assert v.feature_dimension==29
    chosen=model.choose(e.session.observe(),[[0],[2,0]],view=v,interface_identity=e.session.interface_identity)
    assert chosen.actions in ((0,),(2,0))
    e.step(2)
    with pytest.raises(ValueError,match='before any GET'):
        model.choose(e.session.observe(),[[0]],view=v,interface_identity=e.session.interface_identity)


def test_initial_only_search_can_go_beyond_four_and_reports_computation_limit(tmp_path):
    c,r=setup([item(str(i)) for i in range(9)])
    e=episode(c,r);v=view(tmp_path)
    class LengthProbe(ProgramReturnModel):
        def forward(self,features,programs):
            return (programs==3).sum(1).float()
    model=LengthProbe(v.feature_dimension)
    chosen,report=model.search(e.session.observe(),view=v,interface_identity=e.session.interface_identity,max_expansions=12)
    assert chosen.actions==(3,)*9+(0,) and report['frontier_exhausted']
    assert report['deepest_GETs']==9 and report['future_observations_read']==0
    short,report=model.search(e.session.observe(),view=v,interface_identity=e.session.interface_identity,max_expansions=2)
    assert short.actions==(3,3,0) and not report['frontier_exhausted']
    assert report['environment_GET_cap'] is None and not e.steps
