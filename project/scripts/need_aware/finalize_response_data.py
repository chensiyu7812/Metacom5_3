#!/usr/bin/env python3
"""Autonomous CPU pipeline: await supply, build actual reply data, native-check and freeze.

No GPU, training, Generation or paid API. B's long jobs are not polled. This
program watches only its own supply completion artifact and exits after 2 hours.
"""
import argparse,json,math,os,time
from pathlib import Path
from collections import Counter
from metacom_pm.need_aware.data.response_data import build,jsonl
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl,sha_file
from metacom_pm.need_aware.data.contracts import digest,load_runtime
from metacom_pm.need_aware.data.reply_objective import encode_reply,VERSION,MAX_LENGTH,PAIR_WEIGHT,MARGIN
from metacom_pm.need_aware.evaluation.wp4_mcq import POLICY
from metacom_pm.need_aware.runtime.models import NativeTokenizer,QWEN35,capacity,bind_inventory
from metacom_pm.need_aware.runtime.requests import make,deduplicate


def run(a):
    os.umask(0o077);root=Path(a.root);start=time.monotonic()
    while not (root/'supply/SUPPLY_DONE.json').exists():
        if (root/'supply/SUPPLY_FAILED.json').exists():raise RuntimeError('supply failed; inspect source job receipt')
        if time.monotonic()-start>7200:raise TimeoutError('supply not complete; no model result created')
        time.sleep(60)
    target=root/'release'
    if target.exists():raise FileExistsError('release exists; preserve previous attempt')
    allocation=json.loads((root/'ALLOCATION.json').read_text())
    summary=build(a.source,a.training,allocation,root/'supply',target,
        [root/'review50/ANNOTATIONS.private.jsonl',root/'support96/ANNOTATIONS.private.jsonl'])
    for part in ('runtime','evaluation'):
        assert sha_file(root/f'development_frozen/{part}/tasks.mcq.jsonl')==sha_file(target/f'development/{part}/tasks.mcq.jsonl')
    spec=bind_inventory(QWEN35,a.inventory);native=NativeTokenizer(spec)
    stats={};encoded_dir=target/'encoded'
    for split in ('fit','tune','development'):
        rows=jsonl(target/f'supervision/{split}.private.jsonl');enc=[]
        for r in rows:
            p=Path(r['runtime_ref']);assert sha_file(p)==r['runtime_sha256']
            msgs=json.loads(p.read_text())['messages'];e=encode_reply(native.tok,r,msgs)
            assert e['positive']['input_ids'][:e['prompt_tokens']]==native.chat_ids(msgs)
            assert e['positive']['input_ids'][-1]==248046
            enc.append(e)
        write_jsonl(encoded_dir/f'{split}.private.jsonl',enc)
        lengths=[len(e['positive']['input_ids']) for e in enc]
        stats[split]=dict(rows=len(enc),owners=len({r['owner'] for r in rows}),
            paired_rows=sum(e['pair_mask'] for e in enc),positive_tokens=sum(lengths),
            extra_negative_tokens=sum(len(e['rejected']['input_ids']) for e in enc if e['rejected']),
            min_sequence=min(lengths,default=None),max_sequence=max(lengths,default=None),
            mean_sequence=sum(lengths)/len(lengths) if lengths else None,
            prefix_equals_inference=len(enc),native_end_token=248046,
            known_weak_advice_rows=sum(r['positive_status']=='nonassertive_official_advice_weak_supervision' for r in rows))
    tasks={t.task_id:t for t in load_runtime(target/'development/runtime/tasks.mcq.jsonl')}
    req=[]
    for r in jsonl(target/'development/requests.private.jsonl'):
        t=tasks[r['task_id']];ids=native.chat_ids(r['messages']);decode=spec.decode(64)
        row=make(t,r['arm'],spec,r['messages'],ids,decode,
            dict(evidence_sha256=r['evidence_sha256'],supply_sha256=r['runtime_supply_sha256']),
            capacity(ids,decode),dict(protocol='naa-response-wp4-v1',model_inventory_sha256=sha_file(a.inventory)))
        row.update(task_sha256=digest(t.to_dict()),scoring_protocol=POLICY['scoring_protocol'])
        req.append(row)
    dedup=deduplicate(req)
    # No result-based order: task rows and arms are frozen by original candidate order.
    write_jsonl(target/'development/native.requests.private.jsonl',req)
    write_json(target/'development/POLICY.json',POLICY)
    candidate=dict(protocol=VERSION,authorized=False,model=spec.model_id,revision=spec.revision,
        train_file=str(target/'supervision/fit.private.jsonl'),
        train_sha256=sha_file(target/'supervision/fit.private.jsonl'),
        tune_file=str(target/'supervision/tune.private.jsonl'),tune_sha256=sha_file(target/'supervision/tune.private.jsonl'),
        encoded_fit_file=str(encoded_dir/'fit.private.jsonl'),encoded_fit_sha256=sha_file(encoded_dir/'fit.private.jsonl'),
        initialization='same pinned base + same seed for both methods',seed=20261128,
        sample_order='frozen file order, identical U2/U3',epochs=1,gradient_accumulation=8,
        max_optimizer_steps=math.ceil(stats['fit']['rows']/8),learning_rate=1e-4,
        weight_decay=0.,warmup_steps=5,gradient_clip=1.,max_seq_length=MAX_LENGTH,
        lora=dict(target_modules=['q_proj','v_proj','in_proj_qkv'],rank=8,alpha=16,dropout=0.),
        class_weights='all 1.0, same for U2 and U3',pair_weight=PAIR_WEIGHT,pair_margin=MARGIN,
        pair_loss='softplus(0.5 - mean_reply_logp_positive + mean_reply_logp_one_checked_negative)',
        selection='fixed final step; tune NLL diagnostic only, development never trains or selects checkpoint',
        ordinary_sft='mean target-token NLL per positive, then equal example weights',
        negative_mean_scope='only reviewed delivered-source pairs within accumulation group',
        extra_compute=dict(negative_forwards=stats['fit']['paired_rows'],
            negative_tokens=stats['fit']['extra_negative_tokens'],
            relative_token_overhead=stats['fit']['extra_negative_tokens']/max(1,stats['fit']['positive_tokens'])))
    write_json(target/'TRAINING_CANDIDATE.json',candidate)
    receipt=dict(protocol='naa-response-real-data-cpu-receipt-v1',summary=summary,training=stats,
        native_mcq=dict(logical=len(req),**dedup,capacity=dict(Counter(r['status'] for r in req)),
            tokens_by_arm={arm:sum(r['capacity']['input_tokens'] for r in req if r['arm']==arm) for arm in {r['arm'] for r in req}}),
        gpu_calls=0,training_steps=0,generator_calls=0,scorer_selftest_is_not_model_result=True)
    write_json(target/'CPU_RECEIPT.json',receipt)
    resources=dict(protocol='naa-response-joint-resource-candidate-v1',authorized=False,
        owner='B executes; A supplies data, source masks and deterministic scoring',
        preserves_active_wp3=True,retired_template_training_authorization_not_reused=True,
        baseline=dict(logical_requests=len(req),arms=['U0','U1','U1+','No-memory','Options-only'],
            model='Qwen35',gpu_seconds_cap=8000,physical_attempt_cap=1400,technical_smoke_included=16),
        training=dict(methods=['U2','U3'],per_method_gpu_seconds_cap=10800,
            total_gpu_seconds_cap=21600,optimizer_steps_each=candidate['max_optimizer_steps'],
            first_two_updates_are_in_budget_technical_smoke=True,
            no_claim_at_unequal_steps=True,candidate_sha256=sha_file(target/'TRAINING_CANDIDATE.json')),
        post_training=dict(mcq_requests=2*len(tasks),agent_open_requests=3*84,
            open_arms=['U0','U2','U3'],max_open_new_tokens=512,
            gpu_seconds_cap=16000,physical_attempt_cap=840),
        total_gpu_seconds_cap=45600,single_device='A6000',paid_api_calls=0,formal_test_calls=0,
        budgets_include='loads, included smoke, attempts/retries, save, teardown; B binds actual manifest and wall guard',
        estimates=dict(fit_positive_tokens=stats['fit']['positive_tokens'],
            u3_extra_negative_tokens=stats['fit']['extra_negative_tokens'],
            old_sub1600_token_latency_not_a_valid_upper_bound_for_this_8k_input=True),
        B_integration_required=['bind reply_objective to bounded trainer with accumulation-group normalization',
            'bind new native request file and full-Agent tool adapter; do not invoke retired train-v11 target format',
            'confirm same evidence delivery and qv_all_layers coverage; no new structure ablation'],
        decision='one bounded candidate request; no training or additional inference approval is inferred')
    write_json(target/'JOINT_RESOURCE_CANDIDATE.json',resources)
    write_json(target/'FREEZE.json',dict(protocol='naa-response-release-freeze-v1',
        allocation_sha256=sha_file(root/'ALLOCATION.json'),
        external_inputs={str(p):sha_file(p) for p in [root/'review50/ANNOTATIONS.private.jsonl',
            root/'support96/ANNOTATIONS.private.jsonl',root/'supply/SUPPLY_DONE.json']},
        artifacts={str(p.relative_to(target)):sha_file(p) for p in sorted(target.rglob('*')) if p.is_file()}))
    write_json(root/'FINALIZE_DONE.json',dict(release=str(target),freeze_sha256=sha_file(target/'FREEZE.json'),
        cpu_receipt_sha256=sha_file(target/'CPU_RECEIPT.json'),seconds=time.monotonic()-start))
    print(json.dumps(receipt))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for n in ('root','source','training'):p.add_argument('--'+n,required=True)
    p.add_argument('--inventory',default='/opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json')
    args=p.parse_args()
    try:run(args)
    except Exception as exc:
        write_json(Path(args.root)/'FINALIZE_FAILED.json',dict(type=type(exc).__name__,message=str(exc),
            gpu_calls=0,training_steps=0,artifacts_preserved=True))
        raise
