#!/usr/bin/env python3
"""Materialize (zero-API) the RS Strategy Bank V4 LLM content-quality audit.

Substitutes for the project's own previously-designed but never-executed
"5-card human review" content gate, at the user's explicit direction (real
human review isn't being done yet). Covers all 80 cards across all 5
strategy families -- not just the single family the older plan doc
prioritized -- since cost is trivial and full-family coverage gives RS's
Step2 genuine breadth instead of a narrow single-family fallback.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import openai_strict_json_schema  # noqa: E402
from metacom_pm.io import canonical_json, read_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_strategy_card_llm_audit import StrategyCardLLMAudit, prompt_messages  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
BANK = ROOT / "outputs/pm_v1_5_strategy_bank_v4_final_v1/strategy_cards_v4_final.jsonl"
RELEASE_MANIFEST = ROOT / "outputs/pm_v1_5_paid_run_release.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_strategy_card_llm_audit_preflight_20260812"
STAGE = "paper1_rs_strategy_card_llm_audit_v1"
USD_CAP = 1.20

REVIEWER_ID = "RS_STRATEGY_CARD_LLM_AUDITOR_GPT56"
ENDPOINT_KEY = "openai_gpt_5_6_sol"


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\x1f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def main() -> None:
    if OUT.exists():
        raise RuntimeError("RS strategy card LLM audit preflight exists; refusing overwrite")
    authority = read_json(AUTHORITY)
    current = authority["current_execution_phase"]
    alias = authority["active_v3_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != "RS_EVOEMO_CONSTRUCT_VALIDATED_MP_RULE_BASED_STEP1_NEXT" or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS-EvoEmo-construct-validated phase is not the current execution phase")
    if alias.get("compatibility_alias_of") != "current_execution_phase" or alias["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("authority compatibility alias drifted")

    cards = read_jsonl(BANK)
    if len(cards) != 80 or len({c["card_id"] for c in cards}) != 80:
        raise RuntimeError("frozen 80-card bank denominator drifted")

    # Exercise the real per-transport strict-schema conversion the live runner
    # will use, before any approval or spend -- a prior round of this exact
    # audit reached "live" with a schema that failed this conversion (list
    # fields with default_factory aren't valid under OpenAI strict mode),
    # burning zero dollars only because the failure happened pre-network, not
    # because it was caught early. Catch it here instead.
    openai_strict_json_schema(StrategyCardLLMAudit)

    plan: list[dict[str, Any]] = []
    for card in sorted(cards, key=lambda c: c["card_id"]):
        messages = prompt_messages(card, REVIEWER_ID)
        plan.append({
            "protocol": "pm-v1.5-paper1-rs-strategy-card-llm-audit-call-v1",
            "logical_call_id": "rscardauditcall_" + stable_hex(REVIEWER_ID, card["card_id"]),
            "reviewer_id": REVIEWER_ID,
            "endpoint_key": ENDPOINT_KEY,
            "card_id": card["card_id"],
            "strategy_family": card["strategy_family"],
            "messages": messages,
            "messages_sha256": sha256_text(canonical_json(messages)),
            "schema_sha256": sha256_text(canonical_json(StrategyCardLLMAudit.model_json_schema())),
            "seed": 20260812 + int(stable_hex(REVIEWER_ID, card["card_id"], length=8), 16) % 100000,
            "temperature": 0.0,
            "max_output_tokens": 700,
        })

    run_identity = sha256_text(
        canonical_json({
            "stage": STAGE,
            "bank_sha256": sha256_file(BANK),
            "call_plan": [row["logical_call_id"] for row in plan],
            "call_plan_messages_sha256": [row["messages_sha256"] for row in plan],
            "call_plan_schema_sha256": [row["schema_sha256"] for row in plan],
        })
    )
    release_manifest = read_json(RELEASE_MANIFEST)
    consumed_identities = {
        str(record.get("approval_identity") or record.get("run_identity") or "")
        for record in [
            *(release_manifest.get("stage_consumptions") or {}).values(),
            *(release_manifest.get("prior_stage_attempts_history") or []),
            *(release_manifest.get("stage_consumptions_history") or []),
        ]
        if isinstance(record, dict)
    }

    family_counts = {}
    for row in plan:
        family_counts[row["strategy_family"]] = family_counts.get(row["strategy_family"], 0) + 1

    checks = {
        "unique_current_execution_pointer": alias.get("compatibility_alias_of") == "current_execution_phase",
        "exact_80_calls_all_cards_covered": len(plan) == 80 and len({row["logical_call_id"] for row in plan}) == 80,
        "all_5_families_covered": family_counts == {"Question": 20, "Providing Suggestions": 18, "Affirmation and Reassurance": 16, "Restatement or Paraphrasing": 14, "Reflection of feelings": 12},
        "one_strict_schema": len({row["schema_sha256"] for row in plan}) == 1,
        "run_identity_not_previously_consumed_or_pending": (
            run_identity not in consumed_identities
            and run_identity not in (release_manifest.get("stage_approvals") or {}).values()
        ),
        "zero_api_zero_label_zero_fit": True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"RS strategy card LLM audit preflight failed: {checks}")

    OUT.mkdir(parents=True)
    plan_path = OUT / "call_plan_private.jsonl"
    write_jsonl(plan_path, plan)
    report = {
        "protocol": "pm-v1.5-paper1-rs-strategy-card-llm-audit-preflight-v1",
        "status": "PASS_EXACT_80_CALL_PROPOSAL_READY_HUMAN_APPROVAL_REQUIRED_BEFORE_ANY_API_CALL",
        "checks": checks,
        "reviewer_id": REVIEWER_ID,
        "not_equivalent_to_human_review": (
            "This LLM audit substitutes for the project's own previously-designed 5-card human "
            "review content gate, at the user's explicit direction, because real human review is "
            "not being done now. Cards that pass are labeled llm_audit_qualified=true, a weaker "
            "status than the project's own human-verified convention, not eligible_for_formal_rs "
            "in the project's original strict sense -- this distinction must be carried forward "
            "wherever the result is used, not silently upgraded to 'human qualified.'"
        ),
        "proposed_authorization": {
            "stage": STAGE,
            "run_identity": run_identity,
            "logical_calls": 80,
            "maximum_physical_attempts": 160,
            "proposed_absolute_usd_cap": USD_CAP,
            "scope": (
                "Exactly 80 independent GPT-5.6 content-safety/scope audit calls, one per "
                "Strategy Bank V4 card, covering all 5 strategy families. Zero labels created, "
                "zero fits, zero rubric changes to the bank content itself -- diagnostic/"
                "qualification only."
            ),
        },
        "artifacts": {
            "call_plan": {"path": str(plan_path.relative_to(ROOT)), "sha256": sha256_file(plan_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "bundle": sha256_file(BUNDLE),
            "bank": sha256_file(BANK),
            "instrument": sha256_file(ROOT / "src/metacom_pm/v1_5_strategy_card_llm_audit.py"),
        },
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "next": "HUMAN_MUST_EXPLICITLY_APPROVE_THIS_EXACT_STAGE_RUN_IDENTITY_AND_COST_CAP_IN_THE_CENTRAL_RELEASE_MANIFEST",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
