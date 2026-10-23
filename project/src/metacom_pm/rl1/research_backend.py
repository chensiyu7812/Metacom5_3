"""Shared source-bound pool/learning backend; no implicit provider or training."""
from .bound_generation import BoundResourceEnv
from .cached_generation_worker import replay_cached_generations
from .calibration_workflow import qualify
from .learning_preparation import compile_demonstration
from .measurement_identity import binding
from .natural_runner import require_qualified_episode
from .schema import digest
from .supervised_learning import prepare_supervised


class ResearchBackend:
    def __init__(self,queue,*,qualification_bundle,measurement_worker=None,generation_cache=None,generation_worker=None):
        self.queue=queue;self.bundle=qualification_bundle
        self.measurement=measurement_worker;self.generation_cache=generation_cache
        self.generation_worker=generation_worker
        if generation_worker is not None and generation_worker.queue.path.resolve()!=queue.path.resolve():
            raise ValueError('generation worker belongs to another queue')
        self.qualification=qualify(**qualification_bundle) if qualification_bundle is not None else None
        if measurement_worker is not None and (measurement_worker.queue.path.resolve()!=queue.path.resolve()
                or measurement_worker.qualification!=self.qualification):
            raise ValueError('worker belongs to another queue or qualification')

    def service_once(self):
        """At most one explicitly attached score attempt; cache-only G by default."""
        generated=replay_cached_generations(self.queue,self.generation_cache) if self.generation_cache else None
        generation_attempt=self.generation_worker.step() if self.generation_worker else None
        scored=self.measurement.step() if self.measurement else dict(status='NO_QUALIFIED_WORKER')
        return dict(generation=generated,generation_attempt=generation_attempt,measurement=scored)

    def pool_receipts(self,candidates,*,episodes,evidence):
        if self.qualification is None:
            return {} # no auto-selection of a judge or promotion of old diagnostic scores
        freeze=self.bundle['freeze'];receipts={}
        for c in candidates:
            spec,renderer=episodes[c.prefix_identity]
            require_qualified_episode(spec,freeze,self.bundle['inputs'],self.qualification)
            env=BoundResourceEnv(spec,renderer)
            for _,action in compile_demonstration(lambda:BoundResourceEnv(spec,renderer),c.counts):
                env.step(action,expected_state_hash=env.state_hash)
            request=env.generation_request()
            if (request['request_id']!=c.request_identity or renderer.cost(spec,c.counts)!=c.resource_tokens
                    or renderer.identity!=c.renderer_identity or spec.executor_identity!=c.executor_identity
                    or spec.prefix.split!='train' or c.split!='train'
                    or digest(evidence[c.prefix_identity])!=c.evidence_identity):
                raise ValueError('pool candidate changed source/plan or includes held-out feedback')
            raw=self.queue.generate(request)
            if raw is None:continue
            if (raw.get('request_id')!=request['request_id']
                    or raw.get('runtime_identity')!=request['executor_identity']
                    or raw.get('source_provenance_identity')!=digest(request['provenance'])
                    or raw.get('finish_reason')!='natural_stop' or digest(raw.get('text'))!=c.response_identity):
                raise ValueError('pool response differs from its frozen generation')
            query=binding(c.request_identity,c.response_identity,c.evidence_identity,freeze,self.qualification)
            result=self.queue.measure(query,evidence[c.prefix_identity],raw['text'])
            if result is not None:receipts[c.request_identity]=result
        return receipts

    def prepare_supervision(self,candidates,*,menu,episodes,evidence,view,method,union_bundle=None):
        receipts=self.pool_receipts(candidates,episodes=episodes,evidence=evidence)
        return prepare_supervised(candidates,menu=menu,receipts=receipts,
            qualification_bundle=self.bundle,episodes=episodes,view=view,method=method,union_bundle=union_bundle)

    def learning_cycle(self,run,*,allow_update=False):
        if self.bundle is None or run.bundle!=self.bundle:
            raise ValueError('learning and feedback qualification differ')
        run.poll(self.queue)
        service=self.service_once()
        after=run.poll(self.queue)
        complete=all(r['phase']=='terminal' and r['return_value'] is not None for r in after)
        update=run.update_once() if allow_update and complete else None
        return dict(status='UPDATED' if update else 'FEEDBACK_COMPLETE' if complete else 'PENDING_FEEDBACK',
            results=after,service=service,update=update)
