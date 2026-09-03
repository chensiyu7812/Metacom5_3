"""Active Paper-1 MP/ME/MS Multi-View Memory implementation."""

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
    GroundedSourceSpan,
    MULTI_VIEW_MEMORY_SCHEMA_VERSION,
    ProfileFieldType,
)

__all__ = [
    "AcceptedAtomicMemoryUnit",
    "AcceptedEventExperienceUnit",
    "AcceptedProfileViewUnit",
    "EventExperienceType",
    "EventTemporalStatus",
    "GroundedSourceSpan",
    "MULTI_VIEW_CANDIDATE_ADAPTER_VERSION",
    "MULTI_VIEW_MEMORY_SCHEMA_VERSION",
    "ProfileFieldType",
    "materialize_multi_view_candidates",
]
