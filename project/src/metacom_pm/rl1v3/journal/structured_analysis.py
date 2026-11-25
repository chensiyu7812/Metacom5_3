"""Read-only paired analysis of fixed structured endpoints; no reward promotion.

Policies use only visible request text. Gold/outputs enter solely in evaluation.
All source text and field labels are private inputs, never public module data.
"""
from collections import Counter,defaultdict
import html
import json
from pathlib import Path
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once

POLICY_PROTOCOL='pmrl1-j-structured-fixed-policies-v1'
VISIBLE_MARKER='\nVisible evidence ('
POLICIES=('always_BASE','always_RAW','visible_evidence_rule')


def jl(p):return [json.loads(x) for x in Path(p).read_text().splitlines()]


def choose(policy,base_request):
    if policy=='always_BASE':return 'BASE'
    if policy=='always_RAW':return 'RAW'
    if policy!='visible_evidence_rule':raise ValueError('unknown fixed policy')
    text=base_request['model_input']['messages'][-1]['content']
    return 'BASE' if VISIBLE_MARKER in text else 'RAW'


def freeze_policies(requests,out):
    """Only the request file is read; no reference, output, or task gold input."""
    requests,out=Path(requests),Path(out)
    rows=jl(requests);base=[r for r in rows if r['arm']=='BASE']
    assert len(base)==18
    manifest=dict(protocol=POLICY_PROTOCOL,request_sha256=file_sha256(requests),
        inputs_read=[str(requests)],references_read=0,model_outputs_read=0,
        policies={name:[dict(task_id=r['task_id'],arm=choose(name,r)) for r in base] for name in POLICIES},
        visible_rule=dict(marker=VISIBLE_MARKER,if_present='BASE',otherwise='RAW',
            information='public prompt marker only; no answer value, task annotation, reference, future or output',
            limitation='constructed visible-evidence marker, not a learned or natural-dialogue classifier'),
        privileged_taskwise_best=dict(qualification='diagnostic upper bound, not deployable policy',
            choice='max strict task_success; tie lower input tokens, then BASE',
            missing='unknown when an unobserved arm could improve current known best'),
        cost='sum selected unique request input/output tokens and generation wall; one execution per physical request',
        formal_reward_qualified=False)
    write_json_once(out,manifest)
    return manifest


def parse_diagnostics(text,reference,supplied):
    result=dict(strict_json=False,fenced_output=text.lstrip().startswith('```'),value_correct=None,
        source_quote_exact=None,source_quote_visible=None,required_literal_present=None,
        speaker_correct=None,reported_date_correct=None,unknown_form=False,shorter_quote_uncertain=False)
    try:a=json.loads(text)
    except (TypeError,ValueError):return result
    if not isinstance(a,dict):return result
    result['strict_json']=True
    result['value_correct']=a.get('value')==reference['value']
    quote=a.get('quote');ev=reference['evidence']
    if isinstance(quote,str):
        result['source_quote_exact']=bool(quote) and quote in ev['text']
        result['source_quote_visible']=bool(quote) and quote in supplied
        result['required_literal_present']=reference['required_literal'].casefold() in quote.casefold()
    result['speaker_correct']=a.get('speaker')==ev['speaker']
    result['reported_date_correct']=a.get('reported_date')==ev['reported_date']
    result['unknown_form']=(a.get('value')=='unknown' and a.get('certainty')=='unknown' and quote=='' and
        a.get('speaker')=='unknown' and a.get('reported_date') is None)
    result['shorter_quote_uncertain']=bool(reference['value']!='unknown' and result['value_correct'] and
        result['source_quote_exact'] and result['source_quote_visible'] and result['speaker_correct'] and
        result['reported_date_correct'] and not result['required_literal_present'])
    return result


def policy_metrics(rows):
    known=[r for r in rows if r['status']=='development_scored']
    unique={r['request_id']:r for r in rows if r['output_present']}
    return dict(tasks=len(rows),scored=len(known),pending_or_technical=len(rows)-len(known),
        successes=sum(bool(r['score']['task_success']) for r in known),
        success_rate=sum(bool(r['score']['task_success']) for r in known)/len(known) if known else None,
        input_tokens=sum(r['cost']['input_tokens'] for r in unique.values()),
        output_tokens=sum(r['cost']['output_tokens'] for r in unique.values()),
        generation_seconds=sum(r['cost']['generation_seconds'] or 0 for r in unique.values()),
        physical_requests=len(unique),RAW_selected=sum(r['arm']=='RAW' for r in rows),
        cost_excludes_model_load_and_prefill_measurements_not_separately_available=True)


def analyze(package,endpoint_dirs,policy_path,out):
    package,policy_path,out=Path(package),Path(policy_path),Path(out);out.mkdir(parents=True,exist_ok=False)
    requests=jl(package/'REQUESTS_ALL.private.jsonl');by_request={r['request_id']:r for r in requests}
    refs={r['task_id']:r for r in jl(package/'REFERENCES.private.jsonl')}
    tasks={r['task_id']:r for r in jl(package/'TASKS.private.jsonl')}
    policy=json.loads(policy_path.read_text())
    assert policy['protocol']==POLICY_PROTOCOL and policy['request_sha256']==file_sha256(package/'REQUESTS_ALL.private.jsonl')
    assert policy['model_outputs_read']==0 and policy['references_read']==0
    endpoints=[];outputs={};sources={}
    for directory in map(Path,endpoint_dirs):
        current=jl(directory/'ACTUAL_ENDPOINTS.private.jsonl');endpoints.extend(current)
        outs=json.loads((directory/'ACTUAL_OUTPUTS.private.json').read_text())
        if set(outputs)&set(outs):raise ValueError('physical output imported twice')
        outputs.update(outs)
        sources[str(directory/'ACTUAL_ENDPOINTS.private.jsonl')]=file_sha256(directory/'ACTUAL_ENDPOINTS.private.jsonl')
        sources[str(directory/'ACTUAL_OUTPUTS.private.json')]=file_sha256(directory/'ACTUAL_OUTPUTS.private.json')
    if len({r['endpoint_id'] for r in endpoints})!=len(endpoints):raise ValueError('duplicate logical endpoint')
    joined=[]
    for endpoint in endpoints:
        binding=endpoint['binding'];request=by_request[binding['request_id']];tid=request['task_id']
        assert binding['task_id']==tid and binding['arm']==request['arm'] and binding['payload_sha256']==request['payload_sha256']
        output=outputs.get(binding['request_id']);supplied=html.unescape('\n'.join(m['content'] for m in request['model_input']['messages']))
        diag=parse_diagnostics(output['text'],refs[tid],supplied) if output else None
        generation_seconds=None
        if output:
            # Actual bounded HF worker returns seconds; keep absence explicit.
            generation_seconds=output.get('seconds')
        joined.append(dict(task_id=tid,source_group=tasks[tid]['source_group'],category=tasks[tid]['category'],
            arm=request['arm'],request_id=request['request_id'],endpoint_id=endpoint['endpoint_id'],
            status=endpoint['status'],score=endpoint['score'],diagnostics=diag,output_present=output is not None,
            cost=dict(input_tokens=output['input_tokens'] if output else 0,output_tokens=len(output['token_ids']) if output else 0,
                generation_seconds=generation_seconds),reward=None))
    groups=defaultdict(dict)
    for r in joined:groups[r['task_id']][r['arm']]=r
    pairs=[]
    for tid,arms in sorted(groups.items()):
        if set(arms)!={'BASE','RAW'}:raise ValueError('incomplete logical task pair')
        a,b=arms['BASE'],arms['RAW'];valid=all(x['status']=='development_scored' for x in (a,b))
        gain=int(b['score']['task_success'])-int(a['score']['task_success']) if valid else None
        pairs.append(dict(task_id=tid,source_group=a['source_group'],category=a['category'],status='paired_scored' if valid else 'pending',
            BASE_success=a['score']['task_success'] if a['score'] else None,RAW_success=b['score']['task_success'] if b['score'] else None,
            strict_success_gain=gain,RAW_minus_BASE_input_tokens=b['cost']['input_tokens']-a['cost']['input_tokens'],
            RAW_minus_BASE_output_tokens=b['cost']['output_tokens']-a['cost']['output_tokens'],reward=None))
    policies={};policy_groups={}
    for name in POLICIES:
        assignments={r['task_id']:r['arm'] for r in policy['policies'][name]}
        selected=[arms[assignments[tid]] for tid,arms in sorted(groups.items())]
        policies[name]=policy_metrics(selected)
        policy_groups[name]={g:policy_metrics([r for r in selected if r['source_group']==g]) for g in sorted({r['source_group'] for r in selected})}
    oracle=[];oracle_pending=0
    for tid,arms in sorted(groups.items()):
        observed=[r for r in arms.values() if r['status']=='development_scored']
        if not observed or (len(observed)<2 and not any(r['score']['task_success'] for r in observed)):
            oracle_pending+=1;continue
        oracle.append(min(observed,key=lambda r:(-int(r['score']['task_success']),r['cost']['input_tokens'],r['arm']!='BASE')))
    policies['privileged_taskwise_best']=dict(policy_metrics(oracle),unresolved_tasks=oracle_pending,
        deployment_policy=False,privileged_outputs_and_references_used=True)
    policy_groups['privileged_taskwise_best']={g:policy_metrics([r for r in oracle if r['source_group']==g]) for g in sorted({r['source_group'] for r in oracle})}
    base_policy=policies['always_BASE']
    for metric in policies.values():
        metric['successes_minus_always_BASE']=metric['successes']-base_policy['successes']
        metric['input_tokens_minus_always_BASE']=metric['input_tokens']-base_policy['input_tokens']
        metric['output_tokens_minus_always_BASE']=metric['output_tokens']-base_policy['output_tokens']
    pareto=[]
    for tid,arms in sorted(groups.items()):
        observed=[r for r in arms.values() if r['status']=='development_scored']
        nondominated=[r for r in observed if not any(
            int(o['score']['task_success'])>=int(r['score']['task_success']) and o['cost']['input_tokens']<=r['cost']['input_tokens']
            and (int(o['score']['task_success'])>int(r['score']['task_success']) or o['cost']['input_tokens']<r['cost']['input_tokens'])
            for o in observed)]
        pareto.append(dict(task_id=tid,arms=[r['arm'] for r in nondominated],
            dimensions=['strict_task_success_max','input_tokens_min'],weighted_utility_used=False))
    known=[r for r in joined if r['status']=='development_scored']
    diagnostic={arm:dict(total=sum(r['arm']==arm for r in joined),
        strict_json=sum(r['arm']==arm and bool(r['diagnostics'] and r['diagnostics']['strict_json']) for r in joined),
        fenced_output=sum(r['arm']==arm and bool(r['diagnostics'] and r['diagnostics']['fenced_output']) for r in joined),
        shorter_quote_uncertain=sum(r['arm']==arm and bool(r['diagnostics'] and r['diagnostics']['shorter_quote_uncertain']) for r in joined),
        compliant_abstention=sum(r['arm']==arm and bool(r['diagnostics'] and r['diagnostics']['unknown_form'] and r['score'] and r['score']['epistemic_compliance']) for r in joined)) for arm in ('BASE','RAW')}
    aggregate=dict(protocol='structured36-actual-paired-analysis-v1',logical_endpoints=len(joined),source_groups=len({r['source_group'] for r in joined}),
        physical_outputs=len(outputs),status_counts=dict(Counter(r['status'] for r in joined)),
        strict_pair_gain_counts=dict(Counter(str(r['strict_success_gain']) for r in pairs)),policies=policies,
        diagnostics=diagnostic,reward_qualified=False,source_labels='assistant-authored explicit-source development reference',
        strict_quote_failure_is_not_automatic_semantic_error=True,source_group_metrics_path='SOURCE_GROUP_METRICS_PUBLIC.json',
        natural_support_reward_qualified=False,Memory_RS_joint_complete=False,policy_sha256=file_sha256(policy_path),
        analysis_code_sha256=file_sha256(__file__),input_sources_sha256=sources)
    write_jsonl_once(out/'TASKWISE_PARETO_PRIVATE.jsonl',pareto);write_jsonl_once(out/'PER_ENDPOINT_PRIVATE.jsonl',joined);write_jsonl_once(out/'PAIRED_PRIVATE.jsonl',pairs)
    write_json_once(out/'SOURCE_GROUP_METRICS_PUBLIC.json',policy_groups);write_json_once(out/'AGGREGATE_PUBLIC.json',aggregate)
    return aggregate
