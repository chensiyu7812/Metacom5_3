"""General v7 precision contracts/gates for future Qwen memory recompilation.

This module is deliberately separate from the completed v6 artifact loader:
v6 rows remain readable for provenance and DEV regression, while no v6 row
can be promoted to held-out qualification evidence merely by importing this
module.  A future live compiler run must bind these schemas/prompts/gates in
its own versioned runtime manifest.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from metacom_pm.io import sha256_text
from metacom_pm.paper1.contracts import StrictContract

from .contracts import MPProfileFieldType, MSContinuityType, SupportingSpan

PRECISION_SCHEMA_VERSION = "paper1-semantic-memory-precision-schema-v7"
PRECISION_GROUNDING_VERSION = "paper1-semantic-memory-precision-gates-v7"


class DurabilityEvidence(StrEnum):
    DIRECT_ENDURING = "direct_enduring"
    RECURRENT = "recurrent"
    DIAGNOSED = "diagnosed"
    CURRENTLY_PERSISTENT = "currently_persistent"
    NONE = "none"


class CurrentValidityEvidence(StrEnum):
    DIRECT_CURRENT = "direct_current"
    DIRECT_RECURRENT = "direct_recurrent"
    DIRECT_CURRENT_ROLE = "direct_current_role"
    NONE = "none"


class MPPrecisionReason(StrEnum):
    ACCEPTED = "accepted"
    NOT_OWNER_FACT = "not_owner_fact"
    NOT_DIRECTLY_ENTAILED = "not_directly_entailed"
    TRANSIENT_OR_EPISODIC = "transient_or_episodic"
    FUTURE_PLAN = "future_plan"
    REQUIRES_PRIOR_INFERENCE = "requires_prior_inference"
    DURABILITY_NOT_ESTABLISHED = "durability_not_established"
    CURRENT_VALIDITY_NOT_ESTABLISHED = "current_validity_not_established"
    FIELD_TYPE_MISMATCH = "field_type_mismatch"


class MPPrecisionDecision(StrictContract):
    schema_version: Literal[PRECISION_SCHEMA_VERSION] = PRECISION_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    exact_support_span: tuple[SupportingSpan, ...] = Field(min_length=1)
    field_type: MPProfileFieldType
    owner_subject_direct: bool
    directly_entailed_by_current_span: bool
    durability_evidence: DurabilityEvidence
    current_validity_evidence: CurrentValidityEvidence
    episodic_or_transient: bool
    future_plan: bool
    requires_prior_inference: bool
    accepted: bool
    reason: MPPrecisionReason

    @model_validator(mode="after")
    def decision_matches_general_gate(self) -> "MPPrecisionDecision":
        violations = mp_precision_violations(self)
        should_accept = not violations
        if self.accepted != should_accept:
            raise ValueError(f"MP accepted flag disagrees with precision gate: {violations}")
        if self.accepted != (self.reason is MPPrecisionReason.ACCEPTED):
            raise ValueError("MP accepted flag and reason disagree")
        return self


class ExperienceLinkage(StrEnum):
    SAME_EXPERIENCE = "same_experience"
    UNRESOLVED = "unresolved"


class MEPrecisionReason(StrEnum):
    ACCEPTED = "accepted"
    ACTION_NOT_AGENTIVE = "action_not_agentive"
    OUTCOME_NOT_USER_OBSERVED = "outcome_not_user_observed"
    OUTCOME_NOT_AFTER_ACTION = "outcome_not_after_action"
    SAME_PREDICATE = "same_predicate"
    EXPERIENCE_LINKAGE_UNRESOLVED = "experience_linkage_unresolved"
    THIRD_PARTY_ACTION = "third_party_action"
    FUTURE_OR_HYPOTHETICAL = "future_or_hypothetical"
    PURPOSE_OR_PREDICTION_AS_OUTCOME = "purpose_or_prediction_as_outcome"


class MEPrecisionDecision(StrictContract):
    schema_version: Literal[PRECISION_SCHEMA_VERSION] = PRECISION_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    action_span: tuple[SupportingSpan, ...] = Field(min_length=1)
    action_is_owner: bool
    action_is_agentive: bool
    action_is_completed: bool
    outcome_span: tuple[SupportingSpan, ...] = Field(min_length=1)
    outcome_is_user_observed: bool
    action_before_outcome: bool
    same_predicate: bool
    future_or_hypothetical: bool
    purpose_or_prediction_as_outcome: bool
    experience_linkage: ExperienceLinkage
    accepted: bool
    reason: MEPrecisionReason

    @model_validator(mode="after")
    def decision_matches_general_gate(self) -> "MEPrecisionDecision":
        violations = me_precision_violations(self)
        should_accept = not violations
        if self.accepted != should_accept:
            raise ValueError(f"ME accepted flag disagrees with precision gate: {violations}")
        if self.accepted != (self.reason is MEPrecisionReason.ACCEPTED):
            raise ValueError("ME accepted flag and reason disagree")
        return self


class MSExclusion(StrEnum):
    NONE = "none"
    PROFILE = "profile"
    GREETING = "greeting"
    TRIVIA = "trivia"
    FUTURE = "future"
    CURRENT = "current"
    MALFORMED_ME = "malformed_me"


class MSSemanticAuditDecision(StrictContract):
    schema_version: Literal[PRECISION_SCHEMA_VERSION] = PRECISION_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    exact_support_span: tuple[SupportingSpan, ...] = Field(min_length=1)
    continuity_type: MSContinuityType
    owner_event_or_state: bool
    strictly_past_at_target: bool
    event_or_thread_traceable: bool
    exclusion: MSExclusion
    accepted_for_candidate_source: bool

    @model_validator(mode="after")
    def decision_matches_ms_gate(self) -> "MSSemanticAuditDecision":
        expected = (
            self.owner_event_or_state
            and self.strictly_past_at_target
            and self.event_or_thread_traceable
            and self.exclusion is MSExclusion.NONE
        )
        if self.accepted_for_candidate_source != expected:
            raise ValueError("MS decision disagrees with strict event/thread gate")
        return self


def mp_precision_violations(decision: MPPrecisionDecision) -> tuple[str, ...]:
    violations: list[str] = []
    if not decision.owner_subject_direct:
        violations.append("not_owner_fact")
    if not decision.directly_entailed_by_current_span:
        violations.append("not_directly_entailed")
    if decision.episodic_or_transient:
        violations.append("transient_or_episodic")
    if decision.future_plan:
        violations.append("future_plan")
    if decision.requires_prior_inference:
        violations.append("requires_prior_inference")
    if decision.durability_evidence is DurabilityEvidence.NONE:
        violations.append("durability_not_established")
    if decision.current_validity_evidence is CurrentValidityEvidence.NONE:
        violations.append("current_validity_not_established")
    if (
        decision.field_type is MPProfileFieldType.HEALTH_CONDITION
        and decision.durability_evidence
        not in {
            DurabilityEvidence.RECURRENT,
            DurabilityEvidence.DIAGNOSED,
            DurabilityEvidence.CURRENTLY_PERSISTENT,
        }
    ):
        violations.append("health_durability_not_recurrent_diagnosed_or_persistent")
    if (
        decision.field_type is MPProfileFieldType.STABLE_SOCIAL_ROLE
        and decision.current_validity_evidence is not CurrentValidityEvidence.DIRECT_CURRENT_ROLE
    ):
        violations.append("social_role_not_directly_current")
    if decision.field_type is MPProfileFieldType.OTHER_DURABLE_PROFILE and (
        decision.durability_evidence
        not in {DurabilityEvidence.DIRECT_ENDURING, DurabilityEvidence.RECURRENT}
        or decision.current_validity_evidence is CurrentValidityEvidence.NONE
    ):
        violations.append("catchall_durable_profile_fail_closed")
    return tuple(sorted(set(violations)))


def me_precision_violations(decision: MEPrecisionDecision) -> tuple[str, ...]:
    violations: list[str] = []
    if not decision.action_is_owner:
        violations.append("third_party_action")
    if not decision.action_is_agentive or not decision.action_is_completed:
        violations.append("action_not_agentive_completed")
    if not decision.outcome_is_user_observed:
        violations.append("outcome_not_user_observed")
    if not decision.action_before_outcome:
        violations.append("outcome_not_after_action")
    if decision.same_predicate:
        violations.append("same_predicate_action_outcome")
    if decision.future_or_hypothetical:
        violations.append("future_or_hypothetical")
    if decision.purpose_or_prediction_as_outcome:
        violations.append("purpose_or_prediction_as_outcome")
    if decision.experience_linkage is not ExperienceLinkage.SAME_EXPERIENCE:
        violations.append("experience_linkage_unresolved")
    return tuple(sorted(set(violations)))


PRECISION_EXTRACTOR_SYSTEM_PROMPT = """You are the Paper-1 factual semantic-memory extractor.
Extract only exact seeker-authored evidence from the current session. A prior
memory may disambiguate an explicit reference but may not supply a missing
fact. Never optimize the number of outputs.

MP: output only a directly entailed owner profile fact with field-specific
evidence that it is durable and currently valid. Reject transient/situational
narration and future plans. Health requires recurrent, diagnosed, or explicitly
currently-persistent evidence. Stable social roles must be directly stated.
Occupation and education are different fields. other_durable_profile is
fail-closed unless the current span itself establishes durability. Do not use
examples, IDs, names, or phrase blacklists as decision rules.

ME: output only a completed, agentive owner action followed by a semantically
distinct user-observed consequence from the same experience. A symptom/state
cannot be both action and outcome. Reject third-party, future, hypothetical,
purpose, prediction, or unresolved lineage. MS remains a strict-past owner
event/state/change with a traceable event or continuity thread; it is not a
profile, greeting, trivia, future/current item, or malformed ME.

Return only the supplied strict JSON schema. Do not estimate utility, relevance,
helpfulness, treatment choice, ON/OFF effect, or confidence."""

PRECISION_VERIFIER_SYSTEM_PROMPT = """You are the Paper-1 v7 precision verifier.
For every proposal return the exact class-specific precision schema. Re-copy
only exact current-session seeker spans. Evaluate direct entailment before any
prior relation. A prior-memory table is never independent evidence.

For MP, explicitly report exact_support_span, field_type, owner-subject directness,
durability_evidence, current_validity_evidence, episodic_or_transient,
future_plan, requires_prior_inference, accepted, and a closed reason. For ME,
explicitly report action_span, action_is_owner, action_is_agentive,
action_is_completed, outcome_span, outcome_is_user_observed,
action_before_outcome, same_predicate, future_or_hypothetical,
purpose_or_prediction_as_outcome, experience_linkage, accepted, and reason.
For MS, report its exact span, continuity type, owner event/state status,
strict-past proof, traceable event/thread, exclusion category, and acceptance.

Do not repair, rewrite, or add proposals. Do not use item-specific phrase or ID
blacklists. Return only the supplied strict JSON schema."""

PRECISION_EXTRACTOR_PROMPT_SHA256 = sha256_text(PRECISION_EXTRACTOR_SYSTEM_PROMPT)
PRECISION_VERIFIER_PROMPT_SHA256 = sha256_text(PRECISION_VERIFIER_SYSTEM_PROMPT)
