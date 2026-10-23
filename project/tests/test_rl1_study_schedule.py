"""Synthetic receipt census: common scale and late feedback reach both baselines.

These invented receipts test source joins/coverage, not optimization or research
completion. Actual optimization/export is covered in qualified_learning tests.
"""
from copy import deepcopy
from dataclasses import asdict

import pytest

from metacom_pm.rl1.bound_generation import BoundResourceEnv
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.learning_handoff import candidate_menu
from metacom_pm.rl1.learning_preparation import TerminalCandidate
from metacom_pm.rl1.measurement_identity import binding
from metacom_pm.rl1.qualified_learning import make_run_manifest
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.study_schedule import freeze_scale,validate_runset,common_union
from metacom_pm.rl1.supervised_learning import prepare_supervised
from test_rl1_learning_handoff import inputs
from test_rl1_qualified_learning import setup_artifacts


def artifacts(a):
    old=a['manifest'];cs,kw,_=inputs();executor=cs[0].executor_identity
    study=freeze_scale(a['q'],old['scale_evidence'],[executor])
    manifests=[];batches=[];done=[];cache={c.request_identity:(c,kw['receipts'][c.request_identity]) for c in cs}
    for method in ('PPO','PPO-NoText'):
        for seed in (17,29,43):
            # Use real manifest construction, including the complete owner-balanced schedule.
            data=deepcopy(a['data'])
            if method=='PPO-NoText':
                data['method']='PPO-NoText';meta=data['metadata'];meta['method']='PPO-NoText'
                data['metadata']=stamp({k:v for k,v in meta.items() if k!='identity'})
                data=stamp({k:v for k,v in data.items() if k!='identity'})
            m=make_run_manifest(data,bindings=old['train_bindings'],dev_bindings=old['dev_bindings'],seed=seed,
                qualification=a['q'],scale_evidence=old['scale_evidence'],study_scale=study)
            manifests.append(m);own=[]
            for v in range(1,m['max_updates']+1):
                rows=[]
                for index,b in enumerate(m['trajectories'][16*(v-1):16*v]):
                    spec,r=a['specs'][b['prefix_identity']]
                    for role in ('ON','OFF'):
                        # The final seed's last batch adds feedback unavailable to initial BC.
                        on=(role=='ON' and method=='PPO-NoText' and seed==43 and v==8 and index==15)
                        env=BoundResourceEnv(spec,r)
                        if on:env.step(1,expected_state_hash=env.state_hash)
                        env.step(0,expected_state_hash=env.state_hash)
                        req=env.generation_request();rid=req['request_id'];counts=(int(on),0,0,0)
                        if rid not in cache:
                            c=TerminalCandidate(spec.prefix.identity,'train',counts,r.cost(spec,counts),rid,
                                digest('MOCK '+str(counts)),b['evidence_identity'],executor,r.identity)
                            rec=dict(binding=binding(rid,c.response_identity,c.evidence_identity,a['bundle']['freeze'],a['q']),
                                measurement_status='measured_candidate',q=3,m=0)
                            cache[rid]=(c,rec)
                        c,rec=cache[rid]
                        rows.append(dict(trajectory_id=b['trajectory_id'],role=role,candidate=asdict(c),receipt=rec))
                rec=stamp(dict(run_identity=m['identity'],policy_version=v,completed_episodes=16*v,
                    after='MOCK_OPTIMIZER_HASH_'+str(v),training_feedback=rows,scope='ENGINEERING_ONLY'))
                own.append(rec);batches.append(rec)
            done.append(stamp(dict(run_identity=m['identity'],status='FIXED_TRAINING_ENDPOINT_COMPLETED',
                episodes=128,updates=8,parameters=own[-1]['after'],update_receipt_identities=[r['identity'] for r in own],
                scope='ENGINEERING_ONLY',synthetic_fixture_not_optimization=True)))
    return dict(study=study,manifests=manifests,completions=done,batch_receipts=batches,
        initial_candidates=cs,initial_receipts=kw['receipts'],initial_menus={executor:kw['menu']})


def test_all_seeds_share_scale_and_late_feedback_reaches_both_final_baselines(setup_artifacts):
    a=setup_artifacts['BC-init'];bundle=artifacts(a)
    validate_runset(bundle['study'],bundle['manifests'])
    cs,receipts,proof=common_union(**bundle)
    assert len(cs)>len(bundle['initial_candidates']) and len(proof['completed_runs'])==6
    late=bundle['batch_receipts'][-1]['training_feedback'][-2]['candidate']['request_identity']
    assert late in receipts and late not in bundle['initial_receipts']
    assert bundle['manifests'][-1]['identity'] in proof['producers'][late]
    menu=candidate_menu(cs,scope='final_train_union',source_identity=proof['identity'])
    specs={c.prefix_identity:a['specs'][c.prefix_identity] for c in cs}
    for method in ('OneShot','BC-union'):
        data=prepare_supervised(cs,menu=menu,receipts=receipts,qualification_bundle=a['bundle'],episodes=specs,
            view=a['view'],method=method,union_bundle=bundle)
        assert data['status']=='READY'
        if method=='OneShot':assert len(data['rows'])==len(cs)


@pytest.mark.parametrize('missing',['run','batch','initial','wrong_scale','held_out'])
def test_union_rejects_incomplete_or_incomparable_feedback(setup_artifacts,missing):
    bundle=artifacts(setup_artifacts['BC-init'])
    if missing=='run':bundle['completions'].pop()
    elif missing=='batch':bundle['batch_receipts'].pop()
    elif missing=='initial':bundle['initial_candidates'].pop()
    elif missing=='wrong_scale':
        m=bundle['manifests'][0];m['episodes']=384
        bundle['manifests'][0]=stamp({k:v for k,v in m.items() if k!='identity'})
    else:
        from dataclasses import replace
        bundle['initial_candidates'][0]=replace(bundle['initial_candidates'][0],split='test')
    with pytest.raises(ValueError):common_union(**bundle)
