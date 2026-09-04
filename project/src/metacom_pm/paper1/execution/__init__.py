"""Outcome-blind execution contracts for the active Paper-1 stack."""

from .step2 import (
    STEP2_RESOURCE_PROTOCOL,
    Step2ResourceEnvelope,
    TypedTreatmentBundle,
    build_typed_treatment_bundle,
    render_step2_resource_envelope,
)
from .packing import (
    PACKING_PROTOCOL,
    PackedResource,
    RankedCandidate,
    ResourceBudgetOverflow,
    pack_ranked_prefix,
    rank_candidates,
    select_ranked_prefix,
)
from .rq2_prompts import (
    RQ2_PROMPT_PROTOCOL,
    GeneratorMessage,
    Rq2GeneratorRequest,
    build_dg_supporter_request,
    build_static_rq2_request,
)
from .rq1_prompts import (
    ESC_SUPPORTER_SYSTEM_PROMPT,
    RQ1_PROMPT_PROTOCOL,
    Rq1GeneratorRequest,
    build_esc_supporter_request,
)
from .visible_state import (
    VISIBLE_STATE_PROTOCOL,
    QueryTiming,
    VisibleStateProjection,
    VisibleStateSource,
    build_dg_visible_state,
    build_rs_visible_state,
    build_static_memory_visible_state,
)

__all__ = [
    "STEP2_RESOURCE_PROTOCOL",
    "VISIBLE_STATE_PROTOCOL",
    "QueryTiming",
    "Step2ResourceEnvelope",
    "TypedTreatmentBundle",
    "VisibleStateProjection",
    "VisibleStateSource",
    "build_dg_visible_state",
    "build_rs_visible_state",
    "build_static_memory_visible_state",
    "build_typed_treatment_bundle",
    "render_step2_resource_envelope",
    "PACKING_PROTOCOL",
    "PackedResource",
    "RankedCandidate",
    "ResourceBudgetOverflow",
    "pack_ranked_prefix",
    "rank_candidates",
    "select_ranked_prefix",
    "RQ2_PROMPT_PROTOCOL",
    "GeneratorMessage",
    "Rq2GeneratorRequest",
    "build_dg_supporter_request",
    "build_static_rq2_request",
    "ESC_SUPPORTER_SYSTEM_PROMPT",
    "RQ1_PROMPT_PROTOCOL",
    "Rq1GeneratorRequest",
    "build_esc_supporter_request",
]
