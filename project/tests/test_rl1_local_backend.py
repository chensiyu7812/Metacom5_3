"""Public local-service integration, synthetic loaders only; no GPU/network."""
from dataclasses import dataclass,replace
from pathlib import Path

import pytest
import torch

from metacom_pm.rl1.bound_generation import BoundResourceEnv
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.generation_worker import GenerationWorker
from metacom_pm.rl1.local_backend import LocalBackend,local_protocol,ENGINEERING,LOCAL
from metacom_pm.rl1.natural_batch import FeedbackQueue
from metacom_pm.rl1.research_backend import ResearchBackend
from metacom_pm.rl1.schema import digest
from test_rl1_environment import fixture_spec,renderer


@dataclass
class Binding:embedding_dimension:int=4
@dataclass
class Runtime:version:str='MOCK'


def setup(tmp_path,*,finish='natural_stop',wrong=False):
    events=[];runtime=stamp(dict(version='MOCK_G',cuda_visible_devices='0',cuda_device_order='PCI_BUS_ID'))
    spec=replace(fixture_spec(budget=2048),executor_identity=runtime['identity'])
    spec=replace(spec,inventory=tuple(tuple(replace(x,
        coarse_age='not_applicable' if x.head=='RS' else 'previous_session') for x in h) for h in spec.inventory))
    r=renderer();env=BoundResourceEnv(spec,r);env.step(0,expected_state_hash=env.state_hash);req=env.generation_request()
    p=local_protocol(scope=ENGINEERING,runtime=runtime,bge_binding=dict(embedding_dimension=4),
        bge_runtime=dict(version='MOCK'),assets={},packages={},gpu_uuid='MOCK_GPU',
        request_ids=[req['request_id']],max_embedding_batches=5)
    class G:
        manifest={k:v for k,v in runtime.items() if k!='identity'};identity=runtime['identity']
        def generate(self,request):
            events.append(('generate',request));torch.manual_seed(99)
            if finish=='interrupt':raise KeyboardInterrupt()
            return dict(request_id=request['request_id'],runtime_identity=self.identity,
                source_provenance_identity='WRONG' if wrong else digest(request['provenance']),
                text='MOCK reply',finish_reason=finish)
    class BGE:
        binding=Binding();runtime_identity=Runtime()
        def encode(self,texts):
            events.append(('encode',list(texts)));torch.manual_seed(98)
            return tuple((.1,.2,.3,.4) for t in texts)
    class Guard:
        def check(self,**kwargs):events.append(('check',kwargs));return dict(eligible=True)
    def g(_):events.append(('load_G',None));torch.manual_seed(97);return G()
    def b():events.append(('load_BGE',None));torch.manual_seed(96);return BGE()
    backend=LocalBackend(p,tmp_path/'backend',generator_factory=g,bge_factory=b,gpu_guard=Guard())
    queue=FeedbackQueue(tmp_path/'queue.sqlite');worker=GenerationWorker(queue,backend,tmp_path/'worker')
    return backend,queue,worker,req,events,spec,r


def test_lazy_load_order_public_observation_and_rng_preserved(tmp_path):
    b,q,w,req,events,spec,r=setup(tmp_path)
    assert not events and not b.root.exists()
    encoder=b.feature_encoder();env=BoundResourceEnv(spec,r)
    rng=torch.get_rng_state().clone();first=encoder.encode(env.observe())
    assert torch.equal(rng,torch.get_rng_state())
    assert [x[0] for x in events if x[0].startswith('load')]==['load_G','load_BGE']
    supplied=[t for event,ts in events if event=='encode' for t in ts]
    assert all(x.content not in '\n'.join(supplied) for head in spec.inventory for x in head)
    env.step(1,expected_state_hash=env.state_hash);encoder.encode(env.observe())
    supplied=[t for event,ts in events if event=='encode' for t in ts]
    assert spec.inventory[0][0].content in '\n'.join(supplied)
    assert all(x.content not in '\n'.join(supplied) for head in spec.inventory[1:] for x in head)
    q.generate(req);result=w.step()
    assert result['new_calls']==1 and q.generate(req)['text']=='MOCK reply'
    assert torch.equal(rng,torch.get_rng_state()) and w.step()['status']=='IDLE'
    with pytest.raises(ValueError,match='already entered'):b.generate(req)


def test_unauthorized_and_wrong_loader_cannot_touch_hardware(tmp_path):
    b,q,w,req,events,_,_=setup(tmp_path)
    p=stamp({k:v for k,v in (b.protocol|dict(scope=LOCAL)).items() if k!='identity'})
    real=LocalBackend(p,tmp_path/'unauthorized')
    with pytest.raises(ValueError,match='not authorized'):real.generate(req)
    assert not real.root.exists()
    with pytest.raises(ValueError,match='frozen loaders'):
        LocalBackend(p,tmp_path/'wrong',generator_factory=lambda _:None)


def test_sealed_result_finishes_queue_after_interruption_without_model_entry(tmp_path,monkeypatch):
    b,q,w,req,events,_,_=setup(tmp_path);q.generate(req)
    with monkeypatch.context() as m:
        m.setattr(q,'settle',lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
        with pytest.raises(KeyboardInterrupt):w.step()
    count=len(events)
    result=GenerationWorker(FeedbackQueue(q.path),b,w.root).step()
    assert result['recovered_publication'] and result['new_calls']==0 and len(events)==count


@pytest.mark.parametrize('problem',['interrupt','identity'])
def test_unknown_or_wrong_source_never_reenters_model(tmp_path,problem):
    b,q,w,req,events,_,_=setup(tmp_path,finish='interrupt' if problem=='interrupt' else 'natural_stop',wrong=problem=='identity')
    q.generate(req)
    with pytest.raises(KeyboardInterrupt if problem=='interrupt' else ValueError):w.step()
    assert w.step()['status']=='RECONCILIATION_REQUIRED'
    assert len([x for x in events if x[0]=='generate'])==1 and q.generate(req) is None


def test_known_preflight_failure_keeps_generation_waiting(tmp_path):
    b,q,w,req,events,_,_=setup(tmp_path);q.generate(req)
    b.gpu_guard.check=lambda **_: (_ for _ in ()).throw(RuntimeError('MOCK occupied GPU'))
    with pytest.raises(RuntimeError,match='occupied'):w.step()
    assert q.counts()==[dict(kind='generation',state='WAITING',count=1)]
    assert not list(w.root.glob('*.started.json')) and not list(b.root.glob('load_*.started.json'))


def test_failed_generation_is_not_repaired_or_scored(tmp_path):
    b,q,w,req,events,_,_=setup(tmp_path,finish='context_exhausted');q.generate(req)
    service=ResearchBackend(q,qualification_bundle=None,generation_worker=w)
    out=service.service_once()
    assert out['generation_attempt']['finish_reason']=='context_exhausted'
    assert out['measurement']['status']=='NO_QUALIFIED_WORKER'
    assert 'q' not in q.generate(req) and len([x for x in events if x[0]=='generate'])==1


def test_load_and_embedding_limits_remain_across_restart(tmp_path):
    b,q,w,req,events,_,_=setup(tmp_path);b.encode(['MOCK'])
    again=LocalBackend(b.protocol,b.root,generator_factory=b.generator_factory,bge_factory=b.bge_factory,gpu_guard=b.gpu_guard)
    with pytest.raises(ValueError,match='load envelope'):again.prepare()
    for i in range(4):b.encode(['MOCK'+str(i)])
    with pytest.raises(ValueError,match='embedding envelope'):b.encode(['beyond limit'])


def test_out_of_scope_generation_stays_waiting(tmp_path):
    b,q,w,req,events,_,_=setup(tmp_path)
    changed={k:v for k,v in req.items() if k!='request_id'};changed['draw_identity']='another'
    changed=dict(changed,request_id=digest(changed));q.generate(changed)
    assert w.step()['status']=='OUTSIDE_LOCAL_STAGE' and not events


def test_gpu_visibility_rules_preserved_without_GPU():
    from metacom_pm.rl1.local_gpu_guard import parse_gpu
    def xml(process=''):
        return '<nvidia_smi_log><gpu><uuid>MOCK</uuid><processes>'+process+'</processes></gpu></nvidia_smi_log>'
    assert parse_gpu('MOCK, A6000, 46000, 0','',xml(),expected_uuid='MOCK')['eligible']
    assert not parse_gpu('MOCK, A6000, 40000, 0','',xml(),expected_uuid='MOCK')['eligible']
    p='<process_info><pid>123</pid><process_name>other</process_name><type>C</type></process_info>'
    assert not parse_gpu('MOCK, A6000, 46000, 0','',xml(p),expected_uuid='MOCK')['eligible']
    assert parse_gpu('MOCK, A6000, 5000, 40','',xml(p),expected_uuid='MOCK',own_pid=123)['eligible']
    assert not parse_gpu('MOCK, A6000, 46000, 0','',xml(),expected_uuid='WRONG')['eligible']


def probe_fixture(tmp_path):
    from metacom_pm.rl1.local_integration import trace,select_cases
    from metacom_pm.rl1.learning_preparation import TerminalCandidate
    from metacom_pm.rl1.schema import HEADS,PublicTurn
    b,_,_,_,events,spec,r=setup(tmp_path)
    episodes={};candidates=[]
    for i,head in enumerate(HEADS):
        s=replace(spec,prefix=replace(spec.prefix,session_id=f'MOCK_{i}',
            turns=(PublicTurn('seeker',f'MOCK public question {i}'),)))
        episodes[s.prefix.identity]=(s,r)
        _,requests=trace(s,r,head)
        for j,req in enumerate(requests):
            counts=tuple(int(j==1 and k==i) for k in range(4))
            candidates.append(TerminalCandidate(s.prefix.identity,'train',counts,
                0,req['request_id'],digest('MOCK prior'),'MOCK evidence',s.executor_identity,r.identity))
    cases=select_cases(candidates,episodes)
    p=local_protocol(scope=ENGINEERING,runtime=b.protocol['runtime'],bge_binding=dict(embedding_dimension=4),
        bge_runtime=dict(version='MOCK'),assets={},packages={},gpu_uuid='MOCK_GPU',
        request_ids=[r['request_id'] for c in cases for r in c['requests']],max_embedding_batches=8,
        context_identity=digest(cases))
    backend=LocalBackend(p,tmp_path/'probe/backend',generator_factory=b.generator_factory,
        bge_factory=b.bge_factory,gpu_guard=b.gpu_guard)
    return p,cases,episodes,backend,events


def test_complete_fixed_probe_is_source_bound_and_idempotent(tmp_path):
    from metacom_pm.rl1.local_integration import run_probe
    p,cases,episodes,b,events=probe_fixture(tmp_path)
    result=run_probe(p,cases,episodes,tmp_path/'probe',backend=b)
    assert len(result['generations'])==8 and len(result['feature_rows'])==8
    assert result['real_model_calls']==result['new_scoring_calls']==result['natural_policy_updates']==0
    assert len([e for e in events if e[0]=='generate'])==8
    assert len([e for e in events if e[0]=='encode'])==8
    count=len(events)
    assert run_probe(p,cases,episodes,tmp_path/'probe',backend=b)==result and len(events)==count


def test_probe_rejects_source_change_before_any_loader(tmp_path):
    from metacom_pm.rl1.local_integration import run_probe
    p,cases,episodes,b,events=probe_fixture(tmp_path)
    pid=cases[0]['prefix_identity'];s,r=episodes[pid]
    episodes[pid]=(replace(s,draw_identity='unexpected_draw'),r)
    with pytest.raises(ValueError,match='changed'):run_probe(p,cases,episodes,tmp_path/'probe',backend=b)
    assert not events and not b.root.exists()


def native_policy_backend(tmp_path,change=None):
    from dataclasses import asdict
    import json
    from metacom_pm.rl1.generation import NaturalEndPolicy
    b,_,_,_,events,_,_=setup(tmp_path)
    policy=asdict(NaturalEndPolicy(131072,(128001,128008,128009)))
    native={k:v for k,v in b.protocol['runtime'].items() if k!='identity'}
    native['policy']=policy
    expected=json.loads(json.dumps(stamp(native)))
    p=stamp({k:v for k,v in dict(b.protocol,runtime=expected).items() if k!='identity'})
    def factory(_):
        g=b.generator_factory(expected);g.manifest=native;g.identity=expected['identity']
        if change=='timeout':g.manifest['policy']['timeout_seconds']=301.
        if change=='eos':g.manifest['policy']['eos_token_ids']=(128001,128008,128010)
        if change=='identity':g.identity='FALSE_IDENTITY'
        return g
    return LocalBackend(p,tmp_path/'native',generator_factory=factory,
        bge_factory=b.bge_factory,gpu_guard=b.gpu_guard)


def test_native_policy_tuple_matches_json_freeze_by_full_canonical_identity(tmp_path):
    import json
    b=native_policy_backend(tmp_path);b.prepare()
    assert isinstance(b.generator.manifest['policy']['eos_token_ids'],tuple)
    assert isinstance(b.protocol['runtime']['policy']['eos_token_ids'],list)
    observed=json.loads((b.root/'load_0000.observed.json').read_text())
    assert observed['runtime']==b.protocol['runtime']
    assert observed['canonical_runtime_identity']==digest(b.protocol['runtime'])
    assert (b.root/'load_0000.done.json').exists()


@pytest.mark.parametrize('change',['timeout','eos','identity'])
def test_actual_runtime_change_is_retained_and_rejected_without_reload(tmp_path,change):
    import json
    b=native_policy_backend(tmp_path,change)
    with pytest.raises(ValueError,match='differs'):b.prepare()
    observed=json.loads((b.root/'load_0000.observed.json').read_text())
    assert observed['runtime']!=b.protocol['runtime']
    assert not (b.root/'load_0000.done.json').exists()
    with pytest.raises(ValueError,match='load envelope'):b.prepare()
