from pathlib import Path

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import Head, TaskType
from metacom_pm.paper1.core.freeze import (
    ArtifactBinding,
    CandidateBundleFreeze,
    EffectMeasurementFreeze,
    FeatureSchemaFreeze,
    FreezeStatus,
    GeneratorStackBinding,
    MatchedRandomFreeze,
    PreOutcomeFreezeManifest,
    bind_artifact,
)


def _generator():
    return GeneratorStackBinding(
        provider="NVIDIA hosted NIM",
        model="meta/llama-3.1-8b-instruct",
        route="build.nvidia.com/v1/chat/completions",
        source_artifacts=(),
    )


def test_artifact_binding_is_portable_and_hashes_exact_bytes(tmp_path):
    artifact = tmp_path / "x.txt"
    artifact.write_text("exact bytes", encoding="utf-8")
    binding = bind_artifact(tmp_path, "x.txt", role="test")
    assert binding.repo_relative_path == "x.txt"
    with pytest.raises(ValidationError):
        ArtifactBinding(repo_relative_path="/tmp/x", sha256="a" * 64, role="bad")
    with pytest.raises(ValueError):
        bind_artifact(tmp_path, "../escape", role="bad")


def test_draft_preserves_unresolved_items_without_unlocking_outcomes():
    manifest = PreOutcomeFreezeManifest(
        status=FreezeStatus.DRAFT,
        source_tree_sha="a" * 40,
        generator=_generator(),
        official_evaluation_artifacts=(),
        pending_items=("outer_fold_count",),
    )
    assert manifest.status is FreezeStatus.DRAFT
    assert manifest.formal_outcome_calls_at_freeze == 0


def test_frozen_status_cannot_hide_incomplete_configuration():
    with pytest.raises(ValidationError, match="pending"):
        PreOutcomeFreezeManifest(
            status=FreezeStatus.FROZEN,
            source_tree_sha="a" * 40,
            generator=_generator(),
            official_evaluation_artifacts=(),
            pending_items=("top_k",),
        )


def test_route_a_and_feature_leakage_are_fail_closed():
    with pytest.raises(ValidationError, match="other optional heads OFF"):
        PreOutcomeFreezeManifest(
            status=FreezeStatus.DRAFT,
            source_tree_sha="a" * 40,
            generator=_generator(),
            official_evaluation_artifacts=(),
            candidate_bundles=(
                CandidateBundleFreeze(
                    head=Head.MP,
                    compiler_id="mp-v1",
                    canonical_other_heads_off=False,
                ),
            ),
        )
    with pytest.raises(ValidationError, match="utility/outcome"):
        PreOutcomeFreezeManifest(
            status=FreezeStatus.DRAFT,
            source_tree_sha="a" * 40,
            generator=_generator(),
            official_evaluation_artifacts=(),
            feature_schemas=(
                FeatureSchemaFreeze(
                    head=Head.MS,
                    exact_feature_names=("worth_opening",),
                    contains_utility_or_outcome_feature=True,
                ),
            ),
        )


def test_effect_measurement_coding_is_positive_effect_not_utility_magnitude():
    valid = EffectMeasurementFreeze(
        task_type=TaskType.QA,
        scorer_id="es-memeval-official-v1",
        materially_better_rule="prefrozen task-specific comparison",
        equivalent_rule="prefrozen practical-equivalence region",
        uncertain_rule="scorer result cannot determine direction",
        invalid_rule="mechanical delivery or scoring failure",
    )
    assert valid.equivalent_target == 0
    assert valid.uncertain_enters_likelihood is False

    with pytest.raises(ValidationError, match="ON=1, OFF=0, equivalent=0"):
        EffectMeasurementFreeze(
            task_type=TaskType.QA,
            scorer_id="es-memeval-official-v1",
            materially_better_rule="rule",
            equivalent_rule="rule",
            uncertain_rule="rule",
            invalid_rule="rule",
            equivalent_target=1,
        )

    with pytest.raises(ValidationError, match="cannot enter"):
        EffectMeasurementFreeze(
            task_type=TaskType.QA,
            scorer_id="es-memeval-official-v1",
            materially_better_rule="rule",
            equivalent_rule="rule",
            uncertain_rule="rule",
            invalid_rule="rule",
            uncertain_enters_likelihood=True,
        )


def test_matched_random_must_match_prefrozen_on_counts_and_exact_token_budget():
    with pytest.raises(ValidationError, match="exact prefrozen ON counts and token budget"):
        PreOutcomeFreezeManifest(
            status=FreezeStatus.DRAFT,
            source_tree_sha="a" * 40,
            generator=_generator(),
            official_evaluation_artifacts=(),
            matched_random=MatchedRandomFreeze(
                construction_id="bad-near-match",
                exact_injected_token_budget=False,
            ),
        )
