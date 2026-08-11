from __future__ import annotations

import json
from pathlib import Path

import pytest

from metacom_pm.v1_5_v5_3_public_backbone import (
    PublicBackboneFreeze,
    audit_public_backbone,
    build_public_backbone_freeze,
)


ROOT = Path(__file__).resolve().parents[1]


def _audit():
    return audit_public_backbone(
        evoemo_path=ROOT / "data/external/evo_emo.json",
        esconv_path=ROOT / "data/external/ESConv.json",
        esconv_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )


AUDIT = _audit()


def test_public_backbone_quarantines_all_evoemo_esconv_seeds() -> None:
    audit = AUDIT
    source = audit["source_snapshot"]
    assert source["evoemo_users"] == 18
    assert source["evoemo_unique_esconv_seed_ids"] == 84
    assert source["esconv_quarantined_seed_ids"] == 84
    assert source["esconv_eligible_after_quarantine"] == 1216


def test_public_backbone_has_strict_public_candidate_lower_bounds() -> None:
    support = AUDIT["candidate_support_lower_bound"]
    assert support["MS"]["users_with_preliminary_actual_rank1"] == 18
    assert support["MS"]["session_local_summary_and_observation_items"] >= 2600
    assert support["ME"]["strict_exact_action_result_items"] >= 20
    assert support["ME"]["users_with_strict_exact_item"] >= 12
    assert support["ME"]["users_with_preliminary_actual_rank1"] == 18
    assert support["MP"]["users_with_preliminary_actual_rank1"] == 18
    assert support["RS"]["seeker_turn_states"] > 18000
    assert support["RS"]["transparent_flags_sufficient_as_only_learned_features"] is False


def test_contract_denies_hindsight_and_does_not_put_cost_in_head_label() -> None:
    contract = build_public_backbone_freeze(AUDIT)
    denied = set(contract.observability_boundary["runtime_denied_evoemo_fields"])
    assert "questions" in denied
    assert "current_unclosed_session.summary" in denied
    assert "current_unclosed_session.observation" in denied
    assert "future_dialog_history[].summary" in denied
    assert contract.effect_estimand["cost_enters_component_training_label"] is False
    assert "tie is zero uplift/0.5" in contract.effect_estimand["quality_target_form"]
    assert contract.qualification_gates["learnability_first_design"][
        "transparent_regex_flags_alone_are_forbidden_for_RS"
    ] is True
    assert contract.historical_exposure["evoemo_pristine_confirmation"] is False


def test_outer_folds_hold_out_each_user_exactly_once() -> None:
    contract = build_public_backbone_freeze(AUDIT)
    held_out = [
        user
        for fold in contract.cross_fitting["outer_folds"]
        for user in fold["held_out_users"]
    ]
    assert len(held_out) == 18
    assert len(set(held_out)) == 18
    assert all(len(fold["held_out_users"]) == 3 for fold in contract.cross_fitting["outer_folds"])
    fold_by_user = {
        user: fold["fold"]
        for fold in contract.cross_fitting["outer_folds"]
        for user in fold["held_out_users"]
    }
    assert fold_by_user["p13"] == fold_by_user["p18"]


def test_contract_identity_detects_drift() -> None:
    contract = build_public_backbone_freeze(AUDIT)
    payload = json.loads(contract.model_dump_json())
    payload["historical_exposure"]["evoemo_pristine_confirmation"] = True
    with pytest.raises(ValueError):
        PublicBackboneFreeze.model_validate(payload)
