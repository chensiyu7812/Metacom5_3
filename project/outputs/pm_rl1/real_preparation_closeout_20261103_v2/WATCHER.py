import hashlib, json, os, subprocess, sys, time
from pathlib import Path
repo=Path('/home/tokkio/Metacom5_3').resolve(); root=Path(__file__).resolve().parent
base=repo/'project/outputs/pm_rl1'; pid=2724801
script=repo/'project/scripts/rl1/144_audit_development_progress.py'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def ident():
    try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    except OSError:return None
def save(name,data):
    with (root/name).open('x') as f:json.dump(data,f,indent=2);f.write('\n')
start=ident();expected=sha(script);deadline=time.monotonic()+86400
save('WATCHER_STARTED.json',dict(watched_pid=pid,process_start=start,script_sha256=expected,code_sha256=sha(__file__),API_calls=0,training_updates=0))
marker=base/'execution_bridges_20261103_v1/live_J/CLOSED.json'
while time.monotonic()<deadline and ident()==start and start is not None and not marker.exists():time.sleep(15)
if ident()==start and start is not None and not marker.exists():
    result=dict(status='MONITOR_TIMEOUT_NO_ACTION')
elif sha(script)!=expected:
    result=dict(status='AUDIT_CODE_CHANGED_NO_ACTION')
else:
    output=base/'paid_development_snapshot_20261103_refresh_final'
    args=[sys.executable,str(script),'--package',str(base/'execution_bridges_20261103_v1'),'--bank',str(base/'human_reference_reuse_20261102_v2'),'--output',str(output)]
    with (root/'AUDIT.log').open('x') as log:run=subprocess.run(args,cwd=repo,stdout=log,stderr=subprocess.STDOUT)
    result=dict(status='OFFLINE_AUDIT_COMPLETED' if run.returncode==0 else 'OFFLINE_AUDIT_FAILED',exit_code=run.returncode,stage_closed_marker=marker.exists(),output=str(output))
result.update(API_calls=0,model_loads=0,training_updates=0)
save('WATCHER_FINISHED.json',result);print(json.dumps(result),flush=True)
