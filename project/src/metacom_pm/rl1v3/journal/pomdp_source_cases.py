"""Source-derived POMDP development candidates; no model or retrieval execution.

The private source recipes/evaluation are never runtime observations. Complete
legal pools and genuine source prefixes are retained independently of manual
reference spans. Possible sequential bridges are hypotheses, not benefits.
"""
from collections import Counter
from pathlib import Path
import hashlib,json
from .. import contracts as K
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from ..sources import source_registry as S
from .runtime_binding import plain
from .selective_memory_validation_sources import load_development_cache

PROTOCOL='pmrl1-j-pomdp-real-source-cases-v1'
RUNTIME_KEYS={'task_id','timestamp','turns','query','view_protocol'}
GOALS=('fact','natural_support')


def load_bounded_registry(resources,metadata,design):
    return load_development_cache(resources_path=resources,metadata_path=metadata,
        allowed_owners=design['allowed_owners'],excluded_owners=design['excluded_J06_owners'])


def exact_group(registry,prefix,owner,spec):
    entry=registry.entry(owner,spec['session']);source=entry.source
    current=source.session_id==prefix.session_id
    if current:
        if any(i>prefix.cut_turn for i in spec['turns']):raise ValueError('future current-session reference')
    elif registry.reason(entry.source_id,prefix) is not None:
        raise ValueError('reference outside actual legal frontier')
    if not spec['turns'] or len(set(spec['turns']))!=len(spec['turns']):raise ValueError('empty or repeated source coordinates')
    spans=[]
    for index in spec['turns']:
        span=S.span(source,index);span.verify(source)
        spans.append(plain(span))
    return dict(source_id=entry.source_id,owner_id=owner,session_id=source.session_id,
        source_rank=source.chronological_rank,reported_at=plain(entry.reported_at),ready_at=plain(entry.ready_at),
        source_status='current_prefix' if current else 'legal_strict_past',spans=spans,
        source_transcript_sha256=source.transcript_sha256,source_family_id=source.family_id,
        source_split=source.source_split,quote_group_sha256=object_sha256(spans))


def verify_current_delivery(groups,query):
    for group in groups:
        if group['source_status']=='current_prefix':
            if any(span['exact_quote'] not in query for span in group['spans']):
                raise ValueError('current reference not actually in visible goal')


def source_only_selection(selection,cases):
    if selection['retrieval_results_seen'] or selection['new_G_outputs_seen'] or selection['authorized_G_calls']!=0:
        raise ValueError('source-only pre-outcome proposal required')
    by={c['case_id']:c for c in cases}
    selected=[]
    for stratum,members in selection['strata'].items():
        if not members or any(x not in by or by[x]['primary_type']!=stratum for x in members):
            raise ValueError('source stratum mismatch')
        selected.append(min(members,key=lambda x:hashlib.sha256(x.encode()).hexdigest()))
    if set(selected)!=set(selection['selected_case_ids']) or len(selected)!=4:
        raise ValueError('frozen source-stratified selection changed')
    return frozenset(selected)


def build(*,resources,metadata,design_path,selection_path,out):
    resources,metadata,design_path,selection_path,out=map(Path,(resources,metadata,design_path,selection_path,out))
    design=json.loads(design_path.read_text());selection=json.loads(selection_path.read_text())
    cases=design['cases']
    if not 6<=len(cases)<=10 or len({c['case_id'] for c in cases})!=len(cases):raise ValueError('six to ten distinct finite source cases required')
    if design['sealed_fold6_body_read'] or design['new_model_calls']!=0:raise ValueError('CPU bounded development scope')
    for path,h in design['source_inputs_sha256'].items():
        if file_sha256(path)!=h:raise ValueError('original source input changed')
    chosen=source_only_selection(selection,cases)
    registry=load_bounded_registry(resources,metadata,design)
    tasks=[];envelopes=[];evals=[];bindings=[];pools=[];strata=[];goals=[]
    for case in cases:
        prefix=registry.prefix(case['owner'],case['anchor_session'],case['cut_turn']);registry.context(prefix)
        if prefix.fold==6 or prefix.owner_id in design['excluded_J06_owners']:raise ValueError('sealed or excluded family')
        legal=sorted((e for e in registry.entries if e.source.owner_id==prefix.owner_id and registry.reason(e.source_id,prefix) is None),
            key=lambda e:e.source.chronological_rank)
        if len(case['goals'])!=2 or {g['kind'] for g in case['goals']}!=set(GOALS):raise ValueError('paired fact/support goals required')
        atoms=[]
        for atom in case['atoms']:
            if atom['kind'] not in ('reported_fact','given_context','unresolved_boundary'):raise ValueError('atom kind')
            groups=[exact_group(registry,prefix,case['owner'],g) for g in atom['evidence_groups']]
            atoms.append(dict(atom_id=atom['id'],reference=atom['reference'],kind=atom['kind'],evidence_groups=groups,
                evidence_group_semantics='For reported facts, each listed group is an alternative sufficient original quotation/context; unresolved boundaries remain unresolved and are not proven by text matching.'))
        binding=dict(case_id=case['case_id'],owner_id=case['owner'],actual_prefix=plain(prefix),
            asof_runtime_sha256=prefix.runtime_sha256,atoms=atoms,temporal_boundary=case['temporal_boundary'],
            manual_locations_are_evaluator_only=True,source_clue_hypothesis=case['private_source_only_clue_hypothesis'])
        bindings.append(binding)
        for goal in case['goals']:
            query=goal['query']
            if not isinstance(query,str) or not query.strip():raise ValueError('actual visible goal required')
            if goal['kind']=='natural_support' and goal['required_atom_ids']:raise ValueError('support must not inherit exhaustive factual recital')
            reported={a['atom_id'] for a in atoms if a['kind']=='reported_fact'}
            if set(goal['required_atom_ids'])-reported:raise ValueError('unknown/unresolved fact cannot be required as a settled fact')
            for atom in atoms:verify_current_delivery(atom['evidence_groups'],query)
            task_id='pmtask:'+object_sha256([PROTOCOL,case['case_id'],goal['kind'],query])[:24]
            task=dict(task_id=task_id,timestamp=prefix.timestamp,turns=[dict(role='seeker',text=query)],query=query,
                view_protocol='source-derived-current-goal-with-real-prefix-anchor-v1')
            assert set(task)==RUNTIME_KEYS
            tasks.append(task)
            envelopes.append(dict(task_id=task_id,actual_prefix=plain(prefix),visible_task=task,
                visible_task_sha256=object_sha256(task),asof_runtime_sha256=prefix.runtime_sha256,
                anchor_scope='Real source prefix controls legality; its hidden body is not the current goal or a retrieval query.'))
            evals.append(dict(task_id=task_id,case_id=case['case_id'],goal_kind=goal['kind'],source_binding=binding,
                required_fact_ids=goal['required_atom_ids'],support_goal=goal['support_goal'],
                unresolved_boundary_ids=[a['atom_id'] for a in atoms if a['kind']=='unresolved_boundary'],
                evaluation_rules=design['rules'],review_status='assistant_source_development_not_independent_human',formal_reward=None))
            pools.append(dict(task_id=task_id,owner_id=prefix.owner_id,prefix_id=prefix.prefix_id,
                source_ids=[e.source_id for e in legal],session_ids=[e.source.session_id for e in legal],
                reports=[plain(e.reported_at) for e in legal],ready_at=[plain(e.ready_at) for e in legal],
                legal_count=len(legal),no_manual_source_removal=True,source_pool_sha256=object_sha256([e.source_id for e in legal])))
            strata.append(dict(task_id=task_id,case_id=case['case_id'],primary_type=case['primary_type'],goal_kind=goal['kind'],
                owner_id=case['owner'],family_component=next(i for i,f in enumerate(design['family_components']) if case['owner'] in f),
                original_fold=prefix.fold,original_split=prefix.split,selected_for_unapproved_G_proposal=case['case_id'] in chosen))
            if case['case_id'] in chosen:goals.append(task_id)
    if len(goals)!=8:raise ValueError('eight source-stratified future proposal goals required')
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    for name,rows in [('TASKS.runtime.jsonl',tasks),('TASK_ENVELOPES.private.jsonl',envelopes),
        ('EVALSPEC.private.jsonl',evals),('SOURCE_BINDINGS.private.jsonl',bindings),('FULL_LEGAL_POOLS.private.jsonl',pools),('STRATA.private.jsonl',strata)]:
        write_jsonl_once(out/name,rows)
    write_json_once(out/'FUTURE_G_SELECTION_PRIVATE.json',dict(selection,selected_task_ids=goals,
        task_manifest_sha256=file_sha256(out/'TASKS.runtime.jsonl'),authorized=False))
    lines=['# POMDP source-derived candidates — private source and goal record',
        'All evidence pointers and hypothetical bridge terms are evaluator-only. All legal sources remain available. No retrieval or model benefit is assumed.']
    for case,binding in zip(cases,bindings):
        lines+=['\n## '+case['case_id']+' / '+case['primary_type'],case['temporal_boundary'],
            'Hypothesis only: '+case['private_source_only_clue_hypothesis']]
        for goal in case['goals']:lines+=['\n### '+goal['kind'],goal['query'],'Required reported-fact ids: '+str(goal['required_atom_ids']),str(goal['support_goal'])]
        for atom in binding['atoms']:
            lines+=['\n'+atom['atom_id']+' ['+atom['kind']+'] '+atom['reference']]
            for g in atom['evidence_groups']:
                lines+=['- '+g['owner_id']+'/'+g['session_id']+' reported '+g['reported_at']['date']+' / '+g['source_status']]
                lines += ['  '+str(s['turn_index'])+' '+s['speaker']+': '+s['exact_quote'] for s in g['spans']]
    (out/'CASES_AND_EVIDENCE_PRIVATE.md').write_text('\n'.join(lines)+'\n')
    summary=dict(protocol=PROTOCOL,source_cases=len(cases),CPU_tasks=len(tasks),goal_counts=dict(Counter(x['goal_kind'] for x in strata)),
        source_family_components=len(design['family_components']),source_cache_sessions=len(registry.entries),
        source_type_counts=dict(Counter(c['primary_type'] for c in cases)),legal_pool_counts=[p['legal_count'] for p in pools],
        selected_future_G_tasks=8,future_G_authorized=False,model_calls=0,sealed_body_read=False,unseen_source_claim=False,
        original_splits_preserved=True,manual_source_pruning=False,generated_outputs_read=False,
        source_only_clue_hypotheses_are_not_success_labels=True)
    write_json_once(out/'SUMMARY_PUBLIC.json',summary)
    manifest=dict(protocol=PROTOCOL,files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},
        inputs_sha256={str(p.resolve()):file_sha256(p) for p in (resources,metadata,design_path,selection_path)},
        builder_sha256=file_sha256(__file__),code_dependencies_sha256={
            str(Path(__file__).with_name('selective_memory_validation_sources.py')):file_sha256(Path(__file__).with_name('selective_memory_validation_sources.py'))},
        manual_evidence_not_runtime=True,actual_new_G_calls=0)
    write_json_once(out/'MANIFEST.json',manifest)
    return summary
