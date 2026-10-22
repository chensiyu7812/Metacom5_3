"""Qualified natural-learning coordinator, separate from the old diagnostic.

Requires real BC/value initialization, original qualification evidence, a
frozen owner-balanced schedule and stage permission. Providers are external
workers using the existing durable queue and their own atomic money broker.
This module cannot dispatch a model or increase a request/financial allowance.
"""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import math
import os
from pathlib import Path
import random

import torch

from .calibration_workflow import qualify, stamp, verify_identity
from .bound_generation import BoundResourceEnv
from .e0_learning import PPO
from .natural_batch import parameter_identity
from .natural_runner import NaturalEpisode, require_qualified_episode
from .schema import digest
from .supervised_learning import (ENGINEERING, NATURAL, file_sha, save_json,
    require_execution, validate_prepared, load_initialization)

VERSION='pmrl1-qualified-learning-v1'


def make_run_manifest(prepared, *, bindings, dev_bindings, seed, qualification, scale_evidence):
    """Outcome-blind fixed order; owner IDs never enter actor inputs."""
    validate_prepared(prepared);verify_identity(qualification)
    if prepared['method'] not in ('BC-init','PPO-NoText') or seed not in (17,29,43):
        raise ValueError('PPO requires its own original BC initialization')
    if qualification['identity']!=prepared['qualification_identity']:
        raise ValueError('qualification identity mismatch')
    required={'prefix_identity','owner','spec_identity','evidence_identity','renderer_identity'}
    if not bindings or any(set(b)!=required for b in bindings):
        raise ValueError('complete prefix/source bindings required')
    if len({b['prefix_identity'] for b in bindings})!=len(bindings):
        raise ValueError('duplicate train prefix')
    if (len(dev_bindings)!=18 or any(set(b)!=required for b in dev_bindings)
            or len({b['prefix_identity'] for b in dev_bindings})!=18
            or len({b['owner'] for b in dev_bindings})!=3
            or {b['owner'] for b in dev_bindings}&{b['owner'] for b in bindings}):
        raise ValueError('fixed 18-prefix / 3-owner development set required')
    if (not {g['prefix_identity'] for g in prepared['metadata']['groups']} <= {b['prefix_identity'] for b in bindings}
            or any(b['renderer_identity'] not in prepared['metadata']['renderers'] for b in bindings+dev_bindings)):
        raise ValueError('initial BC/renderer must belong to the fixed train stack')
    owners={owner:sorted([b for b in bindings if b['owner']==owner],key=lambda b:b['prefix_identity'])
            for owner in sorted({b['owner'] for b in bindings})}
    if len(owners)!=12 or any(len(rows)!=8 for rows in owners.values()):
        raise ValueError('original 12-owner, 96-prefix train schedule required')
    for k in ('hours_128','hours_384'):
        if type(scale_evidence.get(k)) not in (int,float) or not math.isfinite(scale_evidence[k]) or scale_evidence[k]<0:
            raise ValueError('finite full-engine throughput estimates required')
    if not scale_evidence.get('source_identity'):
        raise ValueError('scale decision must bind throughput evidence')
    size=128 if qualification['status']=='CALIBRATED_LOW_CONTRAST' or scale_evidence['hours_384']>96 else 384
    if size==128 and scale_evidence['hours_128']>96:
        raise ValueError('128 still exceeds envelope; explicit scheduling decision required')
    rng=random.Random(seed);order=[]
    for _ in range(4 if size==384 else 1):
        names=list(owners);rng.shuffle(names)
        groups={o:rng.sample(owners[o],8) for o in names}
        order.extend(groups[o][i] for i in range(8) for o in names)
    if size==128:
        names=list(owners);rng.shuffle(names)
        groups={o:rng.sample(owners[o],3) for o in names}
        order.extend(groups[o][i] for i in range(2) for o in names)
        order.extend(groups[o][2] for o in names[:8])
    base=dict(version=VERSION,scope=prepared['scope'],prepared_identity=prepared['identity'],
        method='PPO' if prepared['method']=='BC-init' else 'PPO-NoText',seed=seed,
        feature_identity=prepared['metadata']['feature_identity'],
        qualification_identity=qualification['identity'],
        qualification_bundle_identity=prepared['qualification_bundle_identity'],
        executors=prepared['metadata']['executors'],renderers=prepared['metadata']['renderers'],
        episodes=size,dev_checks=[64,128] if size==128 else [128,384],
        scale_evidence=deepcopy(scale_evidence),train_bindings=deepcopy(bindings),dev_bindings=deepcopy(dev_bindings),
        batch_size=16,max_updates=size//16)
    salt=digest(base)
    base['trajectories']=[dict(b,trajectory_id=digest(dict(run=salt,index=i,prefix=b['prefix_identity'])))
                          for i,b in enumerate(order)]
    return stamp(base)


class QualifiedRun:
    def __init__(self, prepared, *, manifest, qualification_bundle, view,
                 initialization_path, initialization_receipt, workdir, approval=None):
        validate_prepared(prepared);verify_identity(manifest)
        qualification=qualify(**qualification_bundle)
        if (digest(qualification_bundle)!=prepared['qualification_bundle_identity']
                or make_run_manifest(prepared,bindings=manifest['train_bindings'],dev_bindings=manifest['dev_bindings'],seed=manifest['seed'],
                    qualification=qualification,scale_evidence=manifest['scale_evidence'])!=manifest
                or view.identity!=manifest['feature_identity']
                or view.no_text!=(manifest['method']=='PPO-NoText')):
            raise ValueError('qualified run/source/feature identity mismatch')
        require_execution(manifest['scope'],manifest['identity'],approval,'natural_training')
        model,state=load_initialization(prepared,seed=manifest['seed'],path=initialization_path,
            receipt=initialization_receipt)
        self.manifest,self.approval,self.bundle=deepcopy((manifest,approval,qualification_bundle))
        self.qualification=qualification;self.view=view;self.model=model
        self.trainer=PPO(model);self.trainer.optimizer.load_state_dict(state['ppo_optimizer'])
        self.rng_state=state['torch_rng'].clone()
        self.records=[];self.batch_id=None;self.behavior=None;self.consumed=False
        self.initialization_identity=digest(initialization_receipt)
        self.workdir=Path(workdir);self.workdir.mkdir(parents=True,exist_ok=True,mode=0o700)
        with self.locked():
            binding=dict(manifest_identity=manifest['identity'],initialization_identity=self.initialization_identity)
            marker=self.workdir/'RUN.json'
            if marker.exists():
                if json.loads(marker.read_text())!=binding:raise ValueError('run directory already belongs to another source')
            else:save_json(marker,binding)

    @contextmanager
    def locked(self):
        with (self.workdir/'.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            yield

    def _permission(self):
        require_execution(self.manifest['scope'],self.manifest['identity'],self.approval,'natural_training')

    def _episode(self,e,b,split='train'):
        if type(e) is not NaturalEpisode:
            raise ValueError('formal coordinator requires qualified NaturalEpisode')
        require_qualified_episode(e.spec,self.bundle['freeze'],self.bundle['inputs'],self.qualification)
        if (e.spec.prefix.split!=split or e.spec.prefix.identity!=b['prefix_identity']
                or e.spec.prefix.owner_id!=b['owner'] or e.spec.identity!=b['spec_identity']
                or e.trajectory_id!=b['trajectory_id'] or digest(e.evidence)!=b['evidence_identity']
                or e.renderer.identity!=b['renderer_identity']
                or e.spec.executor_identity not in self.manifest['executors']
                or e.freeze!=self.bundle['freeze'] or e.qualification!=self.qualification):
            raise ValueError('episode differs from fixed train schedule/source')

    def _behavior(self):
        if self.behavior!=parameter_identity(self.model):
            raise ValueError('behavior weights changed while feedback is pending')

    def collect(self,episodes):
        with self.locked():
            self._permission()
            v=self.trainer.version
            if self.batch_id is not None or v>=self.manifest['max_updates'] or len(episodes)!=16:
                raise ValueError('one remaining complete batch of 16 required')
            expected=self.manifest['trajectories'][16*v:16*(v+1)]
            for e,b in zip(episodes,expected):
                self._episode(e,b)
                if e.env.phase!='acquiring':raise ValueError('new on-policy trajectory required')
            self.batch_id=digest(dict(run=self.manifest['identity'],version=v))
            self.behavior=parameter_identity(self.model)
            save_json(self.workdir/(self.batch_id+'.collection_started.json'),
                dict(version=v,behavior=self.behavior,trajectories=[e.trajectory_id for e in episodes]))
            with torch.random.fork_rng(devices=[]):
                torch.set_rng_state(self.rng_state)
                for e in episodes:
                    transitions=[]
                    def sample(observation):
                        values,mask=self.view.sequential(observation)
                        x=torch.tensor(values,dtype=torch.float32);mask=torch.tensor(mask,dtype=torch.bool)
                        with torch.no_grad():
                            dist,value=self.model(x,mask);action=dist.sample()
                        transitions.append(dict(observation=x,mask=mask,action=action.detach(),
                            old_log_prob=dist.log_prob(action).detach(),old_value=value.detach(),
                            forced=int(mask.sum())==1,done=False,reward=None))
                        return int(action)
                    e.acquire(sample)
                    for t,s in zip(transitions,e.steps):t['reward']=s['reward']
                    transitions[-1]['done']=True
                    self.records.append(dict(episode=e,transitions=transitions))
                self.rng_state=torch.get_rng_state().clone()
            self._behavior()
            self._save(self.workdir/(self.batch_id+'.collected.pt'))

    def poll(self,queue):
        with self.locked():
            self._permission();self._behavior()
            if self.batch_id is None or self.consumed:raise ValueError('no pending batch')
            results=[]
            for row in self.records:
                result=row['episode'].advance(queue.generate,queue.measure)
                row['transitions'][-1]['reward']=result['terminal_reward'];results.append(result)
            n=len(list(self.workdir.glob(self.batch_id+'.feedback_*.pt')))
            self._save(self.workdir/(self.batch_id+f'.feedback_{n:04d}.pt'))
            return results

    def update_once(self):
        with self.locked():
            self._permission();self._behavior()
            if self.consumed or len(self.records)!=16:raise ValueError('complete unconsumed batch required')
            episodes=[];v=self.trainer.version
            expected=self.manifest['trajectories'][16*v:16*(v+1)]
            for row,b in zip(self.records,expected):
                self._episode(row['episode'],b)
                result=row['episode'].result()
                if result['phase']!='terminal' or result['return_value'] is None:
                    raise ValueError('all 16 qualified rewards required; no zero/drop of pending')
                ts=deepcopy(row['transitions']);remaining=0.
                for t in reversed(ts):
                    remaining+=t['reward'];t['return']=remaining;t['advantage']=remaining-float(t['old_value'])
                if abs(remaining-result['return_value'])>1e-10:raise ValueError('trajectory return mismatch')
                episodes.append(dict(complete=True,policy_version=v,transitions=ts,total_return=remaining))
            intent=self.workdir/(self.batch_id+'.update_intent.json')
            save_json(intent,dict(batch=self.batch_id,version=v,behavior=self.behavior))
            with torch.random.fork_rng(devices=[]):
                torch.set_rng_state(self.rng_state)
                stats=self.trainer.update(episodes)
                self.rng_state=torch.get_rng_state().clone()
            self.consumed=True
            after=self.workdir/(self.batch_id+'.after.pt');self._save(after)
            receipt=stamp(dict(stats,batch_id=self.batch_id,run_identity=self.manifest['identity'],
                policy_version=self.trainer.version,completed_episodes=16*self.trainer.version,
                before=self.behavior,after=parameter_identity(self.model),scope=self.manifest['scope'],
                natural_policy_updates=int(self.manifest['scope']==NATURAL),
                checkpoint_sha256=file_sha(after)))
            save_json(self.workdir/(self.batch_id+'.update_done.json'),receipt)
            return receipt

    def next_batch(self):
        with self.locked():
            if not self.consumed or self.trainer.version>=self.manifest['max_updates']:
                raise ValueError('batch not completed or frozen run exhausted')
            if not (self.workdir/(self.batch_id+'.update_done.json')).exists():
                raise ValueError('update settlement requires reconciliation')
            if self.trainer.version*16 in self.manifest['dev_checks']:
                self._require_dev(self.trainer.version*16)
            self.records=[];self.batch_id=None;self.behavior=None;self.consumed=False

    def development_bindings(self):
        count=self.trainer.version*16
        if not self.consumed or count not in self.manifest['dev_checks']:
            raise ValueError('not a fixed development checkpoint')
        return [dict(b,trajectory_id=digest(dict(run=self.manifest['identity'],
            episodes=count,development=b['prefix_identity']))) for b in self.manifest['dev_bindings']]

    def evaluate_development(self,episodes,queue):
        """Greedy frozen-policy development evaluation; no optimizer or RNG use."""
        with self.locked():
            self._permission();bindings=self.development_bindings()
            if len(episodes)!=18:raise ValueError('all 18 fixed dev prefixes required')
            parameter=parameter_identity(self.model);count=self.trainer.version*16
            def policy(obs):
                values,mask=self.view.sequential(obs)
                with torch.no_grad():dist,_=self.model(torch.tensor(values,dtype=torch.float32),torch.tensor(mask))
                return int(dist.probs.argmax())
            results=[]
            for e,b in zip(episodes,bindings):
                self._episode(e,b,split='dev')
                if e.env.phase=='acquiring':e.acquire(policy)
                # Re-polling/restarting may reuse feedback, but not a trajectory
                # sampled with some other policy or a changed checkpoint.
                replay=BoundResourceEnv(e.spec,e.renderer)
                for step in e.steps:
                    if step['action']!=policy(replay.observe()):raise ValueError('dev action differs from fixed greedy policy')
                    replay.step(step['action'],expected_state_hash=replay.state_hash)
                results.append(e.advance(queue.generate,queue.measure))
            if parameter_identity(self.model)!=parameter:raise ValueError('dev evaluation changed policy')
            complete=all(r['phase']=='terminal' and r['return_value'] is not None for r in results)
            report=stamp(dict(status='DEVELOPMENT_COMPLETED' if complete else 'DEVELOPMENT_PENDING',
                run_identity=self.manifest['identity'],completed_episodes=count,parameters=parameter,
                prefix_identities=[b['prefix_identity'] for b in bindings],results=results,
                scope=self.manifest['scope'],natural_policy_updates=0))
            if complete:
                path=self.workdir/f'dev_{count}.json'
                if path.exists():
                    if json.loads(path.read_text())!=json.loads(json.dumps(report)):raise ValueError('completed dev result drift')
                else:save_json(path,report)
            return report

    def _require_dev(self,count):
        path=self.workdir/f'dev_{count}.json'
        if not path.exists():raise ValueError('fixed development evaluation still pending')
        report=json.loads(path.read_text());verify_identity(report)
        if (report['run_identity']!=self.manifest['identity'] or report['status']!='DEVELOPMENT_COMPLETED'
                or report['completed_episodes']!=count
                or report['prefix_identities']!=[b['prefix_identity'] for b in self.manifest['dev_bindings']]
                or (count==self.trainer.version*16 and report['parameters']!=parameter_identity(self.model))):
            raise ValueError('development checkpoint identity mismatch')

    def finish(self):
        with self.locked():
            self._permission()
            if not self.consumed or self.trainer.version!=self.manifest['max_updates']:
                raise ValueError('fixed training endpoint has not been reached')
            for count in self.manifest['dev_checks']:self._require_dev(count)
            return stamp(dict(status='FIXED_TRAINING_ENDPOINT_COMPLETED',run_identity=self.manifest['identity'],
                episodes=self.manifest['episodes'],updates=self.trainer.version,
                parameters=parameter_identity(self.model),scope=self.manifest['scope'],
                independent_test_evaluation_completed=False))

    def _save(self,path):
        state=dict(run_identity=self.manifest['identity'],initialization_identity=self.initialization_identity,
            model=self.model.state_dict(),optimizer=self.trainer.optimizer.state_dict(),version=self.trainer.version,
            rng=self.rng_state,batch_id=self.batch_id,behavior=self.behavior,consumed=self.consumed,
            records=[dict(trajectory_id=r['episode'].trajectory_id,snapshot=r['episode'].snapshot(),
                          transitions=r['transitions']) for r in self.records])
        with path.open('xb') as f:torch.save(state,f);f.flush();os.fsync(f.fileno())
        path.chmod(0o600);save_json(Path(str(path)+'.sha256.json'),dict(sha256=file_sha(path)))

    def restore(self,path,episodes):
        with self.locked():
            self._permission();path=Path(path)
            if file_sha(path)!=json.loads(Path(str(path)+'.sha256.json').read_text())['sha256']:
                raise ValueError('checkpoint integrity mismatch')
            state=torch.load(path,map_location='cpu',weights_only=True)
            if (state['run_identity']!=self.manifest['identity']
                    or state['initialization_identity']!=self.initialization_identity):
                raise ValueError('checkpoint belongs to another run/BC initialization')
            v=state['version']-int(state['consumed'])
            if not 0<=v<self.manifest['max_updates'] or len(episodes)!=16 or len(state['records'])!=16:
                raise ValueError('invalid pending/completed batch checkpoint')
            expected=self.manifest['trajectories'][16*v:16*(v+1)]
            for e,b,row in zip(episodes,expected,state['records']):
                self._episode(e,b)
                if row['trajectory_id']!=e.trajectory_id:raise ValueError('checkpoint trajectory mismatch')
                e.restore(row['snapshot'])
            self.model.load_state_dict(state['model']);self.trainer.optimizer.load_state_dict(state['optimizer'])
            self.trainer.version=state['version'];self.rng_state=state['rng']
            self.batch_id=state['batch_id'];self.behavior=state['behavior'];self.consumed=state['consumed']
            self.records=[dict(episode=e,transitions=row['transitions']) for e,row in zip(episodes,state['records'])]
            if not self.consumed:self._behavior()
