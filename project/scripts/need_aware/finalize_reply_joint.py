#!/usr/bin/env python3
"""Bounded autonomous CPU join to B's implemented trainer/renderer; never runs a model.

Preserves A's first release. Waits for its own source job, then emits a separate
joint candidate, real native-token checks and a resource request. No GPU polling.
"""
import argparse,json,math,os,subprocess,sys,time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace
import naa_agent as NA
import naa_train as TRAIN
import naa_wp4 as W4
from metacom_pm.need_aware.data.contracts import load_runtime,digest
from metacom_pm.need_aware.data.personamem import sha_file,write_json,write_jsonl
from metacom_pm.need_aware.data.response_data import jsonl
from metacom_pm.need_aware.data.reply_bridge import delivered,row,VERSION
from metacom_pm.need_aware.agent import behavior as B
from metacom_pm.need_aware.memory.writer import StoreCache
from metacom_pm.need_aware.runtime import models as M,requests as Q,training as T,lora as L
from metacom_pm.need_aware.runtime.authorization import MANIFEST_PROTOCOL
from metacom_pm.need_aware.runtime.budget import default_caps
from metacom_pm.need_aware.evaluation.wp4_mcq import POLICY,validate_cell_binding


def run(a):
    os.umask(0o077);root=Path(a.root);out=root/'joint_release';start=time.monotonic()
    if out.exists():raise FileExistsError('preserve existing joint release')
    while not (root/'FINALIZE_DONE.json').exists():
        if (root/'FINALIZE_FAILED.json').exists():raise RuntimeError('upstream CPU finalizer failed')
        if time.monotonic()-start>a.wait_seconds:raise TimeoutError('upstream CPU finalizer deadline')
        time.sleep(60)
    old=root/'release';freeze=json.loads((old/'FREEZE.json').read_text())
    if sha_file(old/'FREEZE.json')!=json.loads((root/'FINALIZE_DONE.json').read_text())['freeze_sha256']:
        raise ValueError('upstream freeze changed')
    for rel,sha in freeze['artifacts'].items():
        if sha_file(old/rel)!=sha:raise ValueError('upstream artifact changed: '+rel)
    out.mkdir()
    allocation=json.loads((root/'ALLOCATION.json').read_text())
    tasks={t.task_id:t for t in load_runtime(Path(a.training)/'runtime/tasks.jsonl')}
    cache=StoreCache(root/'supply/stores');get=lru_cache(maxsize=2)(cache.get)
    supply_done=json.loads((root/'supply/SUPPLY_DONE.json').read_text())
    def supply(tid):
        p=root/'supply/runtime'/f'{tid}.json'
        if sha_file(p)!=supply_done['runtime_manifest'][p.name]:raise ValueError('supply changed')
        return json.loads(p.read_text())
    partitions={}
    for split in ('fit','tune'):
        converted=[]
        for c in jsonl(old/f'supervision/{split}.private.jsonl'):
            s=supply(c['task_id']);converted.append(row(c,tasks[c['task_id']],s,get(s['store_id'])))
        converted=T.group_order(converted,20261128)
        write_jsonl(out/f'supervision/{split}.private.jsonl',converted);partitions[split]=converted
    forbidden=set(allocation['original_split']['development']+allocation['wp3_owners']+allocation['wp4_reserve_owners'])
    # Exact fit/tune owner allowlist is stronger than only excluding known held-out sets.
    for split,rows in partitions.items():
        if any(r['owner_id'] not in allocation['original_split'][split] for r in rows):
            raise ValueError('unexpected training owner')
    contract=T.validate_reply(partitions['fit']+partitions['tune'],forbidden_owners=forbidden)
    if not partitions['fit']:raise ValueError('no supported fit examples')
    forbidden_file=out/'forbidden_owners.private.txt';forbidden_file.write_text('\n'.join(sorted(forbidden))+'\n')
    spec=M.bind_inventory(M.QWEN35,a.inventory);native=M.NativeTokenizer(spec);decode=spec.decode(64)
    candidate=dict(protocol=VERSION,authorized=False,train_file=str(out/'supervision/fit.private.jsonl'),
        train_sha256=sha_file(out/'supervision/fit.private.jsonl'),tune_file=str(out/'supervision/tune.private.jsonl'),
        tune_sha256=sha_file(out/'supervision/tune.private.jsonl'),seed=20261128,epochs=1,
        max_optimizer_steps=math.ceil(len(partitions['fit'])/8),gradient_accumulation=8,learning_rate=1e-4,
        weight_decay=0.,warmup_steps=5,rank_weight=.1,rank_margin=.5,
        lora=dict(L.WP4_LORA,suffixes=list(L.WP4_LORA['suffixes'])),base_g_id=spec.g_id,
        sample_order='same group hash order for U2/U3, seed 20261128',class_weights='all 1.0 in both methods',
        sft='sum positive target-token NLL / total positive target tokens in accumulation group',
        rank='mean over all examples, zero for unknown pairs; one reviewed negative: softplus(0.5-lp_positive+lp_negative)',
        lp='mean target-token log probability including native turn-end',
        compute_parity='both methods execute the same positive and checked negative branches; U2 ranking coefficient zero',
        max_seq_length=M.COMMON_INPUT_CAP,selection='fixed final step; tune NLL diagnostic only; development never trains',
        supply=supply_done['protocol'],evidence_choice_status='CPU candidate; jointly confirm after sealed W3 scoring',
        predecessor_sha256=sha_file(old/'TRAINING_CANDIDATE.json'),
        predecessor_status='preserved historical candidate; joint candidate uses implemented B objective/renderer')
    write_json(out/'TRAINING_CANDIDATE.json',candidate)
    TRAIN.cmd_check_reply(SimpleNamespace(candidate=str(out/'TRAINING_CANDIDATE.json'),store_root=None,
        forbidden_owners=str(forbidden_file),inventory=a.inventory,out=str(out/'TRAINING_CHECK.json')))
    # Tune is held out from optimization but must satisfy the same native encoding contract.
    _,tune_alignment=T.encode_reply(partitions['tune'],T.native_encoder(native,T.TURN_END['Qwen35'],M.COMMON_INPUT_CAP),
        eos_ids=decode['eos_token_id'],turn_end_id=T.TURN_END['Qwen35'])
    devfile=root/'development_frozen/runtime/tasks.mcq.jsonl'
    dev=load_runtime(devfile);requests=[]
    versions=dict(joint=VERSION,behavior=B.BEHAVIOR_VERSION,request=Q.REQUEST_VERSION,
        scoring=POLICY['scoring_protocol'],supply=supply_done['protocol'])
    for task in dev:
        s=supply(task.task_id);store=get(s['store_id']);packed=delivered(tasks[task.task_id],s,store)
        ids=[]
        for arm in B.W40_CONDITIONS:
            messages,trace=B.mcq_messages(arm,task,store,packed)
            trace.update(store_id=store.store_id,supply_sha256=sha_file(root/'supply/runtime'/f'{task.task_id}.json'))
            native_ids=native.chat_ids(messages)
            r=Q.make(task,arm,spec,messages,native_ids,decode,trace,M.capacity(native_ids,decode),versions)
            r.update(task_sha256=digest(task.to_dict()),scoring_protocol=POLICY['scoring_protocol'])
            validate_cell_binding(r,'Qwen35',arm);requests.append(r)
            if arm in B.SAME_EVIDENCE:ids.append(tuple(trace['delivered_ids']))
        if len(set(ids))!=1:raise ValueError('same evidence changed')
    dedup=Q.deduplicate(requests)
    md=out/'development';md.mkdir();caps=default_caps(dedup['physical_unique'],gpu_seconds=10000,
        max_physical_calls=1500,per_model_gpu_seconds=10000)
    caps.update(input_cap=M.COMMON_INPUT_CAP,backend_cap=M.BACKEND_CONTEXT_CAP,max_model_loads_per_model=2,teardown_seconds=10)
    manifest=dict(protocol=MANIFEST_PROTOCOL,authorized=False,research_qualified=False,
        scope='CPU W4 candidate; fixed 272 tasks, five controls, same deployable evidence; joint supply choice pending',
        tasks_sha256=sha_file(devfile),task_ids_sha256=None,model_order=['Qwen35'],
        bindings={'Qwen35':{**spec.__dict__,'g_id':spec.g_id,'decode':decode}},
        checkpoints={'Qwen35':NA.checkpoint_headers(spec)},runtime=NA.runtime_pins(),versions=versions,counts=dedup,
        order_rule='frozen task order; U0,U1,U1+,NoMem,OptOnly per task',evidence_choice_status=candidate['evidence_choice_status'])
    W4._write_manifest(md,requests,manifest,caps);write_json(md/'POLICY.json',POLICY)
    check=json.loads((out/'TRAINING_CHECK.json').read_text())
    fit=partitions['fit'];pairs=sum(bool(r['rejected']) for r in fit)
    round300=lambda x:300*math.ceil(x/300)
    train_cap=round300(check['time_bound']['per_method_train_s']+check['time_bound']['load_s']+130)
    # Planning bounds, not measured long-context training speed or a GPU approval.
    mcq_s=2*sum(len(r['input_ids'])/5298+64/21.17 for r in requests if r['arm']=='U0')
    open_s=3*84*(M.COMMON_INPUT_CAP/5298+512/21.17)
    post_cap=round300(mcq_s+open_s+4*38+40)
    resource=dict(protocol=VERSION,authorized=False,review_status='B resource review and researcher training approval pending',
        executor='B only',candidate_sha256=sha_file(out/'TRAINING_CANDIDATE.json'),
        training_check_sha256=sha_file(out/'TRAINING_CHECK.json'),preserve_active_W3=True,
        W4_0=dict(logical_requests=len(requests),gpu_seconds_cap=10000,physical_attempt_cap=1500,
            authorization='B conditional scope only; this candidate is not an execution approval'),
        training=dict(methods=['U2','U3'],per_method_gpu_seconds_cap=train_cap,total_gpu_seconds_cap=2*train_cap,
            optimizer_steps_each=candidate['max_optimizer_steps'],fit_rows=len(fit),paired_fit_rows=pairs,
            same_initialization_data_order_updates_weights_lora=True,
            smoke='B included first 20 optimizer steps; hard time/memory guards; never spend outside cap',
            time_estimate=check['time_bound'],unequal_steps='incomplete comparison, not a fair training effect'),
        post_training=dict(mcq_requests=2*len(dev),agent_open_requests=3*84,open_arms=['U0','U2','U3'],
            max_open_new_tokens=512,gpu_seconds_cap=post_cap,physical_attempt_cap=840,
            adapted_mcq_inputs='same U0 evidence input only; no extra adapted diagnostic arms'),
        new_training_and_post_gpu_seconds=2*train_cap+post_cap,
        all_stages_gpu_seconds=10000+2*train_cap+post_cap,
        time_estimate_limit='CPU token/earlier latency planning bound, not measured 8k backward speed',
        paid_api_calls=0,formal_test_calls=0,additional_training_authorized=False,
        required_interfaces=['joint evidence selection after W3','bind full-Agent actual episode traces to 84 task contracts'])
    write_json(out/'JOINT_RESOURCE_CANDIDATE.json',resource)
    receipt=dict(protocol=VERSION,contract=contract,training_check=check,tune_alignment=tune_alignment,
        partitions={k:dict(rows=len(v),owners=len({r['owner_id'] for r in v}),paired=sum(bool(r['rejected']) for r in v),
            positive_status=dict(Counter(r['provenance']['positive_status'] for r in v))) for k,v in partitions.items()},
        native_mcq=dict(logical=len(requests),**dedup,status=dict(Counter(r['status'] for r in requests))),
        gpu_calls=0,training_steps=0,generator_calls=0,old_template_rows=0,
        executor_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
    write_json(out/'CPU_RECEIPT.json',receipt)
    write_json(out/'FREEZE.json',dict(protocol=VERSION,artifacts={str(p.relative_to(out)):sha_file(p)
        for p in sorted(out.rglob('*')) if p.is_file()}))
    write_json(out/'JOINT_DONE.json',dict(freeze_sha256=sha_file(out/'FREEZE.json'),seconds=time.monotonic()-start,
        cpu_receipt_sha256=sha_file(out/'CPU_RECEIPT.json'),authorized=False))
    print(json.dumps(receipt))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--root',required=True);p.add_argument('--training',required=True)
    p.add_argument('--inventory',default='/opt/tokkio-data0/naa/20261127/logs/native/model_inventory.json')
    p.add_argument('--wait-seconds',type=int,default=7200)
    a=p.parse_args()
    try:run(a)
    except Exception as exc:
        write_json(Path(a.root)/'JOINT_FAILED.json',dict(type=type(exc).__name__,message=str(exc),gpu_calls=0,artifacts_preserved=True))
        raise
