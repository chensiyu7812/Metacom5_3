from __future__ import annotations

import numpy as np
import pytest

from metacom_pm.contracts import MemorySource
from metacom_pm.hybrid_retrieval import HybridMemoryRetriever, SourceScoreFloors
from metacom_pm.hybrid_retrieval_diagnostics import (
    CalibrationExample,
    calibrate_source_floors,
    compare_fixed_token_budget,
    compare_fixed_top_k,
    iter_case_calibration_examples,
    split_of_user_id,
    _is_positive_label,
)
from metacom_pm.retrieval import MemoryRetriever


class _FakeEncoder:
    def __init__(self, vocab: dict[str, np.ndarray]):
        self.vocab = vocab

    def encode(self, texts):
        return np.stack([self.vocab[text] for text in texts])


def _one_hot(dimension: int, index: int) -> np.ndarray:
    vector = np.zeros(dimension, dtype=np.float64)
    vector[index] = 1.0
    return vector


def _memory_row(
    text: str,
    *,
    item_utility: str = "helpful",
    stale: bool = False,
    conflicts: bool = False,
) -> dict:
    return {
        "text": text,
        "item_utility": item_utility,
        "stale": stale,
        "conflicts_with_current_state": conflicts,
    }


def _bundle(user_id: str, cases: list[dict]) -> dict:
    return {"user_id": user_id, "cases": cases}


def test_split_of_user_id_accepts_all_four_and_rejects_garbage():
    assert split_of_user_id("pmv2_train_u001") == "train"
    assert split_of_user_id("pmv2_calibration_u012") == "calibration"
    assert split_of_user_id("pmv2_internal_test_u016") == "internal_test"
    assert split_of_user_id("pmv2_external_test_u003") == "external_test"
    with pytest.raises(ValueError):
        split_of_user_id("not_a_pmv2_user_id")


def test_is_positive_label_requires_helpful_and_fresh_and_nonconflicting():
    assert _is_positive_label(_memory_row("x")) is True
    assert _is_positive_label(_memory_row("x", stale=True)) is False
    assert _is_positive_label(_memory_row("x", conflicts=True)) is False
    assert _is_positive_label(_memory_row("x", item_utility="irrelevant")) is False
    assert _is_positive_label(_memory_row("x", item_utility="harmful")) is False


def test_iter_case_calibration_examples_filters_split_and_flattens_pools():
    bundles = [
        _bundle(
            "pmv2_train_u001",
            [
                {
                    "current_user_text": "q1",
                    "profile_memories": [_memory_row("mp text")],
                    "event_memories": [_memory_row("me text")],
                    "summary_memories": [_memory_row("ms text")],
                }
            ],
        ),
        _bundle(
            "pmv2_internal_test_u016",
            [
                {
                    "current_user_text": "q2",
                    "profile_memories": [_memory_row("should not appear")],
                    "event_memories": [],
                    "summary_memories": [],
                }
            ],
        ),
    ]
    examples = iter_case_calibration_examples(bundles, allowed_splits=frozenset({"train"}))
    assert len(examples) == 3
    assert {e.source for e in examples} == {MemorySource.MP, MemorySource.ME, MemorySource.MS}
    assert all(e.split == "train" for e in examples)
    assert all("should not appear" not in e.text for e in examples)


def test_calibrate_source_floors_fits_from_train_and_reports_calibration_only():
    encoder = _FakeEncoder(
        {
            "query": _one_hot(1, 0),
            "strong positive": _one_hot(1, 0),
            "weak positive": _one_hot(1, 0),
            "clear negative": _one_hot(1, 0),
        }
    )
    examples = [
        CalibrationExample("train", "query", MemorySource.ME, "strong positive", True),
        CalibrationExample("train", "query", MemorySource.ME, "weak positive", True),
        CalibrationExample("train", "query", MemorySource.ME, "clear negative", False),
        CalibrationExample("calibration", "query", MemorySource.ME, "strong positive", True),
        CalibrationExample("calibration", "query", MemorySource.ME, "clear negative", False),
    ]
    # All texts share the same fake vector/tokens, so lexical/semantic
    # scores are identical across rows here; what matters for this test is
    # the split-membership bookkeeping and count arithmetic, not score
    # values (test_hybrid_retrieval.py already covers scoring itself).
    result = calibrate_source_floors(examples, encoder=encoder)
    me = result[MemorySource.ME]
    assert me.train_positive_count == 2
    assert me.train_negative_count == 1
    assert me.calibration_positive_count == 1
    assert me.calibration_negative_count == 1
    assert me.calibration_recall is not None
    assert me.calibration_negative_exclusion_rate is not None


def test_calibrate_source_floors_raises_without_train_positives():
    encoder = _FakeEncoder({"q": _one_hot(1, 0), "x": _one_hot(1, 0)})
    examples = [
        CalibrationExample("train", "q", MemorySource.ME, "x", False),
    ]
    with pytest.raises(RuntimeError):
        calibrate_source_floors(examples, encoder=encoder)


def _fake_user(user_id: str) -> dict:
    return {
        "id": user_id,
        "basic_info": {},
        "dialog_history": [
            {
                "id": "sess_a",
                "timestamp": "t0",
                "summary": "",
                "dialogue": [
                    {"role": "seeker", "content": "work deadline stress worry"},
                ],
            },
            {
                "id": "sess_b",
                "timestamp": "t1",
                "summary": "",
                "dialogue": [
                    {"role": "seeker", "content": "completely unrelated hobby chatter"},
                ],
            },
        ],
        "subsequent_topics": [
            {"topic": "work deadline stress worry", "related_sessions": ["sess_a"]},
        ],
    }


def test_compare_fixed_top_k_finds_the_related_session_for_both_scorers():
    user = _fake_user("u1")
    encoder = _FakeEncoder(
        {
            "work deadline stress worry": _one_hot(2, 0),
            "completely unrelated hobby chatter": _one_hot(2, 1),
        }
    )
    lexical_retriever = MemoryRetriever(top_k_by_source={MemorySource.ME: 1})
    hybrid_retriever = HybridMemoryRetriever(
        semantic_encoder=encoder,
        top_k_by_source={MemorySource.ME: 1},
        floors_by_source={MemorySource.ME: SourceScoreFloors(-1.0, -1.0)},
    )
    result = compare_fixed_top_k(
        [user], lexical_retriever=lexical_retriever, hybrid_retriever=hybrid_retriever
    )
    assert result["lexical_only"].topics_evaluated == 1
    assert result["lexical_only"].hit_rate == 1.0
    assert result["hybrid"].topics_evaluated == 1
    assert result["hybrid"].hit_rate == 1.0
    assert len(result["lexical_only"].query_hashes) == 1


def test_compare_fixed_token_budget_finds_the_related_session_for_both_scorers():
    user = _fake_user("u1")
    encoder = _FakeEncoder(
        {
            "work deadline stress worry": _one_hot(2, 0),
            "completely unrelated hobby chatter": _one_hot(2, 1),
        }
    )
    hybrid_retriever = HybridMemoryRetriever(
        semantic_encoder=encoder,
        top_k_by_source={MemorySource.ME: 5},
        floors_by_source={MemorySource.ME: SourceScoreFloors(-1.0, -1.0)},
    )
    result = compare_fixed_token_budget(
        [user], hybrid_retriever=hybrid_retriever, token_budget=100
    )
    assert result["lexical_only"].hit_rate == 1.0
    assert result["hybrid"].hit_rate == 1.0
