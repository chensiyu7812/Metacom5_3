#!/usr/bin/env python3
"""Apply the frozen MS/MP V1.1 development gate without API calls."""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import read_json, read_jsonl, write_json  # noqa: E402
from metacom_pm.v1_5_mp_function_pair_blind_review import decode_mp_function_verdict  # noqa: E402
from metacom_pm.v1_5_source_aware_risk_blind_review import RISK_DIMENSION_FIELDS  # noqa: E402

MANIFEST = ROOT / "outputs/pm_v1_5_paper1_ms_mp_v1_1_blind_review_manifest_20260813"
LIVE = ROOT / "outputs/pm_v1_5_paper1_ms_mp_v1_1_blind_review_live_20260813"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_mp_v1_1_blind_review_aggregate_20260813"
MS_CLOSEOUT = ROOT / "data/pm_v1_5_contracts/paper1_ms_v1_1_panel_generation_closeout_v1.json"


def main() -> None:
    calls = {r["logical_call_id"]: r for r in read_jsonl(MANIFEST / "calls_private.jsonl")}
    results = {r["logical_call_id"]: r for r in read_jsonl(LIVE / "results_private.jsonl")}
    if set(calls) != set(results) or any(not r["schema_valid_and_locally_validated"] for r in results.values()):
        raise RuntimeError("all exact 50 calls must be complete and valid")
    criteria = {}
    for comp in ("MS", "MP"):
        quality = []
        for lid, c in calls.items():
            if c["kind"] != f"{comp.lower()}_quality": continue
            v = results[lid]["validated_review"]["verdict"]
            winner = c["a_arm"] if v == "A_BETTER" else c["b_arm"] if v == "B_BETTER" else None
            quality.append("win" if winner == f"{comp}+R0" else "loss" if winner == "M0+R0" else "neutral")
        risk_by_case = {}
        for lid, c in calls.items():
            if c["kind"] == f"{comp.lower()}_risk": risk_by_case.setdefault(c["case_id"], {})[c["arm"]] = results[lid]["validated_review"]
        material, critical = [], []
        for cid, arms in risk_by_case.items():
            b, t = arms["M0+R0"], arms[f"{comp}+R0"]
            if any(t[f] >= 2 and t[f] > b[f] for f in RISK_DIMENSION_FIELDS): material.append(cid)
            if any(t[f] == 3 for f in RISK_DIMENSION_FIELDS): critical.append(cid)
        labels = []
        for lid, c in calls.items():
            if comp == "MS" and c["kind"] == "ms_function": labels.append(results[lid]["validated_review"]["label"])
            if comp == "MP" and c["kind"] == "mp_function_pair": labels.append(decode_mp_function_verdict(
                results[lid]["validated_review"]["verdict"], mp_position=c["mp_position"]))
        qpass = quality.count("win") > quality.count("loss")
        rpass = not material and not critical
        fpass = labels.count("CLEAR") >= 1 and sum(x in ("CLEAR", "PLAUSIBLE") for x in labels) >= 2
        criteria[comp.lower()] = {"quality": {"wins": quality.count("win"), "losses": quality.count("loss"),
            "neutral": quality.count("neutral"), "pass": qpass}, "risk": {"material_increase_cases": material,
            "critical_cases": critical, "pass": rpass}, "function": {"labels": labels,
            "clear": labels.count("CLEAR"), "clear_or_plausible": sum(x in ("CLEAR", "PLAUSIBLE") for x in labels),
            "pass": fpass}, "pass_this_round": qpass and rpass and fpass}
    closeout = read_json(MS_CLOSEOUT)
    integrity = closeout["ignore_integrity_precheck"]
    ignore_pass = (
        closeout["completed_logical_calls"] == closeout["planned_logical_calls"] == 30
        and integrity["ignore_reply_rows"] == 6
        and integrity["regression_probe_hits"] == 0
        and integrity["regression_probe_pass"] is True
        and integrity["physical_source_exclusion"].startswith("Passed")
    )
    criteria["ms"]["ignore_integrity"] = {
        "pass": ignore_pass,
        "source": str(MS_CLOSEOUT.relative_to(ROOT)),
        "ignore_reply_rows": integrity["ignore_reply_rows"],
        "regression_probe_hits": integrity["regression_probe_hits"],
    }
    criteria["ms"]["pass_this_round"] = criteria["ms"]["pass_this_round"] and criteria["ms"]["ignore_integrity"]["pass"]
    both = criteria["ms"]["pass_this_round"] and criteria["mp"]["pass_this_round"]
    label = "FIRST_VERSION_DEVELOPMENT_PROMOTION_MET_BOTH_HEADS" if both else (
        "FIRST_VERSION_DEVELOPMENT_PROMOTION_PARTIAL" if criteria["ms"]["pass_this_round"] or criteria["mp"]["pass_this_round"] else "FIRST_VERSION_DEVELOPMENT_PROMOTION_NOT_MET")
    OUT.mkdir(parents=True, exist_ok=True)
    report = {"protocol": "pm-v1.5-paper1-ms-mp-v1-1-blind-review-aggregate-v1",
        "status": "COMPLETE_FROZEN_DEVELOPMENT_GATE_APPLIED", "criteria": criteria,
        "verdict": {"label": label, "both_pass": both},
        "scope": "Development promotion only; never formal head pass or external-test pass.", "api_calls": 0}
    write_json(OUT / "report.json", report); print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
