"""B30-FINAL Part A: stable-kinship MP recovery -- implementation blocker.

Covers: primary MP unchanged (same-owner/strict-past/exact-lineage
candidate construction is untouched by this lane, since no candidate is
added), basic_info isolation, MP_PREFERENCE absence, and the core claim
this blocker exists to prevent -- narrative_marker_absent must never be
read as a confirmed-stable signal, and B29's 132-row family_relationship
proposal must never be treated as 132 adopted MP candidates.
"""

import inspect
import json
from pathlib import Path

import pytest

from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import enumerate_targets
from metacom_pm.paper1.features import b30_stable_kinship_mp_blocker as blocker_module
from metacom_pm.paper1.features.b30_stable_kinship_mp_blocker import (
    BLOCKER_ID,
    build_stable_kinship_mp_blocker_report,
    write_stable_kinship_mp_blocker_manifest,
)
from metacom_pm.paper1.features.mp_extraction_audit import primary_compiler_hits

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return build_sanitized_runtime_users(load_raw_users(EVO_PATH))


@pytest.fixture(scope="module")
def real_targets(real_users):
    return enumerate_targets(real_users)


@pytest.fixture(scope="module")
def report(real_users, real_targets):
    return build_stable_kinship_mp_blocker_report(real_users, real_targets, EVO_PATH)


def test_status_is_a_real_implementation_blocker(report):
    assert report["status"] == "IMPLEMENTATION_BLOCKER_RESEARCHER_DECISION_REQUIRED"
    assert report["blocker_id"] == BLOCKER_ID
    assert report["outcome_calls"] == 0


def test_primary_mp_candidate_pool_is_unchanged_same_owner_strict_past(report, real_users):
    # No candidate is added by this blocker: recomputed primary-compiler
    # count must match the production compiler exactly (3 unique / 3 owners,
    # each traceable to an exact session_id/turn.idx -- same-owner and
    # strict-past provenance are properties of the untouched compiler).
    hits = primary_compiler_hits(real_users)
    assert report["primary_mp_unchanged"]["unique_hit_count"] == len(hits) == 3
    owners = {h.owner_id for h in hits}
    assert len(owners) == 3


def test_action_taken_this_round_declares_no_modification(report):
    assert "none" in report["action_taken_this_round"].lower()
    assert "3 unique / 3 owners" in report["action_taken_this_round"]


def test_no_synthetic_rescue_no_basic_info_no_mp_preference_no_me_expansion(report):
    assert report["no_synthetic_rescue"] is True
    assert report["no_basic_info"] is True
    assert report["no_mp_preference"] is True
    assert report["no_me_cross_turn_expansion"] is True


def test_basic_info_never_read_by_this_module_source():
    # structural check, same technique test_paper1_mp_extraction_audit.py
    # already uses for its own module -- this blocker never reads basic_info
    # (dataset-author persona metadata) at all, directly or indirectly. The
    # module's own "no_basic_info" negation flag legitimately contains the
    # substring "basic_info", so this checks for an actual read path
    # (the sole reader function, or an import of the ontology-B module)
    # rather than a bare substring match.
    source = inspect.getsource(blocker_module)
    assert "_load_raw_basic_info_only" not in source
    assert "mp_source_ontology_audit" not in source


def test_report_json_never_leaks_basic_info_persona_fields(report):
    rendered = json.dumps(report)
    # basic_info fields per mp_source_ontology_audit's ontology B row --
    # none of these are legitimate MP content and must never appear as
    # values sourced from this blocker (the field names may appear only
    # inside the m2_packet_conflict_note prose, never as structured data).
    for forbidden_value_marker in ("nationality", "nationality:", '"job":'):
        assert forbidden_value_marker not in rendered


def test_mp_preference_appears_only_as_an_explicit_negation(report):
    rendered = json.dumps(report)
    assert "MP_PREFERENCE" not in rendered
    assert "response_preference_history" not in rendered


def test_narrative_marker_absent_is_never_treated_as_confirmed_stable(report):
    b21 = report["prior_findings_confirming_no_rule_exists"]["B21_mp_extraction_audit"]
    b29 = report["prior_findings_confirming_no_rule_exists"]["B29_candidate_definition_decision_surface"]
    assert b21["mechanical_precision_first_rule_available"] is False
    # the weak-signal note itself must explicitly disclaim marker-absent as
    # "confirmed stable"
    note = b29["narrative_marker_note"]
    assert "never" in note.lower()
    assert "confirmed stable" in note.lower()


def test_132_row_proposal_is_explicitly_not_adopted_as_formal_coverage(report):
    justification = report["why_132_row_proposal_not_directly_adoptable"]
    assert "132" in justification
    assert "not formal MP coverage" in justification or "not formal mp coverage" in justification.lower()


def test_missing_exact_rule_and_affected_scope_are_populated(report):
    assert "family_relationship" in report["missing_exact_rule"] or "relationship" in report["missing_exact_rule"]
    assert report["affected"]["head"] == "MP"
    assert "RQ2" in report["affected"]["RQ"]


def test_minimal_alternatives_has_at_least_three_substantive_options(report):
    alternatives = report["minimal_alternatives"]
    assert len(alternatives) >= 3
    for alt in alternatives:
        assert isinstance(alt, str) and len(alt) > 40


def test_m2_packet_conflict_is_reported_not_silently_resolved(report):
    note = report["m2_packet_conflict_note"]
    assert "authorized stable-kinship MP rebuild" in note
    assert "conflict" in note.lower()


def test_write_manifest_round_trips(report, tmp_path):
    path = write_stable_kinship_mp_blocker_manifest(report, tmp_path)
    assert path.exists()
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded == report


def test_report_is_deterministic_across_repeated_builds(real_users, real_targets):
    first = build_stable_kinship_mp_blocker_report(real_users, real_targets, EVO_PATH)
    second = build_stable_kinship_mp_blocker_report(real_users, real_targets, EVO_PATH)
    assert first == second
