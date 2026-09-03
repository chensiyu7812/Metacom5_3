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
    "bind_artifact",
    "inspect_treatment_delivery",
    "parse_resource_blocks",
    "render_resource_block",
]
