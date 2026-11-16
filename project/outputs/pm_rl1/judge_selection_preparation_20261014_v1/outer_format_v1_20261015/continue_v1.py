"""Authorized continuation of original AB slots; immutable cross-interface ledger.

The engineering execution and its source code are archived. Development adds
only a scoped schedule/authorization; transport and final interface are unchanged.
"""
from pathlib import Path
import argparse,fcntl,os,sys,time
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import selection as s
import outer_format_v1 as interface
from resume_engineering import GPUChecks,validate_artifacts,slots,now

SUBDIR='output_interface_v1'
DIAGNOSTIC_POLICY = dict(version='unresolved-review-diagnostic-continuation-v1-20261015',
    post_outcome_amendment=True,applies_to=list(s.CANDIDATES),
    only_reviewer_unresolved_ambiguity_may_continue=True,
    coexisting_hard_stop_overrides=True,new_same_class_ambiguities_may_continue=True,
    unresolved_unknown_blocks_recommendation=True,reward_eligible=False,
    semantic_revision_delta=0)

def protocol(plan,development=False,diagnostic=False,api_engineering=False,api_development=False):
    api_engineering=api_engineering or api_development
    development=development or diagnostic
    i=interface.identity()
    implementation=dict(original=s.code_identity(),interface=i['code_sha256'],
        continuation=s.sha(__file__),gpu_helper=s.sha(HERE.parent/'resume_engineering.py'))
    if api_engineering:implementation['official_access']=s.sha(HERE/'deepseek_access.py')
    configs={}
    for key,old in plan['configs'].items():
        c={k:v for k,v in old.items() if k!='identity'}
        c.update(original_configuration_identity=old['identity'],output_interface=i,
            complete_implementation=implementation)
        configs[key]=c|dict(identity=s.digest(c))
    requests=[]
    scheduled=slots(plan) if not development else sorted(
        [r for r in plan['requests'] if r['candidate'] in s.CANDIDATES[:2]],
        key=lambda r:(s.STAGES.index(r['phase']),r['schedule_position']))
    if api_engineering:
        scheduled=sorted([r for r in plan['requests'] if r['candidate'] in s.CANDIDATES[2:] and r['phase']=='engineering'],key=lambda r:r['schedule_position'])
    if api_development:
        scheduled=sorted([r for r in plan['requests'] if r['candidate']==s.CANDIDATES[3]],
            key=lambda r:(s.STAGES.index(r['phase']),r['schedule_position']))
    for old in scheduled:
        r={k:v for k,v in old.items() if k!='request_id'}
        r.update(original_slot_request_id=old['request_id'],original_configuration_identity=old['configuration_identity'],
            configuration_identity=configs[old['candidate']]['identity'],output_interface_identity=i['identity'])
        requests.append(r|dict(request_id=s.digest(r)))
    value=dict(version='original-AB-eight-output-interface-amendment-v1',original_plan_identity=plan['identity'],
        interface=i,implementation=implementation,configs=configs,requests=requests,
        semantic_revision_delta=0,semantic_revisions_used=1,original_old_calls=66,
        existing_pool_calls=2,pool_call_cap=8,cumulative_cap=74,original_cap=140,
        allowed_live_candidates=list(s.CANDIDATES[:2]),allowed_phase='engineering',
        max_new_calls=6,original_slots_only=True,retries=0)
    if development:
        prior=HERE/'protocol.json'
        value.update(version='original-AB-forty-authorized-development-20261015',
            existing_pool_calls=8,pool_call_cap=80,cumulative_cap=146,capacity=289,
            allowed_phase=['engineering','development','diagnostics'],max_new_calls=72,
            per_configuration_cap=40,output_subdir='output_interface_v1_AB_development',
            previous_protocols=[dict(path=str(prior),sha256=s.sha(prior),subdir=SUBDIR)])
    if diagnostic:
        previous=s.HERE/'AB_development_20261015/protocol.json'
        value.update(version='original-AB-bounded-diagnostic-continuation-20261015',
            existing_pool_calls=22,max_new_calls=58,diagnostic_policy=DIAGNOSTIC_POLICY,
            output_subdir='output_interface_v1_AB_diagnostic')
        value['previous_protocols'].append(dict(path=str(previous),sha256=s.sha(previous),
            subdir='output_interface_v1_AB_development'))
    if api_engineering:
        value.update(version='original-CD-eight-official-api-20261015',existing_pool_calls=33,
            pool_call_cap=41,cumulative_cap=107,capacity=289,max_new_calls=8,
            per_configuration_cap=40,per_candidate_caps={c:(40 if c in s.CANDIDATES[:2] else 4) for c in s.CANDIDATES},
            allowed_live_candidates=list(s.CANDIDATES[2:]),allowed_phase='engineering',
            output_subdir='output_interface_v1_CD_engineering',diagnostic_policy=DIAGNOSTIC_POLICY,
            official_api=True,trial_cap_usd='2',reservation_nanodollars=s.API_WORST,
            previous_protocols=[dict(path=str(path),sha256=s.sha(path),subdir=subdir) for path,subdir in [
                (HERE/'protocol.json',SUBDIR),
                (s.HERE/'AB_development_20261015/protocol.json','output_interface_v1_AB_development'),
                (s.HERE/'AB_diagnostic_continuation_20261015/protocol.json','output_interface_v1_AB_diagnostic')]])
    if api_development:
        previous=s.HERE/'CD_engineering_20261015/protocol.json'
        service=s.HERE/'live_runs/output_interface_v1_CD_engineering/stage/service_identity.json'
        value.update(version='original-D-remaining36-official-api-20261015',existing_pool_calls=41,
            pool_call_cap=77,cumulative_cap=143,max_new_calls=36,api_development=True,
            allowed_live_candidates=[s.CANDIDATES[3]],allowed_phase=['engineering','development','diagnostics'],
            per_candidate_caps={c:(4 if c==s.CANDIDATES[2] else 40) for c in s.CANDIDATES},
            output_subdir='output_interface_v1_D_development',
            financial_trial_identity=s.read(previous)['identity'],
            prior_service_identity=dict(path=str(service),sha256=s.sha(service)))
        value['previous_protocols'].append(dict(path=str(previous),sha256=s.sha(previous),subdir='output_interface_v1_CD_engineering'))
    return value|dict(identity=s.digest(value))

def registered_protocols(p):
    values=[(p,p.get('output_subdir',SUBDIR))]
    for ref in p.get('previous_protocols',[]):
        if s.sha(ref['path'])!=ref['sha256']:raise ValueError('historical protocol changed')
        old=s.read(ref['path'])
        if old['identity']!=s.digest({k:v for k,v in old.items() if k!='identity'}):raise ValueError('historical protocol identity')
        values.append((old,ref['subdir']))
    return values

def reconstruct(plan,p,root,mode='live',diagnostic_permissions=()):
    root=Path(root);old={r['request_id']:r for r in plan['requests']};new={};locations={}
    for registered,subdir in registered_protocols(p):
        for r in registered['requests']:
            if r['request_id'] in new and new[r['request_id']]!=r:raise ValueError('ambiguous request identity')
            new[r['request_id']]=r;locations[r['request_id']]=subdir
    occupied={};slot_owners={};issues=[];blocked={}
    for suffix in ('started','result','raw','response'):
        for f in root.rglob('*.'+suffix+'.json'):
            rid=f.name.split('.')[0]
            if rid in old:
                req=old[rid];slot=rid;expected=root/req['candidate']
            elif rid in new:
                req=new[rid];slot=req['original_slot_request_id'];expected=root/locations[rid]/req['candidate']
            else:raise ValueError('unknown cross-version attempt: '+str(f))
            if f.parent!=expected:raise ValueError('noncanonical attempt path')
            if slot in slot_owners and slot_owners[slot]!=rid:raise ValueError('duplicate original slot across interfaces')
            slot_owners[slot]=rid
            if suffix in ('started','result'):
                row=s.read(f)
                if row['request']!=req or row['mode']!=mode:raise ValueError('request/mode identity changed')
                if suffix=='result' and rid in new and row['evaluation']['measurement']['measurement_status'] not in s.VALID:
                    blocked[req['candidate']]='new-interface technical failure'
            occupied.setdefault(rid,dict(original_slot=slot,candidate=req['candidate'],kinds=[]))['kinds'].append(suffix)
    for rid,v in occupied.items():
        if 'started' not in v['kinds']:issues.append('orphan output counted: '+rid)
        if 'started' not in v['kinds'] or 'result' not in v['kinds']:
            blocked[v['candidate']]='incomplete prior attempt; counted, never retried'
    for c in s.CANDIDATES:
        for _,subdir in registered_protocols(p):
            stop=root/subdir/c/'STOP.json'
            if stop.exists() and (str(stop),s.sha(stop)) not in diagnostic_permissions:
                blocked[c]='persistent new-interface STOP'
    counts={c:sum(v['candidate']==c for v in occupied.values()) for c in s.CANDIDATES}
    if len(occupied)>p['pool_call_cap'] or any(counts[c]>p.get('per_candidate_caps',{}).get(c,p.get('per_configuration_cap',4)) for c in s.CANDIDATES):raise ValueError('cross-version cap exceeded')
    return dict(occupied=occupied,slot_owners=slot_owners,blocked=blocked,issues=issues,
        started_or_evidenced=len(occupied),cumulative_calls=66+len(occupied),per_configuration=counts)

def review_valid(review,plan,orig,rid,response_path):
    if review['request_id']!=rid or review['response_sha256']!=s.sha(response_path):raise ValueError('unbound semantic review')
    if review['item_key']!=orig['item_key'] or not review['explanation']:raise ValueError('missing review identity/reason')
    for k in ('material_source_proven_error','critical_unknown','unexplained_equivalence_difference'):
        if type(review[k]) is not bool:raise ValueError('missing stop assessment')
    e=plan['items'][orig['item_key']]['evidence'];turns=e['current_prefix']+[t for h in e['legal_past_sessions'] for t in h['turns']]
    lookup={t['id']:t['text'] for t in turns}
    for a in review['source_checks']:
        if a['source_id'] not in lookup or not a['exact_quote'] or a['exact_quote'] not in lookup[a['source_id']]:
            raise ValueError('review source quote mismatch')
    return any(review[k] for k in ('material_source_proven_error','critical_unknown','unexplained_equivalence_difference'))

def diagnostic_disposition(review,measurement):
    """Uniform dispatch policy; never a score repair or reward qualification."""
    other=review.get('other_hard_stop_reasons',[])
    if not isinstance(other,list) or any(not isinstance(x,str) or not x for x in other):
        raise ValueError('invalid other hard stop reasons')
    hard=bool(review['material_source_proven_error'] or review['unexplained_equivalence_difference'] or other)
    return dict(technical_status=measurement['measurement_status'],
        model_unknown=measurement['measurement_status']=='semantic_uncertainty',
        reviewer_unresolved_ambiguity=review['critical_unknown'],
        source_proven_material_error=review['material_source_proven_error'],
        unexplained_equivalence_difference=review['unexplained_equivalence_difference'],
        other_hard_stop_reasons=other,hard_stop=hard,
        diagnostic_continuation=review['critical_unknown'] and not hard,
        q=measurement.get('q'),m=measurement.get('m'),U=measurement.get('candidate_utility'),
        usable_for_qualification=False,reward_eligible=False,
        recommendation_blocked_by_unresolved=review['critical_unknown'],
        record_class='development_diagnostic_after_known_unresolved_dispute',
        independent_human_observations_added=0)

def diagnostic_permissions(plan,p,auth,root):
    """Explicit linked exceptions for existing STOPs, not deletion or relabelling."""
    permissions=[]
    for ref in auth['historical_unknown_stops']:
        for name in ('stop','review','response','result'):
            if s.sha(ref[name+'_path'])!=ref[name+'_sha256']:raise ValueError('diagnostic historical binding changed')
        stop=s.read(ref['stop_path']);review=s.read(ref['review_path']);result=s.read(ref['result_path'])
        req=result['request'];orig=next(r for r in plan['requests'] if r['request_id']==req['original_slot_request_id'])
        if Path(ref['stop_path'])!=Path(ref['result_path']).parent/'STOP.json':raise ValueError('STOP location mismatch')
        if stop['request_id']!=req['request_id'] or ref['request_id']!=req['request_id']:raise ValueError('STOP request mismatch')
        if stop['reason']!='source-bound semantic hard stop':raise ValueError('not an unresolved semantic STOP')
        review_valid(review,plan,orig,req['request_id'],Path(ref['response_path']))
        evaluation=result['evaluation'];measurement=evaluation['measurement']
        if evaluation.get('validation_stage')!='complete' or measurement['measurement_status'] not in s.VALID:
            raise ValueError('diagnostic exception cannot bypass technical validation')
        decision=diagnostic_disposition(review,measurement)
        if not decision['diagnostic_continuation']:raise ValueError('historical STOP not solely unresolved ambiguity')
        if not Path(ref['stop_path']).is_relative_to(Path(root)):raise ValueError('STOP outside pool')
        permissions.append((ref['stop_path'],ref['stop_sha256']))
    return permissions

def validate_release(plan,p,auth,root):
    if p.get('official_api'):
        development=p.get('api_development',False)
        scope=(107,36,143,289,'2') if development else (99,8,107,289,'2')
        candidates=[s.CANDIDATES[3]] if development else list(s.CANDIDATES[2:])
        if auth.get('status')!='APPROVED' or auth.get('protocol_identity')!=p['identity']:raise ValueError('CD authority missing')
        if (auth.get('baseline_cumulative'),auth.get('new_calls_limit'),auth.get('cumulative_cap'),auth.get('capacity'),auth.get('trial_cap_usd'))!=scope:
            raise ValueError('CD authorization scope changed')
        if auth.get('allowed_candidates')!=candidates or auth.get('diagnostic_policy')!=DIAGNOSTIC_POLICY or p['diagnostic_policy']!=DIAGNOSTIC_POLICY:
            raise ValueError('CD candidate/diagnostic scope changed')
        if not auth.get('research_payload_authorized') or not auth.get('official_terms_accepted_by_researcher') or auth.get('semantic_revision_delta')!=0:raise ValueError('CD data/measurement authority missing')
        for path,sha in auth['immutable_bindings'].items():
            if s.sha(path)!=sha:raise ValueError('CD immutable binding changed')
        if development and auth.get('financial_trial_identity')!=p['financial_trial_identity']:raise ValueError('financial trial reset')
        if reconstruct(plan,p,root)['cumulative_calls']<scope[0]:raise ValueError('lost historical attempts')
        return candidates
    if p.get('diagnostic_policy'):
        if p['diagnostic_policy']!=DIAGNOSTIC_POLICY or auth.get('diagnostic_policy')!=DIAGNOSTIC_POLICY:
            raise ValueError('diagnostic policy changed')
        if auth.get('status')!='APPROVED' or auth.get('protocol_identity')!=p['identity']:raise ValueError('diagnostic authority missing')
        if (auth.get('new_calls_limit'),auth.get('baseline_cumulative'),auth.get('pool_call_cap'),auth.get('cumulative_cap'),auth.get('capacity'))!=(58,88,80,146,289):
            raise ValueError('diagnostic scope changed')
        if auth.get('allowed_candidates')!=list(s.CANDIDATES[:2]) or auth.get('DeepSeek_authorized') is not False or auth.get('semantic_revision_delta')!=0:
            raise ValueError('diagnostic candidate/measurement scope changed')
        for path,sha in auth['immutable_bindings'].items():
            if s.sha(path)!=sha:raise ValueError('diagnostic prerequisite changed')
        # Validate the preserved format-only releases without trying to count a
        # later ledger using an older, smaller protocol registry.
        allowed=validate_release(plan,s.read(HERE/'protocol.json'),s.read(HERE/'continuation_authorization.json'),root)
        diagnostic_permissions(plan,p,auth,root)
        current=reconstruct(plan,p,root)
        if current['cumulative_calls']<88:raise ValueError('lost historical attempts')
        return allowed
    if p.get('capacity')==289:
        if auth.get('status')!='APPROVED' or auth.get('protocol_identity')!=p['identity']:raise ValueError('development authority missing')
        if (auth.get('new_calls_limit'),auth.get('pool_call_cap'),auth.get('cumulative_cap'),auth.get('capacity'))!=(72,80,146,289):raise ValueError('development scope changed')
        if auth.get('baseline_cumulative')!=74 or auth.get('semantic_revision_delta')!=0:raise ValueError('baseline/scope changed')
        if auth.get('allowed_candidates')!=list(s.CANDIDATES[:2]) or auth.get('DeepSeek_authorized') is not False:raise ValueError('local scope changed')
        for path,sha in auth['immutable_bindings'].items():
            if s.sha(path)!=sha:raise ValueError('development prerequisite changed')
        original=s.read(HERE/'protocol.json');prior_auth=s.read(HERE/'continuation_authorization.json')
        allowed=validate_release(plan,original,prior_auth,root)
        current=reconstruct(plan,p,root)
        for req in original['requests']:
            if req['original_slot_request_id'] not in current['slot_owners']:raise ValueError('engineering slot missing')
        return allowed
    if auth['status']!='APPROVED' or auth['protocol_identity']!=p['identity'] or auth['new_calls_limit']!=6:
        raise ValueError('wrong continuation authority')
    if auth['pool_call_cap']!=8 or auth['cumulative_cap']!=74 or auth['semantic_revision_delta']!=0:raise ValueError('scope changed')
    approved=[]
    for c,r in auth['format_only_releases'].items():
        if c not in s.CANDIDATES[:2]:raise ValueError('only AB authorized')
        for f,h in r['immutable_bindings'].items():
            if s.sha(f)!=h:raise ValueError('release source changed')
        d=s.read(r['derived_path']);v=s.read(r['review_path'])
        orig=next(x for x in slots(plan) if x['candidate']==c and x['ordinal']==1)
        if d['original_request_id']!=orig['request_id'] or d['new_configuration_identity']!=p['configs'][c]['identity']:raise ValueError('derived identity mismatch')
        if d['evaluation']['measurement']['measurement_status'] not in s.VALID:raise ValueError('offline complete validation failed')
        if review_valid(v,plan,orig,orig['request_id'],Path(d['original_response_path'])):continue
        if s.read(root/c/'STOP.json')['request_id']!=orig['request_id']:raise ValueError('STOP not solely the old format attempt')
        if s.read(root/c/'STOP.json')['reason']!='parse_or_evidence_failure':raise ValueError('other STOP reason')
        if d['evaluation']['adaptation']['transformation']!='single_fence_removed':raise ValueError('not verified format-only release')
        approved.append(c)
    return approved

def run(plan,p,auth,root,out,*,mode,preflight,wait_idle,transport_factory,review_fn,budget=None):
    root=Path(root);out=Path(out);allowed=validate_release(plan,p,auth,root)
    api=p.get('official_api',False)
    permissions=diagnostic_permissions(plan,p,auth,root) if p.get('diagnostic_policy') and not api else ()
    initial=reconstruct(plan,p,root,mode,permissions);oldmap={r['request_id']:r for r in plan['requests']}
    s.save(out/'schedule.json',dict(protocol_identity=p['identity'],original_stage=str(root/'engineering.AB.stage_result.json'),
        original_stage_sha256=s.sha(root/'engineering.AB.stage_result.json'),
        requests=p['requests'],history_before=initial,auth_sha256=s.digest(auth),new_experiment=False))
    blocked=dict(initial['blocked']);blocked.update({c:'not released: full validation or semantic stop' for c in p['allowed_live_candidates'] if c not in allowed})
    pending=[r for r in p['requests'] if r['original_slot_request_id'] not in initial['slot_owners'] and r['candidate'] not in blocked]
    transport=None;resident_start=None;loads=[];attempts=[]
    if pending:
        try:
            preflight()
            if not api and not wait_idle()['eligible']:blocked.update({r['candidate']:'unchanged GPU guard not met within one 300-second window' for r in pending})
        except Exception as exc:
            s.save(out/'preflight_failure.json',dict(time_jst=now(),error_type=type(exc).__name__,error=str(exc)))
            blocked.update({r['candidate']:'preflight failure; no dispatch' for r in pending})
    try:
        for req in p['requests']:
            orig=oldmap[req['original_slot_request_id']];c=req['candidate'];rid=req['request_id']
            history=reconstruct(plan,p,root,mode,permissions);blocked.update(history['blocked'])
            if orig['request_id'] in history['slot_owners']:
                attempts.append(dict(original_slot=orig['request_id'],request_id=rid,started=False,reason='slot already started/evidenced under an interface; skip'));continue
            if c in blocked:
                attempts.append(dict(original_slot=orig['request_id'],request_id=rid,started=False,reason=blocked[c]));continue
            if (history['started_or_evidenced']>=p['pool_call_cap'] or
                history['cumulative_calls']>=p['cumulative_cap'] or
                history['started_or_evidenced']-initial['started_or_evidenced']>=p['max_new_calls'] or
                history['per_configuration'][c]>=p.get('per_configuration_cap',4)):raise ValueError('call limit')
            folder=root/p.get('output_subdir',SUBDIR)/c;folder.mkdir(parents=True,exist_ok=True);base=folder/rid
            try:
                config=p['configs'][c]
                if transport is None:
                    if not api:resident_start=time.monotonic()
                    transport=transport_factory(config)
                    if not api:loads.append(dict(seconds=transport.load_seconds,shared=True))
                transport.config=config;transport.gpu_condition()
            except Exception as exc:
                blocked[c]='load or resident GPU guard failure: '+str(exc)
                if transport is None:blocked.update({x:'shared load failed; no retry' for x in allowed})
                attempts.append(dict(original_slot=orig['request_id'],request_id=rid,started=False,reason=blocked[c]));continue
            messages,schema=s.payload(plan,orig)
            reservation_id=('pmrl1-D-development:' if p.get('api_development') else 'pmrl1-CD-engineering:')+rid
            if api:
                try:
                    if budget is None:raise ValueError('missing shared budget')
                    budget.reserve(reservation_id,p['reservation_nanodollars'],dict(protocol=p['identity'],request=req))
                except Exception as exc:
                    blocked.update({x:'financial pre-reservation guard: '+type(exc).__name__ for x in allowed})
                    s.save(out/(rid+'.not_dispatched.json'),dict(request_id=rid,reason=str(exc),started=False))
                    attempts.append(dict(original_slot=orig['request_id'],request_id=rid,started=False,reason=blocked[c]));continue
            s.save(base.with_suffix('.started.json'),dict(mode=mode,request=req,original_request=orig,protocol_identity=p['identity'],
                timestamp=time.time(),time_jst=now(),cumulative_before=history['cumulative_calls'],
                **(dict(reservation_id=reservation_id) if api else {})))
            start=time.monotonic();raw=None;accounting=None;within=True
            try:
                raw=transport.send(messages,schema,request=req,raw_path=base.with_suffix('.raw.json'))
                if not base.with_suffix('.raw.json').exists():s.save(base.with_suffix('.raw.json'),raw)
                s.save(base.with_suffix('.response.json'),raw)
                if raw['request_identity']!=rid:raise ValueError('response/request mismatch')
                if api:
                    from deepseek_access import cost_from_usage
                    accounting=cost_from_usage(raw)
                    service={k:raw.get(k) for k in ('model','system_fingerprint')}
                    if service['model'] not in config['response_model_allowlist'] or not raw.get('id') or not raw.get('created'):
                        raise ValueError('provider response identity missing or changed')
                    sf=out/'service_identity.json'
                    if sf.exists() and s.read(sf)!=service:raise ValueError('provider service identity drift')
                    if not sf.exists():s.save(sf,service)
                    if accounting['accounted_upper_nanodollars'] is None:raise ValueError('missing usage; full reserve retained')
                result=interface.evaluate(plan,orig,raw,config['identity'],rid)
            except Exception as exc:
                result=dict(validation_stage='transport',measurement=dict(measurement_status='technical_failure',q=None,m=None,candidate_utility=None,
                    reward_eligible=False,error_type=type(exc).__name__,error=('official transport or validation failure; consult saved stream' if api else str(exc))))
            if api:
                actual=accounting['accounted_upper_nanodollars'] if accounting else None
                within=budget.settle(reservation_id,actual,result['measurement']['measurement_status'])
            s.save(base.with_suffix('.result.json'),dict(mode=mode,request=req,original_request=orig,
                protocol_identity=p['identity'],evaluation=result,elapsed_seconds=time.monotonic()-start,
                API_usd=(accounting.get('usage_price_estimate_usd') if accounting else None) if api else 0,
                **(dict(financial_accounting=accounting,reservation_id=reservation_id,reservation_retained=actual is None,
                    maximum_responsibility_usd=s.usd(p['reservation_nanodollars']),budget_within_reservation=within) if api else {})))
            attempts.append(dict(original_slot=orig['request_id'],request_id=rid,started=True,status=result['measurement']['measurement_status']))
            print(s.canonical(dict(completed=rid,item=orig['item_key'],candidate=c,status=result['measurement']['measurement_status'])),flush=True)
            reason=None
            if result['measurement']['measurement_status'] not in s.VALID:reason='new-interface technical failure; no retry'
            elif api and not within:reason='financial usage exceeds reservation'
            else:
                try:
                    review=review_fn(req,orig,base.with_suffix('.response.json'))
                    original_stop=review_valid(review,plan,orig,rid,base.with_suffix('.response.json'))
                    if p.get('diagnostic_policy'):
                        decision=diagnostic_disposition(review,result['measurement'])
                        if review['material_source_proven_error'] and not review.get('hard_stop_evidence'):
                            raise ValueError('source-proven hard stop requires claim, source and original criterion')
                        s.save(out/(rid+'.diagnostic.json'),decision|dict(request_id=rid,
                            original_slot_request_id=orig['request_id'],policy_version=DIAGNOSTIC_POLICY['version'],
                            response_sha256=s.sha(base.with_suffix('.response.json'))))
                        if decision['hard_stop']:reason='source-bound semantic hard stop'
                    elif original_stop:reason='source-bound semantic hard stop'
                except Exception as exc:reason='semantic review pending/invalid: '+str(exc)
            if reason:
                blocked[c]=reason
                s.save(folder/'STOP.json',dict(time_jst=now(),request_id=rid,reason=reason,original_stop_preserved=True))
    finally:
        summary=dict(time_jst=now(),protocol_identity=p['identity'],attempts=attempts,blocked=blocked,
            history_before=initial,history_after=reconstruct(plan,p,root,mode,permissions),loads=loads,
            shared_residence_seconds=time.monotonic()-resident_start if resident_start is not None else 0,
            no_next_phase=True,qualification='NOT_EVALUATED',new_experiment=False)
        s.save(out/'stage_result.json',summary)
    return summary

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-live',action='store_true',required=True)
    parser.add_argument('--development',action='store_true');parser.add_argument('--diagnostic-continuation',action='store_true');parser.add_argument('--api-engineering',action='store_true');parser.add_argument('--api-development',action='store_true');args=parser.parse_args()
    if args.api_engineering or args.api_development:
        from deepseek_access import execute_official_stage
        return execute_official_stage(sys.modules[__name__],development=args.api_development)
    package=(s.HERE/'AB_diagnostic_continuation_20261015' if args.diagnostic_continuation else
        s.HERE/'AB_development_20261015' if args.development else HERE)
    plan=s.load_plan();p=s.read(package/'protocol.json')
    if p!=protocol(plan,development=args.development,diagnostic=args.diagnostic_continuation):raise ValueError('interface/protocol/code drift')
    auth=s.read(package/'continuation_authorization.json');root=s.HERE/'live_runs';out=root/p.get('output_subdir',SUBDIR)/'stage'
    with (root/'.pool.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);out.mkdir(parents=True,exist_ok=False)
        checks=GPUChecks(out)
        approval=s.read(s.HERE/'local_engineering_20261015/approval_engineering_AB.json')
        def preflight():
            t=time.monotonic();value=validate_artifacts(plan,approval)
            for req in p['requests']:s.payload(plan,next(r for r in plan['requests'] if r['request_id']==req['original_slot_request_id']))
            value['elapsed_seconds']=time.monotonic()-t;s.save(out/'artifact_preflight.json',value)
        def factory(config):
            from adapters import GemmaTransport
            class Observed(GemmaTransport):
                def gpu_condition(self):
                    r=checks.check(own_pid=os.getpid())
                    if not r['eligible']:raise ValueError(str(r['rejection_reasons']))
                    return r['queries'][0]['stdout']
            return Observed(config,approval['local_model_path'])
        def review(req,orig,response):
            path=out/(req['request_id']+'.review.json');start=time.monotonic()
            print(s.canonical(dict(awaiting_source_review=str(path),request_id=req['request_id'],item=orig['item_key'])),flush=True)
            while not path.exists():
                if time.monotonic()-start>600:raise TimeoutError('source review not supplied; stop configuration')
                time.sleep(1)
            return s.read(path)
        answer=run(plan,p,auth,root,out,mode='live',preflight=preflight,wait_idle=checks.wait_idle,transport_factory=factory,review_fn=review)
        print(s.canonical(dict(history=answer['history_after'],blocked=answer['blocked'],shared_residence_seconds=answer['shared_residence_seconds'])),flush=True)

if __name__=='__main__':main()
