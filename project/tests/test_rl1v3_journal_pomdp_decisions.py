import json
import pytest
from metacom_pm.rl1v3.journal import pomdp_decision_diagnostics as D


def event(name,method='LLMToolAgent',**kw):
    return dict(event=name,task_id='synthetic-task',method=method,**kw)


def returned(action='SEARCH',**observation):
    obs=dict(query='hobby report',readings=[{'ordinal':1,'reading_text':'A synthetic hobby record'}],
             action_mask=['STOP','SEARCH','EXPAND'],accesses_remaining=3)
    obs.update(observation)
    return event('TOOL_RETURNED',action={'action':action,'query':'hobby'},observation=obs)


def test_program_events_without_method_are_not_lost():
    e={'event':'ONESHOT_COMMITTED','task_id':'synthetic-task','plan':[{'action':'STOP'}]}
    selected=D.index_events([e,event('TOOL_RETURNED','LLMOneShot',action={'action':'STOP'})])
    r=D.stop_observation('LLMOneShot',selected[('synthetic-task','LLMOneShot')])
    assert r['stop_reason']=='committed_stop' and r['explicit_committed_stop']


def test_forced_stop_is_not_model_selected_or_budget_free():
    e=[event('FORCED_STOP',reason='program_end_or_control_access_cap'),
       event('TOOL_RETURNED',action={'action':'STOP'})]
    assert D.stop_observation('LLMToolAgent',e)['stop_reason']=='forced_stop_unresolved'
    e += [event('MODEL_REQUEST_START',role='agent') for _ in range(4)]
    r=D.stop_observation('LLMToolAgent',e)
    assert r['stop_reason']=='control_call_cap' and not r['model_selected_stop']


@pytest.mark.parametrize('name,kw,expected',[
    ('TOOL_REJECTED',{'reason':'token_budget'},'tool_token_budget'),
    ('ONESHOT_ABSENT_HIT_STOP',{},'absent_hit'),
    ('MACRO_BUDGET_STOP',{},'tool_token_budget')])
def test_separate_budget_and_resource_reasons(name,kw,expected):
    assert D.stop_observation('LLMOneShot',[event(name,**kw)])['stop_reason']==expected


def test_active_stop_requires_validated_model_choice():
    e=[event('CONTROLLER_ACTION_VALIDATED',action={'action':'STOP'}),event('TOOL_RETURNED',action={'action':'STOP'})]
    assert D.stop_observation('LLMToolAgent',e)['model_selected_stop']
    assert not D.stop_observation('SequentialRule',e)['model_selected_stop']


def test_terminal_truncation_never_complete_even_with_eos_other_role():
    e=[event('AGENT_PATH_START'),event('MODEL_REQUEST_VALIDATED',role='agent',finish_reason='eos')]
    assert D.technical_state({'output':{'finish_reason':'length'}},e)=='terminal_truncation'
    assert D.technical_state({},[])=='not_executed'
    assert D.technical_state({},e+[event('DYNAMIC_STOP')])=='technical_failure'


def test_returned_endpoint_does_not_claim_committed_job():
    e=[event('AGENT_PATH_START'),event('MODEL_REQUEST_VALIDATED',role='terminal',finish_reason='eos'),
       event('AGENT_PATH_COMPLETED')]
    assert D.technical_state({'endpoint_committed':False},e)=='returned_eos_uncommitted'
    assert D.technical_state({'endpoint_committed':True},e)=='complete_eos'


def test_no_text_missing_readings_is_unknown_not_redundant_content():
    e=[returned(),returned()]
    for r in e:r['observation'].pop('readings')
    result=D.read_adaptation(e)
    assert result['content_unchanged_acquisitions'] is None
    assert result['content_comparison_unavailable_transitions']==2


def test_observed_novel_query_is_behavior_not_task_success():
    first=returned();second=returned();second['action']['query']='hobby synthetic'
    r=D.read_adaptation([first,second])
    assert r['searches_with_new_observed_terms']==1 and r['content_unchanged_acquisitions']==1
    assert all(t['decision_value'] is None for t in r['transitions'])


def test_call_reduction_and_coverage_do_not_produce_success():
    row={'technical_status':'complete_eos','acquisitions_returned':0}
    assert D.appropriateness(row,{'evidence_coverage':'complete'})=='unresolved'
    assert D.appropriateness(row,{'task_success':'uncertain'})=='unresolved'
    assert D.appropriateness(row,{'task_success':'pass'})=='reasonable_nonacquisition_within_reviewed_task'
    row['acquisitions_returned']=4
    assert D.appropriateness(row,{'task_success':'pass'},{'task_success':'pass'}).startswith('possible_overacquisition')


def test_failed_acquisition_requires_explicit_missing_evidence_review():
    row={'technical_status':'complete_eos','acquisitions_returned':1}
    assert D.appropriateness(row,{'task_success':'fail'})=='unresolved'
    r={'task_success':'fail','required_evidence_missing':True,'legal_missing_evidence_exists':True}
    assert D.appropriateness(row,r).startswith('acquisition_insufficient_candidate')


def test_midstate_selection_uses_first_legal_state_not_favorable_outcome():
    e1=returned();e1.update(seq=10,after_state_sha256='state-one')
    e2=returned();e2.update(seq=11,after_state_sha256='state-two',task_success='pass')
    plan={'batches':[{'batch':'DR1','task_ids':['synthetic-task']}]}
    assert D.select_midstates(plan,[e1,e2])[0]['state_sha256']=='state-one'
    e1['observation']['accesses_remaining']=0
    assert D.select_midstates(plan,[e1,e2])[0]['state_sha256']=='state-two'


def endpoint(payload):
    return dict(task_id='synthetic-task',method='STOP',model_input=payload,payload_sha256=D.digest(payload),
        real_model_output=True,technical_status='returned_eos',endpoint_committed=True,output={'finish_reason':'eos'})


def test_exact_match_requires_verified_reconstruction_and_true_bytes():
    payload={'input_ids':[1],'messages':[],'decode':{}}
    end=endpoint(payload)
    assert D.exact_terminal_matches(task_id='synthetic-task',reconstructed_payload=payload,
        reconstruction_verified=False,endpoints=[end])['status'].startswith('unknown')
    assert len(D.exact_terminal_matches(task_id='synthetic-task',reconstructed_payload=payload,
        reconstruction_verified=True,endpoints=[end])['matches'])==1
    end['model_input']={'input_ids':[True],'messages':[],'decode':{}}
    assert not D.exact_terminal_matches(task_id='synthetic-task',reconstructed_payload=payload,
        reconstruction_verified=True,endpoints=[end])['matches']


@pytest.mark.parametrize('changes',[{'real_model_output':False},{'technical_status':'unexecuted'},
    {'endpoint_committed':False},{'payload_sha256':'wrong'},{'task_id':'other-task'}])
def test_exact_candidate_excludes_nonreal_uncommitted_or_other_task(changes):
    payload={'a':1};end=endpoint(payload);end.update(changes)
    assert not D.exact_terminal_matches(task_id='synthetic-task',reconstructed_payload=payload,
        reconstruction_verified=True,endpoints=[end])['matches']


def test_public_projection_is_whitelist_and_never_private_text():
    row=D.diagnose([{'task_id':'synthetic-task','method':'STOP'}],[])[0]
    row.update(query='PRIVATE_SENTINEL',output='PRIVATE_SENTINEL',raw_error='PRIVATE_SENTINEL')
    public=D.public_projection([row],['synthetic-task'])
    assert 'PRIVATE_SENTINEL' not in json.dumps(public)
    assert 'synthetic-task' not in json.dumps(public)
    assert public[0]['formal_reward'] is None and public[0]['logging_wall_ns'] is None


def test_grammar_eos_does_not_hide_state_protocol_failure_or_invent_tools():
    start=event('MODEL_REQUEST_START','LLMOneShot',role='oneshot',request={
        'request_id':'synthetic-request','binding':{'task_id':'synthetic-task','method':'LLMOneShot'}})
    returned_control={'event':'MODEL_REQUEST_RETURNED','request_id':'synthetic-request','role':'oneshot',
        'output':{'finish_reason':'eos','grammar_state':{'grammar_terminated':True}}}
    stopped={'event':'DYNAMIC_STOP','current':['synthetic-task','LLMOneShot'],
        'reason':'ControllerProtocolError: query shape or unobserved query token'}
    events=[event('AGENT_PATH_START','LLMOneShot'),start,returned_control,stopped]
    row=D.diagnose([{'task_id':'synthetic-task','method':'LLMOneShot'}],events)[0]
    assert row['technical_status']=='technical_failure'
    assert row['failure_layer']=='controller_state_protocol'
    assert row['controller_eos_returns']==row['controller_grammar_terminated_returns']==1
    assert row['controller_programs_state_validated']==0
    assert row['acquisitions_returned']==0 and row['stop_reason']=='technical_failure'
    assert row['task_success']=='pending' and row['appropriateness']=='unresolved'


def test_midstate_own_endpoint_and_other_arm_endpoint_remain_distinct():
    payload={'input_ids':[7]};own=endpoint(payload);own['method']='LLMToolAgent'
    check=D.exact_terminal_matches(task_id='synthetic-task',reconstructed_payload=payload,
        reconstruction_verified=True,endpoints=[own])
    assert check['status']=='same_path_endpoint_only' and not check['matches']
    assert len(check['same_path_matches'])==1


def test_quality_join_keeps_unknown_and_original_group_gap_distinct():
    end=dict(task_id='synthetic-task',method='STOP',slot_id='s',output_sha256='o',payload_sha256='p',
        evalspec_sha256='e',endpoint_committed=True,technical_status='returned_eos',real_model_output=True)
    review={k:end[k] for k in ('task_id','method','slot_id','output_sha256','payload_sha256','evalspec_sha256')}
    review.update(task_completion={'status':'uncertain','development_interval':[0,1]},formal_reward=None,
        facts=[{'required':True,'source_delivery':'original_group_absent'}])
    joined=D.normalize_quality_reviews([review],[end])[('synthetic-task','STOP')]
    assert joined['task_success']=='uncertain' and joined['task_success_interval']==[0,1]
    assert joined['required_original_groups_absent']==1 and not joined['evidence_gap_is_exhaustive']
    assert 'required_evidence_missing' not in joined
    review['output_sha256']='wrong'
    with pytest.raises(ValueError,match='binding'):D.normalize_quality_reviews([review],[end])


def test_quality_join_rejects_success_on_unexecuted_and_reward_upgrade():
    end=dict(task_id='synthetic-task',method='STOP',slot_id='s',output_sha256=None,payload_sha256=None,
        evalspec_sha256='e',endpoint_committed=False,technical_status='unexecuted',real_model_output=False)
    review={k:end[k] for k in ('task_id','method','slot_id','output_sha256','payload_sha256','evalspec_sha256')}
    review.update(task_completion={'status':'complete','development_interval':[1,1]},formal_reward=None)
    with pytest.raises(ValueError,match='real committed EOS'):D.normalize_quality_reviews([review],[end])
    review['task_completion']={'status':'not_evaluated','development_interval':None}
    joined=D.normalize_quality_reviews([review],[end])[('synthetic-task','STOP')]
    assert joined['required_fact_observations'] is None and joined['required_original_groups_absent'] is None
    review['formal_reward']=0
    with pytest.raises(ValueError,match='reward'):D.normalize_quality_reviews([review],[end])


def test_uncertain_self_comparison_is_zero_but_missing_stays_null():
    key=('synthetic-task','STOP');end={'task_id':key[0],'method':key[1]}
    review={'task_success':'uncertain','task_success_interval':[0,1]}
    assert D.diagnose([end],[],reviews={key:review})[0]['task_success_delta_vs_initial_stop_interval']==[0,0]
    assert D.diagnose([end],[])[0]['task_success_delta_vs_initial_stop_interval'] is None


def test_policy_pair_reuse_requires_actual_endpoints_and_exact_payload_bytes():
    a=endpoint({'input_ids':[1]});a['method']='LLMOneShot';a['output'].update(text='synthetic',token_ids=[2])
    b=endpoint({'input_ids':[True]});b['method']='LLMToolAgent';b['output'].update(text='synthetic',token_ids=[2])
    row=D.policy_pair_reuse([a,b],['synthetic-task'])['pairs'][0]
    assert row['both_actual_committed_eos'] and row['reply_text_equal'] and not row['exact_payload_equal']
    b['endpoint_committed']=False
    assert D.policy_pair_reuse([a,b],['synthetic-task'])['pairs'][0]['reply_text_equal'] is None
