#!/usr/bin/env python3
"""Open frozen MP private mapping and form exact-consensus labels; zero API."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402

AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b3_mp_pre_adjudication_phase_v1.json"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811/private_case_key.jsonl"
PUBLIC = ROOT / "outputs/pm_v1_5_paper1_v3_g4b2_mp_public_reviews_20260811"
CONT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b2_mp_public_529_continuation_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b3_mp_pre_adjudication_20260811"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def ac1(pairs: list[tuple[str, str]], classes: tuple[str, ...]) -> float:
    po = sum(a == b for a, b in pairs) / len(pairs)
    marg = {c: sum(a == c or b == c for a, b in pairs) / (2 * len(pairs)) for c in classes}
    pe = sum(p * (1 - p) for p in marg.values()) / (len(classes) - 1)
    return (po - pe) / (1 - pe) if pe < 1 else 1.0


def main() -> None:
    authority = read(AUTHORITY)
    if authority["active_v3_phase"]["id"] != "G4B3_MP_PRE_ADJUDICATION":
        raise RuntimeError("G4B3 is not active")
    phase = read(PHASE)
    binding = authority["active_v3_phase"]["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("phase binding drifted")
    for item in phase["input_bindings"]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"input drifted: {item['path']}")
    a_rows = rows(PUBLIC / "reviewer_a_public_reviews.jsonl") + rows(CONT / "review.jsonl")
    b_rows = rows(PUBLIC / "reviewer_b_public_reviews.jsonl")
    a = {row["review_item_id"]: row for row in a_rows}
    b = {row["review_item_id"]: row for row in b_rows}
    keys = [row for row in rows(PRIVATE) if row["component"] == "MP"]
    if not (len(a) == len(b) == len(keys) == 204):
        raise RuntimeError("MP denominator incomplete")
    paired = []
    labels = []
    for key in keys:
        da = a[key["reviewer_a_item_id"]]["decision"]
        db = b[key["reviewer_b_item_id"]]["decision"]
        paired.append((da, db))
        resolved = da == db and da in {"SUITABLE", "NOT_SUITABLE"}
        label = 1 if resolved and da == "SUITABLE" else 0 if resolved else None
        labels.append({
            "protocol": "pm-v1.5-paper1-v3-g4b3-mp-consensus-label-v1",
            "case_key": key["case_key"], "state_id": key["state_id"],
            "actual_rank1_id": key["actual_rank1_id"], "split_group_key": key["split_group_key"],
            "outer_fold": key["outer_fold"], "component": "MP",
            "reviewer_a_decision": da, "reviewer_b_decision": db,
            "primary_binary_label": label,
            "resolution": "EXACT_RESOLVED_CONSENSUS" if resolved else "UNRESOLVED_RUNTIME_OFF",
        })
    exact = sum(a == b for a, b in paired) / 204
    resolved_pairs = [(a, b) for a, b in paired if "SEMANTIC_ABSTAIN" not in {a, b}]
    resolved_agreement = sum(a == b for a, b in resolved_pairs) / len(resolved_pairs)
    resolved = [row for row in labels if row["primary_binary_label"] is not None]
    class_counts = Counter(row["primary_binary_label"] for row in resolved)
    class_groups: dict[int, set[str]] = defaultdict(set)
    for row in resolved:
        class_groups[row["primary_binary_label"]].add(row["split_group_key"])
    metrics = {
        "exact_three_class_raw_agreement": exact,
        "resolved_binary_raw_agreement": resolved_agreement,
        "gwet_ac1_three_class": ac1(paired, ("SUITABLE", "NOT_SUITABLE", "SEMANTIC_ABSTAIN")),
        "exact_consensus_resolved_coverage": len(resolved) / 204,
        "resolved_labels": len(resolved),
        "unresolved_runtime_off": 204 - len(resolved),
        "class_counts": {"OFF": class_counts[0], "ON": class_counts[1]},
        "class_group_counts": {"OFF": len(class_groups[0]), "ON": len(class_groups[1])},
        "groups_overall": len({row["split_group_key"] for row in resolved}),
    }
    checks = {
        "exact_agreement_min_075": exact >= 0.75,
        "resolved_agreement_min_080": resolved_agreement >= 0.80,
        "gwet_ac1_min_060": metrics["gwet_ac1_three_class"] >= 0.60,
        "resolved_coverage_min_065": len(resolved) / 204 >= 0.65,
        "resolved_total_min_128": len(resolved) >= 128,
        "each_class_min_32": class_counts[0] >= 32 and class_counts[1] >= 32,
        "groups_overall_min_17": metrics["groups_overall"] >= 17,
        "groups_each_class_min_8": len(class_groups[0]) >= 8 and len(class_groups[1]) >= 8,
    }
    failed = [key for key, value in checks.items() if not value]
    OUT.mkdir(parents=True, exist_ok=False)
    label_path = OUT / "mp_consensus_labels.jsonl"
    write_jsonl(label_path, labels)
    report = {
        "protocol": "pm-v1.5-paper1-v3-g4b3-mp-pre-adjudication-report-v1",
        "status": "G4B3_MP_PRE_ADJUDICATION_PASS_GROUPED_OOF_MAY_BE_DESIGNED" if not failed else "G4B3_MP_PRE_ADJUDICATION_FAIL_MP_FIXED_OFF",
        "metrics": metrics, "checks": checks, "failed_checks": failed,
        "label_file": {"path": str(label_path.relative_to(ROOT)), "sha256": sha256_file(label_path), "rows": 204},
        "adjudication_performed": False, "api_calls": 0, "pm_fit": False,
        "all_16_actions_remain_downstream": True,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
