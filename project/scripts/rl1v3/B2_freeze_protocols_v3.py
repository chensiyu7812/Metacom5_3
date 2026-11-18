"""Freeze the v3 evaluation-side protocols before any real terminal is judged (CPU, no model).

Writes (write-once) under outputs/pm_rl1/v3/B2/:
  attribution_v3/CASES_V2_VS_V3.json  the five programmatic H-/I counterexamples run through the frozen
                                      v2 code and the v3 code, next to the true atomic errors;
  protocols_v3_frozen.json (+ manifest) checklist template v3, judge v3, aggregation v3, ER-v3
                                      pre-registration, NeedCard pilot/audit protocols, terminal registry
                                      and B8e interface; v2/v1 identities listed as kept history.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "tests"))          # programmatic counterexamples (hand-written fixtures)

from metacom_pm.rl1v3 import contracts as K  # noqa: E402
from metacom_pm.rl1v3.checklist import writer_v2 as CW2, writer_v3 as CW3  # noqa: E402
from metacom_pm.rl1v3.evaluate import protocol_v2 as EV2, terminal_registry as TR  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, object_sha256, sha256_text, write_json_once  # noqa: E402
from metacom_pm.rl1v3.judge import aggregate as AG, aggregate_v3 as AG3  # noqa: E402
from metacom_pm.rl1v3.judge import engineering_reward_v2 as ER2, engineering_reward_v3 as ER3  # noqa: E402
from metacom_pm.rl1v3.judge import protocol_v2 as JP2, protocol_v3 as JP3  # noqa: E402
from metacom_pm.rl1v3.needs import pilot as PL, pilot_audit as PA, protocol_v2 as W2  # noqa: E402
from metacom_pm.rl1v3.train import real_instances as RI  # noqa: E402

OUT = PROJECT / "outputs/pm_rl1/v3/B2"


def cases() -> dict:
    import rl1v3_b2_attribution_cases as C
    from rl1v3_wsb_fixtures import context
    from test_rl1v3_b2_checklist_judge import envelope
    env = envelope()
    cl2 = CW2.build(env["needcard"], method_evidence=env["method_evidence"])
    cl3 = CW3.build(env["needcard"], method_evidence=env["method_evidence"])
    turns = context().prefix.turns

    def run2(case, role="J1", **ans):
        i = JP2.JudgeIdentityV2(role=role, model_id="fixture", model_sha256="1" * 64, decode_id="greedy")
        rd = C.ms_reading() if case.get("readings") == "ms" else ()
        return JP2.run(lambda m: C.v2_answer(cl2, **ans), i, turns, C.reply(case["sentence"]), cl2, rd)

    def run3(case, role="J1", **ans):
        i = JP3.JudgeIdentityV3(role=role, model_id="fixture", model_sha256="1" * 64, decode_id="greedy")
        rd = C.ms_reading() if case.get("readings") == "ms" else ()
        return JP3.run(lambda m: C.v3_answer(cl3, **ans), i, turns, C.reply(case["sentence"]), cl3, rd)

    def fu(jr):
        return (sorted(i for i, x in jr.items.items() if x.verdict == "fail"),
                sorted(i for i, x in jr.items.items() if x.verdict == "uncertain"))
    out = {}
    for name, case in C.CASES.items():
        f2, u2 = fu(run2(case, **case["v2"]))
        f3, u3 = fu(run3(case, **case["v3"]))
        truth = C.interval(cl3, case["truth_fail"])
        out[name] = dict(reply=C.reply(case["sentence"]), truth_fail=sorted(case["truth_fail"]), truth_interval=truth,
                         v2=dict(fail=f2, uncertain=u2, interval=C.interval(cl2, f2, u2)),
                         v3=dict(fail=f3, uncertain=u3, interval=C.interval(cl3, f3, u3)))
        out[name]["v2_correct"] = out[name]["v2"]["interval"] == truth
        out[name]["v3_correct"] = out[name]["v3"]["interval"] == truth
    c5 = C.CASE5
    j1, j2 = run2(c5, **c5["v2"]["J1"]), run2(c5, role="J2", **c5["v2"]["J2"])
    v2_int = K.gsc_interval(cl2, AG.item_verdicts(cl2, j1, j2))
    k1, k2 = run3(c5, **c5["v3"]["J1"]), run3(c5, role="J2", **c5["v3"]["J2"])
    d = AG3.attribution_disputes(cl3, k1, k2)
    v = AG3.item_verdicts(cl3, k1, k2)
    out["5_two_judges_different_owner"] = dict(
        reply=C.reply(c5["sentence"]), truth_fail=sorted(c5["truth_fail"]), truth_interval=C.interval(cl3, c5["truth_fail"]),
        v2=dict(gsc_interval=list(v2_int), note="lower bound counts the error twice, upper bound not at all"),
        v3=dict(disputes=d and d[0]["items"], admission=AG3.gsc_admission(cl3, v, d)["status"],
                gsc_interval=list(AG3.gsc_interval(cl3, v, d)), note="pending until human adjudication"),
        v2_correct=False, v3_correct=True)
    return dict(protocol="pmrl1v3-b2-attribution-counterexamples-v1", total_weight=cl3.total_weight, cases=out,
                v2_wrong=sorted(k for k, x in out.items() if not x["v2_correct"]),
                v3_wrong=sorted(k for k, x in out.items() if not x["v3_correct"]),
                fixture="hand-written programmatic examples; no model", evidence_tier="engineering_only")


def main():
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=PROJECT, capture_output=True, text=True).stdout.strip()
    ce = cases()
    write_json_once(OUT / "attribution_v3/CASES_V2_VS_V3.json", ce)
    rec = dict(
        protocol="pmrl1v3-b2-protocol-freeze-v3", code_head=head, frozen_before_any_real_terminal=True,
        reason="v2 H-/I attribution merged distinct errors and double counted one error (CASES_V2_VS_V3.json)",
        counterexamples=dict(v2_wrong=ce["v2_wrong"], v3_wrong=ce["v3_wrong"]),
        checklist=dict(v3=CW3.writer_identity(), v2_kept=CW2.writer_identity(), I_items=list(CW3.I_KINDS),
                       ledger_rules=list(CW3.ATTRIBUTION_RULES), weights=CW3.WEIGHTS, constraint=CW3.CONSTRAINT,
                       unchanged_from_v2=["items", "categories", "weights", "total weight", "evidence", "R text",
                                          "G/S templates"]),
        judge=dict(v3=JP3.JUDGE_PROTOCOL, v3_system_sha256=sha256_text(JP3.SYSTEM_PROMPT), error_kinds=list(JP3.ERROR_KINDS),
                   v2_kept=JP2.JUDGE_PROTOCOL, v2_system_sha256=sha256_text(JP2.SYSTEM_PROMPT)),
        aggregation=dict(v3=AG3.AGGREGATION_PROTOCOL, rule="L7 ownership swap -> human adjudication before GSC"),
        engineering_reward=dict(v3=ER3.preregistration(), v3_config_sha256=ER3.ERConfigV3().sha256,
                                v2_kept=ER2.preregistration()["sha256"],
                                computation_identical_to_v2=dict(primary=ER3.PRIMARY == ER2.PRIMARY,
                                                                 grid=ER3.SENSITIVITY_GRID == ER2.SENSITIVITY_GRID)),
        evaluation=dict(protocol=EV2.EVAL_PROTOCOL, bootstrap=EV2.BOOTSTRAP),
        needcard=dict(writer=W2.WRITER_PROTOCOL, writer_prompt_sha256=W2.prompt_sha256(), pilot=PL.PILOT_PROTOCOL,
                      pilot_limits=PL.LIMITS, pilot_stop_conditions=list(PL.STOP_CONDITIONS), audit=PA.AUDIT_PROTOCOL,
                      audit_checks=PA.CHECKS, audit_evidence_error_gate=PA.EVIDENCE_ERROR_GATE),
        b6e_b8e=dict(terminal_registry=TR.REGISTRY_PROTOCOL, b8e_interface=RI.INTERFACE, arms=list(RI.ARMS)),
        evidence_tier="engineering_only", model_calls=0)
    rec["sha256"] = object_sha256({k: v for k, v in rec.items() if k != "code_head"})
    write_json_once(OUT / "protocols_v3_frozen.json", rec)
    code = [PROJECT / p for p in (
        "scripts/rl1v3/B2_freeze_protocols_v3.py", "src/metacom_pm/rl1v3/checklist/writer_v3.py",
        "src/metacom_pm/rl1v3/judge/protocol_v3.py", "src/metacom_pm/rl1v3/judge/aggregate_v3.py",
        "src/metacom_pm/rl1v3/judge/engineering_reward_v3.py", "src/metacom_pm/rl1v3/needs/pilot.py",
        "src/metacom_pm/rl1v3/needs/pilot_audit.py", "src/metacom_pm/rl1v3/evaluate/terminal_registry.py",
        "src/metacom_pm/rl1v3/train/real_instances.py", "tests/rl1v3_b2_attribution_cases.py")]
    man = build_manifest(task="B2_freeze_protocols_v3", root=PROJECT, inputs={},
                         outputs=[OUT / "protocols_v3_frozen.json", OUT / "attribution_v3/CASES_V2_VS_V3.json"],
                         code=code, code_sha=head)
    write_json_once(OUT / "protocols_v3_frozen.manifest.json", dict(man, model_calls=0, gpu_used=False))
    print(json.dumps(dict(sha256=rec["sha256"], v2_wrong=ce["v2_wrong"], v3_wrong=ce["v3_wrong"],
                          checklist=rec["checklist"]["v3"], er3=rec["engineering_reward"]["v3"]["sha256"]), indent=1))


if __name__ == "__main__":
    main()
