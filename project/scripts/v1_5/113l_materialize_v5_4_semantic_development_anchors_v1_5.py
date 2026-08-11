#!/usr/bin/env python3
"""Materialize outcome-file-blind public anchors for the V5.4 semantic gate."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.4-semantic-development-anchors-v1"
SOURCE = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/effect_group_manifest_private.jsonl"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_4_semantic_contrast_learnability_recovery_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_semantic_development_anchors_20260809"
COMPONENTS = ("MP", "MS", "ME", "RS")
TARGET_FAMILIES = 12
SUBTYPE_QUOTAS = {
    "MP": {"relationship_update": 9, "onboarding_profile": 3},
    "MS": {"turn_observation": 8, "session_summary": 4},
    "ME": {"context_event": 8, "reusable_action_result": 4},
    "RS": {
        "AM01_invite_open_expression": 2,
        "AM02_ask_one_focused_clarification": 2,
        "AM04_tentative_paraphrase_check": 2,
        "AM05_grounded_validation": 2,
        "AM10_offer_one_optional_micro_step": 2,
        "AM14_supportive_transition": 2,
    },
}


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _cluster(row: dict) -> str:
    return str(row.get("user_id") or row.get("source_state_id") or row["state_id"])


def _ordered(rows: list[dict], component: str, subtype: str) -> list[dict]:
    return sorted(
        rows,
        key=lambda row: stable_hex(
            PROTOCOL,
            component,
            subtype,
            str(row["effect_group_id"]),
            n=32,
        ),
    )


def _select(component_rows: list[dict], component: str) -> list[dict]:
    by_subtype = defaultdict(list)
    for row in component_rows:
        by_subtype[str(row["model_features"]["candidate_subtype"])].append(row)
    selected = []
    used_clusters = set()
    for subtype, quota in SUBTYPE_QUOTAS[component].items():
        candidates = _ordered(by_subtype[subtype], component, subtype)
        distinct = [row for row in candidates if _cluster(row) not in used_clusters]
        repeated = [row for row in candidates if _cluster(row) in used_clusters]
        chosen = (distinct + repeated)[:quota]
        if len(chosen) != quota:
            raise RuntimeError(f"insufficient {component}/{subtype} anchors")
        selected.extend(chosen)
        used_clusters.update(_cluster(row) for row in chosen)
    if len(selected) != TARGET_FAMILIES:
        raise RuntimeError(f"{component} did not produce exactly {TARGET_FAMILIES} anchors")
    return sorted(
        selected,
        key=lambda row: stable_hex(PROTOCOL, component, str(row["effect_group_id"]), n=32),
    )


def main() -> None:
    contract = json.loads(CONTRACT.read_text())
    if not contract["status"].endswith("NO_NEW_EFFECT_CALLS_AUTHORIZED"):
        raise RuntimeError("semantic development anchors require the no-effect-call recovery state")
    rows = _jsonl(SOURCE)
    output_rows = []
    audit = {}
    for component in COMPONENTS:
        selected = _select([row for row in rows if row["component"] == component], component)
        for index, row in enumerate(selected, start=1):
            family_id = f"v54sem_{component.lower()}_{stable_hex(PROTOCOL, component, row['effect_group_id'], n=16)}"
            output_rows.append(
                {
                    "protocol": PROTOCOL,
                    "semantic_family_id": family_id,
                    "component": component,
                    "family_ordinal": index,
                    "source_dataset": row["source_dataset"],
                    "source_formal_effect_group_id": row["effect_group_id"],
                    "source_state_id": row["state_id"],
                    "cluster_id": _cluster(row),
                    "user_id": row.get("user_id"),
                    "session_id": row.get("session_id"),
                    "turn_id": row.get("turn_id"),
                    "candidate_subtype": row["model_features"]["candidate_subtype"],
                    "visible_dialogue": row["visible_dialogue"],
                    "anchor_current_user_text": row["current_user_text"],
                    "candidate": row["candidate"],
                    "candidate_text": row["candidate_text"],
                    "candidate_owner_time_version_valid_from_source_manifest": True,
                    "effect_or_quality_outcome_read_by_materializer": False,
                    "development_only_not_fresh_confirmation": True,
                }
            )
        audit[component] = {
            "families": len(selected),
            "clusters": len({_cluster(row) for row in selected}),
            "candidate_subtypes": dict(Counter(row["model_features"]["candidate_subtype"] for row in selected)),
        }
    ids = [row["semantic_family_id"] for row in output_rows]
    checks = {
        "48_total_families": len(output_rows) == 48,
        "48_unique_family_ids": len(set(ids)) == 48,
        "12_per_component": Counter(row["component"] for row in output_rows)
        == Counter({component: 12 for component in COMPONENTS}),
        "source_manifest_only_no_result_path_constant": "formal_qf" not in str(SOURCE),
        "all_development_only": all(row["development_only_not_fresh_confirmation"] for row in output_rows),
        "all_outcome_blind_attested": all(not row["effect_or_quality_outcome_read_by_materializer"] for row in output_rows),
    }
    if not all(checks.values()):
        raise RuntimeError(f"semantic anchor materialization failed: {checks}")
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "anchors_private.jsonl", output_rows)
    write_json(
        OUT / "report.json",
        {
            "protocol": PROTOCOL,
            "status": "COMPLETE_ZERO_API_DEVELOPMENT_ANCHORS",
            "checks": checks,
            "component_audit": audit,
            "source_manifest_sha256": sha256_file(SOURCE),
            "recovery_contract_sha256": sha256_file(CONTRACT),
            "quality_effect_or_response_outcome_read": False,
            "api_calls": 0,
        },
    )
    print({"status": "COMPLETE_ZERO_API_DEVELOPMENT_ANCHORS", "component_audit": audit})


if __name__ == "__main__":
    main()
