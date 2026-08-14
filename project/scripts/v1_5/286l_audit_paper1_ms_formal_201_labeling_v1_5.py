#!/usr/bin/env python3
"""Audit the formal 201-item dual-model labeling pass: compute binary-collapsed
exact-agreement-only consensus per item (per paper1_ms_qualification_final_decision_v1.json),
report coverage/label distribution, and real observed cost. Zero API calls.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import read_json, read_jsonl, sha256_file, write_json, write_jsonl  # noqa: E402


RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_formal_201_labeling_live_20260812/control_results_private.jsonl"
RAW = ROOT / "outputs/pm_v1_5_paper1_ms_formal_201_labeling_live_20260812/raw_provider_outputs_before_local_validation.jsonl"
PACKET = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812/ms_reannotation_packet_blind.jsonl"
PRIVATE_KEY = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_private_20260812/ms_reannotation_private_key.jsonl"
ENDPOINTS = ROOT / "configs/paper1_ms_formal_201_labeling_endpoints_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_formal_201_labeling_audit_20260812"

PRIMARY_REVIEWER = "MS_FORMAL_PRIMARY_GPT56"
CHALLENGER_REVIEWER = "MS_FORMAL_CHALLENGER_CLAUDE_HAIKU"


def _collapse(label: str | None) -> str | None:
    if label is None:
        return None
    return "USE" if label == "SUITABLE" else "DO_NOT_USE"


def main() -> None:
    if OUT.exists():
        raise RuntimeError("formal labeling audit output exists; refusing overwrite")
    results = read_jsonl(RESULTS)
    packet_ids = {row["repair_item_id"] for row in read_jsonl(PACKET)}
    endpoints = read_json(ENDPOINTS)["candidates"]

    by_item: dict[str, dict[str, dict]] = {}
    for row in results:
        by_item.setdefault(row["repair_item_id"], {})[row["reviewer_id"]] = row

    transport_failures = []
    consensus_rows = []
    disagreement_rows = []
    unlabeled_missing_reviewer = []
    label_counts_3way = Counter()
    label_counts_binary = Counter()
    agreement_confusion = Counter()

    for item_id in sorted(packet_ids):
        reviewers = by_item.get(item_id, {})
        primary = reviewers.get(PRIMARY_REVIEWER)
        challenger = reviewers.get(CHALLENGER_REVIEWER)
        if primary is None or challenger is None:
            unlabeled_missing_reviewer.append({"repair_item_id": item_id, "have": sorted(reviewers.keys())})
            continue
        if not primary["schema_valid_and_locally_validated"] or not challenger["schema_valid_and_locally_validated"]:
            transport_failures.append({
                "repair_item_id": item_id,
                "primary_valid": primary["schema_valid_and_locally_validated"],
                "primary_error": primary.get("error"),
                "challenger_valid": challenger["schema_valid_and_locally_validated"],
                "challenger_error": challenger.get("error"),
            })
            continue
        primary_label = primary["validated_review"]["final_suitability"]
        challenger_label = challenger["validated_review"]["final_suitability"]
        primary_b = _collapse(primary_label)
        challenger_b = _collapse(challenger_label)
        agreement_confusion[(primary_b, challenger_b)] += 1
        if primary_b == challenger_b:
            consensus_rows.append({
                "repair_item_id": item_id,
                "primary_final_suitability": primary_label,
                "challenger_final_suitability": challenger_label,
                "consensus_binary_label": primary_b,
                "primary_decision_reason_code": primary["validated_review"]["decision_reason_code"],
                "challenger_decision_reason_code": challenger["validated_review"]["decision_reason_code"],
            })
            label_counts_3way[(primary_label, challenger_label)] += 1
            label_counts_binary[primary_b] += 1
        else:
            disagreement_rows.append({
                "repair_item_id": item_id,
                "primary_final_suitability": primary_label,
                "challenger_final_suitability": challenger_label,
            })

    prompt_tokens = sum(int((row.get("usage") or {}).get("prompt_tokens", 0) or 0) for row in results)
    completion_tokens = sum(int((row.get("usage") or {}).get("completion_tokens", 0) or 0) for row in results)
    cost_by_reviewer: dict[str, float] = {}
    for reviewer, endpoint_key in ((PRIMARY_REVIEWER, "openai_gpt_5_6_sol"), (CHALLENGER_REVIEWER, "anthropic_claude_haiku_4_5_challenger")):
        rows = [r for r in results if r["reviewer_id"] == reviewer]
        pt = sum(int((r.get("usage") or {}).get("prompt_tokens", 0) or 0) for r in rows)
        ct = sum(int((r.get("usage") or {}).get("completion_tokens", 0) or 0) for r in rows)
        rate = endpoints[endpoint_key]
        cost_by_reviewer[reviewer] = round(pt / 1_000_000 * rate["input_usd_per_million_tokens"] + ct / 1_000_000 * rate["output_usd_per_million_tokens"], 4)
    total_cost = round(sum(cost_by_reviewer.values()), 4)

    report = {
        "protocol": "pm-v1.5-paper1-ms-formal-201-labeling-audit-v1",
        "status": "FORMAL_LABELING_COMPLETE_CONSENSUS_COMPUTED",
        "totals": {
            "packet_items": len(packet_ids),
            "consensus_labeled": len(consensus_rows),
            "disagreement_unlabeled": len(disagreement_rows),
            "transport_failure_unlabeled": len(transport_failures),
            "missing_reviewer_unlabeled": len(unlabeled_missing_reviewer),
            "coverage_fraction": round(len(consensus_rows) / len(packet_ids), 4),
        },
        "consensus_binary_label_distribution": dict(label_counts_binary),
        "consensus_3way_pair_distribution": {f"{a}|{b}": c for (a, b), c in label_counts_3way.items()},
        "agreement_confusion_binary": {f"{a}->{b}": c for (a, b), c in agreement_confusion.items()},
        "transport_failures": transport_failures,
        "missing_reviewer": unlabeled_missing_reviewer,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "observed_cost_usd": total_cost,
        "cost_by_reviewer": cost_by_reviewer,
        "absolute_cap_usd": 8.79,
        "api_calls": 402,
        "training_labels_created": len(consensus_rows),
        "fits": 0,
        "source_hashes": {
            "results": sha256_file(RESULTS),
            "raw": sha256_file(RAW),
            "packet": sha256_file(PACKET),
            "private_key": sha256_file(PRIVATE_KEY),
        },
    }
    OUT.mkdir(parents=True)
    write_json(OUT / "report.json", report)
    write_jsonl(OUT / "consensus_labels_private.jsonl", consensus_rows)
    write_jsonl(OUT / "disagreement_items_private.jsonl", disagreement_rows)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
