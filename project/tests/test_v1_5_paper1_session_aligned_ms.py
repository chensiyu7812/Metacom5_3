from __future__ import annotations

import numpy as np

from metacom_pm.v1_5_paper1_session_aligned_ms import (
    build_surfaces,
    checkpoint_prefix,
    rank1_rows,
    session_resource_text,
    token_jaccard,
    validate_public_surfaces,
)


def _user():
    return {
        "id": "p1",
        "dialog_history": [
            {
                "id": "s1",
                "dialogue": [
                    {"idx": 1, "role": "seeker", "content": "old " * 30},
                    {"idx": 2, "role": "supporter", "content": "go on"},
                    {"idx": 3, "role": "seeker", "content": "detail " * 25},
                ],
            },
            {
                "id": "s2",
                "dialogue": [
                    {"idx": 1, "role": "seeker", "content": "current " * 20},
                    {"idx": 2, "role": "supporter", "content": "I hear you"},
                    {"idx": 3, "role": "seeker", "content": "topic " * 31},
                ],
            },
        ],
    }


def test_checkpoint_is_first_prefix_at_fifty_seeker_words():
    session = _user()["dialog_history"][1]
    prefix, raw_index = checkpoint_prefix(session)
    assert raw_index == 3
    assert len(prefix) == 3


def test_resource_is_exact_seeker_only_session():
    text = session_resource_text(_user()["dialog_history"][0])
    assert text.count("SEEKER:") == 2
    assert "go on" not in text
    assert "old" in text and "detail" in text


def test_surface_rank1_and_validation_are_session_aligned():
    states, candidates = build_surfaces(
        [_user()], {"evo::p1": {"split_group_key": "g1", "outer_fold": 1}}
    )
    state_vectors = {row["state_id"]: np.array([1.0, 0.0]) for row in states}
    candidate_vectors = {
        row["candidate_id"]: np.array([1.0, 0.0]) if row["source_session_id"] == "s1" else np.array([0.0, 1.0])
        for row in candidates
    }
    ranked = rank1_rows(states, candidates, state_vectors, candidate_vectors)
    assert ranked[0]["candidate_present"] is False
    assert ranked[1]["candidate_source_session_id"] == "s1"
    assert validate_public_surfaces(states, candidates, ranked)["status"] == "PASS"


def test_jaccard_is_bounded():
    assert token_jaccard("a b", "b c") == 1 / 3
    assert token_jaccard("", "b") == 0.0
