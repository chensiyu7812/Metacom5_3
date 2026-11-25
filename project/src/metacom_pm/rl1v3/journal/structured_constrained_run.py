"""Independent admission and thin worker selection for one frozen format diagnostic."""
import fcntl,hashlib,json,os,subprocess,sys,time
from pathlib import Path
from ..generator import limited_run as L
from ..io import file_sha256,object_sha256
from . import structured_run as S
from .structured_constrained import PROTOCOL as CONSTRAINT_PROTOCOL,SCHEMA

RUN_PROTOCOL='pmrl1-j-structured-constrained-run-v1'
JOB_KIND='JOURNAL_STRUCTURED_CONSTRAINED'

def constrained_request_id(row,constraint_sha256):
    return 'jconstrained:'+object_sha256(dict(payload_sha256=row['payload_sha256'],constraint_sha256=constraint_sha256))

def check(path):
    p=json.loads(Path(path).read_text())
    L.require((p['protocol'],p['job_kind'])==(RUN_PROTOCOL,JOB_KIND),'independent constrained identity')
    L.require(p['authorized'] is False and p['remaining_batches_authorized'] is False,'proposal must remain unapproved')
    original,oldrows,baseline=S.check(p['original_plan_path'])
    L.require(object_sha256(original)==p['original_plan_sha256'],'original plan identity')
    preserved=('baseline_path','baseline_sha256','checkpoint_path','model_path','python','batch_number','task_ids',
      'renderer_id','max_calls','logical_requests','global_seconds','load_seconds','request_seconds','max_model_loads',
      'warmup_calls','automatic_retry','task_manifest_path','task_manifest_sha256','review_path','review_sha256','stop_rules')
    L.require(all(p[k]==original[k] for k in preserved),'original execution/semantic contract changed')
    L.require(p['max_calls']==18 and p['global_seconds']==1200,'finite 18 call scope')
    constraint=json.loads(Path(p['constraint_path']).read_text())
    L.require(constraint['protocol']==CONSTRAINT_PROTOCOL and constraint['schema']==SCHEMA,'format schema changed')
    L.require(object_sha256(constraint)==p['constraint_sha256'],'constraint identity')
    for name,sha in p['files_sha256'].items():L.require(file_sha256(name)==sha,'bound input changed: '+name)
    root=Path(p['executor_root']).resolve()
    for name,sha in p['executor_files_sha256'].items():
        q=(root/name).resolve();L.require(q.is_relative_to(root) and file_sha256(q)==sha,'executor changed: '+name)
    for name,sha in original['executor_files_sha256'].items():
        L.require(p['executor_files_sha256'].get(name)==sha,'original executor bytes changed')
    for name in ('structured_constrained.py','structured_constrained_worker.py','structured_constrained_run.py'):
        L.require('project/src/metacom_pm/rl1v3/journal/'+name in p['executor_files_sha256'],'missing constrained executor binding')
    vendor=Path(p['vendor_path']).resolve()
    L.require(vendor.is_relative_to(root),'isolated dependency root')
    L.require('xgrammar/__init__.py' in p['vendor_files_sha256'] and
        any(n.endswith('.so') for n in p['vendor_files_sha256']),'missing compiled grammar dependency binding')
    for name,sha in p['vendor_files_sha256'].items():
        q=(vendor/name).resolve();L.require(q.is_relative_to(vendor) and file_sha256(q)==sha,'constraint dependency changed')
    for name,sha in p['constraint_runtime_files_sha256'].items():
        L.require(file_sha256(name)==sha,'grammar runtime dependency changed: '+name)
    rows=S.jl(p['requests_path'])
    L.require(file_sha256(p['requests_path'])==p['requests_sha256'],'constrained request bytes')
    L.require(len(rows)==len(oldrows)==18 and [r['request_id'] for r in rows]==p['ordered_request_ids'],'fixed order/cardinality')
    for row,old in zip(rows,oldrows):
        expected=dict(old,original_request_id=old['request_id'],constraint_sha256=p['constraint_sha256'],
          request_id=constrained_request_id(old,p['constraint_sha256']))
        L.require(row==expected,'only decode constraint may differ; original payload must be identical')
    return p,rows,baseline

def admit(plan,auth):
    L.require(auth.get('authorized') is True,'new explicit constrained approval required')
    L.require((auth.get('protocol'),auth.get('job_kind'))==(RUN_PROTOCOL,JOB_KIND),'old approval cannot transfer')
    L.require(auth.get('plan_sha256')==object_sha256(plan),'approval plan hash')
    L.require(auth.get('max_calls')==18 and auth.get('max_model_loads')==1,'approval scope')
    L.require(auth.get('researcher') and auth.get('decision_evidence'),'actual researcher approval required')

class StructuredConstrainedHF(L.SubprocessHF):
    def load(self,seconds):
        L.require(time.monotonic()<self.deadline,'global deadline before load')
        L.device_guard(initial=True)
        self.error=(self.out/'worker.stderr.log').open('xb')
        env=dict(os.environ,PYTHONPATH=str(self.root/'project/src')+os.pathsep+self.plan['vendor_path'],
          CUDA_VISIBLE_DEVICES=L.GPU,CUBLAS_WORKSPACE_CONFIG=':4096:8',HF_HUB_OFFLINE='1',
          TRANSFORMERS_OFFLINE='1',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
          PMRL1_CONSTRAINED_VENDOR=self.plan['vendor_path'],
          PMRL1_LIMITED_SUPERVISOR_PID=str(os.getpid()),PMRL1_LIMITED_DEADLINE=str(self.deadline))
        self.p=subprocess.Popen([sys.executable,'-m','metacom_pm.rl1v3.generator.limited_worker_guard',
          self.plan['python'],'-m','metacom_pm.rl1v3.journal.structured_constrained_worker'],
          cwd=self.out,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.error,env=env,start_new_session=True)
        report=json.loads(Path(self.plan['checkpoint_path']).read_text())
        return self._exchange(dict(operation='load',model_path=self.plan['model_path'],spec=self.baseline['spec'],checkpoint=report),seconds)

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
        backend=StructuredConstrainedHF(root,plan,baseline,journal.path,started+1200)
        return L.drive(plan,rows,baseline,journal,backend,
            lambda:(L.storage_guard(run_root),L.device_guard(backend.p.pid if backend.p else None)),started=started)
