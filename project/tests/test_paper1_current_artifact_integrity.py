import hashlib
import json
from pathlib import Path

import yaml


PROJECT = Path(__file__).resolve().parents[1]
AUTHORITY = PROJECT / "data" / "paper1_authority"


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_current_public_1427_identity_is_hash_bound_and_text_free():
    identity = _json(AUTHORITY / "es_memeval_public_v1_0_0_1427_identity_decision_v1.json")
    manifest = AUTHORITY / "es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl"
    rows = _jsonl(manifest)
    assert identity["primary_task_name"] == "ES-MemEval-Public-v1.0.0-1427"
    assert identity["formal_paper_boundary"]["paper_qa"] == 1209
    assert identity["formal_paper_boundary"]["public_qa"] == 1427
    assert len(rows) == len({row["row_id"] for row in rows}) == 1427
    assert all("question" not in row and "answer" not in row for row in rows)
    assert _sha(manifest) == identity["identity_manifest"]["sha256"]
    assert _sha(PROJECT / "data/external/evo_emo.json") == identity["source"]["sha256"]


def test_current_esc_overlap_slices_are_hash_bound_and_outcome_blind():
    summary = _json(AUTHORITY / "esc_eval_english331_source_overlap_summary_v1.json")
    manifest = AUTHORITY / "esc_eval_english331_source_overlap_v1.jsonl"
    rows = _jsonl(manifest)
    assert len(rows) == 331
    assert sum(row["analysis_slice"] == "primary_non_esconv_transfer" for row in rows) == 173
    assert sum(row["analysis_slice"] == "esconv_source_overlap" for row in rows) == 158
    assert summary["contains_outcomes"] is False
    assert _sha(manifest) == summary["manifest_sha256"]


def test_current_rs_canonical_top8_artifacts_are_hash_bound_and_complete():
    report = _json(PROJECT / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_report_v1.json")
    catalog = PROJECT / "data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl"
    top8 = PROJECT / "data/paper1_public_rs/esconv_rs_canonical_bge_top8_v1.jsonl"
    assert report["counts"] == {
        "raw_atomic_units": 15061,
        "exact_canonical_treatments": 13172,
        "exact_alias_instances_beyond_first": 1889,
        "decision_states": 11883,
    }
    assert _sha(catalog) == report["identities"]["canonical_catalog_sha256"]
    assert _sha(top8) == report["identities"]["canonical_top8_sha256"]
    for k in (1, 2, 3, 4, 6, 8):
        cell = report["k_surface"][str(k)]
        assert cell["coverage"] == 1.0
        assert cell["truncation_rate_common_cap384"] == 0.0
    assert report["compute"]["outcome_calls"] == 0
    assert report["compute"]["Generator_calls"] == 0


def test_current_config_does_not_list_completed_freezes_as_pending():
    config = yaml.safe_load((PROJECT / "configs/paper1_public_only.yaml").read_text())
    pending = set(config["pending_zero_outcome_freeze"])
    assert "active_multi_view_extractor_runtime_and_401_artifact" not in pending
    assert "task_specific_material_better_and_equivalence_rules" not in pending
    assert "exact_feature_schema" in pending
    assert "generator_step2_runtime_manifest" in pending


def test_teacher_reference_denominators_are_exact_before_rating():
    design = _json(
        AUTHORITY / "paper1_pairwise_teacher_human_reference_design_20260904_v1.json"
    )
    units = design["measurement_units"]
    allocation = design["task_allocation"]
    assert units["base_semantic_pairs"] == 80
    assert units["reversed_pair_presentations"] == 16
    assert units["total_blinded_pair_presentations"] == 96
    assert units["independent_primary_raters"] == 2
    assert units["primary_rater_pair_judgements"] == 192
    assert sum(row["base_semantic_pairs"] for row in allocation.values()) == 80
    assert sum(row["reversed_presentations"] for row in allocation.values()) == 16
    assert sum(row["total_presentations"] for row in allocation.values()) == 96
    assert design["identity_and_blinding"]["base_pair_identity_manifest"].startswith(
        "PENDING"
    )
    assert set(design["locks"].values()) == {"CLOSED"}


def test_mistral_formal_schedule_is_balanced_and_still_pre_outcome():
    schedule = _json(
        AUTHORITY / "paper1_official_mistral24b_formal_schedule_contract_20260904_v1.json"
    )
    algorithm = schedule["schedule_algorithm"]
    assert schedule["official_scorer"]["temperature"] == "official_provider_default_omitted"
    assert schedule["execution"]["concurrency"] == 8
    assert schedule["execution"]["server_seed"] == 0
    assert schedule["execution"]["server_command_must_pass_explicit_seed"] is True
    assert schedule["execution"]["pilot_server_seed_was_explicitly_bound"] is False
    assert len(algorithm["canonical_arms"]) == 6
    assert algorithm["one_arm_complete_before_next_arm"] == "FORBIDDEN"
    assert algorithm["all_six_arms_contiguous_per_matched_unit"] is True
    assert algorithm["evaluator_prompt_contains_arm_identity"] is False
    assert algorithm["final_request_manifest_sha256"].startswith("PENDING")
    assert schedule["interpretation"]["guarantees_per_item_determinism"] is False
    assert set(schedule["locks"].values()) == {"CLOSED"}


def test_active_generator_binding_keeps_v3_as_unopened_provenance_only():
    binding = _json(
        AUTHORITY / "paper1_active_generator_selection_binding_20260904_v1.json"
    )
    assert binding["selection"]["model"] == "meta/llama-3.1-8b-instruct"
    assert binding["selection"]["pm_effect_generation_authorized"] is True
    assert binding["archived_provenance"]["routine_ci_reopens_archived_files"] is False
    assert binding["active_runtime"]["authority_sha256"] == _sha(
        AUTHORITY / "paper1_generator_backend_retirement_local_amendment_20260903_v1.json"
    )
    assert set(binding["locks"].values()) == {"CLOSED"}
