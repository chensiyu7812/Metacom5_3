"""B24/B25: Phase-1 memory feature-readiness / identifiability audit."""

import json
from pathlib import Path

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import enumerate_targets
from metacom_pm.paper1.features.feature_readiness_audit import (
    FEATURE_INVENTORY,
    ZERO_VARIANCE_DIAGNOSTIC_PROXY_STATUS,
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
        for axis_name in (
            "lexical_similarity",
            "lexical_candidate_query_jaccard_ge_0_6_proxy",
            "retrieval_rank",
        ):
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


def test_lexical_jaccard_proxy_is_zero_variance_wherever_candidates_exist():
    # Grounded corpus finding: the 0.6 lexical-overlap proxy threshold is
    # never crossed anywhere in the current corpus. B25: this proxy is
    # explicitly not the authoritative already-visible construct (see
    # feature_inventory), so its zero-variance status must use the
    # dedicated ZERO_VARIANCE_DIAGNOSTIC_PROXY_NOT_FEATURE_READY label, not
    # the generic one other (non-proxy-labeled) axes use.
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    expected = {"MP/qa", "MP/summary", "MS/qa", "MS/summary", "ME/qa", "ME/summary"}
    assert (
        set(summary["lexical_candidate_query_jaccard_ge_0_6_proxy_zero_variance_head_tasks"])
        == expected
    )
    for row in rows:
        if row.task_type is TaskType.DIALOGUE_GENERATION:
            continue
        axis = row.lexical_candidate_query_jaccard_ge_0_6_proxy
        if axis.computable:
            assert axis.readiness_status == ZERO_VARIANCE_DIAGNOSTIC_PROXY_STATUS
            assert axis.zero_variance is True


def test_lexical_jaccard_proxy_field_name_never_claims_to_be_already_visible():
    # B25.2/B25.3: the field/status names themselves must not read as the
    # authoritative already_visible construct.
    for row in _rows():
        manifest = row.to_manifest_row()
        assert "already_visible" not in manifest
        proxy = manifest["lexical_candidate_query_jaccard_ge_0_6_proxy"]
        assert proxy["readiness_status"] != "ZERO_VARIANCE_NOT_FEATURE_READY"
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    assert "already_visible_zero_variance_head_tasks" not in summary
    summary_text = json.dumps(summary)
    assert '"already_visible"' not in summary_text


def test_ms_retrieval_rank_and_lexical_overlap_have_real_variance():
    # Contrast case: MS (up to 33 candidates/target) is NOT zero-variance for
    # rank/lexical overlap, unlike MP/ME's near-degenerate 1-2 candidate pools.
    rows = {(r.head, r.task_type): r for r in _rows()}
    ms_qa = rows[(Head.MS, TaskType.QA)]
    assert ms_qa.retrieval_rank.readiness_status == "COMPUTABLE_WITH_VARIANCE"
    assert ms_qa.retrieval_rank.distinct_value_count > 1
    assert ms_qa.lexical_similarity.readiness_status == "COMPUTABLE_WITH_VARIANCE"
    assert ms_qa.lexical_similarity.distinct_value_count > 1


def test_embedding_similarity_always_reported_not_yet_materialized():
    # 2026-08-19: BGE-M3 cosine similarity is now wired into
    # build_semantic_census (see zero_outcome_census.py), but this audit's
    # own fixtures never pass query_vectors/candidate_vectors -- computable
    # must stay False and the status must say so, not silently flip to
    # IMPLEMENTED just because the underlying code path now exists.
    for row in _rows():
        manifest = row.to_manifest_row()
        assert manifest["embedding_similarity"]["readiness_status"] == (
            "WIRED_NOT_YET_MATERIALIZED_IN_PUBLISHED_ARTIFACT"
        )
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
        assert parsed["protocol"] == "pm-paper1-memory-feature-readiness-row-v2"

    written_summary = json.loads(paths["summary"].read_text(encoding="utf-8"))
    assert written_summary["rows_manifest_count"] == len(rows)

    import hashlib

    rendered = paths["rows_manifest"].read_text(encoding="utf-8")
    assert written_summary["rows_manifest_sha256"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()


# --- B25.5: feature inventory completeness ----------------------------------

_REQUIRED_CANONICAL_NAMES = {
    "mp_state_profile_similarity",
    "mp_profile_already_visible",
    "mp_profile_field_type",
    "mp_profile_relative_age",
    "ms_state_memory_similarity",
    "ms_memory_already_visible",
    "ms_relative_age",
    "ms_thread_entity_overlap",
    "ms_explicit_return_marker",
    "me_state_experience_similarity",
    "me_experience_already_visible",
    "me_relative_age",
    "me_historical_outcome_type",
    "me_current_action_request",
    "me_candidate_token_cost",
    "embedding_similarity",
}

_VALID_INVENTORY_STATUSES = {
    "IMPLEMENTED",
    "IMPLEMENTED_AS_DIAGNOSTIC_PROXY",
    "NOT_IMPLEMENTED",
    "NOT_IMPLEMENTED_PENDING_MECHANICAL_DEFINITION",
    "NOT_AUDITED",
}


def test_feature_inventory_lists_every_blueprint_named_item_from_b25_instruction():
    names = {item["canonical_name"] for item in FEATURE_INVENTORY}
    missing = _REQUIRED_CANONICAL_NAMES - names
    assert missing == set(), f"feature inventory silently omits: {missing}"


def test_feature_inventory_items_have_a_valid_status_and_a_note():
    for item in FEATURE_INVENTORY:
        assert item["status"] in _VALID_INVENTORY_STATUSES, item
        assert item["note"].strip() != "", item
        assert item["head"] in ("MP", "MS", "ME", "SHARED"), item


def test_feature_inventory_never_marks_a_not_implemented_item_as_implemented_via_new_heuristic():
    # B25.4: profile_field_type/historical_outcome_type must stay honestly
    # NOT_IMPLEMENTED in the base (legacy regex/Jaccard-lane) inventory --
    # those two are only ever upgraded via the v6-semantic-compiler-gated
    # _semantic_feature_inventory() overlay (see its module docstring),
    # never silently in FEATURE_INVENTORY itself.
    #
    # thread_entity_overlap/explicit_return_marker/current_action_request
    # are different in kind: they are pure deterministic regex/token
    # functions on Target.visible_query_text, unconditionally available in
    # both the legacy and v6-semantic lanes -- not gated on the v6 compiler
    # existing at all. metacom_pm.paper1.memory.explicit_signals implements
    # all three with dedicated tests (test_paper1_memory_explicit_signals.py),
    # so their base-inventory upgrade to IMPLEMENTED is real, not silent.
    by_name = {item["canonical_name"]: item for item in FEATURE_INVENTORY}
    for name in ("mp_profile_field_type", "me_historical_outcome_type", "embedding_similarity"):
        assert by_name[name]["status"] == "NOT_IMPLEMENTED", by_name[name]
    for name in (
        "ms_thread_entity_overlap",
        "ms_explicit_return_marker",
        "me_current_action_request",
    ):
        assert by_name[name]["status"] == "IMPLEMENTED", by_name[name]


def test_feature_inventory_already_visible_items_pending_mechanical_definition():
    by_name = {item["canonical_name"]: item for item in FEATURE_INVENTORY}
    for name in (
        "mp_profile_already_visible",
        "ms_memory_already_visible",
        "me_experience_already_visible",
    ):
        assert by_name[name]["status"] == "NOT_IMPLEMENTED_PENDING_MECHANICAL_DEFINITION", by_name[name]


def test_feature_inventory_is_present_in_the_summary_report():
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    inventory = summary["feature_inventory"]
    assert len(inventory["items"]) == len(FEATURE_INVENTORY)
    names = {item["canonical_name"] for item in inventory["items"]}
    assert _REQUIRED_CANONICAL_NAMES <= names


def test_measurement_provenance_disclosures_present_and_accurate():
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    disclosures = summary["measurement_provenance_disclosures"]
    token_note = disclosures["token_length"].lower()
    assert "whitespace" in token_note
    assert "not the frozen generator" in token_note or "not the frozen" in token_note
    assert "audit_only" in disclosures["candidate_count"].lower().replace("/", "_") or (
        "provisional" in disclosures["candidate_count"].lower()
    )
    assert "provisional" in disclosures["retrieval_rank"].lower()
    assert "not distinct" in disclosures["target_candidate_edges"].lower()
    assert "not" in disclosures["mp_me_sparsity"].lower()
    assert "pass" in disclosures["mp_me_sparsity"].lower() or "gate" in disclosures["mp_me_sparsity"].lower()


def test_mp_and_me_identifiability_limitation_explicitly_not_a_pass_fail_gate():
    rows = _rows()
    summary = summarize_feature_readiness(rows)
    assert summary["mp_identifiability_limitation"]["not_a_pass_fail_gate"] is True
    assert summary["me_identifiability_limitation"]["not_a_pass_fail_gate"] is True


def test_b25_never_changes_the_underlying_unique_edge_or_coverage_counts():
    # B25.7: the semantic/naming fix must not change any of the numbers
    # frozen by B23/B24 -- only labels and disclosures change.
    rows = {(r.head, r.task_type): r for r in _rows()}
    mp_qa = rows[(Head.MP, TaskType.QA)]
    ms_qa = rows[(Head.MS, TaskType.QA)]
    me_qa = rows[(Head.ME, TaskType.QA)]
    assert (mp_qa.unique_candidate_count, mp_qa.owners_with_candidates, mp_qa.target_candidate_edges) == (
        3,
        3,
        184,
    )
    assert (ms_qa.unique_candidate_count, ms_qa.owners_with_candidates) == (401, 18)
    assert (me_qa.unique_candidate_count, me_qa.owners_with_candidates, me_qa.target_candidate_edges) == (
        3,
        2,
        255,
    )
