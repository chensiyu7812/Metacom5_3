"""Latency-aware adapter over the original durable BC-to-PPO coordinator.

Quality transport/qualification and historical token containers stay intact.
All optimizer targets are replaced by the explicit balanced objective. Timing
lookup supplies already bound receipts; this adapter never dispatches G/J or
relabels a diagnostic/unqualified reply. Checkpoints include timing evidence.
"""
from copy import deepcopy
import json
from pathlib import Path

import torch

from .balanced_objective import VERSION,BalancedObjective,ppo_targets,rewards
from .calibration_workflow import stamp,verify_identity
from .durable import publish,save_json_once
from .natural_batch import parameter_identity
from .organized_feedback import OrganizedEpisode
from .organized_learning import OrganizedRun
from .organized_policy_interface import HeadSession
from .organized_supervision import VERSION as QUALITY_VERSION
from .schema import digest
from .supervised_learning import save_json,file_sha


def episode_endpoint(e):
    if e.phase=='acquiring':raise ValueError('complete acquisition required')
    return stamp(dict(version=QUALITY_VERSION,prefix_identity=e.catalog.prefix.identity,
        actions=[s['action'] for s in e.steps],requests=deepcopy(e.requests),
        resource_tokens=e.session.observe().resource_tokens,cost_identity=e.cost.identity,
        evidence_source=deepcopy(e.evidence_source),domain_identity=e.domain))


class BalancedRun(OrganizedRun):
    def __init__(self,prepared,**kwargs):
        meta=prepared['metadata']
        if meta.get('reward_adapter')!=VERSION or meta.get('path_family')!='sequential':
            raise ValueError('balanced sequential initialization required')
        self.objective=BalancedObjective(**meta['balanced_objective'])
        if self.objective.identity!=meta['cost_identity']:raise ValueError('balanced objective changed')
        self.legacy_cost=meta['legacy_quality_container_cost_identity'];self.latency_feedback={}
        self.execution_path=meta['execution_path_identity']
        super().__init__(prepared,**kwargs)

    def _episode(self,e,b,split='train'):
        if type(e) is not OrganizedEpisode or e.route is None:raise ValueError('qualified organized episode required')
        e.route.check(e.domain);domain=self.manifest['resource_domain']
        if (e.catalog.prefix.split!=split or e.catalog.prefix.identity!=b['prefix_identity']
                or e.catalog.prefix.owner_id!=b['owner'] or e.catalog.identity!=b['spec_identity']
                or e.trajectory_id!=b['trajectory_id'] or digest(e.evidence)!=b['evidence_identity']
                or e.renderer.identity!=b['renderer_identity'] or e.executor_identity not in self.manifest['executors']
                or e.route.bundle!=self.bundle or e.route.qualification!=self.qualification
                or e.route.use_record['identity']!=domain['measurement_use_identity']
                or e.cost.identity!=self.legacy_cost or domain['cost_identity']!=self.objective.identity
                or e.session.observe().body_visible==self.view.no_text):
            raise ValueError('episode differs from balanced source/quality/objective binding')

    def _timing(self,e,*,area,behavior,lookup=None):
        key=digest(dict(area=area,trajectory=e.trajectory_id));path=self.workdir/(key+'.latency.json')
        expected=dict(run_identity=self.manifest['identity'],area=area,trajectory=e.trajectory_id,
            behavior=behavior,objective_identity=self.objective.identity)
        record=self.latency_feedback.get(key)
        if path.exists():
            saved=json.loads(path.read_text());verify_identity(saved)
            if record is not None and saved!=record:raise ValueError('timing changed after checkpoint')
            record=saved
        if record is None and lookup is not None:
            receipt=lookup(e,behavior)
            if receipt is not None:record=stamp(expected|dict(receipt=receipt))
        if record is None:return None
        verify_identity(record)
        if any(record.get(k)!=v for k,v in expected.items()):raise ValueError('timing belongs to another behavior/run')
        t=record['receipt'];verify_identity(t);endpoint=episode_endpoint(e);req=e.requests['ON']
        if (t['endpoint_identity']!=endpoint['identity'] or t['input_identity']!=digest(req['messages'])
                or t['execution_path_identity']!=self.execution_path or t['without_text']!=self.view.no_text
                or t['behavior_identity']!=behavior
                or t['decision_mode'] not in ('sampled_policy','policy_replay','greedy_policy')
                or req['request_id'] not in e.responses or t['reply_identity']!=digest(e.responses[req['request_id']]['text'])):
            raise ValueError('timing/source/qualified answer mismatch')
        rewards(e.terminal_reward,t,objective=self.objective,actions=endpoint['actions'],path_family='sequential')
        save_json_once(path,record);self.latency_feedback[key]=record
        return t

    def poll(self,queue,timing_lookup=None):
        batch=self.batch_id;quality=super().poll(queue)
        with self.locked():
            self._permission();self._behavior()
            if self.batch_id!=batch:raise ValueError('batch changed during feedback')
            result=[]
            for row,q in zip(self.records,quality):
                e=row['episode']
                t=self._timing(e,area=batch,behavior=self.behavior,lookup=timing_lookup) if e.phase=='terminal' else None
                if e.phase!='terminal':result.append(q)
                elif t is None:result.append(stamp(dict(phase='pending_latency',return_value=None,objective_identity=self.objective.identity)))
                else:
                    rs=rewards(e.terminal_reward,t,objective=self.objective,actions=[s['action'] for s in e.steps],path_family='sequential')
                    result.append(stamp(dict(phase='terminal',quality_gain=e.terminal_reward,return_value=sum(rs),
                        rewards=rs,objective_identity=self.objective.identity,latency_receipt_identity=t['identity'])))
            index=len(list(self.workdir.glob(batch+'.balanced_feedback_*.pt')))
            self._save(self.workdir/(batch+f'.balanced_feedback_{index:04d}.pt'))
            return result

    def _update_episodes(self):
        original=super()._update_episodes()  # validates every qualified episode and current behavior source
        result=[]
        for row,old in zip(self.records,original):
            e=row['episode'];t=self._timing(e,area=self.batch_id,behavior=self.behavior)
            if t is None:raise ValueError('all 16 latency receipts required; no zero/drop of pending')
            result.append(ppo_targets(old['transitions'],gain=e.terminal_reward,timing=t,
                endpoint_identity=episode_endpoint(e)['identity'],objective=self.objective,policy_version=self.trainer.version,
                execution_path_identity=self.execution_path,behavior_identity=self.behavior))
        return result

    def _feedback_export(self):
        result=[]
        for row in self.records:
            e=row['episode'];t=self._timing(e,area=self.batch_id,behavior=self.behavior)
            if t is None:raise ValueError('cannot export an update with missing latency')
            rs=rewards(e.terminal_reward,t,objective=self.objective,actions=[s['action'] for s in e.steps],path_family='sequential')
            for item in e.feedback_export():
                result.append(dict(item,legacy_cost_role='quality-container provenance only; not optimized',
                    training_objective_identity=self.objective.identity,training_return=sum(rs),
                    applied_rewards=rs,latency_receipt=t))
        return result

    def _save(self,path):
        # Same atomic checkpoint shape as the original coordinator, plus exact
        # latency evidence; update-intent SHA now binds BOTH quality and time.
        state=dict(run_identity=self.manifest['identity'],initialization_identity=self.initialization_identity,
            model=self.model.state_dict(),optimizer=self.trainer.optimizer.state_dict(),version=self.trainer.version,
            rng=self.rng_state,batch_id=self.batch_id,behavior=self.behavior,consumed=self.consumed,
            update_statistics=self.update_statistics,objective_identity=self.objective.identity,
            latency_feedback=deepcopy(self.latency_feedback),
            replay_runtime=dict(torch=str(torch.__version__),threads=torch.get_num_threads(),device='cpu'),
            records=[dict(trajectory_id=r['episode'].trajectory_id,snapshot=r['episode'].snapshot(),
                transitions=r['transitions']) for r in self.records])
        publish(path,lambda f:torch.save(state,f));path.chmod(0o600)
        save_json(Path(str(path)+'.sha256.json'),dict(sha256=file_sha(path)))

    def _restore(self,path,episodes,partial=False):
        super()._restore(path,episodes,partial=partial)
        state=torch.load(path,map_location='cpu',weights_only=True)
        if state.get('objective_identity')!=self.objective.identity:raise ValueError('checkpoint objective changed')
        self.latency_feedback=state['latency_feedback']
        for key,record in self.latency_feedback.items():
            verify_identity(record);save_json_once(self.workdir/(key+'.latency.json'),record)

    def evaluate_development(self,episodes,queue,timing_lookup=None):
        with self.locked():
            self._permission();bindings=self.development_bindings()
            if len(episodes)!=18:raise ValueError('all 18 development prefixes required')
            parameter=parameter_identity(self.model);count=self.trainer.version*16;results=[]
            def policy(obs):
                x,mask=self.view.sequential(obs)
                with torch.no_grad():dist,_=self.model(torch.tensor(x,dtype=torch.float32),torch.tensor(mask))
                return int(dist.probs.argmax())
            for e,b in zip(episodes,bindings):
                self._episode(e,b,split='dev')
                if e.phase=='acquiring':e.acquire(policy)
                replay=HeadSession(e.catalog,e.renderer,without_text=self.view.no_text)
                for step in e.steps:
                    if step['action']!=policy(replay.observe()):raise ValueError('dev action changed')
                    replay.step(step['action'])
                q=e.advance(queue.generate,queue.measure)
                t=self._timing(e,area=f'dev_{count}',behavior=parameter,lookup=timing_lookup) if e.phase=='terminal' else None
                if e.phase!='terminal':results.append(q)
                elif t is None:results.append(dict(phase='pending_latency',return_value=None))
                else:
                    rs=rewards(e.terminal_reward,t,objective=self.objective,actions=[s['action'] for s in e.steps],path_family='sequential')
                    results.append(dict(phase='terminal',return_value=sum(rs),quality_gain=e.terminal_reward,
                        latency_receipt_identity=t['identity'],objective_identity=self.objective.identity))
            if parameter_identity(self.model)!=parameter:raise ValueError('development changed parameters')
            complete=all(r['phase']=='terminal' and r['return_value'] is not None for r in results)
            report=stamp(dict(status='DEVELOPMENT_COMPLETED' if complete else 'DEVELOPMENT_PENDING',
                run_identity=self.manifest['identity'],completed_episodes=count,parameters=parameter,
                prefix_identities=[b['prefix_identity'] for b in bindings],results=results,
                scope=self.manifest['scope'],natural_policy_updates=0,objective_identity=self.objective.identity))
            if complete:
                path=self.workdir/f'dev_{count}.json'
                if path.exists():
                    if json.loads(path.read_text())!=report:raise ValueError('completed development report changed')
                else:save_json(path,report)
            return report
