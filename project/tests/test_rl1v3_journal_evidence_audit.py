"""Evidence-aware QA scope and real-source regression checks, no model output."""
import json
from pathlib import Path
import pytest
from metacom_pm.rl1v3.journal.evidence_audit import parse_question_time,atom_delivery,aggregate_evidence_status


def test_date_parser_preserves_typo_and_does_not_invent_group_cutoff():
    text='As of Jenuary 5, 2025, what has the user been doing?'
    p=parse_question_time(text)
    assert p['upper']=='2025-01-05' and p['spelling_alias']=='Jenuary→January'
    assert 'Jenuary' in text
    assert parse_question_time('What does she do currently?')['upper'] is None


def test_month_is_interval_not_arbitrary_precise_cutoff():
    p=parse_question_time('What happened by December 2024?')
    assert p['lower']=='2024-12-01' and p['upper']=='2024-12-31'
    assert p['semantics']=='date_precision_ambiguous'


def test_delivery_requires_complete_reviewed_group_not_lexical_hit():
    groups=[['s1:3','s2:5'],['s3:7']]
    assert not atom_delivery(groups,{'s1'})
    assert atom_delivery(groups,{'s1','s2'})
    assert atom_delivery(groups,{'s3'})
    assert not atom_delivery([] ,{'anything'})


def test_uncertain_reference_is_never_generator_failure():
    atoms=[dict(required=True,status_end_history='unknown',status_explicit_date='unknown',dp_delivered=False,dp_delivered_strict=False)]
    assert aggregate_evidence_status(atoms,'dp')=='reference_pending_or_scope_conflict'
    atoms[0].update(status_end_history='supported',status_explicit_date='supported',dp_delivered=True,dp_delivered_strict=True)
    atoms.append(dict(required=False,status_end_history='unknown',status_explicit_date='unknown',dp_delivered=False,dp_delivered_strict=False))
    assert aggregate_evidence_status(atoms,'dp')=='documented_atoms_covered'


def load_private():
    p=Path('/opt/tokkio-data0/tokkio_runs/pmrl1-j-evidence-20261125/memory_audit/v2/ATOMS_PRIVATE.jsonl')
    if not p.exists():pytest.skip('local private development audit absent')
    return [json.loads(x) for x in p.read_text().splitlines()]


def test_actual_missing_atoms_have_source_grounding_without_gold_as_source():
    rows=load_private()
    incomplete=[r for r in rows if r['dp_evidence_end_history']=='evidence_insufficient']
    assert incomplete
    for row in incomplete:
        missing=[a for a in row['atoms'] if a['required'] and not a['dp_delivered']]
        assert missing
        for atom in missing:
            assert any(e['relation']=='support' and e['temporal_legal_strict'] for e in atom['source_evidence'])
            assert all(e['exact_quote'] and e['source_file_sha256'] for e in atom['source_evidence'])


def test_actual_30_spans_match_source_and_smoke_dates():
    rows=load_private();assert len(rows)==30
    root=Path(__file__).resolve().parents[2]
    raw=json.loads((root/'project/data/external/evo_emo.json').read_text())
    lookup={(u['id'],s['id']):s for u in raw for s in u['dialog_history']}
    for row in rows:
        for atom in row['atoms']:
            for e in atom['source_evidence']:
                t=lookup[e['owner_id'],e['session_id']]['dialogue'][e['ordinal_turn']]
                assert t['idx']==e['original_idx'] and t['role']==e['speaker']
                assert t['content'][e['start_char']:e['end_char']]==e['exact_quote']
    alias_rows=[r for r in rows if r['explicit_time']['spelling_alias']]
    assert len(alias_rows)==2
    for row in alias_rows:
        assert row['explicit_time']['spelling_alias']=='Jenuary→January'
        assert row['dp_evidence_strict_date']=='documented_atoms_covered'
        assert row['ret_future_sessions_strict']
