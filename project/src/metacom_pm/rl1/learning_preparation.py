"""Provider-free BC/OneShot/NoText interfaces for the existing completion plan.

This module compiles observations and labels; it cannot load a model, run an
optimizer, qualify a scorer, or authorize an experiment. Labels remain separate
from public policy inputs. Unmeasured terminal plans are never negative labels.
"""
from dataclasses import dataclass

from .schema import Observation, PLANS, digest


@dataclass(frozen=True)
class TerminalCandidate:
    prefix_identity: str
    split: str
    counts: tuple[int, int, int, int]
    resource_tokens: int
    request_identity: str
    response_identity: str
    evidence_identity: str
    executor_identity: str
    renderer_identity: str


def adapt_qualified_episode_feedback(candidate, record, *, spec, freeze, freeze_inputs, qualification):
    """Normalize the existing NaturalEpisode receipt after its original guards.

    This is a coordinator-side adapter. It does not turn an API diagnostic
    score, a hand-written calibration flag, or an engineering result into a
    qualified natural reward.
    """
    from .natural_runner import require_qualified_episode
    require_qualified_episode(spec, freeze, freeze_inputs, qualification)
    if (candidate.prefix_identity != spec.prefix.identity or candidate.split != spec.prefix.split
            or candidate.executor_identity != spec.executor_identity):
        raise ValueError('candidate belongs to another episode')
    from .measurement_identity import binding
    expected = binding(candidate.request_identity, candidate.response_identity,
                       candidate.evidence_identity, freeze, qualification)
    if record.get('binding') != expected:
        raise ValueError('natural feedback binding mismatch')
    measured = record.get('measurement_status') == 'measured_candidate'
    if not measured and (record.get('q') is not None or record.get('m') is not None):
        raise ValueError('missing feedback must remain null')
    normalized = dict(status=qualification['status'], measurement_identity=freeze['runtime_identity'],
        source_qualification_identity=qualification['identity'], freeze_identity=freeze['identity'])
    normalized['identity'] = digest(normalized)
    score = dict(status='measured' if measured else 'pending', uncertain=not measured,
        request_identity=candidate.request_identity, response_identity=candidate.response_identity,
        evidence_identity=candidate.evidence_identity, measurement_identity=freeze['runtime_identity'],
        qualification_identity=normalized['identity'], source_receipt_identity=digest(record),
        q=record.get('q') if measured else None, misuse=record.get('m') if measured else None)
    return normalized, score


def legal_path(env_factory, counts):
    """First legal path in fixed action order, including nonmonotone budgets.

    Called by the offline teacher/compiler, never by the runtime actor. It does
    not select the next action using the text of an unacquired resource.
    """
    counts = tuple(counts)
    if any(type(n) is not int for n in counts) or counts not in PLANS:
        raise ValueError('unknown terminal plan')
    pending = [()]
    visited = set()
    while pending:
        path = pending.pop(0)
        env = env_factory()
        for action in path:
            env.step(action, expected_state_hash=env.state_hash)
        obs = env.observe()
        if obs.counts == counts:
            return path + (0,)
        if obs.counts in visited:
            continue
        visited.add(obs.counts)
        for action in range(1, 5):
            if obs.action_mask[action] and obs.counts[action-1] < counts[action-1]:
                pending.append(path + (action,))
    raise ValueError('terminal plan is not sequentially reachable')


def compile_demonstration(env_factory, counts):
    """Only Observation/action reach the learner; teacher provenance is external."""
    path = legal_path(env_factory, counts)
    env = env_factory()
    transitions = []
    for action in path:
        obs = env.observe()
        transitions.append((obs, action))
        env.step(action, expected_state_hash=env.state_hash)
    return tuple(transitions)


def select_bc_target(candidates, measurements, *, qualification, resource_budget=2048):
    """Choose only after all scheduled candidates have qualified bound feedback.

    `qualification` is an externally verified receipt. This function checks its
    content binding; validating its provenance remains the launcher's duty.
    """
    if resource_budget != 2048:
        raise ValueError('the active plan fixes the resource budget at 2048')
    if not candidates or len({c.prefix_identity for c in candidates}) != 1:
        raise ValueError('one nonempty prefix candidate group required')
    if any(c.split != 'train' or c.counts not in PLANS or any(type(n) is not int for n in c.counts) or
           type(c.resource_tokens) is not int or not 0 <= c.resource_tokens <= resource_budget
           for c in candidates):
        raise ValueError('BC targets require valid train plans')
    if len({c.counts for c in candidates}) != len(candidates):
        raise ValueError('duplicate scheduled terminal plan')
    if len({(c.executor_identity, c.renderer_identity, c.evidence_identity) for c in candidates}) != 1:
        raise ValueError('candidate executor/renderer/evidence identities differ')
    off = next((c for c in candidates if c.counts == (0, 0, 0, 0)), None)
    if off is None or off.resource_tokens != 0:
        raise ValueError('bound true OFF candidate required')
    allowed = {'CALIBRATED_FOR_BOUNDED_STUDY', 'CALIBRATED_LOW_CONTRAST'}
    if not qualification or qualification.get('status') not in allowed:
        return dict(status='PENDING_QUALIFIED_FEEDBACK', target=None)
    identity = qualification.get('identity')
    if not identity or identity != digest({k: v for k, v in qualification.items() if k != 'identity'}):
        raise ValueError('qualification receipt identity mismatch')
    if not qualification.get('measurement_identity'):
        raise ValueError('qualification must bind a measurement identity')
    values = {}
    identical_inputs = {}
    missing = []
    for c in candidates:
        m = measurements.get(c.request_identity)
        if not m or m.get('status') != 'measured' or m.get('uncertain') is not False:
            missing.append(c.request_identity)
            continue
        if any(m.get(k) != v for k, v in {
            'request_identity': c.request_identity, 'response_identity': c.response_identity,
            'evidence_identity': c.evidence_identity,
            'measurement_identity': qualification['measurement_identity'],
            'qualification_identity': identity,
        }.items()):
            raise ValueError('measurement binding mismatch')
        q, misuse = m.get('q'), m.get('misuse')
        if type(q) is not int or q not in range(5) or type(misuse) not in (int, float) or misuse not in (0, .25, 1):
            raise ValueError('invalid frozen q/m value')
        values[c.request_identity] = q / 4 - misuse
        input_key = (c.evidence_identity, c.response_identity)
        if input_key in identical_inputs and identical_inputs[input_key] != (q, misuse):
            raise ValueError('identical scorer input has inconsistent labels')
        identical_inputs[input_key] = (q, misuse)
    if missing:
        return dict(status='PENDING_SCHEDULED_FEEDBACK', target=None, missing=missing)
    base = values[off.request_identity]
    rewards = {c.request_identity: values[c.request_identity] - base - .05*c.resource_tokens/resource_budget
               for c in candidates}
    best = min(candidates, key=lambda c: (-rewards[c.request_identity], c.resource_tokens, c.counts))
    return dict(status='COMPILED_MEASURED_CANDIDATE_TARGET', target=best.counts,
                request_identity=best.request_identity, reward=rewards[best.request_identity],
                measured_plans=len(candidates), unmeasured_plans_are_negative=False,
                qualification_identity=identity)


class PolicyInputView:
    """One shared public encoder, with a stable NoText ablation at every phase."""
    def __init__(self, encoder, *, no_text=False):
        self.encoder = encoder
        self.no_text = no_text
        self.identity = digest(dict(encoder=encoder.identity, no_text=no_text,
                                    version='pmrl1-policy-input-view-v1'))

    def sequential(self, observation):
        record = self.encoder.encode(observation)
        values = list(record.values)
        if self.no_text:
            d = self.encoder.dimension
            values[d:5*d] = [0.] * (4*d)
        return tuple(values), record.action_mask

    def oneshot(self, observation):
        if type(observation) is not Observation or observation.counts != (0, 0, 0, 0) or observation.acquired:
            raise ValueError('OneShot only receives the initial public observation')
        values, _ = self.sequential(observation)
        if len(observation.initial_plan_mask) != 70:
            raise ValueError('shared 70-plan feasibility mask required')
        return values, observation.initial_plan_mask


def make_oneshot_policy(feature_dimension):
    """Untrained architecture only; same backbone width and 70 reachable plans."""
    import torch
    from torch import nn
    from torch.distributions import Categorical

    class OneShot(nn.Module):
        def __init__(self):
            super().__init__()
            self.body = nn.Sequential(nn.Linear(feature_dimension, 128), nn.Tanh(),
                nn.Linear(128, 128), nn.Tanh(), nn.Linear(128, 128), nn.Tanh())
            self.policy = nn.Linear(128, len(PLANS))

        def forward(self, features, plan_masks):
            if features.shape[-1] != feature_dimension or plan_masks.shape[-1] != len(PLANS) or not plan_masks.any(dim=-1).all():
                raise ValueError('invalid OneShot feature/mask')
            return Categorical(logits=self.policy(self.body(features)).masked_fill(~plan_masks, -torch.inf))

    return OneShot()


def initialization_manifest(*, method, seed, feature_identity, target_manifest_identity=None):
    if method not in ('BC-init', 'BC-union', 'OneShot', 'PPO-NoText') or seed not in (17, 29, 43):
        raise ValueError('method or seed outside the current plan')
    if not feature_identity:
        raise ValueError('explicit feature identity required')
    return dict(status='INITIALIZATION_PLAN_ONLY', method=method, seed=seed,
        feature_identity=feature_identity, target_manifest_identity=target_manifest_identity,
        optimizer=dict(name='Adam', lr=3e-4, weight_decay=1e-4, batch_size=64, epochs=50),
        acquired_text_zero_from_initialization=method == 'PPO-NoText',
        checkpoint_exists=False, training_authorized=False,
        checkpoint_required=['model_state', 'optimizer_state', 'feature_identity',
            'target_manifest_identity', 'qualification_identity', 'seed', 'method',
            'executor_identity', 'renderer_identity', 'plan_order_identity'])
