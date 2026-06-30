from metacom_pm.evo_response_v4 import (
    DEFAULT_RESPONSE_V4_CONDITIONS,
    EvoResponseV4CandidateScore,
    EvoResponseV4Judgment,
    _candidate_id_validator,
    _validate_response_v4_outputs,
    balanced_candidate_order,
)
from metacom_pm.io import write_jsonl


def test_balanced_candidate_order_cycles_each_condition_through_each_position():
    conditions = DEFAULT_RESPONSE_V4_CONDITIONS
    for variant in (0, 1):
        positions = [set() for _ in conditions]
        for unit_ordinal in range(len(conditions)):
            order = balanced_candidate_order(
                conditions,
                unit_ordinal=unit_ordinal,
                order_variant=variant,
            )
            for index, condition in enumerate(order):
                positions[index].add(condition)
        assert all(position == set(conditions) for position in positions)


def test_candidate_id_validator_rejects_missing_candidate():
    parsed = EvoResponseV4Judgment(
        candidates=[
            EvoResponseV4CandidateScore(
                candidate_id="C1",
                emotional_support=3,
                personalization=3,
                memory_appropriateness=3,
                factual_grounding=3,
                temporal_consistency=3,
                non_intrusiveness=3,
                overall=3,
                reason="ok",
            )
        ]
    )
    validator = _candidate_id_validator({"C1", "C2"})
    try:
        validator(parsed)
    except ValueError as exc:
        assert "candidate ID mismatch" in str(exc)
    else:
        raise AssertionError("validator accepted a missing candidate")


def test_validate_response_v4_outputs_rejects_missing_score_row(tmp_path):
    conditions = ("pm", "strong_rule")
    unit = {"unit_id": "unit_test"}
    judgment_path = tmp_path / "judgments.jsonl"
    score_path = tmp_path / "scores.jsonl"
    raw_path = tmp_path / "raw.jsonl"
    write_jsonl(
        judgment_path,
        [
            {
                "unit_id": "unit_test",
                "order_variant": 0,
                "scores": [
                    {
                        "candidate_id": "C1",
                        "emotional_support": 3,
                        "personalization": 3,
                        "memory_appropriateness": 3,
                        "factual_grounding": 3,
                        "temporal_consistency": 3,
                        "non_intrusiveness": 3,
                        "overall": 3,
                        "reason": "ok",
                    },
                    {
                        "candidate_id": "C2",
                        "emotional_support": 3,
                        "personalization": 3,
                        "memory_appropriateness": 3,
                        "factual_grounding": 3,
                        "temporal_consistency": 3,
                        "non_intrusiveness": 3,
                        "overall": 3,
                        "reason": "ok",
                    },
                ],
                "candidate_mapping": {
                    "C1": {"condition": "pm", "position": 1},
                    "C2": {"condition": "strong_rule", "position": 2},
                },
            }
        ],
    )
    write_jsonl(
        score_path,
        [
            {
                "unit_id": "unit_test",
                "order_variant": 0,
                "condition": "pm",
                "candidate_id": "C1",
                "position": 1,
                "emotional_support": 3,
                "personalization": 3,
                "memory_appropriateness": 3,
                "factual_grounding": 3,
                "temporal_consistency": 3,
                "non_intrusiveness": 3,
                "overall": 3,
                "reason": "ok",
            }
        ],
    )
    write_jsonl(
        raw_path,
        [
            {
                "unit_id": "unit_test",
                "order_variant": 0,
                "validated": {"candidates": []},
                "error": None,
            }
        ],
    )
    result = _validate_response_v4_outputs(
        score_path=score_path,
        judgment_path=judgment_path,
        raw_path=raw_path,
        expected_units=[unit],
        order_variants=[0],
        conditions=conditions,
    )
    assert not result["ok"]
    assert any("missing score keys" in error for error in result["errors"])
