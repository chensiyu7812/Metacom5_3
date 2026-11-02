"""Durable variable-length collection and existing-PPO input assembly.

This is not a training entrypoint: no optimizer, initialization or permission
is created here. A qualified coordinator must supply the real BC checkpoint
and its execution grant. Synthetic tests may exercise existing PPO separately.
"""
from copy import deepcopy
import fcntl
import json
from pathlib import Path

import torch

from .calibration_workflow import stamp, verify_identity
from .durable import save_json_once
from .natural_batch import parameter_identity
from .organized_feedback import OrganizedEpisode
from .schema import digest

VERSION = 'pmrl1-organized-variable-rollout-v1'


class OrganizedRollout:
    def __init__(self, model, view, root, *, run_identity, policy_version, seed):
        if (not run_identity or type(policy_version) is not int or policy_version < 0
                or type(seed) is not int):
            raise ValueError('bound run/policy version/RNG required')
        self.model,self.view,self.root=model,view,Path(root)
        self.behavior=parameter_identity(model);self.version=policy_version
        self.identity=digest(dict(version=VERSION,run=run_identity,policy_version=policy_version,
            behavior=self.behavior,view=view.identity,no_text=view.no_text,seed=seed))
        self.rng=torch.Generator().manual_seed(seed).get_state().tolist()
        self.records=[];self.encoding=[];self.current=0;self.step_count=0
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.fault_hook=lambda event, **kw:None

    def _behavior(self):
        if parameter_identity(self.model) != self.behavior:
            raise ValueError('behavior parameters changed during collection/feedback')

    def _check(self, episodes):
        self._behavior()
        if (len(episodes)!=16 or len({e.trajectory_id for e in episodes})!=16
                or any(type(e) is not OrganizedEpisode or e.catalog.prefix.split!='train'
                    or e.session.observe().body_visible==self.view.no_text for e in episodes)):
            raise ValueError('16 unique train trajectories with matching persistent visibility required')
        if len({(e.domain,e.cost.identity,e.route.identity if e.route else None) for e in episodes}) != 1:
            raise ValueError('one common resource/feedback/cost domain per batch required')

    def _snapshot(self, episodes):
        return stamp(dict(collector_identity=self.identity,behavior=self.behavior,
            episode_bindings=[e.binding for e in episodes],current=self.current,steps=self.step_count,
            rng=self.rng,records=deepcopy(self.records),encoding=deepcopy(self.encoding),
            episodes=[e.snapshot() for e in episodes]))

    def _save(self, episodes):
        save_json_once(self.root/f'collection_{self.step_count:08d}.json',self._snapshot(episodes))

    def collect(self, episodes):
        self._check(episodes)
        with (self.root/'.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            paths=sorted(self.root.glob('collection_*.json'))
            if paths:
                saved=json.loads(paths[-1].read_text());verify_identity(saved)
                if (saved['collector_identity']!=self.identity or saved['behavior']!=self.behavior
                        or saved['episode_bindings']!=[e.binding for e in episodes]):
                    raise ValueError('collection belongs to another checkpoint/source')
                for e,s in zip(episodes,saved['episodes']):e.restore(s)
                self.current,self.step_count,self.rng,self.records,self.encoding=deepcopy(
                    (saved['current'],saved['steps'],saved['rng'],saved['records'],saved['encoding']))
            else:
                if any(e.phase!='acquiring' or e.steps for e in episodes):
                    raise ValueError('fresh episodes required')
                self.records=[[] for _ in episodes];self._save(episodes)
            while self.current<len(episodes):
                episode=episodes[self.current]
                while episode.phase=='acquiring':
                    obs=episode.session.observe()
                    with torch.random.fork_rng(devices=[]):
                        torch.set_rng_state(torch.tensor(self.rng,dtype=torch.uint8))
                        values,mask=self.view.sequential(obs)
                        with torch.no_grad():
                            dist,value=self.model(torch.tensor(values,dtype=torch.float32),torch.tensor(mask))
                            action=dist.sample()
                        rng=torch.get_rng_state().tolist()
                    episode.step(int(action))
                    transition=dict(observation=list(values),mask=list(mask),action=int(action),
                        old_log_prob=float(dist.log_prob(action)),old_value=float(value),
                        forced=sum(mask)==1,done=episode.phase!='acquiring',reward=episode.steps[-1]['reward'])
                    self.records[self.current].append(transition)
                    self.encoding.append(deepcopy(self.view.last_receipt))
                    self.rng=rng;self.step_count+=1
                    if episode.phase!='acquiring':self.current+=1
                    self._behavior();self._save(episodes)
                    self.fault_hook('step_committed',steps=self.step_count,complete=self.current)
            return stamp(dict(status='COLLECTED_PENDING_FEEDBACK',collector_identity=self.identity,
                trajectories=16,transitions=self.step_count,behavior=self.behavior,
                policy_version=self.version,natural_policy_updates=0))

    def poll(self, episodes, queue):
        self._check(episodes)
        if self.current!=16:raise ValueError('finish all 16 acquisitions before feedback')
        results=[e.advance(queue.generate,queue.measure) for e in episodes]
        # Recovering re-polls the durable queue, never resamples the policy.
        return results

    def ppo_inputs(self, episodes):
        self._check(episodes)
        if self.current!=16 or any(e.phase!='terminal' or e.route is None for e in episodes):
            raise ValueError('all 16 qualified ON/OFF returns required; no missing/drop/zero')
        result=[]
        for episode,record in zip(episodes,self.records):
            episode.route.check(episode.domain)
            if len(record)!=len(episode.steps) or [t['action'] for t in record]!=[s['action'] for s in episode.steps]:
                raise ValueError('feedback trajectory differs from collected policy')
            ts=deepcopy(record);remaining=0.
            for t,s in reversed(list(zip(ts,episode.steps))):
                t['reward']=s['reward'];remaining+=s['reward']
                t['return']=remaining;t['advantage']=remaining-t['old_value']
                t['observation']=torch.tensor(t['observation'],dtype=torch.float32)
                t['mask']=torch.tensor(t['mask'],dtype=torch.bool)
                t['action']=torch.tensor(t['action'])
                t['old_log_prob']=torch.tensor(t['old_log_prob'])
                t['old_value']=torch.tensor(t['old_value'])
            if abs(remaining-episode.result()['return_value'])>1e-10:
                raise ValueError('cost/terminal return mismatch')
            result.append(dict(complete=True,policy_version=self.version,transitions=ts,total_return=remaining))
        return result
