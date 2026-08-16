import json
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

ROOT = Path(__file__).resolve().parents[1]


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


def test_active_draft_binds_dialogue_only_rs_artifacts_not_superseded_v1():
    manifest = json.loads(
        (ROOT / "data/paper1_authority/paper1_pre_outcome_freeze_draft_v1.json").read_text(
            encoding="utf-8"
        )
    )
    paths = {
        row["repo_relative_path"] for row in manifest["official_evaluation_artifacts"]
    }
    assert "data/paper1_public_rs/esconv_strategy_source_identity_dialogue_only_v2.jsonl" in paths
    assert "data/paper1_public_rs/esconv_rs_decision_state_identity_v1.jsonl" in paths
    assert "data/paper1_public_rs/esconv_rs_renderer_card_audit_v1.jsonl" in paths
    assert "data/paper1_public_rs/esconv_rs_renderer_boundary_audit_v1.json" in paths
    assert "data/paper1_authority/esconv_strategy_source_identity_v1.jsonl" not in paths
    assert manifest["status"] == "DRAFT_AWAITING_M1_INTEGRATION"
    assert manifest["formal_outcome_calls_at_freeze"] == 0
    assert manifest["notes"]["formal_unlock"] is False


def test_m2_decision_packet_is_a_locked_draft_with_explicit_researcher_choices():
    packet = json.loads(
        (ROOT / "data/paper1_authority/paper1_m2_decision_packet_draft_v1.json").read_text(
            encoding="utf-8"
        )
    )
    assert packet["status"] == "PRE_OUTCOME_DECISION_DRAFT_NOT_A_FREEZE_NOT_AN_UNLOCK"
    assert packet["formal_outcome_calls"] == 0
    assert packet["formal_unlock"] is False
    assert packet["researcher_decision_ids"]
    assert "rs_exemplar_policy" in packet["researcher_decision_ids"]
    assert "rs_boundary_horizon" in packet["researcher_decision_ids"]
    renderer = packet["evidence"]["rs_renderer_boundary_audit"]
    assert renderer["status"] == (
        "ZERO_OUTCOME_DECISION_SURFACE_NOT_RENDERER_OR_BOUNDARY_FREEZE"
    )
    assert renderer["tokenizer"]["provider_parity_status"].startswith(
        "PUBLIC_LLAMA31_TOKENIZER_MIRROR_"
    )
    assert any(
        row["status"] == "BLOCKED_PENDING_B_REPAIR" for row in packet["decisions"]
    )
