"""CPU tests for the G4 context layer and evidence-state v2 behaviour (no model)."""
from metacom_pm.rl1v3.semcap import g4_context as G
from metacom_pm.rl1v3.semcap import identity as I
from metacom_pm.rl1v3.semcap import evidence_state as E
from metacom_pm.rl1v3.semcap import agent_skill as A

EV = [dict(evidence_id='H3.1', speaker='seeker', text='We argued last night. Maybe we talk after dinner.', reported_at='2024-10-10', origin='actually_read_history'),
      dict(evidence_id='H3.2', speaker='supporter', text='I went through the same with my husband.', reported_at='2024-10-10', origin='actually_read_history'),
      dict(evidence_id='X1', speaker='seeker', text='My boss fired me.', reported_at='2023-01-01', origin='actually_read_history', situation=I.EXTERNAL_CASE),
      dict(evidence_id='C0', speaker='supporter', text='Hi, how are you?', reported_at='2024-10-15', origin='current_visible')]
STATE = dict(situation=I.UNKNOWN_SOURCE, evidence=EV, current_date='2024-10-15', user_turn='I need to talk.')


def test_records_carry_report_time_speaker_and_external_isolation():
    txt = G.render_records(EV, I.UNKNOWN_SOURCE, '2024-10-15')
    assert '[H3.1] (session reported 2024-10-10; current user)' in txt
    assert '[H3.2] (session reported 2024-10-10; earlier supporter (identity not established))' in txt
    assert '[X1] (session reported 2023-01-01; help-seeker in an external example (not the current user))' in txt
    assert 'Current conversation date: 2024-10-15.' in txt and 'refer to that report date' in txt
    rec = G.memory_record(EV[2], I.UNKNOWN_SOURCE)
    assert rec['is_current_user'] is False and rec['situation'] == I.EXTERNAL_CASE


def test_generator_messages_never_native_assistant():
    msgs = G.generator_messages('BASE.', STATE, block='Checked statements: x')
    assert [m['role'] for m in msgs] == ['system', 'user', 'user'] and msgs[-1]['content'] == 'I need to talk.'
    assert 'not established' in msgs[0]['content'] and 'Checked statements' in msgs[1]['content']
    assert 'CHECK:' in G.generator_messages('BASE.', STATE, tool=True)[0]['content']


def test_parse_claims_enumerates_ids_and_rejects_illegal():
    text = ('thought\nCLAIM: The user talked with the partner after dinner. || EVIDENCE: H3.1, H9.9 || SUBJECT: user || TIME: as_of_latest_evidence\n'
            'CLAIM: The user went through the same. || EVIDENCE: Z1 || SUBJECT: user || TIME: at_report_time')
    clean, leaked = G.clean_output(text)
    assert leaked and clean.startswith('CLAIM:')
    claims, rejects = G.parse_claims(clean, 'CLAIM', G.allowed_ids(EV), 3)
    assert len(claims) == 1 and claims[0]['evidence_ids'] == ['H3.1'] and claims[0]['dropped_illegal_ids'] == ['H9.9']
    assert rejects[0]['reason'] == 'no legal evidence id'
    assert G.wants_check('CHECK: x || EVIDENCE: C0') and not G.wants_check('Hi there. CHECK: x')


def test_disagreement_conflict_vs_change_over_time():
    same = E.disagreement([dict(evidence_id='a', session=1, judgement='supported'), dict(evidence_id='b', session=1, judgement='contradicted')])
    assert same['kind'] == 'conflict'
    later = E.disagreement([dict(evidence_id='a', session=1, judgement='supported'), dict(evidence_id='b', session=2, judgement='contradicted')])
    assert later['kind'] == 'cross_session_difference' and later['later_side'] == 'contradicting'
    assert E.disagreement([dict(evidence_id='a', session=1, judgement='supported')]) is None
    note = A.generator_note({'The user enjoys running.': dict(judgement='contradicted', evidence_ids=['a', 'b'], conflict=later)})
    assert 'change over time or a conflict between reports' in note


class Stub:
    def __init__(self): self.seen = []
    def __call__(self, items, claim, subject=None, time_scope=None, per_item=False):
        self.seen.append([i['evidence_id'] for i in items])
        return dict(skill='INSPECT_CLAIM', claim=claim, judgement='supported', evidence_ids=[i['evidence_id'] for i in items],
                    conflict=None, probabilities=None, per_item=None, cost=dict(model_calls=1, llm_calls=0, seconds=0.0))


def test_mixed_external_items_are_isolated_per_item():
    st = Stub(); sk = A.InspectClaimSkill(st, I.UNKNOWN_SOURCE)
    act = dict(action='INSPECT_CLAIM', claim='The user was fired.', evidence_ids=['X1', 'H3.1'], subject='user', time_scope='as_of_latest_evidence')
    r, wm, t = sk.invoke(EV, act, {})
    assert st.seen == [['H3.1']] and r['excluded_external_ids'] == ['X1']
    r2, wm2, _ = sk.invoke(EV, dict(act, evidence_ids=['X1']), {})
    assert r2['judgement'] == E.UNPROCESSED and wm2 == {}
