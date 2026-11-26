"""Read-only decision observations, never a correct-action or reward oracle.

Consumes collector-verified private events. Public projection is an allowlist;
query text, resource text, handles, replies, IDs and error strings stay private.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import hashlib
import json
import re

PROTOCOL = 'pmrl1-j-dynamic-decision-diagnostics-v1'
ARMS = ('STOP','FixedTop4Macro','LLMOneShot','LLMToolAgent','SequentialRule','SequentialNoText')


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def words(value):
    return frozenset(re.findall(r"[a-z0-9']+",value.casefold()))


def index_events(events):
    requests={e['request']['request_id']:(e['request']['binding']['task_id'],e['request']['binding']['method'])
              for e in events if e['event']=='MODEL_REQUEST_START'}
    result=defaultdict(list)
    for event in events:
        key=(event.get('task_id'),event.get('method'))
        if not all(key):
            if event.get('task_id') and event['event'] in {'ONESHOT_COMMITTED','ONESHOT_ABSENT_HIT_STOP'}:
                key=(event['task_id'],'LLMOneShot')
            elif event.get('request_id') in requests:key=requests[event['request_id']]
            elif event['event']=='MODEL_REQUEST_START':key=requests[event['request']['request_id']]
            elif event['event']=='DYNAMIC_STOP' and event.get('current'):key=tuple(event['current'])
        if len(key)==2 and all(key):result[key].append(event)
    return result


def _output(endpoint,events):
    if type(endpoint.get('output')) is dict:return endpoint['output']
    returned=[e['output'] for e in events if e['event']=='MODEL_REQUEST_RETURNED' and e.get('role')=='terminal']
    return returned[-1] if returned else None


def technical_state(endpoint,events):
    names={e['event'] for e in events}
    if 'AGENT_PATH_START' not in names:return 'not_executed'
    output=_output(endpoint,events)
    if 'AGENT_PATH_INCOMPLETE' in names or (output and output.get('finish_reason')=='length'):
        return 'terminal_truncation'
    validated=any(e['event']=='MODEL_REQUEST_VALIDATED' and e.get('role')=='terminal'
                  and e.get('finish_reason')=='eos' for e in events)
    if validated and 'AGENT_PATH_COMPLETED' in names:
        return 'complete_eos' if endpoint.get('endpoint_committed') is True else 'returned_eos_uncommitted'
    if names & {'DYNAMIC_STOP','MODEL_REQUEST_FAILED','EXPERIMENT_GUARD_FAILED'}:return 'technical_failure'
    return 'unresolved_or_in_progress'


def stop_observation(method,events):
    returned=[e for e in events if e['event']=='TOOL_RETURNED']
    acquisitions=[e for e in returned if e['action']['action']!='STOP']
    controls=[e for e in events if e['event']=='MODEL_REQUEST_START' and e.get('role')=='agent']
    limits=[]
    if len(acquisitions)>=4:limits.append('acquisition_cap')
    if method=='LLMToolAgent' and len(controls)>=4:limits.append('control_call_cap')
    token_refusal=any(e['event']=='TOOL_REJECTED' and e.get('reason')=='token_budget' for e in events)
    macro_refusal=any(e['event']=='MACRO_BUDGET_STOP' for e in events)
    absent=any(e['event']=='ONESHOT_ABSENT_HIT_STOP' for e in events)
    forced=[e for e in events if e['event']=='FORCED_STOP']
    active=any(e['event']=='CONTROLLER_ACTION_VALIDATED' and e['action']['action']=='STOP' for e in events)
    stop_returned=any(e['action']['action']=='STOP' for e in returned)
    planned=[e['plan'] for e in events if e['event']=='ONESHOT_COMMITTED']
    if not events:reason='not_executed'
    elif token_refusal or macro_refusal:reason='tool_token_budget'
    elif absent:reason='absent_hit'
    elif method=='STOP' and stop_returned:reason='initial_fixed_stop'
    elif method=='FixedTop4Macro':
        search=[e for e in events if e['event']=='MACRO_SEARCH_RETURNED']
        if not search:reason='unresolved'
        elif len(search[-1].get('private_ranked_ids',[]))<4:reason='resource_frontier_exhausted'
        else:reason='macro_top4_complete'
    elif method=='LLMToolAgent' and active and stop_returned and not forced:reason='explicit_model_stop'
    elif method=='LLMOneShot' and planned and any(a['action']=='STOP' for a in planned[-1]) and stop_returned and not forced:
        reason='committed_stop'
    elif method in ('SequentialRule','SequentialNoText') and stop_returned:reason='rule_program_end'
    elif forced:
        if 'control_call_cap' in limits:reason='control_call_cap'
        elif method=='LLMOneShot':reason='program_exhausted'
        elif returned and returned[-1].get('observation',{}).get('accesses_remaining')==0:reason='acquisition_cap'
        else:reason='forced_stop_unresolved'
    else:reason='unresolved'
    return dict(stop_reason=reason,binding_limits=limits,model_selected_stop=reason=='explicit_model_stop',
        explicit_committed_stop=reason=='committed_stop',acquisitions_returned=len(acquisitions),
        controller_agent_starts=len(controls),token_budget_refused=token_refusal or macro_refusal,
        absent_planned_hit=absent)


def read_adaptation(events):
    """Trace behavior only. New observed terms do not establish causal improvement."""
    previous=None;count=0;novel_queries=0;changed_queries=0;unchanged_content=0;previous_query=None;hidden=0
    rows=[]
    for e in events:
        if e['event']!='TOOL_RETURNED' or e['action']['action']=='STOP':continue
        action=e['action'];obs=e['observation'];initial=words(obs['query'])
        current=obs.get('readings')
        if action['action']=='SEARCH':
            novel=words(action['query'])-initial
            changed=previous_query is not None and action['query']!=previous_query
            if novel:novel_queries+=1
            if changed:changed_queries+=1
            previous_query=action['query']
        else:novel=set();changed=False
        unchanged=(digest(current)==digest(previous) if previous is not None and current is not None else None)
        unchanged_content+=unchanged is True;hidden+=current is None;count+=1
        rows.append(dict(event_seq=e.get('seq'),after_state_sha256=e.get('after_state_sha256'),
            observation_sha256=e.get('observation_sha256'),action=action['action'],
            new_query_terms_count=len(novel),query_changed_after_prior_search=changed,
            delivered_reading_content_unchanged=unchanged,observed_reading_units=None if current is None else len(current),
            accesses_remaining=obs.get('accesses_remaining'),decision_value=None))
        previous=current
    return dict(transitions=rows,returned_acquisitions=count,searches_with_new_observed_terms=novel_queries,
        searches_changed_after_prior_search=changed_queries,content_unchanged_acquisitions=None if hidden else unchanged_content,
        content_comparison_unavailable_transitions=hidden,
        interpretation='behavior/source observation only; no action-value or task-success label')


def appropriateness(row,review=None,stop_review=None):
    """Optional explicit development reviews; missing/uncertain never becomes zero."""
    if row['technical_status']!='complete_eos':return 'unresolved'
    review=review or {};stop_review=stop_review or {}
    if row['acquisitions_returned']==0 and review.get('task_success')=='pass':
        return 'reasonable_nonacquisition_within_reviewed_task'
    if row['acquisitions_returned']>0 and review.get('task_success')=='pass' and stop_review.get('task_success')=='pass':
        return 'possible_overacquisition_same_reviewed_success_without_reads'
    if (review.get('task_success')=='fail' and review.get('required_evidence_missing') is True
            and review.get('legal_missing_evidence_exists') is True):
        return 'acquisition_insufficient_candidate_from_explicit_review'
    return 'unresolved'


def failure_layer(events):
    """Mechanical failure taxonomy, never a semantic task-failure label."""
    errors=[e.get('reason','') for e in events if e['event']=='DYNAMIC_STOP']
    if any('ControllerProtocolError' in r and any(k in r for k in (
        'unobserved query token','initial query','foreign handle','unavailable in current state',
        'earlier planned SEARCH','acquisition cap','action after STOP')) for r in errors):
        return 'controller_state_protocol'
    if any('ControllerProtocolError' in r for r in errors):return 'controller_parse_or_constraint'
    if any(e['event']=='MODEL_REQUEST_FAILED' for e in events):return 'model_transport_or_generation'
    if errors:return 'other_technical_failure'
    return None


def normalize_quality_reviews(reviews,endpoints):
    """Join existing assistant development observations; do not re-score text.

    A missing original quote group is a delivery diagnostic, not proof that
    no alternative evidence was available or that retrieval caused failure.
    """
    source={(r['task_id'],r['method']):r for r in endpoints};result={}
    mapping={'complete':'pass','incomplete':'fail','uncertain':'uncertain','not_evaluated':'pending'}
    intervals={'complete':[1,1],'incomplete':[0,0],'uncertain':[0,1],'not_evaluated':None}
    for review in reviews:
        key=(review['task_id'],review['method'])
        if key not in source or key in result:raise ValueError('quality review grid identity')
        end=source[key]
        for field in ('slot_id','output_sha256','payload_sha256','evalspec_sha256'):
            if review[field]!=end[field]:raise ValueError('quality review binding '+field)
        status=review['task_completion']['status']
        if status not in mapping or review['task_completion']['development_interval']!=intervals[status]:
            raise ValueError('quality status interval')
        if status!='not_evaluated' and (end.get('endpoint_committed') is not True
                or end.get('technical_status')!='returned_eos' or end.get('real_model_output') is not True):
            raise ValueError('quality observation requires real committed EOS')
        if review.get('formal_reward') is not None:raise ValueError('development reward scope')
        facts=[f for f in review.get('facts',[]) if f.get('required') is True]
        result[key]=dict(task_success=mapping[status],task_success_interval=intervals[status],
            required_fact_observations=len(facts) if status!='not_evaluated' else None,
            required_original_groups_absent=sum(f.get('source_delivery')=='original_group_absent' for f in facts) if status!='not_evaluated' else None,
            required_original_groups_partial=sum(f.get('source_delivery')=='partial_original_group' for f in facts) if status!='not_evaluated' else None,
            required_original_groups_complete=sum(f.get('source_delivery')=='complete_original_group' for f in facts) if status!='not_evaluated' else None,
            evidence_gap_is_exhaustive=False,review_scope='existing_assistant_development_observation_not_qualified_reward')
    if set(result)!=set(source):raise ValueError('quality review full grid required')
    return result


def diagnose(endpoints,events,*,reviews=None):
    indexed=index_events(events);reviews=reviews or {};rows=[]
    for endpoint in endpoints:
        task,method=endpoint['task_id'],endpoint['method']
        if method not in ARMS:raise ValueError('unexpected arm')
        selected=indexed.get((task,method),[])
        row=dict(task_id=task,method=method,batch=endpoint.get('batch'),
            technical_status=technical_state(endpoint,selected),
            **stop_observation(method,selected),**read_adaptation(selected),
            task_success=(reviews.get((task,method)) or {}).get('task_success','pending'),
            formal_reward=None,correct_action_label=None,logging_wall_ns=None,
            logging_scope='no isolated logging span in frozen executor; wall remainder is not logging cost')
        review=reviews.get((task,method)) or {}
        for field in ('task_success_interval','required_fact_observations','required_original_groups_absent',
                      'required_original_groups_partial','required_original_groups_complete','evidence_gap_is_exhaustive'):
            row[field]=review.get(field)
        own=review.get('task_success_interval');initial=(reviews.get((task,'STOP')) or {}).get('task_success_interval')
        row['task_success_delta_vs_initial_stop_interval']=(
            [own[0]-initial[1],own[1]-initial[0]] if own is not None and initial is not None else None)
        if method=='STOP' and own is not None:row['task_success_delta_vs_initial_stop_interval']=[0,0]
        control_outputs=[e['output'] for e in selected if e['event']=='MODEL_REQUEST_RETURNED'
                         and e.get('role') in ('oneshot','agent')]
        row.update(failure_layer=failure_layer(selected),
            controller_eos_returns=sum(o.get('finish_reason')=='eos' for o in control_outputs),
            controller_grammar_terminated_returns=sum((o.get('grammar_state') or {}).get('grammar_terminated') is True for o in control_outputs),
            controller_programs_state_validated=sum(e['event']=='CONTROLLER_PROGRAM_VALIDATED' for e in selected),
            controller_actions_state_validated=sum(e['event']=='CONTROLLER_ACTION_VALIDATED' for e in selected))
        if row['technical_status']=='technical_failure' and row['stop_reason']=='unresolved':
            row['stop_reason']='technical_failure'
        if method=='FixedTop4Macro':
            parents=sum(e['event']=='MACRO_PARENT_RETURNED' for e in selected)
            searches=sum(e['event']=='MACRO_SEARCH_RETURNED' for e in selected)
            row.update(acquisitions_returned=parents+searches,macro_parent_reads=parents,
                       macro_retrieval_calls=searches,primitive_domain='macro_up_to_five_not_four_action_matched')
        else:row['primitive_domain']='at_most_four_search_expand'
        row['appropriateness']=appropriateness(row,reviews.get((task,method)),reviews.get((task,'STOP')))
        rows.append(row)
    return rows


def select_midstates(plan,events):
    """At most one per frozen source-pair batch, without outcomes or coverage filters."""
    indexed=index_events(events);chosen=[]
    for batch in plan['batches']:
        found=None
        for task in batch['task_ids']:
            for e in indexed.get((task,'LLMToolAgent'),[]):
                if e['event']!='TOOL_RETURNED' or e['action']['action']=='STOP':continue
                obs=e['observation']
                if obs['accesses_remaining']>0 and set(obs['action_mask']) & {'SEARCH','EXPAND'}:
                    found=dict(batch=batch['batch'],task_id=task,event_seq=e.get('seq'),
                        state_sha256=e.get('after_state_sha256'),observation_sha256=e.get('observation_sha256'),
                        observation=obs,alternate_endpoint='not_determined',formal_reward=None)
                    break
            if found:break
        chosen.append(found or dict(batch=batch['batch'],status='no_eligible_observed_midstate',formal_reward=None))
    return chosen


def reconstruct_midstate_payload(observation,*,tokenizer,renderer,baseline_sha256,renderer_sha256):
    """CPU rendering of <=4 selected logged observations; no hidden pool or gold."""
    if 'readings' not in observation or not isinstance(observation.get('turns'),list):
        raise ValueError('complete visible observation required')
    readings=observation['readings']
    if [r['ordinal'] for r in readings]!=list(range(1,len(readings)+1)):
        raise ValueError('logged reading order')
    # Exactly SearchExpandEpisode._views: canonical source order in one MS block.
    views=[] if not readings else [dict(head='MS',view='raw',reported_at=None,stage=None,
        reading_text='\n\n'.join(r['reading_text'] for r in readings))]
    material=dict(visible_prefix=dict(turns=observation['turns']),readings=views)
    packet,_=renderer.packet(material,tokenizer,baseline_sha256=baseline_sha256,implementation_sha256=renderer_sha256)
    if len(packet.input_ids)!=observation['input_tokens']:
        raise ValueError('native reconstruction token-count mismatch')
    return packet.payload()


def exact_terminal_matches(*,task_id,reconstructed_payload,reconstruction_verified,endpoints,state_method='LLMToolAgent'):
    """Same-task canonical bytes AND SHA, not merely matching reading sets.

    Caller must bind exact frozen renderer/tokenizer and selected state first.
    This function never treats a hash alone as a reconstruction certificate.
    """
    if reconstruction_verified is not True or type(reconstructed_payload) is not dict:
        return dict(status='unknown_no_verified_reconstruction',matches=[])
    h=digest(reconstructed_payload);matches=[];same_path=[]
    for endpoint in endpoints:
        if endpoint['task_id']!=task_id:continue
        candidate=endpoint.get('model_input')
        same_bytes=(json.dumps(candidate,ensure_ascii=False,sort_keys=True,separators=(',',':'))
                    ==json.dumps(reconstructed_payload,ensure_ascii=False,sort_keys=True,separators=(',',':')))
        if (same_bytes and endpoint.get('payload_sha256')==h and endpoint.get('real_model_output') is True
                and endpoint.get('technical_status')=='returned_eos' and endpoint.get('endpoint_committed') is True):
            output=endpoint.get('output') or {}
            if output.get('finish_reason')=='eos':
                item=dict(method=endpoint['method'],payload_sha256=h,
                    output_sha256=endpoint.get('output_sha256'),meaning='existing_same_payload_terminal_not_independent_replication')
                (same_path if endpoint['method']==state_method else matches).append(item)
    return dict(status='existing_cross_arm_same_payload_endpoint' if matches else
                ('same_path_endpoint_only' if same_path else 'no_exact_terminal_match'),matches=matches,same_path_matches=same_path)


PUBLIC_FIELDS=('method','technical_status','stop_reason','binding_limits','model_selected_stop',
    'explicit_committed_stop','acquisitions_returned','controller_agent_starts','token_budget_refused',
    'absent_planned_hit','returned_acquisitions','searches_with_new_observed_terms',
    'searches_changed_after_prior_search','content_unchanged_acquisitions','primitive_domain',
    'task_success','appropriateness','formal_reward','correct_action_label','logging_wall_ns','failure_layer',
    'controller_eos_returns','controller_grammar_terminated_returns',
    'controller_programs_state_validated','controller_actions_state_validated','task_success_interval',
    'required_fact_observations','required_original_groups_absent','required_original_groups_partial',
    'required_original_groups_complete','evidence_gap_is_exhaustive','task_success_delta_vs_initial_stop_interval')


def public_projection(rows,task_order):
    aliases={task:f'T{i+1:02d}' for i,task in enumerate(task_order)}
    return [dict(task=aliases[r['task_id']],**{key:r[key] for key in PUBLIC_FIELDS}) for r in rows]


def policy_pair_reuse(endpoints,task_order):
    """Actual same-task outputs only; repeated deterministic prompts add no groups."""
    indexed={(r['task_id'],r['method']):r for r in endpoints};rows=[]
    for i,task in enumerate(task_order):
        pair=[indexed[(task,m)] for m in ('LLMOneShot','LLMToolAgent')]
        eligible=all(r.get('endpoint_committed') is True and r.get('real_model_output') is True
                     and r.get('technical_status')=='returned_eos' for r in pair)
        row=dict(task=f'T{i+1:02d}',both_actual_committed_eos=eligible,
                 exact_payload_equal=None,reply_text_equal=None,reply_token_ids_equal=None)
        if eligible:
            a,b=pair
            row.update(exact_payload_equal=(json.dumps(a['model_input'],sort_keys=True,ensure_ascii=False)
                ==json.dumps(b['model_input'],sort_keys=True,ensure_ascii=False)
                and a['payload_sha256']==b['payload_sha256']==digest(a['model_input'])),
                reply_text_equal=a['output']['text']==b['output']['text'],
                reply_token_ids_equal=a['output']['token_ids']==b['output']['token_ids'])
        rows.append(row)
    return dict(protocol=PROTOCOL,pairs=rows,formal_reward=None,
        interpretation='existing policy-package pairs; exact duplicates do not add independent states')


def aggregate(rows):
    return dict(protocol=PROTOCOL,paths=len(rows),technical_status=dict(Counter(r['technical_status'] for r in rows)),
        stop_reasons=dict(Counter(r['stop_reason'] for r in rows)),
        appropriateness=dict(Counter(r['appropriateness'] for r in rows)),
        model_selected_stops=sum(r['model_selected_stop'] for r in rows),
        task_success_observations=dict(Counter(r['task_success'] for r in rows)),
        reviewed_by_arm={m:dict(Counter(r['task_success'] for r in rows if r['method']==m)) for m in ARMS},
        no_correct_action_labels=True,formal_reward=None,logging_wall_ns=None,
        causal_identification='policy-package endpoints only unless separately verified exact intermediate payload matches',
        training_status='not_established_by_call_count_or_coverage; requires real reviewed task contrasts and observable choice signal')
