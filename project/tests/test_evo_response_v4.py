from metacom_pm.evo_response_v4 import (
    DEFAULT_RESPONSE_V4_CONDITIONS,
    EvoResponseV4CandidateScore,
    EvoResponseV4Judgment,
    _candidate_id_validator,
    _require_pilot_compatible_with_current_run,
    _validate_response_v4_outputs,
    balanced_candidate_order,
)
from metacom_pm.api import Endpoint
from metacom_pm.io import write_json, write_jsonl


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


def _pilot_summary() -> dict:
    return {
        "protocol": "evoemo_response_v4",
        "mode": "pilot",
        "status": "PASS",
        "judge_model": "gpt-4o",
        "judge_family": "openai_gpt4o",
        "ground_truth_mode": "full",
        "conditions": ["pm", "strong_rule"],
        "turn_indices": [3, 8],
        "generation_freeze_sha256": "generation-freeze",
        "evaluation_freeze_sha256": "evaluation-freeze",
        "thresholds": {
            "max_order_mean_abs_diff": 0.5,
            "max_position_mean_shift": 0.4,
        },
    }


def _endpoint() -> Endpoint:
    return Endpoint(
        base_url="https://api.openai.com/v1",
        model="gpt-4o",
        api_key_env="OPENAI_API_KEY",
        family="openai_gpt4o",
    )


def _check_pilot_summary(path):
    return _require_pilot_compatible_with_current_run(
        path,
        judge_endpoint=_endpoint(),
        ground_truth_mode="full",
        conditions=["pm", "strong_rule"],
        turn_indices=[3, 8],
        generation_freeze_sha256="generation-freeze",
        evaluation_freeze_sha256="evaluation-freeze",
        max_order_mean_abs_diff=0.5,
        max_position_mean_shift=0.4,
    )


def test_require_pilot_compatible_accepts_exact_match(tmp_path):
    path = tmp_path / "pilot_summary.json"
    summary = _pilot_summary()
    write_json(path, summary)

    assert _check_pilot_summary(path) == summary


def test_require_pilot_compatible_rejects_condition_mismatch(tmp_path):
    path = tmp_path / "pilot_summary.json"
    summary = _pilot_summary()
    summary["conditions"] = ["pm", "best_fixed"]
    write_json(path, summary)

    try:
        _check_pilot_summary(path)
    except RuntimeError as exc:
        assert "conditions" in str(exc)
    else:
        raise AssertionError("accepted pilot summary with mismatched conditions")


def test_require_pilot_compatible_rejects_evaluation_freeze_mismatch(tmp_path):
    path = tmp_path / "pilot_summary.json"
    summary = _pilot_summary()
    summary["evaluation_freeze_sha256"] = "older-evaluation-freeze"
    write_json(path, summary)

    try:
        _check_pilot_summary(path)
    except RuntimeError as exc:
        assert "evaluation_freeze_sha256" in str(exc)
    else:
        raise AssertionError("accepted pilot summary with mismatched evaluation freeze")
