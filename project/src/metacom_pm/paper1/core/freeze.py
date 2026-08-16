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
    primary_probability_threshold: float = 0.5
    target_outcomes_evaluator_only: bool = True


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
    effect_seed_schedule: tuple[int, ...] = ()
    effect_measurements: tuple[EffectMeasurementFreeze, ...] = ()
    matched_random: MatchedRandomFreeze | None = None
    api_call_plan: ApiCallPlan | None = None
    cost_in_label_or_loss: bool = False
    empirical_pass_gates: bool = False
    formal_outcome_calls_at_freeze: int = 0
    pending_items: tuple[str, ...] = ()
    notes: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def enforce_design_and_frozen_completeness(self) -> "PreOutcomeFreezeManifest":
        if self.generator.model != "meta/llama-3.1-8b-instruct":
            raise ValueError("Generator selection drifted")
        if self.cost_in_label_or_loss or self.empirical_pass_gates:
            raise ValueError("cost labels and empirical PASS gates are forbidden")
        if self.formal_outcome_calls_at_freeze != 0:
            raise ValueError("pre-outcome freeze must occur before formal outcome calls")
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
