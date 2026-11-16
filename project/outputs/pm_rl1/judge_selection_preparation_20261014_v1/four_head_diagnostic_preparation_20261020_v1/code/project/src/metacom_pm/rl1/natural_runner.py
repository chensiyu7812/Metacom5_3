"""One episode coordinator interface; providers may be offline test doubles.

The policy receives Observation only. This module does not import a model or
optimizer. A measured terminal value is not authorization to start PPO.
"""
from dataclasses import asdict
from copy import deepcopy
from .bound_generation import BoundResourceEnv
from .calibration_workflow import require_freeze, verify_identity, stamp
from .schema import Observation, Score, digest


def require_qualified_episode(spec, freeze, freeze_inputs, qualification):
    require_freeze(freeze, freeze_inputs)
    verify_identity(qualification)
    if (qualification.get('status') not in freeze_inputs['contract']['measurement']['qualified_states']
            or qualification.get('freeze_identity') != freeze['identity']
            or qualification.get('runtime_identity') != freeze['runtime_identity']
            or spec.judge_identity != freeze['runtime_identity']):
        raise ValueError('qualified frozen measurement required')
    reward = freeze_inputs['contract']['measurement']['reward']
    invariants = freeze_inputs['contract']['invariants']
    if (spec.resource_budget != invariants['resource_tokens'] or spec.alpha != reward['alpha']
            or spec.cost_weight != reward['lambda'] or invariants['max_gets'] != 4):
        raise ValueError('episode reward/dynamics differ from execution contract')

class _EpisodeLoop:
    """Shared state machine. Production callers must use NaturalEpisode below.

    Providers return None while a request is outstanding. Re-polling never
    re-samples actions. The queue, not this object, owns dispatch and dedup.
    Private evidence and snapshots stay on the coordinator side.
    """
    def __init__(self, spec, renderer, *, evidence, freeze, qualification, trajectory_id):
        if not isinstance(trajectory_id, str) or not trajectory_id:
            raise ValueError('new rollout trajectory identity required even with cached feedback')
        self.spec, self.renderer = spec, renderer
        self.evidence, self.freeze, self.qualification = deepcopy(evidence), deepcopy(freeze), deepcopy(qualification)
        self.trajectory_id = trajectory_id
        self.env = BoundResourceEnv(spec, renderer)
        self.off_env = BoundResourceEnv(spec, renderer)
        self.off_env.step(0, expected_state_hash=self.off_env.state_hash)
        self.steps, self.score_receipts, self.scores = [], [], {}
        self.terminal = None
        self.binding = digest(dict(spec=spec.identity, renderer=renderer.identity,
            evidence=evidence, freeze=freeze, qualification=qualification, trajectory=trajectory_id))

    def acquire(self, policy):
        while self.env.phase == 'acquiring':
            observation = self.env.observe()
            assert type(observation) is Observation
            action = policy(observation)
            result = self.env.step(action, expected_state_hash=self.env.state_hash)
            self.steps.append(dict(observation_identity=digest(asdict(observation)),
                action=int(action), reward=result.reward))
        return self.result()

    @staticmethod
    def _deliver(env, response):
        env.accept_generation(request_id=response['request_id'], text=response['text'],
            finish_reason=response['finish_reason'], runtime_identity=response['runtime_identity'])

    def _score(self, req, response, measure):
        query = dict(generation_request_id=req['request_id'], response_identity=digest(response['text']),
            evidence_identity=digest(self.evidence), runtime_identity=self.freeze['runtime_identity'],
            rubric_identity=self.freeze['rubric_identity'], freeze_identity=self.freeze['identity'])
        key = digest(query)
        rec = self.scores.get(key)
        if rec is None:
            rec = measure(query, self.evidence, response['text'])
            if rec is None:
                return None
            if rec.get('binding') != query:
                raise ValueError('measurement bound to wrong response/evidence/runtime')
            if not any(digest(old) == digest(rec) for old in self.score_receipts):
                self.score_receipts.append(deepcopy(rec))
            if rec['measurement_status'] != 'measured_candidate':
                if rec.get('q') is not None or rec.get('m') is not None:
                    raise ValueError('unmeasured response cannot carry a reward')
                if rec['measurement_status'] == 'technical_failure':
                    self.env.fail('technical_measurement_failure')
                return None
            self.scores[key] = deepcopy(rec)
        return Score(rec['q'], rec['m'], (digest(rec),))

    def advance(self, generate, measure):
        if self.env.phase in ('terminal', 'technical_failure'):
            return self.result()
        if self.env.phase == 'acquiring':
            raise ValueError('acquire before terminal feedback')
        req = self.env.generation_request()
        if self.env.phase == 'pending_generation':
            on = generate(req)
            if on is None:
                return self.result()
            self._deliver(self.env, on)
        if self.env.phase != 'pending_score':
            return self.result()
        on = self.env.snapshot()['generation']
        off_req = self.off_env.generation_request()
        if self.off_env.phase == 'pending_generation':
            off = on if req == off_req else generate(off_req)
            if off is None:
                return self.result()
            self._deliver(self.off_env, off)
        if self.off_env.phase != 'pending_score':
            self.env.fail('incomplete_OFF_generation')
            return self.result()
        off = self.off_env.snapshot()['generation']
        on_score = self._score(req, on, measure)
        if self.env.phase == 'technical_failure':
            return self.result()
        off_score = on_score if req == off_req else self._score(off_req, off, measure)
        if self.env.phase == 'technical_failure':
            return self.result()
        if on_score is not None and off_score is not None:
            self.terminal = self.env.accept_scores(on=on_score, off=off_score,
                judge_identity=self.spec.judge_identity, on_response_sha256=digest(on['text']),
                off_request_id=off_req['request_id'], off_response=off['text'],
                off_finish_reason=off['finish_reason'], off_runtime_identity=off['runtime_identity']).reward
            self.steps[-1]['reward'] = self.terminal
        return self.result()

    def snapshot(self):
        return stamp(dict(binding=self.binding, env=self.env.snapshot(), off=self.off_env.snapshot(),
            steps=deepcopy(self.steps), receipts=deepcopy(self.score_receipts),
            scores=deepcopy(self.scores), terminal=self.terminal))

    def restore(self, saved):
        verify_identity(saved)
        if saved['binding'] != self.binding:
            raise ValueError('pending episode identity changed')
        self.env = BoundResourceEnv.restore(self.spec, self.renderer, saved['env'])
        self.off_env = BoundResourceEnv.restore(self.spec, self.renderer, saved['off'])
        self.steps, self.score_receipts, self.scores = deepcopy((saved['steps'], saved['receipts'], saved['scores']))
        self.terminal = saved['terminal']
        # List/tuple representation differs between JSON and torch checkpoints;
        # compare the canonical source-bound JSON identity.
        if digest(self.snapshot()) != digest(saved):
            raise ValueError('pending episode restore mismatch')

    def result(self):
        return stamp(dict(trajectory_id=self.trajectory_id, episode_identity=self.spec.identity,
            renderer_identity=self.renderer.identity, freeze_identity=self.freeze['identity'],
            qualification_identity=self.qualification['identity'], steps=deepcopy(self.steps),
            terminal_reward=self.terminal,
            return_value=sum(s['reward'] for s in self.steps) if self.terminal is not None else None,
            phase=self.env.phase, measurement_receipts=deepcopy(self.score_receipts),
            private_audit_snapshot=self.env.snapshot(), automatic_training_authorization=False))


class NaturalEpisode(_EpisodeLoop):
    def __init__(self, spec, renderer, *, evidence, freeze, freeze_inputs, qualification, trajectory_id):
        require_qualified_episode(spec, freeze, freeze_inputs, qualification)
        super().__init__(spec, renderer, evidence=evidence, freeze=freeze,
                         qualification=qualification, trajectory_id=trajectory_id)


def run_episode(spec, renderer, *, policy, generate, measure, evidence,
                freeze, freeze_inputs, qualification, trajectory_id):
    episode = NaturalEpisode(spec, renderer, evidence=evidence, freeze=freeze,
        freeze_inputs=freeze_inputs, qualification=qualification, trajectory_id=trajectory_id)
    episode.acquire(policy)
    return episode.advance(generate, measure)
