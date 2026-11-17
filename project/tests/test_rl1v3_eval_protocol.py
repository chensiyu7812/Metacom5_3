"""Pre-registered evaluation arms and the never-a-single-number report."""
from __future__ import annotations

import pytest

from metacom_pm.rl1v3.evaluate import protocol as EP


def ep(pid, subset, value=0.5, **kw):
    base = dict(prefix_id=pid, subset=subset, er_value=value, j1_lower=.4, j1_upper=.6, gsc_lower=None,
                gsc_upper=None, hard_factual=None, hard_safety=None, j1_factual_fail=False, j1_safety_fail=False,
                misuse=False, required_heads=("ME",), optional_heads=("MP",), input_tokens=500,
                latency_pred=None, latency_measured=None, natural_weight=2.0, stratum="history")
    base.update(kw)
    return base


def all_arms():
    return {a.name: [ep("p1", a.subset or ("ME",)), ep("p2", (), value=None)] for a in EP.REQUIRED_ARMS}


def test_required_arms_are_fixed_and_oracle_is_privileged():
    names = [a.name for a in EP.REQUIRED_ARMS]
    assert names == ["OFF", "ME_only", "Fixed_best", "ALL", "OneShot", "Seq_BC", "PPO_BC_init",
                     "PPO_scratch", "PPO_NoText", "DP_Oracle"]
    oracle = next(a for a in EP.REQUIRED_ARMS if a.name == "DP_Oracle")
    assert not oracle.deployable and oracle.kind == "privileged"


def test_missing_required_arm_must_be_declared_with_reason():
    arms = all_arms()
    del arms["PPO_scratch"]
    with pytest.raises(ValueError, match="PPO_scratch"):
        EP.build_report(arms)
    with pytest.raises(ValueError, match="reason"):
        EP.build_report(arms, missing_arms={"PPO_scratch": " "})
    rep = EP.build_report(arms, missing_arms={"PPO_scratch": "run crashed; see log"})
    assert rep["arms"]["PPO_scratch"]["status"] == "missing"
    with pytest.raises(ValueError, match="outside"):
        EP.build_report(dict(all_arms(), Magic=[]))


def test_every_metric_is_reported_with_value_or_reason():
    rep = EP.build_report(all_arms(), oracle_value={"p1": .7})
    for name, arm in rep["arms"].items():
        m = arm["metrics"]
        assert list(m) == list(EP.METRICS)
        assert all(v["status"] in ("ok", "not_available") for v in m.values())
        assert all(v.get("reason") for v in m.values() if v["status"] == "not_available")
    off = rep["arms"]["OFF"]["metrics"]
    assert off["pending_rate"]["value"] == .5
    assert off["gsc_lower_mean"]["status"] == "not_available" and "J2" in off["gsc_lower_mean"]["reason"]
    assert off["latency_pred_mean"]["reason"].startswith("B4")
    assert off["regret_vs_oracle_mean"]["value"] == pytest.approx(.2)


def test_omission_and_unneeded_reads_use_needcard_heads():
    m = EP.arm_metrics([ep("a", ("MS",)), ep("b", ("ME", "RS")), ep("c", ("ME",))])
    assert m["omission_rate"]["value"] == pytest.approx(1 / 3)
    assert m["unneeded_read_rate"]["value"] == pytest.approx(2 / 4)
    assert m["get_rate_by_head"]["value"]["ME"] == pytest.approx(2 / 3)
    m2 = EP.arm_metrics([ep("a", ("ME",), required_heads=None)])
    assert m2["omission_rate"]["status"] == "not_available"
