#!/usr/bin/env python3
"""Prepare cost/real public states, then optionally run a bounded proxy study.

This diagnostic uses existing real replies, relative-model feedback, and an
estimated deployment cost. It does not manufacture formal q/m qualification.
"""
import argparse
from collections import defaultdict
from dataclasses import asdict
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json,file_sha,CONFIG
from metacom_pm.rl1.reusable_latency import fit,estimate,ppo_episode

BASE=PROJECT/'outputs/pm_rl1'
FEEDBACK=BASE/'relative_feedback_pilot_20261104_v1'
SCOPE='REAL_DATA_RELATIVE_FEEDBACK_DIAGNOSTIC'


def read(p):return json.loads(Path(p).read_text())


def normalize_response(raw,evidence):
    """Accept existing session citations as coarse scopes, never invented turns.

    Keep the original response untouched. This repairs a syntax-level mismatch
    only; it does not change verdicts, risks, reasons, or human expectations.
    """
    from metacom_pm.rl1.relative_diagnostic import parse
    try:return parse(raw,evidence),[]
    except ValueError as exc:
        if str(exc)!='unknown cited evidence':raise
    text=raw.split('</think>')[-1].strip()
    if text.startswith('```json') and text.endswith('```'):text=text[7:-3].strip()
    obj=json.loads(text);sessions={s['id'] for s in evidence['legal_past_sessions']}
    coarse=[x for x in obj['evidence_ids'] if x in sessions]
    obj['evidence_ids']=[x for x in obj['evidence_ids'] if x not in sessions]
    return parse(json.dumps(obj),evidence),coarse


def feedback(out):
    from collections import Counter
    from metacom_pm.rl1.relative_diagnostic import agreement
    pairs=read(FEEDBACK/'PAIRS_PRIVATE.json');requests=read(FEEDBACK/'REQUESTS_PRIVATE.json');expected=read(FEEDBACK/'EXPECTATIONS_PRIVATE.json')
    normalized={};normalizations=[];parse_errors=[]
    for q in requests:
        path=FEEDBACK/'responses'/(q['identity']+'.json')
        if not path.exists():continue
        r=read(path);pair=next(p for p in pairs if p['identity']==q['pair_identity'])
        if r['finish_reason']!='natural_stop':continue
        try:
            parsed,coarse=normalize_response(r['raw'],pair['evidence']);normalized[q['identity']]=parsed
            if coarse:normalizations.append(dict(request=q['identity'],original_sha256=file_sha(path),
                coarse_session_ids=coarse,verdict_unchanged=True,scope='known source sessions, not precise claim grounding'))
        except (ValueError,TypeError) as exc:parse_errors.append(dict(request=q['identity'],error=str(exc)))
    results={};checks=[];counts=Counter()
    for pair in pairs:
        if pair['left']==pair['right']:got=dict(status='identical_reply',gain=0.)
        else:
            qs=[next(q for q in requests if q['pair_identity']==pair['identity'] and q['reverse']==r) for r in (False,True)]
            got=agreement(pair,*(normalized.get(q['identity']) for q in qs))
        results[pair['identity']]=got
        if pair['group']!='reference':continue
        want=expected[pair['identity']];verdict=got.get('verdict')
        counts['consistent']+=got['status'] in ('agreed','uncertain') and want!='unscored_reference'
        if want in ('A_better','B_better'):counts['factual_correct']+=verdict==want
        elif want=='near_equal':counts['ties_correct']+=verdict==want
        elif want=='not_material':counts['near_not_material']+=verdict=='near_equal' or got['status']=='uncertain'
        checks.append(dict(key=pair['key'],expected=want,result=got))
    passed=counts['factual_correct']==3 and counts['ties_correct']>=2 and counts['near_not_material']==1 and counts['consistent']>=6
    summary=dict(status='REFERENCE_SCREEN_PASSED' if passed else 'REFERENCE_SCREEN_NOT_PASSED',
        counts=dict(counts),checks=checks,normalizations=normalizations,remaining_parse_errors=parse_errors,
        original_protocol_identity=read(FEEDBACK/'PROTOCOL.json')['identity'],expectations_unchanged=True,
        source_responses={str(p.resolve()):file_sha(p) for p in sorted((FEEDBACK/'responses').glob('*.json'))},
        pair_results=results,api_cost_usd=0,natural_policy_updates=0)
    save_json(out/'NORMALIZED_FEEDBACK.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('pair_results','source_responses')},ensure_ascii=False),flush=True)


def prepare(out):
    if out.exists():raise ValueError('new diagnostic output required')
    menu=read(BASE/'organized_initial_training_20261103_v2/MENU_PRIVATE.json')
    responses=read(BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    endpoints=read(FEEDBACK/'ENDPOINTS_PRIVATE.json')
    groups={e['requests']['ON']['request_id']:e['prefix_identity'] for e in menu['endpoints']}
    rows=[dict(r,prefix_identity=groups[k]) for k,r in responses.items()]
    pilot=BASE/'memoized_latency_pilot_20261104_v1';protocol=read(pilot/'PROTOCOL.json')
    pilots=[read(pilot/(s['slot']+'.result.private.json')) for s in protocol['schedule'] if not s['warmup'] and s['path']=='memoized']
    for r in pilots:r['prefix_identity']=protocol['cases'][r['schedule']['case']]
    source=digest(dict(responses=digest(responses),pilot_protocol=protocol['identity']))
    model=fit(rows,pilots,source_identity=source,deployment_identity=protocol['regime_identity'])
    costs={e['identity']:estimate(model,responses[e['requests']['ON']['request_id']],e['actions'],
        deployment_identity=model['deployment_identity']) for e in endpoints}
    out.mkdir(parents=True,mode=0o700);save_json(out/'COST_MODEL.json',model);save_json(out/'COSTS_PRIVATE.json',costs)
    p=stamp(dict(scope=SCOPE,feedback_protocol=read(FEEDBACK/'PROTOCOL.json')['identity'],
        endpoints_identity=digest(endpoints),cost_model_identity=model['identity'],
        weights=[0.,.05,.2],training_weight=.05,seeds=[17,23,42],episodes_per_seed=128,batch_size=16,
        supervised=CONFIG,training_data=f'{len({e["prefix_identity"] for e in endpoints})} original train prefixes; fixed candidate tree; no dev/test',
        feedback_utility='ordinal +1/0/-1 relative OFF; includes overall harm; not q/m or human cardinal values',
        cost_uncertainty='short paths extrapolate per-component overhead; +/-50% overhead and held-prefix p90 G error sensitivity',
        completion_rule='release complete prefix subproblems only; at least two; eligibility depends on missingness, never score direction; retain all unresolved rows',
        formal_natural_qualification=False,permission='Current researcher request: 好的，试试看，看看能不能解决现在的问题。'))
    save_json(out/'PROTOCOL.json',p)
    print(json.dumps(dict(status='COST_MODEL_FITTED',generator_validation=model['generator_validation'],
        held_case_errors=[r['error'] for r in model['end_to_end_held_case_validation']],endpoints=len(endpoints))),flush=True)


def states(out):
    from metacom_pm.rl1.online_materials import load_materials
    from metacom_pm.rl1.memoized_online import RequestRenderer,MemoizedHeadSession
    endpoints=read(FEEDBACK/'ENDPOINTS_PRIVATE.json');pids={e['prefix_identity'] for e in endpoints}
    package=BASE/'organized_initial_training_20261103_v2';c,catalogs,renderer=load_materials(package,prefix_ids=pids)
    encoded=read(BASE/'organized_initial_encoding_20261103_v2/FEATURES_PRIVATE.json');graph={}
    for e in endpoints:
        session=MemoizedHeadSession(catalogs[e['prefix_identity']],RequestRenderer(renderer));history=[]
        for action in e['actions']:
            obs=asdict(session.observe());oid=digest(obs);row=encoded[oid]
            assert row['prefix_identity']==e['prefix_identity'] and row['mask']==list(obs['action_mask'])
            key=digest(dict(prefix=e['prefix_identity'],history=history))
            node=dict(prefix=e['prefix_identity'],history=list(history),observation_identity=oid,
                features=row['features'],NoText_features=row['NoText_features'],public_mask=row['mask'])
            if key in graph:assert graph[key]==node
            graph[key]=node;session.step(action);history.append(action)
    for node in graph.values():
        h=node['history'];choices=[e['actions'][len(h)] for e in endpoints if e['prefix_identity']==node['prefix'] and e['actions'][:len(h)]==h]
        node['experiment_mask']=[node['public_mask'][a] and a in choices for a in range(5)]
        if not node['experiment_mask'][0]:raise ValueError('bounded tree must contain a measured STOP at each state')
    save_json(out/'STATES_PRIVATE.json',graph)
    print(json.dumps(dict(status='REAL_STATES_READY',nodes=len(graph),prefixes=len(pids),feature_dimension=len(next(iter(graph.values()))['features']))),flush=True)


def run(out,*,exact=None):
    import torch
    from metacom_pm.rl1.e0_learning import PPO
    from metacom_pm.rl1.observation_features import make_actor_critic
    from metacom_pm.rl1.natural_batch import parameter_identity
    protocol=read(out/('DIAGNOSTIC_PROTOCOL.json' if (out/'DIAGNOSTIC_PROTOCOL.json').exists() else 'PROTOCOL.json'));endpoints=read(FEEDBACK/'ENDPOINTS_PRIVATE.json')
    assert digest(endpoints)==protocol['endpoints_identity']
    if exact is not None:
        if protocol['scope']!='REAL_DATA_EXACT_REPLY_COST_CONTROL':raise ValueError('explicit equivalence control scope required')
        original={e['endpoint_identity']:e for e in read(BASE/'actual_training_feedback_20261103_v1/ENDPOINTS_PRIVATE.json')}
        inputs=read(BASE/'actual_training_feedback_20261103_v1/INPUTS_PRIVATE.json')
        responses=read(BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
        if set(exact)!= {e['identity'] for e in endpoints}:raise ValueError('incomplete equivalence proof')
        for e in endpoints:
            proof=original[e['identity']]
            if proof['ON']!=proof['OFF'] or proof!=exact[e['identity']]:raise ValueError('quality equality not established')
            item=inputs[proof['ON']]
            if digest(dict(evidence=item['evidence'],reply=item['reply']))!=proof['ON']:raise ValueError('canonical scoring input changed')
            for role in ('ON','OFF'):
                req=e['requests'][role];response=responses[req['request_id']]
                if (req['request_id'] not in item['request_ids'] or item['reply']!=response['text']
                        or response['finish_reason']!='natural_stop' or response['source_provenance_identity']!=digest(req['provenance'])):
                    raise ValueError('equal scoring input does not match actual reply')
        labels=exact;gains={e['identity']:0. for e in endpoints}
    else:
        normalized=read(out/'NORMALIZED_FEEDBACK.json') if (out/'NORMALIZED_FEEDBACK.json').exists() else None
        feedback_status=normalized['status'] if normalized else read(FEEDBACK/'ANALYSIS.json')['status']
        if feedback_status!='REFERENCE_SCREEN_PASSED':
            save_json(out/'RESULTS.json',dict(status='STOPPED_REFERENCE_SCREEN',scope=SCOPE,real_data_PPO_updates=0));return
        labels=normalized['pair_results'] if normalized else read(FEEDBACK/'PAIR_RESULTS_PRIVATE.json');pairs=read(FEEDBACK/'PAIRS_PRIVATE.json');gains={}
        for e in endpoints:
            if e['actions']==[0]:gains[e['identity']]=0.
            else:
                pair=next(p for p in pairs if p.get('endpoint_identity')==e['identity']);gains[e['identity']]=labels[pair['identity']]['gain']
    pending=[k for k,v in gains.items() if v is None]
    incomplete={e['prefix_identity'] for e in endpoints if e['identity'] in pending}
    completed={e['prefix_identity'] for e in endpoints}-incomplete
    coverage=dict(planned_endpoints=len(endpoints),pending_endpoints=pending,
        incomplete_prefixes=sorted(incomplete),complete_prefixes=sorted(completed),
        eligibility='all fixed candidates resolved, independent of preference direction')
    save_json(out/'FEEDBACK_COVERAGE.json',coverage)
    if len(completed)<2:
        save_json(out/'RESULTS.json',dict(status='PENDING_RELATIVE_FEEDBACK',coverage=coverage,scope=SCOPE,real_data_PPO_updates=0));return
    endpoints=[e for e in endpoints if e['prefix_identity'] in completed]
    graph=read(out/'STATES_PRIVATE.json');costs=read(out/'COSTS_PRIVATE.json');weight=protocol['training_weight']
    pids=sorted({e['prefix_identity'] for e in endpoints});by_program={(e['prefix_identity'],tuple(e['actions'])):e for e in endpoints}
    def node(pid,h):return graph[digest(dict(prefix=pid,history=list(h)))]
    def net(e,w=weight):return gains[e['identity']]-w*costs[e['identity']]['seconds']
    headroom={pid:dict(best_ordinal_quality_gain=max(gains[e['identity']] for e in endpoints if e['prefix_identity']==pid),
        versus_sequential_STOP={str(w):max(net(e,w) for e in endpoints if e['prefix_identity']==pid)-net(by_program[pid,(0,)],w)
            for w in protocol['weights']},
        versus_fixed_OFF={str(w):max(net(e,w) for e in endpoints if e['prefix_identity']==pid)+w*costs[by_program[pid,(0,)]['identity']]['generator_seconds']
            for w in protocol['weights']}) for pid in pids}
    save_json(out/'REAL_TARGETS_PRIVATE.json',dict(gains=gains,headroom=headroom,feedback_digest=digest(labels),costs_digest=digest(costs)))
    if (out/'LEARNING_STARTED.json').exists():raise ValueError('diagnostic already entered; no silent rerun')
    save_json(out/'LEARNING_STARTED.json',dict(protocol=protocol['identity'],feedback=digest(labels),states=digest(graph),costs=digest(costs),
        code={str(p.resolve()):file_sha(p) for p in [Path(__file__),PROJECT/'src/metacom_pm/rl1/reusable_latency.py',
            PROJECT/'src/metacom_pm/rl1/e0_learning.py',PROJECT/'src/metacom_pm/rl1/observation_features.py']}))
    torch.set_num_threads(1);summaries=[]
    def rollout(actor,pid,version,hidden=False,greedy=False):
        h=[];ts=[]
        while True:
            n=node(pid,h);x=torch.tensor(n['NoText_features' if hidden else 'features'],dtype=torch.float32);mask=torch.tensor(n['experiment_mask'])
            with torch.no_grad():dist,val=actor(x,mask);action=dist.probs.argmax() if greedy else dist.sample()
            ts.append(dict(observation=x,mask=mask,action=action,old_log_prob=dist.log_prob(action),old_value=val,forced=int(mask.sum())==1))
            h.append(int(action))
            if not int(action):break
        e=by_program[pid,tuple(h)]
        episode=ppo_episode(ts,gain=gains[e['identity']],cost=costs[e['identity']],weight=weight,policy_version=version)
        episode['scope']=protocol['scope']
        return episode,e
    def distribution(actor,pid,hidden=False):
        leaves=[]
        def visit(history,probability):
            n=node(pid,history);mask=torch.tensor(n['experiment_mask'])
            if actor is None:probs=mask.float()/mask.sum()
            else:
                with torch.no_grad():probs=actor(torch.tensor(n['NoText_features' if hidden else 'features'],dtype=torch.float32),mask)[0].probs
            for a in range(5):
                if not mask[a]:continue
                mass=probability*float(probs[a]);path=history+[a]
                if a:visit(path,mass)
                else:leaves.append((mass,by_program[pid,tuple(path)]))
        visit([],1.);mass=sum(p for p,e in leaves)
        if abs(mass-1.)>1e-5:raise ValueError('incomplete bounded policy enumeration')
        return dict(expected_return=sum(p*net(e) for p,e in leaves)/mass,
            expected_GETs=sum(p*(len(e['actions'])-1) for p,e in leaves)/mass,
            stop_probability=sum(p for p,e in leaves if e['actions']==[0])/mass)
    def evaluate(actor,version,hidden=False):
        return [dict(prefix=pid,actions=(e:=rollout(actor,pid,version,hidden,True)[1])['actions'],
            quality_gain=gains[e['identity']],estimated_seconds=costs[e['identity']]['seconds'],return_value=net(e),
            **distribution(actor,pid,hidden)) for pid in pids]
    baselines={pid:dict(uniform_random=distribution(None,pid),fixed_OFF_return=-weight*costs[by_program[pid,(0,)]['identity']]['generator_seconds'],
        optimal_program_return=max(net(e) for e in endpoints if e['prefix_identity']==pid)) for pid in pids}
    for hidden in (False,):
      for seed in protocol['seeds']:
        torch.manual_seed(seed);actor=make_actor_critic(len(next(iter(graph.values()))['features']))
        optimizer=torch.optim.Adam(actor.parameters(),lr=CONFIG['lr'],weight_decay=CONFIG['weight_decay'])
        demos=[]
        for pid in pids:
            best=min((e for e in endpoints if e['prefix_identity']==pid),key=lambda e:(-net(e),tuple(e['actions'])))
            h=[];rs=[-weight*s for s in costs[best['identity']]['step_seconds']];rs[-1]+=gains[best['identity']]
            for i,a in enumerate(best['actions']):
                n=node(pid,h);demos.append((n['NoText_features' if hidden else 'features'],n['experiment_mask'],a,sum(rs[i:])));h.append(a)
        x=torch.tensor([r[0] for r in demos]);m=torch.tensor([r[1] for r in demos]);a=torch.tensor([r[2] for r in demos]);y=torch.tensor([r[3] for r in demos])
        for epoch in range(CONFIG['epochs']):
            order=torch.randperm(len(demos))
            for ix in order.split(CONFIG['batch_size']):
                loss=-actor(x[ix],m[ix])[0].log_prob(a[ix]).mean();optimizer.zero_grad();loss.backward();optimizer.step()
        for p in actor.parameters():p.requires_grad_(False)
        for p in actor.value.parameters():p.requires_grad_(True)
        vo=torch.optim.Adam(actor.value.parameters(),lr=CONFIG['lr'],weight_decay=CONFIG['weight_decay'])
        for _ in range(CONFIG['value_head_only_steps']):
            loss=(actor(x,m)[1]-y).square().mean();vo.zero_grad();loss.backward();vo.step()
        for p in actor.parameters():p.requires_grad_(True)
        before=parameter_identity(actor);bc=evaluate(actor,0,hidden);ppo=PPO(actor);updates=[]
        for version in range(protocol['episodes_per_seed']//16):
            batch=[rollout(actor,pids[(version*16+i)%len(pids)],version,hidden)[0] for i in range(16)]
            updates.append(ppo.update(batch))
        final=evaluate(actor,ppo.version,hidden)
        checkpoint=out/f'diagnostic_{"NoText" if hidden else "FullText"}_{seed}.pt'
        torch.save(dict(scope=SCOPE,protocol_identity=protocol['identity'],model=actor.state_dict(),optimizer=ppo.optimizer.state_dict(),
            version=ppo.version,feedback_identity=digest(labels),cost_model_identity=read(out/'COST_MODEL.json')['identity']),checkpoint)
        summaries.append(dict(seed=seed,hidden=hidden,BC=bc,PPO=final,updates=updates,before=before,after=parameter_identity(actor),
            checkpoint_sha256=file_sha(checkpoint)))
        print(json.dumps(dict(seed=seed,hidden=hidden,updates=ppo.version,BC_mean=sum(r['return_value'] for r in bc)/len(bc),
            PPO_mean=sum(r['return_value'] for r in final)/len(final))),flush=True)
    save_json(out/'RESULTS.json',dict(status='BOUNDED_REAL_DATA_PROXY_LEARNING_COMPLETED',scope=SCOPE,
        headroom=headroom,baselines=baselines,coverage=coverage,runs=summaries,real_data_PPO_updates=sum(len(r['updates']) for r in summaries),
        formal_qualified_natural_updates=0,held_out_generalization_measured=False,API_cost_usd=0))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','states','feedback','run']);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();globals()[a.mode](a.output)
