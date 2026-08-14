#!/usr/bin/env python3
"""Zero-API analysis: compare the independent content-following review (303l)
against the brittle generator_claimed self-citation proxy from the external
test (300l), to produce a corrected RS/MS function rate.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
LIVE = ROOT / "outputs/pm_v1_5_paper1_rs_ms_content_following_review_live_20260812"
PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_content_following_review_preflight_20260812"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_content_following_review_analysis_20260812"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def main() -> None:
    results = read_jsonl(LIVE / "results_private.jsonl")
    anchors = {row["case_id"]: row for row in read_jsonl(PREFLIGHT / "anchors_private.jsonl")}

    ms_judgments: Counter = Counter()
    rs_judgments: Counter = Counter()
    ms_confusion: Counter = Counter()
    rs_confusion: Counter = Counter()

    for row in results:
        review = row["validated_review"]
        anchor = anchors[row["case_id"]]
        ms_j, rs_j = review["ms_judgment"], review["rs_judgment"]
        ms_judgments[ms_j] += 1
        rs_judgments[rs_j] += 1
        if anchor["ms_offered"]:
            ms_confusion[(anchor["generator_claimed"]["MS"], ms_j)] += 1
        if anchor["rs_offered"]:
            rs_confusion[(anchor["generator_claimed"]["RS"], rs_j)] += 1

    ms_offered_n = sum(v for k, v in ms_judgments.items() if k != "NOT_OFFERED")
    rs_offered_n = sum(v for k, v in rs_judgments.items() if k != "NOT_OFFERED")
    ms_followed = ms_judgments.get("FOLLOWED", 0)
    rs_followed = rs_judgments.get("FOLLOWED", 0)

    def confusion_stats(confusion: Counter) -> dict[str, Any]:
        tp = confusion.get((True, "FOLLOWED"), 0)
        fp = confusion.get((True, "NOT_FOLLOWED_OR_IGNORED"), 0)
        fn = confusion.get((False, "FOLLOWED"), 0)
        tn = confusion.get((False, "NOT_FOLLOWED_OR_IGNORED"), 0)
        precision = round(tp / (tp + fp), 4) if (tp + fp) else None
        recall = round(tp / (tp + fn), 4) if (tp + fn) else None
        return {
            "claimed_true_and_judge_followed_TP": tp,
            "claimed_true_but_judge_not_followed_FP_overclaim": fp,
            "claimed_false_but_judge_followed_FN_undercount": fn,
            "claimed_false_and_judge_not_followed_TN": tn,
            "self_citation_precision_when_claimed_true": precision,
            "self_citation_recall_of_truly_followed": recall,
        }

    report = {
        "protocol": "pm-v1.5-paper1-rs-ms-content-following-review-analysis-v1",
        "status": "GENERATOR_CLAIMED_SELF_CITATION_CORRECTED_BY_INDEPENDENT_JUDGE",
        "rs_corrected_follow_rate": {
            "candidate_present_and_valid_calls": rs_offered_n,
            "independent_judge_followed": rs_followed,
            "independent_judge_followed_rate": round(rs_followed / rs_offered_n, 4) if rs_offered_n else None,
            "self_citation_claimed_rate_same_denominator": round(sum(1 for r in results if anchors[r["case_id"]]["rs_offered"] and anchors[r["case_id"]]["generator_claimed"]["RS"]) / rs_offered_n, 4) if rs_offered_n else None,
            "confusion_vs_self_citation": confusion_stats(rs_confusion),
        },
        "ms_corrected_follow_rate": {
            "candidate_present_and_valid_calls": ms_offered_n,
            "independent_judge_followed": ms_followed,
            "independent_judge_followed_rate": round(ms_followed / ms_offered_n, 4) if ms_offered_n else None,
            "self_citation_claimed_rate_same_denominator": round(sum(1 for r in results if anchors[r["case_id"]]["ms_offered"] and anchors[r["case_id"]]["generator_claimed"]["MS"]) / ms_offered_n, 4) if ms_offered_n else None,
            "confusion_vs_self_citation": confusion_stats(ms_confusion),
        },
        "interpretation": (
            "RS: self-citation has near-perfect precision (never falsely claims RS was used) but very "
            "low recall (misses most real uses) -- the earlier 8.8% claimed-rate badly understated real "
            "content-following, corrected rate is 65.2%. MS: self-citation is unreliable in BOTH "
            "directions (5 overclaims, 3 undercounts out of 13) -- precision 28.6%, i.e. most MS=True "
            "self-citations do NOT correspond to the reply actually reflecting the specific MS past-fact "
            "cue. Spot-read rationales show the model often satisfies RS's 'restate a change' instruction "
            "using SOME change in the conversation, self-cites MS anyway, without grounding in the "
            "specific MS-authorized past source -- a plausible mechanism for MS's overclaim pattern given "
            "MS and RS's restatement-family instructions overlap thematically."
        ),
        "still_not_measured": (
            "This corrects the FUNCTION question (did the reply's content reflect the guidance), not the "
            "QUALITY question (was the reply better than baseline) or RISK (harm/appropriateness beyond "
            "unauthorized-evidence leaks) or a real per-token COST. A formal blind quality/risk pairwise "
            "measurement (234l pattern) is still required before any 'RS+MS helps' claim."
        ),
        "real_cost_usd": 0.2443,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "analysis.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
