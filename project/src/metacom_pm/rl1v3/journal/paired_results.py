"""Read immutable real-worker journals into complete paired development results.

Missing/technical rows remain explicit; this module never grades semantics,
invokes a model, or produces trainable rewards.
"""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def collect(requests, job, output):
    requests,job,output=Path(requests),Path(job),Path(output)
    output.mkdir(parents=True,exist_ok=False)
    rows=[json.loads(x) for x in requests.read_text().splitlines()]
    request_ids={row['request_id'] for row in rows}
    if len(request_ids)!=len(rows):raise ValueError('duplicate requested physical identity')
    events=[json.loads(p.read_text()) for p in sorted(job.glob('[0-9]*.json'))]
    returned={};started=[];load=None
    for e in events:
        if e['event']=='LOAD_OK':load=e['measurement']
        elif e['event']=='REQUEST_START':started.append(e['request_id'])
        elif e['event']=='REQUEST_RETURNED':
            if e['request_id'] in returned:raise ValueError('duplicate physical return')
            returned[e['request_id']]=e['output']
    summary=json.loads((job/'SUMMARY.json').read_text())
    if len(started)!=len(set(started)):raise ValueError('repeated physical start')
    if not set(started)<=request_ids:raise ValueError('unrequested physical start')
    if not set(returned)<=set(started):raise ValueError('return without matching start')
    if len(started)!=summary['physical_calls']:raise ValueError('journal/summary call count mismatch')
    result=[];pairs=defaultdict(list)
    for row in rows:
        key=row['request_id'];value=returned.get(key)
        status='not_started' if key not in started else 'started_no_return'
        if value:status='returned_eos' if value['finish_reason']=='eos' else 'technical_'+value['finish_reason']
        item=dict(domain=row['domain'],task_id=row['task_id'],arm=row['arm'],request_id=key,
            payload_sha256=row['payload_sha256'],renderer_id=row['renderer_id'],
            technical_status=status,input_tokens=len(row['model_input']['input_ids']),
            output_tokens=len(value['token_ids']) if value else None,
            generation_seconds=value['seconds'] if value else None,
            response=value['text'] if value else None,response_sha256=hashlib.sha256(value['text'].encode()).hexdigest() if value else None,
            finish_reason=value['finish_reason'] if value else None,
            evaluation_status='uncertain_pending_evidence_review',reward=None)
        if value and item['input_tokens']!=value['input_tokens']:raise ValueError('input token disagreement')
        result.append(item);pairs[(row['domain'],row['task_id'])].append(item)
    required={'memory':{'OFF','DP','RET','matched-other'},'rs':{'R0','Generic','Legacy-RS','Professional-RAW','Method','F-resident'}}
    complete=[]
    for (domain,task),members in pairs.items():
        complete.append(dict(domain=domain,task_id=task,arms=sorted(x['arm'] for x in members),
            all_arms_requested={x['arm'] for x in members}==required[domain],
            all_eos=all(x['technical_status']=='returned_eos' for x in members),
            outcomes_not_filled_with_zero=True))
    with (output/'PAIRED_RESPONSES_PRIVATE.jsonl').open('x') as f:
        for row in result:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
    text=['# Actual paired smoke outputs — private\n', 'Unqualified development evidence; no formal reward.\n']
    for (domain,task),members in pairs.items():
        text.append(f'\n## {domain} / {task}\n')
        for row in members:
            text.append(f"\n### {row['arm']}\n\nStatus: {row['technical_status']}; input/output tokens {row['input_tokens']}/{row['output_tokens']}; generation seconds {row['generation_seconds']}.\n\n{row['response'] or '[No response; pending]'}\n")
    (output/'PAIRED_RESPONSES_PRIVATE.md').write_text('\n'.join(text))
    report=dict(protocol='pmrl1-j-actual-paired-results-v1',job_status=summary['status'],
        requests=len(rows),physical_calls=summary['physical_calls'],returned=len(returned),
        technical_counts=dict(Counter(x['technical_status'] for x in result)),
        model_load=load,total_wall_seconds=summary['wall_seconds'],
        total_input_tokens=sum(x['input_tokens'] for x in result if x['response'] is not None),
        total_output_tokens=sum(x['output_tokens'] or 0 for x in result),
        total_generation_seconds=sum(x['generation_seconds'] or 0 for x in result),
        pairs=complete,semantic_evaluation='pending_separate_evidence_review',reward_qualified=False,
        source_files_sha256={str(requests):sha(requests),str(job/'SUMMARY.json'):sha(job/'SUMMARY.json')},
        latency_scope='local synchronized calls; excludes client/network/TTS; load and overall job separately reported')
    (output/'MEASUREMENTS.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--requests',required=True);p.add_argument('--job',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();print(json.dumps(collect(a.requests,a.job,a.output),indent=2))
