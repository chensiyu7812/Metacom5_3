"""Read sealed records only. No transport, key, repair, or dispatch operations."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import importlib.util, json, os, csv, shutil

os.umask(0o077)
R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
spec=importlib.util.spec_from_file_location('strict_entry',R/'project/scripts/rl1/124_strict_audit_continuation.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
pr,items,scores,rubric,p,proxy=m.load()
root=Path(pr['run_dir']);out=Path(__file__).resolve().parent
auth=Path(pr['activation_file']).parent
assert (root/'STOP.json').exists() or (root/'CLOSED.json').exists(), 'Never close out an active run'
started,results=proxy.replay(root,pr)
m.d.verify_receipts(proxy,root,pr,started,results)
m.t.require_approval(pr,m.r.read(auth/'APPROVED.json'))
assert m.history(pr)==304
summary=m.summary(pr,proxy,scores)
prev=m.r.read(pr['prior_protocol_path'])
oldroot=Path(pr['prior_run'])
oldstarts,oldresults=p.replay(oldroot,prev)
m.d.verify_receipts(p,oldroot,prev,oldstarts,oldresults)
assert not set(oldstarts)&set(started)
assert len(started)<=6 and len(started)+304<=310
now=datetime.now(timezone.utc).isoformat()

def save(name,x):
    dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with dest.open('x',encoding='utf-8') as f:
        f.write(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2)+'\n')
    dest.chmod(0o600)

def copy(src,name):
    dst=out/name;dst.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with dst.open('xb') as f:f.write(Path(src).read_bytes())
    dst.chmod(0o600)

save('ALL_SLOTS.json',summary)
from deepseek_access import cost_from_usage
rows=[]
for slot in summary['all_original_slots']:
    sid=slot['slot_id'];key=slot['item_key'];result=slot['result'];old=slot['position']<=2
    src=oldroot if old else root
    je=scores[key]['evaluation']
    row=dict(position=slot['position'],item=key,repetition=slot['repetition'],slot_id=sid,
        status=slot['status'],delivery=slot['delivery'],inherited_attempt=old,
        request_id=result['request_identity'] if result else None,
        historical_score_request=scores[key]['request_identity'],reply_sha256=slot['reply_identity'],
        evidence_sha256=slot['evidence_identity'],preliminary_score_sha256=slot['preliminary_score_identity'],
        old_q=je['value']['q'],old_m=je['m'],old_U=je['U'],new_q=None,new_m=None,new_U=None,
        technical_valid=result['technical_valid'] if result else None,
        model_check_unknown=None,model_score_review_unresolved=None,routing=None,old_trigger=None,
        elapsed_seconds=None,prompt_tokens=None,completion_tokens=None,reasoning_tokens=None,
        accounted_upper_usd=None,usage_price_estimate_usd=None,unsettled_usd=None,error=None)
    if result:
        req=m.r.read(src/(sid+'.request.json'))
        pre=m.r.read((m.old.PREP if old else m.PREP)/'outbound_private'/f'{slot["position"]:02d}.json')
        assert req['messages']==pre['messages']
        assert req['schema']==pre['schema' if old else 'local_schema']
        if not old:assert req['wire_body']==pre['wire_body']
        rawfile=src/(sid+'.response.json');raw=m.r.read(rawfile) if rawfile.exists() else None
        if raw:
            msg=raw['choices'][0]['message']
            final=msg.get('content') if old else (msg.get('tool_calls') or [{}])[0].get('function',{}).get('arguments')
            if final is not None:save(f'finals/{slot["position"]:02d}_{key}_r{slot["repetition"]}.txt',final)
            row['finish_reason']=raw['choices'][0].get('finish_reason')
            row['service_model']=raw.get('model');row['fingerprint']=raw.get('system_fingerprint')
            try:row['usage_price_estimate_usd']=cost_from_usage(raw)['usage_price_estimate_usd']
            except (KeyError,ValueError,TypeError):pass
        usage=result.get('usage') or {};ev=result['evaluation'];fin=result['financial']
        row.update(elapsed_seconds=result['elapsed_seconds'],prompt_tokens=usage.get('prompt_tokens'),
            completion_tokens=usage.get('completion_tokens'),reasoning_tokens=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
            accounted_upper_usd=fin['accounted_upper_usd'],unsettled_usd=fin['unsettled_reservation_usd'],
            routing=slot['candidate_routing']['action'],old_trigger=slot['old_reply_only_trigger_on_same_output'],
            error=ev.get('error') or result.get('hard_stop'))
        if result['technical_valid']:
            val=ev['value'];review=val['score_review']
            row.update(model_check_unknown=val['check']['status']=='uncertain',
                model_score_review_unresolved=any(z['status']=='unresolved' for z in review['checks'].values()) or any(z['disposition']=='unresolved' for z in review['findings']),
                score_check_status={k:z['status'] for k,z in review['checks'].items()},
                finding_dispositions=[z['disposition'] for z in review['findings']])
        copy(src/(sid+'.result.json'),f'results/{slot["position"]:02d}_{key}_r{slot["repetition"]}.json')
    else:row['not_dispatched_reason']=m.r.read(root/'STOP.json') if (root/'STOP.json').exists() else 'No dispatch recorded'
    rows.append(row)
save('ITEM_RESULTS.json',rows)
with (out/'ITEM_RESULTS.csv').open('x',encoding='utf-8-sig',newline='') as f:
    fields=list(dict.fromkeys(k for row in rows for k in row));writer=csv.DictWriter(f,fieldnames=fields)
    writer.writeheader();writer.writerows({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()} for row in rows)

fin=pr['financial_baseline'];s=p.s
budget=m.t.budget_class(p)(Path(fin['ledger_path']),trial=fin['financial_trial_identity'],study=m.t.VERSION,
    stage_cap=s.nanodollars('1'),trial_cap=s.nanodollars('3.65'),shared_cap=s.nanodollars('20'),
    baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('.03079930'))
total,trial,reserved,settled=budget._totals(budget.events())
unknown=set(reserved)-set(settled)
newrows=[x for x in rows if not x['inherited_attempt'] and x['status']!='not_dispatched']
def amount(sub,key):return str(sum((Decimal(x[key]) for x in sub if x.get(key) is not None),Decimal(0)))
def counts(sub):return dict(prompt_tokens=sum(x['prompt_tokens'] or 0 for x in sub),
    completion_tokens=sum(x['completion_tokens'] or 0 for x in sub),
    reasoning_tokens_subset=sum(x['reasoning_tokens'] or 0 for x in sub),
    request_elapsed_seconds=sum(x['elapsed_seconds'] or 0 for x in sub),local_gpu_seconds=0)
cost=dict(continuation_accounted_usd=amount(newrows,'accounted_upper_usd'),
    phase_accounted_usd=amount(rows,'accounted_upper_usd'),phase_spent_plus_liability_usd=s.usd(budget.stage_total(reserved,settled)),
    continuation_usage_price_estimate_usd=amount(newrows,'usage_price_estimate_usd'),
    phase_usage_price_estimate_usd=amount(rows,'usage_price_estimate_usd'),invoice_confirmed=False,
    known_unsettled_usd=s.usd(sum(s.nanodollars(reserved[k]['maximum_cost_usd']) for k in unknown)),
    unsettled_reservation_ids=sorted(unknown),trial_accounted_including_liability_usd=s.usd(trial),
    shared_followup_including_liability_usd=s.usd(total-budget.baseline),full_ledger_including_liability_usd=s.usd(total),
    shared_remaining_usd=s.usd(s.nanodollars(20)-(total-budget.baseline)),
    continuation_usage=counts(newrows),whole_phase_usage=counts(rows),
    new_management_requests={n:len(list((root/'management').glob(n+'.started.json'))) for n in ('models','user_balance')},
    ledger_path=fin['ledger_path'],ledger_sha256=m.r.sha(fin['ledger_path']),
    model=pr['config']['model'],published_mapping=pr['config']['published_mapping'],thinking='enabled/high',
    native_single_reserve_usd='.786432',phase_cap_usd='1',trial_cap_usd='3.65',shared_cap_usd='20',
    currency_estimate_not_invoice=True)
save('VALIDATION_AND_COST.json',cost)
save('VERIFICATION.json',dict(utc=now,protocol=pr['identity'],approval_verified=True,
    frozen_code_inputs_history_hashes_unchanged=True,old_STOPs_unchanged=True,
    all_attempts_seals_verified=len(started)+len(oldstarts),exact_previews_verified=len(started)+len(oldstarts),
    original_contract_sha256=m.r.sha(R/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json'),
    baseline=304,new_attempts=len(started),cumulative=304+len(started),capacity=374,
    prior_attempts_never_reissued=True,original_slot_ids_preserved=True,
    new_numeric_scores=0,retries=0,repairs=0,generations=0,training_updates=0,local_gpu_seconds=0,
    development_only=True,independent_human_labels_added=0,offline_preparation_tests=45))
save('CLOSEOUT.json',dict(utc=now,status=summary['status']+'_SCOPE_CLOSED',protocol=pr['identity'],
    new_attempts=len(started),cumulative=304+len(started),active_capacity=374,
    original_phase_attempts=len(started)+2,valid=sum(x['technical_valid'] is True for x in rows),
    failed=sum(x['technical_valid'] is False for x in rows),not_dispatched=sum(x['status']=='not_dispatched' for x in rows),
    remaining_executable_without_new_decision=0,cost=cost,old_scores_preserved=True,
    old_stops_preserved=True,reward_eligible=False,natural_updates=0))
for label,src in [('old',oldroot),('strict',root)]:
    for f in src.iterdir():
        if f.is_file() and not f.name.startswith('.'):copy(f,f'raw/{label}/{f.name}')
for f in (m.old.PREP/'materials').glob('*.txt'):copy(f,'materials/'+f.name)
for name in ['protocol.json','PENDING_EXECUTION_SCOPE.json','CONTINUATION_RULES.json','BUDGET.json','OFFLINE_TESTS.txt','OFFICIAL_DOCS_CHECK.json']:
    if (m.PREP/name).exists():copy(m.PREP/name,'frozen_preparation/'+name)
for name in ['ANALYSIS_RULES.json','EXPOSURE.json','LOCAL_REFERENCE_PROVENANCE.json','FROZEN_RUBRIC_EN.txt']:
    copy(m.old.PREP/name,'frozen_preparation/'+name)
for name in ['RESEARCHER_APPROVAL.txt','APPROVED.json','activation.json']:copy(auth/name,'authorization/'+name)
save('PROVENANCE.json',dict(protocol=pr['identity'],prior_protocol=prev['identity'],
    receipt_hashes={str(f):m.r.sha(f) for src in [oldroot,root] for f in src.iterdir() if f.is_file() and not f.name.startswith('.')},
    inputs_sha256=m.r.sha(m.old.PREP/'inputs_private.json'),historical_scores_sha256=m.r.sha(m.old.PREP/'historical_scores_private.json')))
print(json.dumps(dict(status=summary['status'],new_attempts=len(started),cumulative=304+len(started),cost=cost),ensure_ascii=False,indent=2))
