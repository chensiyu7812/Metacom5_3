import json
from pathlib import Path
B=Path(__file__).resolve().parent.parent;ROOT=B/'live_runs/output_interface_v1_D_development';PLAN=json.loads((B/'plan.json').read_text())
for f in ROOT.glob('*/*.result.json'):
 r=json.loads(f.read_text());req=r['request'];rid=req['request_id']
 if (ROOT/'stage'/(rid+'.review.json')).exists():continue
 item=PLAN['items'][req['item_key']];print('REQUEST',rid,req['item_key'],req['draw']);print('REPLY',item['reply']);print('CURRENT',json.dumps(item['evidence']['current_prefix'],ensure_ascii=False)) if not req['item_key'].startswith(('dev01','dev02','dev03','dev04','dev06','dev07','dev10','dev14','dev15','dev16')) else None
 raw=json.loads(f.with_name(rid+'.response.json').read_text());print('FINAL',raw['choices'][0]['message']['content']);print('SCORES',{k:r['evaluation']['measurement'].get(k) for k in ['measurement_status','q','m','candidate_utility']});print('TIME',r['elapsed_seconds']);print('COST',r['financial_accounting'])
