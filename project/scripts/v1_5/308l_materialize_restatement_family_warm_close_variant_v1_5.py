#!/usr/bin/env python3
"""Materialize (zero-API) an experimental variant of the 14 'Restatement or
Paraphrasing' cards, testing the specific fix hypothesis from the quality
measurement round: BOTH execution profiles (minimal and dialogic) forbid
appending advice AND a new question/probe -- verified by direct comparison,
not assumed (dialogic actually lost to baseline 21/21=100%, worse than
minimal's 11/13=84.6%, disconfirming the initial "minimal is the problem"
hypothesis). Judge rationales across all loss examples consistently credit
baseline for "inviting the next step" or offering continued presence.

This variant keeps each card's own support_move (the restatement content)
and family-specific do-not clause completely unchanged, and still forbids
advice/suggestions (preserving Restatement's identity, distinct from
Providing Suggestions), but explicitly permits closing with a brief warm
acknowledgment of continued presence OR one short open-ended question.

Labeled as an experimental variant, NOT written back into the LLM-audit-
qualified bank -- this has not been re-audited for safety/scope.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
QUALIFIED_CARDS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812/strategy_cards_v4_llm_audit_qualified_only.jsonl"
OUT = ROOT / "outputs/pm_v1_5_restatement_family_warm_close_variant_20260812"

MINIMAL_CLAUSE = "Execute only this support move in one concise sentence. Do not append a question, advice, a second move, or another task."
DIALOGIC_CLAUSE = "Integrate the paraphrase naturally and leave room for correction only when ambiguity matters. Do not append advice or a new probe."
WARM_CLOSE_CLAUSE = (
    "Integrate the paraphrase naturally, then close with either a brief warm "
    "acknowledgment of continued presence or one short open-ended question "
    "inviting the user to continue. Do not give advice or a suggestion, and "
    "do not add a second restatement or another task."
)


def main() -> None:
    if OUT.exists():
        raise RuntimeError("restatement warm-close variant exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    if current["id"] != "RS_MS_QUALITY_RISK_COST_MEASURED_CLAIM_NOT_SUPPORTED_RESTATEMENT_FAMILY_ROOT_CAUSE_MP_NEXT":
        raise RuntimeError("quality/risk/cost-measured phase is not current")

    cards = read_jsonl(QUALIFIED_CARDS)
    restatement = [c for c in cards if c["strategy_family"] == "Restatement or Paraphrasing"]
    if len(restatement) != 14:
        raise RuntimeError(f"expected 14 Restatement cards, found {len(restatement)}")

    variants: list[dict[str, Any]] = []
    for card in restatement:
        original_guidance = card["prompt_guidance"]
        for clause in (MINIMAL_CLAUSE, DIALOGIC_CLAUSE):
            if clause in original_guidance:
                break
        else:
            raise RuntimeError(f"card {card['card_id']} guidance does not match either known execution-profile clause")
        remainder = original_guidance.split(clause, 1)[1].strip()
        # remainder is: "{family-specific do-not clause}. Use only information visible in the current prompt."
        new_guidance = f"{card['support_move']} {WARM_CLOSE_CLAUSE} {remainder}"
        variants.append({
            "protocol": "pm-v1.5-restatement-family-warm-close-variant-v1",
            "card_id": card["card_id"],
            "original_execution_profile": card["execution_profile"],
            "support_move": card["support_move"],
            "original_prompt_guidance": original_guidance,
            "variant_prompt_guidance": new_guidance,
            "family_specific_donot_and_scope_remainder": remainder,
            "when_not_to_use": card["when_not_to_use"],
            "strategy_family": card["strategy_family"],
            "experimental_not_llm_audit_qualified_for_this_variant_text": True,
        })

    checks = {
        "exact_14_variants": len(variants) == 14,
        "support_move_unchanged": all(v["support_move"] in v["variant_prompt_guidance"] for v in variants),
        "still_forbids_advice_or_suggestion": all("do not give advice" in v["variant_prompt_guidance"].lower() for v in variants),
        "still_forbids_second_move": all("second restatement or another task" in v["variant_prompt_guidance"].lower() for v in variants),
        "now_permits_warm_close_or_question": all(
            "warm acknowledgment" in v["variant_prompt_guidance"] and "open-ended question" in v["variant_prompt_guidance"]
            for v in variants
        ),
        "family_specific_donot_clause_preserved_verbatim": all(
            v["variant_prompt_guidance"].endswith(v["family_specific_donot_and_scope_remainder"])
            for v in variants
        ),
        "ends_with_scope_sentence": all(
            v["variant_prompt_guidance"].strip().endswith("Use only information visible in the current prompt.")
            for v in variants
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"restatement warm-close variant checks failed: {checks}")

    OUT.mkdir(parents=True)
    variants_path = OUT / "restatement_warm_close_variants.jsonl"
    write_jsonl(variants_path, variants)
    report = {
        "protocol": "pm-v1.5-restatement-family-warm-close-variant-report-v1",
        "status": "PASS_VARIANT_READY_ZERO_API",
        "checks": checks,
        "hypothesis": (
            "Both minimal and dialogic execution profiles forbid advice AND a new "
            "question/probe -- the actual shared root cause of the quality loss "
            "(verified: dialogic lost 21/21=100%, worse than minimal's 11/13=84.6%, "
            "disconfirming the initial minimal-only hypothesis). This variant keeps "
            "support_move and safety/scope do-not clauses unchanged, forbids advice "
            "and a second move (preserving Restatement's identity and safety), but "
            "explicitly permits closing with a brief warm acknowledgment or one open "
            "question -- targeting exactly what judge rationales credited baseline for."
        ),
        "sample_before_after": {
            "card_id": variants[0]["card_id"],
            "before": variants[0]["original_prompt_guidance"],
            "after": variants[0]["variant_prompt_guidance"],
        },
        "artifacts": {"variants": {"path": str(variants_path.relative_to(ROOT)), "sha256": sha256_file(variants_path)}},
        "api_calls": 0,
        "next": "DESIGN_ZERO_API_REGENERATION_PREFLIGHT_FOR_THE_31_AFFECTED_STATES",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
