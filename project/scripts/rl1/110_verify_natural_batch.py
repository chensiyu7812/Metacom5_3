#!/usr/bin/env python3
"""CPU-only integration receipt with test fixtures; no natural training/data."""
import argparse
from collections import Counter
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT/'src'), str(PROJECT/'tests')]


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    os.environ['CUDA_VISIBLE_DEVICES']=''
    import torch
    from metacom_pm.rl1.natural_batch import PendingBatch, FeedbackQueue, baseline_schedule, parameter_identity, MOCK
    from metacom_pm.rl1.observation_features import make_actor_critic
    from rl1_batch_fixtures import episodes, make_encoder, answer, drain, complete
    from metacom_pm.rl1.schema import digest
    a.out.mkdir(parents=True,exist_ok=False,mode=0o700)
    start=time.monotonic();torch.set_num_threads(1);torch.manual_seed(17)
    encoder,seen=make_encoder();model=make_actor_critic(encoder.feature_dimension)
    batch=PendingBatch(model,encoder,a.out/'updates');queue=FeedbackQueue(a.out/'mock_feedback.sqlite')
    batch.collect(episodes(),batch_id='engineering-16-only')
    sampled=[dict(trajectory_id=r['episode'].trajectory_id,steps=r['episode'].result()['steps'],
        policy_version=batch.trainer.version,visible_feature_identities=[digest(t['observation'].tolist()) for t in r['transitions']],
        old_log_probabilities=[float(t['old_log_prob']) for t in r['transitions']],
        old_values=[float(t['old_value']) for t in r['transitions']],
        action_masks=[t['mask'].tolist() for t in r['transitions']]) for r in batch.records]
    before=parameter_identity(model);batch.poll(queue)
    delayed=queue.claim_next();assert delayed is not None
    drain(queue)
    refused=False
    try:batch.update_once()
    except ValueError:refused=True
    assert refused and parameter_identity(model)==before
    pending=a.out/'pending.pt';batch.save(pending)
    encoder2,_=make_encoder();recovered=PendingBatch(make_actor_critic(encoder2.feature_dimension),encoder2,a.out/'updates')
    recovered.restore(pending,episodes())
    # A STARTED request is not automatically retried after recovery.
    assert queue.claim_next() is None
    queue.settle(delayed['id'],answer(delayed))
    results=complete(recovered,queue)
    receipt=recovered.update_once()
    final=[dict(trajectory_id=x['trajectory_id'],phase=x['phase'],steps=x['steps'],
        synthetic_return=x['return_value']) for x in results]
    contract=json.loads((PROJECT/'docs/pm_rl1_completion_20260930_v2/execution_contract.json').read_text())
    summary=dict(scope=MOCK,status='ENGINEERING_ACCEPTANCE_PASSED',real_natural_updates=0,
        real_generation_calls=0,real_judge_calls=0,api_usd=0,qualification_granted=False,
        sampled_trajectories=16,pm_updates=1,optimizer_minibatch_steps=16,
        total_actions=sum(len(x['steps']) for x in final),
        get_actions=sum(s['action']!=0 for x in final for s in x['steps']),
        stop_actions=16,synthetic_contexts=2,queue_counts=queue.counts(),
        update_blocked_while_pending=refused,pending_restored_without_resampling=True,
        unresolved_request_not_redispatched=True,optimizer_receipt=receipt,
        encoder='MOCK:sha256-4-not-BGE',tokenizer='MOCK:character-counter',
        natural_baseline_training_executed=False,wall_seconds=time.monotonic()-start)
    for name,obj in [('receipt.json',summary),('sampled_trajectories.json',sampled),
        ('completed_trajectories.json',final),('baseline_schedules.json',
        [baseline_schedule(contract,episodes_per_seed=n) for n in (128,384)])]:
        (a.out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
    for p in a.out.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
