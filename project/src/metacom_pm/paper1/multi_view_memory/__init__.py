"""Active Paper-1 MP/ME/MS Multi-View Memory implementation."""

from .artifact import load_accepted_multi_view_units
from .candidate_adapter import (
    MULTI_VIEW_CANDIDATE_ADAPTER_VERSION,
    materialize_multi_view_candidates,
)
from .contracts import (
    AcceptedAtomicMemoryUnit,
    AcceptedEventExperienceUnit,
    AcceptedProfileViewUnit,
    EventExperienceType,
    EventTemporalStatus,
    ExtractorSessionOutput,
    ExtractorWireSessionOutput,
    GroundedSourceSpan,
    MULTI_VIEW_MEMORY_SCHEMA_VERSION,
    ProfileFieldType,
    ProposedEventExperienceUnit,
    ProposedProfileViewUnit,
    ProposedSourceSpan,
    VerificationDecision,
    VerificationReason,
    VerifierSessionOutput,
    VerifierWireSessionOutput,
)

__all__ = [
    "AcceptedAtomicMemoryUnit",
    "AcceptedEventExperienceUnit",
    "AcceptedProfileViewUnit",
    "EventExperienceType",
    "EventTemporalStatus",
    "ExtractorSessionOutput",
    "ExtractorWireSessionOutput",
    "GroundedSourceSpan",
    "MULTI_VIEW_CANDIDATE_ADAPTER_VERSION",
    "MULTI_VIEW_MEMORY_SCHEMA_VERSION",
    "ProfileFieldType",
    "ProposedEventExperienceUnit",
    "ProposedProfileViewUnit",
    "ProposedSourceSpan",
    "VerificationDecision",
    "VerificationReason",
    "VerifierSessionOutput",
    "VerifierWireSessionOutput",
    "load_accepted_multi_view_units",
    "materialize_multi_view_candidates",
]
