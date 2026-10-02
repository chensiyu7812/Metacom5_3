"""Outcome-blind RS resource-semantics human-review contracts.

Human state-appropriateness is aggregate qualification evidence.  It is not a
runtime utility estimate and may never be used to delete or rerank an exact
treatment.  Candidate/state exclusion remains limited to separately confirmed
mechanical structure failures.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from enum import StrEnum
from math import sqrt
from typing import Any, Iterable, Literal, Mapping, Sequence

from pydantic import Field, model_validator

from metacom_pm.io import sha256_text
from metacom_pm.paper1.contracts import StrictContract

BLIND_REVIEW_PROTOCOL = "pm-paper1-rs-resource-semantics-blind-human-review-v1"
AGGREGATE_RULE_PROTOCOL = "pm-paper1-rs-resource-semantics-aggregate-rule-v1"


class AtomicityLabel(StrEnum):
    PASS = "PASS"
    MULTI_MOVE = "MULTI_MOVE"
    VAGUE = "VAGUE"
    UNCERTAIN = "UNCERTAIN"


class StateAppropriatenessLabel(StrEnum):
    PASS = "PASS"
    TOPIC_MISMATCH = "TOPIC_MISMATCH"
    UNSUPPORTED_ASSUMPTION = "UNSUPPORTED_ASSUMPTION"
    UNCERTAIN = "UNCERTAIN"


class BoundaryCompatibilityLabel(StrEnum):
    PASS = "PASS"
    BOUNDARY_CONFLICT = "BOUNDARY_CONFLICT"
    NO_EXPLICIT_BOUNDARY = "NO_EXPLICIT_BOUNDARY"
    UNCERTAIN = "UNCERTAIN"


class ExecutabilityLabel(StrEnum):
    PASS = "PASS"
    NOT_EXECUTABLE = "NOT_EXECUTABLE"
    UNDERSPECIFIED = "UNDERSPECIFIED"
    UNCERTAIN = "UNCERTAIN"


class LeakageLabel(StrEnum):
    PASS = "PASS"
    SOURCE_SPECIFIC_LEAKAGE = "SOURCE_SPECIFIC_LEAKAGE"
    OUTCOME_LEAKAGE = "OUTCOME_LEAKAGE"
    UNCERTAIN = "UNCERTAIN"


class RedundancyLabel(StrEnum):
    DISTINCT = "DISTINCT"
    VISIBLE_REDUNDANCY = "VISIBLE_REDUNDANCY"
    NEAR_DUPLICATE = "NEAR_DUPLICATE"
    UNCERTAIN = "UNCERTAIN"


class BlindSemanticsReviewItem(StrictContract):
    protocol: Literal[BLIND_REVIEW_PROTOCOL] = BLIND_REVIEW_PROTOCOL
    blind_item_id: str = Field(pattern=r"^rs_semblind_[0-9a-f]{24}$")
    visible_state: str = Field(min_length=1)
    current_user_text: str = Field(min_length=1)
    exact_rendered_treatment: str = Field(min_length=1)
    rendered_card_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_id: None = None
    atomicity: None = None
    state_appropriateness: None = None
    boundary_compatibility: None = None
    executability: None = None
    leakage: None = None
    redundancy_near_duplicate: None = None
    rationale: None = None
    evaluates_response_quality_or_utility: Literal[False] = False
    recommends_runtime_utility_filter: Literal[False] = False

    @model_validator(mode="after")
    def verify_treatment_hash(self) -> "BlindSemanticsReviewItem":
        if sha256_text(self.exact_rendered_treatment) != self.rendered_card_text_sha256:
            raise ValueError("blind review treatment text/hash mismatch")
        return self


class CompletedSemanticsHumanReview(StrictContract):
    protocol: Literal[BLIND_REVIEW_PROTOCOL] = BLIND_REVIEW_PROTOCOL
    blind_item_id: str = Field(pattern=r"^rs_semblind_[0-9a-f]{24}$")
    reviewer_id: str = Field(min_length=1)
    reviewer_is_human: Literal[True] = True
    atomicity: AtomicityLabel
    state_appropriateness: StateAppropriatenessLabel
    boundary_compatibility: BoundaryCompatibilityLabel
    executability: ExecutabilityLabel
    leakage: LeakageLabel
    redundancy_near_duplicate: RedundancyLabel
    rationale: str = Field(min_length=1)
    evaluates_response_quality_or_utility: Literal[False] = False
    recommends_runtime_utility_filter: Literal[False] = False


class StructuralExclusionReason(StrEnum):
    IDENTITY_OR_HASH_FAILURE = "IDENTITY_OR_HASH_FAILURE"
    LEAVE_DIALOGUE_OUT_FAILURE = "LEAVE_DIALOGUE_OUT_FAILURE"
    NON_ATOMIC_TREATMENT_CONFIRMED = "NON_ATOMIC_TREATMENT_CONFIRMED"
    EXPLICIT_BOUNDARY_CONFLICT_CONFIRMED = "EXPLICIT_BOUNDARY_CONFLICT_CONFIRMED"
    NON_EXECUTABLE_TREATMENT_CONFIRMED = "NON_EXECUTABLE_TREATMENT_CONFIRMED"
    SOURCE_OR_OUTCOME_LEAKAGE_CONFIRMED = "SOURCE_OR_OUTCOME_LEAKAGE_CONFIRMED"


class StructuralAdjudication(StrictContract):
    """Separate mechanical adjudication; human fit alone cannot exclude."""

    qualification_item_id: str = Field(pattern=r"^rs_semq_[0-9a-f]{24}$")
    structurally_valid: bool
    exclusion_reasons: tuple[StructuralExclusionReason, ...] = ()
    deterministic_evidence: tuple[str, ...] = ()
    state_appropriateness_used_as_exclusion: Literal[False] = False
    redundancy_used_as_exclusion: Literal[False] = False
    near_duplicate_threshold_used: Literal[False] = False
    utility_filter_used: Literal[False] = False

    @model_validator(mode="after")
    def validity_matches_reasons(self) -> "StructuralAdjudication":
        if self.structurally_valid == bool(self.exclusion_reasons):
            raise ValueError("structural validity must be true iff exclusion reasons are empty")
        if self.exclusion_reasons and not self.deterministic_evidence:
            raise ValueError("structural exclusion requires deterministic evidence")
        return self


def make_blind_item_id(qualification_item_id: str, *, blind_seed: str) -> str:
    return "rs_semblind_" + sha256_text(f"{blind_seed}|{qualification_item_id}")[:24]


def build_blind_review_materials(
    packet: Mapping[str, Any], *, blind_seed: str
) -> tuple[list[BlindSemanticsReviewItem], dict[str, Any]]:
    """Create a rank/family/similarity-blind form and a separately held key."""

    rows = list(packet.get("rows") or [])
    if packet.get("outcome_calls") != 0:
        raise ValueError("semantics packet must remain outcome-free")
    if packet.get("human_judgments_completed") != 0:
        raise ValueError("source packet is no longer the pristine pre-review packet")
    if len(rows) != 64 or packet.get("sampling", {}).get("actual_N") != 64:
        raise ValueError("expected the frozen 64-item semantics packet")

    blind_rows: list[BlindSemanticsReviewItem] = []
    key_rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        qualification_item_id = str(row["qualification_item_id"])
        blind_item_id = make_blind_item_id(qualification_item_id, blind_seed=blind_seed)
        if blind_item_id in seen:
            raise ValueError("blind item id collision")
        seen.add(blind_item_id)
        blind_rows.append(
            BlindSemanticsReviewItem(
                blind_item_id=blind_item_id,
                visible_state=row["visible_state"],
                current_user_text=row["current_user_text"],
                exact_rendered_treatment=row["exact_rendered_treatment"],
                rendered_card_text_sha256=row["rendered_card_text_sha256"],
            )
        )
        key_rows.append(
            {
                "blind_item_id": blind_item_id,
                "qualification_item_id": qualification_item_id,
                "rank": row["rank"],
                "sampling_primary_family": row["sampling_primary_family"],
                "canonical_treatment_id": row["canonical_treatment_id"],
                "cosine_similarity": row["cosine_similarity"],
                "source_dialogue_id": row["source_dialogue_id"],
                "provenance_union": row["provenance_union"],
            }
        )

    # The reviewer sees a deterministic pseudorandom order, not packet/rank order.
    blind_rows.sort(key=lambda row: sha256_text(f"{blind_seed}|order|{row.blind_item_id}"))
    key_rows.sort(key=lambda row: row["blind_item_id"])
    return blind_rows, {
        "protocol": BLIND_REVIEW_PROTOCOL,
        "blind_seed": blind_seed,
        "rows": key_rows,
        "rank_family_similarity_hidden_from_reviewer": True,
        "key_must_not_be_given_to_reviewer_until_review_is_locked": True,
    }


def validate_complete_human_reviews(
    blind_items: Sequence[BlindSemanticsReviewItem],
    raw_reviews: Iterable[Mapping[str, Any]],
) -> list[CompletedSemanticsHumanReview]:
    expected = {row.blind_item_id for row in blind_items}
    reviews = [CompletedSemanticsHumanReview.model_validate(row) for row in raw_reviews]
    observed = [row.blind_item_id for row in reviews]
    if len(observed) != len(set(observed)):
        raise ValueError("duplicate human review blind item id")
    if set(observed) != expected:
        missing = sorted(expected - set(observed))
        extra = sorted(set(observed) - expected)
        raise ValueError(f"human review set is not the exact 64-item set: missing={missing}, extra={extra}")
    return reviews


def summarize_human_reviews(
    reviews: Sequence[CompletedSemanticsHumanReview], key: Mapping[str, Any]
) -> dict[str, Any]:
    """Fixed descriptive summaries only; this function never emits PASS/FAIL."""

    key_by_blind = {row["blind_item_id"]: row for row in key["rows"]}
    if set(key_by_blind) != {row.blind_item_id for row in reviews}:
        raise ValueError("review/key identity mismatch")
    dimensions = {
        "atomicity": AtomicityLabel,
        "state_appropriateness": StateAppropriatenessLabel,
        "boundary_compatibility": BoundaryCompatibilityLabel,
        "executability": ExecutabilityLabel,
        "leakage": LeakageLabel,
        "redundancy_near_duplicate": RedundancyLabel,
    }

    def wilson_95(successes: int, total: int) -> list[float]:
        if total == 0:
            return [0.0, 0.0]
        z = 1.959963984540054
        proportion = successes / total
        denominator = 1 + z * z / total
        centre = (proportion + z * z / (2 * total)) / denominator
        half_width = (
            z
            * sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
            / denominator
        )
        return [max(0.0, centre - half_width), min(1.0, centre + half_width)]

    def counts(group: Sequence[CompletedSemanticsHumanReview]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for dimension, label_enum in dimensions.items():
            observed = Counter(str(getattr(row, dimension)) for row in group)
            total = len(group)
            result[dimension] = {
                str(label): {
                    "n": observed[str(label)],
                    "N": total,
                    "proportion": observed[str(label)] / total if total else None,
                    "wilson_95": wilson_95(observed[str(label)], total),
                }
                for label in label_enum
            }
        return result

    by_rank: dict[str, list[CompletedSemanticsHumanReview]] = defaultdict(list)
    by_family: dict[str, list[CompletedSemanticsHumanReview]] = defaultdict(list)
    for review in reviews:
        metadata = key_by_blind[review.blind_item_id]
        by_rank[str(metadata["rank"])].append(review)
        by_family[str(metadata["sampling_primary_family"])].append(review)
    return {
        "protocol": AGGREGATE_RULE_PROTOCOL,
        "status": "DESCRIPTIVE_RESOURCE_RETRIEVER_QUALIFICATION_EVIDENCE_ONLY",
        "N": len(reviews),
        "overall_label_counts": counts(reviews),
        "by_rank_label_counts": {name: counts(rows) for name, rows in sorted(by_rank.items())},
        "by_family_label_counts": {name: counts(rows) for name, rows in sorted(by_family.items())},
        "pass_or_fail_line_applied": False,
        "candidate_level_utility_filter_created": False,
        "top_k_or_outcome_selected": False,
    }
