from __future__ import annotations

import json
from pathlib import Path

from metacom_pm.v1_5_semantic_adapter_probe import (
    candidate_relation_premise,
    latest_dialogue_window,
    validate_oracle_plans,
)


ROOT = Path(__file__).resolve().parents[1]


def test_latest_window_preserves_latest_seeker_turn() -> None:
    text = "\n".join([f"SUPPORTER: old {i}" for i in range(50)] + ["SEEKER: latest need"])
    window = latest_dialogue_window(text, max_chars=80)
    assert window.endswith("SEEKER: latest need")
    assert "old 0" not in window


def test_candidate_relation_keeps_current_and_past_roles_explicit() -> None:
    premise = candidate_relation_premise("SEEKER: current", "past fact")
    assert "CURRENT EMOTIONAL-SUPPORT DIALOGUE" in premise
    assert "STRICTLY PAST USER STATEMENT" in premise
    assert premise.endswith("past fact")


def test_oracle_plan_file_is_exact_and_nonforcing() -> None:
    oracle = json.loads(
        (ROOT / "data/pm_v1_5_contracts/paper1_ms_oracle_semantic_plans_v1.json").read_text()
    )
    cases = [
        json.loads(line)
        for line in (
            ROOT
            / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811/qualification_cases_private.jsonl"
        ).read_text().splitlines()
        if line.strip()
    ]
    expected = {
        row["qualification_case_id"]
        for row in cases
        if row["qualification_class"] == "TEACHER_SUITABLE"
    }
    checks = validate_oracle_plans(oracle["plans"], expected_case_ids=expected)
    assert checks and all(checks.values())


def test_contract_forbids_live_mutation() -> None:
    contract = json.loads(
        (ROOT / "data/pm_v1_5_contracts/paper1_semantic_adapter_ablation_v1.json").read_text()
    )
    assert contract["method_version"] == "PAPER1_SOURCE_ANNOTATED_RESOURCE_SUITABILITY_V2"
    assert contract["experiment_revision"] == "SEMANTIC_ADAPTER_ABLATION_V1"
    assert contract["authority"]["api_calls_authorized"] == 0
    assert contract["authority"]["training_labels_authorized"] == 0
    assert contract["authority"]["pm_fits_authorized"] == 0
    assert contract["oracle_plan_probe"]["states"] == 8
