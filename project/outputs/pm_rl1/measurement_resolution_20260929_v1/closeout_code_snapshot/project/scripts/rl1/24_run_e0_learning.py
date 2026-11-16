#!/usr/bin/env python3
"""Predeclared CPU-only toy PPO diagnostic, no semantic rewards or model calls."""
import json
from pathlib import Path
import random
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.e0_learning import CASES, ToyActorCritic, PPO, rollout, evaluate
import torch

OUT = PROJECT / 'outputs/pm_rl1/measurement_resolution_20260929_v1/e0'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def main():
    torch.set_num_threads(1)
    contract = dict(protocol='rl1-e0-ppo-learning-v1', cases=list(CASES), seeds=[17, 29, 43],
        episodes_per_seed=4096, episodes_per_batch=16, epochs=4, episodes_per_minibatch=4,
        gamma=1, gae_lambda=1, learning_rate=3e-4, clip=.2, value_coefficient=.5,
        entropy_coefficient=.01, gradient_clip=.5, device='cpu', threads=1,
        public_toy_features='five task-category flags, canonical acquired counts, budget and step fractions',
        production_encoder=False, semantic_training=False, real_PM_checkpoint=False,
        endpoint_rule='fixed 4096; report all cases/seeds, no outcome-dependent extension or checkpoint selection',
        validation_target='greedy endpoint matches exact DP on all five finite toy cases for each seed',
        module_sha256=sha256_file(PROJECT / 'src/metacom_pm/rl1/e0_learning.py'),
        runner_sha256=sha256_file(Path(__file__)), torch_version=torch.__version__, API_usd=0)
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT/'contract.json').exists():
        raise RuntimeError('already executed or unresolved prior attempt; preserve it')
    save(OUT/'contract.json', contract)
    results = []; started = time.monotonic()
    for seed in contract['seeds']:
        torch.manual_seed(seed); rng = random.Random(seed)
        model = ToyActorCritic(); trainer = PPO(model)
        initial = {k: v.clone() for k, v in model.state_dict().items()}
        curve = [dict(episodes=0, evaluation=evaluate(model, 0))]
        losses = []
        for count in range(16, 4097, 16):
            batch = [rollout(model, rng.randrange(5), trainer.version) for _ in range(16)]
            stats = trainer.update(batch)
            losses.append(stats)
            if count in (256, 512, 1024, 2048, 4096):
                curve.append(dict(episodes=count, evaluation=evaluate(model, trainer.version)))
                print(json.dumps(dict(seed=seed, episodes=count, evaluation=curve[-1]['evaluation'])), flush=True)
        checkpoint = OUT / f'seed_{seed}.pt'
        trainer.save(checkpoint, rng, 4096)
        endpoint = curve[-1]['evaluation']
        row = dict(seed=seed, episodes=4096, ppo_batches=trainer.version, curves=curve,
                   endpoint_all_cases_optimal=all(abs(r['greedy_return'] - r['oracle_return']) < 1e-6 for r in endpoint),
                   parameters_changed=any(not torch.equal(initial[k], v) for k, v in model.state_dict().items()),
                   maximum_behavior_log_error=max(x['behavior_log_probability_max_error'] for x in losses),
                   checkpoint_sha256=sha256_file(checkpoint))
        results.append(row); save(OUT/f'seed_{seed}.json', row)
        save(OUT/'summary.json', dict(completed_seeds=len(results), results=results,
              elapsed_seconds=time.monotonic()-started, real_semantic_PM_training_updates=0,
              LLM_calls=0, API_usd=0, toy_only=True,
              all_endpoints_optimal=all(r['endpoint_all_cases_optimal'] for r in results)))


if __name__ == '__main__':
    main()
