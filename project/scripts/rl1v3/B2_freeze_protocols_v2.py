"""Freeze the v2 evaluation-side protocol identities before any real terminal exists (CPU, no model).

Writes outputs/pm_rl1/v3/B2/protocols_v2_frozen.json + manifest (write-once): checklist template v2
identity and I/H- attribution rules, judge v2 prompt hash, ER-v2 pre-registration (sensitivity grid,
refusal reasons), eval protocol v2 bootstrap, NeedCard writer v2 prompt hash.  v1 identities are
listed next to them; nothing v1 is modified.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.checklist import writer as CW1, writer_v2 as CW2  # noqa: E402
from metacom_pm.rl1v3.evaluate import protocol as EV1, protocol_v2 as EV2  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, object_sha256, sha256_text, write_json_once  # noqa: E402
from metacom_pm.rl1v3.judge import engineering_reward as ER1, engineering_reward_v2 as ER2  # noqa: E402
from metacom_pm.rl1v3.judge import protocol as JP1, protocol_v2 as JP2  # noqa: E402
from metacom_pm.rl1v3.needs import protocol as W1, protocol_v2 as W2  # noqa: E402


def main():
    out = PROJECT / "outputs/pm_rl1/v3/B2"
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True, text=True).stdout.strip()
    rec = dict(
        protocol="pmrl1v3-b2-protocol-freeze-v2", code_head=head, frozen_before_any_real_terminal=True,
        checklist=dict(v2=CW2.writer_identity(), v1=CW1.writer_identity(),
                       I_definition="Resource Misuse / Integrity", I_items=[k for k, _ in CW2.FIXED_I],
                       attribution_rules=list(CW2.ATTRIBUTION_RULES), weights=CW2.WEIGHTS),
        judge=dict(v2=JP2.JUDGE_PROTOCOL, v2_system_sha256=sha256_text(JP2.SYSTEM_PROMPT),
                   v1=JP1.JUDGE_PROTOCOL, v1_system_sha256=sha256_text(JP1.SYSTEM_PROMPT)),
        engineering_reward=dict(v2=ER2.preregistration(), v2_config_sha256=ER2.ERConfigV2().sha256,
                                v1=ER1.PROTOCOL, v1_config_sha256=ER1.ERConfig().sha256),
        evaluation=dict(v2=EV2.EVAL_PROTOCOL, bootstrap=EV2.BOOTSTRAP, metrics=list(EV2.METRICS), v1=EV1.EVAL_PROTOCOL),
        needcard_writer=dict(v2=W2.WRITER_PROTOCOL, v2_prompt_sha256=W2.prompt_sha256(),
                             v1=W1.WRITER_PROTOCOL, v1_prompt_sha256=W1.prompt_sha256()),
        evidence_tier="engineering_only", model_calls=0)
    rec["sha256"] = object_sha256({k: v for k, v in rec.items() if k != "code_head"})
    write_json_once(out / "protocols_v2_frozen.json", rec)
    code = [PROJECT / p for p in ("scripts/rl1v3/B2_freeze_protocols_v2.py", "src/metacom_pm/rl1v3/checklist/writer_v2.py",
                                  "src/metacom_pm/rl1v3/judge/protocol_v2.py", "src/metacom_pm/rl1v3/judge/engineering_reward_v2.py",
                                  "src/metacom_pm/rl1v3/evaluate/protocol_v2.py", "src/metacom_pm/rl1v3/needs/protocol_v2.py")]
    man = build_manifest(task="B2_freeze_protocols_v2", root=PROJECT, inputs={}, outputs=[out / "protocols_v2_frozen.json"],
                         code=code, code_sha=head)
    write_json_once(out / "protocols_v2_frozen.manifest.json", dict(man, model_calls=0, gpu_used=False))
    print(json.dumps(rec, indent=1, ensure_ascii=False)[:1500])


if __name__ == "__main__":
    main()
