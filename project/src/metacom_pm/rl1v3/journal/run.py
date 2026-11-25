"""Journal smoke admission; reuse the existing isolated, bounded HF worker.

No model/device access occurs during check. A0/PP1 approvals cannot authorize this.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
from ..generator import limited_run as L
from ..generator.g0e import DECODE, SYSTEM
from ..io import file_sha256, object_sha256

PROTOCOL='pmrl1-j-smoke-run-v1'


def check(path):
    path=Path(path).resolve();plan=json.loads(path.read_text())
    L.require(plan['protocol']==PROTOCOL and plan['job_kind']=='JOURNAL_SMOKE','journal identity required')
    L.require(plan['authorized'] is False,'proposal must remain immutable')
    L.require(plan['max_calls']==20 and plan['max_model_loads']==1 and plan['warmup_calls']==0,'bounded smoke scope')
    L.require(plan['global_seconds']==1200 and plan['load_seconds']==600 and plan['request_seconds']==300,'hard deadline changed')
    L.require(plan['automatic_retry'] is False,'no retry')
    L.require(plan['python']=='/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python','frozen Python')
    L.require(plan['model_path']=='/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3','frozen model')
    root=Path(plan['executor_root']).resolve()
    L.require({plan['requests_path'],plan['baseline_path'],plan['checkpoint_path']} <= set(plan['files_sha256']),'unbound run input')
    required_executor={
        'project/src/metacom_pm/rl1v3/journal/run.py',
        'project/src/metacom_pm/rl1v3/journal/renderer.py',
        'project/src/metacom_pm/rl1v3/generator/limited_run.py',
        'project/src/metacom_pm/rl1v3/generator/limited_hf_worker.py',
        'project/src/metacom_pm/rl1v3/generator/limited_worker_guard.py',
        'project/src/metacom_pm/rl1v3/generator/runprep_checkpoint.py',
    }
    L.require(required_executor <= set(plan['executor_files_sha256']),'unbound executor')
    for name,sha in plan['files_sha256'].items():
        L.require(file_sha256(Path(name))==sha,'input changed: '+name)
    for name,sha in plan['executor_files_sha256'].items():
        p=(root/name).resolve()
        L.require(p.is_relative_to(root),'executor path escape')
        L.require(file_sha256(p)==sha,'executor changed: '+name)
    rows=[json.loads(x) for x in Path(plan['requests_path']).read_text().splitlines()]
    L.require(file_sha256(plan['requests_path'])==plan['requests_sha256'],'request set SHA')
    baseline=json.loads(Path(plan['baseline_path']).read_text())
    L.require(object_sha256(baseline)==plan['baseline_sha256'],'baseline mismatch')
    spec=baseline['spec']
    L.require(spec['model']['revision']=='707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7','model revision')
    L.require(spec['runtime']['gpu_uuid']==L.GPU and spec['runtime']['backend']=='hf','fixed GPU/backend')
    L.require(spec['decode']==DECODE and spec['system_prompt']==SYSTEM,'fixed decoding/system')
    L.require([r['request_id'] for r in rows]==plan['ordered_request_ids'],'ordered requests changed')
    L.require(len(rows)==20 and len({r['request_id'] for r in rows})==20,'request cardinality')
    for row in rows:
        payload=row['model_input']
        L.require(set(payload)=={'messages','input_ids','decode'},'payload allowlist')
        L.require(object_sha256(payload)==row['payload_sha256'],'payload hash')
        L.require(row['request_id']=='jreq:'+row['payload_sha256'],'request ID/payload mismatch')
        L.require(row['baseline_sha256']==baseline['binding_sha256'],'row baseline mismatch')
        L.require(object_sha256(payload['input_ids'])==row['input_ids_sha256'],'token hash')
        L.require(row['renderer_id']==plan['renderer_id'],'renderer binding')
        L.require(payload['decode']==DECODE and payload['messages'][0]=={'role':'system','content':SYSTEM},'fixed G0e protocol')
        L.require(len(payload['input_ids'])+320<=16384,'runtime capacity')
    return plan,rows,baseline


def admit(plan,auth):
    L.require(auth.get('authorized') is True,'new explicit journal approval required')
    L.require(auth.get('protocol')==PROTOCOL and auth.get('job_kind')=='JOURNAL_SMOKE','A0/PP1 approval does not transfer')
    L.require(auth.get('plan_sha256')==object_sha256(plan),'approval plan hash')
    L.require(auth.get('max_calls')==20 and auth.get('max_model_loads')==1,'approval scope')
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
