import json
from pathlib import Path

from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate
from metacom_pm.v1_5_v5_3_public_formal_manifest import RS_MOVE_QUOTAS


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809"


def _rows():
    return [
        json.loads(line)
        for line in (OUT / "effect_group_manifest_private.jsonl").read_text().splitlines()
        if line.strip()
    ]


def test_frozen_formal_manifest_passes_all_pre_effect_checks():
    audit = json.loads((OUT / "audit.json").read_text())
    contract = json.loads((OUT / "contract.json").read_text())
    tracked = json.loads(
        (ROOT / "data/pm_v1_5_contracts/v5_3_public_formal_effect_manifest_v1.json").read_text()
    )
    assert audit["status"] == "PASS"
    assert all(audit["checks"].values())
    assert contract == tracked
    assert contract["status"] == "PRE_EFFECT_FROZEN"
    assert contract["live_execution_allowed"] is False
    assert contract["call_budget"]["automatic_risk_judge_calls"] == 0


def test_formal_manifest_has_exact_user_dialogue_and_move_support():
    rows = _rows()
    assert len(rows) == 576
    for component in ("MP", "MS", "ME"):
        component_rows = [row for row in rows if row["component"] == component]
        assert len(component_rows) == 144
        users = {row["user_id"] for row in component_rows}
        assert len(users) == 18
        assert all(sum(row["user_id"] == user for row in component_rows) == 8 for user in users)
    rs_rows = [row for row in rows if row["component"] == "RS"]
    assert len({row["dialogue_id"] for row in rs_rows}) == 144
    assert {
        move: sum(row["candidate_type"] == move for row in rs_rows)
        for move in RS_MOVE_QUOTAS
    } == RS_MOVE_QUOTAS


def test_every_formal_candidate_is_typed_and_outcome_blind():
    for row in _rows():
        TypedResourceCandidate(**row["candidate"])
        assert row["outcome_or_response_read"] is False
        assert row["development_state_excluded_before_selection"] is True
        assert len(row["paired_generator_seeds"]) == 3
