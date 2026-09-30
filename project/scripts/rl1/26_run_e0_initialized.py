#!/usr/bin/env python3
"""Test the planned finite-support BC -> PPO route on fully known toy feedback.

The separate from-scratch diagnostic is preserved. Oracle labels are teacher-only
and come from a fully observed toy table, never invented for unmeasured real plans.
"""
import json
from pathlib import Path
import random
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.e0_learning import ToyState, ToyActorCritic, PPO, rollout, evaluate, exact_value
import torch

OUT = PROJECT/'outputs/pm_rl1/measurement_resolution_20260929_v1/e0_initialized'


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(value,indent=2)+'\n'); tmp.replace(path)


def support():
    seen=set(); pending=[ToyState(i) for i in range(5)]
    while pending:
        state=pending.pop()
        if state in seen:continue
        seen.add(state)
        for a,legal in enumerate(state.mask()):
            if legal and a:
                pending.append(state.step(a)[0])
    states=sorted(seen,key=lambda s:(s.case,s.counts))
    labels=[]
    for state in states:
        action_values=[]
        for a,legal in enumerate(state.mask()):
            if not legal:action_values.append(float('-inf'));continue
            nxt,r,done=state.step(a)
            action_values.append(r+(0 if done else exact_value(nxt)))
        best=max(action_values)
        optimal=torch.tensor([abs(v-best)<1e-8 for v in action_values],dtype=torch.float32)
        labels.append(optimal/optimal.sum())
    return states,torch.stack(labels)


def main():
    torch.set_num_threads(1)
    if (OUT/'contract.json').exists():raise RuntimeError('existing attempt is preserved')
    contract=dict(protocol='rl1-e0-finite-support-bc-then-ppo-v1',seeds=[17,29,43],bc_epochs=500,
                  bc_lr=.003,ppo_episodes=128,ppo_defaults='unchanged e0_learning.PPO defaults',
                  reason='from-scratch 4096-episode diagnostic learned complementarity but did not reliably stop; test the originally planned supervised initialization route',
                  no_hyperparameter_grid=True,no_outcome_based_extension=True,critic_oracle_fit=False,
                  complete_toy_support_only=True,real_PM_training=False,LLM_calls=0,
                  module_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/e0_learning.py'),runner_sha256=sha256_file(Path(__file__)))
    save(OUT/'contract.json',contract)
    states,labels=support(); obs=torch.tensor([s.observation() for s in states]); masks=torch.tensor([s.mask() for s in states])
    save(OUT/'support_manifest.json',dict(states=len(states),observed_terminal_feedback='complete known toy utility function',unmeasured_real_plans_used=0,
             rows=[dict(case=s.case,counts=s.counts,optimal_actions=torch.where(labels[i]>0)[0].tolist()) for i,s in enumerate(states)]))
    results=[]; started=time.monotonic()
    for seed in contract['seeds']:
        torch.manual_seed(seed); rng=random.Random(seed); model=ToyActorCritic()
        optimizer=torch.optim.Adam(list(model.body.parameters())+list(model.policy.parameters()),lr=.003)
        for epoch in range(500):
            dist,_=model(obs,masks)
            loss=-(labels*dist.probs.clamp_min(1e-12).log()).sum(-1).mean()
            optimizer.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),.5);optimizer.step()
        bc_eval=evaluate(model,0);before={k:v.clone() for k,v in model.state_dict().items()}
        trainer=PPO(model); curves=[dict(episodes=0,evaluation=bc_eval)]
        for count in range(16,129,16):
            trainer.update([rollout(model,rng.randrange(5),trainer.version) for _ in range(16)])
            if count in (64,128):curves.append(dict(episodes=count,evaluation=evaluate(model,trainer.version)))
        checkpoint=OUT/f'seed_{seed}.pt';trainer.save(checkpoint,rng,128)
        result=dict(seed=seed,bc_loss=float(loss.detach()),curves=curves,ppo_batches=trainer.version,
                    ppo_changed_parameters=any(not torch.equal(before[k],v) for k,v in model.state_dict().items()),
                    endpoint_all_cases_optimal=all(abs(x['greedy_return']-x['oracle_return'])<1e-6 for x in curves[-1]['evaluation']),
                    checkpoint_sha256=sha256_file(checkpoint))
        results.append(result);save(OUT/f'seed_{seed}.json',result)
        save(OUT/'summary.json',dict(results=results,completed_seeds=len(results),elapsed_seconds=time.monotonic()-started,
             all_endpoints_optimal=all(r['endpoint_all_cases_optimal'] for r in results),toy_only=True,LLM_calls=0,API_usd=0,
             interpretation='BC -> PPO integration only; not evidence that PPO improves on the exact-DP initialization'))
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
