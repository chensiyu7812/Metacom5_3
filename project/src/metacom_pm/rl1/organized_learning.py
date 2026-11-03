"""Organized-domain adapter for the existing qualified learning coordinator.

Reuse its fixed schedule, BC initialization, PPO, update checkpoints, recovery,
development checkpoints and completion receipts. Only environment/collection
and feedback projection differ. No provider, model loader or synthetic reward
fallback is available here.
"""
from copy import deepcopy
import json

import torch

from .calibration_workflow import stamp
from .natural_batch import parameter_identity
from .organized_feedback import OrganizedEpisode
from .organized_policy_interface import HeadSession
from .organized_rollout import OrganizedRollout
from .organized_supervision import VERSION as SUPERVISION_VERSION
from .qualified_learning import QualifiedRun
from .schema import digest
from .supervised_learning import save_json


class OrganizedRun(QualifiedRun):
    def __init__(self, prepared, **kwargs):
        if prepared.get('version') != SUPERVISION_VERSION:
            raise ValueError('organized supervision required')
        super().__init__(prepared, **kwargs)

    def _episode(self, e, b, split='train'):
        if type(e) is not OrganizedEpisode or e.route is None:
            raise ValueError('qualified organized episode required')
        e.route.check(e.domain)
        domain = self.manifest['resource_domain']
        if (e.catalog.prefix.split != split or e.catalog.prefix.identity != b['prefix_identity']
                or e.catalog.prefix.owner_id != b['owner'] or e.catalog.identity != b['spec_identity']
                or e.trajectory_id != b['trajectory_id'] or digest(e.evidence) != b['evidence_identity']
                or e.renderer.identity != b['renderer_identity']
                or e.executor_identity not in self.manifest['executors']
                or e.route.bundle != self.bundle or e.route.qualification != self.qualification
                or e.route.use_record['identity'] != domain['measurement_use_identity']
                or e.cost.identity != domain['cost_identity']
                or e.session.observe().body_visible == self.view.no_text):
            raise ValueError('episode differs from fixed organized schedule/domain')

    def collect(self, episodes):
        with self.locked():
            self._permission()
            v = self.trainer.version
            if self.batch_id is not None or v >= self.manifest['max_updates'] or len(episodes) != 16:
                raise ValueError('one remaining complete batch of 16 required')
            for e, b in zip(episodes, self.manifest['trajectories'][16*v:16*(v+1)]):
                self._episode(e, b)
                if e.phase != 'acquiring' or e.steps:
                    raise ValueError('fresh on-policy organized episode required')
            self.batch_id = digest(dict(run=self.manifest['identity'], version=v))
            self.behavior = parameter_identity(self.model)
            before = self.workdir/(self.batch_id+'.collection_0000.pt')
            if before.exists():
                raise FileExistsError('collection already started; use resume_collection')
            self._save(before)
            self._collect_organized(episodes)

    def _collect_organized(self, episodes):
        collector = OrganizedRollout(self.model, self.view,
            self.workdir/(self.batch_id+'.collection_steps'), run_identity=self.manifest['identity'],
            policy_version=self.trainer.version, seed=self.manifest['seed'],
            rng_state=self.rng_state.tolist())
        collector.fault_hook = self.fault_hook
        collector.collect(episodes)
        self.records = []
        for e, records in zip(episodes, collector.records):
            ts = deepcopy(records)
            for t in ts:
                for key in ('observation', 'old_log_prob', 'old_value'):
                    t[key] = torch.tensor(t[key], dtype=torch.float32)
                t['mask'] = torch.tensor(t['mask'], dtype=torch.bool)
                t['action'] = torch.tensor(t['action'], dtype=torch.long)
            self.records.append(dict(episode=e, transitions=ts))
        self.rng_state = torch.tensor(collector.rng, dtype=torch.uint8)
        self._behavior()
        self._save(self.workdir/(self.batch_id+'.collected.pt'))

    def resume_collection(self, episodes):
        with self.locked():
            self._permission()
            batch = digest(dict(run=self.manifest['identity'], version=self.trainer.version))
            before = self.workdir/(batch+'.collection_0000.pt')
            if not before.exists() or (self.workdir/(batch+'.collected.pt')).exists():
                raise ValueError('no interrupted collection; restore completed batch instead')
            self._restore(before, episodes, partial=True)
            for e, b in zip(episodes, self.manifest['trajectories'][16*self.trainer.version:16*(self.trainer.version+1)]):
                self._episode(e, b)
                if e.steps or e.phase != 'acquiring':
                    raise ValueError('fresh episodes required for step replay')
            self._collect_organized(episodes)

    def _feedback_export(self):
        return [item for row in self.records for item in row['episode'].feedback_export()]

    def evaluate_development(self, episodes, queue):
        with self.locked():
            self._permission()
            bindings = self.development_bindings()
            if len(episodes) != 18:
                raise ValueError('all 18 fixed dev prefixes required')
            parameter = parameter_identity(self.model)
            count = self.trainer.version*16

            def policy(obs):
                values, mask = self.view.sequential(obs)
                with torch.no_grad():
                    dist, _ = self.model(torch.tensor(values, dtype=torch.float32), torch.tensor(mask))
                return int(dist.probs.argmax())

            results = []
            for e, b in zip(episodes, bindings):
                self._episode(e, b, split='dev')
                if e.phase == 'acquiring':
                    e.acquire(policy)
                replay = HeadSession(e.catalog, e.renderer, without_text=self.view.no_text)
                for step in e.steps:
                    if step['action'] != policy(replay.observe()):
                        raise ValueError('dev action differs from fixed greedy policy')
                    replay.step(step['action'])
                results.append(e.advance(queue.generate, queue.measure))
            if parameter_identity(self.model) != parameter:
                raise ValueError('dev evaluation changed policy')
            complete = all(r['phase'] == 'terminal' and r['return_value'] is not None for r in results)
            report = stamp(dict(status='DEVELOPMENT_COMPLETED' if complete else 'DEVELOPMENT_PENDING',
                run_identity=self.manifest['identity'], completed_episodes=count, parameters=parameter,
                prefix_identities=[b['prefix_identity'] for b in bindings], results=results,
                scope=self.manifest['scope'], natural_policy_updates=0))
            if complete:
                path = self.workdir/f'dev_{count}.json'
                if path.exists():
                    if json.loads(path.read_text()) != json.loads(json.dumps(report)):
                        raise ValueError('completed dev result drift')
                else:
                    save_json(path, report)
            return report
