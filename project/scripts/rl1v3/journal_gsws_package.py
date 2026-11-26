#!/usr/bin/env python3
"""Freeze a new, not-authorized four-job scope on the existing GE2 dependency stack."""
import argparse,json,shutil
from pathlib import Path
from metacom_pm.rl1v3.io import object_sha256,file_sha256
from metacom_pm.rl1v3.journal import gsws as S
from metacom_pm.rl1v3.journal.gsws_run import PROTOCOL,JOB_KIND,BASE_COMMIT
from metacom_pm.rl1v3.journal.gsws_runtime import slots
from metacom_pm.rl1v3.journal.ge2_sources import rows,write_once


def freeze(repo,run_root,old_package,output):
    repo=Path(repo);r=Path(run_root);old=Path(old_package);out=Path(output)
    if out.exists():raise FileExistsError('never replace frozen package')
    out.mkdir(parents=True);ex=out/'executor';shutil.copytree(old/'executor',ex,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    paths=list((repo/'project/src/metacom_pm/rl1v3/journal').glob('gsws*.py'))+list((repo/'project/scripts/rl1v3').glob('journal_gsws_*.py'))
    paths.append(repo/'project/src/metacom_pm/rl1v3/journal/ge2_source_coordinate_audit.py')
    for p in paths:dest=ex/p.relative_to(repo);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    prior=json.loads((old/'batch-01/PLAN.json').read_text());b=r/'source-bundle-v1'
    tasks=rows(b/'TASKS.runtime.jsonl');cfg=json.loads((b/'SOURCE_CONFIG_PRIVATE.json').read_text())
    write_once(out/'SEMANTIC_CONTRACT.json',S.contract())
    for name in ['LATENCY_CONTRACT.json','ENVIRONMENT_CONTRACT.json']:shutil.copy2(old/name,out/name)
    sha_files={str(p):file_sha256(p) for p in [b/'TASKS.runtime.jsonl',b/'TASK_ENVELOPES.private.jsonl',b/'SOURCE_CONFIG_PRIVATE.json',
        b/'EVALSPEC.private.jsonl',r/'evaluation-v1/STATE_EVAL_CONTRACT_PRIVATE.jsonl',r/'evaluation-v1/COORDINATES_PRIVATE.json',r/'evaluation-v1/BLIND_REVIEW_CONTRACT.json',
        r/'task_freeze/SELECTION_RULES_PRIVATE.json',r/'task_freeze/SELECTION_PRIVATE.json',
        Path(prior['baseline_path']),Path(prior['checkpoint_path']),Path(cfg['asset_manifest_path']),
        out/'SEMANTIC_CONTRACT.json',out/'LATENCY_CONTRACT.json',out/'ENVIRONMENT_CONTRACT.json']}
    sha_files.update(cfg['source_inputs_sha256'])
    inv={str(p.relative_to(ex)):file_sha256(p) for p in sorted((ex/'project').rglob('*')) if p.is_file() and '__pycache__' not in str(p)}
    v=ex/'vendor_dynamic_controller';vendor={str(p.relative_to(v)):file_sha256(p) for p in sorted(v.rglob('*')) if p.is_file() and '__pycache__' not in str(p)}
    scope=object_sha256(dict(protocol=PROTOCOL,base=BASE_COMMIT,inputs=sha_files,executor=inv,contract=S.contract(),
                            terminal_slots=slots(tasks),interpreter_calls=32))
    plans=[]
    for i in range(4):
        d=out/f'batch-{i+1:02}';d.mkdir();ts=tasks[i*2:i*2+2];ss=slots(ts)
        req=dict(protocol=PROTOCOL,task_ids=[t['task_id'] for t in ts],terminal_slots=ss,
            role_call_caps={'terminal':12,'oneshot':4,'agent':4},max_calls=20,scope_sha256=scope,
            controller_contract_sha256=object_sha256(S.contract()),
            future_payload_binding='exact actual observation, validated source receipt and native payload at each call',authorized=False)
        write_once(d/'REQUEST_SCOPE_PRIVATE.json',req)
        p=dict(prior,protocol=PROTOCOL,job_kind=JOB_KIND,base_commit=BASE_COMMIT,arms=list(S.ARMS),diagnostic_arm=None,
            batch_number=i+1,catalog_path=str(out/'CATALOG.json'),scope_sha256=scope,
            task_manifest_path=str(b/'TASKS.runtime.jsonl'),envelopes_path=str(b/'TASK_ENVELOPES.private.jsonl'),
            review_path=str(r/'evaluation-v1/STATE_EVAL_CONTRACT_PRIVATE.jsonl'),source_config_path=str(b/'SOURCE_CONFIG_PRIVATE.json'),
            selection_path=str(r/'task_freeze/SELECTION_RULES_PRIVATE.json'),
            controller_contract_path=str(out/'SEMANTIC_CONTRACT.json'),controller_contract_sha256=object_sha256(S.contract()),
            environment_contract_path=str(out/'ENVIRONMENT_CONTRACT.json'),latency_contract_path=str(out/'LATENCY_CONTRACT.json'),
            requests_path=str(d/'REQUEST_SCOPE_PRIVATE.json'),requests_sha256=file_sha256(d/'REQUEST_SCOPE_PRIVATE.json'),
            task_ids=req['task_ids'],task_sha256={t['task_id']:object_sha256(t) for t in ts},terminal_slots=ss,
            max_calls=20,role_call_caps=req['role_call_caps'],executor_root=str(ex),executor_files_sha256=inv,
            executor_inventory_sha256=object_sha256(inv),vendor_path=str(v),vendor_files_sha256=vendor,
            files_sha256=dict(sha_files,**{str(d/'REQUEST_SCOPE_PRIVATE.json'):file_sha256(d/'REQUEST_SCOPE_PRIVATE.json')}),
            stop_rules=dict(interpreter_protocol_or_length='Preserve failed aid; one allocated RAW fallback terminal, no repair/retry.',
                unequal_original_evidence='Stop comparison; do not silently normalize or trim sources.',
                terminal_length='Technical incomplete, preserved; next independent slot may continue without retry.',
                integrity_device_transport_deadline='Stop own job; preserve partial/unexecuted; no retry or other GPU.'),
            timing_notes=['Same-boot monotonic local pipeline; model first text is not client text or speech.',
                'State1 records incremental latency and prior interpreter cost; earlier counterfactual terminal is not an online cost.',
                'A1 and A2 each one 512-token interpreter per state; actual unequal tokens/time are reported.',
                'Fixed order, zero warmup, no caching; cold start separately reported.'])
        p.pop('direct_recipes_path',None)
        write_once(d/'PLAN.json',p)
        plans.append(dict(name=f'GSWS-{i+1}',plan_path=str(d/'PLAN.json'),plan_object_sha256=object_sha256(p),
                          plan_file_sha256=file_sha256(d/'PLAN.json'),requests_sha256=p['requests_sha256']))
    catalog=dict(protocol=PROTOCOL,authorized=False,automatic_followup=False,max_calls=80,terminal_slots=48,
        interpreter_calls_max=32,model_loads_max=4,total_hard_seconds=4800,warmup_calls=0,retry_calls=0,
        task_ids=[t['task_id'] for t in tasks],batches=plans,executor_inventory_sha256=object_sha256(inv),
        base_commit=BASE_COMMIT,formal_reward=None)
    write_once(out/'CATALOG.json',catalog)
    print(json.dumps(dict(catalog_file_sha256=file_sha256(out/'CATALOG.json'),**catalog),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for key in ('repo','run-root','old-package','output'):p.add_argument('--'+key,required=True)
    a=p.parse_args();freeze(a.repo,a.run_root,a.old_package,a.output)
