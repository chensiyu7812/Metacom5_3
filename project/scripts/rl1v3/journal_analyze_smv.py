"""Recompute SMV30 from frozen inputs and explicit, unqualified observations.

Never infer semantic labels from answer keywords or convert evidence coverage
into success. Identical reused endpoints cancel their uncertainty in comparisons.
"""
import argparse,json
from collections import Counter
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once
from metacom_pm.rl1v3.journal.selective_memory_validation_review import validate_review

POLICIES=('STOP','MS','C1','simple_visible')
CHANNELS=('fact','natural_support','joint')

def jl(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]

def conjunction(items):
    if not items:return None
    if any(x in ('partial','omitted','unsupported','fail') for x in items):return [0,0]
    if any(x in ('unresolved','uncertain') for x in items):return [0,1]
    if not all(x in ('supported','pass') for x in items):raise ValueError('unreviewed/invalid state')
    return [1,1]

def total(rows,key):
    values=[r[key] for r in rows if r[key] is not None]
    return dict(denominator=len(values),bounds=[sum(v[i] for v in values) for i in (0,1)])

def delta(a,b,key):
    if a[key] is None or b[key] is None:return None
    if a['request_id']==b['request_id']:
        if a[key]!=b[key]:raise ValueError('same endpoint has inconsistent observations')
        return [0,0]
    return [a[key][0]-b[key][1],a[key][1]-b[key][0]]

def aggregate(rows):
    return dict(tasks=len(rows),completion=total(rows,'completion'),
        requested_facts=total(rows,'requested_facts'),support_operation=total(rows,'support_operation'),
        required_fact_slots=sum(r['required_fact_slots'] for r in rows),
        supplied_required_groups=sum(r['supplied_required_groups'] for r in rows),
        required_facts_expressed=sum(r['required_facts_expressed'] for r in rows),
        inputs=sum(r['input_tokens'] for r in rows),outputs=sum(r['output_tokens'] for r in rows),
        generation_seconds=sum(r['generation_seconds'] for r in rows),
        choices=dict(Counter(r['arm'] for r in rows)))

def analyze(source,actual,review,preparation,out):
    source,actual,review,preparation,out=map(Path,(source,actual,review,preparation,out))
    if out.exists():raise FileExistsError(out)
    requests={r['request_id']:r for r in jl(source/'requests-top4-v1/REQUESTS_ALL.private.jsonl')}
    tasks=jl(source/'source-bundle-v3/TASKS.runtime.jsonl')
    evals={r['task_id']:r for r in jl(source/'source-bundle-v3/EVALSPEC.private.jsonl')}
    responses={r['logical_id']:r for r in jl(actual/'ACTUAL_RESPONSES_PRIVATE.jsonl')}
    observations=jl(review/'DEVELOPMENT_REVIEW_PRIVATE.jsonl')
    supplies={(r['task_id'],r['arm']):r for r in jl(preparation/'SOURCE_SUPPLY_PRIVATE.jsonl')}
    choices=jl(source/'source-bundle-v3/POLICY_CHOICES.private.jsonl')
    if len(observations)!=len(responses) or {r['logical_id'] for r in observations}!=set(responses):raise ValueError('complete 30 endpoint review required')
    alias={t['task_id']:f'T{i:02d}' for i,t in enumerate(tasks,1)};cells=[]
    for r in observations:
        response=responses[r['logical_id']];request=requests[r['request_id']];ev=evals[r['task_id']]
        if response['evalspec_sha256']!=r['evalspec_sha256'] or response['payload_sha256']!=r['payload_sha256']:raise ValueError('response/review binding')
        output=response['output'];validate_review(r,request,ev,output_text=output['text'] if output else None,output_sha256=response['output_sha256'])
        if response['technical_status']!='eos':raise ValueError('this complete cohort analysis requires EOS; retain technical failure separately')
        supply=supplies[(r['task_id'],r['arm'])]
        required=[f for f in r['facts'] if f['required']]
        cells.append(dict(task=alias[r['task_id']],task_id=r['task_id'],arm=r['arm'],channel=ev['channel'],
            source_case=ev['source_case_id'],situation=ev['situation'],request_id=r['request_id'],
            payload_sha256=r['payload_sha256'],output_object_sha256=response['output_sha256'],
            completion=r['development_interval'],requested_facts=conjunction([f['status'] for f in required]),
            support_operation=None if ev['channel']=='fact' else conjunction([r['support']['status']]),
            required_fact_slots=len(required),required_facts_expressed=sum(f['status']=='supported' for f in required),
            supplied_required_groups=supply['supplied_required_groups'],
            prohibited_condition_failures=sum(p['status']=='fail' for p in r['prohibitions']),
            unresolved_support=r['support']['status']=='uncertain',unresolved_reference_disputes=sum(d['status']=='unresolved' for d in r['source_or_reference_disputes']),
            additional_unsupported_claims=sum(c['status']=='unsupported' for c in r['additional_claims']),
            additional_uncertain_claims=sum(c['status'] in ('uncertain','unresolved') for c in r['additional_claims']),
            input_tokens=output['input_tokens'],output_tokens=len(output['token_ids']),generation_seconds=output['seconds'],
            formal_reward=None))
    by={(r['task_id'],r['arm']):r for r in cells};policies={};comparisons={};pairs=[]
    for policy in POLICIES:
        selected=[by[(c['task_id'],c[policy])] for c in choices]
        policies[policy]=dict(all=aggregate(selected),channels={ch:aggregate([r for r in selected if r['channel']==ch]) for ch in CHANNELS})
        against=[by[(c['task_id'],'MS')] for c in choices];differences={};savings={}
        for ch in ('all',*CHANNELS):
            applicable=[(a,b) for a,b in zip(selected,against) if ch=='all' or a['channel']==ch]
            differences[ch]={}
            for key in ('completion','requested_facts','support_operation'):
                ds=[delta(a,b,key) for a,b in applicable];ds=[d for d in ds if d is not None]
                differences[ch][key]=[sum(d[i] for d in ds) for i in (0,1)] if ds else None
        for a,b in zip(selected,against):
            if a['request_id']==b['request_id']:kind='same_endpoint'
            elif a['completion']==b['completion']==[1,1]:kind='both_definite_success'
            elif a['completion']==b['completion']==[0,0]:kind='both_definite_failure'
            elif [0,1] in (a['completion'],b['completion']):kind='uncertain_selection'
            elif a['completion']==[1,1]:kind='definite_repair'
            else:kind='definite_regression'
            s=savings.setdefault(kind,dict(tasks=0,input_saved=0,output_saved=0,task_aliases=[]))
            s['tasks']+=1;s['input_saved']+=b['input_tokens']-a['input_tokens'];s['output_saved']+=b['output_tokens']-a['output_tokens'];s['task_aliases'].append(a['task'])
        comparisons[policy]=dict(paired_difference_from_fixed_MS=differences,cost_savings_by_outcome=savings)
    for t in tasks:
        a,b=by[(t['task_id'],'STOP')],by[(t['task_id'],'MS')]
        pairs.append(dict(task=a['task'],channel=a['channel'],source_case=a['source_case'],STOP=a,MS=b,
            MS_minus_STOP={k:delta(b,a,k) for k in ('completion','requested_facts','support_operation')},
            frozen_choices={p:next(c for c in choices if c['task_id']==t['task_id'])[p] for p in POLICIES}))
    report=dict(protocol='SMV30-static-development-analysis-v1',tasks=15,source_situations=5,source_families=3,
        physical_model_calls=30,logical_policy_choices=60,channels=list(CHANNELS),policies=policies,comparisons=comparisons,
        semantic_reference='assistant_source_authored_development',independent_human_evaluation=False,formal_reward=None,
        uncertainty_is_not_zero=True,no_effect_claim_about_sequential_decisions=True,
        analysis_code_sha256=file_sha256(__file__),review_records_sha256=file_sha256(review/'DEVELOPMENT_REVIEW_PRIVATE.jsonl'),
        old_evaluation_sha256=file_sha256(source/'source-bundle-v3/EVALSPEC.private.jsonl'),
        frozen_policy_sha256=file_sha256(source/'source-bundle-v3/POLICY_CHOICES.private.jsonl'),
        limits=['Three already-exposed source families; correlated channel variants.',
                'Policy rows reuse the same 30 endpoints; they are not 60 independent model outputs.',
                'Whole-task uncertainty includes scope/briefness; mechanical checks do not qualify semantics.',
                'Selected generation sums are observed components, not measured deployed client latency.'])
    out.mkdir(parents=True)
    write_json_once(out/'SMV30_SUMMARY_PUBLIC.json',report)
    write_json_once(out/'SMV30_TASKWISE_PUBLIC.json',dict(protocol=report['protocol'],rows=pairs,formal_reward=None))
    mark=lambda v:'NA' if v is None else '1' if v==[1,1] else '0' if v==[0,0] else '?'
    text=['# SMV30逐题开发观察','原任务/来源/策略/合同不变。自然支持没有必答事实清单；NA不是满分。?保留不确定，不是置信区间。',
        '|题|通道|STOP事实/支持/完整|MS事实/支持/完整|STOP→MS必要供证|STOP→MS输入/输出tokens|C1|简单基线|',
        '|---|---|---|---|---:|---:|---|---|']
    for r in pairs:
        a,b=r['STOP'],r['MS'];dims=lambda v:'/'.join(mark(v[k]) for k in ('requested_facts','support_operation','completion'))
        text.append('|'+ '|'.join([r['task'],r['channel'],dims(a),dims(b),f"{a['supplied_required_groups']}→{b['supplied_required_groups']}/{a['required_fact_slots']}",f"{a['input_tokens']}/{a['output_tokens']}→{b['input_tokens']}/{b['output_tokens']}",r['frozen_choices']['C1'],r['frozen_choices']['simple_visible']])+'|')
    (out/'SMV30_TASKWISE_ZH.md').write_text('\n'.join(text)+'\n')
    return {p:report['policies'][p]['all'] for p in POLICIES}

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for k in ('source','actual','review','preparation','out'):p.add_argument('--'+k,required=True)
    print(json.dumps(analyze(**vars(p.parse_args())),indent=2))
