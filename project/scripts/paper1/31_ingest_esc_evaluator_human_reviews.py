#!/usr/bin/env python3
"""Ingest two completed v1 ESC human submissions without altering raw judgments.

The v1 browser instrument displayed the official Humanoid rubric under the
``Skillful`` label and the official Skillful rubric under ``Humanoid``.  This
script preserves each submission byte-for-byte, records its SHA-256, and
creates normalized blind-rating rows by applying only that mechanical swap.
No adjudicated score, evaluator winner, PM outcome, or training label is made.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.evaluator_qualification import (  # noqa: E402
    DIMENSIONS,
    assert_blind_payload,
    canonical_sha256,
    human_reliability,
    validate_scores,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)

RAW_TO_OFFICIAL = {
    "Fluency": "Fluency",
    "Expression": "Expression",
    "Empathy": "Empathy",
    "Information": "Information",
    "Skillful": "Humanoid",
    "Humanoid": "Skillful",
    "Overall": "Overall",
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _submission_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("submission")
    if not isinstance(rows, list) or not rows:
        raise ValueError("submission must contain a non-empty list")
    return rows


def normalize_submission(
    payload: dict[str, Any],
    *,
    rater_id: str,
    frozen_items: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    meta = payload.get("meta")
    if not isinstance(meta, dict) or meta.get("item_count") != len(frozen_items):
        raise ValueError("submission item count does not match the frozen qualification set")
    if set(meta.get("dimensions", [])) != set(DIMENSIONS):
        raise ValueError("submission dimensions do not match the frozen seven dimensions")
    normalized = []
    seen: set[str] = set()
    for raw in _submission_rows(payload):
        item_id = raw.get("blind_item_id")
        if item_id not in frozen_items or item_id in seen:
            raise ValueError(f"unknown or duplicate blind item: {item_id}")
        seen.add(item_id)
        if raw.get("human_completed") is not True:
            raise ValueError(f"human rating is incomplete: {item_id}")
        raw_scores = {dimension: raw.get(dimension) for dimension in DIMENSIONS}
        validate_scores(raw_scores)
        official_scores = {
            official: raw_scores[raw_dimension]
            for raw_dimension, official in RAW_TO_OFFICIAL.items()
        }
        official_scores = validate_scores(official_scores)
        row = {
            "protocol": "pm-paper1-esc-evaluator-human-blind-rating-v2-normalized",
            "blind_item_id": item_id,
            "rater_id": rater_id,
            "dialogue": frozen_items[item_id]["dialogue"],
            "scores": official_scores,
            "notes": raw.get("notes"),
            "human_completed": True,
            "normalization": {
                "source_instrument": "pm-paper1-esc-evaluator-human-instrument-v1",
                "rule": "raw Skillful -> official Humanoid; raw Humanoid -> official Skillful",
                "judgment_values_changed": False,
            },
        }
        assert_blind_payload(row)
        normalized.append(row)
    if seen != set(frozen_items):
        raise ValueError("submission does not cover every frozen blind item exactly once")
    return normalized


def _category_mapping(audit: dict[str, Any]) -> dict[str, str]:
    result = {row["blind_item_id"]: "natural_public_baseline" for row in audit["natural"]}
    result.update(
        {row["blind_item_id"]: str(row["probe_factor"]) for row in audit["controlled"]}
    )
    return result


def _category_means(
    rows: list[dict[str, Any]], category_by_item: dict[str, str]
) -> dict[str, dict[str, float]]:
    result: dict[str, dict[str, float]] = {}
    categories = sorted(set(category_by_item.values()))
    by_id = {row["blind_item_id"]: row for row in rows}
    for category in categories:
        item_ids = [item for item, value in category_by_item.items() if value == category]
        result[category] = {
            dimension: statistics.fmean(by_id[item]["scores"][dimension] for item in item_ids)
            for dimension in DIMENSIONS
        }
    return result


def corrected_instrument(historical: dict[str, Any]) -> dict[str, Any]:
    rows = historical.get("dimensions")
    if not isinstance(rows, list) or len(rows) != 7:
        raise ValueError("historical instrument must contain seven rubric rows")
    old_by_label = {row["paper_dimension"]: row for row in rows}
    if set(old_by_label) != set(DIMENSIONS):
        raise ValueError("historical instrument dimensions drifted")
    corrected_by_official = {
        official: old_by_label[raw_dimension]["official_rubric_text"]
        for raw_dimension, official in RAW_TO_OFFICIAL.items()
    }
    return {
        "protocol": "pm-paper1-esc-evaluator-human-instrument-v2",
        "status": "CORRECTED_AFTER_RAW_HUMAN_CAPTURE_BEFORE_CANDIDATE_SCORING",
        "source": historical.get("source"),
        "correction": {
            "supersedes_for_future_use": "paper1_esc_evaluator_human_instrument_20260820_v1.json",
            "v1_defect": "official Humanoid and Skillful rubric texts were positionally swapped",
            "raw_submissions_are_immutable": True,
            "normalization_rule": "v1 Skillful scores become official Humanoid; v1 Humanoid scores become official Skillful",
        },
        "dimensions": [
            {
                "paper_dimension": dimension,
                "official_rubric_text": corrected_by_official[dimension],
                "scale": [0, 1, 2, 3, 4],
            }
            for dimension in DIMENSIONS
        ],
        "blind_to": historical.get("blind_to"),
        "two_independent_raters_required": True,
        "adjudication_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rater-a-submission", type=Path, required=True)
    parser.add_argument("--rater-b-submission", type=Path, required=True)
    parser.add_argument(
        "--authority-dir", type=Path, default=PROJECT / "data" / "paper1_authority"
    )
    parser.add_argument(
        "--human-review-dir", type=Path, default=PROJECT / "data" / "paper1_human_review"
    )
    args = parser.parse_args()

    config = load_public_only_config(PROJECT / "configs" / "paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    item_path = args.authority_dir / "paper1_esc_evaluator_qualification_set_20260820_v1.jsonl"
    audit_path = args.authority_dir / "paper1_esc_evaluator_qualification_audit_mapping_20260820_v1.json"
    historical_instrument_path = (
        args.authority_dir / "paper1_esc_evaluator_human_instrument_20260820_v1.json"
    )
    items = _read_jsonl(item_path)
    frozen_items = {row["blind_item_id"]: row for row in items}
    if len(frozen_items) != 24:
        raise RuntimeError("frozen ESC qualification set must contain 24 unique items")

    source_paths = {
        "RATER_A": args.rater_a_submission,
        "RATER_B": args.rater_b_submission,
    }
    payloads = {rater: _read_json(path) for rater, path in source_paths.items()}
    normalized = {
        rater: normalize_submission(payload, rater_id=rater, frozen_items=frozen_items)
        for rater, payload in payloads.items()
    }

    raw_dir = args.human_review_dir / "raw"
    raw_outputs = {
        "RATER_A": raw_dir / "paper1_esc_evaluator_human_submission_rater_a_20260823_v1.json",
        "RATER_B": raw_dir / "paper1_esc_evaluator_human_submission_rater_b_20260823_v1.json",
    }
    for rater, path in raw_outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source_paths[rater].read_bytes())

    normalized_outputs = {
        "RATER_A": args.authority_dir / "paper1_esc_evaluator_human_rater_a_normalized_20260823_v1.jsonl",
        "RATER_B": args.authority_dir / "paper1_esc_evaluator_human_rater_b_normalized_20260823_v1.jsonl",
    }
    for rater, path in normalized_outputs.items():
        _write_jsonl(path, normalized[rater])

    item_ids = [row["blind_item_id"] for row in items]
    reliability = human_reliability(
        normalized["RATER_A"] + normalized["RATER_B"], item_ids
    )
    audit = _read_json(audit_path)
    corrected_instrument_path = (
        args.authority_dir / "paper1_esc_evaluator_human_instrument_20260823_v2.json"
    )
    _write_json(
        corrected_instrument_path,
        corrected_instrument(_read_json(historical_instrument_path)),
    )
    category_by_item = _category_mapping(audit)
    report = {
        "protocol": "pm-paper1-esc-evaluator-dual-human-reference-20260823-v1",
        "status": "TWO_INDEPENDENT_HUMAN_RATINGS_COMPLETE_ADJUDICATION_PENDING",
        "grain": "one blind qualification item x one official ESC-Eval dimension x two raters",
        "frozen_qualification_items": 24,
        "source_submissions": {
            rater: {
                "path": str(raw_outputs[rater].relative_to(PROJECT)),
                "source_sha256": _sha256_bytes(source_paths[rater].read_bytes()),
                "stored_sha256": _sha256_bytes(raw_outputs[rater].read_bytes()),
                "generated_at": payloads[rater]["meta"].get("generated_at"),
                "complete_items": len(normalized[rater]),
            }
            for rater in ("RATER_A", "RATER_B")
        },
        "instrument_correction": {
            "severity": "HIGH_FOR_PER_DIMENSION_LABELING_NO_LOSS_OF_RAW_JUDGMENTS",
            "historical_instrument": "project/data/paper1_authority/paper1_esc_evaluator_human_instrument_20260820_v1.json",
            "corrected_instrument": "project/data/paper1_authority/paper1_esc_evaluator_human_instrument_20260823_v2.json",
            "historical_instrument_sha256": _sha256_bytes(historical_instrument_path.read_bytes()),
            "corrected_instrument_sha256": _sha256_bytes(corrected_instrument_path.read_bytes()),
            "mechanical_rule": RAW_TO_OFFICIAL,
            "raw_values_modified": False,
            "rerating_required_for_this_mapping_defect": False,
        },
        "human_reliability": reliability,
        "category_means_by_rater": {
            rater: _category_means(normalized[rater], category_by_item)
            for rater in ("RATER_A", "RATER_B")
        },
        "interpretation": {
            "dual_reference_use": "retain both raters equally; report candidate agreement against each rater and disagreement sensitivity",
            "single_gold_claimed": False,
            "rater_disagreement_invalidates_reviews": False,
            "controlled_probe_limit": "verbosity variants also add supportive framing; controlled results cannot identify pure length preference",
            "formal_primary_metrics_replaced": False,
            "adjudication": "current authority still requires adjudication before final evaluator winner; no adjudicated score is fabricated here",
        },
        "identity": {
            "frozen_items_sha256": _sha256_bytes(item_path.read_bytes()),
            "audit_mapping_sha256": _sha256_bytes(audit_path.read_bytes()),
            "normalized_rater_a_sha256": _sha256_bytes(normalized_outputs["RATER_A"].read_bytes()),
            "normalized_rater_b_sha256": _sha256_bytes(normalized_outputs["RATER_B"].read_bytes()),
            "reference_content_sha256": canonical_sha256(
                {rater: normalized[rater] for rater in ("RATER_A", "RATER_B")}
            ),
        },
        "locks": {
            "RQ1_RS_CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK": "CLOSED",
            "RQ1_CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
            "RQ2_CONFIRMATORY_OUTCOME_LOCK": "CLOSED",
        },
        "calls": {"paid_api": 0, "formal_outcome": 0, "pm_training": 0},
    }
    out = args.authority_dir / "paper1_esc_evaluator_dual_human_reference_20260823_v1.json"
    _write_json(out, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
