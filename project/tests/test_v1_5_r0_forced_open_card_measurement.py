from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OLD = ROOT / "outputs/pm_v1_5_paper1_v3_r0_function_closure_diagnostic_20260811"
NEW = ROOT / "outputs/pm_v1_5_paper1_v3_r0_function_forced_open_card_closure_diagnostic_v2_20260811"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_r0_function_packet_is_byte_identical_to_v1() -> None:
    for name in ("r0_function_blind.jsonl", "r0_function_private_key.jsonl"):
        assert sha(OLD / name) == sha(NEW / name)


def test_closure_packet_is_forced_card_not_learned_rs() -> None:
    blind = rows(NEW / "forced_open_card_closure_quality_blind.jsonl")
    private = rows(NEW / "forced_open_card_closure_quality_private_key.jsonl")
    audit = rows(NEW / "closure_actual_rank1_audit.jsonl")

    assert len(blind) == len(private) == len(audit) == 2
    assert all("forced-open-card-vs-r0" in x["protocol"] for x in blind)
    assert all("not a learned-RS policy evaluation" in x["decision"]["claim_boundary"] for x in blind)
    assert all(x["actual_RS_rank1"]["move_id"] == "AM01_invite_open_expression" for x in private)
    assert all(x["actual_RS_rank1"]["selection_mode"] == "lexical_fallback" for x in private)
    assert all(x["actual_RS_rank1"]["transparent_rule_on"] is False for x in private)
    assert all(x["learned_RS_checkpoint_available_for_this_surface"] is False for x in private)
    assert all(x["all_observable_opportunity_flags_false"] is True for x in audit)


def test_five_layer_contract_separates_measurement_and_cost() -> None:
    contract = json.loads(
        (ROOT / "data/pm_v1_5_contracts/paper1_v3_five_layer_measurement_contract_v1.json").read_text(encoding="utf-8")
    )
    assert [x["id"] for x in contract["layers"]] == [
        "CANDIDATE_SUITABILITY",
        "RESPONSE_ACT_FIT",
        "COMPONENT_FUNCTION",
        "RESPONSE_OUTCOME",
        "COST",
    ]
    function = contract["layers"][2]
    assert "There is no default one-memory-contribution cap" in function["multi_component_rule"]
    cost = contract["layers"][4]
    assert {"provider_input_tokens", "provider_output_tokens", "latency_ms", "usd"}.issubset(cost["required_fields"])
    assert "Cost never changes" in cost["rule"]


def test_corrected_phase_authorizes_no_execution_or_refit() -> None:
    phase = json.loads(
        (ROOT / "data/pm_v1_5_contracts/paper1_v3_r0_function_forced_open_card_measurement_phase_v2.json").read_text(encoding="utf-8")
    )
    assert phase["diagnostic"]["forced_open_card_closure"]["compatible_full_fit_RS_checkpoint_exists"] is False
    assert phase["authorization"]["API_calls"] == 0
    assert phase["authorization"]["response_generation"] is False
    assert phase["authorization"]["PM_refit"] is False
    assert phase["authorization"]["training_label_creation"] is False
