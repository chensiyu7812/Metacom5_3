"""Collect original eight slots after continuation. No inference or score repair."""
from pathlib import Path
import sys,csv,json,hashlib
OUT=Path(__file__).resolve().parent;HERE=OUT.parent;sys.path.insert(0,str(HERE))
import selection as s
from resume_engineering import slots,now,reconstruct
plan=s.load_plan();root=HERE/'live_runs';run=root/'continuations/engineering_AB_resume_20261015_02'
stage=s.read(run/'continuation_result.json');a=s.read(OUT/'engineering_amendment_corrected.json')
records=[];attempts={x['request_id']:x for x in stage['attempts']}
for req in slots(plan):
 rid=req['request_id'];candidate=req['candidate'];folder=root/candidate;c=plan['configs'][candidate];item=plan['items'][req['item_key']]
 paths={key:folder/(rid+'.'+key+'.json') for key in ['started','raw','response','result']}
 result=s.read(paths['result']) if paths['result'].exists() else None
 raw=s.read(paths['raw']) if paths['raw'].exists() else None
 response=s.read(paths['response']) if paths['response'].exists() else None
 m=(result or {}).get('measurement',{});status=m.get('measurement_status','not_dispatched');t=response or raw or {}
 failure=None
 if result and status not in s.VALID:
  if t.get('total_seconds',0)>c['timeout_seconds']:failure='technical_timeout'
  elif t.get('natural_eos') is False:failure='non_natural_stop'
  elif status=='parse_or_evidence_failure':failure='parse_or_evidence_failure'
  else:failure='runtime_or_transport_failure'
 if status not in s.VALID:assert all(m.get(k) is None for k in ['q','m','candidate_utility'])
 readiness=s.read(s.HERE/'local_engineering_20261015'/f'gemma_{c["label"]}_readiness.json')
 planned_n=readiness['request_input_tokens'][rid]
 actual_n=t.get('input_tokens')
 if actual_n is not None:assert actual_n==planned_n
 records.append(dict(order=len(records)+1,configuration=c['label'],candidate=candidate,item_key=req['item_key'],request=req,planned_configuration=c,executed_configuration=c if paths['started'].exists() else None,engineering_amendment_sha256=s.sha(OUT/'engineering_amendment_corrected.json'),parent_stage=str(run/'continuation_result.json'),started=paths['started'].exists(),status=status,failure_category=failure,not_dispatched_reason=attempts.get(rid,{}).get('reason') if not result else None,q=m.get('q'),m=m.get('m'),U=m.get('candidate_utility'),measurement=m,reward_eligible=False,reply=item['reply'],reply_sha256=hashlib.sha256(item['reply'].encode()).hexdigest(),evidence_identity=item['evidence_identity'],origin_job_id=item['origin_job_id'],messages_identity=req['messages_identity'],schema_identity=req['schema_identity'],preflight_input_tokens=planned_n,actual_input_tokens=actual_n,full_input_length_matches_preflight=actual_n==planned_n if actual_n is not None else None,elapsed_seconds=(result or {}).get('elapsed_seconds'),gpu_seconds=t.get('gpu_seconds'),peak_allocated_bytes=t.get('peak_allocated_bytes'),peak_reserved_bytes=t.get('peak_reserved_bytes'),tokens=t.get('token_accounting'),natural_eos=t.get('natural_eos'),API_usd=0,final_output=response.get('native_parsed') if response else None,artifacts={k:dict(path=str(v),sha256=s.sha(v)) for k,v in paths.items() if v.exists()}))
h=reconstruct(plan,root)
checks=[s.read(f) | {'receipt_path':str(f)} for d in ['engineering_AB_resume_20261015_01','engineering_AB_resume_20261015_02'] for f in sorted((root/'continuations'/d).glob('gpu_check_*.json'))]
summary=dict(time_jst=now(),plan_identity=plan['identity'],original_implementation_identity=plan['implementation_identity'],engineering_resume_sha256=a['resume_code_sha256'],semantic_revision_delta=0,old_calls=66,attempts_in_original_eight=h['total_started_or_evidenced'],cumulative_calls=h['cumulative_calls'],original_call_cap=140,authorized_pool_cap=8,authorized_cumulative_cap=74,API_usd=0,GPU_generation_seconds_known=sum(x['gpu_seconds'] or 0 for x in records),GPU_generation_time_records=sum(x['gpu_seconds'] is not None for x in records),shared_GPU_residence_seconds=stage['shared_GPU_residence_seconds'],loads=stage['loads'],GPU_checks=len(checks),GPU_idle_checks=sum(x['own_pid'] is None for x in checks),GPU_idle_check_results=[dict(path=x['receipt_path'],index=x['check_index'],start=x['start_jst'],end=x['end_jst'],gpu=x['selected_gpu'],visible_processes=x['visible_processes'],visibility=x['process_visibility'],eligible=x['eligible'],reasons=x['rejection_reasons']) for x in checks if x['own_pid'] is None],qualification='NOT_EVALUATED',next_phase_started=False,all_eight_slots=records)
s.save(OUT/'results_private.json',summary)
fields=['order','configuration','item_key','started','status','failure_category','not_dispatched_reason','q','m','U','actual_input_tokens','preflight_input_tokens','elapsed_seconds','gpu_seconds','peak_allocated_bytes','peak_reserved_bytes','natural_eos','API_usd','request_id','total_output_tokens','thinking_tokens','final_tokens','format_tokens']
with (OUT/'eight_slots_private.csv').open('x',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
 for row in records:
  data={k:row.get(k) for k in fields};data['request_id']=row['request']['request_id'];t=row['tokens'] or {}
  data.update(total_output_tokens=t.get('total_output'),thinking_tokens=t.get('thinking'),final_tokens=t.get('final'),format_tokens=t.get('format'));w.writerow(data)
print(json.dumps({k:v for k,v in summary.items() if k!='all_eight_slots'},ensure_ascii=False,indent=2))
for row in records:print(json.dumps({k:row[k] for k in ['configuration','item_key','started','status','failure_category','q','m','U','gpu_seconds']},ensure_ascii=False))
