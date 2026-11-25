"""Actual fixed-J06 journals, including stopped jobs and observed-only costs."""
import argparse,json
from collections import Counter
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once


def collect(root,catalog):
    root,catalog=Path(root),Path(catalog)
    cat=json.loads(catalog.read_text());jobs=[]
    assert cat['physical_calls']==96 and len(cat['plans'])==6
    for spec in cat['plans']:
        label=spec['label'];plan_path=Path(spec['plan_path']);plan=json.loads(plan_path.read_text())
        assert object_sha256(plan)==spec['plan_object_sha256'] and file_sha256(plan_path)==spec['plan_file_sha256']
        assert file_sha256(plan['requests_path'])==spec['requests_sha256']
        requests=[json.loads(s) for s in Path(plan['requests_path']).read_text().splitlines()]
        auth=json.loads((root/(label+'_AUTHORIZED.json')).read_text())
        assert auth['authorized'] and auth['plan_sha256']==spec['plan_object_sha256'] and auth['max_calls']==16 and auth['max_model_loads']==1
        assert file_sha256(auth['decision_evidence'])==auth['decision_evidence_sha256']
        job=root/(label+'_run1')/('job-'+object_sha256(auth));events=[];previous=None
        for seq,p in enumerate(sorted(job.glob('[0-9]*.json'))):
            e=json.loads(p.read_text());assert e['seq']==seq and e['previous_event_sha256']==previous
            previous=file_sha256(p);events.append(e)
        summary=json.loads((job/'SUMMARY.json').read_text())
        assert events[0]['event']=='RUN_START' and events[0]['approval']==auth
        assert summary['plan_sha256']==spec['plan_object_sha256'] and summary['last_journal_sha256']==previous
        assert summary['wall_seconds']<=plan['global_seconds']==1200
        starts=[e for e in events if e['event']=='REQUEST_START'];returned=[e for e in events if e['event']=='REQUEST_RETURNED']
        assert [e['request_id'] for e in starts]==plan['ordered_request_ids'][:len(starts)]
        assert len(starts)==summary['physical_calls']<=16
        assert [e['request_id'] for e in returned]==[e['request_id'] for e in starts[:len(returned)]]
        measured=[]
        for row,event in zip(requests,returned):
            val=event['output'];payload=row['model_input'];ids=val['token_ids']
            assert row['request_id']==event['request_id'] and object_sha256(payload)==row['payload_sha256']
            assert val['input_tokens']==len(payload['input_ids'])
            eos=payload['decode']['eos_token_id'];eos=[eos] if isinstance(eos,int) else eos
            if val['finish_reason']=='eos':assert ids and ids[-1] in eos and not any(t in eos for t in ids[:-1])
            elif val['finish_reason']=='length':assert len(ids)==payload['decode']['max_new_tokens'] and not any(t in eos for t in ids)
            else:raise ValueError('unknown finish type; inspect actual failure')
            measured.append(dict(request_id=row['request_id'],task_id=row['task_id'],arm=row['arm'],
                input_tokens=val['input_tokens'],output_tokens=len(ids),generation_seconds=val['seconds'],finish_reason=val['finish_reason']))
        loads=[e for e in events if e['event']=='LOAD_OK']
        assert len(loads)<=sum(e['event']=='LOAD_START' for e in events)<=1
        jobs.append(dict(label=label,plan_sha256=spec['plan_object_sha256'],requests_sha256=spec['requests_sha256'],
            status=summary['status'],reason=summary.get('reason'),physical_calls=len(starts),returned_calls=len(returned),
            planned_calls=16,unattempted_calls=16-len(starts),unknown_output_cost_calls=len(starts)-len(returned),
            pending=summary['pending'],length_count=summary['length_count'],loads=len(loads),warmup=0,retries=0,
            input_tokens_observed=sum(m['input_tokens'] for m in measured),output_tokens_observed=sum(m['output_tokens'] for m in measured),
            generation_seconds_observed=sum(m['generation_seconds'] for m in measured),
            load_seconds=sum(e['measurement']['seconds'] for e in loads),job_wall_seconds=summary['wall_seconds'],
            finish_counts=dict(Counter(m['finish_reason'] for m in measured)),per_physical_call=measured,
            journal_summary_sha256=file_sha256(job/'SUMMARY.json')))
    fields=['physical_calls','returned_calls','unattempted_calls','unknown_output_cost_calls','length_count','loads',
        'input_tokens_observed','output_tokens_observed','generation_seconds_observed','load_seconds','job_wall_seconds']
    return dict(protocol='pmrl1-j-joint96-physical-measurements-v1',jobs=jobs,totals={k:sum(j[k] for j in jobs) for k in fields},
        planned_calls=96,catalog_sha256=file_sha256(catalog),warmup=0,retries=0,formal_reward=None,
        cost_scope='Observed HF output costs; stopped/unreturned calls kept separate. Job wall sums are not client latency.')


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('root','catalog','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();r=collect(a.root,a.catalog);write_json_once(Path(a.out),r);print(json.dumps(r['totals'],indent=2))
