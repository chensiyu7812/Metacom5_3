"""Original-reference delivery audit for the separate static Top4 stress sidecar.

The macro has different primitive access accounting. Token-cap feasibility and
source coverage do not establish action-matched value or generated quality.
"""
from pathlib import Path
import json
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from .pomdp_source_trace_audit import rows,span_key,delivered_groups


def audit(*,bundle,cpu,pressure,original_audit,out):
    bundle,cpu,pressure,original_audit,out=map(Path,(bundle,cpu,pressure,original_audit,out))
    if out.exists():raise FileExistsError(out)
    manifest=json.loads((bundle/'MANIFEST.json').read_text())
    for name,h in manifest['files_sha256'].items():
        if file_sha256(bundle/name)!=h:raise ValueError('original reference changed')
    summary=json.loads((pressure/'TOP4_PRESSURE_PUBLIC.json').read_text())
    for name,h in summary['files_sha256'].items():
        if file_sha256(pressure/name)!=h:raise ValueError('static pressure evidence changed')
    if file_sha256(cpu/'LEGAL_POOLS.private.jsonl')!=summary['pool_sha256']:raise ValueError('legal pool identity changed')
    original=json.loads((original_audit/'SUMMARY_PUBLIC.json').read_text())
    if original['trace_sha256']!=file_sha256(cpu/'TRACES.private.jsonl'):raise ValueError('original trace identity changed')
    tasks={r['task_id']:r for r in rows(bundle/'TASKS.runtime.jsonl')}
    evals={r['task_id']:r for r in rows(bundle/'EVALSPEC.private.jsonl')}
    pools={r['task_id']:r for r in rows(cpu/'LEGAL_POOLS.private.jsonl')}
    requests={r['task_id']:r for r in rows(pressure/'TOP4_REQUESTS_PRIVATE.jsonl')}
    checked=[];public=[]
    for row in rows(pressure/'TOP4_READS_PRIVATE.jsonl'):
        task_id=row['task_id'];ev=evals[task_id];by={r['record_id']:r for r in pools[task_id]['records']}
        selected=[by[rid] for rid in row['selected_record_ids']]
        expected={span_key(s):s for r in selected for s in r['source_refs']}
        actual={span_key(s):s for s in row['source_refs']}
        if len(row['source_refs'])!=len(expected) or actual!=expected:
            raise ValueError('Top4 source delivery is not complete selected parents')
        if any(s['exact_quote'] not in row['reading_text'] for s in actual.values()):raise ValueError('source text absent from delivered reading')
        if not row['initial_query_only'] or row['selected_k']!=4 or not row['full_top4_fits']:
            raise ValueError('fixed complete Top4 scope')
        if row['delivery_tokens']>4096 or row['input_tokens']+320>16384:raise ValueError('capacity failure')
        if row['same_primitive_access_cost']!=5:raise ValueError('primitive comparison scope changed')
        req=requests[task_id]
        if req['input_tokens']!=row['input_tokens']:raise ValueError('request token identity mismatch')
        state=delivered_groups(ev['source_binding']['atoms'],set(actual),tasks[task_id]['query'])
        known=[a for a in state if a['kind']=='reported_fact'];required=set(ev['required_fact_ids'])
        result=dict(task_id=task_id,case_id=ev['case_id'],goal_kind=ev['goal_kind'],
            known_required_slots=len(required),known_required_supplied=sum(a['source_group_present'] for a in known if a['atom_id'] in required),
            diagnostic_reported_slots=len(known),diagnostic_reported_supplied=sum(a['source_group_present'] for a in known),
            canonical_input_tokens=row['input_tokens'],delivery_tokens=row['delivery_tokens'],
            selected_complete_parents=4,primitive_operations=5,original_primitive_cap=4,
            same_delivery_token_cap=True,action_matched=False,snippet_delivery=False,
            whole_cpu_seconds=row['whole_cpu_seconds'],source_delivery=state,
            task_success=None,formal_reward=None,model_calls=0)
        checked.append(result);public.append({k:v for k,v in result.items() if k!='source_delivery'})
    if len(checked)!=16 or {r['task_id'] for r in checked}!=set(tasks):raise ValueError('all original16 goals required')
    facts=[r for r in checked if r['goal_kind']=='fact'];support=[r for r in checked if r['goal_kind']=='natural_support']
    combined=dict(original['policies'])
    combined['FixedTop4WholeStress']=dict(paths=len(checked),fact_required_slots=sum(r['known_required_slots'] for r in facts),
        fact_required_supplied=sum(r['known_required_supplied'] for r in facts),
        fact_goals_all_known_groups_supplied=sum(r['known_required_supplied']==r['known_required_slots'] for r in facts),
        support_diagnostic_slots=sum(r['diagnostic_reported_slots'] for r in support),support_diagnostic_supplied=sum(r['diagnostic_reported_supplied'] for r in support),
        support_success=None,total_primitive_operations=sum(r['primitive_operations'] for r in checked),
        charged_delivery_tokens=sum(r['delivery_tokens'] for r in checked),canonical_input_tokens=sum(r['canonical_input_tokens'] for r in checked),
        action_matched=False,original_primitive_cap=4,primitive_operations_per_goal=5,snippet_delivery=False)
    report=dict(protocol='pomdp-static-source-pressure-audit-v1',source_cases=8,goals=16,
        original_paths_preserved=80,additional_static_paths=16,comparison=combined,
        original_source_reference_unchanged=True,unknown_boundaries_not_resolved=True,
        source_coverage_not_task_success=True,same_delivery_token_cap=4096,native_context_tokens=16384,output_reserve=320,
        static_comparator_exceeds_original_primitive_cap=True,no_action_matched_effect_claim=True,
        new_G_calls=0,formal_reward=None,
        pressure_reads_sha256=file_sha256(pressure/'TOP4_READS_PRIVATE.jsonl'),source_reference_sha256=file_sha256(bundle/'EVALSPEC.private.jsonl'))
    out.mkdir(parents=True);write_jsonl_once(out/'TOP4_SOURCE_DELIVERY_PRIVATE.jsonl',checked)
    write_jsonl_once(out/'TOP4_SOURCE_COUNTS_PUBLIC.jsonl',public);write_json_once(out/'COMPARISON_PUBLIC.json',report)
    write_json_once(out/'MANIFEST.json',dict(files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},
        inputs_sha256={str(p.resolve()):file_sha256(p) for p in (bundle/'MANIFEST.json',pressure/'TOP4_PRESSURE_PUBLIC.json',original_audit/'MANIFEST.json')},
        code_sha256=file_sha256(__file__),no_new_task_or_reference=True))
    return report
