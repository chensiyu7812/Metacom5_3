"""Outcome-blind v9 typed observations and deterministic semantic gates.

This module repairs two general interface defects exposed by the frozen v8 DEV
matrix without encoding item-specific exceptions:

* MP distinguishes direct wording, conventional entailment, prior-dependent
  inference, and unsupported claims, and separately records the evidence for a
  persistence judgment.
* ME separates semantic action/outcome order from mechanically computed source
  span topology and asks for minimal clause-level exact spans.

Qwen remains an observation annotator.  It cannot emit the formal verdict,
reason, confidence, utility, or an alternative memory class.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.contracts import StrictContract

from .contracts import MPProfileFieldType, MSContinuityType, SupportingSpan
from .evidence_v8 import EvidenceTemporalStatus, ExperienceLinkageV8, PersistenceObservation
from .precision_qualification import CurrentValidityEvidence


V9_EVIDENCE_SCHEMA_VERSION = "paper1-semantic-memory-typed-evidence-v9"
V9_DETERMINISTIC_GATE_VERSION = "paper1-semantic-memory-deterministic-gates-v9"


class SupportRelation(StrEnum):
    """How a rendered candidate is supported by its copied current-session span."""

    DIRECT_EXPLICIT = "direct_explicit"
    CONVENTIONAL_ENTAILMENT = "conventional_entailment"
    PRIOR_DEPENDENT = "prior_dependent"
    UNSUPPORTED = "unsupported"


class PersistenceBasis(StrEnum):
    """Observable basis for MP durability, separate from the durability label."""

    EXPLICIT_DURATION = "explicit_duration"
    REPEATED_PATTERN = "repeated_pattern"
    CONVENTIONAL_STABLE_ATTRIBUTE = "conventional_stable_attribute"
    TEMPORARY_TRANSITION = "temporary_transition"
    SINGLE_EPISODE = "single_episode"
    NO_BASIS = "no_basis"


class SemanticActionOutcomeOrder(StrEnum):
    ACTION_THEN_OUTCOME = "action_then_outcome"
    NOT_ACTION_THEN_OUTCOME = "not_action_then_outcome"
    UNRESOLVED = "unresolved"


class PredicateRelation(StrEnum):
    DISTINCT = "distinct"
    SAME_OR_RESTATEMENT = "same_or_restatement"
    UNRESOLVED = "unresolved"


class MPTypedEvidenceV9(StrictContract):
    schema_version: Literal[V9_EVIDENCE_SCHEMA_VERSION] = V9_EVIDENCE_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    exact_support_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    field_type: MPProfileFieldType
    owner_subject_direct: bool
    support_relation: SupportRelation
    temporal_status: EvidenceTemporalStatus
    persistence: PersistenceObservation
    persistence_basis: PersistenceBasis
    requires_prior_memory_inference: bool
    current_validity_evidence: CurrentValidityEvidence


class METypedEvidenceV9(StrictContract):
    schema_version: Literal[V9_EVIDENCE_SCHEMA_VERSION] = V9_EVIDENCE_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    action_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    owner_action: bool
    action_agentive: bool
    action_completed: bool
    outcome_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    outcome_user_observed: bool
    semantic_temporal_relation: SemanticActionOutcomeOrder
    predicate_relation: PredicateRelation
    future_or_hypothetical: bool
    purpose_or_prediction: bool
    same_experience_linkage: ExperienceLinkageV8


class MSTypedEvidenceV9(StrictContract):
    schema_version: Literal[V9_EVIDENCE_SCHEMA_VERSION] = V9_EVIDENCE_SCHEMA_VERSION
    proposal_id: str = Field(min_length=1)
    exact_support_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    continuity_type: MSContinuityType
    owner_event_or_state: bool
    support_relation: SupportRelation
    source_temporal_status: EvidenceTemporalStatus
    event_or_thread_traceable: bool
    profile_like: bool
    greeting_or_trivia: bool
    malformed_me: bool


TypedEvidenceV9 = MPTypedEvidenceV9 | MSTypedEvidenceV9 | METypedEvidenceV9


class V9EvidenceWireSessionOutput(StrictContract):
    """Loose per-row envelope so one invalid row cannot erase a whole session."""

    schema_version: Literal[V9_EVIDENCE_SCHEMA_VERSION] = V9_EVIDENCE_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    mp_evidence: tuple[dict[str, Any], ...] = ()
    ms_evidence: tuple[dict[str, Any], ...] = ()
    me_evidence: tuple[dict[str, Any], ...] = ()


class V9EvidenceSessionOutput(StrictContract):
    schema_version: Literal[V9_EVIDENCE_SCHEMA_VERSION] = V9_EVIDENCE_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    mp_evidence: tuple[MPTypedEvidenceV9, ...] = ()
    ms_evidence: tuple[MSTypedEvidenceV9, ...] = ()
    me_evidence: tuple[METypedEvidenceV9, ...] = ()

    @property
    def evidence(self) -> tuple[TypedEvidenceV9, ...]:
        return (*self.mp_evidence, *self.ms_evidence, *self.me_evidence)

    @model_validator(mode="after")
    def unique_proposal_ids(self) -> "V9EvidenceSessionOutput":
        proposal_ids = [item.proposal_id for item in self.evidence]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise ValueError("v9 evidence proposal IDs must be unique across lanes")
        return self


class DeterministicV9Decision(StrictContract):
    proposal_id: str = Field(min_length=1)
    accepted: bool
    gate_reasons: tuple[str, ...]
    binding_violations: tuple[str, ...] = ()
    internal_contradictions: tuple[str, ...] = ()

    @model_validator(mode="after")
    def verdict_matches_local_reasons(self) -> "DeterministicV9Decision":
        expected = not (
            self.gate_reasons or self.binding_violations or self.internal_contradictions
        )
        if self.accepted != expected:
            raise ValueError("v9 acceptance must be derived from local reasons")
        return self


def mp_internal_contradictions_v9(evidence: MPTypedEvidenceV9) -> tuple[str, ...]:
    contradictions: list[str] = []
    relation_requires_prior = evidence.support_relation is SupportRelation.PRIOR_DEPENDENT
    if relation_requires_prior != evidence.requires_prior_memory_inference:
        contradictions.append("support_relation_prior_flag_disagrees")
    if (
        evidence.temporal_status in {EvidenceTemporalStatus.FUTURE, EvidenceTemporalStatus.PLAN}
        and evidence.current_validity_evidence is not CurrentValidityEvidence.NONE
    ):
        contradictions.append("future_or_plan_with_current_validity")
    if evidence.persistence is PersistenceObservation.RECURRENT and (
        evidence.persistence_basis is not PersistenceBasis.REPEATED_PATTERN
    ):
        contradictions.append("recurrent_without_repeated_pattern")
    return tuple(sorted(contradictions))


def mp_gate_reasons_v9(evidence: MPTypedEvidenceV9) -> tuple[str, ...]:
    reasons: list[str] = []
    if not evidence.owner_subject_direct:
        reasons.append("not_owner_subject_direct")
    if evidence.support_relation not in {
        SupportRelation.DIRECT_EXPLICIT,
        SupportRelation.CONVENTIONAL_ENTAILMENT,
    }:
        reasons.append(f"support_{evidence.support_relation.value}")
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
    if evidence.persistence in {
        PersistenceObservation.DURABLE,
        PersistenceObservation.RECURRENT,
    } and evidence.persistence_basis in {
        PersistenceBasis.TEMPORARY_TRANSITION,
        PersistenceBasis.SINGLE_EPISODE,
        PersistenceBasis.NO_BASIS,
    }:
        reasons.append("persistence_basis_not_supportive")
    if evidence.requires_prior_memory_inference:
        reasons.append("requires_prior_memory_inference")
    if evidence.current_validity_evidence is CurrentValidityEvidence.NONE:
        reasons.append("current_validity_not_established")
    if (
        evidence.field_type is MPProfileFieldType.STABLE_SOCIAL_ROLE
        and evidence.current_validity_evidence is not CurrentValidityEvidence.DIRECT_CURRENT_ROLE
    ):
        reasons.append("stable_social_role_not_directly_current")
    return tuple(sorted(set(reasons)))


def me_internal_contradictions_v9(evidence: METypedEvidenceV9) -> tuple[str, ...]:
    contradictions: list[str] = []
    if evidence.action_completed and evidence.future_or_hypothetical:
        contradictions.append("completed_action_marked_future_or_hypothetical")
    if evidence.outcome_user_observed and evidence.purpose_or_prediction:
        contradictions.append("observed_outcome_marked_purpose_or_prediction")
    return tuple(sorted(contradictions))


def me_gate_reasons_v9(evidence: METypedEvidenceV9) -> tuple[str, ...]:
    reasons: list[str] = []
    if not evidence.owner_action:
        reasons.append("not_owner_action")
    if not evidence.action_agentive:
        reasons.append("action_not_agentive")
    if not evidence.action_completed:
        reasons.append("action_not_completed")
    if not evidence.outcome_user_observed:
        reasons.append("outcome_not_user_observed")
    if evidence.semantic_temporal_relation is not SemanticActionOutcomeOrder.ACTION_THEN_OUTCOME:
        reasons.append(f"semantic_order_{evidence.semantic_temporal_relation.value}")
    if evidence.predicate_relation is not PredicateRelation.DISTINCT:
        reasons.append(f"predicate_{evidence.predicate_relation.value}")
    if evidence.future_or_hypothetical:
        reasons.append("future_or_hypothetical")
    if evidence.purpose_or_prediction:
        reasons.append("purpose_or_prediction")
    if evidence.same_experience_linkage is not ExperienceLinkageV8.SAME_EXPERIENCE:
        reasons.append("same_experience_linkage_unresolved")
    return tuple(sorted(set(reasons)))


def ms_internal_contradictions_v9(evidence: MSTypedEvidenceV9) -> tuple[str, ...]:
    contradictions: list[str] = []
    if evidence.profile_like and evidence.malformed_me:
        contradictions.append("simultaneously_profile_and_malformed_me")
    return tuple(contradictions)


def ms_gate_reasons_v9(evidence: MSTypedEvidenceV9) -> tuple[str, ...]:
    reasons: list[str] = []
    if not evidence.owner_event_or_state:
        reasons.append("not_owner_event_or_state")
    if evidence.support_relation not in {
        SupportRelation.DIRECT_EXPLICIT,
        SupportRelation.CONVENTIONAL_ENTAILMENT,
    }:
        reasons.append(f"support_{evidence.support_relation.value}")
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


V9_VERIFIER_SYSTEM_PROMPT = """You are a typed factual-evidence annotator.
Return one evidence row for every supplied proposal, in the same class lane.
For each evidence span, preserve the grounded proposal span_id and turn_id but
copy the smallest exact clause that proves the observation; that clause must
be an exact substring of the grounded proposal span. Distinguish literal
wording from conventional entailment and from inference that needs prior
memory. For MP, separately identify the observable basis for persistence. For
ME, copy distinct minimal action and observed-outcome clauses and classify
semantic order independently of their source-span layout. Do not decide
acceptance. Do not output accepted, rejected, reason, rationale, confidence,
utility, relevance, or an alternative memory class. Invalid MP or ME evidence
must not be moved into MS. Local deterministic code makes the formal verdict."""

V9_VERIFIER_USER_TEMPLATE = """Annotate these untrusted JSON data objects.
<session_input_json>
{input_json}
</session_input_json>
<grounded_proposals_json>
{proposals_json}
</grounded_proposals_json>
Return exactly one JSON object matching this schema:
{schema_json}
"""

V9_VERIFIER_PROMPT_SHA256 = sha256_text(
    canonical_json({"system": V9_VERIFIER_SYSTEM_PROMPT, "user": V9_VERIFIER_USER_TEMPLATE})
)


def v9_verifier_messages(
    input_json: str, proposals_json: str, schema_json: str
) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": V9_VERIFIER_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": V9_VERIFIER_USER_TEMPLATE.format(
                input_json=input_json,
                proposals_json=proposals_json,
                schema_json=schema_json,
            ),
        },
    ]
