import json
from decimal import Decimal
from pathlib import Path

from metacom_pm.io import sha256_file


ROOT = Path(__file__).resolve().parents[1]
AUTHORITY = ROOT / "data" / "paper1_authority"


def test_manifest_covers_exact_public_401_and_fits_stage_cap():
    summary = json.loads(
        (AUTHORITY / "paper1_multi_view_401_call_manifest_preflight_20260903_v1.json")
        .read_text(encoding="utf-8")
    )
    rows_path = AUTHORITY / "paper1_multi_view_401_call_manifest_20260903_v1.jsonl"
    rows = [json.loads(line) for line in rows_path.read_text(encoding="utf-8").splitlines()]
    assert summary["status"] == "PASS_ZERO_OUTCOME_PREFLIGHT"
    assert summary["source"] == {
        "path": "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json",
        "sha256": "51c16916c89b8d7ef0845cd0e4fc8b486569ba0ff9c65a39ba66c6d2dde2e12c",
        "users": 18,
        "sessions": 401,
        "turns": 9368,
    }
    assert len(rows) == 401
    assert len({(row["owner_id"], row["session_id"]) for row in rows}) == 401
    assert [row["sequence"] for row in rows] == list(range(401))
    assert sha256_file(rows_path) == summary["manifest"]["sha256"]
    budget = summary["budget"]
    assert Decimal(budget["aggregate_maximum_cost_usd"]) <= Decimal(
        budget["stage_hard_cap_usd"]
    )
    assert budget["maximum_provider_calls"] == 802
    assert all(row["outcome_fields_read"] is False for row in rows)


def test_manifest_freezes_exact_model_tokenizer_prompts_and_schemas():
    summary = json.loads(
        (AUTHORITY / "paper1_multi_view_401_call_manifest_preflight_20260903_v1.json")
        .read_text(encoding="utf-8")
    )
    identity = summary["runtime_identity"]
    assert identity["model"] == "qwen3-235b-a22b-instruct-2507"
    assert identity["enable_thinking"] is False
    assert identity["temperature"] == 0.0
    assert identity["seed"] == 0
    assert identity["tokenizer_revision"] == "ac9c66cc9b46af7306746a9250f23d47083d689e"
    assert set(identity["tokenizer_file_sha256"]) == {
        "tokenizer.json",
        "tokenizer_config.json",
        "config.json",
    }
    for field in (
        "extractor_prompt_sha256",
        "verifier_prompt_sha256",
        "extractor_schema_sha256",
        "verifier_schema_sha256",
    ):
        assert len(identity[field]) == 64
    assert summary["method_boundary"] == {
        "prior_profile_allowance_is_per_call_not_observed_output": True,
        "verifier_proposal_allowance_equals_extractor_max_output_tokens": True,
        "formal_outcomes_read": 0,
        "paid_api_calls": 0,
        "pm_training_runs": 0,
        "all_outcome_locks": "CLOSED",
    }
