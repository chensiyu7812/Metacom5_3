"""Historical V3 evidence-provenance tests; excluded from routine Paper-1 CI."""

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
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
