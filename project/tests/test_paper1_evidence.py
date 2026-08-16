import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "data/v3_authority"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_final_llama_rq0_evidence_is_self_consistent():
    preflight = json.loads((AUTHORITY / "rq0_llama31_8b_esc_eval_exact_preflight_v1.json").read_text())
    generation = json.loads((AUTHORITY / "rq0_llama31_8b_esc_eval_exact_generation_closeout_v1.json").read_text())
    score = json.loads((AUTHORITY / "rq0_llama31_8b_esc_eval_exact_score_preflight_v1.json").read_text())
    qualification = json.loads((AUTHORITY / "rq0_llama31_8b_esc_eval_exact_qualification_v1.json").read_text())
    assert qualification["status"] == "RQ0_COMPLETE_LLAMA31_8B_FROZEN_FOR_PM_EFFECT_GENERATION"
    assert qualification["candidate"]["model"] == "meta/llama-3.1-8b-instruct"
    assert generation["complete_dialogues"] == 331
    assert generation["successful_turns"] == 1655
    assert qualification["scoring_integrity"]["dimension_calls"] == 2317
    assert sha(AUTHORITY / "rq0_llama31_8b_esc_eval_exact_contract_v1.json") == preflight["input_hashes"]["rq0_llama31_8b_esc_eval_exact_contract_v1.json"]
    assert sha(ROOT / "scripts/v3/46_run_rq0_llama31_8b_esc_eval_exact.py") == preflight["input_hashes"]["46_run_rq0_llama31_8b_esc_eval_exact.py"]
    assert sha(ROOT / "scripts/v3/48_score_rq0_llama31_8b_esc_eval_exact.py") == score["measurement"]["scorer_sha256"]
    assert qualification["evidence_hashes"]["official_result_sha256"] == score["result_sha256"]


def test_historical_transitive_dependency_gap_is_disclosed_not_hidden():
    closure = json.loads(
        (AUTHORITY / "rq0_llama31_8b_integration_dependency_closure_v1.json").read_text()
    )
    assert closure["status"].endswith("HISTORICAL_PREFLIGHT_OMISSION_DISCLOSED")
    assert (
        closure["historical_runtime_dependency_not_bound_by_preflight"][
            "historical_worktree_sha256"
        ]
        != closure["historical_runtime_dependency_not_bound_by_preflight"][
            "origin_main_integration_base_sha256"
        ]
    )
    for relative, expected in closure["exactly_ported_dependencies"].items():
        assert sha(ROOT.parent / relative) == expected


def test_public_1427_identity_is_named_without_paper_replication_claim():
    identity = json.loads((AUTHORITY / "es_memeval_public_v1_0_0_1427_identity_decision_v1.json").read_text())
    manifest = AUTHORITY / "es_memeval_public_v1_0_0_1427_row_identity_v1.jsonl"
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert identity["primary_task_name"] == "ES-MemEval-Public-v1.0.0-1427"
    assert identity["formal_paper_boundary"]["paper_qa"] == 1209
    assert identity["formal_paper_boundary"]["public_qa"] == 1427
    assert len(rows) == 1427
    assert sha(manifest) == identity["identity_manifest"]["sha256"]
    assert sha(ROOT / "data/external/evo_emo.json") == identity["source"]["sha256"]


def test_esc_overlap_slices_are_frozen_outcome_blind():
    summary = json.loads((ROOT / "data/paper1_authority/esc_eval_english331_source_overlap_summary_v1.json").read_text())
    manifest = ROOT / "data/paper1_authority/esc_eval_english331_source_overlap_v1.jsonl"
    rows = [json.loads(line) for line in manifest.read_text().splitlines()]
    assert len(rows) == 331
    assert summary["primary_non_esconv_transfer_cards"] == 173
    assert summary["esconv_source_overlap_cards"] == 158
    assert summary["contains_outcomes"] is False
    assert sha(manifest) == summary["manifest_sha256"]
