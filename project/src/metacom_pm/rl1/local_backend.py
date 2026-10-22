"""Explicitly bounded local G/BGE service, independent of the old diagnostic.

Importing/constructing a backend never loads a model. The caller supplies a
stage-bound authorization, original runtime identities and finite load/call
limits. Policy CPU RNG is preserved around every loader and model invocation.
"""
from copy import deepcopy
from dataclasses import asdict
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import time

import torch

from .bound_generation import validate_and_project
from metacom_pm.io import sha256_file
from .calibration_workflow import stamp, verify_identity
from .observation_features import PlanAwareFeatureEncoder
from .schema import digest
from .supervised_learning import save_json

ENGINEERING='ENGINEERING_ONLY'
LOCAL='BOUNDED_LOCAL_INTEGRATION'


def local_protocol(*,scope,runtime,bge_binding,bge_runtime,assets,packages,gpu_uuid,
                   request_ids,max_embedding_batches,max_loads=1,context_identity='ENGINEERING_FIXTURE'):
    if scope not in (ENGINEERING,LOCAL) or not request_ids or len(set(request_ids))!=len(request_ids):
        raise ValueError('explicit local scope and unique finite generation requests required')
    if any(type(v) is not int or v<1 for v in (max_embedding_batches,max_loads)):
        raise ValueError('finite load and embedding envelopes required')
    if digest({k:v for k,v in runtime.items() if k!='identity'})!=runtime['identity']:
        raise ValueError('executor runtime identity changed')
    if scope==LOCAL and context_identity=='ENGINEERING_FIXTURE':raise ValueError('bind the actual fixed integration cases')
    return stamp(dict(version='pmrl1-local-backend-v1',scope=scope,runtime=deepcopy(runtime),
        bge_binding=deepcopy(bge_binding),bge_runtime=deepcopy(bge_runtime),
        text_encoder_identity=digest(dict(binding=bge_binding,runtime=bge_runtime)),
        assets=deepcopy(assets),packages=deepcopy(packages),gpu_uuid=gpu_uuid,
        request_ids=sorted(request_ids),max_generations=len(request_ids),max_embedding_batches=max_embedding_batches,
        max_loads=max_loads,context_identity=context_identity,api_calls=0,training_updates=0,automatic_retry=False))


def authorize(protocol,approval):
    verify_identity(protocol)
    if protocol['scope']==ENGINEERING:return
    if (protocol['scope']!=LOCAL or not isinstance(approval,dict)
            or approval.get('status')!='APPROVED' or approval.get('protocol_identity')!=protocol['identity']
            or not approval.get('user_authorization_reference')
            or approval.get('operations')!=['local_generation','public_embedding']):
        raise ValueError('this fixed local integration stage is not authorized')


def check_static(protocol):
    verify_identity(protocol)
    for path,expected in protocol['assets'].items():
        if sha256_file(Path(path))!=expected:raise ValueError('local source/model file changed: '+str(path))
    for name,expected in protocol['packages'].items():
        if importlib.metadata.version(name)!=expected:raise ValueError('frozen package version changed: '+name)
    return dict(files=len(protocol['assets']),packages=len(protocol['packages']),model_loads=0)


def load_generator(runtime):
    # Use the original public loader byte-for-byte; do not edit its frozen file.
    path=Path(__file__).resolve().parents[3]/'scripts/rl1/92_run_p2_common_pool.py'
    spec=importlib.util.spec_from_file_location('pmrl1_original_generator_loader',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.load_frozen_generator(runtime)


def load_bge():
    from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Encoder
    return BgeM3Encoder()


class LocalBackend:
    def __init__(self,protocol,root,*,approval=None,generator_factory=None,bge_factory=None,gpu_guard=None):
        verify_identity(protocol)
        if protocol['scope']!=ENGINEERING and any(x is not None for x in (generator_factory,bge_factory,gpu_guard)):
            raise ValueError('production uses the frozen loaders and GPU guard')
        if protocol['scope']==ENGINEERING and any(x is None for x in (generator_factory,bge_factory,gpu_guard)):
            raise ValueError('engineering requires explicit synthetic G/BGE/guard')
        self.protocol,self.approval=deepcopy((protocol,approval));self.root=Path(root)
        self.generator_factory=generator_factory or load_generator
        self.bge_factory=bge_factory or load_bge
        self.gpu_guard=gpu_guard;self.generator=None;self.bge=None
        # Pure construction: authorization, filesystem and hardware deferred.

    @property
    def identity(self):return self.protocol['identity']

    def _ensure(self):
        authorize(self.protocol,self.approval)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        marker=self.root/'BACKEND.json'
        if marker.exists():
            if json.loads(marker.read_text())!=self.protocol:raise ValueError('local stage directory changed')
        else:save_json(marker,self.protocol)
        if self.generator is not None:
            self.gpu_guard.check(own_pid=os.getpid());return
        loads=sorted(self.root.glob('load_*.started.json'))
        if len(loads)>=self.protocol['max_loads']:
            raise ValueError('load envelope exhausted; interrupted load is not retried')
        if self.protocol['scope']!=ENGINEERING:
            for key in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE'):
                if os.environ.get(key)!='1':raise ValueError('offline local model loading required')
            check_static(self.protocol)
            from .local_gpu_guard import LocalGPUCheck
            self.gpu_guard=LocalGPUCheck(self.protocol['gpu_uuid'],self.protocol['runtime'],self.root/'gpu_checks')
        self.gpu_guard.check()
        index=len(loads)
        save_json(self.root/f'load_{index:04d}.started.json',dict(protocol_identity=self.identity))
        started=time.monotonic()
        self.generator=self.generator_factory(self.protocol['runtime'])
        if dict(self.generator.manifest,identity=self.generator.identity)!=self.protocol['runtime']:
            self.generator=None
            raise ValueError('loaded generator differs from frozen runtime')
        save_json(self.root/f'load_{index:04d}.done.json',dict(runtime=self.protocol['runtime'],seconds=time.monotonic()-started))

    def feature_encoder(self):
        return PlanAwareFeatureEncoder(self.encode,embedding_dimension=self.protocol['bge_binding']['embedding_dimension'],
            text_encoder_identity=self.protocol['text_encoder_identity'])

    def prepare(self):
        with torch.random.fork_rng(devices=[]):self._ensure()

    def encode(self,texts):
        if not texts or any(not isinstance(x,str) or not x for x in texts):raise ValueError('nonempty public texts required')
        with torch.random.fork_rng(devices=[]):
            self._ensure() # G must load first, before BGE consumes its memory reserve.
            prior=sorted(self.root.glob('embedding_*.started.json'))
            if any(not p.with_name(p.name.replace('.started.','.done.')).exists() for p in prior):
                raise ValueError('unfinished embedding invocation; reconcile before continuing')
            if len(prior)>=self.protocol['max_embedding_batches']:raise ValueError('embedding envelope exhausted')
            if self.bge is None:
                if (self.root/'bge_load.started.json').exists():
                    raise ValueError('prior BGE load exists; no automatic reload')
                save_json(self.root/'bge_load.started.json',dict(protocol_identity=self.identity))
                started=time.monotonic()
                self.bge=self.bge_factory()
                if asdict(self.bge.binding)!=self.protocol['bge_binding'] or asdict(self.bge.runtime_identity)!=self.protocol['bge_runtime']:
                    self.bge=None
                    raise ValueError('loaded BGE identity changed')
                save_json(self.root/'bge_load.done.json',dict(runtime=self.protocol['bge_runtime'],seconds=time.monotonic()-started))
            self.gpu_guard.check(own_pid=os.getpid())
            name=f'embedding_{len(prior):04d}'
            save_json(self.root/(name+'.started.json'),dict(texts_identity=digest(texts),rows=len(texts)))
            started=time.monotonic()
            vectors=self.bge.encode(texts)
            dimension=self.protocol['bge_binding']['embedding_dimension']
            if len(vectors)!=len(texts) or any(len(v)!=dimension or not all(math.isfinite(x) for x in v) for v in vectors):
                raise ValueError('BGE output shape or finite-value mismatch')
            save_json(self.root/(name+'.done.json'),dict(rows=len(vectors),dimension=dimension,
                vectors_identity=digest(vectors),text_encoder_identity=self.protocol['text_encoder_identity'],seconds=time.monotonic()-started))
            return vectors

    def generate(self,request):
        authorize(self.protocol,self.approval)
        validate_and_project(request,self.protocol['runtime']['identity'])
        if request['request_id'] not in self.protocol['request_ids']:raise ValueError('generation outside fixed local stage')
        name='generation_'+request['request_id']
        if (self.root/(name+'.started.json')).exists():raise ValueError('generation already entered; no automatic repeat')
        with torch.random.fork_rng(devices=[]):
            self._ensure()
            save_json(self.root/(name+'.started.json'),dict(protocol_identity=self.identity,request=request))
            result=self.generator.generate(request)
            save_json(self.root/(name+'.raw.json'),result)
            return result
