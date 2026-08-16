from pathlib import Path

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import Head
from metacom_pm.paper1.core.freeze import (
    ArtifactBinding,
    CandidateBundleFreeze,
    FeatureSchemaFreeze,
    FreezeStatus,
    GeneratorStackBinding,
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
