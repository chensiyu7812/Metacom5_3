#!/usr/bin/env python3
"""Materialize the zero-call G0 generator-screening identity.

The output intentionally contains hashes and public benchmark identifiers only;
the official role-card text remains in the pinned ESC-Eval checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
SALT = "metacom-v3-g0-esc-eval-screen-v1"
SOURCE_QUOTAS = {"ESconv": 8, "MHP": 5, "ExTES": 5, "Psych": 3, "EPITOME": 3}
DEFAULT_EXECUTOR_DIR = (
    PROJECT_ROOT.parent
    / "private_evidence"
    / "current_20260813"
    / "pm_v1_5_r0_delta_four_arm_development_panel_20260813"
)
OFFICIAL_DIMENSIONS = [
    {"paper_name": "Fluency", "public_adapter_key": "fluency"},
    {"paper_name": "Expression", "public_adapter_key": "diversity"},
    {"paper_name": "Empathy", "public_adapter_key": "empathic"},
    {"paper_name": "Information", "public_adapter_key": "suggestion"},
    {"paper_name": "Skill", "public_adapter_key": "tech"},
    {"paper_name": "Humanoid", "public_adapter_key": "human"},
    {"paper_name": "Overall", "public_adapter_key": "overall"},
]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _executor_sample(executor_dir: Path) -> list[dict[str, Any]]:
    cases_path = executor_dir / "development_cases_private.jsonl"
    calls_path = executor_dir / "physical_call_plan_private.jsonl"
    cases = _read_jsonl(cases_path)
    calls = _read_jsonl(calls_path)
    by_case: dict[str, dict[str, dict[str, Any]]] = {}
    for call in calls:
        by_case.setdefault(call["case_id"], {})[call["requested_action_id"]] = call
    if len(cases) != 16 or len({row["runtime_owner_key"] for row in cases}) != 16:
        raise ValueError("executor source must contain exactly 16 owner-unique packets")

    selected: list[dict[str, Any]] = []
    for case in sorted(cases, key=lambda row: _sha_text(f"executor|{row['case_id']}")):
        available = by_case.get(case["case_id"], {})
        treatment = "MS+RS" if "MS+RS" in available else "MS+R0"
        for screen_arm, source_arm in (("R0_ONLY", "M0+R0"), ("MAX_AUTHORIZED_DELTA", treatment)):
            call = available.get(source_arm)
            if call is None:
                raise ValueError(f"missing {source_arm} for executor packet")
            selected.append(
                {
                    "packet_id": "g0exec_" + _sha_text(case["case_id"])[:16],
                    "owner_cluster_id": "g0owner_" + _sha_text(case["runtime_owner_key"])[:16],
                    "screen_arm": screen_arm,
                    "source_action_id": source_arm,
                    "prompt_sha256": call["messages_sha256"],
                    "response_schema_sha256": call["response_schema_sha256"],
                    "frozen_temperature": 0.0,
                    "frozen_max_output_tokens": 256,
                }
            )
    if len(selected) != 32 or len({row["packet_id"] for row in selected}) != 16:
        raise ValueError("executor screen must contain 32 calls across 16 packets")
    return selected


def materialize(executor_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    dry_path = AUTHORITY_DIR / "benchmark_protocol_dry_run_manifest_v1.json"
    contract_path = AUTHORITY_DIR / "g0_generator_bakeoff_contract_v1.json"
    dry = json.loads(dry_path.read_text(encoding="utf-8"))
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    executor = _executor_sample(executor_dir)
    english = [row for row in dry["ESC-Eval"]["cards"] if row["language"] == "english"]

    selected: list[dict[str, Any]] = []
    for source, quota in SOURCE_QUOTAS.items():
        pool = [row for row in english if row["source"] == source]
        ranked = sorted(pool, key=lambda row: _sha_text(f"{SALT}|{row['card_key']}"))
        if len(ranked) < quota:
            raise ValueError(f"source {source} has only {len(ranked)} cards for quota {quota}")
        for rank, row in enumerate(ranked[:quota], start=1):
            selected.append(
                {
                    "screen_id": f"g0esc_{_sha_text(row['card_key'])[:16]}",
                    "card_key": row["card_key"],
                    "source": source,
                    "source_rank": rank,
                    "role_card_sha256": row["role_card_sha256"],
                    "annotation_sha256": row["annotation_sha256"],
                }
            )
    selected.sort(key=lambda row: row["screen_id"])
    counts = Counter(row["source"] for row in selected)
    if len(selected) != 24 or len({row["card_key"] for row in selected}) != 24:
        raise ValueError("G0 screening sample must contain exactly 24 unique cards")
    if dict(counts) != SOURCE_QUOTAS:
        raise ValueError("G0 source quotas drifted")

    candidate_count = len(contract["candidates"])
    turns = int(contract["esc_eval_screen"]["turns_per_dialogue"])
    report = {
        "protocol": "metacom-v3-g0-generator-bakeoff-preflight-v1",
        "date": "2026-08-13",
        "status": "ZERO_CALL_PREFLIGHT_PASS_EXECUTION_REQUIRES_EXPLICIT_BUDGET_APPROVAL",
        "api_calls": 0,
        "contains_role_card_or_dialogue_text": False,
        "official_dimensions": OFFICIAL_DIMENSIONS,
        "screening_sample": {
            "language": "english",
            "cards": len(selected),
            "source_counts": SOURCE_QUOTAS,
            "selection_rule": f"within-source lowest SHA256({SALT}|card_key)",
            "manifest_sha256": "PENDING_RENDER",
        },
        "executor_sample": {
            "packets": 16,
            "calls_per_candidate": len(executor),
            "owner_unique": True,
            "manifest_sha256": "PENDING_RENDER",
            "prior_use_disclosure": contract["executor_screen"]["prior_use_disclosure"],
        },
        "logical_calls": {
            "supporter_per_candidate": len(selected) * turns,
            "local_esc_role_per_candidate": len(selected) * turns,
            "supporter_all_candidates": len(selected) * turns * candidate_count,
            "local_esc_role_all_candidates": len(selected) * turns * candidate_count,
            "executor_per_candidate": contract["executor_screen"]["logical_calls_per_candidate"],
            "qwen_paid_logical_calls": (
                len(selected) * turns
                + contract["executor_screen"]["logical_calls_per_candidate"]
            ),
        },
        "cost_ceiling": contract["cost_ceiling"],
        "selection_boundary": contract["selection_rule"],
        "input_hashes": {
            "benchmark_protocol_dry_run_manifest_v1.json": _sha_file(dry_path),
            "g0_generator_bakeoff_contract_v1.json": _sha_file(contract_path),
            "executor_development_cases_private.jsonl": _sha_file(executor_dir / "development_cases_private.jsonl"),
            "executor_physical_call_plan_private.jsonl": _sha_file(executor_dir / "physical_call_plan_private.jsonl"),
        },
        "run_identity": "PENDING_RENDER",
    }
    manifest_bytes = "".join(_canonical(row) + "\n" for row in selected).encode("utf-8")
    report["screening_sample"]["manifest_sha256"] = hashlib.sha256(manifest_bytes).hexdigest()
    executor_bytes = "".join(_canonical(row) + "\n" for row in executor).encode("utf-8")
    report["executor_sample"]["manifest_sha256"] = hashlib.sha256(executor_bytes).hexdigest()
    identity_payload = {
        "protocol": report["protocol"],
        "official_dimensions": report["official_dimensions"],
        "screening_sample": report["screening_sample"],
        "executor_sample": report["executor_sample"],
        "logical_calls": report["logical_calls"],
        "cost_ceiling": report["cost_ceiling"],
        "selection_boundary": report["selection_boundary"],
        "input_hashes": report["input_hashes"],
    }
    report["run_identity"] = _sha_text(_canonical(identity_payload))
    return report, selected, executor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=AUTHORITY_DIR / "g0_generator_bakeoff_preflight_v1.json",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=AUTHORITY_DIR / "g0_esc_eval_screening_manifest_v1.jsonl",
    )
    parser.add_argument("--executor-dir", type=Path, default=DEFAULT_EXECUTOR_DIR)
    parser.add_argument(
        "--executor-manifest",
        type=Path,
        default=AUTHORITY_DIR / "g0_executor_screening_manifest_v1.jsonl",
    )
    args = parser.parse_args()
    report, rows, executor = materialize(args.executor_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.manifest.write_text("".join(_canonical(row) + "\n" for row in rows), encoding="utf-8")
    args.executor_manifest.write_text(
        "".join(_canonical(row) + "\n" for row in executor), encoding="utf-8"
    )
    print(json.dumps({"cards": len(rows), "executor_calls": len(executor), "api_calls": 0, "run_identity": report["run_identity"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
