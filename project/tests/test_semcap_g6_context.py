"""CPU tests for the G6 interface v2 (no model)."""
from metacom_pm.rl1v3.semcap import g6_context as G6
from metacom_pm.rl1v3.semcap import g4_context as X
from metacom_pm.rl1v3.semcap import identity as I

EV = [dict(evidence_id='C0', speaker='seeker', text='We argued about money.', reported_at=None, origin='current_visible'),
      dict(evidence_id='C1', speaker='supporter', text='Have you talked to him since?', reported_at=None, origin='current_visible')]
ST = dict(situation=I.IMPORTED_HUMAN, evidence=EV, current_date=None, user_turn='Not yet, I am scared.')


def test_u0_is_enumerable_for_checks_but_not_in_generator_records():
    ev = G6.with_u0(ST)
    assert ev[-1]['evidence_id'] == 'U0' and ev[-1]['speaker'] == 'seeker'
    msgs = G6.risk_messages(ST)
    assert '[U0] (current conversation; current user) Not yet, I am scared.' in msgs[1]['content']
    assert 'U0' in msgs[1]['content'].split('Use only these record IDs:')[1] and 'NONE' in msgs[1]['content']
    gm = X.generator_messages('BASE.', ST)
    assert '[U0]' not in gm[1]['content'] and gm[-1]['content'] == 'Not yet, I am scared.'


def test_question_answer_linking_both_directions():
    ev = G6.with_u0(ST)
    ids, added = G6.link_qa(ev, ['U0'])
    assert ids == ['C1', 'U0'] and added == ['C1']
    ids, added = G6.link_qa(ev, ['C1'])
    assert ids == ['C1', 'U0'] and added == ['U0']
    ids, added = G6.link_qa(ev, ['C0'])
    assert ids == ['C0'] and added == []


def test_none_and_parse():
    assert G6.is_none('NONE') and G6.is_none('None.') and not G6.is_none('RISK: x || EVIDENCE: U0')
    claims, rej = G6.parse_risk('RISK: The user has talked to him. || EVIDENCE: C1, U0, H9.9 || SUBJECT: user || TIME: as_of_latest_evidence',
                                X.allowed_ids(G6.with_u0(ST)))
    assert claims[0]['evidence_ids'] == ['C1', 'U0'] and claims[0]['dropped_illegal_ids'] == ['H9.9'] and not rej


def test_p_and_bprime_blocks_share_claims_and_ids():
    claims = [dict(claim='The user has talked to him.', evidence_ids=['C1', 'U0'])]
    p = G6.claims_block(claims)
    b = G6.claims_block(claims, [dict(judgement='contradicted', conflict=None)])
    assert '"The user has talked to him." (records: C1, U0)' in p and '"The user has talked to him." (records: C1, U0)' in b
    assert 'check result' not in p and 'contradicted by these records' in b
    x = G6.claims_block(claims, [dict(judgement='supported', conflict=dict(kind='cross_session_difference'))])
    assert 'may be a change over time or a conflict between reports' in x
    assert G6.claims_block([]) is None
