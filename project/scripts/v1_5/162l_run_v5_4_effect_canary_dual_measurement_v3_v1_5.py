#!/usr/bin/env python3
"""Continue canary measurement after fixing local dynamic-schema registration."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
V2_SCRIPT = ROOT / "scripts/v1_5/161l_run_v5_4_effect_canary_dual_measurement_v2_v1_5.py"
V2_OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v2_20260810"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_dual_measurement_v3_20260810"
PROTOCOL = "pm-v1.5-v5.4-effect-canary-dual-measurement-v3"

spec = importlib.util.spec_from_file_location("v54_canary_measurement_v2", V2_SCRIPT)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load V2 measurement runner")
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)

runner.PROTOCOL = PROTOCOL
runner.OUT = OUT
runner.V1_OUT = V2_OUT
runner.v1.PROTOCOL = PROTOCOL
runner.v1.OUT = OUT

for schema in (runner.v1.QualityBatch, runner.v1.RiskBatch, runner.FunctionBatchV2):
    schema.model_rebuild(_types_namespace=vars(runner.v1))
    schema.model_json_schema()


if __name__ == "__main__":
    carried = runner.seed_exact_valid_carry_forward()
    print(json.dumps({"protocol": PROTOCOL, "exact_valid_calls_carried_forward": carried}, indent=2), flush=True)
    runner.v1.main()
