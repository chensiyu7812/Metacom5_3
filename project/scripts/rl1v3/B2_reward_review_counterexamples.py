"""Round-8 reward review: write the ten counterexamples (frozen checklist-v3 / judge-v3 / ER-v3, correct
fixture judge answers) to ``outputs/pm_rl1/v3/B2/reward_review/COUNTEREXAMPLES.json``.

CPU only, no model or judge call.  The cases live with the test fixtures (``tests/rl1v3_reward_review_cases.py``)
so the JSON and ``tests/test_rl1v3_reward_review.py`` read the same definitions.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(PROJECT / "src"), str(PROJECT / "tests")]

from metacom_pm.rl1v3.evaluate import marginal_value as MV  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, write_json_once  # noqa: E402
from metacom_pm.rl1v3.judge import engineering_reward_v3 as ER3  # noqa: E402
from rl1v3_reward_review_cases import CASES, run_case  # noqa: E402

OUT = PROJECT / "outputs/pm_rl1/v3/B2/reward_review"


def main():
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True, text=True).stdout.strip()
    rows = [run_case(c) for c in CASES]
    out = dict(protocol="pmrl1v3-reward-review-counterexamples-v1", er_protocol=ER3.PROTOCOL,
               er_preregistration_sha256=ER3.preregistration()["sha256"], marginal_protocol=MV.PROTOCOL,
               marginal_status=MV.STATUS, margin=0.0, judge="fixture answers of a correct judge (not a model)",
               cases=rows, summary={v: [r["id"] for r in rows if r["verdict"] == v] for v in ("ok", "partial", "gap")},
               code_head=head, model_calls=0, gpu_used=False, evidence_tier="engineering_only",
               status="protocol review on synthetic fixtures; says what ER-v3 can see with a perfect judge, "
                      "not how often each case occurs")
    write_json_once(OUT / "COUNTEREXAMPLES.json", out)
    man = build_manifest(task="B2_reward_review", root=PROJECT, inputs={}, outputs=[OUT / "COUNTEREXAMPLES.json"],
                         code=[PROJECT / "scripts/rl1v3/B2_reward_review_counterexamples.py",
                               PROJECT / "tests/rl1v3_reward_review_cases.py",
                               PROJECT / "src/metacom_pm/rl1v3/evaluate/marginal_value.py"], code_sha=head)
    write_json_once(OUT / "manifest.json", dict(man, model_calls=0, gpu_used=False))
    for r in rows:
        print(r["id"], r["verdict"], r["er_effect"], "ideal", r["ideal"], "dER", r["er_value_delta"], r["attribution"])
    print(json.dumps(out["summary"]))


if __name__ == "__main__":
    main()
