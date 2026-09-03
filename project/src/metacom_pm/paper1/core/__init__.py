"""Mechanical execution primitives for the active Paper-1 pipeline."""

from .treatment import (
    ResourceBlock,
    RunBinding,
    inspect_treatment_delivery,
    parse_resource_blocks,
    render_resource_block,
)
from .freeze import (
    ArtifactBinding,
    EffectMeasurementFreeze,
    FreezeStatus,
    PreOutcomeFreezeManifest,
    ThresholdOperatingPointFreeze,
    ThresholdSelectionFreeze,
    bind_artifact,
)
from .threshold import (
    ClientLatencyConstraint,
    PROBABILITY_THRESHOLD_GRID,
    THRESHOLD_PROTOCOL,
    ThresholdCalibrationRow,
    ThresholdCalibrationScope,
    ThresholdPolicyKind,
    ThresholdSelectionResult,
    select_threshold_operating_point,
)
from .latency_policy import (
    CANONICAL_MEMORY_HEAD_ORDER,
    HeadLatencyCandidate,
    LatencyConstrainedAllocation,
    allocate_latency_constrained_heads,
)
from .latency_prediction import (
    DEFAULT_CONTEXT_TOKEN_BIN_UPPER_BOUNDS,
    DEFAULT_RESOURCE_TOKEN_BIN_UPPER_BOUNDS,
    FrozenLatencyLookup,
    LATENCY_PREDICTION_PROTOCOL,
    LatencyLookupCell,
    PairedLatencyProfileSample,
    build_frozen_latency_lookup,
    build_pre_call_head_latency_candidate,
)

__all__ = [
    "ResourceBlock",
    "RunBinding",
    "ArtifactBinding",
    "EffectMeasurementFreeze",
    "FreezeStatus",
    "PreOutcomeFreezeManifest",
    "ThresholdOperatingPointFreeze",
    "ThresholdSelectionFreeze",
    "ClientLatencyConstraint",
    "PROBABILITY_THRESHOLD_GRID",
    "THRESHOLD_PROTOCOL",
    "ThresholdCalibrationRow",
    "ThresholdCalibrationScope",
    "ThresholdPolicyKind",
    "ThresholdSelectionResult",
    "select_threshold_operating_point",
    "CANONICAL_MEMORY_HEAD_ORDER",
    "HeadLatencyCandidate",
    "LatencyConstrainedAllocation",
    "allocate_latency_constrained_heads",
    "DEFAULT_CONTEXT_TOKEN_BIN_UPPER_BOUNDS",
    "DEFAULT_RESOURCE_TOKEN_BIN_UPPER_BOUNDS",
    "FrozenLatencyLookup",
    "LATENCY_PREDICTION_PROTOCOL",
    "LatencyLookupCell",
    "PairedLatencyProfileSample",
    "build_frozen_latency_lookup",
    "build_pre_call_head_latency_candidate",
    "bind_artifact",
    "inspect_treatment_delivery",
    "parse_resource_blocks",
    "render_resource_block",
]
