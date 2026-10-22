"""Fixed train-source G/BGE integration, separate from scoring and learning."""
from dataclasses import asdict
import fcntl
import json
from pathlib import Path
import time

import torch

from .bound_generation import BoundResourceEnv
from .calibration_workflow import stamp,verify_identity
from .generation_worker import GenerationWorker
from .local_backend import LocalBackend,authorize
from .natural_batch import FeedbackQueue
from .research_backend import ResearchBackend
from .schema import HEADS,digest
from .supervised_learning import save_json


def trace(spec,renderer,head):
    if spec.prefix.split!='train':raise ValueError('local integration uses fixed train cases only')
    env=BoundResourceEnv(spec,renderer);initial=env.observe()
    env.step(HEADS.index(head)+1,expected_state_hash=env.state_hash);after=env.observe()
    if initial.acquired or len(after.acquired)!=1 or after.acquired[0].head!=head:
        raise ValueError('GET observation delivery differs')
    env.step(0,expected_state_hash=env.state_hash)
    off=BoundResourceEnv(spec,renderer);off.step(0,expected_state_hash=off.state_hash)
    return [initial,after],[off.generation_request(),env.generation_request()]


def select_cases(candidates,episodes):
    selected=[];used=set()
    by_plan={(c.prefix_identity,c.counts):c for c in candidates if c.split=='train'}
    for index,head in enumerate(HEADS):
        counts=tuple(int(i==index) for i in range(4))
        choices=[c for c in candidates if c.split=='train' and c.counts==counts
                 and c.prefix_identity not in used and (c.prefix_identity,(0,0,0,0)) in by_plan]
        if not choices:raise ValueError('cannot prepare four distinct existing train prefixes')
        chosen=min(choices,key=lambda c:digest(['pmrl1-local-integration-v1',head,c.prefix_identity]))
        spec,renderer=episodes[chosen.prefix_identity];observations,requests=trace(spec,renderer,head)
        pair=[by_plan[(chosen.prefix_identity,(0,0,0,0))],chosen]
        if [c.request_identity for c in pair]!=[r['request_id'] for r in requests]:
            raise ValueError('fixed case differs from original P2 generation input')
        selected.append(dict(head=head,prefix_identity=chosen.prefix_identity,spec_identity=spec.identity,
            renderer_identity=renderer.identity,observations_identity=digest([asdict(o) for o in observations]),
            requests=requests,prior_reply_identities={c.request_identity:c.response_identity for c in pair}))
        used.add(chosen.prefix_identity)
    return selected


def verify_cases(cases,episodes):
    if len(cases)!=4 or [c['head'] for c in cases]!=list(HEADS) or len({c['prefix_identity'] for c in cases})!=4:
        raise ValueError('fixed four distinct train cases required')
    observations=[];requests=[]
    for case in cases:
        spec,renderer=episodes[case['prefix_identity']];obs,req=trace(spec,renderer,case['head'])
        if (case['spec_identity']!=spec.identity or case['renderer_identity']!=renderer.identity
                or digest(req)!=digest(case['requests']) or digest([asdict(o) for o in obs])!=case['observations_identity']):
            raise ValueError('fixed integration source/request/observation changed')
        observations.extend(obs);requests.extend(req)
    if len({r['request_id'] for r in requests})!=8:raise ValueError('exactly eight distinct requests required')
    return observations,requests


def run_probe(protocol,cases,episodes,root,*,approval=None,backend=None):
    # Authorization and all source checks precede any model/device operation.
    authorize(protocol,approval);verify_identity(protocol)
    if protocol['context_identity']!=digest(cases):raise ValueError('integration cases differ from approved stage')
    observations,requests=verify_cases(cases,episodes)
    if sorted(r['request_id'] for r in requests)!=protocol['request_ids']:raise ValueError('request scope changed')
    if protocol['max_generations']!=8 or protocol['max_loads']!=1 or protocol['max_embedding_batches']!=8:
        raise ValueError('this probe has exactly one load, eight generation slots and eight embedding batches')
    root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (root/'RESULT.json').exists():
            result=json.loads((root/'RESULT.json').read_text());verify_identity(result)
            if result['protocol_identity']!=protocol['identity']:raise ValueError('completed probe belongs to another scope')
            return result
        if (root/'STARTED.json').exists():raise ValueError('unfinished probe; inspect durable entries before a new load')
        backend=backend or LocalBackend(protocol,root/'backend',approval=approval)
        if backend.protocol!=protocol:raise ValueError('local backend identity mismatch')
        started=time.monotonic();rng=torch.get_rng_state().clone()
        # A busy device is an admission failure, not a consumed generation slot.
        # A model load that actually began remains durably bounded by LocalBackend.
        backend.prepare()
        save_json(root/'STARTED.json',dict(protocol_identity=protocol['identity']))
        queue=FeedbackQueue(root/'queue.sqlite');worker=GenerationWorker(queue,backend,root/'generation')
        service=ResearchBackend(queue,qualification_bundle=None,generation_worker=worker)
        encoder=backend.feature_encoder();features=[]
        for obs in observations:
            record=encoder.encode(obs)
            features.append(dict(observation_identity=digest(asdict(obs)),features_identity=digest(asdict(record))))
        if not torch.equal(rng,torch.get_rng_state()):raise ValueError('local services disturbed policy RNG')
        for request in requests:queue.generate(request)
        rows=[]
        while True:
            result=service.service_once()['generation_attempt']
            if result['status']=='IDLE':break
            if result['status']!='GENERATION_SETTLED':raise ValueError('generation incomplete; inspect probe journal')
            if result.get('finish_reason')!='natural_stop':raise ValueError('technical generation failure; no automatic repeat')
        for case in cases:
            for request in case['requests']:
                raw=queue.generate(request)
                if raw is None or raw['finish_reason']!='natural_stop':raise ValueError('missing complete bound reply')
                rows.append(dict(request_id=request['request_id'],response_identity=digest(raw['text']),
                    matches_prior_reply=digest(raw['text'])==case['prior_reply_identities'][request['request_id']],
                    generation_seconds=raw.get('generation_seconds'),output_tokens=raw.get('output_tokens')))
        if not torch.equal(rng,torch.get_rng_state()):raise ValueError('generation disturbed policy RNG')
        record=stamp(dict(status='LOCAL_G_BGE_INTEGRATION_COMPLETED',protocol_identity=protocol['identity'],
            scope=protocol['scope'],wall_seconds=time.monotonic()-started,feature_rows=features,generations=rows,
            backend_timings={p.name:json.loads(p.read_text()).get('seconds')
                             for p in sorted(backend.root.glob('*.done.json'))},
            runtime=protocol['runtime']['identity'],text_encoder_identity=protocol['text_encoder_identity'],
            real_model_calls=8 if protocol['scope']!='ENGINEERING_ONLY' else 0,
            new_scoring_calls=0,new_api_cost_usd='0',BC_checkpoints=0,natural_policy_updates=0,
            prior_generation_cache_modified=False,full_study_throughput_projection_valid=False))
        save_json(root/'RESULT.json',record);return record
