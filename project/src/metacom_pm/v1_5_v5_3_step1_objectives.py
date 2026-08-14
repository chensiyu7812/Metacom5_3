"""Pre-effect Step1 estimands for V5.3.

The policy manager does not learn from a reviewer-authored ``should open``
bit.  It learns the requested-component ITT under one frozen executor while
preserving quality, material risk, functional use, and cost as separate
measurements.  Each of MP/MS/ME/RS is one low-capacity *component bundle*:
the primary adoptable-opening model plus a risk auxiliary when the event
support is sufficient.  Incremental token cost is known at routing time and
is never predicted from outcome labels.

This module is deliberately outcome-blind.  It freezes how future paired
measurements are converted into targets; it does not read any reply or label.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from .contracts import StrictModel
from .io import canonical_json, stable_hex


STEP1_OBJECTIVE_PROTOCOL = "pm-v1.5-v5.3-step1-multiobjective-estimand-v1"


class Step1ObjectiveFreeze(StrictModel):
    protocol: Literal[
        "pm-v1.5-v5.3-step1-multiobjective-estimand-v1"
    ] = STEP1_OBJECTIVE_PROTOCOL
    status: Literal["PRE_EFFECT_ESTIMANDS_FROZEN"] = "PRE_EFFECT_ESTIMANDS_FROZEN"
    components: list[str]
    treatment_estimand: str
    primary_component_bundle: dict[str, object]
    independent_measurements: dict[str, object]
    target_derivation: dict[str, object]
    joint_projection: dict[str, object]
    risk_policy: dict[str, object]
    uncertainty_policy: dict[str, object]
    evidence_levels: dict[str, object]
    forbidden_shortcuts: list[str]
    generated_response_or_quality_risk_outcome_read: Literal[False] = False
    api_calls: Literal[0] = 0
    freeze_identity: str = Field(pattern=r"^v53step1obj_[0-9a-f]{24}$")

    @model_validator(mode="after")
    def coherent(self):
        if self.components != ["MP", "MS", "ME", "RS"]:
            raise ValueError("component order must remain MP/MS/ME/RS")
        if self.independent_measurements.get("cost_is_learned") is not False:
            raise ValueError("incremental cost is runtime-known, not an outcome head")
        if self.target_derivation.get("construction_condition_is_gold") is not False:
            raise ValueError("construction condition must never become worth-opening gold")
        if self.uncertainty_policy.get("force_uncertain_to_binary") is not False:
            raise ValueError("uncertain outcomes must not be silently forced to binary")
        payload = self.model_dump(mode="json", exclude={"freeze_identity"})
        expected = "v53step1obj_" + stable_hex(canonical_json(payload), n=24)
        if self.freeze_identity != expected:
            raise ValueError("freeze_identity does not match Step1 objective content")
        return self


def build_step1_objective_freeze() -> Step1ObjectiveFreeze:
    payload = {
        "protocol": STEP1_OBJECTIVE_PROTOCOL,
        "status": "PRE_EFFECT_ESTIMANDS_FROZEN",
        "components": ["MP", "MS", "ME", "RS"],
        "treatment_estimand": (
            "requested-component intention-to-treat effect under the frozen V5.3 "
            "candidate layer, typed executor, generator, guard, and deterministic fallback"
        ),
        "primary_component_bundle": {
            "count": 4,
            "model_family": "component_specific_low_capacity_regularized_models",
            "primary_output": "probability_of_adoptable_opening",
            "adoptable_opening_requires": [
                "on_arm_materially_better_than_off_arm",
                "on_arm_has_no_material_risk",
                "requested_resource_functionally_contributes",
                "assignment_and_binding_are_valid",
            ],
            "risk_auxiliary": (
                "component_specific_probability_of_material_risk_when_event_support_is_sufficient; "
                "otherwise abstain and retain structural vetoes"
            ),
            "functional_use_is": "mechanism_target_and_diagnostic_not_a_runtime_post_treatment_feature",
        },
        "independent_measurements": {
            "quality": "on_better|off_better|tie|uncertain",
            "material_risk": "separate_on_arm_and_off_arm_events_plus_incremental_difference",
            "functional_use": "yes|no|uncertain_per_requested_component",
            "cost": "observed_incremental_input_tokens_and_total_call_cost",
            "cost_is_learned": False,
            "fallback": "valid_ITT_outcome_not_missing_data",
        },
        "target_derivation": {
            "positive": (
                "quality=on_better AND on_material_risk=no AND functional_use=yes"
            ),
            "negative": (
                "quality=off_better OR on_material_risk=yes OR functional_use=no"
            ),
            "uncertain": (
                "quality=tie/uncertain, risk uncertain, reviewer disagreement, or both arms fail "
                "without an attributable component direction"
            ),
            "construction_condition_is_gold": False,
            "candidate_eligibility_is_gold": False,
            "generator_failure_is_dropped": False,
            "mechanically_invalid_assignment_or_missing_physical_output_is_dropped": True,
        },
        "joint_projection": {
            "legal_actions": 16,
            "m0_r0_is_normal_action": True,
            "score": (
                "sum of selected component adoptable-opening values minus deterministic "
                "incremental-token penalty and pre-frozen interaction penalties"
            ),
            "cost_source": "runtime candidate serialization plus observed recovery accounting",
            "risk_veto": (
                "reject an action when a calibrated risk auxiliary exceeds its development "
                "threshold; if sparse, do not invent a probability and use only structural vetoes"
            ),
            "interaction_terms_estimated_only_from": "coherent paired multi-component states",
        },
        "risk_policy": {
            "quality_or_cost_can_cancel_material_misuse": False,
            "critical_events": [
                "fabricated_recall",
                "wrong_owner_personalization",
                "explicit_boundary_violation",
            ],
            "critical_events_reported_individually": True,
            "risk_auxiliary_minimum_support_frozen_after_label_shape_audit": True,
        },
        "uncertainty_policy": {
            "force_uncertain_to_binary": False,
            "training_use": "exclude_from_primary_binary_loss_or use predeclared low-weight soft target",
            "calibration_use": "retain for abstention and sensitivity analysis",
            "report_raw_counts": True,
        },
        "evidence_levels": {
            "SUPPORTED": "point estimate and interval satisfy the reference comparison",
            "DIRECTIONALLY_USABLE": (
                "nontrivial learned selection and practically acceptable point estimate, but "
                "the cluster interval is too wide for the reference margin"
            ),
            "NOT_SUPPORTED": (
                "constant-action collapse, failure to beat matched controls, materially worse "
                "quality point estimate, or no interpretable component support"
            ),
            "narrow_noninferiority_interval_required_to_call_pm_learned": False,
        },
        "forbidden_shortcuts": [
            "collapse_quality_risk_and_cost_into_an_unrecorded_reviewer_weight",
            "use_post_treatment_function_or_risk_as_runtime_input",
            "treat_candidate_absence_or_rank1_retrieval_failure_as_pm_off_gold",
            "treat_tie_as_positive_only_to_balance_classes",
            "tune_lambda_or_risk_threshold_on_confirmation_or_external_outcomes",
        ],
        "generated_response_or_quality_risk_outcome_read": False,
        "api_calls": 0,
    }
    payload["freeze_identity"] = "v53step1obj_" + stable_hex(
        canonical_json(payload), n=24
    )
    return Step1ObjectiveFreeze.model_validate(payload)
