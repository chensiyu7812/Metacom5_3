"""Field-type realization templates for the MP (profile) resource delta.

MP's candidate space is a small closed set of six non-name EvoEmo basic_info
field types (``MP_PROFILE_SCOPE_V1`` in ``v1_5_paper1_rank1.py``), never a
per-case free-text fact the way MS/ME candidates are. This makes a field-type
level realization template both sufficient and appropriate: the same six
templates apply to every user, and none may mention a literal field value
(age number, school name, job title, city, ...), matching the "profile is
not an identity feature" boundary (``paper1_memory_head_rescue_decision_v2
.json``) and the compiler's "never recite it" instruction.

Root-cause context this module fixes: the pre-repair measurement found MP
functional realization at only 5/128 ("practical constraint mostly only
declared, never changing the reply" -- V15-ARCH-28). ``PlannedV3Resource
.allowed_response_change`` is what the V4 compiler surfaces to the generator
as the concrete, bounded instruction for how a resource may change the reply
(see ``_resource_delta``'s ``common`` string in
``v1_5_response_program_v4.py``); MS has always had case-specific authored
content there (e.g. ``232l_run_paper1_v3_ms_executor_qualification_v1_5.py``,
``266l_materialize_paper1_ms_final_control_repair_v1_5.py``), but MP never
did -- every MP resource ever compiled used only a generic validation
placeholder (``f"bounded {component} response change"``,
``202l_validate_paper1_component_general_v3_g2_v1_5.py``), which gives the
generator nothing concrete to act on. This module is the missing content.
"""

from __future__ import annotations

from typing import Mapping

from .v1_5_paper1_rank1 import MP_PROFILE_SCOPE_V1


class MPFieldRealizationTemplate:
    __slots__ = ("meaning_cue", "allowed_response_change", "forbidden_inference")

    def __init__(self, meaning_cue: str, allowed_response_change: str, forbidden_inference: str) -> None:
        self.meaning_cue = meaning_cue
        self.allowed_response_change = allowed_response_change
        self.forbidden_inference = forbidden_inference


MP_FIELD_REALIZATION_TEMPLATES_V1: Mapping[str, MPFieldRealizationTemplate] = {
    "age": MPFieldRealizationTemplate(
        meaning_cue="The user's age or life-stage context is known.",
        allowed_response_change=(
            "If the current topic involves an age-linked practical detail (school versus "
            "workplace framing, retirement, a generational gap with family), let the known "
            "life stage silently shape which scenario or wording the reply assumes -- never "
            "state or imply a specific age, birth year, or generation label."
        ),
        forbidden_inference=(
            "Do not infer maturity, competence, health, independence, or priorities from age; "
            "do not use age to explain or excuse the user's feelings or problem."
        ),
    ),
    "education": MPFieldRealizationTemplate(
        meaning_cue="The user's education or school status is known.",
        allowed_response_change=(
            "If the reply would otherwise offer a generic next step (find a mentor, take a "
            "class, talk to an advisor), let the known education context make that suggestion "
            "concretely fitting (campus resource versus workplace resource, student schedule "
            "versus work schedule) without naming the school, degree, or subject."
        ),
        forbidden_inference=(
            "Do not infer intelligence, class background, career trajectory, or future success "
            "from education status."
        ),
    ),
    "gender": MPFieldRealizationTemplate(
        meaning_cue="The user's gender identity is known.",
        allowed_response_change=(
            "Use it only to keep pronouns and self-reference consistent with how the user "
            "already refers to themselves; it may never change the substance of advice, "
            "assumed interests, or emotional framing."
        ),
        forbidden_inference=(
            "Do not infer interests, communication style, emotional needs, or social roles "
            "from gender."
        ),
    ),
    "job": MPFieldRealizationTemplate(
        meaning_cue="The user's job or employment status is known.",
        allowed_response_change=(
            "If the current topic involves scheduling, logistics, or the feasibility of a "
            "suggestion (timing of a coping activity, workplace-specific stress, availability "
            "during the day), let the known work context silently shape a concretely feasible "
            "timing, format, or logistic detail -- without stating the job title, employer, or "
            "industry."
        ),
        forbidden_inference=(
            "Do not infer income, social status, competence, or stress level from job type."
        ),
    ),
    "location": MPFieldRealizationTemplate(
        meaning_cue="The user's location or locale context is known.",
        allowed_response_change=(
            "If the topic involves in-person resources, local logistics, or travel and "
            "commute time, let the known location silently shape logistic feasibility (a local "
            "versus remote option, travel time) without naming the city, region, or country."
        ),
        forbidden_inference=(
            "Do not infer culture, values, safety, cost of living, or lifestyle from location."
        ),
    ),
    "nationality": MPFieldRealizationTemplate(
        meaning_cue="The user's nationality, culture, or language background is known.",
        allowed_response_change=(
            "Only silently avoid a suggestion that assumes a mismatched cultural, legal, or "
            "administrative context (a resource, holiday, or institution specific to a "
            "different country) -- never mention nationality, culture, or language explicitly."
        ),
        forbidden_inference=(
            "Do not infer values, family structure, religion, or communication style from "
            "nationality."
        ),
    ),
}


def _check_coverage() -> None:
    scope_fields = set(MP_PROFILE_SCOPE_V1)
    template_fields = set(MP_FIELD_REALIZATION_TEMPLATES_V1)
    if scope_fields != template_fields:
        raise ValueError(
            "MP field realization templates must cover exactly MP_PROFILE_SCOPE_V1: "
            f"missing={sorted(scope_fields - template_fields)}, "
            f"extra={sorted(template_fields - scope_fields)}"
        )


_check_coverage()


def mp_realization_template(profile_field: str) -> MPFieldRealizationTemplate:
    if profile_field not in MP_FIELD_REALIZATION_TEMPLATES_V1:
        raise ValueError(f"unfrozen MP profile field: {profile_field!r}")
    return MP_FIELD_REALIZATION_TEMPLATES_V1[profile_field]
