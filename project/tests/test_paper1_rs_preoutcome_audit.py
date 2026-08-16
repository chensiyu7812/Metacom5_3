import hashlib
import json
from pathlib import Path

from metacom_pm.paper1.rs.preoutcome_audit import (
    ExplicitBoundary,
    RenderVariant,
    explicit_boundaries,
    exemplar_content_proxies,
    narrow_stateful_boundaries,
    prefix_any_boundaries,
    render_strategy_card,
    strategy_is_boundary_compatible,
)
from metacom_pm.paper1.rs.strategy_bank import StrategySourceCard


ROOT = Path(__file__).resolve().parents[1]


def _card(label="Reflection of feelings", example="It sounds like this was hard for you."):
    return StrategySourceCard(
        card_id="rs_src_0123456789abcdef01234567",
        source_dialogue_id="esconv_0001",
        source_turn_index=3,
        strategy_label=label,
        retrieval_text="seeker: My mother called yesterday.",
        guidance_text="Use the move only when it fits.",
        example_response=example,
        retrieval_text_sha256="0" * 64,
        example_response_sha256="1" * 64,
    )


def test_renderer_variants_are_explicitly_grounded_and_exemplar_is_delimited():
    card = _card()
    guidance_only = render_strategy_card(card, RenderVariant.GUIDANCE_ONLY)
    with_example = render_strategy_card(card, RenderVariant.GUIDANCE_PLUS_EXEMPLAR)
    assert card.example_response not in guidance_only
    assert card.example_response in with_example
    assert "another dialogue" in with_example
    assert "not evidence" in with_example
    assert "current visible dialogue" in guidance_only
    assert "current visible dialogue" in with_example


def test_exemplar_proxies_are_descriptive_not_a_composite_score():
    proxies = exemplar_content_proxies(
        _card(example="I told my mother on Monday that Sam could help.")
    )
    assert proxies.first_person_reference
    assert proxies.kinship_reference
    assert proxies.time_or_number_reference
    assert proxies.capitalized_token_reference
    assert not hasattr(proxies, "risk_score")


def test_explicit_boundary_categories_do_not_conflate_no_advice_and_listen_only():
    assert explicit_boundaries("I just want you to listen") == {
        ExplicitBoundary.LISTEN_ONLY
    }
    assert explicit_boundaries("I don't want advice") == {ExplicitBoundary.NO_ADVICE}
    assert explicit_boundaries("Please don't ask me questions") == {
        ExplicitBoundary.NO_PROBING
    }
    assert not explicit_boundaries(
        "Hopefully they don't ask me what choices he made and want details."
    )
    assert not explicit_boundaries("I just want to listen to what she says.")
    assert not explicit_boundaries("They do not want advice.")
    assert not explicit_boundaries("I have no advice for my friend.")
    assert explicit_boundaries("I don't want any advice.") == {
        ExplicitBoundary.NO_ADVICE
    }


def test_candidate_level_mapping_keeps_compatible_moves_available():
    listen = frozenset({ExplicitBoundary.LISTEN_ONLY})
    no_advice = frozenset({ExplicitBoundary.NO_ADVICE})
    no_probing = frozenset({ExplicitBoundary.NO_PROBING})
    assert not strategy_is_boundary_compatible("Providing Suggestions", listen)
    assert not strategy_is_boundary_compatible("Question", listen)
    assert not strategy_is_boundary_compatible("Providing Suggestions", no_advice)
    assert strategy_is_boundary_compatible("Question", no_advice)
    assert not strategy_is_boundary_compatible("Question", no_probing)
    assert strategy_is_boundary_compatible("Reflection of feelings", listen)
    assert strategy_is_boundary_compatible("Affirmation and Reassurance", no_probing)


def test_boundary_horizons_are_separate_audit_alternatives_with_narrow_revocation():
    dialogue = "\n".join(
        [
            "seeker: I don't want advice.",
            "supporter: I hear you.",
            "seeker: Actually, any advice?",
        ]
    )
    assert prefix_any_boundaries(dialogue) == {ExplicitBoundary.NO_ADVICE}
    assert narrow_stateful_boundaries(dialogue) == frozenset()


def test_negative_advice_language_does_not_revoke_a_persistent_boundary():
    dialogue = "\n".join(
        [
            "seeker: I don't want advice.",
            "supporter: I hear you.",
            "seeker: I still don't want any advice.",
            "supporter: Understood.",
            "seeker: I don't want you to recommend anything.",
        ]
    )
    assert narrow_stateful_boundaries(dialogue) == {ExplicitBoundary.NO_ADVICE}


def test_committed_renderer_audit_is_text_free_locked_and_not_a_freeze():
    summary_path = (
        ROOT / "data/paper1_public_rs/esconv_rs_renderer_boundary_audit_v1.json"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    manifest_path = ROOT / summary["card_manifest"]["path"]
    rows = manifest_path.read_text(encoding="utf-8").splitlines()
    digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()

    assert summary["status"] == (
        "ZERO_OUTCOME_DECISION_SURFACE_NOT_RENDERER_OR_BOUNDARY_FREEZE"
    )
    assert summary["formal_outcome_calls"] == 0
    assert summary["formal_unlock"] is False
    assert summary["tokenizer"]["provider_parity_status"].startswith(
        "PUBLIC_LLAMA31_TOKENIZER_MIRROR_"
    )
    assert summary["tokenizer"]["artifact_identity_status"] == (
        "LOCAL_TOKENIZER_BYTES_SHA256_VERIFIED"
    )
    assert summary["renderer_variants"]["guidance_only"]["distinct_render_count"] == 8
    assert summary["renderer_variants"]["guidance_plus_exemplar"][
        "distinct_render_count"
    ] > 8
    assert len(rows) == summary["card_manifest"]["rows"] == 12_169
    assert digest == summary["card_manifest"]["sha256"]
    assert summary["card_manifest"]["contains_raw_dialogue_or_example_text"] is False
    assert summary["boundary_candidate_mapping"]["whole_head_off"] is False
    assert summary["boundary_candidate_mapping"]["all_resource_arms_must_share_rule"]
    assert summary["boundary_candidate_mapping"]["status"].endswith(
        "RESEARCHER_DECISION_REQUIRED"
    )

    for raw in rows:
        row = json.loads(raw)
        assert "example_response" not in row
        assert "retrieval_text" not in row
        assert set(row["rendered_resource_tokens"]) == {
            "guidance_only",
            "guidance_plus_exemplar",
        }
        assert set(row["rendered_resource_sha256"]) == {
            "guidance_only",
            "guidance_plus_exemplar",
        }
