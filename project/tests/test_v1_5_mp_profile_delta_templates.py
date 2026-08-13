from __future__ import annotations

import pytest

from metacom_pm.v1_5_component_general_v3 import V3Candidate, build_component_general_plan_v3
from metacom_pm.v1_5_mp_profile_delta_templates_v1 import (
    MP_FIELD_REALIZATION_TEMPLATES_V1,
    mp_realization_template,
)
from metacom_pm.v1_5_paper1_rank1 import MP_PROFILE_SCOPE_V1
from metacom_pm.v1_5_response_program_v4 import response_generation_messages_v4


def test_templates_cover_exactly_the_frozen_mp_profile_scope_fields():
    assert set(MP_FIELD_REALIZATION_TEMPLATES_V1) == set(MP_PROFILE_SCOPE_V1)


def test_every_template_is_real_content_not_a_placeholder():
    for field, template in MP_FIELD_REALIZATION_TEMPLATES_V1.items():
        assert len(template.meaning_cue) > 20
        assert len(template.allowed_response_change) > 60
        assert len(template.forbidden_inference) > 20
        assert "bounded" not in template.allowed_response_change.lower()


def test_unknown_field_raises():
    with pytest.raises(ValueError):
        mp_realization_template("not_a_real_field")


def test_template_content_reaches_the_compiled_prompt():
    template = mp_realization_template("job")
    candidate = V3Candidate(
        component="MP",
        evidence_id="evidence-mp-job",
        meaning_cue=template.meaning_cue,
        exact_source="job: (redacted for audit-only field)",
        owner_id="owner-1",
        time_status="STRICTLY_PAST",
        allowed_response_change=template.allowed_response_change,
        forbidden_inference=template.forbidden_inference,
    )
    plan = build_component_general_plan_v3(
        requested_action_id="MP+R0",
        current_user_id="owner-1",
        candidates={"MP": candidate, "MS": None, "ME": None, "RS": None},
    )
    prompt = response_generation_messages_v4(
        current_context="I feel stuck today.",
        current_goal="Offer grounded support.",
        plan=plan,
    )[0]["content"]
    assert "scheduling, logistics, or the feasibility" in prompt
    assert "income, social status, competence" in prompt
    assert "decide CONSTRAIN or IGNORE" in prompt
