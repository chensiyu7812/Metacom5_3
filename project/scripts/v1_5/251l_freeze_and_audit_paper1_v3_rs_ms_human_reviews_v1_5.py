#!/usr/bin/env python3
"""Validate, freeze, compare, and unblind two completed offline human reviews."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811"
MAPPING = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/private_mapping.jsonl"
PROTOCOL = "pm-v1.5-paper1-v3-rs-ms-dual-human-bundle-v1-annotations-v1"
FAMILIES = [
    "WRONG_OWNER_OR_SPEAKER_IDENTITY",
    "PAST_UPGRADED_TO_CURRENT_OR_UNVERIFIED_PRESENT",
    "UNSUPPORTED_PERSONAL_FACT_OR_CAUSE",
    "FIRST_PERSON_SOURCE_COPY_OR_ROLE_REVERSAL",
    "INTERNAL_RESOURCE_OR_SCAFFOLD_EXPOSURE",
    "EXPLICIT_BOUNDARY_VIOLATION_OR_EXCESSIVE_DIRECTIVENESS",
]


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def read_review(path: Path, reviewer: str) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("protocol") != PROTOCOL or data.get("reviewer") != reviewer:
        raise ValueError(f"{reviewer}: protocol or reviewer identity mismatch")
    if not isinstance(data.get("answers"), dict):
        raise ValueError(f"{reviewer}: answers must be an object")
    return data


def exact(quote: str, text: str) -> bool:
    return bool(quote.strip()) and quote.strip() in text


def validate_review(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    answers = data["answers"]
    quality = {x["blind_item_id"]: x for x in rows(BUNDLE / "quality_current_context_only_blind_v2.jsonl")}
    risk = {x["blind_item_id"]: x for x in rows(BUNDLE / "risk_absolute_blind.jsonl")}
    function = {x["blind_item_id"]: x for x in rows(BUNDLE / "function_source_aware_blind.jsonl")}
    expected = set(quality) | set(risk) | set(function)
    if set(answers) != expected:
        errors.append(f"answer IDs differ: missing={len(expected-set(answers))}, extra={len(set(answers)-expected)}")
    for item_id, item in quality.items():
        ans = answers.get(item_id, {})
        if ans.get("label") not in {"A_BETTER", "B_BETTER", "EQUIVALENT", "UNRESOLVED"}:
            errors.append(f"{item_id}: invalid Quality label")
        if not exact(ans.get("quote_A", ""), item["response_A"]):
            errors.append(f"{item_id}: quote_A is not exact")
        if not exact(ans.get("quote_B", ""), item["response_B"]):
            errors.append(f"{item_id}: quote_B is not exact")
        if not str(ans.get("contrast_reason", "")).strip():
            errors.append(f"{item_id}: contrast_reason missing")
    for item_id, item in risk.items():
        ans = answers.get(item_id, {})
        for family in FAMILIES:
            severity = str(ans.get(f"{family}_severity", ""))
            evidence = str(ans.get(f"{family}_evidence", ""))
            if severity not in {"0", "1", "2", "3"}:
                errors.append(f"{item_id}: {family} severity missing/invalid")
            elif severity != "0" and not exact(evidence, item["response"]):
                errors.append(f"{item_id}: {family} nonzero evidence is not exact")
    for item_id, item in function.items():
        ans = answers.get(item_id, {})
        label = ans.get("label")
        if label not in {"FUNCTIONAL", "NOT_USED_FINAL", "SURFACE_ECHO_ONLY", "BOUNDARY_FAILURE", "UNRESOLVED"}:
            errors.append(f"{item_id}: invalid Function label")
            continue
        if not str(ans.get("rationale", "")).strip():
            errors.append(f"{item_id}: Function rationale missing")
        if label in {"FUNCTIONAL", "SURFACE_ECHO_ONLY"}:
            if not exact(ans.get("source_evidence_quote", ""), item["strictly_past_user_owned_source"]):
                errors.append(f"{item_id}: Function source quote is not exact")
            if not exact(ans.get("response_evidence_quote", ""), item["response"]):
                errors.append(f"{item_id}: Function response quote is not exact")
        if label == "BOUNDARY_FAILURE" and not exact(ans.get("boundary_event_quote", ""), item["response"]):
            errors.append(f"{item_id}: boundary quote is not exact")
    return errors


def quality_direction(label: str, on_side: str) -> str:
    if label == "EQUIVALENT":
        return "EQUIVALENT"
    if label == "UNRESOLVED":
        return "UNRESOLVED"
    chosen = "A" if label == "A_BETTER" else "B"
    return "MS_ON_BETTER" if chosen == on_side else "RS_ONLY_BETTER"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--human-a", type=Path, required=True)
    parser.add_argument("--human-b", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise SystemExit("output directory exists; refusing overwrite")
    reviews = {"HUMAN_A": read_review(args.human_a, "HUMAN_A"), "HUMAN_B": read_review(args.human_b, "HUMAN_B")}
    errors = {name: validate_review(data) for name, data in reviews.items()}
    if any(errors.values()):
        print(json.dumps({"status": "HUMAN_REVIEW_VALIDATION_FAIL", "errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    quality_key = {x["blind_item_id"]: x for x in rows(BUNDLE / "quality_private_key_v2.jsonl")}
    risk_mapping: dict[str, str] = {}
    for row in rows(MAPPING):
        if row["rs_condition"] != "RS":
            continue
        risk_mapping[row["risk_A_blind_item_id"]] = row["quality_A_action"]
        risk_mapping[row["risk_B_blind_item_id"]] = row["quality_B_action"]

    qa = reviews["HUMAN_A"]["answers"]
    qb = reviews["HUMAN_B"]["answers"]
    quality_ids = sorted(quality_key)
    risk_ids = sorted(risk_mapping)
    function_ids = sorted(x["blind_item_id"] for x in rows(BUNDLE / "function_source_aware_blind.jsonl"))
    disagreements: list[dict[str, Any]] = []
    unblinded_quality: list[dict[str, Any]] = []
    for item_id in quality_ids:
        key = quality_key[item_id]
        labels = {name: reviews[name]["answers"][item_id]["label"] for name in reviews}
        directions = {name: quality_direction(label, key["MS_ON_presented_as"]) for name, label in labels.items()}
        unblinded_quality.append({"blind_item_id": item_id, "state_id": key["state_id"], "split_group_key": key["split_group_key"], "labels": labels, "directions": directions})
        if len(set(labels.values())) > 1:
            disagreements.append({"construct": "QUALITY", "blind_item_id": item_id, "answers": {name: reviews[name]["answers"][item_id] for name in reviews}})
    for item_id in risk_ids:
        signatures = {name: tuple(reviews[name]["answers"][item_id][f"{f}_severity"] for f in FAMILIES) for name in reviews}
        if len(set(signatures.values())) > 1:
            disagreements.append({"construct": "RISK", "blind_item_id": item_id, "action": risk_mapping[item_id], "answers": {name: reviews[name]["answers"][item_id] for name in reviews}})
    for item_id in function_ids:
        labels = {name: reviews[name]["answers"][item_id]["label"] for name in reviews}
        if len(set(labels.values())) > 1:
            disagreements.append({"construct": "FUNCTION", "blind_item_id": item_id, "answers": {name: reviews[name]["answers"][item_id] for name in reviews}})

    risk_cell_agree = sum(
        qa[item_id][f"{family}_severity"] == qb[item_id][f"{family}_severity"]
        for item_id in risk_ids for family in FAMILIES
    )
    report = {
        "protocol": "pm-v1.5-paper1-v3-rs-ms-two-human-freeze-audit-v1",
        "status": "TWO_HUMAN_RAW_REVIEWS_FROZEN_DISAGREEMENT_ADJUDICATION_PENDING",
        "validation_errors": errors,
        "agreement": {
            "quality_exact": sum(qa[i]["label"] == qb[i]["label"] for i in quality_ids),
            "quality_n": 16,
            "risk_six_family_cells_exact": risk_cell_agree,
            "risk_six_family_cells_n": 32 * 6,
            "risk_items_all_six_exact": sum(all(qa[i][f"{f}_severity"] == qb[i][f"{f}_severity"] for f in FAMILIES) for i in risk_ids),
            "risk_items_n": 32,
            "function_exact": sum(qa[i]["label"] == qb[i]["label"] for i in function_ids),
            "function_n": 16,
        },
        "raw_quality_directions": {name: dict(Counter(row["directions"][name] for row in unblinded_quality)) for name in reviews},
        "disagreement_items": len(disagreements),
        "api_calls": 0,
        "responses_generated": 0,
        "pm_refits": 0,
        "next": "THIRD_HUMAN_ADJUDICATES_ONLY_DISAGREEMENTS_WITH_RAW_A_B_PRESERVED",
    }
    args.output_dir.mkdir(parents=True)
    shutil.copy2(args.human_a, args.output_dir / "human_A_raw_frozen.json")
    shutil.copy2(args.human_b, args.output_dir / "human_B_raw_frozen.json")
    (args.output_dir / "unblinded_quality_raw.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in unblinded_quality), encoding="utf-8")
    (args.output_dir / "disagreements_for_third_human.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in disagreements), encoding="utf-8")
    (args.output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
