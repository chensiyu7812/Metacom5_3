#!/usr/bin/env python3
"""Finalize the feature surface after a mechanical inverted-boolean gate repair."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import numpy as np  # noqa: E402
from metacom_pm.io import sha256_file, write_json  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-full-dialogue-feature-surface-final-v1"
DIR = ROOT / "outputs/pm_v1_5_v5_4_full_dialogue_feature_surface_20260810"
RAW = DIR / "report.json"
SURFACE = DIR / "feature_surface_private_ids_not_model_features.jsonl"
VECTORS = DIR / "frozen_bge_embedding_views_private.npz"


def main() -> None:
    raw = json.loads(RAW.read_text())
    rows = [json.loads(line) for line in SURFACE.read_text().splitlines() if line.strip()]
    arrays = np.load(VECTORS)
    feature_names = list(rows[0]["model_feature_values"])
    checks = {
        "raw_computation_completed": raw["rows"] == 96,
        "rows_96": len(rows) == 96,
        "24_rows_each_component": Counter(row["component_split_head_only"] for row in rows) == Counter({component: 24 for component in ("MP", "MS", "ME", "RS")}),
        "four_embedding_views_96_by_1024": set(arrays.files) == {"full_dialogue", "latest_user", "prefix", "actual_candidate"} and all(arrays[name].shape == (96, 1024) for name in arrays.files),
        "all_embeddings_finite": all(np.isfinite(arrays[name]).all() for name in arrays.files),
        "all_scalar_features_finite": all(all(np.isfinite(value) for value in row["model_feature_values"].values()) for row in rows),
        "feature_schema_identical": all(list(row["model_feature_values"]) == feature_names for row in rows),
        "construction_assignment_absent": all(not row["construction_assignment_present"] for row in rows),
        "author_or_variant_position_absent": all(not row["author_or_variant_position_present"] for row in rows),
        "response_effect_or_oracle_absent": all(not row["response_effect_or_oracle_present"] for row in rows),
    }
    passed = all(checks.values())
    report = {
        "protocol": PROTOCOL,
        "status": "FULL_DIALOGUE_FEATURE_SURFACE_FINAL_PASS_EFFECT_MANIFEST_MAY_BE_BUILT" if passed else "FEATURE_SURFACE_FINAL_FAIL_NO_EFFECT",
        "checks": checks,
        "mechanical_repair": {
            "old_report_status": raw["status"],
            "old_report_all_substantive_checks_true": all(
                value for key, value in raw["checks"].items()
                if key != "response_effect_or_oracle_read"
            ),
            "bug": "the old aggregation included response_effect_or_oracle_read=False directly in all(checks.values()), making PASS logically impossible when no outcome was read",
            "data_or_feature_value_changed": False,
            "embedding_or_nli_recomputed": False,
            "old_report_sha256": sha256_file(RAW)
        },
        "rows": len(rows),
        "feature_names": feature_names,
        "model_fit_or_selected": False,
        "construction_assignment_used": False,
        "response_effect_or_oracle_read": False,
        "api_calls": 0,
        "artifact_hashes": {"surface": sha256_file(SURFACE), "vectors": sha256_file(VECTORS)},
    }
    write_json(DIR / "report_final.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
