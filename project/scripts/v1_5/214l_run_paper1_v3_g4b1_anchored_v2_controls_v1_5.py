#!/usr/bin/env python3
"""Execute G4B1 V2 controls through the frozen raw-first V1 machinery."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.v1_5_g4b_anchored_review_v2 import prompt_messages  # noqa: E402


BASE_PATH = ROOT / "scripts/v1_5/209l_run_paper1_v3_g4b_reviews_v1_5.py"
spec = importlib.util.spec_from_file_location("g4b_v1_raw_first_runner", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load frozen G4B raw-first runner")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)

PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_controls_20260811"


def _surface_maps() -> dict[tuple[str, str, str], dict[str, Any]]:
    result = {}
    for reviewer_id, (_endpoint_key, stem) in base.REVIEWERS.items():
        for item in base.rows(PACKET / f"{stem}_controls.jsonl"):
            result[("CONTROL", reviewer_id, item["review_item_id"])] = item
    return result


base.CONTROL_PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4b1_anchored_v2_control_execution_phase_v1.json"
base.CONFIG = ROOT / "configs/paper1_v3_g4b1_anchored_v2_execution_v1.json"
base.PREFLIGHT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_preflight_20260811"
base.DEFAULT_OUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4b1_anchored_v2_reviews_20260811"
base.STAGE = "paper1_v3_g4b1_anchored_v2_control_review_v1"
base.prompt_messages = prompt_messages
base._surface_maps = _surface_maps


if __name__ == "__main__":
    base.main()
