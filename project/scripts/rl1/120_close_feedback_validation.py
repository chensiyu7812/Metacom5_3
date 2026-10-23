#!/usr/bin/env python3
"""Read-only experimental closeout: no transport, credentials, or new scores.

Recompute counts/cost/utility directly from immutable responses and ledger.
Source interpretation is a separate, attributed local analysis, not new gold.
"""
from collections import Counter
from datetime import datetime,timezone
from decimal import Decimal
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys

PROJECT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('feedback_entry',PROJECT/'scripts/rl1/119_run_feedback_validation.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
from metacom_pm.rl1.evidence import evidence_turns


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as f:f.write(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def close(out):
    pr,items,prompt=entry.load();p=entry.engine();root=Path(pr['run_dir'])
    if not (root/'CLOSED.json').exists() and not (root/'STOP.json').exists():raise ValueError('run not closed; no interim closeout')
    started,results=p.replay(root,pr);entry.d.verify_receipts(p,root,pr,started,results)
    assert entry.w.historical_guard(pr,entry.BASE)==285
    out.mkdir(mode=0o700)
    original=Path(pr['financial_baseline']['ledger_path']).read_bytes()
    assert hashlib.sha256(original[:pr['financial_baseline']['ledger_bytes']]).hexdigest()==pr['financial_baseline']['ledger_sha256']
    events=[json.loads(x) for x in original.splitlines()];reserved={};settled={}
    for ev in events:
        if ev['event']=='RESERVED':
            assert ev['reservation_id'] not in reserved;reserved[ev['reservation_id']]=ev
        if ev['event']=='SETTLED':
            assert ev['reservation_id'] not in settled;settled[ev['reservation_id']]=ev
    assert set(settled)<=set(reserved)
    own={k:v for k,v in reserved.items() if v.get('binding',{}).get('study')==pr['version']}
    assert set(started)<=set(own)
    def amount(k,v):return Decimal(settled[k]['actual_cost_usd'] if k in settled else v['maximum_cost_usd'])
    stage_paid=sum((Decimal(settled[k]['actual_cost_usd']) for k in own if k in settled),Decimal(0))
    outstanding=sum((Decimal(v['maximum_cost_usd']) for k,v in own.items() if k not in settled),Decimal(0))
    trial=sum((amount(k,v) for k,v in reserved.items() if v.get('selection_trial')==pr['financial_baseline']['financial_trial_identity']),Decimal(0))
    total=Decimal('.03079930')+sum((amount(k,v) for k,v in reserved.items()),Decimal(0))
    assert stage_paid+outstanding<=Decimal('2') and trial<=Decimal('3.65')
    assert total-Decimal('1.50724291')<=20
    summary=entry.w.summarize(pr,root,p)
    writes={};tokens=Counter();latencies=[];counts=Counter();recomputed=[]
    for slot in pr['schedule']:
        sid=slot['slot_id'];res=results.get(sid)
        if res is None:continue
        counts[slot['component']]+=1;latencies.append(res['elapsed_seconds'])
        rawpath=root/(sid+'.response.json')
        if not rawpath.exists():continue
        raw=json.loads(rawpath.read_text());usage=raw.get('usage')
        if usage and all(type(usage.get(k)) is int and usage[k]>=0 for k in ('prompt_tokens','completion_tokens')):
            estimate=Decimal(usage['prompt_tokens'])*Decimal('.0000003')+Decimal(usage['completion_tokens'])*Decimal('.0000012')
            if sid in settled:assert estimate==Decimal(settled[sid]['actual_cost_usd'])
            for k in ('prompt_tokens','completion_tokens'):tokens[k]+=usage[k]
            thinking=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
            if type(thinking) is int:tokens['reasoning_tokens_subset']+=thinking
        # Only the complete final is extracted; reasoning remains in raw receipts.
        choice=raw.get('choices',[{}])[0];final=(choice.get('message') or {}).get('content')
        if final is not None:write(out/'finals'/(f"{slot['position']:02d}_{slot['material_id']}_{slot['component']}.txt"),final)
        if res['technical_valid']:
            if slot['component']=='audit':
                again=entry.w.f.evaluate_audit(raw,items[slot['item_key']],p)
            else:again=p.evaluate(items[slot['item_key']],'joint',raw,pr['identity'],sid)
            assert again==res['evaluation']
            if slot['component']!='audit':
                val=again['value'];unknown=val['status']=='uncertain'
                q=None if unknown else val['q'];m=None if unknown else max((a['severity'] for a in val['assessments']),default=0)
                utility=None if unknown else float(Decimal(q)/4-Decimal(str(m)))
                assert (q,m,utility)==(again['q'],again['m'],again['U'])
                recomputed.append(dict(slot_id=sid,q=q,m=m,U=utility))
        req=json.loads((root/(sid+'.request.json')).read_text());data=json.loads(req['messages'][1]['content'])
        assert data['legal_evidence']==items[slot['item_key']]['evidence'] and data['reply']==items[slot['item_key']]['reply']
        allowed={'legal_evidence','reply','response_units'}
        if slot['component']!='joint':allowed.add('preliminary_score')
        if slot['component']=='repair':allowed.add('machine_audit')
        assert set(data)==allowed
        writes[sid]=dict(request_hash=entry.r.sha(root/(sid+'.request.json')),response_hash=entry.r.sha(rawpath),
            result_hash=entry.r.sha(root/(sid+'.result.json')),original_full_sources_preserved=True)
    for cid in ('V1','V2','V3','V4'):
        evidence=items[cid+'_OFF']['evidence'];lines=[f'{cid} complete legal evidence; date {evidence.get("current_date")}']
        lines.extend(f"[{sid}] {turn['role']}: {turn['text']}" for sid,turn in evidence_turns(evidence).items())
        for side in ('OFF','ON'):lines.extend(['',cid+'_'+side+' COMPLETE REPLY',items[cid+'_'+side]['reply']])
        write(out/'sources'/(cid+'_FULL_SOURCE_AND_REPLIES.txt'),'\n\n'.join(lines))
    starts_at=[x['started_unix'] for x in started.values()]
    finish=root/'CLOSED.json' if (root/'CLOSED.json').exists() else root/'STOP.json'
    elapsed_wall=finish.stat().st_mtime-min(starts_at) if starts_at else 0
    validation=dict(checked_at=datetime.now(timezone.utc).isoformat(),protocol_identity=pr['identity'],baseline=285,
        actual_started=len(started),cumulative=285+len(started),calls_by_component=dict(counts),slots=24,
        old_history_and_stops_unchanged=True,original_financial_prefix_preserved=True,
        all_finished_raw_finals_reparsed=True,scored_utility_recomputed=recomputed,input_bindings=writes,
        stage_settled_upper_usd=str(stage_paid),stage_unsettled_usd=str(outstanding),api_trial_usd=str(trial),
        shared_followup_usd=str(total-Decimal('1.50724291')),full_ledger_usd=str(total),
        known_global_unsettled=list(set(reserved)-set(settled)),tokens=dict(tokens),
        request_elapsed_sum_seconds=sum(latencies),elapsed_wall_seconds=elapsed_wall,
        price_basis='official checked peak/cache-miss input USD0.30 and output USD1.20 per million; accounting upper, not invoice',
        thinking_included_not_added_twice=True,ledger_sha256=hashlib.sha256(original).hexdigest(),
        independent_human_reviews=0,natural_updates=0,reward_eligible=False)
    write(out/'ALL_SLOTS.json',summary);write(out/'VALIDATION_AND_COST.json',validation)
    write(out/'ORIGINAL_INPUTS.json',items)
    write(out/'RAW_PROVENANCE.json',dict(run_dir=str(root),source_files={str(x):entry.r.sha(x) for x in root.rglob('*') if x.is_file()}))
    shutil.copy2(entry.PREP/'MATERIAL_COUNT_AUDIT.json',out/'MATERIAL_COUNT_AUDIT.json')
    print(json.dumps({k:validation[k] for k in ('actual_started','cumulative','calls_by_component','stage_settled_upper_usd','stage_unsettled_usd','api_trial_usd','tokens','request_elapsed_sum_seconds','elapsed_wall_seconds')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    os.umask(0o077);ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=entry.BASE/'feedback_validation_results_20261022_v1')
    close(ap.parse_args().out)
