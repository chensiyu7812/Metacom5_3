"""Per-head semantic uncertainty compiler for Paper 1.

This module does not claim to understand unrestricted human language and it
does not choose thresholds.  It only turns a cross-fitted, component-specific
suitability probability into an auditable three-way decision.  Thresholds must
be calibrated inside the outer-training fold and supplied explicitly.

An uncertain head is compiled OFF by itself.  The other three bits are left
untouched, so the complete 16-action design is preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Mapping

from .v1_5_v5_3_semantic_off_accounting import SemanticStatus
from .v1_5b_policy_runtime import COMPONENTS, compile_component_bits


class HeadRoutingDecision(str, Enum):
    ON = "ON"
    OFF = "OFF"
    UNCERTAIN_AS_OFF = "UNCERTAIN_AS_OFF"


@dataclass(frozen=True)
class HeadAbstentionThresholds:
    component: str
    off_max: float
    on_min: float
    calibration_scope: str
    calibration_artifact_sha256: str

    def __post_init__(self) -> None:
        if self.component not in COMPONENTS:
            raise ValueError(f"unsupported component: {self.component}")
        if not (isfinite(self.off_max) and isfinite(self.on_min)):
            raise ValueError("thresholds must be finite")
        if not 0.0 <= self.off_max < self.on_min <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= off_max < on_min <= 1")
        if self.calibration_scope != "OUTER_TRAIN_ONLY":
            raise ValueError("semantic abstention thresholds must be outer-train calibrated")
        if len(self.calibration_artifact_sha256) != 64:
            raise ValueError("a full calibration artifact SHA-256 is required")


@dataclass(frozen=True)
class HeadSemanticDecision:
    component: str
    suitability_probability: float
    routing_decision: HeadRoutingDecision
    semantic_status: SemanticStatus
    requested_on: bool


def decide_head(
    probability: float,
    thresholds: HeadAbstentionThresholds,
) -> HeadSemanticDecision:
    if not isfinite(probability) or not 0.0 <= probability <= 1.0:
        raise ValueError("suitability probability must be finite and in [0, 1]")
    if probability >= thresholds.on_min:
        decision = HeadRoutingDecision.ON
        semantic_status = SemanticStatus.OPEN_ELIGIBLE
        requested_on = True
    elif probability <= thresholds.off_max:
        decision = HeadRoutingDecision.OFF
        semantic_status = SemanticStatus.DO_NOT_OPEN_NOT_USEFUL
        requested_on = False
    else:
        decision = HeadRoutingDecision.UNCERTAIN_AS_OFF
        semantic_status = SemanticStatus.ABSTAIN_LOW_CONFIDENCE
        requested_on = False
    return HeadSemanticDecision(
        component=thresholds.component,
        suitability_probability=probability,
        routing_decision=decision,
        semantic_status=semantic_status,
        requested_on=requested_on,
    )


def compile_independent_head_decisions(
    *,
    probabilities: Mapping[str, float],
    thresholds: Mapping[str, HeadAbstentionThresholds],
) -> tuple[str, dict[str, HeadSemanticDecision]]:
    """Compile four independent decisions into one of the original 16 actions."""

    if set(probabilities) != set(COMPONENTS):
        raise ValueError("probabilities must contain exactly MP, MS, ME, and RS")
    if set(thresholds) != set(COMPONENTS):
        raise ValueError("thresholds must contain exactly MP, MS, ME, and RS")
    decisions = {
        component: decide_head(probabilities[component], thresholds[component])
        for component in COMPONENTS
    }
    for component, decision in decisions.items():
        if decision.component != component:
            raise ValueError("threshold key/component mismatch")
    action = compile_component_bits(
        {component: decision.requested_on for component, decision in decisions.items()}
    )
    return action, decisions
