from pathlib import Path
import sys,json,hashlib,sqlite3,subprocess,datetime,collections,importlib.metadata
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import selection as s
out=Path(__file__).parent
plan=s.load_plan()
old1=s.REPO/'project/outputs/pm_rl1/completion_20260930_v2/P3/candidate_v1'
old1=next(old1.glob('development/*/summary.json')).parent
old2=s.REPO/'project/outputs/pm_rl1/p3_v2_after_confirmation_20261014/runs/development'
audit=[]
for p in [old1,old2]:
 ids={x.name.split('.')[0] for x in p.glob('*.request.json')}
 rawids={x.name.split('.')[0] for x in p.glob('*.raw.json')}
 mids={x.name.split('.')[0] for x in p.glob('*.measurement.json')}
 assert ids==rawids==mids
 summary=s.read(p/'summary.json')
 assert len(ids)==summary['physical_calls_this_invocation']==33
 statuses=collections.Counter()
 for rid in sorted(ids):
  request=s.read(p/(rid+'.request.json'));raw=s.read(p/(rid+'.raw.json'));m=s.read(p/(rid+'.measurement.json'))
  assert request['request_id']==rid==raw['request_id']
  statuses[m['measurement_status']]+=1
 if (p/'attempts.sqlite').exists():
  c=sqlite3.connect('file:'+str(p/'attempts.sqlite')+'?mode=ro',uri=True)
  assert {x[0] for x in c.execute('select request_id from attempts')}==ids
 audit.append(dict(directory=str(p),physical_calls=len(ids),request_raw_measurement_bindings_verified=True,status_counts=dict(statuses),request_ids=sorted(ids)))
protocol=s.read(s.REPO/'project/outputs/pm_rl1/p3_v2_after_confirmation_20261014/protocol.json')
assert protocol['semantic_revisions_after_human_labels']==1
live=[]
for p in s.HERE.rglob('*.started.json'):
 d=s.read(p)
 if d.get('mode')=='live':live.append(str(p))
assert not live,live
ledger=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
b=s.Budget(ledger,trial=plan['identity'],trial_cap=0,shared_cap=s.nanodollars(20),baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('0.03079930'))
total,trial,reserved,settled=b._totals(b.events())
manifest=s.read(s.HERE/'delivery_manifest.json')
print('delivery_manifest_keys',list(manifest))
filemap=manifest.get('files',manifest.get('sha256',manifest.get('artifacts',{})))
print('delivery_filemap_type',type(filemap).__name__,len(filemap))
if isinstance(filemap,dict):
 bad=[rel for rel,h in filemap.items() if isinstance(h,str) and s.sha(s.HERE/rel)!=h]
 assert not bad,bad
r=dict(time_jst=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),plan_identity=plan['identity'],implementation_identity=s.code_identity(),old_runs=audit,old_calls=sum(x['physical_calls'] for x in audit),semantic_revision_count=1,new_pool_live_starts=live,new_pool_reusable_records=0,original_call_cap=140,authorized_new_calls=8,authorized_cumulative_cap=74,paid_ledger_sha256=s.sha(ledger),ledger_total_usd=s.usd(total),ledger_since_boundary_usd=s.usd(total-s.nanodollars('1.50724291')),ledger_reserved_count=len(reserved),ledger_unsettled_count=len(set(reserved)-set(settled)),packages={k:importlib.metadata.version(k) for k in plan['configs']['gemma4_12b_bf16']['packages']},gpu=subprocess.check_output(['nvidia-smi','--query-gpu=uuid,name,memory.free,utilization.gpu','--format=csv,noheader,nounits'],text=True),compute_processes=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name','--format=csv,noheader'],text=True),disk=subprocess.check_output(['df','-h','/opt/tokkio-data0'],text=True))
s.save(out/'audit_preflight.json',r)
print(json.dumps({k:v for k,v in r.items() if k!='old_runs'},ensure_ascii=False,indent=2))
