#!/usr/bin/env python3
"""Execute the exact hash-bound 101-call RS/MS Panel V2 blind review (332l
manifest), per paper1_rs_ms_panel_v2_blind_review_v2_execution_phase_v1.json.

Provider-safety boundary: every call to the provider is constructed from
ONLY `call["public_call"]` (messages, temperature, max_output_tokens, seed,
schema_sha256) via `_send(...)`. Local bookkeeping (case_id, arm,
owner_cluster, kind, pair_id, ...) never crosses into that function --
`_send` takes no such argument and a pre-call assertion rejects any
public_call whose key set is not exactly PROVIDER_SAFE_KEYS. This is the
runner half of the boundary the manifest's own checks enforce on the
message text (332l's condition_and_arm_labels_absent_from_provider_text).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.paid_run_release import require_paid_run_release  # noqa: E402
from metacom_pm.v1_5_function_observability_v2_blind_review import FunctionObservabilityV2BlindReview  # noqa: E402
from metacom_pm.v1_5_ms_rs_interaction_blind_review import MSRSInteractionBlindReview  # noqa: E402
from metacom_pm.v1_5_rs_ms_quality_risk_blind_review import RSMSQualityBlindReview, RSMSRiskBlindReview  # noqa: E402

PROTOCOL = "pm-v1.5-paper1-rs-ms-panel-v2-blind-review-v2-live-v1"
STAGE = "paper1_rs_ms_panel_v2_blind_review_v2"
STAGE_ID = "RS_MS_PANEL_V2_BLIND_REVIEW_V2_EXECUTION"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
BUNDLE = ROOT / "data/pm_v1_5_contracts/paper1_active_execution_bundle_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_rs_ms_panel_v2_blind_review_v2_execution_phase_v1.json"
CONFIG = ROOT / "configs/paper1_rs_ms_panel_v2_blind_review_v2_execution_v1.json"
MANIFEST_DIR = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_blind_review_manifest_v2_20260813"
OUT = ROOT / "outputs/pm_v1_5_paper1_rs_ms_panel_v2_blind_review_v2_live_20260813"
USD_CAP = 1.35

PROVIDER_SAFE_KEYS = frozenset({"messages", "temperature", "max_output_tokens", "seed", "schema_sha256"})
SCHEMA_BY_KIND = {
    "rs_quality": RSMSQualityBlindReview,
    "ms_quality": RSMSQualityBlindReview,
    "risk": RSMSRiskBlindReview,
    "rs_strategy_realization": FunctionObservabilityV2BlindReview,
    "ms_function_independent": FunctionObservabilityV2BlindReview,
    "ms_rs_interaction_pairwise": MSRSInteractionBlindReview,
}
ID_FIELD_BY_KIND = {
    "rs_quality": "pair_id",
    "ms_quality": "pair_id",
    "risk": "item_id",
    "rs_strategy_realization": "blind_item_id",
    "ms_function_independent": "blind_item_id",
    "ms_rs_interaction_pairwise": "pair_id",
}
ID_KEY_BY_KIND = {
    "rs_quality": "pair_id",
    "ms_quality": "pair_id",
    "risk": "item_id",
    "rs_strategy_realization": "blind_item_id",
    "ms_function_independent": "blind_item_id",
    "ms_rs_interaction_pairwise": "pair_id",
}


def require_authority() -> dict[str, Any]:
    authority = read_json(AUTHORITY)
    bundle = read_json(BUNDLE)
    current = authority["current_execution_phase"]
    expected_bundle = {"path": str(BUNDLE.relative_to(ROOT)), "sha256": sha256_file(BUNDLE)}
    if current["id"] != STAGE_ID or current["active_phase_manifest"] != expected_bundle:
        raise RuntimeError("RS/MS Panel V2 blind review V2 execution is not current")
    if bundle["current_phase"]["id"] != STAGE_ID:
        raise RuntimeError("bundle does not point at this execution phase")
    phase = read_json(PHASE)
    for binding in phase["input_bindings"]:
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"bound input drifted: {binding['role']}")
    for binding in phase["implementation_bindings"]:
        if binding["role"] == "runner_source":
            continue  # cannot hash itself mid-execution; verified by a dedicated test instead
        if sha256_file(ROOT / binding["path"]) != binding["sha256"]:
            raise RuntimeError(f"implementation drifted: {binding['role']}")
    return phase


def _send(client: Any, public_call: dict[str, Any], schema_cls: type) -> tuple[Any, Any]:
    """The ONLY function in this script that talks to the provider. Takes
    nothing but the public_call projection -- no case_id/arm/owner_cluster
    can reach it because they are not parameters."""

    if set(public_call) != PROVIDER_SAFE_KEYS:
        raise RuntimeError(f"public_call has non-allowlisted keys: {set(public_call) - PROVIDER_SAFE_KEYS}")
    return client.chat(
        public_call["messages"],
        temperature=float(public_call["temperature"]),
        max_tokens=int(public_call["max_output_tokens"]),
        seed=int(public_call["seed"]),
        response_schema=schema_cls,
        retries=2,
    )


def _load_calls() -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for name in ("quality_calls_private.jsonl", "risk_calls_private.jsonl", "function_calls_private.jsonl"):
        calls.extend(read_jsonl(MANIFEST_DIR / name))
    return calls


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--run-identity")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    phase = require_authority()
    calls = _load_calls()
    if len(calls) != 101:
        raise RuntimeError(f"exact 101-call plan required, got {len(calls)}")
    for call in calls:
        if set(call["public_call"]) != PROVIDER_SAFE_KEYS:
            raise RuntimeError(f"call {call['logical_call_id']} public_call is not provider-safe")

    dry = {
        "protocol": PROTOCOL,
        "status": "LIVE_READY_EXACT_101_BLIND_REVIEW_CALLS",
        "logical_calls": len(calls),
        "absolute_usd_cap": USD_CAP,
        "run_identity": phase["execution"]["run_identity"],
        "api_calls": 0,
    }
    print(json.dumps(dry, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.run_identity != phase["execution"]["run_identity"]:
        raise RuntimeError("run identity does not match live phase")
    if args.accept_usd_cap != USD_CAP:
        raise RuntimeError(f"must accept exact frozen cap {USD_CAP:g}")
    require_paid_run_release(read_json(CONFIG), config_path=CONFIG, stage=STAGE, run=True, run_identity=args.run_identity)

    OUT.mkdir(parents=True, exist_ok=True)
    completed = (
        {row["logical_call_id"]: row for row in read_jsonl(OUT / "results_private.jsonl")}
        if (OUT / "results_private.jsonl").exists()
        else {}
    )
    raw_records = (
        {row["logical_call_id"]: row for row in read_jsonl(OUT / "raw_provider_outputs_before_validation.jsonl")}
        if (OUT / "raw_provider_outputs_before_validation.jsonl").exists()
        else {}
    )
    config = load_config(CONFIG)
    endpoint_config = load_config(ROOT / "configs/paper1_rs_ms_quality_risk_measurement_endpoints_v1.json")
    client = make_client(endpoint_from_config(endpoint_config, "openai_gpt_5_6_sol"))
    consecutive_failures = 0
    try:
        for call in sorted(calls, key=lambda row: row["logical_call_id"]):
            if call["logical_call_id"] in completed:
                continue
            schema_cls = SCHEMA_BY_KIND[call["kind"]]
            id_key = ID_KEY_BY_KIND[call["kind"]]
            id_field = ID_FIELD_BY_KIND[call["kind"]]
            expected_id = call.get(id_key) or call.get("item_id") or call.get("blind_item_id") or call.get("pair_id")
            error: str | None = None
            validated: dict[str, Any] | None = None
            try:
                result, parsed = _send(client, call["public_call"], schema_cls)
                raw_records[call["logical_call_id"]] = {
                    "protocol": PROTOCOL,
                    "logical_call_id": call["logical_call_id"],
                    "kind": call["kind"],
                    "request_hash": result.request_hash,
                    "raw_text_before_validation": result.text,
                    "raw_response_before_validation": result.raw_response,
                    "parsed_before_local_validation": parsed.model_dump(mode="json") if parsed is not None else None,
                    "usage": result.usage,
                    "latency_ms": result.latency_ms,
                    "finish_reason": result.normalized_finish_reason,
                }
                write_jsonl(OUT / "raw_provider_outputs_before_validation.jsonl", list(raw_records.values()))
                if parsed is None:
                    raise ValueError("provider returned no schema-valid output")
                if getattr(parsed, id_field) != expected_id:
                    raise ValueError("id_field_mismatch")
                validated = parsed.model_dump(mode="json")
                consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                error = f"{type(exc).__name__}: {exc}"
                consecutive_failures += 1
            completed[call["logical_call_id"]] = {
                "protocol": PROTOCOL,
                "logical_call_id": call["logical_call_id"],
                "kind": call["kind"],
                "case_id": call["case_id"],
                "owner_cluster": call["owner_cluster"],
                "messages_sha256": call["messages_sha256"],
                "schema_valid_and_locally_validated": validated is not None,
                "validated_review": validated,
                "error": error,
            }
            write_jsonl(OUT / "results_private.jsonl", list(completed.values()))
            print(f"blind review {len(completed)}/101 kind={call['kind']} valid={validated is not None}", flush=True)
            if consecutive_failures >= 5:
                raise RuntimeError("aborting: 5 consecutive non-retryable failures (stop_rules)")
    finally:
        client.close()

    summary = {
        "protocol": PROTOCOL,
        "status": f"LIVE_COMPLETE_{len(completed)}_OF_101",
        "run_identity": phase["execution"]["run_identity"],
        "completed": len(completed),
        "total": 101,
        "output_directory": str(OUT.relative_to(ROOT)),
    }
    write_json(OUT / "summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
