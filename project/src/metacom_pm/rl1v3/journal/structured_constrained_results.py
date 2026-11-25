"""Collect only attested new calls; preserve the old strict scorer and old output.

Field diagnostics never turn parse failure into a collection of semantic errors.
No fence stripping, text repair, reward qualification or repeat generation.
"""
from collections import Counter
import html,json
from pathlib import Path
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from ..generator import limited_run as L
from .structured_constrained_run import check
from . import structured_learning as S

SCORER_SHA='a83cc1b5960cb419bc893768f190da0664630cdc18c3ee4e9e63ae0a9374d87d'
ORIGINAL_OUTPUT_SHA={1:'23a8987848e18bd3c8495fbb9572fdf6ba0a7f9f54cf31ae5a0b146f840af801',
    2:'b9e85caf2f539e0dfd73292dcb436caa4439ccf368c0fb436ccd5395d24581b1'}
FIELDS=('value_correct','all_required_evidence_supplied','quote_exact_source_substring','quote_supplied',
    'required_literal_in_quote','speaker_source_match','reported_date_source_match','unknown_contract',
    'compliant_abstention_without_required_evidence')


def diagnose(text,reference,*,arm,delivered_text,technical_status):
    out=dict(technical_status=technical_status,strict_score=None,field_diagnostics={k:None for k in FIELDS},
        semantic_fields_assessed=False,format_status='unassessed',reward=None)
    if technical_status!='eos':return out
    score=S.evaluate(text,reference,arm=arm,delivered_text=delivered_text);out['strict_score']=score
    out['format_status']=score['structural_status']
    if score['structural_status']!='pass':return out
    answer=json.loads(text);quote=answer['quote'];expected=reference['value'];ev=reference['evidence']
    unknown=(answer['value']=='unknown' and answer['certainty']=='unknown' and quote==''
        and answer['speaker']=='unknown' and answer['reported_date'] is None)
    available=all(q in delivered_text for q in reference['required_delivered_quotes'])
    d=out['field_diagnostics'];out['semantic_fields_assessed']=True
    d.update(value_correct=answer['value']==expected,all_required_evidence_supplied=available,
        unknown_contract=unknown,compliant_abstention_without_required_evidence=not available and unknown)
    # Empty source fields in a compliant abstention are not attribution errors.
    # Assess attribution only for an actual supported, non-unknown value claim.
    if expected!='unknown' and answer['certainty']=='supported' and answer['value']!='unknown':
        d.update(quote_exact_source_substring=len(quote)>=3 and quote in ev['text'],
            quote_supplied=len(quote)>=3 and quote in delivered_text,
            required_literal_in_quote=reference['required_literal'].casefold() in quote.casefold(),
            speaker_source_match=answer['speaker']==ev['speaker'],reported_date_source_match=answer['reported_date']==ev['reported_date'])
    return out


def collect(plan_path,job,original_outputs,out):
    plan,rows,_=check(plan_path);job,out,original_outputs=map(Path,(job,out,original_outputs))
    if file_sha256(S.__file__)!=SCORER_SHA:raise ValueError('old strict scorer changed')
    if file_sha256(original_outputs)!=ORIGINAL_OUTPUT_SHA[plan['batch_number']]:raise ValueError('original output counterpart changed')
    refs={r['task_id']:r for r in map(json.loads,Path(plan['review_path']).read_text().splitlines())}
    tasks={r['task_id']:r for r in map(json.loads,Path(plan['task_manifest_path']).read_text().splitlines())}
    old=json.loads(original_outputs.read_text());events=[];previous=None
    for seq,path in enumerate(sorted(job.glob('[0-9]*.json'))):
        event=json.loads(path.read_text())
        if event['seq']!=seq or event['previous_event_sha256']!=previous:raise ValueError('journal chain')
        previous=file_sha256(path);events.append(event)
    summary=json.loads((job/'SUMMARY.json').read_text())
    if summary['plan_sha256']!=object_sha256(plan) or summary['last_journal_sha256']!=previous:raise ValueError('new job identity')
    if not events or events[0]['event']!='RUN_START' or events[0]['plan_sha256']!=object_sha256(plan):raise ValueError('new run start')
    starts=[e for e in events if e['event']=='REQUEST_START'];returned={};validated={}
    if [e['request_id'] for e in starts]!=plan['ordered_request_ids'][:len(starts)]:raise ValueError('order/retry')
    for event in events:
        if event['event']=='REQUEST_RETURNED':
            if event['request_id'] in returned:raise ValueError('duplicate return')
            returned[event['request_id']]=event['output']
        if event['event']=='REQUEST_VALIDATED':validated[event['request_id']]=event['finish_reason']
    if not set(returned)<=set(e['request_id'] for e in starts):raise ValueError('unstarted return')
    by_id={r['request_id']:r for r in rows}
    for e in starts:
        if e['payload_sha256']!=by_id[e['request_id']]['payload_sha256']:raise ValueError('payload mismatch')
    results=[];readable=['# Private constrained diagnostic; actual raw replies and unchanged strict score\n']
    for r in rows:
        rid=r['request_id'];ref=refs[r['task_id']];task=tasks[r['task_id']];output=returned.get(rid)
        status='not_returned' if output is None else 'unvalidated_return'
        if rid in validated:
            if L.validate_result(r,output)!=validated[rid]:raise ValueError('result validation mismatch')
            status=validated[rid]
        supplied=html.unescape('\n'.join(m['content'] for m in r['model_input']['messages']))
        binding=dict(task_id=r['task_id'],logical_id=r['logical_id'],arm=r['arm'],request_id=rid,
            original_request_id=r['original_request_id'],payload_sha256=r['payload_sha256'],
            constraint_sha256=plan['constraint_sha256'],evaluator_sha256=SCORER_SHA,reference_sha256=object_sha256(ref),
            task_sha256=object_sha256(task),renderer_id=r['renderer_id'],baseline_sha256=r['baseline_sha256'])
        old_output=old[r['original_request_id']]
        record=dict(binding=binding,endpoint_id='constrained-endpoint:'+object_sha256(binding),
            task_category=task['category'],actual_output=output,output_sha256=object_sha256(output) if output else None,
            old_output_sha256=object_sha256(old_output),
            evaluation=diagnose(output['text'] if output else '',ref,arm=r['arm'],delivered_text=supplied,technical_status=status),
            old_strict_score=S.evaluate(old_output['text'],ref,arm=r['arm'],delivered_text=supplied),reward=None)
        results.append(record)
        readable.extend([f"\n## {r['task_id']} / {r['arm']} / {task['category']}\n",'Question: '+task['question']+'\n',
            'Reference/source (private):\n'+json.dumps(ref,ensure_ascii=False,indent=2)+'\n',
            'Original raw reply:\n'+old_output['text']+'\n','New raw reply:\n'+(output['text'] if output else '[not returned]')+'\n',
            'Evaluation:\n'+json.dumps(record['evaluation'],ensure_ascii=False,indent=2)+'\n'])
    out.mkdir(parents=True,exist_ok=False)
    write_jsonl_once(out/'ENDPOINTS_CONSTRAINED_PRIVATE.jsonl',results)
    (out/'READBACK_CONSTRAINED_PRIVATE.md').write_text(''.join(readable))
    aggregate=dict(protocol='structured-constrained-results-v1',logical=len(results),physical_calls=len(starts),
        technical_counts=dict(Counter(r['evaluation']['technical_status'] for r in results)),
        format_counts=dict(Counter(r['evaluation']['format_status'] for r in results)),
        semantic_fields_assessed=sum(r['evaluation']['semantic_fields_assessed'] for r in results),
        strict_success=sum(bool(r['evaluation']['strict_score'] and r['evaluation']['strict_score']['task_success']) for r in results),
        input_tokens=sum(o['input_tokens'] for o in returned.values()),output_tokens=sum(len(o['token_ids']) for o in returned.values()),
        generation_seconds=sum(o['seconds'] for o in returned.values()),grammar_cpu_mask_seconds=sum(o.get('constraint_measurement',{}).get('cpu_mask_seconds',0) for o in returned.values()),
        grammar_compile_cpu_seconds=sum(e['measurement'].get('grammar_compile_cpu_seconds',0) for e in events if e['event']=='LOAD_OK'),
        formal_reward_qualified=False,scorer_sha256=SCORER_SHA,collector_sha256=file_sha256(__file__),
        plan_sha256=object_sha256(plan),original_output_file_sha256=file_sha256(original_outputs))
    write_json_once(out/'AGGREGATE_CONSTRAINED_PUBLIC.json',aggregate);return aggregate
