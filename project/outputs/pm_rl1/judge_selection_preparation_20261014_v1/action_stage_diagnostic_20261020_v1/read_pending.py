from pathlib import Path
import json,time
r=Path(__file__).resolve().parent.parent/'action_stage_runs/pmrl1-joint-action-stage-development-v1-20261020/live'
end=time.monotonic()+25
while True:
 pending=[f for f in sorted(r.glob('*.result.json')) if not f.with_name(f.name.replace('.result.json','.review.json')).exists()]
 if pending:
  for f in pending:
   d=json.loads(f.read_text());print(f.name,'technical',d['technical_valid'],'q/m/U',[d['evaluation'].get(k) for k in ('q','m','U')],'seconds',round(d['elapsed_seconds'],2))
   raw=f.with_name(f.name.replace('.result.json','.response.json'))
   if raw.exists():print(json.loads(raw.read_text())['choices'][0]['message']['content'])
   else:print('No complete raw response; no partial content read.')
  break
 if (r/'STOP.json').exists():print('STOP', (r/'STOP.json').read_text());break
 if (r/'stage_result.json').exists():print('STAGE COMPLETED');break
 if time.monotonic()>=end:print('Waiting; started',len(list(r.glob('*.started.json'))),'completed',len(list(r.glob('*.result.json'))));break
 time.sleep(.5)
