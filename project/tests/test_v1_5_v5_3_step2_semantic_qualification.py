from __future__ import annotations

import pytest

from metacom_pm.contracts import ALL_ACTION_IDS
from metacom_pm.v1_5_v5_3_step2_semantic_qualification import (
    SemanticQualificationPlan,
    build_semantic_qualification_plan,
    semantic_qualification_programs,
    semantic_qualification_surface_rows,
)


def test_semantic_plan_crosses_four_families_with_all_actions() -> None:
    plan = build_semantic_qualification_plan()
    assert plan.family_count == 4
    assert plan.action_count == 16
    assert plan.logical_call_count == 64
    assert plan.endpoint_or_model_selected is False
    by_family = {}
    for case in plan.cases:
        by_family.setdefault(case.semantic_family, []).append(case.action_id)
        assert case.recovery_policy == "deterministic_fallback"
        assert case.excluded_from_fit_confirmation_external is True
    assert len(by_family) == 4
    assert all(actions == list(ALL_ACTION_IDS) for actions in by_family.values())


def test_semantic_plan_identity_detects_message_drift() -> None:
    plan = build_semantic_qualification_plan()
    assert SemanticQualificationPlan.model_validate_json(plan.model_dump_json()) == plan
    changed = plan.model_dump(mode="json")
    changed["cases"][0]["messages"][1]["content"] += " changed"
    with pytest.raises(ValueError):
        SemanticQualificationPlan.model_validate(changed)


def test_semantic_surface_rows_exclude_prompt_boilerplate() -> None:
    rows = semantic_qualification_surface_rows()
    assert len(rows) == 4 * 9
    assert len({row["surface_id"] for row in rows}) == len(rows)
    assert all("backend" not in row["text"].casefold() for row in rows)


def test_every_frozen_case_rehydrates_its_exact_typed_program() -> None:
    plan = build_semantic_qualification_plan()
    programs = semantic_qualification_programs()
    assert set(programs) == {case.case_id for case in plan.cases}
    for case in plan.cases:
        assert programs[case.case_id].requested_action_id == case.action_id
        assert [item.evidence_id for item in programs[case.case_id].evidence] == case.evidence_ids
