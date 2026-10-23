"""B29.1: MP source ontology decision surface (A conversation-derived vs B persistent-profile-store)."""

import ast
import inspect
from pathlib import Path

import pytest

from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import enumerate_targets
from metacom_pm.paper1.features import mp_source_ontology_audit as _module
from metacom_pm.paper1.features.mp_source_ontology_audit import (
    ONTOLOGY_A_CONVERSATION_DERIVED,
    ONTOLOGY_B_PERSISTENT_PROFILE_STORE_PROPOSED,
    RAW_BASIC_INFO_FIELDS,
    STATUS_PRIMARY_MP_CURRENT,
    STATUS_PROPOSED_NOT_ADOPTED,
    _load_raw_basic_info_only,
    build_mp_source_ontology_report,
    build_mp_source_ontology_rows,
)

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


@pytest.fixture(scope="module")
def real_users():
    return build_sanitized_runtime_users(load_raw_users(EVO_PATH))


@pytest.fixture(scope="module")
def real_targets(real_users):
    return enumerate_targets(real_users)


def test_ontology_a_matches_the_real_unchanged_primary_mp(real_users, real_targets):
    row_a, _row_b = build_mp_source_ontology_rows(real_users, real_targets, EVO_PATH)
    assert row_a.ontology == ONTOLOGY_A_CONVERSATION_DERIVED
    assert row_a.status == STATUS_PRIMARY_MP_CURRENT
    assert row_a.unique_candidate_count == 3
    assert row_a.owners_with_candidates == 3
    assert row_a.target_edges == 214
    assert row_a.target_coverage_fraction == pytest.approx(0.13493064312736444)
    assert row_a.strict_past_availability_time_provable is True


def test_ontology_b_is_proposed_not_adopted_with_correct_raw_counts(real_users, real_targets):
    _row_a, row_b = build_mp_source_ontology_rows(real_users, real_targets, EVO_PATH)
    assert row_b.ontology == ONTOLOGY_B_PERSISTENT_PROFILE_STORE_PROPOSED
    assert row_b.status == STATUS_PROPOSED_NOT_ADOPTED
    assert row_b.owners_with_candidates == 18
    assert row_b.owners_total == 18
    assert row_b.unique_candidate_count == 18 * len(RAW_BASIC_INFO_FIELDS)
    assert row_b.strict_past_availability_time_provable is False
    assert set(row_b.fields_missing_versioning_or_effective_time) == set(RAW_BASIC_INFO_FIELDS)


def test_ontology_b_coverage_is_flagged_vacuous_not_a_real_temporal_claim(real_users, real_targets):
    _row_a, row_b = build_mp_source_ontology_rows(real_users, real_targets, EVO_PATH)
    assert row_b.target_coverage_fraction == 1.0
    note = row_b.coverage_semantics_note.lower()
    assert "vacuous" in note or "trivial" in note
    assert "never" in note or "must never" in note


def test_ontology_b_reports_high_privileged_risk_citing_official_harness_audit(real_users, real_targets):
    _row_a, row_b = build_mp_source_ontology_rows(real_users, real_targets, EVO_PATH)
    risk = row_b.future_gold_source_privileged_risk
    assert risk.startswith("HIGH")
    assert "b28r" in risk.lower() or "official es-memeval harness" in risk.lower()


def test_ontology_a_reports_low_privileged_risk(real_users, real_targets):
    row_a, _row_b = build_mp_source_ontology_rows(real_users, real_targets, EVO_PATH)
    assert row_a.future_gold_source_privileged_risk.startswith("LOW")


def test_raw_basic_info_reader_reads_exactly_the_seven_fields():
    raw_basic_info = _load_raw_basic_info_only(EVO_PATH)
    assert len(raw_basic_info) == 18
    for owner_id, fields in raw_basic_info.items():
        assert set(fields.keys()) == set(RAW_BASIC_INFO_FIELDS)
        assert all(v not in (None, "") for v in fields.values())


def test_load_raw_basic_info_only_is_the_sole_basic_info_reader_in_this_module():
    tree = ast.parse(inspect.getsource(_module))
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if node.slice.value == "basic_info":
                hits.append(node)
    # every subscript access to "basic_info" must live textually inside
    # _load_raw_basic_info_only -- checked indirectly by requiring exactly
    # one such access in the whole module (the raw_user["basic_info"] read).
    assert len(hits) == 1


def test_report_never_wires_ontology_b_into_primary_mp(real_users, real_targets):
    report = build_mp_source_ontology_report(real_users, real_targets, EVO_PATH)
    assert report["outcome_calls"] == 0
    note = report["note"].lower()
    assert "never wired" in note or "never" in note
    assert "memory/mp.py" in report["note"]


def test_report_is_json_serializable_and_zero_outcome(real_users, real_targets):
    import json

    report = build_mp_source_ontology_report(real_users, real_targets, EVO_PATH)
    rendered = json.dumps(report)
    assert report["outcome_calls"] == 0
    for token in ("\"gold\"", "\"answer\":", "\"evidence\":", "\"observation\":"):
        assert token not in rendered.lower()


def test_module_never_imports_forbidden_raw_loaders_beyond_its_own_basic_info_reader():
    # The candidates/ and other memory/ modules must never import this
    # module (it is the one legitimate place basic_info is read) -- checked
    # from the isolation test file. Here we confirm this module itself
    # never imports the raw es_memeval evaluator loader or the materializer
    # (it builds its own tiny, scoped raw reader instead).
    tree = ast.parse(inspect.getsource(_module))
    forbidden = ("metacom_pm.paper1.data.es_memeval", "metacom_pm.paper1.data.materializer")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in forbidden:
            raise AssertionError(f"mp_source_ontology_audit.py imports {node.module}")
