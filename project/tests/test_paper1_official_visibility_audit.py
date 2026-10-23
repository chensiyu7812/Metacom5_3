"""B28/B28R: official ES-MemEval RQ2 visibility / baseline-contract audit."""

import ast
import inspect
import json

import pytest

from metacom_pm.paper1.official_visibility_audit import (
    ARMS,
    ARM_FULL_HISTORY,
    ARM_NO_MEMORY,
    ARM_OFFICIAL_RAG_TOP4,
    AUDITED_SOURCE_FILES,
    AUDITED_SOURCE_TREES,
    AUDITED_SOURCE_TREE_LISTINGS,
    DG_RAG_DOUBLE_BEGINNING_PROMPT_NOTE,
    DG_STRUCTURE,
    DG_TOKEN_CONTRACT,
    D_SUB_CATEGORIES,
    D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY,
    D_SUB_POSTGENERATION_EVALUATOR_ONLY,
    D_SUB_POSTGENERATION_LOGGING_ONLY,
    D_SUB_UNUSED_OFFICIAL_METADATA,
    FIELD_VISIBILITY_TABLE,
    OFFICIAL_RAG_CONTRACT,
    PINNED_COMMIT,
    PINNED_TAG,
    PUBLIC_ARTIFACT_NAME,
    SURFACE_A_RETRIEVAL_CORPUS,
    SURFACE_B_QUERY_STATE_ONLY,
    SURFACE_C_GENERATOR_VISIBLE_PROMPT,
    SURFACE_D_NOT_SUPPORTER_VISIBLE,
    SURFACES,
    TASKS,
    TASK_DIALOGUE_GENERATION,
    TASK_QA,
    TASK_SUMMARIZATION,
    build_official_visibility_audit_report,
    build_task_arm_surface_rows,
    write_official_visibility_manifest,
)
from metacom_pm.paper1 import official_visibility_audit as _module


def test_pinned_source_identity_matches_the_frozen_commit():
    assert PINNED_COMMIT == "692624208acc077b8867698c1d6fcd998dee641a"
    assert PINNED_TAG == "v1.0.0"
    assert PUBLIC_ARTIFACT_NAME == "ES-MemEval-Public-v1.0.0-1427"
    assert "1209" not in PUBLIC_ARTIFACT_NAME


def test_audited_source_files_have_real_looking_git_blob_shas():
    assert len(AUDITED_SOURCE_FILES) >= 33
    for path, sha in AUDITED_SOURCE_FILES.items():
        assert path.startswith("src/")
        assert path.endswith(".py")
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)


def test_b28r_6_new_sum_blobs_present_and_exact():
    expected = {
        "src/exe/sum/sum_gpt4o_full.py": "1a7cf4b5b1920ac379166903e4448a8d08a2733b",
        "src/exe/sum/sum_gpt4o_rag.py": "c106a0518b1d3dc34c224892d4ce8c1a6f651a2c",
        "src/lib/sum/sum_experiment_parameters.py": "837dae7e9d6ff69e2d3e1b02b10ed9d62eff2505",
    }
    for path, sha in expected.items():
        assert AUDITED_SOURCE_FILES[path] == sha


def test_absence_of_a_no_memory_qa_sum_script_is_backed_by_full_tree_listings():
    # B28R.6: an absence claim needs a complete directory listing, not a
    # curated set of blobs -- confirm the tree shas and listings are present
    # and that neither directory contains anything named like a dedicated
    # no-memory/empty baseline.
    assert set(AUDITED_SOURCE_TREES) == {"src/exe/qa", "src/exe/sum"}
    for path, tree_sha in AUDITED_SOURCE_TREES.items():
        assert len(tree_sha) == 40
        listing = AUDITED_SOURCE_TREE_LISTINGS[path]
        assert len(listing) >= 10
        for name in listing:
            assert "no_memory" not in name
            assert "empty" not in name
            assert "baseline" not in name
            assert "_full" in name or "_rag" in name


def test_every_task_arm_surface_combination_is_covered():
    rows = build_task_arm_surface_rows()
    assert len(rows) == len(TASKS) * len(ARMS) * len(SURFACES)
    keys = {(r.task, r.arm, r.surface) for r in rows}
    expected = {(t, a, s) for t in TASKS for a in ARMS for s in SURFACES}
    assert keys == expected


def test_surface_b_is_renamed_query_state_only_not_pm_visible_decision_state():
    assert SURFACE_B_QUERY_STATE_ONLY == "B_query_state_only"
    report = build_official_visibility_audit_report()
    assert "surface_b_no_pm_in_harness_note" in report
    note = report["surface_b_no_pm_in_harness_note"].lower()
    assert "no pm" in note or "no pm/memory-selection" in note


def test_surface_d_renamed_and_has_explicit_consumer_sub_categories():
    assert SURFACE_D_NOT_SUPPORTER_VISIBLE == "D_not_tested_supporter_visible"
    assert set(D_SUB_CATEGORIES) == {
        D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY,
        D_SUB_POSTGENERATION_EVALUATOR_ONLY,
        D_SUB_POSTGENERATION_LOGGING_ONLY,
        D_SUB_UNUSED_OFFICIAL_METADATA,
    }


def test_surfaces_no_longer_claimed_non_overlapping():
    report = build_official_visibility_audit_report()
    note = report["surfaces_non_overlapping_note"].lower()
    assert "not" in note
    assert "guaranteed" in note or "overlap" in note


# --- B28R.1: basic_info field-level split -----------------------------------


def _field_row(field_path: str):
    return next(r for r in FIELD_VISIBILITY_TABLE if r.field_path == field_path)


def test_basic_info_name_reaches_the_tested_supporter():
    row = _field_row("basic_info.name")
    assert row.reaches_tested_supporter_prompt is True
    note = row.reaches_tested_supporter_note.lower()
    assert "greeting" in note or "beginning_prompt" in note
    assert "human_name" in note or "labels" in note


def test_basic_info_other_fields_never_reach_the_tested_supporter():
    row = _field_row("basic_info.age|gender|nationality|location|job|education")
    assert row.reaches_tested_supporter_prompt is False
    assert row.applies_to_tasks == (TASK_DIALOGUE_GENERATION,)
    assert D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY in row.d_sub_categories
    assert D_SUB_POSTGENERATION_EVALUATOR_ONLY in row.d_sub_categories


def test_basic_info_no_longer_reported_as_a_single_evaluator_only_blob():
    # There must be at least two distinct basic_info rows (name vs. the rest)
    basic_info_rows = [r for r in FIELD_VISIBILITY_TABLE if r.field_path.startswith("basic_info")]
    assert len(basic_info_rows) >= 2
    reaches = {r.reaches_tested_supporter_prompt for r in basic_info_rows}
    assert reaches == {True, False}  # not uniformly one classification


def test_social_relationship_and_dialog_history_emotion_topic_are_unused_not_evaluator_only():
    for field_path in ("social_relationship", "dialog_history[].emotion", "dialog_history[].topic"):
        row = _field_row(field_path)
        assert row.d_sub_categories == (D_SUB_UNUSED_OFFICIAL_METADATA,)
        assert row.reaches_tested_supporter_prompt is False


def test_dialog_history_summary_and_subsequent_topic_topic_have_overlapping_sub_categories():
    # Real, mechanically-confirmed examples of D sub-categories co-occurring.
    for field_path in ("dialog_history[].summary", "subsequent_topics[].topic"):
        row = _field_row(field_path)
        assert D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY in row.d_sub_categories
        assert D_SUB_POSTGENERATION_EVALUATOR_ONLY in row.d_sub_categories


# --- B28R.7: QA/Summary evaluator fields accurate ---------------------------


def test_qa_evidence_and_summary_evidence_theme_group_are_schema_present_but_unused():
    qa_evidence = _field_row("question.evidence")
    assert qa_evidence.d_sub_categories == (D_SUB_UNUSED_OFFICIAL_METADATA,)
    sum_fields = _field_row("summary.evidence|theme|group")
    assert sum_fields.d_sub_categories == (D_SUB_UNUSED_OFFICIAL_METADATA,)


def test_qa_answer_and_summary_answer_are_actually_consumed_by_scoring():
    for field_path in ("question.answer", "summary.answer"):
        row = _field_row(field_path)
        assert row.d_sub_categories == (D_SUB_POSTGENERATION_EVALUATOR_ONLY,)
        assert "read" in row.reaches_tested_supporter_note.lower() or "consumed" in row.description.lower()


def test_capability_fields_are_csv_logging_only():
    for field_path in ("question.capability", "summary.capability"):
        row = _field_row(field_path)
        assert "csv" in row.description.lower()
        assert row.d_sub_categories == (D_SUB_POSTGENERATION_LOGGING_ONLY,)


def test_full_history_descriptions_do_not_invent_an_explicit_sort():
    rows = build_task_arm_surface_rows()
    full_history_prompt_rows = [
        row
        for row in rows
        if row.arm == ARM_FULL_HISTORY
        and row.surface == SURFACE_C_GENERATOR_VISIBLE_PROMPT
    ]
    assert len(full_history_prompt_rows) == 3
    assert all("source-list" in row.description for row in full_history_prompt_rows)
    assert all("chronological order" not in row.description for row in full_history_prompt_rows)


# --- B28R.3: DG token contract -----------------------------------------------


def test_dg_token_contract_states_no_input_truncation_but_output_caps():
    assert DG_TOKEN_CONTRACT["harness_level_input_context_truncation"] == "NONE"
    caps = DG_TOKEN_CONTRACT["output_max_tokens"]
    assert caps["seeker"] == 60
    assert caps["supporter"] == 60
    assert caps["observation_scorer"] == 30
    assert caps["observation_usage_judge"] == 30


def test_old_no_truncation_max_token_logic_anywhere_phrasing_is_removed():
    # The exact old blanket claims this round retires -- checked as literal
    # affirmative phrasings, not the (legitimate) explanatory mention of
    # "the removed claim" in this module's own B28R changelog comment.
    source = inspect.getsource(_module)
    for old_phrasing in (
        "no truncation/max-token logic exists anywhere",
        "no truncation/max-token logic found anywhere",
        "no truncation/max-token logic found here either",
    ):
        assert old_phrasing not in source.lower()


# --- B28R.4: DG RAG double beginning_prompt ---------------------------------


def test_dg_rag_double_beginning_prompt_note_present_and_mechanically_grounded():
    note = DG_RAG_DOUBLE_BEGINNING_PROMPT_NOTE.lower()
    assert "twice" in note
    assert "fixedstrategy" in note
    assert "room.append" in note or "_history" in note

    rows = build_task_arm_surface_rows()
    dg_rag_c = next(
        r for r in rows
        if r.task == TASK_DIALOGUE_GENERATION and r.arm == ARM_OFFICIAL_RAG_TOP4 and r.surface == SURFACE_C_GENERATOR_VISIBLE_PROMPT
    )
    assert "twice" in dg_rag_c.description.lower()


# --- B28R.5: A/C relationship precision --------------------------------------


def test_candidate_vs_prompt_visibility_note_no_longer_claims_unconditional_coincidence():
    report = build_official_visibility_audit_report()
    note = report["candidate_vs_prompt_visibility_note"].lower()
    assert "coincide" in note
    assert "only coincides" in note or "not reliably" in note or "not guaranteed" in note
    assert "truncat" in note


def test_dg_full_history_surface_a_is_not_alwaysalldocumentstore():
    rows = build_task_arm_surface_rows()
    row = next(
        r for r in rows
        if r.task == TASK_DIALOGUE_GENERATION and r.arm == ARM_FULL_HISTORY and r.surface == SURFACE_A_RETRIEVAL_CORPUS
    )
    desc = row.description.lower()
    assert "not" in desc and "alwaysalldocumentstore" in desc
    assert "fill_session" in desc


def test_qa_sum_full_history_surface_c_mentions_truncation_prefix_caveat():
    rows = build_task_arm_surface_rows()
    for task in (TASK_QA, TASK_SUMMARIZATION):
        row = next(
            r for r in rows
            if r.task == task and r.arm == ARM_FULL_HISTORY and r.surface == SURFACE_C_GENERATOR_VISIBLE_PROMPT
        )
        assert "prefix" in row.description.lower()


def test_qa_sum_rag_surface_c_admits_not_reliably_strict_subset():
    rows = build_task_arm_surface_rows()
    for task in (TASK_QA, TASK_SUMMARIZATION):
        row = next(
            r for r in rows
            if r.task == task and r.arm == ARM_OFFICIAL_RAG_TOP4 and r.surface == SURFACE_C_GENERATOR_VISIBLE_PROMPT
        )
        assert "not reliably" in row.description.lower() or "not guaranteed" in row.description.lower()


# --- general structural checks ----------------------------------------------


def test_qa_and_summarization_no_memory_arm_is_not_officially_shipped():
    rows = build_task_arm_surface_rows()
    for task in (TASK_QA, TASK_SUMMARIZATION):
        for row in rows:
            if row.task == task and row.arm == ARM_NO_MEMORY:
                assert row.arm_officially_shipped_script is False


def test_dg_no_memory_arm_is_officially_shipped():
    rows = build_task_arm_surface_rows()
    for row in rows:
        if row.task == TASK_DIALOGUE_GENERATION and row.arm == ARM_NO_MEMORY:
            assert row.arm_officially_shipped_script is True


def test_dg_full_history_and_rag_arms_are_officially_shipped():
    rows = build_task_arm_surface_rows()
    for task in TASKS:
        for arm in (ARM_FULL_HISTORY, ARM_OFFICIAL_RAG_TOP4):
            for row in rows:
                if row.task == task and row.arm == arm:
                    assert row.arm_officially_shipped_script is True


def test_dg_structure_matches_the_10_round_20_utterance_plus_greeting_shape():
    assert DG_STRUCTURE["interaction_rounds"] == 10
    assert DG_STRUCTURE["generated_utterances_per_round"] == 2
    assert DG_STRUCTURE["total_generated_utterances"] == 20
    assert DG_STRUCTURE["fixed_supporter_greeting_count"] == 1
    assert (
        DG_STRUCTURE["interaction_rounds"] * DG_STRUCTURE["generated_utterances_per_round"]
        == DG_STRUCTURE["total_generated_utterances"]
    )


def test_official_rag_contract_states_bge_m3_top4_faiss():
    assert OFFICIAL_RAG_CONTRACT["embedding_model"] == "BAAI/bge-m3"
    assert OFFICIAL_RAG_CONTRACT["top_k"] == 4
    assert OFFICIAL_RAG_CONTRACT["vector_store_backend"] == "FAISS"
    assert "session" in OFFICIAL_RAG_CONTRACT["retrieval_granularity"].lower()


def test_official_rag_contract_dg_query_construction_is_dynamic_not_static():
    dg_query_note = OFFICIAL_RAG_CONTRACT["query_construction"][TASK_DIALOGUE_GENERATION].lower()
    assert "current" in dg_query_note
    assert "generated" in dg_query_note or "genuinely" in dg_query_note
    assert "related_sessions" not in dg_query_note
    assert "topic" not in dg_query_note


def test_dg_b_surface_explicitly_disclaims_related_sessions_topic_and_background():
    rows = build_task_arm_surface_rows()
    dg_b_rows = [
        r for r in rows if r.task == TASK_DIALOGUE_GENERATION and r.surface == SURFACE_B_QUERY_STATE_ONLY
    ]
    assert len(dg_b_rows) == len(ARMS)
    for row in dg_b_rows:
        rendered = row.description.lower()
        assert "related_sessions" in rendered
        assert "never reach this surface" in rendered


def test_candidate_vs_prompt_visibility_note_present_and_distinguishes_surfaces():
    report = build_official_visibility_audit_report()
    note = report["candidate_vs_prompt_visibility_note"].lower()
    assert "surface a" in note or "retrieval corpus" in note
    assert "surface c" in note or "generator" in note
    assert "not" in note


def test_report_never_selects_topk_token_cap_or_outer_fold_params():
    report = build_official_visibility_audit_report()
    not_selected = report["not_selected_this_round"]
    assert not_selected["memory_top_k"] is None
    assert not_selected["memory_token_cap"] is None
    assert not_selected["outer_k"] is None
    assert not_selected["outer_seed"] is None
    assert "NOT_IMPLEMENTED" in not_selected["already_visible_heuristic"]


def test_report_is_zero_outcome_and_never_reads_local_corpus_data():
    report = build_official_visibility_audit_report()
    assert report["outcome_calls"] == 0
    rendered = json.dumps(report).lower()
    for token in ("\"gold\"", "\"answer\":", "\"evidence\":"):
        assert token not in rendered


def test_module_never_imports_the_sanitized_loader_materializer_or_raw_evo_emo():
    tree = ast.parse(inspect.getsource(_module))
    forbidden_modules = (
        "metacom_pm.paper1.data.memory_source",
        "metacom_pm.paper1.data.materializer",
        "metacom_pm.paper1.data.es_memeval",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in forbidden_modules:
            raise AssertionError(f"official_visibility_audit.py imports {node.module}")


def test_manifest_write_roundtrip_and_hash(tmp_path):
    rows = build_task_arm_surface_rows()
    report = build_official_visibility_audit_report()
    paths = write_official_visibility_manifest(rows, report, tmp_path)

    manifest_lines = paths["surface_rows_manifest"].read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == len(rows)
    for line in manifest_lines:
        parsed = json.loads(line)
        assert parsed["protocol"] == "pm-paper1-official-visibility-task-arm-surface-row-v2"
        assert parsed["task"] in TASKS
        assert parsed["arm"] in ARMS
        assert parsed["surface"] in SURFACES

    written_report = json.loads(paths["report"].read_text(encoding="utf-8"))
    assert written_report["surface_rows_manifest_count"] == len(rows)

    import hashlib

    rendered = paths["surface_rows_manifest"].read_text(encoding="utf-8")
    assert written_report["surface_rows_manifest_sha256"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def test_no_component_id_or_fold_id_confusion_anywhere_in_this_module():
    report = build_official_visibility_audit_report()
    rendered = json.dumps(report)
    assert '"fold_id"' not in rendered
    assert '"group_component_id"' not in rendered
