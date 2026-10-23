import hashlib

import pytest

from metacom_pm.paper1.contracts import CandidateLineage, CandidateRecord, Head
from metacom_pm.paper1.execution.packing import (
    PACKING_PROTOCOL,
    ResourceBudgetOverflow,
    pack_ranked_prefix,
    rank_candidates,
    select_ranked_prefix,
)


def _candidate(candidate_id: str, content: str, *, head: Head = Head.ME) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        head=head,
        content=content,
        token_count=len(content),
        lineage=CandidateLineage(
            source="test",
            owner_id="p1",
            source_record_ids=(candidate_id,),
            strict_past=True,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        ),
    )


def test_ranking_uses_cosine_then_candidate_id_for_exact_ties():
    candidates = (_candidate("z", "z"), _candidate("a", "a"), _candidate("b", "b"))
    ranked = rank_candidates(
        query_vector=(1.0, 0.0),
        candidates=candidates,
        candidate_vectors={"z": (1.0, 0.0), "a": (1.0, 0.0), "b": (0.0, 1.0)},
    )
    assert [row.candidate.candidate_id for row in ranked] == ["a", "z", "b"]


def test_prefix_is_exact_and_never_backfills_or_reorders():
    candidates = (_candidate("a", "alpha"), _candidate("b", "beta"))
    ranked = rank_candidates(
        query_vector=(1.0, 0.0),
        candidates=candidates,
        candidate_vectors={"a": (1.0, 0.0), "b": (0.5, 0.5)},
    )
    assert [row.candidate.candidate_id for row in select_ranked_prefix(ranked, k=1)] == ["a"]
    assert len(select_ranked_prefix(ranked, k=9)) == 2


def test_zero_is_true_off_and_on_pack_preserves_exact_prefix():
    candidates = (_candidate("a", "alpha"), _candidate("b", "beta"))
    ranked = rank_candidates(
        query_vector=(1.0, 0.0),
        candidates=candidates,
        candidate_vectors={"a": (1.0, 0.0), "b": (0.5, 0.5)},
    )
    off = pack_ranked_prefix(
        head=Head.ME,
        ranked=ranked,
        k=0,
        target_owner_id="p1",
        token_counter=len,
    )
    assert off.protocol == PACKING_PROTOCOL
    assert off.realized_k == 0
    assert off.envelope.resource_block is None

    on = pack_ranked_prefix(
        head=Head.ME,
        ranked=ranked,
        k=2,
        target_owner_id="p1",
        token_counter=len,
    )
    assert on.envelope.bundle.candidate_ids == ("a", "b")


def test_overflow_fails_without_mutating_the_selected_prefix():
    candidate = _candidate("a", "alpha")
    ranked = rank_candidates(
        query_vector=(1.0, 0.0),
        candidates=(candidate,),
        candidate_vectors={"a": (1.0, 0.0)},
    )
    with pytest.raises(ResourceBudgetOverflow, match="no truncation/drop/backfill"):
        pack_ranked_prefix(
            head=Head.ME,
            ranked=ranked,
            k=1,
            target_owner_id="p1",
            token_counter=len,
            max_resource_tokens=1,
        )


def test_missing_vector_and_mixed_head_fail_closed():
    me = _candidate("me", "event")
    with pytest.raises(ValueError, match="missing candidate vectors"):
        rank_candidates(query_vector=(1.0, 0.0), candidates=(me,), candidate_vectors={})

    mp = _candidate("mp", "profile", head=Head.MP)
    ranked = rank_candidates(
        query_vector=(1.0, 0.0),
        candidates=(mp,),
        candidate_vectors={"mp": (1.0, 0.0)},
    )
    with pytest.raises(ValueError, match="another head"):
        pack_ranked_prefix(
            head=Head.ME,
            ranked=ranked,
            k=1,
            target_owner_id="p1",
            token_counter=len,
        )
