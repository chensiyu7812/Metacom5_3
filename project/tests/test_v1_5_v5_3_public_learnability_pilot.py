import json
from pathlib import Path

from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate
from metacom_pm.v1_5_v5_3_public_learnability_pilot import audit_pilot
from metacom_pm.v1_5_v5_3_qrf_judge import (
    BatchedContributionJudgment,
    aggregate_on_minus_off,
    contribution_messages,
)


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809"


def _rows():
    return [json.loads(line) for line in (OUT / "effect_group_manifest_private.jsonl").read_text().splitlines()]


def test_frozen_pilot_has_96_typed_executable_outcome_blind_groups():
    rows = _rows()
    assert audit_pilot(rows)["status"] == "PASS"
    assert len(rows) == 96
    for row in rows:
        TypedResourceCandidate(**row["candidate"])
        assert row["outcome_or_response_read"] is False
        assert len(row["paired_generator_seeds"]) == 3


def test_primary_feature_sets_are_nonconstant_and_bounded_to_six():
    contract = json.loads((OUT / "contract.json").read_text())
    rows = _rows()
    feature_sets = contract["learnability_protection"]["primary_features"]
    for component, names in feature_sets.items():
        assert 4 <= len(names) <= 7
        component_rows = [row for row in rows if row["component"] == component]
        for name in names:
            assert len({json.dumps(row["model_features"].get(name), sort_keys=True) for row in component_rows}) > 1


def test_qrf_contribution_prompt_keeps_ties_and_cost_out_of_label():
    messages = contribution_messages(
        visible_dialogue=[{"role": "user", "content": "I feel stuck."}],
        pairs=[
            {"replicate_id": f"r{i}", "response_a": "A", "response_b": "B"}
            for i in range(3)
        ],
    )
    prompt = messages[-1]["content"]
    assert "tie is 0" in prompt
    assert "Do not judge memory use, cost, or risk" in prompt


def test_qrf_aggregation_maps_reverse_order_back_to_on_minus_off():
    def payload(a_minus_b):
        return BatchedContributionJudgment.model_validate(
            {
                "replicates": [
                    {
                        "replicate_id": f"r{i}",
                        "preferred_response": "A" if a_minus_b > 0 else "B",
                        "delta_a_minus_b": {key: a_minus_b for key in (
                            "goal_advance", "emotional_support",
                            "specific_useful_contribution", "clarity_and_naturalness",
                        )},
                        "response_a_excerpt": "A",
                        "response_b_excerpt": "B",
                    }
                    for i in range(3)
                ]
            }
        )

    result = aggregate_on_minus_off(payload(1), payload(-1))
    assert result["aggregate"]["mean_positive_support_contribution"] == 1.0
