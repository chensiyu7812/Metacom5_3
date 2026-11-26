#!/usr/bin/env python3
"""Same-pool GE2 CPU retrieval comparison; no models or policy reference input."""
import argparse,json,time,statistics
from collections import defaultdict
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,object_sha256
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
from metacom_pm.rl1v3.journal import ge2_sources as S,renderer
from metacom_pm.rl1v3.journal.ge2_retrieval import SharedRetrieval,RetrievalConfig,covered,union_intervals
from metacom_pm.rl1v3.journal.ge2_memory import GE2Episode

def intervals(units):
    out={}
    for u in units:
        rid=u['record_id'];out[rid]=union_intervals(out.get(rid,[])+[[u['start_turn'],u['end_turn']]])
    return out

def materialize(records,selected):
    return [dict(record_id=r['record_id'],text='\n'.join(s['exact_quote'] for s in r['source_refs'] if covered(s['turn_index'],selected[r['record_id']])))
        for r in records if r['record_id'] in selected]

def main():
    p=argparse.ArgumentParser()
    for n in ('bundle','config-freeze','base-plan','asset-manifest','out'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--ranking-cache',type=Path)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
    freeze=json.loads(a.config_freeze.read_text())
    assert freeze['runtime_backend']=='bm25' and freeze['top_k']==4 and freeze['window_radius']==1
    registry=S.load_factory_inputs(a.bundle/'SOURCE_CONFIG_PRIVATE.json')
    base=json.loads(a.base_plan.read_text());baseline=json.loads(Path(base['baseline_path']).read_text())
    native=PromptTokenizer(NativeTokenizer(base['model_path'],a.asset_manifest))
    tasks=S.rows(a.bundle/'CPU_TASKS_46.runtime.jsonl')+S.rows(a.bundle/'TASKS.runtime.jsonl')
    envs={r['task_id']:r for name in ('CPU_ENVELOPES_46_PRIVATE.jsonl','TASK_ENVELOPES.private.jsonl') for r in S.rows(a.bundle/name)}
    # Source ports and rankings have no evaluation arguments.
    ranked=[];pools=[]
    if a.ranking_cache:
        manifest=json.loads((a.ranking_cache/'MANIFEST_PRIVATE.json').read_text())
        for name in ('RANKINGS_PRIVATE.jsonl','LEGAL_POOLS_PRIVATE.jsonl'):
            if file_sha256(a.ranking_cache/name)!=manifest['files'][name]:raise ValueError('diagnostic ranking cache identity')
        ranked=S.rows(a.ranking_cache/'RANKINGS_PRIVATE.jsonl');pools=S.rows(a.ranking_cache/'LEGAL_POOLS_PRIVATE.jsonl')
        if [r['task_id'] for r in pools]!=[t['task_id'] for t in tasks]:raise ValueError('diagnostic task inventory changed')
        if any(r['query_sha256']!=object_sha256(t['query']) for r in ranked for t in tasks if r['task_id']==t['task_id']):raise ValueError('diagnostic query changed')
    for index,task in enumerate([] if a.ranking_cache else tasks):
        prepared,bound=S.prepare_source_port(task,envs[task['task_id']],registry,native,baseline,a.out/'ledgers')
        _,prefix,snapshot,tok,port,binding,records=prepared
        pools.append(dict(task_id=task['task_id'],records=records,source_port_binding_sha256=binding.sha256))
        ids={r['record_id'] for r in records}
        def legal(r):
            return r['record_id'] in ids and bound.reason(bound.entry(r['owner_id'],r['parent_session_id']).source_id,prefix) is None
        for backend in ('time_lexical','bm25'):
            config=RetrievalConfig(backend=backend)
            start=time.perf_counter();retrieval=SharedRetrieval(records,config);index_seconds=time.perf_counter()-start
            start=time.perf_counter();first=retrieval.search(task['query']);cold=time.perf_counter()-start
            hot=[]
            for _ in range(3):
                start=time.perf_counter();again=retrieval.search(task['query']);hot.append(time.perf_counter()-start)
                assert again==first
            initial=intervals(first);second=retrieval.search(task['query'],read_intervals=initial,unread_only=True)
            continued=intervals(first+second)
            full={u['record_id']:[[records_by['source_refs'][0]['turn_index'],records_by['source_refs'][-1]['turn_index']]]
                for u in first for records_by in records if records_by['record_id']==u['record_id']}
            ep=GE2Episode(task=task,records=records,tokenizer=tok,legal=legal,episode_nonce=object_sha256([task['task_id'],backend]),retrieval_config=config)
            ep.step(dict(action='SEARCH',query=task['query'],unread_only=True))
            assert ep.read_intervals==initial
            ep.step(dict(action='SEARCH',query=task['query'],unread_only=True))
            assert ep.read_intervals==continued
            variants={}
            for name,selected in [('current',{}),('first_unit',intervals(first[:1])),('first_search_top4',initial),
                ('same_query_second_search',continued),('first_top4_complete_parents',full),('entire_legal_pool',{r['record_id']:[[r['source_refs'][0]['turn_index'],r['source_refs'][-1]['turn_index']]] for r in records})]:
                views=ep.render_intervals(selected);tokens=views[0].tokens if views else 0
                try:
                    packet=tok.make_packet(views);input_tokens=len(packet.input_ids);payload_sha=packet.payload_sha256
                except ValueError as error:
                    if not str(error).startswith('capacity:'):raise
                    messages,_=renderer.project_messages(dict(visible_prefix=dict(turns=task['turns']),readings=S.plain(views)),tok)
                    input_tokens=len(tok.encode_messages(messages));payload_sha=None
                variants[name]=dict(intervals=selected,delivered=materialize(records,selected),source_tokens=tokens,
                    input_tokens=input_tokens,capacity_reachable=tokens<=4096 and input_tokens+320<=16384,
                    views_sha256=object_sha256(S.plain(views)),payload_sha256=payload_sha)
            ranked.append(dict(task_id=task['task_id'],cohort='original46' if index<46 else 'selected8',backend=backend,
                query_sha256=object_sha256(task['query']),source_count=len(records),source_port_binding_sha256=binding.sha256,
                first_units=first,second_units=second,variants=variants,trace=ep.receipt(),
                cpu_seconds=dict(index=index_seconds,first_search=cold,warm_search_median=statistics.median(hot)),
                timing_scope='CPU ranking only; no model, controller, terminal or user-facing latency'))
    S.write_once(a.out/'RANKINGS_PRIVATE.jsonl',ranked,jsonl=True)
    S.write_once(a.out/'LEGAL_POOLS_PRIVATE.jsonl',pools,jsonl=True)
    # Evaluation is a post-ranking pass, never a retrieval input.
    evals={r['task_id']:r for r in S.rows(a.bundle/'CPU_EVAL_46_PRIVATE.jsonl')}
    selected={r['task_id']:r for r in S.rows(a.bundle/'EVALSPEC.private.jsonl')}
    taskmap={r['task_id']:r for r in tasks};poolmap={r['task_id']:r for r in pools}
    diagnostics=[];location_checks=[]
    for row in ranked:
        task=taskmap[row['task_id']]
        if row['cohort']=='selected8':
            ev=selected[row['task_id']];atoms=ev['required_atoms'];origin=ev['origin'];channel=ev['channel']
        else:
            ev=evals[row['task_id']];origin=ev['origin'];original=ev['original_evaluation']
            atoms,checks=S.normalize_atoms(origin,original,poolmap[row['task_id']]['records'],task['turns'])
            location_checks.append(dict(task_id=row['task_id'],checks=checks))
            channel='fact' if origin=='official30' or original['goal_kind']=='fact' else 'constructed_support'
        counts={name:S.evaluate_supply(atoms,value['delivered'],task['query']) for name,value in row['variants'].items()}
        diagnostics.append(dict(task_id=row['task_id'],cohort=row['cohort'],origin=origin,channel=channel,backend=row['backend'],
            coverage=counts,cost={name:{k:v for k,v in value.items() if k in ('source_tokens','input_tokens','capacity_reachable')} for name,value in row['variants'].items()},
            cpu_seconds=row['cpu_seconds'],source_count=row['source_count'],task_success=None,
            time_scope='original_official_end_history' if origin=='official30' else 'actual_pre_supporter_prefix'))
    S.write_once(a.out/'SUPPLY_DIAGNOSTICS_PRIVATE.jsonl',diagnostics,jsonl=True)
    S.write_once(a.out/'SOURCE_LOCATION_CHECKS_PRIVATE.jsonl',location_checks,jsonl=True)
    aggregate=[]
    for cohort,origin,channel,backend in sorted({(r['cohort'],r['origin'],r['channel'],r['backend']) for r in diagnostics}):
        group=[r for r in diagnostics if (r['cohort'],r['origin'],r['channel'],r['backend'])==(cohort,origin,channel,backend)]
        variants={}
        for name in group[0]['coverage']:
            variants[name]=dict(tasks=len(group),required_slots=sum(r['coverage'][name]['required_slots'] for r in group),
                evaluable_source_slots=sum(r['coverage'][name]['evaluable_source_slots'] for r in group),covered_slots=sum(r['coverage'][name]['covered_slots'] for r in group),
                unknown_slots=sum(r['coverage'][name]['unknown_slots'] for r in group),
                source_complete_tasks=sum(r['coverage'][name]['complete_all_required'] for r in group),
                capacity_reachable=sum(r['cost'][name]['capacity_reachable'] for r in group),
                source_tokens=sum(r['cost'][name]['source_tokens'] for r in group),max_source_tokens=max(r['cost'][name]['source_tokens'] for r in group))
        aggregate.append(dict(cohort=cohort,origin=origin,channel=channel,backend=backend,variants=variants,
            cpu_seconds={key:sum(r['cpu_seconds'][key] for r in group) for key in group[0]['cpu_seconds']}))
    S.write_once(a.out/'COUNTS_PUBLIC.json',dict(protocol='ge2-cpu-source-comparison-v1',original_tasks=46,selected_tasks=8,
        selected_overlap_official_tasks=3,additional_old_joint=2,additional_true_prefix_natural=3,groups=aggregate,
        source_only=True,task_success=None,model_calls=0,sealed_body_read=False,ranking_config_sha256=file_sha256(a.config_freeze),
        notes=['Current/first unit/Top4-window/second same-query/whole-parent are different supply quantities.',
            'Entire legal pool is source-availability only, often exceeds budget; not a policy.',
            'Official QA retains end-history scope; no strict-date leakage claim.',
            'Exact source group coverage is not semantic answer success; unknown groups are not false or zero.']))
    S.write_once(a.out/'MANIFEST_PRIVATE.json',dict(inputs={str(p):file_sha256(p) for p in (a.bundle/'MANIFEST_PRIVATE.json',a.bundle/'TASKS.runtime.jsonl',a.bundle/'EVALSPEC.private.jsonl',a.config_freeze,a.base_plan,a.asset_manifest)},ranking_cache=None if a.ranking_cache is None else str(a.ranking_cache),files={str(p.relative_to(a.out)):file_sha256(p) for p in sorted(a.out.glob('*')) if p.is_file()},
        code={str(p):file_sha256(p) for p in (Path(S.__file__),Path(__file__))},model_calls=0))
    print(json.dumps(dict(out=str(a.out),rankings=len(ranked),tasks=len(tasks),model_calls=0)))

if __name__=='__main__':main()
