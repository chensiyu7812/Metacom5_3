"""New-domain ON/OFF episodes using the existing content-level feedback queue.

No providers, optimizer, weight loader, or implicit measurement qualification.
Source-addressed terminal identity replaces the old four-count terminal key:
with read-dependent retrieval, equal head counts need not mean equal content.
"""
from copy import deepcopy
from dataclasses import asdict, dataclass
import math

from .calibration_workflow import qualify, stamp, verify_identity
from .evidence import evidence_turns
from .measurement_identity import binding
from .organized_policy_interface import HeadSession
from .schema import Action, Score, digest

VERSION = 'pmrl1-organized-feedback-bridge-v1'
TERMINAL_FIELDS = ('version','prefix_identity','catalog_identity','renderer_identity',
    'interface_identity','retrieval_method','executor_identity','draw_identity','messages',
    'selected_resource_identities','selected_keys','usage')


@dataclass(frozen=True)
class TokenCost:
    # Explicit caller choice; no default and no hard acquisition cap.
    weight: float
    unit_tokens: int

    def __post_init__(self):
        if (type(self.weight) not in (int,float) or not math.isfinite(self.weight) or self.weight < 0
                or type(self.unit_tokens) is not int or self.unit_tokens < 1):
            raise ValueError('finite nonnegative per-token price required')

    @property
    def identity(self):
        return digest(dict(version=VERSION, cost=asdict(self), hard_cap=None, saturation=None))

    def delta(self, tokens):
        if type(tokens) is not int:
            raise ValueError('actual renderer token difference required')
        return -self.weight*tokens/self.unit_tokens


def generation_request(terminal):
    if terminal['identity'] != digest({k:terminal[k] for k in TERMINAL_FIELDS}):
        raise ValueError('source terminal changed')
    if (len(terminal['selected_keys']) != len(set(terminal['selected_keys']))
            or len(terminal['selected_keys']) != len(terminal['selected_resource_identities'])
            or terminal['usage']['truncation'] or not terminal['usage']['within_native_context']):
        raise ValueError('whole source-addressed terminal required')
    body = dict(version=VERSION, executor_identity=terminal['executor_identity'],
        renderer_identity=terminal['renderer_identity'], draw_identity=terminal['draw_identity'],
        messages=deepcopy(terminal['messages']), expected_input_tokens=terminal['usage']['input_tokens'],
        provenance={k:deepcopy(terminal[k]) for k in ('prefix_identity','catalog_identity',
            'interface_identity','retrieval_method','selected_resource_identities','selected_keys','usage')})
    return dict(body, request_id=digest(body))


def visible_generation_request(request):
    if (request.get('version') != VERSION or request.get('request_id') !=
            digest({k:v for k,v in request.items() if k != 'request_id'})):
        raise ValueError('organized generation request identity changed')
    body = {k:deepcopy(request[k]) for k in ('messages','executor_identity','draw_identity','renderer_identity')}
    return dict(body, request_id=digest(body))


def execute_generation(generator, request):
    """Projection onto unchanged original G; caller owns permission/claim/budget."""
    from .generation import LocalNaturalGenerator
    visible = visible_generation_request(request)
    raw = LocalNaturalGenerator.generate(generator, visible)
    return bind_generation_result(request, raw)


def bind_generation_result(request, raw):
    visible = visible_generation_request(request)
    if (raw.get('request_id') != visible['request_id']
            or raw.get('runtime_identity') != request['executor_identity']
            or raw.get('input_tokens') != request['expected_input_tokens']
            or raw.get('api_cost_usd') != 0):
        raise ValueError('actual G response/runtime/input length changed')
    return dict(raw, request_id=request['request_id'], visible_request_id=visible['request_id'],
                source_provenance_identity=digest(request['provenance']), raw_identity=digest(raw))


def domain_identity(catalog, renderer, executor_identity):
    # Per-prefix contents have their own provenance. Qualification coverage is
    # about compiler/retriever/presentation/executor versions, not each example.
    s = HeadSession(catalog,renderer)
    return digest(dict(interface=s.interface_identity,renderer=renderer.identity,executor=executor_identity))


class QualifiedRoute:
    """Recompute existing J qualification; explicitly bind its new-domain use.

    The use record is a researcher-reviewed compatibility decision, not a new
    universal accuracy threshold. It may cite reusable evidence plus a minimal
    supplement, but cannot manufacture a qualified receipt from dev scores.
    """
    def __init__(self, bundle, use_record):
        q = qualify(**bundle); verify_identity(use_record)
        if (q['status'] not in ('CALIBRATED_FOR_BOUNDED_STUDY','CALIBRATED_LOW_CONTRAST')
                or bundle['inputs']['contract']['measurement']['reward']['alpha'] != 1
                or use_record.get('status') != 'QUALIFIED_MEASUREMENT_USE'
                or use_record.get('qualification_identity') != q['identity']
                or not use_record.get('domain_identity') or not use_record.get('review_reference')
                or not use_record.get('coverage_evidence_identities')):
            raise ValueError('qualified J and explicit version coverage required')
        self.bundle, self.qualification, self.use_record = deepcopy((bundle,q,use_record))
        self.identity = digest(dict(qualification=q['identity'],use=use_record['identity']))

    def check(self, domain):
        verify_identity(self.use_record)
        if qualify(**self.bundle) != self.qualification or self.use_record['domain_identity'] != domain:
            raise ValueError('measurement qualification or covered resource/G domain changed')


class OrganizedEpisode:
    def __init__(self, catalog, renderer, *, executor_identity, draw_identity,
                 trajectory_id, evidence, evidence_source, cost, route=None, without_text=False):
        if type(cost) is not TokenCost or not trajectory_id or not executor_identity or not draw_identity:
            raise ValueError('explicit trajectory/executor/draw/cost required')
        expected = dict(prefix_identity=catalog.prefix.identity,evidence_identity=digest(evidence))
        if (evidence_source.get('prefix_identity') != expected['prefix_identity']
                or evidence_source.get('evidence_identity') != expected['evidence_identity']
                or not evidence_source.get('source_identity')):
            raise ValueError('bound complete legal scoring evidence required')
        evidence_turns(evidence)
        if ([(t['role'],t['text']) for t in evidence['current_prefix']] !=
                [(t.role,t.content) for t in catalog.prefix.turns]
                or evidence['current_date'] != catalog.prefix.timestamp):
            raise ValueError('scoring evidence belongs to another prefix/cut')
        self.catalog, self.renderer = catalog, renderer
        self.session = HeadSession(catalog,renderer,without_text=without_text)
        self.executor_identity, self.draw_identity, self.trajectory_id = executor_identity, draw_identity, trajectory_id
        self.evidence, self.evidence_source = deepcopy((evidence,evidence_source))
        self.domain = domain_identity(catalog,renderer,executor_identity)
        if route is not None: route.check(self.domain)
        self.route, self.cost = route,cost
        self.steps=[]; self.requests={}; self.responses={}; self.receipts={}
        self.phase='acquiring'; self.terminal_reward=None
        self.binding=digest(dict(version=VERSION,domain=self.domain,catalog=catalog.identity,
            trajectory=trajectory_id,draw=draw_identity,evidence_source=evidence_source,
            cost=cost.identity,route=route.identity if route else None,without_text=without_text))

    def step(self, action):
        if self.phase != 'acquiring': raise ValueError('trajectory already acquired')
        before=self.session.observe()
        after=self.session.step(action,expected_observation=digest(asdict(before)))
        self.steps.append(dict(action=int(action),observation_identity=digest(asdict(before)),
            reward=None if action == Action.STOP else self.cost.delta(after.resource_tokens-before.resource_tokens)))
        if after.stopped:
            on=self.session.terminal(executor_identity=self.executor_identity,draw_identity=self.draw_identity)
            off=HeadSession(self.catalog,self.renderer);off.step(Action.STOP)
            off=off.terminal(executor_identity=self.executor_identity,draw_identity=self.draw_identity)
            self.requests={role:generation_request(t) for role,t in (('ON',on),('OFF',off))}
            self.phase='pending_generation'
        return after

    def acquire(self, policy):
        while self.phase == 'acquiring': self.step(policy(self.session.observe()))
        return self.result()

    def _generation(self, request, generate):
        key=request['request_id']
        if key not in self.responses:
            raw=generate(request)
            if raw is None:return None
            if (raw.get('request_id') != key or raw.get('runtime_identity') != self.executor_identity
                    or raw.get('source_provenance_identity') != digest(request['provenance'])
                    or raw.get('input_tokens') != request['expected_input_tokens']):
                raise ValueError('G response is not bound to the exact acquired sources')
            if raw.get('finish_reason') != 'natural_stop':
                self.phase='technical_failure';return None
            if not isinstance(raw.get('text'),str) or not raw['text'].strip():
                raise ValueError('empty natural reply')
            self.responses[key]=deepcopy(raw)
        return self.responses[key]

    def advance(self, generate, measure):
        if self.phase == 'acquiring':raise ValueError('acquire before queueing G')
        if self.phase in ('terminal','technical_failure'):return self.result()
        # Queue both independent ON/OFF requests even if one is still pending.
        rs={}
        for role,req in self.requests.items():
            rs[role]=self._generation(req,generate)
            if self.phase == 'technical_failure':return self.result()
        if any(r is None for r in rs.values()):return self.result()
        if self.route is None:
            self.phase='pending_qualification';return self.result()
        self.route.check(self.domain); self.phase='pending_score'
        scores={}
        for role,req in self.requests.items():
            q=binding(req['request_id'],digest(rs[role]['text']),digest(self.evidence),
                      self.route.bundle['freeze'],self.route.qualification)
            rec=measure(q,self.evidence,rs[role]['text'])
            if rec is None:continue
            if rec.get('binding') != q:raise ValueError('measurement input identity changed')
            self.receipts[req['request_id']]=deepcopy(rec)
            if rec['measurement_status'] != 'measured_candidate':
                if rec.get('q') is not None or rec.get('m') is not None:
                    raise ValueError('unknown/failed measurement carries numeric reward')
                if rec['measurement_status'] == 'technical_failure':self.phase='technical_failure'
                continue
            scores[role]=Score(rec['q'],rec['m'],(digest(rec),))
        if len(scores)==2 and self.phase != 'technical_failure':
            self.terminal_reward=scores['ON'].utility(1)-scores['OFF'].utility(1)
            self.steps[-1]['reward']=self.terminal_reward;self.phase='terminal'
        return self.result()

    def result(self):
        return stamp(dict(trajectory_id=self.trajectory_id,binding=self.binding,phase=self.phase,
            steps=deepcopy(self.steps),terminal_reward=self.terminal_reward,
            return_value=sum(s['reward'] for s in self.steps) if self.phase=='terminal' else None,
            measurement_qualified=self.route is not None,automatic_training_authorization=False))

    def snapshot(self):
        return stamp(dict(binding=self.binding,phase=self.phase,steps=deepcopy(self.steps),
            requests=deepcopy(self.requests),responses=deepcopy(self.responses),
            receipts=deepcopy(self.receipts),terminal_reward=self.terminal_reward))

    def restore(self, saved):
        verify_identity(saved)
        if saved['binding'] != self.binding or self.steps:raise ValueError('fresh matching episode required')
        for step in saved['steps']:
            self.step(step['action'])
            if self.steps[-1]['observation_identity'] != step['observation_identity']:
                raise ValueError('restored source/observation changed')
            if step['action'] != Action.STOP and self.steps[-1]['reward'] != step['reward']:
                raise ValueError('restored token cost changed')
        if digest(self.requests) != digest(saved['requests']):raise ValueError('restored G requests changed')
        self.phase,self.steps,self.responses,self.receipts,self.terminal_reward=deepcopy(
            (saved['phase'],saved['steps'],saved['responses'],saved['receipts'],saved['terminal_reward']))
        if digest(self.snapshot()) != digest(saved):raise ValueError('episode snapshot mismatch')

    def feedback_export(self):
        if self.phase != 'terminal':raise ValueError('complete qualified ON/OFF required')
        # An ordered acquisition program is required for BC replay. Counts alone
        # are insufficient with content-adaptive retrieval.
        actions=[s['action'] for s in self.steps]
        return [dict(trajectory_id=self.trajectory_id,role=role,split=self.catalog.prefix.split,
            actions=actions if role=='ON' else [0],request=deepcopy(req),
            response=deepcopy(self.responses[req['request_id']]),
            receipt=deepcopy(self.receipts[req['request_id']]),cost_identity=self.cost.identity,
            measurement_use_identity=self.route.use_record['identity']) for role,req in self.requests.items()]
