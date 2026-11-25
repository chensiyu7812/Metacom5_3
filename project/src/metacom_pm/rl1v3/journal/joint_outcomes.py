"""Evidence-bound development intervals and fixed-policy J06 replay summaries.

No unknown-to-zero conversion, reward qualification, policy fitting or model calls.
Fact and support reviews are joined by exact logical and response identities.
"""
from collections import Counter,defaultdict
import json
from pathlib import Path
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from .joint_results import jl,validate_support_review
from .joint_policies import ARMS,PROTOCOL as POLICY_PROTOCOL

FACT_INTERVAL={'supported':[1,1],'partial':[0,0],'omitted':[0,0],'unsupported':[0,0],'unresolved':[0,1]}

def conjunction(intervals):
    if any(x is None for x in intervals):return None
    if not intervals:raise ValueError('necessary criteria may not be empty')
    return [min(x[0] for x in intervals),min(x[1] for x in intervals)]

def interaction(values):
    if any(values.get(k) is None for k in ARMS):return None
    y00,y10,y01,y11=(values[k] for k in ARMS)
    return [y11[0]-y10[1]-y01[1]+y00[0],y11[1]-y10[0]-y01[0]+y00[1]]

def transition(before,after):
    if before is None or after is None or before[0]!=before[1] or after[0]!=after[1]:return 'uncertain'
    if before==[0,0] and after==[1,1]:return 'repair'
    if before==[1,1] and after==[0,0]:return 'new_fail'
    return 'maintain_success' if after==[1,1] else 'maintain_failure'


def paired_difference(before,after,*,same_endpoint=False):
    if before is None or after is None:return None
    if same_endpoint:
        if before!=after:raise ValueError('shared endpoint intervals differ')
        return [0,0]
    return [after[0]-before[1],after[1]-before[0]]


def metrics(rows):
    result=dict(n=len(rows),technical_unavailable=sum(r['joint_interval'] is None for r in rows))
    for dim in ('fact','support','joint'):
        known=[r[dim+'_interval'] for r in rows if r[dim+'_interval'] is not None]
        result[dim]=dict(evaluable=len(known),lower_count=sum(x[0] for x in known),upper_count=sum(x[1] for x in known),
            lower_rate=sum(x[0] for x in known)/len(known) if known else None,
            upper_rate=sum(x[1] for x in known)/len(known) if known else None,
            uncertain=sum(x[0]!=x[1] for x in known))
    unique={r['request_id']:r for r in rows if r['output_present']}
    result['cost']=dict(physical_outputs=len(unique),input_tokens=sum(r['cost']['input_tokens'] for r in unique.values()),
        output_tokens=sum(r['cost']['output_tokens'] for r in unique.values()),
        generation_seconds=sum(r['cost']['generation_seconds'] for r in unique.values()),
        instrumented_path_cpu_ms=sum(r['cost']['path_cpu_ms'] for r in rows),
        load_guard_cost_not_allocated_to_counterfactual_policy=True,not_client_end_to_end_latency=True)
    return result


def merge(joint_root,out):
    root,out=Path(joint_root),Path(out);out.mkdir(parents=True,exist_ok=False)
    bundle=root/'source-bundle-v1';package=root/'packages-v5'
    evals={r['task_id']:r for r in jl(bundle/'EVALSPEC.private.jsonl')}
    policy=json.loads((root/'POLICIES_PREOUTPUT.json').read_text())
    assert policy['protocol']==POLICY_PROTOCOL and policy['runtime_sha256']==file_sha256(bundle/'TASKS.runtime.jsonl')
    assert policy['generated_output_files_read']==policy['evalspec_files_read']==0
    responses=[];facts=[];supports=[];inputs={}
    for n in range(1,7):
        paths=[root/f'actual-v1/batch-{n:02d}/ACTUAL_RESPONSES_PRIVATE.jsonl',
            root/f'fact-review-v1/BATCH_{n:02d}_FACT_REVIEW_PRIVATE.jsonl',root/f'support-review-v1/BATCH{n:02d}_SUPPORT_PRIVATE.jsonl']
        for dest,p in zip((responses,facts,supports),paths):dest.extend(jl(p));inputs[str(p)]=file_sha256(p)
    if any(len(x)!=96 or len({r['logical_id'] for r in x})!=96 for x in (responses,facts,supports)):
        raise ValueError('all 96 response/fact/support identities required once')
    facts={r['logical_id']:r for r in facts};supports={r['logical_id']:r for r in supports}
    path_cost={(r['task_id'],r['arm']):r for r in jl(package/'READ_CHECKS.private.jsonl')}
    disputes={}
    for p in sorted((root/'fact-review-v1').glob('*UNCERTAINTY*.json')):
        side=json.loads(p.read_text());inputs[str(p)]=file_sha256(p)
        for item in side.get('affected_atoms',[]):
            key=(item['logical_id'],item['atom_id'])
            if key in disputes:raise ValueError('duplicate fact interpretation sidecar; require explicit resolution')
            disputes[key]=item
    joined=[]
    for response in responses:
        lid=response['logical_id'];fact=facts[lid];support=supports[lid];e=evals[response['task_id']]
        for review in (fact,support):
            for key in ('logical_id','task_id','arm','request_id','output_sha256','evalspec_sha256'):
                if review[key]!=response[key]:raise ValueError('review join mismatch: '+key)
            if review['formal_reward'] is not None:raise ValueError('formal reward must remain null')
        validate_support_review(support,response,e)
        text=response['output']['text'] if response['output'] else ''
        atom_ids={r['id'] for r in e['personal_fact_references']}
        if {a['id'] for a in fact['fact_atoms']}!=atom_ids:raise ValueError('original fact coverage')
        original=[];effective=[];scope=[]
        for a in fact['fact_atoms']:
            if a['status'] not in FACT_INTERVAL:raise ValueError('unknown fact status')
            if any(q not in text for q in a['output_quotes']):raise ValueError('fact quote not in actual output')
            original.append(FACT_INTERVAL[a['status']]);d=disputes.get((lid,a['id']))
            if d:
                if d['original_status']!=a['status'] or d['completion_interval']!=[0,1]:raise ValueError('unexpected context reinterpretation')
                effective.append(d['completion_interval']);scope.append(d)
            else:effective.append(FACT_INTERVAL[a['status']])
        values=[x['verdict'] for name in ('requirements','prohibitions') for x in support[name].values()]
        si=[0,0] if 'fail' in values else [0,1] if 'uncertain' in values else [1,1]
        if si!=support['support_interval']:raise ValueError('support arithmetic mismatch')
        fi=conjunction(effective);original_fi=conjunction(original)
        if response['technical_status']!='eos':fi=si=original_fi=None
        output=response['output'];pc=path_cost[(response['task_id'],response['arm'])]
        joined.append(dict(logical_id=lid,task_id=response['task_id'],arm=response['arm'],request_id=response['request_id'],
            endpoint_id=response['endpoint_id'],output_sha256=response['output_sha256'],evalspec_sha256=response['evalspec_sha256'],
            source_group=e['source_binding']['owner_id'],source_case_id=e['source_case_id'],stratum=e['needs_stratum_private'],
            fact_interval=fi,original_fact_interval=original_fi,support_interval=si,joint_interval=conjunction([fi,si]),
            fact_review=fact,support_review=support,context_interpretation_disputes=scope,
            temporal_truth_and_report_constraint_are_separate=True,formal_reward=None,output_present=output is not None,
            technical_status=response['technical_status'],cost=dict(input_tokens=output['input_tokens'] if output else 0,
                output_tokens=len(output['token_ids']) if output else 0,generation_seconds=output['seconds'] if output else 0,
                path_cpu_ms=pc['online_path_cpu_ms'])))
    by_task=defaultdict(dict)
    for row in joined:by_task[row['task_id']][row['arm']]=row
    if len(by_task)!=24 or any(set(a)!=set(ARMS) for a in by_task.values()):raise ValueError('incomplete four-arm task')
    fixed={};fixed_groups={};fixed_strata={};original_sensitivity={}
    for name,assignments in policy['policies'].items():
        selected=[by_task[a['task_id']][a['arm']] for a in assignments]
        fixed[name]=metrics(selected)
        original_rows=[dict(r,fact_interval=r['original_fact_interval'],joint_interval=conjunction([r['original_fact_interval'],r['support_interval']])) for r in selected]
        original_sensitivity[name]=metrics(original_rows)
        gaps=[]
        for r in selected:
            others=[v for a,v in by_task[r['task_id']].items() if a!=r['arm'] and v['joint_interval'] is not None]
            if r['joint_interval'] is None or not others:continue
            gaps.append([max(0,max(v['joint_interval'][0] for v in others)-r['joint_interval'][1]),
                max(0,max(v['joint_interval'][1] for v in others)-r['joint_interval'][0])])
        fixed[name]['privileged_oracle_advantage_interval']=dict(evaluable_tasks=len(gaps),
            lower=sum(g[0] for g in gaps),upper=sum(g[1] for g in gaps),
            selected_arm_shared_unknown_not_counted_as_its_own_advantage=True,
            conservative_interval_not_independent_confirmatory_effect=True)
        fixed_groups[name]={g:metrics([r for r in selected if r['source_group']==g]) for g in sorted({r['source_group'] for r in selected})}
        fixed_strata[name]={s:metrics([r for r in selected if r['stratum']==s]) for s in sorted({r['stratum'] for r in selected})}
    oracle_lower=[];oracle_upper=[];pareto=[];interactions=[]
    for tid,arms in by_task.items():
        rows=[arms[a] for a in ARMS];valid=[r for r in rows if r['joint_interval'] is not None]
        if valid:
            oracle_lower.append(min(valid,key=lambda r:(-r['joint_interval'][0],-r['joint_interval'][1],r['cost']['input_tokens'],ARMS.index(r['arm']))))
            oracle_upper.append(min(valid,key=lambda r:(-r['joint_interval'][1],-r['joint_interval'][0],r['cost']['input_tokens'],ARMS.index(r['arm']))))
        non=[r for r in valid if not any(o['joint_interval'][0]>=r['joint_interval'][1] and o['cost']['input_tokens']<=r['cost']['input_tokens']
            and (o['joint_interval'][0]>r['joint_interval'][1] or o['cost']['input_tokens']<r['cost']['input_tokens']) for o in valid if o is not r)]
        pareto.append(dict(task_id=tid,source_group=rows[0]['source_group'],stratum=rows[0]['stratum'],robust_nondominated_arms=[r['arm'] for r in non],
            points=[dict(arm=r['arm'],joint_interval=r['joint_interval'],input_tokens=r['cost']['input_tokens']) for r in valid],weighted_utility_used=False))
        interactions.append(dict(task_id=tid,source_group=rows[0]['source_group'],stratum=rows[0]['stratum'],
            fact_interaction=interaction({a:r['fact_interval'] for a,r in arms.items()}),
            support_interaction=interaction({a:r['support_interval'] for a,r in arms.items()}),
            joint_interaction=interaction({a:r['joint_interval'] for a,r in arms.items()}),
            input_token_interaction=arms['MS_RS']['cost']['input_tokens']-arms['MS']['cost']['input_tokens']-arms['RS']['cost']['input_tokens']+arms['STOP']['cost']['input_tokens']))
    def interaction_summary(selected):
        out=dict(n=len(selected))
        for dim in ('fact','support','joint'):
            values=[r[dim+'_interaction'] for r in selected if r[dim+'_interaction'] is not None]
            out[dim]=dict(evaluable=len(values),sum_lower=sum(v[0] for v in values),sum_upper=sum(v[1] for v in values),
                mean_lower=sum(v[0] for v in values)/len(values) if values else None,
                mean_upper=sum(v[1] for v in values)/len(values) if values else None)
        return out
    contrasts=(('STOP','MS'),('STOP','RS'),('STOP','MS_RS'),('MS','MS_RS'),('RS','MS_RS'))
    transitions=[];transition_counts={}
    ordered_ids=[r['task_id'] for r in jl(bundle/'TASKS.runtime.jsonl')]
    source_alias={}
    for index,tid in enumerate(ordered_ids,1):
        arms=by_task[tid];source=arms['STOP']['source_group'];source_alias.setdefault(source,'G'+str(len(source_alias)+1).zfill(2))
        for before,after in contrasts:
            row=dict(task_label='J'+str(index).zfill(2),source_group=source_alias[source],stratum=arms['STOP']['stratum'],before=before,after=after,dimensions={})
            for dim in ('fact','support','joint'):
                x,y=arms[before][dim+'_interval'],arms[after][dim+'_interval']
                row['dimensions'][dim]=dict(before_interval=x,after_interval=y,transition=transition(x,y),
                    change_interval=[y[0]-x[1],y[1]-x[0]] if x is not None and y is not None else None)
            transitions.append(row)
    for before,after in contrasts:
        selected=[r for r in transitions if (r['before'],r['after'])==(before,after)]
        transition_counts[before+'__'+after]={dim:dict(Counter(r['dimensions'][dim]['transition'] for r in selected)) for dim in ('fact','support','joint')}
    failure_counts=dict(logical_denominator=96,counts_overlap=True,causal_attribution_claimed=False,
        support_fail_by_criterion={c:sum(r['support_review']['requirements' if c.startswith('s') else 'prohibitions'][c]['verdict']=='fail' for r in joined) for c in ('s1','s2','p1','p2')},
        support_uncertain_by_criterion={c:sum(r['support_review']['requirements' if c.startswith('s') else 'prohibitions'][c]['verdict']=='uncertain' for r in joined) for c in ('s1','s2','p1','p2')},
        original_fact_atom_status_counts=dict(Counter(a['status'] for r in joined for a in r['fact_review']['fact_atoms'])),
        known_fact_incomplete_rows=sum(r['fact_interval']==[0,0] for r in joined),
        known_support_noncompliance_rows=sum(r['support_interval']==[0,0] for r in joined),
        unresolved_joint_rows=sum(r['joint_interval']==[0,1] for r in joined),
        actual_operation_observations=dict(Counter(r['support_review']['actual_operation'] for r in joined)))
    overall=dict(protocol='joint24-development-interval-analysis-v2',tasks=24,logical_responses=96,source_groups=6,
        original_fact_observations_preserved=True,context_uncertainty_atoms=len(disputes),
        fixed_policies=fixed,original_observation_sensitivity=original_sensitivity,privileged_oracle=dict(lower_bound_selector=metrics(oracle_lower),upper_bound_selector=metrics(oracle_upper),
            not_deployable=True,uses_output_and_reference=True,cost_weight=None),
        interactions=interaction_summary(interactions),
        arms={arm:metrics([r for r in joined if r['arm']==arm]) for arm in ARMS},
        formal_reward_qualified=False,training_table_complete=False,reference_status='assistant development reviews, not independent human qualification',
        source_cluster_dependence='24 tasks are four constructed variants from each of six source contexts; not 24 independent cases',
        cost_scope='Measured selected call replays and CPU paths; model load/guards are actual experiment overhead, not allocated policy latency.',
        inputs_sha256=inputs,policy_sha256=file_sha256(root/'POLICIES_PREOUTPUT.json'),code_sha256=file_sha256(__file__))
    baseline=fixed['always_STOP']
    for name,m in fixed.items():
        differences=[paired_difference(by_task[a['task_id']]['STOP']['joint_interval'],
            by_task[a['task_id']][a['arm']]['joint_interval'],same_endpoint=a['arm']=='STOP')
            for a in policy['policies'][name]]
        evaluable=[d for d in differences if d is not None]
        m['versus_always_STOP']=dict(joint_gain_interval=[sum(d[0] for d in evaluable),sum(d[1] for d in evaluable)],
            evaluable_tasks=len(evaluable),shared_endpoint_difference_is_zero=True,
            input_token_delta=m['cost']['input_tokens']-baseline['cost']['input_tokens'])
    write_jsonl_once(out/'JOINED_ENDPOINTS_PRIVATE.jsonl',joined);write_jsonl_once(out/'INTERACTIONS_PRIVATE.jsonl',interactions)
    write_jsonl_once(out/'TASKWISE_PARETO_PRIVATE.jsonl',pareto)
    write_json_once(out/'FIXED_SOURCE_GROUPS_PUBLIC.json',fixed_groups);write_json_once(out/'FIXED_STRATA_PUBLIC.json',fixed_strata)
    write_json_once(out/'INTERACTIONS_SOURCE_GROUPS_PUBLIC.json',{g:interaction_summary([r for r in interactions if r['source_group']==g]) for g in sorted({r['source_group'] for r in interactions})})
    write_json_once(out/'INTERACTIONS_STRATA_PUBLIC.json',{s:interaction_summary([r for r in interactions if r['stratum']==s]) for s in sorted({r['stratum'] for r in interactions})})
    write_json_once(out/'PAIR_TRANSITIONS_PUBLIC.json',dict(tasks=24,comparisons=transitions))
    write_json_once(out/'PAIR_TRANSITION_COUNTS_PUBLIC.json',transition_counts)
    write_json_once(out/'FAILURE_ATTRIBUTION_PUBLIC.json',failure_counts)
    write_json_once(out/'AGGREGATE_PUBLIC.json',overall);return overall
