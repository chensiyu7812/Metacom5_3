from __future__ import annotations

from metacom_pm.v1_5_v5_3_identifiability import audit_identifiability


def _row(component: str, user: str, group: str, condition: str, value: float):
    return {
        "model_input": {
            "component": component,
            "contribution_slots": {
                "candidate_present": True,
                "signal": value,
                "constant": 1,
            },
        },
        "state": {
            "catalog_user_id": user,
            "counterfactual_group_id": group,
            "semantic_family": f"{component.lower()}::family",
            "state_condition": condition,
        },
    }


def test_identifiability_uses_user_and_group_not_raw_rows_as_support() -> None:
    rows = []
    for component in ("MP", "MS", "ME", "RS"):
        for index in range(10):
            rows.append(
                _row(
                    component,
                    f"u{index // 2}",
                    f"{component}-g{index // 2}",
                    "positive" if index % 2 else "negative",
                    float(index % 3),
                )
            )
    report = audit_identifiability(rows)
    assert report["rows"] == 40
    assert report["unique_users"] == 5
    for component in ("MP", "MS", "ME", "RS"):
        item = report["per_component"][component]
        assert item["rows"] == 10
        assert item["unique_users"] == 5
        assert item["unique_counterfactual_groups"] == 5
        assert "constant" in item["constant_feature_columns"]
        assert item["formal_power"] == "PENDING_PAIRED_EFFECT_LABELS_AND_FINAL_USER_SPLIT"
    assert report["sample_size_rule"]["reference_plus_minus_0_05_margin_is_binary_learning_gate"] is False
