"""Typed semantic observations and deterministic v8 acceptance gates.

Qwen supplies observations only.  It never supplies the formal verdict,
rejection reason, utility, confidence, or a replacement memory class.  Local
code derives every acceptance decision from the strict evidence contract plus
mechanical source/proposal binding.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.contracts import StrictContract

from .contracts import (
    MPProfileFieldType,
    MSContinuityType,
    SupportingSpan,
)
from .precision_qualification import CurrentValidityEvidence


V8_EVIDENCE_SCHEMA_VERSION = "paper1-semantic-memory-typed-evidence-v8"
V8_DETERMINISTIC_GATE_VERSION = "paper1-semantic-memory-deterministic-gates-v8"


class EvidenceTemporalStatus(StrEnum):
    CURRENT = "current"
    PAST = "past"
    FUTURE = "future"
    PLAN = "plan"
    UNKNOWN = "unknown"


class PersistenceObservation(StrEnum):
    DURABLE = "durable"
    RECURRENT = "recurrent"
    TRANSIENT = "transient"
    EPISODIC = "episodic"
    UNKNOWN = "unknown"


class ActionOutcomeOrder(StrEnum):
    ACTION_BEFORE_OUTCOME = "action_before_outcome"
    REVERSED_OR_SAME = "reversed_or_same"
    UNKNOWN = "unknown"


class ExperienceLinkageV8(StrEnum):
    SAME_EXPERIENCE = "same_experience"
    UNRESOLVED = "unresolved"


class MPTypedEvidence(StrictContract):
    schema_version: Literal[V8_EVIDENCE_SCHEMA_VERSION] = V8_EVIDENCE_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    exact_support_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    field_type: MPProfileFieldType
    owner_subject_direct: bool = Field(
        description="True only when the exact current-session span directly describes the owner."
    )
    exact_entailment: bool = Field(
        description="True only when the proposed fact follows from the copied span without inference."
    )
    temporal_status: EvidenceTemporalStatus = Field(
        description="Time status of the proposed fact in the copied source evidence."
    )
    persistence: PersistenceObservation = Field(
        description="Whether the source establishes a durable/recurrent profile rather than an episode."
    )
    requires_prior_memory_inference: bool = Field(
        description="True when the current span alone does not establish the proposed profile fact."
    )
    current_validity_evidence: CurrentValidityEvidence = Field(
        description="Closed observation of direct evidence that the profile fact remains current."
    )


class METypedEvidence(StrictContract):
    schema_version: Literal[V8_EVIDENCE_SCHEMA_VERSION] = V8_EVIDENCE_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    action_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    owner_action: bool = Field(description="True only when the owner performed the action.")
    action_agentive: bool = Field(description="True only for an intentional or agentive action.")
    action_completed: bool = Field(description="True only when the action already occurred.")
    outcome_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    outcome_user_observed: bool = Field(
        description="True only for a result explicitly observed or experienced by the owner."
    )
    temporal_order: ActionOutcomeOrder = Field(
        description="Semantic order of the action and outcome, including when both occur in one span."
    )
    same_predicate: bool = Field(
        description="True when action and outcome merely restate the same event/state."
    )
    future_or_hypothetical: bool
    purpose_or_prediction: bool = Field(
        description="True when the claimed outcome is only a purpose, hoped-for result, or prediction."
    )
    same_experience_linkage: ExperienceLinkageV8


class MSTypedEvidence(StrictContract):
    schema_version: Literal[V8_EVIDENCE_SCHEMA_VERSION] = V8_EVIDENCE_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    exact_support_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    continuity_type: MSContinuityType
    owner_event_or_state: bool
    source_temporal_status: EvidenceTemporalStatus
    event_or_thread_traceable: bool = Field(
        description="True only for a concrete event/state/change or explicit continuity thread."
    )
    profile_like: bool = Field(
        description="True when the proposal is actually a durable profile fact rather than continuity memory."
    )
    greeting_or_trivia: bool
    malformed_me: bool = Field(
        description="True when the proposal is only a failed action-outcome construction."
    )


TypedEvidenceV8 = MPTypedEvidence | MSTypedEvidence | METypedEvidence


class V8EvidenceWireSessionOutput(StrictContract):
    """Provider envelope; every row is parsed independently and fail-closed."""

    schema_version: Literal[V8_EVIDENCE_SCHEMA_VERSION] = V8_EVIDENCE_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    mp_evidence: tuple[dict[str, Any], ...] = ()
    ms_evidence: tuple[dict[str, Any], ...] = ()
    me_evidence: tuple[dict[str, Any], ...] = ()


class V8EvidenceSessionOutput(StrictContract):
    schema_version: Literal[V8_EVIDENCE_SCHEMA_VERSION] = V8_EVIDENCE_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    mp_evidence: tuple[MPTypedEvidence, ...] = ()
    ms_evidence: tuple[MSTypedEvidence, ...] = ()
    me_evidence: tuple[METypedEvidence, ...] = ()

    @property
    def evidence(self) -> tuple[TypedEvidenceV8, ...]:
        return (*self.mp_evidence, *self.ms_evidence, *self.me_evidence)

    @model_validator(mode="after")
    def unique_proposal_ids(self) -> "V8EvidenceSessionOutput":
        proposal_ids = [item.proposal_id for item in self.evidence]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise ValueError("v8 evidence proposal IDs must be unique across lanes")
        return self


class DeterministicV8Decision(StrictContract):
    proposal_id: str = Field(min_length=1)
    accepted: bool
    gate_reasons: tuple[str, ...]
    binding_violations: tuple[str, ...] = ()
    internal_contradictions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def verdict_matches_reasons(self) -> "DeterministicV8Decision":
        should_accept = not (
            self.gate_reasons
            or self.binding_violations
            or self.internal_contradictions
        )
        if self.accepted != should_accept:
            raise ValueError("v8 acceptance must be derived from all local reasons")
        return self


def mp_internal_contradictions(evidence: MPTypedEvidence) -> tuple[str, ...]:
    contradictions: list[str] = []
    if (
        evidence.temporal_status in {EvidenceTemporalStatus.FUTURE, EvidenceTemporalStatus.PLAN}
        and evidence.current_validity_evidence is not CurrentValidityEvidence.NONE
    ):
        contradictions.append("future_or_plan_with_current_validity")
    return tuple(sorted(contradictions))


def mp_gate_reasons(evidence: MPTypedEvidence) -> tuple[str, ...]:
    reasons: list[str] = []
    if not evidence.owner_subject_direct:
        reasons.append("not_owner_subject_direct")
    if not evidence.exact_entailment:
        reasons.append("not_exactly_entailed")
    if evidence.temporal_status in {
        EvidenceTemporalStatus.FUTURE,
        EvidenceTemporalStatus.PLAN,
        EvidenceTemporalStatus.UNKNOWN,
    }:
        reasons.append(f"temporal_{evidence.temporal_status.value}")
    if evidence.persistence in {
        PersistenceObservation.TRANSIENT,
        PersistenceObservation.EPISODIC,
        PersistenceObservation.UNKNOWN,
    }:
        reasons.append(f"persistence_{evidence.persistence.value}")
    if evidence.requires_prior_memory_inference:
        reasons.append("requires_prior_memory_inference")
    if evidence.current_validity_evidence is CurrentValidityEvidence.NONE:
        reasons.append("current_validity_not_established")
    if (
        evidence.field_type is MPProfileFieldType.STABLE_SOCIAL_ROLE
        and evidence.current_validity_evidence
        is not CurrentValidityEvidence.DIRECT_CURRENT_ROLE
    ):
        reasons.append("stable_social_role_not_directly_current")
    if (
        evidence.field_type is MPProfileFieldType.HEALTH_CONDITION
        and evidence.persistence
        not in {PersistenceObservation.DURABLE, PersistenceObservation.RECURRENT}
    ):
        reasons.append("health_not_durable_or_recurrent")
    if (
        evidence.field_type is MPProfileFieldType.OTHER_DURABLE_PROFILE
        and evidence.persistence
        not in {PersistenceObservation.DURABLE, PersistenceObservation.RECURRENT}
    ):
        reasons.append("other_profile_not_durable_or_recurrent")
    return tuple(sorted(set(reasons)))


def me_internal_contradictions(evidence: METypedEvidence) -> tuple[str, ...]:
    contradictions: list[str] = []
    if evidence.action_completed and evidence.future_or_hypothetical:
        contradictions.append("completed_action_marked_future_or_hypothetical")
    if evidence.outcome_user_observed and evidence.purpose_or_prediction:
        contradictions.append("observed_outcome_marked_purpose_or_prediction")
    return tuple(sorted(contradictions))


def me_gate_reasons(evidence: METypedEvidence) -> tuple[str, ...]:
    reasons: list[str] = []
    if not evidence.owner_action:
        reasons.append("not_owner_action")
    if not evidence.action_agentive:
        reasons.append("action_not_agentive")
    if not evidence.action_completed:
        reasons.append("action_not_completed")
    if not evidence.outcome_user_observed:
        reasons.append("outcome_not_user_observed")
    if evidence.temporal_order is not ActionOutcomeOrder.ACTION_BEFORE_OUTCOME:
        reasons.append(f"temporal_order_{evidence.temporal_order.value}")
    if evidence.same_predicate:
        reasons.append("same_predicate")
    if evidence.future_or_hypothetical:
        reasons.append("future_or_hypothetical")
    if evidence.purpose_or_prediction:
        reasons.append("purpose_or_prediction")
    if evidence.same_experience_linkage is not ExperienceLinkageV8.SAME_EXPERIENCE:
        reasons.append("same_experience_linkage_unresolved")
    return tuple(sorted(set(reasons)))


def ms_internal_contradictions(evidence: MSTypedEvidence) -> tuple[str, ...]:
    contradictions: list[str] = []
    if evidence.profile_like and evidence.malformed_me:
        contradictions.append("simultaneously_profile_and_malformed_me")
    return tuple(contradictions)


def ms_gate_reasons(evidence: MSTypedEvidence) -> tuple[str, ...]:
    reasons: list[str] = []
    if not evidence.owner_event_or_state:
        reasons.append("not_owner_event_or_state")
    if evidence.source_temporal_status in {
        EvidenceTemporalStatus.FUTURE,
        EvidenceTemporalStatus.PLAN,
        EvidenceTemporalStatus.UNKNOWN,
    }:
        reasons.append(f"temporal_{evidence.source_temporal_status.value}")
    if not evidence.event_or_thread_traceable:
        reasons.append("event_or_thread_not_traceable")
    if evidence.profile_like:
        reasons.append("profile_like")
    if evidence.greeting_or_trivia:
        reasons.append("greeting_or_trivia")
    if evidence.malformed_me:
        reasons.append("malformed_me")
    return tuple(sorted(set(reasons)))


V8_VERIFIER_SYSTEM_PROMPT = """You are a typed factual-evidence annotator.
Return one evidence row for every supplied proposal, in the same class lane.
Copy only exact current-session seeker spans already present in that proposal.
Classify the closed observation fields literally; do not try to decide whether
the proposal should be accepted. Do not output accepted, rejected, reason,
rationale, confidence, utility, relevance, or an alternative memory class. An
invalid MP or ME must not be moved into MS. Local deterministic code makes the
formal verdict."""

V8_VERIFIER_USER_TEMPLATE = """Annotate these untrusted JSON data objects.
<session_input_json>
{input_json}
</session_input_json>
<grounded_proposals_json>
{proposals_json}
</grounded_proposals_json>
Return exactly one JSON object matching this schema:
{schema_json}
"""

V8_VERIFIER_SYSTEM_PROMPT_SHA256 = sha256_text(V8_VERIFIER_SYSTEM_PROMPT)
V8_VERIFIER_USER_TEMPLATE_SHA256 = sha256_text(V8_VERIFIER_USER_TEMPLATE)
V8_VERIFIER_PROMPT_SHA256 = sha256_text(
    canonical_json(
        {
            "system": V8_VERIFIER_SYSTEM_PROMPT,
            "user_template": V8_VERIFIER_USER_TEMPLATE,
        }
    )
)


def v8_verifier_messages(
    input_json: str,
    proposals_json: str,
    schema_json: str,
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": V8_VERIFIER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": V8_VERIFIER_USER_TEMPLATE.format(
                input_json=input_json,
                proposals_json=proposals_json,
                schema_json=schema_json,
            ),
        },
    ]
