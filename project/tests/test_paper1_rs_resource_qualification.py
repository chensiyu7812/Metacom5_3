import hashlib

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.rs_atomic_move.resource_qualification import (
    AtomicityLabel,
    BoundaryCompatibilityLabel,
    CompletedSemanticsHumanReview,
    ExecutabilityLabel,
    LeakageLabel,
    RedundancyLabel,
    StateAppropriatenessLabel,
    StructuralAdjudication,
    StructuralExclusionReason,
    build_blind_review_materials,
    summarize_human_reviews,
    validate_complete_human_reviews,
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _packet() -> dict:
    rows = []
    families = (
        "affirmation_and_reassurance",
        "information",
        "others",
        "providing_suggestions",
        "question",
        "reflection_of_feelings",
        "restatement_or_paraphrasing",
        "self_disclosure",
    )
    ranks = (1, 2, 4, 8)
    for index in range(64):
        text = f"Atomic treatment {index}."
        rows.append(
            {
                "qualification_item_id": f"rs_semq_{index:024x}",
                "visible_state": f"seeker: visible state {index}",
                "current_user_text": f"visible state {index}",
                "exact_rendered_treatment": text,
                "rendered_card_text_sha256": _sha(text),
                "rank": ranks[index % 4],
                "sampling_primary_family": families[index % 8],
                "canonical_treatment_id": "rs_treatment_" + _sha(text)[:24],
                "cosine_similarity": 0.8,
                "source_dialogue_id": f"esconv_{index:04d}",
                "provenance_union": {
                    "source_dialogue_ids": [f"esconv_{index + 100:04d}"],
                },
            }
        )
    return {
        "sampling": {"actual_N": 64},
        "rows": rows,
        "human_judgments_completed": 0,
        "outcome_calls": 0,
    }


def _review(blind_item_id: str) -> dict:
    return {
        "blind_item_id": blind_item_id,
        "reviewer_id": "human-reviewer-1",
        "reviewer_is_human": True,
        "atomicity": AtomicityLabel.PASS,
        "state_appropriateness": StateAppropriatenessLabel.PASS,
        "boundary_compatibility": BoundaryCompatibilityLabel.NO_EXPLICIT_BOUNDARY,
        "executability": ExecutabilityLabel.PASS,
        "leakage": LeakageLabel.PASS,
        "redundancy_near_duplicate": RedundancyLabel.DISTINCT,
        "rationale": "The move is atomic, executable, and does not expose hidden source content.",
        "evaluates_response_quality_or_utility": False,
        "recommends_runtime_utility_filter": False,
    }


def test_blind_review_hides_rank_family_similarity_and_provenance():
    blind_rows, key = build_blind_review_materials(_packet(), blind_seed="fixed-seed")
    assert len(blind_rows) == 64
    assert len(key["rows"]) == 64
    dumped = blind_rows[0].model_dump()
    for forbidden in ("rank", "family", "similarity", "provenance", "qualification_item_id"):
        assert forbidden not in dumped
    assert key["rank_family_similarity_hidden_from_reviewer"] is True


def test_review_contract_forbids_utility_or_llm_substitution_surface():
    blind_rows, _ = build_blind_review_materials(_packet(), blind_seed="fixed-seed")
    bad = _review(blind_rows[0].blind_item_id)
    bad["reviewer_is_human"] = False
    bad["recommends_runtime_utility_filter"] = True
    with pytest.raises(ValidationError):
        CompletedSemanticsHumanReview.model_validate(bad)


def test_complete_review_requires_exact_64_and_summary_has_no_pass_gate():
    blind_rows, key = build_blind_review_materials(_packet(), blind_seed="fixed-seed")
    raw = [_review(row.blind_item_id) for row in blind_rows]
    with pytest.raises(ValueError, match="exact 64-item set"):
        validate_complete_human_reviews(blind_rows, raw[:-1])
    reviews = validate_complete_human_reviews(blind_rows, raw)
    summary = summarize_human_reviews(reviews, key)
    assert summary["N"] == 64
    assert summary["pass_or_fail_line_applied"] is False
    assert summary["candidate_level_utility_filter_created"] is False
    assert set(summary["by_rank_label_counts"]) == {"1", "2", "4", "8"}
    assert len(summary["by_family_label_counts"]) == 8


def test_structural_exclusion_requires_separate_deterministic_evidence():
    with pytest.raises(ValidationError, match="deterministic evidence"):
        StructuralAdjudication(
            qualification_item_id="rs_semq_" + "a" * 24,
            structurally_valid=False,
            exclusion_reasons=(StructuralExclusionReason.NON_ATOMIC_TREATMENT_CONFIRMED,),
        )
    valid = StructuralAdjudication(
        qualification_item_id="rs_semq_" + "a" * 24,
        structurally_valid=False,
        exclusion_reasons=(StructuralExclusionReason.NON_ATOMIC_TREATMENT_CONFIRMED,),
        deterministic_evidence=("two independently executable imperative clauses",),
    )
    assert valid.state_appropriateness_used_as_exclusion is False
    assert valid.redundancy_used_as_exclusion is False
    assert valid.utility_filter_used is False
