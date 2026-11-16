import runpy,time
from pathlib import Path
r=Path('../live_runs/output_interface_v1_D_development');start=time.monotonic()
while time.monotonic()-start<30:
 if any(not (r/'stage'/f.name.replace('.result.','.review.')).exists() for f in r.glob('*/*.result.json')):runpy.run_path('inspect_pending.py');break
 if Path('process_exit.json').exists():print(Path('process_exit.json').read_text());break
 time.sleep(1)
else:print('still running; no completed unreviewed final')
