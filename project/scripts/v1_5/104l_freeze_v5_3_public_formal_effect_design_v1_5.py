#!/usr/bin/env python3
"""Analyze the 96-group Q/F pilot and freeze formal effect counts/heads."""

from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import stable_hex, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_public_learnability_analysis import (  # noqa: E402
    COMPONENTS,
    formal_effect_freeze,
    grouped_oof_head_analysis,
)
from metacom_pm.v1_5_v5_3_semantic_ms_retrieval import (  # noqa: E402
    BgeM3Encoder,
    DEFAULT_BGE_M3_SNAPSHOT,
)


PILOT = ROOT / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809"
QF = ROOT / "outputs/pm_v1_5_v5_3_public_qf_development_pilot_20260809"
OUT = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_freeze_20260809"


def _jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    manifest_rows = _jsonl(PILOT / "effect_group_manifest_private.jsonl")
    manifest = {row["effect_group_id"]: row for row in manifest_rows}
    results = _jsonl(QF / "qf_results.jsonl")
    if len(results) != 96 or any(row.get("quality_effect") is None for row in results):
        raise RuntimeError("complete 96-group Q pilot is required")
    if any(row.get("functional") is None for row in results):
        raise RuntimeError("functional diagnostics are incomplete")

    encoder = BgeM3Encoder(DEFAULT_BGE_M3_SNAPSHOT)
    analysis = {}
    for component in COMPONENTS:
        component_results = [row for row in results if row["component"] == component]
        component_manifest = [manifest[row["effect_group_id"]] for row in component_results]
        texts = [
            text
            for row in component_manifest
            for text in (row["current_user_text"], row["candidate_text"])
        ]
        vectors = encoder.encode(texts)
        analysis[component] = grouped_oof_head_analysis(
            component=component,
            result_rows=component_results,
            manifest_by_group=manifest,
            state_vectors=vectors[0::2],
            candidate_vectors=vectors[1::2],
        )
    freeze = formal_effect_freeze(analysis)
    freeze["freeze_identity"] = "v53formal_" + stable_hex(freeze, n=24)
    report = {
        "protocol": "pm-v1.5-v5.3-public-learnability-analysis-v1",
        "status": (
            "ALL_FOUR_DEVELOPMENT_SIGNALS_PASS_FORMAL_EXPANSION_GATE"
            if all(row["development_engineering_signal"] for row in analysis.values())
            else "FORMAL_EXPANSION_BLOCKED"
        ),
        "analysis": analysis,
        "formal_freeze_identity": freeze["freeze_identity"],
        "api_calls": 0,
    }
    write_json(OUT / "learnability_report.json", report)
    write_json(OUT / "formal_effect_freeze.json", freeze)
    write_json(
        ROOT / "data/pm_v1_5_contracts/v5_3_public_formal_effect_freeze_v1.json",
        freeze,
    )
    print(
        {
            "status": report["status"],
            "relative_mse": {key: round(value["relative_mse"], 3) for key, value in analysis.items()},
            "spearman": {key: round(value["oof_spearman"], 3) for key, value in analysis.items()},
            "formal_groups": freeze["formal_groups"],
            "api_calls": 0,
        }
    )


if __name__ == "__main__":
    main()
