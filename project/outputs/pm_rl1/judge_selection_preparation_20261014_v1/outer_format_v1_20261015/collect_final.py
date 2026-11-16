"""Separate strict historical, offline-derived and new-live results. No inference."""
from pathlib import Path
import csv,sys
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import selection as s
import continue_v1 as c
import outer_format_v1 as interface
from resume_engineering import now,slots

plan=s.load_plan();p=s.read(HERE/'protocol.json');assert p==c.protocol(plan)
root=s.HERE/'live_runs';stage_dir=root/c.SUBDIR/'stage';stage=s.read(stage_dir/'stage_result.json')
attempts={r['request_id']:r for r in stage['attempts']};records=[]
for orig,req in zip(slots(plan),p['requests']):
    assert orig['request_id']==req['original_slot_request_id']
    old=root/orig['candidate']/orig['request_id'];new=root/c.SUBDIR/req['candidate']/req['request_id']
    def read_if(path):return s.read(path) if path.exists() else None
    oldresult=read_if(old.with_suffix('.result.json'));oldraw=read_if(old.with_suffix('.response.json'))
    newresult=read_if(new.with_suffix('.result.json'));newraw=read_if(new.with_suffix('.response.json'))
    derived=read_if(HERE/'derived'/(orig['request_id']+'.derived.json'))
    review=read_if(stage_dir/(req['request_id']+'.review.json'))
    item=plan['items'][orig['item_key']]
    label=p['configs'][orig['candidate']]['label']
    readiness=s.read(s.HERE/'local_engineering_20261015'/('gemma_'+label+'_readiness.json'))
    if newraw:assert newraw['input_tokens']==readiness['request_input_tokens'][orig['request_id']]
    artifacts={}
    for version,base in [('original',old),('new_live',new)]:
        for kind in ('started','raw','response','result'):
            f=base.with_suffix('.'+kind+'.json')
            if f.exists():artifacts[version+'_'+kind]=dict(path=str(f),sha256=s.sha(f))
    if derived:
        f=HERE/'derived'/(orig['request_id']+'.derived.json');artifacts['derived']=dict(path=str(f),sha256=s.sha(f))
    records.append(dict(order=len(records)+1,label=label,candidate=orig['candidate'],item_key=orig['item_key'],
        original_request=orig,new_interface_request=req,original_configuration=plan['configs'][orig['candidate']],new_configuration=p['configs'][orig['candidate']],
        reply=item['reply'],reply_sha256=interface.text_hash(item['reply']),evidence_identity=item['evidence_identity'],
        messages_identity=orig['messages_identity'],schema_identity=orig['schema_identity'],preflight_input_tokens=readiness['request_input_tokens'][orig['request_id']],
        previous_started=old.with_suffix('.started.json').exists(),new_live_started=new.with_suffix('.started.json').exists(),
        previous_strict_result=oldresult['measurement'] if oldresult else None,
        offline_derived_result=derived['evaluation'] if derived else None,new_live_result=newresult,
        new_live_telemetry={k:v for k,v in (newraw or {}).items() if k not in ('raw_text','native_parsed')},
        previous_telemetry={k:v for k,v in (oldraw or {}).items() if k not in ('raw_text','native_parsed')},
        new_final=(newraw or {}).get('native_parsed',{}).get('content'),
        source_review=review,not_dispatched_reason=attempts.get(req['request_id'],{}).get('reason'),artifacts=artifacts))
history=c.reconstruct(plan,p,root)
new_rows=[x for x in records if x['new_live_started']]
valid=[x for x in new_rows if (x['new_live_result'] or {}).get('evaluation',{}).get('measurement',{}).get('measurement_status') in s.VALID]
new_gpu=sum(x['new_live_telemetry'].get('gpu_seconds',0) for x in new_rows)
baseline=s.read(HERE/'baseline.json')
bad=[rel for rel,h in baseline['preserved_files'].items() if not (s.HERE/rel).is_file() or s.sha(s.HERE/rel)!=h]
assert not bad,bad
ledger=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
assert s.sha(ledger)==baseline['paid_ledger_sha256']
assert sum(x['previous_started'] for x in records)==2 and history['started_or_evidenced']==2+len(new_rows)<=8
summary=dict(time_jst=now(),protocol_identity=p['identity'],interface=p['interface'],history=history,
    old_strict=dict(started=2,valid=0,failed=2,formal_scores='all null; immutable'),
    offline_derived=dict(reparsed=2,valid=sum(x['offline_derived_result'] and x['offline_derived_result']['measurement']['measurement_status'] in s.VALID for x in records if x['offline_derived_result']),new_calls=0,new_independent_samples=0),
    new_live=dict(authorized_slots=6,started=len(new_rows),mechanically_valid=len(valid),technical_failed=len(new_rows)-len(valid),not_dispatched=6-len(new_rows)),
    new_API_usd=0,new_GPU_generation_path_seconds=new_gpu,shared_loads=stage['loads'],new_shared_GPU_residence_seconds=stage['shared_residence_seconds'],
    original_files_unchanged=len(baseline['preserved_files']),paid_ledger_sha256=s.sha(ledger),
    semantic_revision_delta=0,semantic_revisions_total=1,no_next_stage=True,qualified=False,rows=records)
s.save(HERE/'results_private.json',summary)
fields=['order','label','item_key','previous_started','new_live_started','original_strict_status','original_q','original_m','original_U','derived_status','derived_q','derived_m','derived_U','new_status','new_q','new_m','new_U','not_dispatched_reason','input_tokens','output_tokens','thinking','final','format','elapsed_seconds','gpu_seconds','peak_allocated_bytes','peak_reserved_bytes','original_request_id','new_request_id']
with (HERE/'eight_slots_private.csv').open('x',newline='') as out:
    w=csv.DictWriter(out,fieldnames=fields);w.writeheader()
    for row in records:
        old=row['previous_strict_result'] or {};derived=(row['offline_derived_result'] or {}).get('measurement',{});new=(row['new_live_result'] or {}).get('evaluation',{}).get('measurement',{})
        data={k:row.get(k) for k in fields};data.update(original_request_id=row['original_request']['request_id'],new_request_id=row['new_interface_request']['request_id'],original_strict_status=old.get('measurement_status'),derived_status=derived.get('measurement_status'),new_status=new.get('measurement_status'))
        for prefix,m in [('original',old),('derived',derived),('new',new)]:
            for name,k in [('q','q'),('m','m'),('U','candidate_utility')]:data[prefix+'_'+name]=m.get(k)
        telemetry=row['new_live_telemetry'];data.update({k:telemetry.get(k) for k in ['input_tokens','output_tokens','gpu_seconds','peak_allocated_bytes','peak_reserved_bytes']})
        data.update({k:(telemetry.get('token_accounting') or {}).get(k) for k in ['thinking','final','format']})
        data['elapsed_seconds']=(row['new_live_result'] or {}).get('elapsed_seconds');w.writerow(data)
print(s.canonical({k:v for k,v in summary.items() if k not in ['rows','interface','history']}))
