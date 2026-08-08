#!/usr/bin/env python3
"""Audit P2R feature identifiability and effective sample support (zero API)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import iter_jsonl, write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_identifiability import audit_identifiability  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rows",
        type=Path,
        default=ROOT / "outputs/pm_v1_5_v5_3_p2r_learning_blueprint_v1/component_rows.jsonl",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "outputs/pm_v1_5_v5_3_feature_identifiability_audit_v1",
    )
    args = parser.parse_args()
    report = audit_identifiability(iter_jsonl(args.rows))
    report["source_rows"] = str(args.rows.relative_to(ROOT))
    write_json(args.out_dir / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
