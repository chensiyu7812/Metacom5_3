from __future__ import annotations

from metacom_pm.v1_5_paper1_suitability import (
    SUITABILITY_AXES,
    component_qualification,
    derive_suitability,
    gwet_ac1,
    validate_atomic_judgment,
)


def test_projection_is_atomic_and_fail_closed() -> None:
    assert derive_suitability({axis: "YES" for axis in SUITABILITY_AXES}) == (
        "SUITABLE"
    )
    assert derive_suitability(
        {**{axis: "YES" for axis in SUITABILITY_AXES}, "current_target_fit": "NO"}
    ) == "NOT_SUITABLE"
    assert derive_suitability(
        {
            **{axis: "YES" for axis in SUITABILITY_AXES},
            "specific_increment_available": "UNKNOWN",
        }
    ) == "UNKNOWN"


def test_atomic_judgment_requires_numbered_evidence_or_explicit_absence() -> None:
    judgment = {
        "axes": {
            axis: {
                "decision": "YES",
                "visible_span_ids": ["V1"],
                "candidate_span_ids": ["C1"],
                "absence_reason_code": None,
                "unknown_reason_code": None,
            }
            for axis in SUITABILITY_AXES
        },
        "derived_suitability": "SUITABLE",
    }
    assert validate_atomic_judgment(
        judgment,
        allowed_visible_span_ids=["V1"],
        allowed_candidate_span_ids=["C1"],
    ) == []
    judgment["axes"]["current_target_fit"]["visible_span_ids"] = []
    judgment["axes"]["current_target_fit"]["candidate_span_ids"] = []
    assert "current_target_fit:resolved_without_evidence_or_absence_reason" in (
        validate_atomic_judgment(
            judgment,
            allowed_visible_span_ids=["V1"],
            allowed_candidate_span_ids=["C1"],
        )
    )


def test_gwet_ac1_handles_prevalence_without_nan() -> None:
    assert gwet_ac1(["YES"] * 10, ["YES"] * 10) == 1.0
    value = gwet_ac1(
        ["YES"] * 9 + ["NO"],
        ["YES"] * 8 + ["NO", "NO"],
    )
    assert 0.0 < value < 1.0


def test_component_gate_requires_reliability_and_bidirectional_groups() -> None:
    rows = []
    for index in range(16):
        label = "SUITABLE" if index < 8 else "NOT_SUITABLE"
        axes = (
            {axis: "YES" for axis in SUITABILITY_AXES}
            if label == "SUITABLE"
            else {
                **{axis: "YES" for axis in SUITABILITY_AXES},
                "current_target_fit": "NO",
            }
        )
        rows.append(
            {
                "split_group_key": f"g{index}",
                "reviewer_a_axes": axes,
                "reviewer_b_axes": axes,
                "reviewer_a_derived": label,
                "reviewer_b_derived": label,
            }
        )
    report = component_qualification(rows)
    assert report["status"] == "QUALIFIED"
    assert report["suitable_independent_groups"] == 8
    assert report["not_suitable_independent_groups"] == 8

    rows[-1]["split_group_key"] = "g8"
    failed = component_qualification(rows)
    assert failed["status"] == "FAILED_FIXED_OFF"
    assert "not_suitable_independent_group_support" in failed["failed_checks"]
