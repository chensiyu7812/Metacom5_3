#!/usr/bin/env python3
"""Read-only SC1/SC2 technical measurement; no model/tokenizer/GPU execution.

Reads completed summaries and attested journals, then writes new cost-only
artifacts. Nested grammar timings are not added again to generation/job time.
"""
import argparse,json,math,sys
from collections import Counter
from datetime import datetime
from pathlib import Path

GRAMMAR_MASK_TIMING_SCOPE=(
    'Raw worker cpu_mask_seconds is processor-internal wall time. Its interval includes '
    'int(input_ids[0,-1]) / .item transfer and possible GPU stream synchronization for the previous token. '
    'It excludes the final allowed.to(scores.device) transfer and masked_fill. '
    'It is already nested in generation_seconds; it is not pure CPU matcher overhead '
    'or an independently measured incremental latency.')


def require(ok,message):
    if not ok:raise ValueError(message)


def finite_nonnegative(value,name):
    require(type(value) in (int,float) and math.isfinite(value) and value>=0,'invalid '+name)
    return value


def output_cost(row,output,*,constrained):
    from metacom_pm.rl1v3.generator.limited_run import validate_result
    finish=validate_result(row,output)
    result=dict(input_tokens=output['input_tokens'],output_tokens=len(output['token_ids']),
        generation_seconds=output['seconds'],finish_reason=finish)
    if constrained:
        measurement=output.get('constraint_measurement',{})
        require(type(measurement.get('mask_calls')) is int and measurement['mask_calls']==len(output['token_ids']),
            'mask calls must equal actual output token count')
        mask=finite_nonnegative(measurement.get('cpu_mask_seconds'),'CPU mask seconds')
        require(mask<=output['seconds']+1e-6,'nested CPU mask exceeds generation time')
        result.update(mask_calls=measurement['mask_calls'],grammar_cpu_mask_seconds=mask,
            grammar_mask_timing_scope=GRAMMAR_MASK_TIMING_SCOPE)
    return result


def journal_measure(plan,rows,baseline,job,*,constrained,approval=None):
    from metacom_pm.rl1v3.io import file_sha256,object_sha256
    from metacom_pm.rl1v3.journal.structured_constrained_run import admit as new_admit
    from metacom_pm.rl1v3.journal.structured_run import admit as old_admit
    job=Path(job);require((job/'SUMMARY.json').is_file(),'SUMMARY required; job may still be running')
    previous=None;events=[];source_files={}
    for seq,path in enumerate(sorted(job.glob('[0-9]*.json'))):
        event=json.loads(path.read_text())
        require(event['seq']==seq and event['previous_event_sha256']==previous,'journal chain mismatch')
        require(path.name==f"{seq:03d}-{event['event']}.json",'journal filename/sequence mismatch')
        previous=file_sha256(path);source_files[str(path)]=previous;events.append(event)
    summary=json.loads((job/'SUMMARY.json').read_text());source_files[str(job/'SUMMARY.json')]=file_sha256(job/'SUMMARY.json')
    require(events and events[0]['event']=='RUN_START','missing RUN_START')
    start=events[0];require(start['plan_sha256']==summary['plan_sha256']==object_sha256(plan),'plan identity mismatch')
    require(summary['last_journal_sha256']==previous and summary['job_kind']==plan['job_kind'],'summary/journal mismatch')
    require(summary['baseline_sha256']==plan['baseline_sha256'] and summary['backend']=='hf_real','baseline/backend mismatch')
    auth=start['approval'];(new_admit if constrained else old_admit)(plan,auth)
    if approval is not None:
        require(auth==approval,'approval file differs from RUN_START')
    require(job.name=='job-'+object_sha256(auth),'approval/job directory identity')
    evidence=Path(auth['decision_evidence'])
    require(evidence.is_file() and file_sha256(evidence)==auth['decision_evidence_sha256'],'approval evidence identity')
    source_files[str(evidence)]=file_sha256(evidence)
    require(start['gpu']['gpu_uuid']==baseline['spec']['runtime']['gpu_uuid'],'fixed GPU identity')
    verified=[e for e in events if e['event']=='MODEL_BYTES_VERIFIED']
    require(len(verified)<=1 and all(e['files']==baseline['spec']['model']['files'] for e in verified),'model byte-verification record')
    loads=[e for e in events if e['event']=='LOAD_START'];loaded=[e for e in events if e['event']=='LOAD_OK']
    require(len(loads)<=1 and len(loaded)<=len(loads),'extra load or unmatched load return')
    starts=[e for e in events if e['event']=='REQUEST_START'];returned={};validated={};start_by_id={}
    require([e['request_id'] for e in starts]==plan['ordered_request_ids'][:len(starts)],'request order/retry mismatch')
    require(not starts or len(loaded)==len(verified)==1,'requests before successful load/hash verification')
    by_id={r['request_id']:r for r in rows}
    for ordinal,event in enumerate(starts,1):
        rid=event['request_id'];require(event['physical_ordinal']==ordinal,'physical ordinal mismatch')
        require(event['payload_sha256']==by_id[rid]['payload_sha256'],'started payload mismatch')
        require(event['seq']>loaded[0]['seq'],'request before LOAD_OK')
        start_by_id[rid]=event
    for event in events:
        rid=event.get('request_id')
        if event['event']=='REQUEST_RETURNED':
            require(rid in start_by_id and rid not in returned and event['seq']>start_by_id[rid]['seq'],'unstarted/duplicate return')
            returned[rid]=event
        elif event['event']=='REQUEST_VALIDATED':
            require(rid in returned and rid not in validated and event['seq']>returned[rid]['seq'],'unreturned/duplicate validation')
            validated[rid]=event
    require(summary['physical_calls']==len(starts) and summary['validated_calls']==len(validated),'summary counts mismatch')
    costs={}
    for rid,event in returned.items():
        cost=output_cost(by_id[rid],event['output'],constrained=constrained)
        if rid in validated:require(cost['finish_reason']==validated[rid]['finish_reason'],'finish validation mismatch')
        cost['validated']=rid in validated;costs[rid]=cost
    require(summary['length_count']==sum(c['finish_reason']=='length' and c['validated'] for c in costs.values()),'length denominator mismatch')
    if summary['status']=='FINISHED':require(len(starts)==len(returned)==len(validated)==len(rows),'FINISHED with incomplete request set')
    load_seconds=compile_seconds=load_elapsed=None
    if loaded:
        measurement=loaded[0]['measurement'];load_seconds=finite_nonnegative(measurement['seconds'],'load seconds')
        load_elapsed=(datetime.fromisoformat(loaded[0]['utc'])-datetime.fromisoformat(loads[0]['utc'])).total_seconds()
        require(load_elapsed>=0,'negative load event duration')
        if constrained:
            compile_seconds=finite_nonnegative(measurement.get('grammar_compile_cpu_seconds'),'grammar compile seconds')
            require(compile_seconds<=load_seconds+1e-6,'grammar compile exceeds enclosing load')
    wall=finite_nonnegative(summary['wall_seconds'],'job wall seconds')
    generation=sum(c['generation_seconds'] for c in costs.values())
    require(generation+(load_seconds or 0)<=wall+1e-3,'nested timing accounting exceeds full job')
    report=dict(plan_sha256=object_sha256(plan),approval_sha256=object_sha256(auth),job_status=summary['status'],
        physical_starts=len(starts),returned=len(returned),validated=len(validated),model_loads=len(loads),
        finish_counts=dict(Counter(c['finish_reason'] for c in costs.values())),
        input_tokens=sum(c['input_tokens'] for c in costs.values()),output_tokens=sum(c['output_tokens'] for c in costs.values()),
        load_worker_seconds=load_seconds,load_supervisor_elapsed_seconds=load_elapsed,
        grammar_compile_cpu_seconds=compile_seconds,generation_seconds=generation,job_wall_seconds=wall,
        grammar_mask_calls=sum(c['mask_calls'] for c in costs.values()) if constrained else None,
        grammar_mask_cpu_seconds=sum(c['grammar_cpu_mask_seconds'] for c in costs.values()) if constrained else None,
        grammar_mask_timing_scope=GRAMMAR_MASK_TIMING_SCOPE if constrained else None,
        other_job_seconds=wall-generation-(load_seconds or 0),
        cost_scope='compile nested in load; CPU mask nested in generation; do not add nested times again; not client end-to-end latency')
    return report,costs,source_files


def main(package,run_root,original_root,out):
    package,run_root,original_root,out=map(lambda p:Path(p).resolve(),(package,run_root,original_root,out))
    sys.path.insert(0,str(package/'executor/project/src'))
    from metacom_pm.rl1v3.journal.structured_constrained_run import check
    from metacom_pm.rl1v3.journal.structured_run import check as original_check
    from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
    require(file_sha256(package/'CATALOG_CONSTRAINED.json')=='0574640d2be436b410bc6f5aca236218d4a4f5f4a313f634b5f5b5c2bf08289c','approved package identity')
    reports=[];pairs=[];inputs={}
    for n in (1,2):
        plan_path=package/f'batch-{n:02d}/PLAN_CONSTRAINED.json';plan,rows,baseline=check(plan_path)
        auth_path=run_root/f'SC{n}_AUTHORIZED.json';auth=json.loads(auth_path.read_text())
        job=run_root/f'SC{n}_run1'/('job-'+object_sha256(auth))
        new,costs,files=journal_measure(plan,rows,baseline,job,constrained=True,approval=auth)
        inputs.update(files);inputs[str(plan_path)]=file_sha256(plan_path);inputs[str(auth_path)]=file_sha256(auth_path)
        op,oldrows,oldbaseline=original_check(plan['original_plan_path'])
        old_jobs=list((original_root/f'S{n}_run1').glob('job-*'));require(len(old_jobs)==1,'ambiguous original job')
        old,oldcosts,files=journal_measure(op,oldrows,oldbaseline,old_jobs[0],constrained=False);inputs.update(files)
        old_by_id={r['request_id']:r for r in oldrows}
        for row in rows:
            old_id=row['original_request_id'];require(row['model_input']==old_by_id[old_id]['model_input'],'counterpart input bytes differ')
            before,after=oldcosts.get(old_id),costs.get(row['request_id'])
            pair=dict(task_id=row['task_id'],arm=row['arm'],payload_sha256=row['payload_sha256'],
                old_cost=before,new_cost=after,paired_available=before is not None and after is not None)
            pair['delta']={k:after[k]-before[k] for k in ('input_tokens','output_tokens','generation_seconds')} if pair['paired_available'] else None
            pairs.append(pair)
        reports.append(dict(batch=f'SC{n}',new=new,original=old,
            delta={k:new[k]-old[k] for k in ('input_tokens','output_tokens','generation_seconds','job_wall_seconds')}))
    tokenizer_path=Path(plan['model_path'])/'tokenizer.json'
    require(file_sha256(tokenizer_path)==baseline['spec']['model']['files']['tokenizer.json']['sha256'],'tokenizer bytes')
    metadata=json.loads(tokenizer_path.read_text());suppressed=set(rows[0]['model_input']['decode']['suppress_tokens'])
    tokens=[dict(id=t['id'],content=t['content'],special=t['special']) for t in metadata['added_tokens'] if t['id'] in suppressed]
    require({t['id'] for t in tokens}==suppressed and all(t['special'] for t in tokens),'suppressed token metadata')
    aggregate=dict(protocol='sc36-actual-technical-measurement-v1',batches=reports,
        totals={period:{k:sum(r[period][k] for r in reports) for k in ('physical_starts','returned','validated','input_tokens','output_tokens','generation_seconds','job_wall_seconds')} for period in ('new','original')},
        paired_rows=len(pairs),paired_costs_available=sum(r['paired_available'] for r in pairs),
        delta_scope='Job-total differences can cover unequal returned-call counts; per-request deltas require both actual counterparts.',
        masked_special_tokens=tokens,
        suppression_note='Image/audio modality markers are not JSON structural delimiters or EOS. Finite CPU composition was checked separately; this is not a guarantee for every numerical state.',
        grammar_mask_timing_scope=GRAMMAR_MASK_TIMING_SCOPE,
        nested_timing_not_double_counted=True,semantic_evaluation_included=False,model_loads_by_this_script=0,gpu_calls_by_this_script=0,
        script_sha256=file_sha256(__file__))
    out.mkdir(parents=True,exist_ok=False)
    write_json_once(out/'SC36_TECHNICAL_PUBLIC.json',aggregate)
    write_jsonl_once(out/'SC36_PAIRED_COSTS_PUBLIC.jsonl',pairs)
    write_json_once(out/'SC36_MEASUREMENT_RECEIPT_PRIVATE.json',dict(inputs_sha256=inputs,script_sha256=file_sha256(__file__),
        outputs_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(aggregate,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('package','run-root','original-root','out'):parser.add_argument('--'+name,required=True)
    a=parser.parse_args();main(a.package,a.run_root,a.original_root,a.out)
