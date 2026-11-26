#!/usr/bin/env python3
"""Finite CPU source/lexical diagnostics; no model, policy change or new task.

All rankings are frozen before evaluator-side references are opened. Diagnostic
score decompositions retain every legal candidate and do not amend old traces.
Private inputs and verbatim findings are written only under --out.
"""
import argparse
from collections import Counter
import json
from itertools import combinations
from pathlib import Path

from metacom_pm.rl1v3.io import file_sha256, object_sha256, write_json_once, write_jsonl_once
from metacom_pm.rl1v3.journal import temporal_retrieval as T
from metacom_pm.rl1v3.journal.pomdp_source_cases import load_bounded_registry

# A fixed descriptive English function-word list, not fitted to coverage/results.
FUNCTION_WORDS = frozenset("a an the i me my myself we us our you your he him his she her it its they them their this that these those and or but if as at by for from in into of on to with without is am are was were be been being do does did have has had what which who whom when where how why can could may might shall should will would not no so than then there here any some all only about out up down now still please say said tell told keep let".split())


def rows(path):
    return [json.loads(s) for s in Path(path).read_text().splitlines() if s]


def rank_diagnostic(records, query):
    q = T.words(query)
    ranked, scores = T.lexical(records, query)
    details, bodies, seekers, nonfunction = [], {}, {}, {}
    for record in records:
        rid = record['record_id']
        body = T.words('\n'.join(s['exact_quote'] for s in record['source_refs']))
        seeker = T.words('\n'.join(s['exact_quote'] for s in record['source_refs'] if s['speaker'] == 'seeker'))
        supporter = T.words('\n'.join(s['exact_quote'] for s in record['source_refs'] if s['speaker'] == 'supporter'))
        rendered = T.words(record['reading_text'])
        matched = q & rendered
        wrappers = matched - body
        assert scores[rid] == len(matched) / max(1, len(q))
        bodies[rid] = len(q & body) / max(1, len(q))
        seekers[rid] = len(q & seeker) / max(1, len(q))
        nonfunction[rid] = len((q - FUNCTION_WORDS) & rendered) / max(1, len(q - FUNCTION_WORDS))
        span = min(record['source_refs'], key=lambda s: (-len(q & T.words(s['exact_quote'])), s['turn_index']))
        details.append(dict(record_id=rid, source_rank=record['source_rank'], score=scores[rid],
            matched_terms=sorted(matched), function_terms=sorted(matched & FUNCTION_WORDS),
            wrapper_only_terms=sorted(wrappers), supporter_only_terms=sorted((q & supporter) - seeker),
            selected_span=span, span_overlap=len(q & T.words(span['exact_quote']))))
    order = [r['record_id'] for r in ranked]
    counterfactual = {name: [r['record_id'] for r in T.order_scores(records, score)] for name, score in
        [('body_only', bodies), ('exclude_function_terms', nonfunction), ('seeker_only', seekers)]}
    by = {r['record_id']: r for r in details}
    top = [by[rid] for rid in order[:2]]
    return dict(query=query, query_terms=sorted(q), candidate_count=len(records),
        original_order=order, original_scores=scores, candidate_details=details,
        diagnostic_orders=counterfactual,
        top2_role_counts=dict(Counter(r['selected_span']['speaker'] for r in top)),
        top2_supporter_questions=sum(r['selected_span']['speaker']=='supporter' and '?' in r['selected_span']['exact_quote'] for r in top),
        top2_overlap_tokens=sum(len(r['matched_terms']) for r in top),
        top2_function_overlap_tokens=sum(len(r['function_terms']) for r in top),
        top2_wrapper_only_overlap_tokens=sum(len(r['wrapper_only_terms']) for r in top),
        top2_supporter_only_overlap_tokens=sum(len(r['supporter_only_terms']) for r in top),
        top2_changes={name: v[:2] != order[:2] for name,v in counterfactual.items()},
        rank_only_diagnostic=True, actual_policy_or_source_pool_changed=False)


def run(args):
    bundle, cpu, case_root, out = map(Path, (args.bundle,args.cpu,args.cases,args.out))
    out.mkdir(parents=True,exist_ok=False)
    paths = [bundle/'TASKS.runtime.jsonl',bundle/'TASK_ENVELOPES.private.jsonl',
        cpu/'LEGAL_POOLS.private.jsonl',cpu/'TRACES.private.jsonl']
    tasks = rows(paths[0]); envelopes={r['task_id']:r for r in rows(paths[1])}
    pools={r['task_id']:r for r in rows(paths[2])}; traces=rows(paths[3])
    assert len(tasks)==16 and len(pools)==16
    manifest=json.loads((bundle/'MANIFEST.json').read_text())
    for name,h in manifest['files_sha256'].items():
        assert file_sha256(bundle/name)==h
    summary=json.loads((cpu/'CPU_SUMMARY_PUBLIC.json').read_text())
    for p in paths[2:]: assert file_sha256(p)==summary['files_sha256'][p.name]
    diagnostics=[]
    for t in tasks:
        d=rank_diagnostic(pools[t['task_id']]['records'],t['query'])
        old=next(r for r in traces if r['task_id']==t['task_id'] and r['policy']=='SequentialRule')
        first=next(s for s in old['trace'] if s['action']['action']=='SEARCH')
        assert [r['record_id'] for r in first['delivered']]==d['original_order'][:2]
        d.update(task_id=t['task_id'],scope='frozen_visible_query_first_search')
        diagnostics.append(d)
    rewrites=[]
    for t in tasks:
        old=next(r for r in traces if r['task_id']==t['task_id'] and r['policy']=='SequentialRule')
        prior_body=[];prior_rendered=[];searches=0
        for step in old['trace']:
            if step['action']['action']=='SEARCH':
                searches+=1
                if searches>1:
                    query=step['action']['query'];terms=T.words(query)
                    metadata=terms-T.words(t['query'])-T.words('\n'.join(prior_body))
                    assert not (terms-T.words(t['query'])-T.words('\n'.join(prior_rendered)))
                    d=rank_diagnostic(pools[t['task_id']]['records'],query)
                    assert [x['record_id'] for x in step['delivered']]==d['original_order'][:2]
                    reduced=terms-metadata
                    reduced_scores={r['record_id']:len(reduced&T.words(r['reading_text']))/max(1,len(reduced)) for r in pools[t['task_id']]['records']}
                    order=[r['record_id'] for r in T.order_scores(pools[t['task_id']]['records'],reduced_scores)]
                    d.update(task_id=t['task_id'],scope='actual_CPU_rule_later_search',added_metadata_terms=sorted(metadata),
                        metadata_only_match_positions=sum(len(metadata&T.words(r['reading_text'])) for r in pools[t['task_id']]['records']),
                        removing_added_metadata_changes_top2=order[:2]!=d['original_order'][:2])
                    rewrites.append(d)
            for item in step.get('delivered',[]):
                prior_rendered.append(item['text'])
                prior_body.extend(s['exact_quote'] for s in item.get('spans',[item['span']] if 'span' in item else []))
    dynamic=[]
    if args.dynamic_collection:
        paths.append(Path(args.dynamic_collection))
        for r in rows(args.dynamic_collection):
            if r['method'] not in ('LLMOneShot','LLMToolAgent') or not r.get('source_receipt'):continue
            search=next((s for s in r['source_receipt'].get('trace',[]) if s['action']['action']=='SEARCH'),None)
            if search:
                d=rank_diagnostic(pools[r['task_id']]['records'],search['action']['query'])
                assert [x['record_id'] for x in search['delivered']]==d['original_order'][:2]
                d.update(task_id=r['task_id'],method=r['method'],scope='actual_controller_first_search')
                dynamic.append(d)
    write_jsonl_once(out/'LEXICAL_PRIVATE.jsonl',diagnostics+rewrites+dynamic)
    write_json_once(out/'RANKING_FREEZE_PRIVATE.json',dict(inputs_sha256={str(p):file_sha256(p) for p in paths},
        ranking_sha256=file_sha256(out/'LEXICAL_PRIVATE.jsonl'),reference_opened_by_ranking=False,
        uses_generated_terminal_text=False,diagnostic_not_policy_revision=True,model_calls=0))

    # Evaluator-only joins begin here, after all query-only diagnostics are fixed.
    eval_path=bundle/'EVALSPEC.private.jsonl';audit_path=case_root/'trace-audit-v1/DELIVERY_AND_QUERY_PRIVATE.jsonl'
    evals={r['task_id']:r for r in rows(eval_path)};audits=rows(audit_path)
    for path,h in manifest['inputs_sha256'].items():assert file_sha256(path)==h
    resources=next(p for p in manifest['inputs_sha256'] if p.endswith('resources_private.jsonl'))
    metadata=next(p for p in manifest['inputs_sha256'] if p.endswith('registry.json'))
    design_path=case_root/'SOURCE_DESIGN_V2_PRIVATE.json'
    registry=load_bounded_registry(resources,metadata,json.loads(design_path.read_text()))
    intended={r['task_id']:r for r in rows(bundle/'FULL_LEGAL_POOLS.private.jsonl')}
    prefix_rows=[];source_rows=[];public=[]
    for t,d in zip(tasks,diagnostics):
        tid=t['task_id'];ev=evals[tid];env=envelopes[tid];prefix=env['actual_prefix'];pool=pools[tid]
        assert sorted(pool['source_ids'])==sorted(intended[tid]['source_ids'])
        assert object_sha256(t)==env['visible_task_sha256']
        a=next(r for r in audits if r['task_id']==tid and r['policy']=='SequentialRule')
        first=next(s for s in a['stages'] if s['action']['action']=='SEARCH')
        expand=next(s for s in a['stages'] if s['action']['action']=='EXPAND')
        init=sum(s['source_group_present'] for s in a['initial_source_delivery'] if s['kind']=='reported_fact')
        required=[x for x in ev['source_binding']['atoms'] if x['atom_id'] in ev['required_fact_ids']]
        source_options=[]
        for atom in required:
            source_options.append([frozenset() if all(s['exact_quote'] in t['query'] for s in g['spans']) else frozenset([g['source_id']]) for g in atom['evidence_groups']])
        reference_parents=sorted({s for options in source_options for group in options for s in group})
        minimum=None
        for n in range(len(reference_parents)+1):
            if any(all(any(group<=set(choice) for group in options) for options in source_options) for choice in combinations(reference_parents,n)):
                minimum=n;break
        original=registry.entry(prefix['owner_id'],prefix['session_id']).source
        assert prefix['fold']!=6 and original.turns[prefix['cut_turn']].role=='seeker'
        next_role=original.turns[prefix['cut_turn']+1].role if prefix['cut_turn']+1<len(original.turns) else None
        pr=dict(task_id=tid,case_id=ev['case_id'],goal_kind=ev['goal_kind'],
            original_prefix=prefix,constructed_runtime=t,original_prefix_turns=len(prefix['turns']),
            runtime_turns=len(t['turns']),query_equals_original_last_turn=t['query']==prefix['turns'][-1]['text'],
            original_last_turn_role=prefix['turns'][-1]['role'],original_next_role=next_role,
            genuine_pre_supporter=next_role=='supporter',source_legality_anchor_not_task_identity=True)
        prefix_rows.append(pr)
        sr=dict(task_id=tid,case_id=ev['case_id'],goal_kind=ev['goal_kind'],available_sessions=len(pool['records']),
            initial_known_groups=init,necessary_known_slots=len(ev['required_fact_ids']),
            evaluator_minimum_full_parents_for_known_groups=minimum,
            first_search_known_groups=first['known_required_supplied'],
            first_expand_known_groups=expand['known_required_supplied'],final_known_groups=a['known_required_supplied'],
            optional_or_required_diagnostic_groups=a['diagnostic_reported_supplied'],
            after_first_search_legal_actions=['STOP','SEARCH_using_visible_or_delivered_words','EXPAND_returned_handle_within_budget'],
            source_evidence=ev['source_binding'],actual_read_stages=a['stages'],
            source_only_interpretation='Exact-group delivery is not task success, event identity or real-world current validity.',
            task_success=None,formal_reward=None)
        source_rows.append(sr)
        public.append({k:sr[k] for k in ('task_id','case_id','goal_kind','available_sessions','initial_known_groups','necessary_known_slots','evaluator_minimum_full_parents_for_known_groups','first_search_known_groups','first_expand_known_groups','final_known_groups','optional_or_required_diagnostic_groups')}|
            {k:d[k] for k in ('top2_role_counts','top2_supporter_questions','top2_overlap_tokens','top2_function_overlap_tokens','top2_wrapper_only_overlap_tokens','top2_supporter_only_overlap_tokens','top2_changes')}|
            {k:pr[k] for k in ('original_prefix_turns','runtime_turns','query_equals_original_last_turn','original_last_turn_role','genuine_pre_supporter')}|
            dict(task_success=None,formal_reward=None))
    write_jsonl_once(out/'PREFIX_COMPARISON_PRIVATE.jsonl',prefix_rows)
    write_jsonl_once(out/'SOURCE_INFORMATION_PRIVATE.jsonl',source_rows)
    write_jsonl_once(out/'SOURCE_DIAGNOSTICS_PUBLIC.jsonl',public)
    facts=[r for r in public if r['goal_kind']=='fact'];support=[r for r in public if r['goal_kind']=='natural_support']
    historical=[r for r in facts if r['initial_known_groups']<r['necessary_known_slots']]
    def lexical_summary(rr):
        return dict(queries=len(rr),candidate_presentations=sum(r['candidate_count'] for r in rr),
            top2_presentations=2*len(rr),top2_role_counts=dict(sum((Counter(r['top2_role_counts']) for r in rr),Counter())),
            top2_supporter_questions=sum(r['top2_supporter_questions'] for r in rr),
            matched_tokens=sum(r['top2_overlap_tokens'] for r in rr),function_tokens=sum(r['top2_function_overlap_tokens'] for r in rr),
            wrapper_only_tokens=sum(r['top2_wrapper_only_overlap_tokens'] for r in rr),
            supporter_only_tokens=sum(r['top2_supporter_only_overlap_tokens'] for r in rr),
            changed_top2={k:sum(r['top2_changes'][k] for r in rr) for k in ('body_only','exclude_function_terms','seeker_only')})
    result=dict(protocol='pomdp-source-system-review-v1',tasks=16,source_cases=8,source_family_components=3,
        unique_legal_sessions=len({(r['owner_id'],r['parent_session_id']) for p in pools.values() for r in p['records']}),
        all_runtime_queries_constructed=sum(not r['query_equals_original_last_turn'] for r in prefix_rows),
        runtime_turn_counts={str(k):v for k,v in Counter(r['runtime_turns'] for r in prefix_rows).items()},
        original_prefix_turn_counts={str(k):v for k,v in Counter(r['original_prefix_turns'] for r in prefix_rows).items()},
        genuine_pre_supporter_anchors=sum(r['genuine_pre_supporter'] for r in prefix_rows),
        current_sufficient_fact_tasks=len(facts)-len(historical),history_required_fact_tasks=len(historical),
        known_fact_reference_minimum_parent_counts={str(k):v for k,v in Counter(r['evaluator_minimum_full_parents_for_known_groups'] for r in facts).items()},
        history_required_fact_tasks_sufficient_after_first_SEARCH=sum(r['first_search_known_groups']==r['necessary_known_slots'] for r in historical),
        history_required_fact_tasks_sufficient_after_first_EXPAND=sum(r['first_expand_known_groups']==r['necessary_known_slots'] for r in historical),
        natural_support_required_history_slots=sum(r['necessary_known_slots'] for r in support),
        original_query_lexical=lexical_summary(diagnostics),actual_controller_query_lexical=lexical_summary(dynamic),
        actual_rule_rewrite_lexical=lexical_summary(rewrites),
        rule_rewrite_metadata=dict(queries_with_added_metadata=sum(bool(r['added_metadata_terms']) for r in rewrites),
            metadata_only_match_positions=sum(r['metadata_only_match_positions'] for r in rewrites),
            removing_added_metadata_changes_top2=sum(r['removing_added_metadata_changes_top2'] for r in rewrites)),
        no_static_source_pruning=True,reference_not_ranking_input=True,old_outputs_or_rules_changed=False,
        new_model_calls=0,sealed_test_body_read=False,formal_reward=None)
    write_json_once(out/'SOURCE_DIAGNOSTICS_SUMMARY_PUBLIC.json',result)
    allpaths=[*paths,eval_path,audit_path,bundle/'MANIFEST.json',case_root/'source-observations-v1/MANIFEST.json',Path(resources),Path(metadata),design_path]
    write_json_once(out/'MANIFEST_PRIVATE.json',dict(inputs_sha256={str(p):file_sha256(p) for p in allpaths},
        files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},script_sha256=file_sha256(__file__)))
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for arg in ('bundle','cpu','cases','out'):ap.add_argument('--'+arg,required=True)
    ap.add_argument('--dynamic-collection')
    print(json.dumps(run(ap.parse_args()),indent=2))
