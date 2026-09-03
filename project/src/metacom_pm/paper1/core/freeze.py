"""M2 pre-outcome freeze contracts and portable artifact hashing.

These checks establish configuration completeness and provenance.  They are
not empirical PASS gates and never inspect a model outcome.
"""

from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import Field, model_validator

from ..contracts import Head, StrictContract, TaskType
from .threshold import (
    PROBABILITY_THRESHOLD_GRID,
    THRESHOLD_PROTOCOL,
    ThresholdPolicyKind,
)


class FreezeStatus(StrEnum):
    DRAFT = "DRAFT_AWAITING_M1_INTEGRATION"
    FROZEN = "FROZEN_PRE_FORMAL_OUTCOME"


class ArtifactBinding(StrictContract):
    repo_relative_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    role: str = Field(min_length=1)

    @model_validator(mode="after")
    def path_is_portable(self) -> "ArtifactBinding":
        path = PurePosixPath(self.repo_relative_path)
        if path.is_absolute() or ".." in path.parts or str(path) != self.repo_relative_path:
            raise ValueError("artifact path must be normalized and repo-relative")
        if self.repo_relative_path.startswith("project/"):
            raise ValueError("artifact paths are relative to the project/ directory")
        return self


def bind_artifact(project_root: Path, relative_path: str, *, role: str) -> ArtifactBinding:
    binding_path = PurePosixPath(relative_path)
    if binding_path.is_absolute() or ".." in binding_path.parts or str(binding_path) != relative_path:
        raise ValueError("artifact path must be normalized and repo-relative")
    resolved_root = project_root.resolve()
    resolved_path = (resolved_root / Path(*binding_path.parts)).resolve()
    if resolved_root not in resolved_path.parents:
        raise ValueError("artifact escapes project root")
    if not resolved_path.is_file():
        raise FileNotFoundError(resolved_path)
    digest = hashlib.sha256(resolved_path.read_bytes()).hexdigest()
    return ArtifactBinding(repo_relative_path=relative_path, sha256=digest, role=role)


class GeneratorStackBinding(StrictContract):
    selection_status: str = "FINAL"
    provider: str
    model: str
    route: str
    source_artifacts: tuple[ArtifactBinding, ...]
    prompt_template_ids: tuple[str, ...] = ()
    decoding: dict[str, int | float | str | bool] = Field(default_factory=dict)


class CandidateBundleFreeze(StrictContract):
    head: Head
    compiler_id: str
    source_manifest: ArtifactBinding | None = None
    retrieval_backend: str | None = None
    top_k: int | None = Field(default=None, ge=1)
    max_resource_tokens: int | None = Field(default=None, ge=1)
    render_template_id: str | None = None
    canonical_other_heads_off: bool = True
    candidate_fixed_before_assignment: bool = True


class FeatureSchemaFreeze(StrictContract):
    head: Head
    exact_feature_names: tuple[str, ...]
    standardized_with_outer_train_only: bool = True
    contains_utility_or_outcome_feature: bool = False
    contains_other_component_bits: bool = False


class CrossFitFreeze(StrictContract):
    group_component_manifest: ArtifactBinding
    outer_fold_manifest: ArtifactBinding | None = None
    n_outer_folds: int | None = Field(default=None, ge=2)
    outer_seed: int | None = Field(default=None, ge=0)
    n_inner_folds: int | None = Field(default=None, ge=2)
    exact_evidence_union_only: bool = True
    broad_shared_session_primary: bool = False
    fixed_point_five_reference: float = 0.5
    threshold_selected_inside_training_only: bool = True
    target_outcomes_evaluator_only: bool = True

    @model_validator(mode="after")
    def enforce_threshold_isolation(self) -> "CrossFitFreeze":
        if self.fixed_point_five_reference != 0.5:
            raise ValueError("0.5 must remain the mandatory transparent reference")
        if not self.threshold_selected_inside_training_only:
            raise ValueError("threshold selection must stay inside grouped training data")
        return self


class ThresholdOperatingPointFreeze(StrictContract):
    head: Head
    task_type: TaskType
    outer_fold_id: str | None = None
    policy_kind: ThresholdPolicyKind
    selected_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    calibration_artifact: ArtifactBinding
    calibration_rows: int = Field(ge=0)
    calibration_clusters: int = Field(ge=0)
    identified: bool = True
    confirmatory_outcomes_read: bool = False

    @model_validator(mode="after")
    def policy_kind_matches_threshold(self) -> "ThresholdOperatingPointFreeze":
        if self.head is Head.RS:
            if self.task_type is not TaskType.ESC_RESPONSE or self.outer_fold_id is not None:
                raise ValueError("RS operating point must be the non-folded ESC-response cell")
        elif self.task_type is TaskType.ESC_RESPONSE or self.outer_fold_id is None:
            raise ValueError("memory operating points require a non-ESC task and outer fold")
        if self.policy_kind is ThresholdPolicyKind.PROBABILITY_THRESHOLD:
            if self.selected_threshold is None:
                raise ValueError("probability operating points require a selected threshold")
        elif self.selected_threshold is not None:
            raise ValueError("sentinel operating points cannot carry a probability threshold")
        if self.confirmatory_outcomes_read:
            raise ValueError("confirmatory outcomes cannot select an operating point")
        if self.identified:
            if self.calibration_rows < 1 or self.calibration_clusters < 1:
                raise ValueError("identified operating points require calibration evidence")
        elif (
            self.policy_kind is not ThresholdPolicyKind.ALWAYS_OFF
            or self.calibration_rows != 0
            or self.calibration_clusters != 0
        ):
            raise ValueError("unidentifiable cells must freeze as evidence-free always-off")
        return self


class ThresholdSelectionFreeze(StrictContract):
    protocol: str = THRESHOLD_PROTOCOL
    probability_grid: tuple[float, ...] = PROBABILITY_THRESHOLD_GRID
    include_eligible_always_on: bool = True
    include_always_off: bool = True
    fixed_point_five_reference_required: bool = True
    quality_rule: str = "paired_material_effect_quality_with_equivalent_credit_for_both_arms"
    uncertainty_rule: str = "cluster_mean_standard_error"
    selection_rule: str = (
        "catastrophic_client_completion_ceiling_then_quality_first_one_standard_"
        "error_then_minimum_p95_and_median_client_completion_latency"
    )
    cost_enters_label_or_loss: bool = False
    latency_enters_action_worthiness: bool = True
    catastrophic_client_completion_ceiling_ms: float = 60_000.0
    tighter_deployment_sla_required_for_paper_primary: bool = False
    client_latency_measurement_protocol_id: str | None = None
    confirmatory_outcome_selection_forbidden: bool = True
    outer_target_outcome_selection_forbidden: bool = True
    operating_points: tuple[ThresholdOperatingPointFreeze, ...] = ()

    @model_validator(mode="after")
    def enforce_protocol(self) -> "ThresholdSelectionFreeze":
        if self.probability_grid != PROBABILITY_THRESHOLD_GRID or 0.5 not in self.probability_grid:
            raise ValueError("threshold probability grid drifted")
        if not self.include_eligible_always_on or not self.include_always_off:
            raise ValueError("threshold surface must include both always-on and always-off")
        if not self.fixed_point_five_reference_required:
            raise ValueError("fixed 0.5 must remain a mandatory reference")
        if self.cost_enters_label_or_loss:
            raise ValueError("cost cannot enter the PM label or loss")
        if not self.latency_enters_action_worthiness:
            raise ValueError("deployment action-worthiness requires client latency")
        if self.catastrophic_client_completion_ceiling_ms != 60_000.0:
            raise ValueError("catastrophic client completion ceiling must remain 60000 ms")
        if self.tighter_deployment_sla_required_for_paper_primary:
            raise ValueError("a tighter project-defined SLA cannot become a Paper primary gate")
        if (
            not self.confirmatory_outcome_selection_forbidden
            or not self.outer_target_outcome_selection_forbidden
        ):
            raise ValueError("threshold selection outcome isolation cannot be disabled")
        identities = {
            (point.head, point.task_type, point.outer_fold_id)
            for point in self.operating_points
        }
        if len(identities) != len(self.operating_points):
            raise ValueError("threshold operating-point identities must be unique")
        return self


class MatchedRandomFreeze(StrictContract):
    construction_id: str
    seed: int | None = Field(default=None, ge=0)
    proposals: int | None = Field(default=None, ge=1)
    exact_on_count_by_prefrozen_stratum: bool = True
    exact_injected_token_budget: bool = True
    cost_enters_training_label: bool = False


class EffectMeasurementFreeze(StrictContract):
    """Task-specific coding frozen before any formal paired outcomes are opened."""

    task_type: TaskType
    scorer_id: str = Field(min_length=1)
    materially_better_rule: str = Field(min_length=1)
    equivalent_rule: str = Field(min_length=1)
    uncertain_rule: str = Field(min_length=1)
    invalid_rule: str = Field(min_length=1)
    on_better_target: int = 1
    off_better_target: int = 0
    equivalent_target: int = 0
    uncertain_enters_likelihood: bool = False
    invalid_enters_likelihood: bool = False
    preserve_raw_outcome: bool = True

    @model_validator(mode="after")
    def enforce_positive_effect_coding(self) -> "EffectMeasurementFreeze":
        if (
            self.on_better_target != 1
            or self.off_better_target != 0
            or self.equivalent_target != 0
        ):
            raise ValueError("positive-effect coding must be ON=1, OFF=0, equivalent=0")
        if self.uncertain_enters_likelihood or self.invalid_enters_likelihood:
            raise ValueError("uncertain and invalid pairs cannot enter the training likelihood")
        if not self.preserve_raw_outcome:
            raise ValueError("raw paired outcomes must be preserved")
        return self


class ApiCallPlan(StrictContract):
    generation_cells: int = Field(ge=0)
    official_scorer_cells: int = Field(ge=0)
    engineering_cap_calls: int = Field(ge=0)
    retry_cap_per_cell: int = Field(ge=0)
    estimated_total_calls_upper_bound: int = Field(ge=0)


class PreOutcomeFreezeManifest(StrictContract):
    protocol: str = "pm-paper1-pre-outcome-freeze-v1"
    status: FreezeStatus
    source_tree_sha: str = Field(pattern=r"^[0-9a-f]{40}$")
    generator: GeneratorStackBinding
    official_evaluation_artifacts: tuple[ArtifactBinding, ...]
    candidate_bundles: tuple[CandidateBundleFreeze, ...] = ()
    feature_schemas: tuple[FeatureSchemaFreeze, ...] = ()
    cross_fit: CrossFitFreeze | None = None
    threshold_selection: ThresholdSelectionFreeze | None = None
    effect_seed_schedule: tuple[int, ...] = ()
    effect_measurements: tuple[EffectMeasurementFreeze, ...] = ()
    matched_random: MatchedRandomFreeze | None = None
    api_call_plan: ApiCallPlan | None = None
    cost_in_label_or_loss: bool = False
    latency_in_action_worthiness: bool = True
    empirical_pass_gates: bool = False
    calibration_outcome_calls_at_freeze: int = Field(default=0, ge=0)
    confirmatory_outcome_calls_at_freeze: int = Field(default=0, ge=0)
    # Legacy compatibility field: it historically meant confirmatory/formal
    # benchmark outcomes, not the authorized calibration effects needed before
    # operating-point freeze.
    formal_outcome_calls_at_freeze: int = 0
    pending_items: tuple[str, ...] = ()
    notes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_design_and_frozen_completeness(self) -> "PreOutcomeFreezeManifest":
        if self.generator.model != "meta/llama-3.1-8b-instruct":
            raise ValueError("Generator selection drifted")
        if self.cost_in_label_or_loss or self.empirical_pass_gates:
            raise ValueError("cost labels and empirical PASS gates are forbidden")
        if not self.latency_in_action_worthiness:
            raise ValueError("end-to-end latency must constrain deployment action-worthiness")
        if (
            self.formal_outcome_calls_at_freeze != 0
            or self.confirmatory_outcome_calls_at_freeze != 0
        ):
            raise ValueError("full-stack freeze must occur before confirmatory outcome calls")
        if len(self.effect_seed_schedule) != len(set(self.effect_seed_schedule)):
            raise ValueError("effect seeds must be unique")
        if any(seed < 0 for seed in self.effect_seed_schedule):
            raise ValueError("effect seeds must be non-negative")
        if any(not bundle.canonical_other_heads_off for bundle in self.candidate_bundles):
            raise ValueError("route A requires all other optional heads OFF")
        if any(schema.contains_utility_or_outcome_feature for schema in self.feature_schemas):
            raise ValueError("utility/outcome features are forbidden")
        if any(schema.contains_other_component_bits for schema in self.feature_schemas):
            raise ValueError("route A forbids other-component feature bits")
        if self.matched_random is not None and (
            not self.matched_random.exact_on_count_by_prefrozen_stratum
            or not self.matched_random.exact_injected_token_budget
        ):
            raise ValueError("matched random requires exact prefrozen ON counts and token budget")

        if self.status is FreezeStatus.FROZEN:
            if self.pending_items:
                raise ValueError("a frozen manifest cannot retain pending items")
            if {bundle.head for bundle in self.candidate_bundles} != set(Head):
                raise ValueError("frozen manifest requires RS/MP/MS/ME candidate bundles")
            if {schema.head for schema in self.feature_schemas} != set(Head):
                raise ValueError("frozen manifest requires four exact feature schemas")
            if any(
                value is None
                for bundle in self.candidate_bundles
                for value in (
                    bundle.source_manifest,
                    bundle.retrieval_backend,
                    bundle.top_k,
                    bundle.max_resource_tokens,
                    bundle.render_template_id,
                )
            ):
                raise ValueError("frozen candidate bundles must be fully specified")
            if not self.generator.prompt_template_ids or not self.generator.decoding:
                raise ValueError("frozen Generator stack requires prompts and decoding")
            if self.cross_fit is None or any(
                value is None
                for value in (
                    self.cross_fit.outer_fold_manifest,
                    self.cross_fit.n_outer_folds,
                    self.cross_fit.outer_seed,
                    self.cross_fit.n_inner_folds,
                )
            ):
                raise ValueError("frozen manifest requires packed outer/inner cross-fitting")
            if self.threshold_selection is None or not self.threshold_selection.operating_points:
                raise ValueError("frozen manifest requires calibrated threshold operating points")
            if self.threshold_selection.client_latency_measurement_protocol_id is None:
                raise ValueError("frozen manifest requires client latency measurement identity")
            points = self.threshold_selection.operating_points
            rs_points = [point for point in points if point.head is Head.RS]
            if len(rs_points) != 1:
                raise ValueError("frozen manifest requires exactly one RS operating point")
            memory_points = [point for point in points if point.head is not Head.RS]
            outer_fold_ids = {point.outer_fold_id for point in memory_points}
            if len(outer_fold_ids) != self.cross_fit.n_outer_folds:
                raise ValueError("threshold operating points must cover every outer fold")
            expected_memory_cells = {
                (head, task_type, outer_fold_id)
                for head in (Head.MP, Head.MS, Head.ME)
                for task_type in (TaskType.QA, TaskType.SUMMARY, TaskType.DIALOGUE_GENERATION)
                for outer_fold_id in outer_fold_ids
            }
            actual_memory_cells = {
                (point.head, point.task_type, point.outer_fold_id)
                for point in memory_points
            }
            if actual_memory_cells != expected_memory_cells:
                raise ValueError("frozen manifest requires every memory head/task/outer-fold cell")
            if not self.effect_seed_schedule or self.matched_random is None:
                raise ValueError("frozen manifest requires effect and matched-random seeds")
            if (
                len(self.effect_measurements) != len(TaskType)
                or {measurement.task_type for measurement in self.effect_measurements} != set(TaskType)
            ):
                raise ValueError("frozen manifest requires task-specific effect measurement rules")
            if self.matched_random.seed is None or self.matched_random.proposals is None:
                raise ValueError("frozen matched-random construction is incomplete")
            if self.api_call_plan is None:
                raise ValueError("frozen manifest requires an API call plan")
        return self
