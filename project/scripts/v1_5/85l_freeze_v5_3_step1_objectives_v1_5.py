#!/usr/bin/env python3
"""Freeze V5.3 Step1 multi-objective estimands before paired outcomes."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import write_json  # noqa: E402
from metacom_pm.v1_5_v5_3_step1_objectives import (  # noqa: E402
    build_step1_objective_freeze,
)


def main() -> None:
    out = ROOT / "outputs/pm_v1_5_v5_3_step1_objective_freeze_v1/contract.json"
    contract = build_step1_objective_freeze()
    write_json(out, contract.model_dump(mode="json"))
    print(contract.model_dump(mode="json"))


if __name__ == "__main__":
    main()
