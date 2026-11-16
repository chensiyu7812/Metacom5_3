"""Read-only collection of all eight authorized slots; never parses partial scores."""
from pathlib import Path
import sys,json,csv,datetime,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import selection as s
OUT=Path(__file__).parent; ROOT=s.HERE/'live_runs';plan=s.load_plan()
stage=s.read(ROOT/'engineering.AB.stage_result.json')
slots=[r for r in sorted(plan['requests'],key=lambda r:r['schedule_position']) if r['phase']=='engineering' and r['candidate'] in s.CANDIDATES[:2]]
assert len(slots)==8
attempts={r['request_id']:r for r in stage['attempts']}
records=[]
for req in slots:
 rid=req['request_id'];folder=ROOT/req['candidate'];item=plan['items'][req['item_key']];attempt=attempts[rid]
 files={kind:folder/(rid+'.'+kind+'.json') for kind in ['started','raw','response','result']}
 result=s.read(files['result']) if files['result'].exists() else None
 response=s.read(files['response']) if files['response'].exists() else None
 raw=s.read(files['raw']) if files['raw'].exists() else None
 telemetry=response or raw or {}
 m=result['measurement'] if result else {}
 if result:assert result['request']==req and result['mode']=='live'
 status=m.get('measurement_status','not_dispatched')
 failure=None
 if not result:failure='not_dispatched: '+attempt.get('reason','unknown')
 elif status not in s.VALID:
  if telemetry.get('total_seconds',0)>plan['configs'][req['candidate']]['timeout_seconds']:failure='technical_timeout'
  elif telemetry.get('natural_eos') is False:failure='non_natural_end_or_context_exhaustion'
  elif telemetry.get('natural_eos') is True:failure='parse_or_schema_failure_after_natural_end'
  else:failure='runtime_or_transport_failure'
 q,misuse,u=m.get('q'),m.get('m'),m.get('candidate_utility')
 if status not in s.VALID:assert q is None and misuse is None and u is None
 records.append(dict(local_order=len(records)+1,configuration=plan['configs'][req['candidate']]['label'],request=req,configuration_actual=plan['configs'][req['candidate']],item_key=req['item_key'],origin_job_id=item['origin_job_id'],reply_sha256=hashlib.sha256(item['reply'].encode()).hexdigest(),legal_evidence_identity=item['evidence_identity'],messages_identity=req['messages_identity'],schema_identity=req['schema_identity'],planned_reply=item['reply'],started=files['started'].exists(),status=status,failure_category=failure,not_dispatched_reason=attempt.get('reason') if not attempt['started'] else None,q=q,m=misuse,U=u,reward_eligible=False,measurement_record=m,final_output_for_review=response.get('native_parsed') if response else None,token_accounting=telemetry.get('token_accounting'),elapsed_seconds=result.get('elapsed_seconds') if result else None,gpu_seconds=telemetry.get('gpu_seconds'),peak_allocated_bytes=telemetry.get('peak_allocated_bytes'),peak_reserved_bytes=telemetry.get('peak_reserved_bytes'),natural_eos=telemetry.get('natural_eos'),actual_input_tokens=telemetry.get('input_tokens'),raw_files={k:str(v) if v.exists() else None for k,v in files.items()},artifact_sha256={k:s.sha(v) for k,v in files.items() if v.exists()},API_usd=0,semantic_review='separate source-grounded review; not inferred from parser validity'))
starts=len(list(ROOT.rglob('*.started.json')))
assert starts==sum(r['started'] for r in records)<=8
for c in ['A','B']:assert sum(r['started'] for r in records if r['configuration']==c)<=4
summary={'time_jst':datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat(),'head':s.read(OUT/'baseline_current.json')['head'],'plan_identity':plan['identity'],'implementation_identity':plan['implementation_identity'],'old_calls_verified':66,'new_calls':starts,'cumulative_calls':66+starts,'original_cap':140,'this_turn_cap':74,'applied_semantic_revisions':1,'API_usd_this_turn':0,'GPU_generation_seconds':sum(r['gpu_seconds'] or 0 for r in records),'GPU_generation_records_known':sum(r['gpu_seconds'] is not None for r in records),'GPU_residence_seconds':stage['shared_GPU_residence_seconds'],'shared_loads':stage['loads'],'qualification':'NOT_EVALUATED','DeepSeek_calls':len(list((ROOT/'deepseek_flash_off').glob('*.started.json')))+len(list((ROOT/'deepseek_flash_high').glob('*.started.json'))),'next_phase_started':stage['next_phase_started'],'all_eight_slots':records}
s.save(OUT/'engineering_results_private.json',summary)
fields=['local_order','configuration','item_key','started','status','failure_category','not_dispatched_reason','q','m','U','elapsed_seconds','gpu_seconds','peak_allocated_bytes','peak_reserved_bytes','actual_input_tokens','natural_eos','API_usd','request_id','reply_sha256','legal_evidence_identity','messages_identity','schema_identity','input_tokens','total_output_tokens','thinking_tokens','final_tokens','format_tokens']
with (OUT/'eight_slots_private.csv').open('x',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for r in records:
  row={k:r.get(k) for k in fields};row['request_id']=r['request']['request_id'];t=r['token_accounting'] or {}
  row.update({k+'_tokens':t.get(v) for k,v in [('input','input'),('total_output','total_output'),('thinking','thinking'),('final','final'),('format','format')]});w.writerow(row)
print(json.dumps({k:v for k,v in summary.items() if k!='all_eight_slots'},ensure_ascii=False,indent=2))
print(json.dumps([{k:r[k] for k in ['configuration','item_key','started','status','failure_category','q','m','U','gpu_seconds']} for r in records],ensure_ascii=False,indent=2))
