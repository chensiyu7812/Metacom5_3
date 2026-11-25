"""Build one source-bound joint development bundle, without reading outcomes.

Private source recipes and evaluator references are external inputs. Runtime
questions, legal AsOf anchors, and evaluation material use separate files. A
source prefix is a temporal anchor; constructed text never impersonates it.
"""
from collections import Counter
import json
from pathlib import Path

from ..io import canonical_json, file_sha256, object_sha256
from ..sources import source_registry as S
from .rs_tasks import write_once
from .skills import build_skills

PROTOCOL='pmrl1-j-joint24-source-bundle-v1'
STRATA=('memory_only','RS_only','both','neither')
RUNTIME_KEYS={'task_id','timestamp','turns','query','view_protocol'}


def canonical(value):
    return json.loads(canonical_json(value))


def procedure(design, sources):
    if design['number_of_new_procedures']!=1 or design['professional_approval'] is not False or design['case_examples']:
        raise ValueError('one unapproved procedure without CASE required')
    skills={r['skill_id'].removeprefix('skill:'):r for r in build_skills(sources)}
    refs=[]
    for key in design['source_skill_keys']:
        refs.extend(skills[key]['source_refs'])
    if not refs or any(r['section']!='ch6.s2.1' for r in refs):
        raise ValueError('same formal TIP35 planning/information section required')
    text=design['title']+'\nEnter only when: '+' '.join(design['entry_conditions'])+'\nProcedure:\n'+'\n'.join(f'{n}. {step}' for n,step in enumerate(design['steps'],1))+'\nStop or change approach when: '+' '.join(design['stop_conditions'])
    identity=object_sha256(dict(version=design['version'],reading_text=text,source_refs=refs))
    return dict(candidate_id='jrs-procedure:'+identity,view='method',reading_text=text,
        source_title='SAMHSA TIP35 (2019), Chapter 6, Negotiating a Change Plan',
        source_sha256=refs[0]['file_sha256'],official_url=refs[0]['url'],source_refs=refs,
        applicability=design['entry_conditions'],procedure=design['steps'],stop_conditions=design['stop_conditions'],
        adaptation_delta=design['adaptation_delta'],root_cause_scope=design['root_cause_scope'],
        professional_approval=False,case_examples=[],legally_available_independent_of_applicability=True,
        retrieval_scope='Single legally available candidate, visible-query matching diagnostic only; no multi-candidate ranking claim.')


def build(*, registry_path, design_path, procedure_path, sources, out):
    registry_path,design_path,procedure_path,sources,out=map(Path,(registry_path,design_path,procedure_path,sources,out))
    if out.exists():raise FileExistsError('new frozen bundle directory required')
    design=json.loads(design_path.read_text());pd=json.loads(procedure_path.read_text())
    if design['no_current_T_or_S_outputs_read'] is not True:raise ValueError('source-only pre-outcome authoring required')
    cases=design['cases'];owners={c['owner'] for c in cases}
    if not 1<=len(cases)<=6 or len(owners)!=len(cases):raise ValueError('at most six distinct owner situations')
    registry=S.load(registry_path);tasks=[];envelopes=[];evals=[];bindings=[];strata=[]
    rs=procedure(pd,sources)
    for case in cases:
        owner=case['owner'];entry=registry.entry(owner,case['session']);source=entry.source
        if registry.folds['historical_rl1_split'][owner]!='train':raise ValueError('preserve old held-out split')
        index=entry.original_turn_indices.index(case['original_idx']);turn=source.turns[index]
        if turn.role!='seeker' or turn.text!=case['quote']:raise ValueError('actual source quotation/role mismatch')
        current=next(e for e in registry.entries if e.source.owner_id==owner and e.source.dataset==S.DATASET and e.source.chronological_rank==source.chronological_rank+1)
        cut=next(i for i,t in enumerate(current.source.turns[:-1]) if t.role=='seeker' and current.source.turns[i+1].role=='supporter')
        prefix=registry.prefix(owner,current.source.session_id,cut)
        if registry.reason(entry.source_id,prefix) is not None:raise ValueError('source is not legal strict past')
        _,history=registry.context(prefix)
        span=S.span(source,index)
        binding=dict(case_id=case['key'],owner_id=owner,source_id=entry.source_id,
            source_session_id=source.session_id,source_rank=source.chronological_rank,
            source_turn_index=index,original_turn_index=case['original_idx'],source_span=canonical(span),
            exact_quote=turn.text,quote_sha256=object_sha256(turn.text),reported_at=canonical(entry.reported_at),ready_at=canonical(entry.ready_at),
            source_family_id=source.family_id,source_ancestor_family_ids=list(source.ancestor_family_ids),
            asof_prefix=canonical(prefix),asof_runtime_sha256=prefix.runtime_sha256,
            legal_history_source_ids=[registry.entry(owner,s.session_id).source_id for s in history],
            source_split=prefix.split,fold=prefix.fold,constructed_visible_view_not_source_prefix=True)
        bindings.append(binding)
        for stratum in STRATA:
            query=case['queries'][stratum]
            if not isinstance(query,str) or not query.strip():raise ValueError('actual readable task required')
            fact_current=stratum in {'RS_only','neither'}
            if fact_current!=(turn.text in query):raise ValueError('declared current-fact manipulation differs')
            tid='jtask:'+object_sha256([PROTOCOL,case['key'],stratum,query])[:24]
            task=dict(task_id=tid,timestamp=prefix.timestamp,turns=[dict(role='seeker',text=query)],query=query,
                view_protocol='constructed-current-request-with-real-past-asof-v1')
            tasks.append(task)
            envelopes.append(dict(task_id=tid,owner_id=owner,session_id=prefix.session_id,cut_turn=prefix.cut_turn,
                as_of=prefix.timestamp,actual_prefix=canonical(prefix),asof_runtime_sha256=prefix.runtime_sha256,
                visible_task_sha256=object_sha256(task),visible_task=task,
                anchor_scope='Actual source PrefixSpec only for legal availability; constructed visible request has a separate binding.',
                resource_policy=dict(MS='all and only same-owner strict-past completed sessions from registry/ledger AsOf',
                    RS='same single legal external procedure for every arm; generator follows applicability and stop conditions',
                    forbidden_heads=['MP','ME'],retrieval_inputs='visible_task.query plus legal pool only; never evaluation fields')))
            support_requested=stratum in {'RS_only','both'}
            requirements=[dict(id='s1',criterion='Use only warranted reported personal facts; do not turn an intention or an earlier report into a completed action or an assured current condition.'),
                dict(id='s2',criterion=('Perform or elicit one concrete voluntary next step responsive to the explicit practical request; an appropriate specific feasibility question is allowed. Merely asking permission again or generic emotion discussion does not supply the requested operation.' if support_requested else 'Give the requested brief fact recall/acknowledgement without adding advice, planning, or new questions.'))]
            evals.append(dict(task_id=tid,source_case_id=case['key'],needs_stratum_private=stratum,
                origin='constructed_development_task',independent_confirmatory=False,
                source_binding=bindings[-1],personal_fact_references=case['facts'],fact_available_in_current_view=fact_current,
                support_goal=case['goal'] if support_requested else 'Brief factual recall/acknowledgement, without advice or plan.',
                requirements=requirements,prohibitions=[dict(id='p'+str(n),criterion=x) for n,x in enumerate(case['avoid'] if support_requested else ['Invent a personal fact, event, timing, or outcome.','Add an unsolicited advice, plan, or question despite the present request.'],1)],
                allowed_alternatives=(['A concrete draft or optional step aligned with the visible goal.','One specific missing-feasibility clarification necessary to proceed.','Safe acknowledgement of an unlocated historical fact, without guessing, plus only help that does not depend on the unknown.'] if support_requested else ['Concise accurate paraphrase of the reported fact.','If the earlier fact cannot be located, explicit non-recall without guessing; this is safe abstention but not factual completion.']),
                evaluation_rules=dict(fact_completion='Report each original fact atom as supported/partial/omitted/unsupported/unresolved with evidence. Safe non-recall is not factual completion and is not a fabricated-fact error.',
                    support='Original requirements/prohibitions pass/fail/uncertain with exact reply evidence; allow declared alternatives. No criterion requires a particular head, call, or selected method.',
                    joint_success='All factual atoms completed and support items met -> development complete; substantiated omission/violation -> incomplete; unresolved semantics retained as interval. Formal reward remains null.',
                    interaction='Four paired arms on identical current view/query/pool. Report fact, support, joint outcome, errors and cost separately; Y11-Y10-Y01+Y00 only when outcomes are resolved, otherwise interval.',
                    technical='Length/empty/technical failure separate; do not convert technical or semantic unknown into success.'),
                formal_reward=None,professional_review_status='pending',assistant_authored_not_independent_human_reference=True))
            strata.append(dict(task_id=tid,source_case_id=case['key'],owner_family=owner,stratum=stratum,
                expected_need_is_not_forced_call_label=True,source_split=prefix.split,fold=prefix.fold))
    counts=Counter(x['stratum'] for x in strata)
    if set(counts)!=set(STRATA) or set(counts.values())!={len(cases)}:raise ValueError('balanced original four conditions required')
    for task in tasks:
        if set(task)!=RUNTIME_KEYS:raise ValueError('runtime allowlist')
    write_once(out/'TASKS.runtime.jsonl',tasks,lines=True)
    write_once(out/'TASK_ENVELOPES.private.jsonl',envelopes,lines=True)
    write_once(out/'EVALSPEC.private.jsonl',evals,lines=True)
    write_once(out/'SOURCE_BINDINGS.private.json',bindings)
    write_once(out/'DEMAND_STRATA.private.jsonl',strata,lines=True)
    write_once(out/'RS_PROCEDURE.private.jsonl',[rs],lines=True)
    text=['# 联合24开发任务：可读源与评估（私有）','四类是生成前需求分层，不是必须调用工具的答案。24题来自6个owner情境，不能当作24个独立来源样本。',
        '真实PrefixSpec只绑定AsOf合法历史；当前任务是另有身份的构造请求，不能冒充原自然对话。']
    for ev,task in zip(evals,tasks):
        text+=['\n## '+task['task_id']+' / '+ev['needs_stratum_private'],'\n### 可见任务\n'+task['query'],
            '\n### 真实来源和原评价规则\n```json\n'+json.dumps(ev,ensure_ascii=False,indent=2)+'\n```']
    (out/'READABLE_TASKS_PRIVATE.md').write_text('\n'.join(text)+'\n')
    summary=dict(protocol=PROTOCOL,tasks=len(tasks),owner_source_situations=len(cases),strata=dict(counts),
        original_source_split='train',original_folds_retained=True,
        independent_source_units_not_task_count=True,constructed_current_views=True,
        real_asof_anchors_verified=len(cases),source_quotes_exact=len(cases),strict_past_source_legality_checked=len(cases),
        additional_procedure_candidates=1,professional_or_CASE_approval=False,
        same_view_query_pool_per_task_across_arms=True,heads=['MS','RS'],masked_heads=['MP','ME'],
        intended_arms=['STOP','MS','RS','MS_then_RS'],max_logical_generations=4*len(tasks),
        current_TS_outcomes_read=0,new_model_calls=0,formal_reward=None,old_frozen_files_changed=0,
        RS_selection_scope='Single legal procedure with visible-query applicability diagnostic; no multi-candidate ranking evidence.',
        scientific_limit='Demand strata are constructed pre-generation hypotheses, not oracle action labels. Single-arm RS12 negative evidence remains; synergy is unestablished.')
    write_once(out/'SUMMARY_PUBLIC.json',summary)
    manifest=dict(protocol=PROTOCOL,registry_version=registry.version,
        inputs_sha256={str(p.resolve()):file_sha256(p) for p in [registry_path/'registry.json',registry_path/'sources.jsonl',design_path,procedure_path]},
        source_documents_sha256={str((sources/r['file']).resolve()):r['file_sha256'] for r in rs['source_refs']},
        files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},code_sha256=file_sha256(__file__),
        generated_output_files_read=0,formal_reward=None)
    write_once(out/'MANIFEST.json',manifest)
    return summary


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser()
    for k in ('registry-path','design-path','procedure-path','sources','out'):p.add_argument('--'+k,required=True)
    print(json.dumps(build(**vars(p.parse_args())),ensure_ascii=False,indent=2))
