"""Read-only verification of saved real-data diagnostic artifacts; CPU only."""
import importlib.util
import json
from collections import Counter
from pathlib import Path

import torch

from metacom_pm.rl1.calibration_workflow import verify_identity
from metacom_pm.rl1.natural_batch import parameter_identity
from metacom_pm.rl1.observation_features import make_actor_critic
from metacom_pm.rl1.reusable_latency import estimate
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import file_sha

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT / 'outputs/pm_rl1'
OUT = BASE / 'exact_equivalence_control_20261104_v1'
SOURCE = OUT.with_name(OUT.name + '_inputs')
JUDGE = BASE / 'relative_feedback_pilot_20261104_v1'


def read(path):
    return json.loads(path.read_text())


def verify():
    torch.set_num_threads(1)
    protocol = read(OUT / 'DIAGNOSTIC_PROTOCOL.json')
    started = read(OUT / 'LEARNING_STARTED.json')
    result = read(OUT / 'RESULTS.json')
    model = read(OUT / 'COST_MODEL.json')
    costs = read(OUT / 'COSTS_PRIVATE.json')
    states = read(OUT / 'STATES_PRIVATE.json')
    endpoints = read(SOURCE / 'ENDPOINTS_PRIVATE.json')
    proof = read(SOURCE / 'EQUALITY_PROOF_PRIVATE.json')
    original = {r['endpoint_identity']: r for r in read(BASE / 'actual_training_feedback_20261103_v1/ENDPOINTS_PRIVATE.json')}
    inputs = read(BASE / 'actual_training_feedback_20261103_v1/INPUTS_PRIVATE.json')
    responses = read(BASE / 'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    encoded = read(BASE / 'organized_initial_encoding_20261103_v2/FEATURES_PRIVATE.json')
    for artifact in (protocol, model):
        verify_identity(artifact)
    for path, sha in started['code'].items():
        assert file_sha(Path(path)) == sha
    assert file_sha(PROJECT / 'scripts/rl1/160_run_exact_equivalence_control.py') == protocol['control_script_sha256']
    assert started['protocol'] == protocol['identity']
    assert started['states'] == digest(states) and started['costs'] == digest(costs)
    assert started['feedback'] == digest(proof) and protocol['endpoints_identity'] == digest(endpoints)
    by_program = {(e['prefix_identity'], tuple(e['actions'])): e for e in endpoints}
    margins = []
    sensitivity = {}
    for e in endpoints:
        p = proof[e['identity']]
        assert p == original[e['identity']] and p['ON'] == p['OFF']
        item = inputs[p['ON']]
        assert digest(dict(evidence=item['evidence'], reply=item['reply'])) == p['ON']
        for role in ('ON', 'OFF'):
            req = e['requests'][role]
            r = responses[req['request_id']]
            assert req['request_id'] in item['request_ids'] and r['text'] == item['reply']
            assert r['finish_reason'] == 'natural_stop' and r['source_provenance_identity'] == digest(req['provenance'])
        assert estimate(model, responses[e['requests']['ON']['request_id']], e['actions'],
                        deployment_identity=model['deployment_identity']) == costs[e['identity']]
        for i in range(len(e['actions'])):
            assert (e['prefix_identity'], tuple(e['actions'][:i] + [0])) in by_program
        if e['actions'] != [0]:
            off = costs[by_program[e['prefix_identity'], (0,)]['identity']]
            c = costs[e['identity']]
            margins.append(c['seconds'] - off['seconds'])
            for scale in (.5, 1., 1.5):
                margin = c['generator_seconds'] - off['generator_seconds'] + scale * (c['overhead_seconds'] - off['overhead_seconds'])
                sensitivity.setdefault(str(scale), []).append(margin)
    for node in states.values():
        raw = encoded[node['observation_identity']]
        assert node['features'] == raw['features'] and node['NoText_features'] == raw['NoText_features']
        assert node['public_mask'] == raw['mask'] and node['prefix'] == raw['prefix_identity']
        h = node['history']
        choices = {e['actions'][len(h)] for e in endpoints if e['prefix_identity'] == node['prefix'] and e['actions'][:len(h)] == h}
        assert node['experiment_mask'] == [bool(raw['mask'][a] and a in choices) for a in range(5)]
        assert node['experiment_mask'][0]
    summaries = []
    for run in result['runs']:
        path = OUT / f'diagnostic_FullText_{run["seed"]}.pt'
        assert file_sha(path) == run['checkpoint_sha256']
        cp = torch.load(path, map_location='cpu', weights_only=True)
        assert cp['scope'] == protocol['scope'] and cp['version'] == 8
        assert cp['protocol_identity'] == protocol['identity'] and cp['feedback_identity'] == digest(proof)
        assert cp['cost_model_identity'] == model['identity']
        actor = make_actor_critic(5139)
        actor.load_state_dict(cp['model'])
        assert parameter_identity(actor) == run['after'] != run['before']
        for row in run['PPO']:
            node = states[digest(dict(prefix=row['prefix'], history=[]))]
            with torch.no_grad():
                dist, _ = actor(torch.tensor(node['features']), torch.tensor(node['experiment_mask']))
            assert int(dist.probs.argmax()) == row['actions'][0] == 0
            assert abs(float(dist.probs[0]) - row['stop_probability']) < 1e-6
        assert len(run['updates']) == 8 and max(u['behavior_log_probability_max_error'] for u in run['updates']) == 0.
        summaries.append(dict(seed=run['seed'], **{phase: {
            k: sum(r[k] for r in run[phase]) / len(run[phase])
            for k in ('expected_return', 'expected_GETs', 'stop_probability')}
            for phase in ('BC', 'PPO')}))
    judge_protocol = read(JUDGE / 'PROTOCOL.json')
    for path, sha in judge_protocol['sources'].items():
        actual = JUDGE / 'EXECUTED_RUNNER.py' if path.endswith('/158_try_relative_feedback.py') else Path(path)
        assert file_sha(actual) == sha
    pairs = read(JUDGE / 'PAIRS_PRIVATE.json')
    requests = read(JUDGE / 'REQUESTS_PRIVATE.json')
    assert digest(pairs) == judge_protocol['pairs_identity'] and digest(requests) == judge_protocol['requests_identity']
    assert digest(read(JUDGE / 'EXPECTATIONS_PRIVATE.json')) == judge_protocol['expectations_identity']
    raw = [read(p) for p in (JUDGE / 'responses').glob('*.json')]
    requested = {q['identity']: q for q in requests}
    assert len(raw) == 16 and all(requested[r['request_identity']]['group'] == 'reference' for r in raw)
    normalized = read(BASE / 'bounded_relative_learning_20261104_v1/NORMALIZED_FEEDBACK.json')
    for path, sha in normalized['source_responses'].items():
        assert file_sha(Path(path)) == sha
    assert normalized['status'] == 'REFERENCE_SCREEN_NOT_PASSED'
    assert read(BASE / 'bounded_relative_learning_20261104_v1/RESULTS.json')['real_data_PPO_updates'] == 0
    spec = importlib.util.spec_from_file_location('closeout', PROJECT / 'scripts/rl1/158_try_relative_feedback.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    old = file_sha(JUDGE / 'ANALYSIS.json')
    assert module.analyze(JUDGE) == module.analyze(JUDGE) and file_sha(JUDGE / 'ANALYSIS.json') == old
    ledger = PROJECT / 'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    assert file_sha(ledger) == 'e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417'
    return dict(status='VERIFIED', scope=protocol['scope'], prefixes=len(result['coverage']['complete_prefixes']),
        endpoints=len(endpoints), public_states=len(states), checkpoints=len(summaries),
        PPO_updates=result['real_data_PPO_updates'], sampled_episodes=3 * protocol['episodes_per_seed'],
        runs=summaries, judge_attempts=len(raw), judge_finish_counts=dict(Counter(r['finish_reason'] for r in raw)),
        reference_counts=normalized['counts'], generator_validation=model['generator_validation'],
        extra_read_delay_range_seconds=[min(margins), max(margins)],
        overhead_sensitivity_min_extra_delay={k: min(v) for k, v in sensitivity.items()},
        adverse_independent_p90_errors_remove_positive_margin=sum(m <= 2 * model['generator_validation']['p90_absolute_error'] for m in margins),
        sensitivity_note='Posthoc cost analysis, no retraining. Marginal timing uncertainty is not a confidence interval.',
        API_cost_usd=0, ledger_unchanged=True)


if __name__ == '__main__':
    print(json.dumps(verify(), ensure_ascii=False, indent=2))
