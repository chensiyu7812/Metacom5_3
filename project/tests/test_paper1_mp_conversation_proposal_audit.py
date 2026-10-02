"""B29.2: conversation-derived MP high-recall proposal audit."""

import json
from pathlib import Path

import pytest

from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.features.mp_conversation_proposal_audit import (
    build_mp_conversation_proposal_report,
    build_mp_conversation_proposal_rows,
    write_mp_conversation_proposal_manifest,
)
from metacom_pm.paper1.features.mp_extraction_audit import CATEGORY_PATTERNS

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return build_sanitized_runtime_users(load_raw_users(EVO_PATH))


def test_category_totals_match_the_already_grounded_b16_b21_scan(real_users):
    # Grounded, previously-verified corpus totals (script 04's build
    # report): occupation=2, family_relationship=132, residence=0,
    # study=0, diagnosis=1, durable_trait=4.
    report = build_mp_conversation_proposal_report(real_users)
    summary = report["category_summary"]
    assert summary["occupation"]["total_matches"] == 2
    assert summary["family_relationship"]["total_matches"] == 132
    assert summary["residence"]["total_matches"] == 0
    assert summary["study"]["total_matches"] == 0
    assert summary["diagnosis"]["total_matches"] == 1
    assert summary["durable_trait"]["total_matches"] == 4


def test_every_row_has_an_exact_span_that_slices_correctly(real_users):
    users_by_owner = {u.owner_id: u for u in real_users}
    rows = build_mp_conversation_proposal_rows(real_users)
    assert len(rows) == 139
    for row in rows:
        user = users_by_owner[row.owner_id]
        session = user.session_by_id(row.session_id)
        turn = next(t for t in session.turns if t.idx == row.turn_idx)
        assert turn.content[row.span_start : row.span_end] == row.exact_span_text
        assert row.span_start < row.span_end


def test_narrative_marker_present_and_absent_both_occur_for_family_relationship(real_users):
    rows = build_mp_conversation_proposal_rows(real_users)
    fam_rows = [r for r in rows if r.category == "family_relationship"]
    assert any(r.narrative_marker_present for r in fam_rows)
    assert any(not r.narrative_marker_present for r in fam_rows)


def test_narrative_marker_is_disclosed_as_weak_not_a_classifier(real_users):
    report = build_mp_conversation_proposal_report(real_users)
    note = report["narrative_marker_note"].lower()
    assert "weak" in note
    assert "not" in note and "classifier" in note
    assert "b21" in note


def test_primary_mp_reported_unchanged_and_matches_real_compiler(real_users):
    report = build_mp_conversation_proposal_report(real_users)
    assert report["primary_mp_unchanged"]["unique_candidate_count"] == 3
    assert report["primary_mp_unchanged"]["owners_with_candidates"] == 3


def test_family_relationship_132_not_conflated_with_formal_coverage(real_users):
    report = build_mp_conversation_proposal_report(real_users)
    note = report["proposal_list_is_not_formal_coverage_note"]
    assert "132" in note
    assert "not" in note.lower()
    assert report["researcher_decision_required"] is True


def test_report_is_zero_outcome_and_diagnostic_only(real_users):
    report = build_mp_conversation_proposal_report(real_users)
    assert report["outcome_calls"] == 0
    assert report["status"] == "B29_2_DIAGNOSTIC_PROPOSAL_ONLY_NOT_ADOPTED"
    rendered = json.dumps(report).lower()
    for token in ("\"gold\"", "\"answer\":", "\"evidence\":"):
        assert token not in rendered


def test_all_category_pattern_categories_are_covered():
    report = build_mp_conversation_proposal_report(
        build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    )
    assert set(report["category_summary"].keys()) == set(CATEGORY_PATTERNS.keys())


def test_manifest_write_roundtrip(tmp_path, real_users):
    rows = build_mp_conversation_proposal_rows(real_users)
    report = build_mp_conversation_proposal_report(real_users)
    paths = write_mp_conversation_proposal_manifest(rows, report, tmp_path)

    lines = paths["rows"].read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(rows)
    for line in lines:
        parsed = json.loads(line)
        assert parsed["protocol"] == "pm-paper1-mp-conversation-proposal-row-v1"

    written_report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert written_report["proposal_row_count"] == len(rows)
