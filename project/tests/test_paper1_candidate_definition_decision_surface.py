"""B29.4: MP/ME candidate-definition decision surface."""

import json
from pathlib import Path

import pytest

from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import enumerate_targets
from metacom_pm.paper1.features.candidate_definition_decision_surface import (
    RESEARCHER_DECISIONS_REQUIRED,
    build_candidate_definition_decision_surface,
    write_candidate_definition_decision_surface,
)

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return build_sanitized_runtime_users(load_raw_users(EVO_PATH))


@pytest.fixture(scope="module")
def real_targets(real_users):
    return enumerate_targets(real_users)


def test_surface_combines_all_three_sub_audits(real_users, real_targets):
    report = build_candidate_definition_decision_surface(real_users, real_targets, EVO_PATH)
    assert "mp_source_ontology" in report
    assert "mp_conversation_proposal" in report
    assert "me_cross_turn_proposal" in report
    assert len(report["mp_source_ontology"]["ontologies"]) == 2
    assert report["mp_conversation_proposal_row_count"] == 139
    assert report["me_cross_turn_proposal_row_count"] == 1


def test_no_winner_no_pass_fail_no_minimum_n_no_synthetic_rescue_notes_present(real_users, real_targets):
    report = build_candidate_definition_decision_surface(real_users, real_targets, EVO_PATH)
    assert "no winner" in report["no_winner_note"].lower()
    assert "pass/fail" in report["no_pass_fail_note"].lower()
    assert "minimum-n" in report["no_minimum_n_note"].lower()
    assert "rescue" in report["no_synthetic_rescue_note"].lower()


def test_researcher_decisions_required_is_a_real_nonempty_list(real_users, real_targets):
    report = build_candidate_definition_decision_surface(real_users, real_targets, EVO_PATH)
    assert report["researcher_decisions_required"] == list(RESEARCHER_DECISIONS_REQUIRED)
    assert len(report["researcher_decisions_required"]) >= 3
    for item in report["researcher_decisions_required"]:
        assert isinstance(item, str) and len(item) > 20


def test_status_declares_no_winner_not_a_freeze(real_users, real_targets):
    report = build_candidate_definition_decision_surface(real_users, real_targets, EVO_PATH)
    assert report["status"] == "B29_CANDIDATE_DEFINITION_DECISION_SURFACE_NO_WINNER"
    assert report["outcome_calls"] == 0


def test_no_field_declares_a_pass_fail_verdict(real_users, real_targets):
    report = build_candidate_definition_decision_surface(real_users, real_targets, EVO_PATH)
    rendered = json.dumps(report)
    assert '"PASS"' not in rendered
    assert '"FAIL"' not in rendered
    forbidden_keys = {"winner", "selected_ontology", "recommended_ontology", "best_ontology"}
    assert forbidden_keys.isdisjoint(report.keys())


def test_primary_mp_and_me_counts_unaffected_by_this_surface(real_users, real_targets):
    report = build_candidate_definition_decision_surface(real_users, real_targets, EVO_PATH)
    mp_a = report["mp_source_ontology"]["ontologies"][0]
    assert mp_a["unique_candidate_count"] == 3
    assert mp_a["owners_with_candidates"] == 3
    me_primary = report["me_cross_turn_proposal"]["primary_me_unchanged"]
    assert me_primary["unique_candidate_count"] == 3
    assert me_primary["owners_with_candidates"] == 2


def test_report_is_zero_outcome_throughout(real_users, real_targets):
    report = build_candidate_definition_decision_surface(real_users, real_targets, EVO_PATH)
    assert report["outcome_calls"] == 0
    rendered = json.dumps(report).lower()
    for token in ("\"gold\"", "\"answer\":", "\"evidence\":", "\"observation\":"):
        assert token not in rendered


def test_write_manifest_roundtrip(tmp_path, real_users, real_targets):
    report = build_candidate_definition_decision_surface(real_users, real_targets, EVO_PATH)
    path = write_candidate_definition_decision_surface(report, tmp_path)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert written["status"] == report["status"]
    assert written["outcome_calls"] == 0
