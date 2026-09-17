"""Deterministic candidate-text rendering from verified semantic slots."""

from __future__ import annotations

from pathlib import Path

from metacom_pm.io import sha256_file, sha256_text

from .contracts import (
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    ProposedSemanticMemoryUnit,
)

RENDERER_VERSION = "paper1-semantic-memory-renderer-v1"
RENDERER_SPEC = """paper1 semantic memory renderer v1
MP => Profile fact [profile_field_type]: factual_claim
MS => Continuity fact [continuity_type; source_status=event_status]: factual_claim
ME => Past action: action User-observed outcome [historical_outcome_type]: observed_outcome
No model-generated relevance, utility, confidence, or treatment language is added.
"""
RENDERER_SHA256 = sha256_text(RENDERER_SPEC)
RENDERER_CODE_SHA256 = sha256_file(Path(__file__))


def render_semantic_memory(proposal: ProposedSemanticMemoryUnit) -> str:
    if isinstance(proposal, ProposedMPMemoryUnit):
        return (
            f"Profile fact [{proposal.profile_field_type.value}]: "
            f"{proposal.factual_claim}"
        )
    if isinstance(proposal, ProposedMSMemoryUnit):
        return (
            "Continuity fact "
            f"[{proposal.continuity_type.value}; "
            f"source_status={proposal.event_status.value}]: "
            f"{proposal.factual_claim}"
        )
    if isinstance(proposal, ProposedMEMemoryUnit):
        return (
            f"Past action: {proposal.action} "
            "User-observed outcome "
            f"[{proposal.historical_outcome_type.value}]: "
            f"{proposal.observed_outcome}"
        )
    raise TypeError(f"unsupported semantic-memory proposal: {type(proposal)!r}")
