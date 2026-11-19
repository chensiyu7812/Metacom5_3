"""Round 14: pre-fixed overlap selection and overlap agreement (CPU, no labels generated)."""
from __future__ import annotations

from metacom_pm.rl1v3.review import screen_report as SR


def _items():
    rows = []
    for i in range(40):
        rows.append(dict(prefix_id=f"a{i:02d}", slot="CUR1", stratum_hidden_from_curator="S7_rank0" if i < 8 else "cue"))
    for i in range(50):
        rows.append(dict(prefix_id=f"b{i:02d}", slot="CUR2", stratum_hidden_from_curator="S7_rank0" if i < 10 else "other"))
    return rows


def test_prefixed_overlap_is_deterministic_15_percent_without_s7():
    it = _items()
    a = SR.prefixed_overlap(it, "CUR1", salt="s")
    b = SR.prefixed_overlap(it, "CUR2", salt="s")
    assert len(a) == 5 and len(b) == 6                      # ceil(0.15 * 32), ceil(0.15 * 40)
    assert a == SR.prefixed_overlap(list(reversed(it)), "CUR1", salt="s")
    assert all(int(x[1:]) >= 8 for x in a) and all(int(x[1:]) >= 10 for x in b)
    assert a != SR.prefixed_overlap(it, "CUR1", salt="other-salt")


def test_dp_overlap_uses_only_the_prefixed_order_and_labels():
    order = SR.fixed_order([f"p{i}" for i in range(20)], salt="d")
    labels = {p: ("S1" if i % 3 == 0 else "S2" if i % 3 == 1 else "S0") for i, p in enumerate(sorted(order))}
    pick = SR.dp_overlap_from_labels(order, labels)
    need = [p for p in order if labels[p] in ("S1", "S2")]
    assert len(need) == 14 and pick == need[:3]                      # ceil(0.15 * 14) = 3


def test_overlap_agreement_is_descriptive():
    prim = [dict(prefix_id="x", need="S1", sessions_needed="one"), dict(prefix_id="y", need="S2", sessions_needed=None),
            dict(prefix_id="z", need="S0", sessions_needed=None)]
    ovl = [dict(prefix_id="x", need="S1", sessions_needed="multiple"), dict(prefix_id="y", need="S1", sessions_needed="one"),
           dict(prefix_id="z", need="S0", sessions_needed=None)]
    r = SR.overlap_agreement(prim, ovl)
    assert r["items"] == 3 and r["need_agreement"] == round(2 / 3, 3) and r["s1_disagreements"] == 1
    assert r["sessions_needed_agreement_on_joint_s1"] == 0.0 and r["confusion"]["S2|S1"] == 1
    assert SR.overlap_agreement(prim, []) == dict(items=0)
