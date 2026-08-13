#!/usr/bin/env python3
"""Run only the clean-checkout test surface frozen by the V3 authority."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROFILE = PROJECT_ROOT / "data" / "v3_authority" / "v3_active_test_profile_v1.json"
AUTHORITY_TEST = "tests/test_v3_workspace_authority.py"


def main() -> int:
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    tests = profile["tests"]
    missing = [path for path in tests if not (PROJECT_ROOT / path).is_file()]
    if missing:
        print(f"active V3 profile refers to missing tests: {missing}", file=sys.stderr)
        return 2
    command = [sys.executable, "-m", "pytest", "-q", *tests, AUTHORITY_TEST]
    return subprocess.run(command, cwd=PROJECT_ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
