from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_private_20260812"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _keys(nested)


def test_repair_packet_is_exact_blind_and_nonexclusive() -> None:
    packet = _jsonl(PUBLIC / "ms_reannotation_packet_blind.jsonl")
    private = _jsonl(PRIVATE / "ms_reannotation_private_key.jsonl")
    assert len(packet) == len(private) == 201
    assert len({row["repair_item_id"] for row in packet}) == 201
    assert {row["repair_item_id"] for row in packet} == {
        row["repair_item_id"] for row in private
    }
    forbidden = {
        "teacher_decision",
        "binary_suitability_label",
        "selection_score",
        "outer_fold",
        "runtime_owner_key",
        "split_group_key",
        "state_id",
        "actual_rank1_id",
        "gold_decision",
    }
    assert not (forbidden & set().union(*(set(_keys(row)) for row in packet)))
    assert all(
        row["decision_contract"]["no_single_memory_cap"] is True
        and row["decision_contract"]["sixteen_requested_actions_unchanged"] is True
        for row in packet
    )


def test_fixed_controls_are_balanced_and_never_training() -> None:
    public = _jsonl(PUBLIC / "qualification_controls_blind.jsonl")
    private = _jsonl(PRIVATE / "qualification_control_key.jsonl")
    assert len(public) == len(private) == 12
    assert all(row["not_training"] is True for row in private)
    counts = {}
    for row in private:
        decision = row["expected_final_suitability"]
        counts[decision] = counts.get(decision, 0) + 1
        assert row["candidate_increment"]
        assert row["allowed_response_change"]
        assert row["forbidden_focus_shift"]
        assert row["nonuse_condition"]
    assert counts == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2}
    assert all("expected_final_suitability" not in set(_keys(row)) for row in public)


def test_old_labels_are_not_misrepresented_as_repaired_gold() -> None:
    profile = json.loads((PUBLIC / "data_quality_profile.json").read_text(encoding="utf-8"))
    completeness = profile["new_construct_completeness_before_reannotation"]
    assert completeness["complete_rows"] == 0
    assert completeness["complete_rate"] == 0.0
    assert profile["source_integrity"]["one_to_one_join_rate"] == 1.0
    assert profile["stable_machine_audit_flags_not_gold"]["warning"].endswith(
        "never auto-create or flip repaired gold."
    )


def test_authority_has_one_current_execution_pointer() -> None:
    authority = json.loads(
        (ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json").read_text(
            encoding="utf-8"
        )
    )
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    assert alias["compatibility_alias_of"] == "current_execution_phase"
    assert alias["id"] == current["id"]
    assert current["id"] == "MS_CONSTRUCT_CORRECTED_ROUTE_REOPENED_FRESH_ANCHOR_SET_NEXT"
    assert alias["active_phase_manifest"] == current["active_phase_manifest"]
    assert authority["current_phase"]["historical_only"] is True
    assert authority["current_phase"]["must_not_route_execution"] is True
