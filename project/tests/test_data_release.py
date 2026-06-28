from pathlib import Path
from metacom_pm.audit import audit_synthetic_release
from metacom_pm.evoemo import load_evoemo,build_evo_memory
ROOT=Path(__file__).resolve().parents[1]

def test_packaged_synthetic_audit_passes(tmp_path):
    report=audit_synthetic_release(ROOT/'data/synthetic/runtime_states.jsonl',ROOT/'data/synthetic/memory_backend.jsonl',tmp_path/'audit.json')
    assert report['status']=='PASS'
    assert report['counts']['states']==192
    assert report['counts']['runtime_cards']==1728

def test_evoemo_is_frozen_18_users_401_sessions_34_scenarios():
    users=load_evoemo(ROOT/'data/external/evo_emo.json')
    assert len(users)==18
    assert sum(len(x.get('dialog_history') or []) for x in users)==401
    assert sum(len(x.get('subsequent_topics') or []) for x in users)==34

def test_evo_memory_ignores_gold_event_and_observation_annotations():
    user=load_evoemo(ROOT/'data/external/evo_emo.json')[0]
    items,_=build_evo_memory(user)
    combined=' '.join(x.text for x in items)
    # All items are derived from basic_info, session summaries, or seeker turns.
    assert items
    for session in user.get('dialog_history') or []:
        for obs in session.get('observation') or []:
            content=str(obs.get('content') or '').strip()
            if content and content not in ' '.join(str(t.get('content') or '') for t in session.get('dialogue') or []):
                assert content not in combined
