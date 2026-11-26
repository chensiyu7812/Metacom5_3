#!/usr/bin/env python3
"""Read-only source/provenance replay and private readable traces, without gold."""
import argparse,json,re
from pathlib import Path
from collections import Counter
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once
from metacom_pm.rl1v3.journal.pomdp_memory import query_tokens


def run(cpu,bundle,out):
    cpu,bundle,out=map(Path,(cpu,bundle,out))
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    def rows(p):return [json.loads(x) for x in p.read_text().splitlines()]
    summary=json.loads((cpu/'CPU_SUMMARY_PUBLIC.json').read_text())
    for name,sha in summary['files_sha256'].items():
        if file_sha256(cpu/name)!=sha:raise ValueError('frozen file changed')
    tasks={r['task_id']:r for r in rows(bundle/'TASKS.runtime.jsonl')}
    pools={r['task_id']:r for r in rows(cpu/'LEGAL_POOLS.private.jsonl')}
    traces=rows(cpu/'TRACES.private.jsonl');metrics=[]
    text=['# Real SEARCH / EXPAND / STOP CPU paths (private)',
        '', 'Source text below is not public. No generator/controller was called; all values remain pending.', '']
    delivered=0
    for i,row in enumerate(traces):
        task=tasks[row['task_id']];records={r['record_id']:r for r in pools[row['task_id']]['records']}
        tokens=set(query_tokens(task['query']));initial=set(tokens);last=None;searches=[];source_ids=set();full_ids=set()
        text.extend([f'## Path {i+1} · {row["policy"]}',f'Task: `{row["task_id"]}`','',task['query'],''])
        for j,step in enumerate(row['trace']):
            if last is not None and last!=step['before']:raise ValueError('broken state chain')
            last=step['after']
            action=step['action'];kind=action['action']
            text.extend([f'### Action {j+1}',json.dumps(action,ensure_ascii=False),'',
                f'Delivery tokens: {step["delivered_tokens"]}; wall seconds: {step["elapsed_seconds"]:.6f}', ''])
            if kind=='SEARCH':
                allowed=initial if row['policy']=='SequentialNoText' else tokens
                if not query_tokens(action['query'])<=allowed:raise ValueError('unread query in saved trace')
                searches.append(set(rid for rid,_ in step['private']['ranking']))
            for unit in step.get('delivered',[]):
                record=records[unit['record_id']]
                if unit['reported_at']!=record['reported_at']:raise ValueError('report time changed')
                if unit['scope']=='RAW-SPAN':
                    if unit['span'] not in record['source_refs'] or unit['span']['exact_quote'] not in unit['text']:
                        raise ValueError('source span changed')
                else:
                    if unit['spans']!=record['source_refs'] or not unit['text'].endswith(record['reading_text']):
                        raise ValueError('parent not complete')
                    full_ids.add(record['record_id'])
                source_ids.add(record['record_id']);tokens.update(query_tokens(unit['text']));delivered+=1
                text.extend([f'Scope: {unit["scope"]}; report: {unit["reported_at"]}', '', unit['text'],''])
        if row['reward'] is not None or row['status']!='pending_generation_and_evaluation':raise ValueError('fabricated terminal reward')
        metrics.append(dict(task_id=row['task_id'],policy=row['policy'],accesses=row['accesses'],
            source_sessions_observed=len(source_ids),full_sessions_expanded=len(full_ids),
            query_changed=any(s['action']['action']=='SEARCH' and s['action']['query']!=task['query'] for s in row['trace']),
            second_search_new_parent_hits=len(searches[1]-searches[0]) if len(searches)>1 else None,
            delivered_tokens=row['delivered_tokens'],input_tokens=row['canonical_input_tokens'],
            content_payload_sha256=row['content_payload_sha256']))
        text.extend(['Terminal: pending; reward=null; no generation.',
            f'Canonical input: {row["canonical_input_tokens"]} tokens; total delivery: {row["delivered_tokens"]} tokens.', ''])
    (out/'ALL_80_READABLE_TRACES_PRIVATE.md').write_text('\n'.join(text)+'\n')
    grouped={}
    for policy in sorted({r['policy'] for r in metrics}):
        chosen=[r for r in metrics if r['policy']==policy]
        grouped[policy]=dict(paths=len(chosen),changed_queries=sum(r['query_changed'] for r in chosen),
            observed_sessions=sum(r['source_sessions_observed'] for r in chosen),
            expanded_sessions=sum(r['full_sessions_expanded'] for r in chosen),
            paths_with_new_parent_on_second_search=sum((r['second_search_new_parent_hits'] or 0)>0 for r in chosen),
            new_parent_hits_on_second_search=sum(r['second_search_new_parent_hits'] or 0 for r in chosen))
    bytask={t:{r['policy']:r for r in metrics if r['task_id']==t} for t in tasks}
    public=dict(protocol='pmrl1-j-pomdp-cpu-source-replay-v1',paths=len(traces),tasks=len(tasks),
        source_units_verified=delivered,query_provenance_checked=len(traces),state_chains_checked=len(traces),
        by_policy=grouped,fixed_no_text_identical_payloads=sum(v['FixedTopK']['content_payload_sha256']==v['SequentialNoText']['content_payload_sha256'] for v in bytask.values()),
        sequential_vs_fixed_changed_payloads=sum(v['SequentialRule']['content_payload_sha256']!=v['FixedTopK']['content_payload_sha256'] for v in bytask.values()),
        formal_reward=None,semantic_effect_measured=False,models_called=0,
        source_trace_sha256=file_sha256(cpu/'TRACES.private.jsonl'),
        caveats=['Query changes include capitalization-proxy noise and do not prove useful new evidence.',
            'New source hit is a retrieval observation, not task completion or sequential superiority.',
            'NoText currently collapses to the fixed two-parent program; it is not a trained ablation.',
            'Operational ledger records evidence acquisition, not a calibrated posterior or user-state estimate.'])
    write_json_once(out/'CPU_SOURCE_REPLAY_PUBLIC.json',public)
    write_json_once(out/'PER_PATH_METRICS_PRIVATE.json',metrics)
    write_json_once(out/'MANIFEST.json',dict(files_sha256={p.name:file_sha256(p) for p in out.iterdir()}))
    return public


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('cpu','bundle','out'):p.add_argument('--'+k,required=True)
    print(json.dumps(run(**vars(p.parse_args())),indent=2))
