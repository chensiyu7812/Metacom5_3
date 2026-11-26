#!/usr/bin/env python3
"""CPU-only FixedWindow identity and all observed G07 EXPAND opportunities.

No new arm is run; no generated latency, action label or training target.
"""
from pathlib import Path
from copy import deepcopy
import argparse,json
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.journal.ge2_retrieval import SharedRetrieval,RetrievalConfig,union_intervals
from metacom_pm.rl1v3.journal import ge2_source_coordinate_audit as A
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
from metacom_pm.rl1v3.generator.g0e import DECODE
from journal_audit_ge2_actual_supply import expected_messages,canonical_text,source_handle,rows

p=argparse.ArgumentParser()
for key in ('collection','bundle','current-review','plan','out'):p.add_argument('--'+key,required=True)
a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False,mode=0o700)
plan=json.loads(Path(a.plan).read_text());source=json.loads(Path(plan['source_config_path']).read_text())
tok=PromptTokenizer(NativeTokenizer(plan['model_path'],source['asset_manifest_path']))
paths=rows(Path(a.collection)/'PATHS_PRIVATE.jsonl')
pools={p['task_id']:p['records'] for p in rows(Path(a.bundle)/'LEGAL_POOLS_PRIVATE.jsonl')}
current={r['task_id']:r for r in rows(a.current_review)}
def payload(task,records,intervals):
    m=expected_messages(task,records,intervals)
    return dict(messages=m,input_ids=list(tok.encode_messages(m)),decode=dict(DECODE))
windows=[];window_private=[];continuations=[];continuation_private=[]
for path in paths:
    if path['public']['method']!='LLMToolAgent':continue
    pub=path['public'];task=path['task'];tid=pub['task_id'];records=pools[tid]
    units=SharedRetrieval(records,RetrievalConfig(backend='bm25')).search(task['query'],unread_only=True)
    intervals={u['record_id']:[[u['start_turn'],u['end_turn']]] for u in units}
    v=payload(task,records,intervals);h=object_sha256(v)
    matches=[x['public']['method'] for x in paths if x['public']['task_id']==tid and x['terminal_request'] is not None and object_sha256(x['terminal_request']['payload'])==h]
    cov=A.strict_supply(path['evaluation']['required_atoms'],records,intervals,task,current[tid])
    row=dict(task_alias=pub['task_alias'],condition='unexecuted_fixed_original_query_Top4_windows',
        actual_methods_with_identical_payload=matches,payload_sha256=h,input_tokens=len(v['input_ids']),
        source_tokens=tok.count(canonical_text(records,intervals)),coverage={k:x for k,x in cov.items() if k!='atoms'},
        generator_calls=0,latency_measured=False,independent_endpoint=False,
        quality_transfer='only existing exact payload observation; no extra replication or online latency advantage')
    windows.append(row);window_private.append(dict(**row,task_id=tid,intervals=intervals,payload=v))
    if pub['task_alias']!='G07':continue
    search=next(e for e in path['events'] if e['event']=='TOOL_RETURNED' and e['action']['action']=='SEARCH')
    obs=search['observation'];byid={r['record_id']:r for r in records};handles={source_handle(r):r['record_id'] for r in records}
    base={handles[r['source_handle']]:r['intervals'] for r in obs['readings']}
    for rank,handle in enumerate(obs['last_hits'],1):
        item=next(h for h in obs['hits'] if h['handle']==handle);rid=handles[item['source_handle']];refs=byid[rid]['source_refs']
        positions={r['turn_index']:i for i,r in enumerate(refs)}
        for scope in ['neighbor','parent']:
            chosen=(refs if scope=='parent' else refs[max(0,positions[item['start_turn']]-1):min(len(refs),positions[item['end_turn']]+2)])
            after=deepcopy(base);after[rid]=union_intervals(after.get(rid,[])+[[chosen[0]['turn_index'],chosen[-1]['turn_index']]])
            v=payload(task,records,after);n=tok.count(canonical_text(records,after));cov=A.strict_supply(path['evaluation']['required_atoms'],records,after,task,current[tid])
            reachable='EXPAND' in obs['action_mask'] and obs['access_budget']['remaining']>=1 and n<=4096 and len(v['input_ids'])+320<=16384 and obs['decision_time']['acquisition_seconds_remaining']>0
            row=dict(task_alias='G07',observed_hit_rank=rank,scope=scope,source_covered=cov['covered_slots'],required=cov['required_slots'],unknown=cov['unknown_slots'],
                available_in_observed_action_mask=reachable,source_tokens=n,input_tokens=len(v['input_ids']),
                observed_remaining_accesses=obs['access_budget']['remaining'],model_calls=0,
                future_expansion_wall_time_not_measured=True,task_gain_not_measured=True,correct_action_label=None)
            continuations.append(row);continuation_private.append(dict(**row,handle=handle,source_record_id=rid,after_intervals=after,payload=v,original_observation_sha256=object_sha256(obs)))
write_jsonl_once(out/'FIXED_WINDOW_PAYLOAD_PUBLIC.jsonl',windows)
write_jsonl_once(out/'FIXED_WINDOW_PAYLOAD_PRIVATE.jsonl',window_private)
write_jsonl_once(out/'G07_OBSERVED_EXPAND_PUBLIC.jsonl',continuations)
write_jsonl_once(out/'G07_OBSERVED_EXPAND_PRIVATE.jsonl',continuation_private)
write_json_once(out/'MANIFEST_PRIVATE.json',dict(script_sha256=file_sha256(__file__),collection_manifest_sha256=file_sha256(Path(a.collection)/'COLLECTION_MANIFEST_PRIVATE.json'),
    files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},new_model_calls=0,new_policy_labels=0))
print(json.dumps(dict(fixed_window_exact_matches={r['task_alias']:r['actual_methods_with_identical_payload'] for r in windows},G07_expansions=continuations),indent=2))
