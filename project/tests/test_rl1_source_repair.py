"""Regressions on real source chronology, stale fallback and source binding."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units
from metacom_pm.paper1.contracts import Head
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.schema import PrefixSpec,PublicTurn
from metacom_pm.rl1.source_repair import repaired_as_of_memory,validate_overlay

PROJECT=Path(__file__).resolve().parents[1]

@pytest.fixture(scope='module')
def source():
    users=load_sanitized_runtime_users(PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json')
    units=load_accepted_multi_view_units(PROJECT/'data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl',users=users)
    overlay=json.loads((PROJECT/'tests/fixtures/rl1/source_overlay_20260929_v2.json').read_text())
    return {u.owner_id:u for u in users},units,overlay

def view(source,owner,rank):
    users,units,overlay=source;u=users[owner];s=next(s for s in u.sessions if s.chronological_rank==rank)
    p=PrefixSpec(owner,s.session_id,rank,0,s.timestamp,'train',(PublicTurn('seeker','test'),))
    return repaired_as_of_memory(p,user=u,units=[x for x in units if x.owner_id==owner],token_counter=len,overlay=overlay)

def test_unsupported_refresh_never_resurrects_original(source):
    before,_=view(source,'p18',2);after,receipt=view(source,'p18',3)
    original='mp::mvu_cf220d41c423b152554bb558'
    assert original in {c.candidate_id for c in before[Head.MP]}
    assert original not in {c.candidate_id for c in after[Head.MP]}
    assert 'mp::mvu_0506ef4aa5498802b8fd7e82' in {r['candidate_id'] for r in receipt['removed']}

def test_future_relationship_loss_does_not_change_earlier_view(source):
    before,_=view(source,'p6',4);after,_=view(source,'p6',5)
    cid='mp::mvu_45d1b7d87ae9b42ac9766a87'
    assert cid in {c.candidate_id for c in before[Head.MP]}
    assert cid not in {c.candidate_id for c in after[Head.MP]}

def test_roleplay_atoms_blocked_but_full_transcript_preserved(source):
    after,receipt=view(source,'p8',6)
    assert 'ms::p8::esc995' in {c.candidate_id for c in after[Head.MS]}
    assert any(r['reason']=='ambiguous_scenario_source' for r in receipt['removed'])
    assert not any('esc995' in c.lineage.source_record_ids for h in (Head.MP,Head.ME) for c in after[h])

def test_evidence_edit_invalidates_overlay(source):
    users,units,overlay=source;bad=deepcopy(overlay)
    bad['temporal_blocks'][0]['evidence'][0]['text']='unsupported replacement'
    with pytest.raises(ValueError,match='evidence changed'):validate_overlay(bad,units=units,users=users)

def test_unit_edit_invalidates_review_binding(source):
    users,units,overlay=source;bad=deepcopy(overlay)
    bad['unit_reviews'][0]['unit_identity']='wrong'
    with pytest.raises(ValueError,match='binding changed'):validate_overlay(bad,units=units,users=users)
