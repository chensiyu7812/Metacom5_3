"""Pre-registered B6e run report on fixture records (no model): denominators kept, nothing imputed."""
from __future__ import annotations

import pytest

from metacom_pm.rl1v3.evaluate import b6e_report as R


def att(status, subset, stratum, value=0.9, safety=(), key=None):
    if status == "refused":
        return dict(status="refused", key_sha256=key, subset=subset, stratum=stratum, reasons=["too_uncertain"])
    sens = {f"u={u}|g={g}": value - g for u in (0.0, 0.5, 1.0) for g in (0.0, 0.005, 0.01, 0.02)}
    return dict(status="computed", key_sha256=key, subset=subset, stratum=stratum,
                record=dict(value=value, sensitivity=sens, j1_safety_fail_items=list(safety)))


def test_report_keeps_denominators_and_never_imputes():
    gens = [dict(key_sha256=k, prefix_id="p1", subset=sub, finish_reason=f, input_tokens=1000, output_tokens=200,
                 seconds=2.0, peak_bytes=10, n_gets=1)
            for k, sub, f in (("k1", "OFF", "stop"), ("k2", "MP", "stop"), ("k3", "ME", "length"))]
    j1 = [dict(calls=1, item_flags={"G:1": ()}, ledger={}),
          dict(calls=2, item_flags={"I:1": ("overlap_ambiguous", "ambiguous_with:c1:X1")}, ledger={"ambiguous": {"c1:X2": ["c1:X1"]}}),
          dict(calls=2, item_flags={"S:1": ("parse_failed",)}, ledger={})]
    atts = [att("computed", "OFF", "history", key="k1"), att("computed", "MP", "history", safety=("S:1",), key="k2"),
            att("refused", "ME", "method", key="k3")]
    tables = [dict(prefix_id="p1", reachable=16, complete=False), dict(prefix_id="p2", reachable=8, complete=False)]
    rep = R.build(generations=gens, j1_runs=j1, attempts=atts, tables=tables)
    assert rep["generation"]["truncated"] == dict(n=3, k=1, rate=pytest.approx(1 / 3))
    assert rep["j1"]["full_parse"]["k"] == 2 and rep["j1"]["atomic_conflict"]["k"] == 1
    assert rep["er"]["computed"] == dict(n=24, k=2, rate=pytest.approx(2 / 24))
    assert rep["er"]["pending_or_missing"]["k"] == 22 and rep["er"]["safety_fail"]["k"] == 1
    assert rep["er"]["pending_counted_as_zero"] is False and rep["is_gsc"] is False
    assert rep["refusal"]["by_subset"]["ME"]["refused"] == 1 and rep["refusal"]["by_stratum"]["method"]["rate"] == 1.0
    assert rep["controls"]["OFF"]["computed"] == 1 and rep["controls"]["ME_only"]["computed"] == 0
    assert len(rep["sensitivity_12"]) == 12 and rep["sensitivity_12"]["u=0.5|g=0.01"]["n"] == 2
    assert rep["tables"]["dp_oracle_eligible"] == [] and rep["tables"]["ppo_eligible_without_zero_fill"] == []
    assert rep["cost"]["gets"]["total"] == 3 and rep["cost"]["seconds"]["mean"] == 2.0
