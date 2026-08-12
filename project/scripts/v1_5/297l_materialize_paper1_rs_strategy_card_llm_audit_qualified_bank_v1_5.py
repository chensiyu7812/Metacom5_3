#!/usr/bin/env python3
"""Zero-API: fold the 80-card LLM audit results into a new, honestly-labeled
qualified card set.

Cards get a NEW field llm_audit_qualified (true/false) plus llm_audit_rationale
and llm_audit_confirmed_risk_flags. eligible_for_formal_rs is left unchanged
(still false for every card) -- llm_audit_qualified is explicitly a weaker,
distinct status, not a silent upgrade to the project's own human-verified
convention.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
BANK = ROOT / "outputs/pm_v1_5_strategy_bank_v4_final_v1/strategy_cards_v4_final.jsonl"
RESULTS = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_live_20260812/results_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_qualified_bank_20260812"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("LLM-audit-qualified bank output exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_STRATEGY_CARD_LLM_AUDIT_EXECUTION" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS strategy card LLM audit execution is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    cards = {c["card_id"]: dict(c) for c in read_jsonl(BANK)}
    results = read_jsonl(RESULTS)
    if len(results) != 80 or not all(r["schema_valid_and_locally_validated"] for r in results):
        raise RuntimeError("frozen 80-call audit is not fully valid")

    for row in results:
        review = row["validated_review"]
        card = cards[row["card_id"]]
        card["llm_audit_qualified"] = review["verdict"] == "LLM_AUDIT_QUALIFIED"
        card["llm_audit_rationale"] = review["rationale"]
        card["llm_audit_confirmed_risk_flags"] = review["confirmed_risk_flags"]
        card["llm_audit_additional_risk_flags_found"] = review["additional_risk_flags_missed_by_existing_tags"]
        card["llm_audit_protocol"] = "pm-v1.5-paper1-rs-strategy-card-llm-audit-v1"
        card["llm_audit_not_equivalent_to_human_review"] = True

    qualified = [c for c in cards.values() if c["llm_audit_qualified"]]
    not_qualified = [c for c in cards.values() if not c["llm_audit_qualified"]]

    OUT.mkdir(parents=True)
    all_path = OUT / "strategy_cards_v4_llm_audited.jsonl"
    qualified_path = OUT / "strategy_cards_v4_llm_audit_qualified_only.jsonl"
    write_jsonl(all_path, sorted(cards.values(), key=lambda c: c["card_id"]))
    write_jsonl(qualified_path, sorted(qualified, key=lambda c: c["card_id"]))

    report = {
        "protocol": "pm-v1.5-paper1-rs-strategy-card-llm-audit-qualified-bank-v1",
        "status": "LLM_AUDIT_QUALIFIED_BANK_MATERIALIZED",
        "totals": {
            "cards": len(cards),
            "llm_audit_qualified": len(qualified),
            "llm_audit_not_qualified": len(not_qualified),
        },
        "not_qualified_card_ids": [c["card_id"] for c in not_qualified],
        "by_family": {
            family: {
                "qualified": sum(1 for c in qualified if c["strategy_family"] == family),
                "total": sum(1 for c in cards.values() if c["strategy_family"] == family),
            }
            for family in sorted({c["strategy_family"] for c in cards.values()})
        },
        "not_equivalent_to_human_review": True,
        "eligible_for_formal_rs_unchanged": all(c["eligible_for_formal_rs"] is False for c in cards.values()),
        "artifacts": {
            "all_cards_annotated": {"path": str(all_path.relative_to(ROOT)), "sha256": sha256_file(all_path)},
            "qualified_only": {"path": str(qualified_path.relative_to(ROOT)), "sha256": sha256_file(qualified_path)},
        },
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
