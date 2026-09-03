"""Active Paper-1 Multi-View Memory ontology contracts.

MP/ME/MS are this study's decomposition, not an ES-MemEval taxonomy.  They
map onto three public, runtime-grounded information shapes: a target-time
current profile view, an atomic event/experience timeline, and complete raw
prior-session documents.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, model_validator

from metacom_pm.io import sha256_text
from metacom_pm.paper1.contracts import Head, StrictContract


MULTI_VIEW_MEMORY_SCHEMA_VERSION = "paper1-multi-view-memory-schema-v1"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ProfileFieldType(StrEnum):
    IDENTITY = "identity"
    OCCUPATION = "occupation"
    EDUCATION = "education"
    LOCATION = "location"
    STABLE_RELATIONSHIP_ROLE = "stable_relationship_role"
    DURABLE_HEALTH_CONSTRAINT = "durable_health_constraint"
    ENDURING_INTEREST = "enduring_interest"
    ENDURING_PREFERENCE = "enduring_preference"
    DURABLE_BOUNDARY = "durable_boundary"
    OTHER_STABLE_SLOT = "other_stable_slot"


class EventExperienceType(StrEnum):
    LIFE_EVENT = "life_event"
    RELATIONSHIP_EVENT = "relationship_event"
    STATE_ONSET = "state_onset"
    STATE_CHANGE = "state_change"
    TRANSIENT_STATE = "transient_state"
    MEANINGFUL_EXPERIENCE = "meaningful_experience"
    COPING_ATTEMPT = "coping_attempt"
    SUPPORT_EXPERIENCE = "support_experience"
    ACTION_OBSERVED_OUTCOME = "action_observed_outcome"
    OTHER_OCCURRED_EVENT = "other_occurred_event"


class EventTemporalStatus(StrEnum):
    OCCURRED = "occurred"
    ONGOING_STAGE = "ongoing_stage"


class GroundedSourceSpan(StrictContract):
    span_id: str = Field(min_length=1)
    turn_id: str = Field(min_length=1)
    turn_index: int = Field(ge=0)
    exact_text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(gt=0)
    exact_text_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_span(self) -> "GroundedSourceSpan":
        if self.end_char <= self.start_char:
            raise ValueError("source span end must be after start")
        if self.exact_text_sha256 != sha256_text(self.exact_text):
            raise ValueError("source span text hash mismatch")
        return self


class AcceptedProfileViewUnit(StrictContract):
    schema_version: str = MULTI_VIEW_MEMORY_SCHEMA_VERSION
    memory_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    source_session_id: str = Field(min_length=1)
    source_session_rank: int = Field(ge=0)
    timestamp: str = Field(min_length=1)
    profile_field_type: ProfileFieldType
    profile_slot_key: str = Field(min_length=1)
    normalized_value: str = Field(min_length=1)
    rendered_candidate_content: str = Field(min_length=1)
    supporting_spans: tuple[GroundedSourceSpan, ...] = Field(min_length=1)
    user_anchored: bool = True
    compiler_identity_sha256: str = Field(pattern=SHA256_PATTERN)

    @property
    def head(self) -> Head:
        return Head.MP

    @model_validator(mode="after")
    def require_user_grounding(self) -> "AcceptedProfileViewUnit":
        if not self.user_anchored:
            raise ValueError("MP facts must be anchored in the user's disclosed life context")
        return self


class AcceptedEventExperienceUnit(StrictContract):
    schema_version: str = MULTI_VIEW_MEMORY_SCHEMA_VERSION
    memory_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    source_session_id: str = Field(min_length=1)
    source_session_rank: int = Field(ge=0)
    timestamp: str = Field(min_length=1)
    event_experience_type: EventExperienceType
    temporal_status: EventTemporalStatus
    normalized_event: str = Field(min_length=1)
    rendered_candidate_content: str = Field(min_length=1)
    supporting_spans: tuple[GroundedSourceSpan, ...] = Field(min_length=1)
    user_anchored: bool = True
    action_text: str | None = None
    observed_outcome_text: str | None = None
    compiler_identity_sha256: str = Field(pattern=SHA256_PATTERN)

    @property
    def head(self) -> Head:
        return Head.ME

    @model_validator(mode="after")
    def validate_event_shape(self) -> "AcceptedEventExperienceUnit":
        if not self.user_anchored:
            raise ValueError("ME events must be anchored in the user's disclosed life context")
        is_action_outcome = (
            self.event_experience_type is EventExperienceType.ACTION_OBSERVED_OUTCOME
        )
        has_both = self.action_text is not None and self.observed_outcome_text is not None
        if is_action_outcome != has_both:
            raise ValueError(
                "action/observed-outcome fields are required only for the ME action-outcome subtype"
            )
        return self


AcceptedAtomicMemoryUnit = AcceptedProfileViewUnit | AcceptedEventExperienceUnit


__all__ = [
    "AcceptedAtomicMemoryUnit",
    "AcceptedEventExperienceUnit",
    "AcceptedProfileViewUnit",
    "EventExperienceType",
    "EventTemporalStatus",
    "GroundedSourceSpan",
    "MULTI_VIEW_MEMORY_SCHEMA_VERSION",
    "ProfileFieldType",
]
