"""Strict Phase-A contracts for the Paper-1 semantic-memory compiler."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from metacom_pm.io import sha256_text
from metacom_pm.paper1.contracts import StrictContract

SHA256_PATTERN = r"^[0-9a-f]{64}$"
SEMANTIC_MEMORY_SCHEMA_VERSION = "paper1-semantic-memory-schema-v6"


class MemoryClass(StrEnum):
    MP = "MP"
    MS = "MS"
    ME = "ME"


class MemorySubtype(StrEnum):
    """Frozen factual ontology; values are class-prefixed to prevent ambiguity."""

    MP_IDENTITY = "mp_identity"
    MP_AGE = "mp_age"
    MP_OCCUPATION = "mp_occupation"
    MP_EDUCATION = "mp_education"
    MP_LOCATION = "mp_location"
    MP_STABLE_SOCIAL_ROLE = "mp_stable_social_role"
    MP_HEALTH_CONDITION = "mp_health_condition"
    MP_ENDURING_INTEREST_HABIT = "mp_enduring_interest_habit"
    MP_TRAIT_TENDENCY = "mp_trait_tendency"
    MP_OTHER_DURABLE_PROFILE = "mp_other_durable_profile"

    MS_EVENT = "ms_event"
    MS_STATE = "ms_state"
    MS_CHANGE = "ms_change"

    ME_POSITIVE = "me_positive"
    ME_NEGATIVE = "me_negative"
    ME_MIXED = "me_mixed"
    ME_NEUTRAL = "me_neutral"
    ME_OTHER_OBSERVED = "me_other_observed"


class TemporalStatus(StrEnum):
    """Mechanical temporal relation of the factual memory to its source session."""

    CURRENT_STATE = "current_state"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    UNCERTAIN = "uncertain"


class MPProfileFieldType(StrEnum):
    IDENTITY = "identity"
    AGE = "age"
    OCCUPATION = "occupation"
    EDUCATION = "education"
    LOCATION = "location"
    STABLE_SOCIAL_ROLE = "stable_social_role"
    HEALTH_CONDITION = "health_condition"
    ENDURING_INTEREST_HABIT = "enduring_interest_habit"
    TRAIT_TENDENCY = "trait_tendency"
    OTHER_DURABLE_PROFILE = "other_durable_profile"


class MSContinuityType(StrEnum):
    EVENT = "event"
    STATE = "state"
    CHANGE = "change"


class MEHistoricalOutcomeType(StrEnum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    MIXED = "mixed"
    NEUTRAL = "neutral"
    OTHER_OBSERVED = "other_observed"


MP_SUBTYPE_BY_FIELD_TYPE: dict[MPProfileFieldType, MemorySubtype] = {
    MPProfileFieldType.IDENTITY: MemorySubtype.MP_IDENTITY,
    MPProfileFieldType.AGE: MemorySubtype.MP_AGE,
    MPProfileFieldType.OCCUPATION: MemorySubtype.MP_OCCUPATION,
    MPProfileFieldType.EDUCATION: MemorySubtype.MP_EDUCATION,
    MPProfileFieldType.LOCATION: MemorySubtype.MP_LOCATION,
    MPProfileFieldType.STABLE_SOCIAL_ROLE: MemorySubtype.MP_STABLE_SOCIAL_ROLE,
    MPProfileFieldType.HEALTH_CONDITION: MemorySubtype.MP_HEALTH_CONDITION,
    MPProfileFieldType.ENDURING_INTEREST_HABIT: MemorySubtype.MP_ENDURING_INTEREST_HABIT,
    MPProfileFieldType.TRAIT_TENDENCY: MemorySubtype.MP_TRAIT_TENDENCY,
    MPProfileFieldType.OTHER_DURABLE_PROFILE: MemorySubtype.MP_OTHER_DURABLE_PROFILE,
}

MS_SUBTYPE_BY_CONTINUITY_TYPE: dict[MSContinuityType, MemorySubtype] = {
    MSContinuityType.EVENT: MemorySubtype.MS_EVENT,
    MSContinuityType.STATE: MemorySubtype.MS_STATE,
    MSContinuityType.CHANGE: MemorySubtype.MS_CHANGE,
}

ME_SUBTYPE_BY_OUTCOME_TYPE: dict[MEHistoricalOutcomeType, MemorySubtype] = {
    MEHistoricalOutcomeType.POSITIVE: MemorySubtype.ME_POSITIVE,
    MEHistoricalOutcomeType.NEGATIVE: MemorySubtype.ME_NEGATIVE,
    MEHistoricalOutcomeType.MIXED: MemorySubtype.ME_MIXED,
    MEHistoricalOutcomeType.NEUTRAL: MemorySubtype.ME_NEUTRAL,
    MEHistoricalOutcomeType.OTHER_OBSERVED: MemorySubtype.ME_OTHER_OBSERVED,
}


MEMORY_SUBTYPES_BY_CLASS: dict[MemoryClass, frozenset[MemorySubtype]] = {
    MemoryClass.MP: frozenset(
        subtype for subtype in MemorySubtype if subtype.value.startswith("mp_")
    ),
    MemoryClass.MS: frozenset(
        subtype for subtype in MemorySubtype if subtype.value.startswith("ms_")
    ),
    MemoryClass.ME: frozenset(
        subtype for subtype in MemorySubtype if subtype.value.startswith("me_")
    ),
}

TEMPORAL_STATUSES_BY_CLASS: dict[MemoryClass, frozenset[TemporalStatus]] = {
    MemoryClass.MP: frozenset({TemporalStatus.CURRENT_STATE}),
    MemoryClass.MS: frozenset(
        {
            TemporalStatus.ONGOING,
            TemporalStatus.COMPLETED,
            TemporalStatus.UNCERTAIN,
        }
    ),
    MemoryClass.ME: frozenset({TemporalStatus.COMPLETED}),
}


class SourceRole(StrEnum):
    SEEKER = "seeker"
    SUPPORTER = "supporter"


class SessionTurnInput(StrictContract):
    turn_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    role: SourceRole
    content: str = Field(min_length=1)


class PriorAcceptedMemory(StrictContract):
    memory_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    source_session_id: str = Field(min_length=1)
    source_session_rank: int = Field(ge=0)
    memory_class: MemoryClass
    memory_subtype: MemorySubtype
    normalized_memory: str = Field(min_length=1)
    entities: tuple[str, ...] = ()
    timestamp_status: TemporalStatus
    candidate_source_use: "CandidateSourceUse"
    profile_field_type: MPProfileFieldType | None = None
    continuity_type: MSContinuityType | None = None
    historical_outcome_type: MEHistoricalOutcomeType | None = None

    @model_validator(mode="after")
    def validate_class_slots(self) -> "PriorAcceptedMemory":
        if self.memory_class is MemoryClass.MP:
            if self.profile_field_type is None or any(
                value is not None
                for value in (self.continuity_type, self.historical_outcome_type)
            ):
                raise ValueError("prior MP requires only profile_field_type")
        elif self.memory_class is MemoryClass.MS:
            if self.continuity_type is None or any(
                value is not None
                for value in (self.profile_field_type, self.historical_outcome_type)
            ):
                raise ValueError("prior MS requires only continuity_type")
        elif self.historical_outcome_type is None or any(
            value is not None
            for value in (self.profile_field_type, self.continuity_type)
        ):
            raise ValueError("prior ME requires only historical_outcome_type")
        return self


class SessionCompileInput(StrictContract):
    """The only object that may be serialized into an extractor request."""

    schema_version: Literal[SEMANTIC_MEMORY_SCHEMA_VERSION] = SEMANTIC_MEMORY_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    timestamp: str = Field(min_length=1)
    chronological_rank: int = Field(ge=0)
    turns: tuple[SessionTurnInput, ...] = Field(min_length=1)
    strictly_past_memory_table: tuple[PriorAcceptedMemory, ...] = ()

    @model_validator(mode="after")
    def validate_isolation_and_order(self) -> "SessionCompileInput":
        try:
            date.fromisoformat(self.timestamp)
        except ValueError as exc:
            raise ValueError("timestamp must be an ISO calendar date") from exc
        turn_ids = [turn.turn_id for turn in self.turns]
        turn_indices = [turn.turn_index for turn in self.turns]
        if len(turn_ids) != len(set(turn_ids)):
            raise ValueError("turn_id values must be unique within a session")
        if turn_indices != sorted(turn_indices) or len(turn_indices) != len(set(turn_indices)):
            raise ValueError("turn_index values must be strictly increasing")
        memory_ids = [memory.memory_id for memory in self.strictly_past_memory_table]
        if len(memory_ids) != len(set(memory_ids)):
            raise ValueError("prior memory_id values must be unique")
        for memory in self.strictly_past_memory_table:
            if memory.owner_id != self.owner_id:
                raise ValueError("prior memory must have the same owner")
            if memory.source_session_rank >= self.chronological_rank:
                raise ValueError("prior memory must come from a strictly earlier session")
            if memory.source_session_id == self.session_id:
                raise ValueError("current-session memory cannot enter the prior table")
        return self


class SupportingSpan(StrictContract):
    span_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    exact_text: str = Field(min_length=1)


class PriorMemoryRelationType(StrEnum):
    COREFERS_WITH = "corefers_with"
    REAFFIRMS = "reaffirms"
    UPDATES = "updates"
    SUPERSEDES = "supersedes"
    CONFLICTS_WITH = "conflicts_with"


class LinkedPriorMemoryRelation(StrictContract):
    memory_id: str = Field(min_length=1)
    relation: PriorMemoryRelationType


class CandidateSourceUse(StrEnum):
    CANDIDATE_SOURCE = "candidate_source"
    STATE_TABLE_ONLY = "state_table_only"


class GroundedSupportingSpan(SupportingSpan):
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> "SupportingSpan":
        if self.end_char <= self.start_char:
            raise ValueError("end_char must be greater than start_char")
        return self


class ProposedMemoryBase(StrictContract):
    proposal_id: str = Field(min_length=1)
    supporting_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    entities: tuple[str, ...]
    linked_prior_relations: tuple[LinkedPriorMemoryRelation, ...]

    @property
    def linked_prior_memory_ids(self) -> tuple[str, ...]:
        return tuple(link.memory_id for link in self.linked_prior_relations)


class ProposedMPMemoryUnit(ProposedMemoryBase):
    profile_field_type: MPProfileFieldType
    factual_claim: str = Field(min_length=1)

    @property
    def memory_class(self) -> MemoryClass:
        return MemoryClass.MP

    @property
    def memory_subtype(self) -> MemorySubtype:
        return MP_SUBTYPE_BY_FIELD_TYPE[self.profile_field_type]

    @property
    def normalized_memory(self) -> str:
        return self.factual_claim

    @property
    def timestamp_status(self) -> TemporalStatus:
        return TemporalStatus.CURRENT_STATE

    @property
    def action_span_ids(self) -> tuple[str, ...]:
        return ()

    @property
    def observed_outcome_span_ids(self) -> tuple[str, ...]:
        return ()


class ProposedMSMemoryUnit(ProposedMemoryBase):
    continuity_type: MSContinuityType
    factual_claim: str = Field(min_length=1)
    event_status: Literal[
        TemporalStatus.ONGOING,
        TemporalStatus.COMPLETED,
        TemporalStatus.UNCERTAIN,
    ]

    @property
    def memory_class(self) -> MemoryClass:
        return MemoryClass.MS

    @property
    def memory_subtype(self) -> MemorySubtype:
        return MS_SUBTYPE_BY_CONTINUITY_TYPE[self.continuity_type]

    @property
    def normalized_memory(self) -> str:
        return self.factual_claim

    @property
    def timestamp_status(self) -> TemporalStatus:
        return self.event_status

    @property
    def action_span_ids(self) -> tuple[str, ...]:
        return ()

    @property
    def observed_outcome_span_ids(self) -> tuple[str, ...]:
        return ()


class ProposedMEMemoryUnit(ProposedMemoryBase):
    historical_outcome_type: MEHistoricalOutcomeType
    action: str = Field(min_length=1)
    observed_outcome: str = Field(min_length=1)
    action_span_ids: tuple[str, ...] = Field(min_length=1)
    observed_outcome_span_ids: tuple[str, ...] = Field(min_length=1)

    @property
    def memory_class(self) -> MemoryClass:
        return MemoryClass.ME

    @property
    def memory_subtype(self) -> MemorySubtype:
        return ME_SUBTYPE_BY_OUTCOME_TYPE[self.historical_outcome_type]

    @property
    def normalized_memory(self) -> str:
        return f"Action: {self.action} Observed outcome: {self.observed_outcome}"

    @property
    def timestamp_status(self) -> TemporalStatus:
        return TemporalStatus.COMPLETED


ProposedSemanticMemoryUnit = (
    ProposedMPMemoryUnit | ProposedMSMemoryUnit | ProposedMEMemoryUnit
)


class ExtractorSessionOutput(StrictContract):
    schema_version: Literal[SEMANTIC_MEMORY_SCHEMA_VERSION] = SEMANTIC_MEMORY_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    mp_facts: tuple[ProposedMPMemoryUnit, ...] = ()
    ms_memories: tuple[ProposedMSMemoryUnit, ...] = ()
    me_experiences: tuple[ProposedMEMemoryUnit, ...] = ()

    @property
    def proposals(self) -> tuple[ProposedSemanticMemoryUnit, ...]:
        return (*self.mp_facts, *self.ms_memories, *self.me_experiences)

    @model_validator(mode="after")
    def unique_proposals(self) -> "ExtractorSessionOutput":
        proposal_ids = [proposal.proposal_id for proposal in self.proposals]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise ValueError("proposal_id values must be unique")
        return self


class ExtractorWireSessionOutput(StrictContract):
    """JSON envelope only; every raw proposal is validated independently."""

    schema_version: Literal[SEMANTIC_MEMORY_SCHEMA_VERSION] = SEMANTIC_MEMORY_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    mp_facts: tuple[dict[str, Any], ...] = ()
    ms_memories: tuple[dict[str, Any], ...] = ()
    me_experiences: tuple[dict[str, Any], ...] = ()


class VerifierRejectionReason(StrEnum):
    ACCEPTED = "accepted"
    UNSUPPORTED_ADDITION = "unsupported_addition"
    WRONG_MEMORY_CLASS = "wrong_memory_class"
    WRONG_ACTOR = "wrong_actor"
    THIRD_PARTY_ACTION = "third_party_action"
    FUTURE_PLAN = "future_plan"
    HYPOTHETICAL = "hypothetical"
    ADVICE_ONLY = "advice_only"
    PURPOSE_AS_OUTCOME = "purpose_clause_as_outcome"
    PREDICTION_NOT_OBSERVED = "prediction_not_user_observed_result"
    ACTION_OUTCOME_LINEAGE_UNRESOLVED = "action_outcome_lineage_unresolved"
    INSUFFICIENT_SOURCE_SUPPORT = "insufficient_source_support"
    OTHER_FACTUAL_MISMATCH = "other_factual_mismatch"


class VerifierDecision(StrictContract):
    proposal_id: str = Field(min_length=1)
    accepted: bool
    reason: VerifierRejectionReason
    factual_rationale: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def reason_matches_decision(self) -> "VerifierDecision":
        if self.accepted != (self.reason is VerifierRejectionReason.ACCEPTED):
            raise ValueError("accepted must match the accepted rejection-reason value")
        return self


class VerifierSessionOutput(StrictContract):
    schema_version: Literal[SEMANTIC_MEMORY_SCHEMA_VERSION] = SEMANTIC_MEMORY_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    decisions: tuple[VerifierDecision, ...]

    @model_validator(mode="after")
    def unique_decisions(self) -> "VerifierSessionOutput":
        proposal_ids = [decision.proposal_id for decision in self.decisions]
        if len(proposal_ids) != len(set(proposal_ids)):
            raise ValueError("verifier decisions must have unique proposal IDs")
        return self


class VerifierWireSessionOutput(StrictContract):
    """JSON envelope only; every raw decision is validated independently."""

    schema_version: Literal[SEMANTIC_MEMORY_SCHEMA_VERSION] = SEMANTIC_MEMORY_SCHEMA_VERSION
    owner_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    decisions: tuple[dict[str, Any], ...]


class SchemaRejectedItem(StrictContract):
    phase: Literal["extractor", "verifier"]
    item_index: int = Field(ge=0)
    proposal_id: str | None = None
    violations: tuple[str, ...] = Field(min_length=1)
    raw_item_sha256: str = Field(pattern=SHA256_PATTERN)


class AcceptedSemanticMemoryUnit(StrictContract):
    """Source of truth after schema, grounding and semantic verification pass."""

    schema_version: Literal[SEMANTIC_MEMORY_SCHEMA_VERSION] = SEMANTIC_MEMORY_SCHEMA_VERSION
    memory_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    source_session_id: str = Field(min_length=1)
    source_session_rank: int = Field(ge=0)
    source_turn_ids: tuple[str, ...] = Field(min_length=1)
    memory_class: MemoryClass
    memory_subtype: MemorySubtype
    normalized_memory: str = Field(min_length=1)
    supporting_spans: tuple[GroundedSupportingSpan, ...] = Field(min_length=1)
    entities: tuple[str, ...] = ()
    timestamp: str = Field(min_length=1)
    timestamp_status: TemporalStatus
    candidate_source_use: CandidateSourceUse
    linked_prior_memory_ids: tuple[str, ...] = ()
    linked_prior_relations: tuple[LinkedPriorMemoryRelation, ...] = ()
    profile_field_type: MPProfileFieldType | None = None
    continuity_type: MSContinuityType | None = None
    historical_outcome_type: MEHistoricalOutcomeType | None = None
    action: str | None = None
    observed_outcome: str | None = None
    rendered_candidate_content: str = Field(min_length=1)
    rendered_candidate_content_sha256: str = Field(pattern=SHA256_PATTERN)
    action_span_ids: tuple[str, ...] = ()
    observed_outcome_span_ids: tuple[str, ...] = ()
    compiler_version: str = Field(min_length=1)
    renderer_version: str = Field(min_length=1)
    renderer_sha256: str = Field(pattern=SHA256_PATTERN)
    renderer_code_sha256: str = Field(pattern=SHA256_PATTERN)
    verifier_method: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    region: str = Field(min_length=1)
    model: str = Field(min_length=1)
    enable_thinking: bool
    extractor_prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    verifier_prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    extractor_schema_sha256: str = Field(pattern=SHA256_PATTERN)
    verifier_schema_sha256: str = Field(pattern=SHA256_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    prior_memory_table_sha256: str = Field(pattern=SHA256_PATTERN)
    extractor_request_sha256: str = Field(pattern=SHA256_PATTERN)
    extractor_response_sha256: str = Field(pattern=SHA256_PATTERN)
    verifier_request_sha256: str = Field(pattern=SHA256_PATTERN)
    verifier_response_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_preserved_lineage(self) -> "AcceptedSemanticMemoryUnit":
        if self.rendered_candidate_content_sha256 != sha256_text(
            self.rendered_candidate_content
        ):
            raise ValueError("rendered candidate content hash mismatch")
        if self.memory_subtype not in MEMORY_SUBTYPES_BY_CLASS[self.memory_class]:
            raise ValueError("accepted memory_subtype must match memory_class")
        if self.timestamp_status not in TEMPORAL_STATUSES_BY_CLASS[self.memory_class]:
            raise ValueError("accepted timestamp_status must match memory_class")
        relation_ids = tuple(link.memory_id for link in self.linked_prior_relations)
        if relation_ids != self.linked_prior_memory_ids:
            raise ValueError("linked prior IDs must exactly follow typed relation order")
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("linked prior relations must have unique memory IDs")
        if self.memory_class is MemoryClass.MP:
            if self.profile_field_type is None or any(
                value is not None
                for value in (
                    self.continuity_type,
                    self.historical_outcome_type,
                    self.action,
                    self.observed_outcome,
                )
            ):
                raise ValueError("accepted MP requires only profile_field_type slots")
            if self.memory_subtype is not MP_SUBTYPE_BY_FIELD_TYPE[self.profile_field_type]:
                raise ValueError("accepted MP subtype must derive from profile_field_type")
        elif self.memory_class is MemoryClass.MS:
            if self.continuity_type is None or any(
                value is not None
                for value in (
                    self.profile_field_type,
                    self.historical_outcome_type,
                    self.action,
                    self.observed_outcome,
                )
            ):
                raise ValueError("accepted MS requires only continuity_type slots")
            if self.memory_subtype is not MS_SUBTYPE_BY_CONTINUITY_TYPE[self.continuity_type]:
                raise ValueError("accepted MS subtype must derive from continuity_type")
        elif (
            self.historical_outcome_type is None
            or self.action is None
            or self.observed_outcome is None
            or self.profile_field_type is not None
            or self.continuity_type is not None
        ):
            raise ValueError("accepted ME requires only structured action/outcome slots")
        elif self.memory_subtype is not ME_SUBTYPE_BY_OUTCOME_TYPE[
            self.historical_outcome_type
        ]:
            raise ValueError("accepted ME subtype must derive from outcome type")
        expected_source_use = (
            CandidateSourceUse.STATE_TABLE_ONLY
            if self.memory_class is MemoryClass.MS
            and self.timestamp_status is TemporalStatus.UNCERTAIN
            else CandidateSourceUse.CANDIDATE_SOURCE
        )
        if self.candidate_source_use is not expected_source_use:
            raise ValueError("candidate_source_use must be deterministically derived")
        span_ids = {span.span_id for span in self.supporting_spans}
        expected_turn_ids = tuple(
            dict.fromkeys(span.turn_id for span in self.supporting_spans)
        )
        if self.source_turn_ids != expected_turn_ids:
            raise ValueError("source_turn_ids must exactly follow supporting-span order")
        if not set(self.action_span_ids).issubset(span_ids):
            raise ValueError("accepted action spans must reference supporting spans")
        if not set(self.observed_outcome_span_ids).issubset(span_ids):
            raise ValueError("accepted outcome spans must reference supporting spans")
        if self.memory_class is MemoryClass.ME:
            if not self.action_span_ids or not self.observed_outcome_span_ids:
                raise ValueError("accepted ME requires action and outcome span lineage")
        elif self.action_span_ids or self.observed_outcome_span_ids:
            raise ValueError("only accepted ME may carry action/outcome span lineage")
        return self
