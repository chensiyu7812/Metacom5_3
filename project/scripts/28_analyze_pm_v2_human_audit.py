#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import cohen_kappa_score

from metacom_pm.io import write_json

ROOT = Path(__file__).resolve().parents[1]

RESPONSE_FIELDS = (
    "emotional_support",
    "personalization",
    "memory_appropriateness",
    "factual_grounding",
    "temporal_consistency",
    "non_intrusiveness",
)
RISK_FIELDS = (
    "selected_context_misuse",
    "unnecessary_exposure",
    "stale_or_conflicting_use",
    "unsupported_personal_claim",
    "memory_omission",
    "strategy_overuse",
    "strategy_omission",
)


def read_completed(paths):
    rows = []
    for path in paths:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if not row.get("item_id") or not row.get("annotator_id"):
                    continue
                for field in (*RESPONSE_FIELDS, *RISK_FIELDS):
                    if row.get(field, "").strip() == "":
                        raise ValueError(
                            f"missing {field} for item {row['item_id']} annotator {row['annotator_id']}"
                        )
                    row[field] = float(row[field])
                if any(not 1.0 <= row[field] <= 5.0 for field in RESPONSE_FIELDS):
                    raise ValueError("response score outside 1-5")
                if any(not 0.0 <= row[field] <= 3.0 for field in RISK_FIELDS):
                    raise ValueError("risk score outside 0-3")
                rows.append(row)
    return rows


def safe_spearman(left, right):
    if len(left) < 3 or np.std(left) == 0 or np.std(right) == 0:
        return None
    value = spearmanr(left, right).statistic
    return None if np.isnan(value) else float(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--completed", type=Path, nargs="+", required=True)
    parser.add_argument("--key", type=Path, default=ROOT / "outputs" / "pm_v2_human_audit" / "human_rating_key.json")
    parser.add_argument("--out", type=Path, default=ROOT / "outputs" / "pm_v2_human_audit" / "human_audit_report.json")
    parser.add_argument("--minimum-annotators", type=int, default=2)
    parser.add_argument("--maximum-response-mae", type=float, default=0.80)
    parser.add_argument("--minimum-response-spearman", type=float, default=0.20)
    parser.add_argument("--maximum-risk-mae", type=float, default=0.60)
    parser.add_argument("--minimum-within-one-rate", type=float, default=0.80)
    parser.add_argument("--minimum-interrater-kappa", type=float, default=0.10)
    args = parser.parse_args()

    key_data = json.loads(args.key.read_text(encoding="utf-8"))
    key_rows = {row["item_id"]: row for row in key_data["key_rows"]}
    human_rows = read_completed(args.completed)
    by_item = defaultdict(list)
    seen = set()
    for row in human_rows:
        key = (row["item_id"], row["annotator_id"])
        if key in seen:
            raise RuntimeError(f"duplicate human rating: {key}")
        seen.add(key)
        if row["item_id"] not in key_rows:
            raise RuntimeError(f"unknown human audit item: {row['item_id']}")
        by_item[row["item_id"]].append(row)
    missing = [
        item_id
        for item_id in key_rows
        if len(by_item[item_id]) < args.minimum_annotators
    ]
    if missing:
        raise RuntimeError(
            f"{len(missing)} audit items have fewer than {args.minimum_annotators} ratings"
        )

    human_median = {}
    for item_id, rows in by_item.items():
        human_median[item_id] = {
            field: float(np.median([row[field] for row in rows]))
            for field in (*RESPONSE_FIELDS, *RISK_FIELDS)
        }

    dimensions = {}
    for group, fields, llm_key in (
        ("response", RESPONSE_FIELDS, "llm_response"),
        ("risk", RISK_FIELDS, "llm_risk"),
    ):
        for field in fields:
            human = [human_median[item_id][field] for item_id in sorted(key_rows)]
            llm = [float(key_rows[item_id][llm_key][field]) for item_id in sorted(key_rows)]
            dimensions[f"{group}.{field}"] = {
                "n": len(human),
                "mae": float(np.mean(np.abs(np.asarray(human) - np.asarray(llm)))),
                "within_one_rate": float(
                    np.mean(np.abs(np.asarray(human) - np.asarray(llm)) <= 1.0)
                ),
                "exact_rate": float(np.mean(np.asarray(human) == np.asarray(llm))),
                "spearman": safe_spearman(human, llm),
                "human_mean": float(np.mean(human)),
                "llm_mean": float(np.mean(llm)),
            }

    annotators = sorted({str(row["annotator_id"]) for row in human_rows})
    pairwise_kappa = []
    for left_index in range(len(annotators)):
        for right_index in range(left_index + 1, len(annotators)):
            left_id, right_id = annotators[left_index], annotators[right_index]
            common = []
            for item_id in sorted(key_rows):
                left = next(
                    (row for row in by_item[item_id] if row["annotator_id"] == left_id),
                    None,
                )
                right = next(
                    (row for row in by_item[item_id] if row["annotator_id"] == right_id),
                    None,
                )
                if left is not None and right is not None:
                    common.append((left, right))
            for field in RESPONSE_FIELDS:
                if len(common) < 3:
                    continue
                left_values = [round(row[0][field]) for row in common]
                right_values = [round(row[1][field]) for row in common]
                value = cohen_kappa_score(
                    left_values, right_values, weights="quadratic"
                )
                if not np.isnan(value):
                    pairwise_kappa.append(float(value))
    mean_kappa = float(np.mean(pairwise_kappa)) if pairwise_kappa else None
    response_rows = [dimensions[f"response.{field}"] for field in RESPONSE_FIELDS]
    risk_rows = [dimensions[f"risk.{field}"] for field in RISK_FIELDS]
    response_spearman = [
        row["spearman"] for row in response_rows if row["spearman"] is not None
    ]
    checks = {
        "response_mae": float(np.mean([row["mae"] for row in response_rows]))
        <= args.maximum_response_mae,
        "response_spearman": bool(response_spearman)
        and float(np.mean(response_spearman)) >= args.minimum_response_spearman,
        "response_within_one": float(
            np.mean([row["within_one_rate"] for row in response_rows])
        )
        >= args.minimum_within_one_rate,
        "risk_mae": float(np.mean([row["mae"] for row in risk_rows]))
        <= args.maximum_risk_mae,
        "interrater_kappa": mean_kappa is not None
        and mean_kappa >= args.minimum_interrater_kappa,
    }
    report = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "n_items": len(key_rows),
        "n_human_rows": len(human_rows),
        "annotators": annotators,
        "dimensions": dimensions,
        "mean_response_mae": float(np.mean([row["mae"] for row in response_rows])),
        "mean_response_spearman": (
            float(np.mean(response_spearman)) if response_spearman else None
        ),
        "mean_response_within_one_rate": float(
            np.mean([row["within_one_rate"] for row in response_rows])
        ),
        "mean_risk_mae": float(np.mean([row["mae"] for row in risk_rows])),
        "mean_pairwise_quadratic_kappa": mean_kappa,
        "checks": checks,
        "thresholds": {
            "minimum_annotators": args.minimum_annotators,
            "maximum_response_mae": args.maximum_response_mae,
            "minimum_response_spearman": args.minimum_response_spearman,
            "maximum_risk_mae": args.maximum_risk_mae,
            "minimum_within_one_rate": args.minimum_within_one_rate,
            "minimum_interrater_kappa": args.minimum_interrater_kappa,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.out, report)
    print(report)
    if report["status"] != "PASS":
        raise RuntimeError("PM-v2 human judge calibration gate failed")


if __name__ == "__main__":
    main()
