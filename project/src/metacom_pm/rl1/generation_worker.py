"""Finite source-bound generation worker for the shared feedback queue.

Unknown model entry is never replayed. A sealed returned result can finish
queue publication after a crash, without loading G or invoking it again.
"""
import fcntl
import json
from pathlib import Path

from .bound_generation import validate_and_project
from .calibration_workflow import stamp,verify_identity
from .local_backend import authorize
from .schema import digest
from .supervised_learning import save_json,file_sha


class GenerationWorker:
    def __init__(self,queue,backend,root):
        self.queue,self.backend,self.root=queue,backend,Path(root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        marker=dict(queue=str(queue.path.resolve()),backend_identity=backend.identity)
        path=self.root/'WORKER.json'
        if path.exists():
            if json.loads(path.read_text())!=marker:raise ValueError('generation worker directory changed')
        else:save_json(path,marker)

    def _validate(self,request,result):
        if (result.get('request_id')!=request['request_id']
                or result.get('runtime_identity')!=request['executor_identity']
                or result.get('source_provenance_identity')!=digest(request['provenance'])
                or result.get('finish_reason') not in ('natural_stop','technical_timeout','repetition_guard',
                    'context_exhausted','unexpected_stop','empty_output')
                or (result['finish_reason']=='natural_stop' and
                    (not isinstance(result.get('text'),str) or not result['text'].strip()))):
            raise ValueError('generation result/source/termination binding changed')

    def step(self):
        with (self.root/'.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            authorize(self.backend.protocol,self.backend.approval)
            with self.queue.transaction() as db:
                row=db.execute("SELECT id,payload,state FROM feedback WHERE kind='generation' "
                    "AND state IN ('WAITING','STARTED') ORDER BY CASE state WHEN 'STARTED' THEN 0 ELSE 1 END,rowid LIMIT 1").fetchone()
            if row is None:return dict(status='IDLE')
            key,payload,state=row;request=json.loads(payload)
            validate_and_project(request,self.backend.protocol['runtime']['identity'])
            if key!=digest(dict(kind='generation',payload=request)):raise ValueError('queued generation changed')
            if request['request_id'] not in self.backend.protocol['request_ids']:
                return dict(status='OUTSIDE_LOCAL_STAGE',queue_id=key)
            start=self.root/(key+'.started.json');raw=self.root/(key+'.raw.json');seal=self.root/(key+'.sealed.json')
            if state=='WAITING':
                # A known preflight failure must not pretend a G request entered.
                self.backend.prepare()
                job=self.queue.claim_next(kind='generation')
                if job is None or job['id']!=key:raise ValueError('concurrent generation claimant; reconcile')
                save_json(start,dict(queue_id=key,request=request,backend_identity=self.backend.identity))
            if not start.exists():return dict(status='RECONCILIATION_REQUIRED',reason='STARTED without owned journal')
            if json.loads(start.read_text())!=dict(queue_id=key,request=request,backend_identity=self.backend.identity):
                raise ValueError('generation journal identity changed')
            if seal.exists():
                receipt=json.loads(seal.read_text());verify_identity(receipt)
                if (receipt['queue_id']!=key or receipt['backend_identity']!=self.backend.identity
                        or receipt['raw_sha256']!=file_sha(raw)):
                    raise ValueError('sealed generation changed')
                result=json.loads(raw.read_text());self._validate(request,result)
                self.queue.settle(key,result)
                return dict(status='GENERATION_SETTLED',finish_reason=result['finish_reason'],
                            recovered_publication=True,new_calls=0)
            if state=='STARTED':
                return dict(status='RECONCILIATION_REQUIRED',reason='unfinished prior model entry; never resend')
            result=self.backend.generate(request)
            save_json(raw,result);self._validate(request,result)
            save_json(seal,stamp(dict(queue_id=key,backend_identity=self.backend.identity,raw_sha256=file_sha(raw))))
            self.queue.settle(key,result)
            return dict(status='GENERATION_SETTLED',finish_reason=result['finish_reason'],new_calls=1)
