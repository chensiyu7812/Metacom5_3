"""Fail-closed measurement primitives for the post-formal V5.3 repair.

This module deliberately separates five facts that the original formal runner
partly conflated: candidate validity, PM opportunity, executor realization,
guard correctness, and the deployed response outcome.  It does not infer a
semantic gold label from a quality score or from candidate presence.
"""

from __future__ import annotations

from enum import Enum


class CandidateTruth(str, Enum):
    VALID_APPLICABLE = "VALID_APPLICABLE"
    VALID_REDUNDANT = "VALID_REDUNDANT"
    VALID_NOT_USEFUL = "VALID_NOT_USEFUL"
    INVALID_WRONG_OWNER_TIME_EVENT = "INVALID_WRONG_OWNER_TIME_EVENT"
    UNRESOLVED = "UNRESOLVED"


class OpportunityTruth(str, Enum):
    ON_ONLY = "ON_ONLY"
    OFF_ONLY = "OFF_ONLY"
    EITHER = "EITHER"
    UNRESOLVED = "UNRESOLVED"


class FinalExecutionTruth(str, Enum):
    FUNCTIONAL = "FUNCTIONAL"
    SURFACE_ECHO_ONLY = "SURFACE_ECHO_ONLY"
    NOT_USED_FINAL = "NOT_USED_FINAL"
    BOUNDARY_FAILURE = "BOUNDARY_FAILURE"
    PENDING_SEMANTIC_REVIEW = "PENDING_SEMANTIC_REVIEW"


class RawExecutionTruth(str, Enum):
    PRESENT_REVIEW_REQUIRED = "PRESENT_REVIEW_REQUIRED"
    UNRESOLVED_RAW_MISSING = "UNRESOLVED_RAW_MISSING"


class GuardTruth(str, Enum):
    TRUE_ACCEPT = "TRUE_ACCEPT"
    TRUE_REJECT = "TRUE_REJECT"
    FALSE_ACCEPT = "FALSE_ACCEPT"
    FALSE_REJECT = "FALSE_REJECT"
    PENDING_SEMANTIC_REVIEW = "PENDING_SEMANTIC_REVIEW"
    UNRESOLVED_RAW_MISSING = "UNRESOLVED_RAW_MISSING"


class ResponsibilityOwner(str, Enum):
    CANDIDATE_LAYER = "CANDIDATE_LAYER"
    PM_STEP1 = "PM_STEP1"
    STEP2_EXECUTOR = "STEP2_EXECUTOR"
    GUARD = "GUARD"
    STEP2_GUARD_SUBSYSTEM_UNRESOLVED = "STEP2_GUARD_SUBSYSTEM_UNRESOLVED"
    RESOURCE_GENERATOR_INTERACTION = "RESOURCE_GENERATOR_INTERACTION"
    MEASUREMENT = "MEASUREMENT"
    FULL_SYSTEM_ITT = "FULL_SYSTEM_ITT"
    UNRESOLVED = "UNRESOLVED"


FALLBACK_STATUS = "fell_back_to_m0"


def derive_execution_truth(
    *, on_status: str, raw_first_pass_saved: bool
) -> tuple[FinalExecutionTruth, RawExecutionTruth, GuardTruth]:
    """Derive only facts justified by persisted runner artifacts.

    A deterministic M0 fallback cannot functionally use an authorized ON-only
    candidate in the final response.  When the rejected first pass was not
    persisted, neither its execution quality nor the guard's semantic decision
    may be reconstructed after the fact.
    """

    if on_status == FALLBACK_STATUS:
        return (
            FinalExecutionTruth.NOT_USED_FINAL,
            (
                RawExecutionTruth.PRESENT_REVIEW_REQUIRED
                if raw_first_pass_saved
                else RawExecutionTruth.UNRESOLVED_RAW_MISSING
            ),
            (
                GuardTruth.PENDING_SEMANTIC_REVIEW
                if raw_first_pass_saved
                else GuardTruth.UNRESOLVED_RAW_MISSING
            ),
        )
    return (
        FinalExecutionTruth.PENDING_SEMANTIC_REVIEW,
        RawExecutionTruth.PRESENT_REVIEW_REQUIRED,
        GuardTruth.PENDING_SEMANTIC_REVIEW,
    )


def semantic_value_label_eligible(
    *,
    candidate_truth: CandidateTruth,
    final_execution_truth: FinalExecutionTruth,
    risk_resolved_safe: bool,
) -> bool:
    """Return whether Q may define a component opportunity label.

    Quality remains a valid deployment-ITT outcome for every completed arm.
    It becomes semantic PM supervision only after candidate applicability,
    functional execution, and risk are independently resolved.
    """

    return (
        candidate_truth is CandidateTruth.VALID_APPLICABLE
        and final_execution_truth is FinalExecutionTruth.FUNCTIONAL
        and risk_resolved_safe
    )


def opportunity_from_quality(
    *, q_uplift: float, eligible: bool, equivalence_margin: float = 0.10
) -> OpportunityTruth:
    if not eligible:
        return OpportunityTruth.UNRESOLVED
    if q_uplift > equivalence_margin:
        return OpportunityTruth.ON_ONLY
    if q_uplift < -equivalence_margin:
        return OpportunityTruth.OFF_ONLY
    return OpportunityTruth.EITHER


def primary_mechanism_owner(
    *,
    candidate_truth: CandidateTruth,
    opportunity_truth: OpportunityTruth,
    requested_on: bool,
    final_execution_truth: FinalExecutionTruth,
    guard_truth: GuardTruth,
) -> ResponsibilityOwner:
    """Return the earliest *supported* failure owner, otherwise UNRESOLVED."""

    if candidate_truth is CandidateTruth.INVALID_WRONG_OWNER_TIME_EVENT:
        return ResponsibilityOwner.CANDIDATE_LAYER
    if opportunity_truth is not OpportunityTruth.UNRESOLVED:
        pm_wrong = (
            opportunity_truth is OpportunityTruth.ON_ONLY and not requested_on
        ) or (opportunity_truth is OpportunityTruth.OFF_ONLY and requested_on)
        if pm_wrong:
            return ResponsibilityOwner.PM_STEP1
    if requested_on and final_execution_truth in {
        FinalExecutionTruth.NOT_USED_FINAL,
        FinalExecutionTruth.SURFACE_ECHO_ONLY,
        FinalExecutionTruth.BOUNDARY_FAILURE,
    }:
        if guard_truth in {GuardTruth.FALSE_ACCEPT, GuardTruth.FALSE_REJECT}:
            return ResponsibilityOwner.GUARD
        return ResponsibilityOwner.STEP2_EXECUTOR
    if candidate_truth is CandidateTruth.UNRESOLVED:
        return ResponsibilityOwner.MEASUREMENT
    return ResponsibilityOwner.UNRESOLVED
