"""Fixed Memory diagnostic/Writer admissions over the preserved bounded worker.

These three job identities never consume smoke, A0, RS or each other's approval.
The frozen source requests are checked before any device or model operation.
"""
import fcntl
import hashlib
import json
from pathlib import Path
import time

from ..generator import limited_run as L
from ..generator.g0e import DECODE, SYSTEM
from ..io import file_sha256, object_sha256

SCOPES={
    'JOURNAL_MEMORY_REPR18':('pmrl1-j-memory-repr18-run-v1',18,'repr:'),
    'JOURNAL_WRITER8':('pmrl1-j-writer8-run-v1',8,'writer8:'),
    'JOURNAL_MPME6':('pmrl1-j-mpme6-run-v1',6,'mpme:'),
}


def jl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def validate_scope(plan, rows, frozen):
    scope=SCOPES.get(plan['job_kind'])
    L.require(scope is not None and plan['protocol']==scope[0],'independent Memory identity required')
    _,count,prefix=scope
    L.require(plan['max_calls']==count==len(rows),'fixed Memory call count')
    L.require(len({r['request_id'] for r in rows})==count and
        len({r['payload_sha256'] for r in rows})==count,'duplicate Memory call')
    original={r['request_id']:r for r in frozen}
    L.require(len(original)==len(frozen),'duplicate frozen identity')
    for row in rows:
        L.require(row['request_id']==prefix+row['payload_sha256'],'Memory request prefix/hash')
        L.require(row['request_id'] in original and row==original[row['request_id']],
            'Memory frozen request changed')
    if plan['job_kind']=='JOURNAL_MEMORY_REPR18':
        groups={}
        for row in rows:groups.setdefault(row['task_id'],[]).append(row)
        L.require(len(groups)==6 and sorted(groups)==plan['task_ids'],'six fixed complete tasks required')
        for group in groups.values():
            L.require(len(group)==3 and {r['arm'] for r in group}=={'RAW','TYPED_OR_SUM','SPAN'},
                'incomplete representation triple')
            L.require(len({r['source_session_set_sha256'] for r in group})==1,'source set differs across representations')
    elif plan['job_kind']=='JOURNAL_WRITER8':
        L.require(len(frozen)==8 and [r['request_id'] for r in rows]==[r['request_id'] for r in frozen],
            'frozen Writer8 order/cardinality')
    else:
        groups={}
        for row in rows:groups.setdefault(row['case_id'],[]).append(row)
        L.require(len(groups)==2 and sorted(groups)==plan['case_ids'],'two fixed update cases required')
        for group in groups.values():
            L.require({r['arm'] for r in group}=={'BEFORE_RAW','AFTER_FULL_RAW','AFTER_CPU_PRIOR_PLUS_RAW'}
                and len(group)==3,'incomplete MP/ME update triple')


def check(path):
    plan=json.loads(Path(path).read_text())
    L.require(plan['authorized'] is False,'proposal must remain immutable')
    L.require(plan['max_model_loads']==1 and plan['warmup_calls']==0 and
        plan['automatic_retry'] is False,'extra load/call/retry')
    L.require((plan['global_seconds'],plan['load_seconds'],plan['request_seconds'])==(1200,600,300),
        'fixed hard limits changed')
    L.require(plan['python']=='/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python','frozen Python')
    L.require(plan['model_path']=='/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3','frozen model')
    L.require({plan[k] for k in ('requests_path','baseline_path','checkpoint_path','frozen_requests_path')}
        <=set(plan['files_sha256']),'unbound Memory input')
    for name,sha in plan['files_sha256'].items():L.require(file_sha256(name)==sha,'Memory input changed: '+name)
    root=Path(plan['executor_root']).resolve()
    required={'project/src/metacom_pm/rl1v3/journal/memory_run.py',
        'project/src/metacom_pm/rl1v3/generator/limited_run.py',
        'project/src/metacom_pm/rl1v3/generator/limited_hf_worker.py',
        'project/src/metacom_pm/rl1v3/generator/limited_worker_guard.py',
        'project/src/metacom_pm/rl1v3/generator/runprep_checkpoint.py'}
    L.require(required<=set(plan['executor_files_sha256']),'unbound Memory executor')
    for name,sha in plan['executor_files_sha256'].items():
        p=(root/name).resolve();L.require(p.is_relative_to(root),'executor path escape')
        L.require(file_sha256(p)==sha,'executor changed: '+name)
    baseline=json.loads(Path(plan['baseline_path']).read_text());spec=baseline['spec']
    L.require(object_sha256(baseline)==plan['baseline_sha256'],'baseline hash')
    L.require(spec['model']['revision']=='707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7','model revision')
    L.require(spec['runtime']['gpu_uuid']==L.GPU and spec['runtime']['backend']=='hf','GPU/backend changed')
    L.require(spec['decode']==DECODE and spec['system_prompt']==SYSTEM,'G0e protocol changed')
    rows=jl(plan['requests_path'])
    L.require(file_sha256(plan['requests_path'])==plan['requests_sha256'],'request bytes')
    L.require([r['request_id'] for r in rows]==plan['ordered_request_ids'],'ordered requests changed')
    validate_scope(plan,rows,jl(plan['frozen_requests_path']))
    for row in rows:
        payload=row['model_input']
        L.require(set(payload)=={'messages','input_ids','decode'},'payload allowlist')
        L.require(object_sha256(payload)==row['payload_sha256'],'payload hash')
        L.require(row['baseline_sha256']==baseline['binding_sha256'],'row baseline')
        L.require(row['renderer_id']==plan['renderer_id'],'renderer binding')
        L.require(object_sha256(payload['input_ids'])==row['input_ids_sha256'],'native token hash')
        L.require(payload['decode']==DECODE and payload['messages'][0]==dict(role='system',content=SYSTEM),
            'fixed decode/system')
        L.require(row['authorized'] is False and row['model_called'] is False,'request proposal state')
        L.require(len(payload['input_ids'])+320<=16384,'capacity')
    return plan,rows,baseline


def admit(plan,auth):
    L.require(auth.get('authorized') is True,'new explicit Memory approval required')
    scope=SCOPES.get(plan['job_kind'])
    L.require(scope is not None and (auth.get('protocol'),auth.get('job_kind'))==
        (scope[0],plan['job_kind']) and plan['protocol']==scope[0],
        'A0/smoke/batch/RS/other Memory approval cannot transfer')
    L.require(auth.get('plan_sha256')==object_sha256(plan),'approval plan hash')
    L.require(auth.get('max_calls')==scope[1] and auth.get('max_model_loads')==1,'approval scope')
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
