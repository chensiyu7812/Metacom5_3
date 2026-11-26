from copy import deepcopy
import pytest
from metacom_pm.rl1v3.journal.event_understanding import inspect


def source():
    return [dict(evidence_id='C1',text="She might visit tomorrow; she has not arrived yet.",speaker='seeker',
                 reported_at='2026-11-27',origin='current_visible')]


def test_cues_are_located_but_do_not_assert_event_occurrence():
    s=source();r=inspect(s)
    assert r['action_stage']==r['factuality']==r['event_time']=='unknown'
    assert all(s[0]['text'][c['start_char']:c['end_char']]==c['quote'] for c in r['surface_cues'])
    assert r['evidence'][0]['speaker']=='seeker' and r['formal_reward'] is None


def test_gold_and_unread_sources_rejected():
    s=source()
    with pytest.raises(ValueError):inspect(s,evidence_ids=['H99.T1'])
    s[0]['gold']='arrived'
    with pytest.raises(ValueError):inspect(s)


def test_duplicate_id_does_not_silently_pick_wrong_speaker():
    s=source();other=deepcopy(s[0]);other['speaker']='supporter'
    with pytest.raises(ValueError):inspect(s+[other])


def test_model_support_is_not_semantic_qualification():
    class BadModel:
        def score(self,premises,hypotheses):return [dict(verdict='supported')]
    r=inspect(source(),'The supporter has arrived.',model=BadModel())
    assert r['entailment_assistance']['verdict']=='supported'
    assert r['semantic_qualified'] is False and r['formal_reward'] is None
