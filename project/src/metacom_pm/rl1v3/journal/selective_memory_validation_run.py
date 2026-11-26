"""Independent selective Memory validation admission over the existing isolated bounded HF worker.

Each plan covers eight/seven complete two-arm tasks; all thirty payloads are unique.
CPU check has no device/model access. Old A0, smoke and Memory approvals cannot
authorize this job. Backend, lock, request ledger, deadlines and guards are reused.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import time

from ..generator import limited_run as L
from ..generator.g0e import DECODE, SYSTEM
from ..io import file_sha256, object_sha256

RUN_PROTOCOL='pmrl1-j-selective-memory-validation-v1'
JOB_KIND='JOURNAL_SELECTIVE_MEMORY_VALIDATION'
ARMS={'STOP','MS'}


def jl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def validate_pairing(plan, rows, logical, frozen):
    L.require(len(frozen)==30 and len({r['logical_id'] for r in frozen})==30,'full frozen 30 required')
    L.require(len({r['request_id'] for r in frozen})==30,'30 distinct payload requests required')
    all_tasks=list(dict.fromkeys(r['task_id'] for r in frozen))
    L.require(len(all_tasks)==15 and plan['batch_number'] in (1,2),'fixed 15 task/two batch scope')
    L.require([(r['task_id'],r['arm']) for r in frozen]==[(t,a) for t in all_tasks for a in ('STOP','MS')],
        'frozen task order must contain adjacent STOP/MS pairs')
    selected=all_tasks[:8] if plan['batch_number']==1 else all_tasks[8:]
    count=16 if plan['batch_number']==1 else 14
    L.require(selected==plan['task_ids'],'fixed original task order')
    expected=[r for r in frozen if r['task_id'] in selected]
    L.require(logical==expected and len(logical)==plan['logical_requests']==count,'changed/incomplete frozen task batch')
    L.require(rows==logical and len(rows)==plan['max_calls']==count,'all unique physical/logical calls required')
    groups={}
    for r in frozen:
        L.require(r['domain']=='selective_memory_validation' and
            r['logical_id']=='selective-memory-validation:'+r['task_id']+':'+r['arm'],'independent logical identity')
        groups.setdefault(r['task_id'],[]).append(r['arm'])
    L.require(all(arms==['STOP','MS'] for arms in groups.values()),'complete STOP then MS pairs required')


def check(path):
    plan=json.loads(Path(path).read_text())
    L.require((plan['protocol'],plan['job_kind'])==(RUN_PROTOCOL,JOB_KIND),'independent selective Memory validation identity required')
    L.require(plan['authorized'] is False and plan['remaining_batches_authorized'] is False,'immutable unapproved proposal')
    L.require(plan['max_model_loads']==1 and plan['warmup_calls']==0 and plan['automatic_retry'] is False,'extra load/call/retry')
    L.require((plan['global_seconds'],plan['load_seconds'],plan['request_seconds'])==(1200,600,300),'fixed deadlines')
    L.require(plan['python']=='/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python','frozen Python')
    L.require(plan['model_path']=='/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3','frozen model')
    L.require({plan[k] for k in ('requests_path','baseline_path','checkpoint_path','frozen_requests_path',
        'logical_requests_path','task_manifest_path','review_path','read_checks_path')}<=set(plan['files_sha256']),'unbound run input')
    L.require(file_sha256(plan['task_manifest_path'])==plan['task_manifest_sha256'],
        'original selective Memory validation identity')
    L.require(file_sha256(plan['review_path'])==plan['review_sha256'],'private pre-generation review identity')
    for name,sha in plan['files_sha256'].items():L.require(file_sha256(name)==sha,'input changed: '+name)
    root=Path(plan['executor_root']).resolve()
    required={'project/src/metacom_pm/rl1v3/journal/selective_memory_validation_run.py',
        'project/scripts/rl1v3/journal_selective_memory_validation_run.py',
        'project/src/metacom_pm/rl1v3/journal/renderer.py',
        'project/src/metacom_pm/rl1v3/generator/limited_run.py',
        'project/src/metacom_pm/rl1v3/generator/limited_hf_worker.py',
        'project/src/metacom_pm/rl1v3/generator/limited_worker_guard.py',
        'project/src/metacom_pm/rl1v3/generator/runprep_checkpoint.py'}
    L.require(required<=set(plan['executor_files_sha256']),'unbound executor')
    for name,sha in plan['executor_files_sha256'].items():
        p=(root/name).resolve();L.require(p.is_relative_to(root),'executor path escape')
        L.require(file_sha256(p)==sha,'executor changed: '+name)
    baseline=json.loads(Path(plan['baseline_path']).read_text());spec=baseline['spec']
    L.require(object_sha256(baseline)==plan['baseline_sha256'],'baseline hash')
    L.require(spec['model']['revision']=='707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7','model revision')
    L.require(spec['runtime']['gpu_uuid']==L.GPU and spec['runtime']['backend']=='hf','fixed GPU/backend')
    L.require(spec['decode']==DECODE and spec['system_prompt']==SYSTEM,'frozen decode/system')
    rows=jl(plan['requests_path'])
    L.require(file_sha256(plan['requests_path'])==plan['requests_sha256'],'request SHA')
    L.require([r['request_id'] for r in rows]==plan['ordered_request_ids'],'request order')
    frozen=jl(plan['frozen_requests_path'])
    validate_pairing(plan,rows,jl(plan['logical_requests_path']),frozen)
    L.require([t['task_id'] for t in jl(plan['task_manifest_path'])]==list(dict.fromkeys(r['task_id'] for r in frozen)),
        'runtime task/request order mismatch')
    reviews=jl(plan['review_path'])
    L.require(len(reviews)==15 and {r['task_id'] for r in reviews}=={r['task_id'] for r in frozen},
        'complete pre-output evaluation coverage required')
    for row in rows:
        payload=row['model_input']
        L.require(set(payload)=={'messages','input_ids','decode'},'payload allowlist')
        L.require(object_sha256(payload)==row['payload_sha256'],'payload hash')
        L.require(row['request_id']=='jreq:'+row['payload_sha256'],'request ID/payload')
        L.require(row['baseline_sha256']==baseline['binding_sha256'],'row baseline')
        L.require(row['renderer_id']==plan['renderer_id'],'renderer binding')
        L.require(object_sha256(payload['input_ids'])==row['input_ids_sha256'],'token hash')
        L.require(payload['decode']==DECODE and payload['messages'][0]==dict(role='system',content=SYSTEM),'fixed G0e protocol')
        L.require(row['authorized'] is False and row['model_called'] is False,'request proposal state')
        L.require(len(payload['input_ids'])==row['input_tokens'] and len(payload['input_ids'])+320<=16384,'capacity')
    return plan,rows,baseline


def admit(plan,auth):
    L.require(auth.get('authorized') is True,'new explicit selective Memory validation approval required')
    L.require((auth.get('protocol'),auth.get('job_kind'))==(RUN_PROTOCOL,JOB_KIND) and
        (plan['protocol'],plan['job_kind'])==(RUN_PROTOCOL,JOB_KIND),'A0/smoke/old RS/Memory approval cannot transfer')
    L.require(auth.get('plan_sha256')==object_sha256(plan),'approval plan hash')
    L.require(auth.get('max_calls')==plan['max_calls'] and auth.get('max_model_loads')==1,'approval scope')
    L.require(auth.get('researcher') and auth.get('decision_evidence'),'actual researcher decision required')


def run(path,approval,run_root):
    plan,rows,baseline=check(path)
    auth=json.loads(Path(approval).read_text());admit(plan,auth)
    root=Path(plan['executor_root']);run_root=Path(run_root).resolve()
    storage=L.storage_guard(run_root)
    lock_path=L.DATA/'tokkio_projects/pmrl1-validation/limited-g0e-exclusive.lock'
    with lock_path.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        device=L.device_guard(initial=True)
        L.claim_request_set(plan,auth)
        journal=L.Journal(run_root/('job-'+object_sha256(auth)))
        started=time.monotonic()
        journal.add('RUN_START',approval=auth,plan_sha256=object_sha256(plan),storage=storage,gpu=device)
        try:
            for name,expected in baseline['spec']['model']['files'].items():
                p=Path(plan['model_path'])/name;h=hashlib.sha256()
                L.require(p.stat().st_size==expected['bytes'],'model file size')
                with p.open('rb') as f:
                    for block in iter(lambda:f.read(8*1024*1024),b''):
                        L.require(time.monotonic()-started<1200,'hash/global deadline')
                        h.update(block)
                L.require(h.hexdigest()==expected['sha256'],'model SHA: '+name)
            checkpoint=json.loads(Path(plan['checkpoint_path']).read_text())
            for name,sha in checkpoint['software_files'].items():L.require(file_sha256(name)==sha,'HF software changed')
            journal.add('MODEL_BYTES_VERIFIED',files=baseline['spec']['model']['files'])
        except BaseException as exc:
            journal.add('STOP',reason=str(exc),pending=plan['ordered_request_ids'],no_retry=True)
            raise
        backend=L.SubprocessHF(root,plan,baseline,journal.path,started+1200)
        return L.drive(plan,rows,baseline,journal,backend,
            lambda:(L.storage_guard(run_root),L.device_guard(backend.p.pid if backend.p else None)),started=started)
