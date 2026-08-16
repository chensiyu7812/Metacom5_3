"""B24: Phase-1 memory feature-readiness / identifiability audit."""

import json
from pathlib import Path

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import enumerate_targets
from metacom_pm.paper1.features.feature_readiness_audit import (
    build_feature_readiness_rows,
    summarize_feature_readiness,
    write_feature_readiness_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"


def _rows():
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    targets = enumerate_targets(users)
    return build_feature_readiness_rows(users, targets)


def test_one_row_per_head_per_memory_task_type():
    rows = _rows()
    assert len(rows) == 9  # MP/MS/ME x qa/summary/dialogue_generation
    keys = {(r.head, r.task_type) for r in rows}
    assert keys == {
        (head, task)
        for head in (Head.MP, Head.MS, Head.ME)
        for task in (TaskType.QA, TaskType.SUMMARY, TaskType.DIALOGUE_GENERATION)
    }


def test_mp_and_me_availability_counts_match_the_known_identifiability_limitation():
    rows = {(r.head, r.task_type): r for r in _rows()}
    mp_qa = rows[(Head.MP, TaskType.QA)]
    me_qa = rows[(Head.ME, TaskType.QA)]
    assert mp_qa.unique_candidate_count == 3
    assert mp_qa.owners_with_candidates == 3
    assert me_qa.unique_candidate_count == 3
    assert me_qa.owners_with_candidates == 2


def test_ms_full_coverage_is_availability_not_a_success_claim():
    rows = {(r.head, r.task_type): r for r in _rows()}
    ms_qa = rows[(Head.MS, TaskType.QA)]
    assert ms_qa.coverage_fraction == 1.0
    summary = summarize_feature_readiness(list(rows.values()))
    note = summary["ms_availability_note"].lower()
    assert "availability" in note
    assert "success" not in note or "not" in note  # never asserted as success without negation


def test_target_candidate_edges_note_present_on_every_row():
    for row in _rows():
        manifest = row.to_manifest_row()
        assert "not distinct" in manifest["target_candidate_edges_note"]


def test_dg_rows_have_na_status_for_query_dependent_axes_but_not_for_age_or_token_length():
    rows = {(r.head, r.task_type): r for r in _rows()}
    for head in (Head.MP, Head.MS, Head.ME):
        dg_row = rows[(head, TaskType.DIALOGUE_GENERATION)]
        assert dg_row.static_visible_query_present is False
        for axis_name in ("lexical_similarity", "already_visible", "retrieval_rank"):
            axis = getattr(dg_row, axis_name)
            assert axis.readiness_status == "N_A_NO_STATIC_QUERY_PRE_GENERATION"
            assert axis.computable is False
        # age/token_length/candidate_count are not query-dependent -- still computable for MS/DG
        if head is Head.MS:
            assert dg_row.relative_age_days.computable is True
            assert dg_row.token_length.computable is True


def test_qa_and_summary_rows_have_a_static_visible_query():
    rows = {(r.head, r.task_type): r for r in _rows()}
    for head in (Head.MP, Head.MS, Head.ME):
        for task in (TaskType.QA, TaskType.SUMMARY):
            assert rows[(head, task)].static_visible_query_present is True


def test_already_visible_is_zero_variance_wherever_candidates_exist():
    # Grounded corpus finding: the 0.6 lexical-overlap already-visible
    # threshold is never crossed anywhere in the current corpus.
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    expected = {"MP/qa", "MP/summary", "MS/qa", "MS/summary", "ME/qa", "ME/summary"}
    assert set(summary["already_visible_zero_variance_head_tasks"]) == expected
    for row in rows:
        if row.task_type is TaskType.DIALOGUE_GENERATION:
            continue
        if row.already_visible.computable:
            assert row.already_visible.readiness_status == "ZERO_VARIANCE_NOT_FEATURE_READY"
            assert row.already_visible.zero_variance is True


def test_ms_retrieval_rank_and_lexical_overlap_have_real_variance():
    # Contrast case: MS (up to 33 candidates/target) is NOT zero-variance for
    # rank/lexical overlap, unlike MP/ME's near-degenerate 1-2 candidate pools.
    rows = {(r.head, r.task_type): r for r in _rows()}
    ms_qa = rows[(Head.MS, TaskType.QA)]
    assert ms_qa.retrieval_rank.readiness_status == "COMPUTABLE_WITH_VARIANCE"
    assert ms_qa.retrieval_rank.distinct_value_count > 1
    assert ms_qa.lexical_similarity.readiness_status == "COMPUTABLE_WITH_VARIANCE"
    assert ms_qa.lexical_similarity.distinct_value_count > 1


def test_embedding_similarity_always_reported_not_implemented():
    for row in _rows():
        manifest = row.to_manifest_row()
        assert manifest["embedding_similarity"]["readiness_status"] == "NOT_IMPLEMENTED"
        assert manifest["embedding_similarity"]["computable"] is False


def test_no_missingness_for_age_or_token_length_where_candidates_exist():
    for row in _rows():
        if row.token_length.present_values > 0:
            assert row.token_length.missingness_fraction == 0.0
        if row.relative_age_days.present_values > 0:
            assert row.relative_age_days.missingness_fraction == 0.0


def test_report_never_declares_a_pass_fail_verdict_or_selects_freeze_parameters():
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    assert summary["no_verdict_policy"]["per_head_pass_fail"] == "NOT_DECLARED_THIS_ROUND"
    assert summary["no_verdict_policy"]["minimum_n_gate"] is None
    frozen = summary["unselected_freeze_decisions"]
    assert frozen["n_outer_folds"] is None
    assert frozen["outer_fold_seed"] is None
    assert frozen["memory_top_k"] is None
    assert frozen["memory_token_cap"] is None
    rendered = json.dumps(summary).upper()
    assert '"PASS"' not in rendered
    assert '"FAIL"' not in rendered


def test_report_never_widens_mp_or_loosens_me_and_never_reads_gold_fields():
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    assert "family_relationship" in summary["mp_identifiability_limitation"]["note"].lower()
    assert "not expanded" in summary["mp_identifiability_limitation"]["note"].lower()
    assert "not loosened" in summary["me_identifiability_limitation"]["note"].lower()
    rendered = json.dumps(summary).lower()
    for token in ("evidence", "\"gold\"", "\"answer\"", "observation"):
        assert token not in rendered
    assert summary["outcome_calls"] == 0


def test_opaque_id_usage_note_present():
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    note = summary["opaque_id_usage_note"].lower()
    assert "audit" in note or "grouping" in note
    assert "forbidden as a model feature" in note


def test_manifest_write_roundtrip_and_hash(tmp_path):
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    paths = write_feature_readiness_manifest(rows, summary, tmp_path)

    manifest_lines = paths["rows_manifest"].read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == len(rows)
    for line in manifest_lines:
        parsed = json.loads(line)
        assert parsed["protocol"] == "pm-paper1-memory-feature-readiness-row-v1"

    written_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert written_summary["rows_manifest_count"] == len(rows)

    import hashlib

    rendered = paths["rows_manifest"].read_text(encoding="utf-8")
    assert written_summary["rows_manifest_sha256"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()
