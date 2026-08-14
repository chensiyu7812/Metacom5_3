from __future__ import annotations

import json
from pathlib import Path


AUTHORITY = Path(__file__).resolve().parents[1] / "data" / "v3_authority"


def _protocol() -> dict:
    return json.loads((AUTHORITY / "generator_fair_selection_protocol_v1.json").read_text(encoding="utf-8"))


def test_fair_selection_separates_quality_guardrails_operations_and_cost() -> None:
    protocol = _protocol()
    hierarchy = protocol["metric_hierarchy"]
    assert hierarchy["primary_quality"] == [
        "ESC-Eval Overall 0-to-4 blinded human rating"
    ]
    assert hierarchy["key_quality_dimensions"] == ["Empathy", "Skill", "Information"]
    assert "actual USD" in hierarchy["tie_breakers_after_qualification"]
    assert "no material or critical absolute integrity regression" in hierarchy["hard_gates"]
    assert protocol["pairwise_resolution"]["no_composite"] is True
    assert "cost and latency cannot compensate" in protocol["fairness_dimensions"]["decision_fairness"][2]


def test_fair_selection_canary_is_measurement_only_and_accounts_for_every_call() -> None:
    protocol = _protocol()
    canary = protocol["qualification_canary"]
    assert canary["eia_calls"] == 6 * 3 * 3 * 2 == 108
    assert canary["repeatability_calls"] == 18
    assert canary["absolute_guardrail_calls"] == 18
    assert canary["total_calls"] == 144
    assert canary["active"] is False
    assert "SUPERSEDED BEFORE CALLS" in canary["purpose"]
    assert protocol["full_g0_after_canary"]["additional_calls"] == 378
    assert protocol["full_g0_after_canary"]["active"] is False
    assert "superseded" in protocol["authorization"]


def test_fair_selection_retains_itt_and_does_not_rehabilitate_nemotron_subset() -> None:
    protocol = _protocol()
    assert protocol["selection_set"]["eligible"] == [
        "llama31_8b_incumbent",
        "qwen37_plus_nonthinking",
        "qwen37_plus_thinking_upper_bound",
    ]
    assert protocol["selection_set"]["descriptive_only"] == ["nemotron3_nano_30b_a3b_default_thinking"]
    statistical = " ".join(protocol["fairness_dimensions"]["statistical_fairness"])
    assert "ITT" in statistical and "complete-case deletion" in statistical
