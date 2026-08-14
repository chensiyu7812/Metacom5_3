from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MS_OUT = ROOT / "outputs/pm_v1_5_paper1_ms_v1_1_panel_20260813"
MP_OUT = ROOT / "outputs/pm_v1_5_paper1_mp_v1_1_panel_20260813"


def _read(path: Path) -> dict:
    return json.loads((path / "report.json").read_text(encoding="utf-8"))


def _cases(path: Path) -> list[dict]:
    return [json.loads(l) for l in (path / "development_cases_private.jsonl").read_text(encoding="utf-8").splitlines() if l]


def test_ms_panel_is_owner_unique_across_whole_panel():
    cases = _cases(MS_OUT)
    owners = [c["runtime_owner_key"] for c in cases]
    assert len(owners) == len(set(owners))


def test_mp_panel_is_owner_unique_across_whole_panel():
    cases = _cases(MP_OUT)
    owners = [c["runtime_owner_key"] for c in cases]
    assert len(owners) == len(set(owners))


def test_ms_panel_used_full_context_for_every_case():
    for case in _cases(MS_OUT):
        assert case["used_full_context"] is True


def test_mp_panel_used_full_context_for_every_case():
    for case in _cases(MP_OUT):
        assert case["used_full_context"] is True


def test_ms_panel_every_case_has_an_explicit_pre_decision():
    for case in _cases(MS_OUT):
        assert case["pre_decision"] in ("USE", "ASK", "IGNORE")


def test_ms_panel_ignore_cases_carry_a_real_source_for_the_regression_probe():
    cases = {c["case_id"]: c for c in _cases(MS_OUT)}
    ignore_cases = [c for c in cases.values() if c["pre_decision"] == "IGNORE"]
    with_source = [c for c in ignore_cases if c["ms_exact_source"]]
    assert len(with_source) >= 2  # echo control + the p6 regression probe


def test_ms_panel_regression_probe_reuses_the_exact_leaked_p6_source():
    cases = _cases(MS_OUT)
    probe = [c for c in cases if c["stratum"] == "IGNORE_topical_mismatch_regression_probe"]
    assert len(probe) == 1
    assert "blind sided" in probe[0]["ms_exact_source"]
    assert "never cheated" in probe[0]["ms_exact_source"]


def test_ms_panel_calls_are_deduplicated_no_byte_identical_duplicates():
    report = _read(MS_OUT)
    hashes = [c["prompt_sha256"] for c in report["manifest_calls"]]
    assert len(hashes) == len(set(hashes)) == report["total_calls"]


def test_ms_and_mp_panels_are_zero_api():
    for out in (MS_OUT, MP_OUT):
        report = _read(out)
        assert report["api_calls"] == 0
        assert report["estimated_cost_usd"] == 0.0


def test_mp_panel_constrain_candidates_selected_for_concrete_slot_plausibility():
    report = _read(MP_OUT)
    assert report["strata_counts"]["CONSTRAIN_eligible"] >= 4
    assert "corpus_disclosure" in report
