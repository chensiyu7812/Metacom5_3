#!/usr/bin/env python3
"""Independently re-audit and optionally authorize the frozen formal manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, stable_hex, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_public_formal_manifest import audit_formal_manifest  # noqa: E402


OUT = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809"
TRACKED = ROOT / "data/pm_v1_5_contracts/v5_3_public_formal_effect_manifest_v1.json"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    contract = json.loads((OUT / "contract.json").read_text())
    tracked = json.loads(TRACKED.read_text())
    rows = _jsonl(OUT / "effect_group_manifest_private.jsonl")
    development_path = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809/effect_group_manifest_private.jsonl"
    development = _jsonl(development_path)
    re_audit = audit_formal_manifest(rows, development_rows=development)
    identity_payload = dict(contract)
    recorded_identity = identity_payload.pop("manifest_identity")
    recomputed_identity = "v53formalmanifest_" + stable_hex(
        canonical_json(identity_payload), canonical_json(rows), n=24,
    )
    source_checks = {
        name: sha256_file(ROOT / {
            "evoemo": "data/external/evo_emo.json",
            "esconv": "data/external/ESConv.json",
            "esconv_manifest": "data/strategy/esconv_split_manifest_v1_5.jsonl",
            "strategy_cards": "data/strategy/strategy_cards_v1_5_minimal.jsonl",
            "development_manifest": "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809/effect_group_manifest_private.jsonl",
            "public_contract": "data/pm_v1_5_contracts/v5_3_public_backbone_effect_learning_v1.json",
            "formal_freeze": "data/pm_v1_5_contracts/v5_3_public_formal_effect_freeze_v1.json",
            "formal_manifest_source": "src/metacom_pm/v1_5_v5_3_public_formal_manifest.py",
            "pool_materializer_source": "src/metacom_pm/v1_5_v5_3_public_learnability_pilot.py",
            "typed_adapter_source": "src/metacom_pm/v1_5_typed_resource_adapter.py",
            "formal_manifest_materializer": "scripts/v1_5/106l_materialize_v5_3_public_formal_effect_manifest_v1_5.py",
        }[name]) == expected
        for name, expected in contract["source_hashes"].items()
    }
    forbidden_keys = {
        "quality_effect", "quality_forward", "quality_reverse", "functional",
        "risk", "generated", "response", "outcome_label", "worth_opening",
    }
    checks = {
        "tracked_contract_exact_match": contract == tracked,
        "independent_reaudit_pass": re_audit["status"] == "PASS" and all(re_audit["checks"].values()),
        "manifest_identity_recomputes": recorded_identity == recomputed_identity,
        "all_source_hashes_match": all(source_checks.values()),
        "no_outcome_or_judgment_fields": all(not (set(row) & forbidden_keys) for row in rows),
        "cost_never_in_head_target": "cost" not in contract["target"].lower(),
        "risk_judge_zero_calls": contract["call_budget"]["automatic_risk_judge_calls"] == 0,
        "hard_cap_is_0_84": contract["call_budget"]["hard_qf_judge_usd_cap_with_20_percent_headroom"] == 0.84,
    }
    passed = all(checks.values())
    if args.authorize_live and (args.accept_usd_cap is None or args.accept_usd_cap < 0.84):
        raise SystemExit("live authorization requires --accept-usd-cap 0.84")
    report = {
        "protocol": "pm-v1.5-v5.3-public-formal-manifest-independent-review-v1",
        "status": "PASS" if passed else "FAIL",
        "checks": checks,
        "source_hash_checks": source_checks,
        "manifest_identity": recorded_identity,
        "accepted_usd_cap": args.accept_usd_cap if args.authorize_live else None,
        "live_execution_authorized": bool(args.authorize_live and passed),
        "authorization_scope": "frozen 576 groups, Q/F only, no risk judge, no state replacement",
        "runner_hashes": {
            "formal_runner": sha256_file(ROOT / "scripts/v1_5/108l_run_v5_3_public_formal_qf_v1_5.py"),
            "base_qf_runner": sha256_file(ROOT / "scripts/v1_5/100l_run_v5_3_public_learnability_canary_v1_5.py"),
            "qrf_schema": sha256_file(ROOT / "src/metacom_pm/v1_5_v5_3_qrf_judge.py"),
            "typed_response_program": sha256_file(ROOT / "src/metacom_pm/v1_5_v5_3_typed_response_program.py"),
            "transport_repair": sha256_file(ROOT / "scripts/v1_5/109l_repair_v5_3_public_formal_transport_failures_v1_5.py"),
        },
        "api_calls": 0,
    }
    write_json(OUT / "independent_review.json", report)
    print({"status": report["status"], "live_execution_authorized": report["live_execution_authorized"], "checks": checks})


if __name__ == "__main__":
    main()
