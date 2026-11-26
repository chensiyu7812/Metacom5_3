#!/usr/bin/env python3
"""Strict coordinates of actual GE2 delivery, after binding to actual G input.

Evaluation side only. Does not query, rerank, change runtime or call a model.
"""
from pathlib import Path
import argparse,html,json
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.journal import ge2_source_coordinate_audit as A
from metacom_pm.rl1v3.journal.ge2_memory import PROTOCOL
from metacom_pm.rl1v3.journal.ge2_retrieval import union_intervals
from metacom_pm.rl1v3.journal.renderer import SYSTEM,NOTES


def rows(path):return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]


def source_handle(record):
    return 'source:'+object_sha256([PROTOCOL,record['record_id'],object_sha256(record)])[:24]


def canonical_text(records, intervals):
    byid={r['record_id']:r for r in records};A.validate_intervals(intervals,byid)
    texts=[]
    for rid in sorted(intervals,key=lambda k:(byid[k]['reported_at']['date'],byid[k]['source_rank'],k)):
        r=byid[rid];spans=union_intervals(intervals[rid])
        if not spans:continue
        refs=[ref for ref in r['source_refs'] if any(lo<=ref['turn_index']<=hi for lo,hi in spans)]
        header=('SOURCE_EXACT historical report; original roles; questions, advice and hypotheses '
                'are not user actions; current validity unknown. Reported '+r['reported_at']['date']+
                '. Source '+source_handle(r)+'.')
        texts.append(header+'\n'+'\n'.join('[turn '+str(ref['turn_index'])+'] '+ref['speaker']+': '+ref['exact_quote'] for ref in refs))
    return '\n\n'.join(texts)


def expected_messages(task,records,intervals):
    text=canonical_text(records,intervals)
    result=[dict(role='system',content=SYSTEM)]
    if text:result.append(dict(role='user',content=NOTES+'<Notes>\n<resource kind="historical_report" head="MS">'+html.escape(text)+'</resource>\n</Notes>'))
    result.extend(dict(role='user' if t['role']=='seeker' else 'assistant',content=t['text']) for t in task['turns'])
    return result


def main():
    p=argparse.ArgumentParser()
    for key in ('collection','bundle','current-review','out'):p.add_argument('--'+key,required=True)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False,mode=0o700)
    pool={p['task_id']:p['records'] for p in rows(Path(a.bundle)/'LEGAL_POOLS_PRIVATE.jsonl')}
    current={r['task_id']:r for r in rows(a.current_review)}
    private=[];public=[];controls=[]
    for path in rows(Path(a.collection)/'PATHS_PRIVATE.jsonl'):
        p=path['public'];task=path['task'];tid=p['task_id'];records=pool[tid];receipt=path['source_receipt'];ev=path['evaluation']
        if receipt is None:
            public.append(dict(task_alias=p['task_alias'],method=p['method'],status='no_terminal_delivery',coverage=None));continue
        intervals=A.direct_intervals(receipt['source_recipe']) if p['method']=='DirectEvidence' else receipt['read_intervals']
        request=path['terminal_request'];payload=request['payload']
        if object_sha256(payload)!=request['binding']['payload_sha256'] or object_sha256(receipt)!=request['binding']['source_receipt_sha256']:
            raise ValueError('original input binding changed')
        if expected_messages(task,records,intervals)!=payload['messages']:
            raise ValueError('actual G message does not match exact source coordinates')
        strict=A.strict_supply(ev['required_atoms'],records,intervals,task,current[tid])
        byid={r['record_id']:r for r in records}
        delivered=[dict(record_id=rid,text='\n'.join(ref['exact_quote'] for ref in byid[rid]['source_refs'] if any(lo<=ref['turn_index']<=hi for lo,hi in spans))) for rid,spans in intervals.items()]
        legacy=A.legacy_supply(ev['required_atoms'],delivered,task['query'])
        base=dict(task_alias=p['task_alias'],method=p['method'],task_id=tid,actual_messages_exact_coordinate_match=True,
            strict={k:v for k,v in strict.items() if k!='atoms'},legacy={k:v for k,v in legacy.items() if k!='atoms'},
            legacy_count_changed=legacy['covered_slots']!=strict['covered_slots'],formal_reward=None)
        public.append(base);private.append(dict(**base,strict_atoms=strict['atoms'],legacy_atoms=legacy['atoms'],read_intervals=intervals))
        handles={source_handle(r):r['record_id'] for r in records}
        for event in path['events']:
            if event['event']!='MODEL_REQUEST_START' or event['role']=='terminal':continue
            req=event['request'];obs=json.loads(req['payload']['messages'][1]['content']);seen={}
            for reading in obs['readings']:
                rid=handles[reading['source_handle']];seen[rid]=reading['intervals']
                if canonical_text([byid[rid]],{rid:reading['intervals']})!=reading['reading_text']:
                    raise ValueError('controller actual observation/source mismatch')
            cov=A.strict_supply(ev['required_atoms'],records,seen,task,current[tid])
            controls.append(dict(task_alias=p['task_alias'],method=p['method'],request_id=req['request_id'],role=event['role'],
                snapshot_sha256=obs['snapshot_sha256'],action_mask=obs['action_mask'],access_budget=obs['access_budget'],
                read_intervals=seen,strict=cov,observation_exact_coordinate_match=True,
                interpretation='source availability before actual control call; not a correct-action label'))
    write_jsonl_once(out/'ACTUAL_SUPPLY_PUBLIC.jsonl',public)
    write_jsonl_once(out/'ACTUAL_SUPPLY_PRIVATE.jsonl',private)
    write_jsonl_once(out/'CONTROL_OBSERVATION_SUPPLY_PRIVATE.jsonl',controls)
    inputs=[Path(a.collection)/'COLLECTION_MANIFEST_PRIVATE.json',Path(a.bundle)/'MANIFEST_PRIVATE.json',Path(a.current_review)]
    summary=dict(endpoints=len(public),actual_terminal_messages_bound=sum(r.get('actual_messages_exact_coordinate_match',False) for r in public),
        control_observations_bound=len(controls),changed_required_coverage_counts=sum(r.get('legacy_count_changed',False) for r in public),
        original_counts_preserved=True,new_model_calls=0,formal_reward=None)
    write_json_once(out/'SUMMARY_PUBLIC.json',summary)
    write_json_once(out/'MANIFEST_PRIVATE.json',dict(input_files_sha256={str(p):file_sha256(p) for p in inputs},
        script_sha256=file_sha256(__file__),files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()}))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
