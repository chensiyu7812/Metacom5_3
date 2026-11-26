"""Synthetic CPU-only restoration/admission/runtime regression fixtures."""
from copy import deepcopy
import pytest
from metacom_pm.rl1v3.journal import pomdp_midstate_counterfactual as M
from test_rl1v3_journal_pomdp_dynamic import factory,tasks,Clock,Backend


def prepared():
    clock=Clock();states=[];ts=tasks()
    for task in ts:
        e=factory(task,'LLMToolAgent',emit=lambda *a,**k:None,clock=clock,deadline_ns=10**12)
        action={'action':'SEARCH','query':task['query']};e.step(action)
        snap=M.state_private(e)
        states.append(dict(task_id=task['task_id'],replay_actions=[action],observation=snap['observation'],
            **{k:snap[k] for k in ('state_sha256','observation_sha256','payload_sha256')}))
    req,diags,frozen=M.request_rows(ts,states,factory,clock,10**12)
    return clock,ts,req,diags,frozen


def test_two_states_all_observed_handles_and_rank1_without_gold():
    clock,ts,req,diags,states=prepared()
    assert len(req)==4 and [d['selected_handle'] for d in diags]==[s['snapshot']['last_hits'][0] for s in states]
    assert all(len(d['candidates'])==2 for d in diags)
    assert all(c['source_legal'] and c['budget_reachable'] for d in diags for c in d['candidates'])
    assert all(r['actions'][-1]=={'action':'STOP'} for r in req)
    assert all(r['formal_reward'] is None for r in req)


def test_complete_observation_protects_unhashed_last_hits():
    clock,ts,req,diags,states=prepared();bad=deepcopy(states[0])
    bad['observation']['last_hits'].reverse()
    with pytest.raises(M.L.AdmissionError,match='complete restored observation'):
        M.restore(factory,ts[0],bad,emit=lambda *a,**k:None,clock=clock,deadline_ns=10**12)


def test_full_snapshot_checks_allowed_tokens_not_only_state_hash():
    clock,ts,req,diags,states=prepared();bad=deepcopy(states[0]);bad['snapshot']['allowed_tokens'].append('unobserved')
    with pytest.raises(M.L.AdmissionError,match='private snapshot'):
        M.restore(factory,ts[0],bad,emit=lambda *a,**k:None,clock=clock,deadline_ns=10**12)


def test_rank1_refusal_is_not_replaced_by_next_candidate():
    with pytest.raises(M.L.AdmissionError,match='highest observed'):
        M.choose_rank1([{'handle':'first','source_legal':True,'action_admissible':False,'budget_reachable':False},
            {'handle':'next','source_legal':True,'action_admissible':True,'budget_reachable':True}])


def test_duplicate_expansion_charged_without_new_content():
    clock,ts,req,diags,states=prepared()
    e=M.restore(factory,ts[0],states[0],emit=lambda *a,**k:None,clock=clock,deadline_ns=10**12)
    handle=e.last_hits[0];first=M.candidate_receipt(e,handle);second=M.candidate_receipt(e,handle)
    assert first['canonical_new_content_units']==1 and second['canonical_new_content_units']==0
    assert second['already_expanded'] and second['native_input_token_delta']==0
    assert second['charged_tool_tokens_delta']>0


def test_four_new_calls_no_controller_and_post_restore_timing():
    clock,ts,req,diags,states=prepared();backend=Backend();events=[]
    result=M.execute(plan={'scope_sha256':'synthetic'},requests=req,states=states,tasks=ts,factory=factory,
        backend=backend,emit=lambda event,**f:events.append(dict(event=event,**f)),clock=clock,deadline_ns=10**12,guard=lambda:None)
    assert result['physical_backend_calls']==len(backend.sent)==4 and result['controller_calls']==0
    assert result['actual_model_calls']==0
    assert all(r['role']=='terminal' for r in backend.sent)
    restored=[e for e in events if e['event']=='MIDSTATE_RESTORED']
    starts=[e for e in events if e['event']=='BRANCH_DECISION_START']
    assert all(r['stamp']['monotonic_ns']<s['stamp']['monotonic_ns'] for r,s in zip(restored,starts))
    assert all(r['decision_to_validated_reply_ns']>0 and r['restoration_ns']>0 for r in result['branches'])


@pytest.mark.parametrize('mode',['error','mismatch','terminal_length'])
def test_first_failure_stops_no_retry(mode):
    clock,ts,req,diags,states=prepared();backend=Backend(mode);events=[]
    with pytest.raises((RuntimeError,M.L.AdmissionError)):
        M.execute(plan={'scope_sha256':'synthetic'},requests=req,states=states,tasks=ts,factory=factory,
            backend=backend,emit=lambda event,**fields:events.append(dict(event=event,**fields)),clock=clock,deadline_ns=10**12,guard=lambda:None)
    assert len(backend.sent)==1
    if mode=='error':
        failed=next(e for e in events if e['event']=='MODEL_REQUEST_FAILED')
        assert failed['elapsed_ns']>0 and failed['retry_calls']==0 and failed['partial_generated_output'] is None


def test_approval_has_no_transfer_from_dynamic88_or_cpu_ready():
    with pytest.raises(M.L.AdmissionError,match='new midstate4'):
        M.admit({}, {'authorized':True,'protocol':'pmrl1-j-dynamic88-run-v1','job_kind':'JOURNAL_POMDP_DYNAMIC88'})


def test_changed_request_order_rejected_before_call():
    clock,ts,req,diags,states=prepared();backend=Backend();req.reverse()
    with pytest.raises(M.L.AdmissionError,match='ordered four calls'):
        M.execute(plan={'scope_sha256':'synthetic'},requests=req,states=states,tasks=ts,factory=factory,
            backend=backend,emit=lambda *a,**k:None,clock=clock,deadline_ns=10**12,guard=lambda:None)
    assert backend.sent==[]


def test_actual_observer_deltas_from_decision_and_semantic_unknown():
    clock=Clock();start=clock.stamp();token=clock.stamp();text=clock.stamp()
    result=M.first_output_deltas(start,{'passive_output_observer':{'events':{
        'first_generated_token':token,'first_nonempty_decoded_text':text}}})
    assert 0<result['decision_to_first_generated_token_ns']<result['decision_to_first_nonempty_decoded_text_ns']
    assert result['decision_to_first_non_special_token_ns'] is None
    assert result['client_ttft_ns'] is result['useful_text_ttft_ns'] is None
