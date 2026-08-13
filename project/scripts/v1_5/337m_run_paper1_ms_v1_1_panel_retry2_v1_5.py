#!/usr/bin/env python3
"""Fresh-identity wrapper for the unchanged MS V1.1 30-call plan.

The first identity reached the live entry point but started zero provider calls
because NVIDIA_API_KEY was absent.  This wrapper changes only the execution
stage, phase/config paths, and output directory; it delegates call rebuilding
and provider execution to the originally frozen 337l implementation.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ORIGINAL = ROOT / "scripts/v1_5/337l_run_paper1_ms_v1_1_panel_v1_5.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("paper1_ms_v1_1_original_runner", ORIGINAL)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load the frozen MS V1.1 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.PROTOCOL = "pm-v1.5-paper1-ms-v1-1-panel-retry2-live-v1"
    module.STAGE = "paper1_ms_v1_1_panel_retry2_v1"
    module.STAGE_ID = "MS_V1_1_PANEL_EXECUTION_RETRY2"
    module.PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_v1_1_panel_retry2_execution_phase_v1.json"
    module.CONFIG = ROOT / "configs/paper1_ms_v1_1_panel_retry2_execution_v1.json"
    module.OUT = ROOT / "outputs/pm_v1_5_paper1_ms_v1_1_panel_live_retry2_20260813"
    module.main()


if __name__ == "__main__":
    main()
