"""Read completed frozen diagnostic artifacts, export all slots; no transport imports."""
from pathlib import Path
import importlib.util
import sys
import csv
import io
import json
from decimal import Decimal
from datetime import datetime,timezone

R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
sys.path.insert(0,str(R/'project/src'))
from metacom_pm.rl1 import relation_reference as r
P=Path(__file__).resolve().parent
B=P.parent;PREP=B/'relation_reference_preparation_20261021_v2'
spec=importlib.util.spec_from_file_location('entry',R/'project/scripts/rl1/114_run_relation_reference.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
protocol,items,refs,prompt,payloads,runtime_items=entry.load()
root=Path(protocol['run_dir'])
if not (root/'stage_result.json').exists() and not (root/'STOP.json').exists():
    raise SystemExit('Stage still running; no final export')
report=r.summarize(protocol,root,entry.historical_guard(protocol),entry.engine())
for s in report['slots']:
    if s['state'] in ('completed','model_unknown') and s['semantic_review'] is None:
        raise SystemExit('Complete the bound analyst review before export')
r.save_new(P/'runtime_summary.json',report)
fields=['position','material_id','arm','repetition','state','slot_id','request_identity','reply_identity','evidence_identity',
        'q','m','U','model_unknown','technical_valid','reference_uptake','target_relationship','score_basis',
        'elapsed_seconds','input_tokens','output_tokens_including_thinking','thinking_tokens_subset',
        'accounted_upper_usd','unsettled_reservation_usd','failure_or_unstarted_reason','review_note']
rows=[];full=[];metrics={};matrix=[]
for s in report['slots']:
    result=s.get('result') or {};ev=result.get('evaluation') or {};u=result.get('usage') or {};rev=s.get('semantic_review') or {}
    fin=result.get('financial') or {};details=u.get('completion_tokens_details') or {}
    row={k:s.get(k) for k in ['position','material_id','arm','repetition','state','slot_id','reply_identity','evidence_identity']}
    row.update({k:ev.get(k) for k in ['q','m','U','model_unknown','technical_valid']})
    row.update({k:rev.get(k) for k in ['reference_uptake','target_relationship','score_basis']})
    row.update(request_identity=result.get('request_identity'),elapsed_seconds=result.get('elapsed_seconds'),
        input_tokens=u.get('prompt_tokens'),output_tokens_including_thinking=u.get('completion_tokens'),thinking_tokens_subset=details.get('reasoning_tokens'),
        accounted_upper_usd=fin.get('accounted_upper_usd'),unsettled_reservation_usd=fin.get('unsettled_reservation_usd'),
        failure_or_unstarted_reason=result.get('hard_stop') or ev.get('error') or s.get('not_dispatched_reason'),review_note=rev.get('analyst_note_zh'))
    rows.append(row)
    header=f"{s['position']:02d} {s['material_id']} / {s['arm']} / repetition{s['repetition']} / {s['state']}"
    full += ['## '+header,'','完整待评回复：',items[s['material_id']]['reply'],'',
             f"q/m/U: {ev.get('q')} / {ev.get('m')} / {ev.get('U')}",'']
    response=root/(s['slot_id']+'.response.json')
    if response.exists():
        raw=r.read(response)
        final=raw['choices'][0]['message'].get('content')
        finished=raw['choices'][0].get('finish_reason')
        if final is not None:
            r.save_new(P/'public_finals'/f"{s['position']:02d}_{s['material_id']}_{s['arm']}_r{s['repetition']}.txt",final)
            full += [f'原始final（finish_reason={finished}；不含thinking）：','```json',final,'```','']
    full += ['分析者核对（不计独立人评）：',rev.get('analyst_note_zh','未完成/技术失败，不补分。'),'']
    for finding in rev.get('findings',[]):
        full += ['- '+finding['kind']+': '+finding['reason']]
        full += ['  '+x['source_id']+': '+x['quote'] for x in finding['source_checks']]
stream=io.StringIO();w=csv.DictWriter(stream,fieldnames=fields);w.writeheader();w.writerows(rows)
r.save_new(P/'SLOT_RESULTS.csv','\ufeff'+stream.getvalue())
r.save_new(P/'ALL_PUBLIC_FINALS_AND_REVIEW.md','\n'.join(full))
for arm in ('A','B'):
    rs=[x for x in rows if x['arm']==arm]
    metrics[arm]=dict(planned=len(rs),started=sum(x['state']!='not_dispatched' for x in rs),
        technical_delivered=sum(x['technical_valid'] is True for x in rs),model_unknown=sum(x['model_unknown'] is True for x in rs),
        input_tokens=sum(x['input_tokens'] or 0 for x in rs),output_tokens_including_thinking=sum(x['output_tokens_including_thinking'] or 0 for x in rs),
        thinking_tokens_subset=sum(x['thinking_tokens_subset'] or 0 for x in rs),request_seconds=sum(x['elapsed_seconds'] or 0 for x in rs),
        accounted_upper_usd=str(sum((Decimal(x['accounted_upper_usd'] or '0') for x in rs),Decimal(0))))
for key in items:
    cell=dict(material_id=key)
    for arm in ('A','B'):
        cell[arm]=[{k:x[k] for k in ['repetition','state','q','m','U','target_relationship','score_basis']} for x in rows if x['material_id']==key and x['arm']==arm]
    matrix.append(cell)
r.save_new(P/'ARM_METRICS.json',metrics);r.save_new(P/'SCORE_MATRIX.json',matrix)
r.save_new(P/'RESOURCE_COMPARISONS.json',report['resource_comparisons'])
starts=[r.read(f) for f in root.glob('*.started.json')]
close=r.read(root/'financial_closeout.json') if (root/'financial_closeout.json').exists() else None
stop=r.read(root/'STOP.json') if (root/'STOP.json').exists() else None
end=max((r.read(root/(x['slot']['slot_id']+'.result.json'))['elapsed_seconds']+x['started_unix']
         for x in starts if (root/(x['slot']['slot_id']+'.result.json')).exists()),default=None)
start=min((x['started_unix'] for x in starts),default=None)
r.save_new(P/'COST_AND_EXECUTION.json',dict(protocol_identity=protocol['identity'],baseline=225,
    cumulative=report['cumulative'],started=report['started'],stop=stop,financial_closeout=close,
    arms=metrics,wall_seconds=end-start if end is not None and start is not None else None,
    start_utc=datetime.fromtimestamp(start,timezone.utc).isoformat() if start else None,
    end_utc=datetime.fromtimestamp(end,timezone.utc).isoformat() if end else None,
    local_GPU_seconds=0,invoice_confirmed=False,cost_basis='Complete usage billed at peak cache-miss upper tariff; cached input/discount may reduce invoice. Ledger not reduced.',
    new_generations=0,natural_updates=0))
print(json.dumps(dict(started=report['started'],cumulative=report['cumulative'],technical=report['technical_delivered'],unknown=report['model_unknown'],semantic_counts=report['semantic_counts'],metrics=metrics,financial=close),ensure_ascii=False,indent=2))
