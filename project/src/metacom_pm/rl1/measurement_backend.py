"""One logical qualified score over finite, durably accounted attempts.

Transport, request preparation, parsing and financial policy are injected, never
selected implicitly. The worker cannot qualify a candidate or read credentials.
Old diagnostic STOPs and results are outside its new stage directory.
"""
from copy import deepcopy
import fcntl
import json
from pathlib import Path

from .calibration_workflow import qualify, stamp
from .measurement_identity import POLICY
from .recovery_schedule import RecoverySchedule, Slot
from .schema import digest
from .supervised_learning import ENGINEERING, require_execution, save_json, file_sha


def budget_policy(budget):
    return {k:getattr(budget,k) for k in ('trial','study','stage_cap','trial_cap','shared_cap',
        'baseline','opening','external_liability','old_cap','account_opening','opening_trial')}


class QualifiedFeedbackBackend:
    """Only publish a final logical result; recoverable failures stay pending.

    `adapter` binds identity, code_identity and protocol_identity, prepares the
    exact wire request and evaluates a raw response. `transport.send` must return
    bound request/runtime identities and final usage, or leave delivery unknown.
    `cost(raw)` returns settled nanodollars, or None; zero must be explicit.
    The injected append-only budget shares the existing global financial ledger.
    """
    def __init__(self, queue, *, bundle, adapter, transport, cost, budget, root,
                 scope, max_attempts, recovery_cap, reserve_nanodollars, approval=None):
        q=qualify(**bundle)
        freeze=bundle['freeze']
        if q['status'] not in ('CALIBRATED_FOR_BOUNDED_STUDY','CALIBRATED_LOW_CONTRAST'):
            raise ValueError('feedback route has not qualified')
        if (adapter.identity!=freeze['runtime_identity']
                or adapter.code_identity!=freeze['bindings']['code']
                or adapter.protocol_identity!=freeze['scorer_protocol_identity']):
            raise ValueError('adapter differs from the qualified frozen route')
        if any(type(n) is not int or n<0 for n in (max_attempts,recovery_cap,reserve_nanodollars)) or max_attempts<1:
            raise ValueError('finite attempt and money envelopes required')
        self.protocol=stamp(dict(version='pmrl1-qualified-feedback-backend-v1',scope=scope,
            qualification_identity=q['identity'],freeze_identity=freeze['identity'],
            runtime_identity=adapter.identity,code_identity=adapter.code_identity,
            max_attempts=max_attempts,recovery_cap=recovery_cap,reserve_nanodollars=reserve_nanodollars,
            technical_retries=1,repeat_retries=0,budget_policy=budget_policy(budget)))
        require_execution(scope,self.protocol['identity'],approval,'qualified_feedback')
        if scope==ENGINEERING and getattr(transport,'engineering_only',False) is not True:
            raise ValueError('engineering requires an explicit synthetic transport')
        self.queue,self.adapter,self.transport,self.cost,self.budget=queue,adapter,transport,cost,budget
        self.scope,self.approval=scope,deepcopy(approval)
        self.bundle,self.qualification=deepcopy(bundle),q
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        marker=dict(protocol=self.protocol,queue=str(queue.path.resolve()),budget=str(budget.path.resolve()))
        path=self.root/'BACKEND.json'
        if path.exists():
            if json.loads(path.read_text())!=marker:raise ValueError('backend stage identity changed')
        else:save_json(path,marker)

    def _permission(self):
        require_execution(self.scope,self.protocol['identity'],self.approval,'qualified_feedback')
        if qualify(**self.bundle)!=self.qualification:raise ValueError('qualification changed')
        if budget_policy(self.budget)!=self.protocol['budget_policy']:
            raise ValueError('approved financial policy changed')

    def _rows(self):
        with self.queue.transaction() as db:
            return [dict(id=k,payload=json.loads(p),state=s,result=json.loads(r) if r else None)
                for k,p,s,r in db.execute("SELECT id,payload,state,result FROM feedback "
                    "WHERE kind='measurement' ORDER BY rowid")]

    def _guard(self, claim):
        _,_,reserved,settled=self.budget._totals(self.budget.events())
        own={k:v for k,v in reserved.items() if v.get('binding',{}).get('backend')==self.protocol['identity']}
        if set(own)-set(settled):raise ValueError('unknown delivery/liability; reconcile before dispatch')
        last,count=None,0
        for attempt,row in own.items():
            path=self.root/row['binding']['logical_feedback']/(attempt+'.result.json')
            if not path.exists():raise ValueError('settled attempt has no sealed result; reconcile')
            outcome=json.loads(path.read_text())['outcome']
            if outcome in ('format_failure','schema_failure'):
                count=count+1 if outcome==last else 1;last=outcome
            else:last,count=None,0
            if count>=3:raise ValueError('configuration circuit stopped after three matching technical failures')
        if len(own)>=self.protocol['max_attempts']:raise ValueError('stage attempt envelope exhausted')
        if claim['ordinal'] and sum(v['binding']['ordinal']>0 for v in own.values())>=self.protocol['recovery_cap']:
            raise ValueError('stage technical recovery envelope exhausted')

    def _reserve(self, claim):
        self._permission();self._guard(claim)
        binding=dict(backend=self.protocol['identity'],study=self.budget.study,
            logical_feedback=claim['slot_id'],ordinal=claim['ordinal'],input_identity=claim['input_identity'])
        self.budget.reserve(claim['attempt_id'],self.protocol['reserve_nanodollars'],binding)
        return dict(attempt_id=claim['attempt_id'],reservation_identity=digest(binding),
                    ledger=str(self.budget.path.resolve()))

    def step(self):
        """At most one physical attempt; returns pending/settled/reconcile status."""
        with (self.root/'.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self._permission()
            rows=self._rows()
            if any(r['payload']['binding'].get('cache_policy')!=POLICY for r in rows):
                raise ValueError('legacy diagnostic queue cannot be adopted as a qualified stage')
            active=next((r for r in rows if r['state']=='STARTED'),None)
            if active is None:
                item=self.queue.claim_next(kind='measurement')
                if item is None:return dict(status='IDLE')
                active=dict(id=item['id'],payload=item['payload'],state='STARTED')
                directory=self.root/active['id'];directory.mkdir(mode=0o700)
                save_json(directory/'LOGICAL.json',active)
            directory=self.root/active['id']
            if not (directory/'LOGICAL.json').exists():
                return dict(status='RECONCILIATION_REQUIRED',reason='started queue item has no owned journal')
            original=json.loads((directory/'LOGICAL.json').read_text())
            if original['id']!=active['id'] or original['payload']!=active['payload']:
                raise ValueError('logical request journal changed')
            p=active['payload'];b=p['binding'];f=self.bundle['freeze']
            if (b.get('cache_policy')!=POLICY or b.get('qualification_identity')!=self.qualification['identity']
                    or b.get('freeze_identity')!=f['identity'] or b.get('runtime_identity')!=f['runtime_identity']
                    or b.get('rubric_identity')!=f['rubric_identity']
                    or b.get('evidence_identity')!=digest(p['evidence']) or b.get('response_identity')!=digest(p['reply'])):
                raise ValueError('queued score is outside the qualified route/source')
            request=self.adapter.prepare(deepcopy(p['evidence']),p['reply'])
            # Request identity includes actual prompt/schema/config bytes, not G identity.
            request=dict(wire=request,binding=b,backend_identity=self.protocol['identity'])
            request['identity']=digest(request)
            reqpath=directory/'REQUEST.json'
            if reqpath.exists():
                if json.loads(reqpath.read_text())!=request:raise ValueError('actual scoring request changed')
            else:save_json(reqpath,request)
            repeat=b['measurement_purpose']=='independent_repeat'
            schedule=RecoverySchedule(directory/'attempts.sqlite',
                [Slot(active['id'],request['identity'],self.adapter.identity,'repeat' if repeat else 'qualification')],
                protocol_identity=self.protocol['identity'],max_attempts=1 if repeat else 2,
                recovery_cap=0 if repeat else 1)
            report=schedule.report()
            state=report['states'][active['id']]
            if report['global_stop']:
                return dict(status='RECONCILIATION_REQUIRED',reason=report['global_stop'])
            if state in ('VALID','UNRESOLVED','RECOVERY_EXHAUSTED'):
                return self._publish(active,directory,report)
            try:claim=schedule.claim_next(self._reserve)
            except ValueError as exc:
                # No model has been called. Financial or global capacity is not
                # a zero score or a completed per-item format failure.
                return dict(status='STAGE_BLOCKED',reason=str(exc))
            if claim is None:return dict(status='PENDING',state=state)
            attempt=claim['attempt_id']
            # Unknown exceptions/delivery are retained as outstanding attempts.
            # No automatic retry can pass the scheduler or the money guard.
            raw=self.transport.send(deepcopy(request),attempt_id=attempt)
            save_json(directory/(attempt+'.raw.json'),raw)
            amount=self.cost(raw)
            within=self.budget.settle(attempt,amount,'qualified feedback attempt')
            if amount is None:
                return dict(status='RECONCILIATION_REQUIRED',reason='usage/settlement unknown')
            if (not within or raw.get('request_identity')!=request['identity']
                    or raw.get('runtime_identity')!=self.adapter.identity):
                outcome='global_risk';evaluation=dict(q=None,m=None)
            else:
                evaluation=self.adapter.evaluate(deepcopy(raw),deepcopy(p))
                outcome=evaluation['outcome']
                if outcome=='valid':
                    if (type(evaluation.get('q')) is not int or evaluation['q'] not in range(5)
                            or type(evaluation.get('m')) not in (int,float) or evaluation['m'] not in (0,.25,1)):
                        raise ValueError('adapter returned invalid q/m; reconcile settled raw response')
                elif evaluation.get('q') is not None or evaluation.get('m') is not None:
                    raise ValueError('unusable feedback cannot carry numeric rewards')
            record=stamp(dict(attempt_id=attempt,request_identity=request['identity'],
                outcome=outcome,evaluation=evaluation,raw_sha256=file_sha(directory/(attempt+'.raw.json')),
                accounted_nanodollars=amount))
            save_json(directory/(attempt+'.result.json'),record)
            schedule.settle(attempt,outcome=outcome,input_identity=request['identity'],
                config_identity=self.adapter.identity,settlement_identity=digest(self.budget.events()[-1]),
                result_identity=record['identity'])
            report=schedule.report()
            if report['global_stop']:return dict(status='RECONCILIATION_REQUIRED',reason=report['global_stop'])
            if report['states'][active['id']] in ('VALID','UNRESOLVED','RECOVERY_EXHAUSTED'):
                return self._publish(active,directory,report)
            return dict(status='PENDING_TECHNICAL_RECOVERY',attempts=report['attempts'])

    def _publish(self,active,directory,report):
        row=report['attempts_log'][-1];attempt=row['claim']['attempt_id']
        rec=json.loads((directory/(attempt+'.result.json')).read_text())
        if digest({k:v for k,v in rec.items() if k!='identity'})!=row['result']['result_identity']:
            raise ValueError('sealed logical result changed')
        if file_sha(directory/(attempt+'.raw.json'))!=rec['raw_sha256']:
            raise ValueError('raw result changed')
        outcome=rec['outcome'];ev=rec['evaluation']
        status=('measured_candidate' if outcome=='valid' else 'semantic_uncertainty'
                if outcome in ('semantic_unknown','unavailable') else 'technical_failure')
        result=dict(binding=active['payload']['binding'],measurement_status=status,
            q=ev.get('q') if outcome=='valid' else None,m=ev.get('m') if outcome=='valid' else None,
            backend_identity=self.protocol['identity'],attempt_receipt_identity=rec['identity'],
            attempts=[x['claim']['attempt_id'] for x in report['attempts_log']])
        self.queue.settle(active['id'],result)
        return dict(status='LOGICAL_SETTLED',measurement_status=status,attempts=report['attempts'])
