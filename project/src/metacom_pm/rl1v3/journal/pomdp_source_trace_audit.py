"""Post-trace source delivery audit, never a retrieval or semantic reward input.

Exact original source spans/context groups establish delivery. They do not prove
an answer, helpfulness, event identity, execution, or the value of sequencing.
"""
from collections import Counter,defaultdict
from pathlib import Path
import json
from .. import contracts as K
from ..io import canonical_json,decode_contract,file_sha256,object_sha256,write_json_once,write_jsonl_once
from . import temporal_retrieval as T
from .pomdp_source_cases import load_bounded_registry


def rows(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]


def span_key(span):
    return (span['owner_id'],span['session_id'],span['turn_index'],span['start_char'],span['end_char'],span['raw_turn_sha256'])


def delivered_groups(atoms,seen,query):
    result=[]
    for atom in atoms:
        groups=[]
        for group in atom['evidence_groups']:
            groups.append(all(span_key(s) in seen or s['exact_quote'] in query for s in group['spans']))
        result.append(dict(atom_id=atom['atom_id'],kind=atom['kind'],
            source_group_present=any(groups),matching_alternative_groups=[i for i,present in enumerate(groups) if present],
            semantic_boundary_resolved=None if atom['kind']=='unresolved_boundary' else 'not_tested'))
    return result


def query_provenance(query,initial,prior_body,prior_rendered):
    terms=T.words(query);initial_terms=T.words(initial)
    body_terms=T.words(prior_body);rendered_terms=T.words(prior_rendered)
    illegal=terms-initial_terms-rendered_terms
    if illegal:raise ValueError('query uses unobserved terms')
    return dict(initial_goal_terms=sorted(terms&initial_terms),
        added_body_terms=sorted((terms-initial_terms)&body_terms),
        added_metadata_only_terms=sorted(terms-initial_terms-body_terms),
        no_unobserved_terms=True)


def audit(*,bundle,cpu,design_path,resources,metadata,out):
    bundle,cpu,design_path,resources,metadata,out=map(Path,(bundle,cpu,design_path,resources,metadata,out))
    if out.exists():raise FileExistsError(out)
    manifest=json.loads((bundle/'MANIFEST.json').read_text())
    for name,h in manifest['files_sha256'].items():
        if file_sha256(bundle/name)!=h:raise ValueError('source case freeze changed')
    cpu_summary=json.loads((cpu/'CPU_SUMMARY_PUBLIC.json').read_text())
    for name,h in cpu_summary['files_sha256'].items():
        if file_sha256(cpu/name)!=h:raise ValueError('CPU trace input changed')
    design=json.loads(design_path.read_text());registry=load_bounded_registry(resources,metadata,design)
    tasks={r['task_id']:r for r in rows(bundle/'TASKS.runtime.jsonl')}
    evaluations={r['task_id']:r for r in rows(bundle/'EVALSPEC.private.jsonl')}
    envelopes={r['task_id']:r for r in rows(bundle/'TASK_ENVELOPES.private.jsonl')}
    strata={r['task_id']:r for r in rows(bundle/'STRATA.private.jsonl')}
    pools={r['task_id']:r for r in rows(cpu/'LEGAL_POOLS.private.jsonl')}
    intended={r['task_id']:r for r in rows(bundle/'FULL_LEGAL_POOLS.private.jsonl')}
    requests={(r['task_id'],r['arm']):r for r in rows(cpu/'REQUESTS_ALL.private.jsonl')}
    verified_sources=set();records={}
    for task_id,pool in pools.items():
        prefix=decode_contract(K.PrefixSpec,canonical_json(envelopes[task_id]['actual_prefix']))
        if sorted(pool['source_ids'])!=sorted(intended[task_id]['source_ids']):raise ValueError('legal pool pruned or changed')
        by={r['record_id']:r for r in pool['records']};records[task_id]=by
        for record in by.values():
            source=registry.entry(record['owner_id'],record['parent_session_id'])
            if record['owner_id']!=prefix.owner_id or registry.reason(source.source_id,prefix) is not None:
                raise ValueError('illegal source in actual pool')
            if record['source_rank']>=prefix.cutoff_rank:raise ValueError('nonpast source')
            for raw in record['source_refs']:
                span=decode_contract(K.SourceSpan,canonical_json(raw));span.verify(source.source)
            verified_sources.add((record['owner_id'],record['parent_session_id']))
    result=[];public=[]
    for trace in rows(cpu/'TRACES.private.jsonl'):
        task_id=trace['task_id'];task=tasks[task_id];ev=evaluations[task_id];atoms=ev['source_binding']['atoms']
        required=set(ev['required_fact_ids']);by=records[task_id]
        if trace['trajectory_sha256']!=object_sha256(trace['trace']):raise ValueError('trajectory hash mismatch')
        if trace['reward'] is not None or trace['model_called']:raise ValueError('unexpected model/reward')
        seen=set();body=[];rendered=[];stages=[];first_source_clues=[]
        initial=delivered_groups(atoms,seen,task['query']);previous={x['atom_id'] for x in initial if x['source_group_present'] and x['kind']=='reported_fact'}
        query_rows=[]
        for number,step in enumerate(trace['trace'],1):
            action=step['action'];provenance=None
            if action['action']=='SEARCH':
                provenance=query_provenance(action['query'],task['query'],'\n'.join(body),'\n'.join(rendered))
                if trace['policy']=='SequentialNoText' and (provenance['added_body_terms'] or provenance['added_metadata_only_terms']):
                    raise ValueError('NoText queried delivered content')
                query_rows.append(dict(step=number,query=action['query'],**provenance))
            acquired=[]
            for delivery in step.get('delivered',[]):
                record=by[delivery['record_id']]
                delivered=delivery.get('spans',[delivery['span']] if 'span' in delivery else [])
                if not delivered:raise ValueError('delivery without original spans')
                if delivery['scope']=='MS-RAW-complete-parent' and delivered!=record['source_refs']:
                    raise ValueError('EXPAND did not deliver full source')
                legal_spans={span_key(s):s for s in record['source_refs']}
                for span in delivered:
                    if span_key(span) not in legal_spans or span!=legal_spans[span_key(span)] or span['exact_quote'] not in delivery['text']:
                        raise ValueError('delivered source span not exact')
                    if span_key(span) not in seen:
                        acquired.append(dict(owner_id=span['owner_id'],session_id=span['session_id'],turn=span['turn_index'],speaker=span['speaker'],
                            quote=span['exact_quote'],reported_at=delivery['reported_at']))
                    seen.add(span_key(span));body.append(span['exact_quote'])
                rendered.append(delivery['text'])
            state=delivered_groups(atoms,seen,task['query'])
            now={x['atom_id'] for x in state if x['source_group_present'] and x['kind']=='reported_fact'}
            stages.append(dict(step=number,action=action,source_delivery=state,new_reported_fact_groups=sorted(now-previous),
                known_required_supplied=len(now&required),known_required_total=len(required),
                diagnostic_reported_groups=len(now),new_original_spans=acquired,query_provenance=provenance,
                delivered_tokens=step['delivered_tokens'],canonical_input_tokens=step.get('canonical_input_tokens')))
            previous=now
        req=requests[(task_id,trace['policy'])]
        if req['payload_sha256']!=trace['content_payload_sha256'] or req['input_tokens']!=trace['canonical_input_tokens']:
            raise ValueError('terminal request/trace mismatch')
        final=stages[-1]['source_delivery'];known=[a for a in final if a['kind']=='reported_fact']
        row=dict(task_id=task_id,case_id=ev['case_id'],goal_kind=ev['goal_kind'],policy=trace['policy'],
            initial_source_delivery=initial,stages=stages,final_source_delivery=final,
            known_required_slots=len(required),known_required_supplied=sum(a['source_group_present'] for a in known if a['atom_id'] in required),
            diagnostic_reported_slots=len(known),diagnostic_reported_supplied=sum(a['source_group_present'] for a in known),
            unresolved_boundary_ids=ev['unresolved_boundary_ids'],boundary_truth_resolved=False if ev['unresolved_boundary_ids'] else None,
            successful_accesses=trace['accesses'],charged_delivery_tokens=trace['delivered_tokens'],
            canonical_input_tokens=trace['canonical_input_tokens'],unique_original_spans=len(seen),
            acquisition_seconds=trace['acquisition_seconds'],path_cpu_seconds=trace['path_cpu_seconds'],
            query_rows=query_rows,query_rewrites_with_new_body_terms=sum(bool(x['added_body_terms']) for x in query_rows),
            query_rewrites_with_metadata_terms=sum(bool(x['added_metadata_only_terms']) for x in query_rows),
            query_integrity_passed=True,whole_legal_pool_preserved=True,
            source_groups_added_after_first_access=sum(len(s['new_reported_fact_groups']) for s in stages if s['step']>1),
            additional_SEARCH_reported_groups=sum(len(s['new_reported_fact_groups']) for s in stages if s['step']>1 and s['action']['action']=='SEARCH'),
            EXPAND_reported_groups=sum(len(s['new_reported_fact_groups']) for s in stages if s['action']['action']=='EXPAND'),
            policy_endpoint_input_sha256=trace['content_payload_sha256'],trajectory_sha256=trace['trajectory_sha256'],
            task_success=None,formal_reward=None,model_calls=0)
        result.append(row)
        public.append({k:v for k,v in row.items() if k not in ('initial_source_delivery','stages','final_source_delivery','query_rows','unresolved_boundary_ids')})
    by_policy={}
    policies=list(dict.fromkeys(r['policy'] for r in result))
    for policy in policies:
        subset=[r for r in result if r['policy']==policy];facts=[r for r in subset if r['goal_kind']=='fact'];support=[r for r in subset if r['goal_kind']=='natural_support']
        by_policy[policy]=dict(paths=len(subset),fact_required_slots=sum(r['known_required_slots'] for r in facts),
            fact_required_supplied=sum(r['known_required_supplied'] for r in facts),
            fact_goals_all_known_groups_supplied=sum(r['known_required_supplied']==r['known_required_slots'] for r in facts),
            support_diagnostic_slots=sum(r['diagnostic_reported_slots'] for r in support),
            support_diagnostic_supplied=sum(r['diagnostic_reported_supplied'] for r in support),
            support_success=None,total_accesses=sum(r['successful_accesses'] for r in subset),
            charged_delivery_tokens=sum(r['charged_delivery_tokens'] for r in subset),
            canonical_input_tokens=sum(r['canonical_input_tokens'] for r in subset),
            query_rewrites_with_new_body_terms=sum(r['query_rewrites_with_new_body_terms'] for r in subset),
            query_rewrites_with_metadata_terms=sum(r['query_rewrites_with_metadata_terms'] for r in subset),
            EXPAND_reported_groups=sum(r['EXPAND_reported_groups'] for r in subset),
            additional_SEARCH_reported_groups=sum(r['additional_SEARCH_reported_groups'] for r in subset))
    summary=dict(protocol='pomdp-source-trace-audit-v1',source_cases=8,goals=16,paths=len(result),
        source_family_components=3,unique_legal_source_sessions=len(verified_sources),
        policies=by_policy,query_integrity_violations=0,source_integrity_violations=0,
        source_pruning_detected=False,current_sufficient_control_present=True,
        unresolved_boundaries_never_resolved_by_match=True,supply_is_not_task_success=True,
        actual_new_G_calls=0,formal_reward=None,static_rule_does_not_test_full_POMDP_optimality=True,
        trace_sha256=file_sha256(cpu/'TRACES.private.jsonl'),source_bundle_manifest_sha256=file_sha256(bundle/'MANIFEST.json'))
    out.mkdir(parents=True)
    write_jsonl_once(out/'DELIVERY_AND_QUERY_PRIVATE.jsonl',result)
    write_json_once(out/'SUMMARY_PUBLIC.json',summary);write_jsonl_once(out/'PATH_COUNTS_PUBLIC.jsonl',public)
    text=['# Source coverage and observed query provenance — private',
        'Coverage is source delivery only. No generated answer or formal reward exists. No unknown boundary is converted into a negative answer.']
    for row in result:
        text+=['\n## '+row['case_id']+' / '+row['goal_kind']+' / '+row['policy'],
            'Required known groups '+str(row['known_required_supplied'])+'/'+str(row['known_required_slots'])+'; diagnostic '+str(row['diagnostic_reported_supplied'])+'/'+str(row['diagnostic_reported_slots'])+
            '; input='+str(row['canonical_input_tokens'])+'; charged='+str(row['charged_delivery_tokens'])]
        for stage in row['stages']:
            text+=['\n'+str(stage['step'])+' '+str(stage['action'])+' new reported groups='+str(stage['new_reported_fact_groups'])]
            if stage['query_provenance']:text+=['Query provenance: '+str(stage['query_provenance'])]
            for span in stage['new_original_spans']:text+=['- '+span['session_id']+':'+str(span['turn'])+' '+span['speaker']+' ['+span['reported_at']['date']+'] '+span['quote']]
    (out/'TRACES_AND_EVIDENCE_PRIVATE.md').write_text('\n'.join(text)+'\n')
    write_json_once(out/'MANIFEST.json',dict(files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},
        inputs_sha256={str(p.resolve()):file_sha256(p) for p in (bundle/'MANIFEST.json',cpu/'CPU_SUMMARY_PUBLIC.json',cpu/'TRACES.private.jsonl',design_path)},
        code_sha256=file_sha256(__file__),auditor_not_used_for_retrieval=True))
    return summary
