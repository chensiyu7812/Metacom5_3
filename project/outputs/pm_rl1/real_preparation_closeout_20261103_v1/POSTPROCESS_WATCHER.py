"""Finite read-only supervisor; executes only offline postprocessing."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

repo=Path('/home/tokkio/Metacom5_3').resolve()
root=Path(__file__).resolve().parent
base=repo/'project/outputs/pm_rl1'
jobs={'G':2712946,'J':2720890}
scripts={'G':repo/'project/scripts/rl1/146_prepare_actual_training_feedback.py',
         'J':repo/'project/scripts/rl1/144_audit_development_progress.py'}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def identity(pid):
    try:return Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]
    except OSError:return None
def save(name,value):
    with (root/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
starts={k:identity(v) for k,v in jobs.items()};hashes={k:sha(p) for k,p in scripts.items()}
save('WATCHER_STARTED.json',dict(pid=os.getpid(),jobs=jobs,start_identities=starts,script_sha256=hashes,
    code_sha256=sha(__file__),maximum_monitor_seconds=86400,API_calls=0,model_loads=0,training_updates=0))
done={};deadline=time.monotonic()+86400
while time.monotonic()<deadline and len(done)<2:
    for name,pid in jobs.items():
        if name in done:continue
        marker=(base/'organized_initial_generation_20261103_v2/RESULTS.json' if name=='G'
                else base/'execution_bridges_20261103_v1/live_J/CLOSED.json')
        exited=identity(pid)!=starts[name] or starts[name] is None
        if not marker.exists() and not exited:continue
        if sha(scripts[name])!=hashes[name]:
            done[name]=dict(status='POSTPROCESS_CODE_CHANGED_NO_RUN');continue
        if name=='G' and not marker.exists():
            done[name]=dict(status='G_EXITED_INCOMPLETE_NO_RELOAD');continue
        out=base/('actual_training_feedback_20261103_v1' if name=='G' else 'paid_development_snapshot_20261103_final')
        args=[sys.executable,str(scripts[name]),'--output',str(out)]
        if name=='G':args+=['--package',str(base/'organized_initial_training_20261103_v2'),
                            '--generation',str(base/'organized_initial_generation_20261103_v2')]
        else:args+=['--package',str(base/'execution_bridges_20261103_v1'),
                    '--bank',str(base/'human_reference_reuse_20261102_v2')]
        with (root/(name+'_POSTPROCESS.log')).open('x') as log:
            result=subprocess.run(args,cwd=repo,stdout=log,stderr=subprocess.STDOUT)
        done[name]=dict(status='OFFLINE_POSTPROCESS_COMPLETED' if result.returncode==0 else 'OFFLINE_POSTPROCESS_FAILED',
                       exit_code=result.returncode,stage_closed_marker=marker.exists(),output=str(out),
                       qualification_granted=False,natural_updates=0)
        save(name+'_POSTPROCESS.json',done[name]);print(json.dumps({name:done[name]}),flush=True)
    if len(done)<2:time.sleep(15)
save('WATCHER_FINISHED.json',dict(results=done,monitor_timeout=len(done)<2,API_calls=0,model_loads=0,training_updates=0))
