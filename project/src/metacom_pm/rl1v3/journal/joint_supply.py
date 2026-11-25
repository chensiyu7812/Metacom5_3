"""Source-side supply accounting for the frozen J06 inputs, never G outputs.

The task author checks immutable references only after selection is frozen.
This module cannot score replies or produce qualified task rewards.
"""
from collections import Counter, defaultdict
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from .. import contracts as K
from ..io import canonical_json,decode_contract,file_sha256,object_sha256
from ..sources import source_registry as S
from ..retrieve.v0 import words
from .memory import load_asof
from .rs_tasks import write_once

RAW_PREFIX='SOURCE_EXACT historical session; original speaker attribution; present validity unknown.\n'
ARMS={'STOP':(), 'MS':('MS',), 'RS':('RS',), 'MS_RS':('MS','RS')}


def jl(p):return [json.loads(l) for l in Path(p).read_text().splitlines()]


def checked_files(files,root=None):
    for name,expected in files.items():
        path=Path(name) if root is None else Path(root)/name
        if file_sha256(path)!=expected:raise ValueError('immutable input changed: '+str(path))
    return len(files)


def resource_blocks(messages):
    found=[]
    for m in messages:
        if '<Notes>' in m['content']:
            found.extend(list(ET.fromstring(m['content'][m['content'].index('<Notes>'):])))
    heads=[n.attrib['head'] for n in found]
    if len(heads)!=len(set(heads)):raise ValueError('duplicated delivered head')
    return {n.attrib['head']:n.text or '' for n in found}


def audit(*,bundle,package,receipt,old_smoke,asof,repo,out):
    bundle,package,receipt,old_smoke,asof,repo,out=map(Path,(bundle,package,receipt,old_smoke,asof,repo,out))
    if out.exists():raise FileExistsError('new supply sidecar required')
    manifest=json.loads((bundle/'MANIFEST.json').read_text());freeze=json.loads(receipt.read_text())
    if file_sha256(bundle/'MANIFEST.json')!=freeze['bundle_manifest_sha256']:raise ValueError('source bundle identity changed')
    source_files=checked_files(manifest['files_sha256'],bundle)
    checked_files(manifest['inputs_sha256']);checked_files(manifest['source_documents_sha256'])
    if file_sha256(repo/'project/src/metacom_pm/rl1v3/journal/joint_tasks.py')!=manifest['code_sha256']:
        raise ValueError('frozen source builder code changed')
    regdir=Path(next(p for p in manifest['inputs_sha256'] if p.endswith('/registry.json'))).parent
    registry=S.load(regdir);A=load_asof(asof)
    tasks={r['task_id']:r for r in jl(bundle/'TASKS.runtime.jsonl')}
    envelopes={r['task_id']:r for r in jl(bundle/'TASK_ENVELOPES.private.jsonl')}
    # References are evaluation-side input only: this function never selects a resource.
    evaluations={r['task_id']:r for r in jl(bundle/'EVALSPEC.private.jsonl')}
    rs,=jl(bundle/'RS_PROCEDURE.private.jsonl')
    requests=jl(package/'REQUESTS_ALL.private.jsonl');checks=jl(package/'READ_CHECKS.private.jsonl')
    if len(requests)!=96 or len(checks)!=96 or len(tasks)!=24:raise ValueError('frozen J06 scope required')
    by_check={(r['task_id'],r['arm']):r for r in checks}
    pools={r['task_id']:r for r in jl(package/'LEGAL_POOLS.private.jsonl')}
    base=json.loads(old_smoke.read_text());old_hashes=base['executor_files_sha256']
    checked_files(old_hashes,base['executor_root'])
    plan_ids=[];executor_hashes=None;all_ordered=[]
    for i in range(1,7):
        path=package/f'batch-{i:02d}/PLAN.json';plan=json.loads(path.read_text());checked_files(plan['files_sha256'])
        checked_files(plan['executor_files_sha256'],plan['executor_root'])
        if any(plan['executor_files_sha256'].get(n)!=h for n,h in old_hashes.items()):raise ValueError('old executor hash changed')
        if executor_hashes is not None and plan['executor_files_sha256']!=executor_hashes:raise ValueError('cross-batch executor drift')
        executor_hashes=plan['executor_files_sha256'];all_ordered+=plan['ordered_request_ids']
        if plan['task_manifest_sha256']!=file_sha256(bundle/'TASKS.runtime.jsonl') or plan['review_sha256']!=file_sha256(bundle/'EVALSPEC.private.jsonl'):
            raise ValueError('plan task/reference identity drift')
        plan_ids.append(dict(batch=i,plan_object_sha256=object_sha256(plan),max_calls=plan['max_calls']))
    if all_ordered!=[r['request_id'] for r in requests] or len(set(all_ordered))!=96:raise ValueError('frozen request order/reuse changed')
    rows=[];inventory={};decoder=None
    for tid,task in tasks.items():
        env=envelopes[tid];ev=evaluations[tid];quote=ev['source_binding']['exact_quote']
        prefix=decode_contract(K.PrefixSpec,canonical_json(env['actual_prefix']));registry.context(prefix)
        if prefix.runtime_sha256!=env['asof_runtime_sha256'] or object_sha256(task)!=env['visible_task_sha256']:raise ValueError('visible/asof binding mismatch')
        legal={e.source.session_id:e for e in registry.entries if e.source.owner_id==prefix.owner_id and e.availability_scope=='personal_history' and registry.reason(e.source_id,prefix) is None}
        ledger=A.Ledger(package/'ledgers'/tid.replace(':','-'));records={r.record_id:r for r in ledger.rows}
        if {r.session_id for r in records.values()}!=set(legal) or len(records)!=len(legal):raise ValueError('not the full legal pool')
        for r in records.values():A.verify_record(r,registry)
        pool=pools[tid]
        if set(pool['legal_MS_sessions'])!=set(legal) or pool['legal_MS_count']!=len(legal):raise ValueError('pool receipt mismatch')
        query_words=words(task['query'])
        scores={rid:len(query_words&words(RAW_PREFIX+r.text))/max(1,len(query_words)) for rid,r in records.items()}
        ordered=sorted(records,key=lambda rid:(-scores[rid],-records[rid].reported_at.session_rank,rid))
        inventory[tid]=dict(legal_MS_count=len(legal),legal_RS_count=1,
            pool_contains_reference_quote=any(quote in r.text for r in records.values()),
            source_group_hash=object_sha256(prefix.owner_id)[:16])
        task_requests=[r for r in requests if r['task_id']==tid]
        if len(task_requests)!=4 or {r['arm'] for r in task_requests}!=set(ARMS):raise ValueError('complete paired task required')
        selected_by_arm={}
        for request in task_requests:
            arm=request['arm'];read=by_check[(tid,arm)];payload=request['model_input'];blocks=resource_blocks(payload['messages'])
            if request['payload_sha256']!=object_sha256(payload) or request['request_id']!='jreq:'+object_sha256(payload):raise ValueError('payload identity changed')
            if request['input_ids_sha256']!=object_sha256(payload['input_ids']) or request['input_tokens']!=len(payload['input_ids']):raise ValueError('native input receipt mismatch')
            if decoder is not None and payload['decode']!=decoder:raise ValueError('decode differs across arms')
            decoder=payload['decode']
            visible=[dict(role='user' if t['role']=='seeker' else 'assistant',content=t['text']) for t in task['turns']]
            if payload['messages'][-len(visible):]!=visible:raise ValueError('actual query differs across arms')
            qsha=object_sha256(task['turns'])
            if request['task_query_sha256']!=qsha or read['task_query_sha256']!=qsha or pool['task_query_sha256']!=qsha:raise ValueError('actual retrieval query changed')
            if tuple(read['order'])!=ARMS[arm] or set(blocks)!=set(ARMS[arm]) or [s['head'] for s in read['steps']]!=list(ARMS[arm]):raise ValueError('successful GET/delivery/path mismatch')
            ranked=read['actual_selected_private_rankings']['MS']['ranked']
            if [r['record_id'] for r in ranked]!=ordered or any(r['score']!=scores[r['record_id']] for r in ranked):raise ValueError('full-pool visible-query ranking differs')
            source_ids=[];selected_sessions=[]
            for step in read['steps']:
                if step['head']=='MS':
                    if step['record_ids']!=ordered[:1]:raise ValueError('delivered record is not frozen Top1')
                    selected=records[step['record_ids'][0]]
                    expected_MS='[MS; reported '+(selected.reported_at.date or 'unknown')+']\n'+RAW_PREFIX+selected.text
                    if blocks['MS']!=expected_MS:raise ValueError('whole source unit changed/truncated')
                    selected_sessions.append(selected.session_id);source_ids.append(legal[selected.session_id].source_id)
                    selected_by_arm[arm]=step['record_ids']
                else:
                    if step['record_ids']!=[rs['candidate_id']] or blocks['RS']!=rs['reading_text']:raise ValueError('procedure changed/truncated')
            current=quote in task['query'];ms=quote in blocks.get('MS','')
            atoms=len(ev['personal_fact_references'])
            rows.append(dict(task_id=tid,arm=arm,source_group_hash=inventory[tid]['source_group_hash'],
                demand_stratum=ev['needs_stratum_private'],reference_atom_count=atoms,reference_source_id=ev['source_binding']['source_id'],
                pool_contains_reference_quote=inventory[tid]['pool_contains_reference_quote'],current_contains_reference_quote=current,
                MS_actually_read='MS' in blocks,RS_actually_read='RS' in blocks,MS_delivers_exact_reference_quote=ms,
                reference_quote_available_in_actual_input=current or ms,
                selected_MS_source_ids=source_ids,selected_MS_sessions=selected_sessions,
                selected_MS_record_ids=selected_by_arm.get(arm,[]),payload_resource_order=list(blocks),
                native_input_tokens=request['input_tokens'],incremental_read_tokens={s['head']:s['tokens'] for s in read['steps']},
                private_read_cost=read['private_cost'],online_path_cpu_ms=read['online_path_cpu_ms'],
                quote_sha256=object_sha256(quote),source_only_not_response_judgment=True))
        if selected_by_arm['MS']!=selected_by_arm['MS_RS']:raise ValueError('MS selection differs by same-task arm')
    def counts(group):
        return dict(paths=len(group),MS_GET=sum(r['MS_actually_read'] for r in group),RS_GET=sum(r['RS_actually_read'] for r in group),
            MS_exact_reference_quote_deliveries=sum(r['MS_delivers_exact_reference_quote'] for r in group),
            current_exact_reference_quote_present=sum(r['current_contains_reference_quote'] for r in group),
            reference_quote_available_paths=sum(r['reference_quote_available_in_actual_input'] for r in group),
            reference_atom_slots=sum(r['reference_atom_count'] for r in group),
            source_text_available_atom_slots=sum(r['reference_atom_count'] for r in group if r['reference_quote_available_in_actual_input']),
            native_input_tokens=sum(r['native_input_tokens'] for r in group),
            incremental_MS_tokens=sum(r['incremental_read_tokens'].get('MS',0) for r in group),
            incremental_RS_tokens=sum(r['incremental_read_tokens'].get('RS',0) for r in group))
    summary=dict(protocol='pmrl1-j-joint96-source-supply-only-v1',source_author_role='Source/rule/immutable-input and supply accounting only; no J reply inspection or evaluation qualification.',
        tasks=24,source_groups=6,CPU_paths=96,by_arm={a:counts([r for r in rows if r['arm']==a]) for a in ARMS},
        by_demand_stratum={s:counts([r for r in rows if r['demand_stratum']==s]) for s in sorted({r['demand_stratum'] for r in rows})},
        legal_pool_counts=dict(Counter(str(v['legal_MS_count']) for v in inventory.values())),RS_candidate_count=1,
        pool_contains_all_frozen_reference_quotes=all(v['pool_contains_reference_quote'] for v in inventory.values()),
        frozen_source_bundle_files_checked=source_files,source_builder_code_unchanged=True,
        old_executor_files_byte_identical=len(old_hashes),new_executor_additions=sorted(set(executor_hashes)-set(old_hashes)),
        plan_identities=plan_ids,query_and_pool_same_for_all_four_arms=True,MS_ranking_independently_recomputed=True,
        actual_gets_are_steps_not_private_measurement_rankings=True,whole_selected_MS_and_RS_units_untruncated=True,
        actual_input_resource_order_MS_RS_arm=list(next(r['payload_resource_order'] for r in rows if r['arm']=='MS_RS')),
        GET_order_MS_RS_arm=['MS','RS'],
        incremental_cost_scope='Step tokens are incremental Generator input accounting; first read includes resource wrapper overhead, shared by the second read. They are not alternate procedure sizes.',
        J_generation_outputs_opened=0,generated_responses_scored=0,qualified_reward=None,
        limitations=['Exact reference quote availability proves source-text delivery only, not answer correctness, evidence use or helpfulness.',
            'Six owner source situations produce 24 constructed demand variants; dependence must be preserved.',
            'MS pools contain one or two sessions; RS has one legal procedure. No large-pool or multi-candidate RS-ranking claim.',
            'Declared demand strata are pre-generation source conditions, not compulsory action labels.'])
    write_once(out/'SOURCE_SUPPLY_PRIVATE.jsonl',rows,lines=True)
    write_once(out/'SUMMARY_PUBLIC.json',summary)
    write_once(out/'MANIFEST.json',dict(protocol=summary['protocol'],code_sha256=file_sha256(__file__),
        inputs_sha256={str(p.resolve()):file_sha256(p) for p in [bundle/'MANIFEST.json',receipt,old_smoke,package/'REQUESTS_ALL.private.jsonl',package/'READ_CHECKS.private.jsonl',package/'LEGAL_POOLS.private.jsonl',*[package/f'batch-{i:02d}/PLAN.json' for i in range(1,7)]]},
        outputs_sha256={p.name:file_sha256(p) for p in out.iterdir()}))
    return summary


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    for k in ('bundle','package','receipt','old-smoke','asof','repo','out'):p.add_argument('--'+k,required=True)
    print(json.dumps(audit(**vars(p.parse_args())),ensure_ascii=False,indent=2))
