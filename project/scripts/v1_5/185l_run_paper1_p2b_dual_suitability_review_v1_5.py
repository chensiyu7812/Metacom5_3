#!/usr/bin/env python3
"""Run frozen P2B controls, then qualified-component public blind reviews."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import Endpoint, make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_paper1_suitability import (  # noqa: E402
    SUITABILITY_AXES,
    validate_atomic_judgment,
)
from metacom_pm.v1_5_paper1_suitability_review import (  # noqa: E402
    SuitabilityReview,
    normalize_review,
    prompt_messages,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_p2b_dual_reviewer_suitability_phase_v1.json"
CONFIG = ROOT / "configs/paper1_p2b_review_execution_v1.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_strict_judge_bakeoff_v1.json"
FREEZE = ROOT / "outputs/pm_v1_5_paper1_p2b_dual_review_freeze_20260810"
PRIVATE_FREEZE = ROOT / "outputs/pm_v1_5_paper1_p2b_dual_review_freeze_private_20260810"
P2A = ROOT / "outputs/pm_v1_5_paper1_p2a_suitability_packet"
OUT = ROOT / "outputs/pm_v1_5_paper1_p2b_dual_reviews_20260810"
STAGE = "paper1_p2b_dual_suitability_review_v1"
REVIEWERS = {
    "REVIEWER_A": ("anthropic_claude_haiku_4_5", "reviewer_a"),
    "REVIEWER_B": ("openai_gpt_5_mini", "reviewer_b"),
}
MAX_ATTEMPTS = 2
MAX_OUTPUT_TOKENS = 900
USD_CAP = 6.0


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def endpoint(raw: Mapping[str, Any]) -> Endpoint:
    return Endpoint(
        base_url=str(raw["base_url"]),
        model=str(raw["model"]),
        api_key_env=str(raw["api_key_env"]),
        timeout_seconds=240.0,
        family=str(raw["family"]),
        transport=str(raw["transport"]),
        supports_strict_json_schema=bool(raw["supports_strict_json_schema"]),
        temperature_mode=str(raw.get("temperature_mode") or "explicit"),
        max_output_tokens_parameter=str(raw.get("max_output_tokens_parameter") or "max_tokens"),
        anthropic_strict_tool_use=bool(raw.get("anthropic_strict_tool_use", False)),
        openai_reasoning_effort=raw.get("openai_reasoning_effort"),
    )


def require_authority() -> dict[str, Any]:
    authority = read(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "P2B_DUAL_REVIEWER_SUITABILITY_QUALIFICATION":
        raise RuntimeError("P2B dual review is not the active phase")
    bound = current["active_phase_manifest"]
    if bound["path"] != str(PHASE.relative_to(ROOT)) or bound["sha256"] != sha256_file(PHASE):
        raise RuntimeError("active authority does not hash-bind the supplied P2B phase")
    phase = read(PHASE)
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        path = ROOT / binding["path"]
        if sha256_file(path) != binding["sha256"]:
            raise RuntimeError(f"P2B bound artifact drifted: {binding['path']}")
    return authority


def surface_maps() -> dict[tuple[str, str, str], dict[str, Any]]:
    result: dict[tuple[str, str, str], dict[str, Any]] = {}
    for reviewer, (_, stem) in REVIEWERS.items():
        control_path = FREEZE / f"{stem}_controls_unlabeled.jsonl"
        public_path = P2A / f"{stem}_packet_unlabeled.jsonl"
        for stage, path in (("CONTROL", control_path), ("PUBLIC", public_path)):
            for item in rows(path):
                result[(stage, reviewer, item["review_item_id"])] = item
    return result


def validate_review(parsed: SuitabilityReview, item: Mapping[str, Any]) -> dict[str, Any]:
    if parsed.review_item_id != item["review_item_id"]:
        raise ValueError("review item identity mismatch")
    result = normalize_review(parsed)
    errors = validate_atomic_judgment(
        result,
        allowed_visible_span_ids=[row["span_id"] for row in item["visible_spans"]],
        allowed_candidate_span_ids=[row["span_id"] for row in item["candidate_spans"]],
    )
    for axis in SUITABILITY_AXES:
        payload = result["axes"][axis]
        if payload["decision"] == "YES" and not (
            payload["visible_span_ids"] or payload["candidate_span_ids"]
        ):
            errors.append(f"{axis}:yes_without_selected_span")
    if errors:
        raise ValueError(";".join(errors))
    return result


def control_report() -> dict[str, Any] | None:
    path = OUT / "control_qualification_report.json"
    return read(path) if path.exists() else None


def analyze_controls() -> dict[str, Any]:
    gold = {row["review_item_id"]: row for row in rows(PRIVATE_FREEZE / "control_gold_key.jsonl")}
    details: dict[str, Any] = {}
    component_ok: dict[str, bool] = {}
    for reviewer, (_, stem) in REVIEWERS.items():
        completed = {
            row["review_item_id"]: row
            for row in rows(OUT / f"{stem}_controls_reviews.jsonl")
        }
        details[reviewer] = {}
        for component in ("MP", "MS", "ME", "RS"):
            ids = [item_id for item_id, truth in gold.items() if truth["component"] == component]
            available = [item_id for item_id in ids if item_id in completed]
            axis_correct = sum(
                completed[item_id]["axes"][axis]["decision"] == gold[item_id]["gold_axes"][axis]
                for item_id in available
                for axis in SUITABILITY_AXES
            )
            derived_correct = sum(
                completed[item_id]["derived_suitability"] == gold[item_id]["gold_derived"]
                for item_id in available
            )
            critical_ids = [item_id for item_id in ids if gold[item_id]["critical_boundary_control"]]
            critical_ok = all(
                item_id in completed
                and completed[item_id]["axes"]["current_boundary_permits"]["decision"] == "NO"
                for item_id in critical_ids
            )
            checks = {
                "complete_6": len(available) == 6,
                "axis_accuracy": len(available) == 6 and axis_correct / 24 >= 0.875,
                "derived_accuracy": len(available) == 6 and derived_correct >= 5,
                "critical_boundary": critical_ok,
            }
            details[reviewer][component] = {
                "status": "ELIGIBLE" if all(checks.values()) else "INELIGIBLE",
                "checks": checks,
                "axis_correct": axis_correct,
                "axis_total": 24,
                "derived_correct": derived_correct,
                "derived_total": 6,
            }
    for component in ("MP", "MS", "ME", "RS"):
        component_ok[component] = all(
            details[reviewer][component]["status"] == "ELIGIBLE" for reviewer in REVIEWERS
        )
    primary_feasible = component_ok["RS"] and any(component_ok[c] for c in ("MP", "MS", "ME"))
    report = {
        "protocol": "pm-v1.5-paper1-p2b-control-qualification-report-v1",
        "status": "CONTROL_PASS_PUBLIC_MAY_RUN" if primary_feasible else "CONTROL_FAIL_PRIMARY_CANNOT_PROCEED",
        "reviewers": details,
        "eligible_components": [component for component, ok in component_ok.items() if ok],
        "fixed_off_components": [component for component, ok in component_ok.items() if not ok],
        "paper1_primary_head_surface_feasible": primary_feasible,
        "no_gate_change_or_extra_control": True,
    }
    write_json(OUT / "control_qualification_report.json", report)
    return report


def actual_cost(ledger: PersistentAttemptLedger, endpoints: Mapping[str, Any]) -> float:
    total = 0.0
    endpoint_by_reviewer = {reviewer: key for reviewer, (key, _) in REVIEWERS.items()}
    for row in ledger.event_rows:
        if row.get("event") not in {"SUCCEEDED", "FAILED"}:
            continue
        usage = row.get("usage") or {}
        reviewer = str((row.get("record_ids") or {}).get("reviewer_id") or "")
        raw = endpoints["candidates"][endpoint_by_reviewer[reviewer]]
        total += (
            int(usage.get("prompt_tokens") or 0) * float(raw["input_usd_per_million_tokens"])
            + int(usage.get("completion_tokens") or 0) * float(raw["output_usd_per_million_tokens"])
        ) / 1_000_000
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-stage", choices=["controls", "public"], required=True)
    parser.add_argument("--run-identity", required=True)
    parser.add_argument("--accept-usd-cap", type=float, required=True)
    args = parser.parse_args()
    require_authority()
    if args.accept_usd_cap != USD_CAP:
        raise RuntimeError(f"must accept the exact frozen USD cap {USD_CAP:g}")
    config = read(CONFIG)
    release_stage = f"{STAGE}_{args.run_stage}"
    require_paid_run_release(
        config,
        config_path=CONFIG,
        stage=release_stage,
        run=True,
        run_identity=args.run_identity,
    )
    endpoints = read(ENDPOINTS)
    plan = rows(FREEZE / "call_plan.jsonl")
    surfaces = surface_maps()
    control = control_report()
    if args.run_stage == "public":
        if control is None or control["status"] != "CONTROL_PASS_PUBLIC_MAY_RUN":
            raise RuntimeError("public reviews require a frozen passing control report")
        eligible = set(control["eligible_components"])
    else:
        eligible = {"MP", "MS", "ME", "RS"}
    frozen_call_stage = "CONTROL" if args.run_stage == "controls" else "PUBLIC"
    selected = [row for row in plan if row["call_stage"] == frozen_call_stage]
    expected_selected = 48 if args.run_stage == "controls" else sum(
        surfaces[("PUBLIC", row["reviewer_id"], row["review_item_id"])]["component"]
        in eligible
        for row in plan
        if row["call_stage"] == "PUBLIC"
    )
    if args.run_stage == "public":
        selected = [
            row
            for row in selected
            if surfaces[("PUBLIC", row["reviewer_id"], row["review_item_id"])]["component"] in eligible
        ]
    if len(selected) != expected_selected or not selected:
        raise RuntimeError(
            f"frozen stage selection mismatch: selected={len(selected)} expected={expected_selected}"
        )
    expected = {row["call_key"]: MAX_ATTEMPTS for row in plan}
    OUT.mkdir(parents=True, exist_ok=True)
    ledger = PersistentAttemptLedger(
        OUT / "physical_attempt_ledger.jsonl",
        stage=STAGE,
        expected_calls=expected,
        maximum_total_attempts=len(plan) * MAX_ATTEMPTS,
    )
    clients: dict[str, Any] = {}
    try:
        for index, row in enumerate(selected, 1):
            reviewer = row["reviewer_id"]
            endpoint_key, stem = REVIEWERS[reviewer]
            item = surfaces[(row["call_stage"], reviewer, row["review_item_id"])]
            output_path = OUT / f"{stem}_{args.run_stage}_reviews.jsonl"
            completed = {record["review_item_id"]: record for record in rows(output_path)}
            if row["review_item_id"] in completed or ledger.succeeded(row["call_key"]):
                continue
            if ledger.exhausted(row["call_key"]):
                continue
            messages = prompt_messages(item, reviewer)
            if sha256_text(canonical_json(messages)) != row["prompt_sha256"]:
                raise RuntimeError("provider-visible prompt drift")
            if reviewer not in clients:
                clients[reviewer] = make_client(endpoint(endpoints["candidates"][endpoint_key]))
            while not ledger.succeeded(row["call_key"]) and not ledger.exhausted(row["call_key"]):
                reservation = ledger.reserve(
                    row["call_key"],
                    record_ids={"reviewer_id": reviewer, "review_item_id": row["review_item_id"], "call_stage": row["call_stage"]},
                    prompt_sha256=row["prompt_sha256"],
                )
                response = None
                try:
                    response, parsed = clients[reviewer].chat(
                        messages,
                        temperature=0.0,
                        max_tokens=MAX_OUTPUT_TOKENS,
                        seed=20260810 + int(row["ordinal"]),
                        response_schema=SuitabilityReview,
                        retries=1,
                    )
                    if parsed is None:
                        raise ValueError("structured review missing")
                    result = validate_review(parsed, item)
                    result.update(
                        {
                            "protocol": "pm-v1.5-paper1-p2b-atomic-review-result-v1",
                            "reviewer_id": reviewer,
                            "component": item["component"],
                            "call_stage": row["call_stage"],
                            "endpoint_key": endpoint_key,
                            "model": endpoints["candidates"][endpoint_key]["model"],
                            "request_hash": response.request_hash,
                            "raw_response_text_sha256": hashlib.sha256(response.text.encode()).hexdigest(),
                            "structured_output_audit": response.structured_output_audit,
                        }
                    )
                    ledger.finish(
                        reservation,
                        succeeded=True,
                        request_hash=response.request_hash,
                        usage=response.usage,
                        error=None,
                        result=result,
                        metadata={"endpoint": endpoint_key, "model": endpoints["candidates"][endpoint_key]["model"]},
                    )
                    completed[result["review_item_id"]] = result
                    write_jsonl(output_path, list(completed.values()))
                except Exception as exc:
                    ledger.finish(
                        reservation,
                        succeeded=False,
                        request_hash=response.request_hash if response else None,
                        usage=response.usage if response else None,
                        error=f"{type(exc).__name__}: {exc}",
                        metadata={"endpoint": endpoint_key, "model": endpoints["candidates"][endpoint_key]["model"]},
                    )
            if index % 12 == 0 or index == len(selected):
                print(f"{args.run_stage} progress {index}/{len(selected)} attempts={ledger.started_attempts}", flush=True)
    finally:
        for client in clients.values():
            client.close()
    if args.run_stage == "controls":
        scientific = analyze_controls()
    else:
        scientific = {"status": "PUBLIC_REVIEWS_COMPLETE_AWAITING_PRE_ADJUDICATION_ANALYSIS"}
    completed_selected = sum(ledger.succeeded(row["call_key"]) for row in selected)
    report = {
        "protocol": "pm-v1.5-paper1-p2b-live-stage-report-v1",
        "stage": args.run_stage,
        "status": scientific["status"] if completed_selected == len(selected) else "TRANSPORT_INCOMPLETE",
        "planned_logical_calls": len(selected),
        "completed_logical_calls": completed_selected,
        "attempts_started_total_ledger": ledger.started_attempts,
        "observed_cost_usd": actual_cost(ledger, endpoints),
        "absolute_usd_cap": USD_CAP,
        "scientific": scientific,
        "no_responses_safe_yield_pm_or_external_outcomes": True,
    }
    write_json(OUT / f"{args.run_stage}_live_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
