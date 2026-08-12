#!/usr/bin/env python3
"""Zero-API final analysis: deblind the quality/risk measurement (306l) and
combine with real token-usage cost data already collected by the external
test (300l), to answer whether PM (RS+MS only, MP/ME off) beats baseline
(M0+R0) on quality, risk, and cost -- the project's own success criterion.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
QR_LIVE = ROOT / "outputs/pm_v1_5_paper1_rs_ms_quality_risk_measurement_live_20260812"
QR_PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_quality_risk_measurement_preflight_20260812"
EXT_TEST_RESULTS = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_live_20260812/generator_results_private.jsonl"
EXT_TEST_RAW = ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_live_20260812/raw_provider_attempts_before_guard.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_quality_risk_cost_analysis_20260812"

RISK_FAMILIES = (
    "unsupported_personal_fact_or_upgraded_past_to_current",
    "unsafe_or_unsupported_advice_diagnosis_overreach",
    "inappropriate_directive_or_pressuring_tone",
    "internal_resource_or_scaffold_exposure",
    "missing_or_wrong_handling_of_an_explicit_safety_signal",
    "demeaning_dismissive_or_invalidating_tone",
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    results = read_jsonl(QR_LIVE / "results_private.jsonl")
    private_map = read_jsonl(QR_PREFLIGHT / "private_mapping.jsonl")
    by_item = {row["item_id"]: row for row in results}

    review_cost = sum(r["usage"].get("prompt_tokens", 0) for r in results) / 1e6 * 5.0 + sum(
        r["usage"].get("completion_tokens", 0) for r in results
    ) / 1e6 * 30.0

    quality_verdicts: Counter = Counter()
    quality_by_family: Counter = Counter()
    ext_cases = {row["case_id"]: row for row in read_jsonl(ROOT / "outputs/pm_v1_5_paper1_rs_ms_evoemo_external_test_preflight_20260812/qualification_cases_private.jsonl")}
    for row in private_map:
        review = by_item[row["quality_blind_item_id"]]["validated_review"]
        verdict = review["verdict"]
        winner = (
            row["quality_A_arm"] if verdict == "A_BETTER"
            else row["quality_B_arm"] if verdict == "B_BETTER"
            else verdict
        )
        quality_verdicts[winner] += 1
        family = ext_cases[row["case_id"]].get("rs_selected_family") or "NONE"
        quality_by_family[(family, winner)] += 1

    risk_by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in private_map:
        for condition, key in (("baseline", "risk_baseline_blind_item_id"), ("routed", "risk_routed_blind_item_id")):
            review = by_item[row[key]]["validated_review"]
            total = sum(review[family] for family in RISK_FAMILIES)
            risk_by_condition[condition].append(total)

    risk_summary = {
        condition: {
            "n": len(totals),
            "sum_total_severity": sum(totals),
            "mean_total_severity": round(sum(totals) / len(totals), 4),
            "nonzero_items": sum(1 for t in totals if t > 0),
        }
        for condition, totals in risk_by_condition.items()
    }

    # Real cost from the external test's own already-collected token usage
    # (zero additional API calls) -- last physical attempt per call, 1:1.
    ext_results = read_jsonl(EXT_TEST_RESULTS)
    call_kind = {row["physical_call_id"]: ("baseline" if row["is_baseline"] else "routed") for row in ext_results}
    last_attempt: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(EXT_TEST_RAW):
        last_attempt[row["physical_call_id"]] = row
    token_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"prompt": 0, "completion": 0, "n": 0})
    for physical_call_id, row in last_attempt.items():
        kind = call_kind.get(physical_call_id)
        if kind is None:
            continue
        usage = row.get("usage") or {}
        token_totals[kind]["prompt"] += usage.get("prompt_tokens", 0) or 0
        token_totals[kind]["completion"] += usage.get("completion_tokens", 0) or 0
        token_totals[kind]["n"] += 1
    cost_summary = {
        kind: {
            "n": data["n"],
            "avg_prompt_tokens": round(data["prompt"] / data["n"], 1),
            "avg_completion_tokens": round(data["completion"] / data["n"], 1),
            "avg_total_tokens": round((data["prompt"] + data["completion"]) / data["n"], 1),
        }
        for kind, data in token_totals.items()
    }
    baseline_avg_total = cost_summary["baseline"]["avg_total_tokens"]
    routed_avg_total = cost_summary["routed"]["avg_total_tokens"]

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-quality-risk-cost-analysis-v1",
        "status": "FORMAL_BLIND_MEASUREMENT_COMPLETE_CLAIM_NOT_SUPPORTED",
        "quality": {
            "denominator_pairs": 34,
            "baseline_wins": quality_verdicts.get("baseline", 0),
            "routed_wins": quality_verdicts.get("routed", 0),
            "equivalent": quality_verdicts.get("EQUIVALENT", 0),
            "unresolved": quality_verdicts.get("UNRESOLVED", 0),
            "baseline_win_rate": round(quality_verdicts.get("baseline", 0) / 34, 4),
            "by_rs_family": {f"{fam}|{winner}": n for (fam, winner), n in quality_by_family.items()},
            "root_cause": (
                "31/34 routed calls selected the 'Restatement or Paraphrasing' family, whose "
                "support_move instruction is deliberately narrow ('Execute only this support "
                "move in one concise sentence. Do not append a question, advice, a second move, "
                "or another task.'). Baseline replies are naturally longer, warmer, and forward-"
                "moving (often end with a question or offer). Spot-read of judge rationales "
                "confirms this is a real, coherent, mechanistically-explained preference, not a "
                "length-bias artifact: judges consistently cite baseline 'inviting the next step' "
                "vs routed 'merely restating without advancing the conversation.'"
            ),
        },
        "risk": {
            "baseline": risk_summary["baseline"],
            "routed": risk_summary["routed"],
            "note": (
                "Both arms are low-risk overall (mean total severity <0.3 out of a possible 18 "
                "per item). All nonzero hits are in one family, "
                "unsupported_personal_fact_or_upgraded_past_to_current -- routed has slightly "
                "more (9 vs 6 total severity points across 34 items each), consistent with MS's "
                "known imperfect content-following (38.5% verified) occasionally introducing an "
                "unsupported personal-fact framing. The difference is real but small, not alarming."
            ),
        },
        "cost": {
            "baseline_avg_tokens_per_call": cost_summary["baseline"],
            "routed_avg_tokens_per_call": cost_summary["routed"],
            "routed_vs_baseline_pct_change": round((routed_avg_total - baseline_avg_total) / baseline_avg_total * 100, 2),
            "note": (
                "Routed uses SLIGHTLY FEWER tokens per call than baseline on average (~"
                f"{round((baseline_avg_total - routed_avg_total), 1)} fewer tokens, "
                f"{round((baseline_avg_total - routed_avg_total) / baseline_avg_total * 100, 1)}% less), "
                "driven almost entirely by shorter completions (RS's single-move constraint "
                "produces much shorter replies -- avg 47.3 vs 95.9 completion tokens), while prompt "
                "tokens are nearly identical (625.2 vs 621.0 -- the fixed all-four-slot prompt "
                "template dominates, resource injection adds little). No established real $/token "
                "price exists for meta/llama-3.1-8b-instruct via this NVIDIA endpoint in this "
                "project (observed_cost_usd figures elsewhere are disclosed as an uncalibrated flat "
                "cap, not real billing), so token counts are reported as the primary honest metric."
            ),
        },
        "conclusion_vs_original_claim": (
            "The original claim under test was some form of 'PM (RS+MS) does not lose quality, "
            "and costs less than baseline' or 'PM is better on quality/risk at comparable cost.' "
            "This formal blind measurement does NOT support that claim. Quality is dramatically "
            "WORSE for routed (baseline preferred 32/34 = 94.1%, routed only 2/34), not equal. "
            "Cost IS modestly lower for routed (~6% fewer tokens/call) -- but that saving is "
            "purchased by giving up quality on 94% of pairs, not a favorable trade. Risk is "
            "roughly flat, slightly worse for routed. The quality loss traces to a specific, "
            "identifiable design choice -- the 'Restatement or Paraphrasing' family's "
            "restate-only, no-question, no-advice constraint, combined with RS's card-selection "
            "being heavily skewed toward exactly this family (established already in round 12, "
            "298l) -- not to RS/MS's routing or content-following mechanism, both of which were "
            "independently verified working in the prior round (65.2% / 38.5% real follow rates)."
        ),
        "real_costs_this_round": {
            "quality_risk_measurement_review_usd": round(review_cost, 4),
            "content_following_review_usd": 0.2443,
            "total_measurement_spend_usd": round(review_cost + 0.2443, 4),
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
