"""Shared, outcome-blind contracts for both Paper-1 work lanes.

The audit identifiers in these records are never model features.  Candidate,
feature and learner implementations must build on this module rather than on
the legacy V1.5 ontology.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Head(StrEnum):
    RS = "RS"
    MP = "MP"
    MS = "MS"
    ME = "ME"


class TaskType(StrEnum):
    ESC_RESPONSE = "esc_response"
    QA = "qa"
    SUMMARY = "summary"
    DIALOGUE_GENERATION = "dialogue_generation"


class ExperimentArm(StrEnum):
    R0 = "R0"
    RS_FIXED_HIGH = "RS_Fixed_High"
    RS_MATCHED_RANDOM = "RS_Matched_Random"
    LEARNED_RS_PM = "Learned_RS_PM"
    NO_MEMORY = "No_Memory"
    FULL_HISTORY = "Full_History"
    OFFICIAL_RAG_TOP4 = "Official_RAG_Top4"
    TYPED_FIXED_HIGH = "Typed_Fixed_High"
    TYPED_MATCHED_RANDOM = "Typed_Matched_Random"
    LEARNED_TYPED_MEMORY_PM = "Learned_Typed_Memory_PM"
    LEARNED_MINUS_MP = "Learned_minus_MP"
    LEARNED_MINUS_MS = "Learned_minus_MS"
    LEARNED_MINUS_ME = "Learned_minus_ME"


class EligibilityStatus(StrEnum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"


class TreatmentAssignment(StrEnum):
    OFF = "off"
    ON = "on"


class PolicyOperatingMode(StrEnum):
    CALIBRATED_THRESHOLD = "calibrated_threshold"
    ELIGIBLE_ALWAYS_ON = "eligible_always_on"
    ALWAYS_OFF = "always_off"


class TreatmentDeliveryStatus(StrEnum):
    DELIVERED = "delivered"
    NOT_ASSIGNED = "not_assigned"
    TECHNICAL_FAILURE = "technical_failure"


class PairedOutcome(StrEnum):
    """Raw paired-effect result before constructing a learner target."""

    ON_BETTER = "on_better"
    OFF_BETTER = "off_better"
    EQUIVALENT = "equivalent"
    UNCERTAIN = "uncertain"
    INVALID = "invalid"


class CandidateLineage(StrictContract):
    source: str
    owner_id: str = Field(description="Audit/grouping only; forbidden as a model feature")
    source_record_ids: tuple[str, ...]
    strict_past: bool | None = None
    observed_at: str | None = None
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CandidateRecord(StrictContract):
    candidate_id: str = Field(description="Audit only; forbidden as a model feature")
    head: Head
    content: str = Field(min_length=1)
    token_count: int = Field(ge=0)
    lineage: CandidateLineage
    raw_descriptors: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def memory_candidates_are_strict_past(self) -> "CandidateRecord":
        if self.head in {Head.MP, Head.MS, Head.ME} and self.lineage.strict_past is not True:
            raise ValueError("memory candidates require strict-past lineage")
        return self


class EligibilityDecision(StrictContract):
    status: EligibilityStatus
    hard_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def reasons_match_status(self) -> "EligibilityDecision":
        if self.status is EligibilityStatus.ELIGIBLE and self.hard_reasons:
            raise ValueError("eligible candidates cannot carry hard exclusion reasons")
        if self.status is EligibilityStatus.INELIGIBLE and not self.hard_reasons:
            raise ValueError("ineligible candidates require a mechanical reason")
        return self


class FoldAssignment(StrictContract):
    target_id: str = Field(description="Audit only")
    task_type: TaskType
    fold_id: str
    primary_group_key: str
    exact_evidence_fingerprint: str | None = None
    all_arms_seeds_repeats_bound: bool = True
    target_outcome_excluded_from_fit: bool = True


class ModelFeatureRecord(StrictContract):
    target_id: str = Field(description="Audit only; forbidden as a model feature")
    candidate_id: str = Field(description="Audit only; forbidden as a model feature")
    head: Head
    features: dict[str, str | int | float | bool]


class TreatmentDeliveryTrace(StrictContract):
    assignment: TreatmentAssignment
    status: TreatmentDeliveryStatus
    expected_resource_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    delivered_resource_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    mechanical_violations: tuple[str, ...] = ()
    semantic_adoption_diagnostic: bool | None = None

    @model_validator(mode="after")
    def validate_delivery(self) -> "TreatmentDeliveryTrace":
        if self.assignment is TreatmentAssignment.OFF:
            if self.status is TreatmentDeliveryStatus.DELIVERED:
                raise ValueError("OFF cannot use delivered status")
            if self.expected_resource_sha256 or self.delivered_resource_sha256:
                raise ValueError("OFF cannot contain a delivered resource")
            if self.status is TreatmentDeliveryStatus.NOT_ASSIGNED and self.mechanical_violations:
                raise ValueError("valid OFF cannot carry mechanical violations")
        if self.assignment is TreatmentAssignment.ON and self.status is TreatmentDeliveryStatus.DELIVERED:
            if not self.expected_resource_sha256 or not self.delivered_resource_sha256:
                raise ValueError("delivered ON requires both resource hashes")
            if self.expected_resource_sha256 != self.delivered_resource_sha256:
                raise ValueError("delivered resource identity mismatch")
            if self.mechanical_violations:
                raise ValueError("delivered ON cannot carry mechanical violations")
        if self.status is TreatmentDeliveryStatus.TECHNICAL_FAILURE and not self.mechanical_violations:
            raise ValueError("technical failure requires a mechanical violation")
        return self

    @property
    def mechanically_valid(self) -> bool:
        return self.status in {
            TreatmentDeliveryStatus.DELIVERED,
            TreatmentDeliveryStatus.NOT_ASSIGNED,
        }


class SoftEffectTarget(StrictContract):
    """Aggregated raw paired outcomes for a positive-effect binomial target.

    Equivalent is a valid nonpositive trial. Uncertain and invalid retain their
    distinct audit meanings but do not enter the likelihood denominator.
    """

    on_better: int = Field(ge=0)
    off_better: int = Field(ge=0)
    equivalent: int = Field(ge=0)
    uncertain: int = Field(ge=0)
    invalid: int = Field(default=0, ge=0)

    @property
    def measured_pairs(self) -> int:
        return self.on_better + self.off_better + self.equivalent

    @property
    def nonpositive_pairs(self) -> int:
        return self.off_better + self.equivalent

    @property
    def excluded_pairs(self) -> int:
        return self.uncertain + self.invalid

    @property
    def total_pairs(self) -> int:
        return self.measured_pairs + self.excluded_pairs

    @property
    def positive_effect_fraction(self) -> float | None:
        denominator = self.measured_pairs
        if denominator == 0:
            return None
        return self.on_better / denominator


class PolicyDecision(StrictContract):
    eligible: bool
    predicted_positive_effect_probability: float = Field(ge=0.0, le=1.0)
    operating_mode: PolicyOperatingMode
    threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    threshold_protocol_id: str = Field(min_length=1)
    assignment: TreatmentAssignment

    @model_validator(mode="after")
    def enforce_primary_rule(self) -> "PolicyDecision":
        if self.operating_mode is PolicyOperatingMode.CALIBRATED_THRESHOLD:
            if self.threshold is None:
                raise ValueError("calibrated policy decisions require a frozen threshold")
            open_resource = self.predicted_positive_effect_probability > self.threshold
        elif self.operating_mode is PolicyOperatingMode.ELIGIBLE_ALWAYS_ON:
            if self.threshold is not None:
                raise ValueError("eligible-always-on cannot carry a probability threshold")
            open_resource = True
        else:
            if self.threshold is not None:
                raise ValueError("always-off cannot carry a probability threshold")
            open_resource = False
        expected = TreatmentAssignment.ON if self.eligible and open_resource else TreatmentAssignment.OFF
        if self.assignment is not expected:
            raise ValueError("assignment violates the frozen eligibility + operating-point rule")
        return self


class CostRecord(StrictContract):
    generator_input_tokens: int = Field(ge=0)
    resource_injected_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)
    retrieval_calls: int = Field(ge=0, default=0)
    embedding_calls: int = Field(ge=0, default=0)
    latency_ms: float = Field(ge=0.0)
    retries: int = Field(ge=0, default=0)
    recoverable_api_cost_usd: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OfficialOutcomeRecord(StrictContract):
    benchmark: str
    task_type: TaskType
    target_id: str = Field(description="Audit only")
    arm: ExperimentArm
    metrics: dict[str, float]
    official_scorer_id: str
    diagnostic_only_metrics: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def no_project_composite(self) -> "OfficialOutcomeRecord":
        forbidden = {"composite", "utility", "quality", "risk"}
        if any(name.casefold() in forbidden for name in self.metrics):
            raise ValueError("project-defined composite/internal metrics cannot be official outcomes")
        if not self.metrics:
            raise ValueError("official outcome requires at least one official metric")
        return self
