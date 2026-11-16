"""Offline export of the completed task-reference diagnostic; no new requests."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import csv
import io
import importlib.util
import json
import sys

R = Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
P = Path(__file__).resolve().parent
PREP = P.parent / 'task_reference_preparation_20261021_v1'
sys.path.insert(0, str(R/'project/src'))
from metacom_pm.rl1 import relation_reference as rr, task_reference as tr

spec = importlib.util.spec_from_file_location('task_entry', R/'project/scripts/rl1/116_run_task_reference.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
protocol, items, refs, cards, prompt, payloads, runtime_items = entry.load()
root = Path(protocol['run_dir'])
if not (root/'stage_result.json').exists() and not (root/'STOP.json').exists():
    raise SystemExit('Stage still running; no final export')
report = tr.summarize(protocol, root, tr.historical_guard(protocol, P.parent), entry.engine())
rr.save_new(P/'runtime_summary.json', report)
rows, finals, metrics, matrix = [], [], {}, []
for slot in report['slots']:
    result = slot.get('result') or {}
    ev = result.get('evaluation') or {}
    usage = result.get('usage') or {}
    fin = result.get('financial') or {}
    row = {k:slot[k] for k in ('position','material_id','arm','repetition','state','slot_id','reply_identity','evidence_identity')}
    row.update({k:ev.get(k) for k in ('q','m','U','model_unknown')})
    row.update(technical_valid=result.get('technical_valid'), request_identity=result.get('request_identity'),
        elapsed_seconds=result.get('elapsed_seconds'), input_tokens=usage.get('prompt_tokens'),
        output_tokens_including_thinking=usage.get('completion_tokens'),
        thinking_tokens_subset=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens'),
        cache_hit_tokens=usage.get('prompt_cache_hit_tokens'),
        accounted_upper_usd=fin.get('accounted_upper_usd'),
        unsettled_reservation_usd=fin.get('unsettled_reservation_usd'),
        failure_or_unstarted_reason=result.get('hard_stop') or ev.get('error') or slot.get('not_dispatched_reason'),
        reward_eligible=False)
    rows.append(row)
    rawpath = root/(slot['slot_id']+'.response.json')
    raw = rr.read(rawpath) if rawpath.exists() else None
    final = raw['choices'][0]['message'].get('content') if raw else None
    title = f"{slot['position']:02d} {slot['material_id']} / {slot['arm']} / r{slot['repetition']} / {slot['state']}"
    finals.extend(['## '+title,'','完整待评回复：',items[slot['material_id']]['reply'],'',
        f"q/m/U: {ev.get('q')} / {ev.get('m')} / {ev.get('U')}",
        f"来源身份：{slot['evidence_identity']}；请求身份：{result.get('request_identity')}",''])
    if final is not None:
        name=f"{slot['position']:02d}_{slot['material_id']}_{slot['arm']}_r{slot['repetition']}.txt"
        rr.save_new(P/'public_finals'/name, final)
        finals.extend(['完整原final（未从thinking提取或改写）：','```json',final,'```',''])
    else:
        finals.extend(['无完整final；不填分、不读取未完成thinking补答案。',''])
stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
rr.save_new(P/'SLOT_RESULTS.csv','\ufeff'+stream.getvalue())
rr.save_new(P/'ALL_PUBLIC_FINALS.md','\n'.join(finals))
for arm in ('A','B'):
    rs=[x for x in rows if x['arm']==arm]
    metrics[arm]=dict(planned=len(rs),started=sum(x['state']!='not_dispatched' for x in rs),
        technical_delivered=sum(x['technical_valid'] is True for x in rs),
        model_unknown=sum(x['model_unknown'] is True for x in rs),
        numerical_scored=sum(x['state']=='completed' for x in rs),
        input_tokens=sum(x['input_tokens'] or 0 for x in rs),
        output_tokens_including_thinking=sum(x['output_tokens_including_thinking'] or 0 for x in rs),
        thinking_tokens_subset=sum(x['thinking_tokens_subset'] or 0 for x in rs),
        cache_hit_tokens=sum(x['cache_hit_tokens'] or 0 for x in rs),
        request_seconds=sum(x['elapsed_seconds'] or 0 for x in rs),
        accounted_upper_usd=str(sum((Decimal(x['accounted_upper_usd'] or '0') for x in rs),Decimal(0))))
for key in items:
    matrix.append(dict(material_id=key, **{arm:[{k:x[k] for k in ('position','repetition','state','q','m','U')} for x in rows if x['material_id']==key and x['arm']==arm] for arm in ('A','B')}))
rr.save_new(P/'ARM_METRICS.json',metrics)
rr.save_new(P/'SCORE_MATRIX.json',matrix)
rr.save_new(P/'RESOURCE_COMPARISONS.json',report['resource_comparisons'])
starts=[rr.read(f) for f in root.glob('*.started.json')]
start=min((x['started_unix'] for x in starts),default=None)
end=max((rr.read(root/(x['slot']['slot_id']+'.result.json'))['elapsed_seconds']+x['started_unix'] for x in starts if (root/(x['slot']['slot_id']+'.result.json')).exists()),default=None)
close=rr.read(root/'financial_closeout.json') if (root/'financial_closeout.json').exists() else None
rr.save_new(P/'COST_AND_EXECUTION.json',dict(protocol_identity=protocol['identity'],baseline=253,
    cumulative=report['cumulative'],started=report['started'],stop=report['stop'],financial_closeout=close,
    arms=metrics,wall_seconds=end-start if end is not None and start is not None else None,
    start_utc=datetime.fromtimestamp(start,timezone.utc).isoformat() if start else None,
    end_utc=datetime.fromtimestamp(end,timezone.utc).isoformat() if end else None,
    local_GPU_seconds=0,new_generations=0,natural_updates=0,invoice_confirmed=False,
    cost_basis='Complete usage, peak cache-miss upper tariff; no invoice confirmation or ledger reduction.'))
print(json.dumps(dict(started=report['started'],cumulative=report['cumulative'],technical=report['technical_delivered'],unknown=report['model_unknown'],metrics=metrics,financial=close),ensure_ascii=False,indent=2))
