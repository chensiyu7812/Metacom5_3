"""Actual small-network optimization/coordinator tests on synthetic sources."""
from dataclasses import replace

import pytest
import torch

from metacom_pm.rl1.natural_batch import FeedbackQueue, parameter_identity
from metacom_pm.rl1.organized_learning import OrganizedRun
from metacom_pm.rl1.organized_supervision import prepare_supervised
from metacom_pm.rl1.qualified_learning import make_run_manifest
from metacom_pm.rl1.resource_organization import OrganizationCatalog
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import fit_supervised
from test_rl1_organized_supervision import materials
from test_rl1_organized_learning_bridge import episode, raw, view, evidence_for


@pytest.fixture(scope='module')
def artifacts(tmp_path_factory):
    root = tmp_path_factory.mktemp('organized_coordinator')
    menu, fs, responses, receipts, _ = materials(programs=((0,), (2, 0)))
    base = next(iter(fs.values()))()
    catalogs = {}; train = []; dev = []
    for split, owners, per_owner in [('train', 12, 8), ('dev', 3, 6)]:
        for owner in range(owners):
            for index in range(per_owner):
                original = split == 'train' and owner == index == 0
                p = base.catalog.prefix if original else replace(base.catalog.prefix,
                    owner_id=base.catalog.prefix.owner_id if split == 'train' and owner == 0 else f'MOCK-{split}-{owner}',
                    session_id=f'MOCK-{index}', split=split)
                items = [replace(x, owner_id=p.owner_id if x.owner_id else None)
                         for x in base.catalog._items.values()]
                c = OrganizationCatalog(p, items, provenance_identity=base.catalog.provenance_identity)
                catalogs[p.identity] = c
                binding = dict(prefix_identity=p.identity, owner=p.owner_id, spec_identity=c.identity,
                    renderer_identity=base.renderer.identity, evidence_identity=digest(evidence_for(c)[0]))
                (train if split == 'train' else dev).append(binding)
    result = {}
    for method in ('BC-init', 'PPO-NoText'):
        v = view(root/method, no_text=method == 'PPO-NoText')
        data = prepare_supervised(menu, factories=fs, responses=responses, receipts=receipts, view=v, method=method)
        manifest = make_run_manifest(data, bindings=train, dev_bindings=dev, seed=17,
            qualification=base.route.qualification,
            scale_evidence=dict(hours_128=40, hours_384=120, source_identity='MOCK_NOT_REAL_THROUGHPUT'))
        directory = root/method/'bc'
        receipt = fit_supervised(data, seed=17, directory=directory)
        result[method] = dict(data=data, manifest=manifest, view=v, base=base,
            catalogs=catalogs, directory=directory, receipt=receipt)
    return result


def start(a, work):
    return OrganizedRun(a['data'], manifest=a['manifest'], qualification_bundle=a['base'].route.bundle,
        view=a['view'], initialization_path=a['directory']/'checkpoint.pt',
        initialization_receipt=a['receipt'], workdir=work)


def episodes(a, version=0, bindings=None):
    bindings = bindings if bindings is not None else a['manifest']['trajectories'][16*version:16*(version+1)]
    return [episode(a['catalogs'][b['prefix_identity']], a['base'].renderer, a['base'].route,
        tid=b['trajectory_id'], no_text=a['view'].no_text) for b in bindings]


def drain(queue):
    while (row := queue.claim_next()) is not None:
        p = row['payload']
        if row['kind'] == 'generation':
            # Transparent synthetic utility: MP is useful, other GETs add cost.
            value = raw(p, 'useful' if 'p' in p['provenance']['selected_keys'] else 'baseline')
        else:
            value = dict(binding=p['binding'], measurement_status='measured_candidate',
                         q=4 if p['reply'] == 'useful' else 2, m=0)
        queue.settle(row['id'], value)


def complete(run, queue):
    for _ in range(4):
        results = run.poll(queue)
        if all(r['phase'] == 'terminal' for r in results):
            return
        drain(queue)
    raise AssertionError('synthetic feedback did not complete')


@pytest.mark.parametrize('method', ['BC-init', 'PPO-NoText'])
def test_organized_BC_is_actual_start_then_complete_batch_and_resample(tmp_path, artifacts, method):
    a = artifacts[method]; run = start(a, tmp_path/'run'); queue = FeedbackQueue(tmp_path/'q.sqlite')
    assert parameter_identity(run.model) == a['receipt']['final_parameters']
    assert a['receipt']['final_fit']['greedy_action_accuracy'] == 1
    assert a['receipt']['final_fit']['action_nll'] < a['receipt']['initial_fit']['action_nll']
    run.collect(episodes(a)); run.poll(queue)
    with pytest.raises(ValueError, match='all 16'):
        run.update_once()
    complete(run, queue); receipt = run.update_once()
    assert receipt['after'] != receipt['before'] and receipt['natural_policy_updates'] == 0
    assert len(receipt['training_feedback']) == 32
    assert all('actions' in r and 'request' in r for r in receipt['training_feedback'])
    if method == 'PPO-NoText':
        assert all(not torch.count_nonzero(t['observation'][2:10]) for row in run.records for t in row['transitions'])
    run.next_batch(); run.collect(episodes(a, 1))
    assert run.behavior == receipt['after']


def test_organized_step_and_update_recovery_preserve_parameters(tmp_path, artifacts):
    a = artifacts['BC-init']; q = FeedbackQueue(tmp_path/'q.sqlite')
    ref = start(a, tmp_path/'reference'); ref.collect(episodes(a)); complete(ref, q)
    expected = ref.update_once()
    work = tmp_path/'interrupted'; run = start(a, work)
    def stop(event, **kw):
        if event == 'step_committed' and kw['steps'] == 5:
            raise RuntimeError('injected collection interruption')
    run.fault_hook = stop
    with pytest.raises(RuntimeError):
        run.collect(episodes(a))
    restored = start(a, work); restored.resume_collection(episodes(a)); complete(restored, q)
    assert torch.equal(restored.rng_state, ref.rng_state) is False  # ref already optimized
    def interrupt_update(event, **kw):
        if event == 'optimized_before_checkpoint':
            raise RuntimeError('injected update interruption')
    restored.fault_hook = interrupt_update
    batch = restored.batch_id
    with pytest.raises(RuntimeError):
        restored.update_once()
    recovered = start(a, work)
    receipt = recovered.recover_update(episodes(a), batch_id=batch)
    assert receipt['after'] == expected['after']
    assert torch.equal(recovered.rng_state, ref.rng_state)
    assert recovered.recover_update(episodes(a), batch_id=batch) == receipt


def test_organized_fixed_endpoint_keeps_development_and_all_feedback(tmp_path, artifacts):
    a = artifacts['BC-init']; run = start(a, tmp_path/'run'); q = FeedbackQueue(tmp_path/'q.sqlite')
    for version in range(8):
        run.collect(episodes(a, version)); complete(run, q); run.update_once()
        count = 16*(version+1)
        if count in (64, 128):
            dev = episodes(a, bindings=run.development_bindings())
            for _ in range(4):
                report = run.evaluate_development(dev, q)
                if report['status'] == 'DEVELOPMENT_COMPLETED':
                    break
                drain(q)
            assert report['status'] == 'DEVELOPMENT_COMPLETED'
        if count < 128:
            run.next_batch()
    done = run.finish()
    assert done['episodes'] == 128 and done['updates'] == 8
    assert done['scope'] == 'ENGINEERING_ONLY' and len(done['update_receipt_identities']) == 8


def test_organized_generation_uses_common_worker_and_exact_cache(tmp_path, monkeypatch):
    import hashlib
    import json
    from metacom_pm.rl1.calibration_workflow import stamp
    from metacom_pm.rl1.local_backend import LocalBackend
    from metacom_pm.rl1.generation_worker import GenerationWorker
    from metacom_pm.rl1.cached_generation_worker import make_cache_index, replay_cached_generations
    from metacom_pm.rl1.generation import LocalNaturalGenerator
    from metacom_pm.rl1.organized_feedback import OrganizedEpisode, TokenCost
    from test_rl1_local_backend import setup as backend_setup
    from test_rl1_organized_learning_bridge import setup, item, evidence_for
    old,_,_,_,events,_,_=backend_setup(tmp_path/'old')
    c,r=setup([item('p','MP')]);evidence,source=evidence_for(c)
    e=OrganizedEpisode(c,r,executor_identity=old.protocol['runtime']['identity'],draw_identity='MOCK',
        trajectory_id='MOCK',evidence=evidence,evidence_source=source,cost=TokenCost(.05,2048))
    e.step(2);e.step(0);req=e.requests['ON']
    protocol=stamp({k:v for k,v in old.protocol.items() if k!='identity'} | dict(request_ids=[req['request_id']]))
    backend=LocalBackend(protocol,tmp_path/'backend',generator_factory=old.generator_factory,
        bge_factory=old.bge_factory,gpu_guard=old.gpu_guard)
    calls=[]
    def visible(self, request):
        calls.append(request)
        assert 'provenance' not in request and 'expected_input_tokens' not in request
        return dict(request_id=request['request_id'],runtime_identity=self.identity,input_tokens=req['expected_input_tokens'],
            text='MOCK reply',finish_reason='natural_stop',api_cost_usd=0)
    monkeypatch.setattr(LocalNaturalGenerator,'generate',visible)
    q=FeedbackQueue(tmp_path/'q.sqlite');q.generate(req)
    worker=GenerationWorker(q,backend,tmp_path/'worker')
    result=worker.step();assert result['new_calls']==1 and len(calls)==1
    raw_result=q.generate(req)
    paths={}
    for key,value in [('request',req),('raw',raw_result)]:
        p=tmp_path/(key+'.json');p.write_text(json.dumps(value))
        paths[key+'_path']=str(p);paths[key+'_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    index=make_cache_index([paths],source_identity='synthetic complete new-domain request')
    replay=FeedbackQueue(tmp_path/'replay.sqlite');replay.generate(req)
    assert len(replay_cached_generations(replay,index)['reused'])==1
    assert replay.generate(req)==raw_result and len(calls)==1
    bad=dict(raw_result,input_tokens=req['expected_input_tokens']+1)
    p=tmp_path/'raw.json';p.write_text(json.dumps(bad))
    paths['raw_sha256']=hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(ValueError,match='input length'):
        make_cache_index([paths],source_identity='wrong actual encoded input')


def test_initial_organized_pool_uses_shared_queue_without_live_dispatch(tmp_path):
    from metacom_pm.rl1.research_backend import ResearchBackend
    menu,fs,_,_,_=materials(programs=((0,),(2,0)))
    base=next(iter(fs.values()))();q=FeedbackQueue(tmp_path/'q.sqlite')
    backend=ResearchBackend(q,qualification_bundle=base.route.bundle)
    for _ in range(4):
        data=backend.prepare_organized_supervision(menu=menu,factories=fs,view=view(tmp_path),method='BC-init')
        if data['status']=='READY':break
        drain(q)
    assert data['status']=='READY' and len(data['rows'])==2
    assert backend.service_once()['measurement']['status']=='NO_QUALIFIED_WORKER'
