"""Deterministic, non-utility rendering of accepted MP/ME atoms."""

from __future__ import annotations

from metacom_pm.io import sha256_text

from .contracts import ProposedAtomicMemoryUnit, ProposedEventExperienceUnit


MULTI_VIEW_RENDERER_VERSION = "paper1-multi-view-renderer-v1"


def render_atom(proposal: ProposedAtomicMemoryUnit, *, timestamp: str) -> str:
    if isinstance(proposal, ProposedEventExperienceUnit):
        return (
            f"Past event/experience [{timestamp}; {proposal.event_experience_type.value}; "
            f"{proposal.temporal_status.value}]: {proposal.normalized_event}"
        )
    return (
        f"Current profile [{proposal.profile_field_type.value}; "
        f"{proposal.profile_slot_key}]: {proposal.normalized_value}"
    )


MULTI_VIEW_RENDERER_SHA256 = sha256_text(
    "event=Past event/experience [timestamp; type; temporal_status]: normalized_event\n"
    "profile=Current profile [field_type; slot_key]: normalized_value"
)


__all__ = [
    "MULTI_VIEW_RENDERER_SHA256",
    "MULTI_VIEW_RENDERER_VERSION",
    "render_atom",
]
