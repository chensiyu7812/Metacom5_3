"""B6e plan v3 selection: pre-registered, deterministic, replay-facts-only (formal integration B5 data)."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from metacom_pm.rl1v3.evaluate import b6e_select_v3 as S

V3 = Path(__file__).resolve().parents[1] / "outputs/pm_rl1/v3"
REPLAY = V3 / "WSB_S3/integration_acceptance_320a33d1/B5/replay_reports.jsonl"
COV = V3 / "B1/coverage_sample_v1.jsonl"
EXPECTED = ["01c44f464e0e", "fa14cf4451df", "b60fe830cb1b", "ac45ce97a037", "f310c0e490b1", "74a7a964cc18",
            "6ce6b7faa301", "ab3d17407ca4"]


def data():
    return [json.loads(x) for x in COV.read_text().splitlines()], [json.loads(x) for x in REPLAY.read_text().splitlines()]


def test_selection_on_the_formal_replay_meets_every_preregistered_constraint():
    cov, rep = data()
    s = S.select(cov, rep)
    assert [p[:12] for p in s["selected_ids"]] == EXPECTED
    sel = s["selected"]
    assert Counter(c["class"] for c in sel) == {"R16": 7, "MP8": 1}
    assert len({c["owner_id"] for c in sel}) == 8 and max(Counter(c["fold"] for c in sel).values()) <= 2
    assert {c["fold"] for c in sel} == {1, 2, 3, 4, 5}
    assert s["terminals"] == 120 and s["calls_upper_bound"]["g0_generation"] == 120
    assert s["calls_upper_bound"]["j1_item_judge"] == 360 and s["calls_upper_bound"]["paid_api"] == 0
    assert len(s["candidates"]) == 20 and all(c["fold"] != 6 for c in s["candidates"])
    keys = [c["order_key"] for c in s["candidates"]]
    assert keys == sorted(keys)


def test_selection_is_deterministic_and_ignores_any_quality_field():
    cov, rep = data()
    a = S.select(cov, rep)
    noisy = [dict(r, er_value=0.1, j1_quality=0.9, needcard_status="writer_failed") for r in rep]
    b = S.select(list(reversed(cov)), list(reversed(noisy)))
    assert a["selected_ids"] == b["selected_ids"] and a["rule_sha256"] == b["rule_sha256"] == S.rule_sha256()


def test_infeasible_constraints_stop_instead_of_relaxing():
    cov, rep = data()
    no_mp8 = [dict(r, n_reachable=16, unreachable_heads={}) if r["n_reachable"] == 8 else r for r in rep]
    with pytest.raises(S.SelectionInfeasible):
        S.select(cov, no_mp8)
    only_folds_1_4 = [c for c in cov if c["fold"] != 5]
    with pytest.raises(S.SelectionInfeasible):
        S.select(only_folds_1_4, rep)


def test_failed_replay_prefixes_are_not_selectable():
    cov, rep = data()
    first = S.select(cov, rep)["selected_ids"][0]
    s = S.select(cov, [dict(r, passed=False) if r["prefix_id"] == first else r for r in rep])
    assert first not in s["selected_ids"] and len(s["selected_ids"]) == 8
