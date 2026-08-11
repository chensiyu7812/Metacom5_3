#!/usr/bin/env python3
"""Independent zero-API validation of the complete Paper 1 P2B phase."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import anthropic_strict_tool_schema, openai_strict_json_schema  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json  # noqa: E402
from metacom_pm.v1_5_paper1_suitability_review import (  # noqa: E402
    SuitabilityReview,
    prompt_messages,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_p2b_dual_reviewer_suitability_phase_v1.json"
FREEZE = ROOT / "outputs/pm_v1_5_paper1_p2b_dual_review_freeze_20260810"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_p2b_dual_review_freeze_private_20260810"
P2A = ROOT / "outputs/pm_v1_5_paper1_p2a_suitability_packet"
OUT = ROOT / "outputs/pm_v1_5_paper1_p2b_phase_validation_20260810/report.json"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    authority = read(AUTHORITY)
    phase = read(PHASE)
    plan = rows(FREEZE / "call_plan.jsonl")
    control_a = rows(FREEZE / "reviewer_a_controls_unlabeled.jsonl")
    control_b = rows(FREEZE / "reviewer_b_controls_unlabeled.jsonl")
    gold = rows(PRIVATE / "control_gold_key.jsonl")
    public_a = rows(P2A / "reviewer_a_packet_unlabeled.jsonl")
    public_b = rows(P2A / "reviewer_b_packet_unlabeled.jsonl")
    surfaces = {
        **{("CONTROL", "REVIEWER_A", row["review_item_id"]): row for row in control_a},
        **{("CONTROL", "REVIEWER_B", row["review_item_id"]): row for row in control_b},
        **{("PUBLIC", "REVIEWER_A", row["review_item_id"]): row for row in public_a},
        **{("PUBLIC", "REVIEWER_B", row["review_item_id"]): row for row in public_b},
    }
    hashes_ok = all(sha256_file(ROOT / row["path"]) == row["sha256"] for row in [*phase["input_bindings"], *phase["implementation_bindings"]])
    prompt_hashes_ok = all(
        sha256_text(canonical_json(prompt_messages(surfaces[(row["call_stage"], row["reviewer_id"], row["review_item_id"])], row["reviewer_id"])))
        == row["prompt_sha256"]
        for row in plan
    )
    control_counts = Counter(row["component"] for row in control_a)
    checks = {
        "parent_or_promoted_authority_exact": (
            phase["parent_authority_sha256"] == sha256_file(AUTHORITY)
            and authority["current_phase"]["id"] == "P2A_PACKET_COMPLETE_P2B_REVIEW_PENDING"
        )
        or (
            authority["current_phase"]["id"] == "P2B_DUAL_REVIEWER_SUITABILITY_QUALIFICATION"
            and authority["current_phase"]["promoted_from_authority_sha256"] == phase["parent_authority_sha256"]
            and authority["current_phase"]["active_phase_manifest"]["sha256"] == sha256_file(PHASE)
        ),
        "all_phase_bindings_exact": hashes_ok,
        "strict_schema_openai_valid": bool(openai_strict_json_schema(SuitabilityReview)),
        "strict_schema_anthropic_valid": bool(anthropic_strict_tool_schema(SuitabilityReview)),
        "controls_exact_and_balanced": len(control_a) == len(control_b) == len(gold) == 24
        and control_counts == Counter({"MP": 6, "MS": 6, "ME": 6, "RS": 6}),
        "control_gold_not_public": not any(any("gold" in key for key in row) for row in [*control_a, *control_b]),
        "control_order_differs": [row["review_item_id"] for row in control_a] != [row["review_item_id"] for row in control_b],
        "plan_exact_312": len(plan) == 312
        and Counter(row["call_stage"] for row in plan) == Counter({"PUBLIC": 264, "CONTROL": 48}),
        "call_keys_and_prompt_hashes_unique": len({row["call_key"] for row in plan}) == 312
        and len({(row["reviewer_id"], row["prompt_sha256"]) for row in plan}) == 312,
        "provider_visible_prompts_recomputed": prompt_hashes_ok,
        "controls_first_and_no_semantic_retry": phase["execution"]["controls_first"] is True
        and "same byte-identical" in phase["execution"]["retry"],
        "cost_cap_exact": phase["execution"]["absolute_usd_cap"] == 6.0
        and read(FREEZE / "cost_ceiling.json")["total_two_attempt_usd_upper_proxy"] < 6.0,
        "no_downstream_authority": all(
            any(fragment in value for value in phase["forbidden"])
            for fragment in ("response", "safe-yield", "PM fitting", "baseline")
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    report = {
        "protocol": "pm-v1.5-paper1-p2b-phase-validation-v1",
        "status": "P2B_PHASE_VALIDATION_PASS_AUTHORITY_MAY_PROMOTE" if not failed else "P2B_PHASE_VALIDATION_FAIL",
        "phase_sha256": sha256_file(PHASE),
        "parent_authority_sha256": sha256_file(AUTHORITY),
        "checks": checks,
        "failed_checks": failed,
        "api_calls": 0,
        "labels_created": 0,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    write_json(OUT, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
