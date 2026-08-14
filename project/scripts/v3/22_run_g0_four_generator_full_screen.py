#!/usr/bin/env python3
"""Run the full corrected four-configuration G0 screen via the frozen engine."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
BASE_RUNNER_PATH = PROJECT_ROOT / "scripts" / "v3" / "16_run_g0_research_aligned_esc.py"


def _load_base():
    spec = importlib.util.spec_from_file_location("g0_four_generator_base", BASE_RUNNER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen G0 execution engine")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    if "--limit" in sys.argv:
        raise ValueError("the full-screen identity fixes --limit to 24")
    if "--out" not in sys.argv:
        sys.argv.extend([
            "--out",
            str(PROJECT_ROOT / "outputs" / "v3_g0_four_generator_full_screen_v1_20260814"),
        ])
    sys.argv.extend(["--limit", "24"])
    base = _load_base()
    base.CONTRACT_PATH = AUTHORITY_DIR / "g0_four_generator_full_screen_contract_v1.json"
    base.PROMPT_PATH = AUTHORITY_DIR / "g0_research_aligned_supporter_prompt_v1.json"
    base.PREFLIGHT_PATH = AUTHORITY_DIR / "g0_four_generator_full_screen_preflight_v1.json"
    base.MANIFEST_PATH = AUTHORITY_DIR / "g0_research_aligned_screening_manifest_v2.jsonl"
    return int(base.main())


if __name__ == "__main__":
    raise SystemExit(main())
