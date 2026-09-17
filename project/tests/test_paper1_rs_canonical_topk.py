import numpy as np

from metacom_pm.paper1.rs_atomic_move.canonical_topk import select_top_indices


def test_canonical_topk_uses_score_then_ticket_id_tie_break():
    scores = np.asarray([0.8, 0.9, 0.9, 0.7], dtype=np.float32)
    ids = ("t0", "t2", "t1", "t3")
    assert select_top_indices(
        scores, treatment_ids=ids, eligible_mask=np.ones(4, dtype=bool), top_k=2
    ) == (2, 1)


def test_canonical_topk_honors_full_lineage_exclusion_mask():
    scores = np.asarray([0.99, 0.9, 0.8], dtype=np.float32)
    ids = ("a", "b", "c")
    mask = np.asarray([False, True, True])
    assert select_top_indices(scores, treatment_ids=ids, eligible_mask=mask, top_k=2) == (1, 2)
