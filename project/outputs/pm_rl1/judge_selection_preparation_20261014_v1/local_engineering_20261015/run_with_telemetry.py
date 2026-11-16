"""One invocation of the unchanged authorized runner; observation only, no retry."""
from pathlib import Path
import subprocess,threading,time,json,datetime,sys
HERE=Path(__file__).resolve().parents[1];OUT=Path(__file__).resolve().parent
stop=threading.Event()
def stamp():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
def monitor():
 with (OUT/'gpu_monitor.jsonl').open('x') as f:
  while not stop.is_set():
   t=time.time()
   q=subprocess.run(['nvidia-smi','--query-gpu=uuid,name,memory.used,memory.free,utilization.gpu,power.draw','--format=csv,noheader,nounits'],capture_output=True,text=True)
   p=subprocess.run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory','--format=csv,noheader,nounits'],capture_output=True,text=True)
   f.write(json.dumps({'unix':t,'jst':stamp(),'gpus':q.stdout,'compute_processes':p.stdout,'query_exit_code':q.returncode})+'\n');f.flush()
   stop.wait(10)
cmd=[sys.executable,str(HERE/'selection.py'),'run-stage','--phase','engineering','--candidates','gemma4_12b_bf16','gemma4_12b_bf16_thinking','--approval',str(OUT/'approval_engineering_AB.json'),'--execute-live']
start=time.monotonic();start_jst=stamp()
with (OUT/'runner_invocation.json').open('x') as f:json.dump({'argv':cmd,'start_jst':start_jst,'one_invocation_only':True},f,indent=2)
t=threading.Thread(target=monitor);t.start()
try:
 with (OUT/'runner.log').open('x') as f:
  result=subprocess.run(cmd,cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
finally:stop.set();t.join()
receipt={'start_jst':start_jst,'end_jst':stamp(),'process_wall_seconds':time.monotonic()-start,'exit_code':result.returncode,'command':cmd}
with (OUT/'runner_process_receipt.json').open('x') as f:json.dump(receipt,f,indent=2)
print(json.dumps(receipt))
raise SystemExit(result.returncode)
