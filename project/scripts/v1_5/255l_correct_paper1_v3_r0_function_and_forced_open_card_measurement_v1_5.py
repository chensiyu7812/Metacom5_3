#!/usr/bin/env python3
"""Correct the R0/closure diagnostic without new generation, fitting, or labels."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / "outputs/pm_v1_5_paper1_v3_r0_function_closure_diagnostic_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_r0_function_forced_open_card_closure_diagnostic_v2_20260811"
RANK1 = ROOT / "outputs/pm_v1_5_paper1_p1b_actual_rank1/actual_rank1_unlabeled.jsonl"
CARDS = ROOT / "data/strategy/strategy_cards_v1_5_minimal.jsonl"
BASELINE = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_same_stack_baseline_plan_20260811/report.json"


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in records), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ("r0_function_blind.jsonl", "r0_function_private_key.jsonl"):
        shutil.copyfile(OLD / name, OUT / name)
        assert sha(OLD / name) == sha(OUT / name)

    old_blind = rows(OLD / "closure_quality_blind.jsonl")
    old_private = {x["blind_item_id"]: x for x in rows(OLD / "closure_quality_private_key.jsonl")}
    state_ids = {x["state_id"] for x in old_private.values()}
    rank1 = {
        x["state_id"]: x
        for x in rows(RANK1)
        if x.get("component") == "RS" and x.get("state_id") in state_ids
    }
    cards = {x["strategy_id"]: x for x in rows(CARDS)}
    assert set(rank1) == state_ids

    corrected_blind: list[dict] = []
    corrected_private: list[dict] = []
    audit: list[dict] = []
    for item in old_blind:
        key = old_private[item["blind_item_id"]]
        rr = rank1[key["state_id"]]
        card = cards[rr["actual_rank1_id"]]
        assert rr["retrieval_observations"]["move_id"] == "AM01_invite_open_expression"
        assert rr["retrieval_observations"]["selection_mode"] == "lexical_fallback"
        assert rr["retrieval_observations"]["transparent_rule_on"] is False

        fixed = dict(item)
        fixed["protocol"] = "pm-v1.5-paper1-v3-forced-open-card-vs-r0-closure-quality-blind-item-v2"
        fixed["decision"] = {
            "label": ["A_BETTER", "B_BETTER", "EQUIVALENT", "UNRESOLVED"],
            "material_rule": "Prefer one reply only when it better matches this visible current support phase. For explicit relief plus closure, reward acknowledging improvement, gentle closure, low response burden, and a future-open option; do not reward reopening the issue merely because the reply asks an open question.",
            "equivalent_rule": "Use EQUIVALENT when both replies are similarly phase-appropriate or differences are cosmetic or mixed without a material net direction.",
            "required_evidence": "Quote one exact span from each response and give one concise current-phase contrast reason.",
            "do_not_score": ["memory use", "resource Function", "Cost", "length alone", "style alone", "whether a learned RS head would select either arm"],
            "claim_boundary": "This compares a preexisting no-RS-card response with a preexisting response generated while an open-invitation card was forcibly present. It is not a learned-RS policy evaluation and cannot establish the learned RS ON/OFF decision.",
        }
        corrected_blind.append(fixed)

        private = dict(key)
        private["protocol"] = "pm-v1.5-paper1-v3-forced-open-card-vs-r0-closure-quality-private-key-v2"
        private["response_A_treatment"] = "FORCED_OPEN_INVITATION_CARD" if key["response_A_action"] == "M0+RS" else "NO_RS_CARD_R0"
        private["response_B_treatment"] = "FORCED_OPEN_INVITATION_CARD" if key["response_B_action"] == "M0+RS" else "NO_RS_CARD_R0"
        private["actual_RS_rank1"] = {
            "candidate_id": rr["actual_rank1_id"],
            "move_id": rr["retrieval_observations"]["move_id"],
            "selection_method": rr["selection_method"],
            "selection_mode": rr["retrieval_observations"]["selection_mode"],
            "selection_score": rr["selection_score"],
            "top1_top2_margin": rr["top1_top2_margin"],
            "observable_flags": rr["retrieval_observations"]["observable_flags"],
            "transparent_rule_on": rr["retrieval_observations"]["transparent_rule_on"],
            "guidance_text": card["guidance_text"],
        }
        private["learned_RS_checkpoint_available_for_this_surface"] = False
        private["formal_quality_label"] = None
        corrected_private.append(private)

        audit.append(
            {
                "protocol": "pm-v1.5-paper1-v3-closure-actual-rank1-audit-v1",
                "state_id": key["state_id"],
                "preidentified_closure_signal": key["preidentified_closure_signal"],
                "actual_rank1_id": rr["actual_rank1_id"],
                "move_id": rr["retrieval_observations"]["move_id"],
                "selection_mode": rr["retrieval_observations"]["selection_mode"],
                "transparent_rule_on": rr["retrieval_observations"]["transparent_rule_on"],
                "all_observable_opportunity_flags_false": not any(rr["retrieval_observations"]["observable_flags"].values()),
                "interpretation": "The card remained mechanically visible and won only the lexical fallback. The old experiment forced it ON; no compatible learned-RS checkpoint was applied.",
            }
        )

    write_jsonl(OUT / "forced_open_card_closure_quality_blind.jsonl", corrected_blind)
    write_jsonl(OUT / "forced_open_card_closure_quality_private_key.jsonl", corrected_private)
    write_jsonl(OUT / "closure_actual_rank1_audit.jsonl", audit)

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    report = {
        "protocol": "pm-v1.5-paper1-v3-r0-function-forced-open-card-closure-zero-api-diagnostic-v2",
        "date": "2026-08-11",
        "status": "ZERO_API_CORRECTED_PACKETS_READY_PI_REVIEW_NEXT",
        "correction": {
            "old_name": "M0+R0 versus M0+RS closure routing",
            "valid_name": "no-RS-card R0 versus forced open-invitation-card closure diagnostic",
            "reason": "Both closure cases have AM01 only through lexical fallback with all opportunity flags false and transparent-rule OFF; no compatible Paper-1 learned-RS full-fit checkpoint exists.",
            "learned_RS_evaluation": False,
            "response_act_fit_and_generator_consequence_diagnostic": True,
        },
        "r0_function": {
            "cases": len(rows(OUT / "r0_function_blind.jsonl")),
            "unchanged_from_v1": True,
            "blind_sha256": sha(OUT / "r0_function_blind.jsonl"),
            "private_sha256": sha(OUT / "r0_function_private_key.jsonl"),
            "formal_source_aware_Function": "PENDING_PI_REVIEW",
        },
        "forced_open_card_closure": {
            "cases": len(corrected_blind),
            "actual_rank1_move": "AM01_invite_open_expression",
            "all_lexical_fallback": all(x["selection_mode"] == "lexical_fallback" for x in audit),
            "all_transparent_rule_off": all(x["transparent_rule_on"] is False for x in audit),
            "all_observable_opportunity_flags_false": all(x["all_observable_opportunity_flags_false"] for x in audit),
            "formal_quality_direction": "PENDING_PI_REVIEW",
        },
        "cost_completeness": {
            "estimated_input_tokens_available": {
                row["policy"]: {
                    "total": row["total_estimated_input_tokens"],
                    "mean": row["mean_estimated_input_tokens"],
                }
                for row in baseline["policies"]
            },
            "provider_input_tokens_observed": False,
            "provider_output_tokens_observed": False,
            "latency_ms_observed": False,
            "usd_observed": False,
            "formal_status": "LEGACY_TRACE_COST_INCOMPLETE_ESTIMATES_ONLY",
        },
        "provenance": {
            "all_responses_preexisting": True,
            "new_API_calls": 0,
            "new_responses_generated": 0,
            "PM_refit": False,
            "threshold_change": False,
            "training_labels_created": 0,
        },
    }
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
