"""CPU tests for evidence-state labels, metrics, revision and the INSPECT_CLAIM skill (stub model)."""
import pytest
from metacom_pm.rl1v3.semcap import evidence_state as E
from metacom_pm.rl1v3.semcap import agent_skill as A
from metacom_pm.rl1v3.semcap import identity as I


def test_head_mapping_and_render():
    assert E.HEAD == {0: 'contradicted', 1: 'supported', 2: 'not_established'}
    one = E.render([dict(speaker='seeker', text='I will  call him tomorrow.')])
    assert one == 'The user said: "I will call him tomorrow."'
    two = E.render([dict(speaker='seeker', text='I will call him.', session=1),
                    dict(speaker='supporter', text='Good luck.', session=2)])
    assert two.startswith('Sessions are listed in chronological order.') and 'In session 2, the supporter said' in two


def test_metrics_counts_unprocessed_and_rates():
    g = ['supported', 'not_established', 'not_established', 'contradicted']
    p = ['supported', 'contradicted', E.UNPROCESSED, 'not_established']
    m = E.metrics(g, p)
    assert m['unprocessed'] == 1 and m['not_established_as_contradicted'] == [1, 2]
    assert m['contradicted_missed'] == [1, 1] and m['per_class']['supported']['recall'] == 1.0


class Stub:
    """Deterministic stand-in: supported if 'did' appears, contradicted if "didn't", else N."""
    def __call__(self, items, claim, subject=None, time_scope=None, per_item=False):
        def one(t):
            return 'contradicted' if "didn't" in t else 'supported' if ' did ' in f' {t} ' else 'not_established'
        js = [one(i['text']) for i in items]
        j = 'contradicted' if 'contradicted' in js else 'supported' if 'supported' in js else 'not_established'
        conflict = None
        if per_item and {'supported', 'contradicted'} <= set(js):
            conflict = dict(supporting=[i['evidence_id'] for i, x in zip(items, js) if x == 'supported'],
                            contradicting=[i['evidence_id'] for i, x in zip(items, js) if x == 'contradicted'])
        return dict(skill='INSPECT_CLAIM', claim=claim, judgement=j, evidence_ids=[i['evidence_id'] for i in items],
                    conflict=conflict, probabilities=None, per_item=None, cost=dict(model_calls=1, llm_calls=0, seconds=0.0))


VIS = [dict(evidence_id='H1', speaker='seeker', text='I plan to talk to my manager.', reported_at='2024-01-01', origin='actually_read_history'),
       dict(evidence_id='H2', speaker='seeker', text='I did talk to him on Friday.', reported_at='2024-01-08', origin='actually_read_history'),
       dict(evidence_id='C1', speaker='seeker', text="Honestly I didn't talk to him.", reported_at='2024-01-09', origin='current_visible')]


def act(ids, claim='The user talked to their manager.'):
    return dict(action='INSPECT_CLAIM', claim=claim, evidence_ids=ids, subject='user', time_scope='as_of_latest_evidence')


def test_skill_revision_conflict_and_unread_refusal():
    sk = A.InspectClaimSkill(Stub(), I.IMPORTED_HUMAN)
    r1, wm, t1 = sk.invoke(VIS, act(['H1']), {})
    assert r1['judgement'] == 'not_established' and t1['before'] is None
    r2, wm, t2 = sk.invoke(VIS, act(['H1', 'H2']), wm)
    assert t2['transition'] == 'not_established->supported'
    r3, wm, t3 = sk.invoke(VIS, act(['H1', 'H2', 'C1']), wm)
    assert t3['conflict'] == dict(supporting=['H2'], contradicting=['C1'])
    entry = wm['The user talked to their manager.']
    assert len(entry['history']) == 3  # nothing overwritten
    with pytest.raises(ValueError):
        sk.invoke(VIS, act(['H9']), wm)
    note = A.generator_note(wm)
    assert 'conflict' in note and 'not verified facts' in note


def test_sessions_are_host_ordered():
    items = A.evidence_items(VIS, ['C1', 'H2', 'H1'])
    assert [i['evidence_id'] for i in items] == ['H1', 'H2', 'C1'] and [i['session'] for i in items] == [1, 2, 3]


def test_external_case_never_user_evidence():
    sk = A.InspectClaimSkill(Stub(), I.EXTERNAL_CASE)
    r, wm, t = sk.invoke(VIS, act(['H2']), {})
    assert r['judgement'] == E.UNPROCESSED and wm == {} and t['cost']['model_calls'] == 0


def test_action_schema():
    with pytest.raises(ValueError):
        A.parse_action(dict(act(['H1']), subject='seeker'), {'H1'})
    with pytest.raises(ValueError):
        A.parse_action(dict(act(['H1']), claim='two\nlines'), {'H1'})
