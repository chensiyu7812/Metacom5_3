"""One episode coordinator interface; providers may be offline test doubles.

The policy receives Observation only. This module does not import a model or
optimizer. A measured terminal value is not authorization to start PPO.
"""
from dataclasses import asdict
from .bound_generation import BoundResourceEnv
from .calibration_workflow import require_freeze, verify_identity, stamp
from .schema import Observation, Score, digest


def run_episode(spec, renderer, *, policy, generate, measure, evidence,
                freeze, freeze_inputs, qualification, trajectory_id):
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
    if not isinstance(trajectory_id, str) or not trajectory_id:
        raise ValueError('new rollout trajectory identity required even with cached feedback')
    env = BoundResourceEnv(spec, renderer)
    steps = []
    while env.phase == 'acquiring':
        observation = env.observe()
        assert isinstance(observation, Observation)
        action = policy(observation)
        result = env.step(action, expected_state_hash=env.state_hash)
        steps.append(dict(observation_identity=digest(asdict(observation)), action=int(action),
                          reward=result.reward))
    request = env.generation_request()
    on = generate(request)
    env.accept_generation(request_id=on['request_id'], text=on['text'],
        finish_reason=on['finish_reason'], runtime_identity=on['runtime_identity'])
    terminal = None
    score_receipts = []
    if env.phase == 'pending_score':
        off_env = BoundResourceEnv(spec, renderer)
        off_env.step(0, expected_state_hash=off_env.state_hash)
        off_request = off_env.generation_request()
        off = on if request == off_request else generate(off_request)
        off_env.accept_generation(request_id=off['request_id'], text=off['text'],
            finish_reason=off['finish_reason'], runtime_identity=off['runtime_identity'])
        if off_env.phase != 'pending_score':
            env.fail('incomplete_OFF_generation:' + off['finish_reason'])
        else:
            def score_response(req, response):
                # Coordinator-only provenance, never forwarded to the policy.
                query = dict(generation_request_id=req['request_id'], response_identity=digest(response['text']),
                    evidence_identity=digest(evidence), runtime_identity=freeze['runtime_identity'],
                    rubric_identity=freeze['rubric_identity'], freeze_identity=freeze['identity'])
                rec = measure(query, evidence, response['text'])
                if rec.get('binding') != query:
                    raise ValueError('measurement bound to wrong response/evidence/runtime')
                score_receipts.append(rec)
                if rec['measurement_status'] != 'measured_candidate':
                    if rec.get('q') is not None or rec.get('m') is not None:
                        raise ValueError('unmeasured response cannot carry a reward')
                    return None
                return Score(rec['q'], rec['m'], (digest(rec),))
            on_score = score_response(request, on)
            off_score = on_score if request == off_request else score_response(off_request, off)
            if on_score is not None and off_score is not None:
                terminal = env.accept_scores(on=on_score, off=off_score, judge_identity=spec.judge_identity,
                    on_response_sha256=digest(on['text']), off_request_id=off_request['request_id'],
                    off_response=off['text'], off_finish_reason=off['finish_reason'],
                    off_runtime_identity=off['runtime_identity']).reward
                steps[-1]['reward'] = terminal
            elif any(s['measurement_status'] == 'technical_failure' for s in score_receipts):
                env.fail('technical_measurement_failure')
    return stamp(dict(trajectory_id=trajectory_id, episode_identity=spec.identity,
        renderer_identity=renderer.identity, freeze_identity=freeze['identity'],
        qualification_identity=qualification['identity'], steps=steps,
        terminal_reward=terminal,
        return_value=sum(s['reward'] for s in steps) if terminal is not None else None,
        phase=env.phase, measurement_receipts=score_receipts, private_audit_snapshot=env.snapshot(),
        automatic_training_authorization=False))
