import subprocess,time,json,datetime,sys
from pathlib import Path
out=Path(__file__).resolve().parent;root=out.parent
cmd=[sys.executable,str(root/'resume_engineering.py'),'--amendment',str(out/'engineering_amendment.json'),'--execute-live']
def stamp():return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()
start=stamp();t=time.monotonic()
with (out/'invocation.json').open('x') as f:json.dump(dict(argv=cmd,start_jst=start),f,indent=2)
with (out/'execution.log').open('x') as f:r=subprocess.run(cmd,cwd=root,stdout=f,stderr=subprocess.STDOUT)
record=dict(start_jst=start,end_jst=stamp(),wall_seconds=time.monotonic()-t,exit_code=r.returncode)
with (out/'process_receipt.json').open('x') as f:json.dump(record,f,indent=2)
print(json.dumps(record),flush=True)
raise SystemExit(r.returncode)
