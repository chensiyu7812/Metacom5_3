"""Synthetic invariants, not evidence that a language model understands."""
from copy import deepcopy
import json
import pytest
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal import gsws as S
from metacom_pm.rl1v3.journal.gsws_runtime import slots
from metacom_pm.rl1v3.journal.gsws_worker import WorkerCallBudget


def observation():
    x=dict(protocol=S.PROTOCOL,task_sha256='t',stage=0,source_scope=S.COMMON_CONTEXT,
        current_goal_context=[dict(role='seeker',text='I might visit tomorrow.')],
        evidence=[dict(evidence_id='C0',kind='current_visible',speaker='seeker',turn_index=0,
                       report_time='2026-01-01',text='I might visit tomorrow.')],
        source_time='2026-01-01',operational_context={},raw_observation_sha256='r',content_sha256='c',
        previous_state_sha256=None,previous_interpretation=None)
    x['snapshot_sha256']=object_sha256(x);return x


def claim(**kwargs):
    x=dict(text='A visit is being considered.',epistemic='reported',subject='user',stage='planned',
           event_time='tomorrow; unresolved absolute date',applicability='unresolved',evidence_ids=['C0'])
    x.update(kwargs);return x


def value(**kwargs):
    x=dict(goal_and_boundaries='Visible request only.',claims=[claim()],gaps_or_conflicts='Execution unknown.',
           response_implications='Do not assume it happened.');x.update(kwargs);return x


def accept(v):return S.accept_interpretation(json.dumps(v),'A2_GSWS',observation(),model_output_sha256='x',fixture=True)


def test_bound_state_is_not_semantic_qualification():
    good=accept(value());bad=accept(value(claims=[claim(text='The user completed the visit.',stage='performed')]))
    # Both pass the mechanical check; the wrong implication must remain a semantic failure, not rewarded.
    assert good['semantic_qualification'] is bad['semantic_qualification'] is False
    assert bad['formal_reward'] is None and good['origin']=='cpu_fixture_not_model'


@pytest.mark.parametrize('v',[value(claims=[claim(evidence_ids=['unread'])]),
    value(claims=[claim(evidence_ids=[])]),value(claims=[claim(stage='success')]),
    value(claims=[claim()]*5),dict(value(),gold='secret')])
def test_invalid_contract(v):
    with pytest.raises(ValueError):accept(v)


def test_duplicate_fields_fail():
    with pytest.raises(ValueError):S.accept_interpretation('{"notes":"a","notes":"b","evidence_ids":[]}',
        'A1_READING_NOTES',observation(),model_output_sha256='x')


def test_evaluation_field_in_projection_fails_even_if_rehashed():
    o=observation();o['gold']='hidden';o['snapshot_sha256']=object_sha256({k:v for k,v in o.items() if k!='snapshot_sha256'})
    with pytest.raises(ValueError):S.interpreter_messages(o,'A2_GSWS')


def test_stale_state_rejected():
    st=accept(value());st['interpretation']['claims'][0]['text']='changed'
    with pytest.raises(ValueError):S.shared_view(observation(),st)


def test_generator_and_interpreter_share_ids_without_hashes():
    import re
    obs=observation()
    raw=[dict(role='system',content='same G'),dict(role='user',content='obsolete hash header'),
         dict(role='user',content=obs['current_goal_context'][0]['text'])]
    st=accept(value());task=dict(turns=obs['current_goal_context'])
    for aid in (None,st):
        rendered=S.final_messages(raw,task,aid,obs)
        assert rendered[0]==raw[0] and rendered[-1]==raw[-1]
        assert 'obsolete hash header' not in str(rendered)
        assert 'C0' in rendered[1]['content']
    messages=S.interpreter_messages(obs,'A2_GSWS')
    assert 'snapshot_sha256' not in str(messages) and not re.search(r'[0-9a-f]{64}',str(messages))


def test_history_group_ids_map_to_same_verbatim_turns():
    obs=observation();obs['evidence'] += [dict(evidence_id='H3.T2',kind='historical_report',speaker='seeker',
        turn_index=2,report_time='2025-12-25',text='I plan to visit.'),dict(evidence_id='H3.T3',kind='historical_report',
        speaker='supporter',turn_index=3,report_time='2025-12-25',text='Is that decided?')]
    obs['snapshot_sha256']=object_sha256({k:v for k,v in obs.items() if k!='snapshot_sha256'})
    e=S.model_evidence(obs)
    assert len(e['history'])==1 and e['history'][0]['reported_at']=='2025-12-25'
    assert [t['id'] for t in e['history'][0]['turns']]==['H3.T2','H3.T3']
    task=dict(turns=obs['current_goal_context'])
    raw=[dict(role='system',content='G'),dict(role='user',content=task['turns'][0]['text'])]
    g=S.final_messages(raw,task,observation=obs)
    assert all(t['text'] in g[1]['content'] and t['id'] in g[1]['content'] for t in e['history'][0]['turns'])


def test_worker_budget_every_slot_and_no_retry():
    ts=[dict(task_id='a'),dict(task_id='b')];ss=slots(ts)
    b=WorkerCallBudget({t['task_id']:object_sha256(t) for t in ts},'scope',{'terminal':12,'oneshot':4,'agent':4},ss)
    for slot in ss:
        t=next(t for t in ts if t['task_id']==slot['task_id'])
        binding=dict(slot,task_sha256=object_sha256(t),scope_sha256='scope')
        if slot['arm']!='A0_RAW':b.claim(dict(role='oneshot' if slot['arm']=='A1_READING_NOTES' else 'agent',binding=binding))
        req=dict(role='terminal',binding=binding);b.claim(req)
    assert b.total==20
    with pytest.raises(ValueError):b.claim(req)
