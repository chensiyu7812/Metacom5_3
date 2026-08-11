#!/usr/bin/env python3
"""Materialize an outcome-hidden stratified semantic audit of the completed V5.3 panel.

The public reviewer packet contains current dialogue, typed candidate, and final
ON/OFF replies only.  Original Q/F judgments, target effects, and sampling strata
are written to a separate private key that must remain unopened until review is
complete.  No API calls are made.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import stable_hex, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-blind-semantic-audit-v1"
COMPONENTS = ("MP", "MS", "ME", "RS")
FORMAL_MANIFEST = (
    ROOT
    / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/"
    "effect_group_manifest_private.jsonl"
)
FORMAL_RESULT_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809/shards"
OUT = ROOT / "outputs/pm_v1_5_v5_3_blind_semantic_audit_20260809"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _target(row: Mapping[str, Any]) -> float:
    return float(row["quality_effect"]["aggregate"]["mean_positive_support_contribution"])


def _all_clean(row: Mapping[str, Any]) -> bool:
    return all(
        replicate[arm]["status"] == "clean"
        for replicate in row["generated"]
        for arm in ("ON", "OFF")
    )


def _any_on_fallback(row: Mapping[str, Any]) -> bool:
    return any(
        replicate["ON"]["status"] == "fell_back_to_m0"
        for replicate in row["generated"]
    )


def _take(
    rows: list[dict[str, Any]], *, count: int, used: set[str], reverse: bool = False,
    absolute: bool = False,
) -> list[dict[str, Any]]:
    def key(row: Mapping[str, Any]) -> tuple[float, str]:
        value = abs(_target(row)) if absolute else _target(row)
        return value, stable_hex(PROTOCOL, row["effect_group_id"], n=24)

    eligible = [row for row in rows if str(row["effect_group_id"]) not in used]
    selected = sorted(eligible, key=key, reverse=reverse)[:count]
    used.update(str(row["effect_group_id"]) for row in selected)
    return selected


def _sample_component(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    used: set[str] = set()
    selected: list[tuple[str, dict[str, Any]]] = []
    clean = [row for row in rows if _all_clean(row)]
    fallback = [row for row in rows if _any_on_fallback(row)]
    positive_clean = [row for row in clean if _target(row) > 0]
    negative_clean = [row for row in clean if _target(row) < 0]

    for row in _take(positive_clean, count=2, used=used, reverse=True):
        selected.append(("strong_positive_all_clean", row))
    for row in _take(negative_clean, count=2, used=used):
        selected.append(("strong_negative_all_clean", row))
    for row in _take(fallback, count=2, used=used):
        selected.append(("on_fallback", row))
    for row in _take(clean, count=2, used=used, absolute=True):
        selected.append(("near_zero_all_clean", row))
    if len(selected) != 8:
        raise RuntimeError(f"could only sample {len(selected)} rows")
    return selected


def main() -> None:
    manifests = _jsonl(FORMAL_MANIFEST)
    manifest_by_group = {str(row["effect_group_id"]): row for row in manifests}
    results: list[dict[str, Any]] = []
    for fold in range(1, 7):
        results.extend(_jsonl(FORMAL_RESULT_DIR / f"fold_{fold}_results.jsonl"))
    if len(results) != 576:
        raise RuntimeError("complete formal panel required")

    sampled: list[tuple[str, dict[str, Any]]] = []
    for component in COMPONENTS:
        sampled.extend(
            _sample_component([row for row in results if row["component"] == component])
        )

    private_rows = []
    public_rows = []
    for stratum, result in sampled:
        manifest = manifest_by_group[str(result["effect_group_id"])]
        audit_id = "audit_" + stable_hex(PROTOCOL, result["effect_group_id"], n=16)
        private_rows.append(
            {
                "audit_id": audit_id,
                "effect_group_id": result["effect_group_id"],
                "component": result["component"],
                "candidate_type": result["candidate_type"],
                "sampling_stratum": stratum,
                "original_q_effect": _target(result),
                "original_function_labels": result["functional"],
                "original_quality_forward": result["quality_forward"],
                "original_quality_reverse": result["quality_reverse"],
            }
        )
        public_rows.append(
            {
                "protocol": PROTOCOL,
                "audit_id": audit_id,
                "component": result["component"],
                "candidate_type": result["candidate_type"],
                "visible_dialogue": manifest["visible_dialogue"],
                "current_user_text": manifest["current_user_text"],
                "typed_candidate": manifest["candidate"],
                "candidate_text": manifest["candidate_text"],
                "replicates": [
                    {
                        "replicate_id": replicate["replicate_id"],
                        "on_status": replicate["ON"]["status"],
                        "on_reply": replicate["ON"]["reply"],
                        "off_status": replicate["OFF"]["status"],
                        "off_reply": replicate["OFF"]["reply"],
                    }
                    for replicate in result["generated"]
                ],
            }
        )

    public_rows.sort(key=lambda row: stable_hex(PROTOCOL, "blind_order", row["audit_id"], n=24))
    private_rows.sort(key=lambda row: row["audit_id"])
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "review_packet_blind.jsonl", public_rows)
    write_jsonl(OUT / "private_outcome_key_do_not_open_until_review.jsonl", private_rows)
    write_json(
        OUT / "manifest.json",
        {
            "protocol": PROTOCOL,
            "status": "BLIND_REVIEW_PACKET_READY",
            "sampled_groups": len(public_rows),
            "component_counts": dict(Counter(row["component"] for row in public_rows)),
            "candidate_type_counts": dict(Counter(
                f"{row['component']}:{row['candidate_type']}" for row in public_rows
            )),
            "review_dimensions": {
                "candidate_relevance": [
                    "CLEARLY_APPLICABLE", "RELATED_BUT_REDUNDANT",
                    "RELATED_BUT_NOT_USEFUL", "IRRELEVANT_OR_MISLEADING", "UNCERTAIN",
                ],
                "functional_use_each_replicate": [
                    "FUNCTIONAL_USE", "SURFACE_ECHO_ONLY", "NOT_USED",
                    "BOUNDARY_VIOLATION", "UNREVIEWABLE_RAW_REPLY_MISSING",
                ],
                "response_preference_each_replicate": [
                    "ON_BETTER", "OFF_BETTER", "TIE", "UNCERTAIN",
                ],
            },
            "reviewer_must_not_read_before_freeze": (
                "private_outcome_key_do_not_open_until_review.jsonl"
            ),
            "api_calls": 0,
        },
    )
    print(json.dumps({"groups": len(public_rows), "out": str(OUT)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
