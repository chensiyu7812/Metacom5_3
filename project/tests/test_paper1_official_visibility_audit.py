"""B28: official ES-MemEval RQ2 visibility / baseline-contract audit."""

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
    DG_STRUCTURE,
    EVALUATOR_ONLY_FIELDS,
    OFFICIAL_RAG_CONTRACT,
    PINNED_COMMIT,
    PINNED_TAG,
    PUBLIC_ARTIFACT_NAME,
    SURFACE_A_RETRIEVAL_CORPUS,
    SURFACE_B_PM_VISIBLE_DECISION_STATE,
    SURFACE_C_GENERATOR_VISIBLE_PROMPT,
    SURFACE_D_EVALUATOR_ONLY,
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
    # never conflate the public artifact with the paper's 1209-row figure
    assert "1209" not in PUBLIC_ARTIFACT_NAME


def test_audited_source_files_have_real_looking_git_blob_shas():
    assert len(AUDITED_SOURCE_FILES) >= 30
    for path, sha in AUDITED_SOURCE_FILES.items():
        assert path.startswith("src/")
        assert path.endswith(".py")
        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)


def test_every_task_arm_surface_combination_is_covered():
    rows = build_task_arm_surface_rows()
    assert len(rows) == len(TASKS) * len(ARMS) * len(SURFACES)
    keys = {(r.task, r.arm, r.surface) for r in rows}
    expected = {(t, a, s) for t in TASKS for a in ARMS for s in SURFACES}
    assert keys == expected


def test_qa_and_summarization_no_memory_arm_is_not_officially_shipped():
    # B28: no dedicated no-memory script exists for QA/Summarization in the
    # official repo (unlike DG's dg_gpt4o.py) -- this must be disclosed, not
    # silently implied to be an official baseline.
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


def test_official_rag_contract_flags_dg_truncation_gap():
    # B28: confirmed asymmetry -- QA/Summarization truncate, DG does not.
    qa_trunc = OFFICIAL_RAG_CONTRACT["truncation_max_token_behavior"][TASK_QA].lower()
    dg_trunc = OFFICIAL_RAG_CONTRACT["truncation_max_token_behavior"][TASK_DIALOGUE_GENERATION].lower()
    assert "token" in qa_trunc
    assert "no equivalent" in dg_trunc or "no truncation" in dg_trunc


def test_evaluator_only_fields_never_appear_inside_any_a_b_or_c_surface_description():
    rows = build_task_arm_surface_rows()
    runtime_surfaces = {SURFACE_A_RETRIEVAL_CORPUS, SURFACE_B_PM_VISIBLE_DECISION_STATE, SURFACE_C_GENERATOR_VISIBLE_PROMPT}
    for row in rows:
        if row.surface not in runtime_surfaces:
            continue
        rendered = row.description.lower()
        for field in EVALUATOR_ONLY_FIELDS:
            # exact bracket-key form, e.g. "['answer']" or ["answer"] -- avoids
            # false positives on unrelated prose that happens to contain a
            # forbidden word as a substring of a different word.
            assert f"['{field}']" not in rendered
            assert f'["{field}"]' not in rendered


def test_d_surface_rows_are_the_only_ones_naming_evaluator_only_fields():
    rows = build_task_arm_surface_rows()
    d_rows = [r for r in rows if r.surface == SURFACE_D_EVALUATOR_ONLY]
    assert len(d_rows) == len(TASKS) * len(ARMS)
    for row in d_rows:
        rendered = row.description.lower()
        assert "answer" in rendered or "basic_info" in rendered or "observation" in rendered


def test_dg_b_surface_explicitly_disclaims_related_sessions_topic_and_background():
    # The description text legitimately names these fields in order to say
    # they are excluded ("... never reach this surface") -- so this checks
    # for the negation qualifier, not bare absence of the words.
    rows = build_task_arm_surface_rows()
    dg_b_rows = [
        r for r in rows if r.task == TASK_DIALOGUE_GENERATION and r.surface == SURFACE_B_PM_VISIBLE_DECISION_STATE
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
    for token in ("\"gold\"", "observation_score", "llm_as_a_judge_result"):
        assert token not in rendered


def test_module_never_imports_the_sanitized_loader_materializer_or_raw_evo_emo():
    # B28: this is a pure static-documentation module -- it must never
    # import anything that reads evo_emo.json or the sanitized artifact.
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
        assert parsed["protocol"] == "pm-paper1-official-visibility-task-arm-surface-row-v1"
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
