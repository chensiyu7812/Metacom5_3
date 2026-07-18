#!/usr/bin/env python3
"""No-API PM-v1.5 semantic runtime and readiness preflight."""

from __future__ import annotations

import argparse
from pathlib import Path

from metacom_pm.config import load_config
from metacom_pm.io import sha256_file, write_json
from metacom_pm.pm_v1_5_semantic import (
    FrozenTransformerSemanticEncoder,
    require_semantic_runtime_contract,
    semantic_encoder_spec_from_config,
)
from metacom_pm.pm_v1_5_step0 import readiness_natural_language_challenge


ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", type=Path, default=ROOT / "configs" / "pm_v1_5.yaml"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "outputs" / "pm_v1_5_semantic_runtime_preflight.json",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    encoder = FrozenTransformerSemanticEncoder.load(
        semantic_encoder_spec_from_config(config)
    )
    semantic_runtime = require_semantic_runtime_contract(config, encoder)
    readiness = readiness_natural_language_challenge(encoder)
    report = {
        "status": "PASS_RUNTIME_WITH_REPORT_ONLY_READINESS_DIAGNOSTIC",
        "protocol": "pm-v1.5-semantic-runtime-preflight-v1",
        "pm_v1_5_config_sha256": sha256_file(args.config),
        "semantic_runtime_status": semantic_runtime["status"],
        "readiness_challenge_status": readiness["status"],
        "semantic_runtime": semantic_runtime,
        "readiness_natural_language_challenge": readiness,
        "api_calls": 0,
        "outcome_labels_used": False,
    }
    write_json(args.out, report)
    print(report)


if __name__ == "__main__":
    main()
